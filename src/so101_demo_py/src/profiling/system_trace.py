"""Lazy Linux adapter for the official ROS 2 tracing launch action."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal

from .model import ProfilingMode


SystemTraceStatus = Literal["disabled", "unsupported", "unavailable", "ready"]


@dataclass(frozen=True, slots=True)
class SystemTraceResult:
    """Resolved system-trace action and sanitized backend metadata."""

    status: SystemTraceStatus
    action: object | None
    backend: str | None
    output_path: Path | None
    error: str | None = None


class RequiredSystemTraceUnavailable(RuntimeError):
    """Raised when the launch contract requires an unavailable backend."""


def build_system_trace(
    *,
    mode: ProfilingMode,
    require: bool,
    profiling_root: Path,
    session_id: str,
    platform_name: str = sys.platform,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
    import_module: Callable[[str], ModuleType] = importlib.import_module,
) -> SystemTraceResult:
    """Build the official Trace action only for Linux trace mode."""

    if mode is not ProfilingMode.TRACE:
        return SystemTraceResult("disabled", None, None, None)
    if not platform_name.startswith("linux"):
        return SystemTraceResult("unsupported", None, None, None)

    module_name = "tracetools_launch.action"
    try:
        if find_spec(module_name) is None:
            raise ModuleNotFoundError(module_name)
        module = import_module(module_name)
        trace_type = getattr(module, "Trace")
        session_name = f"so101-{session_id}"
        base_path = profiling_root / "ros2-tracing"
        action = trace_type(
            session_name=session_name,
            append_timestamp=False,
            base_path=str(base_path),
        )
    except Exception as error:
        error_class = type(error).__name__
        if require:
            raise RequiredSystemTraceUnavailable(
                f"required ros2_tracing backend is unavailable ({error_class})"
            ) from error
        return SystemTraceResult(
            "unavailable",
            None,
            "ros2_tracing",
            None,
            error_class,
        )

    return SystemTraceResult(
        "ready",
        action,
        "ros2_tracing",
        base_path / session_name,
    )
