"""Immutable records persisted by the expert-validation supervisor store."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{name.upper()}_INVALID")
    return value


def _sha(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name.upper()}_INVALID")
    return value


def _absolute(name: str, value: Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or path != path.resolve(strict=False):
        raise ValueError(f"{name.upper()}_ABSOLUTE_NORMALIZED")
    return path


@dataclass(frozen=True, slots=True)
class PreflightReceipt:
    receipt_id: str
    campaign_id: str
    manifest_id: str
    canonical_start_request_sha256: str
    receipt: Mapping
    expires_at_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in ("receipt_id", "campaign_id", "manifest_id"):
            _identifier(name, getattr(self, name))
        _sha("canonical_start_request_sha256", self.canonical_start_request_sha256)
        if not isinstance(self.receipt, Mapping):
            raise ValueError("PREFLIGHT_RECEIPT_MAPPING")
        if type(self.expires_at_monotonic_ns) is not int or self.expires_at_monotonic_ns <= 0:
            raise ValueError("PREFLIGHT_EXPIRY")


@dataclass(frozen=True, slots=True)
class CampaignBinding:
    campaign_id: str
    manifest_id: str
    executor_id: str
    operation_id: str
    executor_config_sha256: str
    execution_mode: str
    execution_config: Mapping
    preflight_receipt_id: str

    def __post_init__(self) -> None:
        for name in (
            "campaign_id",
            "manifest_id",
            "executor_id",
            "operation_id",
            "preflight_receipt_id",
        ):
            _identifier(name, getattr(self, name))
        _sha("executor_config_sha256", self.executor_config_sha256)
        if self.execution_mode not in {"SEQUENTIAL", "PARALLEL", "ADAPTIVE"}:
            raise ValueError("EXECUTION_MODE")
        if not isinstance(self.execution_config, Mapping):
            raise ValueError("EXECUTION_CONFIG_MAPPING")
        # Version two fixed execution has no lifetime quota; retained v1 rows may still
        # carry the historical key and must keep validating for read-only projection.
        fixed_fields = {"worker_count"}
        adaptive_fields = {
            "preferred_worker_count",
            "fallback_worker_counts",
            "initial_points_per_worker",
            "worker_start_timeout_s",
            "max_infra_attempts_per_point",
            "adaptive_config_sha256",
        }
        keys = set(self.execution_config)
        if self.execution_mode == "ADAPTIVE":
            if fixed_fields & keys:
                raise ValueError("EXECUTION_CONFIG_MODE_MIX")
        elif adaptive_fields & keys:
            raise ValueError("EXECUTION_CONFIG_MODE_MIX")


@dataclass(frozen=True, slots=True)
class BatchBinding:
    batch_id: str
    campaign_id: str
    batch_kind: str
    point_id: str | None
    journal_root: Path
    coordinator_epoch: int | None = None
    pool_generation: int | None = None
    state: str = "BOUND"
    terminal_summary_sha256: str | None = None
    cleanup_receipt_sha256: str | None = None

    def __post_init__(self) -> None:
        _identifier("batch_id", self.batch_id)
        _identifier("campaign_id", self.campaign_id)
        if self.batch_kind not in {"FIRST_PASS", "FULL_RESTART_RETRY"}:
            raise ValueError("BATCH_KIND")
        if self.batch_kind == "FULL_RESTART_RETRY" and self.point_id is None:
            raise ValueError("RETRY_POINT_REQUIRED")
        if self.point_id is not None:
            _identifier("point_id", self.point_id)
        object.__setattr__(self, "journal_root", _absolute("journal_root", self.journal_root))


@dataclass(frozen=True, slots=True)
class ExecutionOwnerIntent:
    batch_id: str
    owner_kind: str
    spawn_token: str
    expected_executable: str
    argv_sha256: str
    environment_sha256: str
    source_commit: str | None
    install_prefix: Path
    runtime_sha256: str
    control_socket: Path | None = None

    def __post_init__(self) -> None:
        _identifier("batch_id", self.batch_id)
        if self.owner_kind not in {"COORDINATOR", "ADAPTIVE_WRAPPER"}:
            raise ValueError("OWNER_KIND")
        _identifier("spawn_token", self.spawn_token)
        if not self.expected_executable:
            raise ValueError("EXPECTED_EXECUTABLE")
        for name in ("argv_sha256", "environment_sha256", "runtime_sha256"):
            _sha(name, getattr(self, name))
        # Debug metadata only: any string (including an unknown marker) or None is
        # acceptable, so a deployment without Git can still record its ownership intent.
        if self.source_commit is not None and type(self.source_commit) is not str:
            raise ValueError("SOURCE_COMMIT")
        object.__setattr__(self, "install_prefix", Path(self.install_prefix))
        if self.control_socket is not None:
            object.__setattr__(
                self, "control_socket", _absolute("control_socket", self.control_socket)
            )


@dataclass(frozen=True, slots=True)
class OwnedExecutionRecord:
    batch_id: str
    owner_kind: str
    state: str
    spawn_token: str
    expected_executable: str
    argv_sha256: str
    environment_sha256: str
    source_commit: str | None
    install_prefix: Path
    runtime_sha256: str
    pid: int | None
    pgid: int | None
    started_ticks: int | None
    control_socket: Path | None
    coordinator_epoch: int | None
    runner_pid: int | None
    runner_journal_root: Path | None
    acknowledged_at_ns: int | None


@dataclass(frozen=True, slots=True)
class UpstreamCursor:
    batch_id: str
    owner_kind: str
    owner_epoch_or_generation: int
    segment_id: str
    event_id: str
    frame_sha256: str

    def __post_init__(self) -> None:
        for name in ("batch_id", "segment_id", "event_id"):
            _identifier(name, getattr(self, name))
        if self.owner_kind not in {"COORDINATOR", "ADAPTIVE_RUNNER"}:
            raise ValueError("CURSOR_OWNER_KIND")
        if type(self.owner_epoch_or_generation) is not int or self.owner_epoch_or_generation <= 0:
            raise ValueError("CURSOR_OWNER_GENERATION")
        _sha("frame_sha256", self.frame_sha256)


@dataclass(frozen=True, slots=True)
class RetryItem:
    campaign_id: str
    ordinal: int
    point_id: str
    state: str
    batch_id: str | None


@dataclass(frozen=True, slots=True)
class CleanupReceipt:
    campaign_id: str
    batch_id: str
    point_id: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        for name in ("campaign_id", "batch_id", "point_id"):
            _identifier(name, getattr(self, name))
        _sha("receipt_sha256", self.receipt_sha256)


@dataclass(frozen=True, slots=True)
class RetryStartRequest:
    """One admitted retry: an existing committed business ``FAILED`` point, and nothing else.

    The request carries only coordinates. The authority to execute it comes from the one-time
    execution context that is consumed together with it (design section 10).
    """

    command_id: str
    campaign_id: str
    batch_id: str
    point_id: str
    original_batch_id: str
    original_catalog_sha256: str
    original_selection_sha256: str
    original_result_sha256: str
    execution_profile: str
    schema_version: int
    batch_kind: str
    config_sha256: str
    runtime_closure_sha256: str
    worker_count: int
    evidence_root: Path
    install_prefix: Path
    owner_generation: int
    created_at_ns: int

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "campaign_id",
            "batch_id",
            "point_id",
            "original_batch_id",
            "execution_profile",
        ):
            _identifier(name, getattr(self, name))
        for name in (
            "original_catalog_sha256",
            "original_selection_sha256",
            "original_result_sha256",
            "config_sha256",
            "runtime_closure_sha256",
        ):
            _sha(name, getattr(self, name))
        if self.batch_kind != "FULL_RESTART_RETRY":
            raise ValueError("RETRY_BATCH_KIND")
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise ValueError("RETRY_SCHEMA_VERSION")
        if self.worker_count != 1:
            raise ValueError("RETRY_WORKER_COUNT")
        if type(self.owner_generation) is not int or self.owner_generation < 1:
            raise ValueError("RETRY_OWNER_GENERATION")
        object.__setattr__(self, "evidence_root", _absolute("evidence_root", self.evidence_root))
        object.__setattr__(self, "install_prefix", _absolute("install_prefix", self.install_prefix))

    def as_document(self) -> dict[str, object]:
        return {
            "command_id": self.command_id,
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "point_id": self.point_id,
            "original_batch_id": self.original_batch_id,
            "original_catalog_sha256": self.original_catalog_sha256,
            "original_selection_sha256": self.original_selection_sha256,
            "original_result_sha256": self.original_result_sha256,
            "execution_profile": self.execution_profile,
            "schema_version": self.schema_version,
            "batch_kind": self.batch_kind,
            "config_sha256": self.config_sha256,
            "runtime_closure_sha256": self.runtime_closure_sha256,
            "worker_count": self.worker_count,
            "evidence_root": str(self.evidence_root),
            "install_prefix": str(self.install_prefix),
            "owner_generation": self.owner_generation,
        }


@dataclass(frozen=True, slots=True)
class RetrySelectionBinding:
    """The immutable retry selection the store commits: one point of one original first pass."""

    command_id: str
    campaign_id: str
    batch_id: str
    point_id: str
    original_batch_id: str
    original_catalog_sha256: str
    original_selection_sha256: str
    original_result_sha256: str
    original_outcome: str
    execution_profile: str
    schema_version: int
    config_sha256: str
    runtime_closure_sha256: str
    worker_count: int
    evidence_root: Path
    owner_generation: int
    context_kind: str
    spawn_token: str
    lease_id: str | None = None
    lease_generation: int | None = None
    binding_sha256: str = ""

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "campaign_id",
            "batch_id",
            "point_id",
            "original_batch_id",
            "execution_profile",
            "spawn_token",
        ):
            _identifier(name, getattr(self, name))
        for name in (
            "original_catalog_sha256",
            "original_selection_sha256",
            "original_result_sha256",
            "config_sha256",
            "runtime_closure_sha256",
        ):
            _sha(name, getattr(self, name))
        object.__setattr__(self, "evidence_root", _absolute("evidence_root", self.evidence_root))
        # The binding is the retry of a *business* failure; nothing else may construct one.
        if self.original_outcome != "FAILED":
            raise ValueError("RETRY_ORIGINAL_NOT_FAILED")
        if self.context_kind not in {"CANDIDATE", "PRODUCTION"}:
            raise ValueError("RETRY_CONTEXT_KIND")
        if self.context_kind == "PRODUCTION" and (
            self.lease_id is None or self.lease_generation is None
        ):
            raise ValueError("RETRY_LEASE_BINDING_REQUIRED")
        digest = self.compute_sha256()
        if self.binding_sha256 and self.binding_sha256 != digest:
            raise ValueError("RETRY_BINDING_HASH_MISMATCH")
        object.__setattr__(self, "binding_sha256", digest)

    def as_document(self) -> dict[str, object]:
        return {
            "kind": "FULL_RESTART_RETRY",
            "command_id": self.command_id,
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "point_id": self.point_id,
            "original_batch_id": self.original_batch_id,
            "original_catalog_sha256": self.original_catalog_sha256,
            "original_selection_sha256": self.original_selection_sha256,
            "original_result_sha256": self.original_result_sha256,
            "original_outcome": self.original_outcome,
            "execution_profile": self.execution_profile,
            "schema_version": self.schema_version,
            "config_sha256": self.config_sha256,
            "runtime_closure_sha256": self.runtime_closure_sha256,
            "worker_count": self.worker_count,
            "evidence_root": str(self.evidence_root),
            "owner_generation": self.owner_generation,
            "context_kind": self.context_kind,
            "spawn_token": self.spawn_token,
            "lease_id": self.lease_id,
            "lease_generation": self.lease_generation,
        }

    def compute_sha256(self) -> str:
        body = {
            key: value
            for key, value in self.as_document().items()
            if key not in {"binding_sha256"}
        }
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ValidationManifest:
    manifest_id: str
    canonical_document: Mapping
    manifest_sha256: str
    source_config_sha256: str
    created_at_ns: int
    stale: bool = False

    def __post_init__(self) -> None:
        _identifier("manifest_id", self.manifest_id)
        _sha("manifest_sha256", self.manifest_sha256)
        _sha("source_config_sha256", self.source_config_sha256)
        if not isinstance(self.canonical_document, Mapping):
            raise ValueError("MANIFEST_DOCUMENT")
