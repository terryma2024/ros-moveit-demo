"""Frozen MuJoCo behavior checks retained after legacy ownership removal."""

from dataclasses import asdict

from so101_demo.application.pick_place import LIVE_PHASES
from so101_demo.cli import pick_place
from so101_demo.control.moveit.planning import JointPlanRequest

EXPECTED_LIVE_PHASES = (
    "staged_approach",
    "contact_hold",
    "micro_lift",
    "policy_lift_waypoint1",
    "remaining_lift",
    "transport",
    "descend",
    "place_alignment",
    "release_retreat",
)


def _joint_plan_request() -> JointPlanRequest:
    return JointPlanRequest(
        joint_names=("joint1", "joint2", "joint3", "joint4", "joint5"),
        current_positions=(0.0, 0.1, 0.2, 0.3, 0.4),
        target_positions=(0.5, 0.4, 0.3, 0.2, 0.1),
        velocity_scaling=0.05,
        acceleration_scaling=0.04,
        planning_time_s=7.0,
        planning_group="arm",
        tcp_link="so101_tcp",
        start_state_joint_names=(
            "joint1",
            "joint2",
            "joint3",
            "joint4",
            "joint5",
            "joint6",
        ),
        start_state_positions=(0.0, 0.1, 0.2, 0.3, 0.4, -0.2),
    )


def test_phase_sequence_is_frozen() -> None:
    assert LIVE_PHASES == EXPECTED_LIVE_PHASES


def test_plan_request_shape_is_frozen() -> None:
    assert tuple(asdict(_joint_plan_request())) == (
        "joint_names",
        "current_positions",
        "target_positions",
        "velocity_scaling",
        "acceleration_scaling",
        "planning_time_s",
        "planning_group",
        "tcp_link",
        "start_state_joint_names",
        "start_state_positions",
    )


def test_dry_run_cli_contract_is_frozen(capsys) -> None:
    assert pick_place.main(["--backend", "mujoco"]) == 0
    output = capsys.readouterr().out
    assert "status=DONE" in output
    assert "transition_count=19" in output
    assert output.rstrip().endswith("RETREAT,DONE")
