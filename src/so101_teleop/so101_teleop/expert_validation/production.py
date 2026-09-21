"""Production composition root for the dedicated expert-validation service."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import time
import uuid
from typing import Mapping

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from so101_demo.parallel_batch.contracts import BatchSummary, ContractError, PointStatus, RunMode

from .adaptive_events import AdaptiveEventReader
from .artifacts import ValidationArtifactRegistry
from .catalog import CatalogPoint, PointSelection, select_catalog_points
from .committed_artifacts import register_committed_attempt
from .control import ControlProtocolError
from .coordinator_events import (
    AcceptedCoordinatorCursor,
    CampaignUpstreamBinding,
    CoordinatorEventReader,
    CoordinatorProjectionError,
    ReadOnlyCoordinatorJournal,
)
from .execution_context import (
    CandidateExecutionContext,
    ProductionExecutionContext,
    RETRY_BATCH_KIND,
    RETRY_PROFILE,
    RETRY_SCHEMA_VERSION,
    RETRY_WORKER_COUNT,
    install_binding_sha256,
    retry_admission_command_id,
    runtime_closure_sha256,
)
from .executor_registry import ExecutorRegistry, QualificationProbes
from .lease import ValidationLeaseService
from .manifest_geometry import current_manifest_source_hash, freeze_manifest_context
from .models import RetryStartRequest, UpstreamCursor
from .preflight import (
    CampaignStartRequest,
    FIXED_WORKER_COUNTS,
    FixedExecutionConfig,
    MACOS_EXECUTION_PROFILES,
    MACOS_WORKER_COUNTS,
    PreflightRejected,
    UNSUPPORTED_ON_MACOS,
)
from .process_owner import CoordinatorOwnershipError, ExecutionProcessOwner, OwnedCoordinator
from .service import ExpertValidationService, ServiceConflict
from .store import StoreConflict, SupervisorStore
from .statistics import (
    BrokerProjection,
    PointProjection,
    StatisticsProjectionError,
    WorkerProjection,
    retry_history_document,
    retry_history_entry,
    summarize_first_pass,
)
from .supervisor import ExpertValidationSupervisor
from .preflight import PreflightEngine


_BROKER_IMAGE = "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1"

#: The installed matrix by routing key, so a restored row is resolved by name and never inferred.
PROFILES_BY_NAME = {row.profile: row for row in MACOS_EXECUTION_PROFILES}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_file(environment: Mapping[str, str], name: str, default: Path | None = None) -> Path:
    value = environment.get(name)
    path = Path(value) if value else default
    if path is None or not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{name}_INVALID")
    return path.resolve()


def _optional_file(environment: Mapping[str, str], name: str) -> Path | None:
    value = environment.get(name)
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{name}_INVALID")
    return path.resolve()


def _source_identity(
    *, module_path: Path, provenance_binding: Path | None = None,
    subprocess_runner=subprocess.run,
) -> tuple[Path, str | None]:
    """Resolve the installed source root; the commit is an optional DEBUG observation.

    A deployment may be a pure copied install with no Git checkout, so this function
    runs no Git command, requires no commit and never refuses on commit content.
    """

    del subprocess_runner
    if provenance_binding is not None:
        binding_path = Path(provenance_binding)
        if (
            not binding_path.is_absolute()
            or binding_path.is_symlink()
            or not binding_path.is_file()
        ):
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID")
        try:
            document = json.loads(binding_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID") from error
        source_root = document.get("source_root")
        if (
            not isinstance(source_root, str)
            or not Path(source_root).is_absolute()
            or Path(source_root).is_symlink()
            or not Path(source_root).is_dir()
        ):
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID")
        source_root = Path(source_root).resolve()
        declared_commit = document.get("source_commit")
        if declared_commit is not None and not isinstance(declared_commit, str):
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID")
        observed = declared_commit.strip() or None if declared_commit else None
        return source_root, observed
    candidate = Path(module_path).resolve().parent
    for parent in (candidate, *candidate.parents):
        if (parent / "src/so101_demo_py").is_dir():
            return parent, None
    return candidate, None


@dataclass(frozen=True, slots=True)
class ProductionRuntimeLayout:
    source_root: Path
    source_commit: str | None
    demo_prefix: Path
    points_path: Path
    parallel_config_path: Path
    adaptive_config_path: Path
    coordinator_executable: Path
    cleanup_executable: Path
    adaptive_wrapper: Path
    provenance_binding: Path | None
    yolo_weights_path: Path | None
    grounded_root: Path | None
    yolo_weights_sha256: str
    grounded_manifest_sha256: str
    broker_image_id: str
    parallel_acceptance: Path | None
    adaptive_acceptance: Path | None
    adaptive_fault_injection: Path | None
    adaptive_performance_tiers: tuple[int, ...]

    @classmethod
    def discover(cls, environment: Mapping[str, str]) -> "ProductionRuntimeLayout":
        demo_prefix = Path(get_package_prefix("so101_demo_py")).resolve()
        demo_share = Path(get_package_share_directory("so101_demo_py")).resolve()
        points = _required_file(
            environment,
            "SO101_VALIDATION_POINTS",
            demo_share / "config/mujoco/moveit_expert_validation_points_v1.yaml",
        )
        parallel = _required_file(
            environment,
            "SO101_VALIDATION_PARALLEL_CONFIG",
            demo_share / "config/mujoco/parallel_batch_v1.yaml",
        )
        adaptive = _required_file(
            environment,
            "SO101_VALIDATION_ADAPTIVE_CONFIG",
            demo_share / "config/mujoco/parallel_adaptive_workers_v1.yaml",
        )
        coordinator = _required_file(
            environment,
            "SO101_VALIDATION_COORDINATOR",
            demo_prefix / "lib/so101_demo_py/so101_parallel_batch",
        )
        cleanup = _required_file(
            environment,
            "SO101_VALIDATION_ADAPTIVE_CLEANUP",
            demo_prefix / "lib/so101_demo_py/so101_parallel_batch_cleanup",
        )
        wrapper = _required_file(
            environment,
            "SO101_VALIDATION_ADAPTIVE_WRAPPER",
            demo_prefix / "lib/so101_demo_py/run_so101_adaptive_batch.zsh",
        )
        provenance_binding = _optional_file(
            environment, "SO101_VALIDATION_PROVENANCE_BINDING"
        )
        import so101_demo

        module = Path(so101_demo.__file__).absolute()
        if provenance_binding is not None and (
            module.is_symlink()
            or not module.is_file()
            or not module.is_relative_to(demo_prefix)
        ):
            raise RuntimeError("SO101_VALIDATION_INSTALLED_MODULE_INVALID")
        source_root, source_commit = _source_identity(
            module_path=module,
            provenance_binding=provenance_binding,
        )
        configured_source = environment.get("SO101_VALIDATION_SOURCE_ROOT")
        if configured_source and Path(configured_source).resolve() != source_root:
            raise RuntimeError("SO101_VALIDATION_SOURCE_ROOT_MISMATCH")
        # A configured commit is DEBUG metadata only: it can never refuse a layout.
        configured_commit = environment.get("SO101_VALIDATION_SOURCE_COMMIT")
        if configured_commit and source_commit is None:
            source_commit = str(configured_commit).strip() or None
        yolo = environment.get("SO101_VALIDATION_YOLO_WEIGHTS")
        yolo_path = Path(yolo).resolve() if yolo else None
        if yolo_path is not None and (not yolo_path.is_file() or yolo_path.is_symlink()):
            raise RuntimeError("SO101_VALIDATION_YOLO_WEIGHTS_INVALID")
        grounded = environment.get("SO101_VALIDATION_GROUNDED_ROOT")
        grounded_root = Path(grounded).resolve() if grounded else None
        if grounded_root is not None and (
            not grounded_root.is_dir()
            or grounded_root.is_symlink()
            or not (grounded_root / "manifest.json").is_file()
        ):
            raise RuntimeError("SO101_VALIDATION_GROUNDED_ROOT_INVALID")
        tiers = tuple(
            int(value)
            for value in environment.get("SO101_VALIDATION_ADAPTIVE_PERFORMANCE_TIERS", "").split(",")
            if value
        )
        return cls(
            source_root=source_root,
            source_commit=source_commit,
            demo_prefix=demo_prefix,
            points_path=points,
            parallel_config_path=parallel,
            adaptive_config_path=adaptive,
            coordinator_executable=coordinator,
            cleanup_executable=cleanup,
            adaptive_wrapper=wrapper,
            provenance_binding=provenance_binding,
            yolo_weights_path=yolo_path,
            grounded_root=grounded_root,
            yolo_weights_sha256=(
                _sha256(yolo_path)
                if yolo_path is not None
                else environment.get("SO101_VALIDATION_YOLO_SHA256", "0" * 64)
            ),
            grounded_manifest_sha256=(
                _sha256(grounded_root / "manifest.json")
                if grounded_root is not None
                else environment.get("SO101_VALIDATION_GROUNDED_SHA256", "0" * 64)
            ),
            broker_image_id=environment.get("SO101_VALIDATION_BROKER_IMAGE", _BROKER_IMAGE),
            parallel_acceptance=_optional_file(environment, "SO101_VALIDATION_PARALLEL_ACCEPTANCE"),
            adaptive_acceptance=_optional_file(environment, "SO101_VALIDATION_ADAPTIVE_ACCEPTANCE"),
            adaptive_fault_injection=_optional_file(
                environment, "SO101_VALIDATION_ADAPTIVE_FAULT_INJECTION"
            ),
            adaptive_performance_tiers=tiers,
        )


class _GuardAdmission:
    """The guard wiring one execution document needs. Cacheable; it holds no verdict.

    ``(profile, config_sha256, accelerator, selector)`` is the composition key. The
    ``EpochStartGuard`` itself is built on first use, so reading the policy or the selector of a
    document performs no I/O beyond loading that document and starts no probe process.
    """

    def __init__(self, *, document, accelerator) -> None:
        self.document = document
        self.profile = None if document.profile is None else document.profile.profile
        self.config_sha256 = document.config_sha256
        self.accelerator_kind = document.accelerator
        self.selector = document.selector
        self.policy = document.config.start_guard
        self.accelerator = accelerator
        self._guard = None

    @property
    def composition_key(self) -> tuple:
        return (self.profile, self.config_sha256, self.accelerator_kind, self.selector)

    @property
    def guard(self):
        if self._guard is None:
            from so101_demo.parallel_batch.start_guard_probe import (
                compose_default_start_guard)

            self._guard = compose_default_start_guard(
                self.policy, accelerator=self.accelerator)
        return self._guard

    def begin_epoch(self, scope):
        """One fresh observation for this request/spawn epoch; never a stored verdict."""

        return self.guard.begin_epoch(scope)

    def require_before_spawn(self, scope):
        return self.guard.require_before_spawn(scope)


class _LazyStartGuard:
    """Compose the shared guard per execution document; the composition is cached, verdicts are not."""

    def __init__(self, environment: Mapping[str, str], config_path=None) -> None:
        self._environment = dict(environment)
        self._config_path = config_path
        self._admissions: dict[tuple, _GuardAdmission] = {}

    def admission(self, config_path=None) -> _GuardAdmission:
        """The cached composition for one document, keyed by its profile and real bytes."""

        from .preflight import describe_execution_document

        discovered = (config_path or self._config_path
                      or self._environment.get("SO101_VALIDATION_PARALLEL_CONFIG"))
        if not discovered:
            raise ValueError("START_GUARD_CONFIG_REQUIRED")
        # The document decides which guard this host can run. Loading everything as v3 both
        # rejected the schema-4 macOS document and built an NVML probe, which refuses every
        # preflight with GPU_TARGET_UNAVAILABLE on a host with no CUDA device.
        document = describe_execution_document(Path(discovered))
        key = self._composition_key(document)
        admission = self._admissions.get(key)
        if admission is None:
            admission = _GuardAdmission(
                document=document, accelerator=_accelerator_for_document(document))
            self._admissions[key] = admission
        return admission

    @staticmethod
    def _composition_key(document) -> tuple:
        profile = None if document.profile is None else document.profile.profile
        return (profile, document.config_sha256, document.accelerator, document.selector)

    @property
    def policy(self):
        return self.admission().policy

    @property
    def gpu_selector(self):
        return self.admission().selector

    def begin_epoch(self, scope, config_path=None):
        """A fresh probe for the document this request names; the composition may be reused."""

        return self.admission(config_path).begin_epoch(scope)

    def require_before_spawn(self, scope, config_path=None):
        return self.admission(config_path).require_before_spawn(scope)


def _accelerator_for_document(document):
    """The accelerator probe the document's combination asks for; ``None`` keeps the v3 path."""

    if document.accelerator == "mps":
        from so101_demo.parallel_batch.accelerator_probe import select_accelerator_probe

        selection = select_accelerator_probe("mps")
        if selection is None:  # pragma: no cover - the table above only asks for MPS
            raise RuntimeError("MPS_ACCELERATOR_PROBE_MISSING")
        return selection.probe.probe
    return None


class _HostResourceProbe:
    """Fixed mode admits through the shared start guard; no budget authority is consulted."""

    def __init__(self, start_guard=None, gpu_selector=None) -> None:
        self._start_guard = start_guard
        self._gpu_selector = gpu_selector
        self._epochs = 0

    def _admission(self, request):
        """The composition for this request's document, when the guard is the lazy composer."""

        resolve = getattr(self._start_guard, "admission", None)
        if resolve is None:
            return None
        config_path = getattr(request, "parallel_config_path", None)
        return resolve(config_path)

    def probe(self, _request, config):
        observations: dict[str, object] = {"logical_cpu_count": os.cpu_count() or 0}
        reasons: list[str] = []
        workers = max(1, int(getattr(config, "worker_count", 1)))
        observations["requested_worker_count"] = workers
        if self._start_guard is None:
            reasons.append("START_GUARD_UNAVAILABLE")
            return not reasons, tuple(reasons), observations
        try:
            admission = self._admission(_request)
        except Exception as error:
            observations["probe_error"] = type(error).__name__
            reasons.append("RESOURCE_PROBE_FAILED")
            return not reasons, tuple(reasons), observations
        selector = getattr(config, "gpu_device", None)
        if selector is not None:
            gpu_selector = f"{selector.selector_kind}:{selector.selector}"
        elif admission is not None:
            gpu_selector = self._gpu_selector or admission.selector
        else:
            gpu_selector = self._gpu_selector or getattr(
                self._start_guard, "gpu_selector", None)
        if not gpu_selector:
            reasons.append("CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION")
            return not reasons, tuple(reasons), observations
        try:
            from so101_demo.parallel_batch.start_guard import GuardScope

            # Every request is its own epoch: a previous verdict is never reused.
            self._epochs += 1
            scope = GuardScope(
                batch_id="web-preflight",
                epoch=self._epochs,
                owner_pid=os.getpid(),
                owner_starttime_ticks=1,
                gpu_selector=gpu_selector,
                worker_count=workers,
            )
            result = (admission.begin_epoch(scope) if admission is not None
                      else self._start_guard.begin_epoch(scope))
        except Exception as error:
            observations["probe_error"] = type(error).__name__
            reasons.append("RESOURCE_PROBE_FAILED")
            return not reasons, tuple(reasons), observations
        observations["start_guard_status"] = result.status
        # The label is derived from the checks that actually ran, so a client can tell a
        # unified-memory proxy apart from a device-level VRAM reading without guessing.
        admission_kind = (
            "unified-memory-proxy" if "mps_headroom" in result.checks
            else ("nvml-device" if "gpu" in result.checks else None)
        )
        observations["start_guard"] = {
            "status": result.status,
            "cleanup_state": result.cleanup_state,
            "gpu_uuid": None if result.snapshot is None else result.snapshot.gpu_uuid,
            "observed_monotonic_s": result.completed_monotonic_s,
            "admission_kind": admission_kind,
            "checks": {
                name: {"status": check.status, "reason": check.reason,
                       "observed": check.observed, "cutoff": check.cutoff,
                       "unit": check.unit}
                for name, check in sorted(result.checks.items())
            },
        }
        if result.snapshot is not None:
            observations.update(
                effective_cpu_cores=result.snapshot.effective_cpu_cores,
                ram_available_bytes=result.snapshot.ram_available_bytes,
                gpu_free_bytes=result.snapshot.gpu_free_bytes,
                gpu_uuid=result.snapshot.gpu_uuid,
            )
        if result.status == "FAIL":
            for name, check in sorted(result.checks.items()):
                if check.status == "FAIL":
                    reasons.append(check.reason)
        if result.cleanup_state != "CLEAR":
            reasons.append(result.cleanup_state)
        return not reasons, tuple(reasons), observations


class ProductionExpertValidationService(ExpertValidationService):
    """API-complete facade over the durable supervisor composition."""

    #: How often the lease-expiry loop runs. A lease is short-lived by design, so this is the delay
    #: between its deadline passing and its state becoming EXPIRED.
    MAINTENANCE_INTERVAL_S = 0.25

    def __init__(self, *, layout: ProductionRuntimeLayout, registry, artifacts, **kwargs):
        super().__init__(**kwargs)
        self.layout = layout
        self._maintenance_task: asyncio.Task | None = None
        self.maintenance_failed = False
        self._current_source_config_sha256 = lambda: current_manifest_source_hash(self.layout)
        self.registry = registry
        self.artifacts = artifacts
        self._pending: dict[str, tuple[CampaignStartRequest, object, dict[str, object]]] = {}
        self._campaigns: dict[str, dict[str, object]] = {}
        self._campaign_requests: dict[str, CampaignStartRequest] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._restore_campaigns()

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
            if request.execution_mode != "ADAPTIVE":
                try:
                    projected = self._fixed_campaign_projection(request)
                except (
                    CoordinatorProjectionError,
                    ContractError,
                    StatisticsProjectionError,
                ):
                    projected = None
                if projected is not None:
                    projection = projected
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

        from .preflight import resolve_execution_document

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

    def close(self) -> None:
        self.stop_maintenance()
        self.store.close()

    # -- lease maintenance ---------------------------------------------------------------
    #
    # ``create_expert_validation_app`` runs this loop inside its own lifespan. The unified service
    # mounts the validation *routes* without that lifespan and asks the service for a
    # ``start_maintenance`` hook instead; no implementation provided one, so nothing ever expired a
    # lease there and an expired lease stayed ACTIVE in the store - which refuses every later acquire
    # with LEASE_ALREADY_HELD, for good, on a domain a session has walked away from.

    def start_maintenance(self) -> None:
        """Start the expiry loop. Synchronous on purpose: the lifecycle awaits a returned coroutine,
        so an ``async def`` here would block startup for as long as the loop runs."""
        if self._maintenance_task is not None and not self._maintenance_task.done():
            return
        self.maintenance_failed = False
        self._maintenance_task = asyncio.get_running_loop().create_task(self._maintain_leases())

    def stop_maintenance(self) -> None:
        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            self._maintenance_task = None

    async def _maintain_leases(self) -> None:
        """Expire due leases until expiry itself stops working, then stop and say so."""
        while True:
            try:
                self.lease_service.expire_due()
            except Exception:  # noqa: BLE001 - a domain that cannot expire leases must stay visible
                logging.getLogger(__name__).exception("LEASE_MAINTENANCE_FAILED")
                self.maintenance_failed = True
                supervisor = getattr(self, "supervisor", None)
                cancel = getattr(supervisor, "cancel_for_reason", None)
                if cancel is not None:
                    try:
                        cancel("LEASE_MAINTENANCE_FAILED")
                    except Exception:  # noqa: BLE001 - the failure is already recorded
                        logging.getLogger(__name__).exception("LEASE_OWNER_CANCEL_FAILED")
                return
            await asyncio.sleep(self.MAINTENANCE_INTERVAL_S)

    def health(self):
        return {
            "ok": True,
            "service": "expert-validation",
            "lease_maintenance_failed": self.maintenance_failed,
        }

    def capabilities(self):
        lease = self.lease_service.capabilities
        document = self._execution_document()
        if document is not None and document.profile is not None:
            return self._macos_capabilities(document, lease)
        capability = self.registry.require("moveit_expert", "validate_pick_place")
        available_modes = tuple(
            mode
            for mode in capability.execution_modes
            if capability.mode_availability[mode].available
        )
        return {
            "available": bool(available_modes),
            "execution_modes": available_modes,
            "fixed_worker_counts": FIXED_WORKER_COUNTS,
            "worker_count_availability": self._worker_count_availability(),
            "start_guard_policy": self._start_guard_policy(),
            "default_execution_mode": capability.default_execution_mode,
            "lease_duration_s": lease.duration_s,
            "lease_renewal_margin_s": lease.renewal_margin_s,
        }

    def _execution_document(self):
        """The execution document this service would run, or ``None`` when it cannot be read."""

        from .preflight import describe_execution_document

        path = Path(self.layout.parallel_config_path)
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None
        cached = getattr(self, "_document_cache", None)
        if cached is not None and cached[0] == (str(path), digest):
            return cached[1]
        try:
            document = describe_execution_document(path)
        except Exception:  # noqa: BLE001 - an unreadable document advertises nothing
            return None
        self._document_cache = ((str(path), digest), document)
        return document

    def _macos_capabilities(self, document, lease):
        """The platform-bound document: fixed W1/W2, and no budget or qualification authority.

        The StartGuard policy is still displayed, because a client has to be able to show the
        cutoffs a start is judged against; the note next to it says what it is not.
        """

        from .api import START_GUARD_NOT_A_QUALIFICATION, WorkerCountAvailability

        profile = document.profile
        availability = tuple(
            WorkerCountAvailability(
                worker_count=count,
                selectable=count in MACOS_WORKER_COUNTS,
                status="SUPPORTED" if count in MACOS_WORKER_COUNTS else UNSUPPORTED_ON_MACOS,
                reason_codes=() if count in MACOS_WORKER_COUNTS else (UNSUPPORTED_ON_MACOS,),
                profile_sha256=None,
                qualification_sha256=None,
            )
            for count in FIXED_WORKER_COUNTS
        )
        return {
            "available": True,
            "platform": profile.platform,
            "execution_modes": ("SEQUENTIAL", "PARALLEL"),
            "default_execution_mode": profile.execution_mode,
            "fixed_worker_counts": FIXED_WORKER_COUNTS,
            "worker_count_availability": availability,
            "support_matrix": tuple(row.to_document() for row in MACOS_EXECUTION_PROFILES),
            "execution_profile": profile.profile,
            "execution_schema_version": document.schema_version,
            "execution_config_sha256": document.config_sha256,
            # No budget provider and no per-N qualification is consulted for the macOS matrix.
            "worker_qualifications": (),
            "adaptive_default_ladder": (),
            "start_guard_policy": self._start_guard_policy(),
            "start_guard_note": START_GUARD_NOT_A_QUALIFICATION,
            "lease_duration_s": lease.duration_s,
            "lease_renewal_margin_s": lease.renewal_margin_s,
        }

    def _start_guard_policy(self):
        """The enforced guard policy for display; never a resource qualification."""

        engine = getattr(getattr(self, "supervisor", None), "preflight_engine", None)
        probe = getattr(engine, "_resources", None)
        guard_object = getattr(probe, "_start_guard", None)
        if guard_object is None:
            return None
        try:
            policy = guard_object.policy
        except Exception:
            return None
        if policy is None:
            return None
        return {
            "timeout_s": policy.timeout_s,
            "cpu_busy_warn_fraction": policy.cpu_busy_warn_fraction,
            "ram_minimum_bytes": policy.ram_minimum_bytes,
            "ram_minimum_fraction": policy.ram_minimum_fraction,
            "gpu_minimum_bytes": policy.gpu_minimum_bytes,
            # Present only for the schema-v4 macOS MPS combination; null keeps the v3 answer
            # byte-identical for every existing consumer.
            "mps_minimum_headroom_bytes": getattr(policy, "mps_minimum_headroom_bytes", None),
        }

    def _worker_count_availability(self):
        """Every advertised count whose domains/ports exist; the guard decides at start."""

        from .api import WorkerCountAvailability

        configured = getattr(self, "configured_worker_counts", None)
        if configured is None:
            configured = tuple(range(2, FIXED_WORKER_COUNTS[-1] + 1))
        available = set(configured)
        return tuple(
            WorkerCountAvailability(
                worker_count=count,
                selectable=count in available,
                status="CONFIGURED" if count in available else "NOT_CONFIGURED",
                reason_codes=() if count in available else ("DOMAIN_OR_PORT_UNAVAILABLE",),
                profile_sha256=None,
                qualification_sha256=None,
            )
            for count in FIXED_WORKER_COUNTS[1:]
        )

    def acquire_lease(self, body):
        return asdict(self.lease_service.acquire(body["service_session_id"]))

    def renew_lease(self, lease_id, body):
        return asdict(
            self.lease_service.renew(
                body["service_session_id"], lease_id, body["generation"]
            )
        )

    def release_lease(self, lease_id, body):
        self.lease_service.release(
            body["service_session_id"], lease_id, body["generation"]
        )
        return {"lease_id": lease_id, "released": True}

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

        from .preflight import resolve_execution_document

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
        from .preflight import PreflightRejected

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

    def _with_retry_history(self, campaign_id, projection):
        """Append the durable retry history. It is a read: nothing above it is recomputed."""

        admissions = getattr(self.store, "retry_admissions", None)
        if admissions is None:
            # A read-only cursor double keeps no admission table; it has no history to append.
            return projection
        rows = tuple(admissions(campaign_id))
        if not rows:
            # No retry has ever been admitted: the projection is returned unchanged, so a cached
            # campaign keeps its identity.
            return projection
        history = tuple(
            retry_history_document(
                retry_history_entry({
                    **row,
                    "cleanup_receipt_sha256": getattr(
                        self.store.batch(row["batch_id"]), "cleanup_receipt_sha256", None
                    ),
                })
            )
            for row in rows
        )
        return {**projection, "retry_history": history}

    def _campaign_projection(self, campaign_id):
        try:
            cached = self._campaigns[campaign_id]
        except KeyError as error:
            raise ServiceConflict("VALIDATION_CAMPAIGN_NOT_FOUND") from error
        request = self._campaign_requests.get(campaign_id)
        if request is None:
            return self._with_recovery_fence(campaign_id, cached)
        if request.execution_mode == "ADAPTIVE":
            try:
                projection = self._adaptive_campaign_projection(request)
            except CoordinatorProjectionError as error:
                if str(error) == "JOURNAL_REPLAY_INCOMPLETE":
                    return self._with_recovery_fence(campaign_id, cached)
                raise ServiceConflict("UPSTREAM_PROJECTION_INVALID") from error
            if projection is None:
                return self._with_recovery_fence(campaign_id, cached)
            projection = self._with_recovery_fence(campaign_id, projection)
            self._campaigns[campaign_id] = projection
            return projection
        try:
            projection = self._fixed_campaign_projection(request)
        except (CoordinatorProjectionError, ContractError, StatisticsProjectionError) as error:
            if str(error) == "JOURNAL_REPLAY_INCOMPLETE":
                return self._with_recovery_fence(campaign_id, cached)
            raise ServiceConflict("UPSTREAM_PROJECTION_INVALID") from error
        if projection is None:
            return self._with_recovery_fence(campaign_id, cached)
        projection = self._with_recovery_fence(campaign_id, projection)
        self._campaigns[campaign_id] = projection
        return projection

    def _with_recovery_fence(self, campaign_id, projection):
        # Web admission state must not rewrite upstream outcomes or receipts.
        if self.store.recovery_fence(campaign_id) is not None:
            return {**projection, "status": "NEEDS_OPERATOR_RECOVERY"}
        return projection

    def _fixed_campaign_projection(self, request):
        batch_root = (
            Path(request.evidence_root)
            / "campaigns"
            / request.campaign_id
            / request.batch_id
        ).resolve()
        journal_root = batch_root / "coordinator"
        epoch_path = journal_root / "coordinator_epoch.json"
        if epoch_path.is_symlink():
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
        if not epoch_path.exists():
            return None
        if not epoch_path.is_file():
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
        try:
            epoch_document = json.loads(epoch_path.read_text(encoding="utf-8"))
            epoch = epoch_document["coordinator_epoch"]
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID") from error
        if (
            set(epoch_document) != {"batch_id", "coordinator_epoch"}
            or epoch_document["batch_id"] != request.batch_id
            or isinstance(epoch, bool)
            or not isinstance(epoch, int)
            or epoch <= 0
        ):
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
        binding = CampaignUpstreamBinding(
            campaign_id=request.campaign_id,
            batch_id=request.batch_id,
            owner_kind="COORDINATOR",
            owner_epoch_or_generation=epoch,
            journal_root=journal_root,
            batch_root=batch_root,
        )
        reader = CoordinatorEventReader(
            ReadOnlyCoordinatorJournal(journal_root, request.batch_id),
            binding,
        )
        batch = reader.read_after(AcceptedCoordinatorCursor.initial(binding))
        if not batch.events:
            return None
        # The canonical durable projection is committed before it is read back: a retry admission
        # validates the original point's business result against exactly this state, never against
        # a value this request happened to compute.
        self._persist_canonical_projection(request, batch)
        state = batch.projected_state
        raw_points = state.get("points")
        if not isinstance(raw_points, Mapping):
            raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
        selected = tuple(request.selection.point_ids)
        # A canonical projection only carries points that already produced an event. A selected
        # point with no event at all is UNRUN; any point outside the selection is a real defect.
        if set(raw_points) - set(selected):
            raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
        raw_workers = state.get("workers", {})
        if not isinstance(raw_workers, Mapping):
            raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
        active_by_point = {}
        for worker_id, raw_worker in raw_workers.items():
            if not isinstance(worker_id, str) or not isinstance(raw_worker, Mapping):
                raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
            lease = raw_worker.get("lease")
            if lease is not None:
                if not isinstance(lease, Mapping):
                    raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
                point_id = lease.get("point_id")
                attempt_id = lease.get("attempt_id")
                if (
                    point_id not in selected
                    or not isinstance(attempt_id, str)
                    or point_id in active_by_point
                ):
                    raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
                active_by_point[point_id] = (attempt_id, worker_id)
        execution_started_ids = set()
        for event in batch.events:
            if event.type != "ATTEMPT_STARTED":
                continue
            identity = event.payload.get("identity")
            identity = identity if isinstance(identity, Mapping) else event.payload
            if identity.get("point_id") not in selected:
                raise CoordinatorProjectionError("ATTEMPT_PROJECTION_INVALID")
            execution_started_ids.add(identity["point_id"])
        display_ids = {point.id: point.display_id for point in request.selection.points}
        evidence_by_point = {point_id: [] for point_id in selected}
        committed_identities = set()
        for event in batch.events:
            if event.type != "RESULT_COMMITTED":
                continue
            if not isinstance(event.payload.get("identity"), Mapping):
                # A canonical result event must still reference the sealed attempt it commits:
                # the import is authorized by that reference, never by a flat outcome field.
                raise CoordinatorProjectionError("RESULT_REFERENCE_INVALID")
            evidence = register_committed_attempt(event, binding, selected, self.artifacts)
            if evidence.identity in committed_identities:
                raise CoordinatorProjectionError("DUPLICATE_COMMITTED_ATTEMPT")
            committed_identities.add(evidence.identity)
            evidence_by_point[evidence.identity.point_id].append(evidence)
        points = []
        point_statuses = {}
        unrun_point: dict[str, object] = {"status": "UNRUN", "attempts": 0, "terminal": False}
        for point_id in selected:
            raw_point = raw_points.get(point_id, unrun_point)
            if not isinstance(raw_point, Mapping):
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            try:
                status = PointStatus(raw_point["status"])
            except (KeyError, TypeError, ValueError) as error:
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID") from error
            attempts = raw_point.get("attempts", 0)
            if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            if not isinstance(raw_point.get("terminal", False), bool):
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            active_attempt = raw_point.get("active_attempt")
            active_worker_id = None
            if active_attempt is not None:
                active_lease = active_by_point.get(point_id)
                if (
                    not isinstance(active_attempt, str)
                    or active_lease is None
                    or active_lease[0] != active_attempt
                ):
                    raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
                active_worker_id = active_lease[1]
            elif point_id in active_by_point:
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            reason = raw_point.get("blocked_by")
            if reason is not None and not isinstance(reason, str):
                raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
            point_statuses[point_id] = status
            points.append(
                PointProjection(
                    point_id=point_id,
                    status=status,
                    evaluated=status in {PointStatus.PASSED, PointStatus.FAILED},
                    execution_started=point_id in execution_started_ids,
                    active_worker_id=active_worker_id,
                    reason=reason,
                )
            )

        workers = []
        for worker_id, raw_worker in sorted(raw_workers.items()):
            if not isinstance(worker_id, str) or not isinstance(raw_worker, Mapping):
                raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
            lease = raw_worker.get("lease")
            if lease is not None and not isinstance(lease, Mapping):
                raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
            generation = raw_worker.get("generation", 1)
            lease_count = raw_worker.get("lease_count", 0)
            worker_state = raw_worker.get("state", "ACTIVE")
            if (
                type(generation) is not int or generation <= 0
                or type(lease_count) is not int or lease_count < 0
                or not isinstance(worker_state, str) or not worker_state
            ):
                raise CoordinatorProjectionError("WORKER_PROJECTION_INVALID")
            workers.append(
                WorkerProjection(
                    worker_id=worker_id,
                    generation=generation,
                    state=worker_state,
                    active_point_id=lease.get("point_id") if lease is not None else None,
                    lease_count=lease_count,
                    quarantine_reason=raw_worker.get("quarantine_reason"),
                    recovery_result=raw_worker.get("recovery_result"),
                )
            )

        terminal_reason = state.get("terminal_reason")
        if terminal_reason is not None and not isinstance(terminal_reason, str):
            raise CoordinatorProjectionError("BATCH_PROJECTION_INVALID")
        terminal = terminal_reason is not None and all(
            raw_points.get(point_id, unrun_point).get("terminal", False)
            for point_id in selected
        )
        cleanup_complete = state.get("batch_cleanup_complete", False)
        if not isinstance(cleanup_complete, bool):
            raise CoordinatorProjectionError("BATCH_PROJECTION_INVALID")
        summary = BatchSummary(
            run_mode=RunMode.EXECUTE,
            point_statuses=point_statuses,
            batch_terminal=terminal,
            batch_cleanup_complete=cleanup_complete,
            terminal_reason=terminal_reason,
        )
        broker_healthy = state.get("broker_healthy", True)
        broker_failed = state.get("broker_recovery_failed", False)
        if not isinstance(broker_healthy, bool) or not isinstance(broker_failed, bool):
            raise CoordinatorProjectionError("BROKER_PROJECTION_INVALID")
        statistics = summarize_first_pass(
            summary,
            points,
            workers=workers,
            broker=BrokerProjection(
                available=broker_healthy and not broker_failed,
                reason="BROKER_RECOVERY_FAILED" if broker_failed else None,
            ),
        )
        if terminal_reason == "WEB_CANCEL_REQUESTED":
            status = "CANCELLED" if terminal and cleanup_complete else "CANCELLING"
        elif terminal and cleanup_complete and statistics.qualification_passed:
            status = "COMPLETED"
        elif terminal and cleanup_complete and statistics.valid_failed:
            status = "COMPLETED_WITH_FAILURES"
        elif terminal and cleanup_complete:
            status = "INFRA_FAILED"
        elif terminal:
            status = "CLEANING_UP"
        else:
            status = "RUNNING"
        final_event = batch.events[-1]
        self.store.accept_upstream_cursor(
            UpstreamCursor(
                batch_id=request.batch_id,
                owner_kind="COORDINATOR",
                owner_epoch_or_generation=final_event.owner_epoch,
                segment_id=f"segment-{final_event.owner_epoch:020d}",
                event_id=f"event-{final_event.sequence:020d}",
                frame_sha256=final_event.frame_sha256,
            )
        )
        projected_points = tuple(
            {
                "point_id": point.point_id,
                "display_id": display_ids[point.point_id],
                "status": point.status.value,
                "retry_eligible": point.retry_eligible,
                "active_worker_id": point.active_worker_id,
                "reason": point.reason,
                "attempts": tuple(
                    {"generation": evidence.identity.lease_generation,
                     "attempt_id": evidence.identity.attempt_id,
                     "worker_id": evidence.identity.worker_id,
                     "worker_generation": evidence.identity.worker_generation,
                     "batch_id": evidence.identity.batch_id, "kind": "FIRST_PASS",
                     "status": evidence.status}
                    for evidence in evidence_by_point[point.point_id]
                ),
                "artifact_ids": tuple(
                    artifact.artifact_id for evidence in evidence_by_point[point.point_id]
                    for artifact in evidence.artifacts
                ),
                "artifacts": tuple(
                    asdict(artifact) for evidence in evidence_by_point[point.point_id]
                    for artifact in evidence.artifacts
                ),
            }
            for point in statistics.points
        )
        projected_workers = tuple(
            {
                "worker_id": worker.worker_id,
                "generation": worker.generation,
                "state": worker.state,
                "current_point_id": worker.active_point_id,
                "lease_count": worker.lease_count,
                "recovery_result": worker.recovery_result,
                "quarantine_reason": worker.quarantine_reason,
            }
            for worker in statistics.workers
        )
        return {
            "campaign_id": request.campaign_id,
            "manifest_id": request.manifest_id,
            "sequence": batch.next_cursor.sequence,
            "execution_mode": request.execution_mode,
            "owner_kind": "COORDINATOR",
            "batch_id": request.batch_id,
            "status": status,
            "points": projected_points,
            "workers": projected_workers,
            "broker": asdict(statistics.broker),
            "requested": statistics.requested,
            "evaluated": statistics.evaluated,
            "execution_started": statistics.execution_started,
            "valid_succeeded": statistics.valid_succeeded,
            "valid_failed": statistics.valid_failed,
            "indeterminate": statistics.indeterminate,
            "not_executed": statistics.not_executed,
            "evaluation_coverage": statistics.evaluation_coverage,
            "execution_coverage": statistics.execution_coverage,
            "qualified_success_rate": statistics.qualified_success_rate,
            "coverage_complete": statistics.coverage_complete,
            "execution_complete": statistics.execution_complete,
            "batch_cleanup_complete": statistics.batch_cleanup_complete,
            "qualification_passed": statistics.qualification_passed,
        }

    def _persist_canonical_projection(self, request, batch) -> None:
        """Commit the verified canonical prefix, its attempts and its cursor in one transaction.

        A journal that carries no canonical frame at all (a v1-v3 delta journal) has no canonical
        state to persist and is left exactly as it was: the durable reducer state exists only for
        the campaigns whose events the canonical reducer defines.
        """

        from .reducer import CanonicalCampaignReducer, ReducerError

        accept = getattr(self.store, "accept_projection_batch", None)
        if accept is None or not batch.events:
            # A read-only cursor double has no projection table to commit into.
            return
        final = batch.events[-1]
        next_cursor = UpstreamCursor(
            batch_id=request.batch_id,
            owner_kind="COORDINATOR",
            owner_epoch_or_generation=final.owner_epoch,
            segment_id=f"segment-{final.owner_epoch:020d}",
            event_id=f"event-{final.sequence:020d}",
            frame_sha256=final.frame_sha256,
        )
        snapshot = self.store.read_projection_state(request.batch_id)
        try:
            accept(
                batch_id=request.batch_id,
                expected_cursor=snapshot.cursor,
                events=batch.events,
                next_cursor=next_cursor,
                reducer=CanonicalCampaignReducer(),
            )
        except ReducerError as error:
            if error.code == "REDUCER_STATE_REQUIRED":
                return
            raise CoordinatorProjectionError("PROJECTION_PERSIST_FAILED") from error
        except (StoreConflict, ValueError) as error:
            raise CoordinatorProjectionError("PROJECTION_PERSIST_FAILED") from error

    def _adaptive_campaign_projection(self, request):
        """Project the adaptive Runner journal; never the nested pool journals."""
        batch_root = (
            Path(request.evidence_root)
            / "campaigns"
            / request.campaign_id
            / request.batch_id
        ).resolve()
        journal_root = batch_root / "r" / request.batch_id / "journal"
        epoch_path = journal_root / "coordinator_epoch.json"
        if epoch_path.is_symlink():
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
        if not epoch_path.exists():
            return None
        if not epoch_path.is_file():
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
        try:
            epoch_document = json.loads(epoch_path.read_text(encoding="utf-8"))
            epoch = epoch_document["coordinator_epoch"]
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID") from error
        if (
            epoch_document.get("batch_id") != request.batch_id
            or isinstance(epoch, bool)
            or not isinstance(epoch, int)
            or epoch <= 0
        ):
            raise CoordinatorProjectionError("OWNER_EPOCH_INVALID")
        binding = CampaignUpstreamBinding(
            campaign_id=request.campaign_id,
            batch_id=request.batch_id,
            owner_kind="ADAPTIVE_RUNNER",
            owner_epoch_or_generation=epoch,
            journal_root=journal_root,
            batch_root=batch_root,
        )
        reader = AdaptiveEventReader(
            ReadOnlyCoordinatorJournal(journal_root, request.batch_id),
            binding,
        )
        batch = reader.read_after(AcceptedCoordinatorCursor.initial(binding))
        if not batch.events:
            return None
        view = batch.projection
        selected = tuple(request.selection.point_ids)
        display_ids = {point.id: point.display_id for point in request.selection.points}
        projected_points = []
        succeeded = failed = indeterminate = 0
        for point_id in selected:
            point_view = view.points.get(point_id)
            point_status = point_view.status if point_view is not None else "UNRUN"
            if point_status == "PASSED":
                succeeded += 1
            elif point_status == "FAILED":
                failed += 1
            elif point_status not in {"UNRUN"}:
                indeterminate += 1
            projected_points.append({
                "point_id": point_id,
                "display_id": display_ids[point_id],
                "status": point_status,
                "retry_eligible": point_status == "FAILED",
                "active_worker_id": None,
                "reason": None,
                "attempts": (),
                "artifact_ids": (),
                "artifacts": (),
            })
        terminal_status = view.terminal_status
        cleanup_complete = view.cleanup_complete is True
        if terminal_status is None:
            status = "RUNNING"
        elif not cleanup_complete:
            status = "CLEANING_UP"
        else:
            # The Runner's terminal vocabulary is already the campaign one.
            status = terminal_status
        requested = len(selected)
        evaluated = succeeded + failed
        final_event = batch.events[-1]
        self.store.accept_upstream_cursor(
            UpstreamCursor(
                batch_id=request.batch_id,
                owner_kind="ADAPTIVE_RUNNER",
                owner_epoch_or_generation=final_event.owner_epoch,
                segment_id=f"segment-{final_event.owner_epoch:020d}",
                event_id=f"event-{final_event.sequence:020d}",
                frame_sha256=final_event.frame_sha256,
            )
        )
        return {
            "campaign_id": request.campaign_id,
            "manifest_id": request.manifest_id,
            "sequence": batch.next_cursor.sequence,
            "execution_mode": request.execution_mode,
            "owner_kind": "ADAPTIVE_WRAPPER",
            "batch_id": request.batch_id,
            "status": status,
            "points": tuple(projected_points),
            "workers": (),
            "broker": None,
            "requested": requested,
            "evaluated": evaluated,
            "execution_started": evaluated + indeterminate,
            "valid_succeeded": succeeded,
            "valid_failed": failed,
            "indeterminate": indeterminate,
            "not_executed": requested - evaluated - indeterminate,
            "evaluation_coverage": evaluated / requested if requested else 0.0,
            "execution_coverage": (
                (evaluated + indeterminate) / requested if requested else 0.0
            ),
            "qualified_success_rate": (
                succeeded / evaluated if evaluated else None
            ),
            "coverage_complete": terminal_status is not None and evaluated == requested,
            "execution_complete": terminal_status is not None,
            "batch_cleanup_complete": cleanup_complete,
            "qualification_passed": (
                terminal_status == "COMPLETED" if terminal_status is not None else None
            ),
            "levels_used": view.levels_used,
            "fallback_history": tuple(
                {
                    "generation": fallback.generation,
                    "from_count": fallback.from_count,
                    "to_count": fallback.to_count,
                    "reason": fallback.reason,
                    "transition": fallback.transition,
                }
                for fallback in view.fallbacks
            ),
            "current_generation": view.current_generation,
            "infra_attempts": sum(
                point.infra_attempts for point in view.points.values()
            ),
        }

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
        if not self.store.retry_items(campaign_id):
            self.store.enqueue_retries(campaign_id, point_ids)
        self.supervisor.reconcile_retry(campaign_id)
        self.get_campaign(campaign_id)
        request, context = self._production_retry_admission(campaign_id, point_ids[0], body)
        result = await self.supervisor.start_production_retry(request=request, context=context)
        projection = {**self.get_campaign(campaign_id), "status": result["status"]}
        self._campaigns[campaign_id] = projection
        self.store.finish_command(body["command_id"], projection)
        return projection

    def issue_candidate_context(
        self,
        *,
        task_id,
        dispatch_id,
        campaign_id,
        batch_id,
        manifest_id,
        execution_profile,
        command_id,
        owner_generation=1,
        max_runs=1,
        evidence_root=None,
        ttl_s=3600.0,
    ) -> CandidateExecutionContext:
        """Issue one bounded candidate run from the installed document the profile names."""

        installed = self._installed_profile_document(execution_profile)
        now = time.monotonic_ns()
        return self.register_candidate_context(CandidateExecutionContext(
            context_id="candidate-" + uuid.uuid4().hex,
            task_id=task_id,
            dispatch_id=dispatch_id,
            campaign_id=campaign_id,
            batch_id=batch_id,
            manifest_id=manifest_id,
            execution_profile=installed.profile.profile,
            schema_version=installed.schema_version,
            batch_kind=installed.profile.batch_kind,
            worker_count=installed.profile.worker_count,
            config_sha256=installed.config_sha256,
            runtime_closure_sha256=self._current_runtime_closure(),
            evidence_root=Path(evidence_root) if evidence_root is not None else self.store.root.parent,
            owner_generation=owner_generation,
            command_id=command_id,
            issued_at_monotonic_ns=now,
            expires_at_monotonic_ns=now + int(ttl_s * 1_000_000_000),
            max_runs=max_runs,
        ))

    def _installed_profile_document(self, execution_profile):
        from .preflight import resolve_execution_document

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

    def _current_runtime_closure(self) -> str:
        return runtime_closure_sha256(SimpleNamespace(
            coordinator_executable_sha256=_sha256(self.layout.coordinator_executable),
            adaptive_runner_module_sha256=_sha256(
                Path(__import__("so101_demo.parallel_batch.adaptive_runner", fromlist=["x"]).__file__)
            ),
            adaptive_pool_module_sha256=_sha256(
                Path(__import__("so101_demo.parallel_batch.adaptive_pool", fromlist=["x"]).__file__)
            ),
            adaptive_cleanup_executable_sha256=_sha256(self.layout.cleanup_executable),
            adaptive_wrapper_sha256=_sha256(self.layout.adaptive_wrapper),
            parallel_config_sha256=_sha256(self.layout.parallel_config_path),
            adaptive_config_sha256=_sha256(self.layout.adaptive_config_path),
            yolo_weights_sha256=self.layout.yolo_weights_sha256,
            grounded_sam_manifest_sha256=self.layout.grounded_manifest_sha256,
            broker_image_id=self.layout.broker_image_id,
            resource_manifest_sha256=_sha256(self.layout.parallel_config_path),
            source_commit=self.layout.source_commit,
            install_prefix=str(self.layout.demo_prefix),
        ))

    def _production_retry_admission(self, campaign_id, point_id, body):
        """Mint the one context and the one request this installed service may retry with."""

        original, item, catalog_sha256, selection_sha256, result_sha256 = self._retry_origin(
            campaign_id, point_id
        )
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
            execution_profile=RETRY_PROFILE,
            schema_version=RETRY_SCHEMA_VERSION,
            batch_kind=RETRY_BATCH_KIND,
            worker_count=RETRY_WORKER_COUNT,
            campaign_id=campaign_id,
            batch_id=f"retry-{item.ordinal + 1:03d}",
            manifest_id=original.manifest_id,
            config_sha256=self._installed_profile_document(RETRY_PROFILE).config_sha256,
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
        return self._retry_start_request(
            context, item, catalog_sha256, selection_sha256, result_sha256, install_prefix
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
        if not self.store.retry_items(campaign_id):
            self.store.enqueue_retries(campaign_id, point_ids)
        self.supervisor.reconcile_retry(campaign_id)
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

    def subscribe(self):
        queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self._subscribers.discard(queue)


def default_admission_factory(environment: Mapping[str, str], *, config_path=None):
    """Compose the installed shared gate from the full verified P/Q/M/D authority.

    The identity is derived from the discovered v2 config, the installed and source
    inventory bytes and real hardware facts, then verified against the declared
    execution identity; an unreadable or mismatching authority raises instead of
    degrading to a permissive gate.
    """

    return _LazyStartGuard(environment, config_path)


def create_production_service(
    evidence_root: Path,
    *,
    environment: Mapping[str, str] | None = None,
    execution_port=None,
    admission_factory=None,
) -> ProductionExpertValidationService:
    """Compose all durable authorities used by the installed server entry point.

    ``execution_port`` is a typed test seam: only the repository's L2
    installed-test launcher passes it.  The production console entry point
    (``main.py``) never does, so installed production composition always
    targets the installed upstream executables.
    """

    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v3

    environment = dict(os.environ if environment is None else environment)
    layout = ProductionRuntimeLayout.discover(environment)
    state_root = (Path(evidence_root) / "validation-service").resolve()
    # The owner tree is the service's own durable spawn record, and the root the demo-side
    # spawn boundaries inherit: it is created by the first record, never up front.
    owner_tree_root = (Path(evidence_root) / "owner-tree").resolve()
    store = SupervisorStore.open(state_root)
    try:
        owner = ExecutionProcessOwner(store=store, owner_tree_root=owner_tree_root)
        if admission_factory is None:
            start_guard = default_admission_factory(
                environment, config_path=layout.parallel_config_path)
        else:
            start_guard = admission_factory(environment)
        preflight = PreflightEngine(
            _HostResourceProbe(start_guard=start_guard),
            singleton_probe=lambda: not owner.has_active_execution(),
        )
        supervisor = ExpertValidationSupervisor(
            store=store, process_owner=owner, preflight_engine=preflight,
            execution_port=execution_port,
        )
        lease = ValidationLeaseService(store, supervisor)
        probes = QualificationProbes(
            fixed_upstream=layout.coordinator_executable.is_file(),
            parallel_config=layout.parallel_config_path.is_file(),
            broker_image=bool(layout.broker_image_id),
            resource_probe=True,
            two_worker_live_acceptance=(
                str(layout.parallel_acceptance) if layout.parallel_acceptance else None
            ),
            adaptive_runner=True,
            adaptive_pool=True,
            adaptive_wrapper=layout.adaptive_wrapper.is_file(),
            adaptive_cleanup=layout.cleanup_executable.is_file(),
            adaptive_config=layout.adaptive_config_path.is_file(),
            adaptive_fault_injection=layout.adaptive_fault_injection is not None,
            adaptive_twenty_point_acceptance=(
                str(layout.adaptive_acceptance) if layout.adaptive_acceptance else None
            ),
            adaptive_performance_evidence=layout.adaptive_performance_tiers,
        )
        registry = ExecutorRegistry.v1(probes)
        artifacts = ValidationArtifactRegistry()
        service = ProductionExpertValidationService(
            layout=layout,
            registry=registry,
            artifacts=artifacts,
            store=store,
            supervisor=supervisor,
            lease_service=lease,
            current_source_config_sha256=lambda: _sha256(layout.parallel_config_path),
        )
        supervisor.service = service
        return service
    except Exception:
        store.close()
        raise
