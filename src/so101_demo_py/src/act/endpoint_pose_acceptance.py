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
