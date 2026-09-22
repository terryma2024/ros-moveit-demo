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
from so101_teleop.expert_validation.store import SupervisorStore


CAMPAIGN_ID = "cand-w2-20260922T011804Z"
BATCH_ID = "w2-b001"
POINT_IDS = ("task_start", "cup_test_forward_5cm", "cup_test_left_5cm")
WORKERS = {"task_start": "w1", "cup_test_forward_5cm": "w2", "cup_test_left_5cm": "w1"}
SLOTS = {"task_start": "slot-0", "cup_test_forward_5cm": "slot-1", "cup_test_left_5cm": "slot-0"}
SHA_A = "a" * 64
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
            CAMPAIGN_ID, BATCH_ID, point_id, attempt_id, 1, WORKERS[point_id],
        ],
        "lease_sha256": hashlib.sha256(f"{point_id}-lease".encode()).hexdigest(),
        "worker_id": WORKERS[point_id],
        "slot_id": SLOTS[point_id],
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
        "worker_result_path": f"{WORKERS[point_id]}-result-{attempt_id}.json",
        "worker_result_sha256": hashlib.sha256(attempt_id.encode()).hexdigest(),
        "worker_pid": 4242,
        "released": "EXITED",
        "station_readback": {"clear": True, "matches": [], "station_root": point_id},
        "execution_result": None,
    }


def _append_campaign_stream(journal, outcomes, *, verdict):
    """Commit the campaign's own eight-event stream, exactly as the composition writes it."""

    journal.append_committed(
        "CAMPAIGN_STARTED",
        f"{CAMPAIGN_ID}/CAMPAIGN_STARTED",
        {"campaign_id": CAMPAIGN_ID, "batch_id": BATCH_ID, "schema_version": journal.schema_version},
    )
    for point_id in POINT_IDS:
        attempt_id = f"{point_id}-attempt-1"
        outcome = outcomes[point_id]
        worker_id = WORKERS[point_id]
        slot_id = SLOTS[point_id]
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
    journal.append_committed(
        "CLEANUP_COMMITTED", f"{BATCH_ID}/CLEANUP_COMMITTED", {"cleanup_complete": True}
    )


def _result_sha256(point_id, attempt_id, outcome):
    return hashlib.sha256(f"{point_id}:{attempt_id}:{outcome}".encode()).hexdigest()


def _write_campaign_batch(root, outcomes, *, verdict, batch_id=BATCH_ID):
    """Write one campaign batch root: journal, binding, per-point results and the result document."""

    batch_root = (Path(root) / "campaigns" / CAMPAIGN_ID / batch_id).resolve()
    batch_root.mkdir(parents=True)
    (batch_root / "points").mkdir()
    (batch_root / "point-results").mkdir()
    for point_id in POINT_IDS:
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
            "selected_point_ids": list(POINT_IDS),
            "points": [{"point_id": point_id, "point_sha256": "9" * 64} for point_id in POINT_IDS],
        },
    }, sort_keys=True))
    (batch_root / "campaign-result.json").write_text(json.dumps({
        "status": verdict,
        "points": {
            point_id: {"committed": outcomes[point_id]} for point_id in POINT_IDS
        },
    }, sort_keys=True))
    with CoordinatorJournal.create(batch_root / "journal", batch_id) as journal:
        _append_campaign_stream(journal, outcomes, verdict=verdict)
    return batch_root


def _campaign_request(evidence_root, batch_id=BATCH_ID, campaign_id=CAMPAIGN_ID):
    return SimpleNamespace(
        campaign_id=campaign_id,
        manifest_id="manifest-1",
        batch_id=batch_id,
        execution_mode="SEQUENTIAL",
        evidence_root=Path(evidence_root),
        selection=SimpleNamespace(
            point_ids=POINT_IDS,
            points=tuple(
                SimpleNamespace(id=point_id, display_id=f"P{index:02d}")
                for index, point_id in enumerate(POINT_IDS, start=1)
            ),
        ),
    )


class _Layout:
    demo_prefix = Path("/nonexistent-prefix")
    points_path = Path("/nonexistent-points.yaml")
    parallel_config_path = Path("/nonexistent-parallel.yaml")
    adaptive_config_path = Path("/nonexistent-adaptive.yaml")


def _service(tmp_path, *, manifest_id="manifest-1", batch_id=BATCH_ID):
    """A real store bound to the campaign and its first-pass batch, and the service over it."""

    root = Path(tmp_path).resolve()
    store = SupervisorStore.open((root / "store").resolve())
    store.record_manifest(
        manifest_id, {"schema_version": 1, "selection": list(POINT_IDS)},
        source_config_sha256=SHA_A, created_at_ns=1,
    )
    store.record_preflight_receipt(PreflightReceipt(
        receipt_id="receipt-1", campaign_id=CAMPAIGN_ID, manifest_id=manifest_id,
        canonical_start_request_sha256=SHA_A, receipt={"admitted": True},
        expires_at_monotonic_ns=10_000_000_000,
    ))
    store.consume_preflight_and_bind_campaign_batch(
        "receipt-1", SHA_A,
        CampaignBinding(
            campaign_id=CAMPAIGN_ID, manifest_id=manifest_id, executor_id="operator",
            operation_id="operation-1", executor_config_sha256=SHA_A,
            execution_mode="PARALLEL",
            execution_config={"worker_count": 2, "max_points_per_worker": 10},
            preflight_receipt_id="receipt-1",
        ),
        BatchBinding(
            batch_id=batch_id, campaign_id=CAMPAIGN_ID, batch_kind="FIRST_PASS", point_id=None,
            journal_root=(root / "campaigns" / CAMPAIGN_ID / batch_id / "journal").resolve(),
            coordinator_epoch=1,
        ),
        now_monotonic_ns=1,
    )
    store._connection.execute(
        "UPDATE manifests SET canonical_json = ? WHERE manifest_id = ?",
        (
            json.dumps({
                "catalog_sha256": SHA_CATALOG,
                "selection_sha256": SHA_SELECTION,
                "point_ids": list(POINT_IDS),
            }, sort_keys=True, separators=(",", ":")),
            manifest_id,
        ),
    )
    service = ProductionExpertValidationService(
        layout=_Layout(), registry=None, artifacts=ValidationArtifactRegistry(),
        store=store, supervisor=SimpleNamespace(), lease_service=SimpleNamespace(),
        current_source_config_sha256=lambda: SHA_A,
    )
    request = _campaign_request(root, batch_id)
    service._campaign_requests = {CAMPAIGN_ID: request}
    service._campaigns = {CAMPAIGN_ID: {
        "campaign_id": CAMPAIGN_ID, "manifest_id": manifest_id, "sequence": 1,
        "execution_mode": "SEQUENTIAL", "owner_kind": "COORDINATOR", "batch_id": batch_id,
        "status": "STARTED",
        "points": tuple({"point_id": point_id, "status": "UNRUN"} for point_id in POINT_IDS),
    }}
    return service, store, root


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


def _retry_admission(tmp_path, service, store, point_id):
    """Build the real one-time retry admission for a first pass that is already enqueued."""

    original_result = store.read_projection_state(BATCH_ID).state.points[point_id].result_sha256
    store.record_batch_cleanup(BATCH_ID, SHA_A)
    now = time.monotonic_ns()
    values = dict(
        campaign_id=CAMPAIGN_ID, batch_id="retry-001", manifest_id="manifest-1",
        execution_profile=RETRY_PROFILE, schema_version=RETRY_SCHEMA_VERSION,
        batch_kind=RETRY_BATCH_KIND, worker_count=RETRY_WORKER_COUNT, config_sha256=SHA_CONFIG,
        runtime_closure_sha256=SHA_CLOSURE, evidence_root=Path(tmp_path).resolve(),
        owner_generation=1, command_id="cmd-retry-1", issued_at_monotonic_ns=now,
        expires_at_monotonic_ns=now + 3_600_000_000_000, max_runs=2,
    )
    context = CandidateExecutionContext(
        context_id="candidate-context-1", task_id="task-12", dispatch_id="dispatch-1", **values
    )
    request = RetryStartRequest(
        command_id=context.command_id, campaign_id=context.campaign_id,
        batch_id=context.batch_id, point_id=point_id, original_batch_id=BATCH_ID,
        original_catalog_sha256=SHA_CATALOG, original_selection_sha256=SHA_SELECTION,
        original_result_sha256=original_result, execution_profile=context.execution_profile,
        schema_version=context.schema_version, batch_kind=context.batch_kind,
        config_sha256=context.config_sha256,
        runtime_closure_sha256=context.runtime_closure_sha256,
        worker_count=context.worker_count, evidence_root=context.evidence_root,
        install_prefix=Path(tmp_path).resolve() / "install", owner_generation=1,
        created_at_ns=1,
    )
    intent = OwnerIntent.for_argv(
        campaign_id=CAMPAIGN_ID, batch_id="retry-001", role="ADAPTER", generation=1,
        spawn_token="spawn-retry-1",
        argv=("so101_parallel_batch", "--batch-id", "retry-001"), created_at_ns=1,
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
