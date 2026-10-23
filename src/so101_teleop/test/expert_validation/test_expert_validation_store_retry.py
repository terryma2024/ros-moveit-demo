"""Owner reconciliation and retry admission."""

from dataclasses import replace
import json as _json  # noqa: E402
from pathlib import Path
import subprocess
import sys
import time

from expert_validation_store_support import (
    RETRY_PROFILE,
    SHA_A,
    SHA_B,
    SHA_CLOSURE,
    SHA_CONFIG,
    SHA_RESULT,
    _end_owner_process,
    _retry_events,
    _retry_fixture,
    _spawn_owner_process,
    point_result_sha256,
)
import pytest
from teleop_paths import TEST_ROOT

from so101_teleop.expert_validation.models import (
    CleanupReceipt,
    ExecutionOwnerIntent,
)
from so101_teleop.expert_validation.owner_tree import (  # noqa: E402
    ConfirmedOwnerProcess,
)
from so101_teleop.expert_validation.supervisor_store.schema import (
    StoreConflict,
)
from so101_teleop.owned_group import terminate_group  # noqa: E402
from so101_teleop.process_identity import group_members, read_identity  # noqa: E402


def _record_running_owner(store, batch_id, *, identity, spawn_token, owner_kind="COORDINATOR"):
    """Record an acknowledged owner whose recorded identity is exactly this kernel identity.

    ``owned_execution`` stores the command fingerprint under ``argv_sha256`` (the same value the
    owner tree confirms), so the row is built from the identity that was read, never from an
    invented pid and start marker.
    """
    store.record_execution_owner_intent(ExecutionOwnerIntent(
        batch_id=batch_id, owner_kind=owner_kind, spawn_token=spawn_token,
        expected_executable="/opt/validation/bin/so101_parallel_batch",
        argv_sha256=identity.command_sha256, environment_sha256=SHA_B,
        source_commit="1" * 40, install_prefix=Path("/opt/validation"),
        runtime_sha256=SHA_CLOSURE,
    ))
    store.acknowledge_execution_owner(
        batch_id=batch_id, pid=identity.pid, pgid=identity.pgid,
        started_ticks=identity.start_marker, coordinator_epoch=4)
    assert store.owned_execution(batch_id).state == "RUNNING"


def _dead_owner_identity():
    """The identity of a real child, read while it lived and kept after it was reaped."""
    process = _spawn_owner_process()
    try:
        return read_identity(process.pid)
    finally:
        _end_owner_process(process)


def test_admit_retry_retires_a_running_owner_whose_process_is_proven_gone(tmp_path):
    """RED: the recorded first pass ``bf16a`` refused its own retry with ``RETRY_OWNER_ACTIVE``.

    That row was ``state='RUNNING'`` with pid 25005, a coordinator the service had acknowledged and
    which was gone by the time the console retried: ``ps`` listed nothing and its process group was
    empty. Nothing in the store ever writes a state after ``INTENT -> RUNNING``, so the finished
    first pass blocked its retry for good. The row here carries that exact shape from a real child -
    its kernel identity, read while it ran - instead of an invented pid.
    """
    store, request, context, intent = _retry_fixture(tmp_path)
    identity = _dead_owner_identity()
    try:
        _record_running_owner(store, "batch-1", identity=identity, spawn_token="spawn-bf16a")
        binding = store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert binding.batch_id == "retry-001"
        assert store.owned_execution("batch-1").state == "EXITED", (
            "the retired row is durable, not just skipped for this one admission"
        )
    finally:
        store.close()


def test_a_live_recorded_owner_still_refuses_the_retry_and_is_never_retired(tmp_path):
    """The positive control for the transition: a live owner blocks, exactly as it always did."""
    store, request, context, intent = _retry_fixture(tmp_path)
    process = _spawn_owner_process()
    try:
        identity = read_identity(process.pid)
        _record_running_owner(store, "batch-1", identity=identity, spawn_token="spawn-live")
        with pytest.raises(StoreConflict, match="RETRY_OWNER_ACTIVE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert store.reconcile_exited_execution_owner("batch-1") is False
        assert store.owned_execution("batch-1").state == "RUNNING"
    finally:
        _end_owner_process(process)
        store.close()


def test_an_owner_identity_the_platform_will_not_report_still_refuses_the_retry(
    tmp_path, monkeypatch
):
    """A row is never retired on assumption: an unreadable identity keeps blocking."""
    from so101_teleop import process_identity

    store, request, context, intent = _retry_fixture(tmp_path)
    identity = _dead_owner_identity()
    try:
        _record_running_owner(
            store, "batch-1", identity=identity, spawn_token="spawn-unreadable"
        )
        assert store.reconcile_exited_execution_owner("batch-1") is True, (
            "positive control: this very row is retirable while the reader answers"
        )
        store._connection.execute(
            "UPDATE owned_execution SET state = 'RUNNING' WHERE batch_id = 'batch-1'"
        )

        def refuse(_pid):
            raise process_identity.ProcessIdentityError()

        monkeypatch.setattr(process_identity, "read_identity", refuse)
        with pytest.raises(StoreConflict, match="RETRY_OWNER_ACTIVE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert store.owned_execution("batch-1").state == "RUNNING"
    finally:
        store.close()


def test_an_owner_whose_group_still_holds_a_live_process_is_not_retired(tmp_path):
    """A leader that exited is not a finished execution while its group still runs something."""
    store, request, context, intent = _retry_fixture(tmp_path)
    leader = subprocess.Popen(
        [
            sys.executable,
            str(TEST_ROOT / "fixtures/process_tree_helper.py"),
            "--mode", "coordinator", "--root", str(tmp_path / "owner-tree"),
            "--batch-id", "b1", "--leader-exits",
        ],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    handshake = tmp_path / "owner-tree" / "handshake.json"
    pgid = leader.pid
    try:
        identity = read_identity(leader.pid)
        leader.wait(timeout=10)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not handshake.is_file():
            time.sleep(0.02)
        assert handshake.is_file(), "the owner never forked the descendant that keeps its group"
        descendant_pid = _json.loads(handshake.read_text(encoding="utf-8"))["runner_pid"]
        assert group_members(pgid).get(descendant_pid) not in {None, "Z"}, (
            "the negative is only meaningful while a descendant of the leader is really running"
        )

        _record_running_owner(
            store, "batch-1", identity=identity, spawn_token="spawn-with-descendant"
        )
        assert store.reconcile_exited_execution_owner("batch-1") is False
        with pytest.raises(StoreConflict, match="RETRY_OWNER_ACTIVE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert store.owned_execution("batch-1").state == "RUNNING"
    finally:
        terminate_group(pgid=pgid, timeout_s=1.0)
        _end_owner_process(leader)
        store.close()


def test_reconciling_a_dead_owner_is_idempotent_and_leaves_other_rows_alone(tmp_path):
    """One guarded update, one row: a second call changes nothing and a live row is untouched."""
    store, request, context, intent = _retry_fixture(tmp_path)
    live = _spawn_owner_process()
    try:
        live_identity = read_identity(live.pid)
        dead_identity = _dead_owner_identity()
        store._connection.execute(
            "INSERT INTO campaign_batches VALUES ('batch-2', 'campaign-1', "
            "'FULL_RESTART_RETRY', 'p2', 'BOUND', 1, NULL, ?, NULL, NULL)",
            (str((tmp_path.resolve() / "campaigns/campaign-1/batch-2")),),
        )
        _record_running_owner(store, "batch-1", identity=dead_identity, spawn_token="spawn-dead")
        _record_running_owner(store, "batch-2", identity=live_identity, spawn_token="spawn-live")

        assert store.reconcile_exited_execution_owner("batch-1") is True
        assert store.owned_execution("batch-1").state == "EXITED"
        assert store.reconcile_exited_execution_owner("batch-1") is True
        assert store.owned_execution("batch-1").state == "EXITED"

        assert store.reconcile_exited_execution_owner("batch-2") is False
        untouched = store.owned_execution("batch-2")
        assert untouched.state == "RUNNING"
        assert (untouched.pid, untouched.pgid, untouched.started_ticks) == (
            live_identity.pid, live_identity.pgid, live_identity.start_marker
        )
        assert untouched.spawn_token == "spawn-live"
    finally:
        _end_owner_process(live)
        store.close()


def test_an_owner_state_this_store_does_not_know_keeps_blocking(tmp_path):
    """Fail closed on the row states this build cannot reason about."""
    store, request, context, intent = _retry_fixture(tmp_path)
    identity = _dead_owner_identity()
    try:
        _record_running_owner(store, "batch-1", identity=identity, spawn_token="spawn-unknown")
        store._connection.execute(
            "UPDATE owned_execution SET state = 'UNRECOGNIZED' WHERE batch_id = 'batch-1'"
        )
        with pytest.raises(StoreConflict, match="RETRY_OWNER_ACTIVE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        store.close()


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


def test_admit_retry_accepts_the_linux_cuda_single_point_route(tmp_path):
    from so101_teleop.expert_validation.execution_context import LINUX_RETRY_PROFILE

    store, request, context, intent = _retry_fixture(tmp_path)
    try:
        linux_request = replace(
            request, execution_profile=LINUX_RETRY_PROFILE, schema_version=3,
        )
        linux_context = replace(
            context, execution_profile=LINUX_RETRY_PROFILE, schema_version=3,
        )
        binding = store.admit_retry(
            request=linux_request, context=linux_context, spawn_intent=intent,
        )
        assert binding.execution_profile == LINUX_RETRY_PROFILE
        assert store.retry_admission(request.command_id)["schema_version"] == 3
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
        ("execution_profile", "MPS_SINGLE_WORKER_FIRST_PASS", "RETRY_PROFILE_MISMATCH"),
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
    process = _spawn_owner_process()
    try:
        identity = read_identity(process.pid)
        _record_running_owner(
            store, "batch-1", identity=identity, spawn_token="spawn-live"
        )
        with pytest.raises(StoreConflict, match="RETRY_OWNER_ACTIVE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert store.owned_execution("batch-1").state == "RUNNING", (
            "a live owner is never retired, whatever else the admission does"
        )

        store._connection.execute("UPDATE owned_execution SET state = 'INTENT'")
        with pytest.raises(StoreConflict, match="RETRY_OWNER_UNKNOWN"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
    finally:
        _end_owner_process(process)
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
