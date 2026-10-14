"""The offline episode engine: the Teacher event stream and the data sources of one attempt in, a sealed episode and a verdict out.

It consumes the Teacher event stream (`/so101/teacher/events`, replayed from the bag) and the data sources (`sources.py`) and
writes an isolated episode directory with the existing episode assembly and lossless writer, seals it and reads it back. Every defect
it finds is a verdict on the data (INVALID), never an input to the Teacher.

Result: `recorder-result.json` (schema `SO101_RECORDER_RESULT`, exclusive and durable). Return code: 0 sealed VALID, 3 INVALID (the
record is retained and rejected for export).

Recording window. `collection_start_s` is the simulation time at which the capture starts. The capture starts when the initial scene
association exists, which is derived from the Recorder's own read of the scene before the Teacher's SETUP. Teacher events other than
`scene_operation` that arrive before the capture started are not retained and make the data INVALID
(`RECORDER_NOT_READY_BEFORE_TEACHER_EVENT`). The end is the
Teacher's normal-stop clock, and the engine keeps feeding the sources until they have caught up to the Teacher's end observation
(bounded), so the window covers the end reference. `verify_teacher_references` is run before the seal and again on the sealed files.

This module is the engine of the live Recorder with its process discipline removed (ready file, stall telemetry, signal handling,
deferred events, sandbox faults): the live Recorder is gone from the run path.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import threading
import time
from pathlib import Path

from ...application.e2e_acceptance import MANIFEST_SCHEMA_VERSION, SCHEMA_TEACHER
from ..exception_chain import chain_text
from ..qc_session import qc_session
from ..teacher_event_stream import (
    EventStreamMonitor,
    StreamIdentity,
    TeacherEventError,
    decode_event,
)
from .policy import check_outputs_absent

RC_VALID, RC_INVALID = 0, 3
RESULT_SCHEMA = "SO101_RECORDER_RESULT"
REQUIRED_SOURCES = ("head", "wrist", "physics", "scene_state", "world", "joint_states")
#: a poll below this advances the replay by this much (a zero poll would never move the virtual clock)
MIN_STEP_S = 0.001
_MAX_REASONS = 16
_REASON_CHARS = 300
_CHAIN_FACTS = frozenset({"writer_error", "exception_chain"})


def _publish_json(path: Path, document: dict, *, replace: bool = False) -> None:
    """Exclusive, durable publication: the file either does not exist or is complete. `replace` swaps a complete file for the
    next complete one atomically; nothing else is ever replaced."""

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


class OfflineEngine:
    def __init__(self, *, episode, sources, policy, identity: StreamIdentity, result_file, clock, sleep) -> None:
        self.episode, self.sources, self.policy, self.identity = episode, sources, dict(policy), identity
        self.result_file = Path(result_file)
        self.clock, self.sleep = clock, sleep
        self.monitor = EventStreamMonitor(identity)
        self.invalid: list[dict] = []
        #: True once the replay itself latched a reason. A reason the scan latched before the replay (a loss in the raw bag) does not
        #: stop the Teacher events and the tail from reaching the capture: the window it claims has to be consistent to be sealed.
        self.replay_failed = False
        self._presetting = False
        self._invalid_total = 0
        self._lock = threading.Lock()
        self._inbox = collections.deque()
        self._capacity = self.policy["event_inbox_capacity"]
        self._inbox_dropped = 0
        self._overflow_latched = False
        self._stream_broken = False
        self._collect_failed = False
        self.start_obs = self.end_obs = self.terminal = None
        self.stop_seen = False
        self._event_types: dict = {}
        self._last_seq = 0
        self._goal_phase_begin_seen = False
        self._early_first = None    # the first Teacher event that arrived before the capture started: (type, seq, monotonic_ns)
        self._early_count = 0
        self.ready = False          # the capture has started
        self.collection_start_s = None
        self.sealed = False
        self._stop_reason = None
        self._began = None
        self._seal_path = None
        self._counts: dict = {}
        self.rc = None
        self.passes = 0

    # ---- ingress ---------------------------------------------------------------------------------------------------

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

        The verdict is sticky for the whole run, so nothing here poisons the capture: a healthy capture is still sealed, as a FAILED
        record naming the first reason, and a capture that failed on its own simply cannot seal.
        """

        text = (str(reason) or "RECORDER_DATA_INVALID")[:_REASON_CHARS]
        with self._lock:
            if not self._presetting:
                self.replay_failed = True
            self._invalid_total += 1
            if len(self.invalid) < _MAX_REASONS and not (self.invalid and self.invalid[-1]["reason"] == text):
                entry = {"reason": text, "monotonic_ns": time.monotonic_ns()}
                # the exception chains of writer and seal failures are longer than an ordinary fact
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
            self.sources.pump(self)
        except Exception as error:
            self.latch(self._reason(error))
        self._process_events()
        if not self.ready:
            self._try_start()
        if self.ready and not self._collect_failed:
            self._collect()

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

    def _take_events(self) -> list:
        with self._lock:
            if not self._inbox:
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
            # A Teacher event before the capture started: the episode needs a verified reset that the capture covers, so the data
            # is INVALID (named at the finish, with the start gate). Scene operations are never refused: the capture starts from them.
            if self._early_first is None:
                self._early_first = (kind, event["seq"], time.monotonic_ns())
            self._early_count += 1
        else:
            self._retain_event(event)
        if kind == "terminal":
            self.terminal = payload

    def _retain_event(self, event) -> None:
        try:
            # Scene operations always reach source alignment: the rows after them need their associations, and a missing one would only
            # add a second, misleading reason (L2 81fa2857). Everything else is retained only while the data is valid.
            if not self.replay_failed or event["type"] == "scene_operation":
                self.sources.on_teacher_event(self, event)
        except Exception as error:
            self.latch("RECORDER_EVENT_RETENTION_FAILED: " + self._reason(error))

    def event_summary(self) -> dict:
        """Every V2 event this engine accepted, in order and without a gap (retained or not): sealed for QC."""
        return {"schema": "SO101_TEACHER_EVENT", "accepted": sum(self._event_types.values()),
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
        check_outputs_absent(self.result_file)

    def process(self, node, preset_reasons=()) -> int:
        """Replay the attempt: one `step` per poll of virtual time until the Teacher's terminal event, the end of the bag or the frozen
        maximum duration; then finalize. Returns the return code."""
        self.check_outputs_absent()
        self._began = self.clock()
        self.passes = 0
        try:
            self.sources.prepare(self)
        except Exception as error:
            self.latch("RECORDER_SOURCE_CONSTRUCTION_FAILED: " + self._reason(error))
        self._presetting = True
        for reason in preset_reasons:
            self.latch(reason)
        self._presetting = False
        step_s = max(self.policy["poll_s"], MIN_STEP_S)
        while True:
            try:
                self.step()
            except Exception as error:
                self.latch("RECORDER_STEP_FAILED: " + self._reason(error))
            self.passes += 1
            if self.terminal is not None:
                break
            if node.exhausted:
                self._stop_reason = "OFFLINE_BAG_ENDED_WITHOUT_TERMINAL"
                break
            if self.clock() - self._began > self.policy["max_duration_s"]:
                self._stop_reason = "RECORDER_MAX_DURATION_EXCEEDED"
                break
            self.sleep(step_s)
        return self.finalize()

    def finalize(self) -> int:
        """Catch up, check, seal, read back, write the result. Always leaves a retained record; never raises."""

        try:
            if self._early_first is not None:
                kind, seq, _ = self._early_first
                try:
                    gate = json.dumps(self.sources.start_gate_summary(self), sort_keys=True)
                except Exception:
                    gate = "unavailable"
                self.latch("RECORDER_NOT_READY_BEFORE_TEACHER_EVENT", event_type=kind, seq=seq,
                           capture_started=self.episode.capture.started, held_events=self._early_count,
                           ready_means="LISTENING only, not capture started", start_gate=gate)
            if self.terminal is None:
                self.latch(self._stop_reason or "RECORDER_NO_TERMINAL_EVENT")
            elif self.ready and not self.replay_failed:
                self._tail()
            self._check_sources()
            # The seal and the readback of what was just sealed verify the same unchanged files through the same verifiers: inside one
            # session each verifier runs once. The independent check of the sealed episode is the fresh-process QC, which never shares
            # a session with this process.
            with qc_session():
                self._seal()
        except Exception as error:
            self.latch("RECORDER_FINALIZE_FAILED: " + self._reason(error))
        finally:
            try:
                self.sources.close()
            except Exception as error:
                self.latch("RECORDER_SOURCE_CLOSE_FAILED: " + self._reason(error))
        self.rc = RC_INVALID if self.invalid else RC_VALID
        self._write_result()
        return self.rc

    def _tail(self) -> None:
        """Keep servicing the sources, bounded, until they have caught up with the Teacher's end observation.

        Every pass pumps and collects first and asks `tail_ready` after it, so the drain that follows the last source
        message is in the record before the references are checked and the episode is sealed.
        """
        deadline = self.clock() + self.policy["finish_budget_s"]
        while not self.replay_failed:
            try:
                self.sources.pump(self)
                self.sources.collect(self)
                self.episode.capture.check_health()
                if self.sources.tail_ready(self):
                    return
            except Exception as error:
                self.latch(self._reason(error))
                return
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
        return {"schema": SCHEMA_TEACHER, "schema_version": MANIFEST_SCHEMA_VERSION, "teacher_start_observation": self.start_obs,
                "teacher_end_observation": self.end_obs}

    def _reference_check(self, *, window, steps, identity) -> dict:
        from ..episode_qc import verify_teacher_references
        return verify_teacher_references(self._teacher_document(), identity=identity, window=window,
                                         physics_steps=steps)

    def _seal(self) -> None:
        episode = self.episode
        if not self.ready:
            self._close_episode()
            return
        if not self.replay_failed:
            self._pre_seal_reference_check()
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
        outcome = {"status": status, "reason": reason[:_REASON_CHARS], "pick_place_validation_success": status == "PASSED",
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

    def _pre_seal_reference_check(self) -> None:
        """The Teacher-reference check over the recording as it stands, before the seal.

        It runs in a session of its own: the events it parses are about a gigabyte of Python objects and the file grows before the
        seal reads it again (the recorder queue's last row), so that parse can never be reused. Nested inside the finalize session,
        this one is a new top of the stack and is dropped, with the parse and the samples copied from it, before `episode.finish`.
        """
        episode = self.episode
        with qc_session():
            try:
                # The adapter's retained samples are ordered dicts; the QC check wants plain dicts, as JSON gives it.
                steps = [dict(sample) for sample in self.sources.physics_steps(self)]
                check = self._reference_check(window=episode.capture.window, steps=steps, identity=episode.identity)
                if check["status"] != "PASS":
                    self.latch(check["reason"])
            except Exception as error:
                self.latch("RECORDER_REFERENCE_CHECK_FAILED: " + self._reason(error))

    def _close_episode(self) -> None:
        try:
            self.episode.close()
        except Exception as error:
            self.latch("RECORDER_CLOSE_FAILED: " + self._reason(error), exception_chain=chain_text(error),
                       **self._queue_facts())

    def _readback(self) -> None:
        """Verify the sealed files with the existing readers, then the Teacher references again from the files."""

        from ..episode_assembly import episode_audit_pair
        from so101_demo.act.episode_audit.verification import verify_audit_manifest
        from ..episode_qc import _raw_physics_samples, read_verified_rows_sharing_strict
        from ..recorder import verify_episode_seal

        root = Path(self.episode.capture.recorder.root)
        try:
            audit_manifest, scope = episode_audit_pair(root)
            verify_episode_seal(root / "seal.json", audit_manifest=audit_manifest, scope=scope)
            manifest = verify_audit_manifest(audit_manifest)
            if self.replay_failed:
                return
            events = read_verified_rows_sharing_strict(root / "audit", "events.jsonl")
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
            "schema": RESULT_SCHEMA, "schema_version": 1, "status": "INVALID" if invalid else "VALID", "rc": self.rc,
            "reasons": list(self.invalid), "reason_count": self._invalid_total,
            # The engine never authorises export: that needs the Teacher PASS, an independent QC PASS and the commit.
            "export_eligible": False, "export_gate": "REJECTED" if invalid else "PENDING_INDEPENDENT_QC",
            "identity": self.identity.document(),
            # The document keeps the shape its readers know (schema version 1): there is no fault injector, no live listening state and no stall
            # telemetry any more, so these are the constants an offline run always had.
            "fault": "none", "faults": {"fault": "none", "physics_chunks_dropped": 0, "physics_chunks_seen": 0},
            "policy_sha256": self.policy["policy_sha256"], "collection_start_s": self.collection_start_s,
            "listening": True, "window": window, "seal": seal, "episode_root": str(self.episode.capture.recorder.root),
            "event_stream": {
                "accepted": self.monitor.accepted, "foreign": self.monitor.foreign,
                "last_seq": self.monitor.expected_seq - 1, "inbox_dropped": self._inbox_dropped,
                "inbox_capacity": self._capacity, "terminal": self.terminal, "stop_seen": self.stop_seen,
                "start_observation": self.start_obs, "end_observation": self.end_obs,
                "deferred_replayed": 0,
                "deferred_first": None if self._early_first is None else list(self._early_first)},
            "sources": self._counts, "stall_telemetry": {},
            "elapsed_s": None if self._began is None else round(self.clock() - self._began, 3),
            "pid": 0, "episode_inventory": inventory,
        }
        try:
            _publish_json(self.result_file, document)
        except (OSError, ValueError, TypeError) as error:
            import sys
            print(f"RECORDER_RESULT_WRITE_FAILED {error}", file=sys.stderr, flush=True)
