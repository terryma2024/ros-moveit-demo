"""Real durable Coordinator phases keep original execution clocks distinct from finalization."""

from dataclasses import asdict, replace
import hashlib
from pathlib import Path

import pytest

from act_result_teacher import sealed_teacher
from so101_demo.act.result_store import ActCollectionResultVerifier
from so101_demo.act.collection_scope import write_collection_scope
from so101_demo.cli.mujoco_parallel_batch import _ArtifactResults
from so101_demo.parallel_batch.contracts import (BatchKind, BatchRequest, RunMode,
    AttemptStatus, load_parallel_runtime_config_v3)
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.runtime.parallel_ros_runtime import ResetBoundaryReceipt
from so101_demo.act.episode_assembly import assemble_episode_capture, ProductionProducer
from test_act_continuous_capture import AcquisitionGuard, AcquisitionMinter, feed, reference
from test_act_recorder import PROVENANCE
from test_act_seal_and_downgrade import SCOPE, IDENTITY, recorder_physical_audit
from types import SimpleNamespace
from paths import PACKAGE_ROOT


@pytest.mark.parametrize("wrong_final,historical_pass", [(False, False), (True, False), (False, True)])
def test_verifier_uses_exact_durable_execution_lease_and_exact_finalizing_lease(tmp_path, wrong_final, historical_pass):
    scope = tmp_path / "scope.json"
    write_collection_scope(SCOPE, scope)
    worker = tmp_path / "w00"
    journal = CoordinatorJournal.create(tmp_path / "journal", "batch-a")
    now = {"s": 0.}
    clock = lambda: now["s"]
    try:
        verifier = ActCollectionResultVerifier({"w00": worker}, scope=scope)
        verifier.bind_execution_journal(journal)
        with pytest.raises(ValueError, match="RESULT_JOURNAL_BINDING_INVALID"):
            verifier.bind_execution_journal(journal)
        request = BatchRequest("batch-a", RunMode.EXECUTE, ("point-1",), 1,
                                tmp_path / "journal", BatchKind.FIRST_PASS)
        config = load_parallel_runtime_config_v3(PACKAGE_ROOT /
                                                 "config/mujoco/parallel_batch_v3.yaml")
        coordinator = BatchCoordinator(journal, request, config=config, result_port=verifier, clock=clock)
        coordinator.register_worker("w00", generation=1)
        grant = coordinator.grant_lease("w00", generation=1)
        now["s"] = 1.
        initializing = coordinator.ack_lease(grant, request_key="init").lease
        results = _ArtifactResults({"w00": worker}, RunMode.EXECUTE, collection_scope=scope, clock=clock)
        if not historical_pass:
            results.reserve_workspace(initializing, ResetBoundaryReceipt("reset-2", "session-1", 1.1, .1))
        gate = {"schema_version": 1, "kind": "POINT_INITIAL_GATE", **{
            name: getattr(initializing, name) for name in ("batch_id", "coordinator_epoch", "worker_id",
                "worker_generation", "point_id", "attempt_id", "lease_generation")},
            "reset_epoch": "reset-2", "simulation_session_id": "session-1",
            "reset_completed_monotonic_s": 1.1, "source_frame_monotonic_s": 2.9,
            **dict.fromkeys(("canonical_joints", "no_controller_goal", "no_attachment", "no_contact",
                              "no_stale_node"), True)}
        now["s"] = 3.
        executing = coordinator.ack_attempt_started(initializing, request_key="start", gate_summary=gate).lease
        if historical_pass:
            # The archival unreserved v1 publisher is still readable. It is not
            # the selected default publisher and cannot satisfy a bound live Coordinator.
            from so101_demo.act.result_store import ActCollectionResultStore
            workspace = worker / "attempts" / executing.point_id / executing.attempt_id
            legacy = ActCollectionResultStore(workspace, executing, clock=clock,
                audit_manifest=workspace / "working/episode/audit/audit-manifest.json", scope=scope)
            root = legacy.episode_root
        else:
            root = results.workspace(executing).path / "episode"
        capture = assemble_episode_capture(sampler=ProductionProducer(), guard=AcquisitionGuard(),
            physical_audit=lambda t: {**recorder_physical_audit(t), "attempt_id": executing.attempt_id},
            identity={**IDENTITY, "attempt_id": executing.attempt_id, "lease": asdict(executing)},
            provenance=PROVENANCE, inputs={"inputs_sha256": "a" * 64}, episode_root=root,
            scope=SCOPE, scope_path=str(root / "audit/source.json"), monotonic=lambda: 0.)
        capture.start("session-1", executing.attempt_id, 2, 1.)
        minter = AcquisitionMinter()
        for t in (1., 1.1, 1.2, 1.3):
            for camera in ("head", "wrist"):
                feed(capture, minter, camera=camera, stamp_s=t, session="session-1", reset_epoch=2)
            capture.on_reference(reference(t + .1))
            capture.drain()
        capture.finish(1.3, window={"start_s": 1., "end_s": 1.3, "label_cutoff_s": 1.1},
            outcome={"status": "PASSED" if historical_pass else "FAILED", "reason": "fixture_stop",
                     "task8_success": historical_pass,
                     "stopped_confirmed": True})
        now["s"] = 4.
        if historical_pass:
            location = str(legacy.seal(root / "seal.json", teacher=sealed_teacher(legacy, "PASSED")))
        else:
            fields = sealed_teacher(SimpleNamespace(working=results.workspace(executing).path), "FAILED")
            location = results.seal_attempt(executing, SimpleNamespace(
                status=AttemptStatus.FAILED, reason="fixture_stop", physical_action_proven_absent=False,
                teacher_execution_status=fields["execution_status"], teacher_task_result=fields["task_result"],
                act_data_status=fields["data_status"], act_data_reason=None))
        final = coordinator.begin_finalizing(executing, request_key="final").lease
        assert final.lease_deadline_monotonic_s != executing.lease_deadline_monotonic_s
        if historical_pass:
            with pytest.raises(ValueError, match="EPISODE_PHYSICAL_READBACK_INVALID"):
                coordinator.commit_result(final, location, request_key="no-native-pass")
            assert not any(event.type == "RESULT_COMMITTED" for event in journal.replay().events)
        elif wrong_final:
            with pytest.raises(ValueError, match="RESULT_PHASE_LEASE_MISMATCH"):
                verifier.verify(replace(final, lease_deadline_monotonic_s=final.lease_deadline_monotonic_s + 1.),
                                location, RunMode.EXECUTE)
        else:
            assert verifier.verify(final, location, RunMode.EXECUTE)["status"] == "FAILED"
            original = journal.replay().events
            assert any(event.type == "ATTEMPT_STARTED" for event in original)
            assert any(event.type == "FINALIZING_STARTED" for event in original)
            assert journal.replay().events == original
            committed = coordinator.commit_result(final, location, request_key="fixture-commit")
            assert committed["status"] is AttemptStatus.FAILED
            actual = hashlib.sha256((Path(location) / "result.json").read_bytes()).hexdigest()
            assert committed["sha256"] == actual
            disk = CoordinatorJournal.read_only_replay(journal.root, journal.batch_id)
            rows = [event for event in disk.events if event.type == "RESULT_COMMITTED"]
            assert len(rows) == 1 and rows[0].payload["response"]["sha256"] == actual
            assert rows[0].payload["response"]["location"] == location
    finally:
        journal.close()
