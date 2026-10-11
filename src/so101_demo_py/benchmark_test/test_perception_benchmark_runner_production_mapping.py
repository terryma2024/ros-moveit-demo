"""The mapping of production candidates to canonical records."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
from perception_benchmark_runner_support import (
    SHA_B,
    SyntheticAdapter,
    SyntheticGroundedAdapter,
    _formal_yolo_lock,
    _locked_inventory,
    _record,
    _spec,
)
import pytest

from so101_demo.adapters.perception.yolo_seg import _trim_mask_boundary
from so101_demo.core.detection import DetectionBatch, DetectionCandidate
from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    ProductionObservation,
    RawDetectionResult,
)
from so101_demo.perception_benchmark.codec import (
    decode_mask_rle,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    DecisionOutput,
    RunKind,
    RunStatus,
)
from so101_demo.perception_benchmark.runner.detector_runner import DetectorBenchmarkRunner


def _production_candidate(
    frame: object,
    *,
    instance_id: str = "0",
    confidence: float = 0.9,
    mask_offset: int = 0,
) -> DetectionCandidate:
    mask = np.zeros((16, 20), dtype=bool)
    mask[2 + mask_offset : 8 + mask_offset, 3:10] = True
    mask = _trim_mask_boundary(mask)
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


def test_yolo_production_trimmed_mask_maps_to_canonical_raw_candidate(
    tmp_path: Path,
) -> None:
    """Map the deterministic production boundary trim without weakening identity."""

    lock = _formal_yolo_lock()
    inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticAdapter(output_root)

    def observe(frame: object) -> ProductionObservation:
        batch = _production_batch(frame, (_production_candidate(frame),))
        return ProductionObservation(
            DecisionOutput.UNIQUE, batch, "0", None, None, None, 0.25
        )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            run_id="production-trimmed-mask-map",
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


@pytest.mark.parametrize("quality_steps", (1, 2))
def test_grounded_production_mapping_does_not_use_quality_as_identity(
    tmp_path: Path, quality_steps: int
) -> None:
    """Map the same mask and box despite independent float32 quality readback."""

    lock = _formal_yolo_lock(model="grounded_sam")
    inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticGroundedAdapter(output_root)

    def observe(frame: object) -> ProductionObservation:
        mask = np.zeros((16, 20), dtype=bool)
        mask[3:11, 4:12] = True
        quality = np.float32(0.92)
        for _ in range(quality_steps):
            quality = np.nextafter(quality, np.float32(1.0), dtype=np.float32)
        candidate = DetectionCandidate(
            instance_id="0",
            class_id="plastic_cup",
            confidence=0.81,
            bbox_xyxy=(4.0, 3.0, 12.0, 11.0),
            mask=mask,
            source_stamp_ns=frame.source_stamp_ns,  # type: ignore[attr-defined]
            source_frame_id=frame.source_frame_id,  # type: ignore[attr-defined]
            image_width=20,
            image_height=16,
            segmentation_quality=float(quality),
        )
        batch = DetectionBatch(
            model_id=GROUNDED_SAM_MODEL_ID,
            weights_sha256=SHA_B,
            runtime_device="mps",
            inference_latency_ms=1.0,
            image_width=20,
            image_height=16,
            candidates=(candidate,),
        )
        return ProductionObservation(
            DecisionOutput.UNIQUE, batch, "0", None, None, None, 0.25
        )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            model="grounded_sam",
            run_id="grounded-production-float32-quality-ulp",
            run_kind=RunKind.TEST_PRODUCTION,
            threshold_lock_sha256=lock.lock_sha256,
            threshold_lock_path=lock_path,
            production_observer=observe,
        )
    )

    assert manifest.status is RunStatus.VALID
    record = _record(output_root, 0)
    assert record["selected_candidate_id"] == "grounded-sam-000"


def test_grounded_production_mapping_persists_observed_mask_after_stable_match(
    tmp_path: Path,
) -> None:
    """Keep the real production mask when SAM batching changes one boundary pixel."""

    lock = _formal_yolo_lock(model="grounded_sam")
    inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticGroundedAdapter(output_root)

    def observe(frame: object) -> ProductionObservation:
        mask = np.zeros((16, 20), dtype=bool)
        mask[3:11, 4:12] = True
        mask[2, 4] = True
        candidate = DetectionCandidate(
            instance_id="0",
            class_id="plastic_cup",
            confidence=0.81,
            bbox_xyxy=(4.0, 3.0, 12.0, 11.0),
            mask=mask,
            source_stamp_ns=frame.source_stamp_ns,  # type: ignore[attr-defined]
            source_frame_id=frame.source_frame_id,  # type: ignore[attr-defined]
            image_width=20,
            image_height=16,
            segmentation_quality=0.92,
        )
        batch = DetectionBatch(
            model_id=GROUNDED_SAM_MODEL_ID,
            weights_sha256=SHA_B,
            runtime_device="mps",
            inference_latency_ms=1.0,
            image_width=20,
            image_height=16,
            candidates=(candidate,),
        )
        return ProductionObservation(
            DecisionOutput.UNIQUE, batch, "0", None, None, None, 0.25
        )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            model="grounded_sam",
            run_id="grounded-production-observed-mask",
            run_kind=RunKind.TEST_PRODUCTION,
            threshold_lock_sha256=lock.lock_sha256,
            threshold_lock_path=lock_path,
            production_observer=observe,
        )
    )

    assert manifest.status is RunStatus.VALID
    record = _record(output_root, 0)
    candidate = record["raw_candidates"][0]
    assert candidate["mask"]["pixel_count"] == 65
    mask_document = json.loads(
        (output_root / candidate["mask"]["relative_path"]).read_text()
    )
    assert int(decode_mask_rle(mask_document).sum()) == 65
    assert record["irreversible_limits"][
        "production_candidate_mask_iou_threshold"
    ] == pytest.approx(0.98)


def test_grounded_production_mapping_rejects_mask_below_configured_iou(
    tmp_path: Path,
) -> None:
    lock = _formal_yolo_lock(model="grounded_sam")
    inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = SyntheticGroundedAdapter(output_root)

    def observe(frame: object) -> ProductionObservation:
        mask = np.zeros((16, 20), dtype=bool)
        mask[0:8, 0:8] = True
        candidate = DetectionCandidate(
            instance_id="0",
            class_id="plastic_cup",
            confidence=0.81,
            bbox_xyxy=(4.0, 3.0, 12.0, 11.0),
            mask=mask,
            source_stamp_ns=frame.source_stamp_ns,  # type: ignore[attr-defined]
            source_frame_id=frame.source_frame_id,  # type: ignore[attr-defined]
            image_width=20,
            image_height=16,
            segmentation_quality=0.92,
        )
        batch = DetectionBatch(
            model_id=GROUNDED_SAM_MODEL_ID,
            weights_sha256=SHA_B,
            runtime_device="mps",
            inference_latency_ms=1.0,
            image_width=20,
            image_height=16,
            candidates=(candidate,),
        )
        return ProductionObservation(
            DecisionOutput.UNIQUE, batch, "0", None, None, None, 0.25
        )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            model="grounded_sam",
            run_id="grounded-production-mask-iou-rejected",
            run_kind=RunKind.TEST_PRODUCTION,
            threshold_lock_sha256=lock.lock_sha256,
            threshold_lock_path=lock_path,
            production_observer=observe,
        )
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "PRODUCTION_CANDIDATE_MAPPING_INVALID"


def test_grounded_production_mapping_rejects_stable_identity_ambiguity(
    tmp_path: Path,
) -> None:
    """Keep mapping fail-closed when stable candidate fields are duplicated."""

    class AmbiguousGroundedAdapter(SyntheticGroundedAdapter):
        def collect(self, frame: object, mode: CollectionMode) -> RawDetectionResult:
            result = super().collect(frame, mode)
            first = result.raw_candidates[0]
            return replace(
                result,
                raw_candidates=(
                    first,
                    replace(
                        first,
                        candidate_id="grounded-sam-001",
                        sam_quality=0.95,
                    ),
                ),
            )

    lock = _formal_yolo_lock(model="grounded_sam")
    inventory, lock_path, _ = _locked_inventory(tmp_path / "locked", lock)
    output_root = tmp_path / "run"
    output_root.mkdir()
    adapter = AmbiguousGroundedAdapter(output_root)

    def observe(frame: object) -> ProductionObservation:
        mask = np.zeros((16, 20), dtype=bool)
        mask[3:11, 4:12] = True
        candidate = DetectionCandidate(
            instance_id="0",
            class_id="plastic_cup",
            confidence=0.81,
            bbox_xyxy=(4.0, 3.0, 12.0, 11.0),
            mask=mask,
            source_stamp_ns=frame.source_stamp_ns,  # type: ignore[attr-defined]
            source_frame_id=frame.source_frame_id,  # type: ignore[attr-defined]
            image_width=20,
            image_height=16,
            segmentation_quality=0.92,
        )
        batch = DetectionBatch(
            model_id=GROUNDED_SAM_MODEL_ID,
            weights_sha256=SHA_B,
            runtime_device="mps",
            inference_latency_ms=1.0,
            image_width=20,
            image_height=16,
            candidates=(candidate,),
        )
        return ProductionObservation(
            DecisionOutput.UNIQUE, batch, "0", None, None, None, 0.25
        )

    manifest = DetectorBenchmarkRunner(adapter, output_root).run(
        _spec(
            inventory,
            output_root,
            model="grounded_sam",
            run_id="grounded-production-stable-identity-ambiguity",
            run_kind=RunKind.TEST_PRODUCTION,
            threshold_lock_sha256=lock.lock_sha256,
            threshold_lock_path=lock_path,
            production_observer=observe,
        )
    )

    assert manifest.status is RunStatus.INVALID
    assert manifest.invalid_reason == "PRODUCTION_CANDIDATE_MAPPING_INVALID"
    assert not (output_root / "records/000000.json").exists()


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
