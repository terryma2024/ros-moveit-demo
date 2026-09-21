from dataclasses import replace
import hashlib
import os
import stat
from pathlib import Path
from types import SimpleNamespace
import time

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


# --------------------------------------------------------------------------------------
# Task 9: one-time retry admission - one transaction, one command, one owner intent
# --------------------------------------------------------------------------------------

from so101_teleop.expert_validation.execution_context import (  # noqa: E402
    CandidateExecutionContext,
    ProductionExecutionContext,
    install_binding_sha256,
)
from so101_teleop.expert_validation.models import RetryStartRequest  # noqa: E402
from so101_teleop.expert_validation.owner_tree import (  # noqa: E402
    ConfirmedOwnerProcess,
    OwnerIntent,
)
import json as _json  # noqa: E402

SHA_CATALOG = "1" * 64
SHA_SELECTION = "2" * 64
SHA_RESULT = "3" * 64
SHA_CONFIG = "4" * 64
SHA_CLOSURE = "5" * 64

POINT_IDS = ("p1", "p2")

RETRY_PROFILE = "MPS_W1_FULL_RESTART_RETRY"


def point_result_sha256(point_id, default=SHA_RESULT):
    """The durable result digest one point's committed frame carries."""

    if point_id == "p1":
        return default
    return hashlib.sha256(point_id.encode("utf-8")).hexdigest()


def _retry_events(
    batch_id,
    *,
    campaign_id="campaign-1",
    outcome="FAILED",
    outcomes=None,
    terminal=True,
    cleanup=True,
    attempt_validity=None,
    infrastructure_outcome=None,
    result_sha256=SHA_RESULT,
):
    """The canonical event frames of one first pass, one committed result per selected point.

    An ``UNRUN`` point gets no frame at all: a selected point with no event is exactly what the
    reducer leaves unrun, so it is the honest way to build that case.
    """

    events = [
        _VerifiedEvent("CAMPAIGN_STARTED", {
            "campaign_id": campaign_id, "batch_id": batch_id,
            "runtime_identity_sha256": SHA_A, "config_sha256": SHA_CONFIG}, 1, batch_id),
    ]
    sequence = 2
    for point_id, point_outcome in dict(outcomes or {"p1": outcome}).items():
        if point_outcome == "UNRUN":
            continue
        attempt_id = f"{point_id}-attempt-1"
        digest = point_result_sha256(point_id, result_sha256)
        events.append(_VerifiedEvent("POINT_LEASED", {
            "point_id": point_id, "attempt_id": attempt_id,
            "worker_id": "worker-01", "worker_generation": 1}, sequence, batch_id))
        sequence += 1
        events.append(_VerifiedEvent("ATTEMPT_STARTED", {
            "point_id": point_id, "attempt_id": attempt_id,
            **({"attempt_validity": attempt_validity} if attempt_validity else {}),
            **({"infrastructure_outcome": infrastructure_outcome}
               if infrastructure_outcome else {})}, sequence, batch_id))
        sequence += 1
        events.append(_VerifiedEvent("RESULT_COMMITTED", {
            "point_id": point_id, "attempt_id": attempt_id,
            "result_sha256": digest, "outcome": point_outcome,
            **({"attempt_validity": attempt_validity} if attempt_validity else {})},
            sequence, batch_id))
        sequence += 1
    if terminal:
        events.append(_VerifiedEvent(
            "BATCH_TERMINAL", {"business_terminal": "POINTS_COMPLETE"}, sequence, batch_id))
        sequence += 1
    if cleanup:
        events.append(_VerifiedEvent(
            "CLEANUP_COMMITTED", {"cleanup_complete": True}, sequence, batch_id))
    return tuple(events)


def _retry_fixture(
    tmp_path,
    *,
    events=None,
    cleaned_batch=True,
    enqueue=POINT_IDS,
    production=False,
    with_projection=True,
    **context_changes,
):
    """A terminal-clean first pass with one committed business FAILED point, and its context."""

    root = tmp_path.resolve()
    store = SupervisorStore.open((root / "store").resolve())
    receipt = _receipt(store, root)
    manifest_id = receipt.manifest_id
    campaign, batch = _binding(root)
    store.consume_preflight_and_bind_campaign_batch(
        receipt.receipt_id, SHA_A, campaign, batch, now_monotonic_ns=1)
    store._connection.execute(
        "UPDATE manifests SET canonical_json = ? WHERE manifest_id = ?",
        (
            _json_document({
                "catalog_sha256": SHA_CATALOG,
                "selection_sha256": SHA_SELECTION,
                "point_ids": list(POINT_IDS),
            }),
            manifest_id,
        ),
    )
    if events is None:
        events = _retry_events("batch-1")
    if with_projection:
        store.accept_projection_batch(
            batch_id="batch-1",
            expected_cursor=None,
            events=events,
            next_cursor=UpstreamCursor(
                batch_id="batch-1", owner_kind="COORDINATOR", owner_epoch_or_generation=1,
                segment_id="segment-1", event_id="event-last", frame_sha256=SHA_A),
            reducer=_reducer_module().CanonicalCampaignReducer(),
        )
    if cleaned_batch:
        store.record_batch_cleanup("batch-1", "d" * 64)
    if enqueue:
        store.enqueue_retries("campaign-1", enqueue)

    runtime_closure = SHA_CLOSURE
    # The store compares against the real monotonic clock, so the fixture's window and lease are
    # relative to it: an expired object is the one that names an instant already behind us.
    values = dict(
        campaign_id="campaign-1",
        batch_id="retry-001",
        manifest_id=manifest_id,
        execution_profile=RETRY_PROFILE,
        schema_version=5,
        batch_kind="FULL_RESTART_RETRY",
        worker_count=1,
        config_sha256=SHA_CONFIG,
        runtime_closure_sha256=runtime_closure,
        evidence_root=root,
        owner_generation=1,
        command_id="cmd-retry-1",
        issued_at_monotonic_ns=time.monotonic_ns(),
        expires_at_monotonic_ns=time.monotonic_ns() + 3_600_000_000_000,
        max_runs=2,
    )
    values.update(context_changes)
    if production:
        install_prefix = (root / "install").resolve()
        values.pop("max_runs", None)
        store.insert_lease("lease-1", "session-1", 1, values["expires_at_monotonic_ns"])
        context = ProductionExecutionContext(
            context_id="production-context-1",
            service_session_id="session-1",
            lease_id="lease-1",
            lease_generation=1,
            install_prefix=install_prefix,
            install_binding_sha256=install_binding_sha256(
                install_prefix=install_prefix, runtime_closure_sha256=runtime_closure),
            **values,
        )
    else:
        context = CandidateExecutionContext(
            context_id="candidate-context-1",
            task_id="task-9",
            dispatch_id="dispatch-1",
            **values,
        )
    request = RetryStartRequest(
        command_id=context.command_id,
        campaign_id=context.campaign_id,
        batch_id=context.batch_id,
        point_id="p1",
        original_batch_id="batch-1",
        original_catalog_sha256=SHA_CATALOG,
        original_selection_sha256=SHA_SELECTION,
        original_result_sha256=SHA_RESULT,
        execution_profile=context.execution_profile,
        schema_version=context.schema_version,
        batch_kind=context.batch_kind,
        config_sha256=context.config_sha256,
        runtime_closure_sha256=context.runtime_closure_sha256,
        worker_count=context.worker_count,
        evidence_root=context.evidence_root,
        install_prefix=getattr(context, "install_prefix", (root / "install").resolve()),
        owner_generation=context.owner_generation,
        created_at_ns=1,
    )
    intent = OwnerIntent.for_argv(
        campaign_id=request.campaign_id,
        batch_id=request.batch_id,
        role="ADAPTER",
        generation=request.owner_generation,
        spawn_token="spawn-retry-1",
        argv=("so101_parallel_batch", "--batch-id", request.batch_id),
        created_at_ns=1,
    )
    return store, request, context, intent


def _json_document(value):
    return _json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_admit_retry_consumes_the_command_and_writes_batch_queue_and_intent(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        binding = store.admit_retry(request=request, context=context, spawn_intent=intent)

        assert binding.point_id == "p1" and binding.batch_id == "retry-001"
        assert binding.original_outcome == "FAILED"
        assert binding.original_result_sha256 == SHA_RESULT
        assert binding.context_kind == "CANDIDATE"
        # One command row, already consumed, whose payload is the committed binding.
        commands = store._connection.execute(
            "SELECT state FROM commands WHERE command_id = ?", (request.command_id,)
        ).fetchall()
        assert [row["state"] for row in commands] == ["IN_PROGRESS"]
        # The retry binding: a durable batch, a running queue entry and the owner intent.
        batch = store.batch("retry-001")
        assert batch.batch_kind == "FULL_RESTART_RETRY" and batch.point_id == "p1"
        assert batch.journal_root == (
            request.evidence_root / "campaigns" / "campaign-1" / "retry-001"
        ).resolve()
        item = store.retry_items("campaign-1")[0]
        assert (item.point_id, item.state, item.batch_id) == ("p1", "RUNNING", "retry-001")
        assert store.owner_intent(intent.spawn_token) == intent
        # The admitted selection binding is durable as its own record.
        admission = store.retry_admission(request.command_id)
        assert admission["binding_sha256"] == binding.binding_sha256
        assert admission["execution_profile"] == RETRY_PROFILE
        assert admission["worker_count"] == 1
    finally:
        store.close()


def test_admit_retry_refuses_a_foreign_object_instead_of_a_context(tmp_path):
    store, request, _context, intent = _retry_fixture(tmp_path)
    try:
        with pytest.raises(StoreConflict, match="RETRY_CONTEXT_KIND"):
            store.admit_retry(
                request=request, context=object(), spawn_intent=intent)
        assert store.retry_admission(request.command_id) is None
    finally:
        store.close()


def test_admit_retry_refuses_a_spawn_intent_bound_to_another_batch(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        with pytest.raises(StoreConflict, match="RETRY_SPAWN_INTENT_MISMATCH"):
            store.admit_retry(
                request=request, context=context,
                spawn_intent=replace(intent, batch_id="retry-999"),
            )
        with pytest.raises(StoreConflict, match="RETRY_OWNER_GENERATION_MISMATCH"):
            store.admit_retry(
                request=request, context=context, spawn_intent=replace(intent, generation=4))
        assert store.next_retry("campaign-1").state == "QUEUED"
    finally:
        store.close()


def test_admit_retry_refuses_an_expired_context(tmp_path):
    store, request, context, intent = _retry_fixture(
        tmp_path, issued_at_monotonic_ns=1, expires_at_monotonic_ns=2)
    try:
        with pytest.raises(StoreConflict, match="RETRY_CONTEXT_EXPIRED"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert store.next_retry("campaign-1").state == "QUEUED"
    finally:
        store.close()


def test_a_refused_admission_never_consumes_its_command(tmp_path):
    store, request, context, intent = _retry_fixture(
        tmp_path, issued_at_monotonic_ns=1, expires_at_monotonic_ns=2)
    try:
        with pytest.raises(StoreConflict, match="RETRY_CONTEXT_EXPIRED"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
        live = replace(
            context,
            issued_at_monotonic_ns=time.monotonic_ns(),
            expires_at_monotonic_ns=time.monotonic_ns() + 3_600_000_000_000,
        )
        binding = store.admit_retry(request=request, context=live, spawn_intent=intent)
        assert binding.command_id == request.command_id
    finally:
        store.close()


def test_admit_retry_refuses_a_replayed_command(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        store.admit_retry(request=request, context=context, spawn_intent=intent)
        with pytest.raises(StoreConflict, match="RETRY_COMMAND_ALREADY_CONSUMED"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()


def test_admit_retry_refuses_a_command_id_reused_for_a_different_retry(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        store.admit_retry(request=request, context=context, spawn_intent=intent)
        with pytest.raises(StoreConflict, match="RETRY_COMMAND_ID_REUSED"):
            store.admit_retry(
                request=replace(request, point_id="p2", batch_id="retry-002"),
                context=replace(context, batch_id="retry-002"), spawn_intent=intent,
            )
    finally:
        store.close()


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("campaign_id", "campaign-other", "RETRY_CAMPAIGN_MISMATCH"),
        ("batch_id", "retry-002", "RETRY_BATCH_MISMATCH"),
        ("execution_profile", "MPS_W1_FIRST_PASS", "RETRY_PROFILE_MISMATCH"),
        ("schema_version", 6, "RETRY_SCHEMA_MISMATCH"),
        ("config_sha256", SHA_A, "RETRY_CONFIG_MISMATCH"),
        ("runtime_closure_sha256", SHA_A, "RETRY_RUNTIME_CLOSURE_MISMATCH"),
        ("owner_generation", 2, "RETRY_OWNER_GENERATION_MISMATCH"),
    ],
)
def test_admit_retry_refuses_a_request_that_drifted_from_its_context(tmp_path, field, value, code):
    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        with pytest.raises(StoreConflict, match=code):
            store.admit_retry(
                request=replace(request, **{field: value}), context=context, spawn_intent=intent)
        if field == "batch_id":
            with pytest.raises(StoreConflict, match=code):
                store.admit_retry(
                    request=request, context=replace(context, **{field: value}),
                    spawn_intent=intent)
        assert store.retry_admission(request.command_id) is None
    finally:
        store.close()


def test_a_retry_can_never_name_another_worker_count_or_batch_kind(tmp_path):
    """Both coordinates are closed at the two types, so no replay can move them."""

    from so101_teleop.expert_validation.execution_context import (
        CandidateExecutionContext,
        ExecutionContextError,
    )

    values = dict(
        context_id="candidate-context-1", task_id="task-9", dispatch_id="dispatch-1",
        campaign_id="campaign-1", batch_id="retry-001", manifest_id="manifest-1",
        execution_profile=RETRY_PROFILE, schema_version=5, batch_kind="FULL_RESTART_RETRY",
        worker_count=2, config_sha256=SHA_CONFIG, runtime_closure_sha256=SHA_CLOSURE,
        evidence_root=tmp_path.resolve(), owner_generation=1, command_id="cmd-retry-1",
        issued_at_monotonic_ns=1_000, expires_at_monotonic_ns=10_000_000_000_000, max_runs=1,
    )
    with pytest.raises(ExecutionContextError, match="CONTEXT_PROFILE_INVALID"):
        CandidateExecutionContext(**values)

    store, request, _context, _intent = _retry_fixture(tmp_path)
    try:
        with pytest.raises(ValueError, match="RETRY_WORKER_COUNT"):
            replace(request, worker_count=2)
        with pytest.raises(ValueError, match="RETRY_BATCH_KIND"):
            replace(request, batch_kind="FIRST_PASS")
        with pytest.raises(ExecutionContextError, match="CONTEXT_PROFILE_INVALID"):
            replace(_context, batch_kind="FIRST_PASS")
    finally:
        store.close()


def test_admit_retry_refuses_a_context_naming_another_manifest(tmp_path):
    """The manifest belongs to the campaign row; a context cannot substitute one."""

    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        with pytest.raises(StoreConflict, match="RETRY_MANIFEST_MISMATCH"):
            store.admit_retry(
                request=request, context=replace(context, manifest_id="manifest-other"),
                spawn_intent=intent)
        assert store.retry_admission(request.command_id) is None
    finally:
        store.close()


def test_admit_retry_refuses_an_evidence_root_the_context_does_not_bind(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path)
    other = (tmp_path / "other").resolve()
    other.mkdir()
    try:
        with pytest.raises(StoreConflict, match="RETRY_EVIDENCE_ROOT_MISMATCH"):
            store.admit_retry(
                request=replace(request, evidence_root=other), context=context,
                spawn_intent=intent)
    finally:
        store.close()


def test_a_candidate_context_never_authorizes_more_than_its_max_runs(tmp_path):
    store, request, context, intent = _retry_fixture(
        tmp_path, events=_retry_events("batch-1", outcomes={"p1": "FAILED", "p2": "FAILED"}),
        max_runs=1,
    )
    try:
        store.admit_retry(request=request, context=context, spawn_intent=intent)
        # The spawn confirmed the one admitted owner, so only the run budget is left.
        store.confirm_owner_process(
            ConfirmedOwnerProcess(
                spawn_token=intent.spawn_token, pid=4321, pgid=4321, started_ticks=7,
                command_sha256=SHA_A, confirmed_at_ns=2,
            )
        )
        second = replace(
            request, command_id="cmd-retry-2", batch_id="retry-002", point_id="p2",
            original_result_sha256=point_result_sha256("p2"),
        )
        with pytest.raises(StoreConflict, match="RETRY_MAX_RUNS_EXCEEDED"):
            store.admit_retry(
                request=second, context=replace(context, command_id="cmd-retry-2",
                                                batch_id="retry-002"),
                spawn_intent=replace(intent, spawn_token="spawn-retry-2", batch_id="retry-002"),
            )
    finally:
        store.close()


def test_a_production_context_needs_a_live_lease_bound_to_its_own_session(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path, production=True)
    try:
        store._connection.execute("UPDATE leases SET state = 'RESTART_INVALIDATED'")
        with pytest.raises(StoreConflict, match="RETRY_LEASE_REQUIRED"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)

        store._connection.execute("UPDATE leases SET state = 'ACTIVE', generation = 2")
        with pytest.raises(StoreConflict, match="RETRY_LEASE_MISMATCH"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)

        store._connection.execute("UPDATE leases SET generation = 1, expires_monotonic_ns = 1")
        with pytest.raises(StoreConflict, match="RETRY_LEASE_EXPIRED"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)

        store._connection.execute(
            "UPDATE leases SET expires_monotonic_ns = ?, service_session_id = 'session-other'",
            (time.monotonic_ns() + 3_600_000_000_000,))
        with pytest.raises(StoreConflict, match="RETRY_LEASE_MISMATCH"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)

        store._connection.execute(
            "UPDATE leases SET service_session_id = 'session-1'")
        binding = store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert binding.context_kind == "PRODUCTION"
        assert binding.lease_generation == 1
    finally:
        store.close()


def test_a_production_context_from_another_installed_copy_is_refused(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path, production=True)
    try:
        other = (tmp_path / "install-other").resolve()
        with pytest.raises(StoreConflict, match="RETRY_INSTALL_BINDING_MISMATCH"):
            store.admit_retry(
                request=replace(request, install_prefix=other), context=context,
                spawn_intent=intent)
        assert store.retry_admission(request.command_id) is None
    finally:
        store.close()


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        ("PASSED", "RETRY_ORIGINAL_NOT_FAILED"),
        ("INDETERMINATE", "RETRY_ORIGINAL_INDETERMINATE"),
    ],
)
def test_admit_retry_refuses_a_committed_result_that_is_not_a_business_failure(
    tmp_path, outcome, code
):
    store, request, context, intent = _retry_fixture(
        tmp_path, events=_retry_events("batch-1", outcome=outcome))
    try:
        with pytest.raises(StoreConflict, match=code):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()


def test_admit_retry_refuses_a_point_that_never_ran(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path, enqueue=("p2",))
    try:
        with pytest.raises(StoreConflict, match="RETRY_ORIGINAL_UNRUN"):
            store.admit_retry(
                request=replace(request, point_id="p2"), context=context, spawn_intent=intent)
    finally:
        store.close()


def test_admit_retry_refuses_an_invalid_attempt_and_an_infrastructure_failure(tmp_path):
    store, request, context, intent = _retry_fixture(
        tmp_path, events=_retry_events("batch-1", attempt_validity="INVALID"))
    try:
        with pytest.raises(StoreConflict, match="RETRY_ORIGINAL_INVALID"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()

    store, request, context, intent = _retry_fixture(
        tmp_path / "second", events=_retry_events("batch-1", infrastructure_outcome="FAILED"))
    try:
        with pytest.raises(StoreConflict, match="RETRY_ORIGINAL_INFRA_FAILED"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()


def test_admit_retry_refuses_a_result_hash_that_is_not_the_durable_one(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        with pytest.raises(StoreConflict, match="RETRY_ORIGINAL_RESULT_MISMATCH"):
            store.admit_retry(
                request=replace(request, original_result_sha256=SHA_B), context=context,
                spawn_intent=intent)
    finally:
        store.close()


def test_admit_retry_refuses_a_batch_that_is_not_terminal_or_not_clean(tmp_path):
    store, request, context, intent = _retry_fixture(
        tmp_path, events=_retry_events("batch-1", terminal=False))
    try:
        with pytest.raises(StoreConflict, match="RETRY_ORIGINAL_NOT_TERMINAL"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()

    store, request, context, intent = _retry_fixture(
        tmp_path / "second", events=_retry_events("batch-1", cleanup=False))
    try:
        with pytest.raises(StoreConflict, match="RETRY_ORIGINAL_CLEANUP_INCOMPLETE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()

    store, request, context, intent = _retry_fixture(tmp_path / "third", cleaned_batch=False)
    try:
        with pytest.raises(StoreConflict, match="RETRY_ORIGINAL_CLEANUP_INCOMPLETE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()


def test_admit_retry_refuses_an_active_or_unknown_owner(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        store.record_execution_owner_intent(ExecutionOwnerIntent(
            batch_id="batch-1", owner_kind="COORDINATOR", spawn_token="spawn-live",
            expected_executable="so101_parallel_batch", argv_sha256=SHA_A,
            environment_sha256=SHA_B, source_commit="1" * 40,
            install_prefix=Path("/opt/validation"), runtime_sha256=SHA_CLOSURE,
        ))
        store.acknowledge_execution_owner(
            batch_id="batch-1", pid=123, pgid=123, started_ticks=99, coordinator_epoch=4)
        with pytest.raises(StoreConflict, match="RETRY_OWNER_ACTIVE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)

        store._connection.execute("UPDATE owned_execution SET state = 'INTENT'")
        with pytest.raises(StoreConflict, match="RETRY_OWNER_UNKNOWN"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()


def test_admit_retry_refuses_an_unconfirmed_spawn_on_an_uncleaned_batch(tmp_path):
    """A spawn whose readback never confirmed a process, on a batch that did not clean up."""

    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        store._connection.execute(
            "INSERT INTO campaign_batches VALUES ('retry-003', 'campaign-1', "
            "'FULL_RESTART_RETRY', 'p2', 'BOUND', 1, NULL, ?, NULL, NULL)",
            (str((tmp_path.resolve() / "campaigns/campaign-1/retry-003")),),
        )
        store.record_owner_intent(replace(intent, batch_id="retry-003"))
        with pytest.raises(StoreConflict, match="RETRY_OWNER_UNKNOWN"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()


def test_an_unconfirmed_owner_of_an_already_cleaned_batch_does_not_block_a_retry(tmp_path):
    """The first pass cleaned up: it holds no live or unknowable owner any more."""

    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        store.record_owner_intent(
            replace(intent, batch_id="batch-1", spawn_token="spawn-first-pass"))
        binding = store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert binding.batch_id == "retry-001"
    finally:
        store.close()


def test_admit_retry_refuses_a_recovery_fence(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        store.record_recovery_fence(
            "campaign-1", "batch-1", reason="OWNER_TREE_UNRESOLVED", command_id="recover-1")
        with pytest.raises(StoreConflict, match="RETRY_RECOVERY_FENCE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()


def test_admit_retry_refuses_a_point_that_is_not_queued(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path, enqueue=("p2",))
    try:
        with pytest.raises(StoreConflict, match="RETRY_NOT_QUEUED"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()


def test_admit_retry_rolls_back_every_row_when_the_intent_cannot_be_written(tmp_path):
    store, request, context, intent = _retry_fixture(
        tmp_path, events=_retry_events("batch-1", outcomes={"p1": "FAILED", "p2": "FAILED"}))
    try:
        first = store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert first.batch_id == "retry-001"
        store.record_cleanup_and_advance_retry(
            CleanupReceipt("campaign-1", "retry-001", "p1", "e" * 64)
        )
        store.confirm_owner_process(
            ConfirmedOwnerProcess(
                spawn_token=intent.spawn_token, pid=4321, pgid=4321, started_ticks=7,
                command_sha256=SHA_A, confirmed_at_ns=2,
            )
        )
        # The second admission reuses the first spawn token: its intent insert conflicts and
        # must take the whole transaction - command, batch, queue state and admission row with it.
        second = replace(
            request, command_id="cmd-retry-2", batch_id="retry-002", point_id="p2",
            original_result_sha256=point_result_sha256("p2"),
        )
        conflicting = replace(intent, batch_id="retry-002")
        with pytest.raises(StoreConflict, match="RETRY_OWNER_INTENT_CONFLICT"):
            store.admit_retry(
                request=second,
                context=replace(context, command_id="cmd-retry-2", batch_id="retry-002"),
                spawn_intent=conflicting,
            )
        assert store.batch("retry-002") is None
        assert store.retry_admission("cmd-retry-2") is None
        assert store._connection.execute(
            "SELECT count(*) FROM commands WHERE command_id = 'cmd-retry-2'").fetchone()[0] == 0
        assert store.next_retry("campaign-1").point_id == "p2"
        assert store.next_retry("campaign-1").state == "QUEUED"
        # And the same admission succeeds once the duplicate token is replaced.
        binding = store.admit_retry(
            request=second,
            context=replace(context, command_id="cmd-retry-2", batch_id="retry-002"),
            spawn_intent=replace(intent, spawn_token="spawn-retry-2", batch_id="retry-002"),
        )
        assert binding.batch_id == "retry-002"
    finally:
        store.close()


def test_retry_appends_history_without_overwriting_the_first_pass(tmp_path):
    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        before_state = store.read_projection_state("batch-1")
        before_batch = store.batch("batch-1")
        before_campaign = store.campaign_records()[0]
        before_items = store.retry_items("campaign-1")

        store.admit_retry(request=request, context=context, spawn_intent=intent)

        assert store.read_projection_state("batch-1").state.as_document() == (
            before_state.state.as_document())
        assert store.read_projection_state("batch-1").cursor == before_state.cursor
        assert store.batch("batch-1") == before_batch
        assert store.campaign_records()[0] == before_campaign
        assert store.retry_items("campaign-1")[0].point_id == before_items[0].point_id
        assert len(store.retry_admissions("campaign-1")) == 1
        assert store.campaign_batches("campaign-1")[0].batch_id == "batch-1"
    finally:
        store.close()


# --------------------------------------------------------------------------------------
# Task 9: the durable canonical projection the admission reads back is committed by the service
# --------------------------------------------------------------------------------------


def _canonical_journal_batch(tmp_path, *, outcome="FAILED", canonical=True):
    """One verified canonical (or delta-only) journal read into its verified event batch."""

    from so101_demo.parallel_batch.journal import CoordinatorJournal
    from so101_teleop.expert_validation.coordinator_events import (
        AcceptedCoordinatorCursor,
        CampaignUpstreamBinding,
        CoordinatorEventReader,
    )

    root = tmp_path.resolve()
    batch_root = root / "campaigns" / "campaign-1" / "batch-1"
    journal_root = batch_root / "coordinator"
    digest = hashlib.sha256(b"p1-result").hexdigest()
    with CoordinatorJournal.create(journal_root, "batch-1") as journal:
        binding = CampaignUpstreamBinding(
            campaign_id="campaign-1", batch_id="batch-1", owner_kind="COORDINATOR",
            owner_epoch_or_generation=1, journal_root=journal_root, batch_root=batch_root,
        )
        # The sealed-manifest verifier is not what this test is about; the canonical event
        # adapter, the reducer and the transaction are.
        reader = CoordinatorEventReader(journal, binding, manifest_verifier=lambda *_: None)
        if canonical:
            journal.append("CAMPAIGN_STARTED", "start", {
                "campaign_id": "campaign-1", "batch_id": "batch-1",
                "runtime_identity_sha256": SHA_A, "config_sha256": SHA_CONFIG})
            journal.append("POINT_LEASED", "lease-1", {
                "point_id": "p1", "attempt_id": "p1-attempt-1", "worker_id": "worker-01",
                "worker_generation": 1, "lease_generation": 1})
            journal.append("ATTEMPT_STARTED", "attempt-1", {
                "point_id": "p1", "attempt_id": "p1-attempt-1", "worker_id": "worker-01"})
            journal.append("RESULT_COMMITTED", "result-1", {
                "point_id": "p1", "attempt_id": "p1-attempt-1", "outcome": outcome,
                "result_sha256": digest,
                "response": {"location": str(batch_root / "sealed.json"), "sha256": digest}})
            journal.append("BATCH_TERMINAL", "terminal", {"business_terminal": "POINTS_COMPLETE"})
            journal.append("CLEANUP_COMMITTED", "cleanup", {"cleanup_complete": True})
        else:
            journal.append("BATCH_STARTED", "start", {"delta": {"points": {
                "p1": {"status": "FAILED", "attempts": 1, "terminal": True}}}})
        batch = reader.read_after(AcceptedCoordinatorCursor.initial(binding))
    return batch, digest


def _projection_service(store):
    from so101_teleop.expert_validation.production import ProductionExpertValidationService

    service = object.__new__(ProductionExpertValidationService)
    service.store = store
    return service


def test_the_projection_read_commits_the_canonical_state_the_admission_reads_back(tmp_path):
    """A retry is admitted against state this service committed, never a value it just computed."""

    batch, digest = _canonical_journal_batch(tmp_path)
    store, request, context, intent = _retry_fixture(tmp_path, with_projection=False)
    original = SimpleNamespace(batch_id="batch-1")
    try:
        assert store.read_projection_state("batch-1").state is None
        service = _projection_service(store)
        service._persist_canonical_projection(original, batch)

        snapshot = store.read_projection_state("batch-1")
        assert snapshot.state.points["p1"].status.value == "FAILED"
        assert snapshot.state.points["p1"].result_sha256 == digest
        assert snapshot.state.batch_business_terminal == "POINTS_COMPLETE"
        assert snapshot.state.batch_cleanup_complete is True
        assert snapshot.cursor is not None

        # Idempotent: the same verified prefix replayed is the same state, with one attempt.
        service._persist_canonical_projection(original, batch)
        replayed = store.read_projection_state("batch-1")
        assert replayed.state.as_document() == snapshot.state.as_document()
        assert len(replayed.state.attempts) == 1
        assert replayed.cursor == snapshot.cursor

        # And this is exactly the state the one-time admission then validates against.
        binding = store.admit_retry(
            request=replace(request, original_result_sha256=digest),
            context=context, spawn_intent=intent)
        assert binding.original_result_sha256 == digest
    finally:
        store.close()


def test_a_delta_only_journal_is_never_given_a_canonical_durable_state(tmp_path):
    batch, _digest = _canonical_journal_batch(tmp_path, canonical=False)
    store, _request, _context, _intent = _retry_fixture(tmp_path, with_projection=False)
    try:
        _projection_service(store)._persist_canonical_projection(
            SimpleNamespace(batch_id="batch-1"), batch)
        # A v1-v3 delta journal has no canonical reducer state: the projection stays as it was,
        # and a retry against it is refused for the durable reason rather than admitted on a
        # state that was never the canonical one.
        assert store.read_projection_state("batch-1").state is None
    finally:
        store.close()
