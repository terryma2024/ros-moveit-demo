"""The installed producers of phase 3's two inputs: the selection rule and its measurement frames.

Phase 3 of the formal head search calibration (`head_search_operating_point`) consumes two documents and
produces neither: a rule record that must exist **before** any measurement flight is admitted, and the
frames the rule is applied to. Until this module existed, neither had a producer in the installed
program (ledger HS-309), so a real `run` could not get past the CLI entry.

The two producers are deliberately separate, because the ordering is the whole point of the rule:

* `record_selection_rule_documents` writes the rule records of the domains it is asked for (the head
  domain's is the one the run declares under `--selection-rule`) from the sealed production search
  configuration alone. It refuses to write at all when the directory its measurement will own already
  exists, so a rule can never be written after the measurement it is supposed to precede; the phase-3
  module refuses the same thing a second time from the other side (`CAL_RULE_AFTER_MEASUREMENT`).
* `measure_operating_point_measurements` measures the frames the rule consumes and then has the
  installed phase 3 itself select the point of every candidate. It measures the head val split and the
  calibration episodes for the head domain, and the same two splits for the task domain, for the three
  frozen candidates: the campaign's grid of record is an 18-cell `(min_confidence, tracker.iou)` search
  (ledger HS-248/HS-249) whose two geometric values stay at the sealed production configuration's own
  `min_bbox_aspect` and `min_area_px2`, because phase 5 later refuses a bundle whose four perception
  values are not exactly the chosen point.

Two properties make the single recorded detection list re-usable for the whole grid, and both are
declared rather than assumed (`recording_settings`): the frames record detections at the grid's
**lowest** confidence and its **highest** tracker IoU. Ultralytics suppresses a box when a
higher-scoring box overlaps it by more than the threshold, so an NMS pass at a threshold at or below
the one the record was made with yields exactly what the pipeline would have produced at that
threshold, and a confidence floor above the recording floor only drops detections the floor itself
would have dropped (the argument ledger HS-265 recorded for its own selection).

The measurement reuses the gate's own code rather than a second copy of it: the val split of each
domain is the split the frozen-candidate gate verifies (`verify_split_manifest`) and each val cell is
re-measured with the gate's `_measure_static` at the candidate's declared operating point and reported
as a reference that never enters the choice. The metrics of the choice itself are the gate's episode
semantics, which phase 3 already implements (`_metrics`/`_episode_cells`): greedy nearest unused
ground-truth centre within `match_radius_px`, F1 derived from the matched counts. Where episodes are
involved the ground truth is the recorder's own convention - the mean of the cup body's segmentation
pixels in **that camera's** view (`grid/record_episodes7.py`, ledger HS-260/HS-261) - and where the
frozen dataset images are involved it is the dataset's own published truth: the pixel mean of the
instance's visible mask where the dataset publishes one, and otherwise the area centroid of its
published visible-mask polygon.

Nothing here starts ROS or commands motion: the neck angle is a simulated scene state.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import so101_demo
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_operating_point import (
    CAL_NO_CUP_FALSE_CANDIDATE,
    CAL_RULE_AFTER_MEASUREMENT,
    CAL_SPLIT_LEAK,
    check_split_isolation,
    normalise_operating_points,
    record_selection_rule,
    validate_head_search_calibration_operating_point,
)
from so101_demo.perception_benchmark.contracts import OperatingPoint, canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_operating_point_measurements"
PLAN_KIND = "head_search_operating_point_measurement_plan"
RECEIPT_KIND = "head_search_operating_point_measurement_receipt"
RULE_RECEIPT_KIND = "head_search_selection_rule_receipt"
PHASE = "perception_operating_point"

DOCUMENT_NAME = "operating-point-measurements.json"
RECEIPT_NAME = "operating-point-measurement-receipt.json"
RULE_NAME = "selection-rule.json"
TASK_RULE_NAME = "selection-rule-task.json"

#: the two splits the rule selects on, and the split it only reports (design section 7.1, HS-265)
SELECTION_SPLITS = ("val", "calibration")
HELD_OUT_SPLIT = "held_out_evaluation"
VAL_SPLIT = "val"

#: the domains the measurement covers, and the three candidates it covers them for
DOMAINS = ("head", "task")
CANDIDATE_IDS = ("A", "B", "C")

#: the grid of record: the 18 `(min_confidence, tracker.iou)` cells HS-248 declared before measuring it
#: and HS-249 measured. Order is part of the rule - it is the last tie-break of the chain.
GRID_CONFIDENCES = (0.25, 0.35, 0.45, 0.51, 0.60, 0.70)
GRID_TRACKING_IOUS = (0.5, 0.6, 0.7)

#: the point every detection is recorded at: the grid's own extremes, so that every declared point can
#: be re-applied to the same record (see the module docstring)
RECORDING_MIN_CONFIDENCE = min(GRID_CONFIDENCES)
RECORDING_TRACKING_IOU = max(GRID_TRACKING_IOUS)

#: the gate's own matching radius, so the frames and the gate agree on what a match is
MATCH_RADIUS_PX = 8.0

#: the recorder's neck angles per calibration episode: the ends and the middle of the sealed domain
NECK_ANGLES_PER_EPISODE = 3

#: what the campaign's recorder declared a calibration seed's scenario to be (HS-260..HS-265)
EPISODE_SCENARIO_ASSIGNMENT = (
    "condition_classes[min(seed_index // 2, len(condition_classes) - 1)] - the campaign recorder's own "
    "assignment (grid/record_episodes7.py, ledger HS-260..HS-265); the partitions file declares the "
    "classes but not which seed carries which"
)

#: this producer's own refusals; phase 3's three propagate unchanged
CAL_OPERATING_POINT_EVIDENCE_MISSING = "CAL_OPERATING_POINT_EVIDENCE_MISSING"
CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY = "CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY"
REFUSAL_CODES = (
    CAL_OPERATING_POINT_EVIDENCE_MISSING,
    CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
    CAL_RULE_AFTER_MEASUREMENT,
    CAL_SPLIT_LEAK,
    CAL_NO_CUP_FALSE_CANDIDATE,
)

_SHA256_LENGTH = 64


class CalibrationOperatingPointMeasurementRefused(CalibrationInputsRefused):
    """A refusal of either producer, carrying the code the caller records and stops on."""


def _refuse(code: str, detail: str) -> CalibrationOperatingPointMeasurementRefused:
    return CalibrationOperatingPointMeasurementRefused(code, detail)


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _mapping(name: str, value) -> Mapping:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _sequence(name: str, value) -> list:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise _refuse(CAL_OPERATING_POINT_EVIDENCE_MISSING, f"{name} declares nothing to measure")
    return list(value)


def _records(name: str, value) -> list[Mapping]:
    records = []
    for record in _sequence(name, value):
        if not isinstance(record, Mapping):
            raise ValueError(f"every {name} record must be a mapping")
        records.append(record)
    return records


def _digest_of(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def recording_settings() -> dict:
    """The point every detection is recorded at, and why that point makes the grid re-appliable."""

    return {
        "min_confidence": RECORDING_MIN_CONFIDENCE,
        "tracking_iou": RECORDING_TRACKING_IOU,
        "why": (
            "detections are recorded once per frame at the grid's lowest min_confidence and its highest "
            "tracker.iou, so every declared point can be re-applied to the same record: a confidence "
            "floor at or above the recording floor only drops what that floor would have dropped, and "
            "NMS re-suppression at or below the recorded threshold yields exactly what the pipeline "
            "would have produced at that threshold (HS-265)"
        ),
        "channel_order": (
            "the val images are read by Ultralytics itself, and a rendered episode frame is passed to "
            "predict as BGR (`array[:, :, ::-1]`), the conversion the production detector's own "
            "`YoloSegDetector._predict` performs - so both paths hand the model the same RGB tensor"
        ),
    }


def operating_point_grid(*, production_config) -> tuple[dict, ...]:
    """The declared grid: the 18 confidences-by-IoU cells, geometry fixed at production's own values.

    The two geometric values are not searched - they are the sealed production search configuration's
    `min_bbox_aspect` and `min_area_px2`, held fixed while the two searched values move, because phase 5
    requires the bundle's four perception values to be exactly the chosen point and the sealed
    configuration is what production runs with.
    """

    document = _mapping("the sealed production search configuration", production_config)
    values = document.get("values")
    if not isinstance(values, Mapping):
        raise ValueError("the sealed production search configuration declares no values block")
    declared = {}
    for name in ("min_bbox_aspect", "min_area_px2"):
        if not _finite(values.get(name)):
            raise ValueError(
                f"the sealed production search configuration declares no finite {name}, so the grid "
                "would have to invent the value phase 5 compares against"
            )
        declared[name] = float(values[name])
    points = []
    for confidence in GRID_CONFIDENCES:
        for iou in GRID_TRACKING_IOUS:
            points.append(
                OperatingPoint(
                    min_confidence=confidence,
                    min_bbox_aspect=declared["min_bbox_aspect"],
                    min_area_px2=declared["min_area_px2"],
                    tracking_iou=iou,
                ).to_document()
            )
    return tuple(points)


def _required_domain(geometry_seal: Mapping) -> tuple[float, float, float]:
    """The sealed search domain and its three measured neck angles: the ends and the middle."""

    domain = geometry_seal.get("required_search_domain_rad")
    if (
        isinstance(domain, (str, bytes))
        or not isinstance(domain, Sequence)
        or len(domain) != 2
        or not all(_finite(value) for value in domain)
    ):
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_MISSING,
            "the sealed geometry declares no finite required_search_domain_rad, so no calibration "
            "episode has a neck angle to be rendered at",
        )
    low, high = (float(domain[0]), float(domain[1]))
    if not low < high:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"the sealed required search domain {[low, high]} is not an interval",
        )
    return low, (low + high) / 2.0, high


def _camera_name(manifest: Mapping, domain: str) -> str:
    name = manifest.get("camera_name")
    if type(name) is not str or not name:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_MISSING,
            f"the {domain} dataset manifest names no camera, so its frames would carry no view",
        )
    return name


def _val_samples(manifest: Mapping, domain: str, split: str) -> list[dict]:
    """The declared split's samples, in manifest order, with the fields a frame is built from."""

    samples = []
    for sample in manifest.get("samples") or []:
        if not isinstance(sample, Mapping) or sample.get("split") != split:
            continue
        seed, scenario = sample.get("seed"), sample.get("scenario")
        if type(seed) is not int or isinstance(seed, bool):
            raise ValueError(f"every {domain} {split} sample declares an integer seed")
        if type(scenario) is not str or not scenario:
            raise ValueError(f"the {domain} {split} sample {seed} declares no scenario")
        visible = sample.get("visible_instance_count")
        if type(visible) is not int or isinstance(visible, bool) or visible < 0:
            raise ValueError(
                f"the {domain} {split} sample {seed} declares no visible_instance_count"
            )
        for key in ("image", "truth"):
            if type(sample.get(key)) is not str or not sample.get(key):
                raise ValueError(f"the {domain} {split} sample {seed} declares no {key} path")
        samples.append(
            {
                "split": split,
                "seed": int(seed),
                "scenario": scenario,
                "scene_group_id": sample.get("scene_group_id"),
                "image": sample["image"],
                "image_sha256": sample.get("image_sha256"),
                "truth": sample["truth"],
                "truth_sha256": sample.get("truth_sha256"),
                "visible_instance_count": int(visible),
            }
        )
    if not samples:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_MISSING,
            f"the {domain} dataset declares no {split} sample, so the {split} split of the rule cannot "
            "be measured",
        )
    return samples


def image_size(manifest: Mapping, *, domain: str) -> tuple[float, float]:
    """The domain's declared image size, which a published visible-mask polygon is scaled by."""

    width, height = manifest.get("image_width"), manifest.get("image_height")
    if (
        type(width) is not int
        or isinstance(width, bool)
        or type(height) is not int
        or isinstance(height, bool)
        or width <= 0
        or height <= 0
    ):
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_MISSING,
            f"the {domain} dataset manifest declares no image size, so a published visible-mask "
            "polygon cannot be turned into the pixel centre the gate matches on",
        )
    return float(width), float(height)


def _episodes(partitions: Mapping, neck_angles: Sequence[float], seed_limit) -> list[dict]:
    """One calibration episode per declared seed, with the recorder's own scenario assignment."""

    classes = partitions.get("condition_classes")
    if isinstance(classes, (str, bytes)) or not isinstance(classes, Sequence) or not classes:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_MISSING,
            "the sealed scenario partitions declare no condition_classes, so no calibration episode has "
            "a scenario",
        )
    seeds = _sequence("the calibration partition", partitions.get("calibration"))
    for seed in seeds:
        if type(seed) is not int or isinstance(seed, bool):
            raise ValueError("every calibration seed must be an integer")
    if seed_limit is not None:
        if type(seed_limit) is not int or isinstance(seed_limit, bool) or seed_limit < 1:
            raise ValueError("seed_limit must be a positive integer when it is given")
        seeds = seeds[:seed_limit]
    episodes = []
    for index, seed in enumerate(seeds):
        scenario = classes[min(index // 2, len(classes) - 1)]
        if type(scenario) is not str or not scenario:
            raise ValueError("every condition class must be a non-empty name")
        cup_count = 0 if scenario == "no_cup" else (2 if scenario == "two_cups" else 1)
        episodes.append(
            {
                "seed": int(seed),
                "scenario": scenario,
                "cup_count": cup_count,
                "neck_angles_rad": [float(angle) for angle in neck_angles],
            }
        )
    if not episodes:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_MISSING,
            "the sealed scenario partitions declare no calibration seed, so the calibration split of "
            "the rule cannot be measured",
        )
    return episodes


def _candidates(frozen_candidates, weights_sha256) -> list[dict]:
    """The three frozen candidates, each bound to the digest of the weight file it will be measured as."""

    documents = []
    for document in frozen_candidates or ():
        frozen = _mapping("a frozen candidate document", document)
        candidate_id = frozen.get("candidate_id")
        if candidate_id not in CANDIDATE_IDS:
            raise _refuse(
                CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
                f"the frozen candidate {candidate_id!r} is not one of the declared {list(CANDIDATE_IDS)}",
            )
        documents.append(dict(frozen))
    found = sorted(document["candidate_id"] for document in documents)
    if len(set(found)) != len(found):
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"a candidate is declared twice in {found}; the measurement covers each one once",
        )
    if found != sorted(CANDIDATE_IDS):
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_MISSING,
            f"the measurement covers the candidates {list(CANDIDATE_IDS)} but declares {found}",
        )
    if not isinstance(weights_sha256, Mapping):
        raise ValueError("weights_sha256 must map every candidate to its weight file's digest")
    candidates = []
    for document in sorted(documents, key=lambda item: item["candidate_id"]):
        candidate_id = document["candidate_id"]
        sealed = document.get("weight_sha256")
        measured = weights_sha256.get(candidate_id)
        if (
            type(sealed) is not str
            or len(sealed) != _SHA256_LENGTH
            or type(measured) is not str
            or len(measured) != _SHA256_LENGTH
        ):
            raise _refuse(
                CAL_OPERATING_POINT_EVIDENCE_MISSING,
                f"candidate {candidate_id} declares no weight digest, or the weight file was not "
                "digested, so nothing can show which bytes were measured",
            )
        if sealed != measured:
            raise _refuse(
                CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
                f"candidate {candidate_id} is frozen at weights {sealed} but the weight file to measure "
                f"is {measured}; the measurement must run the frozen candidate's own bytes",
            )
        points = document.get("operating_points")
        if not isinstance(points, Mapping):
            raise _refuse(
                CAL_OPERATING_POINT_EVIDENCE_MISSING,
                f"candidate {candidate_id} declares no operating_points, so it has no declared point to "
                "cross-check the gate's measurement against",
            )
        candidates.append(
            {
                "candidate_id": candidate_id,
                "weights_sha256": measured,
                "weights_name": f"{candidate_id}.pt",
                "operating_points": {
                    domain: dict(points[domain])
                    for domain in DOMAINS
                    if isinstance(points.get(domain), Mapping)
                },
            }
        )
    return candidates


def plan_operating_point_measurement(
    *,
    geometry_seal,
    head_dataset_manifest,
    task_dataset_manifest,
    partitions,
    production_config,
    frozen_candidates,
    weights_sha256,
    val_split=VAL_SPLIT,
    seed_limit=None,
    match_radius_px=MATCH_RADIUS_PX,
) -> dict:
    """Lay out the measurement: the grid, the two selection splits, the candidates and every frame's scene.

    Pure and detector-free on purpose: it names exactly which val images and which calibration episodes
    (and at which neck angles) the heavy producer will render and detect, so what is measured can be
    reviewed - and pinned by tests - without a GPU.
    """

    seal = _mapping("the sealed geometry", geometry_seal)
    _camera_name(seal, "sealed geometry")
    neck_angles = list(_required_domain(seal))
    if len(neck_angles) != NECK_ANGLES_PER_EPISODE:  # pragma: no cover - the helper fixes the count
        raise ValueError(
            "a calibration episode is rendered at the two ends and the middle of the domain"
        )
    declared = _mapping("the sealed scenario partitions", partitions)
    grid = operating_point_grid(production_config=production_config)
    if not _finite(match_radius_px) or float(match_radius_px) < 0.0:
        raise ValueError("match_radius_px must be finite and non-negative")
    domains = {}
    for domain, manifest in (
        ("head", _mapping("the head dataset manifest", head_dataset_manifest)),
        ("task", _mapping("the task dataset manifest", task_dataset_manifest)),
    ):
        domains[domain] = {
            "domain": domain,
            "camera_name": _camera_name(manifest, domain),
            "val_split": val_split,
            "val_samples": _val_samples(manifest, domain, val_split),
            "calibration_episodes": _episodes(declared, neck_angles, seed_limit),
        }
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "selection_splits": list(SELECTION_SPLITS),
        "held_out_split": HELD_OUT_SPLIT,
        "val_split": val_split,
        "match_radius_px": float(match_radius_px),
        "recording": recording_settings(),
        "grid": [dict(point) for point in grid],
        "grid_sha256": canonical_sha256(grid),
        "neck_angles_rad": [float(angle) for angle in neck_angles],
        "episode_scenario_assignment": EPISODE_SCENARIO_ASSIGNMENT,
        "seed_limit": seed_limit,
        "domains": domains,
        "candidates": _candidates(frozen_candidates, weights_sha256),
    }
    return {**body, "plan_sha256": canonical_sha256(body)}


def polygon_centre(polygon, *, width: float, height: float) -> tuple[float, float]:
    """The area centroid of a published visible-mask polygon, in pixels.

    The polygons the datasets publish are dense contours of the visible mask, so their area centroid is
    the polygon region's own centre - the same quantity the recorder reads off a segmentation by taking
    the mean of the mask's pixel indices. A degenerate polygon (no area) falls back to the vertex mean.
    """

    if isinstance(polygon, (str, bytes)) or not isinstance(polygon, Sequence) or len(polygon) < 3:
        raise ValueError("a visible-mask polygon needs at least three vertices")
    points = []
    for vertex in polygon:
        if (
            isinstance(vertex, (str, bytes))
            or not isinstance(vertex, Sequence)
            or len(vertex) != 2
            or not all(_finite(value) for value in vertex)
        ):
            raise ValueError("every polygon vertex must be a pair of finite coordinates")
        points.append((float(vertex[0]) * float(width), float(vertex[1]) * float(height)))
    twice_area = 0.0
    x_sum = y_sum = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        x_sum += (x0 + x1) * cross
        y_sum += (y0 + y1) * cross
    if twice_area == 0.0:
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
    return x_sum / (3.0 * twice_area), y_sum / (3.0 * twice_area)


def truth_from_instances(instances, *, width: float, height: float) -> list[dict]:
    """The published ground-truth centres of one frozen dataset image, one per visible instance.

    The mask the dataset publishes is read first (its pixel mean is the recorder's own convention), and
    an instance that publishes only its visible-mask polygon is read from that polygon instead; the
    frame records which of the two it used, so a domain whose dataset publishes no mask cannot look
    like one that does.
    """

    import numpy as np
    from so101_demo.adapters.perception.mujoco_dataset import decode_binary_mask_rle

    centres = []
    for instance in instances or ():
        record = _mapping("a truth instance", instance)
        counts, shape = record.get("visible_mask_rle_counts"), record.get("mask_shape_hw")
        if counts is not None and shape is not None:
            mask = decode_binary_mask_rle(counts, shape)
            rows, columns = np.nonzero(mask)
            if columns.size:
                centres.append(
                    {
                        "instance_id": record.get("body_name") or "instance",
                        "x": float(columns.mean()),
                        "y": float(rows.mean()),
                        "visible_px": int(columns.size),
                        "truth_source": "visible_mask_rle_counts",
                    }
                )
                continue
        polygon = record.get("polygon_xy")
        if polygon is None:
            continue
        x, y = polygon_centre(polygon, width=width, height=height)
        centres.append(
            {
                "instance_id": record.get("body_name") or "instance",
                "x": x,
                "y": y,
                "visible_px": record.get("visible_pixel_count"),
                "truth_source": "polygon_xy",
            }
        )
    return centres


def _centres(name: str, truth) -> list[dict]:
    records = []
    for record in truth or ():
        centre = _mapping(f"a {name} centre", record)
        x, y = centre.get("x"), centre.get("y")
        if not (_finite(x) and _finite(y)):
            raise ValueError(f"a {name} centre declares no finite x/y")
        records.append(
            {
                "x": float(x),
                "y": float(y),
                "visible_px": centre.get("visible_px"),
                "instance_id": centre.get("instance_id"),
                "truth_source": centre.get("truth_source"),
            }
        )
    return records


def _detections_by_candidate(detections) -> dict:
    """One ordered detection list per candidate, with the bbox the geometric floors are applied to."""

    if not isinstance(detections, Mapping):
        raise ValueError("detections must map every candidate to its ordered detection list")
    recorded = {}
    for candidate_id in CANDIDATE_IDS:
        if candidate_id not in detections:
            raise ValueError(
                f"the frame records no measurement for candidate {candidate_id!r}; an absent "
                "measurement is not an empty detection list"
            )
        rows = []
        for row in detections[candidate_id]:
            detection = _mapping("a detection", row)
            if not _finite(detection.get("conf")):
                raise ValueError("every detection declares a finite conf")
            x, y = _centre_of_detection(detection)
            rows.append(
                {
                    "x": x,
                    "y": y,
                    "conf": float(detection["conf"]),
                    "w": detection.get("w"),
                    "h": detection.get("h"),
                }
            )
        recorded[candidate_id] = rows
    return recorded


def _centre_of_detection(detection: Mapping) -> tuple[float, float]:
    """A detection's centre, from `x`/`y` or from the bbox corners a caller recorded instead."""

    if _finite(detection.get("x")) and _finite(detection.get("y")):
        return float(detection["x"]), float(detection["y"])
    bbox = detection.get("bbox")
    if isinstance(bbox, Mapping) and all(
        _finite(bbox.get(corner)) for corner in ("x1", "y1", "x2", "y2")
    ):
        return (
            (float(bbox["x1"]) + float(bbox["x2"])) / 2.0,
            (float(bbox["y1"]) + float(bbox["y2"])) / 2.0,
        )
    raise ValueError("a detection declares no finite x/y")


def _latency_ms(latency_ms) -> dict:
    if not isinstance(latency_ms, Mapping):
        raise ValueError("latency_ms must map every candidate to its measured milliseconds")
    return {candidate_id: float(latency_ms[candidate_id]) for candidate_id in CANDIDATE_IDS}


def _frame(
    *,
    split: str,
    domain: str,
    camera_name: str,
    scenario: str,
    truth,
    detections,
    latency_ms,
    match_radius_px: float,
    scene: dict,
) -> dict:
    if split not in SELECTION_SPLITS:
        raise ValueError(
            f"a frame of the split {split!r} would leak a split the rule does not select on; the "
            f"measurement records only {list(SELECTION_SPLITS)}"
        )
    if domain not in DOMAINS:
        raise ValueError(f"a frame of the domain {domain!r} is not one of {list(DOMAINS)}")
    if type(scenario) is not str or not scenario:
        raise ValueError("every frame declares the scenario it was rendered as")
    return {
        "split": split,
        "domain": domain,
        "camera": camera_name,
        "scenario": scenario,
        "match_radius_px": float(match_radius_px),
        "truth": _centres("ground-truth", truth),
        "detections": _detections_by_candidate(detections),
        "latency_ms": _latency_ms(latency_ms),
        **scene,
    }


def static_frame(
    *,
    domain: str,
    camera_name: str,
    sample: Mapping,
    truth,
    detections,
    latency_ms,
    match_radius_px: float = MATCH_RADIUS_PX,
) -> dict:
    """One frozen dataset image's frame: the val split of one domain, with the dataset's own truth."""

    return _frame(
        split=sample.get("split") or VAL_SPLIT,
        domain=domain,
        camera_name=camera_name,
        scenario=sample.get("scenario"),
        truth=truth,
        detections=detections,
        latency_ms=latency_ms,
        match_radius_px=match_radius_px,
        scene={
            "seed": int(sample["seed"]),
            "scene_group_id": sample.get("scene_group_id"),
            "image": sample.get("image"),
            "image_sha256": sample.get("image_sha256"),
            "neck_rad": sample.get("neck_rad"),
        },
    )


def episode_frame(
    *,
    domain: str,
    camera_name: str,
    seed: int,
    neck_rad: float,
    scenario: str,
    split: str,
    truth,
    detections,
    latency_ms,
    match_radius_px: float = MATCH_RADIUS_PX,
) -> dict:
    """One rendered calibration episode's frame: one seed, one neck angle, one camera's own truth."""

    if type(seed) is not int or isinstance(seed, bool):
        raise ValueError("an episode frame declares an integer seed")
    if not _finite(neck_rad):
        raise ValueError("an episode frame declares a finite neck_rad")
    return _frame(
        split=split,
        domain=domain,
        camera_name=camera_name,
        scenario=scenario,
        truth=truth,
        detections=detections,
        latency_ms=latency_ms,
        match_radius_px=match_radius_px,
        scene={
            "seed": int(seed),
            "neck_rad": float(neck_rad),
            "scene_group_id": f"scene-{int(seed):09d}",
        },
    )


def operating_point_measurement_document(
    *, plan, frames, rules, static_reference=None, provenance=None, path=None
) -> dict:
    """Assemble the document the run declares under `--operating-point-measurements`.

    Its frames are the phase-3 input, and the document records the grid, the two rule records it was
    measured under, the point every detection was recorded at and the gate's own reference cells, so the
    choice can be re-derived from the document alone. `sha256` covers the body without itself, the
    convention the other calibration documents use.
    """

    declared = _mapping("the plan", plan)
    frame_list = [dict(frame) for frame in frames]
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "selection_splits": list(declared["selection_splits"]),
        "held_out_split": declared["held_out_split"],
        "val_split": declared["val_split"],
        "match_radius_px": declared["match_radius_px"],
        "recording": dict(declared["recording"]),
        "grid": [dict(point) for point in declared["grid"]],
        "grid_sha256": declared["grid_sha256"],
        "plan_sha256": declared["plan_sha256"],
        "neck_angles_rad": list(declared["neck_angles_rad"]),
        "episode_scenario_assignment": declared["episode_scenario_assignment"],
        "rule_sha256": {domain: rules[domain]["rule_sha256"] for domain in sorted(rules)},
        "candidates": [
            {
                "candidate_id": candidate["candidate_id"],
                "weights_sha256": candidate["weights_sha256"],
                "weights_name": candidate["weights_name"],
                "operating_points": dict(candidate["operating_points"]),
            }
            for candidate in declared["candidates"]
        ],
        "frames": frame_list,
        "frame_count": len(frame_list),
        "frames_per_split": {
            split: sum(1 for frame in frame_list if frame.get("split") == split)
            for split in declared["selection_splits"]
        },
        "frames_per_domain": {
            domain: sum(1 for frame in frame_list if frame.get("domain") == domain)
            for domain in DOMAINS
        },
        "static_reference": dict(static_reference or {}),
        "provenance": dict(provenance or {}),
    }
    document = {**body, "sha256": canonical_sha256(body)}
    if path is not None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def toolchain_identity(module_path) -> dict:
    """The toolchain root and source commit the running module belongs to, or nulls when it is a source tree.

    A build root carries `source-commit.txt` and an `install/` tree; a worktree checkout has neither, and
    then the fields stay None rather than naming a root that was never built.
    """

    path = Path(module_path).resolve()
    for parent in path.parents:
        if (parent / "install").is_dir() and (parent / "source-commit.txt").is_file():
            commit = (parent / "source-commit.txt").read_text(encoding="utf-8").strip()
            return {"toolchain_root": str(parent), "source_commit": commit or None}
    return {"toolchain_root": None, "source_commit": None}


def record_selection_rule_documents(
    *,
    production_config,
    measurements_output_dir,
    output_dir,
    domains=DOMAINS,
    generation=None,
    measurement_plan_sha256=None,
    provenance=None,
    command=None,
) -> dict:
    """Write the rule records **before** any measurement, or refuse to write anything at all.

    The grid comes from the sealed production search configuration and the splits and the tie-break chain
    are phase 3's own declaration, so the rule cannot differ from the rule phase 3 applies. The directory
    the measurement will own must not exist yet: a rule written after its measurement is exactly what
    design section 7.1 forbids, and the phase-3 module refuses such a record a second time from the other
    side. Nothing is written to the measurement directory - this producer owns only its own output.
    """

    grid = operating_point_grid(production_config=production_config)
    measurements = Path(measurements_output_dir)
    output = Path(output_dir)
    if measurements.exists():
        raise _refuse(
            CAL_RULE_AFTER_MEASUREMENT,
            f"{measurements} exists, so this rule record would be written after the measurement it is "
            "supposed to precede; the ordering design section 7.1 fixes cannot be re-established "
            "afterwards",
        )
    try:
        output.mkdir(parents=True)
    except FileExistsError as error:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"{output} exists; a rule record is never resumed or overwritten",
        ) from error
    rules = {}
    for domain in domains:
        rules[domain] = record_selection_rule(
            points=grid,
            selection_splits=list(SELECTION_SPLITS),
            held_out_splits=[HELD_OUT_SPLIT],
            measurements_admitted=0,
            domain=domain,
            generation=generation,
            measurement_plan_sha256=measurement_plan_sha256,
        )
    names = {"head": RULE_NAME, "task": TASK_RULE_NAME}
    for domain, rule in rules.items():
        (output / names[domain]).write_text(
            json.dumps(rule, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RULE_RECEIPT_KIND,
        "phase": PHASE,
        "status": "RECORDED",
        "command": command,
        "domains": sorted(rules),
        "rule_sha256": {domain: rules[domain]["rule_sha256"] for domain in sorted(rules)},
        "rule_paths": {domain: str(output / names[domain]) for domain in sorted(rules)},
        "point_count": len(grid),
        "grid_sha256": canonical_sha256(grid),
        "selection_splits": list(SELECTION_SPLITS),
        "held_out_split": HELD_OUT_SPLIT,
        "tie_break_chain": list(rules[sorted(rules)[0]]["tie_break_chain"]),
        "measurements_admitted": 0,
        "measurements_output_dir": str(measurements),
        "measurements_output_dir_existed": False,
        "generation": generation,
        "measurement_plan_sha256": measurement_plan_sha256,
        "provenance": dict(provenance or {}),
        "motion_commanded": False,
    }
    (output / RECEIPT_NAME).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"rules": rules, "receipt": receipt, "grid": grid}


def _verified_rule(*, rule, domain, grid) -> dict:
    """One declared rule record, validated by phase 3's own reader and checked against this producer's grid."""

    if not isinstance(rule, Mapping):
        raise ValueError(f"the {domain} selection rule must be a rule record phase 3 made")
    # phase 3's own reader refuses a doctored digest, a rule recorded after a measurement, a rule whose
    # splits overlap and a rule whose points are malformed - no second copy of those rules lives here
    check_split_isolation(rule=rule, measurements=[])
    if rule.get("domain") != domain:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"the rule declared for the {domain} domain records the domain {rule.get('domain')!r}",
        )
    if list(rule.get("selection_splits") or ()) != list(SELECTION_SPLITS):
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"the {domain} rule selects on {rule.get('selection_splits')}, not on "
            f"{list(SELECTION_SPLITS)}",
        )
    if list(rule.get("held_out_splits") or ()) != [HELD_OUT_SPLIT]:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"the {domain} rule reports the held-out splits {rule.get('held_out_splits')}, not "
            f"{[HELD_OUT_SPLIT]}",
        )
    if normalise_operating_points(rule.get("points")) != tuple(grid):
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"the {domain} rule declares a different grid than the one this measurement measured, so "
            "the measurement could not have been the rule's",
        )
    return dict(rule)


def _boxes(result) -> list[dict]:
    """One prediction's boxes as the frame records them: centre, confidence and the box's own size."""

    boxes = getattr(result, "boxes", None)
    recorded = []
    for box in boxes if boxes is not None else ():
        xywh = box.xywh[0]
        recorded.append(
            {
                "x": float(xywh[0]),
                "y": float(xywh[1]),
                "conf": float(box.conf),
                "w": float(xywh[2]),
                "h": float(xywh[3]),
            }
        )
    return recorded


def measure_operating_point_measurements(
    *,
    geometry_seal_path,
    head_dataset_manifest_path,
    task_dataset_manifest_path,
    dataset_config_path,
    production_config_path,
    episode_partitions_path,
    selection_rule_path,
    task_selection_rule_path,
    weights_dir,
    frozen_candidate_paths,
    output_dir,
    device="cuda",
    seed_limit=None,
    match_radius_px=MATCH_RADIUS_PX,
    command=None,
) -> dict:
    """Measure the frames phase 3 consumes, then let the installed phase 3 select every candidate's point.

    The heavy half: it renders the calibration episodes in the sealed scene (the same deterministic
    `_prepare` the campaign's recorder used, with the ground truth of each camera's own segmentation) and
    predicts on the frozen datasets' val images, recording one detection list per candidate per frame at
    the grid's recording point - the production detector's own point (`conf=0.25`, Ultralytics' default
    NMS IoU 0.7), which is the grid's own corner, and with the production detector's own RGB-to-BGR
    conversion for a rendered frame. The val cells are re-measured with the gate's own `_measure_static` at
    each candidate's declared point and reported as a reference. The measurement document is written
    before phase 3 runs, so a phase-3 refusal (a dirty no-cup point, a split leak) leaves the measured
    frames behind as evidence instead of an empty directory. Nothing here commands motion or starts ROS.
    """

    import mujoco
    import numpy as np
    from so101_demo.act.head_search_coarse_step_measurement import runtime_identity
    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetScenario,
        MuJoCoDatasetRenderer,
        load_dataset_config,
    )
    from so101_demo.cli.evaluate_head_search_yolo_candidates import _dataset_sums, _measure_static
    from so101_demo.perception_benchmark.head_search_models import (
        load_frozen_candidate,
        verify_split_manifest,
    )
    from ultralytics import YOLO

    started = time.time()
    geometry_path = Path(geometry_seal_path)
    head_manifest_path = Path(head_dataset_manifest_path)
    task_manifest_path = Path(task_dataset_manifest_path)
    config_path = Path(dataset_config_path)
    production_path = Path(production_config_path)
    partitions_path = Path(episode_partitions_path)
    rule_paths = {"head": Path(selection_rule_path), "task": Path(task_selection_rule_path)}
    weights_root = Path(weights_dir)
    output = Path(output_dir)
    for path in (
        geometry_path,
        head_manifest_path,
        task_manifest_path,
        config_path,
        production_path,
        partitions_path,
        *rule_paths.values(),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"the measurement needs {path}")
    if not weights_root.is_dir():
        raise FileNotFoundError(f"the measurement needs the weights directory {weights_root}")
    try:
        output.mkdir(parents=True)
    except FileExistsError as error:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
            f"{output} exists; a measurement is never resumed, continued or overwritten",
        ) from error

    seal = json.loads(geometry_path.read_text(encoding="utf-8"))
    head_manifest = json.loads(head_manifest_path.read_text(encoding="utf-8"))
    task_manifest = json.loads(task_manifest_path.read_text(encoding="utf-8"))
    partitions = json.loads(partitions_path.read_text(encoding="utf-8"))
    production_config = json.loads(production_path.read_text(encoding="utf-8"))
    rules = {
        domain: _verified_rule(
            rule=json.loads(path.read_text(encoding="utf-8")),
            domain=domain,
            grid=operating_point_grid(production_config=production_config),
        )
        for domain, path in rule_paths.items()
    }

    frozen_paths = {}
    frozen_documents = {}
    for path in frozen_candidate_paths:
        loaded = load_frozen_candidate(path)
        frozen_paths[loaded.candidate_id] = Path(path)
        frozen_documents[loaded.candidate_id] = dict(loaded.document)
    candidates = sorted(
        (dict(load_frozen_candidate(path).document) for path in frozen_paths.values()),
        key=lambda document: document["candidate_id"],
    )
    weights_paths = {
        candidate["candidate_id"]: weights_root / f"{candidate['candidate_id']}.pt"
        for candidate in candidates
    }
    missing = sorted(str(path) for path in weights_paths.values() if not path.is_file())
    if missing:
        raise _refuse(
            CAL_OPERATING_POINT_EVIDENCE_MISSING,
            f"no weight file for {', '.join(missing)}; every candidate is measured as its own bytes",
        )
    weights_digests = {name: _digest_of(path) for name, path in weights_paths.items()}

    plan = plan_operating_point_measurement(
        geometry_seal=seal,
        head_dataset_manifest=head_manifest,
        task_dataset_manifest=task_manifest,
        partitions=partitions,
        production_config=production_config,
        frozen_candidates=candidates,
        weights_sha256=weights_digests,
        seed_limit=seed_limit,
        match_radius_px=match_radius_px,
    )

    roots = {"head": head_manifest_path.parent, "task": task_manifest_path.parent}
    verified = {}
    for domain, manifest, manifest_path in (
        ("head", head_manifest, head_manifest_path),
        ("task", task_manifest, task_manifest_path),
    ):
        samples = verify_split_manifest(
            manifest,
            plan["val_split"],
            dataset_root=roots[domain],
            domain=domain,
            sums=_dataset_sums(roots[domain]),
        )
        declared = {sample["seed"] for sample in plan["domains"][domain]["val_samples"]}
        if {int(sample["seed"]) for sample in samples} != declared:
            raise _refuse(
                CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
                f"the gate's own reading of the {domain} {plan['val_split']} split is not the one this "
                "measurement planned; the two must measure the same images",
            )
        verified[domain] = samples

    renderer = MuJoCoDatasetRenderer(
        load_dataset_config(
            config_path,
            generator_commit=head_manifest.get("generator_commit"),
            sample_limit=None,
        )
    )
    models = {name: YOLO(str(path)) for name, path in weights_paths.items()}
    frames: list[dict] = []
    predictions = 0
    without_geometry = 0
    static_reference: dict[str, dict] = {}
    try:
        neck = mujoco.mj_name2id(renderer._model, mujoco.mjtObj.mjOBJ_JOINT, "neck_yaw_joint")
        if neck < 0:
            raise _refuse(
                CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
                "the sealed scene has no neck_yaw_joint, so no calibration episode can be rendered",
            )
        address = int(renderer._model.jnt_qposadr[neck])
        cameras = {}
        for domain in DOMAINS:
            camera_name = plan["domains"][domain]["camera_name"]
            camera = mujoco.mj_name2id(renderer._model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
            if camera < 0:
                raise _refuse(
                    CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
                    f"the sealed scene has no camera {camera_name!r} for the {domain} domain",
                )
            cameras[domain] = camera
        body_of_geom = {
            geom: int(renderer._model.geom_bodyid[geom]) for geom in range(renderer._model.ngeom)
        }
        body_name = {
            body: mujoco.mj_id2name(renderer._model, mujoco.mjtObj.mjOBJ_BODY, body)
            for body in set(body_of_geom.values())
        }
        cup_bodies = sorted(
            body for body, name in body_name.items() if name and "cup" in name.lower()
        )
        geoms_of_body = {
            body: [geom for geom, owner in body_of_geom.items() if owner == body]
            for body in cup_bodies
        }

        def segmentation(camera: int) -> np.ndarray:
            segmentation_renderer = renderer._segmentation_renderer
            segmentation_renderer.enable_segmentation_rendering()
            try:
                segmentation_renderer.update_scene(renderer._data, camera=camera)
                return renderer._geom_ids(np.array(segmentation_renderer.render(), copy=True))
            finally:
                segmentation_renderer.disable_segmentation_rendering()

        def episode_truth(image) -> list[dict]:
            records = []
            for body in cup_bodies:
                rows, columns = np.nonzero(np.isin(image, geoms_of_body[body]))
                if columns.size:
                    records.append(
                        {
                            "instance_id": body_name[body],
                            "x": float(columns.mean()),
                            "y": float(rows.mean()),
                            "visible_px": int(columns.size),
                            "truth_source": "camera_segmentation",
                        }
                    )
            return records

        def detect(image) -> tuple[dict, dict, int]:
            """Every candidate's detections on one rendered image, and how many boxes carried no bbox."""

            recorded = {}
            latency = {}
            unmeasured = 0
            for candidate_id in CANDIDATE_IDS:
                began = time.perf_counter()
                result = models[candidate_id].predict(
                    image,
                    conf=RECORDING_MIN_CONFIDENCE,
                    iou=RECORDING_TRACKING_IOU,
                    device=device,
                    verbose=False,
                )
                latency[candidate_id] = (time.perf_counter() - began) * 1000.0
                recorded[candidate_id] = _boxes(result[0])
                unmeasured += sum(
                    1
                    for box in recorded[candidate_id]
                    if not (_finite(box["w"]) and _finite(box["h"]))
                )
            return recorded, latency, unmeasured

        # the frozen val images of both domains: the split the gate itself verifies and measures
        for domain in DOMAINS:
            dataset_root = roots[domain]
            width, height = image_size(
                head_manifest if domain == "head" else task_manifest, domain=domain
            )
            for sample in plan["domains"][domain]["val_samples"]:
                truth_document = json.loads(
                    (dataset_root / sample["truth"]).read_text(encoding="utf-8")
                )
                truth = truth_from_instances(
                    truth_document.get("instances") or (), width=width, height=height
                )
                recorded, latency, unmeasured = detect(str(dataset_root / sample["image"]))
                predictions += len(CANDIDATE_IDS)
                without_geometry += unmeasured
                frames.append(
                    static_frame(
                        domain=domain,
                        camera_name=plan["domains"][domain]["camera_name"],
                        sample={
                            **sample,
                            "neck_rad": truth_document.get("camera", {}).get("neck_rad"),
                        },
                        truth=truth,
                        detections=recorded,
                        latency_ms=latency,
                        match_radius_px=plan["match_radius_px"],
                    )
                )

        # the calibration episodes: one scene per declared seed, the recorder's own scenario assignment
        for episode in plan["domains"]["head"]["calibration_episodes"]:
            renderer._prepare(
                np.random.default_rng(int(episode["seed"])),
                DatasetScenario.for_cup_count(int(episode["cup_count"])),
            )
            for angle in episode["neck_angles_rad"]:
                renderer._data.qpos[address] = float(angle)
                mujoco.mj_forward(renderer._model, renderer._data)
                for domain in DOMAINS:
                    truth = episode_truth(segmentation(cameras[domain]))
                    renderer._renderer.update_scene(renderer._data, camera=cameras[domain])
                    image = np.array(renderer._renderer.render(), copy=True)
                    # the renderer yields RGB and Ultralytics reads a numpy source as BGR, exactly as
                    # `YoloSegDetector._predict` converts the production frame before predicting
                    recorded, latency, unmeasured = detect(np.ascontiguousarray(image[:, :, ::-1]))
                    predictions += len(CANDIDATE_IDS)
                    without_geometry += unmeasured
                    frames.append(
                        episode_frame(
                            domain=domain,
                            camera_name=plan["domains"][domain]["camera_name"],
                            seed=int(episode["seed"]),
                            neck_rad=float(angle),
                            scenario=episode["scenario"],
                            split="calibration",
                            truth=truth,
                            detections=recorded,
                            latency_ms=latency,
                            match_radius_px=plan["match_radius_px"],
                        )
                    )
    finally:
        renderer.close()

    # the gate's own measurement of every val cell, at the candidate's declared point, for reference only
    for domain in DOMAINS:
        dataset_root = roots[domain]
        samples = verified[domain]
        for candidate in plan["candidates"]:
            candidate_id = candidate["candidate_id"]
            point = candidate["operating_points"].get(domain)
            if point is None:
                continue
            scratch = output / "static-reference" / f"{candidate_id}-{domain}"
            scratch.mkdir(parents=True, exist_ok=True)
            working = os.getcwd()
            try:
                # Ultralytics writes its run directory into the working directory
                os.chdir(scratch)
                measured = _measure_static(
                    weights_paths[candidate_id],
                    dataset_root,
                    samples,
                    point,
                    device,
                    scratch,
                    document=frozen_documents[candidate_id],
                )
            finally:
                os.chdir(working)
            static_reference[f"{candidate_id}-{domain}"] = {
                "candidate_id": candidate_id,
                "domain": domain,
                "split": plan["val_split"],
                "declared_point": dict(point),
                "sample_count": len(samples),
                "metrics": {key: float(value) for key, value in measured.items()},
                "consumed_for_selection": False,
                "note": (
                    "the gate's own validator at the candidate's declared point; its mask metrics are a "
                    "different measurement from the frame-level centre-matched cells phase 3 selects on, "
                    "so it is a reference and never part of the choice"
                ),
            }

    provenance = {
        "geometry_seal_path": str(geometry_path),
        "geometry_seal_sha256": _digest_of(geometry_path),
        "head_dataset_manifest_path": str(head_manifest_path),
        "head_dataset_manifest_sha256": _digest_of(head_manifest_path),
        "task_dataset_manifest_path": str(task_manifest_path),
        "task_dataset_manifest_sha256": _digest_of(task_manifest_path),
        "dataset_config_path": str(config_path),
        "dataset_config_sha256": _digest_of(config_path),
        "production_search_config_path": str(production_path),
        "production_search_config_sha256": _digest_of(production_path),
        "episode_partitions_path": str(partitions_path),
        "episode_partitions_sha256": _digest_of(partitions_path),
        "selection_rule_path": str(rule_paths["head"]),
        "selection_rule_sha256": _digest_of(rule_paths["head"]),
        "task_selection_rule_path": str(rule_paths["task"]),
        "task_selection_rule_sha256": _digest_of(rule_paths["task"]),
        "weights": {
            name: {"path": str(path), "sha256": weights_digests[name]}
            for name, path in sorted(weights_paths.items())
        },
        "frozen_candidates": {
            candidate_id: {"path": str(path), "sha256": _digest_of(path)}
            for candidate_id, path in sorted(frozen_paths.items())
        },
        "toolchain": toolchain_identity(so101_demo.__file__),
        "mujoco_only": True,
        "ros_nodes_started": False,
        "motion_commanded": False,
    }
    document_path = output / DOCUMENT_NAME
    document = operating_point_measurement_document(
        plan=plan,
        frames=frames,
        rules=rules,
        static_reference=static_reference,
        provenance=provenance,
        path=document_path,
    )

    chosen: dict[str, dict] = {}
    phase3_paths: dict[str, dict] = {}
    for domain in DOMAINS:
        chosen[domain] = {}
        phase3_paths[domain] = {}
        for candidate in plan["candidates"]:
            candidate_id = candidate["candidate_id"]
            target = output / f"phase3-selection-{domain}-{candidate_id}.json"
            selection = validate_head_search_calibration_operating_point(
                rule=rules[domain],
                measurements=frames,
                candidate_id=candidate_id,
                held_out_measurements=(),
                output_path=target,
            )
            phase3_paths[domain][candidate_id] = str(target)
            chosen[domain][candidate_id] = {
                "min_confidence": selection["chosen_point"]["min_confidence"],
                "tracking_iou": selection["chosen_point"]["tracking_iou"],
                "min_bbox_aspect": selection["chosen_point"]["min_bbox_aspect"],
                "min_area_px2": selection["chosen_point"]["min_area_px2"],
                "chosen_index": selection["chosen_index"],
                "ties_broken_by": selection["ties_broken_by"],
                "no_cup_false_candidates": selection["no_cup_guard"]["no_cup_false_candidates"],
                "no_cup_frames_checked": selection["no_cup_guard"]["frames_checked"],
                "measurements_consumed": selection["measurements_consumed"],
                "document_path": str(target),
            }

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": PHASE,
        "status": "MEASURED",
        "command": command,
        "selection_splits": list(SELECTION_SPLITS),
        "held_out_split": HELD_OUT_SPLIT,
        "grid_point_count": len(plan["grid"]),
        "grid_sha256": plan["grid_sha256"],
        "plan_sha256": plan["plan_sha256"],
        "candidate_count": len(plan["candidates"]),
        "frame_count": len(frames),
        "val_frame_count": sum(1 for frame in frames if frame["split"] == VAL_SPLIT),
        "episode_frame_count": sum(1 for frame in frames if frame["split"] == "calibration"),
        "detector_predictions": predictions,
        "detections_without_geometry": without_geometry,
        "recording": dict(plan["recording"]),
        "chosen": chosen,
        "phase3_documents": phase3_paths,
        "static_reference": static_reference,
        "document_path": str(document_path),
        "document_sha256": document["sha256"],
        "elapsed_s": time.time() - started,
        "runtime_identity": runtime_identity(
            weights=weights_paths[CANDIDATE_IDS[0]],
            weights_sha256=weights_digests[CANDIDATE_IDS[0]],
            output_dir=output,
            device=device,
        ),
        "provenance": provenance,
        "motion_commanded": False,
    }
    (output / RECEIPT_NAME).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"document": document, "receipt": receipt, "plan": plan, "rules": rules}
