"""The installed producer of the run's `--admission`: one generation, one plan, one binding.

The run takes a single `role=calibration` measurement flight through the repository's own
`CalibrationMeasurementAdmission`, and the document that carries it is exactly the six fields the run's
entry reads. Every test here is detector-free, ROS-free and MuJoCo-free: the producer reads declared
documents, derives the measurement plan, and lets the *installed* phase 1 and the installed trajectory
precondition decide - no token is invented and nothing is measured.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from so101_demo.act.head_search.calibration_admission_document import (
    ADMISSION_FIELDS,
    ADMISSION_NAME,
    CAL_ADMISSION_INCOMPLETE,
    CAL_TRAJECTORY_CONTRACT_UNSATISFIED,
    PLAN_NAME,
    RECEIPT_NAME,
    CalibrationAdmissionDocumentRefused,
    derive_measurement_plan,
    record_admission_document,
)
from so101_demo.act.head_search.calibration_geometry import (
    GEOMETRY_INPUT_NAME,
    load_sealed_geometry,
)
from so101_demo.act.head_search.calibration_inputs import (
    CAL_ADMISSION_REFUSED,
    CAL_BINDING_REBOUND,
    CAL_INPUT_UNSEALED,
    SEALED_INPUT_NAMES,
    CalibrationInputsRefused,
)
from so101_demo.act.search import HeadSearchController
from so101_demo.act.pick_place_calibration_admission import CalibrationMeasurementAdmission
from so101_demo.perception_benchmark.contracts import canonical_sha256

FOVY_RAD = 1.0471975511965976
WIDTH_PX = 640
HEIGHT_PX = 480
HORIZONTAL_FOV_RAD = 1.3121067481206794
LOCK_INTERVAL = [-6.283175307179587, 6.283175307179587]
REQUIRED_DOMAIN = [-0.17559216195018026, 0.08047101126546086]


def _geometry(*, horizontal_fov_rad: float = HORIZONTAL_FOV_RAD) -> dict:
    """The sealed head camera geometry, with the fields the plan and the evidence are read from.

    It is a real seal: `seal_sha256` is the canonical digest of its own body, which is what the installed
    phase-2 loader requires, and every anchor it declares carries its start angle in `in_frame_matrix`.
    """

    body = {
        "schema_version": 1,
        "camera_name": "head_camera",
        "image_width": WIDTH_PX,
        "image_height": HEIGHT_PX,
        "horizontal_fov_rad": horizontal_fov_rad,
        "lock_valid_neck_rad": list(LOCK_INTERVAL),
        "required_search_domain_rad": list(REQUIRED_DOMAIN),
        "coarse_step_candidate_rad": 0.4,
        "anchors": ["default", "left", "forward"],
        "in_frame_matrix": {
            "default": {
                "centre_angle_rad": 0.23109066719589708,
                "neck_start_rad": 0.1,
                "out_of_frame_rad": [],
                "samples": [
                    {"in_frame": True, "neck_rad": 0.1, "projected_points": 9,
                     "projected_points_in_frame": 9, "visible_pixels": 8243}
                ],
            },
            "left": {
                "centre_angle_rad": -0.0587558227157227,
                "neck_start_rad": 0.0,
                "out_of_frame_rad": [],
                "samples": [
                    {"in_frame": True, "neck_rad": 0.0, "projected_points": 9,
                     "projected_points_in_frame": 9, "visible_pixels": 8340}
                ],
            },
            "forward": {
                "centre_angle_rad": 0.18822150530477078,
                "neck_start_rad": 0.0,
                "out_of_frame_rad": [],
                "samples": [
                    {"in_frame": True, "neck_rad": 0.0, "projected_points": 9,
                     "projected_points_in_frame": 9, "visible_pixels": 6447}
                ],
            },
        },
        "in_frame_failures": [],
        "workspace_matrix": {"in_frame": 120, "key_samples": []},
        "camera": {
            "camera_name": "head_camera",
            "width": WIDTH_PX,
            "height": HEIGHT_PX,
            "fovy_rad": FOVY_RAD,
            "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
            "distortion_model": "plumb_bob",
            "local_position_m": [0.0, 0.0, 0.0],
            "local_xyaxes": [-1.0, 0.0, 0.0, 0.0, -0.6, 0.8],
            "parent_body": "head_mount",
        },
        "validation_arm_rad": [-0.25, 0.0, 0.6, 0.8, 0.0, 0.8],
        "support_height_m": 0.12,
        "camera_mount_origin_m": [-0.06, 0.06, 0.4299186],
        "camera_mount_xyaxes": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        "fov_union_covers_required_domain": True,
        "safe_interval_contains_required_domain": True,
        "source_digests": {"scene_sha256": "a" * 64},
    }
    return {**body, "seal_sha256": canonical_sha256(body)}


def _production_config(**overrides) -> dict:
    """The sealed production search configuration, in the shape the run declares it in."""

    values = {
        "horizontal_fov_rad": 0.9,
        "coarse_step_rad": 0.3,
        "search_timeout_s": 12.0,
        "max_age_s": 0.05,
        "max_skew_s": 0.02,
        "center_deadband_px": 18.0,
        "vertical_bounds_px": [110.0, 370.0],
        "min_area_px2": 64.0,
        "min_confidence": 0.4,
        "max_fine_corrections": 4,
        "max_fine_total_rad": 0.4,
    }
    values.update(overrides.pop("values", {}))
    return {
        "schema_version": 2,
        "runtime_id": "head-search-runtime",
        "values": values,
        "motion": {"goal_tolerance_rad": 0.05, "settle_velocity_rad_s": 0.05},
        "camera": {
            "frame_id": "head_camera_frame",
            "ray_origin_frame_id": "head_camera_frame",
            "name": "head_camera",
            "width": WIDTH_PX,
            "height": HEIGHT_PX,
        },
        **overrides,
    }


def _write_json(path: Path, document) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _sealed_inputs(tmp_path: Path, *, geometry_document=None) -> dict:
    """The six controlled dependencies of plan section 2b, declared exactly as the run declares them."""

    geometry = _geometry() if geometry_document is None else geometry_document
    contents = {
        "dataset_manifest": {"kind": "dataset"},
        "model_manifest": {"kind": "model"},
        "geometry_seal": geometry,
        "scenario_partitions": {"kind": "partitions"},
        "production_config": _production_config(),
        "camera_config": {"camera_name": "head_camera"},
    }
    sealed = {}
    for name in SEALED_INPUT_NAMES:
        path = _write_json(tmp_path / "sealed" / f"{name}.json", contents[name])
        sealed[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return sealed


def _record(tmp_path: Path, *, sealed_inputs=None, **overrides) -> dict:
    """Record one admission. An explicitly declared seal is never rebuilt, so its digests stay true."""

    arguments = {
        "sealed_inputs": _sealed_inputs(tmp_path) if sealed_inputs is None else sealed_inputs,
        "run_root": tmp_path / "runs" / "head-search-calibration-20261002T000000Z",
        "output_dir": tmp_path / "admission",
        "cpu_cores": 8,
        "gpu_device": 0,
        "command": "ros2 run so101_demo_py so101_head_search_calibration measure-admission",
    }
    arguments.update(overrides)
    return record_admission_document(**arguments)


def _read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_the_admission_document_carries_exactly_the_six_fields_the_run_reads(tmp_path: Path) -> None:
    result = _record(tmp_path)
    document = _read(result["admission_path"])
    assert set(document) == set(ADMISSION_FIELDS)
    assert document["status"] == "CALIBRATION_REQUIRED"
    assert document["generation"] == "head-search-calibration-20261002T000000Z"
    assert len(document["measurement_plan_sha256"]) == 64
    assert document["safe_interval_rad"] == list(LOCK_INTERVAL)
    # the run's own entry constructs the class from exactly these six fields and admits the flight
    admission = CalibrationMeasurementAdmission(**document)
    decision = admission.admit(
        role="calibration", generation=document["generation"], operation="neck_target"
    )
    assert decision["admitted"] is True
    assert decision["measurement_plan_sha256"] == document["measurement_plan_sha256"]


def test_the_plan_is_the_flat_configuration_the_installed_controller_accepts(tmp_path: Path) -> None:
    result = _record(tmp_path)
    plan = _read(result["measurement_plan_path"])
    admission = _read(result["admission_path"])
    controller = HeadSearchController(plan)
    assert controller.plan is not None
    assert controller.plan.coverage_complete is True
    assert list(controller.plan.safe_interval_rad) == list(LOCK_INTERVAL)
    assert controller.plan.horizontal_fov_rad == HORIZONTAL_FOV_RAD
    assert list(controller.plan.required_domain_rad) == list(REQUIRED_DOMAIN)
    assert admission["measurement_plan_sha256"] == canonical_sha256(plan)
    # the plan is the controller's configuration and nothing else: no bundle value hides in it
    assert set(plan) == set(controller.config)


def test_the_plan_s_geometry_is_the_sealed_geometry_not_the_configured_copy(tmp_path: Path) -> None:
    """The plan's field of view and interval are the seal's, so a drifted config cannot vouch for them."""

    sealed = _sealed_inputs(tmp_path)
    config = _read(Path(sealed["production_config"]["path"]))
    config["values"]["horizontal_fov_rad"] = 0.9
    config["values"]["lock_valid_neck_rad"] = [-0.5, 0.5]
    _write_json(Path(sealed["production_config"]["path"]), config)
    sealed["production_config"]["sha256"] = hashlib.sha256(
        Path(sealed["production_config"]["path"]).read_bytes()
    ).hexdigest()
    result = _record(tmp_path, sealed_inputs=sealed)
    plan = _read(result["measurement_plan_path"])
    assert plan["horizontal_fov_rad"] == HORIZONTAL_FOV_RAD
    assert plan["lock_valid_neck_rad"] == list(LOCK_INTERVAL)


def test_the_receipt_records_the_refusals_and_the_single_use_of_the_flight(tmp_path: Path) -> None:
    result = _record(tmp_path)
    receipt = _read(result["receipt_path"])
    refusals = receipt["refusals"]
    assert refusals["release"]["code"] == CAL_ADMISSION_REFUSED
    assert refusals["recorder"]["code"] == CAL_ADMISSION_REFUSED
    assert refusals["foreign_role"]["role"] == "act"
    assert refusals["foreign_role"]["code"] == CAL_ADMISSION_REFUSED
    assert refusals["second_flight"]["code"] == CAL_ADMISSION_REFUSED
    assert refusals["second_flight"]["detail"].startswith("CAL_ADMISSION_REFUSED: ")
    assert "SECOND_FLIGHT_REFUSED" in refusals["second_flight"]["detail"]
    assert refusals["second_resource_binding"]["code"] == CAL_BINDING_REBOUND
    for name, refusal in refusals.items():
        if name != "foreign_role":
            assert refusal["refused"] is True
    # the installed phase 1 admitted the flight and bound the resources once, at the entry
    phase_one = receipt["phase_one"]
    assert phase_one["admission"]["admitted"] is True
    assert phase_one["admission"]["role"] == "calibration"
    assert phase_one["admission"]["operation"] == "neck_target"
    assert phase_one["resource_binding"]["bound_at_entry"] is True
    assert phase_one["resource_binding"]["cpu_cores"] == 8
    assert phase_one["resource_binding"]["generation"] == receipt["generation"]
    assert phase_one["manifest"]["manifest_sha256"]
    assert receipt["trajectory_contract"]["coverage_complete"] is True
    assert receipt["trajectory_contract"]["motion_commanded"] is False
    assert receipt["motion_commanded"] is False
    assert receipt["run_root_existed"] is False


def test_the_flight_declares_no_controller_incarnation_and_records_why(tmp_path: Path) -> None:
    """No phase of this run sends a neck target, so no controller or broker generation exists to cite."""

    receipt = _read(_record(tmp_path)["receipt_path"])
    document = receipt["admission"]
    assert document["controller_generation"] is None
    assert document["broker_generation"] is None
    absence = receipt["controller_incarnation"]
    assert absence["declared"] is False
    assert "sends a neck target" in absence["reason"]
    assert "no command broker session takes part" in absence["reason"]


def test_the_plan_and_the_admission_are_recorded_with_their_own_digests(tmp_path: Path) -> None:
    result = _record(tmp_path)
    receipt = _read(result["receipt_path"])
    for name, key in (("measurement_plan_path", "measurement_plan"), ("admission_path", "admission")):
        path = Path(result[name])
        assert path.is_file()
        assert receipt[key]["path"] == str(path)
        assert receipt[key]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["measurement_plan"]["canonical_sha256"] == canonical_sha256(
        _read(result["measurement_plan_path"])
    )
    assert receipt["admission"]["sha256"] == hashlib.sha256(
        Path(result["admission_path"]).read_bytes()
    ).hexdigest()
    assert receipt["provenance"]["command"].endswith("measure-admission")
    sealed = receipt["provenance"]["sealed_inputs"]
    assert set(sealed) == set(SEALED_INPUT_NAMES)
    assert sealed[GEOMETRY_INPUT_NAME]["sha256"] == receipt["provenance"]["geometry_seal_sha256"]


def test_the_producer_refuses_a_generation_whose_run_root_already_exists(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "generation"
    run_root.mkdir(parents=True)
    with pytest.raises(CalibrationAdmissionDocumentRefused) as refusal:
        _record(tmp_path, run_root=run_root)
    assert refusal.value.code == CAL_ADMISSION_INCOMPLETE
    assert "already exists" in refusal.value.detail
    assert "no reuse" in refusal.value.detail


def test_the_producer_writes_nothing_when_it_refuses(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "generation"
    run_root.mkdir(parents=True)
    output = tmp_path / "admission"
    with pytest.raises(CalibrationAdmissionDocumentRefused):
        _record(tmp_path, run_root=run_root, output_dir=output)
    assert not output.exists()


def test_the_producer_refuses_a_sealed_input_whose_bytes_moved(tmp_path: Path) -> None:
    sealed = _sealed_inputs(tmp_path)
    Path(sealed["production_config"]["path"]).write_text("{}\n", encoding="utf-8")
    with pytest.raises(CalibrationInputsRefused) as refusal:
        _record(tmp_path, sealed_inputs=sealed)
    assert refusal.value.code == CAL_INPUT_UNSEALED
    assert "production_config" in refusal.value.detail


def test_the_producer_refuses_a_plan_the_installed_controller_cannot_build(tmp_path: Path) -> None:
    """A step above half the field of view is refused by the run's own precondition, and by name."""

    from so101_demo.act.head_search.calibration_run import (
        CAL_TRAJECTORY_CONTRACT_UNSATISFIED as RUN_CODE,
    )

    assert RUN_CODE == CAL_TRAJECTORY_CONTRACT_UNSATISFIED
    sealed = _sealed_inputs(tmp_path)
    config = _read(Path(sealed["production_config"]["path"]))
    config["values"]["coarse_step_rad"] = 0.9
    _write_json(Path(sealed["production_config"]["path"]), config)
    sealed["production_config"]["sha256"] = hashlib.sha256(
        Path(sealed["production_config"]["path"]).read_bytes()
    ).hexdigest()
    with pytest.raises(CalibrationAdmissionDocumentRefused) as refusal:
        _record(tmp_path, sealed_inputs=sealed)
    assert refusal.value.code == CAL_TRAJECTORY_CONTRACT_UNSATISFIED
    output = tmp_path / "admission"
    assert not (output / ADMISSION_NAME).exists()
    assert not (output / PLAN_NAME).exists()
    assert not (output / RECEIPT_NAME).exists()


def test_the_producer_refuses_a_declared_config_without_the_values_it_needs(tmp_path: Path) -> None:
    sealed = _sealed_inputs(tmp_path)
    config = _read(Path(sealed["production_config"]["path"]))
    del config["values"]["search_timeout_s"]
    _write_json(Path(sealed["production_config"]["path"]), config)
    sealed["production_config"]["sha256"] = hashlib.sha256(
        Path(sealed["production_config"]["path"]).read_bytes()
    ).hexdigest()
    with pytest.raises(CalibrationAdmissionDocumentRefused) as refusal:
        _record(tmp_path, sealed_inputs=sealed)
    assert refusal.value.code == CAL_ADMISSION_INCOMPLETE
    assert "search_timeout_s" in refusal.value.detail


def test_the_producer_refuses_a_geometry_whose_field_of_view_does_not_derive(tmp_path: Path) -> None:
    geometry = _geometry(horizontal_fov_rad=0.7)
    with pytest.raises(CalibrationAdmissionDocumentRefused) as refusal:
        _record(tmp_path, sealed_inputs=_sealed_inputs(tmp_path, geometry_document=geometry))
    assert refusal.value.code == CAL_ADMISSION_INCOMPLETE
    assert "field of view" in refusal.value.detail


def test_the_producer_refuses_an_output_directory_that_already_exists(tmp_path: Path) -> None:
    output = tmp_path / "admission"
    output.mkdir()
    with pytest.raises(CalibrationAdmissionDocumentRefused) as refusal:
        _record(tmp_path, output_dir=output)
    assert refusal.value.code == CAL_ADMISSION_INCOMPLETE
    assert "never resumed or overwritten" in refusal.value.detail


def test_the_derivation_reads_the_geometry_through_the_installed_loader(tmp_path: Path) -> None:
    """The pure derivation consumes what phase 2's loader returns, so the two cannot drift."""

    sealed = _sealed_inputs(tmp_path)
    loaded = load_sealed_geometry(sealed)
    plan = derive_measurement_plan(
        production_config=_read(Path(sealed["production_config"]["path"])),
        geometry_document=_read(Path(loaded["sealed_geometry"]["path"])),
        generation="generation",
    )
    assert plan["horizontal_fov_rad"] == HORIZONTAL_FOV_RAD
    assert plan["lock_valid_neck_rad"] == list(LOCK_INTERVAL)
    assert plan["required_search_domain_rad"] == list(REQUIRED_DOMAIN)
    assert plan["session_id"] == plan["attempt_id"] == "generation"
    assert plan["search_start_rad"] == 0.0
    assert plan["min_confidence"] == 0.4
    assert plan["min_area_px2"] == 64.0
    assert plan["settle_velocity_rad_s"] == 0.05
    assert plan["goal_tolerance_rad"] == 0.05
    assert plan["frame_id"] == "head_camera_frame"
    assert plan["ray_origin_frame_id"] == "head_camera_frame"
