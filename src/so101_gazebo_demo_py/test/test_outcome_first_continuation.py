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


def test_relaxed_micro_lift_accepts_bounded_physical_slip() -> None:
    result = live_execute.evaluate_continuation(
        before=sample(0.0, 0.0, 0.165),
        after=sample(0.0, 0.003845, 0.16649),
        commanded_object_delta_m=(0.0, 0.0, 0.002),
        position_tolerance_m=0.006,
        minimum_axial_progress_m=0.001,
        maximum_lateral_drift_m=0.006,
        arm_stable=True,
        contact_evidence=contact(bilateral=True, depth=0.0011),
        q6_position=-0.052,
    )

    assert result.can_continue


def test_relaxed_micro_lift_still_requires_positive_cup_lift() -> None:
    result = live_execute.evaluate_continuation(
        before=sample(0.0, 0.0, 0.165),
        after=sample(0.0, 0.0, 0.1655),
        commanded_object_delta_m=(0.0, 0.0, 0.002),
        position_tolerance_m=0.006,
        minimum_axial_progress_m=0.001,
        maximum_lateral_drift_m=0.006,
        arm_stable=True,
        contact_evidence=contact(bilateral=True, depth=0.0011),
        q6_position=-0.052,
    )

    assert not result.can_continue
    assert result.failure_code == "CUP_INSUFFICIENT_LIFT"


def test_relaxed_micro_lift_still_bounds_lateral_cup_motion() -> None:
    result = live_execute.evaluate_continuation(
        before=sample(0.0, 0.0, 0.165),
        after=sample(0.0, 0.0061, 0.1665),
        commanded_object_delta_m=(0.0, 0.0, 0.002),
        position_tolerance_m=0.0065,
        minimum_axial_progress_m=0.001,
        maximum_lateral_drift_m=0.006,
        arm_stable=True,
        contact_evidence=contact(bilateral=True, depth=0.0011),
        q6_position=-0.052,
    )

    assert not result.can_continue
    assert result.failure_code == "CUP_LATERAL_DRIFT"


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


def test_explicit_three_attempt_grasp_strategy_can_succeed_on_third_outcome() -> None:
    class Backend:
        def __init__(self) -> None:
            self.sample_count = 0
            self.gripper_targets = []

        def move_gripper(self, target: float) -> None:
            self.gripper_targets.append(target)

        def sample(self) -> PoseSample:
            self.sample_count += 1
            attempt = (self.sample_count + 1) // 2
            lifted = self.sample_count % 2 == 0 and attempt == 3
            return sample(0.0, 0.0, 0.167 if lifted else 0.165)

        def contacts(self):
            return ()

    execute_calls = []
    def execute(delta: float, local_x_m: float = 0.0):
        execute_calls.append((delta, local_x_m))
        return 3, 0.2

    _, result, attempts, _ = live_execute.run_bounded_physical_grasp_attempts(
        Backend(), seating_target=-0.053, preopen_q6=0.465,
        q6_safe_lower=-0.0596, max_attempts=3, execute=execute,
    )

    assert attempts == 3
    assert result[0] == pytest.approx(0.002)
    assert execute_calls.count((-0.002, 0.0)) == 2
    assert execute_calls.count((0.0, -0.0002)) == 2


def test_default_grasp_strategy_stops_after_one_failed_outcome() -> None:
    class Backend:
        def __init__(self) -> None:
            self.sample_count = 0

        def move_gripper(self, target: float) -> None:
            del target

        def sample(self) -> PoseSample:
            self.sample_count += 1
            attempt = (self.sample_count + 1) // 2
            lifted = self.sample_count % 2 == 0 and attempt == 3
            return sample(0.0, 0.0, 0.167 if lifted else 0.165)

        def contacts(self):
            return ()

    backend = Backend()

    with pytest.raises(RuntimeError, match="physical micro-lift failed"):
        live_execute.run_bounded_physical_grasp_attempts(
            backend,
            seating_target=-0.053,
            preopen_q6=0.465,
            q6_safe_lower=-0.0596,
            execute=lambda delta, local_x_m=0.0: (3, 0.2),
        )

    assert backend.sample_count == 2


def test_contact_stopped_gripper_result_defers_to_cup_outcome_gate() -> None:
    output = "error_code: -5\nGoal finished with status: ABORTED"

    assert gripper_result_acceptable(output, bilateral=False)


def test_same_run_place_alignment_uses_cup_error_and_returns_reverse_path() -> None:
    samples = iter((
        sample(-0.097, -0.256, 0.165),
        sample(-0.081, -0.251, 0.165),
    ))
    commands = []

    class Backend:
        def sample(self):
            return next(samples)

    def execute(delta, orientation_tolerance_rad):
        commands.append((delta, orientation_tolerance_rad))
        return 12, (0.39, 0.49, 0.11, 1.0, 0.002)

    aligned, reverse_waypoints, telemetry = live_execute.align_cup_for_release(
        Backend(), (-0.080, -0.250, 0.165), execute=execute,
    )

    assert aligned.object_xyz == pytest.approx((-0.081, -0.251, 0.165))
    assert commands[0][0] == pytest.approx((0.017, 0.006, 0.0))
    assert commands[0][1] == 0.15
    assert reverse_waypoints == ((0.39, 0.49, 0.11, 1.0, 0.002),)
    assert telemetry[-1]["after_xy_error_m"] < telemetry[-1]["before_xy_error_m"]


def test_release_alignment_target_compensates_observed_settling_drift() -> None:
    assert live_execute.release_alignment_target(
        (-0.080, -0.250, 0.165)
    ) == pytest.approx((-0.075, -0.2445, 0.165))


def test_same_run_place_alignment_allows_pre_release_drop_height() -> None:
    class Backend:
        def sample(self):
            return sample(-0.081, -0.251, 0.1757)

    aligned, reverse_waypoints, telemetry = live_execute.align_cup_for_release(
        Backend(), (-0.080, -0.250, 0.165),
        execute=lambda *_args: pytest.fail("already-aligned cup must not move"),
    )

    assert aligned.object_xyz == pytest.approx((-0.081, -0.251, 0.1757))
    assert reverse_waypoints == ()
    assert telemetry == ()


def test_same_run_place_alignment_defers_pre_release_tilt_to_final_outcome() -> None:
    class Backend:
        def sample(self):
            return PoseSample(
                object_xyz=(-0.081, -0.251, 0.175),
                tcp_xyz=(0.020, -0.263, 0.375),
                object_xyzw=(0.22427, 0.0, 0.0, 0.97453),
            )

    aligned, reverse_waypoints, telemetry = live_execute.align_cup_for_release(
        Backend(), (-0.080, -0.250, 0.165),
        execute=lambda *_args: pytest.fail("already-aligned cup must not move"),
    )

    assert aligned.object_xyzw == pytest.approx((0.22427, 0.0, 0.0, 0.97453))
    assert reverse_waypoints == ()
    assert telemetry == ()


def test_same_run_place_alignment_rejects_implausible_pre_release_height() -> None:
    class Backend:
        def sample(self):
            return sample(-0.081, -0.251, 0.1951)

    with pytest.raises(RuntimeError, match="pre-release height outside plausibility"):
        live_execute.align_cup_for_release(
            Backend(), (-0.080, -0.250, 0.165),
            execute=lambda *_args: pytest.fail("implausible pose must not move"),
        )


def test_same_run_place_alignment_fails_closed_outside_translation_bound() -> None:
    class Backend:
        def sample(self):
            return sample(-0.1201, -0.250, 0.165)

    with pytest.raises(RuntimeError, match="place alignment correction exceeds bound"):
        live_execute.align_cup_for_release(
            Backend(), (-0.080, -0.250, 0.165),
            execute=lambda *_args: pytest.fail("out-of-bound correction must not execute"),
        )


def test_same_run_place_alignment_allows_small_intermediate_progress() -> None:
    samples = iter((
        sample(-0.089, -0.250, 0.165),
        sample(-0.0885, -0.250, 0.165),
        sample(-0.081, -0.250, 0.165),
    ))

    class Backend:
        def sample(self):
            return next(samples)

    aligned, reverse_waypoints, telemetry = live_execute.align_cup_for_release(
        Backend(), (-0.080, -0.250, 0.165),
        execute=lambda *_args: (12, (0.39, 0.49, 0.11, 1.0, 0.002)),
    )

    assert aligned.object_xyz == pytest.approx((-0.081, -0.250, 0.165))
    assert len(reverse_waypoints) == 2
    assert len(telemetry) == 2


def test_same_run_place_alignment_fails_after_attempt_budget() -> None:
    samples = iter((
        sample(-0.097, -0.256, 0.165),
        sample(-0.0968, -0.2559, 0.165),
        sample(-0.0966, -0.2558, 0.165),
    ))

    class Backend:
        def sample(self):
            return next(samples)

    with pytest.raises(RuntimeError, match="did not converge within 2 attempts"):
        live_execute.align_cup_for_release(
            Backend(), (-0.080, -0.250, 0.165),
            execute=lambda *_args: (12, (0.39, 0.49, 0.11, 1.0, 0.002)),
        )
