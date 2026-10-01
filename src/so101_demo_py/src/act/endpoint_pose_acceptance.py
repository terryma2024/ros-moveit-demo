"""The shared endpoint-pose acceptance policy: one frozen rule for every collection mode.

The amendment's rule for the cup task answers success with two poses - the start and the end - against
empirically configurable tolerances, instead of a set of process-quality scores. This module owns the policy
document and (below, once implemented) the pure calculator that both the online normal terminal state and the
offline independent QC use, so the two can never disagree about what "passed" means.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

#: the policy document's closed key set and its fixed identity values
POLICY_KIND = "ACT_ENDPOINT_POSE_POLICY"
POLICY_SCHEMA_VERSION = 1
RULE_VERSION = "endpoint_pose_v1"
POLICY_FIELDS = frozenset({"kind", "schema_version", "rule_version", "thresholds"})
#: the five thresholds, in the design's order, with the unit each one is expressed in
THRESHOLD_UNITS = {
    "initial_position_tolerance_m": "m",
    "initial_axis_tolerance_rad": "rad",
    "final_xy_tolerance_m": "m",
    "final_z_tolerance_m": "m",
    "final_axis_tolerance_rad": "rad",
}


def _positive_finite(value, key: str) -> float:
    """A threshold is a finite positive real; booleans, NaN, infinities and non-numbers are refused."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"ENDPOINT_POLICY_INVALID: {key} is not a number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"ENDPOINT_POLICY_INVALID: {key} is not finite and positive")
    if THRESHOLD_UNITS[key] == "rad" and value > math.pi:
        raise ValueError(f"ENDPOINT_POLICY_INVALID: {key} exceeds pi radians")
    return float(value)


def load_endpoint_policy(path: Path) -> dict:
    """Parse the design's closed policy schema, or refuse by name.

    The returned document carries only the four closed keys with float thresholds, so a caller cannot smuggle a
    measurement, an approval or an unknown field into the policy that every gate reads.
    """

    document = yaml.safe_load(Path(path).read_text())
    if not isinstance(document, dict) or set(document) != POLICY_FIELDS:
        raise ValueError("ENDPOINT_POLICY_INVALID: not the closed policy document")
    if (document["kind"] != POLICY_KIND or document["schema_version"] != POLICY_SCHEMA_VERSION
            or document["rule_version"] != RULE_VERSION):
        raise ValueError("ENDPOINT_POLICY_INVALID: unknown kind, schema version or rule version")
    thresholds = document["thresholds"]
    if not isinstance(thresholds, dict) or set(thresholds) != set(THRESHOLD_UNITS):
        raise ValueError("ENDPOINT_POLICY_INVALID: thresholds are not the closed five-field schema")
    return {
        "kind": POLICY_KIND,
        "schema_version": POLICY_SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "thresholds": {key: _positive_finite(thresholds[key], key) for key in THRESHOLD_UNITS},
    }


def _pose(value, label: str) -> tuple:
    """A pose is seven finite reals: xyz plus an xyzw quaternion whose norm is within 1e-3 of one."""

    if not isinstance(value, (list, tuple)) or len(value) != 7:
        raise ValueError(f"ENDPOINT_POSE_INVALID: {label} is not an xyz_xyzw pose")
    numbers = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise ValueError(f"ENDPOINT_POSE_INVALID: {label}[{index}] is not a finite real")
        numbers.append(float(item))
    x, y, z, qx, qy, qz, qw = numbers
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if norm == 0 or abs(norm - 1.0) > 1e-3:
        raise ValueError(f"ENDPOINT_POSE_INVALID: {label} quaternion norm is {norm}")
    return (x, y, z), (qx / norm, qy / norm, qz / norm, qw / norm)


def _axis(quaternion: tuple) -> tuple:
    """The cup's own axis: the body-local +Z rotated by the quaternion, so a yaw about it changes nothing."""

    qx, qy, qz, qw = quaternion
    # R * (0, 0, 1) for an xyzw quaternion
    return (2 * (qx * qz + qw * qy), 2 * (qy * qz - qw * qx), 1 - 2 * (qx * qx + qy * qy))


def _angle_between(left: tuple, right: tuple) -> float:
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right))))
    return math.acos(dot)


def evaluate_endpoint_pose(initial_pose, final_pose, initial_target, final_target, policy: dict) -> dict:
    """The shared pure calculator: two poses against two frozen targets, answering only endpoint questions.

    It performs no IO and touches no live port. It states what the endpoint rule can answer - the two poses match
    the two targets within the frozen thresholds - and nothing about grasp quality, release or stability, which is
    the amendment's whole point: a report may say "endpoint poses passed" and may not say "grasp quality verified".
    """

    thresholds = dict(policy["thresholds"])
    if set(thresholds) != set(THRESHOLD_UNITS):
        raise ValueError("ENDPOINT_POLICY_INVALID: thresholds are not the closed five-field schema")
    start_xyz, start_q = _pose(initial_pose, "initial_pose")
    end_xyz, end_q = _pose(final_pose, "final_pose")
    start_target_xyz, start_target_q = _pose(initial_target, "initial_target")
    end_target_xyz, end_target_q = _pose(final_target, "final_target")

    errors = {
        "initial_position_tolerance_m": math.dist(start_xyz, start_target_xyz),
        "initial_axis_tolerance_rad": _angle_between(_axis(start_q), _axis(start_target_q)),
        "final_xy_tolerance_m": math.dist(end_xyz[:2], end_target_xyz[:2]),
        "final_z_tolerance_m": abs(end_xyz[2] - end_target_xyz[2]),
        "final_axis_tolerance_rad": _angle_between(_axis(end_q), _axis(end_target_q)),
    }
    passed = {key: errors[key] <= thresholds[key] for key in THRESHOLD_UNITS}
    return {"status": "PASS" if all(passed.values()) else "FAIL", "errors": errors, "passed": passed}


#: the development runtime document's fixed identity and its four closed sections with their exact keys
RUNTIME_KIND = "ACT_ENDPOINT_DEVELOPMENT_RUNTIME"
RUNTIME_SCHEMA_VERSION = 1
RUNTIME_FIELDS = frozenset({"kind", "schema_version", "path_policy", "rgb_sync", "safety_release",
                            "hard_stops"})
RUNTIME_SECTIONS = {
    "path_policy": ("path_step_s", "path_clearance_m"),
    "rgb_sync": ("max_age_s", "max_skew_s"),
    "safety_release": ("support_distance_max_m",),
    "hard_stops": ("rtf_min", "disk_free_min_bytes"),
}


def load_development_runtime(path: Path) -> dict:
    """Parse the design's section 5.1 development runtime, or refuse by name.

    These are the user-authorized empirical initial values that let development proceed without measurement
    reports. Each section is closed: an unknown key, a wrong type, a non-finite or non-positive number and an
    integer field carrying a float are refused rather than merged, so a typo cannot silently become a safety
    bound. A CLI-specified run configuration still takes precedence over this installed file.
    """

    document = yaml.safe_load(Path(path).read_text())
    if not isinstance(document, dict) or set(document) != RUNTIME_FIELDS:
        raise ValueError("DEVELOPMENT_RUNTIME_INVALID: not the closed runtime document")
    if document["kind"] != RUNTIME_KIND or document["schema_version"] != RUNTIME_SCHEMA_VERSION:
        raise ValueError("DEVELOPMENT_RUNTIME_INVALID: unknown kind or schema version")
    loaded = {"kind": RUNTIME_KIND, "schema_version": RUNTIME_SCHEMA_VERSION}
    for section, keys in RUNTIME_SECTIONS.items():
        body = document[section]
        if not isinstance(body, dict) or set(body) != set(keys):
            raise ValueError(f"DEVELOPMENT_RUNTIME_INVALID: {section} is not its closed key set")
        values = {}
        for key in keys:
            value = body[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"DEVELOPMENT_RUNTIME_INVALID: {section}.{key} is not a number")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"DEVELOPMENT_RUNTIME_INVALID: {section}.{key} is not finite and positive")
            if key == "disk_free_min_bytes" and not isinstance(value, int):
                raise ValueError(f"DEVELOPMENT_RUNTIME_INVALID: {section}.{key} must be an integer")
            values[key] = value
        loaded[section] = values
    return loaded
