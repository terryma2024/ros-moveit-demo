"""Fsync-backed authority for results and fallback across pool generations."""

from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import stat
from typing import Callable

from .adaptive_contracts import (
    AdaptiveBatchRequest,
    AdaptiveBatchSummary,
    BatchTerminalStatus,
    CommittedPointResult,
    FallbackTransition,
    InfrastructureFailure,
    InfrastructureFailureKind,
    PoolExecutionResult,
    _new_pool_request_for_production_factory,
)
from .contracts import PointStatus
from .journal import CoordinatorJournal


class AdaptiveRunnerError(RuntimeError):
    """The top-level adaptive history or pool result failed closed."""


def _prepare_private_directory(path: Path) -> Path:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    try:
        info = path.lstat()
    except OSError as error:
        raise AdaptiveRunnerError("PRIVATE_DIRECTORY_IDENTITY") from error
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise AdaptiveRunnerError("PRIVATE_DIRECTORY_IDENTITY")
    return path


def _request_document(request: AdaptiveBatchRequest) -> dict[str, object]:
    return {
        "batch_id": request.batch_id,
        "run_mode": request.run_mode.value,
        "selected_point_ids": list(request.selected_point_ids),
        "options": {
            "worker_count": request.options.worker_count,
            "fallback_worker_counts": list(request.options.fallback_worker_counts),
            "initial_points_per_worker": request.options.initial_points_per_worker,
            "worker_start_timeout_s": request.options.worker_start_timeout_s,
            "max_infra_attempts_per_point": (
                request.options.max_infra_attempts_per_point
            ),
            "ros_domain_ids": list(request.options.ros_domain_ids),
        },
        "evidence_root": str(request.evidence_root),
        "runtime_root": str(request.runtime_root),
    }


def _result_document(result: CommittedPointResult) -> dict[str, object]:
    return {
        "point_id": result.point_id,
        "status": result.status.value,
        "evidence_root": str(result.evidence_root),
        "infra_attempts": result.infra_attempts,
    }


def _failure_document(failure: InfrastructureFailure) -> dict[str, object]:
    return {
        "kind": failure.kind.value,
        "generation": failure.generation,
        "worker_count": failure.worker_count,
        "detail": failure.detail,
    }


class AdaptiveBatchRunner:
    """Run strictly descending pools while preserving durable terminal results."""

    def __init__(
        self,
        request: AdaptiveBatchRequest,
        pool_factory: Callable[[object], object],
    ) -> None:
        if not isinstance(request, AdaptiveBatchRequest):
            raise AdaptiveRunnerError("ADAPTIVE_BATCH_REQUEST_REQUIRED")
        if not callable(pool_factory):
            raise AdaptiveRunnerError("POOL_FACTORY_REQUIRED")
        self.request = request
        self.pool_factory = pool_factory
        runtime_parent = _prepare_private_directory(request.evidence_root / "r")
        self.runtime_root = _prepare_private_directory(
            runtime_parent / request.batch_id
        )
        self.journal = CoordinatorJournal.create(
            self.runtime_root / "journal", request.batch_id
        )
        self._terminal_results: dict[str, CommittedPointResult] = {}
        self._infra_attempts = {point_id: 0 for point_id in request.selected_point_ids}
        self._transitions: list[FallbackTransition] = []
        self._remaining = set(request.selected_point_ids)
        self._levels_used: list[int] = []
        self._running_generations: set[int] = set()
        self._terminal_summary: AdaptiveBatchSummary | None = None
        replay = self.journal.replay().events
        if replay:
            self._restore(replay)
        else:
            self.journal.append(
                "BATCH_MANIFEST", "batch-manifest", _request_document(request)
            )

    def close(self) -> None:
        self.journal.close()

    def _restore(self, events) -> None:
        manifest = [event for event in events if event.type == "BATCH_MANIFEST"]
        if len(manifest) != 1 or manifest[0].payload != _request_document(self.request):
            raise AdaptiveRunnerError("BATCH_MANIFEST_CHANGED")
        for event in events:
            payload = event.payload
            if event.type == "POOL_STARTING":
                level = payload["worker_count"]
                if level not in self._levels_used:
                    self._levels_used.append(level)
            elif event.type == "POOL_RUNNING":
                self._running_generations.add(payload["generation"])
            elif event.type == "POINT_RESULT_IMPORTED":
                self._apply_result(self._result_from_document(payload["result"]))
            elif event.type == "POINT_INFRA_INTERRUPTED":
                point_id = payload["point_id"]
                if point_id not in self._infra_attempts:
                    raise AdaptiveRunnerError("UNKNOWN_POINT_RESULT")
                attempts = payload["infra_attempts"]
                if type(attempts) is not int or attempts <= self._infra_attempts[point_id]:
                    raise AdaptiveRunnerError("INFRA_ATTEMPT_HISTORY")
                self._infra_attempts[point_id] = attempts
            elif event.type == "POOL_DEGRADED":
                failure = InfrastructureFailure(
                    InfrastructureFailureKind(payload["failure"]["kind"]),
                    payload["failure"]["generation"],
                    payload["failure"]["worker_count"],
                    payload["failure"]["detail"],
                )
                self._transitions.append(
                    FallbackTransition(
                        payload["generation"],
                        payload["from_count"],
                        payload["to_count"],
                        failure,
                    )
                )
            elif event.type == "BATCH_TERMINAL":
                self._terminal_summary = self._summary_from_document(payload)

    @staticmethod
    def _result_from_document(document) -> CommittedPointResult:
        try:
            return CommittedPointResult(
                document["point_id"],
                PointStatus(document["status"]),
                Path(document["evidence_root"]),
                document["infra_attempts"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AdaptiveRunnerError("POINT_RESULT_HISTORY") from error

    def _apply_result(self, result: CommittedPointResult) -> None:
        if result.point_id not in self._remaining and result.point_id not in self._terminal_results:
            raise AdaptiveRunnerError("UNKNOWN_POINT_RESULT")
        prior = self._terminal_results.get(result.point_id)
        if prior is not None:
            if prior != result:
                raise AdaptiveRunnerError("TERMINAL_RESULT_CONFLICT")
            return
        self._terminal_results[result.point_id] = result
        self._remaining.discard(result.point_id)
        self._infra_attempts[result.point_id] = result.infra_attempts

    def _import_result(self, result: CommittedPointResult, generation: int) -> None:
        if result.point_id not in self._remaining:
            prior = self._terminal_results.get(result.point_id)
            normalized = CommittedPointResult(
                result.point_id,
                result.status,
                result.evidence_root,
                self._infra_attempts[result.point_id],
            )
            if prior != normalized:
                raise AdaptiveRunnerError("TERMINAL_RESULT_CONFLICT")
            return
        normalized = CommittedPointResult(
            result.point_id,
            result.status,
            result.evidence_root,
            self._infra_attempts[result.point_id],
        )
        event = self.journal.append(
            "POINT_RESULT_IMPORTED",
            f"point-result-{result.point_id}",
            {"generation": generation, "result": _result_document(normalized)},
        )
        committed = self._result_from_document(event.payload["result"])
        if committed != normalized:
            raise AdaptiveRunnerError("TERMINAL_RESULT_CONFLICT")
        self._apply_result(committed)

    def record_pool_running(
        self, generation: int, worker_count: int, receipts
    ) -> None:
        if (
            generation <= 0
            or not self._levels_used
            or self._levels_used[-1] != worker_count
        ):
            raise AdaptiveRunnerError("POOL_RUNNING_IDENTITY")
        receipt_documents = [
            asdict(receipt) if hasattr(receipt, "__dataclass_fields__") else receipt
            for receipt in receipts
        ]
        event = self.journal.append(
            "POOL_RUNNING",
            f"pool-running-{generation:02d}",
            {
                "generation": generation,
                "worker_count": worker_count,
                "readiness_receipts": receipt_documents,
            },
        )
        if (
            event.payload["generation"] != generation
            or event.payload["worker_count"] != worker_count
        ):
            raise AdaptiveRunnerError("POOL_RUNNING_CONFLICT")
        self._running_generations.add(generation)

    def _interrupt(self, point_id: str, generation: int) -> bool:
        if point_id not in self._remaining:
            raise AdaptiveRunnerError("INTERRUPTED_TERMINAL_POINT")
        attempts = self._infra_attempts[point_id] + 1
        event = self.journal.append(
            "POINT_INFRA_INTERRUPTED",
            f"point-infra-{point_id}-{attempts}",
            {
                "point_id": point_id,
                "generation": generation,
                "infra_attempts": attempts,
            },
        )
        if event.payload["infra_attempts"] != attempts:
            raise AdaptiveRunnerError("INFRA_ATTEMPT_CONFLICT")
        self._infra_attempts[point_id] = attempts
        return attempts >= self.request.options.max_infra_attempts_per_point

    def _summary(
        self, status: BatchTerminalStatus, *, cleanup_complete: bool
    ) -> AdaptiveBatchSummary:
        final_count = (
            self._levels_used[-1]
            if self._levels_used
            else self.request.options.worker_count
        )
        return AdaptiveBatchSummary(
            status,
            self.request.options.worker_count,
            final_count,
            tuple(self._levels_used or (self.request.options.worker_count,)),
            tuple(
                self._terminal_results[point_id]
                for point_id in self.request.selected_point_ids
                if point_id in self._terminal_results
            ),
            tuple(self._transitions),
            cleanup_complete,
        )

    @staticmethod
    def _summary_document(summary: AdaptiveBatchSummary) -> dict[str, object]:
        return {
            "status": summary.status.value,
            "initial_worker_count": summary.initial_worker_count,
            "final_worker_count": summary.final_worker_count,
            "levels_used": list(summary.levels_used),
            "point_results": [_result_document(item) for item in summary.point_results],
            "transitions": [
                {
                    "generation": item.generation,
                    "from_count": item.from_count,
                    "to_count": item.to_count,
                    "failure": _failure_document(item.failure),
                }
                for item in summary.transitions
            ],
            "cleanup_complete": summary.cleanup_complete,
        }

    def _summary_from_document(self, document) -> AdaptiveBatchSummary:
        transitions = []
        for item in document["transitions"]:
            failure = item["failure"]
            transitions.append(
                FallbackTransition(
                    item["generation"],
                    item["from_count"],
                    item["to_count"],
                    InfrastructureFailure(
                        InfrastructureFailureKind(failure["kind"]),
                        failure["generation"],
                        failure["worker_count"],
                        failure["detail"],
                    ),
                )
            )
        return AdaptiveBatchSummary(
            BatchTerminalStatus(document["status"]),
            document["initial_worker_count"],
            document["final_worker_count"],
            tuple(document["levels_used"]),
            tuple(self._result_from_document(item) for item in document["point_results"]),
            tuple(transitions),
            document["cleanup_complete"],
        )

    def _finish(
        self, status: BatchTerminalStatus, *, cleanup_complete: bool
    ) -> AdaptiveBatchSummary:
        summary = self._summary(status, cleanup_complete=cleanup_complete)
        event = self.journal.append(
            "BATCH_TERMINAL", "batch-terminal", self._summary_document(summary)
        )
        committed = self._summary_from_document(event.payload)
        if committed != summary:
            raise AdaptiveRunnerError("BATCH_TERMINAL_CONFLICT")
        self._terminal_summary = committed
        return committed

    def run(self) -> AdaptiveBatchSummary:
        if self._terminal_summary is not None:
            return self._terminal_summary
        if self._levels_used:
            raise AdaptiveRunnerError("CRASHED_BATCH_REPORT_ONLY")
        pool_parent = _prepare_private_directory(self.runtime_root / "p")
        levels = self.request.options.levels
        for index, worker_count in enumerate(levels):
            generation = index + 1
            self._levels_used.append(worker_count)
            self.journal.append(
                "POOL_STARTING",
                f"pool-starting-{generation:02d}",
                {"generation": generation, "worker_count": worker_count},
            )
            selected = tuple(
                point_id
                for point_id in self.request.selected_point_ids
                if point_id in self._remaining
            )
            pool_root = pool_parent / f"g{generation:02d}w{worker_count:02d}"
            pool_request = _new_pool_request_for_production_factory(
                batch_id=(
                    f"{self.request.batch_id}-g{generation:02d}-w{worker_count:02d}"
                ),
                run_mode=self.request.run_mode,
                selected_point_ids=selected,
                worker_count=worker_count,
                max_points_per_worker=max(1, len(selected)),
                evidence_root=pool_root,
            )
            pool = self.pool_factory(pool_request)
            binder = getattr(pool, "bind_pool_running_recorder", None)
            if not callable(binder):
                raise AdaptiveRunnerError("POOL_RUNNING_RECORDER_REQUIRED")
            binder(
                lambda receipts, generation=generation, worker_count=worker_count:
                self.record_pool_running(generation, worker_count, receipts)
            )
            result = pool.run()
            if not isinstance(result, PoolExecutionResult):
                raise AdaptiveRunnerError("POOL_EXECUTION_RESULT_REQUIRED")
            for terminal in result.terminal_results:
                self._import_result(terminal, generation)
            failure = result.infrastructure_failure
            if failure is not None and (
                failure.generation != generation
                or failure.worker_count != worker_count
            ):
                raise AdaptiveRunnerError("INFRASTRUCTURE_FAILURE_IDENTITY")
            if failure is None and generation not in self._running_generations:
                failure = InfrastructureFailure(
                    InfrastructureFailureKind.STARTUP,
                    generation,
                    worker_count,
                    "POOL_RUNNING was not durably recorded",
                )
            limit_reached = False
            for point_id in result.interrupted_point_ids:
                limit_reached = self._interrupt(point_id, generation) or limit_reached
            if not result.cleanup_complete:
                return self._finish(
                    BatchTerminalStatus.INFRA_FAILED, cleanup_complete=False
                )
            if not self._remaining:
                status = (
                    BatchTerminalStatus.COMPLETED_WITH_FAILURES
                    if any(
                        result.status is PointStatus.FAILED
                        for result in self._terminal_results.values()
                    )
                    else BatchTerminalStatus.COMPLETED
                )
                return self._finish(status, cleanup_complete=True)
            if failure is None:
                if self._remaining:
                    failure = InfrastructureFailure(
                        InfrastructureFailureKind.COORDINATOR,
                        generation,
                        worker_count,
                        "pool exited with unreported points",
                    )
            if limit_reached or index + 1 == len(levels):
                return self._finish(
                    BatchTerminalStatus.INFRA_FAILED, cleanup_complete=True
                )
            next_count = levels[index + 1]
            transition = FallbackTransition(
                generation, worker_count, next_count, failure
            )
            event = self.journal.append(
                "POOL_DEGRADED",
                f"pool-degraded-{generation:02d}",
                {
                    "generation": generation,
                    "from_count": worker_count,
                    "to_count": next_count,
                    "failure": _failure_document(failure),
                },
            )
            if event.payload["to_count"] != next_count:
                raise AdaptiveRunnerError("FALLBACK_TRANSITION_CONFLICT")
            self._transitions.append(transition)
        raise AdaptiveRunnerError("FALLBACK_LOOP_EXHAUSTED")

    def terminal_report(self) -> AdaptiveBatchSummary:
        """Finalize a replayed crashed batch without starting another pool."""

        if self._terminal_summary is not None:
            return self._terminal_summary
        if not self._levels_used:
            raise AdaptiveRunnerError("NO_CRASHED_BATCH_HISTORY")
        return self._finish(BatchTerminalStatus.INFRA_FAILED, cleanup_complete=False)

    def state_snapshot(self) -> dict[str, object]:
        return {
            "terminal_results": dict(self._terminal_results),
            "infra_attempts": dict(self._infra_attempts),
            "transitions": tuple(self._transitions),
            "remaining": tuple(
                point_id
                for point_id in self.request.selected_point_ids
                if point_id in self._remaining
            ),
            "levels_used": tuple(self._levels_used),
        }
