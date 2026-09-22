"""Three-mode campaign lifecycle orchestration over one upstream owner path."""

from __future__ import annotations

from dataclasses import asdict
import asyncio
import hashlib
import inspect
import json
import os
from pathlib import Path
import secrets
import sys
import time

from .adaptive import AdaptiveStartRequest
from .coordinator import CONTROL_SOCKET_ROOT, CoordinatorStartRequest
from .control import ControlProtocolError, CoordinatorControlClient
from .coordinator_events import (
    AcceptedCoordinatorCursor,
    CampaignUpstreamBinding,
    CoordinatorEventReader,
    ReadOnlyCoordinatorJournal,
)
from .execution_context import (
    CandidateExecutionContext,
    ProductionExecutionContext,
    retry_batch_root,
)
from .owner_tree import OwnerIntent
from .process_owner import CoordinatorOwnershipError, ExecutionProcessOwner, OwnedCoordinator
from .store import StoreConflict
from .models import (
    BatchBinding,
    CampaignBinding,
    CleanupReceipt,
    PreflightReceipt,
    RetryStartRequest,
)
from .preflight import (
    CampaignPreflightReceipt,
    CampaignStartRequest,
    FixedExecutionConfig,
    PreflightEngine,
    canonical_start_request_sha256,
)


#: Every flag the service hands a fixed coordinator, in the order it hands them over. A coordinator
#: entry point that cannot accept exactly these cannot be launched by this service, so the list is a
#: constant rather than an inline literal: the macOS entry point's parser and this tuple are pinned to
#: each other by a test, and a flag added here without being accepted there fails that test instead of
#: failing a live run.
FIXED_COORDINATOR_FLAGS = (
    "--points",
    "--config",
    "--batch-id",
    "--worker-count",
    "--evidence-root",
    "--broker-image",
    "--yolo-weights",
    "--yolo-weights-sha256",
    "--grounded-root",
    "--grounded-manifest-sha256",
    "--run-mode",
    "--point-id",
    "--provenance-binding",
)


#: Darwin's ``sun_path`` is 104 bytes including the terminating NUL, and it has no ``bindat``/``connectat``
#: indirection to reach a longer path. A batch root under a validation evidence root is far longer than
#: that, so the endpoint cannot live inside it there. The canonical root itself lives in the contract
#: module, so the composer and the validator cannot disagree about where an endpoint may be.
_DARWIN_SUN_PATH_BYTES = 104


def control_socket_path(batch_root: Path, campaign_id: str) -> Path:
    """Where the launched coordinator's control endpoint lives on this platform.

    Linux keeps it inside the batch root: the client pins the parent directory through
    ``/proc/self/fd``, so the path may exceed ``sun_path``. Darwin cannot address such a path at all -
    the first live macOS launch of a service-driven campaign died binding
    ``<evidence>/campaigns/<campaign>/<batch>/control/control.sock``, which is 200 bytes - so the
    endpoint lives in a short canonical private directory instead. The directory is created privately
    by the endpoint, which verifies ownership and mode before it binds.
    """
    if sys.platform == "darwin":
        candidate = CONTROL_SOCKET_ROOT / f"{campaign_id}-{Path(batch_root).name}.sock"
        if len(os.fsencode(candidate)) >= _DARWIN_SUN_PATH_BYTES:  # pragma: no cover - defensive
            raise ValueError("CONTROL_SOCKET_PATH_TOO_LONG")
        return candidate
    return Path(batch_root) / "control" / "control.sock"


def fixed_coordinator_argv(
    *,
    executable_path,
    points_path,
    config_path,
    batch_id: str,
    worker_count: int,
    evidence_root,
    broker_image_id: str,
    yolo_weights_path,
    yolo_weights_sha256: str,
    grounded_root,
    grounded_manifest_sha256: str,
    selected_point_ids,
    provenance_binding_path=None,
) -> list[str]:
    """The one argv this service launches a fixed coordinator with.

    The runner must be executed by the interpreter this service runs under: naming
    ``/usr/bin/python3`` literally pointed at Apple's Python 3.9 on macOS, where the runner died on
    ``import yaml`` and the execution barrier refused the start after its ten-second wait.
    """
    if executable_path is not None:
        argv = [sys.executable, str(executable_path)]
    else:
        argv = ["ros2", "run", "so101_demo_py", "so101_parallel_batch"]
    argv.extend(
        [
            "--points", str(points_path),
            "--config", str(config_path),
            "--batch-id", batch_id,
            "--worker-count", str(worker_count),
            "--evidence-root", str(evidence_root),
            "--broker-image", broker_image_id,
            "--yolo-weights", str(yolo_weights_path),
            "--yolo-weights-sha256", yolo_weights_sha256,
            "--grounded-root", str(grounded_root),
            "--grounded-manifest-sha256", grounded_manifest_sha256,
            "--run-mode", "execute",
        ]
    )
    for point_id in selected_point_ids:
        argv.extend(("--point-id", point_id))
    if provenance_binding_path is not None:
        argv.extend(("--provenance-binding", str(provenance_binding_path)))
    return argv


class ExpertValidationSupervisor:
    def __init__(
        self, *, store, process_owner, preflight_engine: PreflightEngine, execution_port=None
    ) -> None:
        self.store = store
        self.process_owner = process_owner
        self.preflight_engine = preflight_engine
        self._execution_port = execution_port
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

    async def _spawn(self, request, *, owner_intent=None):
        """Spawn through the process owner, reusing the intent the admission transaction wrote.

        A spawn boundary that cannot adopt that intent (the typed test launcher) is still used, but
        then the admitted intent simply stays unconfirmed - never a second intent for one spawn.
        """

        if hasattr(self.process_owner, "spawn_and_wait"):
            result = self.process_owner.spawn_and_wait(request)
            return await result if inspect.isawaitable(result) else result
        if owner_intent is not None and "owner_intent" in inspect.signature(
            self.process_owner.spawn
        ).parameters:
            return self.process_owner.spawn(request, owner_intent=owner_intent)
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
            argv = fixed_coordinator_argv(
                executable_path=request.coordinator_executable_path,
                points_path=request.points_path,
                config_path=request.parallel_config_path,
                batch_id=batch_id,
                worker_count=config.worker_count,
                evidence_root=batch_root,
                broker_image_id=request.broker_image_id,
                yolo_weights_path=request.yolo_weights_path,
                yolo_weights_sha256=request.yolo_weights_sha256,
                grounded_root=request.grounded_root,
                grounded_manifest_sha256=request.grounded_sam_manifest_sha256,
                selected_point_ids=selected,
                provenance_binding_path=request.provenance_binding_path,
            )
            token = secrets.token_hex(32)
            token_sha = hashlib.sha256(token.encode("utf-8")).hexdigest()
            control_socket = control_socket_path(batch_root, request.campaign_id)
            environment.update({
                "SO101_FIXED_CONTROL_TOKEN": token,
                "SO101_FIXED_CONTROL_CAMPAIGN_ID": request.campaign_id,
                "SO101_FIXED_CONTROL_EPOCH": "1",
                "SO101_FIXED_CONTROL_SOCKET": str(control_socket),
            })
            return self._apply_execution_port(CoordinatorStartRequest(
                campaign_id=request.campaign_id,
                batch_id=batch_id,
                execution_mode=config.execution_mode,
                worker_count=config.worker_count,
                argv=tuple(argv),
                environment=environment,
                batch_root=batch_root,
                control_socket=control_socket,
                control_token_sha256=token_sha,
                coordinator_epoch=1,
                selected_point_ids=selected,
            ))
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
        return self._apply_execution_port(AdaptiveStartRequest(
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
        ))

    def _apply_execution_port(self, owner_request):
        """Only a dedicated test launcher injects this typed port; the
        production entry point always uses the installed executables."""
        port = self._execution_port
        if port is None:
            return owner_request
        from dataclasses import replace

        if isinstance(owner_request, CoordinatorStartRequest):
            return replace(owner_request, argv=tuple(port.fixed_argv(owner_request)))
        return replace(owner_request, argv=tuple(port.adaptive_argv(owner_request)))

    async def start_candidate_retry(self, *, request, context):
        """The candidate endpoint: only a candidate context may authorize this spawn."""

        if not isinstance(context, CandidateExecutionContext):
            raise RuntimeError("RETRY_CANDIDATE_CONTEXT_REQUIRED")
        return await self._start_admitted_retry(request, context)

    async def start_candidate_first_pass(self, *, request, context, receipt=None):
        """The candidate first-pass endpoint: one issued context, one run, one command.

        The admission transaction runs before any process exists: it consumes the context's
        one-time command, checks every coordinate the context binds, consumes the preflight receipt
        and writes the campaign, the batch and the owner spawn intent. The spawn then reuses that
        exact intent, so a spawn that fails leaves an unconfirmed intent, a standing fence and an
        ``IN_PROGRESS`` command that can never be replayed.
        """

        if not isinstance(context, CandidateExecutionContext):
            raise RuntimeError("FIRST_PASS_CANDIDATE_CONTEXT_REQUIRED")
        receipt = receipt or self.preflight_engine.require_admitted(request)
        if (
            not receipt.admitted
            or receipt.canonical_start_request_sha256
            != canonical_start_request_sha256(request)
        ):
            raise RuntimeError("PREFLIGHT_REQUEST_MISMATCH")
        batch_root = self._batch_root(request, request.batch_id)
        owner_request = self._owner_request(request, receipt, request.batch_id, batch_root)
        campaign = CampaignBinding(
            campaign_id=request.campaign_id,
            manifest_id=request.manifest_id,
            executor_id="expert-validation-web",
            operation_id="first-pass",
            executor_config_sha256=hashlib.sha256(
                repr(sorted(asdict(receipt.execution_config).items())).encode("utf-8")
            ).hexdigest(),
            execution_mode=request.execution_mode,
            execution_config=asdict(receipt.execution_config),
            preflight_receipt_id=receipt.receipt_id,
        )
        batch = BatchBinding(
            batch_id=request.batch_id,
            campaign_id=request.campaign_id,
            batch_kind="FIRST_PASS",
            point_id=None,
            journal_root=batch_root,
            coordinator_epoch=1,
        )
        durable_receipt = PreflightReceipt(
            receipt_id=receipt.receipt_id,
            campaign_id=request.campaign_id,
            manifest_id=request.manifest_id,
            canonical_start_request_sha256=receipt.canonical_start_request_sha256,
            receipt=asdict(receipt),
            expires_at_monotonic_ns=receipt.expires_at_monotonic_ns,
        )
        intent = OwnerIntent.for_argv(
            campaign_id=request.campaign_id,
            batch_id=request.batch_id,
            role="ADAPTER",
            generation=context.owner_generation,
            spawn_token="spawn-" + secrets.token_hex(16),
            argv=owner_request.argv,
            parent_spawn_token=None,
            own_session=True,
        )
        binding = self.store.admit_first_pass(
            request=request,
            context=context,
            receipt=durable_receipt,
            campaign=campaign,
            batch=batch,
            spawn_intent=intent,
        )
        self._requests[request.campaign_id] = request
        try:
            result = await self._spawn(owner_request, owner_intent=intent)
        except BaseException as error:
            # The intent and the fence stay: nothing may guess whether a process exists.
            self.store.record_recovery_fence(
                request.campaign_id,
                request.batch_id,
                reason=f"FIRST_PASS_SPAWN_FAILED: {error}",
                command_id=context.command_id,
            )
            raise
        if isinstance(result, dict) and result.get("cleanup_complete"):
            self.store.record_batch_cleanup(
                request.batch_id, result.get("receipt_sha256", "0" * 64)
            )
        self.store.finish_command(context.command_id, binding.as_document())
        return {
            "status": "STARTED",
            "campaign_id": request.campaign_id,
            "batch_id": request.batch_id,
            "manifest_id": request.manifest_id,
            "execution_profile": context.execution_profile,
            "schema_version": context.schema_version,
            "worker_count": context.worker_count,
            "context_id": context.context_id,
            "context_kind": context.kind,
            "command_id": context.command_id,
            "binding_sha256": binding.binding_sha256,
        }

    async def start_production_retry(self, *, request, context):
        """The production endpoint: only an installed context may authorize this spawn."""

        if not isinstance(context, ProductionExecutionContext):
            raise RuntimeError("RETRY_PRODUCTION_CONTEXT_REQUIRED")
        return await self._start_admitted_retry(request, context)

    async def _start_admitted_retry(self, request, context):
        """Admit one retry (one transaction), then spawn exactly that admitted owner once.

        The owner intent is written by that transaction, before any process exists, and the spawn
        boundary reuses it: the intent the tree can later confirm is the one the command was
        consumed with. A spawn that fails therefore leaves the intent in place, unconfirmed, and the
        command row stays IN_PROGRESS, so the retry can never be replayed.
        """

        if not isinstance(request, RetryStartRequest):
            raise RuntimeError("RETRY_REQUEST_INVALID")
        original = self._requests.get(request.campaign_id)
        if original is None:
            raise RuntimeError("RETRY_ORIGINAL_REQUEST_UNKNOWN")
        batch_root = self._batch_root(original, request.batch_id)
        if batch_root != retry_batch_root(
            request.evidence_root, request.campaign_id, request.batch_id
        ):
            raise RuntimeError("RETRY_BATCH_ROOT_MISMATCH")
        receipt = type("RetryReceipt", (), {
            "execution_config": FixedExecutionConfig("SEQUENTIAL", 1)})()
        owner_request = self._owner_request(
            original, receipt, request.batch_id, batch_root, point_ids=(request.point_id,)
        )
        intent = OwnerIntent.for_argv(
            campaign_id=request.campaign_id,
            batch_id=request.batch_id,
            role="ADAPTER",
            generation=request.owner_generation,
            spawn_token="spawn-" + secrets.token_hex(16),
            argv=owner_request.argv,
            parent_spawn_token=None,
            own_session=True,
        )
        binding = self.store.admit_retry(
            request=request, context=context, spawn_intent=intent
        )
        try:
            result = await self._spawn(owner_request, owner_intent=intent)
        except BaseException as error:
            # The intent and the fence stay: nothing may guess whether a process exists.
            self.store.record_recovery_fence(
                request.campaign_id,
                request.batch_id,
                reason=f"RETRY_SPAWN_FAILED: {error}",
                command_id=request.command_id,
            )
            raise
        if isinstance(result, dict):
            if not result.get("cleanup_complete"):
                raise RuntimeError("RETRY_CLEANUP_INCOMPLETE")
            receipt_sha256 = result.get("receipt_sha256", "0" * 64)
        else:
            receipt_sha256 = await self._await_fixed_retry_cleanup(
                result, original, request.batch_id, batch_root
            )
        self.store.record_cleanup_and_advance_retry(
            CleanupReceipt(request.campaign_id, request.batch_id, request.point_id, receipt_sha256)
        )
        self.store.finish_command(request.command_id, binding.as_document())
        return {
            "status": "RETRIES_COMPLETE",
            "campaign_id": request.campaign_id,
            "batch_id": request.batch_id,
            "point_id": request.point_id,
            "binding_sha256": binding.binding_sha256,
        }

    def reconcile_retry(self, campaign_id: str):
        """Close out a retry that already reached spawn; never re-execute and never skip ahead."""

        original = self._requests.get(campaign_id)
        if original is None:
            raise RuntimeError("RETRY_ORIGINAL_REQUEST_UNKNOWN")
        item = self.store.next_retry(campaign_id)
        if item is None or item.state != "RUNNING":
            return None
        batch_root = self._batch_root(original, item.batch_id)
        receipt_sha256 = self._reconcile_retry_batch(original, item.batch_id, batch_root)
        self.store.record_cleanup_and_advance_retry(
            CleanupReceipt(campaign_id, item.batch_id, item.point_id, receipt_sha256)
        )
        return receipt_sha256

    def _reconcile_retry_batch(
        self, request: CampaignStartRequest, batch_id: str, batch_root: Path
    ) -> str:
        record = self.store.owned_execution(batch_id)
        if record is None or record.state == "INTENT":
            # The spawn outcome is unknowable; never replay or skip this entry.
            raise RuntimeError("COMMAND_OUTCOME_UNKNOWN")
        if ExecutionProcessOwner.identity_alive(
            record.pid, record.started_ticks, record.argv_sha256
        ):
            # The previous owner is still provably live; never overlap it.
            raise RuntimeError("RETRY_EXECUTION_STILL_RUNNING")
        return self._verify_retry_journal(request, batch_id, batch_root)

    async def _await_fixed_retry_cleanup(
        self, owned, request: CampaignStartRequest, batch_id: str, batch_root: Path
    ) -> str:
        """Wait out one real retry coordinator and verify its journal cleanup."""

        deadline = time.monotonic() + 120.0
        while True:
            status = self.process_owner.poll(owned)
            if not status.running and not status.descendants_alive:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("RETRY_EXECUTION_TIMEOUT")
            await asyncio.sleep(0.1)
        if status.exit_code not in (0, None):
            raise RuntimeError("RETRY_EXECUTION_FAILED")
        return self._verify_retry_journal(request, batch_id, batch_root)

    def _verify_retry_journal(
        self, request: CampaignStartRequest, batch_id: str, batch_root: Path
    ) -> str:
        journal_root = batch_root / "coordinator"
        epoch_path = journal_root / "coordinator_epoch.json"
        if epoch_path.is_symlink() or not epoch_path.is_file():
            raise RuntimeError("RETRY_OWNER_EPOCH_INVALID")
        try:
            epoch_document = json.loads(epoch_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError("RETRY_OWNER_EPOCH_INVALID") from error
        if (
            epoch_document.get("batch_id") != batch_id
            or epoch_document.get("coordinator_epoch") != 1
        ):
            raise RuntimeError("RETRY_OWNER_EPOCH_INVALID")
        binding = CampaignUpstreamBinding(
            campaign_id=request.campaign_id,
            batch_id=batch_id,
            owner_kind="COORDINATOR",
            owner_epoch_or_generation=1,
            journal_root=journal_root,
            batch_root=batch_root,
        )
        reader = CoordinatorEventReader(
            ReadOnlyCoordinatorJournal(journal_root, batch_id), binding
        )
        batch = reader.read_after(AcceptedCoordinatorCursor.initial(binding))
        state = batch.projected_state
        if state.get("terminal_reason") is None or state.get("batch_cleanup_complete") is not True:
            raise RuntimeError("RETRY_CLEANUP_INCOMPLETE")
        return batch.events[-1].frame_sha256 if batch.events else "0" * 64

    def cancel(self, owned):
        return self.process_owner.request_cancel(owned)

    def status(self, batch_id: str):
        return self.store.batch(batch_id)

    def list_campaigns(self):
        return self.store.list_campaigns()

    def reconcile_startup(self):
        return self.store.reconcile()

    def has_unresolved_campaign(self):
        if self.store.has_recovery_fence():
            return True
        active = getattr(self.process_owner, "active_execution", None)
        if active is not None:
            status = self.process_owner.poll(active)
            if status.running or status.descendants_alive:
                return True
        for record in self.store.owned_executions(("INTENT", "RUNNING")):
            if record.state == "INTENT":
                # Spawn intent without ACK: the outcome is unknowable.
                return True
            if ExecutionProcessOwner.identity_alive(
                record.pid, record.started_ticks, record.argv_sha256
            ):
                return True
        return False

    def cancel_for_reason(self, reason, *, campaign_id=None, batch_id=None, command_id=None):
        active = getattr(self.process_owner, "active_execution", None)
        if active is None:
            return None
        if (
            campaign_id is not None and active.campaign_id != campaign_id
            or batch_id is not None and active.batch_id != batch_id
        ):
            raise CoordinatorOwnershipError("VALIDATION_CAMPAIGN_OWNER_MISMATCH")
        status = self.process_owner.poll(active)
        if not status.running and not status.descendants_alive:
            return None
        if isinstance(active, OwnedCoordinator):
            command_id = "cancel-" + hashlib.sha256(
                f"{active.campaign_id}:{active.batch_id}:{active.coordinator_epoch}:{reason}:{command_id or ''}".encode()
            ).hexdigest()
            try:
                self.process_owner.verify_execution_identity(active)
                binding = self.store.fixed_control_binding(active.batch_id)
                record = self.store.owned_execution(active.batch_id)
                if (
                    binding is None or record is None or record.state != "RUNNING"
                    or binding.campaign_id != active.campaign_id
                    or binding.coordinator_epoch != active.coordinator_epoch
                    or binding.control_socket != active.control_socket
                    or any(getattr(record, name) != getattr(active, name) for name in (
                        "pid", "pgid", "started_ticks", "argv_sha256", "environment_sha256",
                        "control_socket", "coordinator_epoch",
                    ))
                ):
                    raise ControlProtocolError("FIXED_CONTROL_BINDING_MISMATCH")
                return CoordinatorControlClient().cancel(command_id=command_id, binding=binding)
            except (ControlProtocolError, CoordinatorOwnershipError, StoreConflict, ValueError) as error:
                self.store.record_recovery_fence(
                    active.campaign_id, active.batch_id, reason=str(error), command_id=command_id
                )
                raise
        return self.process_owner.request_cancel(active)
