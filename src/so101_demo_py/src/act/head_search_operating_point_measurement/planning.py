"""Kinds, refusal codes, the operating point grid and the measurement plan."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import math
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_operating_point import (
    CAL_NO_CUP_FALSE_CANDIDATE,
    CAL_RULE_AFTER_MEASUREMENT,
    CAL_SPLIT_LEAK,
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


#: the two splits the rule selects on, and the split it only reports (design section 7.1)
SELECTION_SPLITS = ("val", "calibration")


HELD_OUT_SPLIT = "held_out_evaluation"


VAL_SPLIT = "val"


#: the domains the measurement covers, and the three candidates it covers them for
DOMAINS = ("head", "task")


CANDIDATE_IDS = ("A", "B", "C")


#: the grid of record: the 18 `(min_confidence, tracker.iou)` cells the campaign declared before measuring them
#: and then measured. Order is part of the rule - it is the last tie-break of the chain.
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


#: what the campaign's recorder declared a calibration seed's scenario to be
EPISODE_SCENARIO_ASSIGNMENT = (
    "condition_classes[min(seed_index // 2, len(condition_classes) - 1)] - the campaign recorder's own "
    "assignment (grid/record_episodes7.py); the partitions file declares the "
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
            "would have produced at that threshold"
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
