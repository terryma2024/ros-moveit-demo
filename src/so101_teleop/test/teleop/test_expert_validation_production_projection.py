import hashlib
import json
from dataclasses import asdict
from dataclasses import replace
from pathlib import Path
import sys
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from so101_demo.parallel_batch.contracts import AttemptIdentity
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_teleop.expert_validation.api import CampaignProjectionResponse, create_expert_validation_app
from so101_teleop.expert_validation.artifacts import ValidationArtifactRegistry
from so101_teleop.expert_validation.production import ProductionExpertValidationService
from so101_teleop.expert_validation.service import ServiceConflict
from so101_teleop.expert_validation.lease import ValidationLeaseService
from so101_teleop.expert_validation.process_owner import ExecutionProcessOwner
from so101_teleop.expert_validation.store import SupervisorStore

from test_expert_validation_supervisor import _bound_without_execution
from test_expert_validation_frozen_manifest import SameThreadApi

from validation_seal_fixture import make_sealed_attempt


class CursorStore:
    def __init__(self):
        self.accepted = []

    def accept_upstream_cursor(self, cursor):
        self.accepted.append(cursor)

    def recovery_fence(self, _campaign_id):
        return None


@contextmanager
def _control_service(tmp_path):
    supervisor, store, request = _bound_without_execution(tmp_path)
    owner = ExecutionProcessOwner(store=store)
    supervisor.process_owner = owner
    lease_service = ValidationLeaseService(store, supervisor)
    service = ProductionExpertValidationService(
        layout=SimpleNamespace(
            demo_prefix=tmp_path / "missing-prefix",
            points_path=tmp_path / "missing-points.yaml",
            parallel_config_path=tmp_path / "missing-parallel.yaml",
            adaptive_config_path=tmp_path / "missing-adaptive.yaml",
        ), registry=None, artifacts=ValidationArtifactRegistry(),
        store=store, supervisor=supervisor, lease_service=lease_service,
        current_source_config_sha256=lambda: "a" * 64,
    )
    service._campaign_requests = supervisor._requests.copy()
    service._campaigns = {request.campaign_id: {
        "campaign_id": request.campaign_id, "manifest_id": supervisor._requests[request.campaign_id].manifest_id,
        "sequence": 1, "execution_mode": "SEQUENTIAL", "owner_kind": "COORDINATOR",
        "batch_id": request.batch_id, "status": "STARTED",
        "points": tuple({"point_id": point, "status": "UNRUN"} for point in request.selected_point_ids),
    }}
    lease = lease_service.acquire("browser-a")
    body = {"command_id": "cancel-web-1", "service_session_id": lease.service_session_id,
            "lease_id": lease.lease_id, "lease_generation": lease.generation}
    try:
        yield service, owner, request, body
    finally:
        for child in owner._children.values():
            child.wait(timeout=5)
        service.store.close()


@pytest.mark.parametrize("known_target", [False, True])
def test_cancel_api_validates_campaign_target_before_touching_active_owner(tmp_path, known_target):
    with _control_service(tmp_path) as (service, owner, request, body):
        execution = owner.spawn(replace(request, argv=(sys.executable, "-c", "import time; time.sleep(0.8)")))
        if known_target:
            service._campaigns["campaign-other"] = {
                **service._campaigns[request.campaign_id], "campaign_id": "campaign-other", "batch_id": "b002",
            }
        with SameThreadApi(service) as api:
            response = api.request("POST", "/expert-validation/campaigns/campaign-other/cancel", json=body)
        expected = "VALIDATION_CAMPAIGN_OWNER_MISMATCH" if known_target else "VALIDATION_CAMPAIGN_NOT_FOUND"
        assert response.status_code == 409 and response.json() == {"code": expected}
        assert owner.poll(execution).running
        assert service.store.recovery_fence(request.campaign_id) is None
        assert service.store._connection.execute("SELECT count(*) FROM commands WHERE command_id='cancel-web-1'").fetchone()[0] == 0


def test_cancel_api_rejects_same_campaign_with_a_different_active_batch(tmp_path):
    with _control_service(tmp_path) as (service, owner, request, body):
        execution = owner.spawn(replace(request, argv=(sys.executable, "-c", "import time; time.sleep(0.8)")))
        service._campaign_requests.pop(request.campaign_id)
        service._campaigns[request.campaign_id]["batch_id"] = "b002"
        with SameThreadApi(service) as api:
            response = api.request("POST", f"/expert-validation/campaigns/{request.campaign_id}/cancel", json=body)
        assert response.status_code == 409 and response.json() == {"code": "VALIDATION_CAMPAIGN_OWNER_MISMATCH"}
        assert owner.poll(execution).running
        assert service.store.recovery_fence(request.campaign_id) is None
        assert service.store._connection.execute("SELECT count(*) FROM commands").fetchone()[0] == 0


def _coordinator_for_control_projection(service, request):
    from so101_demo.parallel_batch.contracts import BatchRequest, RunMode, load_parallel_runtime_config
    from so101_demo.parallel_batch.coordinator import BatchCoordinator

    journal = CoordinatorJournal.create(request.batch_root / "coordinator", request.batch_id)
    config = Path(__file__).resolve().parents[3] / "so101_demo_py/config/mujoco/parallel_batch_v1.yaml"
    batch = BatchRequest(request.batch_id, RunMode.EXECUTE, request.selected_point_ids, 1, 4, request.batch_root)
    coordinator = BatchCoordinator(journal, batch, config=load_parallel_runtime_config(config), result_port=None)
    coordinator.register_worker("worker-01", generation=1)
    return coordinator, journal


@pytest.mark.parametrize("cleanup,expected", [(False, "CANCELLING"), (True, "CANCELLED")])
def test_fixed_cancel_classification_preserves_upstream_unrun_statistics(tmp_path, cleanup, expected):
    with _control_service(tmp_path) as (service, _owner, request, _body):
        coordinator, journal = _coordinator_for_control_projection(service, request)
        try:
            coordinator.request_stop(reason="WEB_CANCEL_REQUESTED")
            if cleanup:
                # No Worker/controller/runtime was started or leased in this
                # unit scenario. This cannot qualify an execute point outcome.
                coordinator.complete_cleanup(owned_processes_stopped=True, controllers_stopped=True)
            with SameThreadApi(service) as api:
                response = api.request("GET", f"/expert-validation/campaigns/{request.campaign_id}")
            document = response.json()
            assert response.status_code == 200 and document["status"] == expected
            assert document["requested"] == document["not_executed"] == 4
            assert document["evaluated"] == document["execution_started"] == 0
            assert document["valid_succeeded"] == document["valid_failed"] == 0
            assert document["qualification_passed"] is False
            assert document["batch_cleanup_complete"] is cleanup
        finally:
            journal.close()


def test_cancel_of_clean_terminal_campaign_is_durable_noop_not_cancelling(tmp_path):
    with _control_service(tmp_path) as (service, _owner, request, body):
        coordinator, journal = _coordinator_for_control_projection(service, request)
        try:
            coordinator.request_stop(reason="WEB_CANCEL_REQUESTED")
            coordinator.complete_cleanup(owned_processes_stopped=True, controllers_stopped=True)
            with SameThreadApi(service) as api:
                response = api.request("POST", f"/expert-validation/campaigns/{request.campaign_id}/cancel", json=body)
            assert response.status_code == 200 and response.json()["status"] == "CANCELLED"
            assert service.store.recovery_fence(request.campaign_id) is None
            assert service.store._connection.execute("SELECT state FROM commands WHERE command_id='cancel-web-1'").fetchone()[0] == "COMPLETE"
        finally:
            journal.close()


def test_cancel_channel_failure_projects_durable_recovery_without_rewriting_points(tmp_path):
    with _control_service(tmp_path) as (service, owner, request, body):
        original = service._campaigns[request.campaign_id]["points"]
        execution = owner.spawn(replace(request, argv=(sys.executable, "-c", "import time; time.sleep(0.8)")))
        with SameThreadApi(service) as api:
            failed = api.request("POST", f"/expert-validation/campaigns/{request.campaign_id}/cancel", json=body)
            assert failed.status_code == 200 and failed.json()["status"] == "NEEDS_OPERATOR_RECOVERY"
            assert owner.poll(execution).running
            assert failed.json()["batch_cleanup_complete"] is False
        root = service.store.root
        owner._children[execution.pid].wait(timeout=3)
        service.store.close()
        service.store = SupervisorStore.open(root)
        service.supervisor.store = service.store
        service.lease_service = ValidationLeaseService(service.store, service.supervisor)
        recovery_lease = service.lease_service.acquire("browser-recovery")
        assert not service.lease_service.can_start_campaign(recovery_lease.service_session_id)
        with SameThreadApi(service) as api:
            restored = api.request("GET", f"/expert-validation/campaigns/{request.campaign_id}")
            replay = api.request("POST", f"/expert-validation/campaigns/{request.campaign_id}/cancel", json=body)
        assert restored.json()["status"] == "NEEDS_OPERATOR_RECOVERY"
        assert tuple((point["point_id"], point["status"]) for point in restored.json()["points"]) == tuple((point["point_id"], point["status"]) for point in original)
        assert replay.status_code == 200 and replay.json() == failed.json()
        assert service.store.batch(request.batch_id).cleanup_receipt_sha256 is None


@pytest.mark.parametrize("finish_before_projection", [False, True])
def test_cancel_command_replays_durably_and_conflicting_target_never_contacts_owner(tmp_path, finish_before_projection):
    with _control_service(tmp_path) as (service, owner, request, body):
        config = Path(__file__).resolve().parents[3] / "so101_demo_py/config/mujoco/parallel_batch_v1.yaml"
        program = '''
import os, pathlib, time
from so101_demo.parallel_batch.contracts import BatchRequest, RunMode, load_parallel_runtime_config
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.web_control import FixedCoordinatorControlServer
root = pathlib.Path(os.environ["TEST_BATCH_ROOT"])
with CoordinatorJournal.create(root / "coordinator", "b001") as journal:
    import json
    batch = BatchRequest("b001", RunMode.EXECUTE, tuple(json.loads(os.environ["TEST_POINT_IDS"])), 1, 4, root)
    coordinator = BatchCoordinator(journal, batch, config=load_parallel_runtime_config(os.environ["TEST_CONFIG"]), result_port=None)
    coordinator.register_worker("worker-01", generation=1)
    path = pathlib.Path(os.environ["SO101_FIXED_CONTROL_SOCKET"])
    path.parent.mkdir(mode=0o700)
    server = FixedCoordinatorControlServer(coordinator=coordinator, campaign_id=os.environ["SO101_FIXED_CONTROL_CAMPAIGN_ID"], control_token=os.environ["SO101_FIXED_CONTROL_TOKEN"], path=path)
    server.start()
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if os.environ["TEST_COMPLETE_CLEANUP"] == "1" and coordinator.snapshot().terminal_reason and not coordinator.snapshot().summary.batch_cleanup_complete:
                # No Worker/controller was launched or leased: unit cleanup
                # exercises the public gate, never physical qualification.
                coordinator.complete_cleanup(owned_processes_stopped=True, controllers_stopped=True)
                (root / "unit-cleanup-complete").touch()
            time.sleep(0.01)
    finally:
        server.close()
'''
        execution = owner.spawn(replace(request, argv=(sys.executable, "-c", program), environment={
            **request.environment, "TEST_BATCH_ROOT": str(request.batch_root), "TEST_CONFIG": str(config),
            "TEST_POINT_IDS": json.dumps(request.selected_point_ids),
            "TEST_COMPLETE_CLEANUP": "1" if finish_before_projection else "0",
        }))
        deadline = time.monotonic() + 2
        while not request.control_socket.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert request.control_socket.exists()
        if finish_before_projection:
            real_cancel = service.supervisor.cancel_for_reason

            def cancel_then_wait_for_actual_journal(*args, **kwargs):
                response = real_cancel(*args, **kwargs)
                deadline = time.monotonic() + 1
                while not (request.batch_root / "unit-cleanup-complete").exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert (request.batch_root / "unit-cleanup-complete").exists()
                return response

            # Establish the scheduling boundary using the real child, real
            # transport, real public cleanup gate and fsynced journal.
            service.supervisor.cancel_for_reason = cancel_then_wait_for_actual_journal
        with SameThreadApi(service) as api:
            first = api.request("POST", f"/expert-validation/campaigns/{request.campaign_id}/cancel", json=body)
            replay = api.request("POST", f"/expert-validation/campaigns/{request.campaign_id}/cancel", json=body)
            conflict = api.request("POST", "/expert-validation/campaigns/campaign-other/cancel", json=body)
        assert first.status_code == replay.status_code == 200
        assert replay.json() == first.json()
        assert first.json()["status"] == ("CANCELLED" if finish_before_projection else "CANCELLING")
        assert first.json()["batch_cleanup_complete"] is finish_before_projection
        assert first.json()["qualification_passed"] is False
        assert conflict.status_code == 409 and conflict.json() == {"code": "COMMAND_ID_REUSED"}
        assert owner.poll(execution).running
        assert service.store.recovery_fence(request.campaign_id) is None
        assert service.store._connection.execute("SELECT state FROM commands WHERE command_id=?", (body["command_id"],)).fetchone()[0] == "COMPLETE"


def _one_committed_service(tmp_path, *, identity_change=None, committed=True):
    root = tmp_path / "campaigns/campaign-a/batch-a"
    who = AttemptIdentity("batch-a", 1, "worker-01", 1, "point-a", "lease-1", 1)
    sealed = make_sealed_attempt(root / "workers/worker-01", who, succeeded=False)
    manifest = sealed.path / "attempt_result_manifest.json"
    identity = asdict(who)
    identity.update(identity_change or {})
    with CoordinatorJournal.create(root / "coordinator", "batch-a") as journal:
        journal.append("BATCH_STARTED", "start", {"delta": {"points": {
            "point-a": {"status": "UNRUN", "attempts": 1, "terminal": False},
        }}})
        if committed:
            journal.append("RESULT_COMMITTED", "result", {
                "identity": {**identity, "location": str(sealed.path)},
                "response": {"location": str(sealed.path), "status": "FAILED",
                             "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()},
                "delta": {"points": {"point-a": {
                    "status": "FAILED", "attempts": 1, "terminal": True,
                }}},
            })
    service = object.__new__(ProductionExpertValidationService)
    service.store = CursorStore()
    service.artifacts = ValidationArtifactRegistry()
    service._campaigns = {"campaign-a": {"campaign_id": "campaign-a", "sequence": 0}}
    service._campaign_requests = {"campaign-a": SimpleNamespace(
        campaign_id="campaign-a", manifest_id="manifest-a", batch_id="batch-a", execution_mode="SEQUENTIAL",
        evidence_root=tmp_path, selection=SimpleNamespace(
            point_ids=("point-a",), points=(SimpleNamespace(id="point-a", display_id="P01"),),
        ),
    )}
    return service, sealed


@pytest.mark.parametrize("identity_change", [
    {"point_id": "point-b"}, {"worker_id": "worker-02"},
    {"worker_generation": 2}, {"attempt_id": "other-attempt"},
    {"batch_id": "other-batch"}, {"lease_generation": 2},
])
def test_committed_evidence_identity_mismatch_blocks_projection_before_cursor(tmp_path, identity_change):
    service, _ = _one_committed_service(tmp_path, identity_change=identity_change)
    with pytest.raises(ServiceConflict, match="UPSTREAM_PROJECTION_INVALID"):
        service.get_campaign("campaign-a")
    assert service.store.accepted == []


def test_committed_evidence_content_drift_blocks_projection_before_cursor(tmp_path):
    service, sealed = _one_committed_service(tmp_path)
    image = sealed.path / "initial-rgb.png"
    image.chmod(0o644)
    image.write_bytes(b"drift")
    with pytest.raises(ServiceConflict, match="UPSTREAM_PROJECTION_INVALID"):
        service.get_campaign("campaign-a")
    assert service.store.accepted == []


def test_uncommitted_worker_seal_is_not_scanned_or_exposed(tmp_path):
    service, _ = _one_committed_service(tmp_path, committed=False)
    point = service.get_campaign("campaign-a")["points"][0]
    assert point["artifact_ids"] == ()
    assert point.get("artifacts", ()) == ()


def test_get_campaign_projects_terminal_fixed_journal_and_persists_cursor(tmp_path):
    campaign_id = "campaign-a"
    batch_id = "batch-a"
    batch_root = tmp_path / "campaigns" / campaign_id / batch_id
    identities = {
        point: AttemptIdentity(batch_id, 1, "worker-01", index, point, f"{point}-lease-1", 1)
        for index, point in enumerate(("point-a", "point-b"), start=1)
    }
    seals = {
        point: make_sealed_attempt(batch_root / "workers/worker-01", who)
        for point, who in identities.items()
    }
    references = {
        point: {"location": str(seal.path), "status": "PASSED",
                "sha256": hashlib.sha256((seal.path / "attempt_result_manifest.json").read_bytes()).hexdigest()}
        for point, seal in seals.items()
    }
    with CoordinatorJournal.create(batch_root / "coordinator", batch_id) as journal:
        journal.append(
            "BATCH_STARTED",
            "start",
            {
                "delta": {
                    "points": {
                        "point-a": {"status": "UNRUN", "attempts": 0, "terminal": False},
                        "point-b": {"status": "UNRUN", "attempts": 0, "terminal": False},
                    },
                    "workers": {
                        "worker-01": {
                            "generation": 1,
                            "state": "AVAILABLE",
                            "lease_count": 0,
                            "lease": None,
                        }
                    },
                    "broker_healthy": True,
                    "batch_cleanup_complete": False,
                }
            },
        )
        journal.append(
            "ATTEMPT_STARTED", "attempt-a", {"identity": asdict(identities["point-a"])}
        )
        journal.append(
            "RESULT_COMMITTED",
            "result-a",
            {
                "delta": {
                    "points": {
                        "point-a": {"status": "PASSED", "attempts": 1, "terminal": True}
                    }
                },
                "identity": {**asdict(identities["point-a"]), "location": str(seals["point-a"].path)},
                "response": references["point-a"],
            },
        )
        journal.append(
            "ATTEMPT_STARTED", "attempt-b", {"identity": asdict(identities["point-b"])}
        )
        journal.append(
            "RESULT_COMMITTED",
            "result-b",
            {
                "delta": {
                    "points": {
                        "point-b": {"status": "PASSED", "attempts": 1, "terminal": True}
                    }
                },
                "identity": {**asdict(identities["point-b"]), "location": str(seals["point-b"].path)},
                "response": references["point-b"],
            },
        )
        journal.append(
            "BATCH_CLEANUP_COMPLETE",
            "cleanup",
            {
                "delta": {
                    "workers": {
                        "worker-01": {
                            "generation": 2,
                            "state": "STOPPED",
                            "lease_count": 2,
                            "lease": None,
                        }
                    },
                    "terminal_reason": "POINTS_COMPLETE",
                    "batch_cleanup_complete": True,
                }
            },
        )

    selection = SimpleNamespace(
        point_ids=("point-a", "point-b"),
        points=(
            SimpleNamespace(id="point-a", display_id="P01"),
            SimpleNamespace(id="point-b", display_id="P02"),
        ),
    )
    request = SimpleNamespace(
        campaign_id=campaign_id,
        manifest_id="manifest-a",
        batch_id=batch_id,
        execution_mode="SEQUENTIAL",
        evidence_root=tmp_path,
        selection=selection,
    )
    service = object.__new__(ProductionExpertValidationService)
    service.store = CursorStore()
    service.artifacts = ValidationArtifactRegistry()
    service._campaigns = {
        campaign_id: {
            "campaign_id": campaign_id,
            "sequence": 1,
            "execution_mode": "SEQUENTIAL",
            "owner_kind": "COORDINATOR",
            "batch_id": batch_id,
            "status": "STARTED",
            "points": (
                {"point_id": "point-a", "status": "UNRUN"},
                {"point_id": "point-b", "status": "UNRUN"},
            ),
        }
    }
    service._campaign_requests = {campaign_id: request}

    projected = service.get_campaign(campaign_id)

    assert projected["status"] == "COMPLETED"
    assert projected["manifest_id"] == "manifest-a"
    assert projected["sequence"] == 6
    assert [(point["display_id"], point["status"]) for point in projected["points"]] == [
        ("P01", "PASSED"),
        ("P02", "PASSED"),
    ]
    assert projected["requested"] == projected["evaluated"] == 2
    assert projected["valid_succeeded"] == 2
    assert projected["execution_started"] == 2
    assert projected["qualification_passed"] is True
    assert projected["batch_cleanup_complete"] is True
    assert projected["workers"] == (
        {
            "worker_id": "worker-01",
            "generation": 2,
            "state": "STOPPED",
            "current_point_id": None,
            "lease_count": 2,
            "recovery_result": None,
            "quarantine_reason": None,
        },
    )
    assert len(service.store.accepted) == 1
    assert service.store.accepted[0].event_id == "event-00000000000000000006"
    assert CampaignProjectionResponse.model_validate(projected).status == "COMPLETED"
    for point in projected["points"]:
        assert len(point["attempts"]) == 1
        assert point["attempts"][0]["status"] == "PASSED"
        views = {artifact["role"]: artifact for artifact in point["artifacts"]}
        assert {"task-rgb-before", "task-rgb-after", "depth-evidence", "tf-evidence",
                "physical-evidence", "dynamic-execute", "sealed-result"} <= views.keys()
        assert views["task-rgb-before"]["media_type"] == "image/png"
        assert set(point["artifact_ids"]) == {artifact["artifact_id"] for artifact in point["artifacts"]}
        for artifact in point["artifacts"]:
            assert artifact["attempt_id"] == identities[point["point_id"]].attempt_id
            assert artifact["worker_generation"] == identities[point["point_id"]].worker_generation
    assert set(projected["points"][0]["artifact_ids"]).isdisjoint(projected["points"][1]["artifact_ids"])
    assert str(tmp_path) not in json.dumps(projected)
    client = TestClient(create_expert_validation_app(service))
    before = projected["points"][0]["artifacts"][0]
    response = client.get(f'/expert-validation/artifacts/{before["artifact_id"]}')
    assert response.status_code == 200
    assert hashlib.sha256(response.content).hexdigest() == before["sha256"]


def test_get_campaign_keeps_last_projection_during_an_incomplete_journal_frame(tmp_path):
    batch_root = tmp_path / "campaigns/campaign-a/batch-a"
    with CoordinatorJournal.create(batch_root / "coordinator", "batch-a") as journal:
        journal.append("BATCH_STARTED", "start", {"delta": {"points": {}}})
        segment = journal.segment_path
    segment.write_bytes(segment.read_bytes() + b"\x00\x00\x00")
    before = segment.read_bytes()
    cached = {"campaign_id": "campaign-a", "sequence": 1, "status": "RUNNING"}
    service = object.__new__(ProductionExpertValidationService)
    service.store = CursorStore()
    service._campaigns = {"campaign-a": cached}
    service._campaign_requests = {
        "campaign-a": SimpleNamespace(
            campaign_id="campaign-a",
            manifest_id="manifest-a",
            batch_id="batch-a",
            execution_mode="SEQUENTIAL",
            evidence_root=tmp_path,
        )
    }

    assert service.get_campaign("campaign-a") is cached
    assert service.store.accepted == []
    assert segment.read_bytes() == before


def test_fixed_projection_maps_real_active_attempt_and_counts_only_started_execution(tmp_path):
    batch_root = tmp_path / "campaigns/campaign-a/batch-a"
    service = object.__new__(ProductionExpertValidationService)
    service.store = CursorStore()
    request = SimpleNamespace(
        campaign_id="campaign-a",
        manifest_id="manifest-a",
        batch_id="batch-a",
        execution_mode="SEQUENTIAL",
        evidence_root=tmp_path,
        selection=SimpleNamespace(
            point_ids=("point-a",),
            points=(SimpleNamespace(id="point-a", display_id="P01"),),
        ),
    )
    with CoordinatorJournal.create(batch_root / "coordinator", "batch-a") as journal:
        journal.append(
            "LEASE_GRANTED",
            "lease",
            {
                "delta": {
                    "points": {
                        "point-a": {
                            "status": "UNRUN", "attempts": 1, "terminal": False,
                            "active_attempt": "point-a-lease-1",
                        }
                    },
                    "workers": {
                        "worker-01": {
                            "generation": 1, "state": "INITIALIZING", "lease_count": 1,
                            "lease": {"point_id": "point-a", "attempt_id": "point-a-lease-1"},
                        }
                    },
                }
            },
        )

        before_execution = service._fixed_campaign_projection(request)

        assert before_execution["status"] == "RUNNING"
        assert before_execution["execution_started"] == 0
        assert before_execution["points"][0]["active_worker_id"] == "worker-01"
        assert before_execution["workers"][0]["current_point_id"] == "point-a"
        journal.append(
            "ATTEMPT_STARTED",
            "attempt",
            {
                "identity": {"point_id": "point-a"},
                "delta": {"workers": {"worker-01": {"state": "EXECUTING"}}},
            },
        )
        assert service._fixed_campaign_projection(request)["execution_started"] == 1


def _adaptive_service(tmp_path, *, point_ids=("point-a", "point-b")):
    service = object.__new__(ProductionExpertValidationService)
    service.store = CursorStore()
    service._campaigns = {"campaign-a": {"campaign_id": "campaign-a", "sequence": 0, "status": "STARTED"}}
    service._campaign_requests = {
        "campaign-a": SimpleNamespace(
            campaign_id="campaign-a",
            manifest_id="manifest-a",
            batch_id="batch-a",
            execution_mode="ADAPTIVE",
            evidence_root=tmp_path,
            selection=SimpleNamespace(
                point_ids=point_ids,
                points=tuple(
                    SimpleNamespace(id=point_id, display_id=f"P{index:02d}")
                    for index, point_id in enumerate(point_ids, start=1)
                ),
            ),
        )
    }
    return service


def _adaptive_journal(tmp_path):
    batch_root = tmp_path / "campaigns/campaign-a/batch-a"
    return CoordinatorJournal.create(batch_root / "r/batch-a/journal", "batch-a")


def test_adaptive_projection_advances_from_runner_journal(tmp_path):
    service = _adaptive_service(tmp_path)
    with _adaptive_journal(tmp_path) as journal:
        journal.append("BATCH_MANIFEST", "manifest", {"selected_point_ids": ["point-a", "point-b"]})
        journal.append("POOL_STARTING", "pool-starting-01", {"generation": 1, "worker_count": 8})

        running = service.get_campaign("campaign-a")
        assert running["status"] == "RUNNING"
        assert running["owner_kind"] == "ADAPTIVE_WRAPPER"
        assert running["levels_used"] == (8,)
        assert running["points"][0]["status"] == "UNRUN"
        assert running["requested"] == 2

        journal.append("POINT_RESULT_IMPORTED", "result-a", {"generation": 1, "result": {
            "point_id": "point-a", "status": "PASSED",
            "evidence_root": str(tmp_path / "g1"), "infra_attempts": 0,
        }})
        journal.append("POINT_RESULT_IMPORTED", "result-b", {"generation": 1, "result": {
            "point_id": "point-b", "status": "FAILED",
            "evidence_root": str(tmp_path / "g1"), "infra_attempts": 0,
        }})
        journal.append("BATCH_TERMINAL", "batch-terminal", {
            "status": "COMPLETED_WITH_FAILURES", "initial_worker_count": 8,
            "final_worker_count": 8, "levels_used": [8], "point_results": [],
            "transitions": [], "cleanup_complete": True,
        })

        terminal = service.get_campaign("campaign-a")
        assert terminal["status"] == "COMPLETED_WITH_FAILURES"
        assert terminal["batch_cleanup_complete"] is True
        assert terminal["valid_succeeded"] == 1 and terminal["valid_failed"] == 1
        assert terminal["qualification_passed"] is False
        points = {point["point_id"]: point for point in terminal["points"]}
        assert points["point-b"]["retry_eligible"] is True
        assert points["point-a"]["retry_eligible"] is False
        assert len(service.store.accepted) == 2
        assert service.store.accepted[-1].owner_kind == "ADAPTIVE_RUNNER"


def test_adaptive_projection_falls_back_to_cache_before_runner_journal_exists(tmp_path):
    service = _adaptive_service(tmp_path)
    cached = service._campaigns["campaign-a"]
    assert service.get_campaign("campaign-a") is cached
    assert service.store.accepted == []
