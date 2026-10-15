"""The data side of one Teacher attempt after the switch to raw-log recording.

Before the Teacher: one record-only process (`ros2 bag record`, owned by `PilotRecording`) is started and waited for a bounded time;
the Teacher starts whatever happened to it. After the Teacher ended (phase 1 of the two-phase collection): the bag is closed, a
recording receipt binds every raw file, and the data side ends PENDING_QC; no processor runs here. The retired inline form
(`finish_inline`: the offline processor builds the sealed episode and runs the fresh-process QC inside the attempt) is not reachable
from the shard task path and is deleted with the inline mode.

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
from .engine import RESULT_SCHEMA
from .pilot import PilotRecording

PROCESSOR_ROLE = "act-offline-processor"
RAW_ROLE = "act-raw-pilot"
#: The processor builds the episode and runs the fresh QC in about ten minutes for a 100 s episode; this bounds a stuck one.
PROCESSING_TIMEOUT_S = 1200.0
PROCESSOR_TERM_GRACE_S = 10.0
#: Time that must remain on the lease after the processor ended, for everything the Worker still does before the stage deadline:
#: the SIGTERM grace of a processor that hit its cap (10 s), the ResultStore seal (the memo path measured under 2 s; a full
#: recomputation fallback is not budgeted), the `begin_finalizing` acknowledgement (`result_ack_timeout_s` = 10 s), and slack for
#: scheduling and the heartbeat round trip. 60 s is six times the sum of the two acknowledged bounds.
SEAL_MARGIN_S = 60.0
#: A processor given less than this cannot even scan the bag (about 15 s) and start its replay; it is not started.
MIN_PROCESSING_S = 60.0
#: `recorder_late` starts the bag this long after the Teacher's setup evidence appeared (its first command follows within ~2 s).
LATE_START_DELAY_S = 5.0
#: messages dropped by the bag faults
FAULT_DROP_COUNT = {"queue_overflow": 40, "source_gap": 60}
FAULT_TOPIC = {"queue_overflow": "/so101/simulation/physics_step_chunks", "source_gap": "/arm_controller/controller_state"}
BAG_FAULTS = tuple(FAULT_TOPIC)
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


def read_processor_result(path, identity: dict):
    """The processor's `recorder-result.json` as a validated document, or the reason string it could not be trusted."""
    try:
        document = json.loads(Path(path).read_bytes())
    except FileNotFoundError:
        return "OFFLINE_RESULT_MISSING"
    except (OSError, ValueError):
        return "OFFLINE_RESULT_UNREADABLE"
    if type(document) is not dict or document.get("schema") != RESULT_SCHEMA:
        return "OFFLINE_RESULT_SCHEMA_INVALID"
    observed = document.get("identity")
    if type(observed) is not dict or any(observed.get(key) != value for key, value in identity.items()):
        return "OFFLINE_RESULT_IDENTITY_MISMATCH"
    if document.get("status") not in ("VALID", "INVALID"):
        return "OFFLINE_RESULT_STATUS_INVALID"
    if document["status"] == "VALID" and type(document.get("seal")) is not dict:
        return "OFFLINE_RESULT_VALID_WITHOUT_SEAL"
    return document


class OfflineCollection:
    """One attempt's data lifecycle: record, then (after the Teacher) process. `processes` is the Worker's owned process tree or a
    fake with its surface: `start(spec, environment=)`, `exit_code`, `wait_exit(identity, timeout_s)`, `terminate(identity, grace_s)`,
    `stop(identity)`."""

    def __init__(self, *, processes, point_root, sandbox_root, fault: str, environment: dict, spec_factory, inputs_manifest,
                 scope, identity: dict, policy: dict, clock=time.monotonic, sleep=time.sleep,
                 python: str | None = None, pilot_factory=None, bag_fault=None,
                 processing_timeout_s: float = PROCESSING_TIMEOUT_S, late_delay_s: float = LATE_START_DELAY_S,
                 memo_check=None, on_recorder_stopped=None) -> None:
        self._processes = processes
        self._on_recorder_stopped = on_recorder_stopped
        self._point_root = Path(point_root)
        self._fault = fault
        self._sandbox_root = None if sandbox_root is None else Path(sandbox_root)
        #: where this attempt's data side writes: the point root itself, or a directory inside the fault sandbox
        self._base = self._point_root if fault == "none" else self._sandbox_root / str(identity["attempt_id"])
        self._environment = dict(environment)
        self._spec_factory = spec_factory
        self._inputs_manifest = Path(inputs_manifest)
        self._scope = Path(scope)
        self._identity = dict(identity)
        self._policy = policy
        self._clock, self._sleep = clock, sleep
        self._python = python
        self._pilot_factory = pilot_factory
        self._bag_fault = bag_fault
        self._processing_timeout_s = float(processing_timeout_s)
        self._late_delay_s = float(late_delay_s)
        self._memo_check = memo_check
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

    def _recorder_stopped(self) -> None:
        """Tell the owner the bag recorder has stopped (a status side channel). It never changes the data verdict."""
        callback = self._on_recorder_stopped
        if callback is not None:
            try:
                callback()
            except Exception:   # noqa: BLE001
                pass

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
        finally:
            self._recorder_stopped()
        failure = facts.get("failure") if isinstance(facts, dict) else None
        return (isinstance(facts, dict) and facts.get("rc") is not None and facts.get("schema") == STATS_SCHEMA
                and not str(failure or "").startswith("RAW_PILOT_STOP_FAILED"))

    def finish(self, *, lease: dict, skip_processing: str | None = None, deadline_s: float | None = None) -> RecorderOutcome:
        """Phase 1, after the Teacher ended: close the bag and seal the data side as PENDING_QC. Never raises.

        No processor is started and none is waited for: the episode and the QC are built later, by the phase-2 processor, from the
        closed bag. The recording receipt (`raw/recording-receipt.json`) binds every raw file and the documents the processor needs.
        `lease` is the Worker's lease at this instant; `skip_processing` is the reason (a data verdict already made) for which the bag
        is closed and the data stays INVALID with no receipt. `deadline_s` is accepted for the callers' signature and unused: phase 1
        has no processing budget."""
        return self._run_finish(lease, skip_processing, deadline_s, inline=False)

    def finish_inline(self, *, lease: dict, skip_processing: str | None = None, deadline_s: float | None = None) -> RecorderOutcome:
        """The retired inline form: close the bag and run the processor inside the attempt. Not reachable from the shard task path
        (plan task 11 deletes it).

        `deadline_s` is the lease deadline on the same clock as `clock`: the processor's wait is capped at the time left on it minus
        `SEAL_MARGIN_S`, so the Teacher's result is always sealed in time (the data is INVALID instead)."""
        return self._run_finish(lease, skip_processing, deadline_s, inline=True)

    def _run_finish(self, lease: dict, skip_processing, deadline_s, *, inline: bool) -> RecorderOutcome:
        self.teacher_ended = True
        facts: dict = {"fault": self._fault, "events": self.events, "ready": self.ready, "mode": "RAW_BAG_OFFLINE",
                       "policy_sha256": self._policy.get("policy_sha256")}
        try:
            return self._finish(facts, skip_processing, {name: lease[name] for name in LEASE_FIELDS}, deadline_s, inline)
        except Exception as error:   # noqa: BLE001
            return RecorderOutcome("INVALID", ("RECORDER_ORCHESTRATION_FAILED: " + (str(error) or type(error).__name__))
                                   [:_REASON_CHARS], facts)

    def _finish(self, facts: dict, skip_processing, lease: dict, deadline_s=None, inline: bool = True) -> RecorderOutcome:
        if self._late_thread is not None:
            self._late_thread.join(timeout=float(self._policy["ready_timeout_s"]) + 5.0)
        pilot = self._pilot
        try:
            recorded = {} if pilot is None else pilot.finish()
        finally:
            self._recorder_stopped()
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
        if inline:
            return self._process(facts, lease, deadline_s)
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
        facts["recording_receipt"] = write_recording_receipt(
            self._base, lease_identity=lease, identity=self._identity, inputs_manifest=self._inputs_manifest, scope=self._scope,
            teacher_manifest=self._point_root / "dynamic" / "dynamic-execute-manifest.json")
        return RecorderOutcome("PENDING_QC", None, facts)

    # ---- the offline processor ----------------------------------------------------------------------------------

    def _process(self, facts: dict, lease: dict, deadline_s=None) -> RecorderOutcome:
        bag = self.raw_root / "bag"
        if not (bag / "metadata.yaml").is_file():
            return RecorderOutcome("INVALID", "RAW_BAG_MISSING", facts)
        budget_s = self._processing_timeout_s
        if deadline_s is not None:
            left = float(deadline_s) - self._clock() - SEAL_MARGIN_S
            facts["processing_budget"] = {"lease_left_s": round(float(deadline_s) - self._clock(), 3), "seal_margin_s": SEAL_MARGIN_S,
                                          "cap_s": self._processing_timeout_s, "budget_s": round(min(budget_s, left), 3)}
            if left < MIN_PROCESSING_S:
                return RecorderOutcome("INVALID", f"OFFLINE_PROCESSOR_NO_TIME_LEFT: {max(left, 0.0):.0f}s", facts)
            budget_s = min(budget_s, left)
        if self._fault in BAG_FAULTS:
            copy = self._base / "fault-bag"
            self._base.mkdir(parents=True, exist_ok=True)
            facts["bag_fault"] = (self._bag_fault or drop_bag_messages)(bag, copy, topic=FAULT_TOPIC[self._fault], count=FAULT_DROP_COUNT[self._fault])
            bag = copy
        out = self._point_root if self._fault == "none" else self._base / "out"
        qc_output = self._point_root / "qc-report.json" if self._fault == "none" else out / "offline-qc-report.json"
        lease_file = self.raw_root / "lease.json"
        lease_file.write_text(json.dumps(lease, sort_keys=True) + "\n")
        out.mkdir(parents=True, exist_ok=True)
        read_only = self._fault == "output_write_failure"
        argv = (self._python or _python(), "-m", "so101_demo.cli.act_offline_episode",
                "--bag", str(bag), "--inputs", str(self._inputs_manifest), "--out", str(out), "--lease", str(lease_file),
                "--scope", str(self._scope), "--record-stats", str(self.raw_root / "record-stats.json"),
                "--teacher-manifest", str(self._point_root / "dynamic" / "dynamic-execute-manifest.json"),
                "--qc-output", str(qc_output))
        facts["processor"] = {"argv_tail": list(argv[2:4]), "out": str(out), "bag": str(bag), "qc_output": str(qc_output)}
        returncode = None
        began = time.monotonic()
        if read_only:
            os.chmod(out, 0o555)   # the processor must fail to write its episode
        try:
            identity = self._processes.start(self._spec_factory(PROCESSOR_ROLE, argv), environment=self._environment)
            returncode = self._processes.wait_exit(identity, budget_s)
            if returncode is None:
                facts["processor"]["timed_out"] = True
                returncode = self._processes.terminate(identity, PROCESSOR_TERM_GRACE_S)
                self._retire(identity)
                return RecorderOutcome("INVALID", f"OFFLINE_PROCESSOR_TIMEOUT: {budget_s:.0f}s", facts)
            self._retire(identity)
        except Exception as error:   # noqa: BLE001
            return RecorderOutcome("INVALID", ("OFFLINE_PROCESSOR_START_FAILED: " + (str(error) or type(error).__name__))
                                   [:_REASON_CHARS], facts)
        finally:
            if read_only:
                os.chmod(out, 0o755)
            facts["processor"]["wall_s"] = round(time.monotonic() - began, 3)
        facts["processor"]["returncode"] = returncode
        report = _read_report(out / "offline-processor-report.json")
        if report is not None:
            facts["processor"]["report"] = {key: report.get(key) for key in ("verdict", "rc", "reasons", "timing")}
            facts["processor"]["qc"] = report.get("qc")
        if returncode != 0:
            reasons = [] if report is None else [str(item)[:120] for item in (report.get("reasons") or ())[:4]]
            what = "OFFLINE_PROCESSOR_INVALID" if returncode == 3 else "OFFLINE_PROCESSOR_FAILED"
            return RecorderOutcome("INVALID", (f"{what}: rc={returncode}" + ("; " + "; ".join(reasons) if reasons else ""))
                                   [:_REASON_CHARS], facts)
        result = read_processor_result(out / "recorder-result.json", self._identity)
        if isinstance(result, str):
            return RecorderOutcome("INVALID", result, facts)
        qc = (report or {}).get("qc") or {}
        if (result["status"] != "VALID" or report is None or report.get("verdict") != "VALID" or qc.get("status") != "PASS"
                or not qc_output.is_file()):
            return RecorderOutcome("INVALID", "OFFLINE_PROCESSOR_RESULT_NOT_VALID_AND_QC_PASS", facts)
        # VALID needs the fresh QC's memo to cover these exact files. Without it the Worker's seal and the
        # Coordinator's commit would recompute the QC in full (about 290 s each, the Coordinator's twice under its lock), after the
        # processing budget was spent, and the Teacher's result would die at seal with RESULT_AFTER_LEASE_DEADLINE. Data that cannot
        # be sealed in time is INVALID data, not a lost Teacher result.
        covered = (self._memo_check or _memo_covers)(qc_output=qc_output, episode_root=out / "episode", scope=self._scope,
                                                     inputs_manifest=self._inputs_manifest,
                                                     teacher_manifest=None if self._fault == "none" else
                                                     self._point_root / "dynamic" / "dynamic-execute-manifest.json")
        if covered is not True:
            return RecorderOutcome("INVALID", "OFFLINE_QC_MEMO_NOT_VALID", facts)
        facts["seal"] = result["seal"]
        facts["qc_report_path"] = str(qc_output)
        return RecorderOutcome("VALID", None, facts)

    def _retire(self, identity) -> None:
        try:
            self._processes.stop(identity)
        except Exception:   # noqa: BLE001
            pass


def _memo_covers(*, qc_output, episode_root, scope, inputs_manifest, teacher_manifest=None) -> bool:
    """True if a memo beside the QC report covers this report, the QC code and the files on disk now."""
    from .. import qc_memo
    from ..episode_qc import read_qc_report

    try:
        report = read_qc_report(qc_output)
        return qc_memo.memo_matches(qc_output, report, episode_root=episode_root, scope=scope, inputs_manifest=inputs_manifest,
                                    teacher_manifest=teacher_manifest)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _python() -> str:
    import sys

    return sys.executable


def _read_report(path):
    try:
        document = json.loads(Path(path).read_bytes())
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


__all__ = ["OfflineCollection", "drop_bag_messages", "read_processor_result", "PROCESSOR_ROLE", "RAW_ROLE", "BAG_FAULTS"]
