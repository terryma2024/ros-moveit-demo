"""Task 2 (approved measurement protocol v2): pure formulas for the 21 + 7 fields.

Formulas consume only already validated indexed records - no filesystem guessing and no runtime imports - and
return, per field, the configured limit, the observed summary, the reported value and the raw references the
aggregation receipt cites. Nothing here may trust a boolean label such as `qualified`, `target_in_view`,
`contact_ok` or any `*_ok` flag: the design requires every field to be recomputed from raw evidence.
"""

import json
import math
from pathlib import Path

import pytest

from so101_demo.act.task8_measurement_schema import load_contract_v2

CONTRACT = load_contract_v2()
HEAD_FIELDS = sorted(CONTRACT["measurements"])
SUPPORT_FIELDS = sorted(CONTRACT["support"])
HEAD_SAMPLE_KEYS = {
    "schema_version", "kind", "status", "head_search", "observed_lock_frames", "measurements",
    "camera_measurements", "source_commit", "config_sha256", "source_provenance_sha256",
}
REPORT_ENTRY_KEYS = {"value", "unit", "sample_path", "sample_sha256"}
FORBIDDEN_LABELS = ("qualified", "target_in_view", "contact_ok", "stop_confirmed")


def _formulas():
    from so101_demo.act import task8_measurement_formulas as formulas

    return formulas


def test_formula_module_exposes_the_documented_interfaces():
    formulas = _formulas()
    for name in ("compute_head_search_fields", "compute_support_fields",
                 "build_head_closed_sample", "build_support_closed_sample", "FORMULA_IDS"):
        assert hasattr(formulas, name), name


@pytest.mark.parametrize("field", HEAD_FIELDS + SUPPORT_FIELDS)
def test_every_contract_field_has_a_formula_id_matching_the_contract(field):
    formulas = _formulas()
    entry = CONTRACT["measurements"].get(field) or CONTRACT["support"][field]
    assert formulas.FORMULA_IDS[field] == entry["formula_id"], field


def test_head_closed_sample_carries_exactly_the_approved_key_set():
    formulas = _formulas()
    sample = formulas.build_head_closed_sample(head_search={}, observed_lock_frames=[], measurements={},
                                               camera_measurements={}, source_commit="a" * 40,
                                               config_sha256="b" * 64, source_provenance_sha256="c" * 64)
    assert set(sample) == HEAD_SAMPLE_KEYS


def test_measurement_maps_are_bare_values_while_report_entries_carry_four_keys(tmp_path):
    formulas = _formulas()
    sample = formulas.build_support_closed_sample(support={}, source_commit="a" * 40,
                                                  config_sha256="b" * 64,
                                                  source_provenance_sha256="c" * 64)
    for name, value in sample["support"].items():
        assert not isinstance(value, dict), f"{name} must be a bare value in the sample"
    report = formulas.build_field_report(sample, tmp_path)
    for name, entry in report.items():
        assert set(entry) == REPORT_ENTRY_KEYS, name
        assert entry["sample_sha256"] and Path(entry["sample_path"]).is_file()


@pytest.mark.parametrize("label", FORBIDDEN_LABELS)
def test_boolean_labels_are_rejected_as_formula_inputs(label):
    formulas = _formulas()
    with pytest.raises(ValueError, match="RAW_EVIDENCE_REQUIRED"):
        formulas.require_raw_inputs({"measurements": {label: True}})


def test_a_missing_raw_reference_is_refused_rather_than_defaulted():
    formulas = _formulas()
    with pytest.raises(ValueError, match="RAW_EVIDENCE_REQUIRED"):
        formulas.compute_head_search_fields({}, CONTRACT)


# --- per-field boundary-pass and single-point-violation cases (plan Task 2 Step 1) --------------------------

BOX = {"x1": 100.0, "y1": 100.0, "x2": 200.0, "y2": 150.0}


def _raw(field, evidence, configured):
    return {"measurements": {field: evidence}, "configured": {field: configured}}


FIELD_CASES = {
    "min_bbox_aspect": (_raw("min_bbox_aspect", [BOX], 0.5), "PASS",
                        _raw("min_bbox_aspect", [BOX], 0.6), "FAIL"),
    "min_area_px2": (_raw("min_area_px2", [BOX], 5000.0), "PASS",
                     _raw("min_area_px2", [BOX], 5001.0), "FAIL"),
    "center_deadband_px": (_raw("center_deadband_px", {"bboxes": [BOX], "K02": 150.0}, 0.0), "PASS",
                           _raw("center_deadband_px", {"bboxes": [BOX], "K02": 152.0}, 1.0), "FAIL"),
    "vertical_bounds_px": (_raw("vertical_bounds_px", [BOX], [125.0, 125.0]), "PASS",
                           _raw("vertical_bounds_px", [BOX], [126.0, 130.0]), "FAIL"),
    "tracking_iou": (_raw("tracking_iou", [{"previous": BOX, "current": BOX, "inherited": True}], 1.0), "PASS",
                     _raw("tracking_iou", [{"previous": BOX, "current": {"x1": 300.0, "y1": 100.0, "x2": 400.0,
                                                                        "y2": 150.0}, "inherited": True}], 0.1),
                     "FAIL"),
    "max_age_s": (_raw("max_age_s", [{"received_monotonic_s": 0.0, "decision_monotonic_s": 0.5}], 0.5), "PASS",
                  _raw("max_age_s", [{"received_monotonic_s": 0.0, "decision_monotonic_s": 0.51}], 0.5), "FAIL"),
    # exact binary values: 2.0 - 1.0 is exactly 1.0, while 2.5 - 1.0 is unambiguously above the limit
    "max_skew_s": (_raw("max_skew_s", [{"stamps": [1.0, 2.0]}], 1.0), "PASS",
                   _raw("max_skew_s", [{"stamps": [1.0, 2.5]}], 1.0), "FAIL"),
    "submit_lead_s": (_raw("submit_lead_s", [{"first_target_sim_s": 10.05, "submit_snapshot_sim_s": 10.0}], 0.05),
                      "PASS",
                      _raw("submit_lead_s", [{"first_target_sim_s": 10.04, "submit_snapshot_sim_s": 10.0}], 0.05),
                      "FAIL"),
    "stop_latency_s": (_raw("stop_latency_s", [{"stop_request_monotonic_s": 0.0,
                                                "third_confirming_receive_monotonic_s": 0.5}], 0.5), "PASS",
                       _raw("stop_latency_s", [{"stop_request_monotonic_s": 0.0,
                                                "third_confirming_receive_monotonic_s": 0.51}], 0.5), "FAIL"),
    "stop_velocity_rad_s": (_raw("stop_velocity_rad_s", [
        {"receive_monotonic_s": 0.0, "velocity_rad_s": [0.001] * 7},
        {"receive_monotonic_s": 0.1, "velocity_rad_s": [0.002] * 7},
        {"receive_monotonic_s": 0.2, "velocity_rad_s": [0.01] * 7}], 0.01), "PASS",
        _raw("stop_velocity_rad_s", [
            {"receive_monotonic_s": 0.0, "velocity_rad_s": [0.001] * 7},
            {"receive_monotonic_s": 0.1, "velocity_rad_s": [0.002] * 7},
            {"receive_monotonic_s": 0.2, "velocity_rad_s": [0.011] * 7}], 0.01), "FAIL"),
    "path_step_s": (_raw("path_step_s", [0.0, 0.1, 0.2], 0.1), "PASS",
                    _raw("path_step_s", [0.0, 0.1, 0.21], 0.1), "FAIL"),
    "min_confidence": (_raw("min_confidence", [0.5, 0.6], 0.5), "PASS",
                       _raw("min_confidence", [0.49, 0.6], 0.5), "FAIL"),
    "max_fine_corrections": (_raw("max_fine_corrections", [0.1, 0.1, 0.1], 3), "PASS",
                             _raw("max_fine_corrections", [0.1, 0.1, 0.1, 0.1], 3), "FAIL"),
    "max_fine_total_rad": (_raw("max_fine_total_rad", [0.25, 0.25], 0.5), "PASS",
                           _raw("max_fine_total_rad", [0.25, 0.26], 0.5), "FAIL"),
}


@pytest.mark.parametrize("field", sorted(FIELD_CASES))
def test_boundary_pass_and_single_point_violation(field):
    formulas = _formulas()
    passing, expected_pass, violating, expected_fail = FIELD_CASES[field]
    assert formulas.compute_field(field, passing, CONTRACT)["verdict"] == expected_pass, field
    assert formulas.compute_field(field, violating, CONTRACT)["verdict"] == expected_fail, field


def test_a_field_without_a_configured_limit_is_refused_rather_than_defaulted():
    formulas = _formulas()
    raw = {"measurements": {"min_confidence": [0.5, 0.6]}, "configured": {}}
    with pytest.raises(ValueError, match="CONFIGURED_LIMIT_REQUIRED: min_confidence"):
        formulas.compute_field("min_confidence", raw, CONTRACT)


EXTRA_CASES = {
    "horizontal_fov_rad": (
        _raw("horizontal_fov_rad", {"frames": [{"fx": 400.0, "cx": 320.0, "width": 640.0}],
                                    "model_fov_rad": 1.3494818844471055, "tolerance_rad": 1e-3}, 1.3494818844471055),
        "PASS",
        _raw("horizontal_fov_rad", {"frames": [{"fx": 400.0, "cx": 320.0, "width": 640.0}],
                                    "model_fov_rad": 1.5, "tolerance_rad": 1e-3}, 1.3494818844471055),
        "FAIL"),
    "search_timeout_s": (
        _raw("search_timeout_s", [{"anchor": "default", "started_monotonic_s": 0.0,
                                   "terminal_monotonic_s": 15.0}], 15.0), "PASS",
        _raw("search_timeout_s", [{"anchor": "default", "started_monotonic_s": 0.0,
                                   "terminal_monotonic_s": 15.1}], 15.0), "FAIL"),
    "coarse_step_rad": (
        _raw("coarse_step_rad", [{"coarse_accumulator_before": 0.0, "coarse_accumulator_after": 0.2},
                                 {"coarse_accumulator_before": 0.2, "coarse_accumulator_after": 0.35}], 0.2), "PASS",
        _raw("coarse_step_rad", [{"coarse_accumulator_before": 0.0, "coarse_accumulator_after": 0.3}], 0.2), "FAIL"),
}


@pytest.mark.parametrize("field", sorted(EXTRA_CASES))
def test_boundary_pass_and_violation_for_the_second_batch(field):
    formulas = _formulas()
    passing, expected_pass, violating, expected_fail = EXTRA_CASES[field]
    assert formulas.compute_field(field, passing, CONTRACT)["verdict"] == expected_pass, field
    assert formulas.compute_field(field, violating, CONTRACT)["verdict"] == expected_fail, field


def test_a_missing_terminal_event_is_invalid_rather_than_failed():
    formulas = _formulas()
    raw = _raw("search_timeout_s", [{"anchor": "default", "started_monotonic_s": 0.0,
                                     "terminal_monotonic_s": None}], 15.0)
    assert formulas.compute_field("search_timeout_s", raw, CONTRACT)["verdict"] == "INVALID"


# --- camera and TF group ----------------------------------------------------------------------------------

FOVY_480 = 2 * math.atan(240 / 400)          # intrinsics whose modelled fx equals 400 px
TILTED = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -1.0, 0.0]     # R * [0,0,1] = (0,1,0) -> bearing pi/2


def test_head_intrinsics_matches_its_own_model_formula():
    formulas = _formulas()
    raw = _raw("head_intrinsics_px", {"frames": [{"width": 640, "height": 480, "K": [400.0, 400.0, 320.0, 240.0],
                                                  "fovy_rad": FOVY_480}], "tolerance_px": 1e-6}, 1e-6)
    assert formulas.compute_field("head_intrinsics_px", raw, CONTRACT)["verdict"] == "PASS"


def test_head_intrinsics_fails_when_k_varies_beyond_tolerance():
    formulas = _formulas()
    raw = _raw("head_intrinsics_px", {"frames": [{"width": 640, "height": 480, "K": [400.0, 400.0, 320.0, 240.0],
                                                  "fovy_rad": FOVY_480},
                                                 {"width": 640, "height": 480, "K": [401.0, 400.0, 320.0, 240.0],
                                                  "fovy_rad": FOVY_480}], "tolerance_px": 0.5}, 0.5)
    assert formulas.compute_field("head_intrinsics_px", raw, CONTRACT)["verdict"] == "FAIL"


def test_translation_median_passes_and_a_shifted_expected_fails():
    formulas = _formulas()
    passing = _raw("head_translation_m", {"samples": [[0.0, 0.0, 0.1], [0.0, 0.0, 0.1]],
                                          "expected": [0.0, 0.0, 0.1], "tolerance_m": 1e-9}, 0.0)
    violating = _raw("head_translation_m", {"samples": [[0.0, 0.0, 0.1]],
                                            "expected": [0.0, 0.0, 0.11], "tolerance_m": 1e-3}, 0.0)
    assert formulas.compute_field("head_translation_m", passing, CONTRACT)["verdict"] == "PASS"
    assert formulas.compute_field("head_translation_m", violating, CONTRACT)["verdict"] == "FAIL"


def test_rpy_zyx_unwrap_passes_for_a_known_rotation_and_fails_on_mismatch():
    formulas = _formulas()
    yaw_90 = [0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4)]
    passing = _raw("head_rpy_rad", {"quaternions": [yaw_90], "expected": [0.0, 0.0, math.pi / 2],
                                    "tolerance_rad": 1e-9}, 0.0)
    violating = _raw("head_rpy_rad", {"quaternions": [yaw_90], "expected": [0.0, 0.0, 0.0],
                                      "tolerance_rad": 1e-3}, 0.0)
    assert formulas.compute_field("head_rpy_rad", passing, CONTRACT)["verdict"] == "PASS"
    assert formulas.compute_field("head_rpy_rad", violating, CONTRACT)["verdict"] == "FAIL"


def test_a_non_unit_quaternion_is_refused_rather_than_normalised():
    formulas = _formulas()
    raw = _raw("head_rpy_rad", {"quaternions": [[1.0, 0.0, 0.0, 1.0]], "tolerance_rad": 1e-3}, 0.0)
    with pytest.raises(ValueError, match="RAW_EVIDENCE_REQUIRED: quaternion is not unit length"):
        formulas.compute_field("head_rpy_rad", raw, CONTRACT)


def test_yaw_bearing_uses_the_optical_forward_axis_circular_median():
    formulas = _formulas()
    passing = _raw("yaw_zero_bearing_rad", {"rotations": [TILTED], "expected": math.pi / 2,
                                            "tolerance_rad": 1e-9}, 0.0)
    violating = _raw("yaw_zero_bearing_rad", {"rotations": [TILTED], "expected": 0.0,
                                              "tolerance_rad": 1e-3}, 0.0)
    assert formulas.compute_field("yaw_zero_bearing_rad", passing, CONTRACT)["verdict"] == "PASS"
    assert formulas.compute_field("yaw_zero_bearing_rad", violating, CONTRACT)["verdict"] == "FAIL"


def test_a_degenerate_forward_axis_is_refused():
    formulas = _formulas()
    identity = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    raw = _raw("yaw_zero_bearing_rad", {"rotations": [identity], "tolerance_rad": 1e-3}, 0.0)
    with pytest.raises(ValueError, match="RAW_EVIDENCE_REQUIRED: degenerate forward axis"):
        formulas.compute_field("yaw_zero_bearing_rad", raw, CONTRACT)


# --- the remaining four fields ----------------------------------------------------------------------------

def test_lock_valid_neck_selects_the_unique_safe_component_and_shrinks_it():
    formulas = _formulas()
    raw = _raw("lock_valid_neck_rad", {"bounds_rad": [-6.283185307179586, 6.283185307179586],
                                       "anchor_starts_rad": [0.1, -0.2, 0.3],
                                       "unsafe_intervals_rad": [[1.0, 2.0]], "shrink_rad": 1e-5}, [0, 0])
    result = formulas.compute_field("lock_valid_neck_rad", raw, CONTRACT)
    assert result["verdict"] == "PASS"
    assert result["reported_value"][0] == pytest.approx(-6.283185307179586 + 1e-5)
    assert result["reported_value"][1] == pytest.approx(1.0 - 1e-5)


def test_lock_valid_neck_fails_when_no_single_component_holds_zero_and_every_start():
    formulas = _formulas()
    # safe components are [-1, 1] and [1.5, 3]: zero and 0.5 sit in the first, the 2.0 start in the second,
    # so the containing rule cannot select one component and the field must fail rather than pick a side
    raw = _raw("lock_valid_neck_rad", {"bounds_rad": [-3.0, 3.0], "anchor_starts_rad": [0.5, 2.0],
                                       "unsafe_intervals_rad": [[1.0, 1.5], [-3.0, -1.0]], "shrink_rad": 1e-5},
               [0, 0])
    assert formulas.compute_field("lock_valid_neck_rad", raw, CONTRACT)["verdict"] == "FAIL"


def test_velocity_limit_uses_max_rate_and_flags_a_non_positive_interval():
    formulas = _formulas()
    limit = [0.5] * 6
    passing = _raw("velocity_limit_rad_s", {"samples": [{"dt_s": 0.1, "dq_rad": [0.01] * 6},
                                                        {"dt_s": 0.2, "dq_rad": [0.08] * 6}]}, limit)
    violating = _raw("velocity_limit_rad_s", {"samples": [{"dt_s": 0.1, "dq_rad": [0.2] * 6}]}, limit)
    invalid = _raw("velocity_limit_rad_s", {"samples": [{"dt_s": 0.0, "dq_rad": [0.01] * 6}]}, limit)
    assert formulas.compute_field("velocity_limit_rad_s", passing, CONTRACT)["verdict"] == "PASS"
    assert formulas.compute_field("velocity_limit_rad_s", violating, CONTRACT)["verdict"] == "FAIL"
    assert formulas.compute_field("velocity_limit_rad_s", invalid, CONTRACT)["verdict"] == "INVALID"


def test_acceleration_limit_flags_a_non_positive_interval():
    formulas = _formulas()
    limit = [1.0] * 6
    samples = [{"time_s": 0.0, "position_rad": [0.0] * 6},
               {"time_s": 0.1, "position_rad": [0.01] * 6},
               {"time_s": 0.2, "position_rad": [0.03] * 6}]
    assert formulas.compute_field("acceleration_limit_rad_s2",
                                  _raw("acceleration_limit_rad_s2", {"samples": samples}, limit),
                                  CONTRACT)["verdict"] == "PASS"
    broken = [samples[0], samples[1], {"time_s": 0.1, "position_rad": [0.03] * 6}]
    assert formulas.compute_field("acceleration_limit_rad_s2",
                                  _raw("acceleration_limit_rad_s2", {"samples": broken}, limit),
                                  CONTRACT)["verdict"] == "INVALID"


def test_path_clearance_uses_the_minimum_and_refuses_a_non_allowlisted_contact():
    formulas = _formulas()
    passing = _raw("path_clearance_m", {"rows": [{"signed_distance_m": 0.02, "contact_pair": None},
                                                 {"signed_distance_m": 0.011, "contact_pair": None}]}, 0.01)
    violating = _raw("path_clearance_m", {"rows": [{"signed_distance_m": 0.005, "contact_pair": None}]}, 0.01)
    contact = _raw("path_clearance_m", {"rows": [{"signed_distance_m": 0.0, "contact_pair": ["cup", "table"]}],
                                        "allowlisted_contacts": []}, 0.01)
    allowlisted = _raw("path_clearance_m", {"rows": [{"signed_distance_m": 0.0,
                                                      "contact_pair": ["cup", "table"]},
                                                     {"signed_distance_m": 0.05, "contact_pair": None}],
                                            "allowlisted_contacts": [["cup", "table"]]}, 0.01)
    assert formulas.compute_field("path_clearance_m", passing, CONTRACT)["verdict"] == "PASS"
    assert formulas.compute_field("path_clearance_m", violating, CONTRACT)["verdict"] == "FAIL"
    assert formulas.compute_field("path_clearance_m", contact, CONTRACT)["verdict"] == "FAIL"
    assert formulas.compute_field("path_clearance_m", allowlisted, CONTRACT)["verdict"] == "PASS"


def test_every_registered_formula_is_covered_and_missing_evidence_names_its_field():
    """Full 28-field evidence fixtures arrive with the Task 5 driver; here we prove the registry is complete and
    that a partial payload is refused with the missing field named rather than silently defaulted."""

    formulas = _formulas()
    assert set(formulas._FORMULAS) == set(formulas.FORMULA_IDS)
    raw = {"measurements": {"min_confidence": [0.6]}, "configured": {"min_confidence": 0.5}}
    with pytest.raises(ValueError) as error:
        formulas.compute_head_search_fields(raw, CONTRACT)
    assert "RAW_EVIDENCE_REQUIRED" in str(error.value)
    assert formulas.compute_field("min_confidence", raw, CONTRACT)["verdict"] == "PASS"
