"""Bag replay for the offline episode processor (P2).

The offline processor drives the SAME Recorder engine and sources as the live Recorder. Everything those modules take from the
outside world is replaced by a recorded equivalent:

* the node: `ReplayNode` delivers the recorded messages to the subscriptions the sources create, in bag order;
* the receipt clock: every message is delivered at the MONOTONIC instant its bag stamp maps to (`ClockMap`, from the anchors the
  record-only process wrote), so `time.monotonic()` read inside a callback is the message's receipt time. This is the
  substitution for "received by the Recorder" (see p2-substitution.md): the record-only process's receipt, not the Recorder's;
* the passage of time: `VirtualClock`. `time.monotonic(_ns)`, `time.time(_ns)` and, on the replay thread, `time.sleep` follow
  it, and so do the clock defaults the modules bound at import (`monotonic=time.monotonic`, `clock_ns=time.monotonic_ns`).

Nothing here talks to ROS: the messages are deserialized from the bag with the real message types.
"""

from __future__ import annotations

import contextlib
import sys
import threading
import time
import types
from dataclasses import dataclass


# ---- clock mapping -------------------------------------------------------------------------------------------------

class ClockMap:
    """System clock <-> monotonic clock from one or two (system_ns, monotonic_ns) anchors (integer arithmetic).

    rosbag2 stamps a message with the SYSTEM clock at receipt; the clocks every rule of the pipeline uses are monotonic. With two
    anchors (at RECORDING and at stop) the mapping is linear between them and extrapolated outside; with one it is a pure offset.
    """

    def __init__(self, anchors, *, source: str = "anchors") -> None:
        pairs = sorted({(int(a["system_ns"]), int(a["monotonic_ns"])) for a in anchors})
        if not pairs:
            raise ValueError("OFFLINE_CLOCK_ANCHORS_MISSING")
        self.source = source
        self._s0, self._m0 = pairs[0]
        if len(pairs) == 1 or pairs[-1][0] == pairs[0][0]:
            self._num, self._den = 1, 1
        else:
            self._num, self._den = pairs[-1][1] - self._m0, pairs[-1][0] - self._s0
        if self._num <= 0 or self._den <= 0:
            raise ValueError("OFFLINE_CLOCK_ANCHORS_INVALID")
        self.anchors = [{"system_ns": s, "monotonic_ns": m} for s, m in pairs]

    def monotonic_ns(self, system_ns: int) -> int:
        return self._m0 + ((int(system_ns) - self._s0) * self._num) // self._den

    def system_ns(self, monotonic_ns: int) -> int:
        return self._s0 + ((int(monotonic_ns) - self._m0) * self._den) // self._num

    @property
    def drift_ppm(self) -> float:
        return (self._num / self._den - 1.0) * 1e6

    def residual_ns(self, system_ns: int, monotonic_ns: int) -> int:
        """How far a third (system, monotonic) pair is from this mapping."""
        return self.monotonic_ns(system_ns) - int(monotonic_ns)


class VirtualClock:
    """The replay's monotonic clock. Only moves forward; `set` below the current value keeps the current value."""

    def __init__(self, clock_map: ClockMap, start_ns: int) -> None:
        self.map = clock_map
        self.now_ns = int(start_ns)
        self.owner = threading.get_ident()

    def set(self, monotonic_ns: int) -> None:
        if monotonic_ns > self.now_ns:
            self.now_ns = int(monotonic_ns)

    def advance(self, seconds: float) -> None:
        self.now_ns += max(0, round(float(seconds) * 1e9))

    def monotonic(self) -> float:
        return self.now_ns / 1e9

    def time_ns(self) -> int:
        return self.map.system_ns(self.now_ns)

    def time(self) -> float:
        return self.time_ns() / 1e9


_REAL = {name: getattr(time, name) for name in ("monotonic", "monotonic_ns", "time", "time_ns", "sleep", "perf_counter",
                                                "perf_counter_ns")}


def _rewrite_defaults(replacements: dict):
    """Replace the real clock functions a function bound as a default argument; returns the undo list."""
    undo, seen = [], set()
    targets = {id(real): virtual for real, virtual in replacements.items()}

    def fix(function):
        if not isinstance(function, types.FunctionType) or id(function) in seen:
            return
        seen.add(id(function))
        defaults, keyword = function.__defaults__, function.__kwdefaults__
        new_defaults = None if defaults is None else tuple(targets.get(id(item), item) for item in defaults)
        new_keyword = None if keyword is None else {key: targets.get(id(item), item) for key, item in keyword.items()}
        if (new_defaults is not None and any(a is not b for a, b in zip(new_defaults, defaults))) or (
                new_keyword is not None and any(new_keyword[key] is not keyword[key] for key in keyword)):
            undo.append((function, defaults, keyword))
            if new_defaults is not None:
                function.__defaults__ = new_defaults
            if new_keyword is not None:
                function.__kwdefaults__ = new_keyword

    def visit(value, depth=0):
        if isinstance(value, types.FunctionType):
            fix(value)
        elif isinstance(value, (staticmethod, classmethod)):
            fix(value.__func__)
        elif isinstance(value, property):
            for accessor in (value.fget, value.fset, value.fdel):
                fix(accessor)
        elif isinstance(value, type) and depth < 3 and id(value) not in seen:
            seen.add(id(value))
            for member in list(vars(value).values()):
                visit(member, depth + 1)

    for name, module in list(sys.modules.items()):
        if module is None or not (name == "so101_demo" or name.startswith("so101_demo.")):
            continue
        for member in list(vars(module).values()):
            visit(member)
    return undo


@contextlib.contextmanager
def virtual_time(clock: VirtualClock):
    """`time` follows `clock` for the whole process (restored on exit). `sleep` advances it on the replay thread only."""
    replay_thread = threading.get_ident()
    real_sleep = _REAL["sleep"]

    def sleep(seconds):
        if threading.get_ident() == replay_thread:
            clock.advance(seconds)
        else:
            real_sleep(seconds)

    patched = {
        "monotonic": clock.monotonic, "monotonic_ns": lambda: clock.now_ns, "time": clock.time, "time_ns": clock.time_ns,
        "perf_counter": clock.monotonic, "perf_counter_ns": lambda: clock.now_ns, "sleep": sleep,
    }
    undo = _rewrite_defaults({_REAL[name]: patched[name] for name in patched})
    for name, function in patched.items():
        setattr(time, name, function)
    try:
        yield clock
    finally:
        for name, function in _REAL.items():
            setattr(time, name, function)
        # a module first imported inside the context bound THIS context's functions as its defaults: give those back too
        _rewrite_defaults({patched[name]: _REAL[name] for name in patched})
        for function, defaults, keyword in reversed(undo):
            function.__defaults__ = defaults
            function.__kwdefaults__ = keyword


# ---- the bag as a message stream ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class BagMessage:
    index: int
    topic: str
    type_name: str
    stamp_ns: int           # the bag stamp (system clock at the record-only process's receipt)
    monotonic_ns: int       # the same instant on the monotonic clock
    data: bytes


class BagStream:
    """The bag's messages in the bag's own (time) order, one lookahead. Messages are never held beyond the next one."""

    def __init__(self, uri, clock_map: ClockMap, topics=None) -> None:
        import rosbag2_py

        from .bag_io import STORAGE_ID
        from .container_bag_topics import logical_channel_map

        self.map = clock_map
        self._reader = rosbag2_py.SequentialReader()
        self._reader.open(rosbag2_py.StorageOptions(uri=str(uri), storage_id=STORAGE_ID),
                          rosbag2_py.ConverterOptions("", ""))
        self.types = {item.name: item.type for item in self._reader.get_all_topics_and_types()}
        # a container bag stores the shard-scoped channel names; the replay (like bag_info/read_messages) speaks the logical ones,
        # so a subscription made on a logical topic is matched. A bag without a topic map maps every name to itself.
        self.names = logical_channel_map(uri, self.types)
        if topics is not None:
            wanted = set(topics)
            self._reader.set_filter(rosbag2_py.StorageFilter(topics=[p for p, logical in self.names.items() if logical in wanted]))
        self._next = None
        self._index = 0
        self._last_stamp = None
        self.exhausted = False
        self._fill()

    def _fill(self) -> None:
        if self._next is not None or self.exhausted:
            return
        if not self._reader.has_next():
            self.exhausted = True
            return
        topic, data, stamp = self._reader.read_next()
        stamp = int(stamp)
        if self._last_stamp is not None and stamp < self._last_stamp:
            raise ValueError("OFFLINE_BAG_NOT_TIME_ORDERED")
        self._last_stamp = stamp
        self._next = BagMessage(self._index, self.names[topic], self.types[topic], stamp, self.map.monotonic_ns(stamp), bytes(data))
        self._index += 1

    def peek(self):
        self._fill()
        return self._next

    def pop(self):
        message = self.peek()
        self._next = None
        return message

    def close(self) -> None:
        self._reader = None


#: how long (receipt time) a message stamped ahead of the recorded /clock waits for /clock to reach its stamp
HOLD_NS = 50_000_000


# ---- the node --------------------------------------------------------------------------------------------------------

class _Subscription:
    __slots__ = ("topic", "callback", "msg_type", "raw", "closed")

    def __init__(self, topic, callback, msg_type, raw):
        self.topic, self.callback, self.msg_type, self.raw, self.closed = topic, callback, msg_type, raw, False

    def get_publisher_count(self) -> int:
        return 1


class _ReplayClockHandle:
    def __init__(self, node) -> None:
        self._node = node

    def now(self):
        from rclpy.clock import ClockType
        from rclpy.time import Time

        return Time(nanoseconds=self._node.sim_ns, clock_type=ClockType.ROS_TIME)


CAMERA_TOPICS = ("/head_camera/color", "/wrist_camera/color")


class CameraGridRepair:
    """DIAGNOSTIC ONLY (never a contract path): put camera frames on the 100 ms grid so a run can look past the camera defect.

    A frame within `tolerance_ns` of where the previous frame's grid puts it is re-stamped onto it; up to `max_inserted` frames missing between two frames
    are replaced by copies of the previous frame. Everything it changes is counted and the processor labels the result DIAGNOSTIC
    (exit code 5, never VALID): the output is not evidence and must not be committed."""

    def __init__(self, period_ns: int = 100_000_000, tolerance_ns: int = 2_500_000, max_inserted: int = 2) -> None:
        self.period_ns, self.tolerance_ns, self.max_inserted = period_ns, tolerance_ns, max_inserted
        self.last: dict = {}
        self.snapped = self.inserted = 0

    def apply(self, topic, decoded) -> list:
        import copy

        raw = int(decoded.header.stamp.sec) * 1_000_000_000 + int(decoded.header.stamp.nanosec)
        stamp = raw
        previous = self.last.get(topic)
        out = []
        if previous is not None:
            # judged on the RAW interval to the previous raw frame (a camera phase that moved by 2 ms stays moved); the repaired
            # stream keeps the phase it started with
            steps = max(1, round((raw - previous[2]) / self.period_ns))
            deviation = raw - previous[2] - steps * self.period_ns
            if abs(deviation) <= self.tolerance_ns:
                stamp = previous[0] + steps * self.period_ns
                if abs(deviation) > 1000:   # a nanosecond of rounding is not a repair
                    self.snapped += 1
                missing = steps - 1
                if 0 < missing <= self.max_inserted:
                    for index in range(1, missing + 1):
                        copy_ = copy.deepcopy(previous[1])
                        copy_.header.stamp.sec, copy_.header.stamp.nanosec = divmod(previous[0] + index * self.period_ns,
                                                                                     1_000_000_000)
                        out.append(copy_)
                        self.inserted += 1
        decoded.header.stamp.sec, decoded.header.stamp.nanosec = divmod(stamp, 1_000_000_000)
        out.append(decoded)
        self.last[topic] = (stamp, decoded, raw)
        return out


class TeacherClockRepair:
    """DIAGNOSTIC ONLY (never a contract path): replace a Teacher scene-operation clock reading that lags the simulation.

    The Teacher stamps each scene call's `request_ros_clock` / `response_ros_clock` from its node clock, which follows `/clock` and
    lagged the physics by 178 ms at the SETUP apply of the pilot bag (the other 16 operations by 0 to 22 ms). A reading more than
    `threshold_ns` behind the recorded `/clock` at the reading's own monotonic instant gets that `/clock` value instead. Everything
    it changes is counted; the processor labels the result DIAGNOSTIC (exit code 5)."""

    def __init__(self, threshold_ns: int = 30_000_000) -> None:
        self.threshold_ns, self.history, self.repaired = threshold_ns, [], []

    def observe(self, monotonic_ns: int, sim_ns: int) -> None:
        self.history.append((monotonic_ns, sim_ns))

    def sim_at(self, monotonic_ns: int):
        import bisect

        index = bisect.bisect_right(self.history, (monotonic_ns, float("inf"))) - 1
        return None if index < 0 else self.history[index][1]

    def apply(self, text: str) -> str:
        import json

        try:
            event = json.loads(text)
        except ValueError:
            return text
        if event.get("type") == "normal_stop":
            # the stop proof's clock pairs the sim time of the world record it was built from with a LATER monotonic instant
            # (`max(receipt, confirmed)`): one physics step behind the simulation at that instant on the pilot bag (2 ms), which the
            # QC rule "the stop's sim time is not before the latest native sample that ended before it" refuses
            clock = ((event.get("payload") or {}).get("proof") or {}).get("source_clock")
            if isinstance(clock, dict):
                truth = self.sim_at(clock["begin_monotonic_ns"])
                if truth is not None and 0 < truth - clock["sim_time_ns"] <= 20_000_000:
                    self.repaired.append({"seq": event.get("seq"), "operation": "normal_stop", "clock": "source_clock",
                                          "lag_ms": (truth - clock["sim_time_ns"]) / 1e6})
                    clock["sim_time_ns"] = truth
                    return json.dumps(event, sort_keys=True)
            return text
        if event.get("type") != "scene_operation":
            return text
        payload, changed = event["payload"], False
        for key in ("request_ros_clock", "response_ros_clock"):
            clock = payload.get(key)
            if not isinstance(clock, dict):
                continue
            truth = self.sim_at(clock["begin_monotonic_ns"])
            if truth is not None and truth - clock["sim_time_ns"] > self.threshold_ns:
                self.repaired.append({"seq": event.get("seq"), "operation": payload.get("operation"), "clock": key,
                                      "lag_ms": (truth - clock["sim_time_ns"]) / 1e6})
                clock["sim_time_ns"] = truth
                changed = True
        return json.dumps(event, sort_keys=True) if changed else text


class ReplayNode:
    """What the Recorder's sources use of a node, served from a bag.

    `deliver_due()` plays every message whose receipt instant has been reached, in bag order. The node's simulation clock is the
    last `/clock` message delivered. A callback that raises is recorded, never propagated (the live receiver's contract).
    """

    context = None

    #: the one source a late window start withholds: the world evidence is what begins the episode (the Recorder's verified reset is
    #: its first retained world record and the capture cannot start before one exists). Everything else is delivered from the
    #: beginning of the bag: the raw physics chunk of the first world record arrives before that record's own receipt.
    WITHHELD_BEFORE_WINDOW = ("/so101/simulation/evidence",)

    def __init__(self, stream: BagStream, clock: VirtualClock, *, clock_topic: str = "/clock", camera_repair=None,
                 start_at_stamp_ns: int | None = None, teacher_clock_repair=None) -> None:
        self.camera_repair = camera_repair
        self.teacher_clock_repair = teacher_clock_repair
        # the episode window start: world evidence recorded before this bag stamp (the receipt of the first unpaused
        # world record after the worker's last pre-Teacher pause) is not delivered
        self.start_at_stamp_ns = start_at_stamp_ns
        #: True once a message stamped at or after the window start has been played (always True without a window start)
        self.window_open = start_at_stamp_ns is None
        self.stream = stream
        self.clock = clock
        self.sim_ns = 0
        self.delivered = 0
        self.delivered_by_topic: dict = {}
        self._clock_topic = clock_topic
        self._subscriptions: dict = {}
        self._types: dict = {}
        self._errors: list = []
        self._held: dict = {}
        self._lock = threading.Lock()

    # -- the rclpy node surface the sources use --------------------------------------------------------------------

    def create_subscription(self, msg_type, topic, callback, qos_profile=None, *args, raw=False, **kwargs):
        subscription = _Subscription(str(topic), callback, msg_type, bool(raw))
        self._subscriptions.setdefault(str(topic), []).append(subscription)
        return subscription

    def destroy_subscription(self, subscription) -> bool:
        subscription.closed = True
        listeners = self._subscriptions.get(subscription.topic, [])
        if subscription in listeners:
            listeners.remove(subscription)
        return True

    def get_clock(self):
        return _ReplayClockHandle(self)

    def count_publishers(self, topic) -> int:
        return 1

    def create_publisher(self, *args, **kwargs):
        raise RuntimeError("OFFLINE_REPLAY_NODE_HAS_NO_PUBLISHERS")

    def create_client(self, *args, **kwargs):
        raise RuntimeError("OFFLINE_REPLAY_NODE_HAS_NO_SERVICES")

    # -- replay ----------------------------------------------------------------------------------------------------

    def _message_class(self, type_name):
        found = self._types.get(type_name)
        if found is None:
            from rosidl_runtime_py.utilities import get_message
            found = self._types[type_name] = get_message(type_name)
        return found

    def _deliver(self, message, decoded, listeners) -> None:
        self.delivered += 1
        self.delivered_by_topic[message.topic] = self.delivered_by_topic.get(message.topic, 0) + 1
        if message.topic == self._clock_topic and decoded is not None:
            self.sim_ns = int(decoded.clock.sec) * 1_000_000_000 + int(decoded.clock.nanosec)
            if self.teacher_clock_repair is not None:
                self.teacher_clock_repair.observe(message.monotonic_ns, self.sim_ns)
        for listener in listeners:
            if listener.closed:
                continue
            try:
                listener.callback(message.data if listener.raw else decoded)
            except Exception as error:   # noqa: BLE001 - the live receiver's contract: reported by the next pump
                self._errors.append(f"{message.topic}: {type(error).__name__}: {error}"[:300])

    def _release_held(self, limit: int) -> int:
        """Deliver held messages whose stamp the simulation clock has reached (at that instant), or whose hold ran out."""
        released = 0
        progress = True
        while progress:
            progress = False
            for topic, queue in self._held.items():
                if not queue:
                    continue
                message, decoded, listeners, stamp_ns, deadline = queue[0]
                if self.sim_ns >= stamp_ns:
                    at = self.clock.now_ns
                elif deadline <= limit:
                    at = deadline
                else:
                    continue
                queue.pop(0)
                self.clock.set(at)
                self._deliver(message, decoded, listeners)
                released += 1
                progress = True
        return released

    def deliver_due(self, until_ns: int | None = None) -> int:
        """Play every message received at or before `until_ns` (default: the virtual now). Returns how many were played.

        A producer-stamped message is never received before the simulation clock has reached its stamp. The bag has one
        subscription per topic, so `/clock` (500 Hz) can be recorded a few milliseconds after a message stamped with the instant it
        announces (joint_states: 32 of 11314 messages, up to 4 ms, pilot bag 031b82c6); a live receiver sees the producers' order.
        Such a message is held, in topic order, until `/clock` reaches its stamp, for at most HOLD_NS of receipt time; a stamp
        `/clock` does not reach in that time is delivered anyway and the sources' own future-stamp rule judges it.
        """
        from rclpy.serialization import deserialize_message

        limit = self.clock.now_ns if until_ns is None else int(until_ns)
        count = 0
        while True:
            message = self.stream.peek()
            beyond = message is None or message.monotonic_ns > limit
            # a hold that runs out before the next message is received ends in stream order, not at the end of the range
            count += self._release_held(limit if beyond else message.monotonic_ns)
            if beyond:
                return count
            self.stream.pop()
            self.clock.set(message.monotonic_ns)
            count += 1
            if self.start_at_stamp_ns is not None and message.stamp_ns >= self.start_at_stamp_ns:
                self.window_open = True
            if (self.start_at_stamp_ns is not None and message.stamp_ns < self.start_at_stamp_ns
                    and message.topic in self.WITHHELD_BEFORE_WINDOW):
                continue
            listeners = list(self._subscriptions.get(message.topic, ()))
            decoded = None
            if listeners or message.topic == self._clock_topic:
                if any(not listener.raw for listener in listeners) or message.topic == self._clock_topic:
                    try:
                        decoded = deserialize_message(message.data, self._message_class(message.type_name))
                    except Exception as error:   # noqa: BLE001
                        self._errors.append(f"{message.topic}: DESERIALIZE_FAILED: {type(error).__name__}: {error}"[:300])
                        continue
            variants = [decoded]
            if (self.teacher_clock_repair is not None and message.topic == "/so101/teacher/events" and decoded is not None):
                decoded.data = self.teacher_clock_repair.apply(decoded.data)
            if self.camera_repair is not None and message.topic in CAMERA_TOPICS and decoded is not None:
                variants = self.camera_repair.apply(message.topic, decoded)
            queue = self._held.setdefault(message.topic, [])
            for decoded in variants:
                stamp = getattr(getattr(decoded, "header", None), "stamp", None)
                stamp_ns = None if stamp is None else int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
                if listeners and message.topic != self._clock_topic and (queue or (stamp_ns is not None and stamp_ns > self.sim_ns)):
                    queue.append((message, decoded, listeners, 0 if stamp_ns is None else stamp_ns, message.monotonic_ns + HOLD_NS))
                else:
                    self._deliver(message, decoded, listeners)
            if message.topic == self._clock_topic:
                count += self._release_held(message.monotonic_ns)

    def take_callback_errors(self) -> list:
        with self._lock:
            errors, self._errors = self._errors, []
        return errors

    @property
    def exhausted(self) -> bool:
        return self.stream.peek() is None and not any(self._held.values())


class InlineExecutor:
    """`ThreadPoolExecutor(max_workers=1)` run on the caller's thread: the work is done when `submit` returns."""

    def submit(self, function, *args, **kwargs):
        from concurrent.futures import Future

        future = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except BaseException as error:   # noqa: BLE001
            future.set_exception(error)
        return future

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        return None
