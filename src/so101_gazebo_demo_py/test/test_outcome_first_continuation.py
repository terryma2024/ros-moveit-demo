from types import SimpleNamespace

import pytest

from so101_gazebo_demo_py import live_execute
from so101_gazebo_demo_py.gazebo.observer import ContactPair
from so101_gazebo_demo_py.test_support.live_attachment import PoseSample
from so101_gazebo_demo_py.test_support.ros_gazebo_backend import (
    gripper_result_acceptable,
)


def sample(x: float, y: float, z: float) -> PoseSample:
    return PoseSample(
        object_xyz=(x, y, z),
        tcp_xyz=(0.020, -0.263, 0.200 + z),
    )


def contact(*, bilateral: bool, depth: float | None):
    return SimpleNamespace(
        bilateral=bilateral,
        fixed_finger=bilateral,
        moving_jaw=bilateral,
        max_moving_pad_penetration_m=depth,
    )


def test_penetration_is_telemetry_when_cup_reaches_intermediate_position() -> None:
    assert hasattr(live_execute, "evaluate_continuation")
    result = live_execute.evaluate_continuation(
        before=sample(0.0, 0.0, 0.165),
        after=sample(0.0001, 0.0, 0.167),
        commanded_object_delta_m=(0.0, 0.0, 0.002),
        position_tolerance_m=0.001,
        arm_stable=True,
        contact_evidence=contact(bilateral=True, depth=0.0018),
        q6_position=-0.055,
    )

    assert result.can_continue
    assert result.failure_code is None
    assert result.telemetry["max_moving_pad_penetration_m"] == 0.0018


def test_missing_bilateral_contact_is_telemetry_when_cup_result_succeeds() -> None:
    result = live_execute.evaluate_continuation(
        before=sample(0.0, 0.0, 0.165),
        after=sample(0.0, 0.0, 0.167),
        commanded_object_delta_m=(0.0, 0.0, 0.002),
        position_tolerance_m=0.001,
        arm_stable=True,
        contact_evidence=contact(bilateral=False, depth=None),
        q6_position=-0.047,
    )

    assert result.can_continue
    assert result.telemetry["bilateral_contact"] is False


def test_cup_target_miss_blocks_continuation() -> None:
    result = live_execute.evaluate_continuation(
        before=sample(0.0, 0.0, 0.165),
        after=sample(0.0, 0.0, 0.1652),
        commanded_object_delta_m=(0.0, 0.0, 0.002),
        position_tolerance_m=0.001,
        arm_stable=True,
        contact_evidence=contact(bilateral=True, depth=0.0004),
        q6_position=-0.053,
    )

    assert not result.can_continue
    assert result.failure_code == "CUP_INTERMEDIATE_POSITION"


def test_unstable_arm_blocks_continuation() -> None:
    result = live_execute.evaluate_continuation(
        before=sample(0.0, 0.0, 0.165),
        after=sample(0.0, 0.0, 0.167),
        commanded_object_delta_m=(0.0, 0.0, 0.002),
        position_tolerance_m=0.001,
        arm_stable=False,
        contact_evidence=contact(bilateral=True, depth=0.0004),
        q6_position=-0.053,
    )

    assert not result.can_continue
    assert result.failure_code == "ARM_UNSTABLE"


def test_non_finite_cup_pose_blocks_continuation() -> None:
    result = live_execute.evaluate_continuation(
        before=sample(0.0, 0.0, 0.165),
        after=sample(float("nan"), 0.0, 0.167),
        commanded_object_delta_m=(0.0, 0.0, 0.002),
        position_tolerance_m=0.001,
        arm_stable=True,
        contact_evidence=contact(bilateral=False, depth=None),
        q6_position=-0.047,
    )

    assert not result.can_continue
    assert result.failure_code == "CUP_POSE_NONFINITE"


def test_micro_lift_continues_when_penetration_telemetry_exceeds_old_gate() -> None:
    class Backend:
        def __init__(self) -> None:
            self.sample_count = 0

        def sample(self) -> PoseSample:
            self.sample_count += 1
            z = 0.165 if self.sample_count == 1 else 0.167
            return sample(0.0, 0.0, z)

        def contacts(self) -> tuple[ContactPair, ...]:
            return (
                ContactPair(
                    "plastic_cup::body::wall_near",
                    "fixed_fingertip_pad_collision_001",
                    (0.0004,),
                ),
                ContactPair(
                    "plastic_cup::body::wall_near",
                    "moving_fingertip_pad_collision_001",
                    (0.0018,),
                ),
            )

    result = live_execute.verify_physical_micro_lift(
        Backend(), execute=lambda delta: (3, 0.200),
    )

    assert result[0] == pytest.approx(0.002)


def test_full_grasp_attempt_reaches_cup_result_gate_without_bilateral_contact() -> None:
    class Backend:
        def __init__(self) -> None:
            self.sample_count = 0

        def move_gripper(self, target: float) -> None:
            del target

        def sample(self) -> PoseSample:
            self.sample_count += 1
            z = 0.165 if self.sample_count == 1 else 0.167
            return sample(0.0, 0.0, z)

        def contacts(self) -> tuple[ContactPair, ...]:
            return (
                ContactPair(
                    "plastic_cup::body::wall_near",
                    "fixed_fingertip_pad_collision_001",
                    (0.0004,),
                ),
            )

    contact_result, physical, attempts, final_target = (
        live_execute.run_bounded_physical_grasp_attempts(
            Backend(),
            seating_target=-0.053,
            preopen_q6=0.465,
            q6_safe_lower=-0.0596,
            max_attempts=1,
            execute=lambda delta: (3, 0.200),
        )
    )

    assert not contact_result.bilateral
    assert physical[0] == pytest.approx(0.002)
    assert physical[6].can_continue
    assert attempts == 1
    assert final_target == -0.053


def test_contact_stopped_gripper_result_defers_to_cup_outcome_gate() -> None:
    output = "error_code: -5\nGoal finished with status: ABORTED"

    assert gripper_result_acceptable(output, bilateral=False)
