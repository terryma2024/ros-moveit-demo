from dataclasses import dataclass

from so101_gazebo_demo_py.domain import (
    ActionResult, ActionStatus, Failure, FailureCategory, RunMode, RunRequest, RunStatus, State,
)
from so101_gazebo_demo_py.runner import ExecutionContext, StateMachineRunner
from so101_gazebo_demo_py.workflow import SO101_WORKFLOW


@dataclass
class Action:
    state: State
    calls: int = 0

    def run(self, context: ExecutionContext) -> ActionResult:
        self.calls += 1
        if context.request.fail_at is self.state:
            return ActionResult(ActionStatus.FAILED, Failure(FailureCategory.INTERNAL, "INJECTED_FAILURE"))
        return ActionResult(ActionStatus.SUCCEEDED)


def runner() -> tuple[StateMachineRunner, dict[State, Action]]:
    actions = {state: Action(state) for state in SO101_WORKFLOW.action_states}
    return StateMachineRunner(actions), actions


def test_full_dry_run_reaches_done_in_reference_order() -> None:
    machine, actions = runner()
    result = machine.run(RunRequest())
    assert result.status is RunStatus.DONE
    assert result.current_state is State.DONE
    assert result.transition_count == 19
    assert result.state_trace == (
        State.IDLE, State.PREPARE_OPEN_GRIPPER, State.MOVE_ABOVE_OBJECT,
        State.DESCEND, State.CLOSE_GRIPPER, State.WAIT_GRASP_STABLE,
        State.MICRO_LIFT, State.WAIT_MICRO_LIFT_STABLE,
        State.VERIFY_PHYSICAL_GRASP, State.ATTACH_MOVEIT,
        State.LIFT, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE,
        State.DETACH_MOVEIT, State.OPEN_GRIPPER, State.WAIT_RELEASE_SETTLE,
        State.VALIDATE_FINAL_PLACEMENT,
        State.SYNC_WORLD_OBJECT, State.RETREAT, State.DONE,
    )
    assert all(action.calls == 1 for state, action in actions.items() if state in result.state_trace)


def test_stop_after_and_single_step_are_successful_checkpoint_boundaries() -> None:
    machine, _ = runner()
    stopped = machine.run(RunRequest(stop_after=State.DESCEND))
    assert (stopped.status, stopped.current_state, stopped.next_state) == (
        RunStatus.CHECKPOINT_COMPLETE, State.DESCEND, State.CLOSE_GRIPPER
    )
    stepped = machine.run(RunRequest(single_step=True))
    assert (stepped.status, stepped.current_state, stepped.next_state) == (
        RunStatus.CHECKPOINT_COMPLETE, State.PREPARE_OPEN_GRIPPER, State.MOVE_ABOVE_OBJECT
    )


def test_plan_only_rejects_unsupported_state_and_runs_one_supported_action() -> None:
    machine, actions = runner()
    bad = machine.run(RunRequest(mode=RunMode.PLAN_ONLY, plan_only_state=State.CLOSE_GRIPPER))
    assert bad.failure.code == "PLAN_ONLY_STATE_UNSUPPORTED"
    good = machine.run(RunRequest(mode=RunMode.PLAN_ONLY, plan_only_state=State.LIFT))
    assert good.status is RunStatus.PLAN_ONLY_COMPLETE
    assert actions[State.LIFT].calls == 1


def test_force_continue_is_rejected_outside_validation_failed() -> None:
    machine, _ = runner()
    result = machine.run(RunRequest(force_continue=True))
    assert result.status is RunStatus.ERROR
    assert result.failure.code == "FORCE_CONTINUE_NOT_ALLOWED"


def test_validation_failure_pauses_without_overwriting_physical_failure() -> None:
    machine, _ = runner()
    result = machine.run(RunRequest(fail_at=State.VERIFY_PHYSICAL_GRASP))
    assert result.status is RunStatus.CHECKPOINT_COMPLETE
    assert result.current_state is State.VALIDATION_FAILED
    assert result.next_state is State.ATTACH_MOVEIT
    assert result.failure.code == "INJECTED_FAILURE"


def test_transition_limit_fails_closed() -> None:
    machine, _ = runner()
    result = machine.run(RunRequest(max_state_transitions=2))
    assert result.failure.code == "MAX_STATE_TRANSITIONS_EXCEEDED"
