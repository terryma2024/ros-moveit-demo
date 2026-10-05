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


@pytest.mark.parametrize("boundary", ("lower", "upper"))
def test_solution_keeps_control_margin_at_joint_limit(boundary: str) -> None:
    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    lower, upper = solver.joint_limits[3]
    limit = lower if boundary == "lower" else upper
    at_limit = (0.0, 0.0, 0.0, limit, 0.0)
    target = solver.forward(at_limit)

    solution = solver.solve(target, at_limit)
    actual = solver.forward(solution)

    assert lower + 0.002 - 1e-9 <= solution[3] <= upper - 0.002 + 1e-9
    assert actual.position_m == pytest.approx(target.position_m, abs=0.002)
    assert solver.orientation_error_rad(actual, target) <= 0.10


def test_forward_does_not_renormalize_fixed_joint_axes(monkeypatch) -> None:
    import numpy as np

    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    calls = 0
    real_norm = np.linalg.norm

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_norm(*args, **kwargs)

    monkeypatch.setattr(np.linalg, "norm", counted)
    for _ in range(3):
        actual = solver.forward(GRASP_JOINTS)
        assert actual.position_m == pytest.approx(GRASP_POSE.position_m, abs=2e-5)
    # Only the output quaternion normalization is needed per forward call.
    assert calls == 3


def test_solve_reuses_gate_fk(monkeypatch) -> None:
    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    seed = (0.0,) * 5
    target = solver.forward(seed)
    calls = 0
    real_matrix = solver._matrix

    def counted(*args):
        nonlocal calls
        calls += 1
        return real_matrix(*args)

    monkeypatch.setattr(solver, "_matrix", counted)
    assert solver.solve(target, seed) == seed
    assert calls == 1


def test_failed_solve_preserves_all_finite_difference_iterations(monkeypatch) -> None:
    from so101_demo.control.moveit.underactuated_ik import UnderactuatedIkError

    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    calls = 0
    real_matrix = solver._matrix

    def counted(*args):
        nonlocal calls
        calls += 1
        return real_matrix(*args)

    monkeypatch.setattr(solver, "_matrix", counted)
    with pytest.raises(UnderactuatedIkError, match="DYNAMIC_IK_RESIDUAL_EXCEEDED"):
        solver.solve(PoseEvidence((1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)), (0.0,) * 5)
    # 200 original iterations: one base FK plus five finite differences, then final failure FK.
    assert calls == 1201


def test_precomputed_fk_matches_uncached_urdf_chain_for_finite_inputs() -> None:
    import numpy as np
    from so101_demo.control.moveit.underactuated_ik import _rotation_axis, _transform

    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    rng = np.random.default_rng(101)
    limits = np.asarray(solver.joint_limits)
    vectors = [limits[:, 0], limits[:, 1], np.zeros(5), np.asarray(GRASP_JOINTS)]
    vectors.extend(rng.uniform(limits[:, 0], limits[:, 1], (40, 5)))
    for positions in vectors:
        values = dict(zip(JOINTS, positions, strict=True))
        reference = np.eye(4)
        for joint in solver._chain:
            reference = reference @ joint.origin
            if joint.kind != "fixed":
                reference = reference @ _transform(
                    _rotation_axis(joint.axis, values[joint.name]), (0, 0, 0)
                )
        np.testing.assert_array_equal(solver._matrix(positions), reference)


def test_solver_preserves_invalid_seed_error() -> None:
    from so101_demo.control.moveit.underactuated_ik import UnderactuatedIkError

    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    with pytest.raises(UnderactuatedIkError, match="^DYNAMIC_IK_SEED_INVALID$"):
        solver.solve(GRASP_POSE, (0.0, 0.0))
