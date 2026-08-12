from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path

from so101_demo.core import domain as new_domain
from so101_demo.core import policy as new_policy
from so101_demo.core import recovery as new_recovery
from so101_demo.core import runner as new_runner
from so101_demo.core import workflow as new_workflow
from so101_mujoco_demo_py import domain as old_domain
from so101_mujoco_demo_py import runner as old_runner
from so101_mujoco_demo_py import task_policy as old_policy
from so101_mujoco_demo_py import workflow as old_workflow
from so101_mujoco_demo_py.recovery import policy as old_recovery

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
POLICY_PATH = (
    REPOSITORY_ROOT
    / "src"
    / "so101_mujoco_demo_py"
    / "config"
    / "motion_policies"
    / "light_cup_wall_pick.yaml"
)


def _snapshot(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _snapshot(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {_snapshot(key): _snapshot(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(_snapshot(item) for item in value)
    return value


def test_domain_values_and_result_shapes_match_frozen_mujoco() -> None:
    """Catch renamed states/statuses or changed public request/result fields during the port."""

    for old_type, new_type in (
        (old_domain.State, new_domain.State),
        (old_domain.RunStatus, new_domain.RunStatus),
        (old_domain.RunMode, new_domain.RunMode),
        (old_domain.ActionStatus, new_domain.ActionStatus),
        (old_domain.FailureCategory, new_domain.FailureCategory),
    ):
        assert [item.value for item in new_type] == [item.value for item in old_type]
    assert [field.name for field in fields(new_domain.RunRequest)] == [
        field.name for field in fields(old_domain.RunRequest)
    ]
    assert [field.name for field in fields(new_domain.RunResult)] == [
        field.name for field in fields(old_domain.RunResult)
    ]


def test_workflow_matches_frozen_mujoco() -> None:
    """Catch a phase-order or transition destination change during namespace migration."""

    old = old_workflow.SO101_WORKFLOW
    new = new_workflow.SO101_WORKFLOW
    assert tuple(state.value for state in new.forward_states) == tuple(
        state.value for state in old.forward_states
    )
    assert {
        state.value: tuple(destination.value for destination in destinations)
        for state, destinations in new.transitions.items()
    } == {
        state.value: tuple(destination.value for destination in destinations)
        for state, destinations in old.transitions.items()
    }


def test_dry_run_result_matches_frozen_mujoco() -> None:
    """Catch runner behavior that changes transition count, trace, terminal state, or failure."""

    old_result = old_runner.StateMachineRunner(old_runner.dry_run_actions()).run(
        old_domain.RunRequest()
    )
    new_result = new_runner.StateMachineRunner(new_runner.dry_run_actions()).run(
        new_domain.RunRequest()
    )
    assert _snapshot(new_result) == _snapshot(old_result)


def test_task_policy_matches_frozen_mujoco() -> None:
    """Catch loader/default changes against the immutable qualified policy bytes."""

    assert _snapshot(new_policy.load_task_policy(POLICY_PATH)) == _snapshot(
        old_policy.load_task_policy(POLICY_PATH)
    )


def test_recovery_decision_matches_frozen_mujoco() -> None:
    """Catch recovery side-effect ordering changes during module consolidation."""

    old_evidence = old_recovery.RecoveryEvidence(
        simulator_task_object_constrained=True,
        moveit_task_object_attached=True,
        task_object_supported=False,
        gripper_task_object_contact=False,
    )
    new_evidence = new_recovery.RecoveryEvidence(
        simulator_task_object_constrained=True,
        moveit_task_object_attached=True,
        task_object_supported=False,
        gripper_task_object_contact=False,
    )
    assert tuple(state.value for state in new_recovery.RecoveryPolicy().path_for(
        new_domain.State.LIFT, new_evidence
    )) == tuple(state.value for state in old_recovery.RecoveryPolicy().path_for(
        old_domain.State.LIFT, old_evidence
    ))
