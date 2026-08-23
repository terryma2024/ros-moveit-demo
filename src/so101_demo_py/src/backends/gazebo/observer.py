"""Thread-safe receipt-stamped Gazebo world observations."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ReceivedGazeboObservation:
    observation: Any
    received_monotonic_s: float


class GazeboWorldObserver:
    """Keep one coherent raw observation and its local receipt time."""

    def __init__(
        self,
        initial: Any,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._observation = initial
        self._received_monotonic_s = float(clock())

    def update(self, observation: Any) -> None:
        received = float(self._clock())
        with self._lock:
            self._observation = observation
            self._received_monotonic_s = received

    def snapshot(self) -> Any:
        with self._lock:
            return self._observation

    def snapshot_with_receipt(self) -> ReceivedGazeboObservation:
        with self._lock:
            return ReceivedGazeboObservation(
                self._observation,
                self._received_monotonic_s,
            )
