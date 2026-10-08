"""Backend selection must preserve native behavior and the shared solver contract."""

import importlib
import importlib.util
import math
import os
from pathlib import Path

import pytest

from so101_demo.control.moveit.underactuated_ik import UnderactuatedIkError, UnderactuatedPoseIk
from so101_demo.ports.evidence import PoseEvidence

PACKAGE = Path(__file__).parents[1]
URDF = PACKAGE / "assets/mujoco/so101.urdf"
JOINTS = ("1", "2", "3", "4", "5")


def _factory():
    name = "so101_demo.control.moveit.pose_ik"
    assert importlib.util.find_spec(name) is not None, "missing selectable IK factory"
    return importlib.import_module(name)


def _solver(backend=None):
    return _factory().create_pose_ik(URDF, JOINTS, "world", "so101_tcp", backend=backend)


def test_default_and_explicit_native_keep_original_solver_and_results(monkeypatch):
    monkeypatch.delenv("SO101_IK_BACKEND", raising=False)
    reference = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    target = reference.forward((0.0,) * 5)
    for solver in (_solver(), _solver("native")):
        assert type(solver) is UnderactuatedPoseIk
        assert solver.solve(target, (0.0,) * 5) == reference.solve(target, (0.0,) * 5)


def test_explicit_selection_overrides_environment_without_mutating_it(monkeypatch):
    monkeypatch.setenv("SO101_IK_BACKEND", "quik")
    assert type(_solver("native")) is UnderactuatedPoseIk
    assert _factory().resolve_ik_backend() == "quik"


@pytest.mark.parametrize("value", ["", "ikpy", "QUIK", "native ", "auto"])
def test_unknown_backend_is_rejected_before_urdf_loading(value):
    with pytest.raises(ValueError, match="IK_BACKEND_UNSUPPORTED"):
        _factory().create_pose_ik(Path("absent.urdf"), JOINTS, "world", "so101_tcp", backend=value)


@pytest.mark.parametrize("module", ["dynamic_cup_pick_place", "task_reachability"])
def test_cli_accepts_explicit_backend_and_rejects_unknown_backend(module):
    parser = importlib.import_module("so101_demo.cli." + module).build_parser()
    required = [] if module == "dynamic_cup_pick_place" else [
        "--points", "points.yaml", "--policy", "policy.yaml",
        "--session-id", "test", "--evidence-file", "evidence.json",
    ]
    assert parser.parse_args([*required, "--ik-backend", "quik"]).ik_backend == "quik"
    assert parser.parse_args(required).ik_backend is None
    with pytest.raises(SystemExit):
        parser.parse_args([*required, "--ik-backend", "ikpy"])


def _quik_or_skip():
    if importlib.util.find_spec("so101_quik") is None:
        if os.environ.get("SO101_REQUIRE_QUIK_TESTS") == "1":
            pytest.fail("QuIK integration gate requires the installed so101_quik package")
        pytest.skip("so101_quik package not installed")
    return _solver("quik")


def test_quik_same_pose_seed_preserves_tuple_and_canonical_fk():
    solver = _quik_or_skip()
    q = (0.0, 0.4, 0.2, 0.8, 0.0)
    target = solver.forward(q)
    assert solver.solve(target, q) == q
    assert solver.forward_positions((q, q)) == (target.position_m, target.position_m)
    assert solver.orientation_error_rad(target, target) == 0.0


def test_quik_solves_different_target_with_original_geometry_gates():
    solver = _quik_or_skip()
    target = solver.forward((0.0, 0.4, 0.2, 0.8, 0.0))
    q = solver.solve(target, (0.0,) * 5)
    assert isinstance(q, tuple) and len(q) == 5
    assert all(type(v) is float for v in q)
    assert math.dist(solver.forward(q).position_m, target.position_m) <= 0.002
    assert solver.orientation_error_rad(solver.forward(q), target) <= 0.10
    assert all(lo + 0.002 <= v <= hi - 0.002
               for v, (lo, hi) in zip(q, solver.joint_limits, strict=True))


def test_quik_rejects_unreachable_pose_with_project_error_code():
    solver = _quik_or_skip()
    with pytest.raises(UnderactuatedIkError, match="^DYNAMIC_IK_RESIDUAL_EXCEEDED:"):
        solver.solve(PoseEvidence((1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)), (0.0,) * 5)


@pytest.mark.parametrize("backend", ["native", "quik"])
def test_invalid_seed_shape_uses_shared_error(backend):
    solver = _quik_or_skip() if backend == "quik" else _solver(backend)
    with pytest.raises(UnderactuatedIkError, match="^DYNAMIC_IK_SEED_INVALID$"):
        solver.solve(PoseEvidence((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)), (0.0,))


def test_missing_quik_binary_is_explicit_and_never_switches_to_native(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "so101_quik", None)
    with pytest.raises(UnderactuatedIkError, match="^QUIK_BACKEND_UNAVAILABLE:"):
        _solver("quik")


def test_nonfinite_seed_errors_match_native_without_calling_native_solve(monkeypatch):
    quik = _quik_or_skip()
    native = _solver("native")
    seed = (float("nan"), 0.0, 0.0, 0.0, 0.0)
    target = native.forward((0.0,) * 5)
    with pytest.raises(ValueError) as error:
        native.solve(target, seed)

    def forbidden(*_args, **_kwargs):
        pytest.fail("QuIK called native.solve as an implicit fallback")

    monkeypatch.setattr(quik._reference, "solve", forbidden)
    with pytest.raises(ValueError) as quik_error:
        quik.solve(target, seed)
    assert str(quik_error.value) == str(error.value)


def test_quik_uses_only_equivalent_angles_and_rejects_out_of_limit_result():
    import numpy as np

    solver = _quik_or_skip()
    seed = np.zeros(5)
    seed[:] = 0.1
    equivalent = solver._normalize(seed + 2 * math.pi, seed)
    assert equivalent == pytest.approx(seed, abs=1e-14)
    # No equivalent wrist value fits; normalization must not clip it into acceptance.
    outside = seed.copy()
    outside[3] = solver.joint_limits[3][1] + 0.2
    assert solver._normalize(outside, seed)[3] == outside[3]


def test_quik_serializes_shared_native_context_for_parallel_calls():
    from concurrent.futures import ThreadPoolExecutor

    solver = _quik_or_skip()
    target = solver.forward((0.0, 0.4, 0.2, 0.8, 0.0))
    expected = solver.solve(target, (0.0,) * 5)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = tuple(pool.map(lambda _: solver.solve(target, (0.0,) * 5), range(12)))
    assert results == (expected,) * 12


@pytest.mark.parametrize("backend", ["native", "quik"])
def test_reachability_constructor_respects_explicit_backend(monkeypatch, backend):
    if backend == "quik":
        _quik_or_skip()
    from so101_demo.core.dynamic_pick_policy import load_dynamic_pick_template
    from so101_demo.ros.task_reachability import RosMoveGroupReachabilityPlanner

    monkeypatch.setenv("SO101_IK_BACKEND", "quik" if backend == "native" else "native")
    template = load_dynamic_pick_template(
        PACKAGE / "config/policies/dynamic_cup_pick/v1/mujoco.yaml", expected_backend="mujoco"
    )
    planner = RosMoveGroupReachabilityPlanner(
        object(), template, action_client=object(), ik_backend=backend
    )
    assert planner.ik_provenance["backend"] == backend
