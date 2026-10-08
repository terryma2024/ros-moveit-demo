"""Durable QC report publication only; controlled documents grant no runtime authority."""

import copy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from so101_demo.act import episode_qc
from so101_demo.act.endpoint_pose_acceptance import THRESHOLD_UNITS
from test_act_seal_and_downgrade import IDENTITY, lease


TEACHER_REFERENCE = {
    "status": "PASS", "reason": "",
    "details": {"teacher_manifest_sha256": "f" * 64,
        "start_reference": {"session_id": "session-1", "reset_epoch": 2, "simulation_step": 1200,
                            "simulation_time_s": 1.2, "publisher_sequence": 1200},
        "end_reference": {"session_id": "session-1", "reset_epoch": 2, "simulation_step": 8500,
                          "simulation_time_s": 8.5, "publisher_sequence": 8500},
        "recorded_physics": {"first_step": 1000, "last_step": 9000}}}


def report():
    """A current (schema 3) data QC report: data integrity only, no task success and no endpoint_pose_v1."""
    return {"kind": "ACT_EPISODE_QC", "schema_version": 3, "status": "PASS",
        "rule_version": "act_data_qc_v4", "identity": {**IDENTITY, "lease": asdict(lease())},
        "episode_seal_sha256": "a" * 64, "audit_manifest_sha256": "b" * 64,
        "inputs_sha256": "c" * 64, "scope_sha256": "d" * 64,
        "counts": {"records": 2, "head_acquisitions": 4, "wrist_acquisitions": 4,
                   "references": 4, "events": 1, "physics": 2, "native_steps": 51},
        "checks": {"episode_data": {"status": "PASS", "reason": ""},
                   "teacher_reference_consistency": copy.deepcopy(TEACHER_REFERENCE),
                   "topic_loss_gate": {"status": "PASS", "reason": "", "document_sha256": "f" * 64,
                                       "rule_version": "topic_loss_v2", "lost_in_window": 0}}, "reason": ""}


def fail_teacher_reference(document, code="TEACHER_REFERENCE_END_AFTER_RECORDING"):
    """The one way a current report fails: the recording is inconsistent with the Teacher's references."""
    document["status"], document["reason"] = "FAIL", code
    document["checks"]["teacher_reference_consistency"]["status"] = "FAIL"
    document["checks"]["teacher_reference_consistency"]["reason"] = code
    return document


def legacy_v2_report():
    """A schema 2 report as the endpoint_pose_v1 era wrote it. Legacy results are read for audit only."""
    pose = [0., 0., 0., 0., 0., 0., 1.]
    return {"kind": "ACT_EPISODE_QC", "schema_version": 2, "status": "PASS",
        "rule_version": "endpoint_pose_v1", "identity": {**IDENTITY, "lease": asdict(lease())},
        "episode_seal_sha256": "a" * 64, "audit_manifest_sha256": "b" * 64,
        "inputs_sha256": "c" * 64, "scope_sha256": "d" * 64,
        "counts": {"records": 2, "head_acquisitions": 4, "wrist_acquisitions": 4,
                   "references": 4, "events": 1, "physics": 2, "native_steps": 51},
        "checks": {"episode_data": {"status": "PASS", "reason": ""},
                   "execution_safety": {"status": "PASS", "reason": ""},
                   "endpoint_pose": {"status": "PASS", "policy_sha256": "e" * 64,
                       "initial_sequence": 1, "final_sequence": 2, "initial_pose": pose,
                       "final_pose": pose[:], "initial_target": pose[:], "final_target": pose[:],
                       "errors": {name: 0. for name in THRESHOLD_UNITS},
                       "passed": {name: True for name in THRESHOLD_UNITS}}}, "reason": ""}


def writer():
    value = getattr(episode_qc, "write_qc_report", None)
    assert callable(value), "QC v2 atomic publication boundary is absent"
    return value


def test_report_publish_readback_is_exact_and_cannot_overwrite(tmp_path):
    document = report()
    target = tmp_path / "qc-report.json"
    original = copy.deepcopy(document)
    digest = writer()(document, target)
    payload = target.read_bytes()
    assert document == original
    assert digest == hashlib.sha256(payload).hexdigest()
    assert json.loads(payload) == original
    assert episode_qc.read_qc_report(target) == original
    assert payload == (json.dumps(original, sort_keys=True, separators=(",", ":"),
                                  allow_nan=False) + "\n").encode()
    with pytest.raises(ValueError, match="QC_REPORT_ALREADY_WRITTEN"):
        writer()(document, target)
    assert target.read_bytes() == payload


@pytest.mark.parametrize("change", ["unknown", "version", "rule", "boolean_count", "bad_digest",
    "missing_lease", "unknown_check", "missing_reference_check", "legacy_safety_check", "legacy_endpoint_check",
    "pass_with_failed_reference", "fail_without_reason", "bad_reference_code", "bad_manifest_digest",
    "bad_step", "failed_check", "pass_with_reason"])
def test_closed_report_refuses_inconsistent_pass_before_creating_files(tmp_path, change):
    document = report()
    check = document["checks"]["teacher_reference_consistency"]
    if change == "unknown":
        document["committed"] = True
    elif change == "version":
        document["schema_version"] = True
    elif change == "rule":
        document["rule_version"] = "unknown"
    elif change == "boolean_count":
        document["counts"]["records"] = True
    elif change == "bad_digest":
        document["scope_sha256"] = "no"
    elif change == "missing_lease":
        del document["identity"]["lease"]
    elif change == "unknown_check":
        document["checks"]["worker_pass"] = {"status": "PASS", "reason": ""}
    elif change == "missing_reference_check":
        del document["checks"]["teacher_reference_consistency"]
    elif change == "legacy_safety_check":
        # task success is no longer a QC criterion: the old execution_safety entry may not come back
        document["checks"]["execution_safety"] = {"status": "PASS", "reason": ""}
    elif change == "legacy_endpoint_check":
        document["checks"]["endpoint_pose"] = legacy_v2_report()["checks"]["endpoint_pose"]
    elif change == "pass_with_failed_reference":
        check["status"], check["reason"] = "FAIL", "TEACHER_REFERENCE_END_AFTER_RECORDING"
    elif change == "fail_without_reason":
        document["status"] = "FAIL"
        check["status"] = "FAIL"
    elif change == "bad_reference_code":
        fail_teacher_reference(document, "SOMETHING_ELSE")
    elif change == "bad_manifest_digest":
        check["details"]["teacher_manifest_sha256"] = "no"
    elif change == "bad_step":
        check["details"]["end_reference"]["simulation_step"] = True
    elif change == "failed_check":
        document["checks"]["episode_data"] = {"status": "FAIL", "reason": "missing data"}
    elif change == "pass_with_reason":
        document["reason"] = "stale"
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        writer()(document, tmp_path / "qc-report.json")
    assert list(tmp_path.iterdir()) == []


def test_symlink_parent_is_refused_without_touching_original(tmp_path):
    directory = tmp_path / "original"
    directory.mkdir()
    (tmp_path / "alias").symlink_to(directory, target_is_directory=True)
    with pytest.raises(ValueError, match="QC_REPORT_PATH_INVALID"):
        writer()(report(), tmp_path / "alias/qc-report.json")
    assert list(directory.iterdir()) == []


def test_fsync_failure_never_publishes_a_complete_report_name(tmp_path, monkeypatch):
    def fail(_fd):
        raise OSError("controlled fsync failure")
    monkeypatch.setattr(os, "fsync", fail)
    target = tmp_path / "qc-report.json"
    with pytest.raises(ValueError, match="QC_REPORT_UNWRITABLE"):
        writer()(report(), target)
    assert not target.exists()
    # Retain the incomplete staging artifact for diagnosis; do not delete evidence.
    assert len(list(tmp_path.iterdir())) == 1


def test_fresh_process_reads_the_actual_published_report(tmp_path):
    target = tmp_path / "qc-report.json"
    digest = writer()(report(), target)
    code = ("from pathlib import Path; import hashlib,sys; "
            "from so101_demo.act.episode_qc import read_qc_report; "
            "p=Path(sys.argv[1]); d=read_qc_report(p); "
            "assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[2]; "
            "assert d['identity']['lease']['attempt_id']=='attempt-1'; "
            "print('canonical-v3-report-readback')")
    result = subprocess.run([sys.executable, "-c", code, str(target), digest],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "canonical-v3-report-readback"


def test_readback_refuses_noncanonical_and_unknown_rule_with_positive_control(tmp_path):
    target = tmp_path / "qc-report.json"
    writer()(report(), target)
    original = target.read_bytes()
    target.write_bytes(b" " + original)
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        episode_qc.read_qc_report(target)
    document = json.loads(original)
    document["rule_version"] = "unknown"
    target.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        episode_qc.read_qc_report(target)
    target.write_bytes(original)
    assert episode_qc.read_qc_report(target) == report()


@pytest.mark.parametrize("code", ["TEACHER_REFERENCE_MANIFEST_MISSING", "TEACHER_REFERENCE_START_MISSING",
    "TEACHER_REFERENCE_END_MISSING", "TEACHER_REFERENCE_SESSION_MISMATCH", "TEACHER_REFERENCE_START_NOT_IN_WINDOW",
    "TEACHER_REFERENCE_END_AFTER_RECORDING", "TEACHER_REFERENCE_ORDER_INVALID",
    "TEACHER_REFERENCE_PHYSICS_STEP_ABSENT", "TEACHER_REFERENCE_PHYSICS_TIME_MISMATCH"])
def test_failed_report_keeps_the_specific_reference_code_and_absent_references_explicit(tmp_path, code):
    document = fail_teacher_reference(report(), code)
    details = document["checks"]["teacher_reference_consistency"]["details"]
    details["teacher_manifest_sha256"] = None
    details["start_reference"] = details["end_reference"] = None
    target = tmp_path / "qc-report.json"
    writer()(document, target)
    assert episode_qc.read_qc_report(target) == document


def test_a_legacy_schema_2_report_is_readable_for_audit_but_never_written_again(tmp_path):
    legacy = legacy_v2_report()
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        writer()(legacy, tmp_path / "qc-report.json")
    assert list(tmp_path.iterdir()) == []
    target = tmp_path / "legacy-qc-report.json"
    target.write_bytes((json.dumps(legacy, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode())
    assert episode_qc.read_qc_report(target, legacy=True) == legacy
    with pytest.raises(ValueError, match="QC_REPORT_INVALID"):
        episode_qc.read_qc_report(target)
