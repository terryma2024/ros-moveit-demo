"""Strict contracts for the isolated adaptive worker pool through W16."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
from pathlib import Path
import yaml

from .contracts import (
    ContractError,
    PointStatus,
    RunMode,
    _require_absolute_path,
    _require_enum,
    _require_finite,
    _require_id,
    _require_positive_int,
)


_MAX_ADAPTIVE_WORKER_COUNT = 16
_MAX_POINT_COUNT = 20
_MAX_ROS_DOMAIN_ID = 232
_POOL_REQUEST_FACTORY_TOKEN = object()
_FROZEN_ADAPTIVE_VALUES = {
    "schema_version": 1,
    "backend": "mujoco",
    "worker_count": 8,
    "fallback_worker_counts": (6, 4, 2, 1),
    "initial_points_per_worker": 3,
    "worker_start_timeout_s": 120.0,
    "max_infra_attempts_per_point": 5,
    "ros_domain_ids": tuple(range(215, 231)),
    "yolo_executor_count": 2,
}


class BatchTerminalStatus(StrEnum):
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_FAILURES = "COMPLETED_WITH_FAILURES"
    INFRA_FAILED = "INFRA_FAILED"


class InfrastructureFailureKind(StrEnum):
    STARTUP = "STARTUP"
    PROCESS_EXIT = "PROCESS_EXIT"
    ROS_DISCONNECTED = "ROS_DISCONNECTED"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    OOM = "OOM"
    RECOVERY = "RECOVERY"
    CLEANUP = "CLEANUP"
    COORDINATOR = "COORDINATOR"


def _require_short_batch_id(value: object) -> str:
    batch_id = _require_id("batch_id", value)
    if not batch_id.isascii() or not 1 <= len(batch_id) <= 5:
        raise ContractError("BATCH_ID_LENGTH")
    return batch_id


def _require_point_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractError("POINT_ID_SEQUENCE")
    point_ids = tuple(_require_id("point_id", item) for item in value)
    if not point_ids or len(point_ids) > _MAX_POINT_COUNT:
        raise ContractError("POINT_ID_COUNT")
    if len(point_ids) != len(set(point_ids)):
        raise ContractError("UNIQUE_POINT_IDS")
    return point_ids


def _require_domain_ids(value: object, worker_count: int) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractError("ROS_DOMAIN_IDS")
    domains: list[int] = []
    for domain_id in value:
        if isinstance(domain_id, bool) or not isinstance(domain_id, int):
            raise ContractError("ROS_DOMAIN_IDS")
        if not 0 <= domain_id <= _MAX_ROS_DOMAIN_ID:
            raise ContractError("ROS_DOMAIN_IDS")
        domains.append(domain_id)
    if len(domains) < worker_count or len(domains) != len(set(domains)):
        raise ContractError("ROS_DOMAIN_IDS")
    return tuple(domains)


@dataclass(frozen=True, slots=True)
class AdaptiveWorkerOptions:
    worker_count: int
    fallback_worker_counts: tuple[int, ...]
    initial_points_per_worker: int
    worker_start_timeout_s: float
    max_infra_attempts_per_point: int
    ros_domain_ids: tuple[int, ...]
    yolo_executor_count: int = 2

    def __post_init__(self) -> None:
        worker_count = _require_positive_int("worker_count", self.worker_count)
        if worker_count > _MAX_ADAPTIVE_WORKER_COUNT:
            raise ContractError("MAX_WORKER_COUNT")
        if not isinstance(self.fallback_worker_counts, (list, tuple)):
            raise ContractError("FALLBACK_WORKER_COUNTS")
        fallbacks = tuple(
            _require_positive_int("fallback_worker_count", count)
            for count in self.fallback_worker_counts
        )
        if any(count > _MAX_ADAPTIVE_WORKER_COUNT for count in fallbacks) or any(
            next_count >= current_count
            for current_count, next_count in zip((worker_count, *fallbacks), fallbacks)
        ):
            raise ContractError("FALLBACK_WORKER_COUNTS")
        object.__setattr__(self, "worker_count", worker_count)
        object.__setattr__(self, "fallback_worker_counts", fallbacks)
        object.__setattr__(
            self,
            "initial_points_per_worker",
            _require_positive_int("initial_points_per_worker", self.initial_points_per_worker),
        )
        object.__setattr__(
            self,
            "worker_start_timeout_s",
            _require_finite(
                "worker_start_timeout_s", self.worker_start_timeout_s, minimum=0.000001
            ),
        )
        object.__setattr__(
            self,
            "max_infra_attempts_per_point",
            _require_positive_int(
                "max_infra_attempts_per_point", self.max_infra_attempts_per_point
            ),
        )
        object.__setattr__(
            self, "ros_domain_ids", _require_domain_ids(self.ros_domain_ids, worker_count)
        )
        if (
            type(self.yolo_executor_count) is not int
            or self.yolo_executor_count not in {1, 2, 4}
        ):
            raise ContractError("YOLO_EXECUTOR_COUNT")

    @property
    def levels(self) -> tuple[int, ...]:
        return (self.worker_count, *self.fallback_worker_counts)


@dataclass(frozen=True, slots=True)
class AdaptiveBatchRequest:
    batch_id: str
    run_mode: RunMode
    selected_point_ids: tuple[str, ...]
    options: AdaptiveWorkerOptions
    evidence_root: Path
    # The start guard this run prepared.  The adaptive pool allocates through the same guard as
    # the fixed-N path: without it every level is refused by design (START_GUARD_UNAVAILABLE).
    start_guard: object | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "batch_id", _require_short_batch_id(self.batch_id))
        _require_enum("run_mode", self.run_mode, RunMode)
        object.__setattr__(self, "selected_point_ids", _require_point_ids(self.selected_point_ids))
        if not isinstance(self.options, AdaptiveWorkerOptions):
            raise ContractError("ADAPTIVE_WORKER_OPTIONS")
        object.__setattr__(
            self, "evidence_root", _require_absolute_path("evidence_root", self.evidence_root)
        )

    @property
    def point_count(self) -> int:
        return len(self.selected_point_ids)

    @property
    def runtime_root(self) -> Path:
        return self.evidence_root / "r" / self.batch_id


@dataclass(frozen=True, slots=True, init=False)
class PoolRequest:
    """Internal one-generation request; never accepted directly from legacy CLI."""

    batch_id: str
    run_mode: RunMode
    selected_point_ids: tuple[str, ...]
    worker_count: int
    evidence_root: Path
    start_guard: object | None

    def __init__(
        self,
        batch_id: str,
        run_mode: RunMode,
        selected_point_ids: tuple[str, ...],
        worker_count: int,
        evidence_root: Path,
        start_guard: object | None = None,
        *,
        _factory_token: object,
    ) -> None:
        if _factory_token is not _POOL_REQUEST_FACTORY_TOKEN:
            raise ContractError("POOL_REQUEST_FACTORY_ONLY")
        object.__setattr__(self, "batch_id", _require_id("batch_id", batch_id))
        _require_enum("run_mode", run_mode, RunMode)
        object.__setattr__(self, "run_mode", run_mode)
        object.__setattr__(self, "selected_point_ids", _require_point_ids(selected_point_ids))
        validated_count = _require_positive_int("worker_count", worker_count)
        if validated_count > _MAX_ADAPTIVE_WORKER_COUNT:
            raise ContractError("MAX_WORKER_COUNT")
        object.__setattr__(self, "worker_count", validated_count)
        object.__setattr__(
            self, "evidence_root", _require_absolute_path("evidence_root", evidence_root)
        )
        object.__setattr__(self, "start_guard", start_guard)


def _new_pool_request_for_production_factory(
    *,
    batch_id: str,
    run_mode: RunMode,
    selected_point_ids: tuple[str, ...],
    worker_count: int,
    evidence_root: Path,
    start_guard: object | None = None,
) -> PoolRequest:
    """Construct a pool request for ``ProductionAdaptivePoolFactory`` only.

    The request carries no lifetime point quota; affinity, fallback tiers and
    infrastructure-attempt limits remain the unchanged adaptive authority.
    """

    return PoolRequest(
        batch_id,
        run_mode,
        selected_point_ids,
        worker_count,
        evidence_root,
        start_guard,
        _factory_token=_POOL_REQUEST_FACTORY_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class InfrastructureFailure:
    kind: InfrastructureFailureKind
    generation: int
    worker_count: int
    detail: str

    def __post_init__(self) -> None:
        _require_enum("kind", self.kind, InfrastructureFailureKind)
        object.__setattr__(self, "generation", _require_positive_int("generation", self.generation))
        worker_count = _require_positive_int("worker_count", self.worker_count)
        if worker_count > _MAX_ADAPTIVE_WORKER_COUNT:
            raise ContractError("MAX_WORKER_COUNT")
        object.__setattr__(self, "worker_count", worker_count)
        if not isinstance(self.detail, str) or not self.detail:
            raise ContractError("INFRASTRUCTURE_FAILURE_DETAIL")


@dataclass(frozen=True, slots=True)
class FallbackTransition:
    generation: int
    from_count: int
    to_count: int
    failure: InfrastructureFailure

    def __post_init__(self) -> None:
        object.__setattr__(self, "generation", _require_positive_int("generation", self.generation))
        from_count = _require_positive_int("from_count", self.from_count)
        to_count = _require_positive_int("to_count", self.to_count)
        if from_count > _MAX_ADAPTIVE_WORKER_COUNT or to_count >= from_count:
            raise ContractError("FALLBACK_TRANSITION")
        if not isinstance(self.failure, InfrastructureFailure):
            raise ContractError("INFRASTRUCTURE_FAILURE")
        object.__setattr__(self, "from_count", from_count)
        object.__setattr__(self, "to_count", to_count)


@dataclass(frozen=True, slots=True)
class CommittedPointResult:
    point_id: str
    status: PointStatus
    evidence_root: Path
    infra_attempts: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "point_id", _require_id("point_id", self.point_id))
        _require_enum("point_status", self.status, PointStatus)
        if self.status not in {PointStatus.PASSED, PointStatus.FAILED}:
            raise ContractError("TERMINAL_POINT_STATUS")
        object.__setattr__(
            self, "evidence_root", _require_absolute_path("evidence_root", self.evidence_root)
        )
        if isinstance(self.infra_attempts, bool) or not isinstance(self.infra_attempts, int):
            raise ContractError("INFRA_ATTEMPTS")
        if self.infra_attempts < 0:
            raise ContractError("INFRA_ATTEMPTS")


def _require_results(value: object) -> tuple[CommittedPointResult, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractError("COMMITTED_POINT_RESULTS")
    results = tuple(value)
    if any(not isinstance(result, CommittedPointResult) for result in results):
        raise ContractError("COMMITTED_POINT_RESULTS")
    if len({result.point_id for result in results}) != len(results):
        raise ContractError("UNIQUE_POINT_RESULTS")
    return results


@dataclass(frozen=True, slots=True)
class PoolExecutionResult:
    terminal_results: tuple[CommittedPointResult, ...]
    interrupted_point_ids: tuple[str, ...]
    infrastructure_failure: InfrastructureFailure | None
    cleanup_complete: bool
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "terminal_results", _require_results(self.terminal_results))
        interrupted = _require_point_ids(self.interrupted_point_ids) if self.interrupted_point_ids else ()
        terminal_ids = {result.point_id for result in self.terminal_results}
        if terminal_ids.intersection(interrupted):
            raise ContractError("OVERLAPPING_POINT_RESULTS")
        object.__setattr__(self, "interrupted_point_ids", interrupted)
        if self.infrastructure_failure is not None and not isinstance(
            self.infrastructure_failure, InfrastructureFailure
        ):
            raise ContractError("INFRASTRUCTURE_FAILURE")
        if not isinstance(self.cleanup_complete, bool):
            raise ContractError("BOOLEAN: cleanup_complete")
        if not isinstance(self.diagnostics, (list, tuple)) or any(
            not isinstance(item, str) for item in self.diagnostics
        ):
            raise ContractError("DIAGNOSTICS")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


@dataclass(frozen=True, slots=True)
class AdaptiveBatchSummary:
    status: BatchTerminalStatus
    initial_worker_count: int
    final_worker_count: int
    levels_used: tuple[int, ...]
    point_results: tuple[CommittedPointResult, ...]
    transitions: tuple[FallbackTransition, ...]
    cleanup_complete: bool

    def __post_init__(self) -> None:
        _require_enum("status", self.status, BatchTerminalStatus)
        for name in ("initial_worker_count", "final_worker_count"):
            value = _require_positive_int(name, getattr(self, name))
            if value > _MAX_ADAPTIVE_WORKER_COUNT:
                raise ContractError("MAX_WORKER_COUNT")
            object.__setattr__(self, name, value)
        if not isinstance(self.levels_used, (list, tuple)) or not self.levels_used:
            raise ContractError("LEVELS_USED")
        levels = tuple(_require_positive_int("worker_count", level) for level in self.levels_used)
        if any(level > _MAX_ADAPTIVE_WORKER_COUNT for level in levels) or any(
            next_level >= level for level, next_level in zip(levels, levels[1:])
        ):
            raise ContractError("LEVELS_USED")
        object.__setattr__(self, "levels_used", levels)
        object.__setattr__(self, "point_results", _require_results(self.point_results))
        if not isinstance(self.transitions, (list, tuple)) or any(
            not isinstance(item, FallbackTransition) for item in self.transitions
        ):
            raise ContractError("FALLBACK_TRANSITIONS")
        object.__setattr__(self, "transitions", tuple(self.transitions))
        if not isinstance(self.cleanup_complete, bool):
            raise ContractError("BOOLEAN: cleanup_complete")


def load_adaptive_worker_options(path: Path) -> AdaptiveWorkerOptions:
    """Load the closed version-one adaptive-worker configuration."""

    config_path = _require_absolute_path("adaptive_config", path)
    try:
        document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ContractError(f"CONFIG_READ_FAILED: {path}") from error
    except yaml.YAMLError as error:
        raise ContractError(f"CONFIG_YAML_INVALID: {path}") from error
    if not isinstance(document, dict):
        raise ContractError("CONFIG_MAPPING")
    expected = {"schema_version", "backend"} | {
        item.name for item in fields(AdaptiveWorkerOptions)
    }
    actual = set(document)
    unknown = actual - expected
    missing = expected - actual
    if unknown:
        raise ContractError(f"UNKNOWN_CONFIG_FIELD: {sorted(unknown)!r}")
    if missing:
        raise ContractError(f"MISSING_CONFIG_FIELD: {sorted(missing)!r}")
    schema_version = document["schema_version"]
    if isinstance(schema_version, bool) or schema_version != 1:
        raise ContractError("SCHEMA_VERSION")
    if document["backend"] != "mujoco":
        raise ContractError("BACKEND")
    options = AdaptiveWorkerOptions(
        worker_count=document["worker_count"],
        fallback_worker_counts=document["fallback_worker_counts"],
        initial_points_per_worker=document["initial_points_per_worker"],
        worker_start_timeout_s=document["worker_start_timeout_s"],
        max_infra_attempts_per_point=document["max_infra_attempts_per_point"],
        ros_domain_ids=document["ros_domain_ids"],
        yolo_executor_count=document["yolo_executor_count"],
    )
    values = {
        "schema_version": schema_version,
        "backend": document["backend"],
        "worker_count": options.worker_count,
        "fallback_worker_counts": options.fallback_worker_counts,
        "initial_points_per_worker": options.initial_points_per_worker,
        "worker_start_timeout_s": options.worker_start_timeout_s,
        "max_infra_attempts_per_point": options.max_infra_attempts_per_point,
        "ros_domain_ids": options.ros_domain_ids,
        "yolo_executor_count": options.yolo_executor_count,
    }
    for name, expected_value in _FROZEN_ADAPTIVE_VALUES.items():
        if values[name] != expected_value:
            raise ContractError(f"FROZEN_ADAPTIVE_VALUE: {name}")
    return options
