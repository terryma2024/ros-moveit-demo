"""Typed ROS goal fields preserved across CDR serialization."""

from pathlib import Path

from control_msgs.action import FollowJointTrajectory
from control_msgs.msg import JointTolerance
from rclpy.serialization import deserialize_message, serialize_message
from trajectory_msgs.msg import JointTrajectoryPoint


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / 'so101_mujoco_support/test/fixtures/follow_joint_trajectory_goal.cdr.hex'
)


def controller_goal_fixture():
    goal = FollowJointTrajectory.Goal()
    goal.trajectory.header.stamp.sec = 123
    goal.trajectory.header.stamp.nanosec = 456
    goal.trajectory.header.frame_id = 'base_link'
    goal.trajectory.joint_names = ['1', '2']
    point = JointTrajectoryPoint()
    point.positions = [0.125, -0.25]
    point.velocities = [0.0, 0.5]
    point.accelerations = [0.125, -0.125]
    point.time_from_start.nanosec = 2_000_000
    goal.trajectory.points = [point]
    path = JointTolerance()
    path.name = '1'
    path.position = 0.001
    path.velocity = 0.002
    path.acceleration = 0.003
    goal.path_tolerance = [path]
    terminal = JointTolerance()
    terminal.name = '2'
    terminal.position = 0.004
    terminal.velocity = 0.005
    terminal.acceleration = 0.006
    goal.goal_tolerance = [terminal]
    goal.goal_time_tolerance.nanosec = 50_000_000
    return goal


def test_python_controller_goal_cdr_preserves_exact_semantic_fields():
    goal = controller_goal_fixture()
    fixture = bytes.fromhex(FIXTURE.read_text().strip())
    decoded = deserialize_message(fixture, FollowJointTrajectory.Goal)
    assert decoded == goal
    assert decoded.trajectory.joint_names == ['1', '2']
    assert list(decoded.trajectory.points[0].positions) == [0.125, -0.25]
    assert decoded.trajectory.header.stamp.sec == 123
    assert decoded.goal_time_tolerance.nanosec == 50_000_000
    for _ in range(4):
        actual = serialize_message(goal)
        assert deserialize_message(actual, FollowJointTrajectory.Goal) == decoded
