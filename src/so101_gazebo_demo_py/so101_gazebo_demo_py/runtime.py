"""Explicit workflow-state ownership for the composed runtime."""

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .domain import ActionResult, ActionStatus, RunMode, State
from .runner import ExecutionContext, StateAction, SuccessfulAction
from .workflow import SO101_WORKFLOW


@dataclass(slots=True)
class CallableAction:
    callback: Callable[[ExecutionContext], ActionResult]
    def run(self, context: ExecutionContext) -> ActionResult: return self.callback(context)


@dataclass(frozen=True, slots=True)
class RuntimeDependencies:
    readiness: Callable[[], ActionResult]
    plan: Callable[[State], ActionResult]
    execute: Callable[[State], ActionResult]
    gripper: Callable[[State], ActionResult]
    stabilize: Callable[[State], ActionResult]
    verify_grasp: Callable[[], ActionResult]
    gazebo_attachment: Callable[[bool], ActionResult]
    moveit_attachment: Callable[[bool], ActionResult]
    sync_world: Callable[[], ActionResult]
    recovery: Callable[[State], ActionResult]


class Runtime:
    def __init__(self, actions: Mapping[State, StateAction]) -> None: self.actions=dict(actions)


MOTION_STATES = frozenset(SO101_WORKFLOW.plan_only_states) | frozenset({
    State.MICRO_LIFT, State.RECOVER_LIFT_TO_SAFE_HEIGHT, State.RECOVER_MOVE_ABOVE_PICK,
    State.RECOVER_DESCEND_TO_PICK, State.RECOVER_RETREAT,
})
GRIPPER_STATES = frozenset({State.PREPARE_OPEN_GRIPPER,State.CLOSE_GRIPPER,State.OPEN_GRIPPER,State.RECOVER_OPEN_GRIPPER})


def build_runtime(node: Any, profile: Any, policies: Any, options: Any,
                  dependencies: RuntimeDependencies | None = None) -> Runtime:
    del node, profile, policies
    if dependencies is None:
        return Runtime({state: SuccessfulAction() for state in SO101_WORKFLOW.action_states})
    actions: dict[State,StateAction]={}
    ready=False
    def motion(context: ExecutionContext) -> ActionResult:
        nonlocal ready
        if context.request.mode is RunMode.EXECUTE and not ready:
            result=dependencies.readiness()
            if result.status is not ActionStatus.SUCCEEDED: return result
            ready=True
        result=dependencies.plan(context.state)
        if result.status is not ActionStatus.SUCCEEDED or context.request.mode is RunMode.PLAN_ONLY: return result
        return dependencies.execute(context.state)
    for state in MOTION_STATES: actions[state]=CallableAction(motion)
    for state in GRIPPER_STATES: actions[state]=CallableAction(lambda context, s=state: dependencies.gripper(s))
    for state in (State.WAIT_GRASP_STABLE,State.WAIT_MICRO_LIFT_STABLE): actions[state]=CallableAction(lambda context,s=state: dependencies.stabilize(s))
    actions[State.VERIFY_PHYSICAL_GRASP]=CallableAction(lambda context: dependencies.verify_grasp())
    actions[State.ATTACH_GAZEBO]=CallableAction(lambda context: dependencies.gazebo_attachment(True))
    actions[State.DETACH_GAZEBO]=CallableAction(lambda context: dependencies.gazebo_attachment(False))
    actions[State.ATTACH_MOVEIT]=CallableAction(lambda context: dependencies.moveit_attachment(True))
    actions[State.DETACH_MOVEIT]=CallableAction(lambda context: dependencies.moveit_attachment(False))
    actions[State.SYNC_WORLD_OBJECT]=CallableAction(lambda context: dependencies.sync_world())
    for state in SO101_WORKFLOW.action_states-actions.keys():
        actions[state]=CallableAction(lambda context,s=state: dependencies.recovery(s))
    return Runtime(actions)
