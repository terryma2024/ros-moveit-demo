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


def test_native_solve_preserves_complete_update_trace(monkeypatch):
    """The native loop must keep every update, branch and failure outcome exact."""
    from so101_demo.ports.evidence import PoseEvidence

    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    kernel = solver._numeric
    assert hasattr(kernel, "solve"), "native solve loop is missing"
    rng = np.random.default_rng(1055)
    limits = np.asarray(solver.joint_limits)
    cases = [(solver.forward(np.zeros(5)), (0.0,) * 5, {})]
    cases.append((PoseEvidence((1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)),
                  (0.0,) * 5, {}))
    for _ in range(8):
        target = solver.forward(rng.uniform(limits[:, 0], limits[:, 1]))
        cases.append((target, tuple(rng.uniform(limits[:, 0], limits[:, 1])), {}))
    actual = solver.forward(np.zeros(5))
    shifted = PoseEvidence((actual.position_m[0] + 0.004, *actual.position_m[1:]),
                           actual.orientation_xyzw)
    import math

    distance = math.dist(actual.position_m, shifted.position_m)
    for tolerance in (np.nextafter(distance, 0.0), distance, np.nextafter(distance, 1.0)):
        cases.append((shifted, (0.0,) * 5, {"position_tolerance_m": float(tolerance)}))
    original_solve = np.linalg.solve

    def run(target, seed, kwargs, numeric):
        solver._numeric = numeric
        trace = []

        def recorded(lhs, rhs):
            step = original_solve(lhs, rhs)
            trace.append((lhs.tobytes(), rhs.tobytes(), step.tobytes()))
            return step

        monkeypatch.setattr(np.linalg, "solve", recorded)
        try:
            outcome = tuple(float(value).hex() for value in solver.solve(target, seed, **kwargs))
        except Exception as error:
            outcome = (type(error).__name__, error.args)
        return outcome, trace

    for target, seed, kwargs in cases:
        expected = run(target, seed, kwargs, None)
        actual = run(target, seed, kwargs, kernel)
        assert actual == expected


def test_native_failed_solve_uses_bounded_explicit_workspaces(monkeypatch):
    """A 200-update failure must not rebuild motion/residual/Jacobian arrays."""
    from so101_demo.control.moveit.underactuated_ik import UnderactuatedIkError
    from so101_demo.ports.evidence import PoseEvidence

    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    allocations = 0
    original_empty, original_eye = np.empty, np.eye

    def counted_empty(*args, **kwargs):
        nonlocal allocations
        allocations += 1
        return original_empty(*args, **kwargs)

    def counted_eye(*args, **kwargs):
        nonlocal allocations
        allocations += 1
        return original_eye(*args, **kwargs)

    monkeypatch.setattr(np, "empty", counted_empty)
    monkeypatch.setattr(np, "eye", counted_eye)
    with pytest.raises(UnderactuatedIkError, match="DYNAMIC_IK_RESIDUAL_EXCEEDED"):
        solver.solve(PoseEvidence((1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)), (0.0,) * 5)
    assert allocations <= 20, f"iteration arrays were rebuilt {allocations} times"


def test_native_position_batch_matches_forward_without_quaternion_work(monkeypatch):
    """Path samples need exact positions, without unused quaternion normalization."""
    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    assert hasattr(solver, "forward_positions"), "position-only batch FK is missing"
    rng = np.random.default_rng(1056)
    limits = np.asarray(solver.joint_limits)
    vectors = [np.zeros(5), -np.zeros(5), limits[:, 0], limits[:, 1]]
    vectors.extend(rng.uniform(limits[:, 0], limits[:, 1], (80, 5)))
    expected = tuple(solver.forward(q).position_m for q in vectors)
    original_norm = np.linalg.norm
    normalizations = 0

    def recorded(*args, **kwargs):
        nonlocal normalizations
        normalizations += 1
        return original_norm(*args, **kwargs)

    monkeypatch.setattr(np.linalg, "norm", recorded)
    actual = solver.forward_positions(vectors)
    assert np.asarray(actual).tobytes() == np.asarray(expected).tobytes()
    assert normalizations == 0


def test_batched_path_metrics_preserve_true_end_and_all_nine_samples():
    from so101_demo.control.moveit.deterministic_horizon import (
        HorizonIkCache, _kinematic_segment_metrics,
    )

    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    assert hasattr(solver, "forward_positions"), "position-only batch FK is missing"
    rng = np.random.default_rng(1057)
    limits = np.asarray(solver.joint_limits)
    pairs = [(tuple(np.zeros(5)), tuple(-np.zeros(5)))]
    pairs.extend((tuple(a), tuple(b)) for a, b in rng.uniform(
        limits[:, 0], limits[:, 1], (40, 2, 5)))
    for start, end in pairs:
        expected = _kinematic_segment_metrics(solver, start, end)
        actual = _kinematic_segment_metrics(HorizonIkCache(solver), start, end)
        assert tuple(value.hex() for value in actual) == tuple(value.hex() for value in expected)


def test_direct_numpy_product_preserves_layout_bits_and_error_policy():
    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    kernel = solver._numeric
    assert hasattr(kernel, "matmul_into"), "direct NumPy product is missing"
    rng = np.random.default_rng(1060)
    for rows, inner, columns in ((4, 4, 4), (3, 3, 3), (5, 6, 5)):
        for index in range(100):
            a = rng.uniform(-1, 1, (rows, inner))
            b = rng.uniform(-1, 1, (inner, columns))
            if index % 2:
                a = np.asfortranarray(a)
            if index % 3:
                b = np.asfortranarray(b)
            out = np.empty((rows, columns))
            kernel.matmul_into(a, b, out)
            assert out.tobytes() == (a @ b).tobytes()
    a = np.eye(4)
    b = rng.uniform(-1, 1, (4, 4))
    expected = a @ b
    kernel.matmul_into(a, b, a)
    assert a.tobytes() == expected.tobytes()
    for size in (1, 4):
        a = np.full((size, size), 1e308)
        out = np.empty_like(a)
        with np.errstate(over="raise", invalid="raise"):
            try:
                expected = a @ a
            except FloatingPointError as error:
                with pytest.raises(FloatingPointError) as actual:
                    kernel.matmul_into(a, a, out)
                assert actual.value.args == error.args
            else:
                # BLAS implementations differ in whether they expose FPE flags;
                # preserve the behavior of the same-platform NumPy reference.
                kernel.matmul_into(a, a, out)
                assert out.tobytes() == expected.tobytes()
    b = rng.uniform(-1, 1, (4, 4))
    with np.errstate(all="ignore"):
        a = np.full((4, 4), np.nan)
        out = np.empty((4, 4))
        kernel.matmul_into(a, b, out)
        assert out.tobytes() == (a @ b).tobytes()


def test_unknown_numpy_capsule_version_keeps_exact_dispatch_fallback(monkeypatch):
    accelerated = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    if accelerated._numeric is None:
        pytest.skip("optional native extension has not been built")
    seed = (0.0,) * 5
    target = accelerated.forward((0.1, 0.2, 0.1, 0.3, 0.1))
    expected = accelerated.solve(target, seed)
    monkeypatch.setattr(np, "__version__", "99.0.0")
    fallback = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    assert not fallback._numeric.direct_matmul
    assert tuple(value.hex() for value in fallback.solve(target, seed)) == tuple(
        value.hex() for value in expected)


def test_nonrigid_custom_chain_keeps_original_pose_validation_error():
    from so101_demo.control.moveit.underactuated_ik import _Joint
    from so101_demo.ports.evidence import PoseEvidence

    origin = np.eye(4)
    origin[1, 2] = 1e200
    solver = UnderactuatedPoseIk((_Joint("1", "revolute", origin, (0.0, 0.0, 1.0), -1, 1),),
                                ("1",))
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    kernel = solver._numeric
    target = PoseEvidence((1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0))
    outcomes = []
    with np.errstate(all="ignore"):
        for numeric in (None, kernel):
            solver._numeric = numeric
            try:
                solver.solve(target, (0.0,))
            except Exception as error:
                outcomes.append((type(error).__name__, error.args))
            else:
                outcomes.append("unexpected success")
    assert outcomes[1] == outcomes[0]


def test_native_loop_preserves_malformed_target_shape_guard():
    from types import SimpleNamespace

    solver = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    if solver._numeric is None:
        pytest.skip("optional native extension has not been built")
    target = SimpleNamespace(position_m=(0.0, 0.0, 0.0, 0.0),
                             orientation_xyzw=(0.0, 0.0, 0.0, 1.0))
    with pytest.raises(ValueError, match="^invalid IK residual shape$"):
        solver.solve(target, (0.0,) * 5)
