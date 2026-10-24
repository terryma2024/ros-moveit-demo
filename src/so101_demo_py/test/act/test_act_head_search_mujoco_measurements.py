"""The MuJoCo measurement document phase 7 consumes: the sealed scene's simulation timestep.

Every fixture here is synthetic: no ROS, no MuJoCo, no detector, no GPU, no motion, no CUDA. The
fixtures write small MuJoCo scene files into `tmp_path` and exercise the reader, the identity
cross-checks against the sealed geometry/dataset/contract documents, the self-digest of the produced
document and the producer that writes it.

What these tests pin:

* the timestep is read from the scene's own `<option timestep="...">` declaration, following an
  `<include file="...">` when the including file declares none;
* a scene that declares no timestep, or two differing declarations across the file and its includes, is
  refused with `CAL_MUJOCO_EVIDENCE_MISSING` / `CAL_MUJOCO_EVIDENCE_CONTRADICTORY` rather than resolved;
* the scene bytes must match the digest the declared sealed identity records, or the document would be
  an anonymous XML reading;
* the produced document carries `path` + a self-digest over its body (the convention the run's other
  measurement documents use), `simulation_timestep_s` in seconds, and says explicitly that it was not
  measured here and that it commanded no motion;
* the producer writes exactly the document and the receipt into a brand-new directory, and refuses an
  existing one.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search.mujoco_measurements import (
    CAL_MUJOCO_EVIDENCE_CONTRADICTORY,
    CAL_MUJOCO_EVIDENCE_MISSING,
    DIGEST_CONVENTION,
    FIELD,
    KIND,
    PHASE,
    REFUSAL_CODES,
    CalibrationMujocoMeasurementsRefused,
    read_mujoco_timestep,
    validate_head_search_mujoco_measurements,
    write_mujoco_measurements,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCENE = """<mujoco model="fixture">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody><body name="table"/></worldbody>
</mujoco>
"""

SCENE_WITH_INCLUDE = """<mujoco model="fixture">
  <include file="robot.xml"/>
  <worldbody><body name="table"/></worldbody>
</mujoco>
"""

ROBOT = """<mujoco model="robot">
  <option timestep="0.001"/>
  <worldbody><body name="arm"/></worldbody>
</mujoco>
"""


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scene(tmp_path, text: str = SCENE, name: str = "scene.xml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _seal(tmp_path, scene_path, *, key="source_digests", digest=None):
    document = {
        "schema_version": 1,
        key: {"scene_sha256": _digest(scene_path) if digest is None else digest},
    }
    path = tmp_path / "head-camera-geometry.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _manifest(tmp_path, scene_path, *, digest=None):
    document = {"mjcf_sha256": _digest(scene_path) if digest is None else digest}
    path = tmp_path / "dataset-manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _contract(tmp_path, scene_path, *, digest=None):
    document = {"accepted_scene_sha256": _digest(scene_path) if digest is None else digest}
    path = tmp_path / "head-camera-geometry-contract.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# --- the reader -----------------------------------------------------------------------------------


def test_the_scene_declaration_is_read_as_the_simulation_timestep(tmp_path):
    scene = _scene(tmp_path)

    declaration = read_mujoco_timestep(scene)

    assert declaration[FIELD] == pytest.approx(0.002)
    assert declaration["scene_path"] == str(scene)
    assert declaration["scene_sha256"] == _digest(scene)
    assert declaration["declaration_file"] == str(scene)
    assert declaration["declaration_sha256"] == _digest(scene)
    assert declaration["attribute"] == "0.002"


def test_an_include_is_followed_when_the_including_file_declares_none(tmp_path):
    _scene(tmp_path, ROBOT, name="robot.xml")
    scene = _scene(tmp_path, SCENE_WITH_INCLUDE)

    declaration = read_mujoco_timestep(scene)

    assert declaration[FIELD] == pytest.approx(0.001)
    assert declaration["scene_path"] == str(scene)
    assert declaration["scene_sha256"] == _digest(scene)
    assert declaration["declaration_file"] == str(tmp_path / "robot.xml")


def test_a_scene_without_a_declaration_is_refused(tmp_path):
    scene = _scene(tmp_path, "<mujoco model=\"fixture\"><worldbody/></mujoco>\n")

    with pytest.raises(CalibrationMujocoMeasurementsRefused) as refused:
        read_mujoco_timestep(scene)

    assert refused.value.code == CAL_MUJOCO_EVIDENCE_MISSING
    assert isinstance(refused.value, CalibrationInputsRefused)


def test_two_differing_declarations_are_refused_rather_than_resolved(tmp_path):
    _scene(tmp_path, ROBOT, name="robot.xml")
    scene = _scene(
        tmp_path,
        SCENE_WITH_INCLUDE.replace(
            '<worldbody>', '<option timestep="0.002"/><worldbody>', 1
        ),
    )

    with pytest.raises(CalibrationMujocoMeasurementsRefused) as refused:
        read_mujoco_timestep(scene)

    assert refused.value.code == CAL_MUJOCO_EVIDENCE_CONTRADICTORY


def test_an_absent_scene_is_refused(tmp_path):
    with pytest.raises(CalibrationMujocoMeasurementsRefused) as refused:
        read_mujoco_timestep(tmp_path / "absent.xml")

    assert refused.value.code == CAL_MUJOCO_EVIDENCE_MISSING


def test_a_non_positive_declaration_is_refused(tmp_path):
    scene = _scene(tmp_path, SCENE.replace('timestep="0.002"', 'timestep="0.0"'))

    with pytest.raises(CalibrationMujocoMeasurementsRefused) as refused:
        read_mujoco_timestep(scene)

    assert refused.value.code == CAL_MUJOCO_EVIDENCE_MISSING


# --- the document ---------------------------------------------------------------------------------


def _document(tmp_path, **overrides):
    scene = overrides.pop("scene", None) or _scene(tmp_path)
    seal = overrides.pop("seal", None)
    if seal is None:
        seal = _seal(tmp_path, scene)
    return validate_head_search_mujoco_measurements(
        scene_path=scene,
        geometry_seal_path=seal,
        document_path=tmp_path / "mujoco-measurements.json",
        **overrides,
    )


def test_the_document_carries_the_value_the_run_reads(tmp_path):
    document = _document(tmp_path)

    assert document["kind"] == KIND
    assert document["phase"] == PHASE
    assert document["schema_version"] == 1
    assert document[FIELD] == pytest.approx(0.002)
    assert document["unit"] == "s"
    assert document["measured_here"] is False
    assert document["motion_commanded"] is False
    assert document["ros_nodes_started"] is False
    assert document["path"].endswith("mujoco-measurements.json")


def test_the_document_digest_covers_its_own_body(tmp_path):
    document = _document(tmp_path)

    body = {key: value for key, value in document.items() if key != "sha256"}
    assert document["sha256"] == canonical_sha256(body)
    assert DIGEST_CONVENTION in document["digest_convention"]


def test_the_sealed_identities_are_recorded_and_must_agree(tmp_path):
    scene = _scene(tmp_path)
    seal = _seal(tmp_path, scene, key="source_digests")
    manifest = _manifest(tmp_path, scene)
    contract = _contract(tmp_path, scene)

    document = validate_head_search_mujoco_measurements(
        scene_path=scene,
        geometry_seal_path=seal,
        dataset_manifest_path=manifest,
        geometry_contract_path=contract,
        document_path=tmp_path / "mujoco-measurements.json",
    )

    names = {identity["name"] for identity in document["sealed_identities"]}
    assert names == {"geometry_seal", "dataset_manifest", "geometry_contract"}
    assert all(identity["agrees"] is True for identity in document["sealed_identities"])
    assert document["scene_sha256"] == _digest(scene)


def test_an_identity_that_disagrees_with_the_scene_bytes_is_refused(tmp_path):
    scene = _scene(tmp_path)
    seal = _seal(tmp_path, scene, digest="f" * 64)

    with pytest.raises(CalibrationMujocoMeasurementsRefused) as refused:
        validate_head_search_mujoco_measurements(
            scene_path=scene, geometry_seal_path=seal, document_path=tmp_path / "out.json"
        )

    assert refused.value.code == CAL_MUJOCO_EVIDENCE_CONTRADICTORY


def test_an_identity_document_without_a_scene_digest_is_refused(tmp_path):
    scene = _scene(tmp_path)
    path = tmp_path / "seal.json"
    path.write_text(json.dumps({"source_digests": {}}), encoding="utf-8")

    with pytest.raises(CalibrationMujocoMeasurementsRefused) as refused:
        validate_head_search_mujoco_measurements(
            scene_path=scene, geometry_seal_path=path, document_path=tmp_path / "out.json"
        )

    assert refused.value.code == CAL_MUJOCO_EVIDENCE_MISSING


def test_a_document_without_any_sealed_identity_is_refused(tmp_path):
    scene = _scene(tmp_path)

    with pytest.raises(CalibrationMujocoMeasurementsRefused) as refused:
        validate_head_search_mujoco_measurements(
            scene_path=scene, document_path=tmp_path / "out.json"
        )

    assert refused.value.code == CAL_MUJOCO_EVIDENCE_MISSING


def test_the_field_is_the_one_phase_seven_reads():
    assert FIELD == "simulation_timestep_s"
    assert set(REFUSAL_CODES) == {CAL_MUJOCO_EVIDENCE_MISSING, CAL_MUJOCO_EVIDENCE_CONTRADICTORY}


# --- the producer ---------------------------------------------------------------------------------


def test_the_producer_writes_the_document_and_the_receipt(tmp_path):
    scene = _scene(tmp_path)
    seal = _seal(tmp_path, scene)
    output = tmp_path / "run"

    result = write_mujoco_measurements(
        scene_path=scene,
        geometry_seal_path=seal,
        output_dir=output,
        command="ros2 run so101_demo_py so101_head_search_calibration measure-mujoco",
    )

    written = sorted(path.name for path in output.iterdir())
    assert written == ["measurement-receipt.json", "mujoco-measurements.json"]
    document = json.loads((output / "mujoco-measurements.json").read_text(encoding="utf-8"))
    assert document[FIELD] == pytest.approx(0.002)
    assert document["path"] == str(output / "mujoco-measurements.json")
    assert document["mujoco_readback"] is False
    assert document["mujoco_model_timestep_s"] is None
    assert result["receipt"]["status"] == "SUCCEEDED"
    assert result["receipt"]["simulation_timestep_s"] == pytest.approx(0.002)
    assert result["receipt"]["measurement_path"] == document["path"]
    assert result["receipt"]["measurement_sha256"] == document["sha256"]
    assert result["receipt"]["runtime_identity"]["ros_nodes_started"] is False
    assert result["receipt"]["runtime_identity"]["detector_loaded"] is False


def test_the_producer_refuses_an_existing_output_directory(tmp_path):
    scene = _scene(tmp_path)
    seal = _seal(tmp_path, scene)
    output = tmp_path / "run"
    output.mkdir()

    with pytest.raises(FileExistsError):
        write_mujoco_measurements(scene_path=scene, geometry_seal_path=seal, output_dir=output)


def test_the_producer_records_a_mujoco_readback_only_when_it_took_one(tmp_path, monkeypatch):
    scene = _scene(tmp_path)
    seal = _seal(tmp_path, scene)
    output = tmp_path / "run"

    result = write_mujoco_measurements(
        scene_path=scene, geometry_seal_path=seal, output_dir=output, mujoco_readback=True
    )

    document = result["measurement"]
    assert document["mujoco_readback"] is True
    assert document["mujoco_model_timestep_s"] == pytest.approx(0.002)


def test_a_readback_that_disagrees_with_the_declaration_is_refused(tmp_path, monkeypatch):
    scene = _scene(tmp_path)
    seal = _seal(tmp_path, scene)
    output = tmp_path / "run"

    import so101_demo.act.head_search.mujoco_measurements as module

    monkeypatch.setattr(module, "mujoco_model_timestep_s", lambda path: 0.004)
    with pytest.raises(CalibrationMujocoMeasurementsRefused) as refused:
        write_mujoco_measurements(
            scene_path=scene, geometry_seal_path=seal, output_dir=output, mujoco_readback=True
        )

    assert refused.value.code == CAL_MUJOCO_EVIDENCE_CONTRADICTORY


def test_the_document_is_the_one_phase_seven_reads(tmp_path):
    """The produced document is fed to the consumer itself: phase 7 adds one timestep to the lead."""

    from so101_demo.act.head_search.timing_params import compute_submit_lead_s

    document = _document(tmp_path)
    submissions = {
        "path": "controller-submissions.json",
        "sha256": "a" * 64,
        "samples": [
            {
                "time_base": "simulation",
                "submit_snapshot_sim_s": 1.0,
                "first_target_sim_s": 1.0,
            }
        ],
    }

    block = compute_submit_lead_s(submissions=submissions, mujoco=document)

    assert block["value"] == pytest.approx(0.002)
    assert {"path": document["path"], "sha256": document["sha256"]} in block["input_evidence"]
