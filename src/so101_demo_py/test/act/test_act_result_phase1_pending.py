"""Phase 1 seal: a Teacher result with PENDING_QC data and no episode is sealable and verifiable (the processor has not run)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from act_result_teacher import sealed_teacher
from test_act_result_qc import lease, setup_result
from test_act_result_schema3 import _verifier
from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode


def _pending_decision(store, seal, **changes):
    """A phase-1 decision: PENDING_QC data, no episode, and the recording receipt the shard task wrote under raw/."""
    receipt = store.working / "raw" / "recording-receipt.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text("{}\n")
    values = dict(status=AttemptStatus.PASSED, teacher_execution_status="COMPLETED", teacher_task_result="PASS",
                  act_data_status="PENDING_QC", act_data_reason=None, episode_seal_path=seal, recording_receipt_path=receipt)
    return SimpleNamespace(**(values | changes))


@pytest.mark.parametrize("outcome,status", [("PASSED", AttemptStatus.PASSED), ("FAILED", AttemptStatus.FAILED)])
def test_pending_qc_without_an_episode_seals_with_final_teacher_fields_and_no_export(tmp_path, monkeypatch, outcome, status):
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    fields = sealed_teacher(store, outcome)
    seal.unlink()
    decision = _pending_decision(store, seal, status=status, teacher_execution_status=fields["execution_status"],
                                 teacher_task_result=fields["task_result"])
    location = Path(store.seal_attempt(lease(), decision))
    result = json.loads((location / "result.json").read_bytes())
    assert result["status"] == status.value and result["act_data_status"] == "PENDING_QC"
    assert (result["teacher_execution_status"], result["teacher_task_result"]) == (
        fields["execution_status"], fields["task_result"])
    assert result["act_data_qc"] == "NOT_RUN" and result["export_eligible"] is False and result["act_data_reason"] is None
    assert result["episode_seal_sha256"] is None and result["qc_report_path"] is None and result["qc_report_sha256"] is None
    verdict = _verifier(tmp_path, location, inputs).verify(lease(), str(location), RunMode.EXECUTE)
    assert verdict["act_data_status"] == "PENDING_QC" and verdict["export_eligible"] is False
    assert verdict["act_data_qc"] == "NOT_RUN" and verdict["episode_seal_sha256"] is None


def test_a_forged_pending_result_that_claims_export_or_a_qc_pass_is_refused(tmp_path, monkeypatch):
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    sealed_teacher(store, "PASSED")
    seal.unlink()
    location = Path(store.seal_attempt(lease(), _pending_decision(store, seal)))
    path = location / "result.json"
    original = json.loads(path.read_bytes())
    for changes in (dict(export_eligible=True), dict(act_data_qc="PASS")):
        path.write_text(json.dumps(dict(original, **changes)))
        with pytest.raises(ValueError):
            _verifier(tmp_path, location, inputs).verify(lease(), str(location), RunMode.EXECUTE)


@pytest.mark.parametrize("how", ["no_receipt_named", "receipt_file_absent", "receipt_elsewhere"])
def test_pending_qc_without_a_written_recording_receipt_is_still_graded_on_its_missing_episode(tmp_path, monkeypatch, how):
    """Phase 1 is explicit: only a decision naming the receipt under raw/ seals as pending; a bare PENDING_QC claim with no episode
    stays INVALID data (the earlier rule)."""
    store, seal, document, inputs = setup_result(tmp_path, monkeypatch)
    sealed_teacher(store, "PASSED")
    seal.unlink()
    decision = _pending_decision(store, seal)
    if how == "no_receipt_named":
        decision.recording_receipt_path = None
    elif how == "receipt_file_absent":
        decision.recording_receipt_path.unlink()
    else:
        decision.recording_receipt_path = store.working / "recording-receipt.json"
        decision.recording_receipt_path.write_text("{}\n")
    location = Path(store.seal_attempt(lease(), decision))
    result = json.loads((location / "result.json").read_bytes())
    assert result["act_data_status"] == "INVALID" and "RESULT_EPISODE_INVALID" in result["act_data_reason"]
