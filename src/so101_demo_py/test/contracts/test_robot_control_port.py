from so101_demo.control.robot_control import SharedRobotControl
from so101_demo.ports.robot_control import (
    ExecutionResult,
    GripperRequest,
    GripperResult,
    JointStateEvidence,
    JointWaypointRequest,
    PlanResult,
    RobotControlPort,
    StopResult,
    TcpMotionRequest,
)


class Harness:
    def __init__(self) -> None:
        self.state = JointStateEvidence(("1", "2"), (0.0, 0.0), 1.0)
        self.executed = 0

    def plan_joint(self, request: JointWaypointRequest, state: JointStateEvidence) -> object:
        return object()

    def plan_tcp(self, request: TcpMotionRequest, state: JointStateEvidence) -> object:
        return object()

    def execute(self, trajectory: object) -> ExecutionResult:
        self.executed += 1
        return ExecutionResult(True)

    def gripper(self, request: GripperRequest) -> GripperResult:
        return GripperResult(True, request.target_position_rad)

    def stop(self, reason: str) -> StopResult:
        return StopResult(True, reason)


def _control(harness: Harness) -> SharedRobotControl:
    return SharedRobotControl(
        state_reader=lambda timeout_s: harness.state,
        joint_planner=harness.plan_joint,
        tcp_planner=harness.plan_tcp,
        trajectory_executor=harness.execute,
        gripper_commander=harness.gripper,
        stopper=harness.stop,
    )


def test_execute_rejects_stale_start_state() -> None:
    """Catch executing a valid plan after the robot moved away from its captured start."""

    harness = Harness()
    control = _control(harness)
    plan = control.plan_joint_waypoints(JointWaypointRequest(("1", "2"), (0.1, 0.2)))
    harness.state = JointStateEvidence(("1", "2"), (0.02, 0.0), 2.0)
    result = control.execute(plan)
    assert not result.accepted
    assert result.error_code == "PLAN_START_STATE_MISMATCH"
    assert harness.executed == 0


def test_control_returns_typed_plan_and_exposes_required_methods() -> None:
    harness = Harness()
    control = _control(harness)
    plan = control.plan_joint_waypoints(JointWaypointRequest(("1", "2"), (0.1, 0.2)))
    assert isinstance(plan, PlanResult)
    assert plan.accepted
    assert set(RobotControlPort.__protocol_attrs__) >= {
        "current_joint_state",
        "plan_joint_waypoints",
        "plan_tcp_motion",
        "execute",
        "command_gripper",
        "stop",
    }
