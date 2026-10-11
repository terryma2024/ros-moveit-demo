"""One actual reserved Worker workspace publishes the common ACT result contract."""

from dataclasses import replace
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from act_result_teacher import sealed_teacher
from so101_demo.act.collection_scope import write_collection_scope
from so101_demo.act.result_store import ActCollectionResultVerifier
from so101_demo.cli.mujoco_batch.worker_process import _ArtifactResults
from so101_demo.parallel_batch.contracts import AttemptStatus, RunMode
from so101_demo.runtime.parallel_ros_runtime import ResetBoundaryReceipt
from test_act_seal_and_downgrade import lease, sealed_episode, SCOPE


def _teacher_decision(workspace, outcome, status, *, data="PENDING_QC"):
    """The decision the Worker hands the result port: the Teacher's fields, with its manifest on disk."""
    fields = sealed_teacher(SimpleNamespace(working=workspace.path), outcome, data=data)
    return SimpleNamespace(status=status, reason="fixture_stop", physical_action_proven_absent=False,
        teacher_execution_status=fields["execution_status"], teacher_task_result=fields["task_result"],
        act_data_status=fields["data_status"], act_data_reason=None)


def test_reserved_producer_binds_original_inputs_and_publishes_qc(tmp_path, monkeypatch):
    from so101_demo.act import episode_qc
    from test_act_qc_report_publication import fail_teacher_reference, report
    current=lease(); worker=tmp_path/current.worker_id
    scope=tmp_path/'scope.json'; write_collection_scope(SCOPE,scope)
    inputs=tmp_path/'inputs-manifest.json'
    inputs.write_text(json.dumps(dict(inputs_sha256=SCOPE['inputs_sha256'], mode=SCOPE['mode'])))
    results=_ArtifactResults({current.worker_id:worker},RunMode.EXECUTE,
        collection_scope=scope,collection_inputs_manifest=inputs,clock=lambda:15.)
    results.reserve_workspace(current,ResetBoundaryReceipt('reset-2','session-1',11.,.1))
    workspace=results.workspace(current)
    audit,seal=sealed_episode(tmp_path,episode_root=workspace.path/'episode',audit_lease=current,
        outcome=dict(status='FAILED',reason='controlled stop',pick_place_validation_success=False,stopped_confirmed=True))
    expected=report(); expected['identity']=json.loads(audit.read_bytes())['identity']
    expected.update(inputs_sha256=SCOPE['inputs_sha256'],
        scope_sha256=hashlib.sha256(scope.read_bytes()).hexdigest(),
        audit_manifest_sha256=hashlib.sha256(audit.read_bytes()).hexdigest(),
        episode_seal_sha256=hashlib.sha256(seal.read_bytes()).hexdigest())
    expected['counts']['records']=json.loads(seal.read_bytes())['record_count']
    fail_teacher_reference(expected,'TEACHER_REFERENCE_MANIFEST_MISSING')
    def recompute(root,*,scope,inputs_manifest):
        assert inputs_manifest==inputs
        return copy.deepcopy(expected)
    monkeypatch.setattr(episode_qc,'recompute_native_qc',recompute)
    location=Path(results.seal_attempt(current,_teacher_decision(workspace,'FAILED',AttemptStatus.FAILED)))
    result=json.loads((location/'result.json').read_bytes())
    assert result['schema_version']==3 and result['status']=='FAILED' and result['act_data_qc']=='FAIL'
    assert episode_qc.read_qc_report(location/'qc-report.json')==expected
    assert ActCollectionResultVerifier({current.worker_id:worker},scope=scope,inputs_manifest=inputs).verify(
        current,str(location),RunMode.EXECUTE)['status']=='FAILED'


def test_reserved_workspace_and_actual_episode_publish_common_act_result(tmp_path):
    current = lease()
    worker = tmp_path / current.worker_id
    scope = tmp_path / "scope.json"
    write_collection_scope(SCOPE, scope)
    results = _ArtifactResults({current.worker_id: worker}, RunMode.EXECUTE,
                              collection_scope=scope, clock=lambda: 15.)
    reset = ResetBoundaryReceipt("reset-2", "session-1", 11., .1)
    assert results.reserve_workspace(current, reset) is True
    workspace = results.workspace(current)
    identity_bytes = (workspace.path / "workspace_identity.json").read_bytes()
    _, episode = sealed_episode(tmp_path, episode_root=workspace.path / "episode",
        audit_lease=current, outcome={"status": "FAILED", "reason": "fixture_stop",
            "pick_place_validation_success": False, "stopped_confirmed": True})
    original = episode.read_bytes()
    decision = _teacher_decision(workspace, "FAILED", AttemptStatus.FAILED)
    location = results.seal_attempt(current, decision)
    assert Path(location) == workspace.path.parent / "sealed"
    assert (Path(location) / "workspace_identity.json").read_bytes() == identity_bytes
    assert (Path(location) / "episode" / "seal.json").read_bytes() == original
    assert not (Path(location) / "attempt-result.json").exists()
    document = json.loads((Path(location) / "result.json").read_bytes())
    assert document["kind"] == "ACT_COLLECTION_RESULT" and document["status"] == "FAILED"
    verifier = ActCollectionResultVerifier({current.worker_id: worker}, scope=scope)
    assert verifier.verify(current, location, RunMode.EXECUTE)["status"] == "FAILED"


def test_common_result_refuses_a_missing_episode_without_generic_success_fallback(tmp_path):
    current = lease()
    worker = tmp_path / current.worker_id
    scope = tmp_path / "scope.json"
    write_collection_scope(SCOPE, scope)
    results = _ArtifactResults({current.worker_id: worker}, RunMode.EXECUTE,
                              collection_scope=scope, clock=lambda: 15.)
    results.reserve_workspace(current, ResetBoundaryReceipt("reset-2", "session-1", 11., .1))
    # a success invented by the worker, with no Teacher result behind it, is refused outright
    with pytest.raises(ValueError, match="RESULT_TEACHER_FIELDS_REQUIRED"):
        results.seal_attempt(current, SimpleNamespace(status=AttemptStatus.PASSED,
            reason="invented_success", physical_action_proven_absent=False))
    working = results.workspace(current).path
    assert not working.parent.joinpath("sealed").exists()
    assert not working.joinpath("attempt-result.json").exists()


def test_a_teacher_result_without_any_episode_is_published_with_invalid_unexportable_data(tmp_path):
    """Superseded: a missing episode used to refuse the whole result. It is now only a data verdict."""
    current = lease()
    worker = tmp_path / current.worker_id
    scope = tmp_path / "scope.json"
    write_collection_scope(SCOPE, scope)
    results = _ArtifactResults({current.worker_id: worker}, RunMode.EXECUTE,
                              collection_scope=scope, clock=lambda: 15.)
    results.reserve_workspace(current, ResetBoundaryReceipt("reset-2", "session-1", 11., .1))
    workspace = results.workspace(current)
    location = Path(results.seal_attempt(current, _teacher_decision(workspace, "PASSED", AttemptStatus.PASSED)))
    document = json.loads((location / "result.json").read_bytes())
    assert document["status"] == "PASSED" and document["teacher_task_result"] == "PASS"
    assert document["act_data_status"] == "INVALID" and document["act_data_qc"] == "NOT_RUN"
    assert document["export_eligible"] is False and "RESULT_EPISODE_INVALID" in document["act_data_reason"]


def test_common_result_does_not_bind_a_foreign_mode(tmp_path):
    scope = tmp_path / "scope.json"
    write_collection_scope(SCOPE, scope)
    with pytest.raises(ValueError, match="ACT_RESULT_EXECUTE_REQUIRED"):
        _ArtifactResults({"w00": tmp_path / "w00"}, RunMode.PLAN_ONLY,
                         collection_scope=scope, clock=lambda: 15.)


def test_changed_original_workspace_metadata_cannot_be_published(tmp_path):
    current = lease()
    worker = tmp_path / current.worker_id
    scope = tmp_path / "scope.json"
    write_collection_scope(SCOPE, scope)
    results = _ArtifactResults({current.worker_id: worker}, RunMode.EXECUTE,
                              collection_scope=scope, clock=lambda: 15.)
    results.reserve_workspace(current, ResetBoundaryReceipt("reset-2", "session-1", 11., .1))
    workspace = results.workspace(current)
    sealed_episode(tmp_path, episode_root=workspace.path / "episode", audit_lease=current,
        outcome={"status": "FAILED", "reason": "fixture_stop",
                 "pick_place_validation_success": False, "stopped_confirmed": True})
    path = workspace.path / "workspace_identity.json"
    metadata = json.loads(path.read_bytes())
    metadata["identity"]["worker_generation"] += 1
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="ACT_RESERVED_WORKSPACE_INVALID"):
        results.seal_attempt(current, _teacher_decision(workspace, "FAILED", AttemptStatus.FAILED))
    assert not (workspace.path.parent / "sealed").exists()


def test_selected_pass_without_original_native_physical_rows_publishes_invalid_data_not_a_failure(tmp_path):
    current = lease()
    worker = tmp_path / current.worker_id
    scope = tmp_path / "scope.json"
    write_collection_scope(SCOPE, scope)
    results = _ArtifactResults({current.worker_id: worker}, RunMode.EXECUTE,
                              collection_scope=scope, clock=lambda: 15.)
    results.reserve_workspace(current, ResetBoundaryReceipt("reset-2", "session-1", 11., .1))
    workspace = results.workspace(current)
    sealed_episode(tmp_path, episode_root=workspace.path / "episode", audit_lease=current,
        outcome={"status": "PASSED", "reason": "synthetic claim without native source",
                 "pick_place_validation_success": True, "stopped_confirmed": True})
    # The Teacher passed; the episode's PASSED claim has no original native physical rows behind it. That is a data
    # verdict: the result is published with the Teacher's PASSED and INVALID, unexportable data.
    location = Path(results.seal_attempt(current, _teacher_decision(workspace, "PASSED", AttemptStatus.PASSED)))
    document = json.loads((location / "result.json").read_bytes())
    assert document["status"] == "PASSED" and document["act_data_status"] == "INVALID"
    assert document["act_data_qc"] == "NOT_RUN" and document["export_eligible"] is False
    assert "RESULT_EPISODE_INVALID" in document["act_data_reason"]
