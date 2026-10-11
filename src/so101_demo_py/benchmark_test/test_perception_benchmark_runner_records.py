"""Run specification validation, adapter identity, error records and canonical record order."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from perception_benchmark_runner_support import (
    SHA_B,
    SyntheticAdapter,
    SyntheticGroundedAdapter,
    _record,
    _spec,
    _synthetic_inventory,
)
import pytest

from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    RawDetectionResult,
)
from so101_demo.perception_benchmark.codec import (
    read_mask,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
    DecisionOutput,
    PredictionRecord,
    RunStatus,
)
from so101_demo.perception_benchmark.runner.detector_runner import DetectorBenchmarkRunner
from so101_demo.perception_benchmark.runner.records import _record_from_document


@pytest.mark.parametrize("threshold", (0.0, 1.01, float("nan"), True))
def test_run_spec_rejects_invalid_production_candidate_mask_iou_threshold(
    tmp_path: Path,
    threshold: object,
) -> None:
    inventory = _synthetic_inventory(tmp_path)

    with pytest.raises(
        ValueError,
        match="production_candidate_mask_iou_threshold must be in",
    ):
        _spec(
            inventory,
            tmp_path / "run",
            production_candidate_mask_iou_threshold=threshold,
        )


@pytest.mark.parametrize(
    ("model", "model_id"),
    (
        ("yolo_seg", "not-yolo-imposter"),
        ("yolo_seg", f"{YOLO_MODEL_ID}-suffix"),
        ("grounded_sam", "grounded-sam-wrong"),
        ("grounded_sam", f"prefix-{GROUNDED_SAM_MODEL_ID}"),
    ),
)
def test_runner_rejects_noncanonical_adapter_identity_before_collection(
    tmp_path: Path, model: str, model_id: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, count=2)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter: SyntheticAdapter | SyntheticGroundedAdapter
    if model == "yolo_seg":
        adapter = SyntheticAdapter(output_root)
    else:
        adapter = SyntheticGroundedAdapter(output_root)
    adapter.model_id = model_id

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root, model=model)
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "ADAPTER_MODEL_MISMATCH"
    assert adapter.calls == []
    assert not (output_root / "records").exists()


def test_runner_stops_after_first_noncanonical_raw_result_without_continuation(
    tmp_path: Path,
) -> None:
    class NearResultAdapter(SyntheticAdapter):
        def collect(self, frame: object, mode: CollectionMode) -> RawDetectionResult:
            self.candidate_counts[int(frame.source_stamp_ns) - 1] = 0  # type: ignore[attr-defined]
            result = super().collect(frame, mode)
            return replace(result, model_id=f"{YOLO_MODEL_ID}-suffix")

    inventory = _synthetic_inventory(tmp_path, count=3)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = NearResultAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "MODEL_IDENTITY_MISMATCH"
    assert adapter.calls == [0]
    assert list((output_root / "records").iterdir()) == []


def test_runner_rechecks_adapter_identity_on_error_record_path(
    tmp_path: Path,
) -> None:
    class MutatingErrorAdapter(SyntheticAdapter):
        def collect(self, frame: object, mode: CollectionMode) -> RawDetectionResult:
            self.calls.append(int(frame.source_stamp_ns) - 1)  # type: ignore[attr-defined]
            self.model_id = "not-yolo-imposter"
            raise RuntimeError("model failed after identity corruption")

    inventory = _synthetic_inventory(tmp_path, count=3)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = MutatingErrorAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "MODEL_IDENTITY_MISMATCH"
    assert adapter.calls == [0]
    assert list((output_root / "records").iterdir()) == []


def test_grounded_candidate_round_trips_through_runner_record_contract(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, count=1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticGroundedAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root, model="grounded_sam")
    )

    assert manifest.status is RunStatus.VALID
    record = _record_from_document(_record(output_root, 0))
    assert isinstance(record, PredictionRecord)
    assert record.model_id == "grounding-dino-tiny+sam2.1-hiera-tiny"
    candidate = record.raw_candidates[0]
    assert candidate.grounding_box_score == 0.81
    assert candidate.grounding_text_score == 0.73
    assert candidate.sam_quality == 0.92
    assert candidate.class_confidence is None
    expected_mask = np.zeros((16, 20), dtype=bool)
    expected_mask[3:11, 4:12] = True
    assert np.array_equal(read_mask(candidate.mask, output_root), expected_mask)


def test_inference_exception_writes_error_record_and_continues_full_inventory(
    tmp_path: Path,
) -> None:
    """Catch an inference exception shrinking the formal denominator."""

    inventory = _synthetic_inventory(tmp_path)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root, failures={3: RuntimeError("model failed")})

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.VALID
    assert manifest.record_count == 8
    assert manifest.error_count == 1
    assert adapter.calls == list(range(8))
    failed = _record(output_root, 3)
    assert failed["decision"] == DecisionOutput.ERROR.value
    assert failed["record_status"] == "ERROR"
    assert failed["raw_candidates"] == []
    assert failed["selected_candidate_id"] is None


@pytest.mark.parametrize(
    ("error", "error_type", "timed_out", "oom"),
    (
        (TimeoutError("deadline"), "TIMEOUT", True, False),
        (MemoryError("CUDA out of memory"), "OOM", False, True),
        (RuntimeError("accelerator synchronize failed"), "SYNC", False, False),
        (ValueError("RESULT_CONTRACT_INVALID"), "SCHEMA", False, False),
        (RuntimeError("model exploded\napi_token=secret-value"), "MODEL", False, False),
    ),
)
def test_error_records_are_typed_bounded_sanitized_and_never_retried(
    tmp_path: Path,
    error: BaseException,
    error_type: str,
    timed_out: bool,
    oom: bool,
) -> None:
    """Catch typed inference failures becoming retries, fallback, or unsafe text."""

    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root, failures={0: error})

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.VALID
    assert adapter.calls == [0]
    record = _record(output_root, 0)
    assert record["error_type"] == error_type
    assert record["timed_out"] is timed_out
    assert record["oom"] is oom
    assert record["fallback_used"] is False
    assert record["model_id"] == adapter.model_id
    assert "\n" not in record["error_summary"]
    assert len(record["error_summary"]) <= 240
    assert "secret-value" not in record["error_summary"]


@pytest.mark.parametrize("interrupt", (KeyboardInterrupt(), SystemExit(2)))
def test_process_interrupts_are_not_downgraded_to_per_image_error(
    tmp_path: Path, interrupt: BaseException
) -> None:
    """Catch operator/process termination being swallowed as a model error."""

    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root, failures={0: interrupt})

    with pytest.raises(type(interrupt)):
        DetectorBenchmarkRunner(adapter, output_root).run(
            _spec(inventory, output_root)
        )

    assert not (output_root / "records" / "000000.json").exists()


def test_records_follow_canonical_inventory_order_and_four_state_semantics(
    tmp_path: Path,
) -> None:
    """Catch filename order, zip/truncation, or an alternate decision vocabulary."""

    inventory = _synthetic_inventory(tmp_path, 4)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(
        output_root, candidate_counts={0: 0, 1: 1, 2: 2, 3: 1}
    )

    DetectorBenchmarkRunner(adapter, output_root).run(_spec(inventory, output_root))

    assert sorted(path.name for path in (output_root / "records").iterdir()) == [
        "000000.json",
        "000001.json",
        "000002.json",
        "000003.json",
    ]
    assert [_record(output_root, index)["decision"] for index in range(4)] == [
        "NOT_FOUND",
        "UNIQUE",
        "AMBIGUOUS",
        "UNIQUE",
    ]
    for index, sample in enumerate(inventory.samples):
        record = _record(output_root, index)
        assert record["formal_sample_index"] == index
        assert record["image_sha256"] == sample.image_sha256
        assert record["image_width"] == 20
        assert record["image_height"] == 16
        assert record["resource_samples"][0]["process_cpu_percent"] == 0.0
        assert record["timing_breakdown"]["sam_ms"] is None


def test_val_raw_rejects_lock_and_changed_image_before_any_model_call(
    tmp_path: Path,
) -> None:
    """Catch VAL_RAW consuming a lock or inference running after input SHA drift."""

    inventory = _synthetic_inventory(tmp_path, 2)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)
    locked = _spec(inventory, output_root, threshold_lock_sha256=SHA_B)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(locked)

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "VAL_RAW_FORBIDS_THRESHOLD_LOCK"
    assert adapter.calls == []

    clean_root = tmp_path / "run-drift"
    clean_root.mkdir()
    changed = inventory.dataset_root / inventory.samples[0].image_relpath
    changed.write_bytes(changed.read_bytes() + b"tampered")
    drift_adapter = SyntheticAdapter(clean_root)
    manifest = DetectorBenchmarkRunner(drift_adapter, clean_root).run(
        _spec(inventory, clean_root)
    )
    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "INPUT_IMAGE_SHA256_CHANGED"
    assert drift_adapter.calls == []
