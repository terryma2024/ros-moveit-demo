from pathlib import Path
from types import SimpleNamespace

import pytest
from so101_demo.control.moveit.deterministic_horizon import (
    HorizonWaypoint,
    deterministic_seed_candidates,
    interpolated_move_above_waypoints,
    solve_horizon,
    validate_cartesian_corridor,
)
from so101_demo.control.moveit.underactuated_ik import UnderactuatedPoseIk
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import CupPoseSample, resolve_motion_targets
from so101_demo.core.dynamic_pick_policy import load_dynamic_pick_template
from so101_demo.core.task_geometry import Pose7
from so101_demo.ports.evidence import PoseEvidence

PACKAGE = Path(__file__).parents[1]
URDF = PACKAGE / "assets/mujoco/so101.urdf"
POLICY = PACKAGE / "config/policies/dynamic_cup_pick/v1/mujoco.yaml"
JOINTS = ("1", "2", "3", "4", "5")


def test_seed_candidates_are_bounded_deterministic_and_source_complete() -> None:
    current = (0.01, 0.02, 0.03, 0.04, 0.05)
    prior = (0.11, 0.12, 0.13, 0.14, 0.15)

    first = deterministic_seed_candidates(current, prior)
    second = deterministic_seed_candidates(current, prior)

    assert first == second
    assert 8 <= len(first) <= 24
    assert first[0].source == "current_state"
    assert first[1].source == "prior_stage"
    assert {candidate.source for candidate in first} >= {
        "current_state",
        "prior_stage",
        "structured_base_yaw",
        "frozen_seed_bank",
    }
    assert len({candidate.positions_rad for candidate in first}) == len(first)


def test_move_above_waypoints_bound_each_cartesian_orientation_increment() -> None:
    start = (0.0, 0.0, 0.20, 0.0, 0.0)
    target = PoseEvidence((0.12, -0.18, 0.26), (0.0, 0.0, 1.0, 0.0))

    waypoints = interpolated_move_above_waypoints(
        _CartesianIk(), start, target
    )

    assert len(waypoints) == 6
    assert [waypoint.segment_index for waypoint in waypoints] == list(range(1, 7))
    assert all(
        waypoint.state is State.MOVE_ABOVE_OBJECT for waypoint in waypoints
    )
    assert waypoints[-1].target == target
    assert waypoints[0].target.position_m == pytest.approx((0.02, -0.03, 0.21))
    assert all(
        sum(value * value for value in waypoint.target.orientation_xyzw)
        == pytest.approx(1.0)
        for waypoint in waypoints
    )


def test_real_p18_pick_prefix_has_a_deterministic_complete_horizon() -> None:
    template = load_dynamic_pick_template(POLICY, expected_backend="mujoco")
    ik = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, template.planning_frame, template.tcp_link)
    sample = CupPoseSample(
        "world",
        1,
        0.0,
        Pose7((0.051023, -0.339445, 0.165, 0.0, 0.0, 0.0, 1.0)),
    )
    targets = resolve_motion_targets(sample, template)
    above = targets.for_state(State.MOVE_ABOVE_OBJECT)
    descend = targets.for_state(State.DESCEND)
    waypoints = [HorizonWaypoint(State.MOVE_ABOVE_OBJECT, 0, above)]
    waypoints.extend(
        HorizonWaypoint(
            State.DESCEND,
            index,
            PoseEvidence(
                tuple(
                    above.position_m[axis]
                    + index / 6.0 * (descend.position_m[axis] - above.position_m[axis])
                    for axis in range(3)
                ),
                descend.orientation_xyzw,
            ),
        )
        for index in range(1, 7)
    )
    waypoints.extend(
        (
            HorizonWaypoint(State.MICRO_LIFT, 0, targets.for_state(State.MICRO_LIFT)),
            HorizonWaypoint(State.LIFT, 0, targets.for_state(State.LIFT)),
        )
    )

    first = solve_horizon(
        ik,
        tuple(waypoints),
        (0.0, 0.0, 0.0, 0.0, 0.0),
        position_tolerance_m=template.position_tolerance_m,
        orientation_tolerance_rad=max(template.orientation_tolerance_rad),
        beam_width=3,
    )
    second = solve_horizon(
        ik,
        tuple(waypoints),
        (0.0, 0.0, 0.0, 0.0, 0.0),
        position_tolerance_m=template.position_tolerance_m,
        orientation_tolerance_rad=max(template.orientation_tolerance_rad),
        beam_width=3,
    )

    assert first.paths
    assert len(first.paths[0].steps) == 9
    assert first.paths[0] == second.paths[0]
    assert first.paths[0].steps[0].receipt.seed_source != "current_state"
    assert all(step.receipt.accepted for step in first.paths[0].steps)


class _CartesianIk:
    @staticmethod
    def forward(joints) -> PoseEvidence:
        return PoseEvidence(tuple(joints[:3]), (0.0, 0.0, 0.0, 1.0))

    @staticmethod
    def orientation_error_rad(_actual, _target) -> float:
        return 0.0


def _trajectory(points):
    return SimpleNamespace(
        joint_trajectory=SimpleNamespace(
            joint_names=list(JOINTS),
            points=[SimpleNamespace(positions=point) for point in points],
        )
    )


def test_cartesian_corridor_uses_actual_trajectory_samples_and_rejects_detour() -> None:
    start = (0.0, 0.0, 0.20, 0.0, 0.0)
    target = PoseEvidence((0.0, 0.0, 0.26), (0.0, 0.0, 0.0, 1.0))
    straight = _trajectory((start, (0.0, 0.0, 0.23, 0.0, 0.0), (0.0, 0.0, 0.26, 0.0, 0.0)))
    detour = _trajectory((start, (0.02, 0.0, 0.23, 0.0, 0.0), (0.0, 0.0, 0.26, 0.0, 0.0)))

    accepted = validate_cartesian_corridor(
        _CartesianIk(),
        straight,
        JOINTS,
        start,
        target,
        maximum_deviation_m=0.008,
        orientation_tolerance_rad=0.10,
        minimum_clearance_z_m=0.15,
    )
    rejected = validate_cartesian_corridor(
        _CartesianIk(),
        detour,
        JOINTS,
        start,
        target,
        maximum_deviation_m=0.008,
        orientation_tolerance_rad=0.10,
        minimum_clearance_z_m=0.15,
    )

    assert accepted.accepted is True
    assert accepted.sample_count == 3
    assert rejected.accepted is False
    assert rejected.failure_code == "CARTESIAN_CORRIDOR_DEVIATION"
    assert rejected.maximum_deviation_m == pytest.approx(0.02)


def _real_cache(monkeypatch):
    from so101_demo.control.moveit import deterministic_horizon

    cache_type = getattr(deterministic_horizon, "HorizonIkCache", None)
    assert cache_type is not None, "horizon-local exact cache is not implemented"
    ik = UnderactuatedPoseIk.from_urdf(URDF, JOINTS, "world", "so101_tcp")
    calls = {"solve": 0, "forward": 0}
    for name in calls:
        original = getattr(ik, name)

        def counted(*args, _name=name, _original=original, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(ik, name, counted)
    return ik, cache_type(ik), calls


def test_horizon_cache_reuses_real_exact_requests_but_separates_all_inputs(monkeypatch) -> None:
    import math

    ik, cache, calls = _real_cache(monkeypatch)
    seed = (0.0,) * 5
    target = ik.forward(seed)
    kwargs = {"position_tolerance_m": 0.002, "orientation_tolerance_rad": 0.10}
    first = cache.solve(target, seed, **kwargs)
    assert cache.solve(target, seed, **kwargs) == first
    assert calls["solve"] == 1
    cache.solve(target, seed, **{**kwargs, "position_tolerance_m": 0.003})
    cache.solve(target, seed, **{**kwargs, "orientation_tolerance_rad": 0.11})
    cache.solve(target, (-0.0, *seed[1:]), **kwargs)
    cache.solve(target, (math.nextafter(0.0, 1.0), *seed[1:]), **kwargs)
    moved = PoseEvidence((math.nextafter(target.position_m[0], 1.0), *target.position_m[1:]), target.orientation_xyzw)
    cache.solve(moved, seed, **kwargs)
    flipped = PoseEvidence(target.position_m, tuple(-x for x in target.orientation_xyzw))
    cache.solve(flipped, seed, **kwargs)
    assert calls["solve"] == 7


def test_horizon_cache_forward_is_exact_and_local(monkeypatch) -> None:
    ik, cache, calls = _real_cache(monkeypatch)
    seed = (0.0,) * 5
    first = cache.forward(seed)
    assert cache.forward(seed) == first
    assert calls["forward"] == 1
    cache.forward((-0.0, *seed[1:]))
    assert calls["forward"] == 2
    assert type(cache)(ik).forward(seed) == first
    assert calls["forward"] == 3
    assert cache.joint_limits == ik.joint_limits
    assert cache.orientation_error_rad(first, first) == ik.orientation_error_rad(first, first)


def test_horizon_cache_preserves_real_ik_rejection_without_retaining_tracebacks(monkeypatch) -> None:
    from so101_demo.control.moveit.underactuated_ik import UnderactuatedIkError

    _ik, cache, calls = _real_cache(monkeypatch)
    target = PoseEvidence((1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0))
    errors = []
    for _ in range(2):
        with pytest.raises(UnderactuatedIkError) as caught:
            cache.solve(target, (0.0,) * 5, position_tolerance_m=0.002, orientation_tolerance_rad=0.10)
        errors.append(caught.value)
    assert errors[0].args == errors[1].args
    assert errors[0] is not errors[1]
    assert str(errors[1]).startswith("DYNAMIC_IK_RESIDUAL_EXCEEDED:")
    assert calls["solve"] == 1


def test_horizon_cache_does_not_cache_unexpected_solver_exceptions(monkeypatch) -> None:
    ik, cache, _calls = _real_cache(monkeypatch)
    seed = (0.0,) * 5
    target = ik.forward(seed)
    real_solve = ik.solve
    calls = 0

    def transient(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient dependency failure")
        return real_solve(*args, **kwargs)

    monkeypatch.setattr(ik, "solve", transient)
    kwargs = {"position_tolerance_m": 0.002, "orientation_tolerance_rad": 0.10}
    with pytest.raises(RuntimeError, match="transient dependency failure"):
        cache.solve(target, seed, **kwargs)
    assert cache.solve(target, seed, **kwargs) == seed
    assert calls == 2
