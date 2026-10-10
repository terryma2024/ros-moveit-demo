"""Semantic contracts shared by live and sealed dynamic-result verification."""

from __future__ import annotations

import math

import pytest

from so101_demo.core.domain import State
from so101_demo.core.workflow import SO101_WORKFLOW
from paths import PACKAGE_ROOT


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


SCHEMA_V2 = "so101-dynamic-mujoco-execute-v2"
START_TARGET = {"position": [-0.02, -0.28, 0.165], "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}}
END_TARGET = {"position": [-0.08, -0.25, 0.165], "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}}
TRUSTED_FINAL = [-0.08, -0.25, 0.165, 0.0, 0.0, 0.0, 1.0]


def observation(position, time_s, *, quaternion=(0.0, 0.0, 0.0, 1.0)) -> dict[str, object]:
    return {
        "position": list(position),
        "orientation": dict(zip("xyzw", quaternion)),
        "simulation_time_s": time_s,
        "frame_id": "world", "object_id": "plastic_cup", "session_id": "s", "reset_epoch": 17,
    }


def teacher_result(result: str = "PASS", reasons=(), *, end: bool = True) -> dict[str, object]:
    start_observation = observation([-0.02, -0.28, 0.165], 1.0)
    end_observation = observation([-0.08, -0.25, 0.165], 9.0) if end else None
    return {
        "rule_version": "teacher_endpoint",
        "policy_sha256": "a" * 64,
        "result": result,
        "reasons": list(reasons),
        "measured": {},
        "start_target": START_TARGET,
        "end_target": END_TARGET,
        "start_observation": start_observation,
        "end_observation": end_observation,
    }


def teacher_fields(execution: str, result: dict[str, object]) -> dict[str, object]:
    return {
        "schema": SCHEMA_V2,
        "teacher_execution_status": execution,
        "teacher_task_result": result,
        "teacher_start_observation": result["start_observation"],
        "teacher_end_observation": result["end_observation"],
        "act_data_status": "DISABLED",
        "process_diagnostics": [],
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
        **(teacher_fields("COMPLETED", teacher_result()) if status == "DONE"
           else teacher_fields("FAILED", teacher_result("UNCONFIRMED", ["END_OBSERVATION_UNCONFIRMED: x"],
                                                        end=False))),
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


def validate(document: dict[str, object], expected_status: str, *, trusted=None):
    from so101_demo.parallel_batch.dynamic_manifest import validate_dynamic_manifest_semantics

    return validate_dynamic_manifest_semantics(
        document,
        expected_status=expected_status,
        expected_reset_epoch=17,
        expected_final_cup_pose_world=trusted,
    )


def test_valid_complete_done_manifest_is_accepted():
    validate(manifest(), "DONE")


def _place_height_document():
    from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
    from so101_demo.core import place_height as ph

    package = PACKAGE_ROOT
    policy = ph.PlaceHeightPolicy.from_document(load_teacher_execution_policy(package / "config/act/teacher_execution_policy_v2.yaml"))
    geometry = ph.cup_geometry_from_scene(package / "assets/mujoco/act/scene.xml")
    return ph.plan_place_height(0.0705, policy.grasp_offset_m, 0.2176344 - 0.01325, geometry, policy)


def test_a_manifest_with_a_consistent_place_height_document_is_accepted():
    document = manifest()
    document["place_height"] = _place_height_document()
    validate(document, "DONE")


@pytest.mark.parametrize("change", [
    {"target_tcp_z_m": 0.21}, {"guard_m": 0.0}, {"mode": "constant"}, {"tilt_rad": float("nan")}, {"refused": "SOMETHING_ELSE"}])
def test_a_manifest_with_an_inconsistent_place_height_document_is_rejected(change):
    document = manifest()
    document["place_height"] = {**_place_height_document(), **change}
    with pytest.raises(ValueError, match="PLACE_HEIGHT"):
        validate(document, "DONE")


# ---- CP-3483: the place_height record is bound to the frozen execution policy of the run --------------------------------------------

def _frozen_policy(version):
    from so101_demo.act.teacher_endpoint import load_teacher_execution_policy

    return load_teacher_execution_policy(
        PACKAGE_ROOT / f"config/act/teacher_execution_policy_v{version}.yaml")


def _validate_frozen(document, policy, status="DONE"):
    from so101_demo.parallel_batch.dynamic_manifest import validate_dynamic_manifest_semantics

    return validate_dynamic_manifest_semantics(
        document, expected_status=status, expected_reset_epoch=17, frozen_execution_policy=policy)


def test_a_v2_run_must_carry_a_place_height_record_that_matches_the_frozen_policy():
    policy = _frozen_policy(2)
    document = manifest()
    document["place_height"] = _place_height_document()
    _validate_frozen(document, policy)
    missing = manifest()
    with pytest.raises(ValueError, match="PLACE_HEIGHT"):
        _validate_frozen(missing, policy)


@pytest.mark.parametrize("change", [
    {"guard_m": 0.0005}, {"tracking_offset_m": 0.0003}, {"scene_sha256": "0" * 64}, {"tilt_rad": 0.2}, {"grasp_offset_m": 0.0382}])
def test_a_v2_record_that_leaves_the_frozen_policy_is_rejected_even_when_self_consistent(change):
    """A record that is the formula applied to its own (other) inputs passes the structural check; only the frozen policy rejects it."""
    document = manifest()
    record = _place_height_document()
    record.update(change)
    record["target_tcp_z_m"] = (record["geometry"]["table_top_z_m"] + record["geometry"]["half_height_m"] * math.cos(record["tilt_rad"])
                                + record["geometry"]["rim_radius_m"] * math.sin(record["tilt_rad"]) + record["grasp_offset_m"]
                                + record["tracking_offset_m"] - record["guard_m"])
    document["place_height"] = record
    with pytest.raises(ValueError, match="PLACE_HEIGHT"):
        _validate_frozen(document, _frozen_policy(2))


def test_a_v2_error_run_may_stop_before_the_measurement_but_a_present_record_is_still_bound():
    policy = _frozen_policy(2)
    trace = ["IDLE", "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "RECOVER_RETREAT", "ERROR"]
    document = manifest(trace, status="ERROR")
    _validate_frozen(document, policy, "ERROR")
    document["place_height"] = {**_place_height_document(), "guard_m": 0.0005}
    with pytest.raises(ValueError, match="PLACE_HEIGHT"):
        _validate_frozen(document, policy, "ERROR")
    document["place_height"] = {"mode": "tilt_compensated", "refused": "TEACHER_PLACE_MEASUREMENT_FAILED"}
    _validate_frozen(document, policy, "ERROR")


def test_a_v1_run_carries_no_place_height_record():
    policy = _frozen_policy(1)
    _validate_frozen(manifest(), policy)
    document = manifest()
    document["place_height"] = _place_height_document()
    with pytest.raises(ValueError, match="PLACE_HEIGHT"):
        _validate_frozen(document, policy)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda value: value.update(state_trace=["IDLE", "MOVE_ABOVE_OBJECT", "DONE"], transition_count=2), "TRACE"),
        (lambda value: value["state_events"].pop(), "STATE_EVENTS"),
        (lambda value: value["planning_attempts"].__setitem__(0, {**value["planning_attempts"][0], "accepted": False}), "PLANNING"),
        (lambda value: value["teacher_task_result"].update(result="PASS", reasons=["FINAL_XY_OUT_OF_TOLERANCE"]),
         "TEACHER_RESULT"),
        (lambda value: value.update(teacher_execution_status="FAILED"), "TEACHER_STATUS"),
        (lambda value: value["teacher_task_result"]["end_observation"]["orientation"].update(w=0.0),
         "TEACHER_RESULT"),
        (lambda value: value.pop("teacher_task_result"), "TEACHER_RESULT"),
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


def test_failed_micro_lift_event_is_ordered_at_failure_boundary_before_recovery():
    trace = DONE_TRACE[:6] + [
        "MICRO_LIFT", "RECOVER_OPEN_GRIPPER", "RECOVER_DETACH_GAZEBO",
        "RECOVER_DETACH_MOVEIT", "RECOVER_SYNC_WORLD_OBJECT",
        "RECOVER_RETREAT", "ERROR",
    ]
    document = manifest(trace, status="ERROR")
    failed = event("MICRO_LIFT", 500)
    failed["validation_failure"] = "DYNAMIC_MICRO_LIFT_NOT_PROVED"
    document["state_events"].insert(5, failed)

    validate(document, "ERROR")

    document["state_events"].append(document["state_events"].pop(5))
    with pytest.raises(ValueError, match="STATE_EVENTS"):
        validate(document, "ERROR")


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


# ---- manifest v2: the Teacher outcome comes from the Teacher fields (Phase A1b) ---------------------------------

def v2_done(result: str, reasons=()) -> dict[str, object]:
    document = manifest()
    document.update(teacher_fields("COMPLETED", teacher_result(result, reasons, end=result != "UNCONFIRMED")))
    return document


def v2_error(execution: str) -> dict[str, object]:
    document = manifest(
        ["IDLE", "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "RECOVER_RETREAT", "ERROR"], status="ERROR")
    document.update(teacher_fields(execution, teacher_result("UNCONFIRMED", ["END_OBSERVATION_UNCONFIRMED: x"],
                                                              end=False)))
    return document


def test_v2_completed_pass_is_the_only_passed_outcome():
    from so101_demo.parallel_batch.contracts import AttemptStatus

    assert validate(v2_done("PASS"), "DONE") is AttemptStatus.PASSED


def test_v2_completed_task_fail_is_failed():
    from so101_demo.parallel_batch.contracts import AttemptStatus

    document = v2_done("FAIL", ["FINAL_XY_OUT_OF_TOLERANCE"])
    assert validate(document, "DONE") is AttemptStatus.FAILED


def test_v2_completed_unconfirmed_is_indeterminate():
    from so101_demo.parallel_batch.contracts import AttemptStatus

    document = v2_done("UNCONFIRMED", ["END_OBSERVATION_UNCONFIRMED: observation is missing"])
    assert validate(document, "DONE") is AttemptStatus.INDETERMINATE


@pytest.mark.parametrize("execution", ["FAILED", "STOPPED_SAFETY", "STOPPED_USER", "DEADLINE"])
def test_v2_failed_and_stopped_executions_are_failed(execution):
    from so101_demo.parallel_batch.contracts import AttemptStatus

    assert validate(v2_error(execution), "ERROR") is AttemptStatus.FAILED


def test_v2_indeterminate_execution_is_indeterminate():
    from so101_demo.parallel_batch.contracts import AttemptStatus

    assert validate(v2_error("INDETERMINATE"), "ERROR") is AttemptStatus.INDETERMINATE


def test_v2_process_quality_contradictions_no_longer_decide_a_done_run():
    """REPLACED_BY: the old DONE contract (velocity, table/fingertip contact, release order, scene) is audit-only."""
    from so101_demo.parallel_batch.contracts import AttemptStatus

    document = v2_done("PASS")
    final = document["final_samples"][0]
    final.update(table_contact=False, left_contact_count=2, publisher_sequence=800,
                 cup_linear_velocity_world_m_s=[0.5, 0.0, 0.0])
    document["final_samples"].append(dict(final))
    document["planning_scene_readback"]["world_primitive_counts"]["plastic_cup"] = 1
    assert validate(document, "DONE") is AttemptStatus.PASSED


def test_v2_pass_requires_a_completed_execution():
    error = v2_error("FAILED")
    error["teacher_task_result"]["result"] = "PASS"
    with pytest.raises(ValueError, match="TEACHER_RESULT|TEACHER_STATUS"):
        validate(error, "ERROR")


@pytest.mark.parametrize("schema", [None, "so101-dynamic-mujoco-execute-v4", "so101-dynamic-mujoco-execute-v0", 2])
def test_unknown_or_missing_manifest_versions_are_rejected(schema):
    document = v2_done("PASS")
    if schema is None:
        document.pop("schema")
    else:
        document["schema"] = schema
    with pytest.raises(ValueError, match="SCHEMA"):
        validate(document, "DONE")


def test_legacy_v1_manifest_is_read_only_and_never_passes():
    from so101_demo.parallel_batch.contracts import AttemptStatus

    legacy = manifest()
    legacy["schema"] = "so101-dynamic-mujoco-execute-v1"
    for key in ("teacher_execution_status", "teacher_task_result", "teacher_start_observation",
                "teacher_end_observation", "act_data_status", "process_diagnostics"):
        legacy.pop(key)
    assert validate(legacy, "DONE") is AttemptStatus.INDETERMINATE


def test_v2_trusted_final_target_must_match_the_frozen_end_target():
    validate(v2_done("PASS"), "DONE", trusted=TRUSTED_FINAL)
    with pytest.raises(ValueError, match="TRUSTED_FINAL_TARGET"):
        validate(v2_done("PASS"), "DONE", trusted=[0.5, 0.5, 0.165, 0.0, 0.0, 0.0, 1.0])
    with pytest.raises(ValueError, match="TRUSTED_FINAL_TARGET"):
        validate(v2_done("PASS"), "DONE", trusted=[0.0] * 7)


# ---- C2: a terminal stop goes straight to ERROR from any state (R9.2) ----------------------------------------------

def terminal_stop(failure="DYNAMIC_CUP_COMPRESSION_EXCEEDED", boundary="MOVE_ABOVE_PLACE"):
    trace = DONE_TRACE[:DONE_TRACE.index(boundary) + 1] + ["ERROR"]
    document = manifest(trace, status="ERROR")
    document["failure"] = failure
    document["failure_evidence"]["failure_boundary_state"] = boundary
    failed = event(boundary, 500)
    failed["validation_failure"] = failure
    document["state_events"].append(failed)
    return document


def test_terminal_stop_direct_edge_to_error_is_accepted_with_its_boundary():
    validate(terminal_stop(), "ERROR")


def test_non_terminal_failure_with_a_direct_edge_to_error_is_still_rejected():
    with pytest.raises(ValueError, match="TRACE"):
        validate(terminal_stop("INJECTED_BUSINESS_FAILURE"), "ERROR")


def test_terminal_stop_boundary_must_be_the_last_state_before_error():
    document = terminal_stop()
    document["failure_evidence"]["failure_boundary_state"] = "LIFT"
    with pytest.raises(ValueError, match="FAILURE_EVIDENCE"):
        validate(document, "ERROR")


def test_terminal_stop_may_leave_the_cup_attached_in_the_moveit_scene():
    document = terminal_stop()
    document["failure_evidence"]["planning_scene_readback"] = {
        "attached_object_ids": ["plastic_cup"], "world_primitive_counts": {"table": 1, "pedestal": 1}}
    validate(document, "ERROR")


def test_attached_cup_scene_is_refused_without_a_terminal_stop():
    document = manifest(["IDLE", "PREPARE_OPEN_GRIPPER", "MOVE_ABOVE_OBJECT", "RECOVER_RETREAT", "ERROR"],
                        status="ERROR")
    document["failure_evidence"]["planning_scene_readback"] = {
        "attached_object_ids": ["plastic_cup"], "world_primitive_counts": {"table": 1}}
    with pytest.raises(ValueError, match="FAILURE_EVIDENCE"):
        validate(document, "ERROR")
