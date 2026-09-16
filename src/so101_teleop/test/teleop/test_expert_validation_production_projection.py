import hashlib
from types import SimpleNamespace

from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_teleop.expert_validation.api import CampaignProjectionResponse
from so101_teleop.expert_validation.production import ProductionExpertValidationService


class CursorStore:
    def __init__(self):
        self.accepted = []

    def accept_upstream_cursor(self, cursor):
        self.accepted.append(cursor)


def test_get_campaign_projects_terminal_fixed_journal_and_persists_cursor(tmp_path):
    campaign_id = "campaign-a"
    batch_id = "batch-a"
    batch_root = tmp_path / "campaigns" / campaign_id / batch_id
    sealed = batch_root / "workers/worker-01/attempts/point-a/lease-1/sealed"
    sealed.mkdir(parents=True)
    manifest = sealed / "attempt_result_manifest.json"
    manifest.write_text('{"schema_version":1}', encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
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
            "ATTEMPT_STARTED", "attempt-a", {"identity": {"point_id": "point-a"}}
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
                "response": {"location": str(sealed), "sha256": digest},
            },
        )
        journal.append(
            "ATTEMPT_STARTED", "attempt-b", {"identity": {"point_id": "point-b"}}
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
                "response": {"location": str(sealed), "sha256": digest},
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
        batch_id=batch_id,
        execution_mode="SEQUENTIAL",
        evidence_root=tmp_path,
        selection=selection,
    )
    service = object.__new__(ProductionExpertValidationService)
    service.store = CursorStore()
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
