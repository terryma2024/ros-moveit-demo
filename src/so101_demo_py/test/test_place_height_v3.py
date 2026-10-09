"""CP-3504 (design section 4): the v3 place target is a strategy with a closed fallback to the v1 target, never a refusal; its record
`teacher_place_height_v3` has its own validator. The v2 validator is untouched (its tests pass as they were)."""

import math
from pathlib import Path

import pytest

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.core import place_height as ph

PACKAGE = Path(__file__).resolve().parents[1]
V3 = PACKAGE / "config/act/teacher_execution_policy_v3.yaml"
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
HOVER_Z = 0.2176344
OLD_TARGET = HOVER_Z - 0.01325


@pytest.fixture(scope="module")
def geometry():
    return ph.cup_geometry_from_scene(SCENE)


@pytest.fixture(scope="module")
def policy():
    return ph.PlaceHeightPolicy.from_document(load_teacher_execution_policy(V3))


THETA = math.radians(4.04)


def test_a_nominal_measurement_is_tilt_compensated_and_validates(geometry, policy):
    record = ph.plan_place_height_v3(THETA, policy.grasp_offset_m, OLD_TARGET, geometry, policy)
    assert record["schema"] == "teacher_place_height_v3" and record["mode"] == "tilt_compensated" and record["fallback_reason"] is None
    assert record["target_tcp_z_m"] == pytest.approx(ph.target_tcp_z(THETA, policy.grasp_offset_m, geometry, policy), abs=1e-12)
    ph.validate_document_v3(record, policy)
    ph.validate_document_v3(record)
    assert set(record) == ph.RECORD_KEYS_V3


@pytest.mark.parametrize("theta_deg,k_offset,reason", [
    (2.0, 0.0, "TILT_OUT_OF_RANGE"), (7.0, 0.0, "TILT_OUT_OF_RANGE"), (float("nan"), 0.0, "TILT_OUT_OF_RANGE"),
    (4.04, 0.002, "K_OUT_OF_BAND"), (4.04, -0.002, "K_OUT_OF_BAND")])
def test_a_measurement_outside_the_calibration_falls_back_with_its_reason_and_validates(geometry, policy, theta_deg, k_offset, reason):
    theta = math.radians(theta_deg)
    record = ph.plan_place_height_v3(theta, policy.grasp_offset_m + k_offset, OLD_TARGET, geometry, policy)
    assert record["mode"] == "fallback_v1" and record["fallback_reason"] == reason
    assert record["target_tcp_z_m"] == OLD_TARGET == record["constant_offset_target_tcp_z_m"]
    ph.validate_document_v3(record, policy)


def test_the_deviation_bound_and_the_workspace_fall_back(geometry, policy):
    # the deviation bound is 2 mm: a v1 target 3 mm off the computed one
    record = ph.plan_place_height_v3(THETA, policy.grasp_offset_m, OLD_TARGET - 0.003, geometry, policy)
    assert record["fallback_reason"] == "TARGET_DEVIATION" and record["target_tcp_z_m"] == OLD_TARGET - 0.003
    assert record["computed_target_tcp_z_m"] == pytest.approx(ph.target_tcp_z(THETA, policy.grasp_offset_m, geometry, policy))
    ph.validate_document_v3(record, policy)
    outside = ph.plan_place_height_v3(THETA, policy.grasp_offset_m, OLD_TARGET, geometry, policy, workspace_z_range=(0.5, 1.0))
    assert outside["fallback_reason"] == "TARGET_DEVIATION"
    ph.validate_document_v3(outside, policy, workspace_z_range=(0.5, 1.0))


def test_a_foreign_scene_falls_back_before_any_other_check(geometry, policy):
    import dataclasses

    foreign = dataclasses.replace(geometry, scene_sha256="0" * 64)
    record = ph.plan_place_height_v3(math.radians(2.0), policy.grasp_offset_m + 0.01, OLD_TARGET, foreign, policy)
    assert record["fallback_reason"] == "SCENE_HASH_MISMATCH" and record["scene_sha256"] == "0" * 64
    ph.validate_document_v3(record, policy)


@pytest.mark.parametrize("reason", ["TILT_UNSTABLE", "JOINT_STATE_STALE", "MEASUREMENT_FAILED", "SCENE_HASH_MISMATCH"])
def test_the_measurement_less_reasons_have_a_valid_record(geometry, policy, reason):
    record = ph.fallback_record(reason, OLD_TARGET, policy, detail="no window in 1 s", geometry=None if reason != "SCENE_HASH_MISMATCH" else geometry)
    if reason == "SCENE_HASH_MISMATCH":
        record["scene_sha256"] = "1" * 64
    ph.validate_document_v3(record, policy)
    ph.validate_document_v3(record)
    assert record["tilt_rad"] is None and record["grasp_offset_m"] is None or reason == "SCENE_HASH_MISMATCH"


def test_the_closed_enum_is_exactly_the_specified_reasons():
    assert ph.FALLBACK_REASONS == ("TILT_UNSTABLE", "TILT_OUT_OF_RANGE", "K_OUT_OF_BAND", "TARGET_DEVIATION", "JOINT_STATE_STALE",
                                   "SCENE_HASH_MISMATCH", "MEASUREMENT_FAILED")
    with pytest.raises(ValueError):
        ph.fallback_record("SOMETHING_ELSE", OLD_TARGET, ph.PlaceHeightPolicy.from_document(load_teacher_execution_policy(V3)))


def test_the_validator_rejects_a_tampered_or_inconsistent_record(geometry, policy):
    good = ph.plan_place_height_v3(THETA, policy.grasp_offset_m, OLD_TARGET, geometry, policy)
    fallback = ph.plan_place_height_v3(math.radians(2.0), policy.grasp_offset_m, OLD_TARGET, geometry, policy)
    cases = [
        ({**good, "target_tcp_z_m": good["target_tcp_z_m"] + 1e-3}, "formula"),
        ({**good, "fallback_reason": "TILT_UNSTABLE"}, "reason on a compensated record"),
        ({**good, "guard_m": 0.0005}, "guard"),
        ({**good, "schema": "teacher_place_height_v2"}, "schema"),
        ({**good, "extra": 1}, "keys"),
        ({**fallback, "target_tcp_z_m": OLD_TARGET + 1e-3}, "fallback target is not the v1 target"),
        ({**fallback, "fallback_reason": "BECAUSE"}, "reason"),
        ({**fallback, "fallback_reason": "K_OUT_OF_BAND"}, "k reason with k in band"),
        ({**good, "mode": "fallback_v1", "fallback_reason": "TILT_OUT_OF_RANGE"}, "tilt reason with the tilt in range"),
        ({**fallback, "fallback_reason": "SCENE_HASH_MISMATCH"}, "scene hash reason without a mismatch"),
        ({**fallback, "fallback_reason": "TARGET_DEVIATION", "computed_target_tcp_z_m": OLD_TARGET}, "deviation reason within the bound"),
        ({**fallback, "mode": "constant"}, "mode"),
        ("not a dict", "type"),
    ]
    for record, label in cases:
        with pytest.raises(ValueError, match="PLACE_HEIGHT"):
            ph.validate_document_v3(record, policy)
    assert label


def test_the_v2_documents_and_validator_are_unchanged(geometry, policy):
    document = ph.plan_place_height(THETA, policy.grasp_offset_m, OLD_TARGET, geometry, policy)
    ph.validate_document(document, policy)
    assert "schema" not in document and set(document) == {
        "mode", "tilt_rad", "grasp_offset_m", "touch_center_z_m", "guard_m", "tracking_offset_m", "target_tcp_z_m",
        "constant_offset_target_tcp_z_m", "scene_sha256", "geometry"}
    with pytest.raises(ph.PlaceHeightRefused):
        ph.plan_place_height(math.radians(2.0), policy.grasp_offset_m, OLD_TARGET, geometry, policy)
