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

The real batch in this campaign's evidence root is also projected directly when it is present
(``SO101_TASK12_REAL_BATCH`` or the recorded path), so the same code is proven against the raw bytes
of a live run rather than only against this fixture.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import time

import pytest

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
WORKERS = {"task_start": "w1", "cup_test_forward_5cm": "w2", "cup_test_left_5cm": "w1"}
SLOTS = {"task_start": "slot-0", "cup_test_forward_5cm": "slot-1", "cup_test_left_5cm": "slot-0"}


def _worker_for(point_id):
    return WORKERS.get(point_id, "w1")


def _slot_for(point_id):
    return SLOTS.get(point_id, "slot-0")


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_CATALOG = "c" * 64
SHA_SELECTION = "5" * 64
SHA_CONFIG = "2" * 64
SHA_CLOSURE = "7" * 64
SHA_EVIDENCE = "e" * 64
SHA_DYNAMIC = "d" * 64
CAMPAIGN_PASS = "W2_CAMPAIGN_PASS"
CAMPAIGN_INCOMPLETE = "W2_CAMPAIGN_INCOMPLETE"

#: The one real batch this task's evidence records: journal, binding, per-point results and the
#: campaign's own result document, written by the campaign composition itself.
RECORDED_REAL_BATCH = (
    "/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1"
    "/task11/after-fix/w2-20260922T011804Z/batch"
)


def _point_document(point_id, attempt_id, outcome):
    """The campaign's durable per-point committed document (``point_drain`` shape)."""

    return {
        "schema_version": 1,
        "point_id": point_id,
        "attempt_id": attempt_id,
        "outcome": outcome,
        "committed": True,
        "lease_identity": [
            CAMPAIGN_ID, BATCH_ID, point_id, attempt_id, 1, _worker_for(point_id),
        ],
        "lease_sha256": hashlib.sha256(f"{point_id}-lease".encode()).hexdigest(),
        "worker_id": _worker_for(point_id),
        "slot_id": _slot_for(point_id),
        "generation": 1,
        "points_path": f"points/{point_id}.yaml",
        "points_sha256": hashlib.sha256(f"{point_id}-points".encode()).hexdigest(),
        "evidence_manifest_relative_path": f"{point_id}/point-result.json",
        "evidence_manifest_sha256": SHA_EVIDENCE,
        "dynamic_manifest_relative_path": f"{point_id}/dynamic-execute-manifest.json",
        "dynamic_manifest_sha256": SHA_DYNAMIC,
        "physical_evidence": outcome == "PASSED",
        "station_ready": True,
        "moveit_executed": True,
        "cleanup_owned": True,
        "failure_code": None if outcome == "PASSED" else "ANCHOR_UNREACHABLE",
        "batch_exit_code": 0,
        "worker_result_path": f"{_worker_for(point_id)}-result-{attempt_id}.json",
        "worker_result_sha256": hashlib.sha256(attempt_id.encode()).hexdigest(),
        "worker_pid": 4242,
        "released": "EXITED",
        "station_readback": {"clear": True, "matches": [], "station_root": point_id},
        "execution_result": None,
    }


def _append_campaign_stream(journal, outcomes, *, verdict, cleanup_complete=True,
                            point_ids=POINT_IDS):
    """Commit the campaign's own eight-event stream, exactly as the composition writes it.

    ``cleanup_complete=None`` omits the cleanup event altogether, so a batch can be written whose
    own bytes never claim cleanup - the negative case a receipt must never be invented from.
    """

    journal.append_committed(
        "CAMPAIGN_STARTED",
        f"{CAMPAIGN_ID}/CAMPAIGN_STARTED",
        {"campaign_id": CAMPAIGN_ID, "batch_id": BATCH_ID, "schema_version": journal.schema_version},
    )
    for point_id in point_ids:
        attempt_id = f"{point_id}-attempt-1"
        outcome = outcomes[point_id]
        worker_id = _worker_for(point_id)
        slot_id = _slot_for(point_id)
        journal.append_committed(
            "POINT_LEASED", f"{BATCH_ID}/POINT_LEASED/{attempt_id}",
            {
                "point_id": point_id, "attempt_id": attempt_id, "worker_id": worker_id,
                "slot_id": slot_id, "generation": 1,
                "lease": {"batch_id": BATCH_ID, "campaign_id": CAMPAIGN_ID, "point_id": point_id,
                          "attempt_id": attempt_id, "worker_id": worker_id, "slot_id": slot_id,
                          "generation": 1},
                "lease_sha256": hashlib.sha256(f"{point_id}-lease".encode()).hexdigest(),
                "points_path": f"points/{point_id}.yaml",
                "points_sha256": hashlib.sha256(f"{point_id}-points".encode()).hexdigest(),
                "selection_sha256": SHA_SELECTION,
            },
        )
        journal.append_committed(
            "WORKER_REGISTERED", f"{BATCH_ID}/WORKER_REGISTERED/{attempt_id}",
            {"point_id": point_id, "attempt_id": attempt_id, "worker_id": worker_id,
             "slot_id": slot_id, "generation": 1, "pid": 4242, "birth_identity": 9001,
             "status": "ACTIVE"},
        )
        journal.append_committed(
            "ATTEMPT_STARTED", f"{BATCH_ID}/ATTEMPT_STARTED/{attempt_id}",
            {"point_id": point_id, "attempt_id": attempt_id, "worker_id": worker_id,
             "slot_id": slot_id, "generation": 1, "pid": 4242,
             "lease_sha256": hashlib.sha256(f"{point_id}-lease".encode()).hexdigest(),
             "points_sha256": hashlib.sha256(f"{point_id}-points".encode()).hexdigest()},
        )
        journal.append_committed(
            "RESULT_COMMITTED", f"{BATCH_ID}/RESULT_COMMITTED/{attempt_id}",
            {"point_id": point_id, "attempt_id": attempt_id, "worker_id": worker_id,
             "slot_id": slot_id, "generation": 1, "outcome": outcome,
             "failure_code": None if outcome == "PASSED" else "ANCHOR_UNREACHABLE",
             "moveit_executed": True, "station_ready": True, "cleanup_owned": True,
             "evidence_manifest_sha256": SHA_EVIDENCE,
             "dynamic_manifest_sha256": SHA_DYNAMIC,
             "lease_identity": [CAMPAIGN_ID, BATCH_ID, point_id, attempt_id, 1, worker_id]},
        )
        journal.append_committed(
            "POINT_TERMINAL", f"{BATCH_ID}/POINT_TERMINAL/{point_id}",
            {"point_id": point_id, "attempt_id": attempt_id, "outcome": outcome,
             "state": "COMMITTED", "result_sha256": _result_sha256(point_id, attempt_id, outcome)},
        )
    journal.append_committed("BATCH_TERMINAL", f"{BATCH_ID}/BATCH_TERMINAL", {"outcome": verdict})
    if cleanup_complete is not None:
        journal.append_committed(
            "CLEANUP_COMMITTED", f"{BATCH_ID}/CLEANUP_COMMITTED",
            {"cleanup_complete": cleanup_complete},
        )


def _result_sha256(point_id, attempt_id, outcome):
    return hashlib.sha256(f"{point_id}:{attempt_id}:{outcome}".encode()).hexdigest()


def _write_campaign_batch(root, outcomes, *, verdict, batch_id=BATCH_ID, cleanup_complete=True,
                          point_ids=POINT_IDS):
    """Write one campaign batch root: journal, binding, per-point results and the result document."""

    batch_root = (Path(root) / "campaigns" / CAMPAIGN_ID / batch_id).resolve()
    batch_root.mkdir(parents=True)
    (batch_root / "points").mkdir()
    (batch_root / "point-results").mkdir()
    for point_id in point_ids:
        (batch_root / "points" / f"{point_id}.yaml").write_text(f"point_id: {point_id}\n")
        (batch_root / "point-results" / f"{point_id}.json").write_text(
            json.dumps(
                _point_document(point_id, f"{point_id}-attempt-1", outcomes[point_id]),
                sort_keys=True,
            )
        )
    (batch_root / "selection-binding.json").write_text(json.dumps({
        "batch_id": batch_id,
        "campaign_id": CAMPAIGN_ID,
        "catalog_sha256": SHA_CATALOG,
        "binding": {
            "batch_id": batch_id, "campaign_id": CAMPAIGN_ID, "kind": "FIRST_PASS",
            "catalog_schema_version": 1, "coordinate_frame": "world",
            "catalog_sha256": SHA_CATALOG, "selection_sha256": SHA_SELECTION,
            "config_sha256": SHA_CONFIG, "runtime_closure_sha256": SHA_CLOSURE,
            "selected_point_ids": list(point_ids),
            "points": [{"point_id": point_id, "point_sha256": "9" * 64} for point_id in point_ids],
        },
    }, sort_keys=True))
    (batch_root / "campaign-result.json").write_text(json.dumps({
        "status": verdict,
        "points": {
            point_id: {"committed": outcomes[point_id]} for point_id in point_ids
        },
    }, sort_keys=True))
    with CoordinatorJournal.create(batch_root / "journal", batch_id) as journal:
        _append_campaign_stream(journal, outcomes, verdict=verdict, cleanup_complete=cleanup_complete,
                                point_ids=point_ids)
    return batch_root


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


def _recorded_real_batch(projection, real_batch):
    """The strongest assertion set, shared by the fixture and the recorded live batch."""

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
        _recorded_real_batch(projection, None)
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


#: The campaign whose recorded first pass the console's same-page retry refused, and the genuinely
#: ``FAILED`` point it named. The console's request is replayed over the batch's own recorded bytes.
RECORDED_CLEANUP_STATE = Path(os.environ.get(
    "SO101_TASK12_CLEANUP_STATE",
    "/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1"
    "/task12/service-runs/retryafterfix/state",
))
RECORDED_CLEANUP_CAMPAIGN_ID = "campaign-4d9af7fca30f49939f952db367338454"
RECORDED_CLEANUP_BATCH_ID = "bf16a"
RECORDED_CLEANUP_POINT_ID = "sample_05_near_center"


def _recorded_cleanup_batch_root():
    return (
        RECORDED_CLEANUP_STATE / "campaigns" / RECORDED_CLEANUP_CAMPAIGN_ID
        / RECORDED_CLEANUP_BATCH_ID
    )


def _tree_fingerprint(root):
    """Every recorded file's path, size and mtime: a read path may not write one of them."""

    return tuple(sorted(
        (str(path.relative_to(root)), path.stat().st_size, path.stat().st_mtime_ns)
        for path in Path(root).rglob("*") if path.is_file()
    ))


@pytest.mark.skipif(
    not _recorded_cleanup_batch_root().is_dir(), reason="the recorded W1 first pass is absent"
)
def test_the_recorded_w1_first_pass_records_the_receipt_its_console_retry_needed(tmp_path):
    """The recorded 409 replayed, then answered by the same admission over the same bytes.

    The batch's own bytes are read twice: once with the campaign reader to establish, without the
    service, that this batch really shows terminal-clean cleanup and a genuine ``FAILED`` point, and
    once through the service's projection read. The recorded evidence root is read-only here, which
    the fingerprint check at the end proves.
    """

    from so101_teleop.expert_validation.campaign_layout import (
        CampaignLayoutReader,
        read_selection_binding,
    )
    from so101_teleop.expert_validation.coordinator_events import (
        AcceptedCoordinatorCursor,
        CampaignUpstreamBinding,
        ReadOnlyCoordinatorJournal,
    )
    from so101_teleop.expert_validation.journal_layout import resolve_fixed_journal_layout

    batch_root = _recorded_cleanup_batch_root()
    before = _tree_fingerprint(batch_root)
    layout = resolve_fixed_journal_layout(batch_root, RECORDED_CLEANUP_BATCH_ID)
    binding = CampaignUpstreamBinding(
        campaign_id=RECORDED_CLEANUP_CAMPAIGN_ID, batch_id=RECORDED_CLEANUP_BATCH_ID,
        owner_kind="COORDINATOR", owner_epoch_or_generation=layout.epoch,
        journal_root=layout.journal_root, batch_root=layout.batch_root,
    )
    recorded = CampaignLayoutReader(
        ReadOnlyCoordinatorJournal(layout.journal_root, RECORDED_CLEANUP_BATCH_ID), binding
    ).read_after(AcceptedCoordinatorCursor.initial(binding))
    projected = recorded.projected_state
    assert projected["terminal_reason"] == "POINTS_COMPLETE"
    assert projected["batch_cleanup_complete"] is True
    assert projected["points"][RECORDED_CLEANUP_POINT_ID]["status"] == "FAILED"
    terminal_receipt = recorded.events[-1].frame_sha256
    assert recorded.events[-1].type == "CLEANUP_COMMITTED"
    selection = read_selection_binding(binding)
    point_ids = tuple(selection["selected_point_ids"])
    assert RECORDED_CLEANUP_POINT_ID in point_ids and len(point_ids) == 20

    service, store, _root = _service(
        tmp_path, batch_id=RECORDED_CLEANUP_BATCH_ID, campaign_id=RECORDED_CLEANUP_CAMPAIGN_ID,
        point_ids=point_ids, catalog_sha256=selection["catalog_sha256"],
        selection_sha256=selection["selection_sha256"], evidence_root=RECORDED_CLEANUP_STATE,
    )
    try:
        # The recorded store carried exactly this NULL for bf16a while the campaign reported
        # cleanup complete, which is the state the console's retry was refused in.
        assert store.batch(RECORDED_CLEANUP_BATCH_ID).cleanup_receipt_sha256 is None
        store.enqueue_retries(RECORDED_CLEANUP_CAMPAIGN_ID, (RECORDED_CLEANUP_POINT_ID,))
        request, context, intent = _retry_pair(
            evidence_root=_root, campaign_id=RECORDED_CLEANUP_CAMPAIGN_ID,
            original_batch_id=RECORDED_CLEANUP_BATCH_ID, point_id=RECORDED_CLEANUP_POINT_ID,
            batch_id="retry-001", catalog_sha256=selection["catalog_sha256"],
            selection_sha256=selection["selection_sha256"],
            original_result_sha256=projected["points"][RECORDED_CLEANUP_POINT_ID]["result_sha256"],
        )
        with pytest.raises(StoreConflict, match="RETRY_ORIGINAL_CLEANUP_INCOMPLETE"):
            store.admit_retry(request=request, context=context, spawn_intent=intent)

        projection = service.get_campaign(RECORDED_CLEANUP_CAMPAIGN_ID)
        assert projection["status"] == "COMPLETED_WITH_FAILURES"
        assert projection["batch_cleanup_complete"] is True
        assert store.batch(
            RECORDED_CLEANUP_BATCH_ID
        ).cleanup_receipt_sha256 == terminal_receipt

        # The production route's own origin read agrees, and the same request is now admitted.
        _original, item, catalog, selection_sha256, result_sha256 = service._retry_origin(
            RECORDED_CLEANUP_CAMPAIGN_ID, RECORDED_CLEANUP_POINT_ID
        )
        assert item.point_id == RECORDED_CLEANUP_POINT_ID
        assert (catalog, selection_sha256) == (
            selection["catalog_sha256"], selection["selection_sha256"]
        )
        assert result_sha256 == projected["points"][RECORDED_CLEANUP_POINT_ID]["result_sha256"]
        admitted = store.admit_retry(request=request, context=context, spawn_intent=intent)
        assert admitted.original_batch_id == RECORDED_CLEANUP_BATCH_ID
        assert admitted.original_outcome == "FAILED"
        assert admitted.original_result_sha256 == result_sha256
    finally:
        store.close()
    assert _tree_fingerprint(batch_root) == before, "the recorded batch bytes were written to"


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


def _real_batch_path():
    return Path(os.environ.get("SO101_TASK12_REAL_BATCH", RECORDED_REAL_BATCH))


@pytest.mark.skipif(not _real_batch_path().is_dir(), reason="the recorded live batch is absent")
def test_the_recorded_live_batch_layout_projects_from_its_own_bytes(tmp_path):
    """The same code over the raw bytes of a real macOS campaign batch."""

    from so101_teleop.expert_validation.campaign_layout import CampaignLayoutReader
    from so101_teleop.expert_validation.coordinator_events import (
        AcceptedCoordinatorCursor,
        CampaignUpstreamBinding,
        ReadOnlyCoordinatorJournal,
    )
    from so101_teleop.expert_validation.journal_layout import resolve_fixed_journal_layout

    real = _real_batch_path()
    layout = resolve_fixed_journal_layout(real, "w2-b001")
    assert layout.layout == CAMPAIGN_LAYOUT
    binding = CampaignUpstreamBinding(
        campaign_id="cand-w2-20260922T011804Z", batch_id="w2-b001", owner_kind="COORDINATOR",
        owner_epoch_or_generation=layout.epoch, journal_root=layout.journal_root,
        batch_root=layout.batch_root,
    )
    batch = CampaignLayoutReader(
        ReadOnlyCoordinatorJournal(layout.journal_root, "w2-b001"), binding
    ).read_after(AcceptedCoordinatorCursor.initial(binding))
    state = batch.projected_state
    assert state["terminal_reason"] == "POINTS_COMPLETE"
    assert state["batch_cleanup_complete"] is True
    assert sorted(state["points"]) == [
        "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm",
        "sample_07_mid_center", "sample_12_far_left", "sample_16_far_right", "task_start",
    ]
    terminals = {
        event.payload["point_id"]: event.payload["result_sha256"]
        for event in batch.events if event.type == "POINT_TERMINAL"
    }
    assert {
        point_id: point["result_sha256"] for point_id, point in state["points"].items()
    } == terminals


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
# One campaign, two binding vocabularies: the recorded retry closed loop.
#
# Recorded defect (``$RUN/task12/retry-closed-loop-20260922T063350Z``): the console's same-page retry
# was admitted, spawned a real coordinator and ran its ``FULL_RESTART_RETRY`` batch (``retry-001``)
# to ``N1_CAMPAIGN_PASS`` with complete cleanup - and the endpoint then answered
# ``409 {"code": "CAMPAIGN_FIELD_INVALID:catalog_sha256"}`` while reading that batch back. The retry
# composition writes the *same* selection in its own vocabulary: the catalog it was selected from is
# ``original_catalog_sha256`` and the one point it executes is ``point``. The readback refused
# before it could commit the batch's own cleanup frame, which is why the batch's durable receipt
# stayed NULL while its bytes show cleanup complete.
#
# These tests read the recorded bytes of that campaign - the retry batch copied to scratch, the
# first pass in place under a fingerprint - and pin both vocabularies to one contract.
# ---------------------------------------------------------------------------------------------

RECORDED_RETRY_STATE = Path(os.environ.get(
    "SO101_TASK12_RETRY_STATE",
    "/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1"
    "/task12/service-runs/retrycl/state",
))
RECORDED_RETRY_CAMPAIGN_ID = "campaign-e94a4b7470644a59a3cf921ce6e64444"
RECORDED_RETRY_FIRST_PASS_ID = "bca3f"
RECORDED_RETRY_BATCH_ID = "retry-001"
RECORDED_RETRY_POINT_ID = "sample_05_near_center"
#: The campaign's own catalog digest; both bindings name it, each in its own vocabulary.
RECORDED_RETRY_CATALOG_SHA256 = (
    "c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5"
)
#: The first-pass selection size, and the ``FAILED`` point the retry was admitted for.
RECORDED_RETRY_FIRST_PASS_POINTS = 15


def _recorded_retry_batch_root(batch_id):
    return RECORDED_RETRY_STATE / "campaigns" / RECORDED_RETRY_CAMPAIGN_ID / batch_id


def _campaign_upstream_binding(batch_root, batch_id):
    from so101_teleop.expert_validation.coordinator_events import CampaignUpstreamBinding
    from so101_teleop.expert_validation.journal_layout import resolve_fixed_journal_layout

    layout = resolve_fixed_journal_layout(Path(batch_root), batch_id)
    assert layout.layout == CAMPAIGN_LAYOUT
    return CampaignUpstreamBinding(
        campaign_id=RECORDED_RETRY_CAMPAIGN_ID, batch_id=batch_id, owner_kind="COORDINATOR",
        owner_epoch_or_generation=layout.epoch, journal_root=layout.journal_root,
        batch_root=layout.batch_root,
    )


def _stage_recorded_batch(tmp_path, batch_id=RECORDED_RETRY_BATCH_ID):
    """The recorded retry batch copied to scratch: no reader is ever pointed at the record."""

    source = _recorded_retry_batch_root(batch_id)
    if not source.is_dir():
        pytest.skip(f"the recorded retry closed loop is not present at {source}")
    destination = tmp_path / "staged" / "campaigns" / RECORDED_RETRY_CAMPAIGN_ID / batch_id
    destination.parent.mkdir(parents=True)
    shutil.copytree(source, destination)
    return destination


def _read_recorded_batch(batch_root, batch_id):
    from so101_teleop.expert_validation.campaign_layout import CampaignLayoutReader
    from so101_teleop.expert_validation.coordinator_events import (
        AcceptedCoordinatorCursor,
        ReadOnlyCoordinatorJournal,
    )

    binding = _campaign_upstream_binding(batch_root, batch_id)
    return binding, CampaignLayoutReader(
        ReadOnlyCoordinatorJournal(binding.journal_root, batch_id), binding
    ).read_after(AcceptedCoordinatorCursor.initial(binding))


def test_the_recorded_retry_batch_is_read_in_its_own_binding_vocabulary(tmp_path):
    """RED: ``read_selection_binding`` refused these bytes with ``CAMPAIGN_FIELD_INVALID``.

    The same reader, over the same batch, must find the retry's selection: the catalog the original
    selection was frozen from, named ``original_catalog_sha256``, and the one point it executes,
    named ``point``. Nothing is inferred from the document's top-level summary, which is only
    cross-checked against it.
    """

    from so101_teleop.expert_validation.campaign_layout import read_selection_binding

    scratch = _stage_recorded_batch(tmp_path)
    before = _tree_fingerprint(scratch)
    binding = _campaign_upstream_binding(scratch, RECORDED_RETRY_BATCH_ID)

    selection = read_selection_binding(binding)
    assert selection["kind"] == "FULL_RESTART_RETRY"
    assert selection["original_catalog_sha256"] == RECORDED_RETRY_CATALOG_SHA256
    assert "catalog_sha256" not in selection
    assert selection["point"]["point_id"] == RECORDED_RETRY_POINT_ID
    assert "selected_point_ids" not in selection

    batch = _read_recorded_batch(scratch, RECORDED_RETRY_BATCH_ID)[1]
    state = batch.projected_state
    assert state["terminal_reason"] == "POINTS_COMPLETE"
    assert state["batch_cleanup_complete"] is True
    assert sorted(state["points"]) == [RECORDED_RETRY_POINT_ID]
    assert state["points"][RECORDED_RETRY_POINT_ID]["status"] == "FAILED"
    assert batch.events[-1].type == "CLEANUP_COMMITTED"
    assert _tree_fingerprint(scratch) == before, "the staged retry bytes were written to"


def test_the_recorded_retry_batchs_own_readback_verifies_its_cleanup(tmp_path):
    """The exact call that answered 409 now proves the cleanup and yields the batch's receipt.

    ``ExpertValidationSupervisor.reconcile_retry`` reads the retry batch through this method and
    commits what it returns as the batch's durable ``cleanup_receipt_sha256``. The recorded batch
    really is terminal-clean, so the refusal - not a missing recording path - is what left that
    column NULL; the returned receipt is the batch's own committed cleanup frame.
    """

    from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor

    scratch = _stage_recorded_batch(tmp_path)
    # The method reads only its arguments; no supervisor (and so no process owner) is needed here.
    receipt = ExpertValidationSupervisor._verify_retry_journal(
        object.__new__(ExpertValidationSupervisor),
        SimpleNamespace(campaign_id=RECORDED_RETRY_CAMPAIGN_ID),
        RECORDED_RETRY_BATCH_ID, scratch,
    )
    assert receipt == _journal_final_frame_sha256(scratch, RECORDED_RETRY_BATCH_ID)


def test_the_recorded_first_pass_of_the_same_campaign_still_reads_unchanged():
    """The first pass keeps its bytes and its vocabulary: nothing about it was renamed.

    The recorded store's own receipt for this batch (``9def6124…``) is the frame this reader's
    independent replay returns, so the receipt a successful readback commits and the receipt the
    database already carries for the first pass are the same fact.
    """

    from so101_teleop.expert_validation.campaign_layout import read_selection_binding

    batch_root = _recorded_retry_batch_root(RECORDED_RETRY_FIRST_PASS_ID)
    if not batch_root.is_dir():
        pytest.skip(f"the recorded first pass is not present at {batch_root}")
    before = _tree_fingerprint(batch_root)
    binding, batch = _read_recorded_batch(batch_root, RECORDED_RETRY_FIRST_PASS_ID)

    selection = read_selection_binding(binding)
    assert selection["kind"] == "FIRST_PASS"
    assert selection["catalog_sha256"] == RECORDED_RETRY_CATALOG_SHA256
    assert "original_catalog_sha256" not in selection
    point_ids = tuple(selection["selected_point_ids"])
    assert len(point_ids) == RECORDED_RETRY_FIRST_PASS_POINTS
    assert RECORDED_RETRY_POINT_ID in point_ids

    state = batch.projected_state
    assert state["terminal_reason"] == "POINTS_COMPLETE"
    assert state["batch_cleanup_complete"] is True
    assert state["points"][RECORDED_RETRY_POINT_ID]["status"] == "FAILED"
    assert batch.events[-1].type == "CLEANUP_COMMITTED"
    assert _journal_final_frame_sha256(
        batch_root, RECORDED_RETRY_FIRST_PASS_ID
    ) == "9def6124ebdeaded52534b85617bc60f76db7216c51d78b8095fc3a74285a6e4"
    assert _tree_fingerprint(batch_root) == before, "the recorded first-pass bytes were written to"


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
    """Neither vocabulary is weakened: an unverifiable retry binding still fails closed."""

    from so101_teleop.expert_validation.campaign_layout import read_selection_binding
    from so101_teleop.expert_validation.coordinator_events import CoordinatorProjectionError

    scratch = _stage_recorded_batch(tmp_path)
    path = scratch / "selection-binding.json"
    pristine = json.loads(path.read_text())
    document = json.loads(json.dumps(pristine))
    mutate(document["binding"])
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")

    with pytest.raises(CoordinatorProjectionError, match=expected):
        read_selection_binding(_campaign_upstream_binding(scratch, RECORDED_RETRY_BATCH_ID))

    # The control: the same reader over the unmutated bytes this case was copied from reads them.
    path.write_text(json.dumps(pristine, indent=2, sort_keys=True) + "\n")
    assert read_selection_binding(
        _campaign_upstream_binding(scratch, RECORDED_RETRY_BATCH_ID)
    )["original_catalog_sha256"] == RECORDED_RETRY_CATALOG_SHA256
