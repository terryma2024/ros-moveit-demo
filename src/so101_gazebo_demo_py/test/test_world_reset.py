from so101_gazebo_demo_py.domain import ActionResult, ActionStatus
from so101_gazebo_demo_py.gazebo.reset import WorldResetCoordinator


def test_reset_orders_detach_pose_scene_arm_gripper_then_proof() -> None:
    calls=[]
    def action(name): return lambda: calls.append(name) or ActionResult(ActionStatus.SUCCEEDED)
    coordinator=WorldResetCoordinator(*(action(name) for name in ("detach","pose","scene","arm","gripper","prove")))
    assert coordinator.reset().status is ActionStatus.SUCCEEDED
    assert calls == ["detach","pose","scene","arm","gripper","prove"]


def test_reset_stops_at_first_unproved_side_effect() -> None:
    calls=[]
    def bad(): calls.append("detach"); return ActionResult(ActionStatus.FAILED)
    result=WorldResetCoordinator(bad, *(lambda: ActionResult(ActionStatus.SUCCEEDED) for _ in range(5))).reset()
    assert result.status is ActionStatus.FAILED and calls == ["detach"]
