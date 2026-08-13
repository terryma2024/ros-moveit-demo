"""Backend-neutral ports and receipts for complete reset transactions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..core.task_geometry import Pose7


@dataclass(frozen=True, slots=True)
class ResetStepReceipt:
    success: bool
    failure_code: str | None
    evidence: dict[str, object]

    def __post_init__(self) -> None:
        if self.success == (self.failure_code is not None):
            raise ValueError("reset step success and failure code disagree")


@dataclass(frozen=True, slots=True)
class HomePlanReceipt:
    success: bool
    plan: Any | None
    failure_code: str | None
    evidence: dict[str, object]

    def __post_init__(self) -> None:
        if self.success:
            if self.plan is None or self.failure_code is not None:
                raise ValueError("successful Home planning requires exactly one plan")
        elif self.failure_code is None or self.plan is not None:
            raise ValueError("failed Home planning cannot expose a plan")


@dataclass(frozen=True, slots=True)
class TransactionalResetRequest:
    backend: str
    session_id: str
    named_home_state: str
    parking_pose: Pose7
    spawn_pose: Pose7

    def __post_init__(self) -> None:
        if not self.backend or not self.session_id or not self.named_home_state:
            raise ValueError("reset request identity must be non-empty")


@dataclass(frozen=True, slots=True)
class ResetPhaseReceipt:
    phase: str
    success: bool
    failure_code: str | None
    evidence: dict[str, object]


@dataclass(frozen=True, slots=True)
class TransactionalResetReceipt:
    backend: str
    session_id: str
    success: bool
    phase: str
    failure_code: str | None
    steps: tuple[ResetPhaseReceipt, ...]
    evidence: dict[str, object]

    def __post_init__(self) -> None:
        if self.success == (self.failure_code is not None):
            raise ValueError("reset transaction success and failure code disagree")


@runtime_checkable
class ResetObservationPort(Protocol):
    def observe_initial(self) -> ResetStepReceipt: ...

    def verify_final(self) -> ResetStepReceipt: ...


@runtime_checkable
class GoalCancellationPort(Protocol):
    def cancel_arm_goals(self) -> ResetStepReceipt: ...

    def cancel_gripper_goals(self) -> ResetStepReceipt: ...


@runtime_checkable
class PhysicalObjectResetPort(Protocol):
    def detach_task_object(self) -> ResetStepReceipt: ...

    def park_task_object(self, pose: Pose7) -> ResetStepReceipt: ...

    def restore_task_object(self, pose: Pose7) -> ResetStepReceipt: ...


@runtime_checkable
class ResetPlanningScenePort(Protocol):
    def detach_task_object(self) -> ResetStepReceipt: ...

    def synchronize_task_scene(self, cup_pose: Pose7) -> ResetStepReceipt: ...


@runtime_checkable
class ResetRobotPort(Protocol):
    def open_gripper(self) -> ResetStepReceipt: ...

    def plan_home(self, named_state: str) -> HomePlanReceipt: ...

    def execute_home_and_verify(self, plan: Any) -> ResetStepReceipt: ...


@dataclass(frozen=True, slots=True)
class TransactionalResetPorts:
    observation: ResetObservationPort
    goals: GoalCancellationPort
    physical: PhysicalObjectResetPort
    scene: ResetPlanningScenePort
    robot: ResetRobotPort


class FailClosedPhysicalObjectResetPort:
    """Default physical boundary for an unimplemented real-arm adapter."""

    @staticmethod
    def _unavailable() -> ResetStepReceipt:
        return ResetStepReceipt(
            False,
            "RESET_REAL_ARM_UNAVAILABLE",
            {"reason": "no authorized physical object reset adapter"},
        )

    def detach_task_object(self) -> ResetStepReceipt:
        return self._unavailable()

    def park_task_object(self, pose: Pose7) -> ResetStepReceipt:
        del pose
        return self._unavailable()

    def restore_task_object(self, pose: Pose7) -> ResetStepReceipt:
        del pose
        return self._unavailable()
