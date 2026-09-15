"""Fail-closed read-only statistics for fixed and adaptive validation runs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from parallel_batch.adaptive_contracts import AdaptiveBatchSummary, BatchTerminalStatus
from parallel_batch.contracts import BatchSummary, PointStatus


class StatisticsProjectionError(ValueError):
    """An accepted event projection disagrees with an upstream summary."""


def _point_status(value: PointStatus | str) -> PointStatus:
    try:
        return value if isinstance(value, PointStatus) else PointStatus(value)
    except (TypeError, ValueError) as error:
        raise StatisticsProjectionError("POINT_STATUS_INVALID") from error


def _unique_by_id(values, *, error: str):
    result = tuple(values)
    identifiers = [value.point_id for value in result]
    if len(identifiers) != len(set(identifiers)):
        raise StatisticsProjectionError(error)
    return result


@dataclass(frozen=True, slots=True)
class AttemptProjection:
    generation: int
    status: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.generation, bool) or self.generation <= 0:
            raise StatisticsProjectionError("ATTEMPT_GENERATION_INVALID")
        if not isinstance(self.status, str) or not self.status:
            raise StatisticsProjectionError("ATTEMPT_STATUS_INVALID")
        if self.reason is not None and (not isinstance(self.reason, str) or not self.reason):
            raise StatisticsProjectionError("ATTEMPT_REASON_INVALID")


@dataclass(frozen=True, slots=True)
class PointProjection:
    point_id: str
    status: PointStatus | str
    evaluated: bool
    execution_started: bool
    active_worker_id: str | None = None
    invalid_attempts: int = 0
    retry_eligible: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.point_id, str) or not self.point_id:
            raise StatisticsProjectionError("POINT_ID_INVALID")
        object.__setattr__(self, "status", _point_status(self.status))
        if not isinstance(self.evaluated, bool) or not isinstance(self.execution_started, bool):
            raise StatisticsProjectionError("POINT_BOOLEAN_INVALID")
        if self.active_worker_id is not None and (
            not isinstance(self.active_worker_id, str) or not self.active_worker_id
        ):
            raise StatisticsProjectionError("ACTIVE_WORKER_INVALID")
        if (
            isinstance(self.invalid_attempts, bool)
            or not isinstance(self.invalid_attempts, int)
            or self.invalid_attempts < 0
        ):
            raise StatisticsProjectionError("INVALID_ATTEMPT_COUNT")
        if self.reason is not None and (not isinstance(self.reason, str) or not self.reason):
            raise StatisticsProjectionError("POINT_REASON_INVALID")


@dataclass(frozen=True, slots=True)
class AdaptivePointProjection:
    point_id: str
    status: PointStatus | str
    attempts: tuple[AttemptProjection, ...] = ()
    active_worker_id: str | None = None
    retry_eligible: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.point_id, str) or not self.point_id:
            raise StatisticsProjectionError("POINT_ID_INVALID")
        object.__setattr__(self, "status", _point_status(self.status))
        attempts = tuple(self.attempts)
        if any(not isinstance(attempt, AttemptProjection) for attempt in attempts):
            raise StatisticsProjectionError("ATTEMPT_PROJECTION_INVALID")
        if len({attempt.generation for attempt in attempts}) != len(attempts):
            raise StatisticsProjectionError("ATTEMPT_GENERATION_DUPLICATE")
        object.__setattr__(self, "attempts", attempts)
        if self.active_worker_id is not None and (
            not isinstance(self.active_worker_id, str) or not self.active_worker_id
        ):
            raise StatisticsProjectionError("ACTIVE_WORKER_INVALID")


@dataclass(frozen=True, slots=True)
class WorkerProjection:
    worker_id: str
    generation: int
    state: str
    active_point_id: str | None = None
    lease_count: int = 0
    quarantine_reason: str | None = None
    recovery_result: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.worker_id, str) or not self.worker_id:
            raise StatisticsProjectionError("WORKER_ID_INVALID")
        if isinstance(self.generation, bool) or self.generation <= 0:
            raise StatisticsProjectionError("WORKER_GENERATION_INVALID")
        if not isinstance(self.state, str) or not self.state:
            raise StatisticsProjectionError("WORKER_STATE_INVALID")
        if isinstance(self.lease_count, bool) or self.lease_count < 0:
            raise StatisticsProjectionError("WORKER_LEASE_COUNT_INVALID")


@dataclass(frozen=True, slots=True)
class BrokerProjection:
    available: bool = True
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool):
            raise StatisticsProjectionError("BROKER_AVAILABILITY_INVALID")
        if self.reason is not None and (not isinstance(self.reason, str) or not self.reason):
            raise StatisticsProjectionError("BROKER_REASON_INVALID")


@dataclass(frozen=True, slots=True)
class FixedFirstPassStatistics:
    requested: int
    evaluated: int
    execution_started: int
    valid_succeeded: int
    valid_failed: int
    indeterminate: int
    invalid_attempts: int
    not_executed: int
    evaluation_coverage: float
    execution_coverage: float
    qualified_success_rate: float | None
    coverage_complete: bool
    execution_complete: bool
    batch_cleanup_complete: bool
    qualification_passed: bool
    points: tuple[PointProjection, ...]
    workers: tuple[WorkerProjection, ...]
    broker: BrokerProjection


@dataclass(frozen=True, slots=True)
class AdaptiveFirstPassStatistics:
    status: str
    initial_worker_count: int
    final_worker_count: int
    levels_used: tuple[int, ...]
    batch_cleanup_complete: bool
    valid_succeeded: int
    valid_failed: int
    indeterminate: int
    not_executed: int
    infra_attempts: int
    points: tuple[AdaptivePointProjection, ...]
    workers: tuple[WorkerProjection, ...]
    broker: BrokerProjection
    transitions: tuple


def summarize_first_pass(
    batch_summary: BatchSummary,
    points: Iterable[PointProjection],
    *,
    workers: Iterable[WorkerProjection] = (),
    broker: BrokerProjection | None = None,
) -> FixedFirstPassStatistics:
    """Project fixed-mode display counts without recreating qualification policy."""

    if not isinstance(batch_summary, BatchSummary):
        raise StatisticsProjectionError("FIXED_SUMMARY_REQUIRED")
    projected = _unique_by_id(points, error="POINT_ID_DUPLICATE")
    by_id = {point.point_id: point for point in projected}
    if set(by_id) != set(batch_summary.point_statuses):
        raise StatisticsProjectionError("POINT_SET_MISMATCH")
    if any(by_id[point_id].status is not status for point_id, status in batch_summary.point_statuses.items()):
        raise StatisticsProjectionError("POINT_STATUS_MISMATCH")
    projected_workers = tuple(workers)
    if any(not isinstance(worker, WorkerProjection) for worker in projected_workers):
        raise StatisticsProjectionError("WORKER_PROJECTION_INVALID")
    if batch_summary.batch_terminal and (
        any(point.active_worker_id is not None for point in projected)
        or any(worker.active_point_id is not None for worker in projected_workers)
    ):
        raise StatisticsProjectionError("TERMINAL_ACTIVE_LEASE")

    points_with_retry = tuple(
        replace(
            point,
            retry_eligible=(
                batch_summary.batch_terminal
                and batch_summary.batch_cleanup_complete
                and point.status is PointStatus.FAILED
                and point.active_worker_id is None
            ),
        )
        for point in projected
    )
    requested = len(points_with_retry)
    evaluated = sum(point.evaluated for point in points_with_retry)
    execution_started = sum(point.execution_started for point in points_with_retry)
    succeeded = sum(point.status is PointStatus.PASSED for point in points_with_retry)
    failed = sum(point.status is PointStatus.FAILED for point in points_with_retry)
    indeterminate = sum(point.status is PointStatus.INDETERMINATE for point in points_with_retry)
    not_executed = requested - evaluated - indeterminate
    if not_executed < 0:
        raise StatisticsProjectionError("POINT_COUNTER_INCONSISTENT")
    qualified_rate = None
    if batch_summary.batch_cleanup_complete and evaluated:
        qualified_rate = succeeded / evaluated
    return FixedFirstPassStatistics(
        requested=requested,
        evaluated=evaluated,
        execution_started=execution_started,
        valid_succeeded=succeeded,
        valid_failed=failed,
        indeterminate=indeterminate,
        invalid_attempts=sum(point.invalid_attempts for point in points_with_retry),
        not_executed=not_executed,
        evaluation_coverage=evaluated / requested,
        execution_coverage=execution_started / requested,
        qualified_success_rate=qualified_rate,
        coverage_complete=batch_summary.coverage_complete,
        execution_complete=batch_summary.execution_complete,
        batch_cleanup_complete=batch_summary.batch_cleanup_complete,
        qualification_passed=batch_summary.qualification_passed,
        points=points_with_retry,
        workers=projected_workers,
        broker=broker or BrokerProjection(),
    )


def summarize_adaptive_first_pass(
    batch_summary: AdaptiveBatchSummary,
    points: Iterable[AdaptivePointProjection],
    *,
    workers: Iterable[WorkerProjection] = (),
    broker: BrokerProjection | None = None,
) -> AdaptiveFirstPassStatistics:
    """Project only facts committed by the adaptive runner."""

    if not isinstance(batch_summary, AdaptiveBatchSummary):
        raise StatisticsProjectionError("ADAPTIVE_SUMMARY_REQUIRED")
    projected = _unique_by_id(points, error="POINT_ID_DUPLICATE")
    projected_by_id = {point.point_id: point for point in projected}
    result_by_id = {result.point_id: result for result in batch_summary.point_results}
    if not set(result_by_id).issubset(projected_by_id):
        raise StatisticsProjectionError("ADAPTIVE_RESULT_MISMATCH")
    if any(
        projected_by_id[point_id].status is not result.status
        for point_id, result in result_by_id.items()
    ):
        raise StatisticsProjectionError("ADAPTIVE_RESULT_MISMATCH")
    terminal = batch_summary.status is not BatchTerminalStatus.INFRA_FAILED
    if terminal and set(result_by_id) != set(projected_by_id):
        raise StatisticsProjectionError("ADAPTIVE_RESULT_MISMATCH")
    if terminal and any(point.active_worker_id is not None for point in projected):
        raise StatisticsProjectionError("TERMINAL_ACTIVE_LEASE")
    if batch_summary.status is BatchTerminalStatus.COMPLETED and any(
        result.status is PointStatus.FAILED for result in batch_summary.point_results
    ):
        raise StatisticsProjectionError("ADAPTIVE_TERMINAL_STATUS_MISMATCH")
    if batch_summary.status is BatchTerminalStatus.COMPLETED_WITH_FAILURES and not any(
        result.status is PointStatus.FAILED for result in batch_summary.point_results
    ):
        raise StatisticsProjectionError("ADAPTIVE_TERMINAL_STATUS_MISMATCH")

    projected_points = tuple(
        replace(
            point,
            retry_eligible=(
                batch_summary.status is BatchTerminalStatus.COMPLETED_WITH_FAILURES
                and batch_summary.cleanup_complete
                and point.status is PointStatus.FAILED
                and point.active_worker_id is None
            ),
        )
        for point in projected
    )
    projected_workers = tuple(workers)
    if any(not isinstance(worker, WorkerProjection) for worker in projected_workers):
        raise StatisticsProjectionError("WORKER_PROJECTION_INVALID")
    return AdaptiveFirstPassStatistics(
        status=batch_summary.status.value,
        initial_worker_count=batch_summary.initial_worker_count,
        final_worker_count=batch_summary.final_worker_count,
        levels_used=batch_summary.levels_used,
        batch_cleanup_complete=batch_summary.cleanup_complete,
        valid_succeeded=sum(point.status is PointStatus.PASSED for point in projected_points),
        valid_failed=sum(point.status is PointStatus.FAILED for point in projected_points),
        indeterminate=sum(
            point.status is PointStatus.INDETERMINATE for point in projected_points
        ),
        not_executed=sum(point.status is PointStatus.UNRUN for point in projected_points),
        infra_attempts=sum(result.infra_attempts for result in batch_summary.point_results),
        points=projected_points,
        workers=projected_workers,
        broker=broker or BrokerProjection(),
        transitions=batch_summary.transitions,
    )
