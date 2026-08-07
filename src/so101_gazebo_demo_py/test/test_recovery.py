from so101_gazebo_demo_py.checkpoint import ExpectedWorldState
from so101_gazebo_demo_py.domain import State
from so101_gazebo_demo_py.recovery.policy import RecoveryPolicy


def test_recovery_skips_unobserved_side_effects() -> None:
    state=ExpectedWorldState(gazebo_task_object_attached=False, moveit_task_object_attached=False)
    assert RecoveryPolicy().path_for(State.LIFT, state) == (State.RECOVER_RETREAT,)


def test_recovery_reverses_observed_scene_then_gazebo_attachment() -> None:
    state=ExpectedWorldState(gazebo_task_object_attached=True, moveit_task_object_attached=True)
    path=RecoveryPolicy().path_for(State.LIFT, state)
    assert path.index(State.RECOVER_DETACH_GAZEBO) < path.index(State.RECOVER_DETACH_MOVEIT)
    assert path[-1] is State.RECOVER_RETREAT
