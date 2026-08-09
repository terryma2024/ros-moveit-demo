from so101_gazebo_demo_py.domain import ActionStatus, State
from so101_gazebo_demo_py.workflow import SO101_WORKFLOW, resolve_transition


EXPECTED_TRANSITIONS = {
    State.IDLE: (State.PREPARE_OPEN_GRIPPER, State.ERROR),
    State.PREPARE_OPEN_GRIPPER: (State.MOVE_ABOVE_OBJECT, State.ERROR),
    State.MOVE_ABOVE_OBJECT: (State.DESCEND, State.RECOVER_RETREAT),
    State.DESCEND: (State.CLOSE_GRIPPER, State.RECOVER_OPEN_GRIPPER),
    State.CLOSE_GRIPPER: (State.WAIT_GRASP_STABLE, State.RECOVER_OPEN_GRIPPER),
    State.WAIT_GRASP_STABLE: (State.MICRO_LIFT, State.RECOVER_OPEN_GRIPPER),
    State.MICRO_LIFT: (State.WAIT_MICRO_LIFT_STABLE, State.RECOVER_OPEN_GRIPPER),
    State.WAIT_MICRO_LIFT_STABLE: (State.VERIFY_PHYSICAL_GRASP, State.RECOVER_OPEN_GRIPPER),
    State.VERIFY_PHYSICAL_GRASP: (State.ATTACH_MOVEIT, State.VALIDATION_FAILED),
    State.VALIDATION_FAILED: (State.ATTACH_MOVEIT, State.VALIDATION_FAILED),
    State.ATTACH_MOVEIT: (State.LIFT, State.RECOVER_OPEN_GRIPPER),
    State.LIFT: (State.MOVE_ABOVE_PLACE, State.RECOVER_LIFT_TO_SAFE_HEIGHT),
    State.MOVE_ABOVE_PLACE: (State.DESCEND_TO_PLACE, State.RECOVER_LIFT_TO_SAFE_HEIGHT),
    State.DESCEND_TO_PLACE: (State.DETACH_MOVEIT, State.RECOVER_LIFT_TO_SAFE_HEIGHT),
    State.DETACH_MOVEIT: (State.OPEN_GRIPPER, State.RECOVER_DETACH_MOVEIT),
    State.OPEN_GRIPPER: (State.WAIT_RELEASE_SETTLE, State.RECOVER_LIFT_TO_SAFE_HEIGHT),
    State.WAIT_RELEASE_SETTLE: (
        State.VALIDATE_FINAL_PLACEMENT, State.RECOVER_LIFT_TO_SAFE_HEIGHT,
    ),
    State.VALIDATE_FINAL_PLACEMENT: (
        State.SYNC_WORLD_OBJECT, State.RECOVER_LIFT_TO_SAFE_HEIGHT,
    ),
    State.SYNC_WORLD_OBJECT: (State.RETREAT, State.RECOVER_SYNC_WORLD_OBJECT),
    State.RETREAT: (State.DONE, State.RECOVER_RETREAT),
    State.RECOVER_LIFT_TO_SAFE_HEIGHT: (State.RECOVER_MOVE_ABOVE_PICK, State.ERROR),
    State.RECOVER_MOVE_ABOVE_PICK: (State.RECOVER_DESCEND_TO_PICK, State.ERROR),
    State.RECOVER_DESCEND_TO_PICK: (State.RECOVER_OPEN_GRIPPER, State.ERROR),
    State.RECOVER_OPEN_GRIPPER: (State.RECOVER_DETACH_GAZEBO, State.ERROR),
    State.RECOVER_DETACH_GAZEBO: (State.RECOVER_DETACH_MOVEIT, State.ERROR),
    State.RECOVER_DETACH_MOVEIT: (State.RECOVER_SYNC_WORLD_OBJECT, State.ERROR),
    State.RECOVER_SYNC_WORLD_OBJECT: (State.RECOVER_RETREAT, State.ERROR),
    State.RECOVER_RETREAT: (State.ERROR, State.ERROR),
}


def test_workflow_matches_reference_transition_table() -> None:
    assert SO101_WORKFLOW.transitions == EXPECTED_TRANSITIONS
    assert SO101_WORKFLOW.terminal_states == frozenset({State.DONE, State.ERROR})
    assert SO101_WORKFLOW.force_continue_states == frozenset({State.VALIDATION_FAILED})
    assert SO101_WORKFLOW.plan_only_states == frozenset({
        State.MOVE_ABOVE_OBJECT, State.DESCEND, State.LIFT,
        State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE, State.RETREAT,
    })


def test_physical_grasp_precedes_attachment() -> None:
    assert resolve_transition(State.WAIT_GRASP_STABLE, ActionStatus.SUCCEEDED) is State.MICRO_LIFT
    assert resolve_transition(State.MICRO_LIFT, ActionStatus.SUCCEEDED) is State.WAIT_MICRO_LIFT_STABLE
    assert resolve_transition(State.WAIT_MICRO_LIFT_STABLE, ActionStatus.SUCCEEDED) is State.VERIFY_PHYSICAL_GRASP
    assert resolve_transition(State.VERIFY_PHYSICAL_GRASP, ActionStatus.SUCCEEDED) is State.ATTACH_MOVEIT


def test_forward_workflow_uses_physics_only_and_detaches_shadow_before_release() -> None:
    assert "ATTACH_GAZEBO" not in {state.value for state in SO101_WORKFLOW.forward_states}
    assert "DETACH_GAZEBO" not in {state.value for state in SO101_WORKFLOW.forward_states}
    assert SO101_WORKFLOW.forward_states.index(State.DETACH_MOVEIT) < (
        SO101_WORKFLOW.forward_states.index(State.OPEN_GRIPPER)
    )
    assert resolve_transition(State.OPEN_GRIPPER, ActionStatus.SUCCEEDED) is (
        State.WAIT_RELEASE_SETTLE
    )


def test_non_success_action_status_uses_failure_transition() -> None:
    for status in (ActionStatus.FAILED, ActionStatus.CANCELLED, ActionStatus.TIMED_OUT, ActionStatus.NOT_SUPPORTED):
        assert resolve_transition(State.DESCEND, status) is State.RECOVER_OPEN_GRIPPER
