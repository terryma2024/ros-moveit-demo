"""Store builders and fixtures shared by the expert validation store tests."""

import hashlib
import json as _json  # noqa: E402
import subprocess
import sys
import time

from so101_teleop.expert_validation.execution_context import (  # noqa: E402
    CandidateExecutionContext,
    ProductionExecutionContext,
    install_binding_sha256,
)
from so101_teleop.expert_validation.models import (
    BatchBinding,
    CampaignBinding,
    PreflightReceipt,
    RetryStartRequest,  # noqa: E402
    UpstreamCursor,
)
from so101_teleop.expert_validation.owner_tree import (  # noqa: E402
    OwnerIntent,
)
from so101_teleop.expert_validation.store import SupervisorStore
from so101_teleop.process_identity import read_identity  # noqa: E402

SHA_A = "a" * 64


SHA_B = "b" * 64


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


class _VerifiedEvent:
    def __init__(self, event_type, payload, sequence, batch_id):
        self.type = event_type
        self.payload = payload
        self.sequence = sequence
        self.coordinator_epoch = 1
        self.frame_sha256 = hashlib.sha256(f"{batch_id}:{sequence}".encode()).hexdigest()
        self.batch_id = batch_id


def _reducer_module():
    import importlib
    return importlib.import_module("so101_teleop.expert_validation.reducer")


SHA_CATALOG = "1" * 64


SHA_SELECTION = "2" * 64


SHA_RESULT = "3" * 64


SHA_CONFIG = "4" * 64


SHA_CLOSURE = "5" * 64


POINT_IDS = ("p1", "p2")


RETRY_PROFILE = "MPS_SINGLE_WORKER_FULL_RESTART_RETRY"


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


def _spawn_owner_process() -> subprocess.Popen:
    """A real child that leads its own process group, so its kernel identity is a real one."""
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            identity = read_identity(process.pid)
        except Exception:
            identity = None
        if identity is not None and identity.argv[1:] == ("-c", "import time; time.sleep(120)"):
            return process
        if process.poll() is not None:
            break
        time.sleep(0.005)
    _end_owner_process(process)
    raise AssertionError("owner test child did not publish its command line")


def _end_owner_process(process: subprocess.Popen, timeout: float = 5.0) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=timeout)
