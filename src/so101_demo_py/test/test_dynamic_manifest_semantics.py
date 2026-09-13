"""Semantic contracts shared by live and sealed dynamic-result verification."""

from __future__ import annotations

import pytest

from so101_demo.core.domain import State
from so101_demo.core.workflow import SO101_WORKFLOW


DONE_TRACE = [
    "IDLE", "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "DESCEND",
    "CLOSE_GRIPPER", "WAIT_GRASP_STABLE", "MICRO_LIFT",
    "WAIT_MICRO_LIFT_STABLE", "VERIFY_PHYSICAL_GRASP", "ATTACH_MOVEIT",
    "LIFT", "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE", "DETACH_MOVEIT",
    "OPEN_GRIPPER", "WAIT_RELEASE_SETTLE", "VALIDATE_FINAL_PLACEMENT",
    "SYNC_WORLD_OBJECT", "RETREAT", "DONE",
]
MOTION_STATES = {
    "MOVE_ABOVE_OBJECT", "DESCEND", "MICRO_LIFT", "LIFT",
    "MOVE_ABOVE_PLACE", "DESCEND_TO_PLACE", "RETREAT",
    "RECOVER_LIFT_TO_SAFE_HEIGHT", "RECOVER_MOVE_ABOVE_PICK",
    "RECOVER_DESCEND_TO_PICK", "RECOVER_RETREAT",
}


def sample(sequence: int, *, reset_epoch: int = 17) -> dict[str, object]:
    return {
        "reset_epoch": reset_epoch,
        "simulation_step": sequence * 5,
        "publisher_sequence": sequence,
        "cup_position_world_m": [-0.08, -0.25, 0.1648],
        "cup_orientation_world_xyzw": [0.0, 0.0, 0.0, 1.0],
        "cup_linear_velocity_world_m_s": [0.0, 0.0, 0.0],
        "cup_angular_velocity_world_rad_s": [0.0, 0.0, 0.0],
        "left_contact_count": 0,
        "right_contact_count": 0,
        "maximum_normal_force_n": 0.2,
        "table_contact": True,
    }


def event(state: str, sequence: int) -> dict[str, object]:
    value: dict[str, object] = {
        "state": state,
        "before": sample(sequence),
        "after": sample(sequence + 1),
    }
    if state in MOTION_STATES:
        value.update(
            terminal_joint_positions_rad=[0.0] * 5,
            terminal_joint_state_source_stamp_ns=sequence * 1_000_000,
            execution_reconciliations=[],
        )
    if state == "VALIDATE_FINAL_PLACEMENT":
        value.update(
            expected_cup_pose_world=[-0.08, -0.25, 0.1648, 0.0, 0.0, 0.0, 1.0],
            final_xy_error_m=0.0,
            final_upright_tilt_rad=0.0,
        )
    return value


def successful_states(trace: list[str]) -> list[str]:
    states = []
    for current, following in zip(trace, trace[1:]):
        state = State(current)
        if state in SO101_WORKFLOW.action_states:
            success, _failure = SO101_WORKFLOW.transitions[state]
            if following == success.value:
                states.append(current)
    return states


def manifest(trace: list[str] | None = None, *, status: str = "DONE") -> dict[str, object]:
    trace = list(DONE_TRACE if trace is None else trace)
    completed = successful_states(trace)
    events = [event(state, 100 + index * 2) for index, state in enumerate(completed)]
    planning = [
        {"kind": "moveit_joint_plan", "state": state, "accepted": True}
        for state in completed if state in MOTION_STATES
    ]
    terminal = sample(1000)
    failure = None if status == "DONE" else "INJECTED_BUSINESS_FAILURE"
    document: dict[str, object] = {
        "status": status,
        "current_state": status,
        "failure": failure,
        "state_trace": trace,
        "transition_count": len(trace) - 1,
        "state_events": events,
        "planning_attempts": planning,
        "final_samples": [terminal] if status == "DONE" else [],
        "planning_scene_readback": {
            "attached_object_ids": [],
            "world_primitive_counts": {"plastic_cup": 13},
        },
        "release_marker_sequence": 900 if "OPEN_GRIPPER" in trace else None,
    }
    if status == "ERROR":
        failure_boundaries = [
            current for current, following in zip(trace, trace[1:])
            if State(current) in SO101_WORKFLOW.transitions
            and following == SO101_WORKFLOW.transitions[State(current)][1].value
        ]
        document["failure_evidence"] = {
            "failure_boundary_state": failure_boundaries[0] if failure_boundaries else trace[-2],
            "physical_action_proven_absent": False,
            "terminal_sample": terminal,
            "planning_scene_readback": document["planning_scene_readback"],
            "capture_errors": [],
        }
    return document


def validate(document: dict[str, object], expected_status: str) -> None:
    from so101_demo.parallel_batch.dynamic_manifest import validate_dynamic_manifest_semantics

    validate_dynamic_manifest_semantics(
        document,
        expected_status=expected_status,
        expected_reset_epoch=17,
    )


def test_valid_complete_done_manifest_is_accepted():
    validate(manifest(), "DONE")


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda value: value.update(state_trace=["IDLE", "MOVE_ABOVE_OBJECT", "DONE"], transition_count=2), "TRACE"),
        (lambda value: value["state_events"].pop(), "STATE_EVENTS"),
        (lambda value: value["planning_attempts"].__setitem__(0, {**value["planning_attempts"][0], "accepted": False}), "PLANNING"),
        (lambda value: value["final_samples"][0].update(publisher_sequence=800), "RELEASE_ORDER"),
        (lambda value: value["final_samples"][0].update(table_contact=False), "FINAL_PHYSICAL"),
        (lambda value: value["final_samples"][0].update(cup_position_world_m=[0.2, 0.2, 0.1648]), "FINAL_PHYSICAL"),
        (lambda value: value["planning_scene_readback"]["world_primitive_counts"].update(plastic_cup=1), "SCENE"),
    ],
)
def test_done_manifest_rejects_semantic_omissions_and_contradictions(mutation, error):
    document = manifest()
    mutation(document)
    with pytest.raises(ValueError, match=error):
        validate(document, "DONE")


@pytest.mark.parametrize(
    "trace",
    [
        ["IDLE", "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "RECOVER_RETREAT", "ERROR"],
        ["IDLE", "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "DESCEND", "RECOVER_OPEN_GRIPPER", "RECOVER_DETACH_GAZEBO", "RECOVER_DETACH_MOVEIT", "RECOVER_SYNC_WORLD_OBJECT", "RECOVER_RETREAT", "ERROR"],
        ["IDLE", "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "DESCEND", "CLOSE_GRIPPER", "WAIT_GRASP_STABLE", "RECOVER_OPEN_GRIPPER", "RECOVER_DETACH_GAZEBO", "RECOVER_DETACH_MOVEIT", "RECOVER_SYNC_WORLD_OBJECT", "RECOVER_RETREAT", "ERROR"],
        DONE_TRACE[:17] + ["RECOVER_LIFT_TO_SAFE_HEIGHT", "RECOVER_MOVE_ABOVE_PICK", "RECOVER_DESCEND_TO_PICK", "RECOVER_OPEN_GRIPPER", "RECOVER_DETACH_GAZEBO", "RECOVER_DETACH_MOVEIT", "RECOVER_SYNC_WORLD_OBJECT", "RECOVER_RETREAT", "ERROR"],
    ],
)
def test_stage_specific_business_failures_remain_classifiable(trace):
    validate(manifest(trace, status="ERROR"), "ERROR")


def test_pre_action_failure_requires_explicit_no_action_authority():
    document = manifest(["IDLE", "ERROR"], status="ERROR")
    document["state_events"] = []
    document["planning_attempts"] = []
    document["failure_evidence"] = {
        "failure_boundary_state": "IDLE",
        "physical_action_proven_absent": True,
        "terminal_sample": None,
        "planning_scene_readback": None,
        "capture_errors": [],
    }
    validate(document, "ERROR")
    document["failure_evidence"]["physical_action_proven_absent"] = False
    with pytest.raises(ValueError, match="FAILURE_EVIDENCE"):
        validate(document, "ERROR")


def test_post_action_failure_with_stale_terminal_physical_evidence_is_indeterminate():
    document = manifest(
        ["IDLE", "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "RECOVER_RETREAT", "ERROR"],
        status="ERROR",
    )
    latest_event = max(
        item["after"]["publisher_sequence"] for item in document["state_events"]
    )
    document["failure_evidence"]["terminal_sample"]["publisher_sequence"] = latest_event
    with pytest.raises(ValueError, match="FAILURE_EVIDENCE"):
        validate(document, "ERROR")


def test_post_release_failure_requires_sample_newer_than_release_marker():
    trace = DONE_TRACE[:17] + [
        "RECOVER_LIFT_TO_SAFE_HEIGHT", "RECOVER_MOVE_ABOVE_PICK",
        "RECOVER_DESCEND_TO_PICK", "RECOVER_OPEN_GRIPPER",
        "RECOVER_DETACH_GAZEBO", "RECOVER_DETACH_MOVEIT",
        "RECOVER_SYNC_WORLD_OBJECT", "RECOVER_RETREAT", "ERROR",
    ]
    document = manifest(trace, status="ERROR")
    document["failure_evidence"]["terminal_sample"]["publisher_sequence"] = 899
    with pytest.raises(ValueError, match="RELEASE_ORDER"):
        validate(document, "ERROR")


def test_failure_trace_wrong_policy_transition_is_rejected():
    document = manifest(
        ["IDLE", "PREPARE_OPEN_GRIPPER", "DESCEND", "ERROR"], status="ERROR"
    )
    with pytest.raises(ValueError, match="TRACE"):
        validate(document, "ERROR")
