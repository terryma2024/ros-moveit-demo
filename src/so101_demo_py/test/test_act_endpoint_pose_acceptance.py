"""E1's controls for the shared endpoint-pose policy and calculator.

The policy is the frozen rule every collection mode shares, and the calculator is the one place that answers
"do the two poses match the two targets"; these tests pin its closed schema, its boundaries and its refusals.
"""

from __future__ import annotations

import math

import pytest
import yaml

from so101_demo.act.endpoint_pose_acceptance import (
    THRESHOLD_UNITS,
    evaluate_endpoint_pose,
    load_development_runtime,
    load_endpoint_policy,
)
from paths import PACKAGE_ROOT

POLICY = PACKAGE_ROOT / "config/act/endpoint_pose_acceptance_v1.yaml"
START = [0.02, -0.28, 0.165, 0, 0, 0, 1]
END = [-0.07, -0.23, 0.165, 0, 0, 0, 1]


@pytest.fixture()
def policy():
    return load_endpoint_policy(POLICY)


def _tilt(degrees: float) -> list:
    return [*START[:3], math.sin(math.radians(degrees) / 2), 0, 0, math.cos(math.radians(degrees) / 2)]


def test_endpoints_pass_without_process_quality_fields(policy):
    """The plan's verbatim case: the calculator answers only the endpoint question."""

    report = evaluate_endpoint_pose(START, END, START, END, policy)
    assert report["status"] == "PASS"
    assert all(report["passed"].values())
    assert set(report["errors"]) == set(policy["thresholds"])


def test_the_axis_boundary_is_where_the_design_puts_it(policy):
    """0.15 rad is 8.59 degrees: an 8-degree tilt passes, a 20-degree tilt fails."""

    inside = evaluate_endpoint_pose(_tilt(8), END, START, END, policy)
    assert inside["status"] == "PASS" and inside["errors"]["initial_axis_tolerance_rad"] <= 0.15
    outside = evaluate_endpoint_pose(_tilt(20), END, START, END, policy)
    assert outside["status"] == "FAIL" and not outside["passed"]["initial_axis_tolerance_rad"]


def test_yaw_about_the_cups_own_axis_is_not_evaluated(policy):
    yaw = [*START[:3], 0, 0, math.sin(math.radians(90) / 2), math.cos(math.radians(90) / 2)]
    assert evaluate_endpoint_pose(yaw, END, START, END, policy)["status"] == "PASS"


def test_the_final_position_error_separates_xy_from_z(policy):
    """XY and Z have their own tolerances, so a Z-only deviation must fail through the Z field alone."""

    shifted = [END[0], END[1], END[2] + 0.05, *END[3:]]
    report = evaluate_endpoint_pose(START, shifted, START, END, policy)
    assert report["passed"]["final_xy_tolerance_m"] is True
    assert report["passed"]["final_z_tolerance_m"] is False
    assert report["status"] == "FAIL"


@pytest.mark.parametrize("pose", [
    [0.02, -0.28, True, 0, 0, 0, 1],              # a boolean coordinate
    [0.02, -0.28, 0.165, 0, 0, 0, 0.5],           # a quaternion whose norm is not one
    [0.02, -0.28, 0.165, 0, 0, 0],                # six values, not seven
    [0.02, -0.28, float("nan"), 0, 0, 0, 1],      # not finite
])
def test_bad_poses_are_refused_by_name(policy, pose):
    with pytest.raises(ValueError, match="ENDPOINT_POSE_INVALID"):
        evaluate_endpoint_pose(pose, END, START, END, policy)


@pytest.mark.parametrize("document", [
    {"kind": "WRONG", "schema_version": 1, "rule_version": "endpoint_pose_v1",
     "thresholds": {key: 0.1 for key in THRESHOLD_UNITS}},
    {"kind": "ACT_ENDPOINT_POSE_POLICY", "schema_version": 2, "rule_version": "endpoint_pose_v1",
     "thresholds": {key: 0.1 for key in THRESHOLD_UNITS}},
    {"kind": "ACT_ENDPOINT_POSE_POLICY", "schema_version": 1, "rule_version": "endpoint_pose_v2",
     "thresholds": {key: 0.1 for key in THRESHOLD_UNITS}},
    {"kind": "ACT_ENDPOINT_POSE_POLICY", "schema_version": 1, "rule_version": "endpoint_pose_v1",
     "thresholds": {**{key: 0.1 for key in THRESHOLD_UNITS}, "extra": 1}},
    {"kind": "ACT_ENDPOINT_POSE_POLICY", "schema_version": 1, "rule_version": "endpoint_pose_v1",
     "thresholds": {**{key: 0.1 for key in THRESHOLD_UNITS}, "final_z_tolerance_m": True}},
])
def test_bad_policies_are_refused_by_name(tmp_path, document):
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError, match="ENDPOINT_POLICY_INVALID"):
        load_endpoint_policy(path)


RUNTIME = PACKAGE_ROOT / "config/act/endpoint_pose_development_runtime_v1.yaml"


def test_the_authorized_runtime_defaults_load_exactly():
    """Section 5.1's values are what the installed file carries, and they come back unchanged."""

    runtime = load_development_runtime(RUNTIME)
    assert runtime["path_policy"] == {"path_step_s": 0.002, "path_clearance_m": 0.002}
    assert runtime["rgb_sync"] == {"max_age_s": 0.1, "max_skew_s": 0.1}
    assert runtime["safety_release"] == {"support_distance_max_m": 0.002}
    assert runtime["hard_stops"] == {"rtf_min": 0.90, "disk_free_min_bytes": 53687091200}


def _runtime_document() -> dict:
    return {
        "kind": "ACT_ENDPOINT_DEVELOPMENT_RUNTIME", "schema_version": 1,
        "path_policy": {"path_step_s": 0.002, "path_clearance_m": 0.002},
        "rgb_sync": {"max_age_s": 0.1, "max_skew_s": 0.1},
        "safety_release": {"support_distance_max_m": 0.002},
        "hard_stops": {"rtf_min": 0.90, "disk_free_min_bytes": 53687091200},
    }


@pytest.mark.parametrize("patch", [
    {"extra_section": {"a": 1}},
    {"path_policy": {"path_step_s": 0.002}},
    {"hard_stops": {"rtf_min": True, "disk_free_min_bytes": 53687091200}},
    {"hard_stops": {"rtf_min": 0.90, "disk_free_min_bytes": 5.5e10}},
    {"rgb_sync": {"max_age_s": -0.1, "max_skew_s": 0.1}},
    {"kind": "OTHER"},
    {"rgb_sync": {"max_age_s": float("inf"), "max_skew_s": 0.1}},
])
def test_bad_development_runtimes_are_refused_by_name(tmp_path, patch):
    document = {**_runtime_document(), **patch}
    path = tmp_path / "runtime.yaml"
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError, match="DEVELOPMENT_RUNTIME_INVALID"):
        load_development_runtime(path)
