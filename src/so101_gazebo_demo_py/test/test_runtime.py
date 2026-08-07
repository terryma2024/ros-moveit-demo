from so101_gazebo_demo_py.domain import ActionResult, ActionStatus, RunMode, RunRequest, State
from so101_gazebo_demo_py.runner import ExecutionContext
from so101_gazebo_demo_py.runtime import RuntimeDependencies, build_runtime


def dependencies(calls):
    ok=lambda: ActionResult(ActionStatus.SUCCEEDED)
    return RuntimeDependencies(
        lambda: calls.append("ready") or ok(),
        lambda state: calls.append(("plan",state)) or ok(),
        lambda state: calls.append(("execute",state)) or ok(),
        lambda state: calls.append(("gripper",state)) or ok(),
        lambda state: calls.append(("stable",state)) or ok(),
        lambda: calls.append("verify") or ok(),
        lambda attached: calls.append(("gazebo",attached)) or ok(),
        lambda attached: calls.append(("moveit",attached)) or ok(),
        lambda: calls.append("sync") or ok(),
        lambda state: calls.append(("recovery",state)) or ok(),
    )


def run(action,state,mode): return action.run(ExecutionContext(RunRequest(mode=mode,plan_only_state=state),state,0))


def test_plan_only_plans_without_readiness_or_execution() -> None:
    calls=[]; runtime=build_runtime(None,None,None,None,dependencies(calls))
    run(runtime.actions[State.MOVE_ABOVE_OBJECT],State.MOVE_ABOVE_OBJECT,RunMode.PLAN_ONLY)
    assert calls == [("plan",State.MOVE_ABOVE_OBJECT)]


def test_execute_readiness_once_then_plan_and_execute() -> None:
    calls=[]; runtime=build_runtime(None,None,None,None,dependencies(calls))
    for state in (State.MOVE_ABOVE_OBJECT,State.DESCEND): run(runtime.actions[state],state,RunMode.EXECUTE)
    assert calls == ["ready",("plan",State.MOVE_ABOVE_OBJECT),("execute",State.MOVE_ABOVE_OBJECT),("plan",State.DESCEND),("execute",State.DESCEND)]


def test_attachment_and_scene_states_have_separate_ownership() -> None:
    calls=[]; runtime=build_runtime(None,None,None,None,dependencies(calls))
    for state in (State.ATTACH_GAZEBO,State.ATTACH_MOVEIT,State.DETACH_GAZEBO,State.DETACH_MOVEIT,State.SYNC_WORLD_OBJECT):
        run(runtime.actions[state],state,RunMode.EXECUTE)
    assert calls == [("gazebo",True),("moveit",True),("gazebo",False),("moveit",False),"sync"]
