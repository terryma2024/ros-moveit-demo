from dataclasses import dataclass

from so101_gazebo_demo_py.domain import ActionStatus
from so101_gazebo_demo_py.motion.gripper import GripperClient


class Future:
    def __init__(self, value): self.value = value
    def done(self): return True
    def result(self): return self.value


@dataclass
class Goal:
    accepted: bool = True
    def get_result_async(self): return Future(type("Wrapped", (), {"result": type("R", (), {"error_code": 0})()})())


class Action:
    def wait_for_server(self, timeout_sec): return True
    def send_goal_async(self, goal): self.goal = goal; return Future(Goal())


def test_gripper_sends_only_q6_and_duration() -> None:
    action = Action()
    client = GripperClient(action, goal_factory=lambda q6, duration: ("6", q6, duration))
    result = client.command(-0.04, 0.5, 1.0)
    assert result.status is ActionStatus.SUCCEEDED
    assert action.goal == ("6", -0.04, 0.5)
