"""The Teacher endpoint rule ``teacher_endpoint`` and the Teacher execution policy (pure, standalone).

Task success is answered by one start pose and one end pose read from the executed world against frozen
targets. This module owns the two closed policy documents and the pure judgement; it reads no runtime state.
Missing or untrustworthy observations give ``UNCONFIRMED`` and never ``PASS``; there is no best-of-history
selection, and yaw about the cup axis is not restricted.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import yaml

ENDPOINT_KIND = "ACT_TEACHER_ENDPOINT_POLICY"
EXECUTION_KIND = "ACT_TEACHER_EXECUTION_POLICY"
EXECUTION_POLICY_FILE = "teacher_execution_policy.yaml"
SCHEMA_VERSION = 1
RULE_VERSION = "teacher_endpoint"
ENDPOINT_FIELDS = frozenset({"kind", "schema_version", "rule_version", "tolerances"})
TOLERANCE_UNITS = {
    "initial_position_m": "m",
    "initial_axis_rad": "rad",
    "final_xy_m": "m",
    "final_z_m": "m",
    "final_axis_rad": "rad",
    "settle_s": "s",
}
#: The fields every execution policy shares (the general runtime policy holds exactly these three).
EXECUTION_VALUES = ("state_max_age_s", "state_unavailable_stop_s", "execution_deadline_s")
PLACE_HEIGHT_FIELDS = frozenset({
    "place_height_mode", "place_touchdown_guard_m", "place_tracking_offset_m", "place_tilt_min_rad", "place_tilt_max_rad",
    "place_grasp_offset_m", "place_grasp_offset_half_band_m", "place_target_max_deviation_m", "place_geometry_scene_sha256",
    "place_reference_offset_m",
})
#: The Teacher execution policy: the minimal runtime gates. The motion and carry values, the
#: tilt-compensated place height, the fixed dwells, the arm-stop wait of the release sequence and the provenance of the cup pose
#: (broker RGB-D) and of the verdict (simulator truth).
EXECUTION_SCHEMA = 3
NUMBER_FIELDS = ("grasp_stable_dwell_s", "release_settle_dwell_s", "arm_stop_wait_s", "arm_stop_velocity_rad_s")
TEACHER_POLICY_PROVENANCE = {"cup_pose_source": "broker_rgbd", "verdict_source": "sim_truth"}
TEACHER_EXECUTION_FIELDS = (
    frozenset({"kind", "schema_version", "gripper_close_target_rad", "carry_max_velocity_scaling",
               "carry_max_acceleration_scaling", *EXECUTION_VALUES})
    | PLACE_HEIGHT_FIELDS | frozenset(NUMBER_FIELDS) | frozenset(TEACHER_POLICY_PROVENANCE))
#: Schema 4 (plan 2026-10-20 teacher speed tiers 1 and 2) adds the per-phase free-space MoveIt scaling of MOVE_ABOVE_OBJECT and
#: RETREAT and the PREPARE_OPEN_GRIPPER trajectory duration. A document is closed for its own schema: schema 3 has none of these
#: keys and loads and hashes exactly as before; schema 4 requires all of them. CLOSE_GRIPPER, OPEN_GRIPPER, DESCEND, MICRO_LIFT,
#: the carry, the waits and the contact policy have no key and keep their values.
EXECUTION_SCHEMA_SPEED = 4
SPEED_SCALING_FIELDS = ("move_above_object_velocity_scaling", "move_above_object_acceleration_scaling",
                        "retreat_velocity_scaling", "retreat_acceleration_scaling")
SPEED_DURATION_FIELD = "prepare_open_gripper_duration_s"
SPEED_FIELDS = frozenset((*SPEED_SCALING_FIELDS, SPEED_DURATION_FIELD))
#: the gripper trajectory duration every gripper command had before schema 4 (a hard-coded 2.0 s), and the closed range of the new key
DEFAULT_GRIPPER_DURATION_S = 2.0
PREPARE_OPEN_DURATION_RANGE_S = (0.5, 5.0)
#: Schema 5 (round-2 plan 2026-10-21, S2) is schema 4 plus the two-stage DESCEND and the OPEN_GRIPPER duration: the free-space MoveIt
#: scaling of the approach part of DESCEND, the distance above the grasp pose at which the approach ends (the last part keeps the
#: template scaling), and the OPEN_GRIPPER trajectory duration. Schema 3 and 4 documents are closed without these keys and load and
#: hash exactly as before. CLOSE_GRIPPER keeps its 2.0 s.
EXECUTION_SCHEMA_DESCEND = 5
DESCEND_SCALING_FIELDS = ("descend_approach_velocity_scaling", "descend_approach_acceleration_scaling")
DESCEND_DISTANCE_FIELD = "descend_final_distance_m"
OPEN_DURATION_FIELD = "open_gripper_duration_s"
DESCEND_FIELDS = frozenset((*DESCEND_SCALING_FIELDS, DESCEND_DISTANCE_FIELD, OPEN_DURATION_FIELD))
#: the open range (low, high] of the final distance (m)
DESCEND_FINAL_DISTANCE_RANGE_M = (0.005, 0.05)
#: Schema 6 (R3-a, human approval 2026-10-24) is schema 5 plus one closed `diversity` block: the distributions of the per-episode
#: parameters and the campaign seed (`act/teacher_diversity.py`). The block is frozen with the policy and part of its hash; the actual
#: values of an episode derive from (campaign seed, scene id). Schema 3, 4 and 5 documents are closed without the key and load and hash
#: exactly as before.
EXECUTION_SCHEMA_DIVERSITY = 6
DIVERSITY_FIELD = "diversity"
TEACHER_EXECUTION_FIELDS_BY_SCHEMA = {
    EXECUTION_SCHEMA: TEACHER_EXECUTION_FIELDS,
    EXECUTION_SCHEMA_SPEED: TEACHER_EXECUTION_FIELDS | SPEED_FIELDS,
    EXECUTION_SCHEMA_DESCEND: TEACHER_EXECUTION_FIELDS | SPEED_FIELDS | DESCEND_FIELDS,
    EXECUTION_SCHEMA_DIVERSITY: TEACHER_EXECUTION_FIELDS | SPEED_FIELDS | DESCEND_FIELDS | frozenset({DIVERSITY_FIELD}),
}
QUATERNION_NORM_TOLERANCE = 1e-6
WORLD_FRAME = "world"


def _load_document(source, code: str):
    try:
        raw = Path(source).read_bytes() if isinstance(source, (str, Path)) else bytes(source)
        return yaml.safe_load(raw)
    except (OSError, yaml.YAMLError, ValueError, TypeError) as error:
        raise ValueError(f"{code}: cannot read the document: {error}") from error


def _real(value, key: str, code: str, *, allow_zero: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{code}: {key} is not a number")
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{code}: {key} is not finite and {'non-negative' if allow_zero else 'positive'}")
    return float(value)


def _sha256(document: dict) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def speed_policy_value(policy, key: str, default: float, *, since_schema: int = EXECUTION_SCHEMA_SPEED) -> float:
    """The speed value ``key`` of a loaded Teacher execution policy, or ``default`` for a policy that predates it.

    ``since_schema`` is the first schema that carries the key (4 for the original speed keys, 5 for the DESCEND and OPEN_GRIPPER
    keys). A policy of that schema or later that lacks the key is not a policy this build can run (``TEACHER_POLICY_UNAVAILABLE``);
    an older policy, the general runtime policy and no policy at all keep today's behaviour."""

    if policy is not None and key in policy:
        return float(policy[key])
    if (policy is not None and policy.get("kind") == EXECUTION_KIND
            and type(policy.get("schema_version")) is int and policy["schema_version"] >= since_schema):
        raise RuntimeError("TEACHER_POLICY_UNAVAILABLE: " + key)
    return default


def load_teacher_endpoint_policy(source) -> dict:
    """Load and validate the endpoint policy from YAML bytes or a path; the result carries its sha256."""

    code = "TEACHER_ENDPOINT_POLICY_INVALID"
    document = _load_document(source, code)
    if not isinstance(document, dict) or set(document) != ENDPOINT_FIELDS:
        raise ValueError(f"{code}: not the closed policy document")
    if (document["kind"] != ENDPOINT_KIND or type(document["schema_version"]) is not int
            or document["schema_version"] != SCHEMA_VERSION or document["rule_version"] != RULE_VERSION):
        raise ValueError(f"{code}: unknown kind, schema version or rule version")
    tolerances = document["tolerances"]
    if not isinstance(tolerances, dict) or set(tolerances) != set(TOLERANCE_UNITS):
        raise ValueError(f"{code}: tolerances are not the closed six-field schema")
    clean = {}
    for key, unit in TOLERANCE_UNITS.items():
        value = _real(tolerances[key], key, code, allow_zero=key == "settle_s")
        if unit == "rad" and value > math.pi:
            raise ValueError(f"{code}: {key} exceeds pi radians")
        clean[key] = value
    policy = {"kind": ENDPOINT_KIND, "schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
              "tolerances": clean}
    return {**policy, "policy_sha256": _sha256(policy)}


def load_teacher_execution_policy(source) -> dict:
    """Load and validate the Teacher execution policy (schema 3: tilt-compensated place height; schema 4: plus the speed keys; schema 5: plus the DESCEND stage and OPEN_GRIPPER keys; schema 6: plus the closed diversity block)
    from YAML bytes or a path, with its sha256. An unknown schema, an unknown place height mode, a missing or extra field is
    refused (``TEACHER_EXECUTION_POLICY_INVALID``)."""

    code = "TEACHER_EXECUTION_POLICY_INVALID"
    document = _load_document(source, code)
    if not isinstance(document, dict) or "schema_version" not in document:
        raise ValueError(f"{code}: not the closed policy document")
    version = document["schema_version"]
    if (document.get("kind") != EXECUTION_KIND or type(version) is not int
            or version not in TEACHER_EXECUTION_FIELDS_BY_SCHEMA):
        raise ValueError(f"{code}: unknown kind or schema version")
    if set(document) != TEACHER_EXECUTION_FIELDS_BY_SCHEMA[version]:
        raise ValueError(f"{code}: not the closed policy document")
    policy = {"kind": EXECUTION_KIND, "schema_version": version}
    for key in EXECUTION_VALUES:
        policy[key] = _real(document[key], key, code, allow_zero=False)
    target = document["gripper_close_target_rad"]
    if (isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target)
            or not -0.1 <= target <= 0.1):
        raise ValueError(f"{code}: gripper_close_target_rad is not a finite angle within 0.1 rad of zero")
    policy["gripper_close_target_rad"] = float(target)
    scaling_keys = ("carry_max_velocity_scaling", "carry_max_acceleration_scaling")
    if version >= EXECUTION_SCHEMA_SPEED:
        scaling_keys += SPEED_SCALING_FIELDS
    if version >= EXECUTION_SCHEMA_DESCEND:
        scaling_keys += DESCEND_SCALING_FIELDS
    for key in scaling_keys:
        value = document[key]
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                or not 0 < value <= 1):
            raise ValueError(f"{code}: {key} is not a finite scaling in (0, 1]")
        policy[key] = float(value)
    duration_keys = ()
    if version >= EXECUTION_SCHEMA_SPEED:
        duration_keys += (SPEED_DURATION_FIELD,)
    if version >= EXECUTION_SCHEMA_DESCEND:
        duration_keys += (OPEN_DURATION_FIELD,)
    for key in duration_keys:
        duration = document[key]
        low, high = PREPARE_OPEN_DURATION_RANGE_S
        if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration)
                or not low <= duration <= high):
            raise ValueError(f"{code}: {key} is not a finite duration within {low} to {high} s")
        policy[key] = float(duration)
    if version >= EXECUTION_SCHEMA_DESCEND:
        distance = document[DESCEND_DISTANCE_FIELD]
        low, high = DESCEND_FINAL_DISTANCE_RANGE_M
        if (isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance)
                or not low < distance <= high):
            raise ValueError(f"{code}: {DESCEND_DISTANCE_FIELD} is not a finite distance above {low} m through {high} m")
        policy[DESCEND_DISTANCE_FIELD] = float(distance)
    if version >= EXECUTION_SCHEMA_DIVERSITY:
        from .teacher_diversity import parse_diversity

        try:
            policy[DIVERSITY_FIELD] = parse_diversity(document[DIVERSITY_FIELD])
        except ValueError as error:
            raise ValueError(f"{code}: {error}") from error
    from ..core.place_height import MODE, PlaceHeightPolicy

    if document["place_height_mode"] != MODE:
        raise ValueError(f"{code}: place_height_mode is not a known mode")
    policy["place_height_mode"] = MODE
    for key in sorted(PLACE_HEIGHT_FIELDS - {"place_height_mode", "place_geometry_scene_sha256"}):
        value = document[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{code}: {key} is not a finite number")
        policy[key] = float(value)
    sha = document["place_geometry_scene_sha256"]
    if type(sha) is not str:
        raise ValueError(f"{code}: place_geometry_scene_sha256 is not a sha256")
    policy["place_geometry_scene_sha256"] = sha
    try:
        PlaceHeightPolicy.from_document(policy)
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError(f"{code}: {error}") from error
    for key in NUMBER_FIELDS:
        policy[key] = _real(document[key], key, code, allow_zero=False)
    if not 0.0 < policy["arm_stop_wait_s"] <= 5.0 or not 0.0 < policy["arm_stop_velocity_rad_s"] <= 0.01:
        raise ValueError(f"{code}: arm_stop_wait_s or arm_stop_velocity_rad_s is out of range")
    if policy["grasp_stable_dwell_s"] > 5.0 or policy["release_settle_dwell_s"] > 5.0:
        raise ValueError(f"{code}: a dwell exceeds 5 s")
    for key, wanted in TEACHER_POLICY_PROVENANCE.items():
        if document[key] != wanted:
            raise ValueError(f"{code}: {key} is not {wanted}")
        policy[key] = wanted
    return {**policy, "policy_sha256": _sha256(policy)}


def _quaternion(value):
    """Return a validated (x, y, z, w) tuple or None when it is not finite and unit-norm."""

    if not isinstance(value, dict) or set(value) != {"x", "y", "z", "w"}:
        return None
    parts = []
    for key in ("x", "y", "z", "w"):
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            return None
        parts.append(float(item))
    if abs(math.sqrt(sum(p * p for p in parts)) - 1.0) > QUATERNION_NORM_TOLERANCE:
        return None
    return tuple(parts)


def _position(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    out = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            return None
        out.append(float(item))
    return tuple(out)


def _body_axis(q) -> tuple:
    """Body +Z rotated into the world frame by the xyzw quaternion."""

    x, y, z, w = q
    return (2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y))


def _angle(a, b) -> float:
    dot = sum(i * j for i, j in zip(a, b))
    return math.acos(max(-1.0, min(1.0, dot)))


def _tilt(q) -> float:
    return _angle(_body_axis(q), (0.0, 0.0, 1.0))


def _target(value, label: str):
    if not isinstance(value, dict):
        raise ValueError(f"TEACHER_ENDPOINT_TARGET_INVALID: {label} is not a pose")
    position, quaternion = _position(value.get("position")), _quaternion(value.get("orientation"))
    if position is None or quaternion is None:
        raise ValueError(f"TEACHER_ENDPOINT_TARGET_INVALID: {label} position or quaternion is invalid")
    return position, quaternion


def validate_task_targets(policy: dict, start_target: dict, end_target: dict) -> None:
    """Refuse targets that cannot describe a real transfer that ends upright."""

    tol = policy["tolerances"]
    start_position, _ = _target(start_target, "start_target")
    end_position, end_quaternion = _target(end_target, "end_target")
    if _tilt(end_quaternion) > tol["final_axis_rad"]:
        raise ValueError("TEACHER_ENDPOINT_TARGET_NOT_UPRIGHT: end target axis tilt exceeds final_axis_rad")
    distance = math.hypot(end_position[0] - start_position[0], end_position[1] - start_position[1])
    if not distance > tol["initial_position_m"] + tol["final_xy_m"]:
        raise ValueError("TEACHER_ENDPOINT_TARGETS_COINCIDENT: start and end XY distance is not above "
                         "initial_position_m + final_xy_m")


def _observation(value):
    """Return (parsed or None, problem or None) for one observation."""

    if value is None:
        return None, "observation is missing"
    if not isinstance(value, dict):
        return None, "observation is not a mapping"
    position, quaternion = _position(value.get("position")), _quaternion(value.get("orientation"))
    time_s = value.get("simulation_time_s")
    if position is None:
        return None, "position is not finite"
    if quaternion is None:
        return None, "quaternion is not finite and unit-norm"
    if isinstance(time_s, bool) or not isinstance(time_s, (int, float)) or not math.isfinite(time_s):
        return None, "simulation time is not finite"
    if value.get("frame_id") != WORLD_FRAME:
        return None, "frame is not world"
    for key in ("object_id", "session_id"):
        if not isinstance(value.get(key), str) or not value[key]:
            return None, f"{key} is missing"
    if isinstance(value.get("reset_epoch"), bool) or not isinstance(value.get("reset_epoch"), int):
        return None, "reset_epoch is missing"
    return {"position": position, "quaternion": quaternion, "time": float(time_s)}, None


def evaluate_teacher_endpoint(policy: dict, *, start_target: dict, end_target: dict,
                              start_observation, end_observation) -> dict:
    """Judge one start and one end observation against the frozen targets.

    Targets are validated first and raise ``ValueError``. Observation problems give ``UNCONFIRMED``;
    otherwise any exceeded tolerance gives ``FAIL``.
    """

    validate_task_targets(policy, start_target, end_target)
    tol = policy["tolerances"]
    start_position, start_quaternion = _target(start_target, "start_target")
    end_position, _ = _target(end_target, "end_target")
    unconfirmed: list[str] = []
    start, problem = _observation(start_observation)
    if problem:
        unconfirmed.append(f"START_OBSERVATION_UNCONFIRMED: {problem}")
    end, problem = _observation(end_observation)
    if problem:
        unconfirmed.append(f"END_OBSERVATION_UNCONFIRMED: {problem}")
    if start and end:
        for key in ("object_id", "session_id", "reset_epoch"):
            if start_observation[key] != end_observation[key]:
                unconfirmed.append(f"OBSERVATION_IDENTITY_MISMATCH: {key} differs between start and end")
        if not end["time"] > start["time"]:
            unconfirmed.append("OBSERVATION_TIME_ORDER_INVALID: end simulation time is not after start")
    measured = {key: None for key in (
        "initial_position_error_m", "initial_axis_angle_rad", "final_xy_error_m", "final_z_error_m",
        "final_axis_tilt_rad")}
    failures: list[str] = []
    if start:
        measured["initial_position_error_m"] = math.dist(start["position"], start_position)
        measured["initial_axis_angle_rad"] = _angle(_body_axis(start["quaternion"]),
                                                    _body_axis(start_quaternion))
        if measured["initial_position_error_m"] > tol["initial_position_m"]:
            failures.append("INITIAL_POSITION_OUT_OF_TOLERANCE")
        if measured["initial_axis_angle_rad"] > tol["initial_axis_rad"]:
            failures.append("INITIAL_AXIS_OUT_OF_TOLERANCE")
    if end:
        measured["final_xy_error_m"] = math.hypot(end["position"][0] - end_position[0],
                                                  end["position"][1] - end_position[1])
        measured["final_z_error_m"] = abs(end["position"][2] - end_position[2])
        measured["final_axis_tilt_rad"] = _tilt(end["quaternion"])
        if measured["final_xy_error_m"] > tol["final_xy_m"]:
            failures.append("FINAL_XY_OUT_OF_TOLERANCE")
        if measured["final_z_error_m"] > tol["final_z_m"]:
            failures.append("FINAL_Z_OUT_OF_TOLERANCE")
        if measured["final_axis_tilt_rad"] > tol["final_axis_rad"]:
            failures.append("FINAL_AXIS_OUT_OF_TOLERANCE")
    if unconfirmed:
        result, reasons = "UNCONFIRMED", unconfirmed + failures
    elif failures:
        result, reasons = "FAIL", failures
    else:
        result, reasons = "PASS", []
    return {
        "rule_version": RULE_VERSION,
        "policy_sha256": policy["policy_sha256"],
        "result": result,
        "reasons": reasons,
        "measured": measured,
        "start_target": start_target,
        "end_target": end_target,
        "start_observation": start_observation,
        "end_observation": end_observation,
    }
