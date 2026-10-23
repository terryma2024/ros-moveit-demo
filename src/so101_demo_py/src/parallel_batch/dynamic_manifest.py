"""ROS-free semantic verification for dynamic execution manifests."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from ..application.e2e_acceptance import SCHEMA_GENERAL, SCHEMA_TEACHER, is_manifest_of
from ..core.domain import State
from ..core.dynamic_pick import DYNAMIC_MOTION_STATES
from ..core.workflow import SIM_INTEGRITY_CODES, SO101_WORKFLOW, TEACHER_WORKFLOW, TERMINAL_STOP_CODES
from so101_demo.parallel_batch.contracts.common import AttemptStatus

EXECUTION_STATUSES = frozenset({
    "COMPLETED", "FAILED", "STOPPED_SAFETY", "STOPPED_USER", "DEADLINE", "INDETERMINATE",
})
FAILED_EXECUTIONS = frozenset({"FAILED", "STOPPED_SAFETY", "STOPPED_USER", "DEADLINE"})
TASK_RESULTS = frozenset({"PASS", "FAIL", "UNCONFIRMED"})
DATA_STATUSES = frozenset({"VALID", "INVALID", "DISABLED", "PENDING_QC"})
RULE_VERSION = "teacher_endpoint"
_TASK_FIELDS = frozenset({
    "rule_version", "policy_sha256", "result", "reasons", "measured", "start_target", "end_target",
    "start_observation", "end_observation",
})


def _fail(boundary: str) -> None:
    raise ValueError(f"DYNAMIC_MANIFEST_{boundary}")


def teacher_attempt_status(execution: str, result: str) -> AttemptStatus:
    """The attempt status as a function of the Teacher's own two fields, and of nothing else.

    A completed execution is judged by the endpoint result (PASS, FAIL or UNCONFIRMED -> INDETERMINATE). An execution
    that did not complete is FAILED when the Teacher itself failed, stopped or ran out of time, and INDETERMINATE when
    its own outcome is unconfirmed. A PASS needs a completed execution. Data QC never enters this function.
    """

    if execution not in EXECUTION_STATUSES or result not in TASK_RESULTS:
        raise ValueError("RESULT_TEACHER_FIELDS_INVALID")
    if execution == "COMPLETED":
        return {
            "PASS": AttemptStatus.PASSED, "FAIL": AttemptStatus.FAILED,
            "UNCONFIRMED": AttemptStatus.INDETERMINATE,
        }[result]
    if result == "PASS":
        raise ValueError("RESULT_TEACHER_FIELDS_INVALID")
    return AttemptStatus.FAILED if execution in FAILED_EXECUTIONS else AttemptStatus.INDETERMINATE


def _finite_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _finite_vector(value: object, length: int) -> bool:
    return (
        type(value) is list
        and len(value) == length
        and all(_finite_number(component) for component in value)
    )


def _unit_quaternion(value: object) -> bool:
    return (
        _finite_vector(value, 4)
        and math.isclose(
            math.sqrt(sum(component * component for component in value)),
            1.0,
            rel_tol=1e-6,
            abs_tol=1e-6,
        )
    )


def _physical_sample(sample: object, reset_epoch: int) -> bool:
    if type(sample) is not dict:
        return False
    return (
        sample.get("reset_epoch") == reset_epoch
        and type(sample.get("simulation_step")) is int
        and sample["simulation_step"] > 0
        and type(sample.get("publisher_sequence")) is int
        and sample["publisher_sequence"] > 0
        and _finite_vector(sample.get("cup_position_world_m"), 3)
        and _unit_quaternion(sample.get("cup_orientation_world_xyzw"))
        and _finite_vector(sample.get("cup_linear_velocity_world_m_s"), 3)
        and _finite_vector(sample.get("cup_angular_velocity_world_rad_s"), 3)
        and type(sample.get("left_contact_count")) is int
        and sample["left_contact_count"] >= 0
        and type(sample.get("right_contact_count")) is int
        and sample["right_contact_count"] >= 0
        and _finite_number(sample.get("maximum_normal_force_n"))
        and sample["maximum_normal_force_n"] >= 0.0
        and type(sample.get("table_contact")) is bool
    )


def _scene_is_detached_world(scene: object) -> bool:
    return (
        type(scene) is dict
        and scene.get("attached_object_ids") == []
        and type(scene.get("world_primitive_counts")) is dict
        and scene["world_primitive_counts"].get("plastic_cup") == 13
    )


def _scene_is_attached_cup(scene: object) -> bool:
    return (
        type(scene) is dict
        and scene.get("attached_object_ids") == ["plastic_cup"]
        and type(scene.get("world_primitive_counts")) is dict
        and "plastic_cup" not in scene["world_primitive_counts"]
    )


def _terminal_stop_edge(document: Mapping[str, object], current: State, following: State) -> bool:
    """R9.2: a terminal stop code goes straight from the state it stopped in to ERROR, with no RECOVER_* chain."""

    failure = document.get("failure")
    return (
        following is State.ERROR
        and current is not State.ERROR
        and isinstance(failure, str)
        and failure.split(":", 1)[0] in TERMINAL_STOP_CODES
    )


def _trace_contract(document: Mapping[str, object], expected_status: str, workflow=SO101_WORKFLOW):
    trace = document.get("state_trace")
    if (
        type(trace) is not list
        or len(trace) < 2
        or trace[0] != "IDLE"
        or trace[-1] != expected_status
        or document.get("transition_count") != len(trace) - 1
    ):
        _fail("TRACE")
    try:
        states = [State(value) for value in trace]
    except (TypeError, ValueError):
        _fail("TRACE")
    for current, following in zip(states, states[1:]):
        if current not in workflow.transitions:
            _fail("TRACE")
        if following not in workflow.transitions[current] and not _terminal_stop_edge(
                document, current, following):
            _fail("TRACE")
    failure_boundaries = [
        current
        for current, following in zip(states, states[1:])
        if following == workflow.transitions[current][1]
        or _terminal_stop_edge(document, current, following)
    ]
    if expected_status == "ERROR" and not failure_boundaries:
        _fail("TRACE")
    if expected_status == "DONE" and failure_boundaries:
        _fail("TRACE")
    return states, failure_boundaries


def _successful_action_states(states: list[State], workflow=SO101_WORKFLOW) -> list[State]:
    return [
        current
        for current, following in zip(states, states[1:])
        if current in workflow.action_states
        and following == workflow.transitions[current][0]
    ]


def _event_contract(document: Mapping[str, object], states: list[State], boundary: State | None, workflow=SO101_WORKFLOW):
    events = document.get("state_events")
    if type(events) is not list or any(type(item) is not dict for item in events):
        _fail("STATE_EVENTS")
    expected = [state.value for state in _successful_action_states(states, workflow)]
    observed = [item.get("state") for item in events]
    if observed != expected:
        expected_with_failed = []
        failed_index = None
        for current, following in zip(states, states[1:]):
            success, failure = workflow.transitions[current]
            if current in workflow.action_states and following == success:
                expected_with_failed.append(current.value)
            elif boundary is current and (following == failure or _terminal_stop_edge(document, current, following)):
                failed_index = len(expected_with_failed)
                expected_with_failed.append(current.value)
        allowed_failed_record = (
            boundary is not None
            and failed_index is not None
            and observed == expected_with_failed
            and isinstance(events[failed_index].get("validation_failure"), str)
            and bool(events[failed_index]["validation_failure"])
        )
        if not allowed_failed_record:
            _fail("STATE_EVENTS")
    by_state = {item["state"]: item for item in events}
    for state in _successful_action_states(states, workflow):
        if state not in DYNAMIC_MOTION_STATES:
            continue
        event = by_state[state.value]
        if (
            not _finite_vector(event.get("terminal_joint_positions_rad"), 5)
            or type(event.get("terminal_joint_state_source_stamp_ns")) is not int
            or event["terminal_joint_state_source_stamp_ns"] <= 0
            or type(event.get("execution_reconciliations")) is not list
        ):
            _fail("CONTROLLER")
    return events


def _planning_contract(document: Mapping[str, object], states: list[State], workflow=SO101_WORKFLOW) -> None:
    planning = document.get("planning_attempts")
    if type(planning) is not list or any(type(item) is not dict for item in planning):
        _fail("PLANNING")
    for state in _successful_action_states(states, workflow):
        if state in DYNAMIC_MOTION_STATES and not any(
            item.get("state") == state.value and item.get("accepted") is True
            for item in planning
        ):
            _fail("PLANNING")


def _observation_valid(value: object, reset_epoch: int) -> bool:
    return (
        type(value) is dict
        and _finite_vector(value.get("position"), 3)
        and type(value.get("orientation")) is dict
        and set(value["orientation"]) == {"x", "y", "z", "w"}
        and _unit_quaternion([value["orientation"][key] for key in "xyzw"])
        and _finite_number(value.get("simulation_time_s"))
        and value.get("frame_id") == "world"
        and isinstance(value.get("object_id"), str) and bool(value["object_id"])
        and isinstance(value.get("session_id"), str) and bool(value["session_id"])
        and value.get("reset_epoch") == reset_epoch
    )


def _target_valid(value: object) -> bool:
    return (
        type(value) is dict
        and _finite_vector(value.get("position"), 3)
        and type(value.get("orientation")) is dict
        and set(value["orientation"]) == {"x", "y", "z", "w"}
        and _unit_quaternion([value["orientation"][key] for key in "xyzw"])
    )


def _place_height_contract(
    document: Mapping[str, object], expected_status: str, frozen_execution_policy: Mapping[str, object] | None,
) -> None:
    """Teacher manifest: a finished run carries a `teacher_place_height` record (tilt_compensated or fallback_reference); an ERROR run may stop before the
    measurement, so its record is optional but still bound when present. With the frozen policy the record is checked against it."""

    from ..core.place_height import PlaceHeightPolicy, validate_document

    if "place_height" not in document:
        if expected_status == "DONE":
            _fail("PLACE_HEIGHT")
        return
    try:
        policy = None if frozen_execution_policy is None else PlaceHeightPolicy.from_document(frozen_execution_policy)
        validate_document(document["place_height"], policy)
    except (ValueError, KeyError, TypeError):
        _fail("PLACE_HEIGHT")


def _process_summary_contract(document: Mapping[str, object], frozen_execution_policy: Mapping[str, object] | None) -> None:
    """Teacher manifest: the `teacher_process_summary` is present and coherent, names the provenance and agrees with the place record."""

    from ..core.process_summary import validate_summary

    summary = document.get("teacher_process_summary")
    try:
        validate_summary(summary)
    except ValueError:
        _fail("PROCESS_SUMMARY")
    policy = summary.get("policy")
    if type(policy) is not dict:
        _fail("PROCESS_SUMMARY")
    expected = {"cup_pose_source": "broker_rgbd", "verdict_source": "sim_truth"}
    if frozen_execution_policy is not None:
        expected = {key: frozen_execution_policy.get(key) for key in expected}
    if any(policy.get(key) != value for key, value in expected.items()):
        _fail("PROCESS_SUMMARY")
    record = document.get("place_height")
    if type(record) is dict and (summary.get("place_height_mode") != record.get("mode")
                                 or summary.get("place_fallback_reason") != record.get("fallback_reason")):
        _fail("PROCESS_SUMMARY")


def _failure_class_contract(document: Mapping[str, object], execution: object) -> None:
    """Teacher manifest: `failure_class = sim_integrity` exactly for a FAILED attempt whose failure is a SIM_INTEGRITY code (design 5b)."""

    failure = document.get("failure")
    code = failure.split(":", 1)[0] if isinstance(failure, str) else None
    sim = code in SIM_INTEGRITY_CODES
    if "failure_class" not in document or document["failure_class"] != ("sim_integrity" if sim else None):
        _fail("FAILURE_CLASS")
    if sim and execution != "FAILED":
        _fail("FAILURE_CLASS")


def _teacher_contract(
    document: Mapping[str, object], expected_status: str, reset_epoch: int,
    expected_final_cup_pose_world: object,
    frozen_execution_policy: Mapping[str, object] | None = None,
    schema: str = SCHEMA_GENERAL,
) -> AttemptStatus:
    """Structural integrity of the Teacher fields, then the Teacher outcome they declare.

    The worker does not re-judge process quality: PASSED needs a COMPLETED execution and an endpoint PASS.
    """

    execution = document.get("teacher_execution_status")
    task = document.get("teacher_task_result")
    if execution not in EXECUTION_STATUSES or type(task) is not dict or not _TASK_FIELDS.issubset(task):
        _fail("TEACHER_RESULT")
    result = task["result"]
    reasons = task["reasons"]
    if (
        result not in TASK_RESULTS
        or task["rule_version"] != RULE_VERSION
        or type(reasons) is not list
        or any(not isinstance(reason, str) for reason in reasons)
        or document.get("act_data_status") not in DATA_STATUSES
        or type(document.get("process_diagnostics")) is not list
        or any(type(item) is not dict for item in document["process_diagnostics"])
        or document.get("teacher_start_observation") != task["start_observation"]
        or document.get("teacher_end_observation") != task["end_observation"]
    ):
        _fail("TEACHER_RESULT")
    if (execution == "COMPLETED") != (expected_status == "DONE"):
        _fail("TEACHER_STATUS")
    if schema == SCHEMA_TEACHER:
        _place_height_contract(document, expected_status, frozen_execution_policy)
        _process_summary_contract(document, frozen_execution_policy)
        _failure_class_contract(document, execution)
    elif "place_height" in document:
        _fail("PLACE_HEIGHT")      # only a Teacher run measures and records a place height
    if result in {"PASS", "FAIL"}:
        if (
            execution != "COMPLETED"
            or not _observation_valid(task["start_observation"], reset_epoch)
            or not _observation_valid(task["end_observation"], reset_epoch)
            or not _target_valid(task["start_target"])
            or not _target_valid(task["end_target"])
            or not isinstance(task["policy_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", task["policy_sha256"]) is None
        ):
            _fail("TEACHER_RESULT")
        if (result == "PASS") != (not reasons):
            _fail("TEACHER_RESULT")
    elif execution == "COMPLETED" and not reasons:
        _fail("TEACHER_RESULT")
    trusted = expected_final_cup_pose_world
    if trusted is not None and result in {"PASS", "FAIL"}:
        # Only XY and the attitude of the frozen end target are the coordinator's trusted final placement; the
        # target height is the input cup's resting height and is not part of that trusted pose.
        if not _finite_vector(trusted, 7) or not _unit_quaternion(trusted[3:]):
            _fail("TRUSTED_FINAL_TARGET")
        target = task["end_target"]
        quaternion = [target["orientation"][key] for key in "xyzw"]
        alignment = abs(sum(left * right for left, right in zip(quaternion, trusted[3:])))
        if (math.dist(target["position"][:2], trusted[:2]) > 1e-9 or 1.0 - alignment > 1e-9):
            _fail("TRUSTED_FINAL_TARGET")
    if execution == "COMPLETED" and document.get("failure") is not None:
        _fail("DONE")
    if execution != "COMPLETED" and result == "PASS":
        _fail("TEACHER_STATUS")
    return teacher_attempt_status(execution, result)


def _error_contract(
    document: Mapping[str, object],
    reset_epoch: int,
    events: list[dict[str, object]],
    boundary: State,
    schema: str = SCHEMA_GENERAL,
) -> None:
    if not isinstance(document.get("failure"), str) or not document["failure"]:
        _fail("ERROR")
    evidence = document.get("failure_evidence")
    teacher_run = schema == SCHEMA_TEACHER
    # Teacher run: a simulation-integrity failure is a broken simulator, so its evidence capture may fail; it is then recorded, not hidden
    sim_integrity = teacher_run and document["failure"].split(":", 1)[0] in SIM_INTEGRITY_CODES
    if (
        type(evidence) is not dict
        or evidence.get("failure_boundary_state") != boundary.value
        or type(evidence.get("physical_action_proven_absent")) is not bool
        or type(evidence.get("capture_errors")) is not list
        or (evidence["capture_errors"] != [] and not sim_integrity)
        or any(not isinstance(item, str) for item in evidence["capture_errors"])
    ):
        _fail("FAILURE_EVIDENCE")
    no_action = evidence["physical_action_proven_absent"]
    if no_action:
        if boundary is not State.IDLE or events or document.get("planning_attempts") != []:
            _fail("FAILURE_EVIDENCE")
        return
    if sim_integrity and evidence["capture_errors"]:
        return
    sample = evidence.get("terminal_sample")
    scene = evidence.get("planning_scene_readback")
    # A terminal stop skips the RECOVER_* chain, so the cup may still be attached to the MoveIt scene. In a Teacher run every failure ends in
    # ERROR from the state it happened in, with the cup attached or detached in MoveIt.
    stopped_in_place = teacher_run or any(
        _terminal_stop_edge(document, State(current), State(following))
        for current, following in zip(document["state_trace"], document["state_trace"][1:])
    )
    if not _physical_sample(sample, reset_epoch) or not (
            _scene_is_detached_world(scene) or stopped_in_place and _scene_is_attached_cup(scene)):
        _fail("FAILURE_EVIDENCE")
    prior_sequences = [
        value["publisher_sequence"]
        for event in events
        for value in (event.get("before"), event.get("after"))
        if _physical_sample(value, reset_epoch)
    ]
    if prior_sequences and sample["publisher_sequence"] <= max(prior_sequences):
        _fail("FAILURE_EVIDENCE")
    release = document.get("release_marker_sequence")
    if release is not None:
        if type(release) is not int or release <= 0 or sample["publisher_sequence"] <= release:
            _fail("RELEASE_ORDER")


def validate_dynamic_manifest_semantics(
    document: Mapping[str, object], *, expected_status: str, expected_reset_epoch: int,
    expected_final_cup_pose_world: list[float] | None = None,
    frozen_execution_policy: Mapping[str, object] | None = None,
) -> AttemptStatus:
    """Reject structurally incoherent manifests and return the Teacher outcome they declare.

    Only the two exact schemas carry a Teacher outcome: the general manifest (with its recovery states) and the Teacher manifest
    (no recovery states, a place record and a process summary). Any other schema, or none, is rejected. Process-quality
    observations (contacts, velocities, release order, scene shadow) are audit-only and never decide the outcome.
    """

    if expected_status not in {"DONE", "ERROR"}:
        _fail("STATUS")
    if (
        type(document) is not dict
        or document.get("status") != expected_status
        or document.get("current_state") != expected_status
        or type(expected_reset_epoch) is not int
        or expected_reset_epoch < 0
    ):
        _fail("STATUS")
    if not is_manifest_of(document, SCHEMA_GENERAL, SCHEMA_TEACHER):
        _fail("SCHEMA")
    schema = document["schema"]
    if frozen_execution_policy is not None and schema != SCHEMA_TEACHER:
        _fail("SCHEMA")      # the frozen Teacher execution policy belongs to the Teacher manifest; the general manifest has none
    workflow = TEACHER_WORKFLOW if schema == SCHEMA_TEACHER else SO101_WORKFLOW
    states, boundaries = _trace_contract(document, expected_status, workflow)
    boundary = boundaries[0] if boundaries else None
    events = _event_contract(document, states, boundary, workflow)
    _planning_contract(document, states, workflow)
    if expected_status == "ERROR":
        _error_contract(document, expected_reset_epoch, events, boundary, schema)
    return _teacher_contract(
        document, expected_status, expected_reset_epoch, expected_final_cup_pose_world, frozen_execution_policy, schema)
