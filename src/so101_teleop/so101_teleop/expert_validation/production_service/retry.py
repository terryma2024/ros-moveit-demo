"""Cancel and retry of campaigns and the candidate retry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

from so101_demo.parallel_batch.contracts.common import ContractError
from so101_teleop.expert_validation.control import ControlProtocolError
from so101_teleop.expert_validation.execution_context import (
    LINUX_RETRY_PROFILE,
    LINUX_RETRY_SCHEMA_VERSION,
    RETRY_BATCH_KIND,
    RETRY_PROFILE,
    RETRY_SCHEMA_VERSION,
    RETRY_WORKER_COUNT,
    CandidateExecutionContext,
    ProductionExecutionContext,
    install_binding_sha256,
    retry_admission_command_id,
    runtime_closure_sha256,
)
from so101_teleop.expert_validation.manifest_geometry import (
    current_manifest_source_hash,
)
from so101_teleop.expert_validation.models import RetryStartRequest
from so101_teleop.expert_validation.preflight import (
    UNSUPPORTED_ON_MACOS,
    PreflightRejected,
)
from so101_teleop.expert_validation.process_owner import (
    CoordinatorOwnershipError,
    OwnedCoordinator,
)
from so101_teleop.expert_validation.production_service.layout import _sha256
from so101_teleop.expert_validation.service import ServiceConflict


class CampaignRetry:
    def cancel_campaign(self, campaign_id, body):
        document = {"operation": "CANCEL_CAMPAIGN", "campaign_id": campaign_id, "request": body}
        digest = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        repeated = self.store.repeat_command(body["command_id"], digest)
        if repeated is not None:
            # A stored outcome is a read, not renewed cancellation authority.
            return repeated
        self.lease_service.authorize(
            body["lease_id"], body["lease_generation"], service_session_id=body["service_session_id"]
        )
        projection = self.get_campaign(campaign_id)
        terminal_statuses = {
            "COMPLETED", "COMPLETED_WITH_FAILURES", "INFRA_FAILED", "CANCELLED",
        }
        clean_terminal = projection.get("batch_cleanup_complete") is True and projection["status"] in terminal_statuses
        active = getattr(self.supervisor.process_owner, "active_execution", None)
        if not clean_terminal and active is not None and (
            active.campaign_id != campaign_id or active.batch_id != projection["batch_id"]
        ):
            raise ServiceConflict("VALIDATION_CAMPAIGN_OWNER_MISMATCH")
        self.store.begin_command(body["command_id"], digest, "CANCEL_CAMPAIGN")
        if not clean_terminal and projection["status"] != "NEEDS_OPERATOR_RECOVERY":
            try:
                outcome = self.supervisor.cancel_for_reason(
                    "USER_CANCELLED", campaign_id=campaign_id, batch_id=projection["batch_id"],
                    command_id=body["command_id"],
                )
                if active is None or (isinstance(active, OwnedCoordinator) and outcome is None):
                    self.store.record_recovery_fence(
                        campaign_id, projection["batch_id"], reason="EXECUTION_OWNER_UNAVAILABLE",
                        command_id=body["command_id"],
                    )
            except (ControlProtocolError, CoordinatorOwnershipError):
                # Only a durable, campaign-bound fence resolves this Web
                # command. It is not a successful stop ACK or cleanup receipt.
                if self.store.recovery_fence(campaign_id) is None:
                    raise
            projection = self.get_campaign(campaign_id)
            if projection["status"] != "NEEDS_OPERATOR_RECOVERY" and not (
                projection.get("batch_cleanup_complete") is True and projection["status"] in terminal_statuses
            ):
                projection = {**projection, "status": "CANCELLING"}
        self._campaigns[campaign_id] = projection
        self.store.finish_command(body["command_id"], projection)
        return projection

    async def retry_campaign(self, campaign_id, body):
        """The production retry endpoint: one installed context, one point, one command."""

        document = {
            "operation": "FULL_RESTART_RETRY", "campaign_id": campaign_id, "request": body,
        }
        digest = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        repeated = self.store.repeat_command(body["command_id"], digest)
        if repeated is not None:
            return repeated
        self.lease_service.authorize(
            body["lease_id"], body["lease_generation"], service_session_id=body["service_session_id"]
        )
        if not self.lease_service.can_start_campaign(body["service_session_id"]):
            raise ServiceConflict("VALIDATION_RECOVERY_REQUIRED")
        point_ids = tuple(body["point_ids"])
        if len(point_ids) != 1:
            # A retry binding is one committed business failure; a multi-point command would have
            # to mint several contexts behind one client command id.
            raise ServiceConflict("RETRY_ONE_POINT_PER_COMMAND")
        self.store.begin_command(body["command_id"], digest, "FULL_RESTART_RETRY")
        # A dead owner may have committed cleanup while this service was down. Advance that
        # durable entry before deciding whether the new one-point command needs an enqueue.
        self.supervisor.reconcile_retry(campaign_id)
        if not any(item.state != "COMPLETE" for item in self.store.retry_items(campaign_id)):
            self.store.enqueue_retries(campaign_id, point_ids)
        self.get_campaign(campaign_id)
        request, context = self._production_retry_admission(campaign_id, point_ids[0], body)
        result = await self.supervisor.start_production_retry(request=request, context=context)
        projection = {**self.get_campaign(campaign_id), "status": result["status"]}
        self._campaigns[campaign_id] = projection
        self.store.finish_command(body["command_id"], projection)
        return projection

    def _installed_profile_document(self, execution_profile):
        from so101_teleop.expert_validation.preflight import resolve_execution_document

        try:
            installed = resolve_execution_document(
                Path(self.layout.parallel_config_path).parent, execution_profile
            )
        except PreflightRejected as error:
            raise ServiceConflict(str(error)) from error
        if installed.profile is None or installed.profile.profile != execution_profile:
            # A named profile whose installed document is not the one it claims is never inferred.
            raise ServiceConflict(UNSUPPORTED_ON_MACOS)
        return installed

    def _production_retry_admission(self, campaign_id, point_id, body):
        """Mint the one context and the one request this installed service may retry with.

        The pair is the return value: the caller admits with both, so a helper that handed back only
        the request made the retry unpacks raise ``cannot unpack non-iterable RetryStartRequest``
        before any admission and before any process existed.
        """

        original, item, catalog_sha256, selection_sha256, result_sha256 = self._retry_origin(
            campaign_id, point_id
        )
        if sys.platform.startswith("linux") and original.execution_profile is None:
            from so101_demo.parallel_batch.contracts.linux_cuda import (
                load_parallel_runtime_config_linux_cuda,
            )

            try:
                load_parallel_runtime_config_linux_cuda(Path(original.parallel_config_path))
            except (ContractError, OSError, ValueError) as error:
                raise ServiceConflict("RETRY_CONFIG_UNSUPPORTED") from error
            if _sha256(Path(original.parallel_config_path)) != original.parallel_config_sha256:
                raise ServiceConflict("RETRY_CONFIG_HASH_MISMATCH")
            retry_profile = LINUX_RETRY_PROFILE
            retry_schema_version = LINUX_RETRY_SCHEMA_VERSION
            retry_config_sha256 = original.parallel_config_sha256
        else:
            retry_profile = RETRY_PROFILE
            retry_schema_version = RETRY_SCHEMA_VERSION
            retry_config_sha256 = self._installed_profile_document(RETRY_PROFILE).config_sha256
        lease = self.store.current_lease()
        if lease is None:
            raise ServiceConflict("RETRY_LEASE_REQUIRED")
        runtime_closure = runtime_closure_sha256(original)
        install_prefix = Path(original.install_prefix)
        command_id = retry_admission_command_id(body["command_id"], item.ordinal)
        context = self.register_production_context(ProductionExecutionContext(
            context_id="production-" + uuid.uuid4().hex,
            service_session_id=lease["service_session_id"],
            lease_id=lease["lease_id"],
            lease_generation=lease["generation"],
            install_prefix=install_prefix,
            install_binding_sha256=install_binding_sha256(
                install_prefix=install_prefix, runtime_closure_sha256=runtime_closure),
            execution_profile=retry_profile,
            schema_version=retry_schema_version,
            batch_kind=RETRY_BATCH_KIND,
            worker_count=RETRY_WORKER_COUNT,
            campaign_id=campaign_id,
            batch_id=f"retry-{item.ordinal + 1:03d}",
            manifest_id=original.manifest_id,
            config_sha256=retry_config_sha256,
            runtime_closure_sha256=runtime_closure,
            evidence_root=Path(original.evidence_root),
            owner_generation=1,
            command_id=command_id,
            issued_at_monotonic_ns=time.monotonic_ns(),
            # The one-time context dies with the lease that authorized it.
            expires_at_monotonic_ns=min(
                time.monotonic_ns() + 300_000_000_000, lease["expires_monotonic_ns"]
            ),
        ))
        return (
            self._retry_start_request(
                context, item, catalog_sha256, selection_sha256, result_sha256, install_prefix
            ),
            context,
        )

    async def retry_campaign_candidate(self, campaign_id, body, context):
        """The candidate endpoint: the same one-point admission, under a candidate context."""

        if not isinstance(context, CandidateExecutionContext):
            raise ServiceConflict("CANDIDATE_CONTEXT_REQUIRED")
        document = {
            "operation": "CANDIDATE_FULL_RESTART_RETRY", "campaign_id": campaign_id,
            "request": body, "context": context.context_id,
        }
        digest = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        repeated = self.store.repeat_command(body["command_id"], digest)
        if repeated is not None:
            return repeated
        point_ids = tuple(body["point_ids"])
        if len(point_ids) != 1:
            raise ServiceConflict("RETRY_ONE_POINT_PER_COMMAND")
        self.store.begin_command(body["command_id"], digest, "CANDIDATE_FULL_RESTART_RETRY")
        self.supervisor.reconcile_retry(campaign_id)
        if not any(item.state != "COMPLETE" for item in self.store.retry_items(campaign_id)):
            self.store.enqueue_retries(campaign_id, point_ids)
        self.get_campaign(campaign_id)
        _original, item, catalog_sha256, selection_sha256, result_sha256 = self._retry_origin(
            campaign_id, point_ids[0]
        )
        request = self._retry_start_request(
            context, item, catalog_sha256, selection_sha256, result_sha256,
            Path(self._campaign_requests[campaign_id].install_prefix),
        )
        result = await self.supervisor.start_candidate_retry(request=request, context=context)
        projection = {**self.get_campaign(campaign_id), "status": result["status"]}
        self._campaigns[campaign_id] = projection
        self.store.finish_command(body["command_id"], projection)
        return projection

    def _retry_origin(self, campaign_id, point_id):
        """The durable original of one retry: its request, queue entry, manifest and result."""

        original = self._campaign_requests.get(campaign_id)
        if original is None:
            raise ServiceConflict("VALIDATION_CAMPAIGN_NOT_FOUND")
        item = self.store.next_retry(campaign_id)
        if item is None or item.point_id != point_id or item.state != "QUEUED":
            raise ServiceConflict("RETRY_NOT_QUEUED")
        first_pass = next(
            (batch for batch in self.store.campaign_batches(campaign_id)
             if batch.batch_kind == "FIRST_PASS"),
            None,
        )
        if first_pass is None:
            raise ServiceConflict("CAMPAIGN_FIRST_PASS_MISSING")
        manifest = self.store.manifest(
            original.manifest_id,
            current_source_config_sha256=current_manifest_source_hash(self.layout),
        )
        if manifest is None:
            raise ServiceConflict("VALIDATION_MANIFEST_NOT_FOUND")
        snapshot = self.store.read_projection_state(first_pass.batch_id)
        point = None if snapshot.state is None else snapshot.state.points.get(point_id)
        if point is None or point.result_sha256 is None:
            raise ServiceConflict("RETRY_ORIGINAL_RESULT_UNKNOWN")
        document = manifest.canonical_document
        return (
            original,
            item,
            document["catalog_sha256"],
            document["selection_sha256"],
            point.result_sha256,
        )

    def _retry_start_request(
        self, context, item, catalog_sha256, selection_sha256, result_sha256, install_prefix
    ):
        return RetryStartRequest(
            command_id=context.command_id,
            campaign_id=context.campaign_id,
            batch_id=context.batch_id,
            point_id=item.point_id,
            original_batch_id=next(
                batch.batch_id for batch in self.store.campaign_batches(context.campaign_id)
                if batch.batch_kind == "FIRST_PASS"
            ),
            original_catalog_sha256=catalog_sha256,
            original_selection_sha256=selection_sha256,
            original_result_sha256=result_sha256,
            execution_profile=context.execution_profile,
            schema_version=context.schema_version,
            batch_kind=context.batch_kind,
            config_sha256=context.config_sha256,
            runtime_closure_sha256=context.runtime_closure_sha256,
            worker_count=context.worker_count,
            evidence_root=context.evidence_root,
            install_prefix=install_prefix,
            owner_generation=context.owner_generation,
            created_at_ns=time.time_ns(),
        )
