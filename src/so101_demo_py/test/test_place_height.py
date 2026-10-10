"""CP-3480 / CP-3394: the tilt-compensated place height. Pure part: the geometry, the policy v2 loader, the bounds and the audit
document. The numbers in the comments are the 20 retained PASS bags of the force-stop investigation."""

import hashlib
import math

import pytest
import yaml

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.core import place_height as ph
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT
SCENE = PACKAGE / "assets/mujoco/act/scene.xml"
V2 = PACKAGE / "config/act/teacher_execution_policy.yaml"
OLD_TARGET_Z = 0.2176344 - 0.01325                    # the v1 constant-offset target of the retained bags
THETA = math.radians(4.04)


@pytest.fixture(scope="module")
def geometry():
    return ph.cup_geometry_from_scene(SCENE)


@pytest.fixture()
def policy_document():
    return yaml.safe_load(V2.read_bytes())


@pytest.fixture()
def policy():
    return ph.PlaceHeightPolicy.from_document(load_teacher_execution_policy(V2))


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


# ---- policy v2 ---------------------------------------------------------------------------------------------------------------------

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
    # against the 20 retained bags: the v1 target sits 0.785 mm (commanded) below the TCP height of first contact, and the arm
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


def test_a_nominal_measurement_plans_and_the_document_validates(geometry, policy):
    document = ph.plan_place_height(THETA, policy.grasp_offset_m, OLD_TARGET_Z, geometry, policy)
    assert document["mode"] == "tilt_compensated" and document["scene_sha256"] == geometry.scene_sha256
    ph.validate_document(document)
    ph.validate_document(document, policy)
    for change in ({"target_tcp_z_m": document["target_tcp_z_m"] + 1e-6}, {"guard_m": 0.0}, {"mode": "constant"},
                   {"tilt_rad": float("nan")}, {"geometry": {"table_top_z_m": 0.12}}):
        with pytest.raises(ValueError, match="PLACE_HEIGHT"):
            ph.validate_document({**document, **change}, policy)
    with pytest.raises(ValueError, match="PLACE_HEIGHT"):
        ph.validate_document({**document, "tilt_rad": policy.tilt_max_rad + 0.01,
                              "target_tcp_z_m": ph.target_tcp_z(policy.tilt_max_rad + 0.01, document["grasp_offset_m"], geometry, policy)},
                             policy)


@pytest.mark.parametrize("theta_deg,k_offset,code", [
    (2.9, 0.0, ph.TILT_OUT_OF_RANGE), (5.6, 0.0, ph.TILT_OUT_OF_RANGE), (float("nan"), 0.0, ph.TILT_OUT_OF_RANGE),
    (4.04, 0.0004, ph.HEIGHT_OUT_OF_BOUNDS), (4.04, -0.0004, ph.HEIGHT_OUT_OF_BOUNDS)])
def test_a_measurement_outside_the_calibration_is_refused_with_its_code(geometry, policy, theta_deg, k_offset, code):
    with pytest.raises(ph.PlaceHeightRefused) as refusal:
        ph.plan_place_height(math.radians(theta_deg), policy.grasp_offset_m + k_offset, OLD_TARGET_Z, geometry, policy)
    assert refusal.value.code == code and str(refusal.value).startswith(code + ": ")


def test_a_target_far_from_the_constant_offset_target_or_a_foreign_scene_is_refused(geometry, policy):
    with pytest.raises(ph.PlaceHeightRefused) as far:
        ph.plan_place_height(THETA, policy.grasp_offset_m, OLD_TARGET_Z - 0.01, geometry, policy)
    assert far.value.code == ph.HEIGHT_OUT_OF_BOUNDS
    foreign = ph.CupGeometry(**{**{f: getattr(geometry, f) for f in geometry.__slots__}, "scene_sha256": "0" * 64})
    with pytest.raises(ph.PlaceHeightRefused) as scene:
        ph.plan_place_height(THETA, policy.grasp_offset_m, OLD_TARGET_Z, foreign, policy)
    assert scene.value.code == ph.HEIGHT_OUT_OF_BOUNDS


def test_a_refusal_document_is_valid_only_with_one_of_the_three_codes():
    for code in ph.REFUSAL_CODES:
        ph.validate_document({"mode": "tilt_compensated", "refused": code})
    with pytest.raises(ValueError, match="PLACE_HEIGHT"):
        ph.validate_document({"mode": "tilt_compensated", "refused": "SOMETHING_ELSE"})
