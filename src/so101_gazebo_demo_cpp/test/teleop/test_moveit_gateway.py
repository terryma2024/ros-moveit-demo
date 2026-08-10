import asyncio

from so101_teleop.models import CollisionPair, JointPlanRequest, Pose6D, TcpPlanRequest
from so101_teleop.moveit_gateway import MoveItGateway
from test_support import FakeMoveItBackend, ready_snapshot


def test_joint_plan_excludes_q6_and_preserves_first_trajectory_collision():
    """Including q6 in arm planning or losing its first collision makes execution unsafe."""
    async def scenario():
        backend = FakeMoveItBackend(
            waypoint_collisions={3: [CollisionPair(source="moveit", object_a="jaw", object_b="plastic_cup")]}
        )
        gateway = MoveItGateway(backend)
        request = JointPlanRequest(command_id="plan-1", target_joints_rad={
            "1": 0.1, "2": 0.2, "3": 0.3, "4": 0.4, "5": 0.5, "6": 0.6,
        })

        result = await gateway.plan_joints(request, ready_snapshot())

        assert backend.planned_targets == {"1": 0.1, "2": 0.2, "3": 0.3, "4": 0.4, "5": 0.5}
        assert result.code == "TRAJECTORY_COLLISION"
        assert result.collisions[0].waypoint_index == 3
        assert {result.collisions[0].object_a, result.collisions[0].object_b} == {"jaw", "plastic_cup"}

    asyncio.run(scenario())


def test_tcp_plan_uses_actual_joint_seed_then_shared_joint_path():
    """Replacing the actual seed with browser target state can select a discontinuous IK branch."""
    async def scenario():
        backend = FakeMoveItBackend(ik_solution={"1": 0.11, "2": 0.22, "3": 0.33, "4": 0.44, "5": 0.55})
        gateway = MoveItGateway(backend)
        request = TcpPlanRequest(
            command_id="tcp-1",
            target=Pose6D(frame_id="world", tcp_frame="so101_tcp", x_m=0.1, y_m=0.2, z_m=0.3,
                          roll_rad=0.0, pitch_rad=0.0, yaw_rad=0.0),
        )
        snapshot = ready_snapshot()

        result = await gateway.plan_tcp(request, snapshot)

        assert backend.ik_seed == {name: sample.position_rad for name, sample in snapshot.joints.items() if name != "6"}
        assert backend.planned_targets == backend.ik_solution
        assert result.code == "OK"

    asyncio.run(scenario())
