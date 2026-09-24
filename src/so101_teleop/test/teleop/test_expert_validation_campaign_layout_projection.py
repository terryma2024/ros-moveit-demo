"""End-to-end projection over the macOS campaign's own batch layout.

The batch root a macOS campaign writes is ``<evidence_root>/campaigns/<campaign>/<batch>`` with its
journal under ``journal/`` and its durable per-point documents under ``point-results/``. These tests
build exactly that layout - the event payloads, the binding document and the point documents follow
the bytes the real campaign writes - and drive the *installed* projection path over it:

* the projection reaches its terminal verdict and reports ``batch_cleanup_complete``;
* ``_persist_canonical_projection`` commits the canonical state for the batch, so
  ``store.read_projection_state(batch_id)`` is no longer empty;
* a retry admission against that committed state finds the original business ``FAILED`` result
  instead of refusing ``RETRY_ORIGINAL_RESULT_UNKNOWN``.

Every case here is deterministic and runs in the ordinary gate: the bytes are written by
``campaign_batch_fixture``, which the retry fixture shares. The recorded production batches are
replayed separately by ``test/replay/replay_recorded_validation.py`` - an explicit, read-only entry
point that reports itself "not run" when a recording is absent instead of skipping cases here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from campaign_batch_fixture import (
    CATALOG_SHA256,
    CONFIG_SHA256,
    RETRY_KIND,
    RUNTIME_CLOSURE_SHA256,
    SELECTION_SHA256,
    result_sha256,
    write_campaign_batch,
)
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_teleop.expert_validation.artifacts import ValidationArtifactRegistry
from so101_teleop.expert_validation.execution_context import (
    CandidateExecutionContext,
    RETRY_BATCH_KIND,
    RETRY_PROFILE,
    RETRY_SCHEMA_VERSION,
    RETRY_WORKER_COUNT,
)
from so101_teleop.expert_validation.journal_layout import CAMPAIGN_LAYOUT
from so101_teleop.expert_validation.models import (
    BatchBinding,
    CampaignBinding,
    CleanupReceipt,
    PreflightReceipt,
    RetryStartRequest,
)
from so101_teleop.expert_validation.owner_tree import OwnerIntent
from so101_teleop.expert_validation.production import ProductionExpertValidationService
from so101_teleop.expert_validation.service import ServiceConflict
from so101_teleop.expert_validation.store import StoreConflict, SupervisorStore


CAMPAIGN_ID = "cand-w2-20260922T011804Z"
BATCH_ID = "w2-b001"
POINT_IDS = ("task_start", "cup_test_forward_5cm", "cup_test_left_5cm")
#: The fast five-point selection: the four anchors plus the one point that has genuinely failed.
FIVE_POINT_IDS = (
    "task_start", "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm",
    "sample_05_near_center",
)
SHA_A = "a" * 64
SHA_B = "b" * 64
#: The campaign's own binding hashes come from the shared batch writer, so this module and the retry
#: fixture cannot drift about the bytes either of them verifies.
SHA_CATALOG = CATALOG_SHA256
SHA_SELECTION = SELECTION_SHA256
SHA_CONFIG = CONFIG_SHA256
SHA_CLOSURE = RUNTIME_CLOSURE_SHA256
CAMPAIGN_PASS = "W2_CAMPAIGN_PASS"
CAMPAIGN_INCOMPLETE = "W2_CAMPAIGN_INCOMPLETE"

#: The one real batch this task's evidence records: journal, binding, per-point results and the
#: campaign's own result document, written by the campaign composition itself.
RECORDED_REAL_BATCH = (
    "/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1"
    "/task11/after-fix/w2-20260922T011804Z/batch"
)


#: The verified result hash of one committed attempt, as the batch's own ``POINT_TERMINAL`` writes
#: it. The shared writer computes the same value for the same input.
_result_sha256 = result_sha256


def _write_campaign_batch(root, outcomes, *, verdict, batch_id=BATCH_ID, cleanup_complete=True,
                          point_ids=POINT_IDS):
    """This module's own batch coordinates, bound to the one shared writer.

    The writer itself is ``campaign_batch_fixture``: a second copy of the event vocabulary here
    would be a second source of truth for bytes the installed readers verify.
    """

    return write_campaign_batch(
        root, outcomes, campaign_id=CAMPAIGN_ID, batch_id=batch_id, verdict=verdict,
        point_ids=point_ids, cleanup_complete=cleanup_complete,
    )


def _campaign_request(evidence_root, batch_id=BATCH_ID, campaign_id=CAMPAIGN_ID,
                      point_ids=POINT_IDS):
    return SimpleNamespace(
        campaign_id=campaign_id,
        manifest_id="manifest-1",
        batch_id=batch_id,
        execution_mode="SEQUENTIAL",
        evidence_root=Path(evidence_root),
        selection=SimpleNamespace(
            point_ids=point_ids,
            points=tuple(
                SimpleNamespace(id=point_id, display_id=f"P{index:02d}")
                for index, point_id in enumerate(point_ids, start=1)
            ),
        ),
    )


class _Layout:
    demo_prefix = Path("/nonexistent-prefix")
    points_path = Path("/nonexistent-points.yaml")
    parallel_config_path = Path("/nonexistent-parallel.yaml")
    adaptive_config_path = Path("/nonexistent-adaptive.yaml")


def _service(tmp_path, *, manifest_id="manifest-1", batch_id=BATCH_ID, campaign_id=CAMPAIGN_ID,
             point_ids=POINT_IDS, catalog_sha256=SHA_CATALOG, selection_sha256=SHA_SELECTION,
             evidence_root=None):
    """A real store bound to the campaign and its first-pass batch, and the service over it.

    ``evidence_root`` is where the campaign's own batch bytes are read from; it defaults to the
    store's parent, which is the layout the production service restores a campaign with. A recorded
    campaign outside the store can be projected by pointing it at the bytes that really exist.
    """

    root = Path(tmp_path).resolve()
    store = SupervisorStore.open((root / "store").resolve())
    store.record_manifest(
        manifest_id, {"schema_version": 1, "selection": list(point_ids)},
        source_config_sha256=SHA_A, created_at_ns=1,
    )
    store.record_preflight_receipt(PreflightReceipt(
        receipt_id="receipt-1", campaign_id=campaign_id, manifest_id=manifest_id,
        canonical_start_request_sha256=SHA_A, receipt={"admitted": True},
        expires_at_monotonic_ns=10_000_000_000,
    ))
    store.consume_preflight_and_bind_campaign_batch(
        "receipt-1", SHA_A,
        CampaignBinding(
            campaign_id=campaign_id, manifest_id=manifest_id, executor_id="operator",
            operation_id="operation-1", executor_config_sha256=SHA_A,
            execution_mode="PARALLEL",
            execution_config={"worker_count": 2, "max_points_per_worker": 10},
            preflight_receipt_id="receipt-1",
        ),
        BatchBinding(
            batch_id=batch_id, campaign_id=campaign_id, batch_kind="FIRST_PASS", point_id=None,
            journal_root=(root / "campaigns" / campaign_id / batch_id / "journal").resolve(),
            coordinator_epoch=1,
        ),
        now_monotonic_ns=1,
    )
    store._connection.execute(
        "UPDATE manifests SET canonical_json = ? WHERE manifest_id = ?",
        (
            json.dumps({
                "catalog_sha256": catalog_sha256,
                "selection_sha256": selection_sha256,
                "point_ids": list(point_ids),
            }, sort_keys=True, separators=(",", ":")),
            manifest_id,
        ),
    )
    service = ProductionExpertValidationService(
        layout=_Layout(), registry=None, artifacts=ValidationArtifactRegistry(),
        store=store, supervisor=SimpleNamespace(), lease_service=SimpleNamespace(),
        current_source_config_sha256=lambda: SHA_A,
    )
    read_root = root if evidence_root is None else Path(evidence_root).resolve()
    request = _campaign_request(read_root, batch_id, campaign_id, point_ids)
    service._campaign_requests = {campaign_id: request}
    service._campaigns = {campaign_id: {
        "campaign_id": campaign_id, "manifest_id": manifest_id, "sequence": 1,
        "execution_mode": "SEQUENTIAL", "owner_kind": "COORDINATOR", "batch_id": batch_id,
        "status": "STARTED",
        "points": tuple({"point_id": point_id, "status": "UNRUN"} for point_id in point_ids),
    }}
    return service, store, read_root


def _assert_terminal_clean_projection(projection):
    """The strongest assertion set for a first pass that reached terminal-clean cleanup."""

    assert projection["status"] == "COMPLETED"
    assert projection["batch_cleanup_complete"] is True
    assert projection["terminal"] if "terminal" in projection else True
    assert projection["points"], projection
    assert {point["status"] for point in projection["points"]} == {"PASSED"}
    return True


def test_campaign_layout_projects_terminal_cleanup_and_commits_the_canonical_state(tmp_path):
    _write_campaign_batch(tmp_path, {point_id: "PASSED" for point_id in POINT_IDS},
                          verdict=CAMPAIGN_PASS)
    service, store, _root = _service(tmp_path)
    try:
        assert store.read_projection_state(BATCH_ID).state is None
        projection = service.get_campaign(CAMPAIGN_ID)
        _assert_terminal_clean_projection(projection)
        assert projection["valid_succeeded"] == len(POINT_IDS)
        assert projection["evaluated"] == len(POINT_IDS)
        # The canonical state is committed, not merely computed for this read.
        snapshot = store.read_projection_state(BATCH_ID)
        assert snapshot.state is not None
        assert snapshot.cursor is not None
        assert snapshot.state.batch_cleanup_complete is True
        assert snapshot.state.batch_business_terminal == "POINTS_COMPLETE"
        assert {
            point_id: point.status.value for point_id, point in snapshot.state.points.items()
        } == {point_id: "PASSED" for point_id in POINT_IDS}
        assert all(
            point.result_sha256 == _result_sha256(point_id, f"{point_id}-attempt-1", "PASSED")
            for point_id, point in snapshot.state.points.items()
        )
    finally:
        store.close()


def test_an_incomplete_campaign_is_not_reported_as_a_pass(tmp_path):
    outcomes = {point_id: "PASSED" for point_id in POINT_IDS}
    outcomes["cup_test_left_5cm"] = "FAILED"
    _write_campaign_batch(tmp_path, outcomes, verdict=CAMPAIGN_INCOMPLETE)
    service, store, _root = _service(tmp_path)
    try:
        projection = service.get_campaign(CAMPAIGN_ID)
        assert projection["status"] == "COMPLETED_WITH_FAILURES"
        assert projection["batch_cleanup_complete"] is True
        assert projection["valid_failed"] == 1
        point = next(
            point for point in projection["points"] if point["point_id"] == "cup_test_left_5cm"
        )
        assert point["status"] == "FAILED"
        assert store.read_projection_state(BATCH_ID).state.batch_business_terminal == (
            CAMPAIGN_INCOMPLETE
        )
    finally:
        store.close()


def _write_infrastructure_failed_batch(root):
    """A terminal campaign with one failed worker and another unfinished lease."""

    reference = _write_campaign_batch(
        Path(root) / "reference", {point_id: "PASSED" for point_id in POINT_IDS},
        verdict=CAMPAIGN_PASS,
    )
    batch_root = Path(root) / "campaigns" / CAMPAIGN_ID / BATCH_ID
    batch_root.mkdir(parents=True)
    shutil.copyfile(reference / "selection-binding.json", batch_root / "selection-binding.json")
    attempt = "task_start-attempt-1"
    worker_result = batch_root / f"w1-result-{attempt}.json"
    worker_result.write_text(json.dumps({
        "worker_id": "w1", "failure_code": "STATION_NOT_READY", "results": [],
    }, sort_keys=True))
    with CoordinatorJournal.create(batch_root / "journal", BATCH_ID) as journal:
        journal.append_committed(
            "CAMPAIGN_STARTED", f"{CAMPAIGN_ID}/CAMPAIGN_STARTED",
            {"campaign_id": CAMPAIGN_ID, "batch_id": BATCH_ID, "schema_version": 1},
        )
        for point_id in POINT_IDS[:2]:
            attempt_id = f"{point_id}-attempt-1"
            worker_id = _worker_for(point_id)
            slot_id = _slot_for(point_id)
            identity = {"point_id": point_id, "attempt_id": attempt_id,
                        "worker_id": worker_id, "slot_id": slot_id, "generation": 1}
            journal.append_committed(
                "POINT_LEASED", f"{BATCH_ID}/POINT_LEASED/{attempt_id}",
                {**identity, "selection_sha256": SHA_SELECTION},
            )
            journal.append_committed(
                "WORKER_REGISTERED", f"{BATCH_ID}/WORKER_REGISTERED/{attempt_id}",
                identity,
            )
            journal.append_committed(
                "ATTEMPT_STARTED", f"{BATCH_ID}/ATTEMPT_STARTED/{attempt_id}",
                identity,
            )
        journal.append_committed(
            "ATTEMPT_FAILED", f"{BATCH_ID}/ATTEMPT_FAILED/{attempt}",
            {"point_id": "task_start", "attempt_id": attempt, "worker_id": "w1",
             "slot_id": "slot-0", "generation": 1,
             "infrastructure_code": "STATION_NOT_READY", "outcome": None,
             "worker_result_sha256": hashlib.sha256(worker_result.read_bytes()).hexdigest()},
        )
        journal.append_committed(
            "BATCH_TERMINAL", f"{BATCH_ID}/BATCH_TERMINAL",
            {"outcome": CAMPAIGN_INCOMPLETE},
        )
        journal.append_committed(
            "CLEANUP_COMMITTED", f"{BATCH_ID}/CLEANUP_COMMITTED",
            {"cleanup_complete": True},
        )
    return batch_root


def test_infrastructure_failure_projects_terminal_unrun_points(tmp_path):
    _write_infrastructure_failed_batch(tmp_path)
    service, store, _root = _service(tmp_path)
    try:
        projection = service.get_campaign(CAMPAIGN_ID)
        assert projection["status"] == "INFRA_FAILED"
        assert projection["batch_cleanup_complete"] is True
        assert projection["requested"] == len(POINT_IDS)
        assert projection["evaluated"] == 0
        assert projection["execution_started"] == 2
        assert {point["status"] for point in projection["points"]} == {"UNRUN"}
        assert all(worker["current_point_id"] is None for worker in projection["workers"])
        state = store.read_projection_state(BATCH_ID).state
        assert state is not None
        assert state.batch_infrastructure_terminal == CAMPAIGN_INCOMPLETE
    finally:
        store.close()


def test_tampered_worker_failure_result_refuses_projection(tmp_path):
    batch_root = _write_infrastructure_failed_batch(tmp_path)
    (batch_root / "w1-result-task_start-attempt-1.json").write_text("tampered")
    service, store, _root = _service(tmp_path)
    try:
        with pytest.raises(ServiceConflict, match="UPSTREAM_PROJECTION_INVALID"):
            service.get_campaign(CAMPAIGN_ID)
        assert store.read_projection_state(BATCH_ID).state is None
    finally:
        store.close()


def test_the_campaign_layout_reader_resolves_the_campaign_directory(tmp_path):
    batch_root = _write_campaign_batch(
        tmp_path, {point_id: "PASSED" for point_id in POINT_IDS}, verdict=CAMPAIGN_PASS
    )
    from so101_teleop.expert_validation.journal_layout import resolve_fixed_journal_layout

    layout = resolve_fixed_journal_layout(batch_root, BATCH_ID)
    assert layout.layout == CAMPAIGN_LAYOUT
    assert layout.journal_root == batch_root / "journal"
    assert layout.epoch == 1


def _retry_pair(*, evidence_root, campaign_id, original_batch_id, point_id, batch_id,
                catalog_sha256, selection_sha256, original_result_sha256,
                argv_batch_id=None, command_id="cmd-retry-1"):
    """The real one-time retry admission pair the production route builds, and its spawn intent."""

    root = Path(evidence_root).resolve()
    now = time.monotonic_ns()
    values = dict(
        campaign_id=campaign_id, batch_id=batch_id, manifest_id="manifest-1",
        execution_profile=RETRY_PROFILE, schema_version=RETRY_SCHEMA_VERSION,
        batch_kind=RETRY_BATCH_KIND, worker_count=RETRY_WORKER_COUNT, config_sha256=SHA_CONFIG,
        runtime_closure_sha256=SHA_CLOSURE, evidence_root=root,
        owner_generation=1, command_id=command_id, issued_at_monotonic_ns=now,
        expires_at_monotonic_ns=now + 3_600_000_000_000, max_runs=2,
    )
    context = CandidateExecutionContext(
        context_id="candidate-context-1", task_id="task-12", dispatch_id="dispatch-1", **values
    )
    request = RetryStartRequest(
        command_id=context.command_id, campaign_id=context.campaign_id,
        batch_id=context.batch_id, point_id=point_id, original_batch_id=original_batch_id,
        original_catalog_sha256=catalog_sha256, original_selection_sha256=selection_sha256,
        original_result_sha256=original_result_sha256,
        execution_profile=context.execution_profile, schema_version=context.schema_version,
        batch_kind=context.batch_kind, config_sha256=context.config_sha256,
        runtime_closure_sha256=context.runtime_closure_sha256, worker_count=context.worker_count,
        evidence_root=context.evidence_root, install_prefix=root / "install",
        owner_generation=1, created_at_ns=1,
    )
    intent = OwnerIntent.for_argv(
        campaign_id=campaign_id, batch_id=batch_id, role="ADAPTER", generation=1,
        spawn_token="spawn-retry-1",
        argv=("so101_parallel_batch", "--batch-id", argv_batch_id or batch_id), created_at_ns=1,
    )
    return request, context, intent


def _retry_admission(tmp_path, service, store, point_id, *, campaign_id=CAMPAIGN_ID,
                     original_batch_id=BATCH_ID, batch_id="retry-001"):
    """The admission for a first pass whose canonical state the projection already committed.

    Nothing is staged here: the original batch's cleanup receipt has to be durable before
    ``admit_retry`` is called, exactly as the service's own projection read leaves it.
    """

    original_result = store.read_projection_state(
        original_batch_id
    ).state.points[point_id].result_sha256
    request, context, intent = _retry_pair(
        evidence_root=tmp_path, campaign_id=campaign_id, original_batch_id=original_batch_id,
        point_id=point_id, batch_id=batch_id, catalog_sha256=SHA_CATALOG,
        selection_sha256=SHA_SELECTION, original_result_sha256=original_result,
    )
    return request, context, intent, original_result


def test_a_failed_point_can_be_retried_after_the_campaign_projection_committed_it(tmp_path):
    outcomes = {point_id: "PASSED" for point_id in POINT_IDS}
    outcomes["cup_test_left_5cm"] = "FAILED"
    _write_campaign_batch(tmp_path, outcomes, verdict=CAMPAIGN_INCOMPLETE)
    service, store, root = _service(tmp_path)
    try:
        projection = service.get_campaign(CAMPAIGN_ID)
        assert projection["status"] == "COMPLETED_WITH_FAILURES"

        # The service's own retry flow enqueues the failed point and then reads the original's
        # committed result back. ``_retry_origin`` is the call that answered
        # RETRY_ORIGINAL_RESULT_UNKNOWN while the canonical state stayed empty.
        store.enqueue_retries(CAMPAIGN_ID, ("cup_test_left_5cm",))
        _original, item, catalog, selection, result_sha256 = service._retry_origin(
            CAMPAIGN_ID, "cup_test_left_5cm"
        )
        assert item.point_id == "cup_test_left_5cm"
        assert catalog == SHA_CATALOG and selection == SHA_SELECTION
        assert result_sha256 == _result_sha256(
            "cup_test_left_5cm", "cup_test_left_5cm-attempt-1", "FAILED"
        )

        request, context, intent, original_result = _retry_admission(
            root, service, store, "cup_test_left_5cm"
        )
        assert request.original_result_sha256 == original_result
        binding = store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert binding.point_id == "cup_test_left_5cm"
        assert binding.original_outcome == "FAILED"
        assert binding.original_result_sha256 == original_result
    finally:
        store.close()


def test_a_passed_point_is_not_admissible_for_retry(tmp_path):
    _write_campaign_batch(tmp_path, {point_id: "PASSED" for point_id in POINT_IDS},
                          verdict=CAMPAIGN_PASS)
    service, store, root = _service(tmp_path)
    try:
        service.get_campaign(CAMPAIGN_ID)
        store.enqueue_retries(CAMPAIGN_ID, ("task_start",))
        request, context, intent, _result = _retry_admission(root, service, store, "task_start")
        with pytest.raises(Exception) as refusal:
            store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert "RETRY_ORIGINAL_NOT_FAILED" in str(refusal.value)
    finally:
        store.close()


def _journal_final_frame_sha256(batch_root, batch_id):
    """The verified frame hash of the batch's own last committed event, read independently."""

    replay = CoordinatorJournal.read_only_replay(Path(batch_root) / "journal", batch_id)
    assert replay.events, "the batch published no committed event at all"
    final = replay.events[-1]
    assert final.type == "CLEANUP_COMMITTED", final.type
    return final.frame_sha256


def test_the_projection_records_the_verified_cleanup_receipt_the_retry_admission_needs(tmp_path):
    """A clean projection must leave the durable receipt ``admit_retry`` checks for the original.

    Recorded production defect (``$RUN/task12/retry-after-fix-20260922T052643Z/legs/w1/driver.log``):
    the W1 first pass reached ``PROJECTION_TERMINAL_AND_CLEAN`` with a genuinely ``FAILED`` point and
    ``cleanup.complete`` true, and the console's same-page retry then answered
    ``409 {"code": "RETRY_ORIGINAL_CLEANUP_INCOMPLETE"}`` - the service read the batch's cleanup
    bytes but never recorded the receipt they prove. RED: the receipt was still NULL here and the
    admission refused by that name.
    """

    outcomes = {point_id: "PASSED" for point_id in POINT_IDS}
    outcomes["cup_test_left_5cm"] = "FAILED"
    batch_root = _write_campaign_batch(tmp_path, outcomes, verdict=CAMPAIGN_INCOMPLETE)
    terminal_receipt = _journal_final_frame_sha256(batch_root, BATCH_ID)
    service, store, root = _service(tmp_path)
    try:
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 is None
        projection = service.get_campaign(CAMPAIGN_ID)
        assert projection["status"] == "COMPLETED_WITH_FAILURES"
        assert projection["batch_cleanup_complete"] is True

        recorded = store.batch(BATCH_ID).cleanup_receipt_sha256
        assert recorded == terminal_receipt, (
            "a batch whose own verified bytes show cleanup complete has no durable cleanup "
            "receipt, so admit_retry refuses RETRY_ORIGINAL_CLEANUP_INCOMPLETE"
        )
        # Same receipt, same read: a later poll never re-records anything.
        service.get_campaign(CAMPAIGN_ID)
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 == recorded

        # The refusal is gone: the very admission the console builds now proceeds.
        store.enqueue_retries(CAMPAIGN_ID, ("cup_test_left_5cm",))
        request, context, intent, original_result = _retry_admission(
            root, service, store, "cup_test_left_5cm"
        )
        binding = store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert binding.original_outcome == "FAILED"
        assert binding.original_result_sha256 == original_result
    finally:
        store.close()


def test_a_five_point_first_pass_records_the_receipt_its_failed_point_needs(tmp_path):
    """The fast five-point selection is not a special case: the same bytes record the same receipt.

    Five points (the four anchors plus ``sample_05_near_center``), one of them genuinely ``FAILED``.
    Nothing here depends on the selection size: the receipt comes from the batch's own verified
    cleanup event, so a short first pass reaches the retry admission exactly as a twenty-point one.
    """

    outcomes = {point_id: "PASSED" for point_id in FIVE_POINT_IDS}
    outcomes["sample_05_near_center"] = "FAILED"
    batch_root = _write_campaign_batch(
        tmp_path, outcomes, verdict="N1_CAMPAIGN_INCOMPLETE", point_ids=FIVE_POINT_IDS
    )
    terminal_receipt = _journal_final_frame_sha256(batch_root, BATCH_ID)
    service, store, root = _service(tmp_path, point_ids=FIVE_POINT_IDS)
    try:
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 is None
        projection = service.get_campaign(CAMPAIGN_ID)
        assert projection["status"] == "COMPLETED_WITH_FAILURES"
        assert projection["batch_cleanup_complete"] is True
        assert [point["point_id"] for point in projection["points"]] == list(FIVE_POINT_IDS)
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 == terminal_receipt

        store.enqueue_retries(CAMPAIGN_ID, ("sample_05_near_center",))
        request, context, intent, original_result = _retry_admission(
            root, service, store, "sample_05_near_center"
        )
        binding = store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert binding.point_id == "sample_05_near_center"
        assert binding.original_outcome == "FAILED"
        assert binding.original_result_sha256 == original_result
    finally:
        store.close()


@pytest.mark.parametrize("cleanup_complete", [False, None])
def test_a_batch_without_committed_cleanup_never_gets_a_receipt(tmp_path, cleanup_complete):
    """Bytes that do not show cleanup complete cannot produce a receipt, and the refusal stands."""

    outcomes = {point_id: "PASSED" for point_id in POINT_IDS}
    outcomes["cup_test_left_5cm"] = "FAILED"
    batch_root = _write_campaign_batch(
        tmp_path, outcomes, verdict=CAMPAIGN_INCOMPLETE, cleanup_complete=cleanup_complete
    )
    service, store, root = _service(tmp_path)
    try:
        projection = service.get_campaign(CAMPAIGN_ID)
        assert projection["batch_cleanup_complete"] is False
        assert projection["status"] == "CLEANING_UP"
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 is None

        store.enqueue_retries(CAMPAIGN_ID, ("cup_test_left_5cm",))
        request, context, intent, _result = _retry_admission(
            root, service, store, "cup_test_left_5cm"
        )
        with pytest.raises(StoreConflict, match="RETRY_ORIGINAL_CLEANUP_INCOMPLETE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 is None
    finally:
        store.close()


def test_a_different_recorded_receipt_is_never_overwritten(tmp_path):
    """The durable receipt is a fact about verified bytes: another caller may not replace it."""

    outcomes = {point_id: "PASSED" for point_id in POINT_IDS}
    outcomes["cup_test_left_5cm"] = "FAILED"
    batch_root = _write_campaign_batch(tmp_path, outcomes, verdict=CAMPAIGN_INCOMPLETE)
    service, store, _root = _service(tmp_path)
    try:
        store.record_batch_cleanup(BATCH_ID, SHA_A)
        with pytest.raises(StoreConflict, match="BATCH_CLEANUP_RECEIPT_CONFLICT"):
            store.record_batch_cleanup(BATCH_ID, SHA_B)
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 == SHA_A
        # Recording the same receipt again is the idempotent case, not a conflict.
        store.record_batch_cleanup(BATCH_ID, SHA_A)
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 == SHA_A
        # And the read path leaves the already-durable receipt exactly as it found it.
        service.get_campaign(CAMPAIGN_ID)
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 == SHA_A
        assert _journal_final_frame_sha256(batch_root, BATCH_ID) != SHA_A
    finally:
        store.close()


@pytest.mark.parametrize(
    "field,value,expected",
    [
        # The journal's leases name a selection this binding document does not describe.
        ("selection_sha256", "f" * 64, "CAMPAIGN_BINDING_INVALID"),
        # A binding document whose hashes are not hashes is refused, never read as one.
        ("config_sha256", "not-a-hash", "CAMPAIGN_FIELD_INVALID"),
        ("catalog_sha256", "not-a-hash", "CAMPAIGN_FIELD_INVALID"),
    ],
)
def test_a_binding_the_journal_does_not_reference_refuses_the_projection(
    tmp_path, field, value, expected
):
    batch_root = _write_campaign_batch(
        tmp_path, {point_id: "PASSED" for point_id in POINT_IDS}, verdict=CAMPAIGN_PASS
    )
    document = json.loads((batch_root / "selection-binding.json").read_text())
    document["binding"][field] = value
    (batch_root / "selection-binding.json").write_text(json.dumps(document))
    service, store, _root = _service(tmp_path)
    try:
        with pytest.raises(ServiceConflict, match="UPSTREAM_PROJECTION_INVALID") as refusal:
            service.get_campaign(CAMPAIGN_ID)
        assert expected in str(refusal.value.__cause__)
        assert store.read_projection_state(BATCH_ID).state is None
    finally:
        store.close()


def test_a_missing_durable_point_document_refuses_the_projection(tmp_path):
    batch_root = _write_campaign_batch(
        tmp_path, {point_id: "PASSED" for point_id in POINT_IDS}, verdict=CAMPAIGN_PASS
    )
    (batch_root / "point-results" / "task_start.json").unlink()
    service, store, _root = _service(tmp_path)
    try:
        with pytest.raises(ServiceConflict, match="UPSTREAM_PROJECTION_INVALID"):
            service.get_campaign(CAMPAIGN_ID)
        assert store.read_projection_state(BATCH_ID).state is None
    finally:
        store.close()


def _write_coordinator_batch(root, *, with_reference=True):
    """The canonical layout the service was written against: ``coordinator/`` + sealed evidence."""

    from dataclasses import asdict

    from so101_demo.parallel_batch.contracts import AttemptIdentity

    from validation_seal_fixture import make_sealed_attempt

    batch_root = (Path(root) / "campaigns" / CAMPAIGN_ID / BATCH_ID).resolve()
    batch_root.mkdir(parents=True)
    sealed_by_point = {}
    with CoordinatorJournal.create(batch_root / "coordinator", BATCH_ID) as journal:
        journal.append("CAMPAIGN_STARTED", "start", {
            "campaign_id": CAMPAIGN_ID, "batch_id": BATCH_ID,
            "runtime_identity_sha256": SHA_A, "config_sha256": SHA_CONFIG,
        })
        for index, point_id in enumerate(POINT_IDS, start=1):
            attempt_id = f"{point_id}-lease-1"
            identity = AttemptIdentity(
                BATCH_ID, 1, "worker-01", index, point_id, attempt_id, 1
            )
            sealed = make_sealed_attempt(
                batch_root / "workers" / "worker-01", identity, succeeded=True
            )
            digest = hashlib.sha256(
                (sealed.path / "attempt_result_manifest.json").read_bytes()
            ).hexdigest()
            sealed_by_point[point_id] = (sealed, digest)
            result_payload = {
                "point_id": point_id, "attempt_id": attempt_id, "outcome": "PASSED",
                "result_sha256": digest,
            }
            if with_reference:
                # The sealed reference is what authorizes the artifact import; without it the
                # canonical path refuses, exactly as it did before this change.
                result_payload["identity"] = {**asdict(identity), "location": str(sealed.path)}
                result_payload["response"] = {
                    "location": str(sealed.path), "status": "PASSED", "sha256": digest,
                }
            journal.append("POINT_LEASED", attempt_id, {
                "point_id": point_id, "attempt_id": attempt_id,
                "worker_id": "worker-01", "worker_generation": index, "lease_generation": 1,
            })
            journal.append("ATTEMPT_STARTED", f"attempt-{index}", {
                "point_id": point_id, "attempt_id": attempt_id, "worker_id": "worker-01",
            })
            journal.append("RESULT_COMMITTED", f"result-{index}", result_payload)
            journal.append("POINT_TERMINAL", f"terminal-{index}", {
                "point_id": point_id, "attempt_id": attempt_id, "result_sha256": digest,
            })
        journal.append("BATCH_TERMINAL", "batch-terminal", {
            "business_terminal": "POINTS_COMPLETE",
        })
        journal.append("CLEANUP_COMMITTED", "cleanup", {"cleanup_complete": True})
    return batch_root, sealed_by_point


def test_the_coordinator_layout_path_is_unchanged(tmp_path):
    """The canonical layout keeps its own path: epoch, sealed import, terminal and persistence."""

    _batch_root, sealed_by_point = _write_coordinator_batch(tmp_path)
    service, store, _root = _service(tmp_path)
    try:
        projection = service.get_campaign(CAMPAIGN_ID)
        assert projection["status"] == "COMPLETED"
        assert projection["batch_cleanup_complete"] is True
        by_point = {point["point_id"]: point for point in projection["points"]}
        for point_id, (sealed, digest) in sealed_by_point.items():
            assert by_point[point_id]["status"] == "PASSED"
            # The sealed attempt manifest is still what authorizes the artifact import.
            assert by_point[point_id]["artifact_ids"]
            assert digest in {artifact["sha256"] for artifact in by_point[point_id]["artifacts"]}
            assert store.read_projection_state(BATCH_ID).state.points[
                point_id
            ].result_sha256 == digest
    finally:
        store.close()


def test_the_coordinator_layout_without_a_sealed_reference_still_fails_closed(tmp_path):
    """A canonical result with no sealed reference is refused, never imported by convention."""

    _write_coordinator_batch(tmp_path, with_reference=False)
    service, store, _root = _service(tmp_path)
    try:
        with pytest.raises(ServiceConflict, match="UPSTREAM_PROJECTION_INVALID") as refusal:
            service.get_campaign(CAMPAIGN_ID)
        assert "RESULT_REFERENCE_INVALID" in str(refusal.value.__cause__)
    finally:
        store.close()


# ---------------------------------------------------------------------------------------------
# One campaign, two binding vocabularies: the retry closed loop.
#
# Recorded defect (``$RUN/task12/retry-closed-loop-20260922T063350Z``): the console's same-page
# retry was admitted, spawned a real coordinator and ran its ``FULL_RESTART_RETRY`` batch
# to ``N1_CAMPAIGN_PASS`` with complete cleanup - and the endpoint then answered
# ``409 {"code": "CAMPAIGN_FIELD_INVALID:catalog_sha256"}`` while reading that batch back. The retry
# composition writes the *same* selection in its own vocabulary: the catalog it was selected from is
# ``original_catalog_sha256`` and the one point it executes is ``point``. The readback refused
# before it could commit the batch's own cleanup frame, which is why the batch's durable receipt
# stayed NULL while its bytes showed cleanup complete.
#
# The cases below write that batch here and pin both vocabularies to one contract, so it is checked
# in the ordinary gate. The recorded bytes of that campaign are replayed separately by
# ``test/replay/replay_recorded_validation.py``, an explicit read-only entry point.
# ---------------------------------------------------------------------------------------------

RETRY_CAMPAIGN_ID = "cand-w2-retry-20260922T063350Z"
RETRY_BATCH_ID = "retry-001"
RETRY_POINT_ID = "sample_05_near_center"
#: The retry batch's own verdict about the whole retry, while the one point it executed carries its
#: own business outcome: the two are read separately and never merged into one another.
RETRY_VERDICT = "N1_CAMPAIGN_PASS"


def _campaign_upstream_binding(batch_root, batch_id, campaign_id=CAMPAIGN_ID):
    from so101_teleop.expert_validation.coordinator_events import CampaignUpstreamBinding
    from so101_teleop.expert_validation.journal_layout import resolve_fixed_journal_layout

    layout = resolve_fixed_journal_layout(Path(batch_root), batch_id)
    assert layout.layout == CAMPAIGN_LAYOUT
    return CampaignUpstreamBinding(
        campaign_id=campaign_id, batch_id=batch_id, owner_kind="COORDINATOR",
        owner_epoch_or_generation=layout.epoch, journal_root=layout.journal_root,
        batch_root=layout.batch_root,
    )


def _read_campaign_batch(batch_root, batch_id, campaign_id=CAMPAIGN_ID):
    from so101_teleop.expert_validation.campaign_layout import CampaignLayoutReader
    from so101_teleop.expert_validation.coordinator_events import (
        AcceptedCoordinatorCursor,
        ReadOnlyCoordinatorJournal,
    )

    binding = _campaign_upstream_binding(batch_root, batch_id, campaign_id)
    return binding, CampaignLayoutReader(
        ReadOnlyCoordinatorJournal(binding.journal_root, batch_id), binding
    ).read_after(AcceptedCoordinatorCursor.initial(binding))


def _write_retry_batch(root, *, outcome="FAILED", point_id=RETRY_POINT_ID,
                       batch_id=RETRY_BATCH_ID, campaign_id=RETRY_CAMPAIGN_ID,
                       cleanup_complete=True):
    """The retry composition's own batch: one point, written in the retry binding vocabulary."""

    return write_campaign_batch(
        root, {point_id: outcome}, campaign_id=campaign_id, batch_id=batch_id, kind=RETRY_KIND,
        verdict=RETRY_VERDICT, cleanup_complete=cleanup_complete,
    )


def test_a_retry_batch_is_read_in_its_own_binding_vocabulary(tmp_path):
    """RED: ``read_selection_binding`` refused these bytes with ``CAMPAIGN_FIELD_INVALID``.

    The same reader, over the same kind of batch, must find the retry's selection: the catalog the
    original selection was frozen from, named ``original_catalog_sha256``, and the one point it
    executes, named ``point``. Nothing is inferred from the document's top-level summary, which is
    only cross-checked against it.
    """

    from so101_teleop.expert_validation.campaign_layout import read_selection_binding

    batch_root = _write_retry_batch(tmp_path)
    binding = _campaign_upstream_binding(batch_root, RETRY_BATCH_ID, RETRY_CAMPAIGN_ID)

    selection = read_selection_binding(binding)
    assert selection["kind"] == RETRY_KIND == "FULL_RESTART_RETRY"
    assert selection["original_catalog_sha256"] == SHA_CATALOG
    assert "catalog_sha256" not in selection
    assert selection["point"]["point_id"] == RETRY_POINT_ID
    assert "selected_point_ids" not in selection

    batch = _read_campaign_batch(batch_root, RETRY_BATCH_ID, RETRY_CAMPAIGN_ID)[1]
    state = batch.projected_state
    assert state["terminal_reason"] == "POINTS_COMPLETE"
    assert state["batch_cleanup_complete"] is True
    assert sorted(state["points"]) == [RETRY_POINT_ID]
    assert state["points"][RETRY_POINT_ID]["status"] == "FAILED"
    assert batch.events[-1].type == "CLEANUP_COMMITTED"


def test_a_retry_batchs_own_readback_verifies_its_cleanup(tmp_path):
    """The exact call that answered 409 proves the cleanup and yields the batch's own receipt.

    ``ExpertValidationSupervisor.reconcile_retry`` reads a finished retry batch through this method
    and commits what it returns as that batch's durable ``cleanup_receipt_sha256``. The refusal, not
    a missing recording path, is what once left that column NULL: the frame returned here is the
    batch's own committed cleanup frame, and a batch that never committed cleanup has none.
    """

    from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor

    batch_root = _write_retry_batch(tmp_path)
    receipt = ExpertValidationSupervisor._verify_retry_journal(
        object.__new__(ExpertValidationSupervisor),
        SimpleNamespace(campaign_id=RETRY_CAMPAIGN_ID), RETRY_BATCH_ID, batch_root,
    )
    assert receipt == _journal_final_frame_sha256(batch_root, RETRY_BATCH_ID)

    unverified = _write_retry_batch(tmp_path / "unverified", cleanup_complete=None)
    with pytest.raises(RuntimeError, match="RETRY_CLEANUP_INCOMPLETE"):
        ExpertValidationSupervisor._verify_retry_journal(
            object.__new__(ExpertValidationSupervisor),
            SimpleNamespace(campaign_id=RETRY_CAMPAIGN_ID), RETRY_BATCH_ID, unverified,
        )


def _selection_of_size(size):
    """A first-pass selection of ``size`` points: the four anchors plus generated samples."""

    anchors = ("task_start", "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm")
    return anchors + tuple(
        f"sample_{index:02d}_near_center" for index in range(5, 5 + size - len(anchors))
    )


@pytest.mark.parametrize("size", [4, 15, 20])
def test_the_receipt_and_the_retry_admission_do_not_depend_on_the_selection_size(tmp_path, size):
    """The recorded campaigns ran 15- and 20-point first passes; the size is not a special case.

    The receipt comes from the batch's own verified cleanup frame, so a long selection reaches the
    retry admission exactly as a short one does - asserted here for the sizes the recordings used
    and for the shortest selection that still has a genuinely ``FAILED`` point.
    """

    point_ids = _selection_of_size(size)
    failed = point_ids[-1]
    outcomes = {point_id: "PASSED" for point_id in point_ids}
    outcomes[failed] = "FAILED"
    batch_root = _write_campaign_batch(
        tmp_path, outcomes, verdict=CAMPAIGN_INCOMPLETE, point_ids=point_ids
    )
    terminal_receipt = _journal_final_frame_sha256(batch_root, BATCH_ID)
    service, store, root = _service(tmp_path, point_ids=point_ids)
    try:
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 is None
        projection = service.get_campaign(CAMPAIGN_ID)
        assert projection["status"] == "COMPLETED_WITH_FAILURES"
        assert projection["batch_cleanup_complete"] is True
        assert [point["point_id"] for point in projection["points"]] == list(point_ids)
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 == terminal_receipt

        store.enqueue_retries(CAMPAIGN_ID, (failed,))
        request, context, intent, original_result = _retry_admission(root, service, store, failed)
        admitted = store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert admitted.point_id == failed
        assert admitted.original_outcome == "FAILED"
        assert admitted.original_result_sha256 == original_result
    finally:
        store.close()


def _point_document_without_committed(document):
    document["committed"] = False


def _point_document_for_another_point(document):
    document["point_id"] = "sample_99_absent"


def _point_document_for_another_attempt(document):
    document["attempt_id"] = "task_start-attempt-2"


def _point_document_with_another_outcome(document):
    document["outcome"] = "FAILED"


def _point_document_leased_for_another_point(document):
    document["lease_identity"][2] = "sample_99_absent"


def _point_document_with_a_truncated_lease(document):
    document["lease_identity"] = document["lease_identity"][:5]


def _point_document_with_another_evidence_digest(document):
    document["evidence_manifest_sha256"] = "f" * 64


def _point_document_with_another_dynamic_digest(document):
    document["dynamic_manifest_sha256"] = "f" * 64


@pytest.mark.parametrize(
    "mutate,expected",
    [
        # The four fields the reader requires: a document that does not commit this exact result is
        # refused, never read as evidence for a result it does not name.
        (_point_document_without_committed, "CAMPAIGN_POINT_RESULT_INVALID"),
        (_point_document_for_another_point, "CAMPAIGN_POINT_RESULT_INVALID"),
        (_point_document_for_another_attempt, "CAMPAIGN_POINT_RESULT_INVALID"),
        (_point_document_with_another_outcome, "CAMPAIGN_POINT_RESULT_INVALID"),
        # The lease identity ties the document to the campaign's own lease of this point.
        (_point_document_leased_for_another_point, "CAMPAIGN_POINT_RESULT_INVALID"),
        (_point_document_with_a_truncated_lease, "CAMPAIGN_POINT_RESULT_INVALID"),
        # The two manifest digests are cross-checked against the committed event naming them.
        (_point_document_with_another_evidence_digest, "CAMPAIGN_POINT_RESULT_MISMATCH"),
        (_point_document_with_another_dynamic_digest, "CAMPAIGN_POINT_RESULT_MISMATCH"),
    ],
)
def test_a_point_document_the_committed_event_does_not_verify_refuses_the_projection(
    tmp_path, mutate, expected
):
    """Every field the batch writer writes is one the reader really verifies.

    Measured, not assumed: dropping any of these fields leaves the projection green, while a *wrong*
    value refuses it. That is why the writer keeps them and writes nothing else.
    """

    batch_root = _write_campaign_batch(
        tmp_path, {point_id: "PASSED" for point_id in POINT_IDS}, verdict=CAMPAIGN_PASS
    )
    path = batch_root / "point-results" / "task_start.json"
    document = json.loads(path.read_text())
    mutate(document)
    path.write_text(json.dumps(document, sort_keys=True))
    service, store, _root = _service(tmp_path)
    try:
        with pytest.raises(ServiceConflict, match="UPSTREAM_PROJECTION_INVALID") as refusal:
            service.get_campaign(CAMPAIGN_ID)
        assert expected in str(refusal.value.__cause__)
        assert store.read_projection_state(BATCH_ID).state is None
    finally:
        store.close()


def _without_any_catalog_digest(binding_document):
    del binding_document["original_catalog_sha256"]


def _catalog_digest_the_document_does_not_name(binding_document):
    binding_document["original_catalog_sha256"] = "f" * 64


def _catalog_digest_that_is_not_a_digest(binding_document):
    binding_document["original_catalog_sha256"] = "not-a-hash"


def _two_catalog_digests_in_one_binding(binding_document):
    binding_document["catalog_sha256"] = "f" * 64


def _retry_vocabulary_under_the_first_pass_kind(binding_document):
    binding_document["kind"] = "FIRST_PASS"


def _without_any_point(binding_document):
    del binding_document["point"]


def _point_the_document_does_not_select(binding_document):
    binding_document["point"]["point_id"] = "sample_09_absent"


@pytest.mark.parametrize(
    "mutate,expected",
    [
        # A binding that names no catalog digest at all: the retry name is gone and the first-pass
        # name was never written, so there is nothing to verify and nothing may be assumed.
        (_without_any_catalog_digest, "CAMPAIGN_FIELD_INVALID:catalog_sha256"),
        # A digest the document's own top level contradicts: one binding, one catalog.
        (_catalog_digest_the_document_does_not_name, "CAMPAIGN_FIELD_INVALID:catalog_sha256"),
        (_catalog_digest_that_is_not_a_digest, "CAMPAIGN_FIELD_INVALID:catalog_sha256"),
        (_two_catalog_digests_in_one_binding, "CAMPAIGN_FIELD_INVALID:catalog_sha256"),
        # The retry vocabulary belongs to the retry kind and is never accepted on another one.
        (_retry_vocabulary_under_the_first_pass_kind, "CAMPAIGN_FIELD_INVALID:catalog_sha256"),
        # A binding that names no point at all, and one whose point is not the selection.
        (_without_any_point, "CAMPAIGN_BINDING_INVALID"),
        (_point_the_document_does_not_select, "CAMPAIGN_BINDING_INVALID"),
    ],
)
def test_a_retry_binding_that_names_no_selection_or_a_mismatched_digest_refuses(
    tmp_path, mutate, expected
):
    """Neither vocabulary is weakened: an unverifiable retry binding still fails closed.

    Every case runs over a batch written here, so each way of breaking the retry binding is checked
    in the ordinary gate instead of only where a recording happens to exist.
    """

    from so101_teleop.expert_validation.campaign_layout import read_selection_binding
    from so101_teleop.expert_validation.coordinator_events import CoordinatorProjectionError

    batch_root = _write_retry_batch(tmp_path)
    path = batch_root / "selection-binding.json"
    pristine = json.loads(path.read_text())
    document = json.loads(json.dumps(pristine))
    mutate(document["binding"])
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")

    with pytest.raises(CoordinatorProjectionError, match=expected):
        read_selection_binding(
            _campaign_upstream_binding(batch_root, RETRY_BATCH_ID, RETRY_CAMPAIGN_ID)
        )

    # The control: the same reader over the unmutated bytes this case was copied from reads them.
    path.write_text(json.dumps(pristine, indent=2, sort_keys=True) + "\n")
    assert read_selection_binding(
        _campaign_upstream_binding(batch_root, RETRY_BATCH_ID, RETRY_CAMPAIGN_ID)
    )["original_catalog_sha256"] == SHA_CATALOG
