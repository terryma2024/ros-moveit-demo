from pathlib import Path

import pytest

from so101_demo.control.moveit.underactuated_ik import UnderactuatedPoseIk
from so101_demo.ports.evidence import PoseEvidence


URDF = Path(__file__).parents[1] / "assets" / "mujoco" / "so101.urdf"
JOINTS = ("1", "2", "3", "4", "5")
GRASP_JOINTS = (-0.000206491845, 0.472194274096, 0.214652624195, 0.854922375695, 0.000576703465)
GRASP_POSE = PoseEvidence(
    (0.0206766838, -0.2628210212, 0.2006306106),
    (-0.010265991, -0.010262987, -0.706752687, 0.707311756),
)


def test_forward_kinematics_matches_proved_fixed_grasp_tcp() -> None:
    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")

    actual = solver.forward(GRASP_JOINTS)

    assert actual.position_m == pytest.approx(GRASP_POSE.position_m, abs=2e-5)
    assert abs(sum(a * b for a, b in zip(actual.orientation_xyzw, GRASP_POSE.orientation_xyzw))) \
        == pytest.approx(1.0, abs=2e-4)


def test_full_pose_solver_recovers_grasp_branch_from_home_seed() -> None:
    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")

    solution = solver.solve(GRASP_POSE, (0.0, 0.0, 0.0, 0.0, 0.0))
    actual = solver.forward(solution)

    assert actual.position_m == pytest.approx(GRASP_POSE.position_m, abs=0.002)
    assert solver.orientation_error_rad(actual, GRASP_POSE) <= 0.10
