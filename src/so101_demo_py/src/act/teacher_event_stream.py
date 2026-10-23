"""The Teacher event stream on `/so101/teacher/events` (JSON schema `SO101_TEACHER_EVENT`).

The Teacher publishes execution facts for an independent Recorder process to consume. The stream is one-way and the
Teacher side is non-blocking by construction:

* the Teacher thread only calls `TeacherEventStream.offer`, which pushes into a bounded `TeacherEventQueue` (it never
  waits, never raises and drops-and-counts when the queue is full);
* a separate publisher thread drains that queue and calls an injected `publish(text)`; it never waits for an
  acknowledgement and a failing `publish` is counted, not propagated;
* a dropped or unpublished event consumed a sequence number, so the consumer sees it as a gap in `seq` and marks its
  own data INVALID. Nothing here can reach back into control.

This module has no ROS import. The ROS publisher and subscription are in `adapters/act/ros_teacher_event_stream.py`.
"""

from __future__ import annotations

import json
import threading

from .teacher_events import DEFAULT_DEPTH, SCHEMA, TeacherEventQueue

STREAM_SCHEMA = SCHEMA
STREAM_TOPIC = "/so101/teacher/events"
EVENT_TYPES = (
    "reset_complete", "teacher_start_observation", "phase_begin", "phase_finish", "normal_stop",
    "teacher_end_observation", "terminal", "scene_operation",
)
# The in-process queue kinds the execution publishes; each maps to the stream type of the same name.
FORWARDED_KINDS = frozenset({"phase_begin", "phase_finish", "normal_stop"})
# QoS (see adapters/act/ros_teacher_event_stream.py for the justification): reliable, volatile, keep_last(depth).
STREAM_QOS = {"reliability": "RELIABLE", "durability": "VOLATILE", "history": "KEEP_LAST", "depth": 256}
STREAM_QUEUE_DEPTH = DEFAULT_DEPTH
_ENVELOPE_KEYS = frozenset({
    "schema", "seq", "session_id", "reset_epoch", "attempt_id", "type", "sim_time_ns", "monotonic_ns", "payload",
})
_ERROR_CHARS = 300
_POLL_S = 0.02


class TeacherEventError(ValueError):
    """A stream event that is not a legal `SO101_TEACHER_EVENT` document, or breaks the stream's ordering."""


def _is_int(value) -> bool:
    return type(value) is int


def _text(value) -> bool:
    return type(value) is str and bool(value)


class StreamIdentity:
    """Session, reset epoch and attempt: the scope every event of one Teacher attempt carries."""

    __slots__ = ("session_id", "reset_epoch", "attempt_id")

    def __init__(self, session_id: str, reset_epoch: int, attempt_id: str) -> None:
        if not _text(session_id) or not _text(attempt_id) or not _is_int(reset_epoch) or reset_epoch < 0:
            raise ValueError("TEACHER_EVENT_IDENTITY_INVALID")
        self.session_id, self.reset_epoch, self.attempt_id = session_id, reset_epoch, attempt_id

    def document(self) -> dict:
        return {"session_id": self.session_id, "reset_epoch": self.reset_epoch, "attempt_id": self.attempt_id}


def encode_event(identity: StreamIdentity, *, seq: int, event_type: str, sim_time_ns, monotonic_ns: int,
                 payload: dict) -> str:
    """The closed JSON document for one event. Raises on anything that is not strictly representable."""

    document = {"schema": STREAM_SCHEMA, "seq": seq, "type": event_type, "sim_time_ns": sim_time_ns,
                "monotonic_ns": monotonic_ns, "payload": payload, **identity.document()}
    _check_envelope(document)  # the Teacher never emits what the consumer would refuse (checked without a re-parse)
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode_event(text) -> dict:
    """Parse and strictly validate one event. Raises `TeacherEventError` with a stable code."""

    try:
        document = json.loads(text, parse_constant=_refuse_constant)
    except (TypeError, ValueError) as error:
        raise TeacherEventError("TEACHER_EVENT_MALFORMED") from error
    if type(document) is not dict or set(document) != _ENVELOPE_KEYS:
        raise TeacherEventError("TEACHER_EVENT_MALFORMED")
    _check_envelope(document)
    return document


def _check_envelope(document: dict) -> None:
    if document["schema"] != STREAM_SCHEMA:
        raise TeacherEventError("TEACHER_EVENT_SCHEMA_UNKNOWN")
    if document["type"] not in EVENT_TYPES:
        raise TeacherEventError("TEACHER_EVENT_TYPE_UNKNOWN")
    if (not _is_int(document["seq"]) or document["seq"] < 1
            or not _text(document["session_id"]) or not _text(document["attempt_id"])
            or not _is_int(document["reset_epoch"]) or document["reset_epoch"] < 0
            or not _is_int(document["sim_time_ns"]) or document["sim_time_ns"] < 0
            or not _is_int(document["monotonic_ns"]) or document["monotonic_ns"] < 0
            or type(document["payload"]) is not dict):
        raise TeacherEventError("TEACHER_EVENT_MALFORMED")


def _refuse_constant(name):
    raise ValueError(name)


class StreamEventSink:
    """What the Teacher's execution publishes to: forwards the three in-process kinds to the stream.

    `publish` has the shape of `TeacherEventQueue.publish`.
    With no stream it accepts nothing. It never blocks and never raises: a stream that cannot take the event drops and
    counts it, which the Recorder sees as a gap in `seq`.
    """

    def __init__(self, stream=None) -> None:
        self._stream = stream

    def publish(self, kind: str, payload: dict | None = None) -> bool:
        stream = self._stream
        if stream is None or kind not in FORWARDED_KINDS:
            return False
        try:
            return bool(stream.offer(kind, payload))
        except Exception:
            return False


class TeacherEventStream:
    """Teacher-side producer: `offer` from the Teacher thread, a daemon thread publishes.

    `publish` receives the finished JSON text. It may raise, block or be slow: the Teacher is not affected (a stuck
    publisher only fills the bounded queue, after which events are dropped and counted). `start=False` leaves the
    thread unstarted so a test can drive `pump()` itself.
    """

    def __init__(self, identity: StreamIdentity, *, clock_ns, publish, depth: int = STREAM_QUEUE_DEPTH,
                 poll_s: float = _POLL_S, start: bool = True) -> None:
        if not callable(clock_ns) or not callable(publish):
            raise ValueError("TEACHER_EVENT_STREAM_CALLABLE_REQUIRED")
        self.identity = identity
        self._clock_ns, self._publish = clock_ns, publish
        self._queue = TeacherEventQueue(depth)
        self._poll_s = poll_s
        self._published = 0
        self._failures = 0
        self._last_published_seq = 0
        self._last_error = None
        self._stop = threading.Event()
        self._thread = None
        if start:
            self._thread = threading.Thread(target=self._run, name="teacher-event-stream", daemon=True)
            self._thread.start()

    # ---- Teacher thread ----------------------------------------------------------------------------------------

    def offer(self, event_type: str, payload: dict | None = None) -> bool:
        """Offer one event. Never blocks, never raises; False means it was dropped (and counted)."""

        try:
            try:
                sim_time_ns = self._clock_ns()
            except Exception:
                sim_time_ns = None
            return self._queue.publish(event_type, {"sim_time_ns": sim_time_ns, "body": payload or {}})
        except BaseException:
            return False

    def snapshot(self) -> dict:
        """The `teacher_event_stream` manifest block: drop counter and the last published `seq`."""

        queue = self._queue.snapshot()
        return {"schema": STREAM_SCHEMA, "topic": STREAM_TOPIC, "qos": dict(STREAM_QOS),
                "queue_depth": queue["depth"], "offered": queue["published"], "dropped": queue["dropped"],
                "published": self._published, "publish_failures": self._failures,
                "last_published_seq": self._last_published_seq, "last_error": self._last_error}

    # ---- publisher thread --------------------------------------------------------------------------------------

    def pump(self) -> int:
        """Drain once and publish; returns the number of events handled. Used by the thread and by tests."""

        handled = 0
        for event in self._queue.drain():
            handled += 1
            try:
                wrapped = event["payload"]
                text = encode_event(self.identity, seq=event["sequence"], event_type=event["kind"],
                                    sim_time_ns=wrapped["sim_time_ns"], monotonic_ns=event["monotonic_ns"],
                                    payload=wrapped["body"])
                self._publish(text)
            except BaseException as error:
                self._failures += 1
                self._last_error = f"{type(error).__name__}: {error}"[:_ERROR_CHARS]
                continue
            self._published += 1
            self._last_published_seq = event["sequence"]
        return handled

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.pump():
                    self._stop.wait(self._poll_s)
            except BaseException:
                self._stop.wait(self._poll_s)
        try:
            self.pump()  # one last drain of whatever was offered before close
        except BaseException:
            pass

    def close(self, flush_timeout_s: float = 1.0) -> None:
        """Ask the thread to flush and stop. Bounded: a stuck `publish` is abandoned (the thread is a daemon)."""

        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(max(0.0, flush_timeout_s))


class EventStreamMonitor:
    """Consumer-side validation: strict `seq` order, identity, and monotonic clocks.

    `accept` returns the decoded event for this attempt, `None` for an event of another attempt (counted in
    `foreign`, never retained), and raises `TeacherEventError` for any defect of an event that belongs to this attempt.
    """

    def __init__(self, identity: StreamIdentity) -> None:
        self.identity = identity
        self.expected_seq = 1
        self.last_monotonic_ns = 0
        self.last_sim_time_ns = 0
        self.foreign = 0
        self.accepted = 0

    def accept(self, text) -> dict | None:
        event = decode_event(text)
        if event["attempt_id"] != self.identity.attempt_id:
            self.foreign += 1
            return None
        if (event["session_id"], event["reset_epoch"]) != (self.identity.session_id, self.identity.reset_epoch):
            raise TeacherEventError("TEACHER_EVENT_IDENTITY_MISMATCH")
        if event["seq"] != self.expected_seq:
            raise TeacherEventError(
                "TEACHER_EVENT_SEQUENCE_GAP" if event["seq"] > self.expected_seq else "TEACHER_EVENT_SEQUENCE_REPEATED")
        if event["monotonic_ns"] < self.last_monotonic_ns or event["sim_time_ns"] < self.last_sim_time_ns:
            raise TeacherEventError("TEACHER_EVENT_CLOCK_REGRESSED")
        self.expected_seq += 1
        self.last_monotonic_ns, self.last_sim_time_ns = event["monotonic_ns"], event["sim_time_ns"]
        self.accepted += 1
        return event
