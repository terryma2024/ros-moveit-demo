"""`TEACHER_WORKFLOW` - the same forward states and success trace as the general workflow, no recovery chain, every failure to ERROR."""

import pytest

from so101_demo.application.dynamic_execute import build_dynamic_actions
from so101_demo.application.e2e_acceptance import SUCCESS_STATE_TRACE
from so101_demo.core.domain import ActionStatus, Failure, FailureCategory, State
from so101_demo.core.runner import StateMachineRunner, SuccessfulAction
from so101_demo.core.domain import RunMode, RunRequest
from so101_demo.core.workflow import (
    SIM_INTEGRITY_CODES, SO101_WORKFLOW, TEACHER_WORKFLOW, TERMINAL_STOP_CODES, TERMINAL_STOP_CODES_TEACHER, resolve_transition)


def test_the_teacher_forward_states_are_the_general_success_trace():
    trace = [State.IDLE]
    while trace[-1] is not State.DONE:
        trace.append(TEACHER_WORKFLOW.transitions[trace[-1]][0])
    assert tuple(state.value for state in trace) == SUCCESS_STATE_TRACE
    assert TEACHER_WORKFLOW.forward_states == tuple(state for state in SO101_WORKFLOW.forward_states if state is not State.VALIDATION_FAILED)


def test_the_teacher_workflow_has_no_recovery_and_no_validation_failed_state():
    states = set(TEACHER_WORKFLOW.transitions)
    assert not any(state.name.startswith("RECOVER_") for state in states) and State.VALIDATION_FAILED not in states
    assert State.VALIDATION_FAILED not in TEACHER_WORKFLOW.action_states and not TEACHER_WORKFLOW.force_continue_states
    for state, (success, failure) in TEACHER_WORKFLOW.transitions.items():
        assert failure is State.ERROR, state
        assert not success.name.startswith("RECOVER_") and success is not State.VALIDATION_FAILED, state


def test_the_pass_through_states_have_no_failing_branch_to_validation_failed():
    # general: a failed VERIFY_PHYSICAL_GRASP continues through VALIDATION_FAILED; Teacher: it is a pass-through whose failure is an error
    assert SO101_WORKFLOW.transitions[State.VERIFY_PHYSICAL_GRASP][1] is State.VALIDATION_FAILED
    assert TEACHER_WORKFLOW.transitions[State.VERIFY_PHYSICAL_GRASP] == (State.ATTACH_MOVEIT, State.ERROR)
    assert TEACHER_WORKFLOW.transitions[State.VALIDATE_FINAL_PLACEMENT] == (State.SYNC_WORLD_OBJECT, State.ERROR)


@pytest.mark.parametrize("state", sorted(TEACHER_WORKFLOW.action_states, key=lambda item: item.value))
@pytest.mark.parametrize("code", ["MOVEIT_EXECUTION_FAILED", "GRIPPER_RESULT_TIMEOUT", "TEACHER_USER_STOP", "SIM_INTEGRITY_SESSION_MISMATCH",
                                  "DYNAMIC_DETACH_SYNC_FAILED", "TEACHER_ARM_NOT_STOPPED", "SOMETHING_ELSE"])
def test_every_failure_of_every_state_goes_straight_to_error(state, code):
    failure = Failure(FailureCategory.EXECUTION, code, "x")
    assert resolve_transition(state, ActionStatus.FAILED, failure, workflow=TEACHER_WORKFLOW) is State.ERROR
    assert resolve_transition(state, ActionStatus.FAILED, None, workflow=TEACHER_WORKFLOW) is State.ERROR
    assert resolve_transition(state, ActionStatus.SUCCEEDED, workflow=TEACHER_WORKFLOW) is TEACHER_WORKFLOW.transitions[state][0]


def test_the_teacher_stop_code_set_is_only_operator_joint_state_and_simulation_integrity():
    assert TERMINAL_STOP_CODES_TEACHER == {
        "TEACHER_DEADLINE", "TEACHER_USER_STOP", "TEACHER_PARENT_DIED", "TEACHER_CANCEL_UNSETTLED", "TEACHER_JOINT_STATE_UNAVAILABLE",
        *SIM_INTEGRITY_CODES}
    assert SIM_INTEGRITY_CODES == {"SIM_INTEGRITY_SESSION_MISMATCH", "SIM_INTEGRITY_RESET_EPOCH_MISMATCH",
                                   "SIM_INTEGRITY_NON_FINITE_STATE", "SIM_INTEGRITY_EVIDENCE_UNAVAILABLE"}
    removed = {"DYNAMIC_CUP_FORCE_EXCEEDED", "DYNAMIC_CUP_COMPRESSION_EXCEEDED", "DYNAMIC_COLLISION_STOP", "DYNAMIC_PHYSICS_HAZARD",
               "DYNAMIC_FORCE_LIMIT_EXCEEDED", "DYNAMIC_RELEASE_SUPPORT_NOT_PROVED", "DYNAMIC_STATE_UNAVAILABLE_STOP",
               "TEACHER_PLACE_TILT_UNSTABLE", "TEACHER_PLACE_TILT_OUT_OF_RANGE", "TEACHER_PLACE_HEIGHT_OUT_OF_BOUNDS",
               "TEACHER_PLACE_MEASUREMENT_FAILED"}
    assert not removed & TERMINAL_STOP_CODES_TEACHER and removed <= TERMINAL_STOP_CODES


def test_the_general_workflow_keeps_its_recovery_chain_and_stop_codes():
    assert SO101_WORKFLOW.terminal_stop_codes is TERMINAL_STOP_CODES
    assert resolve_transition(State.DESCEND_TO_PLACE, ActionStatus.FAILED, Failure(FailureCategory.EXECUTION, "DYNAMIC_CUP_FORCE_EXCEEDED", "x")) \
        is State.ERROR
    assert resolve_transition(State.DESCEND_TO_PLACE, ActionStatus.FAILED, Failure(FailureCategory.EXECUTION, "MOVEIT_EXECUTION_FAILED", "x")) \
        is State.RECOVER_LIFT_TO_SAFE_HEIGHT
    assert State.RECOVER_RETREAT in SO101_WORKFLOW.transitions and State.VALIDATION_FAILED in SO101_WORKFLOW.transitions


def test_the_runner_walks_the_teacher_workflow_to_done_and_a_failure_ends_in_error_without_recovery():
    class Fails:
        def __init__(self, at):
            self.at = at

        def run(self, context):
            if context.state is self.at:
                return Failing
            return SuccessfulAction().run(context)

    from so101_demo.core.domain import ActionResult
    Failing = ActionResult(ActionStatus.FAILED, Failure(FailureCategory.EXECUTION, "MOVEIT_EXECUTION_FAILED", "x"))
    actions = {state: SuccessfulAction() for state in TEACHER_WORKFLOW.action_states}
    done = StateMachineRunner(actions, workflow=TEACHER_WORKFLOW).run(RunRequest(mode=RunMode.DRY_RUN))
    assert [state.value for state in done.state_trace] == list(SUCCESS_STATE_TRACE)
    for at in (State.MOVE_ABOVE_OBJECT, State.DESCEND_TO_PLACE, State.OPEN_GRIPPER, State.WAIT_RELEASE_SETTLE):
        broken = dict(actions)
        broken[at] = Fails(at)
        result = StateMachineRunner(broken, workflow=TEACHER_WORKFLOW).run(RunRequest(mode=RunMode.DRY_RUN))
        assert result.state_trace[-2:] == (at, State.ERROR), at
        assert not any(state.name.startswith("RECOVER_") for state in result.state_trace)


def test_build_dynamic_actions_binds_the_chosen_workflow():
    assert set(build_dynamic_actions(object(), object(), TEACHER_WORKFLOW)) == set(TEACHER_WORKFLOW.action_states)
    assert State.RECOVER_RETREAT in build_dynamic_actions(object(), object())
    assert State.RECOVER_RETREAT not in build_dynamic_actions(object(), object(), TEACHER_WORKFLOW)
