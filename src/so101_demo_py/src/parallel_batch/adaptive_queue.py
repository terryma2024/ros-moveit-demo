"""Deterministic initial affinity with dynamic work stealing."""

from __future__ import annotations

from collections import deque
import threading
from typing import Iterable


class AdaptivePointSelector:
    """Choose eligible points without turning initial affinity into capacity."""

    def __init__(
        self,
        point_ids: tuple[str, ...],
        worker_ids: tuple[str, ...],
        initial_points_per_worker: int,
    ) -> None:
        if not point_ids or len(point_ids) != len(set(point_ids)):
            raise ValueError("UNIQUE_POINT_IDS_REQUIRED")
        if not worker_ids or len(worker_ids) != len(set(worker_ids)):
            raise ValueError("UNIQUE_WORKER_IDS_REQUIRED")
        if (
            isinstance(initial_points_per_worker, bool)
            or not isinstance(initial_points_per_worker, int)
            or initial_points_per_worker <= 0
        ):
            raise ValueError("POSITIVE_INITIAL_POINTS_PER_WORKER_REQUIRED")
        self._lock = threading.RLock()
        self._point_ids = tuple(point_ids)
        self._worker_ids = tuple(worker_ids)
        self.preferred = {worker_id: deque() for worker_id in worker_ids}
        remaining = deque(point_ids)
        for _ in range(initial_points_per_worker):
            for worker_id in worker_ids:
                if not remaining:
                    break
                self.preferred[worker_id].append(remaining.popleft())
        self._global = remaining

    @property
    def global_points(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._global)

    @staticmethod
    def _take_left(candidates: deque[str], eligible: frozenset[str]) -> str | None:
        while candidates:
            point_id = candidates.popleft()
            if point_id in eligible:
                return point_id
        return None

    @staticmethod
    def _take_right(candidates: deque[str], eligible: frozenset[str]) -> str | None:
        while candidates:
            point_id = candidates.pop()
            if point_id in eligible:
                return point_id
        return None

    def choose(self, worker_id: str, eligible_point_ids: Iterable[str]) -> str | None:
        """Return one currently eligible point in the frozen selection order policy."""

        with self._lock:
            if worker_id not in self.preferred:
                raise ValueError("UNKNOWN_WORKER_ID")
            eligible = frozenset(eligible_point_ids)
            if not eligible:
                return None
            point_id = self._take_left(self.preferred[worker_id], eligible)
            if point_id is not None:
                return point_id
            point_id = self._take_left(self._global, eligible)
            if point_id is not None:
                return point_id
            for other_worker_id in self._worker_ids:
                if other_worker_id == worker_id:
                    continue
                point_id = self._take_right(
                    self.preferred[other_worker_id], eligible
                )
                if point_id is not None:
                    return point_id
            return next(
                (point_id for point_id in self._point_ids if point_id in eligible),
                None,
            )
