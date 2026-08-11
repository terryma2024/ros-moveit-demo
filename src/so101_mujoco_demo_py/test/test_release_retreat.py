from pathlib import Path

import pytest

from so101_mujoco_demo_py.release_retreat import (
    ReleaseRetreatPolicy,
    load_release_retreat_policy,
    release_retreat_translations,
    residual_contact_within_bounds,
)

CONFIG = (
    Path(__file__).resolve().parents[1] / "config" / "motion_policies" / "light_cup_wall_pick.yaml"
)


def test_mujoco_policy_uses_outcome_first_release_retreat() -> None:
    policy = load_release_retreat_policy(CONFIG)

    assert policy == ReleaseRetreatPolicy(
        radial_separation_m=0.010,
        vertical_clearance_m=0.060,
        orientation_tolerance_rad=0.15,
        position_tolerance_m=0.001,
        velocity_scaling=0.03,
        acceleration_scaling=0.03,
        residual_contact_grace_s=0.05,
        max_residual_fingertip_force_n=0.05,
        max_released_cup_displacement_m=0.003,
    )


def test_release_retreat_moves_radially_away_then_up() -> None:
    policy = ReleaseRetreatPolicy(
        radial_separation_m=0.010,
        vertical_clearance_m=0.060,
        orientation_tolerance_rad=0.15,
        position_tolerance_m=0.001,
        velocity_scaling=0.03,
        acceleration_scaling=0.03,
        residual_contact_grace_s=0.05,
        max_residual_fingertip_force_n=0.05,
        max_released_cup_displacement_m=0.003,
    )

    translations = release_retreat_translations(
        tcp_position_m=(0.003, 0.004, 0.200),
        cup_position_m=(0.0, 0.0, 0.165),
        policy=policy,
    )

    assert translations[0] == pytest.approx((0.006, 0.008, 0.0))
    assert translations[1] == pytest.approx((0.0, 0.0, 0.060))


@pytest.mark.parametrize("distance_m", [0.0, -0.001, 0.031])
def test_release_retreat_rejects_unbounded_radial_distance(distance_m: float) -> None:
    with pytest.raises(ValueError, match="radial separation"):
        ReleaseRetreatPolicy(
            radial_separation_m=distance_m,
            vertical_clearance_m=0.060,
            orientation_tolerance_rad=0.15,
            position_tolerance_m=0.001,
            velocity_scaling=0.03,
            acceleration_scaling=0.03,
            residual_contact_grace_s=0.05,
            max_residual_fingertip_force_n=0.05,
            max_released_cup_displacement_m=0.003,
        )


def test_release_retreat_requires_a_defined_radial_direction() -> None:
    policy = ReleaseRetreatPolicy(
        radial_separation_m=0.010,
        vertical_clearance_m=0.060,
        orientation_tolerance_rad=0.15,
        position_tolerance_m=0.001,
        velocity_scaling=0.03,
        acceleration_scaling=0.03,
        residual_contact_grace_s=0.05,
        max_residual_fingertip_force_n=0.05,
        max_released_cup_displacement_m=0.003,
    )

    with pytest.raises(RuntimeError, match="radial direction"):
        release_retreat_translations(
            tcp_position_m=(0.0, 0.0, 0.200),
            cup_position_m=(0.0, 0.0, 0.165),
            policy=policy,
        )


def test_residual_contact_is_force_and_displacement_bounded() -> None:
    policy = load_release_retreat_policy(CONFIG)

    assert residual_contact_within_bounds(0.0031, 0.001, policy)
    assert not residual_contact_within_bounds(0.051, 0.001, policy)
    assert not residual_contact_within_bounds(0.0031, 0.0031, policy)
