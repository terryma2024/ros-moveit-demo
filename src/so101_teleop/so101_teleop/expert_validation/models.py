"""Immutable records persisted by the expert-validation supervisor store."""

from __future__ import annotations

from dataclasses import dataclass
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
        fixed_fields = {"worker_count", "max_points_per_worker"}
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
    source_commit: str
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
        if not re.fullmatch(r"[0-9a-f]{40}", self.source_commit) and self.source_commit != "UNKNOWN":
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
    source_commit: str
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
