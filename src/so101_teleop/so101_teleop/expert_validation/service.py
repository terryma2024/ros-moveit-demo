"""Application service with durable idempotency and immutable manifests."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
from types import SimpleNamespace
import time
import uuid

from .execution_context import (
    CANDIDATE_CONTEXT_KIND,
    CandidateExecutionContext,
    ProductionExecutionContext,
)
from .lease import LeaseConflict

#: Every coordinate the design names for one bounded candidate run. The issuance entry point
#: requires all of them; a caller's restatement of the row the profile decides is validated against
#: the installed matrix, never trusted.
CANDIDATE_ISSUANCE_PARAMETERS = (
    "task_id",
    "dispatch_id",
    "campaign_id",
    "batch_id",
    "manifest_id",
    "execution_profile",
    "worker_count",
    "batch_kind",
    "config_document",
    "evidence_root",
    "owner_generation",
    "expires_in_s",
    "max_runs",
    "command_id",
)


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
        monotonic_ns=time.monotonic_ns,
    ) -> None:
        self.store = store
        self.supervisor = supervisor
        self.lease_service = lease_service
        self._current_source_config_sha256 = current_source_config_sha256
        self._clock_ns = clock_ns
        self._monotonic_ns = monotonic_ns
        # The two execution contexts are kept apart on purpose: a context issued for one endpoint
        # is not even looked up by the other, and presenting it there is a named refusal.
        self._candidate_contexts: dict[str, CandidateExecutionContext] = {}
        self._production_contexts: dict[str, ProductionExecutionContext] = {}

    # -- execution contexts ------------------------------------------------------------------

    def register_candidate_context(self, context: CandidateExecutionContext):
        self._candidate_contexts[context.context_id] = context
        return context

    def register_production_context(self, context: ProductionExecutionContext):
        self._production_contexts[context.context_id] = context
        return context

    def execution_context(self, context_id: str):
        """Read back one issued context, either kind, or ``None``."""

        return self._candidate_contexts.get(context_id) or self._production_contexts.get(
            context_id
        )

    def candidate_context(self, context_id: str) -> CandidateExecutionContext:
        context = self._candidate_contexts.get(context_id)
        if context is None:
            if context_id in self._production_contexts:
                raise ServiceConflict("PRODUCTION_CONTEXT_ON_CANDIDATE_ENDPOINT")
            raise ServiceConflict("EXECUTION_CONTEXT_UNKNOWN")
        return context

    def production_context(self, context_id: str) -> ProductionExecutionContext:
        context = self._production_contexts.get(context_id)
        if context is None:
            if context_id in self._candidate_contexts:
                raise ServiceConflict("CANDIDATE_CONTEXT_ON_PRODUCTION_ENDPOINT")
            raise ServiceConflict("EXECUTION_CONTEXT_UNKNOWN")
        # A production context outlives no lease: an expired one is refused rather than reused.
        if context.is_expired(self._monotonic_ns()):
            raise ServiceConflict("RETRY_CONTEXT_EXPIRED")
        return context

    def issue_candidate_context(self, **kwargs) -> CandidateExecutionContext:
        """Only a live service composed for this host can issue a context."""

        raise ServiceConflict("CANDIDATE_CONTEXT_UNAVAILABLE")

    def issue_candidate_context_api(self, body: dict) -> dict:
        """The issuance endpoint: one bounded candidate context, or a named refusal.

        Issuance is candidate-only by construction: a request that names the other kind is refused
        by name, so this endpoint can never mint production authority.
        """

        kind = body.get("context_kind") or CANDIDATE_CONTEXT_KIND
        if kind != CANDIDATE_CONTEXT_KIND:
            raise ServiceConflict("PRODUCTION_CONTEXT_ON_CANDIDATE_ENDPOINT")
        context = self.issue_candidate_context(**self._candidate_issuance_parameters(body))
        return self.candidate_context_response(context)

    def _candidate_issuance_parameters(self, body: dict) -> dict:
        return {
            name: body[name] for name in CANDIDATE_ISSUANCE_PARAMETERS if name in body
        }

    def candidate_context_response(self, context: CandidateExecutionContext) -> dict:
        """The issued context as the caller receives it: the document, plus its own digest."""

        return {**context.as_document(), "context_sha256": context.context_sha256()}

    async def start_candidate_first_pass_api(self, body: dict):
        """The candidate first-pass endpoint: the declared kind decides, and only CANDIDATE runs.

        A context of the other kind (or one this service never issued) is refused by name before
        any run is prepared, exactly as the retry endpoint refuses it.
        """

        kind = body.get("context_kind") or CANDIDATE_CONTEXT_KIND
        if kind != CANDIDATE_CONTEXT_KIND:
            raise ServiceConflict("EXECUTION_CONTEXT_KIND_INVALID")
        context_id = body.get("context_id")
        if not context_id:
            raise ServiceConflict("CANDIDATE_CONTEXT_REQUIRED")
        context = self.candidate_context(context_id)
        if context.is_expired(self._monotonic_ns()):
            # A context is dead at its deadline, before any guard probe or spawn boundary.
            raise ServiceConflict("CANDIDATE_CONTEXT_EXPIRED")
        declared = body.get("command_id")
        if declared is not None and declared != context.command_id:
            raise ServiceConflict("CANDIDATE_COMMAND_MISMATCH")
        return await self.candidate_first_pass(context, body)

    async def candidate_first_pass(self, context, body):
        raise ServiceConflict("CANDIDATE_FIRST_PASS_UNAVAILABLE")

    async def retry_campaign_api(self, campaign_id, body):
        """The one retry route: the declared context kind decides which endpoint runs it.

        A candidate context presented to the production endpoint (or the reverse) is refused by
        name, so neither context can ever be spent on the other's surface.
        """

        kind = body.get("context_kind") or "PRODUCTION"
        if kind == "CANDIDATE":
            context_id = body.get("context_id")
            if not context_id:
                raise ServiceConflict("CANDIDATE_CONTEXT_REQUIRED")
            return await self.retry_campaign_candidate(
                campaign_id, body, self.candidate_context(context_id)
            )
        if kind != "PRODUCTION":
            raise ServiceConflict("EXECUTION_CONTEXT_KIND_INVALID")
        context_id = body.get("context_id")
        if context_id is not None:
            # A presented context must be this service's own production context.
            self.production_context(context_id)
        return await self.retry_campaign(campaign_id, body)

    async def retry_campaign_candidate(self, campaign_id, body, context):
        raise ServiceConflict("CANDIDATE_RETRY_UNAVAILABLE")

    async def retry_campaign(self, campaign_id, body):
        raise ServiceConflict("PRODUCTION_RETRY_UNAVAILABLE")

    def create_manifest(self, selection, *, source_config_sha256: str, frozen_context=None):
        manifest_id = "manifest-" + uuid.uuid4().hex
        document = {
            "schema_version": 1,
            "manifest_id": manifest_id,
            **(frozen_context or {}),
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
            lease = self.lease_service.authorize(command.lease_id, command.lease_generation)
        except LeaseConflict as error:
            raise ServiceConflict(str(error)) from error
        if not self.lease_service.can_start_campaign(lease.service_session_id):
            raise ServiceConflict("VALIDATION_RECOVERY_REQUIRED")
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
