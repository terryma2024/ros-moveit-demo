"""Bounded timestamp joins; simulator time never uses future feedback."""

from collections import deque
import math
import threading

from .contracts import finite, identifier, validate_observation, vector


def causal_sample(samples, at_s, max_age_s):
    finite(at_s, nonnegative=True)
    finite(max_age_s, nonnegative=True)
    valid = [(stamp, value) for stamp, value in samples if 0 <= at_s - stamp <= max_age_s]
    if not valid:
        raise ValueError("INPUT_STALE")
    return max(valid, key=lambda item: item[0])[1]


class RgbObservationSynchronizer:
    STREAMS = ("head", "wrist", "arm", "neck")

    def __init__(self, *, max_age_s, max_skew_s, capacity=32):
        self.max_age_s = finite(max_age_s, nonnegative=True)
        self.max_skew_s = finite(max_skew_s, nonnegative=True)
        if type(capacity) is not int or capacity < 2:
            raise ValueError("invalid ring capacity")
        self.buffers = {stream: deque(maxlen=capacity) for stream in self.STREAMS}
        self._session = None
        self._attempt = None
        self._last_sample = None
        self._lock = threading.RLock()

    def reset(self, session_id):
        identifier(session_id)
        with self._lock:
            for buffer in self.buffers.values(): buffer.clear()
            self._session, self._attempt, self._last_sample = session_id, None, None

    def push(self, stream, session_id, sim_time_s, value):
        finite(sim_time_s, nonnegative=True)
        with self._lock:
            if stream not in self.STREAMS or session_id != self._session:
                raise ValueError("INPUT_SESSION_INVALID")
            buffer = self.buffers[stream]
            if buffer and sim_time_s <= buffer[-1][0]:
                raise ValueError("INPUT_TIMESTAMP_INVALID")
            if stream in ("head", "wrist"):
                import numpy as np
                if not isinstance(value, np.ndarray) or value.dtype != np.uint8 or value.shape != (480, 640, 3):
                    raise ValueError("INPUT_RGB_INVALID")
                value = value.copy()
            elif stream == "arm":
                value = vector(value, 6)
            else:
                value = finite(value)
            buffer.append((sim_time_s, value))

    def sample(self, session_id, attempt_id, at_s):
        identifier(attempt_id)
        finite(at_s, nonnegative=True)
        with self._lock:
            if session_id != self._session or self._attempt not in (None, attempt_id):
                raise ValueError("INPUT_SESSION_INVALID")
            if self._last_sample is not None and at_s <= self._last_sample:
                raise ValueError("INPUT_TIMESTAMP_INVALID")
            values = {stream: causal_sample([(stamp, (stamp, value)) for stamp, value in buffer],
                                            at_s, self.max_age_s)
                      for stream, buffer in self.buffers.items()}
            stamps = [item[0] for item in values.values()]
            if max(stamps) - min(stamps) > self.max_skew_s:
                raise ValueError("INPUT_SKEW")
            yaw = values["neck"][1]
            result = dict(session_id=session_id, attempt_id=attempt_id, sim_time_s=at_s,
                          state=values["arm"][1] + (math.sin(yaw), math.cos(yaw)),
                          head=values["head"][1].copy(), wrist=values["wrist"][1].copy())
            validate_observation(result)
            self._attempt, self._last_sample = attempt_id, at_s
            self.last_audit = dict(source_stamps=dict(zip(values, stamps, strict=True)),
                                   neck_yaw_rad=yaw, session_id=session_id, attempt_id=attempt_id)
            return result
