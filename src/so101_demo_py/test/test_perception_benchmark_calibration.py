from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from so101_demo.perception_benchmark.calibration import (
    CalibrationError,
    CalibrationResult,
    GroundedSamBenchmarkThresholds,
    PlatformCalibrationMetrics,
    ThresholdLock,
    YoloThresholds,
    calibration_key,
    calibrate_joint_platform_val,
    enumerate_grounded_sam_grid,
    enumerate_yolo_grid,
    select_calibration_result,
    unlock_test_seal,
    verify_threshold_lock,
    write_threshold_lock,
)
from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    encode_mask_rle,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    MaskRef,
    PhaseTimings,
    PredictionRecord,
    RawCandidate,
    RecordStatus,
    RunKind,
    RuntimeProvenance,
    TruthInstance,
    TruthSample,
)
from so101_demo.perception_benchmark.dataset import TestSeal as DatasetTestSeal


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SOURCE_COMMIT = "4d8cc45957b452eacb7d773676a4bd2d3d138f31"


def _write_mask(
    root: Path,
    name: str,
    mask: np.ndarray,
) -> MaskRef:
    value = np.asarray(mask, dtype=bool)
    relative_path = f"masks/{name}.json"
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(encode_mask_rle(value)))
    return MaskRef(
        relative_path=relative_path,
        sha256=sha256_bytes(value.astype(np.uint8).tobytes(order="C")),
        pixel_count=int(value.sum()),
        image_width=value.shape[1],
        image_height=value.shape[0],
    )


def _candidate(
    mask: MaskRef,
    candidate_id: str,
    bbox: tuple[float, float, float, float],
    *,
    model: str,
    box_score: float,
    text_score: float = 0.90,
    sam_quality: float = 0.90,
) -> RawCandidate:
    if model == "yolo_seg":
        return RawCandidate(
            candidate_id=candidate_id,
            label="plastic_cup",
            bbox_xyxy=bbox,
            mask=mask,
            ranking_score=box_score,
            ranking_score_source="class_confidence",
            class_confidence=box_score,
            grounding_box_score=None,
            grounding_text_score=None,
            sam_quality=None,
        )
    return RawCandidate(
        candidate_id=candidate_id,
        label="plastic_cup",
        bbox_xyxy=bbox,
        mask=mask,
        ranking_score=box_score,
        ranking_score_source="grounding_box_score",
        class_confidence=None,
        grounding_box_score=box_score,
        grounding_text_score=text_score,
        sam_quality=sam_quality,
    )


def _record(
    *,
    platform: str,
    model: str,
    sample_index: int,
    scenario: str,
    image_sha: str,
    candidates: tuple[RawCandidate, ...],
    record_status: RecordStatus = RecordStatus.OK,
) -> PredictionRecord:
    if record_status is RecordStatus.ERROR:
        decision = DecisionOutput.ERROR
        selected = None
        rejection = None
        error_type = "INFERENCE_FAILED"
        candidates = ()
    elif not candidates:
        decision = DecisionOutput.NOT_FOUND
        selected = None
        rejection = "TARGET_NOT_FOUND"
        error_type = None
    elif len(candidates) == 1:
        decision = DecisionOutput.UNIQUE
        selected = candidates[0].candidate_id
        rejection = None
        error_type = None
    else:
        decision = DecisionOutput.AMBIGUOUS
        selected = None
        rejection = "TARGET_AMBIGUOUS"
        error_type = None
    return PredictionRecord(
        run_id=f"{platform}-{model}-{sample_index}",
        schema_version="so101-perception-benchmark/v1",
        run_kind=RunKind.VAL_RAW,
        record_status=record_status,
        formal_sample_index=sample_index,
        split="val",
        scenario=scenario,
        image_relpath=f"images/{sample_index:03d}.png",
        image_sha256=image_sha,
        image_width=20,
        image_height=20,
        model_id="yolo11n-seg-v1" if model == "yolo_seg" else "grounded-sam-v1",
        runtime_provenance=RuntimeProvenance(
            runtime_device="mps" if platform == "macos" else "cuda",
            runtime_name=model,
            runtime_version="1.0",
            weights_sha256=SHA_A,
        ),
        config_sha256=SHA_B,
        threshold_lock_sha256=None,
        raw_candidates=candidates,
        phase_timings=PhaseTimings(selector_ms=1.0),
        raw_count=len(candidates),
        decision=decision,
        selected_candidate_id=selected,
        rejection_reason=rejection,
        error_type=error_type,
        error_summary="fixture failure" if error_type else None,
        timed_out=False,
        oom=False,
        fallback_used=False,
    )


def _fixture(
    root: Path,
    model: str,
) -> tuple[tuple[PredictionRecord, ...], tuple[PredictionRecord, ...], tuple[TruthSample, ...]]:
    left = np.zeros((20, 20), dtype=bool)
    left[0:8, 0:8] = True
    right = np.zeros((20, 20), dtype=bool)
    right[0:8, 12:20] = True
    false_positive = np.zeros((20, 20), dtype=bool)
    false_positive[12:20, 0:8] = True
    refs = {
        "left": _write_mask(root, f"{model}-left", left),
        "right": _write_mask(root, f"{model}-right", right),
        "false": _write_mask(root, f"{model}-false", false_positive),
    }
    image_shas = ("1" * 64, "2" * 64, "3" * 64)
    truths = (
        TruthSample(
            0,
            "val",
            "no_cup",
            "images/000.png",
            image_shas[0],
            20,
            20,
            (),
        ),
        TruthSample(
            1,
            "val",
            "one_cup_distractors",
            "images/001.png",
            image_shas[1],
            20,
            20,
            (TruthInstance("truth-left", "plastic_cup", refs["left"]),),
        ),
        TruthSample(
            2,
            "val",
            "two_cups",
            "images/002.png",
            image_shas[2],
            20,
            20,
            (
                TruthInstance("truth-left", "plastic_cup", refs["left"]),
                TruthInstance("truth-right", "plastic_cup", refs["right"]),
            ),
        ),
    )
    candidates = (
        (
            _candidate(
                refs["false"],
                "false",
                (0.0, 12.0, 8.0, 20.0),
                model=model,
                box_score=0.20,
            ),
        ),
        (
            _candidate(
                refs["left"],
                "left",
                (0.0, 0.0, 8.0, 8.0),
                model=model,
                box_score=0.90,
            ),
        ),
        (
            _candidate(
                refs["left"],
                "left",
                (0.0, 0.0, 8.0, 8.0),
                model=model,
                box_score=0.85,
            ),
            _candidate(
                refs["right"],
                "right",
                (12.0, 0.0, 20.0, 8.0),
                model=model,
                box_score=0.80,
            ),
        ),
    )
    mac = tuple(
        _record(
            platform="macos",
            model=model,
            sample_index=index,
            scenario=truths[index].scenario,
            image_sha=image_shas[index],
            candidates=candidates[index],
        )
        for index in range(3)
    )
    linux = tuple(
        _record(
            platform="linux",
            model=model,
            sample_index=index,
            scenario=truths[index].scenario,
            image_sha=image_shas[index],
            candidates=tuple(reversed(candidates[index])),
        )
        for index in range(3)
    )
    return mac, linux, truths


def _calibrate(root: Path, model: str):
    mac, linux, truths = _fixture(root, model)
    return calibrate_joint_platform_val(
        model=model,
        mac_records=mac,
        linux_records=linux,
        truths=truths,
        inventory_sha=SHA_A,
        evidence_root=root,
        mac_prediction_inventory_sha256=SHA_B,
        linux_prediction_inventory_sha256=SHA_C,
        source_commit=SOURCE_COMMIT,
        fixture_mode=True,
    )


def _mask_ref(
    *,
    name: str = "mask.json",
    pixels: int = 64,
    width: int = 40,
    height: int = 20,
) -> MaskRef:
    return MaskRef(name, SHA_A, pixels, width, height)


def _yolo_thresholds(**overrides: object) -> YoloThresholds:
    values: dict[str, object] = {
        "conf": Decimal("0.50"),
        "nms_iou": Decimal("0.50"),
        "target_confidence_threshold": Decimal("0.50"),
        "imgsz": 640,
    }
    values.update(overrides)
    return YoloThresholds(**values)  # type: ignore[arg-type]


def _grounded_thresholds(**overrides: object) -> GroundedSamBenchmarkThresholds:
    values: dict[str, object] = {
        "box_threshold": Decimal("0.50"),
        "text_threshold": Decimal("0.50"),
        "sam_quality": Decimal("0.50"),
        "target_confidence_threshold": Decimal("0.50"),
        "duplicate_iou": Decimal("0.85"),
        "min_mask_pixels": 64,
        "max_mask_area_ratio": Decimal("0.50"),
    }
    values.update(overrides)
    return GroundedSamBenchmarkThresholds(**values)  # type: ignore[arg-type]


def test_grids_have_exact_decimal_counts_endpoints_and_fixed_values() -> None:
    yolo = tuple(enumerate_yolo_grid())
    grounded = tuple(enumerate_grounded_sam_grid())

    assert len(yolo) == 2527
    assert {point.conf for point in yolo} == {
        Decimal(f"{value / 100:.2f}") for value in range(5, 96, 5)
    }
    assert {point.nms_iou for point in yolo} == {
        Decimal(f"{value / 100:.2f}") for value in range(30, 91, 10)
    }
    assert yolo[0] == YoloThresholds(
        Decimal("0.05"), Decimal("0.30"), Decimal("0.05"), 640
    )
    assert yolo[-1] == YoloThresholds(
        Decimal("0.95"), Decimal("0.90"), Decimal("0.95"), 640
    )

    assert len(grounded) == 32400
    assert {point.box_threshold for point in grounded} == {
        Decimal(f"{value / 100:.2f}") for value in range(5, 91, 5)
    }
    assert {point.text_threshold for point in grounded} == {
        Decimal(f"{value / 100:.2f}") for value in range(5, 51, 5)
    }
    assert {point.sam_quality for point in grounded} == {
        Decimal(f"{value / 100:.2f}") for value in range(50, 96, 5)
    }
    assert {point.target_confidence_threshold for point in grounded} == {
        Decimal(f"{value / 100:.2f}") for value in range(5, 91, 5)
    }
    assert grounded[0] == GroundedSamBenchmarkThresholds(
        Decimal("0.05"),
        Decimal("0.05"),
        Decimal("0.50"),
        Decimal("0.05"),
        Decimal("0.85"),
        64,
        Decimal("0.50"),
    )
    assert grounded[-1] == GroundedSamBenchmarkThresholds(
        Decimal("0.90"),
        Decimal("0.50"),
        Decimal("0.95"),
        Decimal("0.90"),
        Decimal("0.85"),
        64,
        Decimal("0.50"),
    )


def test_configs_are_immutable_and_normalize_decimal_json_without_float_drift() -> None:
    yolo = _yolo_thresholds(conf=Decimal("0.50"))
    grounded = _grounded_thresholds(max_mask_area_ratio=Decimal("0.50"))

    assert yolo.normalized_json == (
        '{"conf":"0.50","imgsz":640,"nms_iou":"0.50",'
        '"target_confidence_threshold":"0.50"}'
    )
    assert grounded.normalized_json == (
        '{"box_threshold":"0.50","duplicate_iou":"0.85",'
        '"max_mask_area_ratio":"0.50","min_mask_pixels":64,'
        '"sam_quality":"0.50","target_confidence_threshold":"0.50",'
        '"text_threshold":"0.50"}'
    )
    with pytest.raises(FrozenInstanceError):
        yolo.conf = Decimal("0.55")  # type: ignore[misc]
    with pytest.raises(ValueError, match="two decimal"):
        _yolo_thresholds(conf=Decimal("0.501"))


@pytest.mark.parametrize(
    ("model", "field", "value"),
    [
        ("yolo_seg", "imgsz", 640.0),
        ("yolo_seg", "imgsz", True),
        ("grounded_sam", "min_mask_pixels", 64.0),
        ("grounded_sam", "min_mask_pixels", True),
    ],
)
def test_fixed_integer_config_fields_reject_equal_floats_and_booleans(
    model: str,
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="fixed integer"):
        if model == "yolo_seg":
            _yolo_thresholds(**{field: value})
        else:
            _grounded_thresholds(**{field: value})


def test_yolo_filter_applies_class_gate_before_deterministic_nms_and_selector() -> None:
    ref = _mask_ref()
    candidates = (
        _candidate(ref, "low-class", (10.0, 0.0, 13.0, 1.0), model="yolo_seg", box_score=0.49),
        _candidate(ref, "b", (1.0, 0.0, 4.0, 1.0), model="yolo_seg", box_score=0.80),
        _candidate(ref, "a", (0.0, 0.0, 3.0, 1.0), model="yolo_seg", box_score=0.80),
        _candidate(ref, "selector-low", (20.0, 0.0, 23.0, 1.0), model="yolo_seg", box_score=0.79),
        _candidate(ref, "selector-edge", (30.0, 0.0, 33.0, 1.0), model="yolo_seg", box_score=0.80),
    )
    thresholds = _yolo_thresholds(
        conf=Decimal("0.50"),
        nms_iou=Decimal("0.50"),
        target_confidence_threshold=Decimal("0.80"),
    )

    forward = thresholds.filter_candidates(candidates)
    reverse = thresholds.filter_candidates(tuple(reversed(candidates)))

    assert [candidate.candidate_id for candidate in forward] == [
        "a",
        "selector-edge",
    ]
    assert reverse == forward
    assert [candidate.ranking_score for candidate in forward] == [0.80, 0.80]


def test_yolo_nms_suppresses_overlap_at_the_configured_iou_boundary() -> None:
    ref = _mask_ref()
    candidates = (
        _candidate(ref, "b", (1.0, 0.0, 4.0, 1.0), model="yolo_seg", box_score=0.80),
        _candidate(ref, "a", (0.0, 0.0, 3.0, 1.0), model="yolo_seg", box_score=0.80),
    )

    assert [
        item.candidate_id for item in _yolo_thresholds().filter_candidates(candidates)
    ] == ["a"]


def test_grounded_filter_uses_box_text_dedup_sam_geometry_then_selector() -> None:
    valid = _mask_ref()
    tiny = _mask_ref(name="tiny.json", pixels=63)
    oversized = _mask_ref(name="oversized.json", pixels=401)
    candidates = (
        _candidate(valid, "box-low", (0.0, 2.0, 3.0, 3.0), model="grounded_sam", box_score=0.49),
        _candidate(valid, "text-low", (4.0, 2.0, 7.0, 3.0), model="grounded_sam", box_score=0.90, text_score=0.49),
        _candidate(valid, "sam-low", (8.0, 2.0, 11.0, 3.0), model="grounded_sam", box_score=0.90, sam_quality=0.49),
        _candidate(tiny, "tiny", (12.0, 2.0, 15.0, 3.0), model="grounded_sam", box_score=0.90),
        _candidate(oversized, "oversized", (16.0, 2.0, 19.0, 3.0), model="grounded_sam", box_score=0.90),
        _candidate(valid, "selector-low", (20.0, 2.0, 23.0, 3.0), model="grounded_sam", box_score=0.79),
        _candidate(valid, "selector-edge", (24.0, 2.0, 27.0, 3.0), model="grounded_sam", box_score=0.80),
    )
    thresholds = _grounded_thresholds(
        target_confidence_threshold=Decimal("0.80")
    )

    assert [
        item.candidate_id for item in thresholds.filter_candidates(candidates)
    ] == ["selector-edge"]


def test_grounded_dedup_matches_existing_box_iou_semantics_and_is_id_stable() -> None:
    ref = _mask_ref()
    candidates = (
        _candidate(ref, "b", (3.0, 0.0, 40.0, 1.0), model="grounded_sam", box_score=0.80),
        _candidate(ref, "a", (0.0, 0.0, 37.0, 1.0), model="grounded_sam", box_score=0.80),
    )
    thresholds = _grounded_thresholds(
        box_threshold=Decimal("0.10"),
        text_threshold=Decimal("0.10"),
        sam_quality=Decimal("0.10"),
        target_confidence_threshold=Decimal("0.10"),
    )

    assert [item.candidate_id for item in thresholds.filter_candidates(candidates)] == ["a"]
    assert thresholds.filter_candidates(tuple(reversed(candidates))) == thresholds.filter_candidates(candidates)


def test_grounded_dedup_precedes_sam_gate_and_ranking_stays_box_score() -> None:
    ref = _mask_ref()
    candidates = (
        _candidate(ref, "winner", (0.0, 0.0, 37.0, 1.0), model="grounded_sam", box_score=0.90, text_score=0.50, sam_quality=0.49),
        _candidate(ref, "inferior", (3.0, 0.0, 40.0, 1.0), model="grounded_sam", box_score=0.80, text_score=0.99, sam_quality=0.99),
    )

    assert _grounded_thresholds().filter_candidates(candidates) == ()


def _platform_metrics(
    *,
    macro_f1: float = 0.8,
    mask_ap: float = 0.7,
    two_cup: float = 0.6,
    unsafe: int = 0,
) -> PlatformCalibrationMetrics:
    return PlatformCalibrationMetrics(
        sample_count=3,
        error_count=0,
        macro_f1=macro_f1,
        mask_ap50_95=mask_ap,
        unsafe_unique_count=unsafe,
        unsafe_unique_denominator=2,
        unsafe_unique_rate=unsafe / 2,
        two_cup_both_matched_recall=two_cup,
    )


def _point(
    config: YoloThresholds | GroundedSamBenchmarkThresholds,
    *,
    mac_macro: float = 0.8,
    linux_macro: float = 0.8,
    merged_macro: float = 0.8,
    merged_ap: float = 0.7,
    mac_two: float = 0.6,
    linux_two: float = 0.6,
    mac_unsafe: int = 0,
    linux_unsafe: int = 0,
) -> CalibrationResult:
    return CalibrationResult(
        selected=config,
        platform_metrics={
            "macos": _platform_metrics(
                macro_f1=mac_macro,
                two_cup=mac_two,
                unsafe=mac_unsafe,
            ),
            "linux": _platform_metrics(
                macro_f1=linux_macro,
                two_cup=linux_two,
                unsafe=linux_unsafe,
            ),
        },
        merged_macro_f1=merged_macro,
        merged_mask_ap50_95=merged_ap,
    )


def test_comparator_level_one_requires_zero_unsafe_on_both_platforms() -> None:
    safe = _point(_yolo_thresholds(), merged_macro=0.1)
    unsafe = _point(
        _yolo_thresholds(conf=Decimal("0.55")),
        mac_macro=1.0,
        linux_macro=1.0,
        merged_macro=1.0,
        merged_ap=1.0,
        mac_two=1.0,
        linux_two=1.0,
        linux_unsafe=1,
    )

    assert select_calibration_result((unsafe, safe)) is safe
    assert safe.outcome == "SAFE_CALIBRATED"
    assert safe.deployable is True


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            _point(_yolo_thresholds(), mac_macro=0.81, linux_macro=0.80),
            _point(_yolo_thresholds(conf=Decimal("0.55")), mac_macro=0.79, linux_macro=0.99),
        ),
        (
            _point(_yolo_thresholds(), merged_macro=0.81),
            _point(_yolo_thresholds(conf=Decimal("0.55")), merged_macro=0.80),
        ),
        (
            _point(_yolo_thresholds(), merged_ap=0.71),
            _point(_yolo_thresholds(conf=Decimal("0.55")), merged_ap=0.70),
        ),
        (
            _point(_yolo_thresholds(), mac_two=0.61, linux_two=0.60),
            _point(_yolo_thresholds(conf=Decimal("0.55")), mac_two=0.59, linux_two=0.99),
        ),
    ],
)
def test_comparator_levels_two_through_five_are_applied_in_order(
    first: CalibrationResult,
    second: CalibrationResult,
) -> None:
    assert select_calibration_result((second, first)) is first


@pytest.mark.parametrize(
    ("preferred", "other"),
    [
        (_yolo_thresholds(conf=Decimal("0.55")), _yolo_thresholds(conf=Decimal("0.50"))),
        (
            _yolo_thresholds(target_confidence_threshold=Decimal("0.55")),
            _yolo_thresholds(target_confidence_threshold=Decimal("0.50")),
        ),
        (_yolo_thresholds(nms_iou=Decimal("0.40")), _yolo_thresholds(nms_iou=Decimal("0.50"))),
        (
            _grounded_thresholds(box_threshold=Decimal("0.55")),
            _grounded_thresholds(box_threshold=Decimal("0.50")),
        ),
        (
            _grounded_thresholds(text_threshold=Decimal("0.55")),
            _grounded_thresholds(text_threshold=Decimal("0.50")),
        ),
        (
            _grounded_thresholds(sam_quality=Decimal("0.55")),
            _grounded_thresholds(sam_quality=Decimal("0.50")),
        ),
        (
            _grounded_thresholds(target_confidence_threshold=Decimal("0.55")),
            _grounded_thresholds(target_confidence_threshold=Decimal("0.50")),
        ),
    ],
)
def test_comparator_level_six_prefers_stricter_safety_thresholds(
    preferred: YoloThresholds | GroundedSamBenchmarkThresholds,
    other: YoloThresholds | GroundedSamBenchmarkThresholds,
) -> None:
    assert select_calibration_result((_point(other), _point(preferred))).selected == preferred


def test_comparator_level_seven_is_canonical_json_and_selection_is_order_independent() -> None:
    point = _point(_yolo_thresholds())
    duplicate = _point(_yolo_thresholds())

    assert calibration_key(point)[-1] == point.selected.normalized_json
    assert select_calibration_result((point, duplicate)) == select_calibration_result(
        (duplicate, point)
    )


def test_all_unsafe_characterization_ignores_unsafe_magnitude_and_freezes_best_remaining_point() -> None:
    better_objective = _point(
        _yolo_thresholds(), merged_macro=0.9, mac_unsafe=2, linux_unsafe=2
    )
    fewer_unsafe = _point(
        _yolo_thresholds(conf=Decimal("0.55")),
        merged_macro=0.8,
        mac_unsafe=1,
        linux_unsafe=1,
    )

    selected = select_calibration_result((fewer_unsafe, better_objective))

    assert selected is better_objective
    assert selected.outcome == "UNSAFE_CALIBRATION_NO_FEASIBLE_POINT"
    assert selected.deployable is False


def test_joint_calibration_uses_val_only_verified_masks_and_zero_unsafe_gate(
    tmp_path: Path,
) -> None:
    lock = _calibrate(tmp_path, "yolo_seg")

    assert lock.selected == YoloThresholds(
        Decimal("0.80"), Decimal("0.30"), Decimal("0.80"), 640
    )
    assert lock.outcome == "SAFE_CALIBRATED"
    assert lock.deployable is True
    assert lock.platform_metrics["macos"].unsafe_unique_rate == 0.0
    assert lock.platform_metrics["linux"].unsafe_unique_rate == 0.0
    assert lock.platform_metrics["macos"].sample_count == 3


def test_formal_calibration_requires_exact_two_hundred_shared_identities(
    tmp_path: Path,
) -> None:
    mac, linux, truths = _fixture(tmp_path, "yolo_seg")

    with pytest.raises(CalibrationError, match="FORMAL_VAL_INVENTORY_INVALID"):
        calibrate_joint_platform_val(
            model="yolo_seg",
            mac_records=mac,
            linux_records=linux,
            truths=truths,
            inventory_sha=SHA_A,
            evidence_root=tmp_path,
            mac_prediction_inventory_sha256=SHA_B,
            linux_prediction_inventory_sha256=SHA_C,
            source_commit=SOURCE_COMMIT,
        )


@pytest.mark.parametrize("bad_side", ["truth", "mac", "linux"])
def test_calibration_rejects_non_val_inputs(tmp_path: Path, bad_side: str) -> None:
    mac, linux, truths = _fixture(tmp_path, "yolo_seg")
    if bad_side == "truth":
        truths = (replace(truths[0], split="test"),) + truths[1:]
    elif bad_side == "mac":
        mac = (replace(mac[0], split="test"),) + mac[1:]
    else:
        linux = (replace(linux[0], split="test"),) + linux[1:]

    with pytest.raises(CalibrationError, match="CALIBRATION_VAL_ONLY"):
        calibrate_joint_platform_val(
            "yolo_seg",
            mac,
            linux,
            truths,
            SHA_A,
            evidence_root=tmp_path,
            mac_prediction_inventory_sha256=SHA_B,
            linux_prediction_inventory_sha256=SHA_C,
            source_commit=SOURCE_COMMIT,
            fixture_mode=True,
        )


def test_calibration_rejects_error_records_without_skipping_denominators(
    tmp_path: Path,
) -> None:
    mac, linux, truths = _fixture(tmp_path, "yolo_seg")
    mac = (
        _record(
            platform="macos",
            model="yolo_seg",
            sample_index=0,
            scenario=truths[0].scenario,
            image_sha=truths[0].image_sha256,
            candidates=(),
            record_status=RecordStatus.ERROR,
        ),
    ) + mac[1:]

    with pytest.raises(CalibrationError, match="CALIBRATION_ERROR_RECORD_FORBIDDEN"):
        calibrate_joint_platform_val(
            "yolo_seg",
            mac,
            linux,
            truths,
            SHA_A,
            evidence_root=tmp_path,
            mac_prediction_inventory_sha256=SHA_B,
            linux_prediction_inventory_sha256=SHA_C,
            source_commit=SOURCE_COMMIT,
            fixture_mode=True,
        )


def test_calibration_rejects_wrong_model_and_non_task1_valid_candidate(
    tmp_path: Path,
) -> None:
    mac, linux, truths = _fixture(tmp_path, "yolo_seg")
    with pytest.raises(CalibrationError, match="CALIBRATION_MODEL_MISMATCH"):
        calibrate_joint_platform_val(
            "grounded_sam",
            mac,
            linux,
            truths,
            SHA_A,
            evidence_root=tmp_path,
            mac_prediction_inventory_sha256=SHA_B,
            linux_prediction_inventory_sha256=SHA_C,
            source_commit=SOURCE_COMMIT,
            fixture_mode=True,
        )

    broken_candidate = mac[1].raw_candidates[0]
    object.__setattr__(broken_candidate, "class_confidence", None)
    with pytest.raises(CalibrationError, match="TASK1_RECORD_CONTRACT_INVALID"):
        calibrate_joint_platform_val(
            "yolo_seg",
            mac,
            linux,
            truths,
            SHA_A,
            evidence_root=tmp_path,
            mac_prediction_inventory_sha256=SHA_B,
            linux_prediction_inventory_sha256=SHA_C,
            source_commit=SOURCE_COMMIT,
            fixture_mode=True,
        )


def test_calibration_rejects_mismatched_platform_inventory_and_bad_mask_payload(
    tmp_path: Path,
) -> None:
    mac, linux, truths = _fixture(tmp_path, "yolo_seg")
    linux = (replace(linux[0], image_sha256="4" * 64),) + linux[1:]
    with pytest.raises(CalibrationError, match="PLATFORM_INVENTORY_IDENTITY_MISMATCH"):
        calibrate_joint_platform_val(
            "yolo_seg",
            mac,
            linux,
            truths,
            SHA_A,
            evidence_root=tmp_path,
            mac_prediction_inventory_sha256=SHA_B,
            linux_prediction_inventory_sha256=SHA_C,
            source_commit=SOURCE_COMMIT,
            fixture_mode=True,
        )

    mac, linux, truths = _fixture(tmp_path, "yolo_seg")
    (tmp_path / truths[1].instances[0].mask.relative_path).write_text("{}")
    with pytest.raises(CalibrationError, match="MASK_EVIDENCE_INVALID"):
        calibrate_joint_platform_val(
            "yolo_seg",
            mac,
            linux,
            truths,
            SHA_A,
            evidence_root=tmp_path,
            mac_prediction_inventory_sha256=SHA_B,
            linux_prediction_inventory_sha256=SHA_C,
            source_commit=SOURCE_COMMIT,
            fixture_mode=True,
        )


def _rehash(document: dict[str, object]) -> None:
    unhashed = dict(document)
    unhashed.pop("lock_sha256", None)
    document["lock_sha256"] = hashlib.sha256(
        canonical_json_bytes(unhashed)
    ).hexdigest()


def _formalized_lock(lock: ThresholdLock) -> ThresholdLock:
    platform_metrics = {
        platform: replace(metrics, sample_count=200)
        for platform, metrics in lock.platform_metrics.items()
    }
    return replace(
        lock,
        formal=True,
        platform_sample_counts={"macos": 200, "linux": 200},
        platform_metrics=platform_metrics,
        lock_sha256="0" * 64,
    ).with_recomputed_sha256()


def test_threshold_lock_is_canonical_reproducible_and_binds_all_inputs(
    tmp_path: Path,
) -> None:
    first = _calibrate(tmp_path / "first", "yolo_seg")
    second = _calibrate(tmp_path / "second", "yolo_seg")

    assert first.lock_sha256 == second.lock_sha256
    assert first.source_commit == SOURCE_COMMIT
    assert first.mac_prediction_inventory_sha256 == SHA_B
    assert first.linux_prediction_inventory_sha256 == SHA_C
    assert first.formal is False
    assert first.platform_sample_counts == {"macos": 3, "linux": 3}
    path = write_threshold_lock(tmp_path / "lock.json", first)
    assert path.read_bytes() == canonical_json_bytes(json.loads(path.read_bytes()))
    assert verify_threshold_lock(path) == first


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("formal", True, "THRESHOLD_LOCK_FORMALITY_INVALID"),
        (
            "platform_sample_counts",
            {"macos": 4, "linux": 3},
            "THRESHOLD_LOCK_SAMPLE_COUNTS_INVALID",
        ),
        (
            "platform_sample_counts",
            {"macos": 3.0, "linux": 3},
            "THRESHOLD_LOCK_SAMPLE_COUNTS_INVALID",
        ),
        (
            "platform_sample_counts",
            {"macos": True, "linux": 3},
            "THRESHOLD_LOCK_SAMPLE_COUNTS_INVALID",
        ),
    ],
)
def test_threshold_lock_verifier_rejects_formality_or_actual_count_mismatch(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    path = write_threshold_lock(
        tmp_path / "lock.json", _calibrate(tmp_path / "run", "yolo_seg")
    )
    document = json.loads(path.read_text())
    document[field] = value
    _rehash(document)
    path.write_bytes(canonical_json_bytes(document))

    with pytest.raises(CalibrationError, match=error):
        verify_threshold_lock(path)


@pytest.mark.parametrize(
    "field",
    ["box_threshold", "target_confidence_threshold"],
)
def test_threshold_lock_verifier_rejects_old_grounded_grid_endpoints(
    tmp_path: Path,
    field: str,
) -> None:
    path = write_threshold_lock(
        tmp_path / "lock.json",
        _calibrate(tmp_path / "run", "grounded_sam"),
    )
    document = json.loads(path.read_text())
    document["selected"][field] = "0.95"
    _rehash(document)
    path.write_bytes(canonical_json_bytes(document))

    with pytest.raises(CalibrationError, match="THRESHOLD_LOCK_SELECTED_INVALID"):
        verify_threshold_lock(path)


@pytest.mark.parametrize(
    ("model", "field", "value"),
    [
        ("yolo_seg", "imgsz", 640.0),
        ("yolo_seg", "imgsz", True),
        ("grounded_sam", "min_mask_pixels", 64.0),
        ("grounded_sam", "min_mask_pixels", True),
    ],
)
def test_threshold_lock_verifier_rejects_non_integer_fixed_config_fields(
    tmp_path: Path,
    model: str,
    field: str,
    value: object,
) -> None:
    path = write_threshold_lock(
        tmp_path / "lock.json", _calibrate(tmp_path / "run", model)
    )
    document = json.loads(path.read_text())
    document["selected"][field] = value
    _rehash(document)
    path.write_bytes(canonical_json_bytes(document))

    with pytest.raises(CalibrationError, match="THRESHOLD_LOCK_SELECTED_INVALID"):
        verify_threshold_lock(path)


def test_threshold_lock_verifier_rejects_changed_selected_and_bound_inventory(
    tmp_path: Path,
) -> None:
    path = write_threshold_lock(tmp_path / "lock.json", _calibrate(tmp_path / "run", "yolo_seg"))
    document = json.loads(path.read_text())
    document["selected"]["conf"] = "0.90"
    path.write_bytes(canonical_json_bytes(document))
    with pytest.raises(CalibrationError, match="THRESHOLD_LOCK_HASH_MISMATCH"):
        verify_threshold_lock(path)

    path = write_threshold_lock(tmp_path / "lock-2.json", _calibrate(tmp_path / "run-2", "yolo_seg"))
    document = json.loads(path.read_text())
    document["mac_prediction_inventory_sha256"] = "d" * 64
    path.write_bytes(canonical_json_bytes(document))
    with pytest.raises(CalibrationError, match="THRESHOLD_LOCK_HASH_MISMATCH"):
        verify_threshold_lock(path)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("schema_version", "other/v1", "THRESHOLD_LOCK_SCHEMA_INVALID"),
        ("model", "other", "THRESHOLD_LOCK_MODEL_INVALID"),
        ("val_inventory_sha256", "z" * 64, "THRESHOLD_LOCK_FIELD_INVALID"),
        ("source_commit", "not-a-commit", "THRESHOLD_LOCK_FIELD_INVALID"),
        ("grid_version", "other-grid", "THRESHOLD_LOCK_VERSION_INVALID"),
    ],
)
def test_threshold_lock_verifier_rejects_wrong_schema_model_inventory_source_or_version(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    path = write_threshold_lock(tmp_path / "lock.json", _calibrate(tmp_path / "run", "yolo_seg"))
    document = json.loads(path.read_text())
    document[field] = value
    _rehash(document)
    path.write_bytes(canonical_json_bytes(document))

    with pytest.raises(CalibrationError, match=error):
        verify_threshold_lock(path)


def test_threshold_lock_verifier_rejects_noncanonical_or_inconsistent_metrics(
    tmp_path: Path,
) -> None:
    path = write_threshold_lock(tmp_path / "lock.json", _calibrate(tmp_path / "run", "yolo_seg"))
    document = json.loads(path.read_text())
    path.write_text(json.dumps(document, indent=2))
    with pytest.raises(CalibrationError, match="THRESHOLD_LOCK_NOT_CANONICAL"):
        verify_threshold_lock(path)

    path = write_threshold_lock(tmp_path / "lock-2.json", _calibrate(tmp_path / "run-2", "yolo_seg"))
    document = json.loads(path.read_text())
    document["objective_metrics"]["min_platform_macro_f1"] = 0.123
    _rehash(document)
    path.write_bytes(canonical_json_bytes(document))
    with pytest.raises(CalibrationError, match="THRESHOLD_LOCK_METRICS_INVALID"):
        verify_threshold_lock(path)


def test_test_seal_rejects_fixture_locks_before_access_event(
    tmp_path: Path,
) -> None:
    yolo_path = write_threshold_lock(
        tmp_path / "yolo-lock.json", _calibrate(tmp_path / "yolo", "yolo_seg")
    )
    grounded_path = write_threshold_lock(
        tmp_path / "grounded-lock.json",
        _calibrate(tmp_path / "grounded", "grounded_sam"),
    )
    access_log = tmp_path / "test-access.jsonl"
    caught: CalibrationError | None = None
    try:
        unlock_test_seal(
            DatasetTestSeal("d" * 64, access_log),
            yolo_path,
            grounded_path,
        )
    except CalibrationError as error:
        caught = error

    assert not access_log.exists()
    assert caught is not None
    assert "TEST_SEAL_LOCK_NONFORMAL" in str(caught)

    access_log.write_bytes(canonical_json_bytes({"event": "PREEXISTING"}))
    existing = access_log.read_bytes()
    with pytest.raises(CalibrationError, match="TEST_SEAL_LOCK_NONFORMAL"):
        unlock_test_seal(
            DatasetTestSeal("d" * 64, access_log),
            yolo_path,
            grounded_path,
        )
    assert access_log.read_bytes() == existing


def test_test_seal_unlocks_two_consistent_formal_model_locks_before_access_event(
    tmp_path: Path,
) -> None:
    yolo_path = write_threshold_lock(
        tmp_path / "yolo-lock.json",
        _formalized_lock(_calibrate(tmp_path / "yolo", "yolo_seg")),
    )
    grounded_path = write_threshold_lock(
        tmp_path / "grounded-lock.json",
        _formalized_lock(_calibrate(tmp_path / "grounded", "grounded_sam")),
    )
    access_log = tmp_path / "test-access.jsonl"

    unlocked = unlock_test_seal(
        DatasetTestSeal("d" * 64, access_log),
        yolo_path,
        grounded_path,
    )

    assert unlocked.access_grant is not None
    assert access_log.read_text().count("TEST_ACCESS_GRANTED") == 1
    assert unlocked.access_grant.threshold_lock_sha256s == (
        verify_threshold_lock(yolo_path).lock_sha256,
        verify_threshold_lock(grounded_path).lock_sha256,
    )


def test_test_seal_rejects_two_yolo_locks_before_appending_access_event(
    tmp_path: Path,
) -> None:
    first = write_threshold_lock(
        tmp_path / "first.json",
        _formalized_lock(_calibrate(tmp_path / "first", "yolo_seg")),
    )
    second_lock = _formalized_lock(
        _calibrate(tmp_path / "second", "yolo_seg")
    )
    second_lock = replace(
        second_lock,
        linux_prediction_inventory_sha256="e" * 64,
        lock_sha256="0" * 64,
    ).with_recomputed_sha256()
    second = write_threshold_lock(tmp_path / "second.json", second_lock)
    access_log = tmp_path / "test-access.jsonl"

    with pytest.raises(CalibrationError, match="TEST_SEAL_LOCK_MODEL_MISMATCH"):
        unlock_test_seal(DatasetTestSeal("d" * 64, access_log), first, second)

    assert not access_log.exists()


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        (
            "val_inventory_sha256",
            "e" * 64,
            "TEST_SEAL_LOCK_INVENTORY_MISMATCH",
        ),
        (
            "source_commit",
            "f" * 40,
            "TEST_SEAL_LOCK_SOURCE_MISMATCH",
        ),
    ],
)
def test_test_seal_requires_shared_val_inventory_and_source_before_access_event(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    yolo_path = write_threshold_lock(
        tmp_path / "yolo.json",
        _formalized_lock(_calibrate(tmp_path / "yolo", "yolo_seg")),
    )
    grounded_lock = _formalized_lock(
        _calibrate(tmp_path / "grounded", "grounded_sam")
    )
    grounded_lock = replace(
        grounded_lock,
        **{field: value, "lock_sha256": "0" * 64},
    ).with_recomputed_sha256()
    grounded_path = write_threshold_lock(tmp_path / "grounded.json", grounded_lock)
    access_log = tmp_path / "test-access.jsonl"

    with pytest.raises(CalibrationError, match=error):
        unlock_test_seal(
            DatasetTestSeal("d" * 64, access_log),
            yolo_path,
            grounded_path,
        )

    assert not access_log.exists()
