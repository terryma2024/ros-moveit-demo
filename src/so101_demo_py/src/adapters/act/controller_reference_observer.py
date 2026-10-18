"""Bound original controller publications by reset epoch and callback receipt."""

from collections import deque
import copy
import json
import threading

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


# One controller period at `update_rate` 500. A consecutive stamp step of any other length is a gap.
PERIOD_NS = 2_000_000
# Gap steps kept per controller (the count is always complete): the first ones, enough to locate a defect.
GAP_STEP_LIMIT = 256


class ControllerReferenceObserver:
    """Retain original message fields; a later verifier owns motion decisions.

    It also counts gaps: a consecutive per-controller stamp step other than `PERIOD_NS`. Gaps are not a control event;
    the Recorder seals `gap_report()` and QC refuses a gap inside the label window.
    """

    def __init__(self, *, max_frames, kinds=tuple(_NAMES)):
        integer(max_frames, minimum=51)
        # the controllers observed: the arm and the gripper, and the neck only for a rig that has one
        if not kinds or any(kind not in _NAMES for kind in kinds) or len(set(kinds)) != len(kinds):
            raise ValueError("CONTROLLER_REFERENCE_KINDS_INVALID")
        self._names = {kind: _NAMES[kind] for kind in kinds}
        # The receiver appends and the Recorder's loop reads: every access to a history takes this lock.
        self._lock = threading.RLock()
        self._frames = {kind: deque(maxlen=max_frames) for kind in self._names}
        # a publication counter per kind, independent of the bounded buffer: deriving the sequence
        # from the retained length would freeze it once the deque is full
        self._sequences = {kind: 0 for kind in self._names}
        self._identity = None
        self._floor_ns = None
        self._hazard = None
        self._gaps = {kind: {"frames": 0, "gaps": 0, "steps": []} for kind in self._names}
        self._last_stamp = {kind: None for kind in self._names}

    def gap_report(self):
        """The sealed continuity report of this epoch: frames, gap count and the first gap steps per controller."""
        with self._lock:
            return self._gap_report()

    def _gap_report(self):
        session_id, reset_epoch = self._identity if self._identity is not None else (None, None)
        return {"schema_version": 2, "period_ns": PERIOD_NS, "session_id": session_id, "reset_epoch": reset_epoch,
                "kinds": {kind: {"frames": block["frames"], "gaps": block["gaps"],
                                 "steps": [list(step) for step in block["steps"]]}
                          for kind, block in self._gaps.items()}}

    def reset(self, session_id, reset_epoch, *, source_floor_ns):
        with self._lock:
            return self._reset(session_id, reset_epoch, source_floor_ns=source_floor_ns)

    def _reset(self, session_id, reset_epoch, *, source_floor_ns):
        identity = (identifier(session_id), integer(reset_epoch, minimum=1))
        floor = _ns(source_floor_ns)
        if (self._identity is not None and identity[0] == self._identity[0]
                and (identity[1] <= self._identity[1] or floor < self._floor_ns)):
            raise ValueError("CONTROLLER_REFERENCE_EPOCH_INVALID")
        self._identity, self._floor_ns, self._hazard = identity, floor, None
        for kind in self._sequences:
            self._sequences[kind] = 0
        for history in self._frames.values():
            history.clear()
        self._gaps = {kind: {"frames": 0, "gaps": 0, "steps": []} for kind in self._names}
        self._last_stamp = {kind: None for kind in self._names}

    def invalidate(self):
        """Forget any pre-reset publications until a valid epoch arrives."""
        with self._lock:
            self._invalidate()

    def _invalidate(self):
        self._identity, self._floor_ns = None, None
        self._hazard = None
        for history in self._frames.values():
            history.clear()

    def accept(self, kind, message, *, received_monotonic_s):
        with self._lock:
            return self._accept(kind, message, received_monotonic_s=received_monotonic_s)

    def _accept(self, kind, message, *, received_monotonic_s):
        if self._hazard is not None:
            return False
        try:
            if self._identity is None or kind not in self._names:
                raise ValueError("CONTROLLER_REFERENCE_SCOPE_INVALID")
            names = tuple(message.joint_names)
            expected = self._names[kind]
            stamp = (_ns(message.header.stamp.sec) * 1_000_000_000
                     + _ns(message.header.stamp.nanosec))
            if (names != expected or message.header.stamp.nanosec >= 1_000_000_000
                    or stamp <= self._floor_ns):
                raise ValueError("CONTROLLER_REFERENCE_FRAME_INVALID")
            positions = vector(tuple(message.reference.positions), len(expected))
            velocities = vector(tuple(message.reference.velocities), len(expected))
            receipt = round(finite(received_monotonic_s, nonnegative=True) * 1_000_000_000)
            history = self._frames[kind]
            previous_stamp = self._last_stamp[kind]
            if previous_stamp is not None and stamp > previous_stamp and stamp - previous_stamp != PERIOD_NS:
                block = self._gaps[kind]
                block["gaps"] += 1
                if len(block["steps"]) < GAP_STEP_LIMIT:
                    block["steps"].append((previous_stamp, stamp))
            if history and (stamp <= history[-1]["sim_stamp_ns"]
                            or receipt < history[-1]["received_monotonic_ns"]):
                raise ValueError("CONTROLLER_REFERENCE_ORDER_INVALID")
            original = {}
            from control_msgs.msg import JointTrajectoryControllerState
            if type(message) is JointTrajectoryControllerState:
                from rosidl_runtime_py.convert import message_to_ordereddict
                original = {"original_message": json.loads(json.dumps(
                    message_to_ordereddict(message), allow_nan=False))}
            history.append({
                "sim_stamp_ns": stamp,
                "received_monotonic_ns": receipt,
                "joint_names": names,
                "positions": positions,
                "velocities": velocities,
                # the observer's own per-kind publication sequence, ratified as part of Proposal A;
                # the ordering checks above already guarantee it is monotone by construction
                "observer_sequence": self._sequences[kind] + 1,
                **original,
            })
            # the counter advances after the frame carries its number, so the first publication is 1
            self._sequences[kind] = self._sequences.get(kind, 0) + 1
            self._last_stamp[kind] = stamp
            self._gaps[kind]["frames"] += 1
            return True
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
            self._hazard = str(error)
            return False

    def recent_by_stamp(self, kind, *, now_sim_ns, window_ns):
        with self._lock:
            return self._recent_by_stamp(kind, now_sim_ns=now_sim_ns, window_ns=window_ns)

    def latest_stamp_ns(self, kind):
        """The newest accepted publication stamp of one controller, or None before its first frame."""
        with self._lock:
            return self._last_stamp.get(kind)

    def matching_by_stamp(self, kind, *, now_sim_ns, window_ns, target_ns, tolerance_ns):
        """`recent_by_stamp` followed by the exact-instant filter, without copying the window: the identity and the copies of
        only the frames within `tolerance_ns` of `target_ns` that the window read would also have returned."""
        with self._lock:
            try:
                if self._identity is None or kind not in self._names or self._hazard:
                    raise ValueError("CONTROLLER_REFERENCE_HISTORY_INVALID")
                now = _ns(now_sim_ns)
                window = _ns(window_ns)
                history = self._frames[kind]
                fresh_seen, matching = False, []
                for frame in history:
                    if 0 <= now - frame["sim_stamp_ns"] <= window:
                        fresh_seen = True
                        if abs(frame["sim_stamp_ns"] - target_ns) <= tolerance_ns:
                            matching.append(copy.deepcopy(frame))
                if history and not fresh_seen:
                    raise ValueError("CONTROLLER_REFERENCE_HISTORY_STALE")
                return self._identity, tuple(matching)
            except (KeyError, TypeError, ValueError, OverflowError) as error:
                raise ValueError("CONTROLLER_REFERENCE_HISTORY_INVALID") from error

    def _recent_by_stamp(self, kind, *, now_sim_ns, window_ns):
        """Identity and the frames whose stamp is at most `window_ns` older than `now_sim_ns` (age from the stamp)."""
        try:
            if self._identity is None or kind not in self._names or self._hazard:
                raise ValueError("CONTROLLER_REFERENCE_HISTORY_INVALID")
            now = _ns(now_sim_ns)
            window = _ns(window_ns)
            history = self._frames[kind]
            fresh = tuple(copy.deepcopy(frame) for frame in history if 0 <= now - frame["sim_stamp_ns"] <= window)
            if history and not fresh:
                raise ValueError("CONTROLLER_REFERENCE_HISTORY_STALE")
            return self._identity, fresh
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise ValueError("CONTROLLER_REFERENCE_HISTORY_INVALID") from error

    def recent(self, kind, *, now_monotonic_s, max_wall_age_s):
        with self._lock:
            return self._recent(kind, now_monotonic_s=now_monotonic_s, max_wall_age_s=max_wall_age_s)

    def _recent(self, kind, *, now_monotonic_s, max_wall_age_s):
        try:
            if self._identity is None or kind not in self._names or self._hazard:
                raise ValueError("CONTROLLER_REFERENCE_HISTORY_INVALID")
            now = round(finite(now_monotonic_s, nonnegative=True) * 1_000_000_000)
            max_age = round(finite(max_wall_age_s) * 1_000_000_000)
            if max_age <= 0:
                raise ValueError("CONTROLLER_REFERENCE_AGE_INVALID")
            history = self._frames[kind]
            if any(frame["received_monotonic_ns"] > now for frame in history):
                raise ValueError("CONTROLLER_REFERENCE_FUTURE_RECEIPT")
            fresh = tuple(copy.deepcopy(frame) for frame in history
                          if now - frame["received_monotonic_ns"] <= max_age)
            if history and not fresh:
                raise ValueError("CONTROLLER_REFERENCE_HISTORY_STALE")
            return self._identity, fresh
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise ValueError("CONTROLLER_REFERENCE_HISTORY_INVALID") from error
