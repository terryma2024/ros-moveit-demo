"""The tilt-compensated place height (CP-3480 / CP-3394, CP-3504). Pure part: the geometry, the policy fields, the bounds, and the
place target as a strategy with a closed fallback to the reference target - never a refusal - with its own record validator. The
numbers in the comments are the 20 retained PASS bags of the force-stop investigation."""

import hashlib
import math

import pytest
import yaml

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.core import place_height as ph
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
TEACHER_POLICY = PACKAGE / "config/act/teacher_execution_policy.yaml"
OLD_TARGET_Z = 0.2176344 - 0.01325                    # the constant-offset reference target of the retained bags
THETA = math.radians(4.04)


@pytest.fixture(scope="module")
def geometry():
    return ph.cup_geometry_from_scene(SCENE)


@pytest.fixture()
def policy_document():
    return yaml.safe_load(TEACHER_POLICY.read_bytes())


@pytest.fixture()
def policy():
    return ph.PlaceHeightPolicy.from_document(load_teacher_execution_policy(TEACHER_POLICY))


# ---- the geometry: exact formula, read from the frozen scene ---------------------------------------------------------------------

def test_the_geometry_is_read_from_the_scene_and_the_formula_is_exact(geometry):
    assert (geometry.table_top_z_m, geometry.half_height_m, geometry.rim_radius_m) == pytest.approx((0.12, 0.045, 0.040))
    assert geometry.scene_sha256 == hashlib.sha256(SCENE.read_bytes()).hexdigest()
    # z_touch(theta) = 0.12 + c cos(theta) + r sin(theta); measured at first contact in the 20 retained bags: 0.16770 (sd 0.01 mm)
    assert ph.touch_center_z(THETA, geometry) == pytest.approx(0.12 + 0.045 * math.cos(THETA) + 0.040 * math.sin(THETA), abs=1e-12)
    assert ph.touch_center_z(THETA, geometry) == pytest.approx(0.167706, abs=2e-6)
    assert ph.touch_center_z(0.0, geometry) == pytest.approx(0.165)


def test_the_wall_corners_become_the_lowest_point_only_above_about_56_degrees(geometry):
    assert geometry.wall_corner_radius_m == pytest.approx(0.0413, abs=1e-4) and geometry.wall_corner_z_m == pytest.approx(-0.043)
    for degrees in (0.5, 3.0, 4.04, 5.5, 10.0, 30.0, 55.0):
        theta = math.radians(degrees)
        assert ph.lowest_point_height(theta, geometry) == pytest.approx(ph.touch_center_z(theta, geometry), abs=1e-12), degrees
    crossover = next(d / 100 for d in range(4000, 7000) if ph.lowest_point_height(math.radians(d / 100), geometry)
                     > ph.touch_center_z(math.radians(d / 100), geometry) + 1e-12)
    assert 56.0 <= crossover <= 57.5, crossover
    assert ph.lowest_point_height(math.radians(60.0), geometry) > ph.touch_center_z(math.radians(60.0), geometry)


def test_the_policy_pins_the_scene_the_geometry_was_fitted_for(geometry, policy):
    assert policy.scene_sha256 == geometry.scene_sha256, "scene.xml changed: refit the place height and re-issue the policy"


# ---- the policy ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("change", [
    {"place_height_mode": "constant"}, {"place_height_mode": None}, {"schema_version": 2}, {"schema_version": "3"},
    {"place_touchdown_guard_m": 0.0}, {"place_touchdown_guard_m": -0.0003}, {"place_touchdown_guard_m": 0.00005},
    {"place_touchdown_guard_m": 0.0011}, {"place_touchdown_guard_m": float("nan")},
    {"place_touchdown_guard_m": 0.0003}, {"place_touchdown_guard_m": 0.0006}, {"place_touchdown_guard_m": 0.0008},
    {"place_touchdown_guard_m": 0.00064},
    {"place_tracking_offset_m": -1e-4}, {"place_tracking_offset_m": 0.002},
    {"place_tilt_min_rad": 0.0}, {"place_tilt_min_rad": 0.1, "place_tilt_max_rad": 0.09}, {"place_tilt_max_rad": 0.5},
    {"place_grasp_offset_half_band_m": 0.0001}, {"place_grasp_offset_half_band_m": 0.01},
    {"place_target_max_deviation_m": 0.0}, {"place_target_max_deviation_m": 0.02},
    {"place_geometry_scene_sha256": "abc"}, {"place_geometry_scene_sha256": "G" * 64}, {"place_reference_offset_m": 0.5},
    {"place_grasp_offset_m": "0.037"}, {"place_grasp_offset_m": True},
])
def test_the_loader_refuses_unknown_modes_and_out_of_range_values(tmp_path, policy_document, change):
    policy_document.update(change)
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_teacher_execution_policy(yaml.safe_dump(policy_document).encode())


def test_the_loader_refuses_missing_extra_and_mixed_fields(policy_document):
    for key in ph_fields():
        missing = dict(policy_document)
        del missing[key]
        with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
            load_teacher_execution_policy(yaml.safe_dump(missing).encode())
    extra = dict(policy_document, place_descend_offset_m=-0.01325)                       # the policy cannot express the constant
    with pytest.raises(ValueError, match="TEACHER_EXECUTION_POLICY_INVALID"):
        load_teacher_execution_policy(yaml.safe_dump(extra).encode())


def ph_fields():
    from so101_demo.act.teacher_endpoint import PLACE_HEIGHT_FIELDS
    return sorted(PLACE_HEIGHT_FIELDS)


def test_the_effective_guard_stays_inside_the_swept_safe_band(policy):
    """The offline sweep: 0.1 mm chatters, 0.2-0.3 mm runs to 97-99.8% of the compression limit, 0.35 mm and past is clean. The
    worst case is the guard minus the k half band, so that is what the loader bounds (and the guard plus the band above)."""
    assert ph.GUARD_MIN_M >= 3.5e-4
    assert policy.guard_m - policy.grasp_offset_half_band_m >= 3.5e-4 - 1e-12
    assert policy.guard_m + policy.grasp_offset_half_band_m <= 1e-3 + 1e-12
    fields = {f: getattr(policy, f) for f in policy.__slots__}
    for guard, band, ok in ((0.0007, 0.0003, True), (0.00065, 0.0003, True), (0.00064, 0.0003, False),
                            (0.0007, 0.0004, False), (0.00068, 0.0003, True)):
        candidate = ph.PlaceHeightPolicy(**{**fields, "guard_m": guard, "grasp_offset_half_band_m": band})
        if ok:
            candidate.validate()
        else:
            with pytest.raises(ValueError):
                candidate.validate()


def test_the_guard_is_strictly_positive_and_bounded(policy):
    assert 0.0 < ph.GUARD_MIN_M <= policy.guard_m <= ph.GUARD_MAX_M == 1e-3
    with pytest.raises(ValueError, match="guard"):
        ph.PlaceHeightPolicy(**{**{f: getattr(policy, f) for f in policy.__slots__}, "guard_m": 0.0}).validate()


# ---- the target ----------------------------------------------------------------------------------------------------------------

def test_the_target_ends_the_actual_arm_the_guard_past_first_contact(geometry, policy):
    k = policy.grasp_offset_m
    target = ph.target_tcp_z(THETA, k, geometry, policy)
    assert target == pytest.approx(0.167706 + k + policy.tracking_offset_m - policy.guard_m, abs=2e-6)
    # against the 20 retained bags: the reference target sits 0.785 mm (commanded) below the TCP height of first contact, and the arm
    # ends 0.943 mm below it; the new target is the guard below
    first_contact_tcp = 0.205170
    assert first_contact_tcp - (target - policy.tracking_offset_m) == pytest.approx(policy.guard_m, abs=2e-5)       # k and z_touch vs the 20 bags' measured contact: within 10 um
    assert target > OLD_TARGET_Z and (target - OLD_TARGET_Z) == pytest.approx(0.234e-3, abs=2e-5)


def test_the_deviation_bound_covers_the_calibrated_range_and_no_more(geometry, policy):
    spread = []
    for theta in (policy.tilt_min_rad, policy.tilt_max_rad):
        for k in (policy.grasp_offset_m - policy.grasp_offset_half_band_m, policy.grasp_offset_m + policy.grasp_offset_half_band_m):
            spread.append(ph.target_tcp_z(theta, k, geometry, policy) - OLD_TARGET_Z)
    assert max(abs(v) for v in spread) < policy.max_deviation_m <= 0.002 and max(abs(v) for v in spread) > 0.0013


# ---- the place target is a strategy with a closed fallback, never a refusal ------------------------------------------------------

def test_a_nominal_measurement_is_tilt_compensated_and_validates(geometry, policy):
    record = ph.plan_place_height(THETA, policy.grasp_offset_m, OLD_TARGET_Z, geometry, policy)
    assert record["schema"] == "teacher_place_height" and record["mode"] == "tilt_compensated" and record["fallback_reason"] is None
    assert record["target_tcp_z_m"] == pytest.approx(ph.target_tcp_z(THETA, policy.grasp_offset_m, geometry, policy), abs=1e-12)
    ph.validate_document(record, policy)
    ph.validate_document(record)
    assert set(record) == ph.RECORD_KEYS


@pytest.mark.parametrize("theta_deg,k_offset,reason", [
    (2.0, 0.0, "TILT_OUT_OF_RANGE"), (7.0, 0.0, "TILT_OUT_OF_RANGE"), (float("nan"), 0.0, "TILT_OUT_OF_RANGE"),
    (4.04, 0.002, "K_OUT_OF_BAND"), (4.04, -0.002, "K_OUT_OF_BAND")])
def test_a_measurement_outside_the_calibration_falls_back_with_its_reason_and_validates(geometry, policy, theta_deg, k_offset, reason):
    theta = math.radians(theta_deg)
    record = ph.plan_place_height(theta, policy.grasp_offset_m + k_offset, OLD_TARGET_Z, geometry, policy)
    assert record["mode"] == "fallback_reference" and record["fallback_reason"] == reason
    assert record["target_tcp_z_m"] == OLD_TARGET_Z == record["constant_offset_target_tcp_z_m"]
    ph.validate_document(record, policy)


def test_the_deviation_bound_and_the_workspace_fall_back(geometry, policy):
    # the deviation bound is 2 mm: a reference target 3 mm off the computed one
    record = ph.plan_place_height(THETA, policy.grasp_offset_m, OLD_TARGET_Z - 0.003, geometry, policy)
    assert record["fallback_reason"] == "TARGET_DEVIATION" and record["target_tcp_z_m"] == OLD_TARGET_Z - 0.003
    assert record["computed_target_tcp_z_m"] == pytest.approx(ph.target_tcp_z(THETA, policy.grasp_offset_m, geometry, policy))
    ph.validate_document(record, policy)
    outside = ph.plan_place_height(THETA, policy.grasp_offset_m, OLD_TARGET_Z, geometry, policy, workspace_z_range=(0.5, 1.0))
    assert outside["fallback_reason"] == "TARGET_DEVIATION"
    ph.validate_document(outside, policy, workspace_z_range=(0.5, 1.0))


def test_a_foreign_scene_falls_back_before_any_other_check(geometry, policy):
    import dataclasses

    foreign = dataclasses.replace(geometry, scene_sha256="0" * 64)
    record = ph.plan_place_height(math.radians(2.0), policy.grasp_offset_m + 0.01, OLD_TARGET_Z, foreign, policy)
    assert record["fallback_reason"] == "SCENE_HASH_MISMATCH" and record["scene_sha256"] == "0" * 64
    ph.validate_document(record, policy)


@pytest.mark.parametrize("reason", ["TILT_UNSTABLE", "JOINT_STATE_STALE", "MEASUREMENT_FAILED", "SCENE_HASH_MISMATCH"])
def test_the_measurement_less_reasons_have_a_valid_record(geometry, policy, reason):
    record = ph.fallback_record(reason, OLD_TARGET_Z, policy, detail="no window in 1 s", geometry=None if reason != "SCENE_HASH_MISMATCH" else geometry)
    if reason == "SCENE_HASH_MISMATCH":
        record["scene_sha256"] = "1" * 64
    ph.validate_document(record, policy)
    ph.validate_document(record)
    assert record["tilt_rad"] is None and record["grasp_offset_m"] is None or reason == "SCENE_HASH_MISMATCH"


def test_the_closed_enum_is_exactly_the_specified_reasons():
    assert ph.FALLBACK_REASONS == ("TILT_UNSTABLE", "TILT_OUT_OF_RANGE", "K_OUT_OF_BAND", "TARGET_DEVIATION", "JOINT_STATE_STALE",
                                   "SCENE_HASH_MISMATCH", "MEASUREMENT_FAILED")
    with pytest.raises(ValueError):
        ph.fallback_record("SOMETHING_ELSE", OLD_TARGET_Z, ph.PlaceHeightPolicy.from_document(load_teacher_execution_policy(TEACHER_POLICY)))


def test_the_validator_rejects_a_tampered_or_inconsistent_record(geometry, policy):
    good = ph.plan_place_height(THETA, policy.grasp_offset_m, OLD_TARGET_Z, geometry, policy)
    fallback = ph.plan_place_height(math.radians(2.0), policy.grasp_offset_m, OLD_TARGET_Z, geometry, policy)
    cases = [
        ({**good, "target_tcp_z_m": good["target_tcp_z_m"] + 1e-3}, "formula"),
        ({**good, "fallback_reason": "TILT_UNSTABLE"}, "reason on a compensated record"),
        ({**good, "guard_m": 0.0005}, "guard"),
        ({**good, "schema": "teacher_place_height_unknown"}, "schema"),
        ({**good, "extra": 1}, "keys"),
        ({**fallback, "target_tcp_z_m": OLD_TARGET_Z + 1e-3}, "fallback target is not the reference target"),
        ({**fallback, "fallback_reason": "BECAUSE"}, "reason"),
        ({**fallback, "fallback_reason": "K_OUT_OF_BAND"}, "k reason with k in band"),
        ({**good, "mode": "fallback_reference", "fallback_reason": "TILT_OUT_OF_RANGE"}, "tilt reason with the tilt in range"),
        ({**fallback, "fallback_reason": "SCENE_HASH_MISMATCH"}, "scene hash reason without a mismatch"),
        ({**fallback, "fallback_reason": "TARGET_DEVIATION", "computed_target_tcp_z_m": OLD_TARGET_Z}, "deviation reason within the bound"),
        ({**fallback, "mode": "constant"}, "mode"),
        ("not a dict", "type"),
    ]
    for record, label in cases:
        with pytest.raises(ValueError, match="PLACE_HEIGHT"):
            ph.validate_document(record, policy)
    assert label
