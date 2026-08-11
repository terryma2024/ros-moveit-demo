from pathlib import Path

import pytest
import yaml

from so101_mujoco_demo_py.motion.calibration import (
    ApproachObservation,
    ApproachSafetyAbort,
    CalibrationApproachPolicy,
    CalibrationApproachRunner,
    PoseTrajectory,
    PoseTrajectoryPoint,
    derive_approach_targets,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_contact_calibration_motion_module_exists() -> None:
    assert (PACKAGE_ROOT / "so101_mujoco_demo_py/motion/calibration.py").is_file()


def test_motion_policy_selects_running_pose_constrained_calibration_approach() -> None:
    document = yaml.safe_load(
        (PACKAGE_ROOT / "config/motion_policies/light_cup_wall_pick.yaml").read_text()
    )
    approach = document["contact_calibration_approach"]

    assert approach["planner"] == "pose_constrained"
    assert approach["frame_id"] == "world"
    assert approach["tcp_link"] == "so101_tcp"
    assert approach["pause_physics"] is False
    assert approach["maximum_replans"] == 1
    assert approach["allow_precontact_fingertip_contact"] is False
    assert approach["pregrasp_offset_m"][2] > approach["contact_offset_m"][2]


POLICY = CalibrationApproachPolicy(
    arm_joints=("1", "2", "3", "4", "5"),
    stable_home_rad=(0.0, 0.0, 0.0, 0.0, 0.0),
    pregrasp_offset_m=(0.0006766838, 0.0171789788, 0.0756306106),
    contact_offset_m=(0.0006766838, 0.0171789788, 0.0356306106),
    tcp_orientation_xyzw=(-0.0102659913, -0.0102629866, -0.7067526865, 0.7073117563),
    orientation_tolerance_rad=(0.01, 0.01, 0.01),
    start_tolerance_rad=0.01,
    home_tolerance_rad=0.01,
    max_joint_speed_rad_s=0.02,
    max_lateral_deviation_m=0.003,
    max_cup_displacement_m=0.003,
    max_diagnostic_force_n=11.60,
    max_receipt_age_s=0.2,
    max_replans=1,
)


def observation(
    *,
    positions=(0.0, 0.0, 0.0, 0.0, 0.0),
    tcp=(0.0206766838, -0.2628210212, 0.2406306106),
    cup=(0.02, -0.28, 0.165),
    contacts=frozenset(),
    paused=False,
    session="session-a",
    epoch=4,
    sequence=1,
    received_at=9.95,
    force_n=0.0,
):
    return ApproachObservation(
        joint_names=("1", "2", "3", "4", "5"),
        joint_positions_rad=positions,
        joint_velocities_rad_s=(0.0, 0.0, 0.0, 0.0, 0.0),
        gripper_position_rad=0.465038,
        tcp_position_world_m=tcp,
        cup_position_world_m=cup,
        fingertip_contacts=contacts,
        forbidden_contacts=frozenset(),
        maximum_normal_force_n=force_n,
        paused=paused,
        simulation_session_id=session,
        reset_epoch=epoch,
        publisher_sequence=sequence,
        received_monotonic_s=received_at,
    )


class Observer:
    def __init__(self, values):
        self.values = iter(values)
        self.last = None

    def __call__(self):
        try:
            self.last = next(self.values)
        except StopIteration:
            pass
        return self.last


def trajectory(start, target, orientation, *, lateral=0.0):
    midpoint = (
        (start.tcp_position_world_m[0] + target[0]) / 2.0 + lateral,
        (start.tcp_position_world_m[1] + target[1]) / 2.0,
        (start.tcp_position_world_m[2] + target[2]) / 2.0,
    )
    return PoseTrajectory(
        start.joint_names,
        (
            PoseTrajectoryPoint(start.joint_positions_rad, start.tcp_position_world_m, orientation),
            PoseTrajectoryPoint(start.joint_positions_rad, midpoint, orientation),
            PoseTrajectoryPoint(start.joint_positions_rad, target, orientation),
        ),
    )


def test_targets_are_derived_from_current_fixed_cup_pose() -> None:
    targets = derive_approach_targets((0.02, -0.28, 0.165), POLICY)

    assert targets.pregrasp_position_m == pytest.approx((0.0206766838, -0.2628210212, 0.2406306106))
    assert targets.contact_position_m == pytest.approx((0.0206766838, -0.2628210212, 0.2006306106))
    assert targets.orientation_xyzw == POLICY.tcp_orientation_xyzw


def test_runner_executes_pregrasp_then_axial_descent_without_pause_or_contact() -> None:
    initial = observation()
    observed = Observer([initial])
    planned_targets = []
    path_constraints = []
    executed = []

    def plan(request):
        planned_targets.append(request.target_position_m)
        path_constraints.append(request.enforce_orientation_path)
        assert request.joint_names == ("1", "2", "3", "4", "5", "6")
        assert request.current_positions[-1] == pytest.approx(0.465038)
        return trajectory(observed.last, request.target_position_m, request.target_orientation_xyzw)

    def execute(candidate, monitor):
        monitor()
        executed.append(candidate)
        return True

    result = CalibrationApproachRunner(
        observed, plan, execute, POLICY, monotonic=lambda: 10.0
    ).run()

    assert result.valid is True
    assert result.replan_count == 0
    assert len(executed) == 2
    assert planned_targets[0][2] > planned_targets[1][2]
    assert path_constraints == [False, True]


def test_plan_handoff_drift_replans_once_from_new_current_state() -> None:
    home = observation(sequence=1)
    drifted = observation(positions=(0.0, 0.02, 0.0, 0.0, 0.0), sequence=2)
    observed = Observer([home, home, drifted, drifted])
    starts = []

    def plan(request):
        starts.append(request.current_positions)
        return trajectory(observed.last, request.target_position_m, request.target_orientation_xyzw)

    result = CalibrationApproachRunner(
        observed, plan, lambda _trajectory, _monitor: True, POLICY, monotonic=lambda: 10.0
    ).run(max_phases=1)

    assert result.valid is True
    assert result.replan_count == 1
    assert starts == [
        (*home.joint_positions_rad, home.gripper_position_rad),
        (*drifted.joint_positions_rad, drifted.gripper_position_rad),
    ]


def test_runner_rejects_empty_lateral_or_orientation_invalid_trajectory() -> None:
    initial = observation()
    targets = derive_approach_targets(initial.cup_position_world_m, POLICY)

    for candidate, message in (
        (PoseTrajectory(initial.joint_names, ()), "empty"),
        (
            trajectory(
                initial,
                targets.contact_position_m,
                POLICY.tcp_orientation_xyzw,
                lateral=0.01,
            ),
            "lateral",
        ),
        (
            trajectory(initial, targets.contact_position_m, (0.0, 0.0, 0.0, 1.0)),
            "orientation",
        ),
    ):
        observed = Observer([initial])
        result = CalibrationApproachRunner(
            observed,
            lambda _request, value=candidate: value,
            lambda _trajectory, _monitor: True,
            POLICY,
            monotonic=lambda: 10.0,
        ).run(max_phases=1, descend_only=True)
        assert result.valid is False
        assert message in result.reason.lower()


def test_safety_abort_never_retries_and_rejects_paused_or_early_contact() -> None:
    for unsafe, message in (
        (observation(paused=True), "paused"),
        (observation(contacts=frozenset({"left:cup"})), "contact"),
        (observation(cup=(0.024, -0.28, 0.165)), "displacement"),
        (observation(force_n=11.61), "force"),
    ):
        initial = observation()
        observed = Observer([initial, initial, initial, unsafe])
        plan_count = 0

        def plan(request):
            nonlocal plan_count
            plan_count += 1
            return trajectory(
                observed.last, request.target_position_m, request.target_orientation_xyzw
            )

        def execute(_candidate, monitor):
            monitor()
            raise AssertionError("monitor must abort before execution reports success")

        with pytest.raises(ApproachSafetyAbort, match=message):
            CalibrationApproachRunner(observed, plan, execute, POLICY, monotonic=lambda: 10.0).run(
                max_phases=1
            )
        assert plan_count == 1
