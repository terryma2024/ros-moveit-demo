"""Manifests, campaign requests, preflight and the start of a campaign."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import uuid

from so101_teleop.expert_validation.catalog import (
    CatalogPoint,
    PointSelection,
    select_catalog_points,
)
from so101_teleop.expert_validation.manifest_geometry import (
    freeze_manifest_context,
)
from so101_teleop.expert_validation.preflight import (
    CampaignStartRequest,
)
from so101_teleop.expert_validation.production_service.layout import _sha256
from so101_teleop.expert_validation.service import ServiceConflict


class CampaignStart:
    def create_manifest_from_count(self, total_points):
        selection = select_catalog_points(total_points)
        context, source_hash = freeze_manifest_context(self.layout, selection)
        manifest = self.create_manifest(
            selection, source_config_sha256=source_hash, frozen_context=context,
        )
        return self._manifest_response(manifest)

    def get_manifest_api(self, manifest_id):
        return self._manifest_response(super().get_manifest(manifest_id))

    @staticmethod
    def _manifest_response(manifest):
        document = manifest.canonical_document
        return {
            "manifest_id": manifest.manifest_id,
            "point_count": len(document["point_ids"]),
            "catalog_sha256": document["catalog_sha256"],
            "selection_sha256": document["selection_sha256"],
            "stale": manifest.stale,
            "points": document["points"],
            "manifest_sha256": manifest.manifest_sha256,
            "source_commit": document.get("source_commit"),
            "sampler_id": document.get("sampler_id"),
            "sampler_version": document.get("sampler_version"),
            "catalog_seed": document["catalog_seed"],
            "geometry_sha256": document.get("geometry_sha256"),
            "source_hashes": document.get("source_hashes"),
            "top_view": document.get("top_view"),
        }

    def _selection(self, manifest_id: str) -> PointSelection:
        manifest = super().get_manifest(manifest_id)
        if manifest.stale:
            raise ServiceConflict("VALIDATION_MANIFEST_STALE")
        document = manifest.canonical_document
        points = tuple(
            CatalogPoint(
                id=point["id"],
                display_id=point["display_id"],
                label=point["label"],
                source=point["source"],
                stratum=point["stratum"],
                position_world_m=tuple(point["position_world_m"]),
            )
            for point in document["points"]
        )
        return PointSelection(
            document["catalog_id"],
            document["catalog_seed"],
            document["catalog_sha256"],
            points,
            tuple(document["point_ids"]),
            document["selection_sha256"],
        )

    def _execution_document_binding(self, body):
        """The document and real hash a request executes.

        A request that names a macOS profile executes *that* profile's installed document: its
        own bytes, its own hash and its own worker count. Nothing is inferred from the
        selected-point count, and there is no fallback to a document the request did not name.
        """

        from so101_teleop.expert_validation.preflight import resolve_execution_document

        profile = body.get("execution_profile")
        if profile is None:
            return (Path(self.layout.parallel_config_path),
                    _sha256(self.layout.parallel_config_path))
        document = resolve_execution_document(
            Path(self.layout.parallel_config_path).parent, profile)
        return (document.path, document.config_sha256)

    def _campaign_request(self, body) -> CampaignStartRequest:
        mode = body["execution_mode"]
        adaptive = mode == "ADAPTIVE"
        batch_id = ("a" if adaptive else "b") + uuid.uuid4().hex[:4]
        selection = self._selection(body["manifest_id"])
        config_path, config_sha256 = self._execution_document_binding(body)
        resource_document = json.dumps(
            {"mode": mode, "worker_count": body.get("worker_count")},
            sort_keys=True,
        ).encode("utf-8")
        environment = {}
        if self.layout.provenance_binding is not None:
            environment["SO101_PARALLEL_PROVENANCE_BINDING"] = str(
                self.layout.provenance_binding
            )
        return CampaignStartRequest(
            campaign_id="campaign-" + uuid.uuid4().hex,
            batch_id=batch_id,
            manifest_id=body["manifest_id"],
            selection=selection,
            execution_mode=mode,
            evidence_root=self.store.root.parent,
            points_path=self.layout.points_path,
            parallel_config_path=config_path,
            adaptive_config_path=self.layout.adaptive_config_path,
            worker_count=(
                body.get("preferred_worker_count", 8)
                if adaptive
                else body.get("worker_count", 1)
            ),
            # Version two carries no lifetime quota; the field stays None for new runs.
            max_points_per_worker=None,
            fallback_worker_counts=tuple(body.get("fallback_worker_counts", (6, 4, 2, 1))),
            initial_points_per_worker=body.get("initial_points_per_worker", 3),
            worker_start_timeout_s=body.get("worker_start_timeout_s", 120.0),
            max_infra_attempts_per_point=body.get("max_infra_attempts_per_point", 5),
            yolo_executor_count=body.get("yolo_executor_count", 2),
            service_session_id=body["service_session_id"],
            lease_generation=body["lease_generation"],
            source_commit=self.layout.source_commit,
            install_prefix=str(self.layout.demo_prefix),
            coordinator_executable_sha256=_sha256(self.layout.coordinator_executable),
            adaptive_runner_module_sha256=_sha256(
                Path(__import__("so101_demo.parallel_batch.adaptive_runner", fromlist=["x"]).__file__)
            ),
            adaptive_pool_module_sha256=_sha256(
                Path(__import__("so101_demo.parallel_batch.adaptive_pool", fromlist=["x"]).__file__)
            ),
            adaptive_cleanup_executable_sha256=_sha256(self.layout.cleanup_executable),
            adaptive_wrapper_sha256=_sha256(self.layout.adaptive_wrapper),
            parallel_config_sha256=config_sha256,
            adaptive_config_sha256=_sha256(self.layout.adaptive_config_path),
            execution_profile=body.get("execution_profile"),
            batch_kind=body.get("batch_kind"),
            yolo_weights_sha256=self.layout.yolo_weights_sha256,
            grounded_sam_manifest_sha256=self.layout.grounded_manifest_sha256,
            broker_image_id=self.layout.broker_image_id,
            resource_manifest_sha256=hashlib.sha256(resource_document).hexdigest(),
            yolo_weights_path=self.layout.yolo_weights_path or Path("/models/yolo.pt"),
            grounded_root=self.layout.grounded_root or Path("/models/grounded"),
            coordinator_executable_path=self.layout.coordinator_executable,
            adaptive_wrapper_path=self.layout.adaptive_wrapper,
            provenance_binding_path=self.layout.provenance_binding,
            environment=environment,
        )

    async def preflight_api(self, body):
        self.lease_service.authorize(
            body["lease_id"],
            body["lease_generation"],
            service_session_id=body["service_session_id"],
        )
        if not self.lease_service.can_start_campaign(body["service_session_id"]):
            raise ServiceConflict("VALIDATION_RECOVERY_REQUIRED")
        capability = self.registry.require("moveit_expert", "validate_pick_place")
        availability = capability.mode_availability[body["execution_mode"]]
        if not availability.available:
            raise ServiceConflict(availability.reason or "EXECUTION_MODE_UNAVAILABLE")
        if self.layout.yolo_weights_path is None or self.layout.grounded_root is None:
            raise ServiceConflict("VALIDATION_MODELS_NOT_CONFIGURED")
        from so101_teleop.expert_validation.preflight import PreflightRejected

        try:
            request = self._campaign_request(body)
        except PreflightRejected as error:
            # A named profile whose installed document is missing or unsupported is a stable
            # refusal, never a silent fallback to a document the request did not name.
            raise ServiceConflict(str(error)) from error
        receipt = await self.supervisor.preflight(request)
        self._pending[receipt.receipt_id] = (request, receipt, dict(body))
        return {
            "receipt_id": receipt.receipt_id,
            "admitted": receipt.admitted,
            "manifest_id": receipt.manifest_id,
            "execution_mode": receipt.execution_mode,
            "execution_config": asdict(receipt.execution_config),
            "resource_observations": dict(receipt.resource_observations),
            "start_guard": receipt.resource_observations.get("start_guard"),
            "reason_codes": receipt.reason_codes,
            "expires_at_monotonic_ns": receipt.expires_at_monotonic_ns,
            "execution_profile": receipt.execution_profile,
            "execution_schema_version": receipt.schema_version,
            "execution_batch_kind": receipt.batch_kind,
        }

    async def start_campaign_api(self, body):
        # Idempotency digests only the client-visible command fields; the
        # generated campaign/batch identifiers never participate.
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        repeated = self.store.repeat_command(body["command_id"], digest)
        if repeated is not None:
            return repeated
        receipt_id = body["preflight_receipt_id"]
        try:
            request, receipt, preflight_body = self._pending[receipt_id]
        except KeyError as error:
            raise ServiceConflict("PREFLIGHT_RECEIPT_MISMATCH") from error
        comparable = {
            key: body.get(key) for key in preflight_body if key not in {"lease_id"}
        }
        expected = {
            key: value for key, value in preflight_body.items() if key not in {"lease_id"}
        }
        if comparable != expected:
            raise ServiceConflict("PREFLIGHT_REQUEST_MISMATCH")
        self.lease_service.authorize(
            body["lease_id"],
            body["lease_generation"],
            service_session_id=body["service_session_id"],
        )
        if not self.lease_service.can_start_campaign(body["service_session_id"]):
            raise ServiceConflict("VALIDATION_RECOVERY_REQUIRED")
        self.store.begin_command(body["command_id"], digest, "START_CAMPAIGN")
        result = await self.supervisor.start_first_pass(request, receipt=receipt)
        projection = {
            "campaign_id": result["campaign_id"],
            "manifest_id": request.manifest_id,
            "sequence": 1,
            "execution_mode": request.execution_mode,
            "owner_kind": "ADAPTIVE_WRAPPER" if request.execution_mode == "ADAPTIVE" else "COORDINATOR",
            "batch_id": result["batch_id"],
            "status": "STARTED",
            "points": tuple(
                {"point_id": point_id, "status": "UNRUN"}
                for point_id in request.selection.point_ids
            ),
        }
        self._campaigns[request.campaign_id] = projection
        self._campaign_requests[request.campaign_id] = request
        self.store.finish_command(body["command_id"], projection)
        del self._pending[receipt_id]
        return projection

    def list_campaigns(self):
        return tuple(self.get_campaign(campaign_id) for campaign_id in self._campaigns)

    def get_campaign(self, campaign_id):
        return self._with_retry_history(campaign_id, self._campaign_projection(campaign_id))
