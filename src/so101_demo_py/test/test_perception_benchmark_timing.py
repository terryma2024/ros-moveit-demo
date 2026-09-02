from __future__ import annotations

from types import SimpleNamespace

import pytest

from so101_demo.perception_benchmark.timing import (
    DeviceSynchronizer,
    PhaseTimer,
    PhaseTimingBreakdown,
    ResourceSampler,
)


class _RecordingAccelerator:
    def __init__(self) -> None:
        self.synchronize_calls = 0

    def synchronize(self) -> None:
        self.synchronize_calls += 1


class _RecordingTorchApi:
    __version__ = "2.test"

    def __init__(self) -> None:
        self.cuda = _RecordingAccelerator()
        self.mps = _RecordingAccelerator()


class _FakeProcess:
    def memory_info(self) -> SimpleNamespace:
        return SimpleNamespace(rss=4096)

    def cpu_percent(self, interval: object = None) -> float:
        assert interval is None
        return 12.5


def test_cuda_and_mps_are_synchronized_at_each_timing_boundary() -> None:
    """Catch phase marks reading asynchronous accelerator work too early."""

    for device in ("cuda", "mps"):
        api = _RecordingTorchApi()
        with PhaseTimer(
            DeviceSynchronizer(api, device),
            monotonic_ns=iter((0, 1_000_000, 3_000_000)).__next__,
        ) as timer:
            timer.mark("preprocess")
            timer.mark("dino_or_yolo")

        accelerator = getattr(api, device)
        assert accelerator.synchronize_calls == 3
        assert timer.elapsed_ms == {"preprocess": 1.0, "dino_or_yolo": 2.0}


def test_phase_timer_synchronizes_exception_exit_without_replacing_error() -> None:
    """Catch an exceptional accelerator phase omitting its final device boundary."""

    api = _RecordingTorchApi()
    expected = RuntimeError("model exploded")

    with pytest.raises(RuntimeError) as caught:
        with PhaseTimer(
            DeviceSynchronizer(api, "mps"),
            monotonic_ns=iter((0,)).__next__,
        ):
            raise expected

    assert caught.value is expected
    assert api.mps.synchronize_calls == 2


def test_phase_timer_preserves_body_error_when_exception_sync_also_fails() -> None:
    """Catch cleanup synchronization replacing the original inference failure."""

    class _FailingCleanupAccelerator(_RecordingAccelerator):
        def synchronize(self) -> None:
            super().synchronize()
            if self.synchronize_calls == 2:
                raise RuntimeError("cleanup sync failed")

    api = _RecordingTorchApi()
    api.mps = _FailingCleanupAccelerator()
    expected = RuntimeError("model exploded")

    with pytest.raises(RuntimeError) as caught:
        with PhaseTimer(
            DeviceSynchronizer(api, "mps"),
            monotonic_ns=iter((0,)).__next__,
        ):
            raise expected

    assert caught.value is expected
    assert api.mps.synchronize_calls == 2
    assert "cleanup sync failed" in " ".join(expected.__notes__)


def test_phase_timer_preserves_nonapplicable_nulls_and_coherent_total() -> None:
    """Catch a YOLO-only phase being zero-filled as if SAM had run."""

    api = _RecordingTorchApi()
    with PhaseTimer(
        DeviceSynchronizer(api, "mps"),
        monotonic_ns=iter((0, 2_000_000, 7_000_000, 10_000_000)).__next__,
    ) as timer:
        timer.mark("preprocess")
        timer.mark("dino_or_yolo")
        timer.mark("postprocess")

    timings = timer.to_timings(sam_applicable=False, selector_applicable=False)

    assert timings.preprocess_ms == 2.0
    assert timings.dino_or_yolo_ms == 5.0
    assert timings.sam_ms is None
    assert timings.postprocess_ms == 3.0
    assert timings.selector_ms is None
    assert timings.total_ms == 10.0


@pytest.mark.parametrize(
    "overrides",
    (
        {"total_ms": float("nan")},
        {"postprocess_ms": -0.1},
        {"total_ms": 4.0},
    ),
)
def test_phase_breakdown_rejects_nonfinite_negative_or_incoherent_values(
    overrides: dict[str, float],
) -> None:
    """Catch formal timing rows whose total cannot be reproduced from phases."""

    values: dict[str, float | None] = {
        "preprocess_ms": 1.0,
        "dino_or_yolo_ms": 2.0,
        "sam_ms": None,
        "postprocess_ms": 1.0,
        "selector_ms": None,
        "total_ms": 4.0,
    }
    values.update(overrides)
    if overrides == {"total_ms": 4.0}:
        values["preprocess_ms"] = 2.0

    with pytest.raises(ValueError):
        PhaseTimingBreakdown(**values)  # type: ignore[arg-type]


def test_formal_synchronizer_rejects_cpu() -> None:
    """Catch a formal benchmark silently timing an unsupported CPU fallback."""

    with pytest.raises(RuntimeError, match="forbids CPU"):
        DeviceSynchronizer(_RecordingTorchApi(), "cpu").synchronize()


def test_unavailable_gpu_measurements_are_none_with_reasons_not_zero() -> None:
    """Catch unavailable MPS telemetry being reported as measured zero."""

    api = _RecordingTorchApi()
    api.mps.current_allocated_memory = lambda: 8192  # type: ignore[attr-defined]
    api.mps.driver_allocated_memory = lambda: 12288  # type: ignore[attr-defined]
    sample = ResourceSampler(
        process=_FakeProcess(), torch_api=api, device="mps"
    ).sample()

    assert sample.process_rss_bytes == 4096
    assert sample.process_cpu_percent == 12.5
    assert sample.gpu_memory_allocated_bytes == 8192
    assert sample.gpu_memory_reserved_bytes == 12288
    assert sample.gpu_utilization_percent is None
    assert sample.gpu_temperature_celsius is None
    assert sample.gpu_power_watts is None
    assert sample.unavailable_reasons == {
        "gpu_utilization_percent": "mps telemetry is unavailable",
        "gpu_temperature_celsius": "mps telemetry is unavailable",
        "gpu_power_watts": "mps telemetry is unavailable",
    }
    assert sample.tool_versions["torch"] == "2.test"


def test_resource_sampler_preserves_cuda_measurements() -> None:
    """Catch available CUDA resource data being discarded as unavailable."""

    api = _RecordingTorchApi()
    api.cuda.memory_allocated = lambda: 1000  # type: ignore[attr-defined]
    api.cuda.memory_reserved = lambda: 2000  # type: ignore[attr-defined]
    api.cuda.utilization = lambda: 75.0  # type: ignore[attr-defined]
    api.cuda.temperature = lambda: 61.0  # type: ignore[attr-defined]
    api.cuda.power_draw = lambda: 75_000  # type: ignore[attr-defined]

    sample = ResourceSampler(
        process=_FakeProcess(), torch_api=api, device="cuda"
    ).sample()

    assert sample.gpu_memory_allocated_bytes == 1000
    assert sample.gpu_memory_reserved_bytes == 2000
    assert sample.gpu_utilization_percent == 75.0
    assert sample.gpu_temperature_celsius == 61.0
    assert sample.gpu_power_watts == 75.0
    assert sample.unavailable_reasons == {}


def test_missing_accelerator_telemetry_apis_return_null_with_reasons() -> None:
    """Catch API discovery itself raising instead of producing nullable telemetry."""

    api = SimpleNamespace(
        __version__="2.test",
        cuda=SimpleNamespace(synchronize=lambda: None),
        mps=SimpleNamespace(synchronize=lambda: None),
    )

    sample = ResourceSampler(
        process=_FakeProcess(), torch_api=api, device="cuda"
    ).sample()

    assert sample.gpu_memory_allocated_bytes is None
    assert sample.gpu_memory_reserved_bytes is None
    assert sample.gpu_utilization_percent is None
    assert sample.gpu_temperature_celsius is None
    assert sample.gpu_power_watts is None
    assert set(sample.unavailable_reasons) == {
        "gpu_memory_allocated_bytes",
        "gpu_memory_reserved_bytes",
        "gpu_utilization_percent",
        "gpu_temperature_celsius",
        "gpu_power_watts",
    }
