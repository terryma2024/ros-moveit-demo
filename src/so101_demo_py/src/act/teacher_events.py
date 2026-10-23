"""Bounded, non-blocking, in-process Teacher event stream (SO101_TEACHER_EVENT).

The Teacher publishes execution facts (phase boundaries with their sim stamps, the normal-stop proof, the terminal
result) for the data side to consume. There are no dispatch receipts: the first goal-sending `phase_begin` is the first
command. The stream is one-way: the data side reads
it and has no path back into control. Publishing never blocks, never waits for the consumer and never raises:
when the queue is full the event is dropped, counted and visible to the consumer as a sequence gap, so a loss
always shows up as an INVALID data verdict and never as a control failure.
"""

from __future__ import annotations

import copy
import itertools
import threading
import time
from collections import deque

SCHEMA = "SO101_TEACHER_EVENT"
DEFAULT_DEPTH = 64
KINDS = frozenset({"phase_begin", "phase_finish", "normal_stop"})


class TeacherEventQueue:
    """Producer side `publish`, consumer side `drain`; both are short and never wait on the other side."""

    def __init__(self, depth: int = DEFAULT_DEPTH) -> None:
        if type(depth) is not int or not 1 <= depth <= 4096:
            raise ValueError("TEACHER_EVENT_QUEUE_DEPTH_INVALID")
        self.depth = depth
        self._events: deque = deque()
        self._sequence = itertools.count(1)
        self._published = 0
        self._dropped = 0
        self._lock = threading.Lock()

    def publish(self, kind: str, payload: dict | None = None) -> bool:
        """Offer one event. Returns False when it was dropped. Never blocks and never raises."""

        try:
            sequence = next(self._sequence)
            event = {"schema": SCHEMA, "sequence": sequence, "kind": kind,
                     "monotonic_ns": time.monotonic_ns(), "payload": copy.deepcopy(payload or {})}
        except BaseException:
            self._count_drop()
            return False
        # A producer that cannot take the lock immediately drops instead of waiting for the consumer.
        if not self._lock.acquire(blocking=False):
            self._count_drop()
            return False
        try:
            self._published += 1
            if len(self._events) >= self.depth:
                self._dropped += 1
                return False
            self._events.append(event)
            return True
        finally:
            self._lock.release()

    def _count_drop(self) -> None:
        # Approximate by design: the producer must not wait to count a drop. Bounded by int addition under the GIL.
        self._dropped += 1

    def drain(self, limit: int | None = None) -> list[dict]:
        """Remove and return the pending events, oldest first."""

        with self._lock:
            count = len(self._events) if limit is None else min(limit, len(self._events))
            return [self._events.popleft() for _ in range(count)]

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {"depth": self.depth, "pending": len(self._events), "published": self._published,
                    "dropped": self._dropped}

    @property
    def dropped(self) -> int:
        return self._dropped
