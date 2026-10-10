"""A Task 9 episode becomes a result only through its reserved lease workspace."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from act_result_teacher import sealed_teacher, write_manifest
from so101_demo.act.collection_scope import write_collection_scope
from so101_demo.act.episode_audit import EpisodeAuditWriter
from so101_demo.act.recorder import EpisodeRecorder
from so101_demo.act.result_store import (
    ActCollectionResultStore, ActCollectionResultVerifier, ActCollectionResults, ResultInfraError,
)
from so101_demo.parallel_batch.contracts import AttemptStatus, LeaseIdentity, RunMode
from so101_demo.parallel_batch.contracts import BatchKind, BatchRequest, load_parallel_runtime_config_linux_cuda
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from paths import PACKAGE_ROOT
from test_act_seal_and_downgrade import IDENTITY, SCOPE


PROVENANCE = {"source_sha256": "a" * 64, "scene_sha256": "b" * 64,
              "config_sha256": "c" * 64, "policy_fingerprint": "d" * 64, "seed": 3}


def lease():
    return LeaseIdentity(batch_id="batch-1", coordinator_epoch=1, worker_id="w00",
                         worker_generation=1, point_id="scene-1", attempt_id="attempt-1",
                         lease_generation=1, lease_issued_monotonic_s=10.,
                         lease_deadline_monotonic_s=20.)


def scope_of(tmp_path):
    """The collection scope every episode of a test ran under, written once next to the worker roots."""
    path = tmp_path / "collection-scope.json"
    if not path.exists():
        write_collection_scope(SCOPE, path)
    return path


def failed_episode(store, tmp_path, *, session_id="session-1"):
    """A sealed business-failed episode with the audit it names, at the store's episode root."""
    scope = scope_of(tmp_path)
    recorder = EpisodeRecorder(store.episode_root, session_id=session_id,
                               attempt_id=store.lease.attempt_id, reset_epoch=2, provenance=PROVENANCE)
    identity = {**IDENTITY, "session_id": session_id, "attempt_id": store.lease.attempt_id,
                "lease": asdict(store.lease)}
    audit = EpisodeAuditWriter(store.episode_root, SCOPE, identity, {"inputs_sha256": "a" * 64}).seal(
        {"start_s": 1., "end_s": 1., "label_cutoff_s": 1.})
    store.audit_manifest, store.scope = audit, scope
    return recorder.finish({"status": "FAILED", "reason": "search_failed",
                            "task8_success": False, "stopped_confirmed": True},
                           audit_manifest=audit, scope=scope)


def test_exact_lease_seal_verifies_and_discovers_only_reserved_workspace(tmp_path):
    worker_root = tmp_path / "w00"
    current = lease()
    workspace = worker_root / "attempts" / current.point_id / current.attempt_id
    store = ActCollectionResultStore(workspace, current, clock=lambda: 15.)
    sealed = store.seal(failed_episode(store, tmp_path), teacher=sealed_teacher(store, "FAILED"))
    verifier = ActCollectionResultVerifier({"w00": worker_root}, scope=scope_of(tmp_path))
    result = verifier.verify(current, str(sealed), RunMode.EXECUTE)
    assert result["status"] == "FAILED" and len(result["sha256"]) == 64
    assert verifier.discover(current, workspace) == str(sealed)
    assert verifier.discover(current, tmp_path / "foreign") is None
    with pytest.raises(ValueError, match="LEASE_LOCATION_MISMATCH"):
        verifier.verify(current, str(tmp_path / "foreign/sealed"), RunMode.EXECUTE)


def test_verifier_rejects_self_declared_late_completion_and_identity_tamper(tmp_path):
    current = lease()
    worker_root = tmp_path / "w00"
    workspace = worker_root / "attempts" / current.point_id / current.attempt_id
    store = ActCollectionResultStore(workspace, current, clock=lambda: 19.)
    sealed = store.seal(failed_episode(store, tmp_path), teacher=sealed_teacher(store, "FAILED"))
    verifier = ActCollectionResultVerifier({"w00": worker_root}, scope=scope_of(tmp_path))
    later = replace(current, lease_deadline_monotonic_s=18.)
    with pytest.raises(ValueError, match="RESULT_AFTER_LEASE_DEADLINE"):
        verifier.verify(later, str(sealed), RunMode.EXECUTE)
    other = replace(current, worker_generation=2)
    with pytest.raises(ValueError, match="LEASE_IDENTITY_MISMATCH"):
        verifier.verify(other, str(sealed), RunMode.EXECUTE)


def test_episode_hash_and_business_status_are_independently_verified(tmp_path):
    current = lease()
    worker_root = tmp_path / "w00"
    workspace = worker_root / "attempts" / current.point_id / current.attempt_id
    store = ActCollectionResultStore(workspace, current, clock=lambda: 15.)
    sealed = store.seal(failed_episode(store, tmp_path), teacher=sealed_teacher(store, "FAILED"))
    verifier = ActCollectionResultVerifier({"w00": worker_root}, scope=scope_of(tmp_path))
    episode = sealed / "episode/seal.json"
    episode.write_text(episode.read_text() + " ")
    with pytest.raises(ValueError, match="EPISODE_SEAL_HASH_MISMATCH"):
        verifier.verify(current, str(sealed), RunMode.EXECUTE)


def test_unsealed_directory_cannot_be_discovered_or_committed(tmp_path):
    current = lease()
    worker_root = tmp_path / "w00"
    workspace = worker_root / "attempts" / current.point_id / current.attempt_id
    store = ActCollectionResultStore(workspace, current, clock=lambda: 15.)
    failed_episode(store, tmp_path)
    verifier = ActCollectionResultVerifier({"w00": worker_root}, scope=scope_of(tmp_path))
    assert verifier.discover(current, workspace) is None
    with pytest.raises(ValueError, match="LEASE_LOCATION_MISMATCH|RESULT_MISSING"):
        verifier.verify(current, str(store.episode_root.parent), RunMode.EXECUTE)


def test_corrupt_episode_marks_the_data_invalid_and_never_the_teacher_result(tmp_path):
    """A corrupt episode is a data problem: the Teacher's FAILED stays FAILED and the data is INVALID/NOT_RUN."""
    import json
    current = lease()
    workspace = tmp_path / "w00/attempts" / current.point_id / current.attempt_id
    store = ActCollectionResultStore(workspace, current, clock=lambda: 15.)
    episode_path = failed_episode(store, tmp_path)
    episode_path.write_text(episode_path.read_text() + " ")
    sealed = store.seal(episode_path, teacher=sealed_teacher(store, "FAILED"))
    result = json.loads((sealed / "result.json").read_bytes())
    assert result["status"] == "FAILED" and result["act_data_status"] == "INVALID"
    assert result["act_data_qc"] == "NOT_RUN" and "RESULT_EPISODE_INVALID" in result["act_data_reason"]


def _decision(status, fields, episode_path):
    return SimpleNamespace(status=status, episode_seal_path=episode_path,
        teacher_execution_status=fields["execution_status"], teacher_task_result=fields["task_result"],
        act_data_status=fields["data_status"], act_data_reason=None)


def test_worker_result_port_requires_decision_to_match_the_teacher_result(tmp_path):
    current = lease()
    workspace = tmp_path / "w00/attempts" / current.point_id / current.attempt_id
    store = ActCollectionResultStore(workspace, current, clock=lambda: 15.)
    episode_path = failed_episode(store, tmp_path)
    fields = sealed_teacher(store, "FAILED")
    wrong = _decision(AttemptStatus.PASSED, fields, episode_path)
    with pytest.raises(ValueError, match="RESULT_TERMINAL_MISMATCH"):
        store.seal_attempt(current, wrong)
    right = _decision(AttemptStatus.FAILED, fields, episode_path)
    sealed = store.seal_attempt(current, right)
    assert ActCollectionResultVerifier({"w00": tmp_path / "w00"}, scope=scope_of(tmp_path)).verify(
        current, sealed, RunMode.EXECUTE)["status"] == "FAILED"


def test_worker_recovery_receipt_is_exact_lease_and_durable(tmp_path):
    current = lease()
    workspace = tmp_path / "w00/attempts" / current.point_id / current.attempt_id
    store = ActCollectionResultStore(workspace, current, clock=lambda: 15.)
    path = store.write_recovery_receipt(current, succeeded=True, generation=1,
                                        deadline_monotonic_s=30., clock=lambda: 16.)
    assert store.verify_recovery_receipt(path, current, succeeded=True, generation=1,
                                         deadline_monotonic_s=30., clock=lambda: 17.) is True
    assert store.verify_recovery_receipt(path, replace(current, worker_generation=2),
                                         succeeded=True, generation=2,
                                         deadline_monotonic_s=30., clock=lambda: 17.) is False
    assert store.verify_recovery_receipt(path, current, succeeded=False, generation=1,
                                         deadline_monotonic_s=30., clock=lambda: 17.) is False
    assert store.verify_recovery_receipt(path, current, succeeded=True, generation=1,
                                         deadline_monotonic_s=30., clock=lambda: 14.) is False
    path.write_text(path.read_text() + " ")
    assert store.verify_recovery_receipt(path, current, succeeded=True, generation=1,
                                         deadline_monotonic_s=30., clock=lambda: 17.) is False


def reset_receipt(current, *, reset_epoch=2, session_id="session-1"):
    return {"lease_identity": {name: getattr(current, name) for name in (
        "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
        "point_id", "attempt_id", "lease_generation")},
        "session_id": session_id, "reset_epoch": reset_epoch,
        "joint_positions": (0.,) * 7, "reset_completed_monotonic_s": 12.}


def test_worker_factory_reserves_private_episode_only_after_closed_reset(tmp_path):
    current = lease()
    root = tmp_path / "w00"
    results = ActCollectionResults({"w00": root}, clock=lambda: 15.)
    foreign = reset_receipt(current)
    foreign["lease_identity"]["worker_generation"] = 2
    with pytest.raises(ValueError, match="ACT_RESET_IDENTITY_MISMATCH"):
        results.reserve_workspace(current, foreign)
    assert not root.exists()
    invalid = reset_receipt(current)
    invalid["joint_positions"] = (0.,) * 6
    with pytest.raises(ValueError, match="ACT_RESET_JOINTS_INVALID"):
        results.reserve_workspace(current, invalid)
    assert not root.exists()
    assert results.reserve_workspace(current, reset_receipt(current)) is True
    episode_root = results.episode_root(current)
    assert episode_root == root / "attempts" / current.point_id / current.attempt_id / "working/episode"
    with pytest.raises(ValueError, match="ACT_WORKSPACE_ALREADY_RESERVED"):
        results.reserve_workspace(current, reset_receipt(current))


def test_worker_factory_requires_episode_scope_to_match_reset_receipt(tmp_path):
    current = lease()
    results = ActCollectionResults({"w00": tmp_path / "w00"}, clock=lambda: 15.)
    results.reserve_workspace(current, reset_receipt(current))
    store = results._store(current)
    path = failed_episode(store, tmp_path, session_id="wrong-session")
    decision = _decision(AttemptStatus.FAILED, sealed_teacher(store, "FAILED"), path)
    # the episode of another session is a data problem: it is graded INVALID and the Teacher result is kept
    import json
    sealed = results.seal_attempt(current, decision)
    result = json.loads((Path(sealed) / "result.json").read_bytes())
    assert result["status"] == "FAILED" and result["act_data_status"] == "INVALID"
    assert "RESULT_EPISODE_INVALID" in result["act_data_reason"]


def test_coordinator_journals_business_failed_only_after_verifier(tmp_path):
    journal = CoordinatorJournal.create(tmp_path / "journal", "batch-a")
    try:
        root = tmp_path / "w00"
        verifier = ActCollectionResultVerifier({"w00": root}, scope=scope_of(tmp_path))
        request = BatchRequest("batch-a", RunMode.EXECUTE, ("scene-1",), 1,
                                 tmp_path / "journal", BatchKind.FIRST_PASS)
        config = load_parallel_runtime_config_linux_cuda(
            PACKAGE_ROOT / "config/mujoco/parallel_batch_linux_cuda.yaml")
        coordinator = BatchCoordinator(journal, request, config=config,
                                       clock=lambda: 0., result_port=verifier)
        coordinator.register_worker("w00", generation=1)
        current = coordinator.grant_lease("w00", generation=1)
        coordinator.ack_lease(current, request_key="ack-1")
        gate = {"schema_version": 1, "kind": "POINT_INITIAL_GATE",
                "batch_id": current.batch_id, "coordinator_epoch": current.coordinator_epoch,
                "worker_id": current.worker_id, "worker_generation": current.worker_generation,
                "point_id": current.point_id, "attempt_id": current.attempt_id,
                "lease_generation": current.lease_generation, "reset_epoch": "reset-1",
                "simulation_session_id": "session-1", "reset_completed_monotonic_s": 1.,
                "source_frame_monotonic_s": 2., "canonical_joints": True,
                "no_controller_goal": True, "no_attachment": True, "no_contact": True,
                "no_stale_node": True}
        coordinator.ack_attempt_started(current, request_key="start-1", gate_summary=gate)
        workspace = coordinator.snapshot().workers["w00"].workspace
        store = ActCollectionResultStore(workspace, current, clock=lambda: 1.)
        with pytest.raises(ValueError, match="RESULT_MISSING"):
            coordinator.commit_result(current, str(workspace / "sealed"), request_key="result-1")
        sealed = store.seal(failed_episode(store, tmp_path), teacher=sealed_teacher(store, "FAILED"))
        result = coordinator.commit_result(current, str(sealed), request_key="result-1")
        assert result["status"] == "FAILED"
        assert coordinator.snapshot().points["scene-1"].terminal is True
    finally:
        journal.close()
