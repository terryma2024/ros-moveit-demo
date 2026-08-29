from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from ..ports.pick_place_executor import (
    DynamicCupPickPlaceRequest,
    ExecutorDispatchError,
    RuntimeDispatchResult,
)


@dataclass(frozen=True, slots=True)
class DynamicRuntimeContext:
    session_id: str
    expected_reset_epoch: int
    evidence_root: Path
    source_commit: str
    installed_prefix: str


class DynamicCupPickPlaceExecutor:
    def __init__(
        self,
        context: DynamicRuntimeContext,
        *,
        runner: Callable[[SimpleNamespace], int] | None = None,
    ) -> None:
        self._context = context
        self._runner = runner

    def dispatch(
        self,
        request: DynamicCupPickPlaceRequest,
    ) -> RuntimeDispatchResult:
        if not self._is_supported_request(request):
            return RuntimeDispatchResult(1, self._context.session_id)

        runner = self._runner
        if runner is None:
            from ..ros.dynamic_runtime import run_dynamic_execute

            runner = run_dynamic_execute

        try:
            exit_code = runner(self._runtime_options())
        except Exception:
            raise ExecutorDispatchError("DYNAMIC_RUNTIME_EXCEPTION") from None
        if type(exit_code) is not int:
            raise ExecutorDispatchError("DYNAMIC_RUNTIME_RESULT_INVALID")
        return RuntimeDispatchResult(exit_code, self._context.session_id)

    def _runtime_options(self) -> SimpleNamespace:
        return SimpleNamespace(
            backend="mujoco",
            mode="execute",
            execute=True,
            scene_source="observe_only",
            dynamic_policy=None,
            cup_pose_timeout_s=5.0,
            source_commit=self._context.source_commit,
            installed_prefix=self._context.installed_prefix,
            session_id=self._context.session_id,
            expected_reset_epoch=self._context.expected_reset_epoch,
            evidence_root=self._context.evidence_root,
        )

    @staticmethod
    def _is_supported_request(request: DynamicCupPickPlaceRequest) -> bool:
        return (
            request.capability == "dynamic_cup_pick_place"
            and request.backend == "mujoco"
            and request.scene_source == "observe_only"
            and request.target_object == "plastic_cup"
            and request.action == "pick"
        )
