"""The installed producer of the run's `--bundle-inputs`: the declared blocks and their live readback.

Phase 8 collects the geometry and perception evidence blocks from the run's declared inputs, and every one
of them has to carry the section 7.1 evidence - value, unit, formula, input evidence with digests, observed
distribution, margin, production owner and the startup readback that proves the running system uses the
value. What these tests pin, with synthetic documents and an injected detector builder, is that the
producer records *observed* values rather than restating the recorded ones, that a readback it cannot take
is recorded as unverified with its reason, and that the document is one phase 8 and phase 5 accept.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from so101_demo.act.head_search_calibration_bundle import (
    ALSO_RECORDED_ITEMS,
    ALSO_RECORDED_KEYS,
    PARAMETER_EVIDENCE_KEYS,
    RUNTIME_IDENTITY_FIELDS,
)
from so101_demo.act.head_search_calibration_bundle_inputs import (
    ALSO_RECORDED_DECLARED,
    BUNDLE_INPUTS_NAME,
    CAL_BUNDLE_INPUTS_INCOMPLETE,
    DECLARED_PARAMETERS,
    GEOMETRY_PHASE,
    PERCEPTION_PHASE,
    RECEIPT_NAME,
    CalibrationBundleInputsRefused,
    installed_environment,
    record_bundle_inputs,
    runtime_identity,
)
from so101_demo.act.head_search_calibration_readback import readback_selected_perception_values
from so101_demo.perception_benchmark.contracts import canonical_sha256

FOVY_RAD = 1.0471975511965976
HORIZONTAL_FOV_RAD = 1.3121067481206794
LOCK_INTERVAL = [-6.283175307179587, 6.283175307179587]
REQUIRED_DOMAIN = [-0.17559216195018026, 0.08047101126546086]
CHOSEN_POINT = {
    "min_confidence": 0.25,
    "tracking_iou": 0.5,
    "min_bbox_aspect": 0.5,
    "min_area_px2": 64.0,
}
SELECTION_RULE = (
    "among the declared candidate points, choose the highest measured f1 over the head-domain "
    "measurements of the splits declared for selection; tie-break on the highest recall; tie-break on the "
    "lowest min_confidence; tie-break on the earliest point in the rule's declared grid order."
)
WEIGHT_BYTES = b"the selected model's weights, in a test\n"


def _geometry() -> dict:
    body = {
        "schema_version": 1,
        "camera_name": "head_camera",
        "image_width": 640,
        "image_height": 480,
        "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
        "lock_valid_neck_rad": list(LOCK_INTERVAL),
        "required_search_domain_rad": list(REQUIRED_DOMAIN),
        "coarse_step_candidate_rad": 0.4,
        "anchors": ["forward"],
        "in_frame_matrix": {
            "forward": {"centre_angle_rad": 0.18822150530477078, "neck_start_rad": 0.0,
                        "out_of_frame_rad": [], "samples": [
                            {"in_frame": True, "neck_rad": 0.0, "projected_points": 9,
                             "projected_points_in_frame": 9, "visible_pixels": 6447}]}
        },
        "in_frame_failures": [],
        "workspace_matrix": {"in_frame": 120, "key_samples": []},
        "camera": {
            "camera_name": "head_camera",
            "width": 640,
            "height": 480,
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


def _production_config(**value_overrides) -> dict:
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
        "min_bbox_aspect": 0.5,
        "tracking_iou": 0.3,
        "lock_valid_neck_rad": [-0.4, 0.4],
    }
    values.update(value_overrides)
    return {
        "schema_version": 2,
        "runtime_id": "head-search-v2",
        "values": values,
        "motion": {"goal_tolerance_rad": 0.05, "settle_velocity_rad_s": 0.05},
        "camera": {
            "frame_id": "head_camera_optical_frame",
            "ray_origin_frame_id": "base_link",
            "name": "head_camera",
            "width": 640,
            "height": 480,
        },
        "tracker": {"name": "bytetrack", "iou_threshold": 0.3},
    }


def _operating_point(*, chosen: dict | None = None, candidate_id: str = "C") -> dict:
    point = dict(CHOSEN_POINT if chosen is None else chosen)
    cell = {
        "grid_index": 0,
        "point": point,
        "frame_count": 260,
        "frames_checked": 56,
        "detections_kept": 260,
        "detections_without_geometry": 0,
        "false_positive": 0,
        "false_negative": 0,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "bbox_center_p95_px": 4.306096104033801,
        "no_cup_false_candidates": 0,
        "clean_on_empty_scenes": True,
        "filters_reapplied": ["min_confidence", "tracking_iou", "min_area_px2", "min_bbox_aspect"],
        "splits": {
            "val": {"frame_count": 200, "detections_kept": 200, "false_positive": 0,
                    "false_negative": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0,
                    "bbox_center_p95_px": 4.355},
            "calibration": {"frame_count": 60, "detections_kept": 60, "false_positive": 0,
                            "false_negative": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0,
                            "bbox_center_p95_px": 4.142812176982355},
        },
    }
    rule = {
        "schema_version": 1,
        "kind": "head_search_selection_rule",
        "phase": "perception_operating_point",
        "domain": "head",
        "selection_rule": SELECTION_RULE,
        "selection_splits": ["val", "calibration"],
        "held_out_splits": ["held_out_evaluation"],
        "tie_break_chain": ["highest f1", "highest recall", "lowest min_confidence",
                            "earliest declared grid point"],
        "point_count": 18,
        "measurements_admitted": 0,
        "recorded_before_measurement": True,
        "generation": None,
        "measurement_plan_sha256": None,
        "replaces_rule_sha256": None,
    }
    rule = {**rule, "rule_sha256": canonical_sha256(rule)}
    return {
        "schema_version": 1,
        "kind": "head_search_calibration_operating_point",
        "phase": "perception_operating_point",
        "domain": "head",
        "candidate_id": candidate_id,
        "chosen_index": 0,
        "chosen_point": point,
        "chosen_cell": cell,
        "grid": [cell],
        "grid_sha256": canonical_sha256([cell]),
        "rule": rule,
        "rule_sha256": rule["rule_sha256"],
        "selection_rule": SELECTION_RULE,
        "tie_break_chain": list(rule["tie_break_chain"]),
        "ties_broken_by": "declared_order",
        "measurements_consumed": {"per_split": {"val": 200, "calibration": 60}, "total": 260},
        "split_isolation": {"frames": 520, "held_out_frames": 0,
                            "selection_splits": ["val", "calibration"],
                            "held_out_splits": ["held_out_evaluation"],
                            "per_split": {"val": 400, "calibration": 120}},
        "no_cup_guard": {"candidate_id": candidate_id, "clean": True, "frames_checked": 56,
                         "no_cup_false_candidates": 0, "point": point},
        "held_out_consumed_for_selection": False,
        "held_out_report": {"measured": False, "consumed_for_selection": False},
        "filters_reapplied": cell["filters_reapplied"],
    }


def _frozen_candidate(*, weight_sha256: str, candidate_id: str = "C", chosen: dict | None = None) -> dict:
    point = dict(CHOSEN_POINT if chosen is None else chosen)
    return {
        "schema_version": 1,
        "kind": "head-search-frozen-candidate",
        "candidate_id": candidate_id,
        "weight_sha256": weight_sha256,
        "operating_points": {
            "head": {
                "min_confidence": point["min_confidence"],
                "tracker": {"iou": point["tracking_iou"]},
            }
        },
        "postprocess": {},
        "promotable": True,
        "runtime": {},
        "tracker": {},
    }


def _write_json(path: Path, document) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _declared(tmp_path: Path, *, geometry=None, production=None, operating=None, frozen=None) -> dict:
    weights = tmp_path / "weights" / "C.pt"
    weights.parent.mkdir(parents=True, exist_ok=True)
    weights.write_bytes(WEIGHT_BYTES)
    weight_sha256 = hashlib.sha256(WEIGHT_BYTES).hexdigest()
    return {
        "geometry_seal": _write_json(
            tmp_path / "geometry-seal.json", _geometry() if geometry is None else geometry
        ),
        "production_config": _write_json(
            tmp_path / "production-config.json",
            _production_config() if production is None else production,
        ),
        "operating_point": _write_json(
            tmp_path / "phase3-selection-head-C.json",
            _operating_point() if operating is None else operating,
        ),
        "frozen_candidate": _write_json(
            tmp_path / "frozen-c.json",
            _frozen_candidate(weight_sha256=weight_sha256) if frozen is None else frozen,
        ),
        "weights": weights,
        "weight_sha256": weight_sha256,
    }


#: the system-side reading `installed_environment` takes: nine fields, none of them from a document
ENVIRONMENT = {
    "package_prefix": "/toolchain/install/so101_demo_py",
    "console_script_path": "/toolchain/install/so101_demo_py/lib/so101_demo_py/so101_head_search_calibration",
    "torch_version": "2.5.1+cu124",
    "ultralytics_version": "8.3.40",
    "cuda_version": "12.4",
    "driver_version": "550.54.14",
    "mujoco_version": "3.2.3",
    "tracker_id": "so101_demo.adapters.act.detector.HeadRgbDetector",
    "web_bundle_id": "2" * 64,
}
SYSTEM_FIELDS = tuple(ENVIRONMENT)


class _FakeRuntime:
    """The production adapter's shape: the values it applies, and the detector it wraps."""

    def __init__(self, *, tracking_iou, min_bbox_aspect, runtime_device="cuda") -> None:
        self.tracking_iou = tracking_iou
        self.min_bbox_aspect = min_bbox_aspect
        self.detector = SimpleNamespace(runtime_device=runtime_device)


def _fake_builder(*, tracking_iou, min_bbox_aspect):
    seen = {}

    def build(binding, *, snapshot_root=None):
        seen["binding"] = binding
        seen["snapshot_root"] = snapshot_root
        return SimpleNamespace(
            runtime=_FakeRuntime(tracking_iou=tracking_iou, min_bbox_aspect=min_bbox_aspect),
            snapshot_path=Path(snapshot_root) / "best.pt",
        )

    build.seen = seen
    return build


def _record(tmp_path: Path, *, declared=None, environment=None, builder=None, **overrides) -> dict:
    declared = _declared(tmp_path) if declared is None else declared
    resolved = dict(ENVIRONMENT)
    resolved.update(environment or {})
    arguments = {
        "geometry_seal": declared["geometry_seal"],
        "production_config": declared["production_config"],
        "operating_point": declared["operating_point"],
        "frozen_candidate": declared["frozen_candidate"],
        "weights": declared["weights"],
        "output_dir": tmp_path / "bundle-inputs",
        "environment": (lambda web_bundle_root=None: dict(resolved)),
        "detector_builder": builder if builder is not None else _fake_builder(
            tracking_iou=CHOSEN_POINT["tracking_iou"], min_bbox_aspect=CHOSEN_POINT["min_bbox_aspect"]
        ),
        "command": "ros2 run so101_demo_py so101_head_search_calibration measure-bundle-inputs",
    }
    arguments.update(overrides)
    return record_bundle_inputs(**arguments)


def _read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_the_key_contracts_are_phase_eights_own(tmp_path: Path) -> None:
    """The producer cannot drift from the keys phase 8 collects, so it reuses its tuples by name."""

    document = _read(_record(tmp_path)["document_path"])
    assert set(DECLARED_PARAMETERS) == {
        "horizontal_fov_rad", "lock_valid_neck_rad", "min_confidence", "tracking_iou",
        "min_bbox_aspect", "min_area_px2",
    }
    for phase, names in (
        (GEOMETRY_PHASE, ("horizontal_fov_rad", "lock_valid_neck_rad")),
        (PERCEPTION_PHASE, ("min_confidence", "tracking_iou", "min_bbox_aspect", "min_area_px2")),
    ):
        blocks = document["parameter_evidence"][phase]["parameters"]
        assert set(blocks) == set(names)
        for name, block in blocks.items():
            assert set(PARAMETER_EVIDENCE_KEYS) <= set(block), name
    assert set(document["also_recorded"]) == set(ALSO_RECORDED_DECLARED)
    assert set(ALSO_RECORDED_DECLARED) < set(ALSO_RECORDED_ITEMS)
    assert "frame_contract_10_hz" not in document["also_recorded"]
    for item, record in document["also_recorded"].items():
        assert set(ALSO_RECORDED_KEYS) <= set(record), item
    assert set(document["runtime_identity"]) == set(RUNTIME_IDENTITY_FIELDS)


def test_the_values_are_the_sealed_geometry_and_the_selected_point(tmp_path: Path) -> None:
    document = _read(_record(tmp_path)["document_path"])
    geometry = document["parameter_evidence"][GEOMETRY_PHASE]["parameters"]
    perception = document["parameter_evidence"][PERCEPTION_PHASE]["parameters"]
    assert geometry["horizontal_fov_rad"]["value"] == HORIZONTAL_FOV_RAD
    assert geometry["lock_valid_neck_rad"]["value"] == LOCK_INTERVAL
    for name, value in CHOSEN_POINT.items():
        assert perception[name]["value"] == value, name


def test_the_geometry_values_are_the_seals_not_the_configurations_copy(tmp_path: Path) -> None:
    declared = _declared(tmp_path, production=_production_config(horizontal_fov_rad=0.9))
    document = _read(_record(tmp_path, declared=declared)["document_path"])
    geometry = document["parameter_evidence"][GEOMETRY_PHASE]["parameters"]
    assert geometry["horizontal_fov_rad"]["value"] == HORIZONTAL_FOV_RAD
    assert geometry["lock_valid_neck_rad"]["value"] == LOCK_INTERVAL


def test_every_block_records_input_evidence_that_digests_to_the_file_it_names(tmp_path: Path) -> None:
    result = _record(tmp_path)
    document = _read(result["document_path"])
    blocks = [
        block
        for phase in (GEOMETRY_PHASE, PERCEPTION_PHASE)
        for block in document["parameter_evidence"][phase]["parameters"].values()
    ] + list(document["also_recorded"].values())
    for block in blocks:
        references = block["input_evidence"]
        assert references
        for reference in references:
            path = Path(reference["path"])
            assert path.is_file(), reference
            assert hashlib.sha256(path.read_bytes()).hexdigest() == reference["sha256"]


def test_the_startup_readback_observes_the_components_values(tmp_path: Path) -> None:
    document = _read(_record(tmp_path)["document_path"])
    expected = {"horizontal_fov_rad", "lock_valid_neck_rad", "min_confidence", "min_area_px2", "tracking_iou",
                "min_bbox_aspect"}
    seen = set()
    for phase in (GEOMETRY_PHASE, PERCEPTION_PHASE):
        for name, block in document["parameter_evidence"][phase]["parameters"].items():
            readback = block["startup_readback"]
            assert readback["observed_value"] == block["value"], name
            assert readback["verified"] is True, name
            assert readback["source"]
            seen.add(name)
    assert seen == expected


def test_the_controller_is_constructed_with_the_recorded_values(tmp_path: Path) -> None:
    result = _record(tmp_path)
    receipt = _read(result["receipt_path"])
    configuration = receipt["effective_value_readback"]["controller"]["configuration"]
    assert configuration["min_confidence"] == CHOSEN_POINT["min_confidence"]
    assert configuration["min_area_px2"] == CHOSEN_POINT["min_area_px2"]
    assert configuration["horizontal_fov_rad"] == HORIZONTAL_FOV_RAD
    assert configuration["lock_valid_neck_rad"] == LOCK_INTERVAL
    observed = receipt["effective_value_readback"]["controller"]["observed"]
    assert observed["min_confidence"] == CHOSEN_POINT["min_confidence"]
    assert observed["lock_valid_neck_rad"] == LOCK_INTERVAL
    assert receipt["effective_value_readback"]["controller"]["bounded_plan"]["coverage_complete"] is True


def test_the_detector_is_constructed_with_the_selected_model_and_its_values(tmp_path: Path) -> None:
    declared = _declared(tmp_path)
    builder = _fake_builder(
        tracking_iou=CHOSEN_POINT["tracking_iou"], min_bbox_aspect=CHOSEN_POINT["min_bbox_aspect"]
    )
    receipt = _read(_record(tmp_path, declared=declared, builder=builder)["receipt_path"])
    binding = builder.seen["binding"]
    assert binding.search_values["tracking_iou"] == CHOSEN_POINT["tracking_iou"]
    assert binding.search_values["min_bbox_aspect"] == CHOSEN_POINT["min_bbox_aspect"]
    assert binding.detector["weights_path"] == str(declared["weights"])
    assert binding.detector["weights_sha256"] == hashlib.sha256(WEIGHT_BYTES).hexdigest()
    assert binding.detector["requested_device"] == "cuda"
    assert binding.detector["allow_cpu_fallback"] is False
    observed = receipt["effective_value_readback"]["detector"]["observed"]
    assert observed["tracking_iou"] == CHOSEN_POINT["tracking_iou"]
    assert observed["min_bbox_aspect"] == CHOSEN_POINT["min_bbox_aspect"]


def test_a_readback_that_cannot_be_taken_is_recorded_unverified_with_its_reason(tmp_path: Path) -> None:
    def refusing_builder(binding, *, snapshot_root=None):
        raise RuntimeError("no CUDA device is visible")

    result = _record(tmp_path, builder=refusing_builder)
    document = _read(result["document_path"])
    perception = document["parameter_evidence"][PERCEPTION_PHASE]["parameters"]
    for name in ("tracking_iou", "min_bbox_aspect"):
        readback = perception[name]["startup_readback"]
        assert readback["verified"] is False
        assert readback["observed_value"] == perception[name]["value"]
        assert "no CUDA device is visible" in readback["reason"]
        assert readback["observation"] == "not_observable"
    # the four the controller and the seal carry stay observed and verified
    assert perception["min_confidence"]["startup_readback"]["verified"] is True
    assert perception["min_area_px2"]["startup_readback"]["verified"] is True
    assert document["parameter_evidence"][GEOMETRY_PHASE]["parameters"][
        "horizontal_fov_rad"
    ]["startup_readback"]["verified"] is True
    receipt = _read(result["receipt_path"])
    assert receipt["effective_value_readback"]["detector"]["constructed"] is False
    assert receipt["effective_value_readback"]["detector"]["reason"].startswith("RuntimeError: ")


def test_the_three_frame_lock_rule_is_observed_behaviourally(tmp_path: Path) -> None:
    document = _read(_record(tmp_path)["document_path"])
    record = document["also_recorded"]["three_consecutive_frame_lock_rule"]
    assert "three consecutive" in record["value_or_definition"]
    readback = record["startup_readback"]
    assert readback["verified"] is True
    assert readback["observation"] == "behavioural"
    assert readback["ticks_to_lock"] == 3
    assert readback["status_after_three_ticks"] == "TARGET_LOCKED"
    assert readback["locked_after_two_ticks"] is False
    assert readback["locked_with_one_frame_outside_the_deadband"] is False


def test_the_tracker_algorithm_is_the_one_the_running_detector_uses(tmp_path: Path) -> None:
    document = _read(_record(tmp_path)["document_path"])
    record = document["also_recorded"]["tracker_algorithm"]
    assert "HeadRgbDetector" in record["value_or_definition"]
    assert "bytetrack" in record["value_or_definition"]
    readback = record["startup_readback"]
    assert readback["verified"] is True
    assert readback["observed"]["tracking_iou"] == CHOSEN_POINT["tracking_iou"]
    assert readback["declared_in_production_config"] == {"name": "bytetrack", "iou_threshold": 0.3}


def test_the_motion_tolerances_are_observed_on_the_constructed_controller(tmp_path: Path) -> None:
    document = _read(_record(tmp_path)["document_path"])
    for item, expected in (("settle_velocity_rad_s", 0.05), ("goal_tolerance_rad", 0.05)):
        record = document["also_recorded"][item]
        assert record["value_or_definition"] == expected
        assert record["startup_readback"]["observed_value"] == expected
        assert record["startup_readback"]["verified"] is True


def test_phase_five_certifies_the_blocks_this_producer_declares(tmp_path: Path) -> None:
    """The installed phase 5 reads the assembled bundle back, and it has to certify every value."""

    declared = _declared(tmp_path)
    result = _record(tmp_path, declared=declared)
    document = _read(result["document_path"])
    parameters = {
        name: block
        for phase in (GEOMETRY_PHASE, PERCEPTION_PHASE)
        for name, block in document["parameter_evidence"][phase]["parameters"].items()
    }
    readback = readback_selected_perception_values(
        bundle={"parameters": parameters, "runtime_identity": document["runtime_identity"]},
        operating_point=_read(declared["operating_point"]),
        frozen_candidate=_read(declared["frozen_candidate"]),
    )
    assert readback["values_unmodified"] is True
    assert readback["selection_identity_matches"] is True
    assert readback["candidate_id"] == "C"


def test_the_receipt_records_the_observed_values_and_their_digests(tmp_path: Path) -> None:
    result = _record(tmp_path)
    receipt = _read(result["receipt_path"])
    assert receipt["status"] == "RECORDED"
    assert receipt["motion_commanded"] is False
    assert receipt["cpu_fallback"] is False
    assert receipt["values"] == CHOSEN_POINT | {
        "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
        "lock_valid_neck_rad": LOCK_INTERVAL,
    }
    assert receipt["unverified"] == []
    assert receipt["bundle_inputs"]["path"] == str(result["document_path"])
    assert receipt["bundle_inputs"]["sha256"] == hashlib.sha256(
        Path(result["document_path"]).read_bytes()
    ).hexdigest()
    assert receipt["provenance"]["command"].endswith("measure-bundle-inputs")
    for key in ("geometry_seal", "production_config", "operating_point", "frozen_candidate", "weights"):
        reference = receipt["provenance"]["inputs"][key]
        assert hashlib.sha256(Path(reference["path"]).read_bytes()).hexdigest() == reference["sha256"]
    assert receipt["provenance"]["inputs"]["weights"]["sha256"] == receipt["runtime_identity"][
        "detector_weights_sha256"
    ]


def test_the_producer_refuses_a_frozen_candidate_that_seals_another_file(tmp_path: Path) -> None:
    declared = _declared(
        tmp_path, frozen=_frozen_candidate(weight_sha256="9" * 64)
    )
    with pytest.raises(CalibrationBundleInputsRefused) as refusal:
        _record(tmp_path, declared=declared)
    assert refusal.value.code == CAL_BUNDLE_INPUTS_INCOMPLETE
    assert "weights" in refusal.value.detail


def test_the_producer_refuses_an_operating_point_without_the_chosen_point(tmp_path: Path) -> None:
    operating = _operating_point()
    del operating["chosen_point"]
    declared = _declared(tmp_path, operating=operating)
    with pytest.raises(CalibrationBundleInputsRefused) as refusal:
        _record(tmp_path, declared=declared)
    assert refusal.value.code == CAL_BUNDLE_INPUTS_INCOMPLETE
    assert "chosen point" in refusal.value.detail


def test_the_producer_refuses_a_selection_whose_rule_digest_does_not_cover_it(tmp_path: Path) -> None:
    operating = _operating_point()
    operating["rule"]["point_count"] = 17
    declared = _declared(tmp_path, operating=operating)
    with pytest.raises(CalibrationBundleInputsRefused) as refusal:
        _record(tmp_path, declared=declared)
    assert refusal.value.code == CAL_BUNDLE_INPUTS_INCOMPLETE
    assert "rule" in refusal.value.detail


def test_the_producer_refuses_an_environment_that_cannot_identify_the_running_system(
    tmp_path: Path,
) -> None:
    with pytest.raises(CalibrationBundleInputsRefused) as refusal:
        _record(tmp_path, environment={**ENVIRONMENT, "web_bundle_id": ""})
    assert refusal.value.code == CAL_BUNDLE_INPUTS_INCOMPLETE
    assert "web_bundle_id" in refusal.value.detail


def test_the_producer_refuses_an_existing_output_directory_and_writes_nothing(tmp_path: Path) -> None:
    output = tmp_path / "bundle-inputs"
    output.mkdir()
    with pytest.raises(CalibrationBundleInputsRefused) as refusal:
        _record(tmp_path, output_dir=output)
    assert refusal.value.code == CAL_BUNDLE_INPUTS_INCOMPLETE
    assert "never resumed or overwritten" in refusal.value.detail
    assert sorted(path.name for path in output.iterdir()) == []


def test_the_runtime_identity_checks_every_field_phase_eight_requires(tmp_path: Path) -> None:
    geometry = _geometry()
    identity = runtime_identity(
        environment={**ENVIRONMENT, "detector_weights_sha256": "3" * 64},
        geometry_document=geometry,
        production_config=_production_config(),
    )
    assert tuple(identity) == RUNTIME_IDENTITY_FIELDS
    assert identity["camera_intrinsics_sha256"] == canonical_sha256(geometry["camera"])
    assert identity["camera_id"] == geometry["camera_name"]
    with pytest.raises(CalibrationBundleInputsRefused) as refusal:
        runtime_identity(
            environment={**ENVIRONMENT, "detector_weights_sha256": "3" * 64, "web_bundle_id": ""},
            geometry_document=geometry,
            production_config=_production_config(),
        )
    assert refusal.value.code == CAL_BUNDLE_INPUTS_INCOMPLETE
    assert "web_bundle_id" in refusal.value.detail
    with pytest.raises(CalibrationBundleInputsRefused) as refusal:
        runtime_identity(
            environment={
                **{key: value for key, value in ENVIRONMENT.items() if key != "mujoco_version"},
                "detector_weights_sha256": "3" * 64,
            },
            geometry_document=geometry,
            production_config=_production_config(),
        )
    assert refusal.value.code == CAL_BUNDLE_INPUTS_INCOMPLETE
    assert "mujoco_version" in refusal.value.detail
    drifted = _production_config()
    drifted["camera"]["name"] = "other_camera"
    with pytest.raises(CalibrationBundleInputsRefused) as refusal:
        runtime_identity(
            environment={**ENVIRONMENT, "detector_weights_sha256": "3" * 64},
            geometry_document=geometry,
            production_config=drifted,
        )
    assert refusal.value.code == CAL_BUNDLE_INPUTS_INCOMPLETE
    assert "other_camera" in refusal.value.detail


def test_the_installed_environment_names_the_running_system(tmp_path: Path) -> None:
    """The real reader: the versions, the driver and the bundle digest are read, nothing is injected.

    Only the two install-tree paths are declared, because the ordinary suite runs from a checkout whose
    workspace install carries no head-search console script; the versions, the CUDA runtime, the driver,
    the MuJoCo version and the tracker adapter are read from the process and the machine.
    """

    prefix = tmp_path / "install" / "so101_demo_py"
    script = prefix / "lib" / "so101_demo_py" / "so101_head_search_calibration"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    web = tmp_path / "install" / "so101_teleop" / "share" / "so101_teleop" / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (web / "assets" / "app.js").write_text("console.log(1)\n", encoding="utf-8")

    reading = installed_environment(package_prefix=prefix, web_bundle_root=web)
    assert set(reading) == set(SYSTEM_FIELDS)
    assert reading["package_prefix"] == str(prefix)
    assert reading["console_script_path"] == str(script)
    for field in ("torch_version", "ultralytics_version", "cuda_version", "driver_version",
                  "mujoco_version", "tracker_id"):
        assert reading[field], field
    assert reading["tracker_id"].endswith("HeadRgbDetector")
    assert len(reading["web_bundle_id"]) == 64
    # the digest covers the served files: adding one changes it
    (web / "assets" / "extra.js").write_text("console.log(2)\n", encoding="utf-8")
    assert installed_environment(package_prefix=prefix, web_bundle_root=web)["web_bundle_id"] != reading[
        "web_bundle_id"
    ]
    empty = tmp_path / "empty-web"
    empty.mkdir()
    with pytest.raises(CalibrationBundleInputsRefused) as refusal:
        installed_environment(package_prefix=prefix, web_bundle_root=empty)
    assert refusal.value.code == CAL_BUNDLE_INPUTS_INCOMPLETE
    assert "holds no file" in refusal.value.detail
