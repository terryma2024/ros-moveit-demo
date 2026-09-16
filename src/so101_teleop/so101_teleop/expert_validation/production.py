"""Production composition root for the dedicated expert-validation service."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid
from typing import Mapping

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from so101_demo.parallel_batch.contracts import BatchSummary, ContractError, PointStatus, RunMode
from so101_demo.parallel_batch.journal import CoordinatorJournal

from .artifacts import ValidationArtifactRegistry
from .catalog import CatalogPoint, PointSelection, select_catalog_points
from .coordinator_events import (
    AcceptedCoordinatorCursor,
    CampaignUpstreamBinding,
    CoordinatorEventReader,
    CoordinatorProjectionError,
)
from .executor_registry import ExecutorRegistry, QualificationProbes
from .lease import ValidationLeaseService
from .models import UpstreamCursor
from .preflight import CampaignStartRequest
from .process_owner import ExecutionProcessOwner
from .service import ExpertValidationService, ServiceConflict, _request_hash, StartCampaignCommand
from .store import SupervisorStore
from .statistics import (
    BrokerProjection,
    PointProjection,
    StatisticsProjectionError,
    WorkerProjection,
    summarize_first_pass,
)
from .supervisor import ExpertValidationSupervisor
from .preflight import PreflightEngine


_BROKER_IMAGE = "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1"


@dataclass(frozen=True, slots=True)
class _ReadOnlyCoordinatorJournal:
    root: Path
    batch_id: str

    def replay(self):
        return CoordinatorJournal.read_only_replay(self.root, self.batch_id)


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
    *,
    module_path: Path,
    provenance_binding: Path | None,
    subprocess_runner=subprocess.run,
) -> tuple[Path, str]:
    """Read source authority from Git or an explicit copied-overlay binding."""

    bound_commit = None
    if provenance_binding is not None:
        if (
            not provenance_binding.is_absolute()
            or provenance_binding.is_symlink()
            or not provenance_binding.is_file()
            or provenance_binding.stat().st_size > 1024 * 1024
        ):
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID")
        try:
            document = json.loads(provenance_binding.read_text(encoding="utf-8"))
            source_root = Path(document["source_root"])
            bound_commit = document["source_commit"]
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID") from error
        if (
            document.get("schema_version") != 1
            or not source_root.is_absolute()
            or source_root.is_symlink()
            or not source_root.is_dir()
            or not isinstance(bound_commit, str)
        ):
            raise RuntimeError("SO101_VALIDATION_PROVENANCE_BINDING_INVALID")
        source_root = source_root.resolve()
    else:
        try:
            source_root = Path(
                subprocess_runner(
                    ["git", "-C", str(module_path.parent), "rev-parse", "--show-toplevel"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                ).stdout.strip()
            ).resolve()
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError("SO101_VALIDATION_SOURCE_IDENTITY") from error
    try:
        git_root = Path(
            subprocess_runner(
                ["git", "-C", str(source_root), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        ).resolve()
        source_commit = subprocess_runner(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = subprocess_runner(
            ["git", "-C", str(source_root), "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("SO101_VALIDATION_SOURCE_IDENTITY") from error
    if (
        git_root != source_root
        or len(source_commit) != 40
        or any(character not in "0123456789abcdef" for character in source_commit)
        or dirty
    ):
        raise RuntimeError("SO101_VALIDATION_SOURCE_IDENTITY")
    if bound_commit is not None and bound_commit != source_commit:
        raise RuntimeError("SO101_VALIDATION_SOURCE_COMMIT_MISMATCH")
    return source_root, source_commit


@dataclass(frozen=True, slots=True)
class ProductionRuntimeLayout:
    source_root: Path
    source_commit: str
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
        configured_commit = environment.get("SO101_VALIDATION_SOURCE_COMMIT")
        if configured_commit and configured_commit != source_commit:
            raise RuntimeError("SO101_VALIDATION_SOURCE_COMMIT_MISMATCH")
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


class _HostResourceProbe:
    """Fixed mode admits only after the same host facts required by the upstream config."""

    def probe(self, _request, config):
        observations: dict[str, object] = {"logical_cpu_count": os.cpu_count() or 0}
        reasons: list[str] = []
        try:
            from so101_demo.parallel_batch.resources import SystemResourceProbe

            snapshot = SystemResourceProbe().snapshot()
            observations.update(
                available_ram_gib=snapshot.available_ram_gib,
                gpu_free_gib=snapshot.gpu_free_gib,
            )
            workers = getattr(config, "worker_count", 1)
            if snapshot.logical_cpu_count < 4 * workers:
                reasons.append("CPU_HEADROOM")
            if snapshot.available_ram_gib < 6 + 4 * workers:
                reasons.append("RAM_HEADROOM")
            if snapshot.gpu_free_gib < 8:
                reasons.append("GPU_HEADROOM")
        except Exception as error:
            observations["probe_error"] = type(error).__name__
            reasons.append("RESOURCE_PROBE_FAILED")
        return not reasons, tuple(reasons), observations


class ProductionExpertValidationService(ExpertValidationService):
    """API-complete facade over the durable supervisor composition."""

    def __init__(self, *, layout: ProductionRuntimeLayout, registry, artifacts, **kwargs):
        super().__init__(**kwargs)
        self.layout = layout
        self.registry = registry
        self.artifacts = artifacts
        self._pending: dict[str, tuple[CampaignStartRequest, object, dict[str, object]]] = {}
        self._campaigns: dict[str, dict[str, object]] = {}
        self._campaign_requests: dict[str, CampaignStartRequest] = {}
        self._subscribers: set[asyncio.Queue] = set()

    def close(self) -> None:
        self.store.close()

    def health(self):
        return {"ok": True, "service": "expert-validation"}

    def capabilities(self):
        capability = self.registry.require("moveit_expert", "validate_pick_place")
        available_modes = tuple(
            mode
            for mode in capability.execution_modes
            if capability.mode_availability[mode].available
        )
        lease = self.lease_service.capabilities
        return {
            "available": bool(available_modes),
            "execution_modes": available_modes,
            "default_execution_mode": capability.default_execution_mode,
            "lease_duration_s": lease.duration_s,
            "lease_renewal_margin_s": lease.renewal_margin_s,
        }

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
        manifest = self.create_manifest(
            selection, source_config_sha256=_sha256(self.layout.parallel_config_path)
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

    def _campaign_request(self, body) -> CampaignStartRequest:
        mode = body["execution_mode"]
        adaptive = mode == "ADAPTIVE"
        batch_id = ("a" if adaptive else "b") + uuid.uuid4().hex[:4]
        selection = self._selection(body["manifest_id"])
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
            parallel_config_path=self.layout.parallel_config_path,
            adaptive_config_path=self.layout.adaptive_config_path,
            worker_count=(
                body.get("preferred_worker_count", 8)
                if adaptive
                else body.get("worker_count", 1)
            ),
            max_points_per_worker=body.get("max_points_per_worker"),
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
            parallel_config_sha256=_sha256(self.layout.parallel_config_path),
            adaptive_config_sha256=_sha256(self.layout.adaptive_config_path),
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
        capability = self.registry.require("moveit_expert", "validate_pick_place")
        availability = capability.mode_availability[body["execution_mode"]]
        if not availability.available:
            raise ServiceConflict(availability.reason or "EXECUTION_MODE_UNAVAILABLE")
        if self.layout.yolo_weights_path is None or self.layout.grounded_root is None:
            raise ServiceConflict("VALIDATION_MODELS_NOT_CONFIGURED")
        request = self._campaign_request(body)
        receipt = await self.supervisor.preflight(request)
        self._pending[receipt.receipt_id] = (request, receipt, dict(body))
        return {
            "receipt_id": receipt.receipt_id,
            "admitted": receipt.admitted,
            "manifest_id": receipt.manifest_id,
            "execution_mode": receipt.execution_mode,
            "execution_config": asdict(receipt.execution_config),
            "resource_observations": dict(receipt.resource_observations),
            "reason_codes": receipt.reason_codes,
            "expires_at_monotonic_ns": receipt.expires_at_monotonic_ns,
        }

    async def start_campaign_api(self, body):
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
        command = StartCampaignCommand(
            command_id=body["command_id"],
            lease_id=body["lease_id"],
            lease_generation=body["lease_generation"],
            manifest_id=body["manifest_id"],
            request=request,
        )
        digest = _request_hash(command)
        repeated = self.store.repeat_command(command.command_id, digest)
        if repeated is not None:
            return repeated
        self.store.begin_command(command.command_id, digest, "START_CAMPAIGN")
        result = await self.supervisor.start_first_pass(request, receipt=receipt)
        projection = {
            "campaign_id": result["campaign_id"],
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
        self.store.finish_command(command.command_id, projection)
        del self._pending[receipt_id]
        return projection

    def list_campaigns(self):
        return tuple(self.get_campaign(campaign_id) for campaign_id in self._campaigns)

    def get_campaign(self, campaign_id):
        try:
            cached = self._campaigns[campaign_id]
        except KeyError as error:
            raise ServiceConflict("VALIDATION_CAMPAIGN_NOT_FOUND") from error
        request = self._campaign_requests.get(campaign_id)
        if request is None or request.execution_mode == "ADAPTIVE":
            return cached
        try:
            projection = self._fixed_campaign_projection(request)
        except (CoordinatorProjectionError, ContractError, StatisticsProjectionError) as error:
            if str(error) == "JOURNAL_REPLAY_INCOMPLETE":
                return cached
            raise ServiceConflict("UPSTREAM_PROJECTION_INVALID") from error
        if projection is None:
            return cached
        self._campaigns[campaign_id] = projection
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
            _ReadOnlyCoordinatorJournal(journal_root, request.batch_id),
            binding,
        )
        batch = reader.read_after(AcceptedCoordinatorCursor.initial(binding))
        if not batch.events:
            return None
        state = batch.projected_state
        raw_points = state.get("points")
        if not isinstance(raw_points, Mapping):
            raise CoordinatorProjectionError("POINT_PROJECTION_INVALID")
        selected = tuple(request.selection.point_ids)
        if set(raw_points) != set(selected):
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
            if not isinstance(identity, Mapping) or identity.get("point_id") not in selected:
                raise CoordinatorProjectionError("ATTEMPT_PROJECTION_INVALID")
            execution_started_ids.add(identity["point_id"])
        display_ids = {point.id: point.display_id for point in request.selection.points}
        points = []
        point_statuses = {}
        for point_id in selected:
            raw_point = raw_points[point_id]
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
            generation = raw_worker.get("generation")
            lease_count = raw_worker.get("lease_count", 0)
            worker_state = raw_worker.get("state")
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
            raw_points[point_id].get("terminal", False) for point_id in selected
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
        if terminal and cleanup_complete and statistics.qualification_passed:
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
                "attempts": (),
                "artifact_ids": (),
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

    def cancel_campaign(self, campaign_id, body):
        self.lease_service.authorize(
            body["lease_id"], body["lease_generation"], service_session_id=body["service_session_id"]
        )
        self.supervisor.cancel_for_reason("USER_CANCELLED")
        projection = {**self.get_campaign(campaign_id), "status": "CANCELLING"}
        self._campaigns[campaign_id] = projection
        return projection

    async def retry_campaign(self, campaign_id, body):
        self.lease_service.authorize(
            body["lease_id"], body["lease_generation"], service_session_id=body["service_session_id"]
        )
        result = await self.supervisor.start_retries(campaign_id, tuple(body["point_ids"]))
        projection = {**self.get_campaign(campaign_id), "status": result["status"]}
        self._campaigns[campaign_id] = projection
        return projection

    def subscribe(self):
        queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self._subscribers.discard(queue)


def create_production_service(
    evidence_root: Path, *, environment: Mapping[str, str] | None = None
) -> ProductionExpertValidationService:
    """Compose all durable authorities used by the installed server entry point."""

    environment = dict(os.environ if environment is None else environment)
    layout = ProductionRuntimeLayout.discover(environment)
    state_root = (Path(evidence_root) / "validation-service").resolve()
    store = SupervisorStore.open(state_root)
    try:
        owner = ExecutionProcessOwner(store=store)
        preflight = PreflightEngine(
            _HostResourceProbe(),
            singleton_probe=lambda: not owner.has_active_execution(),
        )
        supervisor = ExpertValidationSupervisor(
            store=store, process_owner=owner, preflight_engine=preflight
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
