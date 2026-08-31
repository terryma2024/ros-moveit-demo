"""Lazy Linux adapter for the official ROS 2 tracing launch action."""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal

from .model import ProfilingMode


SystemTraceStatus = Literal[
    "disabled",
    "unsupported",
    "unavailable",
    "configured",
    "ready",
]

_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(slots=True)
class SystemTraceResult:
    """Resolved system-trace action and sanitized backend metadata."""

    status: SystemTraceStatus
    action: object | None
    backend: str | None
    output_path: Path | None
    error: str | None = None


class RequiredSystemTraceUnavailable(RuntimeError):
    """Raised when the launch contract requires an unavailable backend."""


def validate_profiling_session_id(session_id: str) -> None:
    """Reject session identifiers that cannot safely name an evidence directory."""

    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError(
            "session_id must start with an alphanumeric character and contain only "
            "letters, digits, dot, underscore, or hyphen"
        )


def _policy_trace_action(
    trace_action: object,
    result: SystemTraceResult,
    *,
    require: bool,
    profiling_root: Path,
) -> object:
    """Wrap the official action without importing launch on non-Linux paths."""

    from launch.action import Action

    class PolicyTraceAction(Action):
        def execute(self, context):
            try:
                returned_actions = trace_action.execute(context)
                trace_directory = getattr(trace_action, "trace_directory", None)
                if not trace_directory:
                    raise RuntimeError("Trace action did not report its output directory")
                resolved_output = Path(trace_directory).resolve(strict=False)
                resolved_output.relative_to(profiling_root.resolve(strict=False))
            except (RuntimeError, ValueError) as error:
                result.status = "unavailable"
                result.output_path = None
                result.error = type(error).__name__
                if require:
                    raise RequiredSystemTraceUnavailable(
                        f"required ros2_tracing backend is unavailable ({type(error).__name__})"
                    ) from error
                return []
            result.status = "ready"
            result.output_path = resolved_output
            result.error = None
            return returned_actions

    return PolicyTraceAction()


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
    validate_profiling_session_id(session_id)

    module_name = "tracetools_launch.action"
    try:
        if find_spec(module_name) is None:
            raise ModuleNotFoundError(module_name)
        module = import_module(module_name)
        trace_type = getattr(module, "Trace")
        session_name = f"so101-{session_id}"
        base_path = profiling_root / "ros2-tracing"
        official_action = trace_type(
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

    result = SystemTraceResult(
        "configured",
        None,
        "ros2_tracing",
        None,
    )
    result.action = _policy_trace_action(
        official_action,
        result,
        require=require,
        profiling_root=profiling_root,
    )
    return result
