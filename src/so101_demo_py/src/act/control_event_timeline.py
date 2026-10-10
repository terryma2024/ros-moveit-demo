"""Bounded, read-only observation of local control events.

The timeline cannot prove that an external action client was excluded.
"""

from collections import deque
from dataclasses import dataclass
import threading
import time


class ControlHistoryUnavailable(RuntimeError):
    """An interval cannot be treated as continuous control history."""


@dataclass(frozen=True)
class ControlEvent:
    sequence: int
    wall_ns: int
    kind: str
    generation: int | None = None
    owner: str | None = None
    session_id: str | None = None
    attempt_id: str | None = None
    goal_id: str | None = None
    ros_goal_id: str | None = None
    detail: str | None = None


class ControlEventTimeline:
    """Sequence-check local callbacks; never grant a submit or proof permit."""

    def __init__(self, *, capacity=4096, monotonic_ns=time.monotonic_ns):
        if type(capacity) is not int or capacity < 2 or not callable(monotonic_ns):
            raise ValueError('CONTROL_HISTORY_CONFIG_INVALID')
        self._lock = threading.RLock()
        self._events = deque(maxlen=capacity)
        self._clock = monotonic_ns
        self._sequence = 0
        self._last_wall_ns = None
        self._clock_invalid = False

    def cursor(self):
        with self._lock:
            return self._sequence

    def record(self, kind, *, generation=None, owner=None, session_id=None,
               attempt_id=None, goal_id=None, ros_goal_id=None, detail=None):
        if not isinstance(kind, str) or not kind:
            raise ValueError('CONTROL_EVENT_KIND_INVALID')
        if generation is not None and (type(generation) is not int or generation < 0):
            raise ValueError('CONTROL_EVENT_GENERATION_INVALID')
        for value in (owner, session_id, attempt_id, goal_id, ros_goal_id, detail):
            if value is not None and not isinstance(value, str):
                raise ValueError('CONTROL_EVENT_FIELD_INVALID')
        with self._lock:
            wall_ns = self._clock()
            if type(wall_ns) is not int or wall_ns < 0:
                self._clock_invalid = True
                wall_ns = -1
            if self._last_wall_ns is not None and wall_ns < self._last_wall_ns:
                self._clock_invalid = True
            self._last_wall_ns = wall_ns
            self._sequence += 1
            event = ControlEvent(self._sequence, wall_ns, kind, generation,
                                 owner, session_id, attempt_id, goal_id, ros_goal_id, detail)
            self._events.append(event)
            return event

    def since(self, cursor):
        with self._lock:
            if type(cursor) is not int or cursor < 0 or cursor > self._sequence:
                raise ControlHistoryUnavailable('CONTROL_HISTORY_CURSOR')
            if self._clock_invalid:
                raise ControlHistoryUnavailable('CONTROL_HISTORY_CLOCK')
            if self._events and cursor < self._events[0].sequence - 1:
                raise ControlHistoryUnavailable('CONTROL_HISTORY_GAP')
            return tuple(event for event in self._events if event.sequence > cursor)
