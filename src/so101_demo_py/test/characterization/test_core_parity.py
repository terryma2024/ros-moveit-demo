"""Frozen core behavior checks retained after the strangler cutover."""

from dataclasses import fields
from pathlib import Path

from so101_demo.core import domain, policy, recovery, runner, workflow

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
POLICY_PATH = (
    REPOSITORY_ROOT / "src/so101_demo_py/config/policies/light_cup_wall_pick/v1/mujoco.yaml"
)


def test_domain_values_and_result_shapes_are_frozen() -> None:
    assert [state.value for state in domain.State] == [
        "IDLE",
        "PREPARE_OPEN_GRIPPER",
        "MOVE_ABOVE_OBJECT",
        "DESCEND",
        "CLOSE_GRIPPER",
        "WAIT_GRASP_STABLE",
        "MICRO_LIFT",
        "WAIT_MICRO_LIFT_STABLE",
        "VERIFY_PHYSICAL_GRASP",
        "VALIDATION_FAILED",
        "ATTACH_MOVEIT",
        "LIFT",
        "MOVE_ABOVE_PLACE",
        "DESCEND_TO_PLACE",
        "DETACH_MOVEIT",
        "OPEN_GRIPPER",
        "WAIT_RELEASE_SETTLE",
        "VALIDATE_FINAL_PLACEMENT",
        "SYNC_WORLD_OBJECT",
        "RETREAT",
        "RECOVER_LIFT_TO_SAFE_HEIGHT",
        "RECOVER_MOVE_ABOVE_PICK",
        "RECOVER_DESCEND_TO_PICK",
        "RECOVER_OPEN_GRIPPER",
        "RECOVER_DETACH_GAZEBO",
        "RECOVER_DETACH_MOVEIT",
        "RECOVER_SYNC_WORLD_OBJECT",
        "RECOVER_RETREAT",
        "DONE",
        "ERROR",
    ]
    assert [field.name for field in fields(domain.RunRequest)] == [
        "mode",
        "stop_after",
        "resume",
        "fail_at",
        "max_state_transitions",
        "single_step",
        "force_continue",
        "plan_only_state",
    ]


def test_workflow_and_dry_run_are_frozen() -> None:
    assert workflow.SO101_WORKFLOW.forward_states[-1] is domain.State.RETREAT
    result = runner.StateMachineRunner(runner.dry_run_actions()).run(domain.RunRequest())
    assert result.status is domain.RunStatus.DONE
    assert result.transition_count == 19
    assert result.state_trace[-1] is domain.State.DONE


def test_task_policy_loads_from_unified_immutable_path() -> None:
    loaded = policy.load_task_policy(POLICY_PATH)
    assert loaded.policy_id == "light_cup_wall_pick"
    assert (
        loaded.fingerprint.motion_policy_sha256
        == "aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356"
    )


def test_recovery_decision_remains_side_effect_ordered() -> None:
    evidence = recovery.RecoveryEvidence(
        simulator_task_object_constrained=True,
        moveit_task_object_attached=True,
        task_object_supported=False,
        gripper_task_object_contact=False,
    )
    path = recovery.RecoveryPolicy().path_for(domain.State.LIFT, evidence)
    assert path
    assert path == (
        domain.State.RECOVER_LIFT_TO_SAFE_HEIGHT,
        domain.State.RECOVER_DETACH_GAZEBO,
        domain.State.RECOVER_DETACH_MOVEIT,
        domain.State.RECOVER_SYNC_WORLD_OBJECT,
        domain.State.RECOVER_RETREAT,
    )
