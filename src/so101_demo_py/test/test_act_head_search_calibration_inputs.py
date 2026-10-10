"""Phase 1 of the formal head-search calibration: sealed inputs, admission and one resource binding.

The phase validates the six sealed controlled dependencies by digest, takes the single `role=calibration`
measurement flight, and binds the run's resources exactly once at the CLI entry. Nothing here starts ROS,
MuJoCo or a detector: the sealed inputs are ordinary files under `tmp_path`, and the admission is the
repository's own `CalibrationMeasurementAdmission` (design section 8.2, plan section 2 phase 1).
"""

from __future__ import annotations

import hashlib
import json

import pytest

GENERATION = "g1"
PLAN_SHA = "a" * 64
SAFE_INTERVAL = (-1.0, 1.0)
#: one real file per controlled dependency, with the bytes a seal would have digested
CONTENTS = {
    "dataset_manifest": b'{"kind": "head_search_dataset", "scenes": 40}\n',
    "model_manifest": b'{"kind": "head_search_model", "candidate": "C2a"}\n',
    "geometry_seal": b'{"kind": "head_camera_geometry", "horizontal_fov_rad": 1.3121}\n',
    "scenario_partitions": b'{"kind": "scenario_partitions", "val": 12, "test": 12}\n',
    "production_config": b'{"kind": "head_search_v2", "values": {}}\n',
    "camera_config": b'{"kind": "head_camera", "width_px": 640, "height_px": 480}\n',
}


class _PermissiveAdmission:
    """An admission that would grant anything, so a refusal can only come from the phase itself."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def admit(self, *, role: str, generation: str, operation: str) -> dict:
        self.calls.append((role, generation, operation))
        return {
            "admitted": True,
            "reason": None,
            "role": role,
            "generation": generation,
            "operation": operation,
            "measurement_plan_sha256": PLAN_SHA,
            "safe_interval_rad": list(SAFE_INTERVAL),
        }


def _module():
    from so101_demo.act import head_search_calibration_inputs

    return head_search_calibration_inputs


def _sealed_files(tmp_path) -> dict:
    """Six real files under `tmp_path`, declared with the digests they actually have."""

    declared = {}
    for name, payload in CONTENTS.items():
        path = tmp_path / f"{name}.json"
        path.write_bytes(payload)
        declared[name] = {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest()}
    return declared


def _admission(*, generation: str = GENERATION):
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementAdmission

    return CalibrationMeasurementAdmission(
        generation=generation,
        status="CALIBRATION_REQUIRED",
        measurement_plan_sha256=PLAN_SHA,
        safe_interval_rad=SAFE_INTERVAL,
        controller_generation="ctrl-1",
        broker_generation=generation,
    )


def _run_phase(tmp_path, **overrides) -> dict:
    """Run the whole phase-1 entry over the sealed fixture; an override replaces one argument."""

    module = _module()
    arguments = {
        "sealed_inputs": _sealed_files(tmp_path),
        "admission": _admission(),
        "generation": GENERATION,
        "operation": "neck_target",
        "cpu_cores": 8,
        "gpu_device": 0,
    }
    arguments.update(overrides)
    return module.validate_head_search_calibration_inputs(**arguments)


def test_the_three_refusal_codes_are_exactly_the_planned_codes():
    module = _module()

    assert module.REFUSAL_CODES == (
        "CAL_INPUT_UNSEALED",
        "CAL_ADMISSION_REFUSED",
        "CAL_BINDING_REBOUND",
    )


def test_the_manifest_carries_every_sealed_input_and_its_digest(tmp_path):
    module = _module()
    declared = _sealed_files(tmp_path)

    manifest = module.validate_sealed_inputs(declared)

    assert module.SEALED_INPUT_NAMES == (
        "dataset_manifest",
        "model_manifest",
        "geometry_seal",
        "scenario_partitions",
        "production_config",
        "camera_config",
    )
    assert manifest["sealed"] is True
    assert set(manifest["inputs"]) == set(module.SEALED_INPUT_NAMES)
    for name, record in manifest["inputs"].items():
        assert record["path"] == declared[name]["path"]
        assert record["sha256"] == hashlib.sha256(CONTENTS[name]).hexdigest()
        assert record["size_bytes"] == len(CONTENTS[name])
    assert len(manifest["manifest_sha256"]) == 64
    # the same bytes digest to the same manifest, so two runs over one seal agree
    assert module.validate_sealed_inputs(declared)["manifest_sha256"] == manifest["manifest_sha256"]


def test_the_phase_grants_one_calibration_flight_and_binds_the_resources_once(tmp_path):
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementContext

    module = _module()
    admission = _admission()
    binder = module.CalibrationResourceBinder()

    document = _run_phase(tmp_path, admission=admission, binder=binder)

    assert document["schema_version"] == 1
    assert document["kind"] == "head_search_calibration_inputs"
    assert document["phase"] == "input_validation"
    assert document["manifest"]["sealed"] is True
    decision = document["admission"]
    assert decision["admitted"] is True
    assert decision["role"] == "calibration"
    assert decision["generation"] == GENERATION
    assert decision["operation"] == "neck_target"
    assert decision["measurement_plan_sha256"] == PLAN_SHA
    assert decision["safe_interval_rad"] == list(SAFE_INTERVAL)
    # one flight only: the admission that granted it refuses the next one
    assert admission.admit(
        role="calibration", generation=GENERATION, operation="neck_target"
    )["admitted"] is False
    binding = document["resource_binding"]
    assert binding["bound_at_entry"] is True
    assert binding["cpu_cores"] == 8
    assert binding["gpu_device"] == 0
    assert binding["generation"] == GENERATION
    assert binding["measurement_plan_sha256"] == PLAN_SHA
    assert binding["safe_interval_rad"] == list(SAFE_INTERVAL)
    assert binder.binding == binding
    # the record is the one the production measurement context requires at its entry
    assert set(CalibrationMeasurementContext.REQUIRED_BINDING_KEYS) <= set(binding)


def test_a_sealed_input_that_is_absent_is_refused(tmp_path):
    module = _module()
    declared = _sealed_files(tmp_path)
    (tmp_path / "geometry_seal.json").unlink()

    with pytest.raises(module.CalibrationInputsRefused) as raised:
        module.validate_sealed_inputs(declared)

    assert raised.value.code == "CAL_INPUT_UNSEALED"
    assert "geometry_seal" in str(raised.value)


def test_a_sealed_input_whose_digest_changed_is_refused(tmp_path):
    module = _module()
    declared = _sealed_files(tmp_path)
    (tmp_path / "dataset_manifest.json").write_bytes(CONTENTS["dataset_manifest"] + b"# rewritten\n")

    with pytest.raises(module.CalibrationInputsRefused) as raised:
        module.validate_sealed_inputs(declared)

    assert raised.value.code == "CAL_INPUT_UNSEALED"
    assert "dataset_manifest" in str(raised.value)


def test_a_seal_that_omits_a_controlled_dependency_is_refused(tmp_path):
    module = _module()
    declared = _sealed_files(tmp_path)
    declared.pop("scenario_partitions")

    with pytest.raises(module.CalibrationInputsRefused) as raised:
        module.validate_sealed_inputs(declared)

    assert raised.value.code == "CAL_INPUT_UNSEALED"
    assert "scenario_partitions" in str(raised.value)


def test_a_role_other_than_calibration_is_refused(tmp_path):
    module = _module()
    permissive = _PermissiveAdmission()

    with pytest.raises(module.CalibrationInputsRefused) as raised:
        _run_phase(tmp_path, admission=permissive, role="act")

    assert raised.value.code == "CAL_ADMISSION_REFUSED"
    # the refusal is the phase's own: an admission willing to grant the production role is never asked
    assert permissive.calls == []


@pytest.mark.parametrize("operation", ["release", "recorder"])
def test_a_release_or_recorder_request_is_refused_unconditionally(tmp_path, operation):
    module = _module()
    permissive = _PermissiveAdmission()

    with pytest.raises(module.CalibrationInputsRefused) as raised:
        _run_phase(tmp_path, admission=permissive, operation=operation)

    assert raised.value.code == "CAL_ADMISSION_REFUSED"
    assert permissive.calls == []
    # unconditional means independent of role and of the admission's own state
    with pytest.raises(module.CalibrationInputsRefused) as raised_again:
        _run_phase(tmp_path, admission=permissive, operation=operation, role="act")

    assert raised_again.value.code == "CAL_ADMISSION_REFUSED"
    assert permissive.calls == []


@pytest.mark.parametrize("operation", ["release", "recorder"])
def test_the_real_admission_cannot_smuggle_a_release_or_recorder(tmp_path, operation):
    module = _module()

    with pytest.raises(module.CalibrationInputsRefused) as raised:
        _run_phase(tmp_path, operation=operation)

    assert raised.value.code == "CAL_ADMISSION_REFUSED"


def test_a_foreign_generation_is_refused(tmp_path):
    module = _module()

    with pytest.raises(module.CalibrationInputsRefused) as raised:
        _run_phase(tmp_path, generation="g2")

    assert raised.value.code == "CAL_ADMISSION_REFUSED"


def test_a_second_binding_in_the_same_run_is_refused(tmp_path):
    module = _module()
    binder = module.CalibrationResourceBinder()

    first = binder.bind(
        generation=GENERATION,
        measurement_plan_sha256=PLAN_SHA,
        safe_interval_rad=SAFE_INTERVAL,
        cpu_cores=8,
        gpu_device=0,
    )
    assert binder.binding == first

    with pytest.raises(module.CalibrationInputsRefused) as raised:
        binder.bind(
            generation=GENERATION,
            measurement_plan_sha256=PLAN_SHA,
            safe_interval_rad=SAFE_INTERVAL,
            cpu_cores=4,
            gpu_device=1,
        )

    assert raised.value.code == "CAL_BINDING_REBOUND"
    assert binder.binding == first


def test_a_second_phase_entry_over_the_same_run_is_refused(tmp_path):
    module = _module()
    binder = module.CalibrationResourceBinder()
    first = _run_phase(tmp_path, binder=binder)

    with pytest.raises(module.CalibrationInputsRefused) as raised:
        _run_phase(tmp_path, binder=binder, cpu_cores=1)

    assert raised.value.code == "CAL_BINDING_REBOUND"
    assert binder.binding == first["resource_binding"]


def test_a_refused_input_validation_binds_nothing(tmp_path):
    module = _module()
    declared = _sealed_files(tmp_path)
    declared["camera_config"]["sha256"] = "b" * 64
    binder = module.CalibrationResourceBinder()

    with pytest.raises(module.CalibrationInputsRefused) as raised:
        module.validate_head_search_calibration_inputs(
            sealed_inputs=declared,
            admission=_admission(),
            generation=GENERATION,
            operation="neck_target",
            cpu_cores=8,
            gpu_device=0,
            binder=binder,
        )

    assert raised.value.code == "CAL_INPUT_UNSEALED"
    assert binder.binding is None


def test_validation_writes_nothing_outside_an_explicit_output_path(tmp_path):
    module = _module()
    declared = _sealed_files(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())

    module.validate_sealed_inputs(declared)
    _run_phase(tmp_path)

    assert sorted(path.name for path in tmp_path.iterdir()) == before
    output = tmp_path / "phase-1" / "head-search-calibration-inputs.json"
    document = _run_phase(tmp_path, output_path=output)
    assert json.loads(output.read_text(encoding="utf-8")) == document
    assert sorted(path.name for path in output.parent.iterdir()) == [output.name]
