"""Bound original controller publications by reset epoch and callback receipt."""

from collections import deque

from so101_demo.act.contracts import finite, identifier, integer, vector
from so101_demo.act.joints import ARM_JOINTS


_NAMES = {
    "arm": ARM_JOINTS[:5],
    "gripper": ARM_JOINTS[5:],
    "neck": ("neck_yaw_joint",),
}


def _ns(value):
    if type(value) is not int or value < 0:
        raise ValueError("CONTROLLER_REFERENCE_TIME_INVALID")
    return value


class ControllerReferenceObserver:
    """Retain original message fields; a later verifier owns motion decisions."""

    def __init__(self, *, max_frames):
        integer(max_frames, minimum=51)
        self._frames = {kind: deque(maxlen=max_frames) for kind in _NAMES}
        self._identity = None
        self._floor_ns = None
        self._hazard = None

    def reset(self, session_id, reset_epoch, *, source_floor_ns):
        identity = (identifier(session_id), integer(reset_epoch, minimum=1))
        floor = _ns(source_floor_ns)
        if (self._identity is not None and identity[0] == self._identity[0]
                and (identity[1] <= self._identity[1] or floor < self._floor_ns)):
            raise ValueError("CONTROLLER_REFERENCE_EPOCH_INVALID")
        self._identity, self._floor_ns, self._hazard = identity, floor, None
        for history in self._frames.values():
            history.clear()

    def invalidate(self):
        """Forget any pre-reset publications until a valid epoch arrives."""
        self._identity, self._floor_ns = None, None
        self._hazard = None
        for history in self._frames.values():
            history.clear()

    def accept(self, kind, message, *, received_monotonic_s):
        if self._hazard is not None:
            return False
        try:
            if self._identity is None or kind not in _NAMES:
                raise ValueError("CONTROLLER_REFERENCE_SCOPE_INVALID")
            names = tuple(message.joint_names)
            expected = _NAMES[kind]
            stamp = (_ns(message.header.stamp.sec) * 1_000_000_000
                     + _ns(message.header.stamp.nanosec))
            if (names != expected or message.header.stamp.nanosec >= 1_000_000_000
                    or stamp <= self._floor_ns):
                raise ValueError("CONTROLLER_REFERENCE_FRAME_INVALID")
            positions = vector(message.reference.positions, len(expected))
            velocities = vector(message.reference.velocities, len(expected))
            receipt = round(finite(received_monotonic_s, nonnegative=True) * 1_000_000_000)
            history = self._frames[kind]
            if history and (stamp <= history[-1]["sim_stamp_ns"]
                            or receipt < history[-1]["received_monotonic_ns"]):
                raise ValueError("CONTROLLER_REFERENCE_ORDER_INVALID")
            history.append({
                "sim_stamp_ns": stamp,
                "received_monotonic_ns": receipt,
                "joint_names": names,
                "positions": positions,
                "velocities": velocities,
            })
            return True
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
            self._hazard = str(error)
            return False

    def recent(self, kind, *, now_monotonic_s, max_wall_age_s):
        try:
            if self._identity is None or kind not in _NAMES or self._hazard:
                raise ValueError("CONTROLLER_REFERENCE_HISTORY_INVALID")
            now = round(finite(now_monotonic_s, nonnegative=True) * 1_000_000_000)
            max_age = round(finite(max_wall_age_s) * 1_000_000_000)
            if max_age <= 0:
                raise ValueError("CONTROLLER_REFERENCE_AGE_INVALID")
            history = self._frames[kind]
            if any(frame["received_monotonic_ns"] > now for frame in history):
                raise ValueError("CONTROLLER_REFERENCE_FUTURE_RECEIPT")
            fresh = tuple(dict(frame) for frame in history
                          if now - frame["received_monotonic_ns"] <= max_age)
            if history and not fresh:
                raise ValueError("CONTROLLER_REFERENCE_HISTORY_STALE")
            return self._identity, fresh
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise ValueError("CONTROLLER_REFERENCE_HISTORY_INVALID") from error
