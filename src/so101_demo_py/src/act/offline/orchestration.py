"""The data side of one Teacher attempt after the switch to raw-log recording.

Before the Teacher: one record-only process (`ros2 bag record`, owned by `PilotRecording`) is started and waited for a bounded time;
the Teacher starts whatever happened to it. After the Teacher ended (phase 1 of the two-phase collection): the bag is closed, a
recording receipt binds every raw file, and the data side ends PENDING_QC; no processor runs here.

Direction of dependence (unchanged from the live Recorder's orchestration): the Teacher never waits for, reads from or is stopped by
anything here after its own start. Every defect on this side is a verdict on the data (INVALID) and never an input to the Teacher.
Nothing in this module imports ROS or the Teacher's modules (the processor runs in its own process).

Faults (diagnostic mode only, every output beneath `<run>/fault-sandbox/`):

* `recorder_absent`  - no bag is recorded;
* `recorder_late`    - the bag starts after the Teacher's first command;
* `queue_overflow`   - a burst of consecutive physics chunks is missing from a sandbox copy of the bag;
* `source_gap`       - a burst of consecutive arm `controller_state` messages is missing from a sandbox copy of the bag;
* `output_write_failure` - the processor's output directory is read-only.

Each of them gives a passing Teacher and INVALID data.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from ..collection_orchestration import RecorderOutcome, require_under_sandbox
from .pilot import PilotRecording

PROCESSOR_ROLE = "act-offline-processor"
RAW_ROLE = "act-raw-pilot"
#: `recorder_late` starts the bag this long after the Teacher's setup evidence appeared (its first command follows within ~2 s).
LATE_START_DELAY_S = 5.0
#: messages dropped by the bag faults
FAULT_DROP_COUNT = {"queue_overflow": 40, "source_gap": 60}
FAULT_TOPIC = {"queue_overflow": "/so101/simulation/physics_step_chunks", "source_gap": "/arm_controller/controller_state"}
BAG_FAULTS = tuple(FAULT_TOPIC)
#: faults the phase-2 processor applies (to a copy under its own output directory); phase 1 records them like a fault-free attempt
DEFERRED_FAULTS = BAG_FAULTS + ("output_write_failure",)
_REASON_CHARS = 300
LEASE_FIELDS = ("batch_id", "coordinator_epoch", "worker_id", "worker_generation", "point_id", "attempt_id", "lease_generation",
                "lease_issued_monotonic_s", "lease_deadline_monotonic_s")


def drop_bag_messages(source, destination, *, topic: str, count: int) -> dict:
    """Copy the bag at `source` to `destination`, leaving out `count` consecutive messages of `topic` from the middle of its stream.

    The copy keeps every other message and its stamp, so what the processor then sees is exactly a source that lost a burst."""
    from .bag_io import BagWriter, bag_info, read_messages

    info = bag_info(source)
    total = info["topics"].get(topic, {}).get("count", 0)
    if total <= count + 2:
        raise ValueError(f"FAULT_BAG_TOPIC_TOO_SHORT: {topic} has {total} messages")
    first = (total - count) // 2
    dropped = range(first, first + count)
    writer = BagWriter(destination)
    seen = 0
    dropped_stamps = []
    try:
        for name, type_name, stamp, data in read_messages(source):
            writer.create(name, type_name)
            if name == topic:
                index, seen = seen, seen + 1
                if index in dropped:
                    dropped_stamps.append(stamp)
                    continue
            writer.write_serialized(name, data, stamp)
    finally:
        writer.close()
    return {"topic": topic, "dropped": len(dropped_stamps), "first_dropped_stamp_ns": dropped_stamps[0],
            "last_dropped_stamp_ns": dropped_stamps[-1]}


def write_orchestration_record(point_root, facts: dict, reason) -> bool:
    """Write `<point_root>/recorder-orchestration.json` once (exclusive create, fsync). False when it cannot be written or already
    exists; the data side never decides control's result."""
    try:
        payload = json.dumps({"schema": "SO101_RECORDER_ORCHESTRATION", "schema_version": 1, "reason": reason, **facts},
                             sort_keys=True, default=str, allow_nan=False).encode() + b"\n"
        with open(Path(point_root) / "recorder-orchestration.json", "xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except (OSError, ValueError, TypeError):
        return False


class OfflineCollection:
    """One attempt's phase-1 data lifecycle: record the bag, then (after the Teacher) close it and bind it in the recording
    receipt. `processes` is the Worker's owned process tree or a fake with its surface: `start(spec, environment=)`, `exit_code`,
    `wait_exit(identity, timeout_s)`, `terminate(identity, grace_s)`, `stop(identity)`."""

    def __init__(self, *, processes, point_root, sandbox_root, fault: str, environment: dict, spec_factory, inputs_manifest,
                 scope, identity: dict, policy: dict, clock=time.monotonic, sleep=time.sleep,
                 pilot_factory=None,
                 late_delay_s: float = LATE_START_DELAY_S, defer_faults: bool = False) -> None:
        self._processes = processes
        self._point_root = Path(point_root)
        self._fault = fault
        self._sandbox_root = None if sandbox_root is None else Path(sandbox_root)
        #: `defer_faults` (the two-phase worker): a bag or output fault is applied by the phase-2 processor, so phase 1 records it in
        #: the point root like any attempt; only the recorder faults use the fault sandbox
        self._in_point_root = fault == "none" or (defer_faults and fault in DEFERRED_FAULTS)
        #: where this attempt's data side writes: the point root itself, or a directory inside the fault sandbox
        self._base = self._point_root if self._in_point_root else self._sandbox_root / str(identity["attempt_id"])
        self._environment = dict(environment)
        self._spec_factory = spec_factory
        self._inputs_manifest = Path(inputs_manifest)
        self._scope = Path(scope)
        self._identity = dict(identity)
        self._policy = policy
        self._clock, self._sleep = clock, sleep
        self._pilot_factory = pilot_factory
        self._late_delay_s = float(late_delay_s)
        self._pilot = None
        self._late_thread = None
        #: `recorder_late` evidence (system-clock ns): when the Teacher's setup evidence was seen, when the bag was started
        self.late_evidence: dict = {}
        self.ready = False
        self.late_started = False
        self.ready_reason: str | None = None
        self.start_error: str | None = None
        self.teacher_started = False
        self.teacher_ended = False
        self.events: list[str] = []
        self.identity_of_pilot = None
        if fault != "none":
            # a requested fault always needs its sandbox, even when this attempt records into the point root
            if self._in_point_root:
                require_under_sandbox(self._sandbox_root)
            else:
                require_under_sandbox(self._sandbox_root, self._base, self._base / "raw", self._base / "out")

    # ---- before the Teacher -------------------------------------------------------------------------------------

    @property
    def raw_root(self) -> Path:
        return self._base / "raw"

    def start_before_teacher(self) -> None:
        """Start the record-only process and wait a bounded time for RECORDING. Returns whatever happened; never raises."""
        if self._fault == "recorder_absent":
            self.events.append("recorder_not_started:fault_recorder_absent")
            return
        if self._fault == "recorder_late":
            self.events.append("recorder_deferred:fault_recorder_late")
            return
        self._start()

    def _start(self) -> None:
        try:
            pilot = (self._pilot_factory or PilotRecording)(
                processes=self._processes, root=self.raw_root, environment=self._environment,
                spec_factory=lambda argv: self._spec_factory(RAW_ROLE, argv), timeout_s=float(self._policy["ready_timeout_s"]),
                clock=self._clock, sleep=self._sleep)
        except Exception as error:   # noqa: BLE001 - a defect on the data side is a verdict on the data
            self.start_error = ("RAW_PILOT_START_FAILED: " + (str(error) or type(error).__name__))[:_REASON_CHARS]
            self.events.append("recorder_start_failed")
            return
        self._pilot = pilot   # from here on `finish` closes it, whatever `start` did
        try:
            pilot.start()
            self.events.append("recorder_started")
            self.ready = bool(pilot.ready)
            if not self.ready:
                self.ready_reason = (pilot.failure or "RAW_PILOT_NOT_RECORDING")[:_REASON_CHARS]
        except Exception as error:   # noqa: BLE001
            self.ready_reason = ("RAW_PILOT_START_FAILED: " + (str(error) or type(error).__name__))[:_REASON_CHARS]
            self.events.append("recorder_start_failed")
        self.events.append("recorder_ready" if self.ready else "recorder_not_ready:" + str(self.ready_reason))

    def teacher_started_now(self) -> None:
        """The Teacher has been started. From here on this object makes no blocking call until it ended."""
        self.teacher_started = True

    def arm_late_start(self, trigger: Path) -> None:
        """`recorder_late`: start the bag from a side thread once the Teacher's setup evidence exists and `late_delay_s` passed."""
        if self._fault != "recorder_late" or self._late_thread is not None:
            return

        def late_start():
            deadline = self._clock() + 120.0
            while self._clock() < deadline and not self.teacher_ended:
                if Path(trigger).exists():
                    self.late_evidence["trigger_seen_system_ns"] = time.time_ns()
                    self.late_evidence["delay_s"] = self._late_delay_s
                    self._sleep(self._late_delay_s)
                    if not self.teacher_ended:
                        self.start_late()
                    return
                self._sleep(0.02)

        self._late_thread = threading.Thread(target=late_start, name="raw-recorder-late-start", daemon=True)
        self._late_thread.start()

    def start_late(self) -> bool:
        """`recorder_late`: start the bag now, after the Teacher's first command. It is never waited for by the Teacher."""
        if self._fault != "recorder_late" or self._pilot is not None or self.start_error is not None:
            return False
        self.late_evidence["start_requested_system_ns"] = time.time_ns()
        self._start()
        self.late_started = self._pilot is not None
        return self.late_started

    # ---- after the Teacher --------------------------------------------------------------------------------------

    def _late_bag_first_stamp(self) -> dict:
        """The late bag's first message stamp (system clock, ns): evidence that it starts after the Teacher's setup evidence."""
        try:
            from .bag_io import bag_info

            return {"bag_first_stamp_ns": bag_info(self.raw_root / "bag")["starting_time_ns"]}
        except Exception as error:   # noqa: BLE001
            return {"bag_first_stamp_error": repr(error)[:120]}

    def retire(self) -> bool:
        """A cancelled attempt ends its bag recorder too, best effort. Returns whether the recorder is PROVEN stopped: its process
        exited and its stop stats were written (design 2026-10-10 section 1.2). Nothing started is vacuously proven."""
        from .raw_recorder import STATS_SCHEMA
        self.teacher_ended = True
        pilot = self._pilot
        if pilot is None:
            return True
        if getattr(pilot, "identity", "started") is None:
            return True                                        # the recorder process was never started
        try:
            facts = pilot.finish()
        except Exception:   # noqa: BLE001
            return False
        failure = facts.get("failure") if isinstance(facts, dict) else None
        return (isinstance(facts, dict) and facts.get("rc") is not None and facts.get("schema") == STATS_SCHEMA
                and not str(failure or "").startswith("RAW_PILOT_STOP_FAILED"))

    def finish(self, *, lease: dict, skip_processing: str | None = None) -> RecorderOutcome:
        """Phase 1, after the Teacher ended: close the bag and seal the data side as PENDING_QC. Never raises.

        No processor is started and none is waited for: the episode and the QC are built later, by the phase-2 processor, from the
        closed bag. The recording receipt (`raw/recording-receipt.json`) binds every raw file and the documents the processor needs.
        `lease` is the Worker's lease at this instant; `skip_processing` is the reason (a data verdict already made) for which the bag
        is closed and the data stays INVALID with no receipt."""
        return self._run_finish(lease, skip_processing)

    def _run_finish(self, lease: dict, skip_processing) -> RecorderOutcome:
        self.teacher_ended = True
        facts: dict = {"fault": self._fault, "events": self.events, "ready": self.ready, "mode": "RAW_BAG_OFFLINE",
                       "policy_sha256": self._policy.get("policy_sha256")}
        try:
            return self._finish(facts, skip_processing, {name: lease[name] for name in LEASE_FIELDS})
        except Exception as error:   # noqa: BLE001
            return RecorderOutcome("INVALID", ("RECORDER_ORCHESTRATION_FAILED: " + (str(error) or type(error).__name__))
                                   [:_REASON_CHARS], facts)

    def _finish(self, facts: dict, skip_processing, lease: dict) -> RecorderOutcome:
        if self._late_thread is not None:
            self._late_thread.join(timeout=float(self._policy["ready_timeout_s"]) + 5.0)
        pilot = self._pilot
        recorded = {} if pilot is None else pilot.finish()
        facts["raw_pilot"] = recorded
        if pilot is None:
            reason = self.start_error or ("RECORDER_ABSENT" if self._fault == "recorder_absent" else "RECORDER_NEVER_STARTED")
            return RecorderOutcome("INVALID", reason, facts)
        if self._fault == "recorder_late":
            facts["late_started"] = self.late_started
            facts["late_evidence"] = dict(self.late_evidence, **self._late_bag_first_stamp())
            return RecorderOutcome("INVALID", "RECORDER_STARTED_AFTER_TEACHER", facts)
        if not self.ready:
            return RecorderOutcome("INVALID", self.ready_reason or "RECORDER_NOT_READY_BEFORE_TEACHER_START", facts)
        if recorded.get("failure") or recorded.get("closed") is not True or recorded.get("rc") not in (0, None):
            return RecorderOutcome("INVALID", ("RAW_BAG_NOT_CLOSED_CLEANLY: " + json.dumps(
                {key: recorded.get(key) for key in ("failure", "closed", "rc", "missing_core_topics")}, sort_keys=True,
                default=str))[:_REASON_CHARS], facts)
        if skip_processing is not None:
            return RecorderOutcome("INVALID", skip_processing, facts)
        return self._seal_pending(facts, lease)

    # ---- phase 1: the recording receipt -------------------------------------------------------------------------------

    def _seal_pending(self, facts: dict, lease: dict) -> RecorderOutcome:
        """The bag is closed cleanly: bind it and the processor's documents in the recording receipt. The data stays PENDING_QC."""
        from .recording_receipt import write_recording_receipt

        bag = self.raw_root / "bag"
        if not (bag / "metadata.yaml").is_file():
            return RecorderOutcome("INVALID", "RAW_BAG_MISSING", facts)
        (self.raw_root / "lease.json").write_text(json.dumps(lease, sort_keys=True) + "\n")
        if self._fault != "none":
            facts["fault_deferred_to_processing"] = self._fault   # a diagnostic bag/output fault is applied by the phase-2 processor
        # The orchestration record carries the deferred fault, so the receipt must hash it: it is written first and, because the
        # receipt's own facts cannot be inside a file the receipt hashes, without them.
        record = self._point_root / "recorder-orchestration.json"
        write_orchestration_record(self._point_root, dict(facts, act_data_status="PENDING_QC"), None)
        facts["recording_receipt"] = write_recording_receipt(
            self._base, lease_identity=lease, identity=self._identity, inputs_manifest=self._inputs_manifest, scope=self._scope,
            teacher_manifest=self._point_root / "dynamic" / "dynamic-execute-manifest.json", orchestration_record=record)
        return RecorderOutcome("PENDING_QC", None, facts)


__all__ = ["OfflineCollection", "drop_bag_messages", "PROCESSOR_ROLE", "RAW_ROLE", "BAG_FAULTS"]
