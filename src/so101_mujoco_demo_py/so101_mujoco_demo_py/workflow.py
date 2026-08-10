"""Validated transition definition for the SO-101 pick-place workflow."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .domain import ActionStatus, State


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    transitions: Mapping[State, tuple[State, State]]
    action_states: frozenset[State]
    forward_states: tuple[State, ...]
    terminal_states: frozenset[State]
    force_continue_states: frozenset[State]
    plan_only_states: frozenset[State]


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


SO101_WORKFLOW = WorkflowDefinition(
    transitions=MappingProxyType(_TRANSITIONS),
    action_states=_ACTION_STATES,
    forward_states=_FORWARD_STATES,
    terminal_states=_TERMINAL_STATES,
    force_continue_states=frozenset({State.VALIDATION_FAILED}),
    plan_only_states=_PLAN_ONLY_STATES,
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


def resolve_transition(state: State, outcome: ActionStatus) -> State:
    """Return the success destination only for an explicit success outcome."""
    return SO101_WORKFLOW.transitions[state][outcome is not ActionStatus.SUCCEEDED]
