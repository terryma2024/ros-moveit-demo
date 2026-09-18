"""Closed admission contract for expert-validation campaigns."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Mapping
import uuid

from .catalog import PointSelection


FIXED_WORKER_COUNTS = tuple(range(1, 9))


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHORT_BATCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,4}$", re.ASCII)


class PreflightRejected(RuntimeError):
    """A campaign cannot be admitted without changing its requested mode."""


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
    source_commit: str
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
    source_commit: str
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
    ) -> None:
        self._resources = resource_probe
        self._singleton_probe = singleton_probe
        self._clock_ns = clock_ns
        self._ttl_ns = ttl_ns

    def preflight(self, request: CampaignStartRequest) -> CampaignPreflightReceipt:
        reasons: list[str] = []
        point_count = len(request.selection.point_ids)
        if not 4 <= point_count <= 20:
            reasons.append("POINT_COUNT_RANGE")
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
            parallel_config_sha256=request.parallel_config_sha256,
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
            resource_observations=dict(observations),
        )

    def require_admitted(self, request: CampaignStartRequest) -> CampaignPreflightReceipt:
        receipt = self.preflight(request)
        if not receipt.admitted:
            raise PreflightRejected(",".join(receipt.reason_codes))
        return receipt
