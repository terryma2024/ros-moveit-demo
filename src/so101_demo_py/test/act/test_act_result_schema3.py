"""ACT_COLLECTION_RESULT schema 3: the attempt status is the Teacher's; the data verdict is separate.

Teacher PASS with a failing data QC is a PASSED attempt that is not exportable; Teacher FAIL with a passing data QC is
a FAILED attempt outside the success set. Schema 1/2 records stay readable for audit and are never committed again.
"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from act_result_teacher import OUTCOMES, sealed_teacher, teacher, write_manifest
from test_act_result_qc import controlled_committed_result, lease, setup_result
from so101_demo.parallel_batch.contracts import AttemptStatus, RunMode


def _verifier(tmp_path, location, inputs):
    from so101_demo.act.result_store import ActCollectionResultVerifier
    return ActCollectionResultVerifier({"w00": tmp_path / "w00"},
        scope=location / "episode/audit/source.json", inputs_manifest=inputs)


@pytest.mark.parametrize("outcome,status", [
    ("PASSED", AttemptStatus.PASSED), ("FAILED", AttemptStatus.FAILED),
    ("UNCONFIRMED", AttemptStatus.INDETERMINATE), ("FAILED_EXECUTION", AttemptStatus.FAILED),
    ("STOPPED_SAFETY", AttemptStatus.FAILED), ("DEADLINE", AttemptStatus.FAILED),
    ("INDETERMINATE", AttemptStatus.INDETERMINATE)])
def test_attempt_status_is_a_function_of_the_teacher_fields_only(outcome, status):
    from so101_demo.parallel_batch.dynamic_manifest import teacher_attempt_status
    execution, task = OUTCOMES[outcome]
    assert teacher_attempt_status(execution, task) is status


@pytest.mark.parametrize("execution", ["FAILED", "STOPPED_SAFETY", "STOPPED_USER", "DEADLINE", "INDETERMINATE"])
def test_a_teacher_pass_needs_a_completed_execution(execution):
    from so101_demo.parallel_batch.dynamic_manifest import teacher_attempt_status
    with pytest.raises(ValueError):
        teacher_attempt_status(execution, "PASS")


@pytest.mark.parametrize("teacher_outcome,qc,status,exportable", [
    # the fixture is a diagnostic-mode scope: even Teacher PASS + QC PASS is never export eligible (a formal mode is
    # covered by test_d4_spot_check_receipt.test_export_eligible_needs_a_trainable_mode)
    ("PASSED", "PASS", "PASSED", False),
    ("PASSED", "FAIL", "PASSED", False),    # Teacher PASS + data FAIL: still a Teacher success, never exported
    ("FAILED", "PASS", "FAILED", False),    # Teacher FAIL + data PASS: retained, not in the success set
    ("FAILED", "FAIL", "FAILED", False)])
def test_teacher_status_and_data_qc_are_independent_and_export_needs_both(
        tmp_path, monkeypatch, teacher_outcome, qc, status, exportable):
    # the episode seal records the Teacher's outcome; the data QC grades the data whatever that outcome was
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch,
                                                 seal_outcome="PASSED" if teacher_outcome == "PASSED" else "FAILED")
    if qc == "FAIL":
        document["status"], document["reason"] = "FAIL", "DATA_DEFECT"
        document["checks"]["episode_data"] = dict(status="FAIL", reason="DATA_DEFECT")
    location = store.seal(seal, teacher=sealed_teacher(store, teacher_outcome))
    result = json.loads((location / "result.json").read_bytes())
    assert result["schema_version"] == 3
    assert result["status"] == status and result["act_data_qc"] == qc
    assert result["export_eligible"] is exportable
    assert result["act_data_status"] == "PENDING_QC"
    assert "qc_passed" not in result, "the conflated QC-gated flag is gone"
    verdict = _verifier(tmp_path, location, inputs).verify(lease(), str(location), RunMode.EXECUTE)
    assert verdict["status"] == status and verdict["act_data_qc"] == qc and verdict["export_eligible"] is exportable
    assert verdict["teacher_execution_status"] == "COMPLETED"


def test_a_qc_failure_never_downgrades_the_attempt_in_the_store(tmp_path, monkeypatch):
    """The old contract turned a failing QC into attempt FAILED; schema 3 keeps the Teacher's PASSED."""
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    from test_act_qc_report_publication import fail_teacher_reference
    fail_teacher_reference(document, "TEACHER_REFERENCE_END_AFTER_RECORDING")
    location = store.seal(seal, teacher=sealed_teacher(store, "PASSED"))
    result = json.loads((location / "result.json").read_bytes())
    assert result["status"] == "PASSED" and result["act_data_qc"] == "FAIL" and result["export_eligible"] is False


def test_a_corrupt_episode_marks_the_data_invalid_and_keeps_the_teacher_result(tmp_path, monkeypatch):
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    seal.write_text(seal.read_text() + " ")
    location = store.seal(seal, teacher=sealed_teacher(store, "PASSED"))
    result = json.loads((location / "result.json").read_bytes())
    assert result["status"] == "PASSED" and result["teacher_task_result"] == "PASS"
    assert result["act_data_status"] == "INVALID" and result["act_data_qc"] == "NOT_RUN"
    assert result["export_eligible"] is False and result["qc_report_sha256"] is None
    assert "RESULT_EPISODE_INVALID" in result["act_data_reason"]
    assert not (location / "qc-report.json").exists()


@pytest.mark.parametrize("data", ["INVALID", "DISABLED"])
def test_qc_is_not_run_for_data_the_child_already_marked_invalid_or_disabled(tmp_path, monkeypatch, data):
    from so101_demo.act import episode_qc
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    monkeypatch.setattr(episode_qc, "recompute_native_qc",
                        lambda *args, **kwargs: pytest.fail("QC ran on data that cannot be graded"))
    location = store.seal(seal, teacher=sealed_teacher(store, "PASSED", data=data, reason="X" if data == "INVALID" else None))
    result = json.loads((location / "result.json").read_bytes())
    assert result["status"] == "PASSED" and result["act_data_status"] == data
    assert result["act_data_qc"] == "NOT_RUN" and result["export_eligible"] is False


def _positive(tmp_path, monkeypatch, outcome="PASSED"):
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    location = store.seal(seal, teacher=sealed_teacher(store, outcome))
    verifier = _verifier(tmp_path, location, inputs)
    assert verifier.verify(lease(), str(location), RunMode.EXECUTE)["status"] == outcome
    return location, verifier


def _rewrite(location, change):
    path = location / "result.json"
    document = json.loads(path.read_bytes())
    change(document)
    path.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")


@pytest.mark.parametrize("fault", [
    "unknown_version", "extra_key", "missing_key", "status_not_from_teacher", "export_flag_flipped",
    "qc_pass_on_invalid_data", "teacher_pass_without_completion", "unknown_enum", "retired_version"])
def test_the_verifier_rejects_each_schema_3_inconsistency(tmp_path, monkeypatch, fault):
    location, verifier = _positive(tmp_path, monkeypatch)

    def change(document):
        if fault == "unknown_version":
            document["schema_version"] = 4
        if fault == "extra_key":
            document["qc_passed"] = True
        if fault == "missing_key":
            del document["act_data_qc"]
        if fault == "status_not_from_teacher":
            document["status"] = "FAILED"
        if fault == "export_flag_flipped":
            document["act_data_qc"], document["export_eligible"] = "FAIL", True
        if fault == "qc_pass_on_invalid_data":
            document["act_data_status"] = "INVALID"
        if fault == "teacher_pass_without_completion":
            document["teacher_execution_status"] = "FAILED"
        if fault == "unknown_enum":
            document["teacher_task_result"] = "MAYBE"
        if fault == "retired_version":
            document["schema_version"] = 2
    _rewrite(location, change)
    with pytest.raises(ValueError, match="RESULT_SCHEMA_INVALID|RESULT_TEACHER_|RESULT_DATA_"):
        verifier.verify(lease(), str(location), RunMode.EXECUTE)


@pytest.mark.parametrize("fault", ["manifest_disagrees", "manifest_missing", "data_status_unknown"])
def test_the_verifier_checks_the_teacher_claim_against_the_sealed_teacher_manifest(tmp_path, monkeypatch, fault):
    location, verifier = _positive(tmp_path, monkeypatch)
    manifest = location / "dynamic/dynamic-execute-manifest.json"
    if fault == "manifest_missing":
        manifest.unlink()
    else:
        document = json.loads(manifest.read_bytes())
        if fault == "manifest_disagrees":
            document["teacher_task_result"]["result"] = "FAIL"
        else:
            document["act_data_status"] = "NOT_A_STATUS"
        manifest.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="RESULT_TEACHER_MANIFEST"):
        verifier.verify(lease(), str(location), RunMode.EXECUTE)


@pytest.mark.parametrize("data", ["VALID", "PENDING_QC", "INVALID", "DISABLED"])
def test_the_data_status_is_the_recorders_and_the_teacher_manifest_does_not_constrain_it(tmp_path, monkeypatch, data):
    """A4c: the sealed Teacher manifest says DISABLED (it has no data side); the claim's status comes from the Recorder."""
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    claim = sealed_teacher(store, "PASSED", data=data, reason="X" if data == "INVALID" else None)
    manifest = json.loads((store.working / "dynamic/dynamic-execute-manifest.json").read_bytes())
    assert manifest["act_data_status"] == "DISABLED"
    location = store.seal(seal, teacher=claim)
    assert json.loads((location / "result.json").read_bytes())["act_data_status"] == data


def test_the_store_refuses_a_teacher_claim_its_own_manifest_contradicts(tmp_path, monkeypatch):
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    claim = teacher("PASSED")
    write_manifest(store.working, teacher("FAILED"))
    with pytest.raises(ValueError, match="RESULT_TEACHER_MANIFEST"):
        store.seal(seal, teacher=claim)
    assert not (store.workspace / "sealed").exists()


def test_seal_attempt_classifies_from_the_decision_teacher_fields(tmp_path, monkeypatch):
    from types import SimpleNamespace
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    fields = sealed_teacher(store, "FAILED")
    decision = SimpleNamespace(status=AttemptStatus.FAILED, teacher_execution_status=fields["execution_status"],
        teacher_task_result=fields["task_result"], act_data_status=fields["data_status"], act_data_reason=None,
        episode_seal_path=seal)
    with pytest.raises(ValueError, match="RESULT_TERMINAL_MISMATCH"):
        store.seal_attempt(lease(), SimpleNamespace(**{**vars(decision), "status": AttemptStatus.PASSED}))
    with pytest.raises(ValueError, match="RESULT_TEACHER_FIELDS_REQUIRED"):
        store.seal_attempt(lease(), SimpleNamespace(status=AttemptStatus.FAILED, episode_seal_path=seal))
    location = store.seal_attempt(lease(), decision)
    assert json.loads((Path(location) / "result.json").read_bytes())["status"] == "FAILED"


def test_an_indeterminate_teacher_result_is_sealable_without_any_episode(tmp_path, monkeypatch):
    from types import SimpleNamespace
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    seal.unlink()
    decision = SimpleNamespace(status=AttemptStatus.INDETERMINATE, teacher_execution_status="INDETERMINATE",
        teacher_task_result="UNCONFIRMED", act_data_status="INVALID", act_data_reason="NO_EPISODE", episode_seal_path=seal)
    location = Path(store.seal_attempt(lease(), decision))
    result = json.loads((location / "result.json").read_bytes())
    assert result["status"] == "INDETERMINATE" and result["act_data_qc"] == "NOT_RUN"
    assert result["episode_seal_sha256"] is None
    verdict = _verifier(tmp_path, location, inputs).verify(lease(), str(location), RunMode.EXECUTE)
    assert verdict["status"] == "INDETERMINATE" and verdict["export_eligible"] is False


def test_the_store_requires_the_teacher_result(tmp_path, monkeypatch):
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        store.seal(seal)          # the Teacher result is required: there is no other path


def test_the_coordinator_commit_journal_and_index_record_both_results(tmp_path, monkeypatch):
    from so101_demo.act.result_store import verify_coordinator_commit
    from so101_demo.parallel_batch.journal import CoordinatorJournal
    run, location, scope, inputs, receipt = controlled_committed_result(tmp_path, monkeypatch, teacher_outcome="PASSED")
    # The controlled QC double fails the data (the episode seal says FAILED); the Teacher passed.
    assert receipt["status"] == "PASSED"
    assert (receipt["teacher_execution_status"], receipt["teacher_task_result"]) == ("COMPLETED", "PASS")
    assert (receipt["act_data_status"], receipt["act_data_qc"], receipt["export_eligible"]) == (
        "PENDING_QC", "FAIL", False)
    committed = [event for event in CoordinatorJournal.read_only_replay(run / "coordinator", "batch-1").events
                 if event.type == "RESULT_COMMITTED"]
    assert len(committed) == 1 and committed[0].payload["response"] == receipt
    index = json.loads((run / "coordinator/aggregate_results.json").read_bytes())
    assert index["points"]["point-1"]["status"] == "PASSED"
    assert index["act_results"]["point-1"] == dict(teacher_execution_status="COMPLETED",
        teacher_task_result="PASS", act_data_status="PENDING_QC", act_data_qc="FAIL", export_eligible=False)
    proof = verify_coordinator_commit(run / "coordinator", location=location, scope=scope, inputs_manifest=inputs)
    assert proof["result_status"] == "PASSED" and proof["act_data_qc"] == "FAIL" and proof["export_eligible"] is False
    assert proof["teacher_task_result"] == "PASS" and proof["result_schema_version"] == 3


def test_a_result_of_another_schema_version_cannot_be_committed_by_the_coordinator(tmp_path, monkeypatch):
    run, location, scope, inputs, commit = controlled_committed_result(tmp_path, monkeypatch, commit=False)
    _rewrite(location, lambda document: document.update(schema_version=2))
    with pytest.raises(ValueError, match="RESULT_SCHEMA_INVALID"):
        commit()


def test_batch_summary_reports_the_teacher_success_rate_over_all_started_attempts():
    from so101_demo.parallel_batch.contracts import BatchSummary, PointStatus
    summary = BatchSummary(RunMode.EXECUTE, {"a": PointStatus.PASSED, "b": PointStatus.PASSED,
        "c": PointStatus.FAILED, "d": PointStatus.INDETERMINATE, "f": PointStatus.UNRUN},
        batch_terminal=True,
        act_results={"a": dict(act_data_qc="PASS", export_eligible=True), "b": dict(act_data_qc="FAIL", export_eligible=False),
                     "c": dict(act_data_qc="PASS", export_eligible=False), "d": dict(act_data_qc="NOT_RUN", export_eligible=False)})
    # PASSED, FAILED and INDETERMINATE are the started, legal Teacher attempts; an UNRUN point is not.
    assert summary.teacher_attempts_started == 4 and summary.teacher_passed == 2
    assert summary.teacher_success_rate == 0.5
    # The data side is reported separately: it never shrinks the Teacher denominator.
    assert summary.act_data_qc_passed == 2 and summary.committable_episodes == 1
    assert summary.act_data_pass_rate == 0.5


def test_batch_summary_without_started_attempts_has_no_rate():
    from so101_demo.parallel_batch.contracts import BatchSummary, PointStatus
    summary = BatchSummary(RunMode.EXECUTE, {"a": PointStatus.UNRUN})
    assert summary.teacher_attempts_started == 0 and summary.teacher_success_rate is None
    assert summary.act_data_pass_rate is None and summary.committable_episodes == 0


def test_the_outcome_document_reports_teacher_and_data_rates_separately():
    from so101_demo.cli.mujoco_parallel_batch import outcome_document
    from so101_demo.parallel_batch.contracts import BatchSummary, PointStatus
    summary = BatchSummary(RunMode.EXECUTE, {"a": PointStatus.PASSED, "b": PointStatus.FAILED}, batch_terminal=True,
        act_results={"a": dict(act_data_qc="FAIL", export_eligible=False)})
    _, document = outcome_document(summary)
    assert document["teacher_attempts_started"] == 2 and document["teacher_passed"] == 1
    assert document["teacher_success_rate"] == 0.5
    assert document["act_data_qc_passed"] == 0 and document["committable_episodes"] == 0
