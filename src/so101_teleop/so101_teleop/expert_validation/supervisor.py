"""Three-mode campaign lifecycle orchestration over one upstream owner path."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import inspect
import os
from pathlib import Path

from .adaptive import AdaptiveStartRequest
from .coordinator import CoordinatorStartRequest
from .models import (
    BatchBinding,
    CampaignBinding,
    CleanupReceipt,
    PreflightReceipt,
)
from .preflight import (
    CampaignPreflightReceipt,
    CampaignStartRequest,
    FixedExecutionConfig,
    PreflightEngine,
    canonical_start_request_sha256,
)


class ExpertValidationSupervisor:
    def __init__(self, *, store, process_owner, preflight_engine: PreflightEngine) -> None:
        self.store = store
        self.process_owner = process_owner
        self.preflight_engine = preflight_engine
        self._requests: dict[str, CampaignStartRequest] = {}

    async def preflight(self, request: CampaignStartRequest) -> CampaignPreflightReceipt:
        return self.preflight_engine.preflight(request)

    async def start_first_pass(self, request: CampaignStartRequest, *, receipt=None):
        receipt = receipt or self.preflight_engine.require_admitted(request)
        if (
            not receipt.admitted
            or receipt.canonical_start_request_sha256
            != canonical_start_request_sha256(request)
        ):
            raise RuntimeError("PREFLIGHT_REQUEST_MISMATCH")
        if self.store.manifest(
            request.manifest_id,
            current_source_config_sha256=request.parallel_config_sha256,
        ) is None:
            self.store.record_manifest(
                request.manifest_id,
                {
                    "catalog_sha256": request.selection.catalog_sha256,
                    "selection_sha256": request.selection.selection_sha256,
                    "point_ids": request.selection.point_ids,
                },
                source_config_sha256=request.parallel_config_sha256,
                created_at_ns=receipt.observed_at_ns,
            )
        self.store.record_preflight_receipt(
            PreflightReceipt(
                receipt_id=receipt.receipt_id,
                campaign_id=request.campaign_id,
                manifest_id=request.manifest_id,
                canonical_start_request_sha256=receipt.canonical_start_request_sha256,
                receipt=asdict(receipt),
                expires_at_monotonic_ns=receipt.expires_at_monotonic_ns,
            )
        )
        config = asdict(receipt.execution_config)
        campaign = CampaignBinding(
            campaign_id=request.campaign_id,
            manifest_id=request.manifest_id,
            executor_id="expert-validation-web",
            operation_id="first-pass",
            executor_config_sha256=hashlib.sha256(
                repr(sorted(config.items())).encode("utf-8")
            ).hexdigest(),
            execution_mode=request.execution_mode,
            execution_config=config,
            preflight_receipt_id=receipt.receipt_id,
        )
        batch_root = self._batch_root(request, request.batch_id)
        batch = BatchBinding(
            batch_id=request.batch_id,
            campaign_id=request.campaign_id,
            batch_kind="FIRST_PASS",
            point_id=None,
            journal_root=batch_root,
            coordinator_epoch=1 if request.execution_mode != "ADAPTIVE" else None,
            pool_generation=1 if request.execution_mode == "ADAPTIVE" else None,
        )
        self.store.consume_preflight_and_bind_campaign_batch(
            receipt.receipt_id,
            receipt.canonical_start_request_sha256,
            campaign,
            batch,
            now_monotonic_ns=receipt.observed_at_ns,
        )
        owner_request = self._owner_request(request, receipt, request.batch_id, batch_root)
        self._requests[request.campaign_id] = request
        result = await self._spawn(owner_request)
        if isinstance(result, dict) and result.get("cleanup_complete"):
            self.store.record_batch_cleanup(
                request.batch_id, result.get("receipt_sha256", "0" * 64)
            )
        return {"campaign_id": request.campaign_id, "batch_id": request.batch_id}

    async def _spawn(self, request):
        if hasattr(self.process_owner, "spawn_and_wait"):
            result = self.process_owner.spawn_and_wait(request)
            return await result if inspect.isawaitable(result) else result
        return self.process_owner.spawn(request)

    def _batch_root(self, request: CampaignStartRequest, batch_id: str) -> Path:
        return (
            request.evidence_root / "campaigns" / request.campaign_id / batch_id
        ).resolve()

    def _owner_request(self, request, receipt, batch_id, batch_root, point_ids=None):
        selected = tuple(point_ids or request.selection.point_ids)
        environment = dict(request.environment)
        if request.coordinator_executable_path is not None:
            inherited_path = environment.get("PATH", os.environ.get("PATH", ""))
            environment["PATH"] = os.pathsep.join(
                (str(request.coordinator_executable_path.parent), inherited_path)
            )
            environment.setdefault(
                "SO101_PARALLEL_IPC_BASE", f"/run/user/{os.getuid()}"
            )
        if isinstance(receipt.execution_config, FixedExecutionConfig):
            config = receipt.execution_config
            argv = [
                "/usr/bin/python3"
                if request.coordinator_executable_path is not None
                else "ros2",
            ]
            if request.coordinator_executable_path is not None:
                argv.append(str(request.coordinator_executable_path))
            if request.coordinator_executable_path is None:
                argv.extend(("run", "so101_demo_py", "so101_parallel_batch"))
            argv.extend([
                "--points", str(request.points_path),
                "--config", str(request.parallel_config_path),
                "--batch-id", batch_id,
                "--worker-count", str(config.worker_count),
                "--max-points-per-worker", str(config.max_points_per_worker),
                "--evidence-root", str(batch_root),
                "--broker-image", request.broker_image_id,
                "--yolo-weights", str(request.yolo_weights_path),
                "--yolo-weights-sha256", request.yolo_weights_sha256,
                "--grounded-root", str(request.grounded_root),
                "--grounded-manifest-sha256", request.grounded_sam_manifest_sha256,
                "--run-mode", "execute",
            ])
            for point_id in selected:
                argv.extend(("--point-id", point_id))
            if request.provenance_binding_path is not None:
                argv.extend(("--provenance-binding", str(request.provenance_binding_path)))
            token_sha = hashlib.sha256(
                f"{request.campaign_id}:{batch_id}".encode("utf-8")
            ).hexdigest()
            return CoordinatorStartRequest(
                campaign_id=request.campaign_id,
                batch_id=batch_id,
                execution_mode=config.execution_mode,
                worker_count=config.worker_count,
                max_points_per_worker=config.max_points_per_worker,
                argv=tuple(argv),
                environment=environment,
                batch_root=batch_root,
                control_socket=batch_root / "control.sock",
                control_token_sha256=token_sha,
                coordinator_epoch=1,
                selected_point_ids=selected,
            )
        config = receipt.execution_config
        wrapper = request.adaptive_wrapper_path or (
            Path(__file__).resolve().parents[4] / "scripts/run_so101_adaptive_batch.zsh"
        )
        argv = [
            "/usr/bin/zsh", str(wrapper), "--adaptive-workers",
            "--points", str(request.points_path),
            "--config", str(request.parallel_config_path),
            "--adaptive-config", str(request.adaptive_config_path),
            "--batch-id", batch_id,
            "--worker-count", str(config.preferred_worker_count),
            "--fallback-worker-counts", ",".join(map(str, config.fallback_worker_counts)),
            "--initial-points-per-worker", str(config.initial_points_per_worker),
            "--worker-start-timeout-s", str(config.worker_start_timeout_s),
            "--max-infra-attempts-per-point", str(config.max_infra_attempts_per_point),
            "--yolo-executor-count", str(config.yolo_executor_count),
            "--evidence-root", str(batch_root),
            "--broker-image", request.broker_image_id,
            "--yolo-weights", str(request.yolo_weights_path),
            "--yolo-weights-sha256", request.yolo_weights_sha256,
            "--grounded-root", str(request.grounded_root),
            "--grounded-manifest-sha256", request.grounded_sam_manifest_sha256,
            "--run-mode", "execute",
        ]
        for point_id in selected:
            argv.extend(("--point-id", point_id))
        if request.provenance_binding_path is not None:
            argv.extend(("--provenance-binding", str(request.provenance_binding_path)))
        return AdaptiveStartRequest(
            campaign_id=request.campaign_id,
            batch_id=batch_id,
            preferred_worker_count=config.preferred_worker_count,
            fallback_worker_counts=config.fallback_worker_counts,
            initial_points_per_worker=config.initial_points_per_worker,
            worker_start_timeout_s=config.worker_start_timeout_s,
            max_infra_attempts_per_point=config.max_infra_attempts_per_point,
            yolo_executor_count=config.yolo_executor_count,
            argv=tuple(argv),
            environment=environment,
            evidence_root=batch_root,
            adaptive_config_sha256=config.adaptive_config_sha256,
            catalog_sha256=request.selection.catalog_sha256,
            yolo_weights_sha256=request.yolo_weights_sha256,
            grounded_sam_manifest_sha256=request.grounded_sam_manifest_sha256,
            broker_image_id=request.broker_image_id,
            selected_point_ids=selected,
        )

    async def start_retries(self, campaign_id: str, point_ids: tuple[str, ...]):
        if not point_ids:
            return {"status": "LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED"}
        original = self._requests[campaign_id]
        self.store.enqueue_retries(campaign_id, point_ids)
        for index, point_id in enumerate(point_ids, start=1):
            batch_id = f"retry-{index:03d}"
            batch_root = self._batch_root(original, batch_id)
            batch = BatchBinding(
                batch_id=batch_id,
                campaign_id=campaign_id,
                batch_kind="FULL_RESTART_RETRY",
                point_id=point_id,
                journal_root=batch_root,
                coordinator_epoch=1,
            )
            self.store.bind_retry_batch(batch)
            config = FixedExecutionConfig("SEQUENTIAL", 1, 1)
            receipt = type("RetryReceipt", (), {"execution_config": config})()
            owner_request = self._owner_request(
                original, receipt, batch_id, batch_root, point_ids=(point_id,)
            )
            result = await self._spawn(owner_request)
            if not isinstance(result, dict) or not result.get("cleanup_complete"):
                raise RuntimeError("RETRY_CLEANUP_INCOMPLETE")
            self.store.record_cleanup_and_advance_retry(
                CleanupReceipt(
                    campaign_id,
                    batch_id,
                    point_id,
                    result.get("receipt_sha256", "0" * 64),
                )
            )
        return {"status": "RETRIES_COMPLETE"}

    def cancel(self, owned):
        return self.process_owner.request_cancel(owned)

    def status(self, batch_id: str):
        return self.store.batch(batch_id)

    def list_campaigns(self):
        return self.store.list_campaigns()

    def reconcile_startup(self):
        return self.store.reconcile()

    def has_unresolved_campaign(self):
        active = getattr(self.process_owner, "active_execution", None)
        if active is None:
            return False
        status = self.process_owner.poll(active)
        return status.running or status.descendants_alive

    def cancel_for_reason(self, _reason):
        active = getattr(self.process_owner, "active_execution", None)
        if active is None:
            return None
        status = self.process_owner.poll(active)
        if not status.running and not status.descendants_alive:
            return None
        return self.process_owner.request_cancel(active)
