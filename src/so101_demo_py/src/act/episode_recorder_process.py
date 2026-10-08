"""The act_episode_recorder engine: one independent process per attempt that records the data side of a Teacher run.

The Recorder consumes the Teacher event stream (`/so101/teacher/events`) and the same data sources the in-child capture
uses (RGB head/wrist, physics chunks, scene_state, world evidence, joint_states). It writes an isolated episode directory
with the existing episode assembly and lossless writer, seals it and reads it back. It holds no command authority: its
only outputs are files, and every defect it finds is a verdict on the data (INVALID), never an input to the Teacher.

Exit codes: 0 = sealed VALID, 3 = INVALID (the record is retained and rejected for export), 2 = configuration refused.

Recording window. `collection_start_s` is the simulation time at which the capture starts. The Recorder publishes its ready
file once it is listening (the event stream and every source subscribed); the orchestrator starts the Teacher after
readiness. The capture itself starts when the initial scene association exists, which the Recorder derives from the
Teacher's own setup scene operation (the scene it prepared before any motion), so it runs before the Teacher's start
observation (taken before its first command) and that observation falls inside the window. Teacher events other than
`scene_operation` that arrive before the capture started make the data INVALID. The end is the Teacher's normal-stop
clock, and the
Recorder keeps recording until its sources have caught up to the Teacher's end observation (bounded), so the window
covers the end reference. `verify_teacher_references` is run before the seal and again on the sealed files.

Readiness signal ("listening"): a ready file written exclusively and atomically beside the episode (fsync of file and directory). The
child already announces readiness to its parent the same way (`consumer-ready.json`), the orchestrator can poll it with a
bounded wait without any ROS dependency, and it survives the process for post-mortem. A latched topic would need matching
durability on both ends and a ROS subscription in the launcher.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import stat
import threading
import time
from pathlib import Path

from .exception_chain import chain_text
from .recorder_telemetry import RecorderTelemetry, configure_process, restore_process
from .teacher_event_stream import (STREAM_TOPIC, EventStreamMonitor, StreamIdentity, TeacherEventError,
                                   decode_event)

RC_VALID, RC_CONFIG, RC_INVALID = 0, 2, 3
FAULTS = ("none", "queue_overflow", "source_gap", "output_write_failure")
FAULT_SANDBOX_COMPONENT = "fault-sandbox"
READY_SCHEMA = "SO101_RECORDER_READY_V1"
RESULT_SCHEMA = "SO101_RECORDER_RESULT_V1"
POLICY_KIND = "ACT_EPISODE_RECORDER_POLICY"
REQUIRED_SOURCES = ("head", "wrist", "physics", "scene_state", "world", "joint_states")
_POLICY_FIELDS = frozenset({"kind", "schema_version", "max_duration_s", "event_inbox_capacity", "finish_budget_s",
                            "poll_s", "ready_timeout_s", "capturing_timeout_s", "exit_wait_s", "term_grace_s",
                            "physics_spool_backlog_frames_max", "physics_receiver_lag_max_s"})
_MAX_REASONS = 16
_REASON_CHARS = 300
_CHAIN_FACTS = frozenset({"writer_error", "exception_chain"})
_TEACHER_MANIFEST_SCHEMA = "so101-dynamic-mujoco-execute-v2"


class RecorderConfigRefused(ValueError):
    """The configuration cannot be honoured; the process exits with rc 2 before recording anything."""


# ---- configuration -----------------------------------------------------------------------------------------------

def _number(value, *, low, high, name, integer=False):
    kind = int if integer else (int, float)
    if type(value) is bool or not isinstance(value, kind) or (not integer and not math.isfinite(value)):
        raise RecorderConfigRefused(f"RECORDER_POLICY_INVALID: {name}")
    if not low <= value <= high:
        raise RecorderConfigRefused(f"RECORDER_POLICY_INVALID: {name}")
    return value


def load_recorder_policy(source) -> dict:
    """Load and validate the frozen recorder policy from YAML bytes or a path, with its sha256."""

    import yaml

    try:
        data = Path(source).read_bytes() if isinstance(source, (str, os.PathLike)) else bytes(source)
    except OSError as error:
        raise RecorderConfigRefused(f"RECORDER_POLICY_UNREADABLE: {error}") from error
    try:
        document = yaml.safe_load(data)
    except yaml.YAMLError as error:
        raise RecorderConfigRefused(f"RECORDER_POLICY_INVALID: not YAML: {error}") from error
    if type(document) is not dict or set(document) != _POLICY_FIELDS:
        raise RecorderConfigRefused("RECORDER_POLICY_INVALID: not the closed policy document")
    if (document["kind"] != POLICY_KIND or type(document["schema_version"]) is not int
            or document["schema_version"] != 1):
        raise RecorderConfigRefused("RECORDER_POLICY_INVALID: unknown kind or schema version")
    policy = {
        "kind": POLICY_KIND, "schema_version": 1,
        "max_duration_s": float(_number(document["max_duration_s"], low=60.0, high=900.0, name="max_duration_s")),
        "event_inbox_capacity": _number(document["event_inbox_capacity"], low=8, high=4096,
                                        name="event_inbox_capacity", integer=True),
        "finish_budget_s": float(_number(document["finish_budget_s"], low=0.1, high=30.0, name="finish_budget_s")),
        "poll_s": float(_number(document["poll_s"], low=0.0, high=1.0, name="poll_s")),
        # The orchestrator's bounds (A4c): how long it waits for the LISTENING ready file before it starts the Teacher
        # regardless, how long it waits for the Recorder to exit after the Teacher ended, and the grace after SIGTERM.
        "ready_timeout_s": float(_number(document["ready_timeout_s"], low=0.1, high=60.0, name="ready_timeout_s")),
        "capturing_timeout_s": float(_number(document["capturing_timeout_s"], low=0.1, high=60.0, name="capturing_timeout_s")),
        "exit_wait_s": float(_number(document["exit_wait_s"], low=0.1, high=120.0, name="exit_wait_s")),
        "term_grace_s": float(_number(document["term_grace_s"], low=0.1, high=30.0, name="term_grace_s")),
        # CP-3410: the raw-chunk data fails on a backlog, not on one late chunk. Upper bounds are the structures that hold
        # the backlog: the adapter's 128-chunk pending queue and its 4096-step (8.19 s) lookup history.
        "physics_spool_backlog_frames_max": _number(document["physics_spool_backlog_frames_max"], low=1, high=128,
                                                    name="physics_spool_backlog_frames_max", integer=True),
        "physics_receiver_lag_max_s": float(_number(document["physics_receiver_lag_max_s"], low=0.5, high=8.0,
                                                    name="physics_receiver_lag_max_s")),
    }
    digest = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**policy, "policy_sha256": digest}


def require_fault_sandbox(fault: str, *paths) -> None:
    """A fault other than `none` is only honoured when every output path sits under a `fault-sandbox/` component."""

    if fault not in FAULTS:
        raise RecorderConfigRefused(f"RECORDER_FAULT_UNKNOWN: {fault}")
    if fault == "none":
        return
    for path in paths:
        path = Path(path)
        # The component must be a proper ancestor, both as written and after resolving symlinks.
        resolved = Path(os.path.realpath(path))
        if (FAULT_SANDBOX_COMPONENT not in path.parts[:-1]
                or FAULT_SANDBOX_COMPONENT not in resolved.parts[:-1]):
            raise RecorderConfigRefused(f"RECORDER_FAULT_OUTSIDE_SANDBOX: {path}")


def check_outputs_absent(*paths) -> None:
    for path in paths:
        if os.path.lexists(path):
            raise RecorderConfigRefused(f"RECORDER_OUTPUT_EXISTS: {path}")


def _publish_json(path: Path, document: dict, *, replace: bool = False) -> None:
    """Exclusive, durable publication: the file either does not exist or is complete. `replace` swaps a complete file for the
    next complete one atomically (the ready file LISTENING -> CAPTURING); nothing else is ever replaced."""

    path = Path(path)
    payload = (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{os.getpid()}.pending")
    descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("recorder document write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        if replace:
            os.replace(staging, path)
        else:
            os.link(staging, path)  # fails if the target exists: an existing document is never replaced
    finally:
        if not replace:
            os.unlink(staging)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


# ---- fault injection (Recorder side only, sandbox only) ------------------------------------------------------------

class FaultInjector:
    """The three Recorder-side sandbox faults. Nothing here touches the Teacher, the stream or any control path.

    queue_overflow       the Recorder's event inbox shrinks to two events and handling stalls briefly after the first
                         arrival, as a slow consumer would, so a burst overflows it deterministically;
    source_gap           exactly one physics chunk (the third received) never reaches the physics adapter;
    output_write_failure the episode directory tree becomes read-only once the Recorder is ready.
    """

    INBOX_CAPACITY = 2
    INBOX_STALL_S = 2.0
    GAP_AFTER_CHUNKS = 2

    def __init__(self, fault: str = "none") -> None:
        if fault not in FAULTS:
            raise RecorderConfigRefused(f"RECORDER_FAULT_UNKNOWN: {fault}")
        if fault == "output_write_failure" and os.geteuid() == 0:
            raise RecorderConfigRefused("RECORDER_FAULT_NOT_EFFECTIVE_AS_ROOT")
        self.fault = fault
        self._chunks_seen = 0
        self._chunks_dropped = 0
        self._modes: dict[str, int] = {}

    def inbox_capacity(self, configured: int) -> int:
        return min(configured, self.INBOX_CAPACITY) if self.fault == "queue_overflow" else configured

    def inbox_stall_s(self) -> float:
        return self.INBOX_STALL_S if self.fault == "queue_overflow" else 0.0

    def physics_chunk(self, message):
        """The message to deliver, or None for the one chunk the gap fault drops."""

        if self.fault != "source_gap":
            return message
        self._chunks_seen += 1
        if self._chunks_seen == self.GAP_AFTER_CHUNKS + 1 and not self._chunks_dropped:
            self._chunks_dropped += 1
            return None
        return message

    def physics_adapter_class(self, base):
        """`base`, or a subclass whose ingress passes every chunk through `physics_chunk` (gap fault only)."""

        if self.fault != "source_gap":
            return base
        injector = self

        class FaultInjectingPhysicsAdapter(base):
            def accept_message(self, message):
                forwarded = injector.physics_chunk(message)
                if forwarded is not None:
                    super().accept_message(forwarded)

        return FaultInjectingPhysicsAdapter

    def after_ready(self, root) -> None:
        """Make the episode tree read-only (files 0444, directories 0555). Only the tree, nothing beside it."""

        if self.fault != "output_write_failure":
            return
        root = Path(root)
        paths = [root]
        for directory, directories, files in os.walk(root):
            paths.extend(Path(directory) / name for name in (*directories, *files))
        for path in paths:
            if path.is_symlink():
                continue
            mode = stat.S_IMODE(path.lstat().st_mode)
            self._modes[str(path)] = mode
            os.chmod(path, mode & ~0o222)

    def restore(self, root) -> None:
        """Give the owner write access back so the retained evidence can be inspected and later cleaned up."""

        for name in sorted(self._modes, key=len):   # parents before children
            try:
                os.chmod(name, self._modes[name])
            except OSError:
                pass
        self._modes = {}

    def snapshot(self) -> dict:
        return {"fault": self.fault, "physics_chunks_seen": self._chunks_seen,
                "physics_chunks_dropped": self._chunks_dropped}


# ---- sources -----------------------------------------------------------------------------------------------------

class RecorderSources:
    """What the engine needs from the data sources. The ROS implementation is in `ros/episode_recorder_sources.py`.

    Every method is non-blocking. An exception from `prepare`, `pump`, `try_start`, `collect` or `on_teacher_event`
    becomes an INVALID verdict; it never stops the process from reaching its terminal handling and seal attempt.
    """

    def prepare(self, engine) -> None:
        """Create subscriptions and adapters (called once, before the first pass)."""

    def listening(self, engine) -> bool:
        """True once the Teacher event stream and every source are subscribed (the ready file is published then)."""
        return True

    def pump(self, engine) -> None:
        """One servicing pass: spin the node once, drain the source adapters."""
        raise NotImplementedError

    def try_start(self, engine):
        """Start the capture when its prerequisites hold; return its start time (sim seconds) or None."""
        raise NotImplementedError

    def collect(self, engine) -> None:
        """Drain rows and request the accepted controller references that are due."""

    def on_teacher_event(self, engine, event: dict) -> None:
        """Retain one accepted Teacher event in the episode (boundaries, dispatch receipts, stop proof)."""

    def capture_committed(self, engine) -> bool:
        """True once the capture started and its initial boundary is committed (the ready file then says CAPTURING)."""
        return bool(engine.ready)

    def start_gate_summary(self, engine) -> dict:
        """Passes of the capture-start gate by outcome ({} when the sources keep none): why the capture did not start."""
        return {}

    def retained_history_start_s(self, engine):
        """Simulation time of the earliest retained native sample, or None when unknown (CP-3414).

        A Teacher event received before the capture started is bound against this retained history once the capture
        starts: an event stamped before it cannot be covered by the recording.
        """
        return None

    def tail_ready(self, engine) -> bool:
        """After the terminal event: have the sources caught up with the Teacher's end observation?"""
        return True

    def end_time_s(self, engine) -> float:
        """The simulation time the capture ends at (the Teacher's normal-stop clock when it was retained)."""
        return engine.episode.capture.window["collection_end_s"]

    def physics_steps(self, engine) -> list:
        """The retained raw physics samples, for the Teacher-reference check."""
        return []

    def final_issues(self, engine) -> list:
        """Reasons the recording is incomplete that only the sources can see (owed associations, unfinished work)."""
        return []

    def source_counts(self, engine) -> dict:
        """How many messages each required source delivered (names in REQUIRED_SOURCES)."""
        return {}

    def close(self) -> None:
        """Release subscriptions and adapters."""

    def telemetry_facts(self, engine) -> dict:
        """Bounded observation facts of the sources (receiver, scene poller, chunk spooler); read after `close`."""
        return {}


# ---- engine ------------------------------------------------------------------------------------------------------

# A Teacher emits tens of events per episode; this bounds the ones held while the capture is not yet running (CP-3414).
_DEFERRED_EVENTS_MAX = 512


class RecorderEngine:
    def __init__(self, *, episode, sources, policy, identity: StreamIdentity, ready_file, result_file,
                 fault: str = "none", faults: FaultInjector | None = None, clock=time.monotonic,
                 sleep=time.sleep) -> None:
        self.episode, self.sources, self.policy, self.identity = episode, sources, dict(policy), identity
        self.ready_file, self.result_file = Path(ready_file), Path(result_file)
        # The sources are built with the same injector (the physics adapter class), so the CLI may pass it in.
        self.faults = FaultInjector(fault) if faults is None else faults
        self.clock, self.sleep = clock, sleep
        self.monitor = EventStreamMonitor(identity)
        self.invalid: list[dict] = []
        self._invalid_total = 0
        self._lock = threading.Lock()
        self._inbox = collections.deque()
        self._capacity = self.faults.inbox_capacity(self.policy["event_inbox_capacity"])
        self._inbox_dropped = 0
        self._overflow_latched = False
        self._stall_until = None
        self._stream_broken = False
        self._collect_failed = False
        self.start_obs = self.end_obs = self.terminal = None
        self.stop_seen = False
        self._event_types: dict = {}
        self._last_seq = 0
        self._deferred: list = []          # Teacher events received before the capture started (CP-3414), in order
        self._deferred_first = None
        self._deferred_replayed = 0
        self._goal_phase_begin_seen = False
        self.telemetry = RecorderTelemetry()
        self._process_state = None
        self.ready = False          # the capture has started
        self.capturing = False      # the capture's initial boundary is committed: the ready file says CAPTURING (CP-3425)
        self.listening = False      # the ready file has been published
        self.collection_start_s = None
        self.sealed = False
        self._stop_reason = None
        self._began = None
        self._seal_path = None
        self._counts: dict = {}
        self.rc = None

    # ---- ingress (any thread) ---------------------------------------------------------------------------------

    def on_event_text(self, text) -> None:
        """Offer one JSON text from the stream subscription. Bounded; never blocks and never raises."""

        try:
            with self._lock:
                if len(self._inbox) >= self._capacity:
                    self._inbox_dropped += 1
                    return
                self._inbox.append(text)
        except BaseException:
            pass

    # ---- verdict ----------------------------------------------------------------------------------------------

    def latch(self, reason, **facts) -> None:
        """Record one reason the data cannot be used. First reasons are kept, bounded.

        The verdict is sticky for the whole process, so nothing here poisons the capture: a healthy capture is still
        sealed, as a FAILED record naming the first reason, and a capture that failed on its own simply cannot seal.
        """

        text = (str(reason) or "RECORDER_DATA_INVALID")[:_REASON_CHARS]
        with self._lock:
            self._invalid_total += 1
            if len(self.invalid) < _MAX_REASONS and not (self.invalid and self.invalid[-1]["reason"] == text):
                entry = {"reason": text, "monotonic_ns": time.monotonic_ns()}
                # the exception chains of writer and seal failures are longer than an ordinary fact (CP-3412)
                entry.update({key: str(value)[:(2000 if key in _CHAIN_FACTS else _REASON_CHARS)]
                              for key, value in facts.items()})
                self.invalid.append(entry)

    @staticmethod
    def _reason(error: BaseException) -> str:
        return str(error) or type(error).__name__

    # ---- one pass ---------------------------------------------------------------------------------------------

    def step(self) -> None:
        if self._inbox_dropped and not self._overflow_latched:
            self._overflow_latched = True
            self.latch("RECORDER_EVENT_QUEUE_OVERFLOW", dropped=self._inbox_dropped, capacity=self._capacity)
        try:
            with self.telemetry.phase("pump"):
                self.sources.pump(self)
        except Exception as error:
            self.latch(self._reason(error))
        if not self.listening:
            self._announce_listening()
        with self.telemetry.phase("events"):
            self._process_events()
        if not self.ready:
            with self.telemetry.phase("try_start"):
                self._try_start()
        if self.ready and not self._collect_failed:
            with self.telemetry.phase("collect"):
                self._collect()
        if self.ready and not self.capturing:
            self._announce_capturing()

    def _announce_listening(self) -> None:
        """Publish the ready file once the sources report that they are listening."""
        try:
            if not self.sources.listening(self):
                return
        except Exception as error:
            self.latch("RECORDER_LISTENING_CHECK_FAILED: " + self._reason(error))
            return
        self.listening = True
        try:
            _publish_json(self.ready_file, {
                "schema": READY_SCHEMA, **self.identity.document(), "pid": os.getpid(),
                "state": "LISTENING", "ready_monotonic_ns": time.monotonic_ns(), "topic": STREAM_TOPIC,
                "policy_sha256": self.policy["policy_sha256"], "fault": self.faults.fault})
        except OSError as error:
            self.latch("RECORDER_READY_WRITE_FAILED: " + self._reason(error))

    def _announce_capturing(self) -> None:
        """Rewrite the ready file as CAPTURING once the capture's initial boundary is committed. The orchestrator starts the
        Teacher after it (bounded wait; the Teacher starts anyway on a timeout and the data is INVALID)."""
        try:
            if not self.sources.capture_committed(self):
                return
        except Exception as error:
            self.latch("RECORDER_CAPTURING_CHECK_FAILED: " + self._reason(error))
            self.capturing = True
            return
        self.capturing = True
        try:
            _publish_json(self.ready_file, {
                "schema": READY_SCHEMA, **self.identity.document(), "pid": os.getpid(),
                "state": "CAPTURING", "ready_monotonic_ns": time.monotonic_ns(), "topic": STREAM_TOPIC,
                "collection_start_s": self.collection_start_s,
                "policy_sha256": self.policy["policy_sha256"], "fault": self.faults.fault}, replace=True)
        except OSError as error:
            self.latch("RECORDER_READY_WRITE_FAILED: " + self._reason(error))

    def _try_start(self) -> None:
        try:
            started = self.sources.try_start(self)
        except Exception as error:
            self.latch("RECORDER_CAPTURE_START_FAILED: " + self._reason(error))
            return
        if started is None or started is False:
            return
        self.collection_start_s = float(started)
        if not self.episode.capture.started:
            self.latch("RECORDER_CAPTURE_START_FAILED: the sources reported a start the capture does not have")
            return
        self.ready = True
        self._flush_deferred()
        try:
            self.faults.after_ready(self.episode.capture.recorder.root)
        except Exception as error:
            self.latch("RECORDER_FAULT_INJECTION_FAILED: " + self._reason(error))

    def _take_events(self) -> list:
        stall = self.faults.inbox_stall_s()
        with self._lock:
            if not self._inbox:
                return []
            if stall:
                if self._stall_until is None:
                    self._stall_until = self.clock() + stall
                if self.clock() < self._stall_until:
                    return []
            events = list(self._inbox)
            self._inbox.clear()
            return events

    def _process_events(self) -> None:
        events = self._take_events()
        if events and not self.ready:
            self._try_start()   # a capture that is startable now must not see its first events as "too early"
        for text in events:
            try:
                self._handle_text(text)
            except Exception as error:   # a handler defect is a data verdict, never an exception into the loop
                self.latch("RECORDER_EVENT_HANDLER_FAILED: " + self._reason(error))
            if not self.ready:
                self._try_start()   # the setup scene may have just made the capture startable

    def _handle_text(self, text) -> None:
        if self._stream_broken:
            self._tolerate(text)
            return
        try:
            event = self.monitor.accept(text)
        except TeacherEventError as error:
            self.latch(str(error))
            self._stream_broken = True
            self._tolerate(text)
            return
        if event is None:
            return
        kind, payload = event["type"], event["payload"]
        self._event_types[kind] = self._event_types.get(kind, 0) + 1
        self._last_seq = event["seq"]
        if kind == "phase_begin" and payload.get("goal_sent") is True:
            self._goal_phase_begin_seen = True
        if kind == "teacher_start_observation":
            self.start_obs = payload.get("observation")
        elif kind == "teacher_end_observation":
            self.end_obs = payload.get("observation")
        elif kind == "normal_stop" and type(payload.get("proof")) is dict:
            self.stop_seen = True
        if kind != "scene_operation" and not self.episode.capture.started:
            # The Teacher event arrived before the capture started (CP-3414). The sequence was checked on receipt above.
            # Retention waits for the start: the episode only needs a verified reset boundary that the capture covers, so
            # the event is bound by its own simulation stamps against the retained history once the capture starts.
            # Scene operations are never held: the capture starts from them.
            if len(self._deferred) >= _DEFERRED_EVENTS_MAX:
                self.latch("RECORDER_DEFERRED_EVENT_OVERFLOW", event_type=kind, seq=event["seq"],
                           capacity=_DEFERRED_EVENTS_MAX)
            else:
                if not self._deferred:
                    self._deferred_first = (kind, event["seq"], time.monotonic_ns())
                self._deferred.append(event)
        else:
            self._retain_event(event)
        if kind == "terminal":
            self.terminal = payload

    def _retain_event(self, event) -> None:
        try:
            # Scene operations always reach source alignment: the rows after them need their associations, and a missing one would only
            # add a second, misleading reason (L2 81fa2857). Everything else is retained only while the data is valid.
            if not self.invalid or event["type"] == "scene_operation":
                self.sources.on_teacher_event(self, event)
        except Exception as error:
            self.latch("RECORDER_EVENT_RETENTION_FAILED: " + self._reason(error))

    @staticmethod
    def _event_stamp_s(event):
        """The simulation stamp a deferred event claims, or None for a kind that has none the capture must cover."""
        kind, payload = event["type"], event["payload"]
        try:
            if kind == "reset_complete":
                return float(payload["simulation_time_s"])
            if kind == "teacher_start_observation":
                return float(payload["observation"]["simulation_time_s"])
            if kind == "phase_begin" and payload.get("goal_sent") is True:
                return float(payload["sim_time_ns"]) / 1e9
        except (KeyError, TypeError, ValueError):
            return None
        return None

    def _flush_deferred(self) -> None:
        """Process the events held for the capture start, in order, bound by their sim stamps (CP-3414)."""
        held, self._deferred = self._deferred, []
        if not held:
            return
        try:
            history = self.sources.retained_history_start_s(self)
        except Exception as error:
            history = None
            self.latch("RECORDER_RETAINED_HISTORY_UNKNOWN: " + self._reason(error))
        start = self.collection_start_s
        self._deferred_replayed = len(held)
        for event in held:
            stamp = self._event_stamp_s(event)
            kind = event["type"]
            if stamp is not None:
                if kind == "reset_complete":
                    if history is not None and stamp < history:
                        self.latch("RECORDER_EVENT_BEFORE_RETAINED_HISTORY", event_type=kind, seq=event["seq"],
                                   event_sim_s=stamp, history_start_sim_s=history)
                elif start is not None and stamp < start:
                    # the Teacher's start reference and first command must lie inside the recording
                    self.latch("RECORDER_TEACHER_EVENT_BEFORE_CAPTURE_START", event_type=kind, seq=event["seq"],
                               event_sim_s=stamp, capture_start_sim_s=start)
            self._retain_event(event)

    def event_summary(self) -> dict:
        """Every V2 event this engine accepted, in order and without a gap (retained or not): sealed for QC."""
        return {"schema": "SO101_TEACHER_EVENT_V2", "accepted": sum(self._event_types.values()),
                "last_seq": self._last_seq, "types": dict(self._event_types)}

    def require_teacher_events(self) -> None:
        """The events the record cannot be causal without: reset_complete, a goal-sending phase_begin, normal_stop."""
        for kind, present in (("reset_complete", "reset_complete" in self._event_types),
                              ("phase_begin", self._goal_phase_begin_seen),
                              ("normal_stop", self.stop_seen)):
            if not present:
                self.latch("RECORDER_EVENT_MISSING: " + kind)

    def _tolerate(self, text) -> None:
        """After a stream defect the verdict is already INVALID. Only two facts still matter: the terminal event ends
        the run, and a normal-stop proof lets the retained record be sealed (as FAILED) instead of left unsealed."""
        try:
            event = decode_event(text)
        except TeacherEventError:
            return
        if event["attempt_id"] != self.identity.attempt_id:
            return
        if event["type"] == "normal_stop" and type(event["payload"].get("proof")) is dict:
            self.stop_seen = True
        elif event["type"] == "terminal":
            self.terminal = event["payload"]

    def _queue_facts(self) -> dict:
        """The recorder queue's own account of a write failure (its writer thread's exception); {} when there is none."""
        try:
            error = self.episode.capture.recorder.snapshot().get("writer_error")
        except Exception:
            return {}
        return {} if error is None else {"writer_error": error}

    def _collect(self) -> None:
        try:
            self.sources.collect(self)
            self.episode.capture.check_health()
        except Exception as error:
            self._collect_failed = True   # the capture failed on its own: it cannot recover, so it is not asked again
            self.latch(self._reason(error), exception_chain=chain_text(error), **self._queue_facts())
            try:
                # Nothing drains the capture any more: latch its failure too, so the frames the cameras keep delivering are
                # refused at once instead of filling its queues (L2 rerun: CAPTURE_ACQUISITION_OVERFLOW 1.6 s after the
                # first reference failure, a second reason that only said "nobody is draining").
                self.episode.capture.reject_source(self._reason(error)[:_REASON_CHARS] or "RECORDER_COLLECT_FAILED")
            except Exception:
                pass

    # ---- run and finish ---------------------------------------------------------------------------------------

    def check_outputs_absent(self) -> None:
        check_outputs_absent(self.ready_file, self.result_file)

    def run(self, should_stop=lambda: False) -> int:
        """Record until the Teacher terminal event, a stop request or the frozen max duration; return the exit code."""

        self.check_outputs_absent()
        self._began = self.clock()
        try:
            self.sources.prepare(self)
        except Exception as error:
            self.latch("RECORDER_SOURCE_CONSTRUCTION_FAILED: " + self._reason(error))
        # Process discipline and stall telemetry start once everything long-lived exists (imports, frozen inputs, the
        # subscriptions): the imports are frozen out of the collector's reach and full collections become rare.
        try:
            self._process_state = configure_process()
            self.telemetry.start()
        except Exception as error:   # observation only
            self.latch("RECORDER_TELEMETRY_START_FAILED: " + self._reason(error))
        while True:
            self.telemetry.begin_pass()
            try:
                self.step()
            except Exception as error:
                self.latch("RECORDER_STEP_FAILED: " + self._reason(error))
            finally:
                self.telemetry.end_pass()
            if self.terminal is not None:
                break
            if should_stop():
                self._stop_reason = "RECORDER_TERMINATED"
                break
            if self.clock() - self._began > self.policy["max_duration_s"]:
                self._stop_reason = "RECORDER_MAX_DURATION_EXCEEDED"
                break
            self.sleep(self.policy["poll_s"])
        return self.finalize()

    def finalize(self) -> int:
        """Catch up, check, seal, read back, write the result. Always leaves a retained record; never raises."""

        try:
            if self._deferred and not self.episode.capture.started:
                kind, seq, _ = self._deferred_first
                try:
                    gate = json.dumps(self.sources.start_gate_summary(self), sort_keys=True)
                except Exception:
                    gate = "unavailable"
                self.latch("RECORDER_NOT_READY_BEFORE_TEACHER_EVENT", event_type=kind, seq=seq, capture_started=False,
                           held_events=len(self._deferred), ready_means="LISTENING only, not capture started",
                           start_gate=gate)
            if self.terminal is None:
                self.latch(self._stop_reason or "RECORDER_NO_TERMINAL_EVENT")
            elif self.ready and not self.invalid:
                self._tail()
            self._check_sources()
            self._seal()
        except Exception as error:
            self.latch("RECORDER_FINALIZE_FAILED: " + self._reason(error))
        finally:
            try:
                self.faults.restore(self.episode.capture.recorder.root)
            except Exception:
                pass
            try:
                self.telemetry.snapshot_cpu()
                self.sources.close()
            except Exception as error:
                self.latch("RECORDER_SOURCE_CLOSE_FAILED: " + self._reason(error))
            self._finish_telemetry()
        self.rc = RC_INVALID if self.invalid else RC_VALID
        self._write_result()
        return self.rc

    def _finish_telemetry(self) -> None:
        """Stop the observers, restore the process, keep the document in the episode root (bounded). Never raises."""
        try:
            self.telemetry.stop()
            if self._process_state is not None:
                restore_process(self._process_state)
                self._process_state = None
            document = self.telemetry.document()
            try:
                document["sources"] = self.sources.telemetry_facts(self)
            except Exception as error:
                document["sources"] = {"error": str(error)[:200]}
            self._telemetry_document = document
            _publish_json(Path(self.episode.capture.recorder.root) / "recorder-telemetry.json", document)
        except Exception as error:
            import sys
            print(f"RECORDER_TELEMETRY_WRITE_FAILED {error}", file=sys.stderr, flush=True)

    def _tail(self) -> None:
        """Keep servicing the sources, bounded, until they have caught up with the Teacher's end observation.

        Every pass pumps and collects first and asks `tail_ready` after it, so the drain that follows the last source
        message is in the record before the references are checked and the episode is sealed.
        """
        deadline = self.clock() + self.policy["finish_budget_s"]
        while not self.invalid:
            self.telemetry.begin_pass()
            try:
                with self.telemetry.phase("tail_pump"):
                    self.sources.pump(self)
                with self.telemetry.phase("tail_collect"):
                    self.sources.collect(self)
                self.episode.capture.check_health()
                if self.sources.tail_ready(self):
                    return
            except Exception as error:
                self.latch(self._reason(error))
                return
            finally:
                self.telemetry.end_pass()
            if self.clock() >= deadline:
                self.latch("RECORDER_TAIL_NOT_REACHED")
                return
            self.sleep(self.policy["poll_s"])

    def _check_sources(self) -> None:
        if not self.ready:
            if not any("CAPTURE" in item["reason"] or "NOT_READY" in item["reason"] for item in self.invalid):
                self.latch("RECORDER_CAPTURE_NEVER_STARTED")
            return
        try:
            self._counts = dict(self.sources.source_counts(self))
        except Exception as error:
            self.latch("RECORDER_SOURCE_COUNTS_UNAVAILABLE: " + self._reason(error))
            return
        for name in REQUIRED_SOURCES:
            if not self._counts.get(name):
                self.latch(f"RECORDER_SOURCE_MISSING: {name}")
        try:
            for issue in self.sources.final_issues(self):
                self.latch(issue)
        except Exception as error:
            self.latch("RECORDER_FINAL_CHECK_FAILED: " + self._reason(error))

    def _teacher_document(self) -> dict:
        return {"schema": _TEACHER_MANIFEST_SCHEMA, "teacher_start_observation": self.start_obs,
                "teacher_end_observation": self.end_obs}

    def _reference_check(self, *, window, steps, identity) -> dict:
        from .episode_qc import verify_teacher_references
        return verify_teacher_references(self._teacher_document(), identity=identity, window=window,
                                         physics_steps=steps)

    def _seal(self) -> None:
        episode = self.episode
        if not self.ready:
            self._close_episode()
            return
        if not self.invalid:
            try:
                # The adapter's retained samples are ordered dicts; the QC check wants plain dicts, as JSON gives it.
                steps = [dict(sample) for sample in self.sources.physics_steps(self)]
                check = self._reference_check(window=episode.capture.window, steps=steps, identity=episode.identity)
                if check["status"] != "PASS":
                    self.latch(check["reason"])
            except Exception as error:
                self.latch("RECORDER_REFERENCE_CHECK_FAILED: " + self._reason(error))
        self.require_teacher_events()
        if not self.stop_seen:
            self.latch("RECORDER_NORMAL_STOP_MISSING")
            self._close_episode()
            return
        terminal = self.terminal or {}
        passed = (terminal.get("teacher_task_result") == "PASS"
                  and terminal.get("teacher_execution_status") == "COMPLETED")
        if self.invalid:
            status, reason = "FAILED", "RECORDER_DATA_INVALID: " + self.invalid[0]["reason"]
        elif passed:
            status, reason = "PASSED", "completed"
        else:
            status, reason = "FAILED", "TEACHER_TASK_NOT_PASSED: " + str(terminal.get("teacher_task_result"))
        outcome = {"status": status, "reason": reason[:_REASON_CHARS], "task8_success": status == "PASSED",
                   "stopped_confirmed": True}
        try:
            episode.finish(float(self.sources.end_time_s(self)), outcome=outcome)
        except Exception as error:
            self.latch("RECORDER_SEAL_FAILED: " + self._reason(error), exception_chain=chain_text(error),
                       **self._queue_facts())
            return
        self.sealed = True
        self._seal_path = Path(episode.capture.recorder.root) / "seal.json"
        self._readback()

    def _close_episode(self) -> None:
        try:
            self.episode.close()
        except Exception as error:
            self.latch("RECORDER_CLOSE_FAILED: " + self._reason(error), exception_chain=chain_text(error),
                       **self._queue_facts())

    def _readback(self) -> None:
        """Verify the sealed files with the existing readers, then the Teacher references again from the files."""

        from .episode_assembly import episode_audit_pair
        from .episode_audit import verify_audit_manifest
        from .episode_qc import _raw_physics_samples, read_verified_rows
        from .recorder import verify_episode_seal

        root = Path(self.episode.capture.recorder.root)
        try:
            audit_manifest, scope = episode_audit_pair(root)
            verify_episode_seal(root / "seal.json", audit_manifest=audit_manifest, scope=scope)
            manifest = verify_audit_manifest(audit_manifest)
            if self.invalid:
                return
            events = read_verified_rows(root / "audit", "events.jsonl")
            check = self._reference_check(window=manifest["window"], steps=_raw_physics_samples(events),
                                          identity=manifest["identity"])
            if check["status"] != "PASS":
                self.latch("RECORDER_READBACK_" + check["reason"])
        except Exception as error:
            self.latch("RECORDER_READBACK_FAILED: " + self._reason(error), exception_chain=chain_text(error))

    def _inventory(self) -> dict:
        root = Path(self.episode.capture.recorder.root)
        inventory = {}
        for directory, _, files in os.walk(root):
            for name in sorted(files):
                path = Path(directory) / name
                digest = hashlib.sha256()
                try:
                    with path.open("rb") as stream:
                        for block in iter(lambda: stream.read(1 << 20), b""):
                            digest.update(block)
                    inventory[str(path.relative_to(root))] = {"sha256": digest.hexdigest(), "size": path.stat().st_size}
                except OSError as error:
                    inventory[str(path.relative_to(root))] = {"sha256": "0" * 64, "size": -1, "error": str(error)[:100]}
        return dict(sorted(inventory.items()))

    def _telemetry_summary(self) -> dict:
        try:
            summary = self.telemetry.summary()
            facts = getattr(self, "_telemetry_document", {}).get("sources", {})
            spooler = facts.get("spooler") or {}
            summary["spooler_max_callback_gap_ms"] = spooler.get("max_callback_gap_ms")
            receiver = facts.get("receiver") or {}
            summary["receiver_error"] = receiver.get("error")
            observer = facts.get("world_observer") or {}
            summary["world_gaps"] = observer.get("gaps")
            summary["world_rejections"] = observer.get("rejections")
            summary["start_gate"] = {cause: entry.get("passes") for cause, entry in (facts.get("start_gate") or {}).items()}
            latency = (facts.get("physics_receipts") or {}).get("latency_ms") or {}
            for leg in ("total", "publish_to_receipt"):
                block = latency.get(leg) or {}
                summary[f"physics_{leg}_p99_ms"], summary[f"physics_{leg}_max_ms"] = block.get("p99"), block.get("max")
            return summary
        except Exception:
            return {}

    def _write_result(self) -> None:
        invalid = bool(self.invalid)
        try:
            window = self.episode.capture.window if self.ready else None
        except Exception:
            window = None
        seal = None
        if self.sealed and self._seal_path is not None and self._seal_path.is_file():
            seal = {"path": str(self._seal_path),
                    "sha256": hashlib.sha256(self._seal_path.read_bytes()).hexdigest()}
        try:
            inventory = self._inventory() if invalid or seal is None else {}
        except Exception as error:
            inventory = {"__inventory_error__": {"sha256": "0" * 64, "size": -1, "error": str(error)[:100]}}
        document = {
            "schema": RESULT_SCHEMA, "status": "INVALID" if invalid else "VALID", "rc": self.rc,
            "reasons": list(self.invalid), "reason_count": self._invalid_total,
            # The Recorder never authorises export: that needs the Teacher PASS, an independent QC PASS and the commit.
            "export_eligible": False, "export_gate": "REJECTED" if invalid else "PENDING_INDEPENDENT_QC",
            "identity": self.identity.document(), "fault": self.faults.fault, "faults": self.faults.snapshot(),
            "policy_sha256": self.policy["policy_sha256"], "collection_start_s": self.collection_start_s,
            "listening": self.listening, "window": window, "seal": seal, "episode_root": str(self.episode.capture.recorder.root),
            "event_stream": {
                "accepted": self.monitor.accepted, "foreign": self.monitor.foreign,
                "last_seq": self.monitor.expected_seq - 1, "inbox_dropped": self._inbox_dropped,
                "inbox_capacity": self._capacity, "terminal": self.terminal, "stop_seen": self.stop_seen,
                "start_observation": self.start_obs, "end_observation": self.end_obs,
                "deferred_replayed": self._deferred_replayed,
                "deferred_first": None if self._deferred_first is None else list(self._deferred_first)},
            "sources": self._counts, "stall_telemetry": self._telemetry_summary(),
            "elapsed_s": None if self._began is None else round(self.clock() - self._began, 3),
            "pid": os.getpid(), "episode_inventory": inventory,
        }
        try:
            _publish_json(self.result_file, document)
        except (OSError, ValueError, TypeError) as error:
            import sys
            print(f"RECORDER_RESULT_WRITE_FAILED {error}", file=sys.stderr, flush=True)
