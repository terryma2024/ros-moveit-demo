"""The proposal observer, the raw detection contract and resource sampling."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from perception_benchmark_adapters_support import (
    _frame,
    _grounded_adapter,
    _GroundingModel,
    _GroundingProcessor,
    _resource_sampler,
    _SamModel,
    _SamProcessor,
    _TorchApi,
    _yolo_adapter,
    _YoloModel,
)
import pytest

from so101_demo.adapters.perception.yolo_seg import YoloResultError
from so101_demo.perception_benchmark.adapters import (
    CollectionMode,
    GroundedSamRawAdapter,
    RawDetectionResult,
    ResourceSamplingError,
    YoloRawAdapter,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
)
from so101_demo.perception_benchmark.timing import (
    DeviceSynchronizer,
    ResourceSample,
)


class _ControlledResourceSampler:
    device = "mps"

    def __init__(
        self,
        *,
        result: object | None = None,
        error: Exception | None = None,
        construct_invalid: bool = False,
    ) -> None:
        self.result = result
        self.error = error
        self.construct_invalid = construct_invalid
        self.sample_calls = 0

    def sample(self) -> Any:
        self.sample_calls += 1
        if self.error is not None:
            raise self.error
        if self.construct_invalid:
            return ResourceSample(
                process_rss_bytes=-1,
                process_cpu_percent=10.0,
                gpu_memory_allocated_bytes=1,
                gpu_memory_reserved_bytes=2,
                gpu_utilization_percent=3.0,
                gpu_temperature_celsius=4.0,
                gpu_power_watts=5.0,
            )
        assert self.result is not None
        return self.result


def test_proposal_observer_keeps_high_score_proposal_rejected_by_sam(tmp_path: Path) -> None:
    """Catch retaining only SAM survivors instead of the complete ordered DINO batch."""
    class TwoProcessor(_GroundingProcessor):
        def post_process_grounded_object_detection(self, outputs: object, **kwargs: object):
            result = super().post_process_grounded_object_detection(outputs, **kwargs)[0]
            result.update(
                boxes=np.asarray([[1, 1, 2, 2], [3, 2, 13, 10]], dtype=np.float32),
                scores=np.asarray([0.91, 0.61], dtype=np.float32),
                text_labels=["plastic cup", "plastic cup"],
                query_indices=np.asarray([0, 1], dtype=np.int64),
            )
            return [result]

    class TwoGrounding(_GroundingModel):
        def __call__(self, **inputs: object):
            output = super().__call__(**inputs)
            output.logits = np.repeat(output.logits, 2, axis=1)
            return output

    class TwoSam(_SamModel):
        def __call__(self, **inputs: object):
            self.call_count += 1
            assert np.asarray(inputs["input_boxes"]).shape == (1, 2, 4)
            masks = np.zeros((1, 2, 1, 16, 20), dtype=np.float32)
            masks[0, 0, 0, 0, 0] = 1
            masks[0, 1, 0, 2:10, 3:13] = 1
            return SimpleNamespace(
                pred_masks=masks, iou_scores=np.asarray([[[0.84], [0.84]]], dtype=np.float32)
            )

    seen = []
    sam = TwoSam()

    def observe(proposals):
        assert sam.call_count == 0
        with pytest.raises(TypeError):
            proposals[0][0][0] = 99
        seen.append(proposals)

    adapter, _, grounding, _, _ = _grounded_adapter(
        tmp_path, grounding_processor=TwoProcessor(), grounding_model=TwoGrounding(),
        sam_model=sam, proposal_observer=observe,
    )
    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert grounding.call_count == sam.call_count == 1
    assert len(seen) == 1 and len(seen[0]) == 2
    assert seen[0][0][0] == (1.0, 1.0, 2.0, 2.0)
    assert seen[0][0][1] == pytest.approx(0.91)
    assert seen[0][0][2] == pytest.approx(0.79, abs=1e-6)
    assert len(result.raw_candidates) == 1
    assert result.raw_candidates[0].candidate_id == "grounded-sam-001"
    assert result.raw_candidates[0].bbox_xyxy == seen[0][1][0]


def test_proposal_observer_does_not_change_surviving_raw_candidate(tmp_path: Path) -> None:
    seen = []
    observed = _grounded_adapter(tmp_path, proposal_observer=seen.append)[0]
    baseline_root = tmp_path / "baseline"
    baseline_root.mkdir()
    baseline = _grounded_adapter(baseline_root)[0]

    actual = observed.collect(_frame(), CollectionMode.LOW_FLOOR)
    expected = baseline.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert actual.raw_candidates == expected.raw_candidates
    assert actual.irreversible_limits == expected.irreversible_limits
    assert len(seen) == 1


def test_proposal_observer_records_empty_frame_without_sam_forward(tmp_path: Path) -> None:
    class EmptyProcessor(_GroundingProcessor):
        def post_process_grounded_object_detection(self, outputs: object, **kwargs: object):
            return [{"boxes": np.empty((0, 4), dtype=np.float32),
                     "scores": np.empty(0, dtype=np.float32), "text_labels": [],
                     "query_indices": np.empty(0, dtype=np.int64)}]

    seen = []
    adapter, _, grounding, _, sam = _grounded_adapter(
        tmp_path, grounding_processor=EmptyProcessor(), proposal_observer=seen.append,
    )
    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert seen == [()]
    assert result.raw_candidates == ()
    assert grounding.call_count == 1 and sam.call_count == 0


def test_proposal_observer_failure_stops_before_sam(tmp_path: Path) -> None:
    failure = OSError("proposal evidence unavailable")

    def observe(proposals):
        raise failure

    adapter, _, grounding, _, sam = _grounded_adapter(tmp_path, proposal_observer=observe)
    with pytest.raises(OSError) as caught:
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)
    assert caught.value is failure
    assert grounding.call_count == 1 and sam.call_count == 0


@pytest.mark.parametrize("observer", [False, 0, "not callable"])
def test_proposal_observer_rejects_invalid_callback(tmp_path: Path, observer: Any) -> None:
    with pytest.raises(ValueError, match="proposal_observer"):
        _grounded_adapter(tmp_path, proposal_observer=observer)


def test_proposal_observer_from_bundle_reaches_real_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch the local bundle factory dropping the optional evidence observer."""
    from so101_demo.perception_benchmark.adapters import grounded_sam as module

    class LoadedGrounding(_GroundingModel):
        def to(self, device):
            assert device == "mps"
            return self

    class LoadedSam(_SamModel):
        def to(self, device):
            assert device == "mps"
            return self

    # Bundle byte verification is covered separately; exercise factory-to-collect wiring here.
    verified = SimpleNamespace(
        detector_dir=tmp_path / "detector", segmenter_dir=tmp_path / "segmenter",
        manifest_sha256="b" * 64, target_class_id="plastic_cup", prompt="plastic cup.",
    )
    monkeypatch.setattr(module, "verify_model_bundle", lambda *_: verified)
    seen = []
    adapter = GroundedSamRawAdapter.from_bundle(
        tmp_path, expected_manifest_sha256="b" * 64, requested_device="mps",
        evidence_root=tmp_path, torch_api=_TorchApi(), proposal_observer=seen.append,
        grounding_processor_loader=lambda *a, **k: _GroundingProcessor(),
        grounding_model_loader=lambda *a, **k: LoadedGrounding(),
        sam_processor_loader=lambda *a, **k: _SamProcessor(),
        sam_model_loader=lambda *a, **k: LoadedSam(),
    )
    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert len(seen) == 1 and len(seen[0]) == 1
    assert seen[0][0][0] == result.raw_candidates[0].bbox_xyxy


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_both_adapters_emit_same_raw_contract(tmp_path: Path, model: str) -> None:
    """Catch either model bypassing the shared immutable raw schema."""

    adapter = _yolo_adapter(tmp_path) if model == "yolo" else _grounded_adapter(tmp_path)[0]
    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert isinstance(result, RawDetectionResult)
    assert result.raw_candidates
    assert result.phase_timings.total_ms >= 0.0
    assert all(candidate.mask.sha256 for candidate in result.raw_candidates)
    assert result.fallback_used is False
    assert result.runtime_device == "mps"
    assert result.dtype == "float32"


@pytest.mark.parametrize(
    "model_id",
    (
        "not-yolo-imposter",
        f"prefix-{YOLO_MODEL_ID}",
        f"{YOLO_MODEL_ID}-suffix",
    ),
)
def test_yolo_raw_adapter_rejects_noncanonical_identity_before_model_use(
    tmp_path: Path, model_id: str
) -> None:
    model = _YoloModel()
    torch_api = _TorchApi()

    with pytest.raises(ValueError, match="model_id"):
        YoloRawAdapter(
            model=model,
            model_id=model_id,
            runtime_device="mps",
            weights_sha256="a" * 64,
            evidence_root=tmp_path,
            synchronizer=DeviceSynchronizer(torch_api, "mps"),
            resource_sampler=_resource_sampler(torch_api),
        )

    assert model.predict_calls == []


@pytest.mark.parametrize(
    "model_id",
    (
        "grounded-sam-wrong",
        f"prefix-{GROUNDED_SAM_MODEL_ID}",
        f"{GROUNDED_SAM_MODEL_ID}-suffix",
    ),
)
def test_grounded_raw_adapter_rejects_noncanonical_identity(tmp_path: Path, model_id: str) -> None:
    torch_api = _TorchApi()

    with pytest.raises(ValueError, match="model_id"):
        GroundedSamRawAdapter(
            model_id=model_id,
            runtime_device="mps",
            manifest_sha256="b" * 64,
            evidence_root=tmp_path,
            torch_api=torch_api,
            grounding_processor=_GroundingProcessor(),
            grounding_model=_GroundingModel(),
            sam_processor=_SamProcessor(),
            sam_model=_SamModel(),
            synchronizer=DeviceSynchronizer(torch_api, "mps"),
            resource_sampler=_resource_sampler(torch_api),
        )


@pytest.mark.parametrize(
    ("model_id", "model"),
    [
        (f"{YOLO_MODEL_ID}-suffix", "yolo"),
        (f"{GROUNDED_SAM_MODEL_ID}-suffix", "grounded_sam"),
    ],
)
def test_raw_detection_result_rejects_near_identity_with_candidates(
    tmp_path: Path, model_id: str, model: str
) -> None:
    adapter = _yolo_adapter(tmp_path) if model == "yolo" else _grounded_adapter(tmp_path)[0]
    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    with pytest.raises(ValueError, match="model_id"):
        replace(result, model_id=model_id)


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_resource_sampling_failure_has_typed_adapter_boundary(tmp_path: Path, model: str) -> None:
    """Catch raw telemetry failures escaping without a machine-readable type."""

    expected = ValueError("opaque failure 731")
    sampler = _ControlledResourceSampler(error=expected)
    adapter = (
        _yolo_adapter(tmp_path, resource_sampler=sampler)
        if model == "yolo"
        else _grounded_adapter(tmp_path, resource_sampler=sampler)[0]
    )

    with pytest.raises(Exception) as caught:
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert type(caught.value).__name__ == "ResourceSamplingError"
    assert isinstance(caught.value, ResourceSamplingError)
    assert caught.value.__cause__ is expected
    assert sampler.sample_calls == 1


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_invalid_resource_sample_validation_has_typed_adapter_boundary(
    tmp_path: Path, model: str
) -> None:
    """Catch ResourceSample validation errors leaking as untyped ValueError."""

    sampler = _ControlledResourceSampler(construct_invalid=True)
    adapter = (
        _yolo_adapter(tmp_path, resource_sampler=sampler)
        if model == "yolo"
        else _grounded_adapter(tmp_path, resource_sampler=sampler)[0]
    )

    with pytest.raises(Exception) as caught:
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert type(caught.value).__name__ == "ResourceSamplingError"
    assert isinstance(caught.value.__cause__, ValueError)
    assert sampler.sample_calls == 1


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_inference_value_error_is_not_reclassified_as_resource_sampling(
    tmp_path: Path, model: str
) -> None:
    """Catch an overly broad resource wrapper swallowing model exceptions."""

    expected = ValueError("opaque failure 731")
    sample = ResourceSample(4096, 10.0, 1, 2, 3.0, 4.0, 5.0)
    sampler = _ControlledResourceSampler(result=sample)
    if model == "yolo":
        adapter = _yolo_adapter(
            tmp_path,
            model=_YoloModel(error=expected),
            resource_sampler=sampler,
        )
    else:
        adapter = _grounded_adapter(
            tmp_path,
            grounding_model=_GroundingModel(error=expected),
            resource_sampler=sampler,
        )[0]

    with pytest.raises(Exception) as caught:
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert type(caught.value).__name__ != "ResourceSamplingError"
    if model == "yolo":
        assert isinstance(caught.value, YoloResultError)
        assert caught.value.__cause__ is expected
    else:
        assert caught.value is expected
    assert sampler.sample_calls == 0


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_result_schema_value_error_is_not_reclassified_as_resource_sampling(
    tmp_path: Path, model: str
) -> None:
    """Catch resource wrapping extending beyond the sample call into result schema."""

    sampler = _ControlledResourceSampler(result=object())
    adapter = (
        _yolo_adapter(tmp_path, resource_sampler=sampler)
        if model == "yolo"
        else _grounded_adapter(tmp_path, resource_sampler=sampler)[0]
    )

    with pytest.raises(ValueError, match="resource_samples") as caught:
        adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert not isinstance(caught.value, ResourceSamplingError)
    assert caught.value.__cause__ is None
    assert sampler.sample_calls == 1


@pytest.mark.parametrize("model", ("yolo", "grounded_sam"))
def test_successful_resource_sampling_is_preserved(tmp_path: Path, model: str) -> None:
    """Catch the typed failure boundary changing successful resource records."""

    sample = ResourceSample(4096, 10.0, 1, 2, 3.0, 4.0, 5.0)
    sampler = _ControlledResourceSampler(result=sample)
    adapter = (
        _yolo_adapter(tmp_path, resource_sampler=sampler)
        if model == "yolo"
        else _grounded_adapter(tmp_path, resource_sampler=sampler)[0]
    )

    result = adapter.collect(_frame(), CollectionMode.LOW_FLOOR)

    assert result.resource_samples == (sample,)
    assert result.resource_samples[0] is sample
    assert sampler.sample_calls == 1
