import math

from so101_gazebo_demo.physical_outcome import (
    FinalPlacementSample,
    evaluate_final_placement,
)
from so101_gazebo_demo.policy_config import PhysicalOutcomeConfig, PlanningShadowConfig


def policy() -> PhysicalOutcomeConfig:
    return PhysicalOutcomeConfig(
        intended_support_collision="table::table_top::collision",
        minimum_support_contact_depth_m=-1e-7,
        final_target_min_xy_m=(-0.085, -0.255),
        final_target_max_xy_m=(-0.075, -0.245),
        support_height_range_m=(0.155, 0.175),
        max_upright_tilt_rad=0.08726646259971647,
        max_linear_speed_m_s=0.001,
        max_angular_speed_rad_s=0.05,
        consecutive_samples=5,
        minimum_stable_duration_s=0.20,
        sample_interval_s=0.05,
        settle_timeout_s=2.0,
        max_observation_age_s=0.10,
        max_telemetry_samples=40,
        catastrophic_workspace_bounds_m=(-0.21, -0.46, 0.12, 0.21, 0.06, 0.30),
        max_relative_position_drift_m=0.005,
        max_relative_orientation_drift_rad=0.070,
        planning_shadow=PlanningShadowConfig(0.005, 0.070, 0.10),
    )


def sample(index: int, *, epoch: str = "release-2", x: float = -0.08,
           supported: bool = True, gripper: bool = False) -> FinalPlacementSample:
    return FinalPlacementSample(
        release_epoch_id=epoch,
        receipt_sequence=101 + index,
        source_timestamp_s=10.0 + index * 0.05,
        observed_monotonic_s=10.0 + index * 0.05,
        pose_xyz_xyzw=(x, -0.25, 0.165, 0.0, 0.0, 0.0, 1.0),
        support_contact=supported,
        gripper_contact=gripper,
        gazebo_detached=True,
        moveit_detached=True,
        controller_healthy=True,
        safety_healthy=True,
        shadow_divergence_healthy=True,
    )


def test_accepts_five_stable_post_release_samples() -> None:
    result = evaluate_final_placement(
        tuple(sample(index) for index in range(5)), policy(), "release-2", 100,
    )
    assert result.success
    assert result.failure_code is None
    assert result.sample_count == 5
    assert result.duration_s == 0.20
    assert result.max_linear_speed_m_s == 0.0
    assert result.max_angular_speed_rad_s == 0.0


def test_never_reuses_pre_release_or_other_epoch_samples() -> None:
    samples = (sample(0, epoch="release-1"),) + tuple(sample(index) for index in range(4))
    result = evaluate_final_placement(samples, policy(), "release-2", 100)
    assert not result.success
    assert result.failure_code == "FINAL_STALE_EVIDENCE"
    assert result.sample_count == 4


def test_reports_out_of_region_and_retains_bounded_metrics() -> None:
    result = evaluate_final_placement(
        tuple(sample(index, x=-0.09) for index in range(5)), policy(), "release-2", 100,
    )
    assert not result.success
    assert result.failure_code == "FINAL_OUT_OF_REGION"
    assert result.metrics["final_x_m"] == -0.09
    assert len(result.telemetry) == 5


def test_failure_precedence_keeps_safety_before_contact_and_motion() -> None:
    samples = list(sample(index, supported=False, gripper=True) for index in range(5))
    samples[-1] = FinalPlacementSample(
        **{**samples[-1].as_dict(), "safety_healthy": False},
    )
    result = evaluate_final_placement(tuple(samples), policy(), "release-2", 100)
    assert result.failure_code == "FINAL_SAFETY_FAILURE"


def test_rejects_nonfinite_and_nonmonotonic_timestamps() -> None:
    samples = list(sample(index) for index in range(5))
    samples[-1] = FinalPlacementSample(
        **{**samples[-1].as_dict(), "source_timestamp_s": math.nan},
    )
    assert evaluate_final_placement(
        tuple(samples), policy(), "release-2", 100,
    ).failure_code == "FINAL_STALE_EVIDENCE"


def test_distinguishes_contact_shadow_detach_tilt_and_motion_failures() -> None:
    base = [sample(index) for index in range(5)]
    cases = (
        ({"support_contact": False}, "FINAL_UNSUPPORTED"),
        ({"gripper_contact": True}, "FINAL_GRIPPER_CONTACT"),
        ({"shadow_divergence_healthy": False}, "FINAL_PLANNING_SHADOW_DIVERGENCE"),
        ({"moveit_detached": False}, "FINAL_SAFETY_FAILURE"),
        ({"pose_xyz_xyzw": (-0.08, -0.25, 0.165, 0.1, 0.0, 0.0, 0.994987437)}, "FINAL_TIPPED"),
    )
    for change, expected in cases:
        changed = list(base)
        changed[-1] = FinalPlacementSample(**{**changed[-1].as_dict(), **change})
        assert evaluate_final_placement(
            tuple(changed), policy(), "release-2", 100,
        ).failure_code == expected

    moving = tuple(sample(index, x=-0.08 + index * 0.0001) for index in range(5))
    assert evaluate_final_placement(
        moving, policy(), "release-2", 100,
    ).failure_code == "FINAL_STILL_MOVING"
