"""ROS-free validation of correlated SO-101 MuJoCo E2E evidence."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any


SUCCESS_STATE_TRACE = (
    "IDLE",
    "PREPARE_OPEN_GRIPPER",
    "MOVE_ABOVE_OBJECT",
    "DESCEND",
    "CLOSE_GRIPPER",
    "WAIT_GRASP_STABLE",
    "MICRO_LIFT",
    "WAIT_MICRO_LIFT_STABLE",
    "VERIFY_PHYSICAL_GRASP",
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
    "DONE",
)
_MOTION_STATES = frozenset(
    {
        "MOVE_ABOVE_OBJECT",
        "DESCEND",
        "MICRO_LIFT",
        "LIFT",
        "MOVE_ABOVE_PLACE",
        "DESCEND_TO_PLACE",
        "RETREAT",
    }
)
FINAL_XY_TOLERANCE_M = 0.02
FINAL_SUPPORT_HEIGHT_RANGE_M = (0.155, 0.175)
FINAL_MAX_UPRIGHT_TILT_RAD = 0.15
FINAL_MAX_LINEAR_SPEED_M_S = 0.001
FINAL_MAX_ANGULAR_SPEED_RAD_S = 0.05


@dataclass(frozen=True, slots=True)
class AcceptanceReport:
    accepted: bool
    failures: tuple[str, ...]
    physical_outcome: dict[str, object]
    planning_scene_outcome: dict[str, object]

    def to_document(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "failures": list(self.failures),
            "physical_outcome": self.physical_outcome,
            "planning_scene_outcome": self.planning_scene_outcome,
        }


def _mapping(value: object) -> dict[str, Any] | None:
    if type(value) is not dict or not all(type(key) is str for key in value):
        return None
    return value


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _integer(value: object, *, minimum: int = 0) -> int | None:
    if type(value) is not int or value < minimum:
        return None
    return value


def _vector(value: object, size: int) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        return None
    converted = tuple(_finite(item) for item in value)
    if any(item is None for item in converted):
        return None
    return tuple(item for item in converted if item is not None)


def _pose(value: object) -> tuple[float, ...] | None:
    pose = _vector(value, 7)
    if pose is None:
        return None
    norm = math.sqrt(sum(value * value for value in pose[3:]))
    if not math.isfinite(norm) or norm <= 0.0:
        return None
    return (*pose[:3], *(value / norm for value in pose[3:]))


def _quaternion_error(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    dot = abs(sum(a * b for a, b in zip(first[3:], second[3:], strict=True)))
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


def _upright_tilt(pose: tuple[float, ...]) -> float:
    x, y, _z, _w = pose[3:]
    return math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * (x * x + y * y))))


def _append(failures: list[str], code: str) -> None:
    if code not in failures:
        failures.append(code)


def _policy_values(
    policy: dict[str, Any] | None,
    dynamic: dict[str, Any] | None,
    failures: list[str],
) -> dict[str, object] | None:
    if policy is None or dynamic is None:
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")
        return None
    required_positive = (
        "terminal_position_tolerance_m",
        "terminal_orientation_tolerance_rad",
        "final_pose_position_tolerance_m",
        "final_pose_orientation_tolerance_rad",
        "max_upright_tilt_rad",
        "max_linear_speed_m_s",
        "max_angular_speed_rad_s",
    )
    values = {name: _finite(policy.get(name)) for name in required_positive}
    height = _vector(policy.get("support_height_range_m"), 2)
    skew = _integer(policy.get("max_readback_skew_ns"), minimum=1)
    digest = policy.get("sha256")
    valid = bool(
        policy.get("qualification_status") in {"LOCAL_E2E_CANDIDATE", "QUALIFIED"}
        and type(digest) is str
        and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
        and digest == dynamic.get("policy_sha256")
        and all(value is not None and value > 0.0 for value in values.values())
        and height is not None
        and height[0] <= height[1]
        and skew is not None
    )
    if not valid:
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")
        return None
    return {**values, "support_height_range_m": height, "max_readback_skew_ns": skew}


def _validate_identity(
    expected: dict[str, Any] | None,
    dynamic: dict[str, Any] | None,
    perception: dict[str, Any] | None,
    mujoco: dict[str, Any] | None,
    scene: dict[str, Any] | None,
    failures: list[str],
) -> None:
    if any(
        value is None for value in (expected, dynamic, perception, mujoco, scene)
    ):
        _append(failures, "E2E_IDENTITY_MISMATCH")
        return
    assert expected is not None
    assert dynamic is not None
    assert perception is not None
    assert mujoco is not None
    assert scene is not None
    workflow_id = expected.get("workflow_id")
    request_id = expected.get("request_id")
    session_id = expected.get("simulation_session_id")
    reset_epoch = _integer(expected.get("reset_epoch"))
    if (
        not all(
            type(value) is str and bool(value)
            for value in (workflow_id, request_id, session_id)
        )
        or reset_epoch is None
        or dynamic.get("workflow_id") != workflow_id
        or dynamic.get("request_id") != request_id
        or dynamic.get("simulation_session_id") != session_id
        or dynamic.get("expected_reset_epoch") != reset_epoch
        or perception.get("request_id") != request_id
        or mujoco.get("simulation_session_id") != session_id
        or mujoco.get("reset_epoch") != reset_epoch
        or scene.get("simulation_session_id") != session_id
        or scene.get("reset_epoch") != reset_epoch
    ):
        _append(failures, "E2E_IDENTITY_MISMATCH")


def _validate_motion_event(event: dict[str, Any], policy: dict[str, object]) -> bool:
    trajectory_points = _integer(event.get("trajectory_points"), minimum=1)
    generation = _integer(event.get("terminal_joint_state_generation"), minimum=1)
    source_stamp = _integer(event.get("terminal_joint_state_source_stamp_ns"), minimum=1)
    receipt = _finite(event.get("terminal_joint_state_received_monotonic_s"))
    position_error = _finite(event.get("terminal_position_error_m"))
    orientation_error = _finite(event.get("terminal_orientation_error_rad"))
    terminal_pose = _pose(event.get("terminal_fk_pose"))
    target_pose = _pose(event.get("target_pose"))
    reconciliations = event.get("execution_reconciliations")
    if (
        trajectory_points is None
        or generation is None
        or source_stamp is None
        or receipt is None
        or receipt < 0.0
        or position_error is None
        or orientation_error is None
        or position_error > policy["terminal_position_tolerance_m"]
        or orientation_error > policy["terminal_orientation_tolerance_rad"]
        or terminal_pose is None
        or target_pose is None
        or type(reconciliations) is not list
    ):
        return False
    for item in reconciliations:
        record = _mapping(item)
        if record is None:
            return False
        recon_position = _finite(record.get("terminal_position_error_m"))
        recon_orientation = _finite(record.get("terminal_orientation_error_rad"))
        if (
            record.get("moveit_error_code") != -6
            or recon_position is None
            or recon_orientation is None
            or recon_position > policy["terminal_position_tolerance_m"]
            or recon_orientation > policy["terminal_orientation_tolerance_rad"]
        ):
            return False
    return True


def _validate_dynamic(
    dynamic: dict[str, Any] | None,
    perception: dict[str, Any] | None,
    policy: dict[str, object] | None,
    failures: list[str],
) -> None:
    if dynamic is None or perception is None or policy is None:
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")
        return
    trace = dynamic.get("state_trace")
    events = dynamic.get("state_events")
    release_marker = _integer(dynamic.get("release_marker_sequence"))
    if (
        dynamic.get("schema") != "so101-dynamic-mujoco-execute-v1"
        or dynamic.get("status") != "DONE"
        or dynamic.get("current_state") != "DONE"
        or dynamic.get("failure") is not None
        or trace != list(SUCCESS_STATE_TRACE)
        or type(events) is not list
        or release_marker is None
        or dynamic.get("input_source_stamp_ns") != perception.get("source_stamp_ns")
        or dynamic.get("input_frame_id") != "world"
        or type(perception.get("source_frame_id")) is not str
        or not perception["source_frame_id"].strip()
        or perception.get("status") != "OK"
        or perception.get("failure") is not None
        or perception.get("published_cup_pose") is not True
    ):
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")
        return
    records = [_mapping(event) for event in events]
    if any(record is None for record in records):
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")
        return
    typed_records = [record for record in records if record is not None]
    if [record.get("state") for record in typed_records] != list(SUCCESS_STATE_TRACE[1:-1]):
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")
        return
    by_state = {record["state"]: record for record in typed_records}
    resolved_targets = _mapping(dynamic.get("resolved_targets"))
    lift_target = (
        None if resolved_targets is None else _pose(resolved_targets.get("LIFT"))
    )
    place_target = (
        None
        if resolved_targets is None
        else _pose(resolved_targets.get("MOVE_ABOVE_PLACE"))
    )
    if (
        lift_target is None
        or place_target is None
        or math.dist(lift_target[:2], place_target[:2]) <= 0.01
    ):
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")
    if any(
        not _validate_motion_event(by_state[state], policy)
        for state in _MOTION_STATES
    ):
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")
    micro = by_state["MICRO_LIFT"]
    lift_before = _mapping(by_state["LIFT"].get("before"))
    lift_after = _mapping(by_state["LIFT"].get("after"))
    transport_before = _mapping(by_state["MOVE_ABOVE_PLACE"].get("before"))
    transport_after = _mapping(by_state["MOVE_ABOVE_PLACE"].get("after"))
    lift_before_pose = (
        None
        if lift_before is None
        else _vector(lift_before.get("cup_position_world_m"), 3)
    )
    lift_after_pose = (
        None
        if lift_after is None
        else _vector(lift_after.get("cup_position_world_m"), 3)
    )
    transport_before_pose = (
        None
        if transport_before is None
        else _vector(transport_before.get("cup_position_world_m"), 3)
    )
    transport_after_pose = (
        None
        if transport_after is None
        else _vector(transport_after.get("cup_position_world_m"), 3)
    )
    if (
        (_finite(micro.get("physical_cup_lift_m")) or 0.0) < 0.001
        or micro.get("physical_bilateral_contact") is not True
        or micro.get("physical_table_contact") is not False
        or micro.get("validation_failure") is not None
        or lift_before_pose is None
        or lift_after_pose is None
        or lift_after_pose[2] <= lift_before_pose[2]
        or transport_before_pose is None
        or transport_after_pose is None
        or math.dist(transport_before_pose[:2], transport_after_pose[:2]) <= 0.01
    ):
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")
    final_samples = dynamic.get("final_samples")
    last_sample = (
        _mapping(final_samples[-1])
        if type(final_samples) is list and final_samples
        else None
    )
    if (
        last_sample is None
        or (_integer(last_sample.get("publisher_sequence")) or -1) <= release_marker
        or last_sample.get("table_contact") is not True
        or last_sample.get("left_contact_count") != 0
        or last_sample.get("right_contact_count") != 0
    ):
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")
    scene = _mapping(dynamic.get("planning_scene_readback"))
    if (
        scene is None
        or scene.get("attached_object_ids") != []
        or scene.get("world_primitive_counts")
        != {"table": 1, "pedestal": 1, "plastic_cup": 13}
    ):
        _append(failures, "E2E_DYNAMIC_EVIDENCE_INVALID")


def _validate_mujoco(
    mujoco: dict[str, Any] | None,
    dynamic: dict[str, Any] | None,
    policy: dict[str, object] | None,
    failures: list[str],
) -> tuple[dict[str, object], tuple[float, ...] | None]:
    outcome: dict[str, object] = {"stable": False}
    if mujoco is None or dynamic is None or policy is None:
        _append(failures, "E2E_MUJOCO_FINAL_INVALID")
        return outcome, None
    pose = _pose(mujoco.get("cup_pose_world"))
    linear = _vector(mujoco.get("cup_linear_velocity_world_m_s"), 3)
    angular = _vector(mujoco.get("cup_angular_velocity_world_rad_s"), 3)
    marker = _integer(dynamic.get("release_marker_sequence"))
    sequence = _integer(mujoco.get("publisher_sequence"))
    stamp = _integer(mujoco.get("source_timestamp_ns"), minimum=1)
    readback_stamp = _integer(mujoco.get("readback_monotonic_ns"))
    height = policy["support_height_range_m"]
    stable = bool(
        pose is not None
        and linear is not None
        and angular is not None
        and marker is not None
        and sequence is not None
        and sequence > marker
        and stamp is not None
        and mujoco.get("clock_domain") == "mujoco_sim"
        and readback_stamp is not None
        and mujoco.get("paused") is False
        and mujoco.get("table_contact") is True
        and mujoco.get("left_fingertip_contact_count") == 0
        and mujoco.get("right_fingertip_contact_count") == 0
        and height[0] <= pose[2] <= height[1]
        and _upright_tilt(pose) <= policy["max_upright_tilt_rad"]
        and max(abs(value) for value in linear) <= policy["max_linear_speed_m_s"]
        and max(abs(value) for value in angular) <= policy["max_angular_speed_rad_s"]
    )
    outcome.update(
        {
            "stable": stable,
            "publisher_sequence": sequence,
            "pose_xyz_xyzw": None if pose is None else list(pose),
            "support_contact": mujoco.get("table_contact") is True,
            "fingertip_contact": bool(
                mujoco.get("left_fingertip_contact_count")
                or mujoco.get("right_fingertip_contact_count")
            ),
        }
    )
    if not stable:
        _append(failures, "E2E_MUJOCO_FINAL_INVALID")
    return outcome, pose


def _validate_scene(
    scene: dict[str, Any] | None,
    mujoco: dict[str, Any] | None,
    mujoco_pose: tuple[float, ...] | None,
    policy: dict[str, object] | None,
    failures: list[str],
) -> dict[str, object]:
    outcome: dict[str, object] = {"pose_matches_mujoco": False}
    if scene is None or mujoco is None or mujoco_pose is None or policy is None:
        _append(failures, "E2E_PLANNING_SCENE_INVALID")
        return outcome
    objects = _mapping(scene.get("world_objects"))
    cup = None if objects is None else _mapping(objects.get("plastic_cup"))
    table = None if objects is None else _mapping(objects.get("table"))
    pedestal = None if objects is None else _mapping(objects.get("pedestal"))
    scene_pose = None if cup is None else _pose(cup.get("pose_xyz_xyzw"))
    scene_stamp = _integer(scene.get("source_timestamp_ns"), minimum=1)
    mujoco_stamp = _integer(mujoco.get("source_timestamp_ns"), minimum=1)
    scene_readback_stamp = _integer(scene.get("readback_monotonic_ns"))
    mujoco_readback_stamp = _integer(mujoco.get("readback_monotonic_ns"))
    position_error = (
        None
        if scene_pose is None
        else math.dist(scene_pose[:3], mujoco_pose[:3])
    )
    orientation_error = (
        None
        if scene_pose is None
        else _quaternion_error(scene_pose, mujoco_pose)
    )
    valid = bool(
        scene.get("attached_object_ids") == []
        and cup is not None
        and cup.get("primitive_count") == 13
        and table is not None
        and table.get("primitive_count") == 1
        and pedestal is not None
        and pedestal.get("primitive_count") == 1
        and scene_pose is not None
        and scene_stamp is not None
        and mujoco_stamp is not None
        and scene.get("clock_domain") == "system_wall"
        and mujoco.get("clock_domain") == "mujoco_sim"
        and scene_readback_stamp is not None
        and mujoco_readback_stamp is not None
        and scene_readback_stamp >= mujoco_readback_stamp
        and scene_readback_stamp - mujoco_readback_stamp
        <= policy["max_readback_skew_ns"]
        and position_error is not None
        and position_error <= policy["final_pose_position_tolerance_m"]
        and orientation_error is not None
        and orientation_error <= policy["final_pose_orientation_tolerance_rad"]
    )
    outcome.update(
        {
            "pose_matches_mujoco": valid,
            "position_error_m": position_error,
            "orientation_error_rad": orientation_error,
            "attached_object_ids": scene.get("attached_object_ids"),
        }
    )
    if not valid:
        _append(failures, "E2E_PLANNING_SCENE_INVALID")
    return outcome


def validate_e2e_evidence(document: dict[str, object]) -> AcceptanceReport:
    """Validate a complete evidence document and always return a serializable report."""

    failures: list[str] = []
    root = _mapping(document)
    if root is None:
        return AcceptanceReport(
            False,
            ("E2E_EVIDENCE_REJECTED",),
            {"stable": False},
            {"pose_matches_mujoco": False},
        )
    required = {
        "expected_identity",
        "dynamic",
        "perception",
        "mujoco_final",
        "planning_scene_final",
        "policy",
    }
    if not required.issubset(root):
        _append(failures, "E2E_EVIDENCE_REJECTED")
    expected = _mapping(root.get("expected_identity"))
    dynamic = _mapping(root.get("dynamic"))
    perception = _mapping(root.get("perception"))
    mujoco = _mapping(root.get("mujoco_final"))
    scene = _mapping(root.get("planning_scene_final"))
    raw_policy = _mapping(root.get("policy"))
    policy = _policy_values(raw_policy, dynamic, failures)
    _validate_identity(expected, dynamic, perception, mujoco, scene, failures)
    _validate_dynamic(dynamic, perception, policy, failures)
    physical_outcome, mujoco_pose = _validate_mujoco(
        mujoco, dynamic, policy, failures
    )
    planning_scene_outcome = _validate_scene(
        scene, mujoco, mujoco_pose, policy, failures
    )
    return AcceptanceReport(
        accepted=not failures,
        failures=tuple(failures),
        physical_outcome=physical_outcome,
        planning_scene_outcome=planning_scene_outcome,
    )
