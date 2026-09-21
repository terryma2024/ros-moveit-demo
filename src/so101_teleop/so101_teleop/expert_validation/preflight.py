"""Closed admission contract for expert-validation campaigns."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import time
from types import MappingProxyType
from typing import Mapping
import uuid

from .catalog import PointSelection


FIXED_WORKER_COUNTS = tuple(range(1, 9))

#: The platform-bound macOS support matrix (design section 6). macOS exposes exactly three
#: combinations and nothing else; every other count, mode or profile is refused with a stable
#: ``UNSUPPORTED_ON_MACOS`` reason instead of being extrapolated from the selected points.
MACOS_PLATFORM = "macos"
UNSUPPORTED_ON_MACOS = "UNSUPPORTED_ON_MACOS"
#: The document is a macOS profile and the request named no routing key: nothing is inferred.
EXECUTION_PROFILE_REQUIRED = "EXECUTION_PROFILE_REQUIRED"
#: A profile was claimed but its installed document is not next to the configured one.
EXECUTION_DOCUMENT_MISSING = "EXECUTION_DOCUMENT_MISSING"
#: The declared config hash is not the bytes that will execute.
PARALLEL_CONFIG_HASH_MISMATCH = "PARALLEL_CONFIG_HASH_MISMATCH"
CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION = "CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"


class PreflightRejected(RuntimeError):
    """A campaign cannot be admitted without changing its requested mode."""


@dataclass(frozen=True, slots=True)
class ExecutionProfile:
    """One admissible macOS combination: the routing key a request must name exactly.

    ``(schema_version, profile, batch_kind, worker_count)`` is the whole key. The worker count
    belongs to the profile and is never derived from how many points were selected.
    """

    profile: str
    schema_version: int
    execution_mode: str
    worker_count: int
    batch_kind: str
    accelerator: str = "mps"
    selector: str = "MPS:default"
    platform: str = MACOS_PLATFORM

    def to_document(self) -> dict:
        """The capability row. It carries no budget profile and no qualification hash."""

        return {
            "profile": self.profile,
            "schema_version": self.schema_version,
            "execution_mode": self.execution_mode,
            "worker_count": self.worker_count,
            "batch_kind": self.batch_kind,
            "accelerator": self.accelerator,
            "selector": self.selector,
            "platform": self.platform,
            "selectable": True,
            "status": "SUPPORTED",
            "reason_codes": [],
            "profile_sha256": None,
            "qualification_sha256": None,
        }


def _execution_mode_for_worker_count(worker_count: int) -> str:
    """W1 is one sequential Worker; W2 is two parallel ones. There is no third shape."""

    if worker_count == 1:
        return "SEQUENTIAL"
    if worker_count == 2:
        return "PARALLEL"
    raise PreflightRejected(UNSUPPORTED_ON_MACOS)


def _approved_execution_routes() -> tuple:
    """The shared closed support matrix: the service does not keep a second copy of it."""

    from so101_demo.parallel_batch.contracts import APPROVED_EXECUTION_ROUTES

    return APPROVED_EXECUTION_ROUTES


def macos_execution_profiles() -> tuple[ExecutionProfile, ...]:
    """The three approved combinations, in the support-matrix order."""

    return tuple(
        ExecutionProfile(
            profile=str(route.execution_profile),
            schema_version=route.schema_version,
            execution_mode=_execution_mode_for_worker_count(route.worker_count),
            worker_count=route.worker_count,
            batch_kind=str(route.batch_kind),
        )
        for route in _approved_execution_routes()
    )


#: The macOS support matrix this service advertises: exactly three combinations.
MACOS_EXECUTION_PROFILES: tuple[ExecutionProfile, ...] = macos_execution_profiles()

#: The only worker counts macOS may offer: W1 and W2.
MACOS_WORKER_COUNTS: tuple[int, ...] = (1, 2)

#: The installed document each profile resolves to, beside the configured execution document.
PROFILE_DOCUMENT_BASENAMES: Mapping[str, str] = MappingProxyType({
    "MPS_W2_FIRST_PASS": "parallel_batch_v4_macos_mps_w2.yaml",
    "MPS_W1_FULL_RESTART_RETRY": "parallel_batch_v5_macos_mps_w1_retry.yaml",
    "MPS_W1_FIRST_PASS": "parallel_batch_v6_macos_mps_w1_first_pass.yaml",
})


class PreflightRejected(RuntimeError):
    """A campaign cannot be admitted without changing its requested mode."""


@dataclass(frozen=True, slots=True)
class ExecutionDocument:
    """One loaded execution document and the platform combination it declares."""

    path: Path
    schema_version: int
    config_sha256: str
    profile: ExecutionProfile | None
    accelerator: str
    selector: str
    config: object

    @property
    def macos_bound(self) -> bool:
        return self.profile is not None


def macos_execution_profile(schema_version: int) -> ExecutionProfile | None:
    for profile in MACOS_EXECUTION_PROFILES:
        if profile.schema_version == schema_version:
            return profile
    return None


def execution_profile_for_name(profile: str | None) -> ExecutionProfile | None:
    for row in MACOS_EXECUTION_PROFILES:
        if row.profile == profile:
            return row
    return None


def macos_execution_profile_for_config(config) -> ExecutionProfile | None:
    """The matrix row a loaded document declares, or ``None`` when it is not macOS-bound.

    The accelerator decides. A Linux/CUDA document of any schema keeps the existing NVML path,
    and a schema that macOS does not offer (v3) is not part of the matrix either. A Darwin/MPS
    document whose own profile, batch kind or worker count contradicts its row is refused rather
    than re-interpreted.
    """

    schema_version = getattr(config, "schema_version", None)
    if type(schema_version) is not int:
        return None
    row = macos_execution_profile(schema_version)
    if row is None:
        return None
    accelerator = getattr(config, "accelerator", None)
    if accelerator is None or str(getattr(accelerator, "kind", "")) != row.accelerator:
        return None
    guard = getattr(config, "start_guard", None)
    if getattr(guard, "mps_minimum_headroom_bytes", None) is None:
        raise PreflightRejected(UNSUPPORTED_ON_MACOS)
    declared = getattr(config, "execution_profile", None)
    if declared is not None and str(declared) != row.profile:
        raise PreflightRejected(UNSUPPORTED_ON_MACOS)
    declared_kind = getattr(config, "batch_kind", None)
    if declared_kind is not None and str(declared_kind) != row.batch_kind:
        raise PreflightRejected(UNSUPPORTED_ON_MACOS)
    if getattr(config, "worker_count", None) != row.worker_count:
        raise PreflightRejected(UNSUPPORTED_ON_MACOS)
    return row


def describe_execution_document(path: Path, *, platform: str | None = None) -> ExecutionDocument:
    """Load one installed execution document: real bytes, real hash, real platform combination."""

    from so101_demo.parallel_batch.w2_composition import load_execution_config_for_schema

    resolved = Path(path)
    config = load_execution_config_for_schema(resolved, platform=platform)
    accelerator = getattr(config, "accelerator", None)
    if accelerator is None:
        gpu = getattr(config, "gpu_device", None)
        accelerator_kind = "nvml"
        selector = (f"{gpu.selector_kind}:{gpu.selector}" if gpu is not None else "")
    else:
        accelerator_kind = str(accelerator.kind)
        selector = f"{accelerator_kind.upper()}:{accelerator.resolved_selector}"
    return ExecutionDocument(
        path=resolved,
        schema_version=int(getattr(config, "schema_version", 0)),
        config_sha256=hashlib.sha256(resolved.read_bytes()).hexdigest(),
        profile=macos_execution_profile_for_config(config),
        accelerator=accelerator_kind,
        selector=selector,
        config=config,
    )


def resolve_execution_document(
    directory: Path, profile: str | None, *, platform: str | None = None
) -> ExecutionDocument:
    """The installed document a claimed profile names, or a refusal.

    The three macOS documents are installed side by side, so the profile - never the worker
    count and never the selected-point count - decides which bytes a preflight binds.
    """

    row = execution_profile_for_name(profile)
    if row is None:
        raise PreflightRejected(UNSUPPORTED_ON_MACOS)
    candidate = Path(directory) / PROFILE_DOCUMENT_BASENAMES[row.profile]
    if not candidate.is_file():
        raise PreflightRejected(EXECUTION_DOCUMENT_MISSING)
    document = describe_execution_document(candidate, platform=platform)
    if document.profile is None or document.profile.profile != row.profile:
        raise PreflightRejected(UNSUPPORTED_ON_MACOS)
    return document


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHORT_BATCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,4}$", re.ASCII)


@dataclass(frozen=True, slots=True)
class FixedExecutionConfig:
    """Version-two fixed execution: mode and exact N, never a lifetime quota."""

    execution_mode: str
    worker_count: int



@dataclass(frozen=True, slots=True)
class AdaptiveExecutionConfig:
    preferred_worker_count: int
    fallback_worker_counts: tuple[int, ...]
    initial_points_per_worker: int
    worker_start_timeout_s: float
    max_infra_attempts_per_point: int
    yolo_executor_count: int
    adaptive_config_sha256: str


@dataclass(frozen=True, slots=True)
class CampaignStartRequest:
    campaign_id: str
    batch_id: str
    manifest_id: str
    selection: PointSelection
    execution_mode: str
    evidence_root: Path
    points_path: Path
    parallel_config_path: Path
    adaptive_config_path: Path
    worker_count: int
    max_points_per_worker: int | None
    fallback_worker_counts: tuple[int, ...]
    initial_points_per_worker: int
    worker_start_timeout_s: float
    max_infra_attempts_per_point: int
    yolo_executor_count: int
    service_session_id: str
    lease_generation: int
    source_commit: str | None
    install_prefix: str
    coordinator_executable_sha256: str
    adaptive_runner_module_sha256: str | None
    adaptive_pool_module_sha256: str | None
    adaptive_cleanup_executable_sha256: str | None
    adaptive_wrapper_sha256: str | None
    parallel_config_sha256: str
    adaptive_config_sha256: str | None
    yolo_weights_sha256: str
    grounded_sam_manifest_sha256: str
    broker_image_id: str
    resource_manifest_sha256: str
    #: The routing key a macOS request names. ``None`` keeps the schema-v3/Linux request shape,
    #: and is refused only when the loaded document is one of the three macOS profiles.
    execution_profile: str | None = None
    batch_kind: str | None = None
    yolo_weights_path: Path = Path("/models/yolo.pt")
    grounded_root: Path = Path("/models/grounded")
    coordinator_executable_path: Path | None = None
    adaptive_wrapper_path: Path | None = None
    provenance_binding_path: Path | None = None
    environment: Mapping[str, str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_root", Path(self.evidence_root))
        object.__setattr__(self, "points_path", Path(self.points_path))
        object.__setattr__(self, "parallel_config_path", Path(self.parallel_config_path))
        object.__setattr__(self, "adaptive_config_path", Path(self.adaptive_config_path))
        object.__setattr__(self, "yolo_weights_path", Path(self.yolo_weights_path))
        object.__setattr__(self, "grounded_root", Path(self.grounded_root))
        if self.coordinator_executable_path is not None:
            object.__setattr__(
                self,
                "coordinator_executable_path",
                Path(self.coordinator_executable_path),
            )
        if self.provenance_binding_path is not None:
            object.__setattr__(
                self, "provenance_binding_path", Path(self.provenance_binding_path)
            )
        if self.environment is None:
            object.__setattr__(self, "environment", {})


@dataclass(frozen=True, slots=True)
class CampaignPreflightReceipt:
    receipt_id: str
    campaign_id: str
    service_session_id: str
    lease_generation: int
    manifest_id: str
    canonical_start_request_sha256: str
    execution_mode: str
    execution_config: FixedExecutionConfig | AdaptiveExecutionConfig
    point_count: int
    capacity: int
    source_commit: str | None
    install_prefix: str
    coordinator_executable_sha256: str
    adaptive_runner_module_sha256: str | None
    adaptive_pool_module_sha256: str | None
    adaptive_cleanup_executable_sha256: str | None
    adaptive_wrapper_sha256: str | None
    parallel_config_sha256: str
    adaptive_config_sha256: str | None
    catalog_sha256: str
    selection_sha256: str
    yolo_weights_sha256: str
    grounded_sam_manifest_sha256: str
    broker_image_id: str
    resource_manifest_sha256: str
    observed_at_ns: int
    expires_at_monotonic_ns: int
    admitted: bool
    reason_codes: tuple[str, ...]
    resource_observations: Mapping[str, object]
    #: The macOS routing key this receipt bound, resolved from the document's real bytes.
    execution_profile: str | None = None
    schema_version: int | None = None
    batch_kind: str | None = None


def canonical_start_request_sha256(request: CampaignStartRequest) -> str:
    document = {
        "campaign_id": request.campaign_id,
        "batch_id": request.batch_id,
        "manifest_id": request.manifest_id,
        "point_ids": request.selection.point_ids,
        "selection_sha256": request.selection.selection_sha256,
        "execution_mode": request.execution_mode,
        "worker_count": request.worker_count,
        "fallback_worker_counts": request.fallback_worker_counts,
        "initial_points_per_worker": request.initial_points_per_worker,
        "worker_start_timeout_s": request.worker_start_timeout_s,
        "max_infra_attempts_per_point": request.max_infra_attempts_per_point,
        "yolo_executor_count": request.yolo_executor_count,
        "service_session_id": request.service_session_id,
        "lease_generation": request.lease_generation,
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PreflightEngine:
    def __init__(
        self,
        resource_probe,
        *,
        singleton_probe=lambda: True,
        clock_ns=time.monotonic_ns,
        ttl_ns: int = 30_000_000_000,
        platform: str | None = None,
    ) -> None:
        self._resources = resource_probe
        self.resource_gate = getattr(resource_probe, "_resource_gate", None)
        self._singleton_probe = singleton_probe
        self._clock_ns = clock_ns
        self._ttl_ns = ttl_ns
        self._platform = platform
        self._documents: dict[tuple[str, str], ExecutionDocument] = {}

    def execution_document(self, path) -> ExecutionDocument | None:
        """Load the installed document this request executes, or ``None`` when there is none.

        The cache is keyed by the path *and* its current bytes, so a rewritten document is
        reloaded instead of being answered from the previous one.
        """

        if path is None:
            return None
        resolved = Path(path)
        try:
            digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError:
            return None
        key = (str(resolved), digest)
        document = self._documents.get(key)
        if document is None:
            document = describe_execution_document(resolved, platform=self._platform)
            self._documents.clear()
            self._documents[key] = document
        return document

    def _macos_key_reasons(self, request, profile: ExecutionProfile) -> list[str]:
        """The routing key must be named exactly; the point count never supplies it.

        The key is resolved against the shared closed matrix, so a v4 document claiming W1 and a
        v5 document claiming first-pass are refused here for the same reason the adapter refuses
        them: the combination is not in the table.
        """

        from so101_demo.parallel_batch.contracts import ContractError, resolve_execution_route

        if request.execution_mode == "ADAPTIVE":
            return [UNSUPPORTED_ON_MACOS]
        if request.execution_profile is None or request.batch_kind is None:
            return [EXECUTION_PROFILE_REQUIRED]
        try:
            resolve_execution_route(
                schema_version=profile.schema_version,
                execution_profile=request.execution_profile,
                batch_kind=request.batch_kind,
                worker_count=request.worker_count,
            )
        except ContractError:
            return [UNSUPPORTED_ON_MACOS]
        if (
            request.execution_mode != profile.execution_mode
            or request.worker_count != profile.worker_count
        ):
            return [UNSUPPORTED_ON_MACOS]
        return []

    def preflight(self, request: CampaignStartRequest) -> CampaignPreflightReceipt:
        reasons: list[str] = []
        point_count = len(request.selection.point_ids)
        if not 4 <= point_count <= 20:
            reasons.append("POINT_COUNT_RANGE")
        document: ExecutionDocument | None = None
        profile: ExecutionProfile | None = None
        try:
            document = self.execution_document(request.parallel_config_path)
        except PreflightRejected as error:
            reasons.append(str(error))
        except Exception:  # noqa: BLE001 - an unloadable document admits nothing
            reasons.append(CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION)
        if document is not None:
            profile = document.profile
            if document.config_sha256 != request.parallel_config_sha256:
                reasons.append(PARALLEL_CONFIG_HASH_MISMATCH)
            if profile is not None:
                reasons.extend(
                    reason for reason in self._macos_key_reasons(request, profile)
                    if reason not in reasons
                )
        if request.execution_mode in {"SEQUENTIAL", "PARALLEL"}:
            if request.execution_mode == "SEQUENTIAL" and request.worker_count != 1:
                reasons.append("SEQUENTIAL_WORKER_COUNT")
            if request.execution_mode == "PARALLEL" and request.worker_count not in FIXED_WORKER_COUNTS[1:]:
                reasons.append("PARALLEL_WORKER_COUNT")
            if request.max_points_per_worker is not None:
                # The legacy lifetime quota is never part of a version-two request.
                reasons.append("LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED")
            config = FixedExecutionConfig(request.execution_mode, request.worker_count)
            # The shared queue can lease every selected point, so capacity is the
            # selection size; it is no longer a per-worker quota product.
            capacity = point_count
            resource_admitted, resource_reasons, observations = self._resources.probe(
                request, config
            )
            if not resource_admitted:
                reasons.extend(reason for reason in resource_reasons if reason not in reasons)
        elif request.execution_mode == "ADAPTIVE":
            if request.max_points_per_worker is not None:
                reasons.append("ADAPTIVE_FIXED_FIELD")
            levels = (request.worker_count, *request.fallback_worker_counts)
            if (
                not 1 <= request.worker_count <= 16
                or any(not 1 <= level <= 16 for level in request.fallback_worker_counts)
                or any(next_level >= level for level, next_level in zip(levels, levels[1:]))
            ):
                reasons.append("ADAPTIVE_FALLBACK_TIERS")
            if _SHORT_BATCH.fullmatch(request.batch_id) is None:
                reasons.append("ADAPTIVE_BATCH_ID")
            config = AdaptiveExecutionConfig(
                preferred_worker_count=request.worker_count,
                fallback_worker_counts=tuple(request.fallback_worker_counts),
                initial_points_per_worker=request.initial_points_per_worker,
                worker_start_timeout_s=request.worker_start_timeout_s,
                max_infra_attempts_per_point=request.max_infra_attempts_per_point,
                yolo_executor_count=request.yolo_executor_count,
                adaptive_config_sha256=request.adaptive_config_sha256 or "",
            )
            capacity = point_count
            _, _, observations = self._resources.probe(request, config)
        else:
            reasons.append("EXECUTION_MODE")
            config = FixedExecutionConfig(request.execution_mode, request.worker_count, 1)
            capacity = request.worker_count
            observations = {}
        if not self._singleton_probe():
            reasons.append("EXECUTION_OWNER_EXISTS")
        for name in (
            "coordinator_executable_sha256",
            "parallel_config_sha256",
            "yolo_weights_sha256",
            "grounded_sam_manifest_sha256",
            "resource_manifest_sha256",
        ):
            if _SHA256.fullmatch(getattr(request, name)) is None:
                reasons.append(name.upper() + "_INVALID")
        observed = self._clock_ns()
        observations = dict(observations)
        if document is not None and profile is not None:
            # The receipt and the client both see the values the executing document declares,
            # not a caller's restatement of them.
            observations.update(
                execution_profile=profile.profile,
                execution_schema_version=document.schema_version,
                execution_batch_kind=profile.batch_kind,
                execution_config_sha256=document.config_sha256,
                execution_worker_count=profile.worker_count,
                platform=profile.platform,
            )
        return CampaignPreflightReceipt(
            receipt_id="preflight-" + uuid.uuid4().hex,
            campaign_id=request.campaign_id,
            service_session_id=request.service_session_id,
            lease_generation=request.lease_generation,
            manifest_id=request.manifest_id,
            canonical_start_request_sha256=canonical_start_request_sha256(request),
            execution_mode=request.execution_mode,
            execution_config=config,
            point_count=point_count,
            capacity=capacity,
            source_commit=request.source_commit,
            install_prefix=request.install_prefix,
            coordinator_executable_sha256=request.coordinator_executable_sha256,
            adaptive_runner_module_sha256=request.adaptive_runner_module_sha256,
            adaptive_pool_module_sha256=request.adaptive_pool_module_sha256,
            adaptive_cleanup_executable_sha256=request.adaptive_cleanup_executable_sha256,
            adaptive_wrapper_sha256=request.adaptive_wrapper_sha256,
            parallel_config_sha256=(
                document.config_sha256 if document is not None
                else request.parallel_config_sha256
            ),
            adaptive_config_sha256=request.adaptive_config_sha256,
            catalog_sha256=request.selection.catalog_sha256,
            selection_sha256=request.selection.selection_sha256,
            yolo_weights_sha256=request.yolo_weights_sha256,
            grounded_sam_manifest_sha256=request.grounded_sam_manifest_sha256,
            broker_image_id=request.broker_image_id,
            resource_manifest_sha256=request.resource_manifest_sha256,
            observed_at_ns=observed,
            expires_at_monotonic_ns=observed + self._ttl_ns,
            admitted=not reasons,
            reason_codes=tuple(reasons),
            resource_observations=observations,
            execution_profile=None if profile is None else profile.profile,
            schema_version=None if profile is None else document.schema_version,
            batch_kind=None if profile is None else profile.batch_kind,
        )

    def require_admitted(self, request: CampaignStartRequest) -> CampaignPreflightReceipt:
        receipt = self.preflight(request)
        if not receipt.admitted:
            raise PreflightRejected(",".join(receipt.reason_codes))
        return receipt
