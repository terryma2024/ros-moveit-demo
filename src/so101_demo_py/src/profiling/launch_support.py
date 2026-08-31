"""Launch-facing configuration and lifecycle support for semantic profiling."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from launch.actions import RegisterEventHandler
from launch.event_handlers import OnProcessExit, OnShutdown

from .artifacts import FinalizationResult, finalize_profiling
from .model import ProfilingConfig, ProfilingMode
from .session import SemanticProfiler, SpanToken, build_profiler


@dataclass(slots=True)
class LaunchProfilingSession:
    """Own the launch process stream and its lifecycle event correlation."""

    mode: ProfilingMode
    profiling_root: Path
    require_system_trace: bool
    profiler: SemanticProfiler
    _total_span: SpanToken
    _stack_span: SpanToken
    _scene_span: SpanToken
    _scene_finished: bool = False
    _total_finished: bool = False
    _workflow_seen: bool = False
    _perception_seen: bool = False
    _warnings: list[str] = field(default_factory=list)

    @property
    def child_arguments(self) -> tuple[str, ...]:
        """Arguments appended only to profiling-enabled child processes."""

        return (
            "--profiling",
            self.mode.value,
            "--profiling-output-root",
            str(self.profiling_root),
            "--profiling-session-id",
            self.profiler.config.session_id,
        )

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings) + self.profiler.warnings

    def record_scene_exit(self, returncode: int) -> None:
        if not self._scene_finished:
            outcome = "ready" if returncode == 0 else "failed"
            attributes = {"exit_code": returncode}
            self.profiler.finish_span(
                self._scene_span,
                outcome=outcome,
                attributes=attributes,
            )
            self.profiler.finish_span(
                self._stack_span,
                outcome=outcome,
                attributes=attributes,
            )
            self._scene_finished = True

    def record_workflow_exit(self, returncode: int) -> None:
        self._workflow_seen = True
        if not self._total_finished:
            self.profiler.finish_span(
                self._total_span,
                outcome="completed" if returncode == 0 else "failed",
                attributes={"exit_code": returncode},
            )
            self._total_finished = True
        self._finalize_if_terminal()

    def record_perception_exit(self, returncode: int) -> None:
        self._perception_seen = True
        self.profiler.instant(
            "launch.perception_exit",
            {"exit_code": returncode},
        )
        self._finalize_if_terminal()

    def finalize_for_shutdown(
        self,
        *,
        reason: str,
    ) -> FinalizationResult | None:
        """Finalize best-effort artifacts without changing launch shutdown status."""

        if not self._scene_finished:
            self.profiler.finish_span(
                self._scene_span,
                outcome="interrupted",
                attributes={"shutdown_reason": reason},
            )
            self.profiler.finish_span(
                self._stack_span,
                outcome="interrupted",
                attributes={"shutdown_reason": reason},
            )
            self._scene_finished = True
        if not self._total_finished:
            self.profiler.finish_span(
                self._total_span,
                outcome="interrupted",
                attributes={"shutdown_reason": reason},
            )
            self._total_finished = True
        return self._finalize()

    def _finalize_if_terminal(self) -> None:
        if self._workflow_seen and self._perception_seen:
            self._finalize()

    def _finalize(self) -> FinalizationResult | None:
        try:
            self.profiler.close()
            return finalize_profiling(
                self.profiling_root,
                mode=self.mode,
                backend={
                    "status": (
                        "portable_only"
                        if self.mode is ProfilingMode.TRACE
                        else "disabled"
                    ),
                    "name": None,
                },
            )
        except (OSError, RuntimeError, ValueError) as error:
            self._warnings.append(f"{type(error).__name__}: {error}")
            return None


def resolve_launch_profiling(
    *,
    mode_value: str,
    output_root_value: str,
    require_system_trace_value: str,
    run_root: Path,
    session_id: str,
    source_commit: str | None,
    installed_prefix: str | None,
) -> LaunchProfilingSession | None:
    """Validate launch values and construct profiling only for enabled modes."""

    mode, require_system_trace = validate_launch_profiling_values(
        mode_value=mode_value,
        output_root_value=output_root_value,
        require_system_trace_value=require_system_trace_value,
    )
    if mode is ProfilingMode.OFF:
        return None

    registered_root = run_root.resolve(strict=True)
    if not registered_root.is_dir():
        raise RuntimeError("registered run evidence root must be a directory")
    output_root = _resolve_output_root(
        output_root_value,
        registered_root=registered_root,
    )
    profiling_root = output_root / "profiling"
    try:
        profiling_root.mkdir(mode=0o700)
    except FileExistsError as error:
        raise RuntimeError(
            f"profiling output already exists: {profiling_root}"
        ) from error
    except OSError as error:
        raise RuntimeError(
            f"cannot create profiling output: {profiling_root}: {error}"
        ) from error

    config = ProfilingConfig(
        mode=mode,
        output_root=profiling_root,
        session_id=session_id,
        process_role="launch",
        source_commit=source_commit,
        installed_prefix=installed_prefix,
    )
    profiler = build_profiler(config)
    assert profiler is not None
    total_span = profiler.start_span("launch.total")
    stack_span = profiler.start_span("launch.stack_startup")
    scene_span = profiler.start_span("launch.scene_setup")
    return LaunchProfilingSession(
        mode=mode,
        profiling_root=profiling_root,
        require_system_trace=require_system_trace,
        profiler=profiler,
        _total_span=total_span,
        _stack_span=stack_span,
        _scene_span=scene_span,
    )


def validate_launch_profiling_values(
    *,
    mode_value: str,
    output_root_value: str,
    require_system_trace_value: str,
) -> tuple[ProfilingMode, bool]:
    """Validate public values without touching clocks, files, or ROS actions."""

    try:
        mode = ProfilingMode.parse(mode_value)
    except ValueError as error:
        raise RuntimeError(str(error)) from error
    if require_system_trace_value not in {"true", "false"}:
        raise RuntimeError(
            "profiling_require_system_trace must be true or false"
        )
    if (
        mode is not ProfilingMode.OFF
        and output_root_value
        and not Path(output_root_value).is_absolute()
    ):
        raise RuntimeError("profiling_output_root must be absolute")
    return mode, require_system_trace_value == "true"


def profiling_event_handlers(
    session: LaunchProfilingSession,
    *,
    scene_setup,
    perception,
    workflow,
) -> tuple[RegisterEventHandler, ...]:
    """Register observational handlers beside the business exit policy."""

    def on_scene_exit(event, _context):
        session.record_scene_exit(event.returncode)
        return []

    def on_perception_exit(event, _context):
        session.record_perception_exit(event.returncode)
        return []

    def on_workflow_exit(event, _context):
        session.record_workflow_exit(event.returncode)
        return []

    def on_shutdown(event, _context):
        session.finalize_for_shutdown(
            reason=str(getattr(event, "reason", "launch shutdown")),
        )
        return []

    return (
        RegisterEventHandler(
            OnProcessExit(target_action=scene_setup, on_exit=on_scene_exit)
        ),
        RegisterEventHandler(
            OnProcessExit(target_action=perception, on_exit=on_perception_exit)
        ),
        RegisterEventHandler(
            OnProcessExit(target_action=workflow, on_exit=on_workflow_exit)
        ),
        RegisterEventHandler(OnShutdown(on_shutdown=on_shutdown)),
    )


def _resolve_output_root(value: str, *, registered_root: Path) -> Path:
    if not value:
        return registered_root
    candidate = Path(value)
    if not candidate.is_absolute():
        raise RuntimeError("profiling_output_root must be absolute")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(registered_root)
    except ValueError as error:
        raise RuntimeError(
            "profiling_output_root must remain under the registered run evidence root"
        ) from error
    if os.path.lexists(candidate) and candidate.is_symlink():
        raise RuntimeError("profiling_output_root must not be a symbolic link")
    if candidate.exists() and not candidate.is_dir():
        raise RuntimeError("profiling_output_root must be a directory")
    try:
        candidate.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        raise RuntimeError(
            f"cannot create profiling_output_root {candidate}: {error}"
        ) from error
    return candidate.resolve(strict=True)
