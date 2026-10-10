"""Phase 3 of the formal head search calibration: the perception operating point policy.

Design section 7.2 puts the four perception values first in the dependency order - "each candidate's
perception operating point is calibrated and frozen, then the frozen candidates are evaluated" - and
section 7.1 fixes both the search (`min_confidence`, `tracking_iou`, `min_bbox_aspect` and
`min_area_px2` are searched jointly on val and calibration episodes so no parameter order can influence
the result) and the constraint (`no_cup` scenes must yield no candidate at all). This module implements
the policy half of that phase, the half that must not be able to fit the verdict after the fact:

* the selection rule is recorded **before** any measurement flight is admitted; a rule record created -
  or replaced - once measurements exist is refused with `CAL_RULE_AFTER_MEASUREMENT`;
* the search runs only over the head-domain measurements of the splits the rule declares for selection
  (head val plus the calibration episodes), and any frame of another split - above all a held-out frame -
  is refused with `CAL_SPLIT_LEAK`; held-out measurements may be *reported* and never consumed;
* the choice follows the chain the campaign declared before it measured (ledger HS-248/HS-265): highest
  f1, then highest recall, then lowest `min_confidence`, then the earliest declared grid point;
* a chosen point that yields even one false candidate on an empty scene is refused with
  `CAL_NO_CUP_FALSE_CANDIDATE` rather than shipped;
* re-evaluating the same inputs produces the same chosen point and the same grid ordering.

The measurements are records the phase reads, never produces: each frame carries a `split`, a `domain`,
its ground-truth centres under `truth`, and one list of detections per candidate under `detections`
(HS-245: the value is an ordered collection whose length is the detection count, never a mapping whose
keys could be miscounted as detections). A detection carries at least `x`, `y` and `conf`; a detection
that also declares its bbox (`w`/`h`, `bbox`, or `area_px2`) lets the three non-confidence values be
re-applied to the record, and one that declares no bbox is judged by the confidence floor alone.

Ground-truth matching is the gate's, not a second opinion: the greedy nearest unused ground-truth centre
within `match_radius_px` (default 8.0), and the same bbox-centre p95 index, exactly as
`cli/evaluate_head_search_yolo_candidates.py::_episode_cells` computes them.

Nothing here starts ROS, MuJoCo, CUDA or a detector, and nothing is written unless the caller passes an
explicit `output_path`; the phase document is the only file this module ever creates.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.perception_benchmark.contracts import OperatingPoint, canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_calibration_operating_point"
PHASE = "perception_operating_point"
RULE_KIND = "head_search_selection_rule"

#: the three refusals phase 3 owns, exactly as the plan fixes their spelling
CAL_RULE_AFTER_MEASUREMENT = "CAL_RULE_AFTER_MEASUREMENT"
CAL_SPLIT_LEAK = "CAL_SPLIT_LEAK"
CAL_NO_CUP_FALSE_CANDIDATE = "CAL_NO_CUP_FALSE_CANDIDATE"
REFUSAL_CODES = (CAL_RULE_AFTER_MEASUREMENT, CAL_SPLIT_LEAK, CAL_NO_CUP_FALSE_CANDIDATE)

#: the chain the campaign declared before it measured (HS-248/HS-265), in the order it is applied
TIE_BREAK_CHAIN = (
    "highest f1",
    "highest recall",
    "lowest min_confidence",
    "earliest declared grid point",
)

SELECTION_RULE = (
    "among the declared candidate points, choose the highest measured f1 over the head-domain "
    "measurements of the splits declared for selection (head val plus the calibration episodes); "
    "tie-break on the highest recall; tie-break on the lowest min_confidence; tie-break on the earliest "
    "point in the rule's declared grid order. Held-out measurements are reported only and never enter "
    "the choice."
)

#: the values a candidate point is, and the order the filter chain re-applies them in: the confidence
#: floor first (HS-265: filtering recorded detections by confidence is equivalent to re-running predict
#: at that confidence), then the tracker's IoU as a re-suppression of the recorded list, then the
#: geometric floors the production postprocess applies to the tracker's output
POINT_KEYS = ("min_confidence", "min_bbox_aspect", "min_area_px2", "tracking_iou")
FILTER_CHAIN = ("min_confidence", "tracking_iou", "min_area_px2", "min_bbox_aspect")

#: the empty scene the no-cup constraint is about, exactly as the gate reads it
EMPTY_SCENARIOS = (None, "no_cup")

DEFAULT_DOMAIN = "head"
DEFAULT_MATCH_RADIUS_PX = 8.0

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CalibrationOperatingPointRefused(CalibrationInputsRefused):
    """A phase-3 refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _frames(measurements) -> list[Mapping]:
    """One list of recorded frames, or a plain `ValueError` for a caller that passed something else."""

    if isinstance(measurements, (str, bytes)) or not isinstance(measurements, Sequence):
        raise ValueError("measurements must be a sequence of recorded frames")
    frames = []
    for frame in measurements:
        if not isinstance(frame, Mapping):
            raise ValueError("every measurement must be a recorded frame")
        frames.append(frame)
    return frames


def _candidate_id(candidate_id) -> str:
    if type(candidate_id) is not str or not candidate_id:
        raise ValueError("a candidate id must be a non-empty name")
    return candidate_id


def _detections(frame: Mapping, candidate_id: str) -> list[Mapping]:
    """One candidate's detections on one frame, as the ordered collection the contract fixes.

    An absent measurement is not an empty detection list, and a mapping is not a list of detections -
    `len()` of its keys once produced 48 phantom false candidates (HS-245), so both are caller errors
    rather than silently-coerced counts.
    """

    detections = frame.get("detections")
    if not isinstance(detections, Mapping) or candidate_id not in detections:
        raise ValueError(
            f"the frame records no measurement for candidate {candidate_id!r}; an absent measurement "
            "is not an empty detection list"
        )
    recorded = detections[candidate_id]
    if isinstance(recorded, (str, bytes)) or not isinstance(recorded, Sequence):
        raise ValueError(
            f"the detections of candidate {candidate_id!r} must be an ordered collection of detection "
            "records, never a mapping whose keys would be miscounted as detections (HS-245)"
        )
    return list(recorded)


def _confidence(detection) -> float:
    if not isinstance(detection, Mapping):
        raise ValueError("every detection must be a record")
    conf = detection.get("conf")
    if not _finite(conf):
        raise ValueError("a detection record declares no finite conf")
    return float(conf)


def _centre(record, name: str) -> tuple[float, float]:
    if not isinstance(record, Mapping):
        raise ValueError(f"every {name} must be a record carrying x and y")
    x, y = record.get("x"), record.get("y")
    if not (_finite(x) and _finite(y)):
        raise ValueError(f"a {name} record declares no finite x/y")
    return float(x), float(y)


def _match_radius(frame: Mapping) -> float:
    radius = frame.get("match_radius_px", DEFAULT_MATCH_RADIUS_PX)
    if not _finite(radius) or float(radius) < 0.0:
        raise ValueError("match_radius_px must be finite and non-negative")
    return float(radius)


def _box(detection: Mapping) -> tuple[float, float, float, float] | None:
    """The detection's own bbox from the width and height it declares, or `None` when it declares none."""

    width, height = detection.get("w"), detection.get("h")
    if not (_finite(width) and _finite(height)) or float(width) <= 0.0 or float(height) <= 0.0:
        return None
    x, y = _centre(detection, "detection")
    half_width, half_height = float(width) / 2.0, float(height) / 2.0
    return (x - half_width, y - half_height, x + half_width, y + half_height)


def _iou(left, right) -> float:
    """Intersection over union of two declared boxes; a box that was not declared overlaps nothing."""

    if left is None or right is None:
        return 0.0
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (left[2] - left[0]) * (left[3] - left[1])
    union += (right[2] - right[0]) * (right[3] - right[1]) - intersection
    return intersection / union if union > 0.0 else 0.0


def _geometry(detection: Mapping) -> tuple[float | None, float | None]:
    """The `(area_px2, aspect)` the detection's record supports, each `None` when it is undeclared.

    The aspect is height over width, the convention the repository's own formula layer uses for a cup
    bbox (`pick_place_calibration_measurement_formulas._aspect`), so a floor of 1.15 keeps cups and drops wide clutter.
    """

    width, height = detection.get("w"), detection.get("h")
    bbox = detection.get("bbox")
    if isinstance(bbox, Mapping):
        corners = (bbox.get("x1"), bbox.get("y1"), bbox.get("x2"), bbox.get("y2"))
    elif isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes)) and len(bbox) == 4:
        corners = tuple(bbox)
    else:
        corners = ()
    if corners and all(_finite(corner) for corner in corners):
        if not _finite(width):
            width = float(corners[2]) - float(corners[0])
        if not _finite(height):
            height = float(corners[3]) - float(corners[1])
    area = detection.get("area_px2")
    if _finite(width) and _finite(height) and float(width) > 0.0 and float(height) > 0.0:
        if not _finite(area):
            area = float(width) * float(height)
        return float(area), float(height) / float(width)
    return (float(area) if _finite(area) else None), None


def _filter_frame(detections: Sequence[Mapping], point: Mapping) -> tuple[list[Mapping], int]:
    """Apply one point to one frame's recorded detections and return the survivors.

    The chain is the pipeline's own order: the confidence floor, then the tracker's IoU as a
    re-suppression of the recorded list (non-maximum suppression suppresses a box when a higher-scoring
    box overlaps it by **more** than the threshold, and it is monotone in the threshold, so
    re-suppressing a record at a threshold at or below the one it was made with yields what the pipeline
    would have produced), then the geometric floors on the survivors. A detection that declares no
    bbox has no geometry to compare, so it can neither suppress nor be suppressed by the IoU step and
    cannot be judged by the floors; the second return value counts those detections so a cell can say
    how much of the record the geometric floors could not see.
    """

    threshold = float(point["tracking_iou"])
    survivors: list[Mapping] = []
    for detection in sorted(detections, key=lambda record: -_confidence(record)):
        if _confidence(detection) < float(point["min_confidence"]):
            continue
        box = _box(detection)
        if any(_iou(box, _box(kept)) > threshold for kept in survivors):
            continue
        survivors.append(detection)
    kept = []
    without_geometry = 0
    for detection in survivors:
        area, aspect = _geometry(detection)
        if area is None and aspect is None:
            without_geometry += 1
        if area is not None and area < float(point["min_area_px2"]):
            continue
        if aspect is not None and aspect < float(point["min_bbox_aspect"]):
            continue
        kept.append(detection)
    return kept, without_geometry


def _p95(offsets: list[float], frames: Sequence[Mapping]) -> float | None:
    """The gate's p95 index over the matched centre offsets.

    The gate records `inf` when nothing matched although the frames hold objects - no evidence is not a
    perfect result. A phase document has to stay strict JSON, so the same statement is recorded as
    `None` here.
    """

    if offsets:
        offsets.sort()
        return offsets[min(len(offsets) - 1, int(round(0.95 * (len(offsets) - 1))))]
    if any((frame.get("truth") or []) for frame in frames):
        return None
    return 0.0


def _metrics(frames: Sequence[Mapping], candidate_id: str, point: Mapping) -> dict:
    """One point's cells over one set of frames, with the gate's matching and counting rules."""

    true_positive = false_positive = false_negative = 0
    offsets: list[float] = []
    detections_kept = 0
    without_geometry = 0
    for frame in frames:
        kept, unmeasured = _filter_frame(_detections(frame, candidate_id), point)
        detections_kept += len(kept)
        without_geometry += unmeasured
        radius = _match_radius(frame)
        truths = list(frame.get("truth") or [])
        matched: set[int] = set()
        for detection in kept:
            centre = _centre(detection, "detection")
            best, best_distance = None, None
            for index, truth in enumerate(truths):
                if index in matched:
                    continue
                distance = math.dist(centre, _centre(truth, "truth"))
                if best_distance is None or distance < best_distance:
                    best, best_distance = index, distance
            if best is not None and float(best_distance) <= radius:
                matched.add(best)
                offsets.append(float(best_distance))
                true_positive += 1
            else:
                false_positive += 1
        false_negative += len(truths) - len(matched)
    precision = (
        true_positive / (true_positive + false_positive) if true_positive or false_positive else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive or false_negative else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "bbox_center_p95_px": _p95(offsets, frames),
        "frame_count": len(frames),
        "detections_kept": detections_kept,
        "detections_without_geometry": without_geometry,
    }


def _empty_scene_count(frames: Sequence[Mapping], candidate_id: str, point: Mapping) -> dict:
    """Count the point's detections on frames that hold no object, from the records (HS-245)."""

    total = 0
    checked = 0
    for frame in frames:
        if frame.get("truth"):
            continue
        if frame.get("scenario") not in EMPTY_SCENARIOS:
            continue
        checked += 1
        kept, _ = _filter_frame(_detections(frame, candidate_id), point)
        total += len(kept)
    return {"frames_checked": checked, "no_cup_false_candidates": total}


def normalise_operating_points(points) -> tuple[dict, ...]:
    """The declared grid: one `OperatingPoint` per entry, in the declared order, without duplicates.

    The four values are validated by the repository's own `OperatingPoint` contract rather than by a
    second copy of its rules. A malformed or duplicated point is a caller bug and raises a plain
    `ValueError` without a refusal code, so it can never be mistaken for one of the three phase-3
    refusals.
    """

    if isinstance(points, (str, bytes)) or not isinstance(points, Sequence) or not points:
        raise ValueError("candidate points must be a non-empty sequence of operating points")
    normalised: list[dict] = []
    for point in points:
        try:
            document = OperatingPoint.from_document(point).to_document()
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"a candidate point must be the four operating values: {error}"
            ) from error
        if document in normalised:
            raise ValueError(f"the candidate point {point} is declared twice")
        normalised.append(document)
    return tuple(normalised)


def _declared_splits(name: str, value) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ValueError(f"{name} must be a non-empty sequence of split names")
    splits: list[str] = []
    for split in value:
        if type(split) is not str or not split:
            raise ValueError(f"{name} must name every split")
        if split in splits:
            raise ValueError(f"{name} declares {split!r} twice")
        splits.append(split)
    return tuple(splits)


def _binding_arguments(generation, measurement_plan_sha256) -> None:
    if generation is not None and (type(generation) is not str or not generation):
        raise ValueError("generation must be a non-empty name when it is given")
    if measurement_plan_sha256 is not None and (
        type(measurement_plan_sha256) is not str
        or _SHA256.fullmatch(measurement_plan_sha256) is None
    ):
        raise ValueError("measurement_plan_sha256 must be a sha256 digest when it is given")


def record_selection_rule(
    *,
    points,
    selection_splits,
    held_out_splits,
    measurements_admitted: int = 0,
    existing_rule=None,
    domain: str = DEFAULT_DOMAIN,
    generation=None,
    measurement_plan_sha256=None,
) -> dict:
    """Record the search grid and the selection rule **before** its measurement, or refuse.

    `measurements_admitted` is the count of measurement flights the run had already admitted when this
    record was created (the admission and measurement ledger of phase 1 knows it). Anything but zero
    refuses with `CAL_RULE_AFTER_MEASUREMENT`: a rule that appears once measurements exist - whether it
    is the first record or a replacement of an earlier one - is exactly the rule the design forbids,
    because nothing then stops it from having been picked to fit the numbers.

    The returned record carries its own digest, so a later phase can cite one identity for the rule that
    chose the point. A replacement is permitted while no measurement exists yet and records the digest
    it replaces; `points` keeps the declared order, which is the last tie-break of the chain.
    """

    if type(measurements_admitted) is not int or measurements_admitted < 0:
        raise ValueError("measurements_admitted must be a non-negative count")
    if measurements_admitted:
        raise CalibrationOperatingPointRefused(
            CAL_RULE_AFTER_MEASUREMENT,
            f"{measurements_admitted} measurement flights were already admitted when this rule record "
            "was created, so the rule would have been written after its measurement instead of before",
        )
    declared_points = normalise_operating_points(points)
    selection = _declared_splits("selection_splits", selection_splits)
    held_out = _declared_splits("held_out_splits", held_out_splits)
    overlap = sorted(set(selection) & set(held_out))
    if overlap:
        raise ValueError(
            f"the splits {overlap} are declared both for selection and as held-out, so calibration and "
            "held-out would mix"
        )
    if type(domain) is not str or not domain:
        raise ValueError("domain must be a non-empty name")
    _binding_arguments(generation, measurement_plan_sha256)
    replaces: str | None = None
    if existing_rule is not None:
        if not isinstance(existing_rule, Mapping):
            raise ValueError("existing_rule must be a rule record this module made")
        replaces = existing_rule.get("rule_sha256")
        if type(replaces) is not str or _SHA256.fullmatch(replaces) is None:
            raise ValueError("existing_rule must be a rule record this module made")
        if existing_rule.get("measurements_admitted"):
            raise CalibrationOperatingPointRefused(
                CAL_RULE_AFTER_MEASUREMENT,
                "the rule being replaced was itself recorded after measurements were admitted",
            )
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": RULE_KIND,
        "phase": PHASE,
        "domain": domain,
        "selection_splits": list(selection),
        "held_out_splits": list(held_out),
        "points": [dict(point) for point in declared_points],
        "point_count": len(declared_points),
        "recorded_before_measurement": True,
        "measurements_admitted": 0,
        "selection_rule": SELECTION_RULE,
        "tie_break_chain": list(TIE_BREAK_CHAIN),
        "generation": generation,
        "measurement_plan_sha256": measurement_plan_sha256,
        "replaces_rule_sha256": replaces,
    }
    return {**body, "rule_sha256": canonical_sha256(body)}


def _rule_parts(rule) -> dict:
    """Validate one rule record and return the pieces every later step reads.

    A record whose digest does not cover its own body, or which claims the rule was not written before
    its measurement, is a caller bug (`ValueError`); a well-formed record that admits measurements were
    already taken refuses with `CAL_RULE_AFTER_MEASUREMENT`, so a doctored document cannot talk the
    phase out of the ordering the design fixes.
    """

    if not isinstance(rule, Mapping):
        raise ValueError("the rule must be a record made by record_selection_rule")
    body = {key: value for key, value in rule.items() if key != "rule_sha256"}
    digest = rule.get("rule_sha256")
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        raise ValueError("the rule record does not carry its own digest")
    if canonical_sha256(body) != digest:
        raise ValueError("the rule record's digest does not cover its own body")
    if rule.get("recorded_before_measurement") is not True:
        raise ValueError(
            "the rule record does not record that it was written before its measurement"
        )
    if rule.get("measurements_admitted") != 0:
        raise CalibrationOperatingPointRefused(
            CAL_RULE_AFTER_MEASUREMENT,
            f"the rule record admits {rule.get('measurements_admitted')!r} measurement flights before "
            "it was written, so it was recorded after its measurement",
        )
    points = normalise_operating_points(rule.get("points"))
    selection = _declared_splits("selection_splits", rule.get("selection_splits"))
    held_out = _declared_splits("held_out_splits", rule.get("held_out_splits"))
    overlap = sorted(set(selection) & set(held_out))
    if overlap:
        raise ValueError(f"the rule declares the splits {overlap} for selection and as held-out")
    domain = rule.get("domain", DEFAULT_DOMAIN)
    if type(domain) is not str or not domain:
        raise ValueError("the rule's domain must be a non-empty name")
    return {
        "rule": dict(rule),
        "rule_sha256": digest,
        "points": points,
        "selection_splits": selection,
        "held_out_splits": held_out,
        "domain": domain,
    }


def check_split_isolation(*, rule, measurements) -> dict:
    """Refuse any frame whose split the rule does not declare for selection: `CAL_SPLIT_LEAK`.

    Calibration and held-out measurements must never mix. A held-out frame offered to selection is
    refused by name, an undeclared split is refused, and a frame that declares no split at all is
    refused too - it cannot be shown to belong to a selection split, and treating it as one would be
    exactly the leak this check exists to stop. The returned record counts what the rule admitted.
    """

    parts = _rule_parts(rule)
    frames = _frames(measurements)
    per_split: dict[str, int] = {}
    for frame in frames:
        split = frame.get("split")
        if type(split) is not str or not split:
            raise CalibrationOperatingPointRefused(
                CAL_SPLIT_LEAK,
                "a measurement frame declares no split, so it cannot be shown to belong to a split the "
                "rule declares for selection",
            )
        if split in parts["held_out_splits"]:
            raise CalibrationOperatingPointRefused(
                CAL_SPLIT_LEAK,
                f"a {split!r} measurement frame was offered to selection; held-out measurements are "
                "reported only and never consumed for the choice",
            )
        if split not in parts["selection_splits"]:
            raise CalibrationOperatingPointRefused(
                CAL_SPLIT_LEAK,
                f"a measurement frame declares the split {split!r}, which the rule does not declare for "
                f"selection {list(parts['selection_splits'])}",
            )
        per_split[split] = per_split.get(split, 0) + 1
    return {
        "frames": len(frames),
        "per_split": {split: per_split.get(split, 0) for split in parts["selection_splits"]},
        "selection_splits": list(parts["selection_splits"]),
        "held_out_splits": list(parts["held_out_splits"]),
        "held_out_frames": 0,
    }


def _consumed_frames(frames: Sequence[Mapping], parts: Mapping) -> list[Mapping]:
    """The frames the rule admits for selection: a selection split and the rule's own domain."""

    return [
        frame
        for frame in frames
        if frame.get("split") in parts["selection_splits"]
        and frame.get("domain") == parts["domain"]
    ]


def evaluate_operating_point_grid(*, rule, measurements, candidate_id) -> dict:
    """Measure every declared point on the selection measurements and return the whole grid.

    The grid keeps the rule's declared order, which is what makes the last tie-break of the chain
    meaningful and the re-evaluation deterministic. Each cell carries the point, its pooled counts and
    metrics over both selection splits, the same metrics per split, how many detections survived, how
    many of them the geometric floors could not judge, and the empty-scene count the no-cup constraint
    is about. A frame of an undeclared or held-out split refuses the whole grid with `CAL_SPLIT_LEAK`.
    """

    parts = _rule_parts(rule)
    frames = _frames(measurements)
    isolation = check_split_isolation(rule=rule, measurements=frames)
    candidate = _candidate_id(candidate_id)
    consumed = _consumed_frames(frames, parts)
    if not consumed:
        raise ValueError(
            f"no {parts['domain']} measurement of the selection splits "
            f"{list(parts['selection_splits'])} was supplied, so no point can be measured"
        )
    geometry_bearing = sum(
        1
        for frame in consumed
        for detection in _detections(frame, candidate)
        if _geometry(detection) != (None, None)
    )
    filters = ["min_confidence"] if not geometry_bearing else list(FILTER_CHAIN)
    cells = []
    for index, point in enumerate(parts["points"]):
        pooled = _metrics(consumed, candidate, point)
        empty = _empty_scene_count(consumed, candidate, point)
        cells.append(
            {
                "grid_index": index,
                "point": dict(point),
                **pooled,
                **empty,
                "clean_on_empty_scenes": empty["no_cup_false_candidates"] == 0,
                "filters_reapplied": list(filters),
                "splits": {
                    split: _metrics(
                        [frame for frame in consumed if frame.get("split") == split],
                        candidate,
                        point,
                    )
                    for split in parts["selection_splits"]
                },
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "rule_sha256": parts["rule_sha256"],
        "candidate_id": candidate,
        "domain": parts["domain"],
        "selection_splits": list(parts["selection_splits"]),
        "held_out_splits": list(parts["held_out_splits"]),
        "cells": cells,
        "grid_sha256": canonical_sha256(cells),
        "filters_reapplied": list(filters),
        "geometry_bearing_detections": geometry_bearing,
        "measurements_consumed": {
            "total": len(consumed),
            "per_split": {
                split: sum(1 for frame in consumed if frame.get("split") == split)
                for split in parts["selection_splits"]
            },
        },
        "split_isolation": isolation,
    }


def _grid_cells(grid) -> list[Mapping]:
    if not isinstance(grid, Mapping) or not isinstance(grid.get("cells"), Sequence):
        raise ValueError("the grid must be the document evaluate_operating_point_grid returned")
    cells = list(grid["cells"])
    if not cells:
        raise ValueError("the grid holds no cell, so there is nothing to choose from")
    return cells


def _ties_broken_by(cells: Sequence[Mapping], chosen: int) -> str:
    winner = cells[chosen]
    tied_on_f1 = [cell for cell in cells if cell["f1"] == winner["f1"]]
    if len(tied_on_f1) == 1:
        return "f1"
    tied_on_recall = [cell for cell in tied_on_f1 if cell["recall"] == winner["recall"]]
    if len(tied_on_recall) == 1:
        return "recall"
    confidence = winner["point"]["min_confidence"]
    tied_on_confidence = [
        cell for cell in tied_on_recall if cell["point"]["min_confidence"] == confidence
    ]
    if len(tied_on_confidence) == 1:
        return "min_confidence"
    return "declared_order"


def choose_operating_point(*, rule, grid) -> dict:
    """Choose one cell with the chain the campaign declared, and name the key that decided it.

    The chain is applied as one ordered key - highest f1, highest recall, lowest `min_confidence` - and
    a tie that survives all three goes to the earliest point in the rule's declared grid order, which is
    the only remaining deterministic answer. The grid must be this rule's own, so a cell measured under
    another grid can never be chosen here.
    """

    parts = _rule_parts(rule)
    if isinstance(grid, Mapping) and grid.get("rule_sha256") not in (None, parts["rule_sha256"]):
        raise ValueError("the grid was measured under another rule record")
    cells = _grid_cells(grid)
    if len(cells) != len(parts["points"]):
        raise ValueError(
            f"the grid holds {len(cells)} cells but the rule declares {len(parts['points'])} points"
        )
    chosen = min(
        range(len(cells)),
        key=lambda index: (
            -cells[index]["f1"],
            -cells[index]["recall"],
            cells[index]["point"]["min_confidence"],
            index,
        ),
    )
    return {
        "tie_break_chain": list(TIE_BREAK_CHAIN),
        "ties_broken_by": _ties_broken_by(cells, chosen),
        "chosen_point": dict(cells[chosen]["point"]),
        "chosen_index": chosen,
        "chosen_cell": cells[chosen],
    }


def measure_no_cup_false_candidates(*, rule, measurements, candidate_id, point) -> dict:
    """Measure one point's false candidates on the empty scenes of the selection measurements.

    The count is the gate's own rule - a frame whose `truth` is empty and whose `scenario` is absent or
    `no_cup` - applied to the detections the point lets through, so the constraint design section 7.1
    puts on `min_confidence` (`no_cup` yields no candidate) is measured rather than declared.
    """

    parts = _rule_parts(rule)
    frames = _frames(measurements)
    check_split_isolation(rule=rule, measurements=frames)
    candidate = _candidate_id(candidate_id)
    consumed = _consumed_frames(frames, parts)
    if not consumed:
        raise ValueError(
            f"no {parts['domain']} measurement of the selection splits "
            f"{list(parts['selection_splits'])} was supplied, so the empty scenes cannot be checked"
        )
    declared = normalise_operating_points((point,))[0]
    record = _empty_scene_count(consumed, candidate, declared)
    return {
        "candidate_id": candidate,
        "point": declared,
        "clean": record["no_cup_false_candidates"] == 0,
        **record,
    }


def _refuse_a_dirty_point(guard: Mapping) -> None:
    if guard["clean"]:
        return
    raise CalibrationOperatingPointRefused(
        CAL_NO_CUP_FALSE_CANDIDATE,
        f"the chosen point {guard['point']} yields {guard['no_cup_false_candidates']} false "
        f"candidate(s) on {guard['frames_checked']} empty-scene frame(s), and design section 7.1 "
        "requires no_cup to yield none",
    )


def select_operating_point(*, rule, measurements, candidate_id) -> dict:
    """Select the operating point: isolate the splits, measure the grid, choose, guard the empty scenes.

    The order is the design's: the rule already exists, the measurements must belong to the splits it
    declares, the grid is measured on them, the declared chain chooses a point, and that point is
    refused outright if it produces a single false candidate on an empty scene.
    """

    grid = evaluate_operating_point_grid(
        rule=rule, measurements=measurements, candidate_id=candidate_id
    )
    choice = choose_operating_point(rule=rule, grid=grid)
    guard = measure_no_cup_false_candidates(
        rule=rule,
        measurements=measurements,
        candidate_id=candidate_id,
        point=choice["chosen_point"],
    )
    _refuse_a_dirty_point(guard)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "candidate_id": grid["candidate_id"],
        "domain": grid["domain"],
        "rule_sha256": grid["rule_sha256"],
        "selection_rule": SELECTION_RULE,
        "selection_splits": grid["selection_splits"],
        **choice,
        "grid": grid["cells"],
        "grid_sha256": grid["grid_sha256"],
        "filters_reapplied": grid["filters_reapplied"],
        "measurements_consumed": grid["measurements_consumed"],
        "split_isolation": grid["split_isolation"],
        "no_cup_guard": guard,
    }


def report_held_out_measurements(*, rule, measurements, candidate_id, point) -> dict:
    """Report the chosen point's held-out figures without ever letting them enter the choice.

    Only the rule's declared held-out splits are consumed here, and the record says so
    (`consumed_for_selection: False`), because ledger HS-265 is explicit that held-out data already seen
    by a reviewer is a re-check and not an unbiased validation - and because a selection that read it
    would no longer be the rule that was declared before the measurement. A frame of an undeclared split
    is refused with `CAL_SPLIT_LEAK`; frames of the selection splits are already the selection's own and
    are ignored here. No held-out measurement at all is reported as unmeasured rather than as zero.
    """

    parts = _rule_parts(rule)
    frames = _frames(measurements)
    declared_splits = tuple(parts["selection_splits"]) + tuple(parts["held_out_splits"])
    for frame in frames:
        split = frame.get("split")
        if type(split) is not str or split not in declared_splits:
            raise CalibrationOperatingPointRefused(
                CAL_SPLIT_LEAK,
                f"a measurement frame declares the split {split!r}, which the rule declares neither for "
                f"selection {list(parts['selection_splits'])} nor as held-out "
                f"{list(parts['held_out_splits'])}",
            )
    candidate = _candidate_id(candidate_id)
    declared = normalise_operating_points((point,))[0]
    held_out = [
        frame
        for frame in frames
        if frame.get("split") in parts["held_out_splits"] and frame.get("domain") == parts["domain"]
    ]
    splits = {
        split: _metrics(
            [frame for frame in held_out if frame.get("split") == split], candidate, declared
        )
        for split in parts["held_out_splits"]
        if any(frame.get("split") == split for frame in held_out)
    }
    if not held_out:
        return {
            "candidate_id": candidate,
            "point": declared,
            "held_out_splits": list(parts["held_out_splits"]),
            "measured": False,
            "frame_count": 0,
            "splits": {},
            "consumed_for_selection": False,
            "reason": "no held-out measurement of the declared held-out splits was supplied",
        }
    return {
        "candidate_id": candidate,
        "point": declared,
        "held_out_splits": list(parts["held_out_splits"]),
        "measured": True,
        "frame_count": len(held_out),
        "splits": splits,
        "consumed_for_selection": False,
        **_metrics(held_out, candidate, declared),
    }


def validate_head_search_calibration_operating_point(
    *, rule, measurements, candidate_id, held_out_measurements=(), output_path=None
) -> dict:
    """Produce phase 3's document: the rule, the grid, the chosen point, the guard and the held-out report.

    The rule record is required rather than made here, so the ordering the design fixes is visible in
    the API: `record_selection_rule` refuses to write a rule once a measurement exists, this phase
    refuses a record that says it was written after one, and neither will accept a hand-rolled rule.
    Held-out measurements are reported after the choice has been made and can never change it. When
    `output_path` is given the document is written there and nowhere else; without it nothing is written.
    """

    selection = select_operating_point(
        rule=rule, measurements=measurements, candidate_id=candidate_id
    )
    held_out = report_held_out_measurements(
        rule=rule,
        measurements=held_out_measurements,
        candidate_id=candidate_id,
        point=selection["chosen_point"],
    )
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "candidate_id": selection["candidate_id"],
        "domain": selection["domain"],
        "rule": dict(rule),
        "rule_sha256": selection["rule_sha256"],
        "selection_rule": selection["selection_rule"],
        "tie_break_chain": selection["tie_break_chain"],
        "ties_broken_by": selection["ties_broken_by"],
        "grid": selection["grid"],
        "grid_sha256": selection["grid_sha256"],
        "chosen_point": selection["chosen_point"],
        "chosen_index": selection["chosen_index"],
        "chosen_cell": selection["chosen_cell"],
        "filters_reapplied": selection["filters_reapplied"],
        "measurements_consumed": selection["measurements_consumed"],
        "split_isolation": selection["split_isolation"],
        "no_cup_guard": selection["no_cup_guard"],
        "held_out_report": held_out,
        "held_out_consumed_for_selection": False,
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document
