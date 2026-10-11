"""Write, parse and verify the threshold lock and unlock the test seal."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType

from so101_demo.perception_benchmark.calibration.contracts import (
    _GRID_VERSIONS,
    LOCK_SCHEMA_VERSION,
    OBJECTIVE_VERSION,
    TIE_BREAK_VERSION,
    CalibrationError,
    ModelName,
)
from so101_demo.perception_benchmark.calibration.results import (
    CalibrationResult,
    ObjectiveCalibrationMetrics,
    PlatformCalibrationMetrics,
    ThresholdLock,
    _objective_metrics,
    _threshold_lock_document,
    _validated_sha,
    _validated_source_commit,
)
from so101_demo.perception_benchmark.calibration.thresholds import (
    GroundedSamBenchmarkThresholds,
    YoloThresholds,
    decimal_range,
)
from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    canonical_json_bytes,
)
from so101_demo.perception_benchmark.dataset.contracts import TestSeal


def write_threshold_lock(path: Path, lock: ThresholdLock) -> Path:
    if not isinstance(lock, ThresholdLock):
        raise CalibrationError("THRESHOLD_LOCK_INVALID")
    if lock.with_recomputed_sha256().lock_sha256 != lock.lock_sha256:
        raise CalibrationError("THRESHOLD_LOCK_HASH_MISMATCH")
    target = Path(path)
    atomic_write_json(target, _threshold_lock_document(lock, include_sha=True))
    return target


def _exact_keys(document: object, expected: set[str], code: str) -> Mapping[str, object]:
    if not isinstance(document, Mapping) or set(document) != expected:
        raise CalibrationError(code)
    return document


def _parse_decimal_field(document: Mapping[str, object], name: str) -> Decimal:
    value = document[name]
    if not isinstance(value, str) or re.fullmatch(r"[01]\.\d{2}", value) is None:
        raise CalibrationError("THRESHOLD_LOCK_SELECTED_INVALID")
    try:
        return Decimal(value)
    except ValueError as error:
        raise CalibrationError("THRESHOLD_LOCK_SELECTED_INVALID") from error


def _parse_selected(
    model: ModelName, document: object
) -> YoloThresholds | GroundedSamBenchmarkThresholds:
    try:
        if model == "yolo_seg":
            values = _exact_keys(
                document,
                {"conf", "nms_iou", "target_confidence_threshold", "imgsz"},
                "THRESHOLD_LOCK_SELECTED_MODEL_MISMATCH",
            )
            config: YoloThresholds | GroundedSamBenchmarkThresholds = YoloThresholds(
                _parse_decimal_field(values, "conf"),
                _parse_decimal_field(values, "nms_iou"),
                _parse_decimal_field(values, "target_confidence_threshold"),
                values["imgsz"],
            )
            if (
                config.conf not in decimal_range("0.05", "0.95", "0.05")
                or config.nms_iou not in decimal_range("0.30", "0.90", "0.10")
                or config.target_confidence_threshold not in decimal_range("0.05", "0.95", "0.05")
            ):
                raise CalibrationError("THRESHOLD_LOCK_SELECTED_INVALID")
            return config
        values = _exact_keys(
            document,
            {
                "box_threshold",
                "text_threshold",
                "sam_quality",
                "target_confidence_threshold",
                "duplicate_iou",
                "min_mask_pixels",
                "max_mask_area_ratio",
            },
            "THRESHOLD_LOCK_SELECTED_MODEL_MISMATCH",
        )
        config = GroundedSamBenchmarkThresholds(
            _parse_decimal_field(values, "box_threshold"),
            _parse_decimal_field(values, "text_threshold"),
            _parse_decimal_field(values, "sam_quality"),
            _parse_decimal_field(values, "target_confidence_threshold"),
            _parse_decimal_field(values, "duplicate_iou"),
            values["min_mask_pixels"],
            _parse_decimal_field(values, "max_mask_area_ratio"),
        )
        if (
            config.box_threshold not in decimal_range("0.05", "0.90", "0.05")
            or config.text_threshold not in decimal_range("0.05", "0.50", "0.05")
            or config.sam_quality not in decimal_range("0.50", "0.95", "0.05")
            or config.target_confidence_threshold not in decimal_range("0.05", "0.90", "0.05")
        ):
            raise CalibrationError("THRESHOLD_LOCK_SELECTED_INVALID")
        return config
    except CalibrationError:
        raise
    except (TypeError, ValueError) as error:
        raise CalibrationError("THRESHOLD_LOCK_SELECTED_INVALID") from error


def _parse_platform_metrics(document: object) -> Mapping[str, PlatformCalibrationMetrics]:
    platforms = _exact_keys(document, {"macos", "linux"}, "THRESHOLD_LOCK_METRICS_INVALID")
    expected = {
        "sample_count",
        "error_count",
        "macro_f1",
        "mask_ap50_95",
        "unsafe_unique_count",
        "unsafe_unique_denominator",
        "unsafe_unique_rate",
        "two_cup_both_matched_recall",
    }
    result: dict[str, PlatformCalibrationMetrics] = {}
    try:
        for platform in ("macos", "linux"):
            values = _exact_keys(platforms[platform], expected, "THRESHOLD_LOCK_METRICS_INVALID")
            result[platform] = PlatformCalibrationMetrics(**values)  # type: ignore[arg-type]
    except CalibrationError:
        raise
    except (TypeError, ValueError) as error:
        raise CalibrationError("THRESHOLD_LOCK_METRICS_INVALID") from error
    return MappingProxyType(result)


def _parse_platform_sample_counts(document: object) -> Mapping[str, int]:
    values = _exact_keys(
        document,
        {"macos", "linux"},
        "THRESHOLD_LOCK_SAMPLE_COUNTS_INVALID",
    )
    counts: dict[str, int] = {}
    for platform in ("macos", "linux"):
        value = values[platform]
        if type(value) is not int or value <= 0:
            raise CalibrationError("THRESHOLD_LOCK_SAMPLE_COUNTS_INVALID")
        counts[platform] = value
    return MappingProxyType(counts)


def _parse_objective_metrics(document: object) -> ObjectiveCalibrationMetrics:
    values = _exact_keys(
        document,
        {
            "min_platform_macro_f1",
            "merged_macro_f1",
            "merged_mask_ap50_95",
            "min_platform_two_cup_recall",
        },
        "THRESHOLD_LOCK_METRICS_INVALID",
    )
    try:
        return ObjectiveCalibrationMetrics(**values)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise CalibrationError("THRESHOLD_LOCK_METRICS_INVALID") from error


def verify_threshold_lock(path: Path) -> ThresholdLock:
    target = Path(path)
    if target.is_symlink():
        raise CalibrationError("THRESHOLD_LOCK_UNREADABLE")
    try:
        payload = target.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CalibrationError("THRESHOLD_LOCK_UNREADABLE") from error
    if not isinstance(document, Mapping):
        raise CalibrationError("THRESHOLD_LOCK_DOCUMENT_INVALID")
    if payload != canonical_json_bytes(document):
        raise CalibrationError("THRESHOLD_LOCK_NOT_CANONICAL")
    expected_keys = {
        "schema_version",
        "model",
        "grid_version",
        "objective_version",
        "tie_break_version",
        "val_inventory_sha256",
        "mac_prediction_inventory_sha256",
        "linux_prediction_inventory_sha256",
        "formal",
        "platform_sample_counts",
        "selected",
        "outcome",
        "deployable",
        "source_commit",
        "objective_metrics",
        "platform_metrics",
        "lock_sha256",
    }
    values = _exact_keys(document, expected_keys, "THRESHOLD_LOCK_DOCUMENT_INVALID")
    stored_sha = _validated_sha(values["lock_sha256"])
    unhashed = dict(values)
    unhashed.pop("lock_sha256")
    computed_sha = hashlib.sha256(canonical_json_bytes(unhashed)).hexdigest()
    if stored_sha != computed_sha:
        raise CalibrationError("THRESHOLD_LOCK_HASH_MISMATCH")
    if values["schema_version"] != LOCK_SCHEMA_VERSION:
        raise CalibrationError("THRESHOLD_LOCK_SCHEMA_INVALID")
    if values["model"] not in _GRID_VERSIONS:
        raise CalibrationError("THRESHOLD_LOCK_MODEL_INVALID")
    model: ModelName = values["model"]
    if (
        values["grid_version"] != _GRID_VERSIONS[model]
        or values["objective_version"] != OBJECTIVE_VERSION
        or values["tie_break_version"] != TIE_BREAK_VERSION
    ):
        raise CalibrationError("THRESHOLD_LOCK_VERSION_INVALID")
    val_inventory_sha = _validated_sha(values["val_inventory_sha256"])
    mac_inventory_sha = _validated_sha(values["mac_prediction_inventory_sha256"])
    linux_inventory_sha = _validated_sha(values["linux_prediction_inventory_sha256"])
    commit = _validated_source_commit(values["source_commit"])
    if type(values["formal"]) is not bool:
        raise CalibrationError("THRESHOLD_LOCK_FORMALITY_INVALID")
    formal = values["formal"]
    platform_sample_counts = _parse_platform_sample_counts(values["platform_sample_counts"])
    selected = _parse_selected(model, values["selected"])
    platform_metrics = _parse_platform_metrics(values["platform_metrics"])
    if any(
        platform_sample_counts[platform] != platform_metrics[platform].sample_count
        for platform in ("macos", "linux")
    ):
        raise CalibrationError("THRESHOLD_LOCK_SAMPLE_COUNTS_INVALID")
    if formal and dict(platform_sample_counts) != {"macos": 200, "linux": 200}:
        raise CalibrationError("THRESHOLD_LOCK_FORMALITY_INVALID")
    objective_metrics = _parse_objective_metrics(values["objective_metrics"])
    expected_objective = _objective_metrics(
        CalibrationResult(
            selected=selected,
            platform_metrics=platform_metrics,
            merged_macro_f1=objective_metrics.merged_macro_f1,
            merged_mask_ap50_95=objective_metrics.merged_mask_ap50_95,
        )
    )
    if objective_metrics != expected_objective:
        raise CalibrationError("THRESHOLD_LOCK_METRICS_INVALID")
    if not isinstance(values["deployable"], bool) or values["outcome"] not in (
        "SAFE_CALIBRATED",
        "UNSAFE_CALIBRATION_NO_FEASIBLE_POINT",
    ):
        raise CalibrationError("THRESHOLD_LOCK_OUTCOME_INVALID")
    try:
        lock = ThresholdLock(
            schema_version=LOCK_SCHEMA_VERSION,
            model=model,
            grid_version=values["grid_version"],
            objective_version=values["objective_version"],
            tie_break_version=values["tie_break_version"],
            val_inventory_sha256=val_inventory_sha,
            mac_prediction_inventory_sha256=mac_inventory_sha,
            linux_prediction_inventory_sha256=linux_inventory_sha,
            formal=formal,
            platform_sample_counts=platform_sample_counts,
            selected=selected,
            outcome=values["outcome"],
            deployable=values["deployable"],
            source_commit=commit,
            objective_metrics=objective_metrics,
            platform_metrics=platform_metrics,
            lock_sha256=stored_sha,
        )
    except (TypeError, ValueError) as error:
        raise CalibrationError("THRESHOLD_LOCK_OUTCOME_INVALID") from error
    if _threshold_lock_document(lock, include_sha=True) != dict(values):
        raise CalibrationError("THRESHOLD_LOCK_DOCUMENT_INVALID")
    return lock


def unlock_test_seal(
    seal: TestSeal,
    yolo_lock_path: Path,
    grounded_sam_lock_path: Path,
) -> TestSeal:
    """Verify both distinct model locks before TestSeal appends its access event."""

    if not isinstance(seal, TestSeal):
        raise CalibrationError("TEST_SEAL_INVALID")
    yolo_path = Path(yolo_lock_path)
    grounded_path = Path(grounded_sam_lock_path)
    yolo_lock = verify_threshold_lock(yolo_path)
    grounded_lock = verify_threshold_lock(grounded_path)
    if yolo_lock.model != "yolo_seg" or grounded_lock.model != "grounded_sam":
        raise CalibrationError("TEST_SEAL_LOCK_MODEL_MISMATCH")
    if not yolo_lock.formal or not grounded_lock.formal:
        raise CalibrationError("TEST_SEAL_LOCK_NONFORMAL")
    if any(
        lock.platform_sample_counts[platform] != 200
        for lock in (yolo_lock, grounded_lock)
        for platform in ("macos", "linux")
    ):
        raise CalibrationError("TEST_SEAL_LOCK_SAMPLE_COUNT_INVALID")
    if yolo_lock.val_inventory_sha256 != grounded_lock.val_inventory_sha256:
        raise CalibrationError("TEST_SEAL_LOCK_INVENTORY_MISMATCH")
    if yolo_lock.source_commit != grounded_lock.source_commit:
        raise CalibrationError("TEST_SEAL_LOCK_SOURCE_MISMATCH")
    if yolo_lock.lock_sha256 == grounded_lock.lock_sha256:
        raise CalibrationError("TEST_SEAL_LOCKS_NOT_DISTINCT")
    verified = {
        yolo_path: yolo_lock.lock_sha256,
        grounded_path: grounded_lock.lock_sha256,
    }
    return seal.unlock(
        yolo_path,
        grounded_path,
        verify_lock=lambda path: verified[Path(path)],
    )
