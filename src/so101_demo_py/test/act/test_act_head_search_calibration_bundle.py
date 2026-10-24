"""Phase 8 of the formal head-search calibration: the bundle, its manifest and the run status.

The phase assembles what the earlier phases measured: the seventeen parameters of design section 7.1
with one evidence block each, the five items section 7.1 also requires recorded though they are not
among the seventeen (settle velocity, goal tolerance, the three-consecutive-frame lock rule, the tracker
algorithm and the 10 Hz frame contract), the runtime identity and the controlled
dependencies with their digests. It records no approval state of any kind: the approval is bound to the
bundle digest later, by the promotion step (plan section 2a).

Everything here is a synthetic fixture: no ROS, no MuJoCo, no detector, no GPU. The fixtures are plain
dictionaries; the only files this phase writes are the three documents, and only under `output_dir`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from so101_demo.act.head_search.calibration_bundle import (
    ALSO_RECORDED_ITEMS,
    ARTIFACT_NAMES,
    CAL_BUNDLE_INCOMPLETE,
    CAL_EFFECTIVE_VALUE_MISMATCH,
    PARAMETER_EVIDENCE_KEYS,
    RUNTIME_IDENTITY_FIELDS,
    CalibrationBundleRefused,
    assemble_calibration_bundle,
    build_run_status,
)
from so101_demo.act.head_search.calibration_inputs import SEALED_INPUT_NAMES
from so101_demo.perception_benchmark.contracts import canonical_sha256

COMMAND = "ros2 run so101_demo_py so101_head_search_calibration run --run-root /evidence/run-01"

#: the authoritative seventeen, in the order design section 7.1 lists them
CALIBRATION_BUNDLE_PARAMETERS = (
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
)

#: the unit design section 7.1 fixes for each of the seventeen
UNITS = {
    "horizontal_fov_rad": "rad",
    "lock_valid_neck_rad": "rad",
    "coarse_step_rad": "rad",
    "search_timeout_s": "s",
    "min_confidence": "1",
    "tracking_iou": "1",
    "min_bbox_aspect": "1",
    "min_area_px2": "px^2",
    "center_deadband_px": "px",
    "vertical_bounds_px": "px",
    "max_fine_corrections": "1",
    "max_fine_total_rad": "rad",
    "max_age_s": "s",
    "max_skew_s": "s",
    "submit_lead_s": "s",
    "stop_velocity_rad_s": "rad/s",
    "stop_latency_s": "s",
}

#: which phase hands over which parameter (plan section 3, "Parameter to phase map")
PHASE_PARAMETERS = {
    "geometry_coverage": ("horizontal_fov_rad", "lock_valid_neck_rad"),
    "perception_operating_point": (
        "min_confidence",
        "tracking_iou",
        "min_bbox_aspect",
        "min_area_px2",
    ),
    "search_parameters": (
        "coarse_step_rad",
        "search_timeout_s",
        "center_deadband_px",
        "vertical_bounds_px",
        "max_fine_corrections",
        "max_fine_total_rad",
    ),
    "timing_stop_parameters": (
        "max_age_s",
        "max_skew_s",
        "submit_lead_s",
        "stop_velocity_rad_s",
        "stop_latency_s",
    ),
}

PHASE_VALUES = {
    "geometry_coverage": {
        "horizontal_fov_rad": 1.3121067481206794,
        "lock_valid_neck_rad": [-6.28, 6.28],
    },
    "perception_operating_point": {
        "min_confidence": 0.25,
        "tracking_iou": 0.5,
        "min_bbox_aspect": 1.0,
        "min_area_px2": 64.0,
    },
    "search_parameters": {
        "coarse_step_rad": 0.6560533740603397,
        "search_timeout_s": 18.0,
        "center_deadband_px": 12.0,
        "vertical_bounds_px": [40.0, 440.0],
        "max_fine_corrections": 12,
        "max_fine_total_rad": 0.3,
    },
    "timing_stop_parameters": {
        "max_age_s": 0.15,
        "max_skew_s": 0.03,
        "submit_lead_s": 0.02,
        "stop_velocity_rad_s": 0.01,
        "stop_latency_s": 0.25,
    },
}

#: the top-level key sets the three documents must have, exactly - no approval key is among them
EXPECTED_BUNDLE_KEYS = {
    "schema_version",
    "kind",
    "phase",
    "parameter_names",
    "parameters",
    "also_recorded",
    "runtime_identity",
    "controlled_dependencies",
}
EXPECTED_MANIFEST_KEYS = {
    "schema_version",
    "kind",
    "phase",
    "command",
    "artifacts",
    "controlled_dependencies",
    "runtime_identity",
    "parameter_names",
    "also_recorded",
}
EXPECTED_RUN_STATUS_KEYS = {
    "schema_version",
    "kind",
    "phase",
    "status",
    "audit_only",
    "checkpoint",
    "resume_supported",
    "command",
    "exit_code",
    "first_failing_phase",
    "failure_code",
    "failure_command",
    "failure_exit_code",
    "evidence_produced",
}

#: any key carrying one of these is an approval state, which phase 8 must never record
APPROVAL_TOKENS = ("approval", "approved", "approve", "signoff", "sign_off")


def _sha(seed: str) -> str:
    return canonical_sha256({"seed": seed})


def _evidence(name, value):
    return {
        "value": value,
        "unit": UNITS[name],
        "selection_formula": f"the {name} rule of design 7.1",
        "input_evidence": [
            {"path": f"/evidence/{name}-campaign.json", "sha256": _sha(f"{name}-campaign")},
            {"path": f"/evidence/{name}-val.json", "sha256": _sha(f"{name}-val")},
        ],
        "observed_distribution": {
            "p50": value if not isinstance(value, list) else (value[0] + value[1]) / 2.0,
            "p99": value if not isinstance(value, list) else value[1],
            "samples": 120,
        },
        "safety_margin": {"bound": 1.5, "observed": 1.0},
        "production_owner": "src/act/head_search/calibration.py",
        "startup_readback": {"source": "ros2 param get", "observed_value": value},
    }


def _phase_inputs(values=None):
    """Build the four phase documents; a name missing from ``values`` is simply not declared."""

    values = PHASE_VALUES if values is None else values
    return {
        phase: {
            "parameters": {
                name: _evidence(name, values[phase][name])
                for name in names
                if name in values[phase]
            }
        }
        for phase, names in PHASE_PARAMETERS.items()
    }


def _runtime_identity():
    return {
        "package_prefix": "/toolchain/install/so101_demo_py",
        "console_script_path": "/toolchain/install/so101_demo_py/lib/so101_demo_py/so101_head_search_calibration",
        "detector_weights_sha256": _sha("weights"),
        "torch_version": "2.5.1",
        "ultralytics_version": "8.3.0",
        "cuda_version": "12.4",
        "driver_version": "550.54.14",
        "mujoco_version": "3.2.3",
        "camera_id": "head-cam-0",
        "camera_intrinsics_sha256": _sha("intrinsics"),
        "tracker_id": "iou-tracker-v1",
        "web_bundle_id": "web-20260930",
    }


def _controlled_dependencies():
    return {
        name: {"path": f"/sealed/{name}.json", "sha256": _sha(name)} for name in SEALED_INPUT_NAMES
    }


def _recorded_item(definition):
    return {
        "value_or_definition": definition,
        "input_evidence": [
            {"path": "/evidence/design-7.1-final-paragraph.md", "sha256": _sha("design")}
        ],
        "startup_readback": {"source": "startup log", "observed": definition},
    }


def _also_recorded():
    definitions = {
        "settle_velocity_rad_s": 0.005,
        "goal_tolerance_rad": 0.01,
        "three_consecutive_frame_lock_rule": "locked after three consecutive frames inside deadband",
        "tracker_algorithm": "greedy nearest-within-match-radius IoU tracker",
        "frame_contract_10_hz": "head camera frames arrive at 10 Hz",
    }
    return {item: _recorded_item(definitions[item]) for item in ALSO_RECORDED_ITEMS}


def _assemble(output_dir, **overrides):
    arguments = {
        "status": "SUCCEEDED",
        "command": COMMAND,
        "exit_code": 0,
        "phase_inputs": _phase_inputs(),
        "controlled_dependencies": _controlled_dependencies(),
        "runtime_identity": _runtime_identity(),
        "also_recorded": _also_recorded(),
        "output_dir": output_dir,
    }
    arguments.update(overrides)
    return assemble_calibration_bundle(**arguments)


def _all_keys(value):
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield key
            yield from _all_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _all_keys(item)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_happy_path_assembles_the_seventeen_with_their_evidence(tmp_path):
    result = _assemble(tmp_path / "run-01")

    assert set(result) == {"bundle", "manifest", "run_status"}
    bundle = result["bundle"]
    assert tuple(bundle["parameter_names"]) == CALIBRATION_BUNDLE_PARAMETERS
    assert set(bundle["parameters"]) == set(CALIBRATION_BUNDLE_PARAMETERS)
    for name in CALIBRATION_BUNDLE_PARAMETERS:
        block = bundle["parameters"][name]
        assert set(block) == set(PARAMETER_EVIDENCE_KEYS), name
        assert block["value"] == PHASE_VALUES[_owner(name)][name], name
        assert block["unit"] == UNITS[name], name
        assert block["production_owner"], name
        assert block["selection_formula"], name
        assert block["observed_distribution"], name
        assert block["safety_margin"], name
        assert block["startup_readback"]["observed_value"] == block["value"], name
        assert block["input_evidence"], name
        for reference in block["input_evidence"]:
            assert set(reference) == {"path", "sha256"}, name
            assert len(reference["sha256"]) == 64, name

    assert set(bundle["also_recorded"]) == set(ALSO_RECORDED_ITEMS)
    assert bundle["runtime_identity"] == _runtime_identity()
    assert set(bundle["runtime_identity"]) == set(RUNTIME_IDENTITY_FIELDS)
    assert set(bundle["controlled_dependencies"]) == set(SEALED_INPUT_NAMES)
    for name, dependency in bundle["controlled_dependencies"].items():
        assert dependency["path"] == f"/sealed/{name}.json"
        assert len(dependency["sha256"]) == 64

    assert set(result["manifest"]["artifacts"]) == set(ARTIFACT_NAMES)
    assert result["manifest"]["command"] == COMMAND
    assert result["manifest"]["runtime_identity"] == _runtime_identity()
    assert tuple(result["manifest"]["parameter_names"]) == CALIBRATION_BUNDLE_PARAMETERS

    written = {path.name for path in (tmp_path / "run-01").iterdir()}
    assert written == set(ARTIFACT_NAMES)
    assert result["run_status"]["status"] == "SUCCEEDED"


def _owner(name):
    for phase, names in PHASE_PARAMETERS.items():
        if name in names:
            return phase
    raise AssertionError(name)


def test_a_missing_value_is_refused_and_nothing_is_written(tmp_path):
    values = {phase: dict(items) for phase, items in PHASE_VALUES.items()}
    del values["timing_stop_parameters"]["max_age_s"]
    output_dir = tmp_path / "run-01"

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(output_dir, phase_inputs=_phase_inputs(values))

    assert refusal.value.code == CAL_BUNDLE_INCOMPLETE
    assert "max_age_s" in refusal.value.detail
    assert not output_dir.exists()


def test_a_value_without_its_evidence_block_is_refused(tmp_path):
    phases = _phase_inputs()
    phases["perception_operating_point"]["parameters"]["min_confidence"] = 0.25

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(tmp_path / "run-01", phase_inputs=phases)

    assert refusal.value.code == CAL_BUNDLE_INCOMPLETE
    assert "min_confidence" in refusal.value.detail


@pytest.mark.parametrize(
    "dropped", ["safety_margin", "startup_readback", "selection_formula", "unit"]
)
def test_an_evidence_block_that_omits_a_required_field_is_refused(tmp_path, dropped):
    phases = _phase_inputs()
    del phases["search_parameters"]["parameters"]["coarse_step_rad"][dropped]

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(tmp_path / "run-01", phase_inputs=phases)

    assert refusal.value.code == CAL_BUNDLE_INCOMPLETE
    assert dropped in refusal.value.detail


def test_input_evidence_without_a_digest_is_refused(tmp_path):
    phases = _phase_inputs()
    phases["geometry_coverage"]["parameters"]["horizontal_fov_rad"]["input_evidence"] = [
        {"path": "/evidence/campaign.json"}
    ]

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(tmp_path / "run-01", phase_inputs=phases)

    assert refusal.value.code == CAL_BUNDLE_INCOMPLETE


def test_a_value_with_a_different_startup_readback_is_refused(tmp_path):
    phases = _phase_inputs()
    phases["timing_stop_parameters"]["parameters"]["max_age_s"]["startup_readback"] = {
        "source": "ros2 param get",
        "observed_value": 0.9,
    }

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(tmp_path / "run-01", phase_inputs=phases)

    assert refusal.value.code == CAL_EFFECTIVE_VALUE_MISMATCH
    assert "max_age_s" in refusal.value.detail


def test_a_controlled_dependency_without_its_digest_is_refused(tmp_path):
    dependencies = _controlled_dependencies()
    del dependencies["camera_config"]["sha256"]

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(tmp_path / "run-01", controlled_dependencies=dependencies)

    assert refusal.value.code == CAL_BUNDLE_INCOMPLETE
    assert "camera_config" in refusal.value.detail


def test_a_dependency_outside_the_sealed_six_is_refused(tmp_path):
    dependencies = _controlled_dependencies()
    dependencies["detector_weights"] = {"path": "/sealed/weights.pt", "sha256": _sha("weights")}

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(tmp_path / "run-01", controlled_dependencies=dependencies)

    assert refusal.value.code == CAL_BUNDLE_INCOMPLETE


def test_a_missing_runtime_identity_field_is_refused(tmp_path):
    identity = _runtime_identity()
    del identity["tracker_id"]

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(tmp_path / "run-01", runtime_identity=identity)

    assert refusal.value.code == CAL_BUNDLE_INCOMPLETE
    assert "tracker_id" in refusal.value.detail


def test_a_missing_also_recorded_item_is_refused(tmp_path):
    recorded = _also_recorded()
    del recorded["tracker_algorithm"]

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(tmp_path / "run-01", also_recorded=recorded)

    assert refusal.value.code == CAL_BUNDLE_INCOMPLETE
    assert "tracker_algorithm" in refusal.value.detail


def test_a_parameter_outside_the_seventeen_is_refused(tmp_path):
    phases = _phase_inputs()
    phases["perception_operating_point"]["parameters"]["wobble_rad"] = _evidence(
        "min_confidence", 1.0
    )

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(tmp_path / "run-01", phase_inputs=phases)

    assert refusal.value.code == CAL_BUNDLE_INCOMPLETE
    assert "wobble_rad" in refusal.value.detail


def test_two_assemblies_of_the_same_inputs_are_byte_identical(tmp_path):
    first = _assemble(tmp_path / "run-01")
    second = _assemble(tmp_path / "run-02")

    assert canonical_sha256(first["bundle"]) == canonical_sha256(second["bundle"])
    assert canonical_sha256(first["manifest"]) == canonical_sha256(second["manifest"])
    assert canonical_sha256(first["run_status"]) == canonical_sha256(second["run_status"])
    for name in ARTIFACT_NAMES:
        assert (tmp_path / "run-01" / name).read_bytes() == (
            tmp_path / "run-02" / name
        ).read_bytes()


def test_a_failed_run_records_the_first_failing_phase_and_its_evidence(tmp_path):
    output_dir = tmp_path / "run-01"
    result = assemble_calibration_bundle(
        status="FAILED",
        failure={
            "phase": "search_parameters",
            "code": "CAL_TIMEOUT_UNBOUNDED",
            "command": COMMAND,
            "exit_code": 3,
            "evidence_produced": [
                "geometry-measurements.json",
                "perception-calibration.json",
            ],
        },
        output_dir=output_dir,
    )

    assert set(result) == {"run_status"}
    run_status = result["run_status"]
    assert run_status["status"] == "FAILED"
    assert run_status["first_failing_phase"] == "search_parameters"
    assert run_status["failure_code"] == "CAL_TIMEOUT_UNBOUNDED"
    assert run_status["failure_command"] == COMMAND
    assert run_status["failure_exit_code"] == 3
    assert run_status["evidence_produced"] == [
        "geometry-measurements.json",
        "perception-calibration.json",
    ]
    assert run_status["checkpoint"] is False
    assert {path.name for path in output_dir.iterdir()} == {"run-status.json"}
    assert json.loads(_read(output_dir / "run-status.json")) == run_status


def test_a_failed_run_without_its_failure_record_is_a_caller_error():
    with pytest.raises(ValueError):
        build_run_status(status="FAILED", command=None, exit_code=None)


def test_a_failed_run_without_a_first_failing_phase_is_a_caller_error():
    with pytest.raises(ValueError):
        build_run_status(
            status="FAILED",
            command=None,
            exit_code=None,
            failure={
                "code": "CAL_TIMEOUT_UNBOUNDED",
                "command": COMMAND,
                "exit_code": 3,
                "evidence_produced": [],
            },
        )


def test_a_succeeded_run_status_is_audit_only_and_never_a_checkpoint(tmp_path):
    run_status = _assemble(tmp_path / "run-01")["run_status"]

    assert run_status["status"] == "SUCCEEDED"
    assert run_status["audit_only"] is True
    assert run_status["checkpoint"] is False
    assert run_status["resume_supported"] is False
    assert run_status["first_failing_phase"] is None
    assert run_status["failure_code"] is None
    assert run_status["failure_command"] is None
    assert run_status["failure_exit_code"] is None
    assert set(run_status["evidence_produced"]) == set(ARTIFACT_NAMES)


def test_the_produced_documents_record_no_approval_state(tmp_path):
    output_dir = tmp_path / "run-01"
    result = _assemble(output_dir)

    assert set(result["bundle"]) == EXPECTED_BUNDLE_KEYS
    assert set(result["manifest"]) == EXPECTED_MANIFEST_KEYS
    assert set(result["run_status"]) == EXPECTED_RUN_STATUS_KEYS
    for document in result.values():
        for key in _all_keys(document):
            assert not any(token in key.lower() for token in APPROVAL_TOKENS), key
    for name in ARTIFACT_NAMES:
        text = _read(output_dir / name).lower()
        assert not any(token in text for token in APPROVAL_TOKENS), name


def test_an_approval_field_smuggled_into_a_phase_input_is_refused(tmp_path):
    phases = _phase_inputs()
    phases["geometry_coverage"]["parameters"]["horizontal_fov_rad"]["approved"] = True

    with pytest.raises(CalibrationBundleRefused) as refusal:
        _assemble(tmp_path / "run-01", phase_inputs=phases)

    assert refusal.value.code == CAL_BUNDLE_INCOMPLETE
    assert "approved" in refusal.value.detail
