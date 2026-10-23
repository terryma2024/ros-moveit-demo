"""Validated transition definition for the SO-101 pick-place workflow."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .domain import ActionStatus, Failure, State


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    transitions: Mapping[State, tuple[State, State]]
    action_states: frozenset[State]
    forward_states: tuple[State, ...]
    terminal_states: frozenset[State]
    force_continue_states: frozenset[State]
    plan_only_states: frozenset[State]
    #: failure codes that go straight to ERROR from any state (general workflow: `TERMINAL_STOP_CODES`; Teacher workflow: `TERMINAL_STOP_CODES_TEACHER`)
    terminal_stop_codes: frozenset[str] = frozenset()


_TRANSITIONS = {
    State.IDLE: (State.PREPARE_OPEN_GRIPPER, State.ERROR),
    State.PREPARE_OPEN_GRIPPER: (State.MOVE_ABOVE_OBJECT, State.ERROR),
    State.MOVE_ABOVE_OBJECT: (State.DESCEND, State.RECOVER_RETREAT),
    State.DESCEND: (State.CLOSE_GRIPPER, State.RECOVER_OPEN_GRIPPER),
    State.CLOSE_GRIPPER: (State.WAIT_GRASP_STABLE, State.RECOVER_OPEN_GRIPPER),
    State.WAIT_GRASP_STABLE: (State.MICRO_LIFT, State.RECOVER_OPEN_GRIPPER),
    State.MICRO_LIFT: (State.WAIT_MICRO_LIFT_STABLE, State.RECOVER_OPEN_GRIPPER),
    State.WAIT_MICRO_LIFT_STABLE: (
        State.VERIFY_PHYSICAL_GRASP,
        State.RECOVER_OPEN_GRIPPER,
    ),
    State.VERIFY_PHYSICAL_GRASP: (State.ATTACH_MOVEIT, State.VALIDATION_FAILED),
    State.VALIDATION_FAILED: (State.ATTACH_MOVEIT, State.VALIDATION_FAILED),
    State.ATTACH_MOVEIT: (State.LIFT, State.RECOVER_OPEN_GRIPPER),
    State.LIFT: (State.MOVE_ABOVE_PLACE, State.RECOVER_LIFT_TO_SAFE_HEIGHT),
    State.MOVE_ABOVE_PLACE: (
        State.DESCEND_TO_PLACE,
        State.RECOVER_LIFT_TO_SAFE_HEIGHT,
    ),
    State.DESCEND_TO_PLACE: (
        State.DETACH_MOVEIT,
        State.RECOVER_LIFT_TO_SAFE_HEIGHT,
    ),
    State.DETACH_MOVEIT: (State.OPEN_GRIPPER, State.RECOVER_DETACH_MOVEIT),
    State.OPEN_GRIPPER: (State.WAIT_RELEASE_SETTLE, State.RECOVER_LIFT_TO_SAFE_HEIGHT),
    State.WAIT_RELEASE_SETTLE: (
        State.VALIDATE_FINAL_PLACEMENT,
        State.RECOVER_LIFT_TO_SAFE_HEIGHT,
    ),
    State.VALIDATE_FINAL_PLACEMENT: (
        State.SYNC_WORLD_OBJECT,
        State.RECOVER_LIFT_TO_SAFE_HEIGHT,
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
_FORWARD_STATES = (
    State.IDLE,
    State.PREPARE_OPEN_GRIPPER,
    State.MOVE_ABOVE_OBJECT,
    State.DESCEND,
    State.CLOSE_GRIPPER,
    State.WAIT_GRASP_STABLE,
    State.MICRO_LIFT,
    State.WAIT_MICRO_LIFT_STABLE,
    State.VERIFY_PHYSICAL_GRASP,
    State.VALIDATION_FAILED,
    State.ATTACH_MOVEIT,
    State.LIFT,
    State.MOVE_ABOVE_PLACE,
    State.DESCEND_TO_PLACE,
    State.DETACH_MOVEIT,
    State.OPEN_GRIPPER,
    State.WAIT_RELEASE_SETTLE,
    State.VALIDATE_FINAL_PLACEMENT,
    State.SYNC_WORLD_OBJECT,
    State.RETREAT,
)
_TERMINAL_STATES = frozenset({State.DONE, State.ERROR})
_ACTION_STATES = frozenset(_TRANSITIONS) - {State.IDLE, State.VALIDATION_FAILED}
_PLAN_ONLY_STATES = frozenset(
    {
        State.MOVE_ABOVE_OBJECT,
        State.DESCEND,
        State.LIFT,
        State.MOVE_ABOVE_PLACE,
        State.DESCEND_TO_PLACE,
        State.RETREAT,
    }
)


# A failure with one of these codes is a protective stop, a deadline, a user stop or a cancel that never settled. It
# ends the run: the failure destination is ERROR and no recovery goal (lift, move, open the gripper) is ever sent.
# Only the other failures (a controller reject or abort, planning, scene) may take the original RECOVER_* route.
TERMINAL_STOP_CODES = frozenset({
    "DYNAMIC_FORCE_LIMIT_EXCEEDED",
    "DYNAMIC_CUP_FORCE_EXCEEDED",
    "DYNAMIC_CUP_COMPRESSION_EXCEEDED",
    "DYNAMIC_COLLISION_STOP",
    "DYNAMIC_PHYSICS_HAZARD",
    "DYNAMIC_STATE_UNAVAILABLE_STOP",
    "DYNAMIC_SESSION_MISMATCH",
    "DYNAMIC_RESET_EPOCH_MISMATCH",
    "DYNAMIC_RELEASE_SUPPORT_NOT_PROVED",
    # the tilt-compensated place height refused before any DESCEND_TO_PLACE motion: the cup stays held, nothing is released
    "TEACHER_PLACE_TILT_UNSTABLE",
    "TEACHER_PLACE_TILT_OUT_OF_RANGE",
    "TEACHER_PLACE_HEIGHT_OUT_OF_BOUNDS",
    "TEACHER_PLACE_MEASUREMENT_FAILED",
    "TEACHER_DEADLINE",
    "TEACHER_USER_STOP",
    "TEACHER_PARENT_DIED",
    "TEACHER_CANCEL_UNSETTLED",
})


SO101_WORKFLOW = WorkflowDefinition(
    transitions=MappingProxyType(_TRANSITIONS),
    action_states=_ACTION_STATES,
    forward_states=_FORWARD_STATES,
    terminal_states=_TERMINAL_STATES,
    force_continue_states=frozenset({State.VALIDATION_FAILED}),
    plan_only_states=_PLAN_ONLY_STATES,
    terminal_stop_codes=TERMINAL_STOP_CODES,
)


def _validate(definition: WorkflowDefinition) -> None:
    if set(definition.transitions) != set(State) - definition.terminal_states:
        raise ValueError("every nonterminal state must have a transition")
    if any(len(destinations) != 2 for destinations in definition.transitions.values()):
        raise ValueError("every transition must have success and failure destinations")
    if any(
        destination not in State for pair in definition.transitions.values() for destination in pair
    ):
        raise ValueError("transition destination is unknown")
    if State.VALIDATION_FAILED in definition.action_states:
        raise ValueError("VALIDATION_FAILED cannot own an action")
    if not definition.plan_only_states <= definition.action_states:
        raise ValueError("plan-only states must own actions")


_validate(SO101_WORKFLOW)

# ---- Teacher workflow (Teacher execution policy, design 2026-10-10-so101-teacher-minimal-runtime-gates) -------------------------
# The same forward states in the same order, so the success trace is identical to the general workflow, but: no RECOVER_* state and no
# VALIDATION_FAILED (VERIFY_PHYSICAL_GRASP and VALIDATE_FINAL_PLACEMENT are record-only pass-throughs), and every failure of
# every state goes straight to ERROR.
_TEACHER_FORWARD = tuple(state for state in _FORWARD_STATES if state is not State.VALIDATION_FAILED)
_TRANSITIONS_TEACHER = {
    state: (following, State.ERROR)
    for state, following in zip(_TEACHER_FORWARD, (*_TEACHER_FORWARD[1:], State.DONE))
}

#: the only codes that are terminal stops in the Teacher workflow: the operator and watchdog, the unavailable joint state (the arm cannot be
#: commanded blind) and the simulation-integrity codes. Every other failure is non-terminal and also goes to ERROR.
SIM_INTEGRITY_CODES = frozenset({
    "SIM_INTEGRITY_SESSION_MISMATCH",
    "SIM_INTEGRITY_RESET_EPOCH_MISMATCH",
    "SIM_INTEGRITY_NON_FINITE_STATE",
    "SIM_INTEGRITY_EVIDENCE_UNAVAILABLE",
})
TERMINAL_STOP_CODES_TEACHER = frozenset({
    "TEACHER_DEADLINE",
    "TEACHER_USER_STOP",
    "TEACHER_PARENT_DIED",
    "TEACHER_CANCEL_UNSETTLED",
    "TEACHER_JOINT_STATE_UNAVAILABLE",
}) | SIM_INTEGRITY_CODES

TEACHER_WORKFLOW = WorkflowDefinition(
    transitions=MappingProxyType(_TRANSITIONS_TEACHER),
    action_states=frozenset(_TRANSITIONS_TEACHER) - {State.IDLE},
    forward_states=_TEACHER_FORWARD,
    terminal_states=_TERMINAL_STATES,
    force_continue_states=frozenset(),
    plan_only_states=_PLAN_ONLY_STATES,
    terminal_stop_codes=TERMINAL_STOP_CODES_TEACHER,
)


def _validate_teacher(definition: WorkflowDefinition) -> None:
    states = set(definition.transitions)
    if states != set(definition.forward_states):
        raise ValueError("every forward state must have a transition and no other state may")
    if any(state.name.startswith("RECOVER_") or state is State.VALIDATION_FAILED for state in states):
        raise ValueError("the Teacher workflow has no recovery or validation-failed state")
    for state, (success, failure) in definition.transitions.items():
        if failure is not State.ERROR or (success not in states and success is not State.DONE):
            raise ValueError("Teacher workflow transitions must go forward or to ERROR")
    if not definition.plan_only_states <= definition.action_states or State.IDLE in definition.action_states:
        raise ValueError("plan-only states must own actions")


_validate_teacher(TEACHER_WORKFLOW)


def resolve_transition(
    state: State, outcome: ActionStatus, failure: Failure | None = None, *, workflow: WorkflowDefinition = SO101_WORKFLOW
) -> State:
    """Return the success destination only for an explicit success outcome.

    A terminal stop failure (the workflow's `terminal_stop_codes`) goes straight to ERROR from any state.
    """
    if (
        outcome is not ActionStatus.SUCCEEDED
        and failure is not None
        and failure.code in workflow.terminal_stop_codes
    ):
        return State.ERROR
    return workflow.transitions[state][outcome is not ActionStatus.SUCCEEDED]
