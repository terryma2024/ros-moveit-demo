"""Evidence-driven recovery path selection."""

from dataclasses import dataclass
from typing import Callable, Mapping

from .domain import ActionResult, ActionStatus, Failure, FailureCategory, State
from .simulation.protocols import WorldReset
from .simulation.types import ContactEvidence, SimulationEvidence


@dataclass(frozen=True, slots=True)
class RecoveryEvidence:
    simulator_task_object_constrained: bool | None = None
    moveit_task_object_attached: bool | None = None
    task_object_supported: bool | None = None
    gripper_task_object_contact: bool | None = None


class RecoveryPolicy:
    def path_for(self, failed_state: State, evidence: RecoveryEvidence) -> tuple[State, ...]:
        del failed_state
        if (
            evidence.gripper_task_object_contact is True
            and evidence.task_object_supported is not True
        ):
            return ()
        path = []
        if evidence.simulator_task_object_constrained:
            path.extend((State.RECOVER_LIFT_TO_SAFE_HEIGHT, State.RECOVER_DETACH_GAZEBO))
        if evidence.moveit_task_object_attached:
            path.append(State.RECOVER_DETACH_MOVEIT)
        if evidence.simulator_task_object_constrained or evidence.moveit_task_object_attached:
            path.append(State.RECOVER_SYNC_WORLD_OBJECT)
        path.append(State.RECOVER_RETREAT)
        return tuple(path)


def _matches_collision(contact: ContactEvidence, collision: str) -> bool:
    return collision in {
        contact.body1,
        contact.geom1,
        contact.body2,
        contact.geom2,
    }


def recovery_evidence_from_simulation(
    evidence: SimulationEvidence,
    *,
    moveit_task_object_attached: bool | None,
    intended_support_collision: str,
) -> RecoveryEvidence:
    """Map Task 5 evidence to the simulator-neutral recovery facts."""
    return RecoveryEvidence(
        simulator_task_object_constrained=False,
        moveit_task_object_attached=moveit_task_object_attached,
        task_object_supported=any(
            _matches_collision(contact, intended_support_collision)
            for contact in evidence.other_object_contacts
        ),
        gripper_task_object_contact=bool(
            evidence.left_fingertip_contacts or evidence.right_fingertip_contacts
        ),
    )


class WorldResetAction:
    """Recovery boundary that depends only on the world-reset protocol."""

    def __init__(self, reset: WorldReset, keyframe: str = "task_start") -> None:
        self._reset = reset
        self._keyframe = keyframe

    def run(self) -> ActionResult:
        try:
            self._reset.reset(self._keyframe)
        except Exception as error:
            return ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.WORLD_INCONSISTENCY, "WORLD_RESET_FAILED", str(error)),
            )
        return ActionResult(ActionStatus.SUCCEEDED)


class RecoveryCoordinator:
    def __init__(self, actions: Mapping[State, Callable[[], ActionResult]]) -> None:
        self.actions = actions

    def execute(self, path: tuple[State, ...]) -> ActionResult:
        for state in path:
            result = self.actions[state]()
            if result.status is not ActionStatus.SUCCEEDED:
                return result
        return ActionResult(ActionStatus.SUCCEEDED)
