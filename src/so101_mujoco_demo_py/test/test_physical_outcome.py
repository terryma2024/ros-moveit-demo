import math

from so101_mujoco_demo_py.physical_outcome import (
    FinalPlacementSample,
    PhysicalOutcomePolicy,
    PlanningShadowPolicy,
    evaluate_final_placement,
)


def policy() -> PhysicalOutcomePolicy:
    return PhysicalOutcomePolicy(
        intended_support_collision="table_top",
        minimum_support_signed_distance_m=-1e-7,
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
        planning_shadow=PlanningShadowPolicy(0.005, 0.070, 0.10),
    )


def sample(
    index: int,
    *,
    epoch: str = "release-2",
    x: float = -0.08,
    supported: bool = True,
    gripper: bool = False,
) -> FinalPlacementSample:
    return FinalPlacementSample(
        release_epoch_id=epoch,
        receipt_sequence=101 + index,
        source_timestamp_s=10.0 + index * 0.05,
        observed_monotonic_s=10.0 + index * 0.05,
        pose_xyz_xyzw=(x, -0.25, 0.165, 0.0, 0.0, 0.0, 1.0),
        support_contact=supported,
        gripper_contact=gripper,
        simulator_detached=True,
        moveit_detached=True,
        controller_healthy=True,
        safety_healthy=True,
        shadow_divergence_healthy=True,
    )


def test_accepts_five_stable_post_release_samples_with_preserved_schema() -> None:
    result = evaluate_final_placement(
        tuple(sample(index) for index in range(5)), policy(), "release-2", 100
    )
    assert result.success
    assert result.failure_code is None
    assert result.sample_count == 5
    assert result.duration_s == 0.20
    assert result.max_linear_speed_m_s == 0.0
    assert result.max_angular_speed_rad_s == 0.0


def test_sample_preserves_frozen_gazebo_detached_wire_schema() -> None:
    payload = sample(0).as_dict()
    assert tuple(payload) == (
        "release_epoch_id",
        "receipt_sequence",
        "source_timestamp_s",
        "observed_monotonic_s",
        "pose_xyz_xyzw",
        "support_contact",
        "gripper_contact",
        "gazebo_detached",
        "moveit_detached",
        "controller_healthy",
        "safety_healthy",
        "shadow_divergence_healthy",
    )
    assert payload["gazebo_detached"] is True
    assert "simulator_detached" not in payload
    restored = FinalPlacementSample(**payload)
    assert restored.gazebo_detached is True
    assert restored.simulator_detached is True


def test_distinct_simulation_and_receipt_clock_epochs_are_valid() -> None:
    samples = tuple(
        FinalPlacementSample(
            **{
                **sample(index).as_dict(),
                "observed_monotonic_s": 1000.0 + index * 0.05,
            }
        )
        for index in range(5)
    )
    assert evaluate_final_placement(samples, policy(), "release-2", 100).success


def test_rejects_stale_epoch_and_nonfinite_timestamp() -> None:
    samples = (sample(0, epoch="release-1"),) + tuple(sample(index) for index in range(4))
    assert evaluate_final_placement(samples, policy(), "release-2", 100).failure_code == (
        "FINAL_STALE_EVIDENCE"
    )
    invalid = list(sample(index) for index in range(5))
    invalid[-1] = FinalPlacementSample(**{**invalid[-1].as_dict(), "source_timestamp_s": math.nan})
    assert (
        evaluate_final_placement(tuple(invalid), policy(), "release-2", 100).failure_code
        == "FINAL_STALE_EVIDENCE"
    )


def test_failure_precedence_and_distinct_final_codes_are_preserved() -> None:
    base = [sample(index) for index in range(5)]
    cases = (
        ({"safety_healthy": False, "gripper_contact": True}, "FINAL_SAFETY_FAILURE"),
        ({"shadow_divergence_healthy": False}, "FINAL_PLANNING_SHADOW_DIVERGENCE"),
        ({"simulator_detached": False}, "FINAL_SAFETY_FAILURE"),
        ({"gripper_contact": True}, "FINAL_GRIPPER_CONTACT"),
        ({"support_contact": False}, "FINAL_UNSUPPORTED"),
        ({"pose_xyz_xyzw": (-0.09, -0.25, 0.165, 0.0, 0.0, 0.0, 1.0)}, "FINAL_OUT_OF_REGION"),
        (
            {"pose_xyz_xyzw": (-0.08, -0.25, 0.165, 0.1, 0.0, 0.0, 0.994987437)},
            "FINAL_TIPPED",
        ),
    )
    for change, expected in cases:
        changed = list(base)
        changed[-1] = FinalPlacementSample(**{**changed[-1].as_dict(), **change})
        assert (
            evaluate_final_placement(tuple(changed), policy(), "release-2", 100).failure_code
            == expected
        )

    moving = tuple(sample(index, x=-0.08 + index * 0.0001) for index in range(5))
    assert (
        evaluate_final_placement(moving, policy(), "release-2", 100).failure_code
        == "FINAL_STILL_MOVING"
    )
