"""Test-only fakes for Teleop boundary contract tests."""

from so101_teleop.models import CollisionPair, JointSample, Pose6D, TelemetrySnapshot


def ready_snapshot():
    return TelemetrySnapshot(
        sequence=1,
        simulation_session_id="test-simulation",
        source_ages_s={"joints": 0.01, "tcp": 0.01, "object": 0.01, "scene": 0.01},
        joints={str(index): JointSample(name=str(index), position_rad=index / 100.0) for index in range(1, 7)},
        tcp=Pose6D(frame_id="world", tcp_frame="so101_tcp", x_m=0.0, y_m=0.0, z_m=0.2,
                   roll_rad=0.0, pitch_rad=0.0, yaw_rad=0.0),
        object_pose=Pose6D(frame_id="world", tcp_frame="plastic_cup", x_m=0.0, y_m=0.0, z_m=0.03,
                          roll_rad=0.0, pitch_rad=0.0, yaw_rad=0.0),
        controllers={"arm_controller": "active", "gripper_controller": "active"},
        gazebo_attached=False,
        moveit_attached=False,
    )


class FakeMoveItBackend:
    def __init__(self, waypoint_collisions=None, ik_solution=None):
        self.waypoint_collisions = waypoint_collisions or {}
        self.ik_solution = ik_solution or {}
        self.planned_targets = None
        self.ik_seed = None

    async def solve_ik(self, target, seed):
        self.ik_seed = dict(seed)
        return dict(self.ik_solution)

    async def plan_joints(self, target, start):
        self.planned_targets = dict(target)
        return [dict(start), dict(target), dict(target), dict(target)]

    async def validate(self, joints, waypoint_index):
        return self.waypoint_collisions.get(waypoint_index, [])
