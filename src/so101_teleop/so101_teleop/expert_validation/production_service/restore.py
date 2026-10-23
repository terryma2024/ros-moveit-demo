"""Restore campaigns and their requests from the store after a restart."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from so101_demo.parallel_batch.contracts.common import ContractError
from so101_teleop.expert_validation.coordinator_events import (
    CoordinatorProjectionError,
)
from so101_teleop.expert_validation.preflight import (
    UNSUPPORTED_ON_MACOS,
    CampaignStartRequest,
)
from so101_teleop.expert_validation.production_service.layout import PROFILES_BY_NAME, _sha256
from so101_teleop.expert_validation.service import ServiceConflict
from so101_teleop.expert_validation.statistics import (
    StatisticsProjectionError,
)
from so101_teleop.expert_validation.supervisor_store.schema import StoreConflict


#: Native multi-worker execution was removed. Campaigns of these modes that are stored but not cleanly
#: finished cannot be adopted by a single-worker service; they are fenced to operator recovery instead.
MULTI_WORKER_MODES = frozenset({"PARALLEL", "ADAPTIVE"})
_CLEAN_TERMINAL_STATUSES = frozenset({"COMPLETED", "COMPLETED_WITH_FAILURES", "INFRA_FAILED", "CANCELLED"})
MULTI_WORKER_REMOVED_FENCE_REASON = "NATIVE_MULTI_WORKER_REMOVED"


class CampaignRestore:
    def _fence_removed_multi_worker_campaign(self, request, projection):
        """Fence a stored non-terminal PARALLEL or ADAPTIVE campaign; never relaunch it.

        A clean terminal campaign (a terminal status with its batch cleanup confirmed) stays readable as stored.
        Anything else may still own processes or unconfirmed cleanup, which only an operator can account for.
        """
        clean_terminal = (
            projection.get("status") in _CLEAN_TERMINAL_STATUSES
            and projection.get("batch_cleanup_complete") is True
        )
        if clean_terminal:
            return projection
        if self.store.recovery_fence(request.campaign_id) is None:
            self.store.record_recovery_fence(
                request.campaign_id,
                request.batch_id,
                reason=MULTI_WORKER_REMOVED_FENCE_REASON,
                command_id=f"restore-fence-{request.campaign_id}",
            )
        return {**projection, "status": "NEEDS_OPERATOR_RECOVERY"}

    def _restore_campaigns(self) -> None:
        """Rebind durable campaigns after a restart so reads reconcile."""
        for row in self.store.campaign_records():
            campaign_id = row["campaign_id"]
            try:
                request = self._restored_request(row)
            except (ServiceConflict, StoreConflict, KeyError, ValueError):
                continue
            self._campaign_requests[campaign_id] = request
            self.supervisor._requests[campaign_id] = request
            projection: dict[str, object] = {
                "campaign_id": campaign_id,
                "manifest_id": request.manifest_id,
                "sequence": 1,
                "execution_mode": request.execution_mode,
                "owner_kind": (
                    "ADAPTIVE_WRAPPER" if request.execution_mode == "ADAPTIVE" else "COORDINATOR"
                ),
                "batch_id": request.batch_id,
                "status": "STARTED",
                "points": tuple(
                    {"point_id": point_id, "status": "UNRUN"}
                    for point_id in request.selection.point_ids
                ),
            }
            try:
                if request.execution_mode == "ADAPTIVE":
                    projected = self._adaptive_campaign_projection(request)
                else:
                    projected = self._fixed_campaign_projection(request)
            except (
                CoordinatorProjectionError,
                ContractError,
                StatisticsProjectionError,
            ):
                projected = None
            if projected is not None:
                projection = projected
            if request.execution_mode in MULTI_WORKER_MODES:
                projection = self._fence_removed_multi_worker_campaign(request, projection)
            self._campaigns[campaign_id] = projection

    def _restored_request(self, row) -> CampaignStartRequest:
        batches = self.store.campaign_batches(row["campaign_id"])
        first_pass = next(
            (batch for batch in batches if batch.batch_kind == "FIRST_PASS"), None
        )
        if first_pass is None:
            raise ServiceConflict("CAMPAIGN_FIRST_PASS_MISSING")
        config = json.loads(row["execution_config_json"])
        selection = self._selection(row["manifest_id"])
        # The durable receipt decided which installed document this campaign executed. A restart
        # that rebuilt a v5/v6 campaign against the *configured* document would hand it different
        # bytes than the ones its own results were produced with, so the receipt is the binding.
        profile, config_path, config_sha256, worker_count = self._restored_execution_binding(row)
        if profile is not None:
            row_mode = PROFILES_BY_NAME[profile].execution_mode
            if row["execution_mode"] != row_mode:
                raise ServiceConflict("CAMPAIGN_PROFILE_MODE_MISMATCH")
        environment = {}
        if self.layout.provenance_binding is not None:
            environment["SO101_PARALLEL_PROVENANCE_BINDING"] = str(
                self.layout.provenance_binding
            )
        adaptive = row["execution_mode"] == "ADAPTIVE"
        resource_document = json.dumps(
            {"mode": row["execution_mode"], "worker_count": config.get("worker_count")},
            sort_keys=True,
        ).encode("utf-8")
        return CampaignStartRequest(
            campaign_id=row["campaign_id"],
            batch_id=first_pass.batch_id,
            manifest_id=row["manifest_id"],
            selection=selection,
            execution_mode=row["execution_mode"],
            evidence_root=self.store.root.parent,
            points_path=self.layout.points_path,
            parallel_config_path=config_path,
            adaptive_config_path=self.layout.adaptive_config_path,
            worker_count=(
                worker_count
                if profile is not None
                else (
                    config.get("preferred_worker_count", 8)
                    if adaptive
                    else config.get("worker_count", 1)
                )
            ),
            max_points_per_worker=config.get("max_points_per_worker"),
            fallback_worker_counts=tuple(config.get("fallback_worker_counts", (6, 4, 2, 1))),
            initial_points_per_worker=config.get("initial_points_per_worker", 3),
            worker_start_timeout_s=config.get("worker_start_timeout_s", 120.0),
            max_infra_attempts_per_point=config.get("max_infra_attempts_per_point", 5),
            yolo_executor_count=config.get("yolo_executor_count", 2),
            service_session_id=row.get("service_session_id") or "",
            lease_generation=row.get("lease_generation") or 1,
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
            execution_profile=profile,
            batch_kind=(None if profile is None else PROFILES_BY_NAME[profile].batch_kind),
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

    def _restored_execution_binding(self, row) -> tuple[str | None, Path, str, int]:
        """The profile, document, hash and worker count a restored campaign really executed.

        The receipt carries the profile its preflight bound. When it names one, that profile's own
        installed document is resolved again - never the configured document - so a restarted
        service rebuilds the campaign against the bytes that produced its results.
        """

        from so101_teleop.expert_validation.preflight import resolve_execution_document

        receipt = self.store.preflight_receipt(row["preflight_receipt_id"])
        document = {} if receipt is None else json.loads(receipt["receipt_json"])
        profile = document.get("execution_profile")
        if profile is None:
            return (
                None,
                Path(self.layout.parallel_config_path),
                _sha256(self.layout.parallel_config_path),
                0,
            )
        installed = resolve_execution_document(
            Path(self.layout.parallel_config_path).parent, profile
        )
        if installed.profile is None or installed.profile.profile != profile:
            raise ServiceConflict(UNSUPPORTED_ON_MACOS)
        return (
            profile,
            installed.path,
            installed.config_sha256,
            installed.profile.worker_count,
        )
