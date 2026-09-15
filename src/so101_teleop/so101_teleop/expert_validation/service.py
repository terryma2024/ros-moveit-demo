"""Application service with durable idempotency and immutable manifests."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
from types import SimpleNamespace
import time
import uuid

from .lease import LeaseConflict


class ServiceConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StartCampaignCommand:
    command_id: str
    lease_id: str
    lease_generation: int
    manifest_id: str
    request: object


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__fspath__"):
        return str(value)
    return value


def _request_hash(command: StartCampaignCommand) -> str:
    document = {
        "lease_id": command.lease_id,
        "lease_generation": command.lease_generation,
        "manifest_id": command.manifest_id,
        "request": _jsonable(command.request),
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ExpertValidationService:
    def __init__(
        self,
        *,
        store,
        supervisor,
        lease_service,
        current_source_config_sha256,
        clock_ns=time.time_ns,
    ) -> None:
        self.store = store
        self.supervisor = supervisor
        self.lease_service = lease_service
        self._current_source_config_sha256 = current_source_config_sha256
        self._clock_ns = clock_ns

    def create_manifest(self, selection, *, source_config_sha256: str):
        manifest_id = "manifest-" + uuid.uuid4().hex
        document = {
            "schema_version": 1,
            "catalog_id": selection.catalog_id,
            "catalog_seed": selection.catalog_seed,
            "catalog_sha256": selection.catalog_sha256,
            "selection_sha256": selection.selection_sha256,
            "point_ids": selection.point_ids,
            "points": [
                {
                    "id": point.id,
                    "display_id": point.display_id,
                    "label": point.label,
                    "source": point.source,
                    "stratum": point.stratum,
                    "position_world_m": point.position_world_m,
                }
                for point in selection.points
            ],
        }
        self.store.record_manifest(
            manifest_id,
            document,
            source_config_sha256=source_config_sha256,
            created_at_ns=self._clock_ns(),
        )
        return self.get_manifest(manifest_id)

    def get_manifest(self, manifest_id: str):
        manifest = self.store.manifest(
            manifest_id,
            current_source_config_sha256=self._current_source_config_sha256(),
        )
        if manifest is None:
            raise ServiceConflict("VALIDATION_MANIFEST_NOT_FOUND")
        return manifest

    def start_campaign(self, command: StartCampaignCommand):
        digest = _request_hash(command)
        repeated = self.store.repeat_command(command.command_id, digest)
        if repeated is not None:
            return repeated
        manifest = self.get_manifest(command.manifest_id)
        if manifest.stale:
            raise ServiceConflict("VALIDATION_MANIFEST_STALE")
        try:
            self.lease_service.authorize(command.lease_id, command.lease_generation)
        except LeaseConflict as error:
            raise ServiceConflict(str(error)) from error
        self.store.begin_command(command.command_id, digest, "START_CAMPAIGN")
        request = command.request
        if isinstance(request, dict):
            request = SimpleNamespace(**request)
        result = asyncio.run(self.supervisor.start_first_pass(request))
        self.store.finish_command(command.command_id, result)
        return result

    def get_campaign(self, batch_id: str):
        return self.supervisor.status(batch_id)

    def list_campaigns(self):
        return self.supervisor.list_campaigns()
