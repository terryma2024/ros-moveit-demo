from dataclasses import FrozenInstanceError

import pytest

from so101_gazebo_demo_py.domain import (
    ActionResult,
    ActionStatus,
    Failure,
    FailureCategory,
    RunMode,
    RunRequest,
    RunResult,
    RunStatus,
    State,
)


EXPECTED_STATES = (
    "IDLE", "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "DESCEND",
    "CLOSE_GRIPPER", "WAIT_GRASP_STABLE", "MICRO_LIFT",
    "WAIT_MICRO_LIFT_STABLE", "VERIFY_PHYSICAL_GRASP", "VALIDATION_FAILED",
    "ATTACH_GAZEBO", "ATTACH_MOVEIT", "LIFT", "MOVE_ABOVE_PLACE",
    "DESCEND_TO_PLACE", "OPEN_GRIPPER", "DETACH_GAZEBO", "DETACH_MOVEIT",
    "SYNC_WORLD_OBJECT", "RETREAT", "RECOVER_LIFT_TO_SAFE_HEIGHT",
    "RECOVER_MOVE_ABOVE_PICK", "RECOVER_DESCEND_TO_PICK",
    "RECOVER_OPEN_GRIPPER", "RECOVER_DETACH_GAZEBO",
    "RECOVER_DETACH_MOVEIT", "RECOVER_SYNC_WORLD_OBJECT", "RECOVER_RETREAT",
    "DONE", "ERROR",
)


def test_domain_enums_preserve_external_strings() -> None:
    assert tuple(state.value for state in State) == EXPECTED_STATES
    assert tuple(mode.value for mode in RunMode) == ("dry_run", "plan_only", "execute")
    assert tuple(status.value for status in RunStatus) == (
        "RUNNING", "PLAN_ONLY_COMPLETE", "CHECKPOINT_COMPLETE", "DONE", "ERROR"
    )
    assert ActionStatus.TIMED_OUT.value == "TIMED_OUT"
    assert FailureCategory.GAZEBO_ATTACHMENT.value == "GAZEBO_ATTACHMENT"


def test_domain_records_are_frozen_and_use_immutable_trace() -> None:
    failure = Failure(FailureCategory.INTERNAL, "BROKEN", "failure", {"x": 1.0})
    result = RunResult(RunStatus.ERROR, State.ERROR, None, failure, 1, (State.IDLE, State.ERROR))
    assert isinstance(result.state_trace, tuple)
    with pytest.raises(FrozenInstanceError):
        result.status = RunStatus.DONE
    assert ActionResult(ActionStatus.FAILED, failure).failure is failure
    assert RunRequest().max_state_transitions == 100
