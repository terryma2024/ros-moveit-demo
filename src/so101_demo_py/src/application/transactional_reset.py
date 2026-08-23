"""First-failure reset coordinator over backend-neutral operation ports."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from ..ports.reset import (
    HomePlanReceipt,
    ResetPhaseReceipt,
    ResetStepReceipt,
    TransactionalResetPorts,
    TransactionalResetReceipt,
    TransactionalResetRequest,
)


class ResetPhase(StrEnum):
    OBSERVE_INITIAL = "OBSERVE_INITIAL"
    CANCEL_ARM_GOALS = "CANCEL_ARM_GOALS"
    CANCEL_GRIPPER_GOALS = "CANCEL_GRIPPER_GOALS"
    DETACH_PHYSICAL = "DETACH_PHYSICAL"
    DETACH_MOVEIT = "DETACH_MOVEIT"
    PARK_CUP = "PARK_CUP"
    SYNC_PARKED_SCENE = "SYNC_PARKED_SCENE"
    OPEN_GRIPPER = "OPEN_GRIPPER"
    PLAN_HOME = "PLAN_HOME"
    EXECUTE_HOME = "EXECUTE_HOME"
    RESTORE_CUP = "RESTORE_CUP"
    SYNC_FINAL_SCENE = "SYNC_FINAL_SCENE"
    VERIFY_FINAL = "VERIFY_FINAL"


class TransactionalResetCoordinator:
    def __init__(self, ports: TransactionalResetPorts) -> None:
        self._ports = ports

    @staticmethod
    def _exception(phase: ResetPhase, error: Exception) -> ResetStepReceipt:
        return ResetStepReceipt(
            False,
            f"RESET_{phase.value}_FAILED",
            {"exception_type": type(error).__name__, "message": str(error)},
        )

    def run(self, request: TransactionalResetRequest) -> TransactionalResetReceipt:
        steps: list[ResetPhaseReceipt] = []
        completed: list[str] = []

        def finish_failure(
            phase: ResetPhase,
            result: ResetStepReceipt,
        ) -> TransactionalResetReceipt:
            phase_receipt = ResetPhaseReceipt(
                phase.value,
                False,
                result.failure_code,
                result.evidence,
            )
            steps.append(phase_receipt)
            return TransactionalResetReceipt(
                backend=request.backend,
                session_id=request.session_id,
                success=False,
                phase=phase.value,
                failure_code=result.failure_code,
                steps=tuple(steps),
                evidence={
                    "completed_phases": completed,
                    "failure": result.evidence,
                },
            )

        def invoke(
            phase: ResetPhase,
            operation: Callable[[], ResetStepReceipt],
        ) -> TransactionalResetReceipt | None:
            try:
                result = operation()
            except Exception as error:
                result = self._exception(phase, error)
            if not result.success:
                return finish_failure(phase, result)
            steps.append(ResetPhaseReceipt(phase.value, True, None, result.evidence))
            completed.append(phase.value)
            return None

        operations: tuple[
            tuple[ResetPhase, Callable[[], ResetStepReceipt]], ...
        ] = (
            (ResetPhase.OBSERVE_INITIAL, self._ports.observation.observe_initial),
            (ResetPhase.CANCEL_ARM_GOALS, self._ports.goals.cancel_arm_goals),
            (
                ResetPhase.CANCEL_GRIPPER_GOALS,
                self._ports.goals.cancel_gripper_goals,
            ),
            (ResetPhase.DETACH_PHYSICAL, self._ports.physical.detach_task_object),
            (ResetPhase.DETACH_MOVEIT, self._ports.scene.detach_task_object),
            (
                ResetPhase.PARK_CUP,
                lambda: self._ports.physical.park_task_object(request.parking_pose),
            ),
            (
                ResetPhase.SYNC_PARKED_SCENE,
                lambda: self._ports.scene.synchronize_task_scene(request.parking_pose),
            ),
            (ResetPhase.OPEN_GRIPPER, self._ports.robot.open_gripper),
        )
        for phase, operation in operations:
            failure = invoke(phase, operation)
            if failure is not None:
                return failure

        phase = ResetPhase.PLAN_HOME
        try:
            plan: HomePlanReceipt = self._ports.robot.plan_home(
                request.named_home_state
            )
        except Exception as error:
            plan = HomePlanReceipt(
                False,
                None,
                f"RESET_{phase.value}_FAILED",
                {"exception_type": type(error).__name__, "message": str(error)},
            )
        if not plan.success:
            return finish_failure(
                phase,
                ResetStepReceipt(False, plan.failure_code, plan.evidence),
            )
        steps.append(ResetPhaseReceipt(phase.value, True, None, plan.evidence))
        completed.append(phase.value)
        exact_plan: Any = plan.plan

        remaining: tuple[
            tuple[ResetPhase, Callable[[], ResetStepReceipt]], ...
        ] = (
            (
                ResetPhase.EXECUTE_HOME,
                lambda: self._ports.robot.execute_home_and_verify(exact_plan),
            ),
            (
                ResetPhase.RESTORE_CUP,
                lambda: self._ports.physical.restore_task_object(request.spawn_pose),
            ),
            (
                ResetPhase.SYNC_FINAL_SCENE,
                lambda: self._ports.scene.synchronize_task_scene(request.spawn_pose),
            ),
            (ResetPhase.VERIFY_FINAL, self._ports.observation.verify_final),
        )
        for phase, operation in remaining:
            failure = invoke(phase, operation)
            if failure is not None:
                return failure

        return TransactionalResetReceipt(
            backend=request.backend,
            session_id=request.session_id,
            success=True,
            phase=ResetPhase.VERIFY_FINAL.value,
            failure_code=None,
            steps=tuple(steps),
            evidence={"completed_phases": completed, "phase_count": len(completed)},
        )
