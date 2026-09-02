"""Accelerator-synchronized phase timing and nullable resource telemetry."""

from __future__ import annotations

import importlib
import math
import platform
import time
from dataclasses import dataclass, field
from numbers import Real
from types import MappingProxyType
from typing import Any, Callable, Mapping

from so101_demo.core.detection import RuntimeDevice


_PHASE_ORDER = (
    "preprocess",
    "dino_or_yolo",
    "sam",
    "postprocess",
    "selector",
)
_RESOURCE_FIELDS = (
    "process_rss_bytes",
    "process_cpu_percent",
    "gpu_memory_allocated_bytes",
    "gpu_memory_reserved_bytes",
    "gpu_utilization_percent",
    "gpu_temperature_celsius",
    "gpu_power_watts",
)


def _optional_finite(name: str, value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be null or finite and nonnegative")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{name} must be null or finite and nonnegative")
    return normalized


def _optional_integer(name: str, value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be null or a nonnegative integer")
    return value


@dataclass(frozen=True, slots=True)
class PhaseTimingBreakdown:
    """One synchronized timing row with explicit non-applicable phases."""

    preprocess_ms: float
    dino_or_yolo_ms: float
    sam_ms: float | None
    postprocess_ms: float
    selector_ms: float | None
    total_ms: float

    def __post_init__(self) -> None:
        for name in (
            "preprocess_ms",
            "dino_or_yolo_ms",
            "sam_ms",
            "postprocess_ms",
            "selector_ms",
            "total_ms",
        ):
            value = _optional_finite(name, getattr(self, name))
            if value is None and name not in {"sam_ms", "selector_ms"}:
                raise ValueError("required phase timing must not be null")
            object.__setattr__(self, name, value)
        expected = sum(
            value
            for value in (
                self.preprocess_ms,
                self.dino_or_yolo_ms,
                self.sam_ms,
                self.postprocess_ms,
                self.selector_ms,
            )
            if value is not None
        )
        if not math.isclose(self.total_ms, expected, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("phase timing total is incoherent")


@dataclass(frozen=True, slots=True)
class ResourceSample:
    """One process/GPU resource sample without fabricated zero telemetry."""

    process_rss_bytes: int | None
    process_cpu_percent: float | None
    gpu_memory_allocated_bytes: int | None
    gpu_memory_reserved_bytes: int | None
    gpu_utilization_percent: float | None
    gpu_temperature_celsius: float | None
    gpu_power_watts: float | None
    unavailable_reasons: Mapping[str, str] = field(default_factory=dict)
    tool_versions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "process_rss_bytes",
            "gpu_memory_allocated_bytes",
            "gpu_memory_reserved_bytes",
        ):
            object.__setattr__(self, name, _optional_integer(name, getattr(self, name)))
        for name in (
            "process_cpu_percent",
            "gpu_utilization_percent",
            "gpu_temperature_celsius",
            "gpu_power_watts",
        ):
            object.__setattr__(self, name, _optional_finite(name, getattr(self, name)))
        if (
            self.gpu_utilization_percent is not None
            and self.gpu_utilization_percent > 100.0
        ):
            raise ValueError("gpu_utilization_percent must be in [0, 100]")
        reasons = dict(self.unavailable_reasons)
        if not all(
            name in _RESOURCE_FIELDS
            and isinstance(reason, str)
            and reason
            and getattr(self, name) is None
            for name, reason in reasons.items()
        ):
            raise ValueError("unavailable_reasons must describe null resource fields")
        null_fields = {
            name for name in _RESOURCE_FIELDS if getattr(self, name) is None
        }
        if set(reasons) != null_fields:
            raise ValueError("every null resource field requires an unavailable reason")
        versions = dict(self.tool_versions)
        if not all(
            isinstance(name, str)
            and name
            and isinstance(version, str)
            and version
            for name, version in versions.items()
        ):
            raise ValueError("tool_versions must map non-empty strings")
        object.__setattr__(self, "unavailable_reasons", MappingProxyType(reasons))
        object.__setattr__(self, "tool_versions", MappingProxyType(versions))


class DeviceSynchronizer:
    """Synchronize the exact formal accelerator before reading a boundary."""

    def __init__(self, torch_api: Any, device: RuntimeDevice) -> None:
        self._torch = torch_api
        self.device = device

    def synchronize(self) -> None:
        if self.device == "cuda":
            self._torch.cuda.synchronize()
            return
        if self.device == "mps":
            self._torch.mps.synchronize()
            return
        raise RuntimeError("formal benchmark forbids CPU")


class PhaseTimer:
    """Measure ordered segments after synchronizing at every boundary."""

    def __init__(
        self,
        synchronizer: DeviceSynchronizer,
        *,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._synchronizer = synchronizer
        self._monotonic_ns = monotonic_ns
        self._previous_ns: int | None = None
        self._last_phase_index = -1
        self._elapsed: dict[str, float] = {}

    @property
    def elapsed_ms(self) -> dict[str, float]:
        return dict(self._elapsed)

    def __enter__(self) -> "PhaseTimer":
        if self._previous_ns is not None:
            raise RuntimeError("phase timer cannot be entered twice")
        self._synchronizer.synchronize()
        self._previous_ns = self._monotonic_ns()
        return self

    def mark(self, phase: str) -> float:
        if self._previous_ns is None:
            raise RuntimeError("phase timer is not active")
        if phase not in _PHASE_ORDER:
            raise ValueError("phase name is unknown")
        phase_index = _PHASE_ORDER.index(phase)
        if phase_index <= self._last_phase_index or phase in self._elapsed:
            raise ValueError("phase marks must be unique and ordered")
        self._synchronizer.synchronize()
        current_ns = self._monotonic_ns()
        if current_ns < self._previous_ns:
            raise RuntimeError("monotonic clock moved backwards")
        elapsed = (current_ns - self._previous_ns) / 1_000_000.0
        self._elapsed[phase] = elapsed
        self._previous_ns = current_ns
        self._last_phase_index = phase_index
        return elapsed

    def __exit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: object,
    ) -> None:
        del error_type, traceback
        if error is not None:
            try:
                self._synchronizer.synchronize()
            except Exception as sync_error:
                error.add_note(
                    f"accelerator synchronization also failed: {sync_error}"
                )
        return None

    def to_timings(
        self, *, sam_applicable: bool, selector_applicable: bool
    ) -> PhaseTimingBreakdown:
        required = {"preprocess", "dino_or_yolo", "postprocess"}
        if sam_applicable:
            required.add("sam")
        if selector_applicable:
            required.add("selector")
        if not required.issubset(self._elapsed):
            raise RuntimeError("required phase timing was not marked")
        if not sam_applicable and "sam" in self._elapsed:
            raise RuntimeError("non-applicable SAM phase was measured")
        if not selector_applicable and "selector" in self._elapsed:
            raise RuntimeError("non-applicable selector phase was measured")
        values = {name: self._elapsed.get(name) for name in _PHASE_ORDER}
        return PhaseTimingBreakdown(
            preprocess_ms=values["preprocess"],  # type: ignore[arg-type]
            dino_or_yolo_ms=values["dino_or_yolo"],  # type: ignore[arg-type]
            sam_ms=values["sam"],
            postprocess_ms=values["postprocess"],  # type: ignore[arg-type]
            selector_ms=values["selector"],
            total_ms=sum(self._elapsed.values()),
        )


class ResourceSampler:
    """Sample available process/GPU telemetry and explain every null field."""

    def __init__(
        self,
        *,
        process: Any | None = None,
        torch_api: Any | None = None,
        device: RuntimeDevice,
    ) -> None:
        if device not in {"cuda", "mps"}:
            raise ValueError("formal resource sampling requires cuda or mps")
        if torch_api is None:
            torch_api = importlib.import_module("torch")
        if process is None:
            psutil = importlib.import_module("psutil")
            process = psutil.Process()
            self._psutil_version = str(getattr(psutil, "__version__", "unknown"))
        else:
            self._psutil_version = str(
                getattr(importlib.import_module("psutil"), "__version__", "unknown")
            )
        self._process = process
        self._torch = torch_api
        self.device = device

    @staticmethod
    def _read(
        name: str,
        operation: Callable[[], object],
        reasons: dict[str, str],
        unavailable: str,
    ) -> object | None:
        try:
            return operation()
        except (AttributeError, NotImplementedError, OSError, RuntimeError, TypeError):
            reasons[name] = unavailable
            return None

    def sample(self) -> ResourceSample:
        reasons: dict[str, str] = {}
        memory_info = self._read(
            "process_rss_bytes",
            self._process.memory_info,
            reasons,
            "process RSS telemetry is unavailable",
        )
        process_rss = None if memory_info is None else int(memory_info.rss)
        process_cpu = self._read(
            "process_cpu_percent",
            lambda: self._process.cpu_percent(interval=None),
            reasons,
            "process CPU telemetry is unavailable",
        )

        if self.device == "cuda":
            accelerator = self._torch.cuda
            unavailable = "cuda telemetry is unavailable"
            operations: dict[str, Callable[[], object]] = {
                "gpu_memory_allocated_bytes": lambda: getattr(
                    accelerator, "memory_allocated"
                )(),
                "gpu_memory_reserved_bytes": lambda: getattr(
                    accelerator, "memory_reserved"
                )(),
                "gpu_utilization_percent": lambda: getattr(
                    accelerator, "utilization"
                )(),
                "gpu_temperature_celsius": lambda: getattr(
                    accelerator, "temperature"
                )(),
                "gpu_power_watts": lambda: getattr(accelerator, "power_draw")()
                / 1000.0,
            }
        else:
            accelerator = self._torch.mps
            unavailable = "mps telemetry is unavailable"
            operations = {
                "gpu_memory_allocated_bytes": lambda: getattr(
                    accelerator, "current_allocated_memory"
                )(),
                "gpu_memory_reserved_bytes": lambda: getattr(
                    accelerator, "driver_allocated_memory"
                )(),
            }
            for name in (
                "gpu_utilization_percent",
                "gpu_temperature_celsius",
                "gpu_power_watts",
            ):
                reasons[name] = unavailable

        values: dict[str, object | None] = {
            name: self._read(name, operation, reasons, unavailable)
            for name, operation in operations.items()
        }
        for name in (
            "gpu_memory_allocated_bytes",
            "gpu_memory_reserved_bytes",
            "gpu_utilization_percent",
            "gpu_temperature_celsius",
            "gpu_power_watts",
        ):
            values.setdefault(name, None)
        return ResourceSample(
            process_rss_bytes=process_rss,
            process_cpu_percent=process_cpu,  # type: ignore[arg-type]
            gpu_memory_allocated_bytes=(
                None
                if values["gpu_memory_allocated_bytes"] is None
                else int(values["gpu_memory_allocated_bytes"])  # type: ignore[arg-type]
            ),
            gpu_memory_reserved_bytes=(
                None
                if values["gpu_memory_reserved_bytes"] is None
                else int(values["gpu_memory_reserved_bytes"])  # type: ignore[arg-type]
            ),
            gpu_utilization_percent=values["gpu_utilization_percent"],  # type: ignore[arg-type]
            gpu_temperature_celsius=values["gpu_temperature_celsius"],  # type: ignore[arg-type]
            gpu_power_watts=values["gpu_power_watts"],  # type: ignore[arg-type]
            unavailable_reasons=reasons,
            tool_versions={
                "python": platform.python_version(),
                "torch": str(getattr(self._torch, "__version__", "unknown")),
                "psutil": self._psutil_version,
                "device": self.device,
            },
        )


__all__ = (
    "DeviceSynchronizer",
    "PhaseTimer",
    "PhaseTimingBreakdown",
    "ResourceSample",
    "ResourceSampler",
)
