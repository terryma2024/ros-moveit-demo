"""The 17 measured head-search calibration values, their hard bounds and their refusals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_calibration import (
    HeadSearchCalibrationError,
    calibrate_head_search,
    load_scenario_partitions,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

PACKAGE = Path(__file__).parents[1]
CONTRACT = PACKAGE / "config/act/head-search-calibration-contract-v1.json"
PARTITIONS = PACKAGE / "config/act/head-search-scenario-partitions-v1.json"

EXPECTED = {
    "horizontal_fov_rad",
    "lock_valid_neck_rad",
    "coarse_step_rad",
    "search_timeout_s",
    "min_confidence",
    "tracking_iou",
    "min_bbox_aspect",
    "min_area_px2",
    "center_deadband_px",
    "vertical_bounds_px",
    "max_fine_corrections",
    "max_fine_total_rad",
    "max_age_s",
    "max_skew_s",
    "submit_lead_s",
    "stop_velocity_rad_s",
    "stop_latency_s",
}


def _fixture() -> dict:
    """The smallest set of calibrated inputs that can produce all seventeen values."""

    return {
        "geometry": {
            "horizontal_fov_rad": 1.3121067481206794,
            "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
            "required_search_domain_rad": [-0.29145679447786704, 0.540419500270584],
            "coarse_step_rad": 0.3,
            "camera_digest": "a" * 64,
        },
        "candidate": {
            "min_confidence": 0.4,
            "tracking_iou": 0.3,
            "min_bbox_aspect": 0.5,
            "min_area_px2": 64.0,
        },
        "timing": {
            "frame_age_s": [0.04, 0.05, 0.06, 0.05],
            "skew_s": [0.01, 0.02, 0.015, 0.02],
            "search_timeout_s": 12.0,
            "submit_lead_s": 0.02,
            "stop_velocity_rad_s": 0.05,
            "stop_latency_s": [0.05, 0.06, 0.04],
        },
        "episodes": {
            "val_false_candidates": 0,
            "two_cup_detections": 40,
            "tracker_identity_switches": 0,
            "max_fine_corrections": 4,
            "max_fine_total_rad": 0.4,
            "center_deadband_px": 18.0,
            "vertical_bounds_px": [110.0, 370.0],
        },
        "identities": {
            "geometry_source_sha256": "b" * 64,
            "candidate_identity_sha256": canonical_sha256(
                {
                    "min_confidence": 0.4,
                    "tracking_iou": 0.3,
                    "min_bbox_aspect": 0.5,
                    "min_area_px2": 64.0,
                }
            ),
            "contract_sha256": "d" * 64,
            "runtime_sha256": "e" * 64,
        },
    }


def test_bundle_has_exactly_seventeen_measured_values() -> None:
    bundle = calibrate_head_search(_fixture())

    assert set(bundle.measurements) == EXPECTED
    assert bundle.measurements["max_age_s"].value <= 0.15
    assert bundle.measurements["max_skew_s"].value <= 0.05


def test_every_measurement_carries_its_provenance() -> None:
    bundle = calibrate_head_search(_fixture())

    for name, measurement in bundle.measurements.items():
        assert measurement.unit and measurement.formula_id, name
        assert measurement.inputs_sha256, name
        assert all(len(value) == 64 for value in measurement.inputs_sha256), name
        assert measurement.distribution, name
        assert measurement.margin >= 0.0, name
        assert measurement.production_owner and measurement.consumer_field, name
    assert bundle.sha256 and len(bundle.sha256) == 64


def test_the_four_perception_values_equal_the_frozen_candidate_identity() -> None:
    fixture = _fixture()
    bundle = calibrate_head_search(fixture)

    for name in ("min_confidence", "tracking_iou", "min_bbox_aspect", "min_area_px2"):
        assert bundle.measurements[name].value == pytest.approx(fixture["candidate"][name])


def test_a_hard_bound_violation_is_refused() -> None:
    fixture = _fixture()
    fixture["timing"]["frame_age_s"] = [0.2, 0.2, 0.2]
    with pytest.raises(HeadSearchCalibrationError, match="HEAD_SEARCH_CALIBRATION_BOUND"):
        calibrate_head_search(fixture)


def test_the_listed_rejections_are_refused() -> None:
    cases = [
        (
            "HEAD_SEARCH_CALIBRATION_INVALID",
            lambda f: f["geometry"].update(horizontal_fov_rad=float("nan")),
        ),
        ("HEAD_SEARCH_CALIBRATION_INVALID", lambda f: f["timing"].update(search_timeout_s=-1.0)),
        (
            "HEAD_SEARCH_CALIBRATION_UNSAFE_MOTION",
            lambda f: f["episodes"].update(max_fine_total_rad=1e12),
        ),
        (
            "HEAD_SEARCH_CALIBRATION_INVALID",
            lambda f: f["episodes"].update(val_false_candidates=1.5),
        ),
    ]
    for code, mutate in cases:
        fixture = _fixture()
        mutate(fixture)
        with pytest.raises(HeadSearchCalibrationError, match=code):
            calibrate_head_search(fixture)


def test_the_tracked_partitions_are_disjoint_and_complete() -> None:
    document = json.loads(PARTITIONS.read_text(encoding="utf-8"))
    partitions = load_scenario_partitions(document)

    calibration = set(partitions.calibration)
    held_out = set(partitions.held_out_evaluation)
    qualification = {item.seed for item in partitions.qualification}
    assert len(qualification) == 40
    assert (
        not (calibration & held_out)
        and not (calibration & qualification)
        and not (held_out & qualification)
    )
    assert {item.anchor for item in partitions.qualification} <= {"default", "left", "forward"}
    assert len({item.condition_class for item in partitions.qualification}) >= 2
    scenes = [item.scene_group_id for item in partitions.qualification]
    assert len(set(scenes)) == len(scenes), "a scene must not repeat inside a partition"


def test_the_partition_schema_and_contract_are_tracked() -> None:
    schema = json.loads(
        (PACKAGE / "config/act/head-search-calibration-contract-schema.json").read_text(
            encoding="utf-8"
        )
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert schema and contract
    assert set(contract["parameters"]) == EXPECTED


def test_the_reviewer_s_probes_are_refused() -> None:
    """The exact inputs the Task 6 review found were accepted."""

    def nan_fov(fixture: dict) -> None:
        fixture["geometry"]["horizontal_fov_rad"] = float("nan")

    def negative_timeout(fixture: dict) -> None:
        fixture["timing"]["search_timeout_s"] = -1.0

    def absurd_allowance(fixture: dict) -> None:
        fixture["episodes"]["max_fine_total_rad"] = 1e12

    def fractional_count(fixture: dict) -> None:
        fixture["episodes"]["val_false_candidates"] = 1.5

    cases = [
        ("HEAD_SEARCH_CALIBRATION_INVALID", nan_fov),
        ("HEAD_SEARCH_CALIBRATION_INVALID", negative_timeout),
        ("HEAD_SEARCH_CALIBRATION_UNSAFE_MOTION", absurd_allowance),
        ("HEAD_SEARCH_CALIBRATION_INVALID", fractional_count),
    ]
    for code, mutate in cases:
        fixture = _fixture()
        mutate(fixture)
        with pytest.raises(HeadSearchCalibrationError, match=code):
            calibrate_head_search(fixture)


def test_a_retuned_perception_value_breaks_the_frozen_identity() -> None:
    fixture = _fixture()
    fixture["candidate"]["min_confidence"] = 0.9
    with pytest.raises(HeadSearchCalibrationError, match="HEAD_SEARCH_CALIBRATION_IDENTITY_DRIFT"):
        calibrate_head_search(fixture)


def test_the_partition_loader_refuses_a_wrong_shape() -> None:
    document = json.loads(PARTITIONS.read_text(encoding="utf-8"))

    short = json.loads(json.dumps(document))
    short["qualification"] = short["qualification"][:39]
    with pytest.raises(HeadSearchCalibrationError, match="HEAD_SEARCH_CALIBRATION_INVALID"):
        load_scenario_partitions(short)

    repeated_seed = json.loads(json.dumps(document))
    repeated_seed["qualification"][1]["seed"] = repeated_seed["qualification"][0]["seed"]
    with pytest.raises(HeadSearchCalibrationError, match="HEAD_SEARCH_CALIBRATION_INVALID"):
        load_scenario_partitions(repeated_seed)

    repeated_scene = json.loads(json.dumps(document))
    repeated_scene["qualification"][1]["scene_group_id"] = repeated_scene["qualification"][0][
        "scene_group_id"
    ]
    with pytest.raises(HeadSearchCalibrationError, match="HEAD_SEARCH_CALIBRATION_INVALID"):
        load_scenario_partitions(repeated_scene)


def test_the_schema_requires_every_parameter_and_its_provenance() -> None:
    schema = json.loads(
        (PACKAGE / "config/act/head-search-calibration-contract-schema.json").read_text(
            encoding="utf-8"
        )
    )
    parameters = schema["properties"]["parameters"]
    assert set(parameters["required"]) == EXPECTED
    assert parameters["additionalProperties"] is False
    for rule in parameters["patternProperties"].values():
        assert set(rule["required"]) == {
            "unit",
            "formula_id",
            "margin",
            "production_owner",
            "consumer_field",
        }
        assert rule["additionalProperties"] is False


def test_more_nan_and_negative_probes_are_refused() -> None:
    def nan_interval(fixture: dict) -> None:
        fixture["geometry"]["lock_valid_neck_rad"] = [float("nan"), float("nan")]

    def uncovered_by_nan(fixture: dict) -> None:
        fixture["geometry"]["lock_valid_neck_rad"] = [float("nan"), 100.0]
        fixture["geometry"]["required_search_domain_rad"] = [-100.0, 100.0]

    def negative_lead(fixture: dict) -> None:
        fixture["timing"]["submit_lead_s"] = -0.5

    def nan_deadband(fixture: dict) -> None:
        fixture["episodes"]["center_deadband_px"] = float("nan")

    def repeated_calibration_seed(fixture: dict) -> None:
        fixture["geometry"]["required_search_domain_rad"] = [-0.2, 0.5]

    cases = [nan_interval, uncovered_by_nan, negative_lead, nan_deadband]
    for mutate in cases:
        fixture = _fixture()
        mutate(fixture)
        with pytest.raises(HeadSearchCalibrationError, match="HEAD_SEARCH_CALIBRATION_INVALID"):
            calibrate_head_search(fixture)

    document = json.loads(PARTITIONS.read_text(encoding="utf-8"))
    document["calibration"][1] = document["calibration"][0]
    with pytest.raises(HeadSearchCalibrationError, match="HEAD_SEARCH_CALIBRATION_INVALID"):
        load_scenario_partitions(document)


def test_the_contract_names_the_formulas_the_library_emits() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    bundle = calibrate_head_search(_fixture())

    for name, measurement in bundle.measurements.items():
        assert contract["parameters"][name]["formula_id"] == measurement.formula_id, name
        assert contract["parameters"][name]["production_owner"] == measurement.production_owner, (
            name
        )
        assert contract["parameters"][name]["consumer_field"] == measurement.consumer_field, name
