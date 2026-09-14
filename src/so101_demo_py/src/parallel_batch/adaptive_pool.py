"""Startup contracts shared by adaptive pool workers and their parent."""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading

from .adaptive_contracts import AdaptiveWorkerOptions, PoolRequest
from .adaptive_queue import AdaptivePointSelector


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
