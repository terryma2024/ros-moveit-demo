"""Orchestration of the independent Recorder around one Teacher attempt (Phase A4c).

The orchestrator starts `act_episode_recorder` before the Teacher, waits a bounded time for its LISTENING ready file,
and starts the Teacher whether or not the Recorder became ready. After the Teacher ended it waits a bounded time for the
Recorder to exit, sends SIGTERM when it does not, and maps `recorder-result.json` to the attempt's `act_data_status`.

Direction of dependence: the Teacher never waits for, reads from or is stopped by anything here after its own start. Every
defect on this side is a verdict on the data (INVALID) and never an input to the Teacher. Nothing in this module imports
ROS or the Teacher's modules.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .episode_recorder_process import FAULT_SANDBOX_COMPONENT, READY_SCHEMA, RESULT_SCHEMA

COLLECTION_MODES = ("on", "off")
#: `recorder_absent` and `recorder_late` are orchestrator faults; the other three are passed to the Recorder as `--fault`.
RECORDER_PROCESS_FAULTS = ("queue_overflow", "source_gap", "output_write_failure")
COLLECTION_FAULTS = ("none", "recorder_absent", "recorder_late", *RECORDER_PROCESS_FAULTS)
DIAGNOSTIC_MODE = "preselected_target_diagnostic"
RECORDER_ROLE = "act-episode-recorder"
_REASON_CHARS = 300


class CollectionRefused(ValueError):
    """The collection request is refused before any Teacher starts."""


@dataclass(frozen=True)
class CollectionOptions:
    """The validated `--collection` / `--collection-fault` pair of one run."""

    mode: str = "on"
    fault: str = "none"
    #: `<run>/fault-sandbox`; present only when a fault was requested
    sandbox_root: Path | None = None

    @property
    def enabled(self) -> bool:
        return self.mode == "on"

    @property
    def raw_pilot(self) -> bool:
        """CP-3456: the record-only bag is the only data path, so it is on exactly when the collection is."""
        return self.enabled

    def document(self) -> dict:
        """The form a Worker specification carries; `collection_from_document` re-validates it."""
        return {"mode": self.mode, "fault": self.fault,
                "sandbox_root": None if self.sandbox_root is None else str(self.sandbox_root),
                "raw_pilot": self.enabled}


def validate_collection_request(collection: str, fault: str, *, run_mode: str, run_root,
                                raw_pilot: bool | None = None) -> CollectionOptions:
    """Refuse an unknown value, and refuse a fault outside the diagnostic mode, before any Teacher start.

    `raw_pilot` is the retired `--raw-pilot` switch: the bag recorder is the data path, so `True` is a no-op with the collection on and
    `False` with the collection on is refused (there is no other data path)."""

    if collection not in COLLECTION_MODES:
        raise CollectionRefused(f"COLLECTION_MODE_UNKNOWN: {collection}")
    if fault not in COLLECTION_FAULTS:
        raise CollectionRefused(f"COLLECTION_FAULT_UNKNOWN: {fault}")
    if raw_pilot is not None and type(raw_pilot) is not bool:
        raise CollectionRefused("COLLECTION_RAW_PILOT_UNKNOWN")
    if raw_pilot is True and collection != "on":
        raise CollectionRefused("COLLECTION_RAW_PILOT_REQUIRES_COLLECTION_ON")
    if raw_pilot is False and collection == "on":
        raise CollectionRefused("COLLECTION_RAW_RECORDER_IS_THE_ONLY_DATA_PATH")
    if fault == "none":
        return CollectionOptions(collection, "none", None)
    if run_mode != DIAGNOSTIC_MODE:
        raise CollectionRefused("COLLECTION_FAULT_REQUIRES_DIAGNOSTIC_MODE")
    if collection != "on":
        raise CollectionRefused("COLLECTION_FAULT_REQUIRES_COLLECTION_ON")
    return CollectionOptions(collection, fault, Path(run_root) / FAULT_SANDBOX_COMPONENT)


def collection_from_document(document) -> CollectionOptions:
    """Rebuild and re-validate the options a Worker specification carries; any defect refuses the Worker."""

    if (type(document) is not dict or set(document) not in ({"mode", "fault", "sandbox_root"},
                                                              {"mode", "fault", "sandbox_root", "raw_pilot"})
            or document["mode"] not in COLLECTION_MODES or document["fault"] not in COLLECTION_FAULTS
            or ("raw_pilot" in document and document["raw_pilot"] is not (document["mode"] == "on"))):
        raise CollectionRefused("COLLECTION_SPEC_INVALID")
    root = document["sandbox_root"]
    if document["fault"] == "none":
        if root is not None:
            raise CollectionRefused("COLLECTION_SPEC_INVALID")
        return CollectionOptions(document["mode"], "none", None)
    if (document["mode"] != "on" or type(root) is not str or not Path(root).is_absolute()
            or Path(root).name != FAULT_SANDBOX_COMPONENT or ".." in Path(root).parts):
        raise CollectionRefused("COLLECTION_FAULT_OUTSIDE_SANDBOX")
    return CollectionOptions(document["mode"], document["fault"], Path(root))


def require_under_sandbox(sandbox_root, *paths) -> None:
    """Every fault output must sit beneath `<run>/fault-sandbox/`, as written and after resolving symlinks."""

    if sandbox_root is None:
        raise CollectionRefused("COLLECTION_FAULT_SANDBOX_REQUIRED")
    root = Path(sandbox_root)
    if root.name != FAULT_SANDBOX_COMPONENT:
        raise CollectionRefused(f"COLLECTION_FAULT_OUTSIDE_SANDBOX: {root}")
    real_root = Path(os.path.realpath(root))
    for path in paths:
        path = Path(path)
        if ".." in path.parts or not path.is_relative_to(root) or not Path(os.path.realpath(path)).is_relative_to(real_root):
            raise CollectionRefused(f"COLLECTION_FAULT_OUTSIDE_SANDBOX: {path}")


@dataclass(frozen=True)
class RecorderLaunch:
    """Everything needed to start one Recorder process: its argv and the four outputs it will write."""

    argv: tuple[str, ...]
    environment: dict
    ready_file: Path
    result_file: Path
    episode_root: Path
    identity: dict


@dataclass
class RecorderOutcome:
    """The Recorder's verdict on the data, recorded in full (every field is evidence)."""

    data_status: str
    reason: str | None
    facts: dict = field(default_factory=dict)


def _read_json(path: Path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        payload = os.read(descriptor, 8 * 1024 * 1024)
    finally:
        os.close(descriptor)
    return json.loads(payload)


class RecorderOrchestrator:
    """One attempt's Recorder lifecycle. `processes` is the Worker's owned process tree (or a fake with its surface):
    `start(spec, environment=)`, `exit_code(identity)`, `wait_exit(identity, timeout_s)`, `terminate(identity, grace_s)`,
    `stop(identity)`."""

    def __init__(self, *, processes, launch: RecorderLaunch, policy: dict, fault: str, spec_factory,
                 clock=time.monotonic, sleep=time.sleep) -> None:
        self._processes = processes
        self._launch = launch
        self._policy = policy
        self._fault = fault
        self._spec_factory = spec_factory
        self._clock = clock
        self._sleep = sleep
        self.identity = None
        self.ready = False
        self.late_started = False
        self.ready_reason: str | None = None
        self.start_error: str | None = None
        self.teacher_started = False
        self.teacher_ended = False
        self.events: list[str] = []

    # ---- before the Teacher -------------------------------------------------------------------------------------

    def start_before_teacher(self) -> None:
        """Start the Recorder first and wait a bounded time for LISTENING. Returns whatever happened; never raises.

        `recorder_absent` starts nothing, and `recorder_late` starts the Recorder only after the Teacher's first event
        (`start_late`)."""

        if self._fault == "recorder_absent":
            self.events.append("recorder_not_started:fault_recorder_absent")
            return
        if self._fault == "recorder_late":
            self.events.append("recorder_deferred:fault_recorder_late")
            return
        self._start()
        if self.identity is not None:
            self._wait_ready()

    def teacher_started_now(self) -> None:
        """The Teacher has been started. From here on this orchestrator makes no blocking call until it ended."""
        self.teacher_started = True

    def start_late(self) -> bool:
        """`recorder_late`: start the Recorder now, after the Teacher's first event. It is never waited for."""
        if self._fault != "recorder_late" or self.identity is not None or self.start_error is not None:
            return False
        self._start()
        self.late_started = self.identity is not None
        return self.late_started

    def _start(self) -> None:
        try:
            self.identity = self._processes.start(self._spec_factory(self._launch), environment=self._launch.environment)
            self.events.append("recorder_started")
        except Exception as error:
            self.start_error = ("RECORDER_START_FAILED: " + (str(error) or type(error).__name__))[:_REASON_CHARS]
            self.events.append("recorder_start_failed")

    def _ready_document(self, states=("LISTENING", "CAPTURING")):
        try:
            document = _read_json(self._launch.ready_file)
        except (OSError, ValueError):
            return None
        identity = self._launch.identity
        if (type(document) is dict and document.get("schema") == READY_SCHEMA and document.get("state") in states
                and all(document.get(key) == value for key, value in identity.items())):
            return document
        return None

    def _wait_ready(self) -> None:
        """Bounded wait for LISTENING and then for CAPTURING (CP-3425): the capture is running, with its initial boundary
        committed, before the Teacher starts. On any timeout or an exited Recorder the Teacher starts anyway; only the data
        is INVALID, with the reason of the stage that was missed."""
        stages = (("LISTENING", ("LISTENING", "CAPTURING"), "ready_timeout_s", "recorder_listening",
                   "RECORDER_NOT_READY_BEFORE_TEACHER_START"),
                  ("CAPTURING", ("CAPTURING",), "capturing_timeout_s", "recorder_ready",
                   "RECORDER_NOT_CAPTURING_BEFORE_TEACHER_START"))
        for _name, states, timeout_key, event, reason in stages:
            deadline = self._clock() + float(self._policy[timeout_key])
            while True:
                if self._ready_document(states) is not None:
                    self.events.append(event)
                    break
                if self._processes.exit_code(self.identity) is not None:
                    self.ready_reason = "RECORDER_EXITED_BEFORE_READY"
                    self.events.append("recorder_not_ready:" + self.ready_reason)
                    return
                if self._clock() >= deadline:
                    self.ready_reason = reason
                    self.events.append("recorder_not_ready:" + self.ready_reason)
                    return
                self._sleep(0.02)
        self.ready = True

    # ---- after the Teacher --------------------------------------------------------------------------------------

    def finish(self) -> RecorderOutcome:
        """After the Teacher ended: bounded wait for the Recorder to exit, SIGTERM, then map its result. Never raises."""

        self.teacher_ended = True
        facts: dict = {"fault": self._fault, "events": self.events, "ready": self.ready,
                       "result_file": str(self._launch.result_file), "ready_file": str(self._launch.ready_file),
                       "policy_sha256": self._policy["policy_sha256"]}
        try:
            return self._finish(facts)
        except Exception as error:
            return RecorderOutcome("INVALID", ("RECORDER_ORCHESTRATION_FAILED: " + (str(error) or type(error).__name__))
                                   [:_REASON_CHARS], facts)

    def _finish(self, facts: dict) -> RecorderOutcome:
        if self.identity is None:
            reason = self.start_error or ("RECORDER_ABSENT" if self._fault == "recorder_absent"
                                          else "RECORDER_NEVER_STARTED")
            return RecorderOutcome("INVALID", reason, facts)
        returncode = self._processes.wait_exit(self.identity, float(self._policy["exit_wait_s"]))
        facts["exit_wait_s"] = float(self._policy["exit_wait_s"])
        terminated = False
        if returncode is None:
            terminated = True
            self.events.append("recorder_exit_wait_expired:sigterm")
            returncode = self._processes.terminate(self.identity, float(self._policy["term_grace_s"]))
        facts.update(returncode=returncode, terminated=terminated)
        try:
            self._processes.stop(self.identity)
        except Exception as error:
            facts["retire_error"] = str(error)[:_REASON_CHARS]
        result = self._result_document(facts)
        if not self.ready:
            facts["late_started"] = self.late_started
            return RecorderOutcome("INVALID", (self.ready_reason or (
                "RECORDER_STARTED_AFTER_TEACHER" if self.late_started else "RECORDER_NOT_READY_BEFORE_TEACHER_START")),
                facts)
        if terminated:
            return RecorderOutcome("INVALID", "RECORDER_EXIT_WAIT_EXPIRED", facts)
        if isinstance(result, str):
            return RecorderOutcome("INVALID", result, facts)
        reasons = [str(item)[:_REASON_CHARS] for item in result.get("reasons", ())[:4]]
        if result["status"] != "VALID" or returncode != 0:
            return RecorderOutcome("INVALID", ("RECORDER_RESULT_INVALID: " + "; ".join(reasons))[:_REASON_CHARS]
                                   if reasons else f"RECORDER_RESULT_INVALID: rc={returncode}", facts)
        facts["seal"] = result["seal"]
        return RecorderOutcome("VALID", None, facts)

    def _result_document(self, facts: dict):
        """The validated result document, or the reason string it could not be trusted."""
        try:
            document = _read_json(self._launch.result_file)
        except FileNotFoundError:
            return "RECORDER_RESULT_MISSING"
        except (OSError, ValueError):
            return "RECORDER_RESULT_UNREADABLE"
        if type(document) is not dict or document.get("schema") != RESULT_SCHEMA:
            return "RECORDER_RESULT_SCHEMA_INVALID"
        identity = document.get("identity")
        if type(identity) is not dict or any(identity.get(key) != value for key, value in self._launch.identity.items()):
            return "RECORDER_RESULT_IDENTITY_MISMATCH"
        if document.get("status") not in ("VALID", "INVALID"):
            return "RECORDER_RESULT_STATUS_INVALID"
        facts["recorder_status"] = document["status"]
        facts["recorder_rc"] = document.get("rc")
        facts["recorder_reasons"] = [str(item)[:_REASON_CHARS] for item in document.get("reasons", ())[:16]]
        if document["status"] == "VALID" and (type(document.get("seal")) is not dict or document.get("listening") is not True):
            return "RECORDER_RESULT_VALID_WITHOUT_SEAL"
        return document
