"""ROS-free semantic verification for dynamic execution manifests."""

from __future__ import annotations

import math
from collections.abc import Mapping

from ..application.e2e_acceptance import (
    FINAL_MAX_ANGULAR_SPEED_RAD_S,
    FINAL_MAX_LINEAR_SPEED_M_S,
    FINAL_MAX_UPRIGHT_TILT_RAD,
    FINAL_SUPPORT_HEIGHT_RANGE_M,
    FINAL_XY_TOLERANCE_M,
)
from ..core.domain import State
from ..core.dynamic_pick import DYNAMIC_MOTION_STATES
from ..core.workflow import SO101_WORKFLOW
from .contracts import AttemptStatus


def _success_trace() -> tuple[str, ...]:
    trace = [State.IDLE]
    while trace[-1] not in SO101_WORKFLOW.terminal_states:
        trace.append(SO101_WORKFLOW.transitions[trace[-1]][0])
    return tuple(state.value for state in trace)


_DONE_TRACE = _success_trace()


def _fail(boundary: str) -> None:
    raise ValueError(f"DYNAMIC_MANIFEST_{boundary}")


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


def _trace_contract(document: Mapping[str, object], expected_status: str):
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
        if current not in SO101_WORKFLOW.transitions:
            _fail("TRACE")
        if following not in SO101_WORKFLOW.transitions[current]:
            _fail("TRACE")
    if expected_status == "DONE" and tuple(trace) != _DONE_TRACE:
        _fail("TRACE")
    failure_boundaries = [
        current
        for current, following in zip(states, states[1:])
        if following == SO101_WORKFLOW.transitions[current][1]
    ]
    if expected_status == "ERROR" and not failure_boundaries:
        _fail("TRACE")
    return states, failure_boundaries


def _successful_action_states(states: list[State]) -> list[State]:
    return [
        current
        for current, following in zip(states, states[1:])
        if current in SO101_WORKFLOW.action_states
        and following == SO101_WORKFLOW.transitions[current][0]
    ]


def _event_contract(document: Mapping[str, object], states: list[State], boundary: State | None):
    events = document.get("state_events")
    if type(events) is not list or any(type(item) is not dict for item in events):
        _fail("STATE_EVENTS")
    expected = [state.value for state in _successful_action_states(states)]
    observed = [item.get("state") for item in events]
    if observed != expected:
        expected_with_failed = []
        failed_index = None
        for current, following in zip(states, states[1:]):
            success, failure = SO101_WORKFLOW.transitions[current]
            if current in SO101_WORKFLOW.action_states and following == success:
                expected_with_failed.append(current.value)
            elif boundary is current and following == failure:
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
    for state in _successful_action_states(states):
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


def _planning_contract(document: Mapping[str, object], states: list[State]) -> None:
    planning = document.get("planning_attempts")
    if type(planning) is not list or any(type(item) is not dict for item in planning):
        _fail("PLANNING")
    for state in _successful_action_states(states):
        if state in DYNAMIC_MOTION_STATES and not any(
            item.get("state") == state.value and item.get("accepted") is True
            for item in planning
        ):
            _fail("PLANNING")


def _upright_tilt(orientation: list[float]) -> float:
    x, y, _z, w = orientation
    cosine = max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y)))
    return math.acos(cosine)


def _done_contract(
    document: Mapping[str, object],
    reset_epoch: int,
    events,
    expected_final_cup_pose_world: object,
) -> None:
    if document.get("failure") is not None:
        _fail("DONE")
    release = document.get("release_marker_sequence")
    samples = document.get("final_samples")
    if type(release) is not int or release <= 0 or type(samples) is not list or len(samples) != 1:
        _fail("RELEASE_ORDER")
    final = samples[0]
    if not _physical_sample(final, reset_epoch):
        _fail("FINAL_PHYSICAL")
    if final["publisher_sequence"] <= release:
        _fail("RELEASE_ORDER")
    if not _scene_is_detached_world(document.get("planning_scene_readback")):
        _fail("SCENE")
    validation = next(
        (item for item in events if item.get("state") == "VALIDATE_FINAL_PLACEMENT"), None
    )
    expected = None if validation is None else validation.get("expected_cup_pose_world")
    if not _finite_vector(expected, 7) or not _unit_quaternion(expected[3:]):
        _fail("FINAL_PHYSICAL")
    trusted = expected_final_cup_pose_world
    if trusted is not None:
        if not _finite_vector(trusted, 7) or not _unit_quaternion(trusted[3:]):
            _fail("TRUSTED_FINAL_TARGET")
        position_error = math.dist(expected[:3], trusted[:3])
        orientation_alignment = abs(sum(
            left * right for left, right in zip(expected[3:], trusted[3:])
        ))
        if position_error > 1e-9 or 1.0 - orientation_alignment > 1e-9:
            _fail("TRUSTED_FINAL_TARGET")
        expected = trusted
    position = final["cup_position_world_m"]
    linear = final["cup_linear_velocity_world_m_s"]
    angular = final["cup_angular_velocity_world_rad_s"]
    orientation = final["cup_orientation_world_xyzw"]
    if (
        math.dist(position[:2], expected[:2]) > FINAL_XY_TOLERANCE_M
        or not FINAL_SUPPORT_HEIGHT_RANGE_M[0] <= position[2] <= FINAL_SUPPORT_HEIGHT_RANGE_M[1]
        or _upright_tilt(orientation) > FINAL_MAX_UPRIGHT_TILT_RAD
        or max(abs(value) for value in linear) > FINAL_MAX_LINEAR_SPEED_M_S
        or max(abs(value) for value in angular) > FINAL_MAX_ANGULAR_SPEED_RAD_S
        or final["table_contact"] is not True
        or final["left_contact_count"] != 0
        or final["right_contact_count"] != 0
    ):
        _fail("FINAL_PHYSICAL")


def _error_contract(
    document: Mapping[str, object],
    reset_epoch: int,
    events: list[dict[str, object]],
    boundary: State,
) -> None:
    if not isinstance(document.get("failure"), str) or not document["failure"]:
        _fail("ERROR")
    evidence = document.get("failure_evidence")
    if (
        type(evidence) is not dict
        or evidence.get("failure_boundary_state") != boundary.value
        or type(evidence.get("physical_action_proven_absent")) is not bool
        or evidence.get("capture_errors") != []
    ):
        _fail("FAILURE_EVIDENCE")
    no_action = evidence["physical_action_proven_absent"]
    if no_action:
        if boundary is not State.IDLE or events or document.get("planning_attempts") != []:
            _fail("FAILURE_EVIDENCE")
        return
    sample = evidence.get("terminal_sample")
    scene = evidence.get("planning_scene_readback")
    if not _physical_sample(sample, reset_epoch) or not _scene_is_detached_world(scene):
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
) -> AttemptStatus:
    """Reject structurally present but physically or procedurally incoherent results."""

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
    states, boundaries = _trace_contract(document, expected_status)
    boundary = boundaries[0] if boundaries else None
    events = _event_contract(document, states, boundary)
    _planning_contract(document, states)
    if expected_status == "DONE":
        _done_contract(
            document,
            expected_reset_epoch,
            events,
            expected_final_cup_pose_world,
        )
        return AttemptStatus.PASSED
    _error_contract(document, expected_reset_epoch, events, boundary)
    if document["failure_evidence"]["physical_action_proven_absent"] is True:
        return AttemptStatus.FAILED
    return AttemptStatus.INDETERMINATE
