"""Synthetic adapters, inventories and helpers shared by the benchmark runner tests."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    RawDetectionResult,
)
from so101_demo.perception_benchmark.calibration.lock_io import write_threshold_lock
from so101_demo.perception_benchmark.calibration.results import (
    ObjectiveCalibrationMetrics,
    PlatformCalibrationMetrics,
    ThresholdLock,
)
from so101_demo.perception_benchmark.calibration.thresholds import (
    GroundedSamBenchmarkThresholds,
    YoloThresholds,
)
from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    canonical_json_bytes,
    encode_mask_rle,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
    MaskRef,
    RawCandidate,
    RunKind,
    RuntimeProvenance,
)
from so101_demo.perception_benchmark.dataset import truth as dataset_module_truth
from so101_demo.perception_benchmark.dataset.contracts import (
    DatasetInventory,
    DatasetSampleRef,
    append_test_access_event,
)
from so101_demo.perception_benchmark.runner.contracts import (
    RunSpec,
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
    dataset_module_truth._issue_inventory(inventory)
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
