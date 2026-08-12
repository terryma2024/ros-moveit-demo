from dataclasses import asdict

from so101_demo.application.pick_place import LIVE_PHASES as NEW_LIVE_PHASES
from so101_demo.cli import pick_place as new_cli
from so101_demo.control.moveit.planning import JointPlanRequest as NewJointPlanRequest
from so101_mujoco_demo_py import cli as old_cli
from so101_mujoco_demo_py.live_runtime import LIVE_PHASES as OLD_LIVE_PHASES
from so101_mujoco_demo_py.moveit.planning import JointPlanRequest as OldJointPlanRequest

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


def _joint_plan_request(request_type):
    return request_type(
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
    """Catch omission, insertion, or reordering of a qualified production phase."""

    assert NEW_LIVE_PHASES == OLD_LIVE_PHASES == EXPECTED_LIVE_PHASES


def test_plan_request_is_unchanged() -> None:
    """Catch changed MoveIt request fields/default interpretation during extraction."""

    assert asdict(_joint_plan_request(NewJointPlanRequest)) == asdict(
        _joint_plan_request(OldJointPlanRequest)
    )


def test_dry_run_cli_result_is_unchanged(capsys) -> None:
    """Catch a changed exit code or public result schema in the new CLI."""

    old_exit = old_cli.main([])
    old_output = capsys.readouterr().out
    new_exit = new_cli.main([])
    new_output = capsys.readouterr().out
    assert new_exit == old_exit == 0
    assert new_output == old_output
