from dataclasses import replace
from pathlib import Path

import pytest

from so101_teleop.expert_validation.catalog import CatalogPoint, PointSelection
from so101_teleop.expert_validation.lease import ValidationLeaseService
from so101_teleop.expert_validation.service import (
    ExpertValidationService,
    ServiceConflict,
    StartCampaignCommand,
)
from so101_teleop.expert_validation.store import StoreConflict, SupervisorStore


SHA = "a" * 64


class Supervisor:
    def __init__(self):
        self.requests = []
        self.cancel_requests = []
        self.unresolved = False

    async def start_first_pass(self, request):
        self.requests.append(request)
        return {"campaign_id": request.campaign_id, "batch_id": request.batch_id}

    def cancel_for_reason(self, reason):
        self.cancel_requests.append(reason)

    def has_unresolved_campaign(self):
        return self.unresolved


def _selection():
    points = tuple(
        CatalogPoint(
            id=f"point_{i}", label=f"Point {i}", source="generated",
            stratum="near/center", position_world_m=(float(i), 0.0, 0.0),
            display_id=f"P{i:02d}",
        )
        for i in range(1, 5)
    )
    return PointSelection("catalog", 1, SHA, points, tuple(p.id for p in points), SHA)


def _service(tmp_path, current_hash=SHA):
    store = SupervisorStore.open((tmp_path / "store").resolve())
    supervisor = Supervisor()
    lease = ValidationLeaseService(store, supervisor, clock_ns=lambda: 100, duration_ns=1_000)
    service = ExpertValidationService(
        store=store,
        supervisor=supervisor,
        lease_service=lease,
        current_source_config_sha256=lambda: current_hash,
    )
    return service, lease, supervisor, store


def test_stale_manifest_remains_readable_but_cannot_start(tmp_path):
    service, lease_service, supervisor, store = _service(tmp_path, current_hash="b" * 64)
    try:
        manifest = service.create_manifest(_selection(), source_config_sha256=SHA)
        stale = service.get_manifest(manifest.manifest_id)
        assert stale.stale
        lease = lease_service.acquire("browser-a")
        command = StartCampaignCommand(
            command_id="cmd-1",
            lease_id=lease.lease_id,
            lease_generation=lease.generation,
            manifest_id=manifest.manifest_id,
            request={"campaign_id": "campaign-1"},
        )
        with pytest.raises(ServiceConflict, match="VALIDATION_MANIFEST_STALE"):
            service.start_campaign(command)
        assert supervisor.requests == []
    finally:
        store.close()


def test_start_campaign_is_durably_idempotent(tmp_path):
    service, lease_service, supervisor, store = _service(tmp_path)
    try:
        manifest = service.create_manifest(_selection(), source_config_sha256=SHA)
        lease = lease_service.acquire("browser-a")
        command = StartCampaignCommand(
            command_id="cmd-1",
            lease_id=lease.lease_id,
            lease_generation=lease.generation,
            manifest_id=manifest.manifest_id,
            request={"campaign_id": "campaign-1", "batch_id": "b001"},
        )
        assert service.start_campaign(command) == service.start_campaign(command)
        assert len(supervisor.requests) == 1
        with pytest.raises(StoreConflict, match="COMMAND_ID_REUSED"):
            service.start_campaign(
                replace(command, request={"campaign_id": "campaign-2"})
            )
    finally:
        store.close()


def test_stale_lease_cannot_mutate(tmp_path):
    service, lease_service, _supervisor, store = _service(tmp_path)
    try:
        manifest = service.create_manifest(_selection(), source_config_sha256=SHA)
        lease = lease_service.acquire("browser-a")
        renewed = lease_service.renew(
            "browser-a", lease.lease_id, lease.generation
        )
        with pytest.raises(ServiceConflict, match="STALE_LEASE_GENERATION"):
            service.start_campaign(
                StartCampaignCommand(
                    command_id="cmd-stale",
                    lease_id=lease.lease_id,
                    lease_generation=lease.generation,
                    manifest_id=manifest.manifest_id,
                    request={"campaign_id": "campaign-1"},
                )
            )
        assert renewed.generation > lease.generation
    finally:
        store.close()


def test_expired_campaign_replacement_holder_cannot_start_new_work(tmp_path):
    service, lease_service, supervisor, store = _service(tmp_path)
    try:
        manifest = service.create_manifest(_selection(), source_config_sha256=SHA)
        first = lease_service.acquire("browser-a")
        lease_service.expire_due(now_ns=first.expires_monotonic_ns)
        replacement = lease_service.acquire("browser-b")
        # Blocking holds only while the supervisor still reports unresolved work.
        supervisor.unresolved = True
        with pytest.raises(ServiceConflict, match="VALIDATION_RECOVERY_REQUIRED"):
            service.start_campaign(StartCampaignCommand(
                command_id="cmd-replacement", lease_id=replacement.lease_id,
                lease_generation=replacement.generation, manifest_id=manifest.manifest_id,
                request={"campaign_id": "campaign-replacement", "batch_id": "replacement"},
            ))
        assert supervisor.requests == []
    finally:
        store.close()
