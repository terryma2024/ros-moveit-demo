from pathlib import Path

import pytest

from so101_mujoco_demo_py.staged_approach import (
    APPROACH_PHASES,
    JointObservation,
    JointStabilityWindow,
    load_staged_policy,
    maximum_joint_error,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
POLICY = PACKAGE_ROOT / "config/motion_policies/light_cup_wall_pick.yaml"


def sample(at: float, position: float = 0.0, speed: float = 0.0) -> JointObservation:
    return JointObservation(
        at,
        (position, 0.0, 0.0, 0.0, 0.0, 0.465038),
        (speed, 0.0, 0.0, 0.0, 0.0, 0.0),
    )


def test_policy_requires_preopen_then_the_two_gazebo_approach_phases() -> None:
    policy, digest = load_staged_policy(POLICY)

    assert len(digest) == 64
    assert policy.preopen_q6 == pytest.approx(0.465038)
    assert tuple(phase.name for phase in policy.phases) == APPROACH_PHASES
    assert tuple(len(phase.waypoints) for phase in policy.phases) == (10, 5)
    assert policy.maximum_replans_per_segment == 2


def test_stability_window_requires_duration_speed_span_and_freshness() -> None:
    window = JointStabilityWindow()
    for index in range(6):
        window.append(sample(10.0 + 0.05 * index, position=0.0001 * index))

    assert window.stable(
        now_s=10.26,
        window_s=0.20,
        max_age_s=0.20,
        max_speed_rad_s=0.03,
        max_span_rad=0.003,
    )
    assert not window.stable(
        now_s=10.60,
        window_s=0.20,
        max_age_s=0.20,
        max_speed_rad_s=0.03,
        max_span_rad=0.003,
    )
    window.append(sample(10.65, speed=0.04))
    assert not window.stable(
        now_s=10.65,
        window_s=0.20,
        max_age_s=0.20,
        max_speed_rad_s=0.03,
        max_span_rad=0.003,
    )


def test_maximum_joint_error_is_fail_closed_for_length_mismatch() -> None:
    assert maximum_joint_error((0.0, 0.1), (0.0, 0.2)) == pytest.approx(0.1)
    assert maximum_joint_error((0.0,), (0.0, 0.0)) == pytest.approx(float("inf"))
