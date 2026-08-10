"""Bounded, cancellable collection for an active physical release epoch."""

from dataclasses import dataclass
from typing import Callable

from .physical_outcome import (
    FinalPlacementResult,
    FinalPlacementSample,
    evaluate_final_placement,
)
from .policy_config import PhysicalOutcomeConfig


@dataclass(frozen=True, slots=True)
class ReleaseSettleResult:
    status: str
    samples: tuple[FinalPlacementSample, ...]
    evaluation: FinalPlacementResult


class ReleaseSettleExecutor:
    def __init__(
        self,
        policy: PhysicalOutcomeConfig,
        observe: Callable[[], FinalPlacementSample],
        monotonic: Callable[[], float],
        wait: Callable[[float], None],
        cancelled: Callable[[], bool],
    ) -> None:
        self._policy = policy
        self._observe = observe
        self._monotonic = monotonic
        self._wait = wait
        self._cancelled = cancelled

    def run(self, release_epoch_id: str, release_marker_sequence: int) -> ReleaseSettleResult:
        start = self._monotonic()
        samples: list[FinalPlacementSample] = []
        evaluation = evaluate_final_placement(
            (), self._policy, release_epoch_id, release_marker_sequence,
        )
        while self._monotonic() - start <= self._policy.settle_timeout_s:
            if self._cancelled():
                return ReleaseSettleResult("CANCELLED", tuple(samples), evaluation)
            observed = self._observe()
            samples.append(observed)
            if len(samples) > self._policy.max_telemetry_samples:
                samples.pop(0)
            evaluation = evaluate_final_placement(
                tuple(samples), self._policy, release_epoch_id, release_marker_sequence,
            )
            if evaluation.success:
                return ReleaseSettleResult("SUCCEEDED", tuple(samples), evaluation)
            self._wait(self._policy.sample_interval_s)
        return ReleaseSettleResult("TIMED_OUT", tuple(samples), evaluation)
