"""A Task 9 episode becomes a result only through its reserved lease workspace."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from so101_demo.act.recorder import EpisodeRecorder
from so101_demo.act.result_store import ActCollectionResultStore, ActCollectionResultVerifier, ResultInfraError
from so101_demo.parallel_batch.contracts import LeaseIdentity, RunMode
from so101_demo.parallel_batch.contracts import BatchKindV2, BatchRequestV2, load_parallel_runtime_config_v2
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal


PROVENANCE = {"source_sha256": "a" * 64, "scene_sha256": "b" * 64,
              "config_sha256": "c" * 64, "policy_fingerprint": "d" * 64, "seed": 3}


def lease():
    return LeaseIdentity(batch_id="batch-1", coordinator_epoch=1, worker_id="w00",
                         worker_generation=1, point_id="scene-1", attempt_id="attempt-1",
                         lease_generation=1, lease_issued_monotonic_s=10.,
                         lease_deadline_monotonic_s=20.)


def failed_episode(store):
    recorder = EpisodeRecorder(store.episode_root, session_id="session-1",
                               attempt_id=store.lease.attempt_id, reset_epoch=2,
                               provenance=PROVENANCE)
    return recorder.finish({"status": "FAILED", "reason": "search_failed",
                            "task8_success": False, "stopped_confirmed": True})


def test_exact_lease_seal_verifies_and_discovers_only_reserved_workspace(tmp_path):
    worker_root = tmp_path / "w00"
    current = lease()
    workspace = worker_root / "attempts" / current.point_id / current.attempt_id
    store = ActCollectionResultStore(workspace, current, clock=lambda: 15.)
    sealed = store.seal(failed_episode(store))
    verifier = ActCollectionResultVerifier({"w00": worker_root})
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
    sealed = store.seal(failed_episode(store))
    verifier = ActCollectionResultVerifier({"w00": worker_root})
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
    sealed = store.seal(failed_episode(store))
    verifier = ActCollectionResultVerifier({"w00": worker_root})
    episode = sealed / "episode/seal.json"
    episode.write_text(episode.read_text() + " ")
    with pytest.raises(ValueError, match="EPISODE_SEAL_HASH_MISMATCH"):
        verifier.verify(current, str(sealed), RunMode.EXECUTE)


def test_unsealed_directory_cannot_be_discovered_or_committed(tmp_path):
    current = lease()
    worker_root = tmp_path / "w00"
    workspace = worker_root / "attempts" / current.point_id / current.attempt_id
    store = ActCollectionResultStore(workspace, current, clock=lambda: 15.)
    failed_episode(store)
    verifier = ActCollectionResultVerifier({"w00": worker_root})
    assert verifier.discover(current, workspace) is None
    with pytest.raises(ValueError, match="LEASE_LOCATION_MISMATCH|RESULT_MISSING"):
        verifier.verify(current, str(store.episode_root.parent), RunMode.EXECUTE)


def test_corrupt_episode_never_becomes_business_failed_result(tmp_path):
    current = lease()
    workspace = tmp_path / "w00/attempts" / current.point_id / current.attempt_id
    store = ActCollectionResultStore(workspace, current, clock=lambda: 15.)
    episode_path = failed_episode(store)
    episode_path.write_text(episode_path.read_text() + " ")
    with pytest.raises(ResultInfraError, match="RESULT_EPISODE_INVALID"):
        store.seal(episode_path)
    assert not (workspace / "sealed").exists()


def test_coordinator_journals_business_failed_only_after_verifier(tmp_path):
    journal = CoordinatorJournal.create(tmp_path / "journal", "batch-a")
    try:
        root = tmp_path / "w00"
        verifier = ActCollectionResultVerifier({"w00": root})
        request = BatchRequestV2("batch-a", RunMode.EXECUTE, ("scene-1",), 1,
                                 tmp_path / "journal", BatchKindV2.FIRST_PASS)
        config = load_parallel_runtime_config_v2(
            Path(__file__).resolve().parents[1] / "config/mujoco/parallel_batch_v2.yaml")
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
        sealed = store.seal(failed_episode(store))
        result = coordinator.commit_result(current, str(sealed), request_key="result-1")
        assert result["status"] == "FAILED"
        assert coordinator.snapshot().points["scene-1"].terminal is True
    finally:
        journal.close()
