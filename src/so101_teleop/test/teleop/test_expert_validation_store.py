from dataclasses import replace
import hashlib
import os
import stat
from pathlib import Path

import pytest

from so101_teleop.expert_validation.models import (
    BatchBinding,
    CampaignBinding,
    CleanupReceipt,
    ExecutionOwnerIntent,
    PreflightReceipt,
    UpstreamCursor,
)
from so101_teleop.expert_validation.store import (
    CommandOutcomeUnknown,
    StoreConflict,
    SupervisorStore,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def test_private_database_rejects_external_hard_link_without_changing_alias(tmp_path):
    outside = tmp_path / "unbound.sqlite3"
    outside.write_bytes(b"unbound database")
    outside.chmod(0o640)
    root = tmp_path / "private-store"
    root.mkdir(mode=0o700)
    os.link(outside, root / "supervisor.sqlite3")
    with pytest.raises(StoreConflict, match="STORE_DATABASE_INVALID"):
        SupervisorStore.open(root)
    assert outside.read_bytes() == b"unbound database"
    assert stat.S_IMODE(outside.stat().st_mode) == 0o640


def _manifest(store, suffix="1"):
    manifest_id = "manifest-" + suffix
    store.record_manifest(
        manifest_id,
        {"schema_version": 1, "selection": ["task_start"]},
        source_config_sha256=SHA_A,
        created_at_ns=1,
    )
    return manifest_id


def _receipt(store, root, campaign_id="campaign-1", suffix="1"):
    manifest_id = _manifest(store, suffix)
    receipt = PreflightReceipt(
        receipt_id="receipt-" + suffix,
        campaign_id=campaign_id,
        manifest_id=manifest_id,
        canonical_start_request_sha256=SHA_A,
        receipt={"admitted": True},
        expires_at_monotonic_ns=10_000_000_000,
    )
    store.record_preflight_receipt(receipt)
    return receipt


def _binding(root, campaign_id="campaign-1", batch_id="batch-1", suffix="1"):
    campaign = CampaignBinding(
        campaign_id=campaign_id,
        manifest_id="manifest-" + suffix,
        executor_id="operator",
        operation_id="operation-1",
        executor_config_sha256=SHA_A,
        execution_mode="PARALLEL",
        execution_config={"worker_count": 2, "max_points_per_worker": 10},
        preflight_receipt_id="receipt-" + suffix,
    )
    batch = BatchBinding(
        batch_id=batch_id,
        campaign_id=campaign_id,
        batch_kind="FIRST_PASS",
        point_id=None,
        journal_root=(root / "journal" / batch_id).resolve(),
        coordinator_epoch=4,
    )
    return campaign, batch


def _prepare(store, root, campaign_id="campaign-1", batch_id="batch-1", suffix="1"):
    receipt = _receipt(store, root, campaign_id, suffix)
    campaign, batch = _binding(root, campaign_id, batch_id, suffix)
    store.consume_preflight_and_bind_campaign_batch(
        receipt.receipt_id,
        SHA_A,
        campaign,
        batch,
        now_monotonic_ns=1,
    )
    return campaign, batch


def test_reopen_returns_completed_idempotent_command(tmp_path):
    root = tmp_path.resolve()
    store = SupervisorStore.open(root)
    store.begin_command("cmd-1", SHA_A, "START_CAMPAIGN")
    store.finish_command("cmd-1", {"campaign_id": "campaign-1"})
    store.close()

    reopened = SupervisorStore.open(root)
    try:
        assert reopened.repeat_command("cmd-1", SHA_A) == {
            "campaign_id": "campaign-1"
        }
    finally:
        reopened.close()


def test_same_id_different_payload_is_rejected(tmp_path):
    store = SupervisorStore.open(tmp_path.resolve())
    try:
        store.begin_command("cmd-1", SHA_A, "START_CAMPAIGN")
        with pytest.raises(StoreConflict, match="COMMAND_ID_REUSED"):
            store.repeat_command("cmd-1", SHA_B)
    finally:
        store.close()


def test_in_progress_command_has_unknown_outcome_after_reopen(tmp_path):
    root = tmp_path.resolve()
    store = SupervisorStore.open(root)
    store.begin_command("cmd-1", SHA_A, "START_CAMPAIGN")
    store.close()
    reopened = SupervisorStore.open(root)
    try:
        with pytest.raises(CommandOutcomeUnknown, match="COMMAND_OUTCOME_UNKNOWN"):
            reopened.repeat_command("cmd-1", SHA_A)
    finally:
        reopened.close()


def test_reopen_recovers_owner_and_retry_cursor_without_memory_state(tmp_path):
    root = tmp_path.resolve()
    store = SupervisorStore.open(root)
    _prepare(store, root)
    intent = ExecutionOwnerIntent(
        batch_id="batch-1",
        owner_kind="COORDINATOR",
        spawn_token="spawn-a",
        expected_executable="so101_parallel_batch",
        argv_sha256=SHA_A,
        environment_sha256=SHA_B,
        source_commit="1" * 40,
        install_prefix=Path("/opt/validation"),
        runtime_sha256="c" * 64,
        control_socket=(root / "control.sock").resolve(),
    )
    store.record_execution_owner_intent(intent)
    store.acknowledge_execution_owner(
        batch_id="batch-1",
        pid=123,
        pgid=123,
        started_ticks=99,
        coordinator_epoch=4,
    )
    store.enqueue_retries("campaign-1", ["sample_05", "sample_14"])
    store.close()

    reopened = SupervisorStore.open(root)
    try:
        assert reopened.owned_execution("batch-1").spawn_token == "spawn-a"
        assert reopened.owned_execution("batch-1").pid == 123
        assert reopened.next_retry("campaign-1").point_id == "sample_05"
    finally:
        reopened.close()


def test_cleanup_and_retry_advance_are_one_transaction(tmp_path):
    root = tmp_path.resolve()
    store = SupervisorStore.open(root)
    try:
        _prepare(store, root)
        store.enqueue_retries("campaign-1", ["sample_05"])
        retry_batch = BatchBinding(
            batch_id="retry-1",
            campaign_id="campaign-1",
            batch_kind="FULL_RESTART_RETRY",
            point_id="sample_05",
            journal_root=(root / "journal/retry-1").resolve(),
            coordinator_epoch=1,
        )
        store.bind_retry_batch(retry_batch)
        store.record_cleanup_and_advance_retry(
            CleanupReceipt("campaign-1", "retry-1", "sample_05", "d" * 64)
        )
        assert store.next_retry("campaign-1") is None
        assert store.batch("retry-1").cleanup_receipt_sha256 == "d" * 64
    finally:
        store.close()


def test_accepted_cursor_is_idempotent_and_owner_monotonic(tmp_path):
    root = tmp_path.resolve()
    store = SupervisorStore.open(root)
    try:
        _prepare(store, root)
        cursor = UpstreamCursor(
            batch_id="batch-1",
            owner_kind="COORDINATOR",
            owner_epoch_or_generation=4,
            segment_id="segment-1",
            event_id="event-7",
            frame_sha256=SHA_A,
        )
        store.accept_upstream_cursor(cursor)
        store.accept_upstream_cursor(cursor)
        with pytest.raises(StoreConflict, match="UPSTREAM_CURSOR_CONFLICT"):
            store.accept_upstream_cursor(replace(cursor, frame_sha256=SHA_B))
    finally:
        store.close()


def test_second_writer_is_rejected_before_sqlite_open(tmp_path):
    root = tmp_path.resolve()
    first = SupervisorStore.open(root)
    try:
        with pytest.raises(StoreConflict, match="VALIDATION_SUPERVISOR_ACTIVE"):
            SupervisorStore.open(root)
    finally:
        first.close()


def test_schema_has_no_second_truth_for_worker_point_or_broker_state(tmp_path):
    store = SupervisorStore.open(tmp_path.resolve())
    try:
        names = store.table_names()
        assert "worker_leases" not in names
        assert "point_results" not in names
        assert "broker_health" not in names
        assert {"upstream_cursors", "adaptive_projection_cache"}.issubset(names)
    finally:
        store.close()


def test_sensitive_control_store_database_is_private_before_any_binding(tmp_path):
    store = SupervisorStore.open(tmp_path.resolve())
    try:
        assert stat.S_IMODE((store.root / "supervisor.sqlite3").stat().st_mode) == 0o600
        assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    finally:
        store.close()


# --------------------------------------------------------------------------------------
# Task 5: one transaction for idempotency, reducer state, attempts and accepted cursor
# --------------------------------------------------------------------------------------


class _VerifiedEvent:
    def __init__(self, event_type, payload, sequence, batch_id):
        self.type = event_type
        self.payload = payload
        self.sequence = sequence
        self.coordinator_epoch = 1
        self.frame_sha256 = hashlib.sha256(f"{batch_id}:{sequence}".encode()).hexdigest()
        self.batch_id = batch_id


def _projection_events(batch_id, campaign_id="campaign-1"):
    return (
        _VerifiedEvent("CAMPAIGN_STARTED", {
            "campaign_id": campaign_id, "batch_id": batch_id,
            "runtime_identity_sha256": SHA_A, "config_sha256": SHA_B}, 1, batch_id),
        _VerifiedEvent("POINT_LEASED", {"point_id": "p1", "attempt_id": "p1-attempt-1"}, 2, batch_id),
        _VerifiedEvent("RESULT_COMMITTED", {
            "point_id": "p1", "attempt_id": "p1-attempt-1",
            "result_sha256": SHA_A, "outcome": "PASSED"}, 3, batch_id),
    )


def _projection_cursor(batch_id, frame=SHA_A):
    return UpstreamCursor(
        batch_id=batch_id, owner_kind="COORDINATOR", owner_epoch_or_generation=1,
        segment_id="segment-1", event_id="event-3", frame_sha256=frame)


def _reducer_module():
    import importlib
    return importlib.import_module("so101_teleop.expert_validation.reducer")


def test_projection_batch_is_transactional_idempotent_and_resumable(tmp_path):
    root = tmp_path.resolve()
    store = SupervisorStore.open(root)
    try:
        _campaign, batch = _prepare(store, root)
        events = _projection_events(batch.batch_id)
        cursor = _projection_cursor(batch.batch_id)
        reducer = _reducer_module().CanonicalCampaignReducer()

        state = store.accept_projection_batch(
            batch_id=batch.batch_id, expected_cursor=None, events=events,
            next_cursor=cursor, reducer=reducer)
        assert state.points["p1"].status.value == "PASSED"
        assert len(state.attempts) == 1

        replayed = store.accept_projection_batch(
            batch_id=batch.batch_id, expected_cursor=cursor, events=events,
            next_cursor=cursor, reducer=reducer)
        assert len(replayed.attempts) == 1
        assert replayed.as_document() == state.as_document()

        with pytest.raises(StoreConflict, match="PROJECTION_CURSOR_MISMATCH"):
            store.accept_projection_batch(
                batch_id=batch.batch_id,
                expected_cursor=replace(cursor, frame_sha256=SHA_B),
                events=(), next_cursor=cursor, reducer=reducer)

        _campaign2, batch2 = _prepare(
            store, root, campaign_id="campaign-2", batch_id="batch-2", suffix="2")

        class Exploding(_reducer_module().CanonicalCampaignReducer):
            def apply(self, state, event):
                if event.type == "RESULT_COMMITTED":
                    raise RuntimeError("injected failure after the reducer, before the cursor")
                return super().apply(state, event)

        with pytest.raises(RuntimeError):
            store.accept_projection_batch(
                batch_id=batch2.batch_id, expected_cursor=None,
                events=_projection_events(batch2.batch_id, campaign_id="campaign-2"),
                next_cursor=_projection_cursor(batch2.batch_id), reducer=Exploding())
        rolled_back = store.read_projection_state(batch2.batch_id)
        assert rolled_back.state is None and rolled_back.cursor is None

        snapshot = store.read_projection_state(batch.batch_id)
        assert snapshot.state.as_document() == state.as_document()
        assert snapshot.cursor == cursor
    finally:
        store.close()

    reopened = SupervisorStore.open(root)
    try:
        recovered = reopened.read_projection_state(batch.batch_id)
        assert recovered.state.as_document() == state.as_document()
        assert recovered.cursor == cursor
        after_restart = reopened.accept_projection_batch(
            batch_id=batch.batch_id, expected_cursor=cursor, events=events,
            next_cursor=cursor, reducer=_reducer_module().CanonicalCampaignReducer())
        assert len(after_restart.attempts) == 1
    finally:
        reopened.close()


# --------------------------------------------------------------------------------------
# Task 6: a recovery fence carries the exact generation its reaper committed
# --------------------------------------------------------------------------------------


def test_recovery_fence_takes_the_exact_generation_the_reaper_committed(tmp_path):
    root = tmp_path.resolve()
    store = SupervisorStore.open(root)
    try:
        _prepare(store, root)
        reason = "OWNER_TREE_UNRESOLVED generation 4: WORKER INTENT_UNCONFIRMED"

        store.record_recovery_fence(
            "campaign-1", "batch-1", reason=reason, command_id="recover-1-4", generation=4
        )

        fence = store.recovery_fence("campaign-1")
        assert fence["reason"] == reason
        assert fence["command_id"] == "recover-1-4"
        # The keyword is optional: the callers that predate it are unchanged.
        store.record_recovery_fence("campaign-1", "batch-1", reason=reason, command_id="recover-1-4")
        with pytest.raises(StoreConflict, match="RECOVERY_FENCE_GENERATION_INVALID"):
            store.record_recovery_fence(
                "campaign-1", "batch-1", reason=reason, command_id="recover-1-4", generation=0
            )
        with pytest.raises(StoreConflict, match="RECOVERY_FENCE_GENERATION_INVALID"):
            store.record_recovery_fence(
                "campaign-1", "batch-1", reason=reason, command_id="recover-1-4", generation=True
            )
        assert store.recovery_fence("campaign-1")["command_id"] == "recover-1-4"
    finally:
        store.close()
