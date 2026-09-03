"""Low-frequency perception benchmark regression tests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest
import so101_demo.perception_benchmark.dataset as dataset_module
from PIL import Image
from so101_demo.core.detection import DetectionBatch, DetectionCandidate
from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    ProductionObservation,
    RawDetectionResult,
    ResourceSamplingError,
)
from so101_demo.perception_benchmark.calibration import (
    GroundedSamBenchmarkThresholds,
    ObjectiveCalibrationMetrics,
    PlatformCalibrationMetrics,
    ThresholdLock,
    YoloThresholds,
    write_threshold_lock,
)
from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    canonical_json_bytes,
    encode_mask_rle,
    read_mask,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
    DecisionOutput,
    MaskRef,
    PredictionRecord,
    RawCandidate,
    RunKind,
    RunStatus,
    RuntimeProvenance,
)
from so101_demo.perception_benchmark.dataset import (
    DatasetInventory,
    DatasetSampleRef,
    append_test_access_event,
)
from so101_demo.perception_benchmark.runner import (
    DetectorBenchmarkRunner,
    LoadedRunEvidence,
    RunCheckpoint,
    RunEvidenceExpectation,
    RunIntegrityError,
    RunSpec,
    _record_from_document,
    load_verified_run_evidence,
    verify_resume,
)
from so101_demo.perception_benchmark.timing import (
    PhaseTimingBreakdown,
    ResourceSample,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SOURCE_COMMIT = "deadbeef" * 5


def _resource_sample(*, temperature: float | None = None) -> ResourceSample:
    missing = {
        "gpu_temperature_celsius": "fixture sensor unavailable",
        "gpu_power_watts": "fixture sensor unavailable",
    }
    if temperature is not None:
        missing.pop("gpu_temperature_celsius")
    return ResourceSample(
        process_rss_bytes=4096,
        process_cpu_percent=0.0,
        gpu_memory_allocated_bytes=0,
        gpu_memory_reserved_bytes=0,
        gpu_utilization_percent=0.0,
        gpu_temperature_celsius=temperature,
        gpu_power_watts=None,
        unavailable_reasons=missing,
        tool_versions={"fixture": "1"},
    )


def _inventory_document(
    inventory: DatasetInventory,
    test_access: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": inventory.schema_version,
        "split": inventory.split,
        "archive_sha256": inventory.archive_sha256,
        "sample_count": inventory.sample_count,
        "scenario_counts": dict(inventory.scenario_counts),
        "test_access": test_access,
        "samples": [
            {
                "formal_sample_index": sample.formal_sample_index,
                "split": sample.split,
                "scenario": sample.scenario,
                "image_relpath": sample.image_relpath,
                "label_relpath": sample.label_relpath,
                "truth_relpath": sample.truth_relpath,
                "image_sha256": sample.image_sha256,
                "truth_count": sample.truth_count,
            }
            for sample in inventory.samples
        ],
    }


def _synthetic_inventory(
    root: Path,
    count: int = 8,
    *,
    split: str = "val",
    test_access: dict[str, object] | None = None,
) -> DatasetInventory:
    dataset_root = root / "dataset"
    image_root = dataset_root / "images" / split
    image_root.mkdir(parents=True)
    payloads: list[tuple[str, bytes]] = []
    for index in range(count):
        path = image_root / f"fixture-{index:03d}.png"
        image = Image.new("RGB", (20, 16), (index + 1, 2, 3))
        image.save(path, format="PNG")
        payload = path.read_bytes()
        payloads.append((hashlib.sha256(payload).hexdigest(), payload))

    samples: list[DatasetSampleRef] = []
    for formal_index, (digest, payload) in enumerate(sorted(payloads)):
        image_relpath = f"images/{split}/sample-{formal_index:03d}.png"
        image_path = dataset_root / image_relpath
        image_path.write_bytes(payload)
        samples.append(
            DatasetSampleRef(
                formal_sample_index=formal_index,
                split=split,
                scenario="fixture",
                image_relpath=image_relpath,
                label_relpath=f"labels/{split}/sample-{formal_index:03d}.txt",
                truth_relpath=f"truth/{split}/sample-{formal_index:03d}.json",
                image_sha256=digest,
                truth_count=1,
            )
        )

    provisional = DatasetInventory(
        schema_version="so101-perception-benchmark/v1",
        split=split,
        archive_sha256=SHA_A,
        inventory_sha256=SHA_A,
        dataset_root=dataset_root,
        sample_count=count,
        scenario_counts={"fixture": count},
        samples=tuple(samples),
        test_access_event_sha256=(
            None if test_access is None else str(test_access["event_sha256"])
        ),
    )
    document = _inventory_document(provisional, test_access)
    payload = canonical_json_bytes(document)
    inventory = replace(
        provisional, inventory_sha256=hashlib.sha256(payload).hexdigest()
    )
    atomic_write_json(
        dataset_root / "inventory.json", _inventory_document(inventory, test_access)
    )
    (dataset_root / "inventory.sha256").write_text(
        f"{inventory.inventory_sha256}  inventory.json\n", encoding="ascii"
    )
    dataset_module._issue_inventory(inventory)
    return inventory


class SyntheticAdapter:
    model_id = YOLO_MODEL_ID
    runtime_device = "mps"
    runtime_version = "fixture-1"
    _weights_sha256 = SHA_B

    def __init__(
        self,
        evidence_root: Path,
        *,
        failures: dict[int, BaseException] | None = None,
        candidate_counts: dict[int, int] | None = None,
        temperatures: dict[int, float] | None = None,
        empty_resources_at: int | None = None,
    ) -> None:
        self.evidence_root = evidence_root
        self.failures = failures or {}
        self.candidate_counts = candidate_counts or {}
        self.temperatures = temperatures or {}
        self.empty_resources_at = empty_resources_at
        self.calls: list[int] = []

    def collect(self, frame: object, mode: CollectionMode) -> RawDetectionResult:
        assert mode is CollectionMode.LOW_FLOOR
        index = int(frame.source_stamp_ns) - 1  # type: ignore[attr-defined]
        self.calls.append(index)
        failure = self.failures.get(index)
        if failure is not None:
            raise failure
        candidate_count = self.candidate_counts.get(index, 1)
        candidates: list[RawCandidate] = []
        for candidate_index in range(candidate_count):
            mask = np.zeros((16, 20), dtype=bool)
            mask[2 + candidate_index : 8 + candidate_index, 3:10] = True
            candidate_id = f"yolo-{candidate_index:03d}"
            relative = f"adapter-masks/{index:06d}/{candidate_id}.rle.json"
            atomic_write_json(
                self.evidence_root / relative, encode_mask_rle(mask)
            )
            candidates.append(
                RawCandidate(
                    candidate_id=candidate_id,
                    label="plastic_cup",
                    bbox_xyxy=(3.0, 2.0, 10.0, 10.0),
                    mask=MaskRef(
                        relative_path=relative,
                        sha256=hashlib.sha256(
                            mask.astype(np.uint8).tobytes(order="C")
                        ).hexdigest(),
                        pixel_count=int(mask.sum()),
                        image_width=20,
                        image_height=16,
                    ),
                    ranking_score=0.9 - candidate_index * 0.1,
                    ranking_score_source="class_confidence",
                    class_confidence=0.9 - candidate_index * 0.1,
                    grounding_box_score=None,
                    grounding_text_score=None,
                    sam_quality=None,
                )
            )
        resources = (
            ()
            if self.empty_resources_at == index
            else (_resource_sample(temperature=self.temperatures.get(index)),)
        )
        return RawDetectionResult(
            model_id=self.model_id,
            runtime_device="mps",
            dtype="float32",
            collection_mode=CollectionMode.LOW_FLOOR,
            raw_candidates=tuple(candidates),
            phase_timings=PhaseTimingBreakdown(
                preprocess_ms=0.0,
                dino_or_yolo_ms=1.0,
                sam_ms=None,
                postprocess_ms=0.0,
                selector_ms=None,
                total_ms=1.0,
            ),
            resource_samples=resources,
            fallback_used=False,
            irreversible_limits={"max_det": 300, "nms_iou": 0.9},
        )


class SyntheticGroundedAdapter:
    model_id = GROUNDED_SAM_MODEL_ID
    runtime_device = "mps"
    runtime_version = "fixture-1"
    _manifest_sha256 = SHA_B

    def __init__(self, evidence_root: Path) -> None:
        self.evidence_root = evidence_root
        self.calls: list[int] = []

    def collect(self, frame: object, mode: CollectionMode) -> RawDetectionResult:
        assert mode is CollectionMode.LOW_FLOOR
        index = int(frame.source_stamp_ns) - 1  # type: ignore[attr-defined]
        self.calls.append(index)
        mask = np.zeros((16, 20), dtype=bool)
        mask[3:11, 4:12] = True
        candidate_id = "grounded-sam-000"
        relative = f"adapter-masks/{index:06d}/{candidate_id}.rle.json"
        atomic_write_json(self.evidence_root / relative, encode_mask_rle(mask))
        candidate = RawCandidate(
            candidate_id=candidate_id,
            label="plastic_cup",
            bbox_xyxy=(4.0, 3.0, 12.0, 11.0),
            mask=MaskRef(
                relative_path=relative,
                sha256=hashlib.sha256(
                    mask.astype(np.uint8).tobytes(order="C")
                ).hexdigest(),
                pixel_count=int(mask.sum()),
                image_width=20,
                image_height=16,
            ),
            ranking_score=0.81,
            ranking_score_source="grounding_box_score",
            class_confidence=None,
            grounding_box_score=0.81,
            grounding_text_score=0.73,
            sam_quality=0.92,
        )
        return RawDetectionResult(
            model_id=self.model_id,
            runtime_device="mps",
            dtype="float32",
            collection_mode=CollectionMode.LOW_FLOOR,
            raw_candidates=(candidate,),
            phase_timings=PhaseTimingBreakdown(
                preprocess_ms=0.0,
                dino_or_yolo_ms=1.0,
                sam_ms=2.0,
                postprocess_ms=0.0,
                selector_ms=None,
                total_ms=3.0,
            ),
            resource_samples=(_resource_sample(),),
            fallback_used=False,
            irreversible_limits={
                "box_threshold": 0.01,
                "text_threshold": 0.01,
            },
        )


def _runtime_provenance(
    *, device: str = "mps", weights_sha256: str = SHA_B
) -> RuntimeProvenance:
    return RuntimeProvenance(
        runtime_device=device,  # type: ignore[arg-type]
        runtime_name="synthetic-runtime",
        runtime_version="fixture-1",
        weights_sha256=weights_sha256,
        environment={"fixture": "runner", "torch": "2.8.0"},
    )


def _spec(
    inventory: DatasetInventory,
    output_root: Path,
    **overrides: object,
) -> RunSpec:
    values: dict[str, object] = {
        "run_id": "fixture-val-raw",
        "run_kind": RunKind.VAL_RAW,
        "platform": "macos",
        "model": "yolo_seg",
        "device": "mps",
        "dtype": "float32",
        "inventory": inventory,
        "config_sha256": SHA_A,
        "threshold_lock_sha256": None,
        "threshold_lock_path": None,
        "source_commit": SOURCE_COMMIT,
        "output_root": output_root,
        "collection_mode": CollectionMode.LOW_FLOOR,
        "runtime_provenance": _runtime_provenance(),
    }
    values.update(overrides)
    return RunSpec(**values)  # type: ignore[arg-type]


def _record(root: Path, index: int) -> dict[str, object]:
    return json.loads(
        (root / "records" / f"{index:06d}.json").read_text(encoding="utf-8")
    )


def _checkpoint(root: Path) -> RunCheckpoint:
    document = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
    document["records_dir"] = Path(document["records_dir"])
    document["run_kind"] = RunKind(document["run_kind"])
    document["collection_mode"] = CollectionMode(document["collection_mode"])
    return RunCheckpoint(**document)


def _record_inventory_digest(root: Path) -> str:
    rows = [
        {
            "formal_sample_index": int(path.stem),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted((root / "records").glob("*.json"))
    ]
    return hashlib.sha256(canonical_json_bytes({"records": rows})).hexdigest()


def _formal_yolo_lock(*, formal: bool = True, model: str = "yolo_seg") -> ThresholdLock:
    metrics = PlatformCalibrationMetrics(
        sample_count=200,
        error_count=0,
        macro_f1=0.9,
        mask_ap50_95=0.8,
        unsafe_unique_count=0,
        unsafe_unique_denominator=100,
        unsafe_unique_rate=0.0,
        two_cup_both_matched_recall=0.9,
    )
    lock = ThresholdLock(
        schema_version="so101-threshold-lock/v1",
        model=model,  # type: ignore[arg-type]
        grid_version=(
            "yolo-seg-grid/v1"
            if model == "yolo_seg"
            else "grounded-sam-grid/v1"
        ),
        objective_version="joint-platform-val/v1",
        tie_break_version="joint-platform-seven-level/v1",
        val_inventory_sha256=SHA_A,
        mac_prediction_inventory_sha256=SHA_B,
        linux_prediction_inventory_sha256=SHA_C,
        formal=formal,
        platform_sample_counts={"macos": 200, "linux": 200},
        selected=(
            YoloThresholds(
                Decimal("0.50"), Decimal("0.50"), Decimal("0.50"), 640
            )
            if model == "yolo_seg"
            else GroundedSamBenchmarkThresholds(
                Decimal("0.50"),
                Decimal("0.50"),
                Decimal("0.50"),
                Decimal("0.50"),
                Decimal("0.85"),
                64,
                Decimal("0.50"),
            )
        ),
        outcome="SAFE_CALIBRATED",
        deployable=True,
        source_commit=SOURCE_COMMIT,
        objective_metrics=ObjectiveCalibrationMetrics(0.9, 0.9, 0.8, 0.9),
        platform_metrics={"macos": metrics, "linux": metrics},
        lock_sha256="0" * 64,
    )
    return lock.with_recomputed_sha256()


def _locked_inventory(
    root: Path,
    lock: ThresholdLock,
    *,
    write_lock_before_access: bool = True,
    count: int = 1,
) -> tuple[DatasetInventory, Path, Path]:
    lock_path = root / "locks" / "yolo.json"
    lock_path.parent.mkdir(parents=True)
    if write_lock_before_access:
        write_threshold_lock(lock_path, lock)
    access_log = root / "test-access.jsonl"
    grant = append_test_access_event(
        access_log,
        SHA_A,
        (lock.lock_sha256, SHA_C),
    )
    if not write_lock_before_access:
        write_threshold_lock(lock_path, lock)
    test_access = {
        "event_sha256": grant.event_sha256,
        "sealed_member_inventory_sha256": grant.sealed_member_inventory_sha256,
        "threshold_lock_sha256s": list(grant.threshold_lock_sha256s),
        "granted_at": grant.granted_at,
        "access_log_path": str(access_log),
    }
    return (
        _synthetic_inventory(root, count, split="test", test_access=test_access),
        lock_path,
        access_log,
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


@pytest.mark.parametrize(
    "mutation",
    (
        "gap",
        "duplicate",
        "record-tamper",
        "record-content-tamper",
        "mask-tamper",
        "checkpoint-sha",
        "config",
        "source",
        "model",
        "device",
        "dtype",
        "run-kind",
        "lock",
        "run-id",
        "platform",
        "model-id",
        "weights",
        "collection-mode",
        "runtime-name",
        "runtime-version",
        "runtime-environment",
        "thermal-limit",
        "record-count",
        "record-inventory",
        "inventory",
    ),
)
def test_resume_rejects_any_noncontiguous_tampered_or_changed_identity(
    tmp_path: Path, mutation: str
) -> None:
    """Catch resume selecting a next filename instead of proving one exact prefix."""

    inventory = _synthetic_inventory(tmp_path, 4)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    checkpoint = _checkpoint(output_root)

    if mutation == "gap":
        (output_root / "records" / "000001.json").rename(
            output_root / "records" / "000005.json"
        )
    elif mutation == "duplicate":
        document = _record(output_root, 1)
        document["formal_sample_index"] = 0
        atomic_write_json(output_root / "records" / "000001.json", document)
    elif mutation == "record-tamper":
        path = output_root / "records" / "000002.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "record-content-tamper":
        path = output_root / "records" / "000001.json"
        document = _record(output_root, 1)
        document["timing_breakdown"]["dino_or_yolo_ms"] = 2.0
        document["timing_breakdown"]["total_ms"] = 2.0
        atomic_write_json(path, document)
    elif mutation == "mask-tamper":
        mask_path = output_root / _record(output_root, 2)["raw_candidates"][0]["mask"]["relative_path"]
        mask_path.write_bytes(mask_path.read_bytes() + b" ")
    elif mutation == "checkpoint-sha":
        checkpoint = replace(checkpoint, last_record_sha256=SHA_A)
    elif mutation == "config":
        checkpoint = replace(checkpoint, config_sha=SHA_B)
    elif mutation == "source":
        checkpoint = replace(checkpoint, source_commit="cafebabe" * 5)
    elif mutation == "model":
        checkpoint = replace(checkpoint, model="grounded_sam")
    elif mutation == "device":
        checkpoint = replace(checkpoint, device="cuda")
    elif mutation == "dtype":
        checkpoint = replace(checkpoint, dtype="float16")
    elif mutation == "run-kind":
        checkpoint = replace(checkpoint, run_kind=RunKind.TEST_RAW_FROZEN)
    elif mutation == "lock":
        checkpoint = replace(checkpoint, threshold_lock_sha256=SHA_B)
    elif mutation == "run-id":
        checkpoint = replace(checkpoint, run_id="other-run")
    elif mutation == "platform":
        checkpoint = replace(checkpoint, platform="linux")
    elif mutation == "model-id":
        checkpoint = replace(checkpoint, model_id="other-yolo")
    elif mutation == "weights":
        checkpoint = replace(checkpoint, weights_sha256=SHA_C)
    elif mutation == "collection-mode":
        checkpoint = replace(checkpoint, collection_mode=None)
    elif mutation == "runtime-name":
        checkpoint = replace(checkpoint, runtime_name="other-runtime")
    elif mutation == "runtime-version":
        checkpoint = replace(checkpoint, runtime_version="fixture-2")
    elif mutation == "runtime-environment":
        checkpoint = replace(checkpoint, runtime_environment={"fixture": "changed"})
    elif mutation == "thermal-limit":
        checkpoint = replace(checkpoint, max_gpu_temperature_celsius=90.0)
    elif mutation == "record-count":
        checkpoint = replace(checkpoint, record_count=3)
    elif mutation == "record-inventory":
        checkpoint = replace(checkpoint, record_inventory_sha256=SHA_C)
    else:
        checkpoint = replace(checkpoint, inventory_sha256=SHA_C)

    with pytest.raises(RunIntegrityError):
        verify_resume(
            checkpoint,
            inventory,
            config_sha=SHA_A,
            source_commit=SOURCE_COMMIT,
        )


def test_exact_valid_prefix_resumes_without_reprocessing_or_overwriting(
    tmp_path: Path,
) -> None:
    """Catch a complete verified prefix being re-run or its artifacts overwritten."""

    inventory = _synthetic_inventory(tmp_path, 4)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    before = {
        path.name: path.read_bytes() for path in (output_root / "records").iterdir()
    }
    manifest_before = (output_root / "manifest.json").read_bytes()
    resumed_adapter = SyntheticAdapter(output_root)

    manifest = DetectorBenchmarkRunner(resumed_adapter, output_root).run(spec)

    assert manifest.status is RunStatus.VALID
    assert manifest.record_count == 4
    assert resumed_adapter.calls == []
    assert {
        path.name: path.read_bytes() for path in (output_root / "records").iterdir()
    } == before
    assert (output_root / "manifest.json").read_bytes() == manifest_before


@pytest.mark.parametrize(
    "mutation",
    (
        "delete-mask",
        "delete-record",
        "delete-checkpoint",
        "tamper-tail",
        "change-spec",
        "input-drift",
    ),
)
def test_terminal_valid_rejects_evidence_or_spec_drift_without_rewrite_or_model_call(
    tmp_path: Path, mutation: str
) -> None:
    """Catch terminal VALID bypassing read-only verification on later invocations."""

    inventory = _synthetic_inventory(tmp_path, 2)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    manifest_path = output_root / "manifest.json"
    manifest_before = manifest_path.read_bytes()
    rerun_spec = spec

    if mutation == "delete-mask":
        mask_path = output_root / _record(output_root, 1)["raw_candidates"][0][
            "mask"
        ]["relative_path"]
        mask_path.unlink()
    elif mutation == "delete-record":
        (output_root / "records/000001.json").unlink()
    elif mutation == "delete-checkpoint":
        (output_root / "checkpoint.json").unlink()
    elif mutation == "tamper-tail":
        record_path = output_root / "records/000001.json"
        document = _record(output_root, 1)
        document["timing_breakdown"]["dino_or_yolo_ms"] = 2.0
        document["timing_breakdown"]["total_ms"] = 2.0
        atomic_write_json(record_path, document)
    elif mutation == "change-spec":
        rerun_spec = replace(spec, config_sha256=SHA_C)
    else:
        image_path = inventory.dataset_root / inventory.samples[1].image_relpath
        image_path.write_bytes(image_path.read_bytes() + b"drift")

    adapter = SyntheticAdapter(output_root)
    with pytest.raises(RunIntegrityError):
        DetectorBenchmarkRunner(adapter, output_root).run(rerun_spec)

    assert adapter.calls == []
    assert manifest_path.read_bytes() == manifest_before


def test_terminal_valid_requires_current_verified_lock_path_without_manifest_rewrite(
    tmp_path: Path,
) -> None:
    """Catch a locked terminal run accepting a missing or substituted lock path."""

    lock = _formal_yolo_lock()
    inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(
        inventory,
        output_root,
        run_id="terminal-locked",
        run_kind=RunKind.TEST_RAW_FROZEN,
        threshold_lock_sha256=lock.lock_sha256,
        threshold_lock_path=lock_path,
    )
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    manifest_path = output_root / "manifest.json"
    manifest_before = manifest_path.read_bytes()
    changed = replace(spec, threshold_lock_path=tmp_path / "missing-lock.json")
    adapter = SyntheticAdapter(output_root)

    with pytest.raises(RunIntegrityError):
        DetectorBenchmarkRunner(adapter, output_root).run(changed)

    assert adapter.calls == []
    assert manifest_path.read_bytes() == manifest_before


def test_terminal_schema_failure_does_not_rewrite_decodable_terminal_manifest(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    manifest_path = output_root / "manifest.json"
    document = json.loads(manifest_path.read_bytes())
    document["ended_at"] = None
    atomic_write_json(manifest_path, document)
    terminal_bytes = manifest_path.read_bytes()
    adapter = SyntheticAdapter(output_root)

    with pytest.raises(RunIntegrityError, match="MANIFEST_SCHEMA_INVALID"):
        DetectorBenchmarkRunner(adapter, output_root).run(spec)

    assert adapter.calls == []
    assert manifest_path.read_bytes() == terminal_bytes


@pytest.mark.parametrize("terminal_status", (RunStatus.VALID, RunStatus.INVALID))
@pytest.mark.parametrize("schema_mutation", ("extra-field", "missing-field"))
def test_raw_terminal_manifest_schema_drift_is_read_only_before_strict_loading(
    tmp_path: Path,
    terminal_status: RunStatus,
    schema_mutation: str,
) -> None:
    """Catch strict manifest construction running before raw terminal detection."""

    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    if terminal_status is RunStatus.INVALID:
        spec = replace(spec, platform="linux", device="mps")
    first = DetectorBenchmarkRunner(
        SyntheticAdapter(output_root), output_root
    ).run(spec)
    assert first.status is terminal_status
    manifest_path = output_root / "manifest.json"
    document = json.loads(manifest_path.read_bytes())
    if schema_mutation == "extra-field":
        document["unexpected_terminal_field"] = "must-not-be-rewritten"
    else:
        del document["runtime_version"]
    atomic_write_json(manifest_path, document)
    terminal_bytes = manifest_path.read_bytes()
    adapter = SyntheticAdapter(output_root)

    with pytest.raises(RunIntegrityError, match="MANIFEST_SCHEMA_INVALID"):
        DetectorBenchmarkRunner(adapter, output_root).run(spec)

    assert adapter.calls == []
    assert manifest_path.read_bytes() == terminal_bytes


def test_terminal_invalid_remains_byte_immutable_and_never_resumes(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root, platform="linux", device="mps")
    first_adapter = SyntheticAdapter(output_root)
    first = DetectorBenchmarkRunner(first_adapter, output_root).run(spec)
    assert first.status is RunStatus.INVALID
    manifest_path = output_root / "manifest.json"
    manifest_before = manifest_path.read_bytes()
    second_adapter = SyntheticAdapter(output_root)

    second = DetectorBenchmarkRunner(second_adapter, output_root).run(spec)

    assert second.status is RunStatus.INVALID
    assert second_adapter.calls == []
    assert manifest_path.read_bytes() == manifest_before


def test_checkpoint_crash_never_advances_past_durable_record_and_resume_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Catch checkpoint publication before record durability or silent crash repair."""

    inventory = _synthetic_inventory(tmp_path, 5)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)
    runner = DetectorBenchmarkRunner(adapter, output_root)
    real_write = runner._write_checkpoint

    def crash_at_two(checkpoint: RunCheckpoint) -> None:
        if checkpoint.last_formal_sample_index == 2:
            raise OSError("checkpoint device failed")
        real_write(checkpoint)

    monkeypatch.setattr(runner, "_write_checkpoint", crash_at_two)
    manifest = runner.run(_spec(inventory, output_root))

    assert manifest.status is RunStatus.INVALID
    assert sorted(path.name for path in (output_root / "records").iterdir()) == [
        "000000.json",
        "000001.json",
        "000002.json",
    ]
    assert _checkpoint(output_root).last_formal_sample_index == 1
    resumed = SyntheticAdapter(output_root)
    resumed_manifest = DetectorBenchmarkRunner(resumed, output_root).run(
        _spec(inventory, output_root)
    )
    assert resumed_manifest.status is RunStatus.INVALID
    assert resumed.calls == []


@pytest.mark.parametrize(
    ("adapter_kwargs", "thermal_limit", "reason", "retained"),
    (
        ({"failures": {2: ResourceSamplingError("sensor failed")}}, None, "RESOURCE_EVIDENCE_FAILED", 2),
        ({"empty_resources_at": 2}, None, "RESOURCE_STREAM_EMPTY", 2),
        ({"temperatures": {2: 91.0}}, 80.0, "THERMAL_LIMIT_EXCEEDED", 2),
    ),
)
def test_resource_or_thermal_failure_invalidates_whole_run_and_stops(
    tmp_path: Path,
    adapter_kwargs: dict[str, object],
    thermal_limit: float | None,
    reason: str,
    retained: int,
) -> None:
    """Catch invalid hardware evidence being counted as an ordinary image error."""

    inventory = _synthetic_inventory(tmp_path, 5)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root, **adapter_kwargs)
    spec = _spec(
        inventory,
        output_root,
        max_gpu_temperature_celsius=thermal_limit,
    )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(spec)

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == reason
    assert manifest.record_count == retained
    assert adapter.calls == list(range(retained + 1))
    assert sorted((output_root / "records").glob("*.json")) == [
        output_root / "records" / f"{index:06d}.json"
        for index in range(retained)
    ]
    resumed = SyntheticAdapter(output_root)
    resumed_manifest = DetectorBenchmarkRunner(resumed, output_root).run(spec)
    assert resumed_manifest.status is RunStatus.INVALID
    assert resumed.calls == []


def test_resume_detects_current_input_drift_and_inventory_document_tamper(
    tmp_path: Path,
) -> None:
    """Catch resume trusting stale record metadata over current immutable inputs."""

    inventory = _synthetic_inventory(tmp_path, 3)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    checkpoint = _checkpoint(output_root)

    image_path = inventory.dataset_root / inventory.samples[2].image_relpath
    image_path.write_bytes(image_path.read_bytes() + b"drift")
    with pytest.raises(RunIntegrityError, match="INPUT_IMAGE_SHA256_CHANGED"):
        verify_resume(checkpoint, inventory, SHA_A, SOURCE_COMMIT)

    image_path.write_bytes(image_path.read_bytes()[:-5])
    inventory_path = inventory.dataset_root / "inventory.json"
    inventory_path.write_bytes(inventory_path.read_bytes() + b" ")
    with pytest.raises(RunIntegrityError, match="INVENTORY_CANONICAL_INVALID"):
        verify_resume(checkpoint, inventory, SHA_A, SOURCE_COMMIT)


def test_adapter_mask_is_verified_before_record_or_checkpoint_publication(
    tmp_path: Path,
) -> None:
    """Catch a stale MaskRef being committed before its lossless mask is verified."""

    class MissingMaskAdapter(SyntheticAdapter):
        def collect(self, frame: object, mode: CollectionMode) -> RawDetectionResult:
            result = super().collect(frame, mode)
            mask_path = self.evidence_root / result.raw_candidates[0].mask.relative_path
            mask_path.unlink()
            return result

    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = MissingMaskAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "RECORD_MASK_PATH_INVALID"
    assert list((output_root / "records").iterdir()) == []
    assert not (output_root / "checkpoint.json").exists()


def test_preexisting_record_or_symlink_output_is_never_overwritten(
    tmp_path: Path,
) -> None:
    """Catch runner writes escaping or replacing evidence it does not own."""

    inventory = _synthetic_inventory(tmp_path, 1)
    occupied = tmp_path / "occupied"
    (occupied / "records").mkdir(parents=True)
    original = b"user-owned\n"
    (occupied / "records" / "000000.json").write_bytes(original)
    adapter = SyntheticAdapter(occupied)
    manifest = DetectorBenchmarkRunner(adapter, occupied).run(
        _spec(inventory, occupied)
    )
    assert manifest.status is RunStatus.INVALID
    assert adapter.calls == []
    assert (occupied / "records" / "000000.json").read_bytes() == original

    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    linked_adapter = SyntheticAdapter(outside)
    linked_manifest = DetectorBenchmarkRunner(linked_adapter, linked).run(
        _spec(inventory, linked)
    )
    assert linked_manifest.status is RunStatus.INVALID
    assert linked_adapter.calls == []
    assert list(outside.iterdir()) == []


def _production_candidate(
    frame: object,
    *,
    instance_id: str = "0",
    confidence: float = 0.9,
    mask_offset: int = 0,
) -> DetectionCandidate:
    mask = np.zeros((16, 20), dtype=bool)
    mask[2 + mask_offset : 8 + mask_offset, 3:10] = True
    return DetectionCandidate(
        instance_id=instance_id,
        class_id="plastic_cup",
        confidence=confidence,
        bbox_xyxy=(3.0, 2.0, 10.0, 10.0),
        mask=mask,
        source_stamp_ns=frame.source_stamp_ns,  # type: ignore[attr-defined]
        source_frame_id=frame.source_frame_id,  # type: ignore[attr-defined]
        image_width=20,
        image_height=16,
    )


def _production_batch(
    frame: object, candidates: tuple[DetectionCandidate, ...]
) -> DetectionBatch:
    return DetectionBatch(
        model_id=SyntheticAdapter.model_id,
        weights_sha256=SHA_B,
        runtime_device="mps",
        inference_latency_ms=1.0,
        image_width=20,
        image_height=16,
        candidates=candidates,
    )


def test_production_local_id_maps_to_canonical_raw_id_and_subset_evidence(
    tmp_path: Path,
) -> None:
    """Catch production-local YOLO IDs being copied into low-floor record IDs."""

    lock = _formal_yolo_lock()
    inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root, candidate_counts={0: 2})

    def observe(frame: object) -> ProductionObservation:
        batch = _production_batch(frame, (_production_candidate(frame),))
        return ProductionObservation(
            DecisionOutput.UNIQUE, batch, "0", None, None, None, 0.25
        )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            run_id="production-id-map",
            run_kind=RunKind.TEST_PRODUCTION,
            threshold_lock_sha256=lock.lock_sha256,
            threshold_lock_path=lock_path,
            production_observer=observe,
        )
    )

    assert manifest.status is RunStatus.VALID
    record = _record(output_root, 0)
    assert record["selected_candidate_id"] == "yolo-000"
    assert [item["candidate_id"] for item in record["raw_candidates"]] == [
        "yolo-000"
    ]
    assert record["raw_candidates"][0]["class_confidence"] == 0.9


@pytest.mark.parametrize("mapping_failure", ("ambiguous", "non-injective"))
def test_production_mapping_requires_one_to_one_unambiguous_evidence(
    tmp_path: Path, mapping_failure: str
) -> None:
    """Catch best-effort matching when batch/raw evidence is not bijective."""

    class AmbiguousRawAdapter(SyntheticAdapter):
        def collect(self, frame: object, mode: CollectionMode) -> RawDetectionResult:
            result = super().collect(frame, mode)
            first, second = result.raw_candidates
            return replace(
                result,
                raw_candidates=(
                    first,
                    replace(
                        second,
                        mask=first.mask,
                        ranking_score=first.ranking_score,
                        class_confidence=first.class_confidence,
                    ),
                ),
            )

    lock = _formal_yolo_lock()
    inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter: SyntheticAdapter
    if mapping_failure == "ambiguous":
        adapter = AmbiguousRawAdapter(output_root, candidate_counts={0: 2})
    else:
        adapter = SyntheticAdapter(output_root, candidate_counts={0: 1})

    def observe(frame: object) -> ProductionObservation:
        first = _production_candidate(frame, instance_id="0")
        values = (
            (first,)
            if mapping_failure == "ambiguous"
            else (first, _production_candidate(frame, instance_id="1"))
        )
        batch = _production_batch(frame, values)
        return ProductionObservation(
            DecisionOutput.AMBIGUOUS,
            batch,
            None,
            "TARGET_AMBIGUOUS",
            None,
            None,
            0.25,
        )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            run_id=f"production-{mapping_failure}",
            run_kind=RunKind.TEST_PRODUCTION,
            threshold_lock_sha256=lock.lock_sha256,
            threshold_lock_path=lock_path,
            production_observer=observe,
        )
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "PRODUCTION_CANDIDATE_MAPPING_INVALID"
    assert not (output_root / "records/000000.json").exists()


def test_production_error_preserves_raw_evidence_and_observer_type_flags(
    tmp_path: Path,
) -> None:
    """Catch detector ERROR discarding low-floor evidence or erasing its type."""

    def observe(_frame: object) -> ProductionObservation:
        return ProductionObservation(
            DecisionOutput.ERROR,
            None,
            None,
            None,
            "DETECTOR_ERROR",
            "TimeoutError: detector timed out",
            None,
        )

    # Directly exercise record construction through a synthetic locked inventory in the
    # combined lock-chain test once the runner accepts only verified lock capabilities.
    lock = _formal_yolo_lock()
    test_inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "locked-run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root, candidate_counts={0: 2})
    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            test_inventory,
            output_root,
            run_id="production-error",
            run_kind=RunKind.TEST_PRODUCTION,
            threshold_lock_sha256=lock.lock_sha256,
            threshold_lock_path=lock_path,
            production_observer=observe,
        )
    )

    assert manifest.status is RunStatus.VALID
    record = _record(output_root, 0)
    assert record["record_status"] == "ERROR"
    assert record["error_type"] == "DETECTOR_ERROR"
    assert record["timed_out"] is True
    assert record["oom"] is False
    assert len(record["raw_candidates"]) == 2
    assert record["timing_breakdown"]["dino_or_yolo_ms"] == 1.0
    assert len(record["resource_samples"]) == 1


def test_selector_error_batch_preserves_mapped_subset_and_derives_oom(
    tmp_path: Path,
) -> None:
    lock = _formal_yolo_lock()
    inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root, candidate_counts={0: 2})

    def observe(frame: object) -> ProductionObservation:
        batch = _production_batch(frame, (_production_candidate(frame),))
        return ProductionObservation(
            DecisionOutput.ERROR,
            batch,
            None,
            None,
            "SELECTOR_ERROR",
            "CUDAOutOfMemoryError",
            0.5,
        )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            run_id="production-selector-error",
            run_kind=RunKind.TEST_PRODUCTION,
            threshold_lock_sha256=lock.lock_sha256,
            threshold_lock_path=lock_path,
            production_observer=observe,
        )
    )

    assert manifest.status is RunStatus.VALID
    record = _record(output_root, 0)
    assert record["error_type"] == "SELECTOR_ERROR"
    assert record["oom"] is True
    assert record["timed_out"] is False
    assert [item["candidate_id"] for item in record["raw_candidates"]] == [
        "yolo-000"
    ]


@pytest.mark.parametrize(
    "variant", ("bare", "wrong-model", "fixture", "posthoc", "unregistered")
)
def test_formal_test_requires_verified_pre_access_model_lock_without_log_mutation(
    tmp_path: Path, variant: str
) -> None:
    """Catch a hex digest, fixture/post-hoc lock, or unregistered lock opening test."""

    formal = _formal_yolo_lock(
        formal=variant != "fixture",
        model="grounded_sam" if variant == "wrong-model" else "yolo_seg",
    )
    inventory, lock_path, access_log = _locked_inventory(
        tmp_path,
        formal,
        write_lock_before_access=variant != "posthoc",
    )
    selected_lock = formal
    if variant == "unregistered":
        selected_lock = replace(formal, lock_sha256="0" * 64).with_recomputed_sha256()
        write_threshold_lock(lock_path, selected_lock)
    before = access_log.read_bytes()
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)
    spec = _spec(
        inventory,
        output_root,
        run_id=f"locked-{variant}",
        run_kind=RunKind.TEST_RAW_FROZEN,
        threshold_lock_sha256=(
            formal.lock_sha256 if variant == "bare" else selected_lock.lock_sha256
        ),
        threshold_lock_path=None if variant == "bare" else lock_path,
    )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(spec)

    assert manifest.status is RunStatus.INVALID
    assert adapter.calls == []
    assert access_log.read_bytes() == before


def test_verified_registered_lock_runs_without_touching_access_log(
    tmp_path: Path,
) -> None:
    lock = _formal_yolo_lock()
    inventory, lock_path, access_log = _locked_inventory(tmp_path, lock)
    before = access_log.read_bytes()
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            run_id="locked-valid",
            run_kind=RunKind.TEST_RAW_FROZEN,
            threshold_lock_sha256=lock.lock_sha256,
            threshold_lock_path=lock_path,
        )
    )

    assert manifest.status is RunStatus.VALID
    assert adapter.calls == [0]
    assert access_log.read_bytes() == before


@pytest.mark.parametrize(
    ("platform", "device"), (("macos", "cuda"), ("linux", "mps"))
)
def test_platform_device_pair_is_fail_closed_before_model_call(
    tmp_path: Path, platform: str, device: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)
    adapter.runtime_device = device  # type: ignore[assignment]

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            platform=platform,
            device=device,
            runtime_provenance=_runtime_provenance(device=device),
        )
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "PLATFORM_DEVICE_MISMATCH"
    assert adapter.calls == []


def test_adapter_asset_digest_must_match_supplied_runtime_provenance(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)
    adapter._weights_sha256 = SHA_C

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "RUNTIME_WEIGHTS_PROVENANCE_MISMATCH"
    assert adapter.calls == []


def test_resource_failure_is_typed_not_message_classified(tmp_path: Path) -> None:
    inventory = _synthetic_inventory(tmp_path, 2)
    typed_root = tmp_path / "typed"
    typed_root.mkdir()
    typed = SyntheticAdapter(
        typed_root, failures={0: ResourceSamplingError("telemetry failed")}
    )
    typed_manifest = DetectorBenchmarkRunner(typed, typed_root).run(
        _spec(inventory, typed_root)
    )
    assert typed_manifest.status is RunStatus.INVALID
    assert typed_manifest.invalid_reason == "RESOURCE_EVIDENCE_FAILED"

    ordinary_root = tmp_path / "ordinary"
    ordinary_root.mkdir()
    ordinary = SyntheticAdapter(
        ordinary_root, failures={0: RuntimeError("resource sampler failed")}
    )
    ordinary_manifest = DetectorBenchmarkRunner(ordinary, ordinary_root).run(
        _spec(inventory, ordinary_root)
    )
    assert ordinary_manifest.status is RunStatus.VALID
    assert ordinary_manifest.record_count == 2
    assert ordinary_manifest.error_count == 1


def test_record_masks_are_republished_to_exact_canonical_layout(tmp_path: Path) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.VALID
    mask = _record(output_root, 0)["raw_candidates"][0]["mask"]
    assert mask["relative_path"] == "masks/000000/yolo-000.rle.json"
    assert (output_root / mask["relative_path"]).is_file()
    assert (output_root / "adapter-masks/000000/yolo-000.rle.json").is_file()


@pytest.mark.parametrize("occupied", ("file", "symlink"))
def test_canonical_mask_target_is_never_overwritten_or_followed(
    tmp_path: Path, occupied: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, 1)
    output_root = tmp_path / "run"
    output_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    if occupied == "file":
        target = output_root / "masks/000000/yolo-000.rle.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"user-owned\n")
    else:
        (output_root / "masks").symlink_to(outside, target_is_directory=True)
    adapter = SyntheticAdapter(output_root)

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(inventory, output_root)
    )

    assert manifest.status is RunStatus.INVALID
    records_dir = output_root / "records"
    assert not records_dir.exists() or list(records_dir.iterdir()) == []
    if occupied == "file":
        assert target.read_bytes() == b"user-owned\n"
    else:
        assert list(outside.iterdir()) == []


def test_prior_manifest_detects_last_record_and_checkpoint_rewrite(
    tmp_path: Path,
) -> None:
    """Catch coordinated tail/checkpoint tamper being laundered by a new manifest."""

    inventory = _synthetic_inventory(tmp_path, 2)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    manifest_path = output_root / "manifest.json"
    prior = json.loads(manifest_path.read_text())
    running = dict(prior)
    running["status"] = "RUNNING"
    running["ended_at"] = None
    running["invalid_reason"] = None
    atomic_write_json(manifest_path, running)

    record_path = output_root / "records/000001.json"
    record = json.loads(record_path.read_text())
    record["timing_breakdown"]["dino_or_yolo_ms"] = 2.0
    record["timing_breakdown"]["total_ms"] = 2.0
    atomic_write_json(record_path, record)
    changed_record_sha = hashlib.sha256(record_path.read_bytes()).hexdigest()
    checkpoint_path = output_root / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint["last_record_sha256"] = changed_record_sha
    if "record_inventory_sha256" in checkpoint:
        checkpoint["record_inventory_sha256"] = _record_inventory_digest(output_root)
    atomic_write_json(checkpoint_path, checkpoint)

    resumed = SyntheticAdapter(output_root)
    invalid = DetectorBenchmarkRunner(resumed, output_root).run(spec)

    assert invalid.status is RunStatus.INVALID
    assert invalid.started_at == prior["started_at"]
    assert invalid.record_count == prior["record_count"]
    assert invalid.record_inventory_sha256 == prior["record_inventory_sha256"]
    assert resumed.calls == []


def test_invalid_resume_preserves_original_manifest_identity_and_counts(
    tmp_path: Path,
) -> None:
    """Catch a changed resume spec rewriting the prior run's frozen metadata."""

    inventory = _synthetic_inventory(tmp_path, 2)
    output_root = tmp_path / "run"
    output_root.mkdir()
    original_spec = _spec(inventory, output_root)
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        original_spec
    )
    manifest_path = output_root / "manifest.json"
    prior = json.loads(manifest_path.read_text())
    prior["status"] = "RUNNING"
    prior["ended_at"] = None
    atomic_write_json(manifest_path, prior)
    changed_provenance = RuntimeProvenance(
        runtime_device="mps",
        runtime_name="synthetic-runtime",
        runtime_version="fixture-1",
        weights_sha256=SHA_B,
        environment={"fixture": "changed", "torch": "2.8.0"},
    )
    adapter = SyntheticAdapter(output_root)

    invalid = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            config_sha256=SHA_C,
            runtime_provenance=changed_provenance,
        )
    )

    assert invalid.status is RunStatus.INVALID
    assert invalid.started_at == prior["started_at"]
    assert invalid.config_sha256 == SHA_A
    assert invalid.runtime_environment == {"fixture": "runner", "torch": "2.8.0"}
    assert invalid.record_count == prior["record_count"]
    assert invalid.record_inventory_sha256 == prior["record_inventory_sha256"]
    assert adapter.calls == []


def test_running_manifest_tracks_safe_checkpoint_before_process_interrupt(
    tmp_path: Path,
) -> None:
    """Catch RUNNING metadata remaining at fabricated zero counts after a safe commit."""

    inventory = _synthetic_inventory(tmp_path, 3)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root, failures={1: KeyboardInterrupt()})

    with pytest.raises(KeyboardInterrupt):
        DetectorBenchmarkRunner(adapter, output_root).run(
            _spec(inventory, output_root)
        )

    running = json.loads((output_root / "manifest.json").read_text())
    first_sha = hashlib.sha256(
        (output_root / "records/000000.json").read_bytes()
    ).hexdigest()
    assert running["status"] == "RUNNING"
    assert running["record_count"] == 1
    assert running["error_count"] == 0
    assert running["record_chain_head_sha256"] == first_sha
    assert running["record_inventory_sha256"] == _record_inventory_digest(output_root)
    assert running["ended_at"] is None


def _evidence_expectation(**overrides: object) -> RunEvidenceExpectation:
    values: dict[str, object] = {
        "run_id": "fixture-val-raw",
        "run_kind": RunKind.VAL_RAW,
        "platform": "macos",
        "model": "yolo_seg",
        "device": "mps",
        "dtype": "float32",
        "source_commit": SOURCE_COMMIT,
        "config_sha256": SHA_A,
        "threshold_lock_sha256": None,
        "model_id": YOLO_MODEL_ID,
        "weights_sha256": SHA_B,
        "runtime_name": "synthetic-runtime",
        "runtime_version": "fixture-1",
        "runtime_environment": {"fixture": "runner", "torch": "2.8.0"},
        "max_gpu_temperature_celsius": None,
    }
    values.update(overrides)
    return RunEvidenceExpectation(**values)  # type: ignore[arg-type]


def test_public_run_loader_returns_immutable_full_verified_evidence(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    expected_manifest = DetectorBenchmarkRunner(
        SyntheticAdapter(output_root), output_root
    ).run(_spec(inventory, output_root))

    loaded = load_verified_run_evidence(
        output_root, inventory, _evidence_expectation()
    )

    assert isinstance(loaded, LoadedRunEvidence)
    assert loaded.evidence_root == output_root.resolve(strict=True)
    assert loaded.manifest == expected_manifest
    assert len(loaded.records) == 200
    assert len(loaded.extended_record_documents) == 200
    assert loaded.records[199].formal_sample_index == 199
    with pytest.raises(TypeError):
        loaded.extended_record_documents[0]["platform"] = "linux"  # type: ignore[index]
    with pytest.raises(TypeError):
        loaded.manifest.runtime_environment["fixture"] = "changed"  # type: ignore[index]


def test_public_run_loader_accepts_verified_terminal_tree_relocation(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    producer_root = tmp_path / "producer" / "run"
    producer_root.mkdir(parents=True)
    expected_manifest = DetectorBenchmarkRunner(
        SyntheticAdapter(producer_root), producer_root
    ).run(_spec(inventory, producer_root))
    relocated_root = tmp_path / "durable" / "renamed-run"
    shutil.copytree(producer_root, relocated_root)

    checkpoint = json.loads((relocated_root / "checkpoint.json").read_bytes())
    assert checkpoint["records_dir"] == str(producer_root / "records")

    loaded = load_verified_run_evidence(
        relocated_root, inventory, _evidence_expectation()
    )

    assert loaded.evidence_root == relocated_root.resolve(strict=True)
    assert loaded.manifest == expected_manifest
    assert len(loaded.records) == 200

    checkpoint["records_dir"] = str(tmp_path / "not-records")
    atomic_write_json(relocated_root / "checkpoint.json", checkpoint)
    with pytest.raises(RunIntegrityError, match="RESUME_RECORDS_DIRECTORY_CHANGED"):
        load_verified_run_evidence(
            relocated_root, inventory, _evidence_expectation()
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("run_kind", RunKind.TEST_RAW_FROZEN),
        ("platform", "linux"),
        ("model", "grounded_sam"),
        ("device", "cuda"),
        ("source_commit", "cafebabe" * 5),
        ("config_sha256", SHA_C),
        ("threshold_lock_sha256", SHA_C),
        ("model_id", GROUNDED_SAM_MODEL_ID),
        ("weights_sha256", SHA_C),
        ("runtime_name", "other-runtime"),
        ("runtime_version", "other-version"),
        ("runtime_environment", {"fixture": "changed"}),
        ("max_gpu_temperature_celsius", 80.0),
    ),
)
def test_public_run_loader_rejects_external_expectation_mismatch(
    tmp_path: Path, field: str, value: object
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    expectation = replace(_evidence_expectation(), **{field: value})

    with pytest.raises(RunIntegrityError):
        load_verified_run_evidence(output_root, inventory, expectation)


def test_public_run_expectation_rejects_non_fp32_dtype() -> None:
    with pytest.raises(ValueError, match="dtype must be float32"):
        replace(_evidence_expectation(), dtype="float16")


def _rewrite_terminal_anchors(root: Path) -> None:
    record_path = root / "records/000199.json"
    record_sha = hashlib.sha256(record_path.read_bytes()).hexdigest()
    checkpoint_path = root / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_bytes())
    checkpoint["last_record_sha256"] = record_sha
    checkpoint["record_inventory_sha256"] = _record_inventory_digest(root)
    atomic_write_json(checkpoint_path, checkpoint)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["record_chain_head_sha256"] = record_sha
    manifest["record_inventory_sha256"] = checkpoint["record_inventory_sha256"]
    atomic_write_json(manifest_path, manifest)


@pytest.mark.parametrize(
    "mutation",
    (
        "running-manifest",
        "partial-records",
        "extra-record",
        "tail-tamper",
        "extra-document-field",
        "resource-mismatch",
        "mask-tamper",
        "image-tamper",
    ),
)
def test_public_run_loader_rejects_partial_tampered_or_extended_schema_drift(
    tmp_path: Path, mutation: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    manifest_path = output_root / "manifest.json"
    terminal_before = manifest_path.read_bytes()
    if mutation == "running-manifest":
        manifest = json.loads(terminal_before)
        manifest["status"] = "RUNNING"
        manifest["ended_at"] = None
        atomic_write_json(manifest_path, manifest)
        terminal_before = manifest_path.read_bytes()
    elif mutation == "partial-records":
        (output_root / "records/000199.json").unlink()
    elif mutation == "extra-record":
        (output_root / "records/000200.json").write_bytes(b"{}\n")
    elif mutation == "tail-tamper":
        record_path = output_root / "records/000199.json"
        record_path.write_bytes(record_path.read_bytes() + b" ")
    elif mutation in {"extra-document-field", "resource-mismatch"}:
        record_path = output_root / "records/000199.json"
        document = json.loads(record_path.read_bytes())
        if mutation == "extra-document-field":
            document["unexpected"] = "forbidden"
        else:
            document["resource_samples"][0]["process_cpu_percent"] = -1.0
        atomic_write_json(record_path, document)
        _rewrite_terminal_anchors(output_root)
        terminal_before = manifest_path.read_bytes()
    elif mutation == "mask-tamper":
        record = _record(output_root, 199)
        mask = output_root / record["raw_candidates"][0]["mask"]["relative_path"]
        mask.write_bytes(mask.read_bytes() + b" ")
    else:
        image = inventory.dataset_root / inventory.samples[199].image_relpath
        image.write_bytes(image.read_bytes() + b"drift")

    with pytest.raises(RunIntegrityError):
        load_verified_run_evidence(
            output_root, inventory, _evidence_expectation()
        )

    assert manifest_path.read_bytes() == terminal_before


def test_public_run_loader_requires_exact_full_inventory_denominator(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 8)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )

    with pytest.raises(RunIntegrityError, match="TERMINAL_RUN_DENOMINATOR_INCOMPLETE"):
        load_verified_run_evidence(
            output_root, inventory, _evidence_expectation()
        )


def test_public_run_loader_verifies_registered_test_lock_chain(
    tmp_path: Path,
) -> None:
    lock = _formal_yolo_lock()
    inventory, lock_path, access_log = _locked_inventory(
        tmp_path / "locked", lock, count=200
    )
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(
        inventory,
        output_root,
        run_id="public-locked",
        run_kind=RunKind.TEST_RAW_FROZEN,
        threshold_lock_sha256=lock.lock_sha256,
        threshold_lock_path=lock_path,
    )
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(spec)
    expectation = _evidence_expectation(
        run_id="public-locked",
        run_kind=RunKind.TEST_RAW_FROZEN,
        threshold_lock_sha256=lock.lock_sha256,
    )
    assert len(
        load_verified_run_evidence(output_root, inventory, expectation).records
    ) == 200

    access_log.write_bytes(access_log.read_bytes() + b"{}\n")
    with pytest.raises(RunIntegrityError, match="INVENTORY_ACCESS_CHAIN_INVALID"):
        load_verified_run_evidence(output_root, inventory, expectation)


def test_runner_honors_relocated_access_log_bound_into_inventory_capability(
    tmp_path: Path,
) -> None:
    lock = _formal_yolo_lock()
    inventory, lock_path, producer_access_log = _locked_inventory(
        tmp_path / "producer", lock, count=200
    )
    relocated_root = tmp_path / "relocated-dataset"
    shutil.copytree(inventory.dataset_root, relocated_root)
    relocated_access_log = tmp_path / "relocated-test-access.jsonl"
    shutil.copy2(producer_access_log, relocated_access_log)
    producer_access_log.rename(tmp_path / "producer-access-log-moved.jsonl")
    relocated_inventory = replace(
        inventory,
        dataset_root=relocated_root,
        access_log_path=relocated_access_log,
    )
    dataset_module._issue_inventory(relocated_inventory)
    output_root = tmp_path / "run"
    output_root.mkdir()
    spec = _spec(
        relocated_inventory,
        output_root,
        run_id="relocated-locked",
        run_kind=RunKind.TEST_RAW_FROZEN,
        threshold_lock_sha256=lock.lock_sha256,
        threshold_lock_path=lock_path,
    )

    manifest = DetectorBenchmarkRunner(
        SyntheticAdapter(output_root), output_root
    ).run(spec)

    assert manifest.status is RunStatus.VALID
    assert manifest.record_count == 200


def test_round1_public_run_loader_rejects_another_valid_run_id(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root, run_id="other-valid-run")
    )

    with pytest.raises(RunIntegrityError, match="RUN_EVIDENCE_EXPECTATION_MISMATCH"):
        load_verified_run_evidence(output_root, inventory, _evidence_expectation())


def test_round1_public_run_loader_rejects_runtime_wildcard_for_self_consistent_drift(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    drifted = RuntimeProvenance(
        runtime_device="mps",
        runtime_name="drifted-runtime",
        runtime_version="drifted-2",
        weights_sha256=SHA_B,
        environment={"fixture": "drifted", "torch": "2.9.0"},
    )
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root, runtime_provenance=drifted)
    )

    with pytest.raises((ValueError, RunIntegrityError)):
        wildcard = replace(
            _evidence_expectation(),
            runtime_name=None,
            runtime_version=None,
            runtime_environment=None,
        )
        load_verified_run_evidence(output_root, inventory, wildcard)


@pytest.mark.parametrize(
    ("field", "value"),
    (("started_at", False), ("ended_at", True)),
)
def test_round1_public_run_loader_rejects_non_string_manifest_timestamps(
    tmp_path: Path, field: str, value: object
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    manifest_path = output_root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest[field] = value
    atomic_write_json(manifest_path, manifest)

    with pytest.raises(RunIntegrityError, match="MANIFEST_SCHEMA_INVALID"):
        load_verified_run_evidence(output_root, inventory, _evidence_expectation())


def test_round1_public_run_loader_rejects_boolean_checkpoint_count(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    checkpoint_path = output_root / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_bytes())
    checkpoint["error_count"] = False
    atomic_write_json(checkpoint_path, checkpoint)

    with pytest.raises(RunIntegrityError, match="CHECKPOINT_SCHEMA_INVALID"):
        load_verified_run_evidence(output_root, inventory, _evidence_expectation())


@pytest.mark.parametrize(
    ("filename", "error_code"),
    (
        ("manifest.json", "MANIFEST_SCHEMA_INVALID"),
        ("checkpoint.json", "CHECKPOINT_SCHEMA_INVALID"),
    ),
)
def test_round1_public_run_loader_rejects_normalizable_environment_type_drift(
    tmp_path: Path, filename: str, error_code: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    document_path = output_root / filename
    document = json.loads(document_path.read_bytes())
    document["runtime_environment"] = [
        ["fixture", "runner"],
        ["torch", "2.8.0"],
    ]
    atomic_write_json(document_path, document)

    with pytest.raises(RunIntegrityError, match=error_code):
        load_verified_run_evidence(output_root, inventory, _evidence_expectation())


def test_round1_public_run_loader_rejects_hardlinked_terminal_file(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    os.link(output_root / "manifest.json", tmp_path / "external-manifest.json")

    with pytest.raises(RunIntegrityError, match="RUN_EVIDENCE_FILE_UNSAFE"):
        load_verified_run_evidence(output_root, inventory, _evidence_expectation())


@pytest.mark.parametrize(
    "alias_base",
    (Path("/tmp"), Path(tempfile.gettempdir())),
    ids=("tmp-alias", "default-var-alias"),
)
def test_round2_public_run_loader_accepts_macos_system_ancestor_aliases(
    alias_base: Path,
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="so101-public-run-", dir=alias_base
    ) as temporary:
        workspace = Path(temporary)
        inventory = _synthetic_inventory(workspace, 200)
        output_root = workspace / "run"
        output_root.mkdir()
        DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
            _spec(inventory, output_root)
        )

        loaded = load_verified_run_evidence(
            output_root, inventory, _evidence_expectation()
        )

        assert loaded.evidence_root == output_root.resolve(strict=True)
        assert len(loaded.records) == 200


def test_round2_public_run_loader_rejects_final_root_symlink(
    tmp_path: Path,
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    linked_root = tmp_path / "linked-run"
    linked_root.symlink_to(output_root, target_is_directory=True)

    with pytest.raises(RunIntegrityError, match="RUN_EVIDENCE_ROOT_INVALID"):
        load_verified_run_evidence(
            linked_root, inventory, _evidence_expectation()
        )


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    (
        ("runtime-environment", "RECORD_SCHEMA_INVALID"),
        ("tool-versions", "RECORD_RESOURCE_INVALID"),
        ("unavailable-reasons", "RECORD_RESOURCE_INVALID"),
    ),
)
def test_round2_public_run_loader_rejects_normalizable_nested_record_mappings(
    tmp_path: Path, mutation: str, error_code: str
) -> None:
    inventory = _synthetic_inventory(tmp_path, 200)
    output_root = tmp_path / "run"
    output_root.mkdir()
    DetectorBenchmarkRunner(SyntheticAdapter(output_root), output_root).run(
        _spec(inventory, output_root)
    )
    record_path = output_root / "records/000199.json"
    document = json.loads(record_path.read_bytes())
    if mutation == "runtime-environment":
        document["runtime_provenance"]["environment"] = [
            ["fixture", "runner"],
            ["torch", "2.8.0"],
        ]
    elif mutation == "tool-versions":
        document["resource_samples"][0]["tool_versions"] = [["fixture", "1"]]
    else:
        reasons = document["resource_samples"][0]["unavailable_reasons"]
        document["resource_samples"][0]["unavailable_reasons"] = list(
            reasons.items()
        )
    atomic_write_json(record_path, document)
    _rewrite_terminal_anchors(output_root)

    with pytest.raises(RunIntegrityError, match=error_code):
        load_verified_run_evidence(
            output_root, inventory, _evidence_expectation()
        )
