"""Evidence-driven recovery path selection."""

from ..checkpoint import ExpectedWorldState
from ..domain import State


class RecoveryPolicy:
    def path_for(self, failed_state: State, evidence: ExpectedWorldState) -> tuple[State,...]:
        del failed_state
        if (
            evidence.gripper_task_object_contact is True
            and evidence.task_object_supported is not True
        ):
            return ()
        path=[]
        if evidence.gazebo_task_object_attached:
            path.extend((State.RECOVER_LIFT_TO_SAFE_HEIGHT, State.RECOVER_DETACH_GAZEBO))
        if evidence.moveit_task_object_attached:
            path.append(State.RECOVER_DETACH_MOVEIT)
        if evidence.gazebo_task_object_attached or evidence.moveit_task_object_attached:
            path.append(State.RECOVER_SYNC_WORLD_OBJECT)
        path.append(State.RECOVER_RETREAT)
        return tuple(path)
