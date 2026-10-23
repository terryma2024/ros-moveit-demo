"""Projection reads, first pass admission and candidate context issuance."""

from dataclasses import replace
import hashlib
import json as _json  # noqa: E402
from pathlib import Path
import time
from types import SimpleNamespace

from expert_validation_store_support import (
    SHA_A,
    SHA_B,
    SHA_CATALOG,
    SHA_CLOSURE,
    SHA_CONFIG,
    SHA_SELECTION,
    _end_owner_process,
    _manifest,
    _retry_fixture,
    _spawn_owner_process,
)
import pytest

from so101_teleop.expert_validation.models import (
    BatchBinding,
    CampaignBinding,
    ExecutionOwnerIntent,
    PreflightReceipt,
)
from so101_teleop.expert_validation.owner_tree import (  # noqa: E402
    OwnerIntent,
)
from so101_teleop.expert_validation.store import SupervisorStore
from so101_teleop.expert_validation.supervisor_store.schema import (
    StoreConflict,
)
from so101_teleop.process_identity import read_identity  # noqa: E402


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


def _first_pass_request(root, manifest_id, **changes):
    """One first-pass request whose shape the candidate context can be bound to."""

    from so101_teleop.expert_validation.catalog import CatalogPoint, PointSelection
    from so101_teleop.expert_validation.preflight import CampaignStartRequest

    points = tuple(
        CatalogPoint(
            id=f"p{index}",
            label=f"Point {index}",
            source="generated",
            stratum="near/center",
            position_world_m=(float(index), 0.0, 0.0),
            display_id=f"P{index:02d}",
        )
        for index in range(1, 5)
    )
    values = dict(
        campaign_id="campaign-1",
        batch_id="b001",
        manifest_id=manifest_id,
        selection=PointSelection(
            "catalog", 1, SHA_CATALOG, points, tuple(point.id for point in points), SHA_SELECTION
        ),
        execution_mode="SEQUENTIAL",
        evidence_root=root,
        points_path=root / "points.yaml",
        parallel_config_path=root / "parallel_batch_macos_mps_single_worker_first_pass.yaml",
        adaptive_config_path=root / "adaptive.yaml",
        worker_count=1,
        max_points_per_worker=None,
        fallback_worker_counts=(6, 4, 2, 1),
        initial_points_per_worker=3,
        worker_start_timeout_s=120.0,
        max_infra_attempts_per_point=5,
        yolo_executor_count=2,
        service_session_id="candidate:task-11:candidate-first-pass",
        lease_generation=1,
        source_commit="1" * 40,
        install_prefix=str(root / "install"),
        coordinator_executable_sha256=SHA_A,
        adaptive_runner_module_sha256=SHA_A,
        adaptive_pool_module_sha256=SHA_A,
        adaptive_cleanup_executable_sha256=SHA_A,
        adaptive_wrapper_sha256=SHA_A,
        parallel_config_sha256=SHA_CONFIG,
        adaptive_config_sha256=SHA_A,
        yolo_weights_sha256=SHA_A,
        grounded_sam_manifest_sha256=SHA_A,
        broker_image_id="sha256:" + SHA_A,
        resource_manifest_sha256=SHA_A,
        execution_profile="MPS_SINGLE_WORKER_FIRST_PASS",
        batch_kind="FIRST_PASS",
    )
    values.update(changes)
    return CampaignStartRequest(**values)


def _first_pass_fixture(tmp_path, **context_changes):
    """A fresh campaign, one admitted preflight receipt, and the candidate context for it."""

    from so101_teleop.expert_validation.execution_context import (
        CandidateExecutionContext,
        runtime_closure_sha256,
    )
    from so101_teleop.expert_validation.preflight import canonical_start_request_sha256

    root = tmp_path.resolve()
    store = SupervisorStore.open((root / "store").resolve())
    manifest_id = _manifest(store, "1")
    request = _first_pass_request(root, manifest_id)
    receipt = PreflightReceipt(
        receipt_id="receipt-1",
        campaign_id="campaign-1",
        manifest_id=manifest_id,
        canonical_start_request_sha256=canonical_start_request_sha256(request),
        receipt={
            "admitted": True,
            "execution_profile": "MPS_SINGLE_WORKER_FIRST_PASS",
            "schema_version": 6,
            "batch_kind": "FIRST_PASS",
        },
        expires_at_monotonic_ns=time.monotonic_ns() + 3_600_000_000_000,
    )
    campaign = CampaignBinding(
        campaign_id="campaign-1",
        manifest_id=manifest_id,
        executor_id="candidate-gate",
        operation_id="first-pass",
        executor_config_sha256=SHA_A,
        execution_mode="SEQUENTIAL",
        execution_config={"worker_count": 1},
        preflight_receipt_id="receipt-1",
    )
    batch = BatchBinding(
        batch_id="b001",
        campaign_id="campaign-1",
        batch_kind="FIRST_PASS",
        point_id=None,
        journal_root=(root / "campaigns/campaign-1/b001").resolve(),
        coordinator_epoch=1,
    )
    values = dict(
        context_id="candidate-first-pass-1",
        task_id="task-11",
        dispatch_id="candidate-first-pass",
        campaign_id="campaign-1",
        batch_id="b001",
        manifest_id=manifest_id,
        execution_profile="MPS_SINGLE_WORKER_FIRST_PASS",
        schema_version=6,
        batch_kind="FIRST_PASS",
        worker_count=1,
        config_sha256=SHA_CONFIG,
        runtime_closure_sha256=runtime_closure_sha256(request),
        evidence_root=root,
        owner_generation=1,
        command_id="cmd-first-pass-1",
        issued_at_monotonic_ns=time.monotonic_ns(),
        expires_at_monotonic_ns=time.monotonic_ns() + 3_600_000_000_000,
        max_runs=1,
    )
    values.update(context_changes)
    context = CandidateExecutionContext(**values)
    intent = OwnerIntent.for_argv(
        campaign_id="campaign-1",
        batch_id="b001",
        role="ADAPTER",
        generation=context.owner_generation,
        spawn_token="spawn-first-pass-1",
        argv=("so101_parallel_batch", "--batch-id", "b001"),
        created_at_ns=1,
    )
    return store, request, context, intent, receipt, campaign, batch


def _admit_first_pass(store, request, context, intent, receipt, campaign, batch):
    return store.admit_first_pass(
        request=request,
        context=context,
        receipt=receipt,
        campaign=campaign,
        batch=batch,
        spawn_intent=intent,
    )


def test_admit_first_pass_consumes_the_command_and_binds_campaign_batch_and_intent(tmp_path):
    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(tmp_path)
    try:
        binding = _admit_first_pass(store, request, context, intent, receipt, campaign, batch)

        assert binding.command_id == context.command_id
        assert binding.batch_kind == "FIRST_PASS"
        assert binding.context_kind == "CANDIDATE"
        assert binding.batch_id == "b001" and binding.campaign_id == "campaign-1"
        assert binding.binding_sha256 == binding.compute_sha256()
        # Campaign, batch, owner intent and admission row are all durable, from one transaction.
        assert store.batch("b001") is not None
        assert store.campaign_records()[0]["campaign_id"] == "campaign-1"
        tree = store.owner_tree("campaign-1", "b001")
        assert len(tree) == 1 and tree[0].intent.spawn_token == intent.spawn_token
        assert store.first_pass_admission(context.command_id)["binding_sha256"] == binding.binding_sha256
        # The command stays IN_PROGRESS until the spawn boundary finishes it: an admission that
        # never reached a process must stay unreplayable (the supervisor test pins the other end).
        assert store._connection.execute(
            "SELECT state FROM commands WHERE command_id = ?", (context.command_id,)
        ).fetchone()["state"] == "IN_PROGRESS"
        assert store._connection.execute(
            "SELECT consumed_at_ns FROM preflight_receipts WHERE receipt_id = 'receipt-1'"
        ).fetchone()["consumed_at_ns"] is not None
    finally:
        store.close()


def test_admit_first_pass_refuses_a_replayed_command(tmp_path):
    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(tmp_path)
    try:
        _admit_first_pass(store, request, context, intent, receipt, campaign, batch)
        with pytest.raises(StoreConflict, match="FIRST_PASS_COMMAND_ALREADY_CONSUMED"):
            _admit_first_pass(store, request, context, intent, receipt, campaign, batch)
        assert len(tuple(store.first_pass_admissions("campaign-1"))) == 1
    finally:
        store.close()


def test_admit_first_pass_refuses_a_command_id_reused_for_another_run(tmp_path):
    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(tmp_path)
    try:
        _admit_first_pass(store, request, context, intent, receipt, campaign, batch)
        with pytest.raises(StoreConflict, match="FIRST_PASS_COMMAND_ID_REUSED"):
            store.admit_first_pass(
                request=replace(request, campaign_id="campaign-other"),
                context=replace(context, campaign_id="campaign-other"),
                receipt=receipt,
                campaign=replace(campaign, campaign_id="campaign-other"),
                batch=replace(batch, batch_id="b002", campaign_id="campaign-other"),
                spawn_intent=replace(intent, campaign_id="campaign-other", batch_id="b002"),
            )
    finally:
        store.close()


def test_admit_first_pass_refuses_an_expired_context(tmp_path):
    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(
        tmp_path, issued_at_monotonic_ns=1, expires_at_monotonic_ns=2)
    try:
        with pytest.raises(StoreConflict, match="FIRST_PASS_CONTEXT_EXPIRED"):
            _admit_first_pass(store, request, context, intent, receipt, campaign, batch)
        assert store.first_pass_admission(context.command_id) is None
    finally:
        store.close()


def test_a_refused_first_pass_admission_never_consumes_its_command(tmp_path):
    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(
        tmp_path, issued_at_monotonic_ns=1, expires_at_monotonic_ns=2)
    try:
        with pytest.raises(StoreConflict, match="FIRST_PASS_CONTEXT_EXPIRED"):
            _admit_first_pass(store, request, context, intent, receipt, campaign, batch)
        live = replace(
            context,
            issued_at_monotonic_ns=time.monotonic_ns(),
            expires_at_monotonic_ns=time.monotonic_ns() + 3_600_000_000_000,
        )
        binding = _admit_first_pass(store, request, live, intent, receipt, campaign, batch)
        assert binding.command_id == live.command_id
    finally:
        store.close()


@pytest.mark.parametrize(
    ("holder", "field", "value", "code"),
    [
        ("context", "campaign_id", "campaign-other", "FIRST_PASS_CAMPAIGN_MISMATCH"),
        ("context", "batch_id", "b002", "FIRST_PASS_BATCH_MISMATCH"),
        ("context", "manifest_id", "manifest-other", "FIRST_PASS_MANIFEST_MISMATCH"),
        # A candidate context can never even be constructed for the other profile/schema row, so
        # the profile drift is only expressible on the request side of the pair.
        ("request", "execution_profile", "MPS_SINGLE_WORKER_FULL_RESTART_RETRY", "FIRST_PASS_PROFILE_MISMATCH"),
        ("context", "config_sha256", SHA_A, "FIRST_PASS_CONFIG_MISMATCH"),
        ("context", "runtime_closure_sha256", SHA_A, "FIRST_PASS_RUNTIME_CLOSURE_MISMATCH"),
        ("context", "evidence_root", Path("/evidence-other"), "FIRST_PASS_EVIDENCE_ROOT_MISMATCH"),
        ("context", "owner_generation", 2, "FIRST_PASS_OWNER_GENERATION_MISMATCH"),
        ("request", "lease_generation", 2, "FIRST_PASS_OWNER_GENERATION_MISMATCH"),
    ],
)
def test_admit_first_pass_refuses_a_request_that_drifted_from_its_context(
    tmp_path, holder, field, value, code
):
    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(tmp_path)
    drifted = (
        replace(context, **{field: value}) if holder == "context"
        else replace(request, **{field: value})
    )
    try:
        with pytest.raises(StoreConflict, match=code):
            (
                _admit_first_pass(store, drifted, context, intent, receipt, campaign, batch)
                if holder == "request"
                else _admit_first_pass(store, request, drifted, intent, receipt, campaign, batch)
            )
        assert store.first_pass_admission(context.command_id) is None
        assert store.batch("b001") is None
    finally:
        store.close()


def test_admit_first_pass_refuses_a_production_context(tmp_path):
    """A production context is not a candidate authority, whatever a caller claims."""

    from so101_teleop.expert_validation.execution_context import (
        ProductionExecutionContext,
        install_binding_sha256,
    )

    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(tmp_path)
    try:
        production = ProductionExecutionContext(
            context_id="production-context-1",
            service_session_id="session-1",
            lease_id="lease-1",
            lease_generation=1,
            install_prefix=(tmp_path.resolve() / "install"),
            install_binding_sha256=install_binding_sha256(
                install_prefix=(tmp_path.resolve() / "install"),
                runtime_closure_sha256=context.runtime_closure_sha256,
            ),
            execution_profile=context.execution_profile,
            schema_version=context.schema_version,
            batch_kind=context.batch_kind,
            worker_count=context.worker_count,
            campaign_id=context.campaign_id,
            batch_id=context.batch_id,
            manifest_id=context.manifest_id,
            config_sha256=context.config_sha256,
            runtime_closure_sha256=context.runtime_closure_sha256,
            evidence_root=context.evidence_root,
            owner_generation=context.owner_generation,
            command_id=context.command_id,
            issued_at_monotonic_ns=context.issued_at_monotonic_ns,
            expires_at_monotonic_ns=context.expires_at_monotonic_ns,
        )
        with pytest.raises(StoreConflict, match="FIRST_PASS_CANDIDATE_CONTEXT_REQUIRED"):
            _admit_first_pass(store, request, production, intent, receipt, campaign, batch)
        with pytest.raises(StoreConflict, match="FIRST_PASS_CONTEXT_KIND"):
            _admit_first_pass(store, request, object(), intent, receipt, campaign, batch)
    finally:
        store.close()


def test_admit_first_pass_refuses_an_existing_campaign_or_batch(tmp_path):
    """A first pass is a new campaign: an occupied campaign id is never replayed into."""

    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(tmp_path)
    try:
        _admit_first_pass(store, request, context, intent, receipt, campaign, batch)
        later = replace(
            context,
            context_id="candidate-first-pass-2",
            dispatch_id="candidate-first-pass-other",
            command_id="cmd-first-pass-2",
            issued_at_monotonic_ns=time.monotonic_ns(),
            expires_at_monotonic_ns=time.monotonic_ns() + 3_600_000_000_000,
        )
        with pytest.raises(StoreConflict, match="FIRST_PASS_CAMPAIGN_EXISTS"):
            store.admit_first_pass(
                request=request,
                context=later,
                receipt=replace(receipt, receipt_id="receipt-2"),
                campaign=replace(campaign, preflight_receipt_id="receipt-2"),
                batch=batch,
                spawn_intent=replace(intent, spawn_token="spawn-first-pass-2"),
            )
        assert store._connection.execute(
            "SELECT count(*) FROM commands WHERE command_id = 'cmd-first-pass-2'"
        ).fetchone()[0] == 0
    finally:
        store.close()


def _second_first_pass_campaign(request, context, intent, receipt, campaign, batch):
    """The same run one campaign over, under its own command, dispatch and receipt."""

    return dict(
        request=replace(request, campaign_id="campaign-2", batch_id="b002"),
        context=replace(
            context,
            context_id="candidate-first-pass-2",
            dispatch_id="candidate-first-pass-other",
            command_id="cmd-first-pass-2",
            campaign_id="campaign-2",
            batch_id="b002",
            issued_at_monotonic_ns=time.monotonic_ns(),
            expires_at_monotonic_ns=time.monotonic_ns() + 3_600_000_000_000,
        ),
        receipt=replace(receipt, receipt_id="receipt-2", campaign_id="campaign-2"),
        campaign=replace(campaign, campaign_id="campaign-2", preflight_receipt_id="receipt-2"),
        batch=replace(batch, batch_id="b002", campaign_id="campaign-2"),
        spawn_intent=replace(
            intent, campaign_id="campaign-2", batch_id="b002", spawn_token="spawn-first-pass-2"
        ),
    )


def test_admit_first_pass_refuses_a_recovery_fence_or_an_unresolved_owner(tmp_path):
    """A first pass never starts over a standing fence or an owner whose outcome is unknown."""

    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(tmp_path)
    process = _spawn_owner_process()
    try:
        _admit_first_pass(store, request, context, intent, receipt, campaign, batch)
        second = _second_first_pass_campaign(request, context, intent, receipt, campaign, batch)
        store.record_recovery_fence(
            "campaign-1", "b001", reason="OWNER_TREE_UNRESOLVED", command_id="recover-1"
        )
        with pytest.raises(StoreConflict, match="FIRST_PASS_RECOVERY_FENCE"):
            store.admit_first_pass(**second)
        store._connection.execute("DELETE FROM recovery_fences")
        # The admitted spawn intent was never read back, and its batch has not cleaned up.
        with pytest.raises(StoreConflict, match="FIRST_PASS_OWNER_UNKNOWN"):
            store.admit_first_pass(**second)
        store.record_execution_owner_intent(ExecutionOwnerIntent(
            batch_id="b001", owner_kind="COORDINATOR", spawn_token="spawn-b001",
            expected_executable="so101_parallel_batch", argv_sha256=SHA_A,
            environment_sha256=SHA_B, source_commit="1" * 40,
            install_prefix=Path("/opt/validation"), runtime_sha256=SHA_CLOSURE,
        ))
        with pytest.raises(StoreConflict, match="FIRST_PASS_OWNER_UNKNOWN"):
            store.admit_first_pass(**second)
        # An acknowledged owner whose process is proven gone is not an active one any more: the
        # admission reaches the next genuine gate, which is still this batch's unresolved spawn
        # intent, and the transaction still rolls back with it.
        store.acknowledge_execution_owner(
            batch_id="b001", pid=4321, pgid=4321, started_ticks=7, coordinator_epoch=4)
        with pytest.raises(StoreConflict, match="FIRST_PASS_OWNER_UNKNOWN"):
            store.admit_first_pass(**second)
        assert store.owned_execution("b001").state == "RUNNING", (
            "a refused admission commits nothing, including the retirement it did not need"
        )

        # A genuinely live owner still refuses by name, and is never retired.
        identity = read_identity(process.pid)
        store._connection.execute(
            "UPDATE owned_execution SET pid=?, pgid=?, started_ticks=?, argv_sha256=? "
            "WHERE batch_id='b001'",
            (identity.pid, identity.pgid, identity.start_marker, identity.command_sha256),
        )
        with pytest.raises(StoreConflict, match="FIRST_PASS_OWNER_ACTIVE"):
            store.admit_first_pass(**second)
        assert store.owned_execution("b001").state == "RUNNING"
        assert store._connection.execute(
            "SELECT count(*) FROM commands WHERE command_id = 'cmd-first-pass-2'"
        ).fetchone()[0] == 0
    finally:
        _end_owner_process(process)
        store.close()


def test_a_candidate_context_never_authorizes_more_first_pass_runs_than_its_max_runs(tmp_path):
    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(tmp_path)
    try:
        _admit_first_pass(store, request, context, intent, receipt, campaign, batch)
        second_context = replace(
            context,
            context_id="candidate-first-pass-2",
            command_id="cmd-first-pass-2",
            campaign_id="campaign-2",
            batch_id="b002",
        )
        with pytest.raises(StoreConflict, match="FIRST_PASS_MAX_RUNS_EXCEEDED"):
            store.admit_first_pass(
                request=replace(request, campaign_id="campaign-2", batch_id="b002"),
                context=second_context,
                receipt=replace(receipt, receipt_id="receipt-2", campaign_id="campaign-2"),
                campaign=replace(
                    campaign, campaign_id="campaign-2", preflight_receipt_id="receipt-2"
                ),
                batch=replace(batch, batch_id="b002", campaign_id="campaign-2"),
                spawn_intent=replace(
                    intent, campaign_id="campaign-2", batch_id="b002",
                    spawn_token="spawn-first-pass-2",
                ),
            )
    finally:
        store.close()


def test_candidate_context_issuance_is_one_time_and_records_its_document(tmp_path):
    """The issuance command is consumed once, and the context it minted stays readable."""

    store = SupervisorStore.open(tmp_path.resolve())
    try:
        document = {"kind": "CANDIDATE", "context_id": "candidate-context-1"}
        store.admit_candidate_context_issuance(
            command_id="cmd-issue-1",
            request_sha256=SHA_A,
            context_id="candidate-context-1",
            campaign_id="campaign-1",
            document=document,
        )
        row = store._connection.execute(
            "SELECT state, result_json FROM commands WHERE command_id = 'cmd-issue-1'"
        ).fetchone()
        assert row["state"] == "COMPLETE"
        assert _json.loads(row["result_json"]) == document

        with pytest.raises(StoreConflict, match="CONTEXT_COMMAND_ALREADY_CONSUMED"):
            store.admit_candidate_context_issuance(
                command_id="cmd-issue-1",
                request_sha256=SHA_A,
                context_id="candidate-context-1",
                campaign_id="campaign-1",
                document=document,
            )
        with pytest.raises(StoreConflict, match="CONTEXT_COMMAND_ID_REUSED"):
            store.admit_candidate_context_issuance(
                command_id="cmd-issue-1",
                request_sha256=SHA_B,
                context_id="candidate-context-2",
                campaign_id="campaign-1",
                document={"kind": "CANDIDATE", "context_id": "candidate-context-2"},
            )
    finally:
        store.close()


def test_candidate_context_issuance_is_refused_by_a_fence_or_an_unknown_owner(tmp_path):
    """Issuance happens on a host whose previous owner is fully resolved, or not at all."""

    store, request, context, intent, receipt, campaign, batch = _first_pass_fixture(tmp_path)
    try:
        _admit_first_pass(store, request, context, intent, receipt, campaign, batch)
        store.record_recovery_fence(
            "campaign-1", "b001", reason="OWNER_TREE_UNRESOLVED", command_id="recover-1"
        )
        with pytest.raises(StoreConflict, match="CONTEXT_RECOVERY_FENCE"):
            store.admit_candidate_context_issuance(
                command_id="cmd-issue-1",
                request_sha256=SHA_A,
                context_id="candidate-context-1",
                campaign_id="campaign-2",
                document={"kind": "CANDIDATE", "context_id": "candidate-context-1"},
            )
        store._connection.execute("DELETE FROM recovery_fences")
        # The first-pass admission left an intent whose process was never read back, on a batch
        # that did not clean up: the owner is unknown, and no new context may be issued.
        with pytest.raises(StoreConflict, match="CONTEXT_OWNER_UNKNOWN"):
            store.admit_candidate_context_issuance(
                command_id="cmd-issue-1",
                request_sha256=SHA_A,
                context_id="candidate-context-1",
                campaign_id="campaign-2",
                document={"kind": "CANDIDATE", "context_id": "candidate-context-1"},
            )
        assert store._connection.execute(
            "SELECT count(*) FROM commands WHERE command_id = 'cmd-issue-1'"
        ).fetchone()[0] == 0
    finally:
        store.close()
