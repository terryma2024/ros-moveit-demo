"""Teacher execution policy v3 on the data side (design 2026-10-10 sections 5 and 8): the manifest validator's v3 branch, the e2e
acceptance, the QC reference check, the result store and the processor metadata. v1/v2 stay covered by their untouched tests."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.core import place_height as ph
from so101_demo.core.domain import State
from so101_demo.core.process_summary import ProcessSummary
from so101_demo.core.workflow import TEACHER_WORKFLOW
from test_dynamic_manifest_semantics import (
    DONE_TRACE, MOTION_STATES, TRUSTED_FINAL, event, manifest, sample, teacher_fields, teacher_result)
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT
SCHEMA_TEACHER = "so101-teacher-execute"
FROZEN = load_teacher_execution_policy(PACKAGE / "config/act/teacher_execution_policy.yaml")
POLICY = ph.PlaceHeightPolicy.from_document(FROZEN)


def place_record(*, fallback=None):
    geometry = ph.cup_geometry_from_scene(PACKAGE / "assets/mujoco/act/scene.xml")
    old = 0.2176344 - 0.01325
    if fallback is not None:
        return ph.fallback_record(fallback, old, POLICY, geometry=geometry, theta=0.0705, k=POLICY.grasp_offset_m, detail="x")
    return ph.plan_place_height(0.0705, POLICY.grasp_offset_m, old, geometry, POLICY)


def summary_document(*, flags=False, incomplete=False):
    value = ProcessSummary()
    value.limits = type("L", (), {"maximum_safe_force_n": 3.0, "maximum_compression_distance_m": 1e-4})()
    value.phase_begin("LIFT", 1.0)
    if flags:
        value.offer_step(1, 1.5, 9.0, 1e-5)
    value.phase_finish("LIFT", 2.0, "SUCCEEDED")
    if incomplete:
        value.note_incomplete("PHYSICS_GAP")
    return value.build(policy=FROZEN, place_height=place_record())


def teacher_done(**summary_options):
    document = manifest()
    document.update(schema=SCHEMA_TEACHER, schema_version=1, place_height=place_record(), failure_class=None,
                    teacher_process_summary=summary_document(**summary_options))
    return document


def validate(document, status="DONE", *, frozen=FROZEN, trusted=None):
    from so101_demo.parallel_batch.dynamic_manifest import validate_dynamic_manifest_semantics
    return validate_dynamic_manifest_semantics(
        document, expected_status=status, expected_reset_epoch=17, expected_final_cup_pose_world=trusted, frozen_execution_policy=frozen)


def teacher_error(state: str, *, failure="MOVEIT_EXECUTION_FAILED: x", attached=False, execution="FAILED", failure_class=None):
    """An attempt that failed in `state`: v3 goes straight to ERROR from there, no RECOVER_* state."""
    forward = list(TEACHER_WORKFLOW.forward_states)
    trace = [item.value for item in forward[:forward.index(State(state)) + 1]] + ["ERROR"]
    done = [item for item in trace[:-1] if State(item) in TEACHER_WORKFLOW.action_states]
    done = done[:-1] if done and done[-1] == state else done
    events = [event(item, 100 + index * 2) for index, item in enumerate(done)]
    scene = ({"attached_object_ids": ["plastic_cup"], "world_primitive_counts": {"table": 1}} if attached
             else {"attached_object_ids": [], "world_primitive_counts": {"plastic_cup": 13}})
    document = {
        **teacher_fields(execution, teacher_result("UNCONFIRMED", ["END_OBSERVATION_UNCONFIRMED: x"], end=False)),
        "schema": SCHEMA_TEACHER, "schema_version": 1, "status": "ERROR", "current_state": "ERROR", "failure": failure, "state_trace": trace,
        "transition_count": len(trace) - 1, "state_events": events,
        "planning_attempts": [{"kind": "moveit_joint_plan", "state": item, "accepted": True} for item in done if item in MOTION_STATES],
        "final_samples": [], "planning_scene_readback": scene, "release_marker_sequence": 900 if "OPEN_GRIPPER" in done else None,
        "failure_class": failure_class, "teacher_process_summary": summary_document(),
        "failure_evidence": {"failure_boundary_state": state, "physical_action_proven_absent": False,
                             "terminal_sample": sample(1000), "planning_scene_readback": scene, "capture_errors": []},
    }
    return document


# ---- a finished run ---------------------------------------------------------------------------------------------------------

def test_a_complete_teacher_done_manifest_is_accepted_with_and_without_the_frozen_policy():
    validate(teacher_done())
    validate(teacher_done(), frozen=None)


def test_a_frozen_teacher_policy_requires_the_teacher_manifest():
    with pytest.raises(ValueError, match="DYNAMIC_MANIFEST_SCHEMA"):
        validate({**manifest()}, frozen=FROZEN)               # a general manifest under a Teacher freeze


@pytest.mark.parametrize("fallback", ph.FALLBACK_REASONS)
def test_a_fallback_place_record_is_accepted_when_its_reason_is_supported_by_the_record(fallback):
    document = teacher_done()
    geometry = ph.cup_geometry_from_scene(PACKAGE / "assets/mujoco/act/scene.xml")
    old = 0.2176344 - 0.01325
    cases = {
        ph.FB_TILT_UNSTABLE: dict(theta=None, k=None), ph.FB_JOINT_STATE_STALE: dict(theta=None, k=None),
        ph.FB_MEASUREMENT_FAILED: dict(theta=None, k=None),
        ph.FB_TILT_OUT_OF_RANGE: dict(theta=0.2, k=POLICY.grasp_offset_m),
        ph.FB_K_OUT_OF_BAND: dict(theta=0.0705, k=POLICY.grasp_offset_m + 0.002),
        ph.FB_TARGET_DEVIATION: dict(theta=0.0705, k=POLICY.grasp_offset_m, computed=old + 0.005),
        ph.FB_SCENE_HASH_MISMATCH: dict(theta=0.0705, k=POLICY.grasp_offset_m)}[fallback]
    record = ph.fallback_record(fallback, old, POLICY, geometry=geometry, detail="x", **cases)
    if fallback == ph.FB_SCENE_HASH_MISMATCH:
        record["scene_sha256"] = "0" * 64
    document["place_height"] = record
    document["teacher_process_summary"] = ProcessSummary().build(policy=FROZEN, place_height=record)
    document["teacher_process_summary"]["complete"] = False
    document["teacher_process_summary"]["incomplete_reasons"] = ["THRESHOLDS_UNAVAILABLE"]
    validate(document)


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d.pop("place_height"), "PLACE_HEIGHT"),
    (lambda d: d.update(place_height={**d["place_height"], "target_tcp_z_m": 0.3}), "PLACE_HEIGHT"),
    (lambda d: d.update(place_height={**d["place_height"], "schema": "teacher_place_height_v2"}), "PLACE_HEIGHT"),
    (lambda d: d.pop("teacher_process_summary"), "PROCESS_SUMMARY"),
    (lambda d: d["teacher_process_summary"].update(complete=False), "PROCESS_SUMMARY"),
    (lambda d: d["teacher_process_summary"]["policy"].update(verdict_source="broker"), "PROCESS_SUMMARY"),
    (lambda d: d["teacher_process_summary"]["policy"].update(cup_pose_source="sim_truth"), "PROCESS_SUMMARY"),
    (lambda d: d["teacher_process_summary"].update(place_height_mode="fallback_reference"), "PROCESS_SUMMARY"),
    (lambda d: d.update(failure_class="sim_integrity"), "FAILURE_CLASS"),
    (lambda d: d.pop("failure_class"), "FAILURE_CLASS"),
])
def test_a_teacher_done_manifest_missing_or_contradicting_its_records_is_rejected(mutate, code):
    document = teacher_done()
    mutate(document)
    with pytest.raises(ValueError, match=code):
        validate(document)


def test_a_teacher_trace_with_a_recovery_state_is_rejected():
    document = teacher_done()
    trace = list(DONE_TRACE)
    trace[trace.index("LIFT"):trace.index("LIFT") + 1] = ["LIFT", "RECOVER_LIFT_TO_SAFE_HEIGHT"]
    document.update(state_trace=trace, transition_count=len(trace) - 1)
    with pytest.raises(ValueError, match="DYNAMIC_MANIFEST_TRACE"):
        validate(document)


def test_a_general_manifest_keeps_its_recovery_states_and_does_not_need_teacher_records():
    validate(manifest(), frozen=None)


# ---- an attempt that failed: ERROR from any state, attached or detached ---------------------------------------------------

@pytest.mark.parametrize("state", [item.value for item in TEACHER_WORKFLOW.forward_states
                                   if item not in (State.IDLE, State.DONE, State.ERROR)])
@pytest.mark.parametrize("attached", [False, True])
def test_a_teacher_failure_in_any_state_ends_in_error_without_recovery_and_validates(state, attached):
    document = teacher_error(state, attached=attached)
    validate(document, "ERROR")
    assert not any(item.startswith("RECOVER_") for item in document["state_trace"])


def test_the_same_failure_in_a_general_manifest_needs_the_recovery_chain():
    document = teacher_error("LIFT")
    document["schema"] = "so101-dynamic-execute"
    with pytest.raises(ValueError):
        validate(document, "ERROR", frozen=None)


def test_a_simulation_integrity_failure_is_failed_with_its_class_and_may_have_no_terminal_evidence():
    document = teacher_error("LIFT", failure="SIM_INTEGRITY_EVIDENCE_UNAVAILABLE: x", failure_class="sim_integrity")
    document["failure_evidence"].update(terminal_sample=None, planning_scene_readback=None, capture_errors=["PHYSICAL:DYNAMIC_EVIDENCE_TIMEOUT"])
    validate(document, "ERROR")
    other = teacher_error("LIFT")
    other["failure_evidence"]["capture_errors"] = ["PHYSICAL:X"]
    with pytest.raises(ValueError, match="FAILURE_EVIDENCE"):
        validate(other, "ERROR")
    wrong_class = teacher_error("LIFT", failure="SIM_INTEGRITY_EVIDENCE_UNAVAILABLE: x", failure_class=None)
    with pytest.raises(ValueError, match="FAILURE_CLASS"):
        validate(wrong_class, "ERROR")
    wrong_status = teacher_error("LIFT", failure="SIM_INTEGRITY_EVIDENCE_UNAVAILABLE: x", failure_class="sim_integrity", execution="STOPPED_SAFETY")
    with pytest.raises(ValueError, match="FAILURE_CLASS"):
        validate(wrong_status, "ERROR")


def test_the_release_marker_still_orders_the_failure_evidence():
    document = teacher_error("RETREAT")
    document["release_marker_sequence"] = 5000
    with pytest.raises(ValueError, match="RELEASE_ORDER"):
        validate(document, "ERROR")


# ---- e2e acceptance, QC references, result store, processor metadata -----------------------------------------------------------

def test_e2e_acceptance_reads_the_schema_and_requires_a_coherent_summary():
    from so101_demo.application import e2e_acceptance as e2e
    perception = {"source_stamp_ns": 1, "source_frame_id": "world", "status": "OK", "failure": None, "published_cup_pose": True}
    dynamic = teacher_done()
    dynamic.update(input_source_stamp_ns=1, input_frame_id="world")
    failures: list[str] = []
    assert e2e._validate_dynamic_contract(dynamic, perception, failures) and failures == []
    assert e2e.SCHEMA_TEACHER == SCHEMA_TEACHER
    report_failures: list[str] = []
    assert e2e._validate_teacher_result(dynamic, report_failures) == "PASS" and report_failures == []
    assert e2e._process_summary_valid(dynamic["teacher_process_summary"]) is True
    assert e2e._process_summary_valid({**dynamic["teacher_process_summary"], "complete": False}) is False
    assert e2e._process_summary_valid(None) is False


def test_the_qc_reference_check_accepts_the_teacher_manifest_schema():
    from so101_demo.act.episode_qc import verify_teacher_references
    document = teacher_done()
    result = verify_teacher_references(document, identity={"session_id": "s", "reset_epoch": 17}, window={}, physics_steps=[])
    assert result["reason"] != "TEACHER_REFERENCE_MANIFEST_MISSING"
    document["schema"] = "so101-dynamic-mujoco-execute-v4"
    assert verify_teacher_references(document, identity={}, window={}, physics_steps=[])["reason"] == "TEACHER_REFERENCE_MANIFEST_MISSING"


def test_the_result_store_accepts_a_teacher_manifest_for_the_claim(tmp_path):
    from so101_demo.act import result_store
    path = tmp_path / "dynamic-execute-manifest.json"
    document = teacher_done()
    document["act_data_status"] = "DISABLED"
    path.write_text(json.dumps(document))
    claim = {"execution_status": "COMPLETED", "task_result": "PASS"}
    result_store._check_teacher_manifest(path, claim)
    document["schema"] = "so101-dynamic-mujoco-execute-v9"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="RESULT_TEACHER_MANIFEST_MISMATCH"):
        result_store._check_teacher_manifest(path, claim)


def test_the_processor_metadata_copies_the_summary_policy_and_provenance(tmp_path):
    from so101_demo.act import teacher_process
    manifest_path = tmp_path / "dynamic-execute-manifest.json"
    document = teacher_done()
    manifest_path.write_text(json.dumps(document))
    metadata = teacher_process.write_metadata(manifest_path, tmp_path)
    stored = json.loads((tmp_path / teacher_process.METADATA_FILE).read_text())
    assert stored == json.loads(json.dumps(metadata))
    assert stored["teacher_execution_policy_version"] == 3 and stored["cup_pose_source"] == "broker_rgbd"
    assert stored["verdict_source"] == "sim_truth" and stored["teacher_process_summary_schema"] == "teacher_process_summary"
    assert stored["teacher_manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert stored["teacher_process_summary"] == document["teacher_process_summary"]
    assert teacher_process.write_metadata(manifest_path, tmp_path) == metadata          # idempotent
    (tmp_path / teacher_process.METADATA_FILE).write_text("{}")
    with pytest.raises(ValueError, match="differs"):
        teacher_process.write_metadata(manifest_path, tmp_path)


def test_a_general_manifest_has_no_process_metadata_and_a_broken_teacher_summary_is_refused(tmp_path):
    from so101_demo.act import teacher_process
    old = tmp_path / "old.json"
    old.write_text(json.dumps(manifest()))
    assert teacher_process.write_metadata(old, tmp_path) is None and not (tmp_path / teacher_process.METADATA_FILE).exists()
    broken = tmp_path / "broken.json"
    document = teacher_done()
    document["teacher_process_summary"]["complete"] = False
    broken.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="PROCESS_SUMMARY"):
        teacher_process.write_metadata(broken, tmp_path)


def test_the_processor_writes_the_metadata_only_for_a_valid_teacher_episode():
    import inspect
    from so101_demo.act.offline import processor
    source = inspect.getsource(processor.process_bag)
    assert "write_metadata(teacher, out)" in source and source.index("write_metadata") > source.index('report["qc"] = qc')
