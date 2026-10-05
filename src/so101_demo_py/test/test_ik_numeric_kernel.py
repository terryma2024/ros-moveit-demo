"""Exact numeric regression for the CPU IK kernel, using the real URDF chain."""

from pathlib import Path

import numpy as np
import pytest

from so101_demo.control.moveit.underactuated_ik import UnderactuatedPoseIk


URDF = Path(__file__).parents[1] / "assets/mujoco/so101.urdf"
JOINTS = ("1", "2", "3", "4", "5")


def test_finite_difference_reuses_rotations_without_changing_matrix_bits(monkeypatch):
    """Sharing work must preserve all six FK matrices, including signed zero."""
    import so101_demo.control.moveit.underactuated_ik as module

    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    # Exercise the Python reference independently of an installed native accelerator.
    if hasattr(solver, "_numeric"):
        monkeypatch.setattr(solver, "_numeric", None)
    assert hasattr(solver, "_matrix_with_prefixes"), "shared finite-difference FK is missing"
    limits = np.asarray(solver.joint_limits)
    rng = np.random.default_rng(105)
    vectors = [np.zeros(5), -np.zeros(5), limits[:, 0], limits[:, 1]]
    vectors.extend(rng.uniform(limits[:, 0], limits[:, 1], (80, 5)))
    original_sin = module.math.sin
    calls = 0

    def counted_sin(angle):
        nonlocal calls
        calls += 1
        return original_sin(angle)

    for q in vectors:
        expected = [solver._matrix(q)]
        for index in range(5):
            candidate = q.copy()
            candidate[index] += 1e-5
            expected.append(solver._matrix(candidate))
        monkeypatch.setattr(module.math, "sin", counted_sin)
        before = calls
        matrix, prefixes, motions = solver._matrix_with_prefixes(q)
        actual = [matrix, *solver._perturbed_matrices(q, 1e-5, prefixes, motions)]
        assert calls - before == 10
        monkeypatch.setattr(module.math, "sin", original_sin)
        for reference, value in zip(expected, actual, strict=True):
            assert value.dtype == np.float64
            assert value.tobytes() == reference.tobytes()


def test_compiled_numeric_kernel_matches_reference_at_limits_and_random_inputs():
    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    assert hasattr(solver, "_numeric"), "compiled backend integration is missing"
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    kernel = solver._numeric
    limits = np.asarray(solver.joint_limits)
    rng = np.random.default_rng(1051)
    vectors = [np.zeros(5), -np.zeros(5), limits[:, 0], limits[:, 1]]
    vectors.extend(rng.uniform(limits[:, 0], limits[:, 1], (120, 5)))
    for q in vectors:
        solver._numeric = None
        reference, prefixes, motions = solver._matrix_with_prefixes(q)
        expected = [reference, *solver._perturbed_matrices(q, 1e-5, prefixes, motions)]
        solver._numeric = kernel
        matrix, prefixes, motions = solver._matrix_with_prefixes(q)
        actual = [matrix, *solver._perturbed_matrices(q, 1e-5, prefixes, motions)]
        for a, b in zip(actual, expected, strict=True):
            assert a.tobytes() == b.tobytes()
        position = rng.uniform(-0.5, 0.5, 3)
        rotation = solver._matrix(rng.uniform(limits[:, 0], limits[:, 1]))[:3, :3]
        for a in actual:
            expected = solver._residual_from_matrix(a, position, rotation)
            result = kernel.residual(a, position, rotation)
            assert result.tobytes() == expected.tobytes()


def test_compiled_jacobian_preserves_all_five_difference_columns():
    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    kernel = solver._numeric
    assert hasattr(kernel, "jacobian"), "compiled Jacobian assembly is missing"
    rng = np.random.default_rng(1052)
    limits = np.asarray(solver.joint_limits)
    for q in rng.uniform(limits[:, 0], limits[:, 1], (120, 5)):
        matrix, prefixes, motions = solver._matrix_with_prefixes(q)
        matrices = list(solver._perturbed_matrices(q, 1e-5, prefixes, motions))
        position = rng.uniform(-0.5, 0.5, 3)
        rotation = solver._matrix(rng.uniform(limits[:, 0], limits[:, 1]))[:3, :3]
        residual = solver._residual_from_matrix(matrix, position, rotation)
        reference = np.empty((6, 5))
        for index, candidate in enumerate(matrices):
            reference[:, index] = (
                solver._residual_from_matrix(candidate, position, rotation) - residual
            ) / 1e-5
        actual = kernel.jacobian(matrices, position, rotation, residual, 1e-5)
        assert actual.tobytes() == reference.tobytes()


@pytest.mark.parametrize("joint_names", (JOINTS, tuple(reversed(JOINTS))))
def test_compiled_fk_preserves_arbitrary_axes_and_joint_order(joint_names):
    from so101_demo.control.moveit.underactuated_ik import _Joint, _rotation_rpy, _transform

    rng = np.random.default_rng(1053)
    chain = tuple(
        _Joint(
            name, "revolute", _transform(_rotation_rpy(tuple(rng.uniform(-2, 2, 3))),
                                         tuple(rng.uniform(-0.1, 0.1, 3))),
            tuple(rng.uniform(-1, 1, 3)), -2.0, 2.0,
        ) for name in JOINTS
    )
    solver = UnderactuatedPoseIk(chain, joint_names)
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    for q in rng.uniform(-2, 2, (80, 5)):
        matrix, prefixes, motions = solver._matrix_with_prefixes(q)
        assert matrix.tobytes() == solver._matrix(q).tobytes()
        for index, actual in enumerate(solver._perturbed_matrices(q, 1e-5, prefixes, motions)):
            candidate = q.copy()
            candidate[index] += 1e-5
            assert actual.tobytes() == solver._matrix(candidate).tobytes()


def test_compiled_residual_preserves_small_angle_and_pi_branches():
    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    rotations = [np.eye(3), np.diag((1.0, -1.0, -1.0))]
    for diagonal in (np.nextafter(1.0, 0.0), np.nextafter(1.0, 2.0)):
        rotations.append(np.diag((diagonal, 1.0, 1.0)))
    for rotation in rotations:
        matrix = np.eye(4)
        matrix[:3, :3] = rotation
        position = np.zeros(3)
        expected = solver._residual_from_matrix(matrix, position, np.eye(3))
        actual = solver._numeric.residual(matrix, position, np.eye(3))
        assert actual.tobytes() == expected.tobytes()


def test_compiled_kernel_rejects_invalid_buffer_shapes():
    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    with pytest.raises(ValueError, match="position count"):
        solver._numeric.matrix_with_prefixes(np.zeros(4))
    with pytest.raises(ValueError, match="residual shape"):
        solver._numeric.residual(np.eye(3), np.zeros(3), np.eye(3))
    with pytest.raises(ValueError, match="Jacobian layout"):
        solver._numeric.jacobian([], np.zeros(3), np.eye(3), np.zeros(6), 1e-5)


@pytest.mark.parametrize("duplicate", ("position_name", "chain_joint"))
def test_nonunique_joint_layout_preserves_original_finite_differences(duplicate):
    original = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    names = ("1", *JOINTS) if duplicate == "position_name" else JOINTS
    chain = original._chain
    if duplicate == "chain_joint":
        chain = (*chain, next(joint for joint in chain if joint.name == "1"))
    solver = UnderactuatedPoseIk(chain, names)
    positions = np.arange(len(names), dtype=float) * 0.02
    matrix, prefixes, motions = solver._matrix_with_prefixes(positions)
    assert matrix.tobytes() == solver._matrix(positions).tobytes()
    actual = list(solver._perturbed_matrices(positions, 1e-5, prefixes, motions))
    for index, value in enumerate(actual):
        candidate = positions.copy()
        candidate[index] += 1e-5
        assert value.tobytes() == solver._matrix(candidate).tobytes()


def test_solver_subclass_keeps_its_custom_forward_model():
    class ShiftedIk(UnderactuatedPoseIk):
        def _matrix(self, positions):
            matrix = super()._matrix(positions).copy()
            matrix[2, 3] += 0.05
            return matrix

    solver = ShiftedIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    seed = (0.0,) * 5
    target = solver.forward(seed)
    assert solver.solve(target, seed) == seed
