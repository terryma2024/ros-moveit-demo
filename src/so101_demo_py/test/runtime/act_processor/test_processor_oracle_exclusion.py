"""O2: a committed episode is exportable. The Teacher-oracle rule the export gate applies is applied at collection as a data verdict.

* `teacher_process.bound_teacher_oracle_exclusion` is the one rule; `bundle._teacher_oracle_exclusion` and `processing.grade_episode` both call it;
* an episode whose Teacher manifest is incomplete (or oracle-flagged) is graded INVALID with `TEACHER_ORACLE_EXCLUDED: <flag> <phase>`,
  QC NOT_RUN, no binding, not export eligible; a complete one grades as before;
* the host readback regrades a VALID verdict with the same function, so old VALID data the rule refuses is refused (not export eligible).

Fixtures only: nothing here reads a host path."""
import hashlib
import json
from pathlib import Path

import pytest

from processed_fixture import IDENTITY, LEASE, Processed
from so101_demo.act import episode_qc, result_store
from so101_demo.act.result_store import export_eligible
from so101_demo.core.process_summary import ProcessSummary
from so101_demo.runtime.act_processor import processing

POLICY = {"schema_version": 3, "policy_sha256": "e" * 64, "cup_pose_source": "broker_rgbd", "verdict_source": "sim_truth"}


def teacher_manifest(*, incomplete=None):
    value = ProcessSummary()
    value.limits = type("L", (), {"maximum_safe_force_n": 3.0, "maximum_compression_distance_m": 1e-4})()
    value.phase_begin("LIFT", 1.0)
    value.phase_finish("LIFT", 2.0, "SUCCEEDED")
    if incomplete:
        value.note_incomplete(incomplete)
    return json.dumps({"schema": "so101-teacher-execute", "schema_version": 1, "teacher_process_summary": value.build(policy=POLICY)}).encode()


def scene_files(tmp_path, manifest_bytes, *, bound=None):
    out = tmp_path / "out"
    (out / "episode/audit").mkdir(parents=True)
    (out / "episode/seal.json").write_text("{}\n")
    (out / "qc-report.json").write_text("{}\n")
    teacher = tmp_path / "sealed/dynamic/dynamic-execute-manifest.json"
    teacher.parent.mkdir(parents=True)
    teacher.write_bytes(manifest_bytes)
    bound = hashlib.sha256(manifest_bytes).hexdigest() if bound is None else bound
    return out, teacher, bound


@pytest.fixture
def graded_chain(monkeypatch):
    """`grade_episode` with the seal, audit lease and QC readback replaced; the QC report names the Teacher manifest hash `bound[0]`."""
    monkeypatch.setattr(result_store, "_seal_facts", lambda path: dict(attempt_id=LEASE["attempt_id"], session_id=IDENTITY["session_id"],
                                                                      reset_epoch=IDENTITY["reset_epoch"]))
    monkeypatch.setattr(result_store, "_verify_audit_lease", lambda manifest, lease: None)
    monkeypatch.setattr(result_store, "_verify_result_qc", lambda path, **kwargs: (
        dict(status="PASS", inputs_sha256="i" * 64, scope_sha256="s" * 64, audit_manifest_sha256="a" * 64), "d" * 64, "formal"))
    bound = []
    monkeypatch.setattr(episode_qc, "read_qc_report", lambda path: {"checks": {episode_qc.REFERENCE_CHECK: {"details": {
        "teacher_manifest_sha256": bound[0]}}}})
    return bound


def grade(tmp_path, out, teacher):
    return processing.grade_episode(out=out, qc_output=out / "qc-report.json", lease=LEASE, identity=IDENTITY, scope=tmp_path / "scope.json",
                                    inputs_manifest=tmp_path / "inputs.json", teacher_status="PASSED", teacher_manifest=teacher)


def test_an_incomplete_teacher_episode_is_graded_invalid_with_the_export_reason_and_is_not_export_eligible(tmp_path, graded_chain):
    out, teacher, digest = scene_files(tmp_path, teacher_manifest(incomplete="WORLD_SEQUENCE_GAP"))
    graded_chain.append(digest)
    graded = grade(tmp_path, out, teacher)
    assert graded["status"] == "INVALID" and graded["qc"] == "NOT_RUN" and graded["binding"] is None
    assert graded["reason"] == "TEACHER_ORACLE_EXCLUDED: INCOMPLETE WORLD_SEQUENCE_GAP"
    assert graded["episode_sha256"] == hashlib.sha256(b"{}\n").hexdigest()
    assert export_eligible("PASSED", graded["qc"], "formal") is False


def test_a_complete_teacher_episode_is_graded_as_before(tmp_path, graded_chain):
    out, teacher, digest = scene_files(tmp_path, teacher_manifest())
    graded_chain.append(digest)
    graded = grade(tmp_path, out, teacher)
    assert (graded["status"], graded["reason"], graded["qc"]) == ("VALID", None, "PASS")
    assert graded["binding"]["qc_report_sha256"] == "d" * 64


def test_a_teacher_manifest_without_a_summary_is_not_judged(tmp_path, graded_chain):
    out, teacher, digest = scene_files(tmp_path, json.dumps({"schema": "so101-dynamic-execute", "schema_version": 1}).encode())
    graded_chain.append(digest)
    assert grade(tmp_path, out, teacher)["status"] == "VALID"


def test_a_manifest_the_qc_did_not_bind_is_not_trusted_and_not_valid(tmp_path, graded_chain):
    out, teacher, _ = scene_files(tmp_path, teacher_manifest())
    graded_chain.append("0" * 64)
    graded = grade(tmp_path, out, teacher)
    assert graded["status"] == "INVALID" and graded["qc"] == "NOT_RUN"
    assert graded["reason"] == "TEACHER_ORACLE_UNVERIFIABLE: EXPORT_EPISODE_TEACHER_MANIFEST_UNBOUND"


def test_the_export_gate_and_the_data_verdict_call_the_same_function(tmp_path, graded_chain, monkeypatch):
    from so101_demo.act import bundle, teacher_process

    calls = []

    def rule(report, manifest):
        calls.append((Path(report).name, Path(manifest).name))
        return ("INCOMPLETE", "SHARED")
    monkeypatch.setattr(teacher_process, "bound_teacher_oracle_exclusion", rule)
    out, teacher, digest = scene_files(tmp_path, teacher_manifest())
    graded_chain.append(digest)
    assert grade(tmp_path, out, teacher)["reason"] == "TEACHER_ORACLE_EXCLUDED: INCOMPLETE SHARED"
    location = tmp_path / "loc"
    evidence = dict(result_location=str(location), processing_output=str(out))
    assert bundle._teacher_oracle_exclusion(evidence) == ("INCOMPLETE", "SHARED")
    assert calls == [("qc-report.json", "dynamic-execute-manifest.json")] * 2


def test_the_readback_of_an_old_valid_verdict_the_rule_refuses_is_refused(tmp_path, graded_chain):
    """frm-044 case: processed-result.json says VALID/PASS/export eligible, the sealed Teacher manifest is incomplete."""
    scene = Processed(tmp_path)
    (scene.sealed / "dynamic/dynamic-execute-manifest.json").write_bytes(teacher_manifest(incomplete="WORLD_SEQUENCE_GAP"))
    graded_chain.append(hashlib.sha256((scene.sealed / "dynamic/dynamic-execute-manifest.json").read_bytes()).hexdigest())
    (scene.out / "qc-report.json").write_text("{}\n")
    scene.write(qc_report_sha256="d" * 64, inputs_sha256="i" * 64, scope_sha256="s" * 64, audit_manifest_sha256="a" * 64)
    from so101_demo.act.processed_result import verify_processed_result

    def read():
        return verify_processed_result(scene.output, sealed=scene.sealed, scene_id=scene.scene, result_sha256=scene.result_sha256,
                                       receipt_sha256=scene.receipt_sha256, scope=scene.scope, inputs_manifest=scene.inputs)
    with pytest.raises(ValueError, match="PROCESSED_RESULT_INVALID"):
        read()
    # the same document over a complete manifest reads back
    (scene.sealed / "dynamic/dynamic-execute-manifest.json").write_bytes(teacher_manifest())
    graded_chain[0] = hashlib.sha256(teacher_manifest()).hexdigest()
    assert read()["act_data_status"] == "VALID"
