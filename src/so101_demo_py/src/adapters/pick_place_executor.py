from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from types import SimpleNamespace
from typing import TYPE_CHECKING, Callable

from ..ports.pick_place_executor import (
    DynamicCupPickPlaceRequest,
    ExecutionProvenance,
    ExecutorDispatchError,
    RuntimeDispatchResult,
)
from ..runtime.workflow_events import EventEmitter

if TYPE_CHECKING:
    from ..profiling.session import SemanticProfiler


@dataclass(frozen=True, slots=True)
class DynamicRuntimeContext:
    session_id: str
    expected_reset_epoch: int
    evidence_root: Path
    source_commit: str
    installed_prefix: str
    execution_provenance: ExecutionProvenance
    profiler: SemanticProfiler | None = None
    workflow_id: str | None = None
    event_emitter: EventEmitter | None = None


class DynamicCupPickPlaceExecutor:
    def __init__(
        self,
        context: DynamicRuntimeContext,
        *,
        cup_pose_timeout_s: float = 30.0,
        runner: Callable[[SimpleNamespace], int] | None = None,
    ) -> None:
        if (
            type(cup_pose_timeout_s) is not float
            or not math.isfinite(cup_pose_timeout_s)
            or cup_pose_timeout_s <= 0.0
        ):
            raise ValueError("cup_pose_timeout_s must be finite and positive")
        self._context = context
        self._cup_pose_timeout_s = cup_pose_timeout_s
        self._runner = runner

    def dispatch(
        self,
        request: DynamicCupPickPlaceRequest,
    ) -> RuntimeDispatchResult:
        if not self._is_supported_request(request):
            return RuntimeDispatchResult(1, self._context.session_id)
        if not self._has_valid_context(self._context):
            raise ExecutorDispatchError("DYNAMIC_RUNTIME_CONTEXT_INVALID")

        try:
            if self._context.event_emitter is not None:
                self._context.event_emitter.emit(
                    "RUNTIME_STARTED",
                    payload={
                        "request_id": request.request_id,
                        "session_id": self._context.session_id,
                        "reset_epoch": self._context.expected_reset_epoch,
                    },
                )
            runner = self._runner
            if runner is None:
                from ..ros.dynamic_runtime import run_dynamic_execute

                runtime_options = self._runtime_options(request)
                if self._context.event_emitter is None:
                    exit_code = run_dynamic_execute(
                        runtime_options,
                        profiler=self._context.profiler,
                    )
                else:
                    exit_code = run_dynamic_execute(
                        runtime_options,
                        profiler=self._context.profiler,
                        event_emitter=self._context.event_emitter,
                    )
            else:
                exit_code = runner(self._runtime_options(request))
        except Exception:
            self._emit_missing_terminal("DYNAMIC_RUNTIME_EXCEPTION")
            raise ExecutorDispatchError("DYNAMIC_RUNTIME_EXCEPTION") from None
        if type(exit_code) is not int:
            self._emit_missing_terminal("DYNAMIC_RUNTIME_RESULT_INVALID")
            raise ExecutorDispatchError("DYNAMIC_RUNTIME_RESULT_INVALID")
        if exit_code == 0:
            self._emit_missing_terminal(
                None,
                manifest_path=self._context.evidence_root
                / "dynamic-execute-manifest.json",
            )
        else:
            self._emit_missing_terminal("RUNTIME_FAILED")
        return RuntimeDispatchResult(exit_code, self._context.session_id)

    def _emit_missing_terminal(
        self,
        failure_code: str | None,
        *,
        manifest_path: Path | None = None,
    ) -> None:
        emitter = self._context.event_emitter
        if emitter is None or (
            emitter.last_event is not None
            and emitter.last_event.event in {"RUNTIME_COMPLETED", "RUNTIME_FAILED"}
        ):
            return
        if failure_code is not None:
            emitter.emit(
                "RUNTIME_FAILED",
                payload={},
                failure_code=failure_code,
            )
            return
        if manifest_path is None:
            raise RuntimeError("runtime completion manifest is missing")
        emitter.emit(
            "RUNTIME_COMPLETED",
            payload={"manifest_path": str(manifest_path), "runtime_exit_code": 0},
        )

    def _runtime_options(
        self, request: DynamicCupPickPlaceRequest
    ) -> SimpleNamespace:
        values: dict[str, object] = dict(
            backend="mujoco",
            mode="execute",
            execute=True,
            scene_source="observe_only",
            dynamic_policy=None,
            cup_pose_timeout_s=self._cup_pose_timeout_s,
            source_commit=self._context.source_commit,
            installed_prefix=self._context.installed_prefix,
            session_id=self._context.session_id,
            expected_reset_epoch=self._context.expected_reset_epoch,
            evidence_root=self._context.evidence_root,
        )
        if self._context.workflow_id is not None:
            values.update(
                workflow_id=self._context.workflow_id,
                request_id=request.request_id,
            )
        return SimpleNamespace(**values)

    @staticmethod
    def _is_supported_request(request: DynamicCupPickPlaceRequest) -> bool:
        return (
            request.capability == "dynamic_cup_pick_place"
            and request.backend == "mujoco"
            and request.scene_source == "observe_only"
            and request.target_object == "plastic_cup"
            and request.action == "pick"
        )

    @staticmethod
    def _has_valid_context(context: DynamicRuntimeContext) -> bool:
        return (
            type(context.session_id) is str
            and bool(context.session_id.strip())
            and type(context.expected_reset_epoch) is int
            and context.expected_reset_epoch >= 0
            and isinstance(context.evidence_root, Path)
            and context.evidence_root.is_absolute()
            and type(context.source_commit) is str
            and re.fullmatch(r"[0-9a-f]{40}", context.source_commit) is not None
            and type(context.installed_prefix) is str
            and bool(context.installed_prefix)
            and Path(context.installed_prefix).is_absolute()
            and isinstance(context.execution_provenance, ExecutionProvenance)
            and context.execution_provenance.source_commit == context.source_commit
            and context.execution_provenance.installed_prefix
            == context.installed_prefix
            and context.execution_provenance.session_id == context.session_id
            and context.execution_provenance.expected_reset_epoch
            == context.expected_reset_epoch
            and context.execution_provenance.evidence_root
            == str(context.evidence_root)
            and (
                (
                    context.workflow_id is None
                    and context.event_emitter is None
                )
                or (
                    type(context.workflow_id) is str
                    and re.fullmatch(
                        r"[A-Za-z0-9][A-Za-z0-9_.-]*",
                        context.workflow_id,
                    )
                    is not None
                    and isinstance(context.event_emitter, EventEmitter)
                    and context.event_emitter.workflow_id == context.workflow_id
                    and context.event_emitter.component == "dynamic_runtime"
                )
            )
        )
