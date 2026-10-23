"""Bounded timestamp joins; simulator time never uses future feedback."""

from collections import deque
import copy
import math
import threading
import time

from .contracts import finite, identifier, validate_observation, vector
from .rig_profile import DEFAULT_RIG


def time_ns(seconds):
    """Represent source and grid seconds at the original ROS nanosecond resolution."""
    return round(finite(seconds, nonnegative=True) * 1_000_000_000)


MAX_SOURCE_AGE_NS = 100_000_000


def source_age_ok_ns(at_ns, stamp_ns, max_age_ns=MAX_SOURCE_AGE_NS):
    """THE source-age rule, in integer nanoseconds: the source is not from the future and at most `max_age_ns` old.

    The provider, the capture, the synchronizer and the recorder's row audit all admit a source through this one test.
    Floating-point seconds are never compared: a physics stamp is `step * 0.002`, so a source exactly 100 ms old differs
    from the limit by rounding noise (L2 VeUKeAls, EPISODE_SOURCE_STALE).
    """
    return 0 <= at_ns - stamp_ns <= max_age_ns


def bracketed_age_ok_ns(at_ns, stamp_ns, next_stamp_ns):
    """The one extension of the source-age rule: a planning-scene read whose content provably did not change up to the
    NEXT read is valid at every instant from its own stamp until that next read, not only for `max_age_ns`.

    "Provably" is established by the caller from the two reads (identical scene content, no Teacher apply between them) and
    recorded in the row; this function is only the interval test. Where there is no such evidence `source_age_ok_ns` applies
    unchanged.
    """
    return stamp_ns <= at_ns < next_stamp_ns


def causal_sample(samples, at_s, max_age_s):
    at_ns, age_ns = time_ns(at_s), time_ns(max_age_s)
    valid = [(stamp, value) for stamp, value in samples if source_age_ok_ns(at_ns, time_ns(stamp), age_ns)]
    if not valid:
        raise ValueError("INPUT_STALE")
    return max(valid, key=lambda item: item[0])[1]


class RgbObservationSynchronizer:
    #: The streams of the default rig (v1); an instance's `streams` come from its rig profile: the cameras in order, `arm`,
    #: and `neck` only for a rig that has one.
    STREAMS = ("head", "wrist", "arm", "neck")

    #: The joint-state streams arrive at the controller rate (500 Hz): a ring of 32 holds 64 ms, so a loop pass longer than
    #: about 60 ms found no sample inside the 100 ms window of the row it was minting and failed INPUT_STALE (L2 5daa904e: a
    #: 500 ms pass). 2048 entries cover 4 s; they are two floats each. Camera rings stay at `capacity` (a frame is 0.9 MB).
    STATE_CAPACITY = 2048

    def __init__(self, *, max_age_s, max_skew_s, capacity=None,
                 monotonic=time.monotonic, rig=DEFAULT_RIG):
        self.rig = rig
        self.cameras = rig.camera_names
        self.streams = (*self.cameras, "arm", *(("neck",) if rig.has_neck else ()))
        explicit = capacity is not None
        capacity = 32 if capacity is None else capacity
        self.max_age_s = finite(max_age_s, nonnegative=True)
        self.max_skew_s = finite(max_skew_s, nonnegative=True)
        if type(capacity) is not int or capacity < 2:
            raise ValueError("invalid ring capacity")
        self.buffers = {stream: deque(maxlen=capacity if explicit or stream in self.cameras else self.STATE_CAPACITY)
                        for stream in self.streams}
        self._session = None
        self._attempt = None
        self._last_sample = None
        self._lock = threading.RLock()
        if not callable(monotonic):
            raise ValueError("INPUT_CLOCK_INVALID")
        self.monotonic = monotonic

    def reset(self, session_id):
        identifier(session_id)
        with self._lock:
            for buffer in self.buffers.values(): buffer.clear()
            self._session, self._attempt, self._last_sample = session_id, None, None

    def push(self, stream, session_id, sim_time_s, value, *,
             received_monotonic_s=None):
        finite(sim_time_s, nonnegative=True)
        received = finite(self.monotonic() if received_monotonic_s is None
                          else received_monotonic_s, nonnegative=True)
        with self._lock:
            if stream not in self.streams or session_id != self._session:
                raise ValueError("INPUT_SESSION_INVALID")
            buffer = self.buffers[stream]
            if buffer and sim_time_s <= buffer[-1][0]:
                raise ValueError("INPUT_TIMESTAMP_INVALID")
            if stream in self.cameras:
                import numpy as np
                if not isinstance(value, np.ndarray) or value.dtype != np.uint8 or value.shape != (480, 640, 3):
                    raise ValueError("INPUT_RGB_INVALID")
                value = value.copy()
            elif stream == "arm":
                value = vector(value, 6)
            else:
                value = finite(value)
            buffer.append((sim_time_s, value, received))

    def sample(self, session_id, attempt_id, at_s):
        identifier(attempt_id)
        finite(at_s, nonnegative=True)
        with self._lock:
            if session_id != self._session or self._attempt not in (None, attempt_id):
                raise ValueError("INPUT_SESSION_INVALID")
            if self._last_sample is not None and at_s <= self._last_sample:
                raise ValueError("INPUT_TIMESTAMP_INVALID")
            values = {stream: causal_sample([(stamp, (stamp, value, received))
                                             for stamp, value, received in buffer],
                                            at_s, self.max_age_s)
                      for stream, buffer in self.buffers.items()}
            stamps = [item[0] for item in values.values()]
            if max(map(time_ns, stamps)) - min(map(time_ns, stamps)) > time_ns(self.max_skew_s):
                raise ValueError("INPUT_SKEW")
            yaw = values["neck"][1] if self.rig.has_neck else None
            result = dict(session_id=session_id, attempt_id=attempt_id, sim_time_s=at_s,
                          state=(values["arm"][1] + (math.sin(yaw), math.cos(yaw)) if self.rig.has_neck
                                 else values["arm"][1]),
                          **{camera: values[camera][1].copy() for camera in self.cameras})
            validate_observation(result, rig=self.rig)
            self._attempt, self._last_sample = attempt_id, at_s
            neck_audit = dict(neck_yaw_rad=yaw) if self.rig.has_neck else {}
            self.last_audit = dict(source_stamps=dict(zip(values, stamps, strict=True)),
                                   source_received_wall_s={stream: item[2]
                                                           for stream, item in values.items()},
                                   **neck_audit, session_id=session_id, attempt_id=attempt_id)
            return result

    def sample_with_audit(self, session_id, attempt_id, at_s):
        """Return one observation and its selected-source receipts atomically."""
        with self._lock:
            observation = self.sample(session_id, attempt_id, at_s)
            return observation, copy.deepcopy(self.last_audit)
