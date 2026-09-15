"""Startup contracts shared by adaptive pool workers and their parent."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import traceback
from typing import Callable

from .adaptive_contracts import (
    AdaptiveWorkerOptions,
    CommittedPointResult,
    InfrastructureFailure,
    InfrastructureFailureKind,
    PoolExecutionResult,
    PoolRequest,
)
from .adaptive_queue import AdaptivePointSelector
from .contracts import AttemptStatus, BatchSummary, PointStatus, RunMode


@dataclass(frozen=True, slots=True)
class WorkerReadinessReceipt:
    worker_id: str
    generation: int
    process_start_ticks: int
    coordinator_registered: bool
    runtime_ready: bool
    broker_ready: bool
    broker_generation: int
    observed_monotonic_s: float

    def __post_init__(self) -> None:
        if not isinstance(self.worker_id, str) or not self.worker_id:
            raise ValueError("WORKER_ID")
        for name in ("generation", "process_start_ticks", "broker_generation"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(name.upper())
        for name in ("coordinator_registered", "runtime_ready", "broker_ready"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(name.upper())
        observed = self.observed_monotonic_s
        if (
            isinstance(observed, bool)
            or not isinstance(observed, (int, float))
            or not math.isfinite(observed)
            or observed < 0.0
        ):
            raise ValueError("OBSERVED_MONOTONIC_S")
        object.__setattr__(self, "observed_monotonic_s", float(observed))


class WorkerStartGate:
    """Keep one prepared worker local until its exact parent releases it."""

    def __init__(self, *, expected_worker_id: str, generation: int) -> None:
        if not isinstance(expected_worker_id, str) or not expected_worker_id:
            raise ValueError("WORKER_IDENTITY")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation <= 0:
            raise ValueError("WORKER_IDENTITY")
        self.expected_worker_id = expected_worker_id
        self.generation = generation
        self._condition = threading.Condition(threading.RLock())
        self._receipt: WorkerReadinessReceipt | None = None
        self._released = False

    @property
    def receipt(self) -> WorkerReadinessReceipt | None:
        with self._condition:
            return self._receipt

    def record_readiness(self, receipt: WorkerReadinessReceipt) -> None:
        if (
            not isinstance(receipt, WorkerReadinessReceipt)
            or receipt.worker_id != self.expected_worker_id
            or receipt.generation != self.generation
            or not receipt.coordinator_registered
            or not receipt.runtime_ready
            or not receipt.broker_ready
        ):
            raise ValueError("WORKER_READINESS")
        with self._condition:
            self._receipt = receipt

    def release(self, worker_id: str, generation: int) -> None:
        if worker_id != self.expected_worker_id or generation != self.generation:
            raise ValueError("WORKER_IDENTITY")
        with self._condition:
            if self._receipt is None:
                raise ValueError("WORKER_NOT_READY")
            self._released = True
            self._condition.notify_all()

    def wait_released(self, timeout_s: float) -> bool:
        if (
            isinstance(timeout_s, bool)
            or not isinstance(timeout_s, (int, float))
            or not math.isfinite(timeout_s)
            or timeout_s < 0.0
        ):
            raise ValueError("START_GATE_TIMEOUT")
        with self._condition:
            if not self._released:
                self._condition.wait(float(timeout_s))
            return self._released


@dataclass(frozen=True, slots=True)
class AdaptivePoolContext:
    request: PoolRequest
    options: AdaptiveWorkerOptions
    selector: AdaptivePointSelector

    def __post_init__(self) -> None:
        if not isinstance(self.request, PoolRequest):
            raise ValueError("POOL_REQUEST")
        if not isinstance(self.options, AdaptiveWorkerOptions):
            raise ValueError("ADAPTIVE_WORKER_OPTIONS")
        if not isinstance(self.selector, AdaptivePointSelector):
            raise ValueError("ADAPTIVE_POINT_SELECTOR")
        if self.request.worker_count != self.options.worker_count:
            raise ValueError("ADAPTIVE_WORKER_COUNT")


_POOL_ID = re.compile(
    r"^(?P<batch>[A-Za-z0-9][A-Za-z0-9_-]*)-"
    r"g(?P<generation>[0-9]{2})-w(?P<count>[0-9]{2})$"
)
_UNIX_SOCKET_PATH_MAX_BYTES = 107


def adaptive_socket_paths(pool_root: Path, worker_count: int) -> tuple[Path, ...]:
    """Enumerate every AF_UNIX endpoint created by one adaptive pool."""

    root = Path(pool_root)
    if not root.is_absolute() or type(worker_count) is not int or worker_count <= 0:
        raise ValueError("ADAPTIVE_SOCKET_PATHS")
    ipc = root / "ipc"
    paths = [
        *(ipc / str(index) / "s" for index in range(1, worker_count + 1)),
        *(ipc / f"worker-{index:02d}.sock" for index in range(1, worker_count + 1)),
        *(
            ipc / f"worker-{index:02d}-control.sock"
            for index in range(1, worker_count + 1)
        ),
        ipc / "broker" / "perception.sock",
        ipc / "broker" / "authority.sock",
    ]
    return tuple(paths)


def _preflight_adaptive_socket_paths(pool_root: Path, worker_count: int) -> None:
    for path in adaptive_socket_paths(pool_root, worker_count):
        if len(os.fsencode(path)) > _UNIX_SOCKET_PATH_MAX_BYTES:
            raise ValueError(f"UNIX_SOCKET_PATH_TOO_LONG: {path}")


class ProductionAdaptivePool:
    """Translate one production composition into the runner's pool contract."""

    def __init__(
        self,
        *,
        prepared,
        context: AdaptivePoolContext,
        generation: int,
        composition_factory: Callable[..., object],
        composition_kwargs: dict[str, object] | None = None,
    ) -> None:
        if (
            not isinstance(context, AdaptivePoolContext)
            or prepared.request != context.request
            or type(generation) is not int
            or generation <= 0
            or not callable(composition_factory)
        ):
            raise ValueError("PRODUCTION_ADAPTIVE_POOL")
        self.prepared = prepared
        self.context = context
        self.generation = generation
        self.composition_factory = composition_factory
        self.composition_kwargs = dict(composition_kwargs or {})
        self._pool_running_recorder = None
        self._pool_running = False

    def bind_pool_running_recorder(self, recorder) -> None:
        if not callable(recorder) or self._pool_running_recorder is not None:
            raise ValueError("POOL_RUNNING_RECORDER")
        self._pool_running_recorder = recorder

    def _record_pool_running(self, receipts) -> None:
        self._pool_running_recorder(receipts)
        self._pool_running = True

    def _failure(self, kind: InfrastructureFailureKind, detail: str):
        return InfrastructureFailure(
            kind,
            self.generation,
            self.context.request.worker_count,
            detail,
        )

    def _persist_failure(self, error: Exception, *, composition, cleanup: bool) -> None:
        stage = (
            getattr(error, "startup_stage", None)
            or ("composition_factory" if composition is None else "composition_run")
        )
        chain = []
        current: BaseException | None = error
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            chain.append({"type": type(current).__name__, "message": str(current)})
            current = current.__cause__ or current.__context__
        document = {
            "schema_version": 1,
            "kind": "so101_adaptive_pool_failure",
            "batch_id": self.context.request.batch_id,
            "generation": self.generation,
            "worker_count": self.context.request.worker_count,
            "stage": stage,
            "pool_running": self._pool_running,
            "cleanup_complete": cleanup,
            "partial_cleanup": getattr(error, "partial_cleanup", None),
            "exception_chain": chain,
            "traceback": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
            "recorded_unix_ns": time.time_ns(),
        }
        path = self.context.request.evidence_root.parent / (
            f"{self.context.request.evidence_root.name}-failure.json"
        )
        payload = json.dumps(
            document, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, path)
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _map_summary(self, summary: BatchSummary, composition) -> PoolExecutionResult:
        terminal_results = []
        missing_terminal_locations = []
        if summary.run_mode is RunMode.EXECUTE:
            locations = getattr(composition, "adaptive_result_locations", {})
            for point_id, status in summary.point_statuses.items():
                if status in {PointStatus.PASSED, PointStatus.FAILED}:
                    location = locations.get(point_id)
                    if location is None:
                        missing_terminal_locations.append(point_id)
                        continue
                    terminal_results.append(
                        CommittedPointResult(
                            point_id,
                            status,
                            Path(location),
                            0,
                        )
                    )

        statuses = getattr(composition, "adaptive_attempt_statuses", {})
        invalid = tuple(
            point_id
            for point_id, status in statuses.items()
            if status in {AttemptStatus.INVALID, AttemptStatus.INDETERMINATE}
            and point_id not in {item.point_id for item in terminal_results}
        )
        unreported_ids = list(missing_terminal_locations)
        unreported_ids.extend(
            point_id
            for point_id, status in summary.point_statuses.items()
            if status in {PointStatus.UNRUN, PointStatus.INDETERMINATE}
            and point_id not in invalid
        )
        unreported = tuple(dict.fromkeys(unreported_ids))
        interrupted = tuple(dict.fromkeys((*invalid, *unreported)))
        failure = None
        if missing_terminal_locations:
            failure = self._failure(
                InfrastructureFailureKind.COORDINATOR,
                "committed result location is absent from the fsync journal",
            )
        elif invalid:
            failure = self._failure(
                InfrastructureFailureKind.RECOVERY,
                "adaptive attempt became invalid or indeterminate",
            )
        exit_codes = tuple(getattr(composition, "worker_exit_codes", ()))
        if failure is None and any(code != 0 for code in exit_codes):
            failure = self._failure(
                InfrastructureFailureKind.PROCESS_EXIT,
                f"worker process exited nonzero: {exit_codes}",
            )
        cleanup_complete = bool(
            summary.batch_cleanup_complete
            and getattr(composition, "adaptive_cleanup_complete", True)
        )
        if failure is None and not cleanup_complete:
            failure = self._failure(
                InfrastructureFailureKind.CLEANUP,
                "pool cleanup did not complete",
            )
        return PoolExecutionResult(
            tuple(terminal_results),
            interrupted if failure is not None else (),
            failure,
            cleanup_complete,
            tuple(getattr(composition, "adaptive_diagnostics", ())),
        )

    def run(self) -> PoolExecutionResult:
        if self._pool_running_recorder is None:
            raise ValueError("POOL_RUNNING_RECORDER_REQUIRED")
        composition = None
        try:
            composition = self.composition_factory(
                self.prepared,
                adaptive_context=self.context,
                pool_running_recorder=self._record_pool_running,
                **self.composition_kwargs,
            )
            summary = composition.run()
            if not isinstance(summary, BatchSummary):
                raise ValueError("BATCH_SUMMARY_REQUIRED")
            return self._map_summary(summary, composition)
        except Exception as error:
            message = str(error)
            normalized = message.upper()
            if "BROKER" in normalized:
                kind = InfrastructureFailureKind.BROKER_DISCONNECTED
            elif "OOM" in normalized or "OUT OF MEMORY" in normalized:
                kind = InfrastructureFailureKind.OOM
            elif "ROS" in normalized and "DISCONNECT" in normalized:
                kind = InfrastructureFailureKind.ROS_DISCONNECTED
            elif "RECOVERY" in normalized:
                kind = InfrastructureFailureKind.RECOVERY
            elif "JOURNAL" in normalized or "COORDINATOR" in normalized:
                kind = InfrastructureFailureKind.COORDINATOR
            elif "CLEANUP" in normalized:
                kind = InfrastructureFailureKind.CLEANUP
            elif not self._pool_running:
                kind = InfrastructureFailureKind.STARTUP
            else:
                kind = InfrastructureFailureKind.PROCESS_EXIT
            interrupted = self.context.request.selected_point_ids
            cleanup = bool(
                getattr(composition, "adaptive_cleanup_complete", False)
            )
            diagnostics = list(getattr(composition, "adaptive_diagnostics", ()))
            try:
                self._persist_failure(error, composition=composition, cleanup=cleanup)
            except Exception as persistence_error:
                diagnostics.append(
                    "FAILURE_EVIDENCE_WRITE:"
                    f"{type(persistence_error).__name__}:{persistence_error}"
                )
            return PoolExecutionResult(
                (),
                interrupted,
                self._failure(kind, f"{type(error).__name__}: {message}"),
                cleanup,
                tuple(diagnostics),
            )


class ProductionAdaptivePoolFactory:
    """Build generation-local compositions without widening the v1 request."""

    def __init__(
        self,
        prepared,
        *,
        composition_factory=None,
        composition_kwargs: dict[str, object] | None = None,
    ) -> None:
        adaptive_request = getattr(prepared, "adaptive_request", None)
        if getattr(prepared, "request", object()) is not None or adaptive_request is None:
            raise ValueError("ADAPTIVE_PREPARED_BATCH_REQUIRED")
        if composition_factory is None:
            from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition

            composition_factory = ProductionBatchComposition
        if not callable(composition_factory):
            raise ValueError("PRODUCTION_COMPOSITION_FACTORY")
        self.prepared = prepared
        self.adaptive_request = adaptive_request
        self.composition_factory = composition_factory
        self.composition_kwargs = dict(composition_kwargs or {})

    def __call__(self, request: PoolRequest) -> ProductionAdaptivePool:
        if not isinstance(request, PoolRequest):
            raise ValueError("POOL_REQUEST_REQUIRED")
        match = _POOL_ID.fullmatch(request.batch_id)
        if match is None:
            raise ValueError("POOL_REQUEST_IDENTITY")
        generation = int(match.group("generation"))
        if (
            match.group("batch") != self.adaptive_request.batch_id
            or int(match.group("count")) != request.worker_count
            or request.run_mode is not self.adaptive_request.run_mode
            or not set(request.selected_point_ids).issubset(
                self.adaptive_request.selected_point_ids
            )
            or request.max_points_per_worker != len(request.selected_point_ids)
            or request.evidence_root
            != self.adaptive_request.runtime_root
            / f"p/g{generation:02d}w{request.worker_count:02d}"
        ):
            raise ValueError("POOL_REQUEST_IDENTITY")
        _preflight_adaptive_socket_paths(request.evidence_root, request.worker_count)
        options = replace(
            self.adaptive_request.options,
            worker_count=request.worker_count,
            fallback_worker_counts=(),
        )
        worker_ids = tuple(
            f"worker-{index:02d}" for index in range(1, request.worker_count + 1)
        )
        context = AdaptivePoolContext(
            request,
            options,
            AdaptivePointSelector(
                request.selected_point_ids,
                worker_ids,
                options.initial_points_per_worker,
            ),
        )
        return ProductionAdaptivePool(
            prepared=replace(self.prepared, request=request),
            context=context,
            generation=generation,
            composition_factory=self.composition_factory,
            composition_kwargs=self.composition_kwargs,
        )
