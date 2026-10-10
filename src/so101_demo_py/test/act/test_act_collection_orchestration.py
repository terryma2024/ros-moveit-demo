"""The collection request of one run (Phase A4c, cleanup step 2): validated before any Teacher starts, refused outside the diagnostic
mode and outside the fault sandbox, and carried to the Worker as a re-validated document.

The orchestrator tests of the live Recorder (ready file, CAPTURING, SIGTERM, exit wait) went with that orchestrator; the offline data path
is tested in `test_p3_offline_switch` and `test_p3_rework`. All with fakes: no stack, no ROS.
"""

from types import SimpleNamespace

import pytest

from so101_demo.act.collection_orchestration import (
    COLLECTION_FAULTS, CollectionOptions, CollectionRefused, collection_from_document, require_under_sandbox,
    validate_collection_request)
from so101_demo.parallel_batch.contracts import AttemptStatus


# ---- the request is validated before anything starts ---------------------------------------------------------------

def test_the_collection_request_is_validated_before_any_teacher_start(tmp_path):
    run = tmp_path / "run"
    assert validate_collection_request("on", "none", run_mode="formal", run_root=run) == CollectionOptions("on", "none", None)
    assert validate_collection_request("off", "none", run_mode="formal", run_root=run).enabled is False
    diagnostic = "preselected_target_diagnostic"
    options = validate_collection_request("on", "source_gap", run_mode=diagnostic, run_root=run)
    assert options.sandbox_root == run / "fault-sandbox" and options.fault == "source_gap"
    for collection, fault, mode, code in (
            ("on", "source_gap", "formal", "COLLECTION_FAULT_REQUIRES_DIAGNOSTIC_MODE"),
            ("off", "source_gap", diagnostic, "COLLECTION_FAULT_REQUIRES_COLLECTION_ON"),
            ("maybe", "none", diagnostic, "COLLECTION_MODE_UNKNOWN"), ("on", "chaos", diagnostic, "COLLECTION_FAULT_UNKNOWN")):
        with pytest.raises(CollectionRefused, match=code):
            validate_collection_request(collection, fault, run_mode=mode, run_root=run)


def test_every_fault_is_refused_in_the_formal_mode(tmp_path):
    for fault in COLLECTION_FAULTS:
        if fault == "none":
            continue
        with pytest.raises(CollectionRefused, match="REQUIRES_DIAGNOSTIC_MODE"):
            validate_collection_request("on", fault, run_mode="formal", run_root=tmp_path)


def test_a_fault_output_outside_the_sandbox_is_refused(tmp_path):
    sandbox = tmp_path / "run" / "fault-sandbox"
    inside = sandbox / "attempt-1" / "episode"
    require_under_sandbox(sandbox, inside, sandbox / "attempt-1" / "recorder-result.json")
    outside = tmp_path / "run" / "attempts" / "episode"
    for bad in (outside, sandbox / ".." / "episode", tmp_path / "fault-sandbox-evil" / "episode"):
        with pytest.raises(CollectionRefused, match="COLLECTION_FAULT_OUTSIDE_SANDBOX"):
            require_under_sandbox(sandbox, inside, bad)
    with pytest.raises(CollectionRefused, match="COLLECTION_FAULT_OUTSIDE_SANDBOX"):
        require_under_sandbox(tmp_path / "run" / "not-a-sandbox", tmp_path / "run" / "not-a-sandbox" / "x")
    with pytest.raises(CollectionRefused, match="COLLECTION_FAULT_SANDBOX_REQUIRED"):
        require_under_sandbox(None, inside)
    link = tmp_path / "run" / "fault-sandbox" / "escape"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(CollectionRefused, match="COLLECTION_FAULT_OUTSIDE_SANDBOX"):
        require_under_sandbox(sandbox, link / "episode")


def test_the_worker_specification_round_trips_and_a_forged_one_is_refused(tmp_path):
    options = validate_collection_request("on", "queue_overflow", run_mode="preselected_target_diagnostic",
                                          run_root=tmp_path / "run")
    assert collection_from_document(options.document()) == options
    plain = CollectionOptions("off", "none", None)
    assert collection_from_document(plain.document()) == plain
    for forged in ({**options.document(), "sandbox_root": str(tmp_path / "run")},
                   {**options.document(), "sandbox_root": None}, {**options.document(), "mode": "off"},
                   {**options.document(), "fault": "chaos"}, {"mode": "on"},
                   {**plain.document(), "sandbox_root": str(tmp_path / "fault-sandbox")}):
        with pytest.raises(CollectionRefused):
            collection_from_document(forged)


def test_seal_attempt_hands_the_independent_qc_report_to_the_store(tmp_path, monkeypatch):
    from test_act_result_schema3 import setup_result
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    captured = {}
    store.seal = lambda path, *, teacher, qc_report_path=None: captured.update(
        path=path, teacher=teacher, qc=qc_report_path) or "sealed"
    decision = SimpleNamespace(status=AttemptStatus.PASSED, teacher_execution_status="COMPLETED",
                               teacher_task_result="PASS", act_data_status="VALID", act_data_reason=None,
                               episode_seal_path=seal, qc_report_path=store.working / "qc-report.json")
    assert store.seal_attempt(store.lease, decision) == "sealed"
    assert captured["qc"] == store.working / "qc-report.json" and captured["teacher"]["data_status"] == "VALID"
    # a decision without a report (the Teacher-only path) hands the store nothing and the store grades in process
    del decision.qc_report_path
    store.seal_attempt(store.lease, decision)
    assert captured["qc"] is None
