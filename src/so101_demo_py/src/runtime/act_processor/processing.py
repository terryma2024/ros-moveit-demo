"""One processing task: verify the phase-1 record, run `act_offline_episode`, grade the data, write `processed-result.json`.

Phase 1 left a sealed attempt whose `result.json` says `PENDING_QC` and whose `raw/recording-receipt.json` binds every raw file.
This module trusts neither until it has re-read them. It then runs the offline processor with exactly the arguments the retired
inline path used (`OfflineCollection._process`), maps the processor's exit code, and grades the episode the way the result store
graded an inline episode, so `processed-result.json` carries the data verdict fields `result.json` carried inline.

Exit code mapping (the retry itself is the Host's scheduler, not here):

    rc 0 and the checks below  VALID                      final
    rc 3, or a failed check    INVALID (a data verdict)   final, never retried
    rc 2, or a refused input   REFUSED (a fault)          not retried
    rc 4, crash, timeout, stop, output write error        INFRASTRUCTURE_FAILURE: retryable in a new `-proc-<n+1>` directory

A diagnostic fault the Teacher attempt deferred (`fault_deferred_to_processing`) is applied the way `finish_inline` applied it,
and then any non-zero processor exit is the fault's expected INVALID data, not an infrastructure failure.

The phase-1 `sealed/` directory is only read. Everything is written under `output_dir`.
"""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time

from so101_demo.act.offline.orchestration import (
    BAG_FAULTS, FAULT_DROP_COUNT, FAULT_TOPIC, drop_bag_messages, read_processor_result, _memo_covers, _read_report)
from so101_demo.act.offline.recording_receipt import RECEIPT_RELATIVE, verify_recording_receipt
from so101_demo.act.parallel_collection_contracts import read_document
from so101_demo.runtime.container_campaign.task_contracts import TaskSpec
from so101_demo.runtime.inference.config import validate_file_ref

TASK_KIND = "ACT_PROCESSING_TASK"
TASK_RESULT_KIND = "ACT_PROCESSING_TASK_RESULT"
PROCESSED_KIND = "ACT_PROCESSED_RESULT"
PROCESSED_NAME = "processed-result.json"
PHASE1_ATTEMPT = re.compile(r"/attempts/(?P<scene>[a-zA-Z0-9][a-zA-Z0-9_-]*)/(?P<attempt>[a-zA-Z0-9][a-zA-Z0-9_-]*)/sealed")
DEFERRED_FAULTS = BAG_FAULTS + ("output_write_failure",)
#: the processor is told to stop this long before the task deadline so the task result is still written
DEADLINE_MARGIN_S = 5.0
TERM_GRACE_S = 10.0
_REASON_CHARS = 300
_TASK_FIELDS = {"schema_version", "kind", "task_id", "processor_id", "launch_generation", "scene_id", "proc_attempt",
                "phase1_attempt", "phase1_result_sha256", "inputs_manifest", "scope", "output_dir"}

VALID, INVALID, REFUSED, INFRASTRUCTURE_FAILURE = "VALID", "INVALID", "REFUSED", "INFRASTRUCTURE_FAILURE"


class Refused(ValueError):
    """The task or the phase-1 record cannot be honoured (a fault, not retryable)."""


class InfrastructureFailure(RuntimeError):
    """The processing itself failed (retryable): crash, timeout, a stop, an output that cannot be written."""


@dataclass(frozen=True)
class ProcessingTask:
    task_id: str
    scene_id: str
    proc_attempt: int
    sealed: Path
    phase1_result_sha256: str
    inputs_manifest: Path
    scope: Path
    output_dir: Path
    deadline_monotonic_s: float


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_processing_task(task, *, owned_root, processing_root, processor_id, launch_generation):
    """The assignment, validated against this processor and the frozen references; creates nothing."""
    if type(task) is not TaskSpec:
        raise Refused("PROCESSING_TASK_SPEC_INVALID")
    owned_root, processing_root = Path(owned_root), Path(processing_root)
    if task.inputs_ref.path != str(owned_root / "task-inputs" / (task.task_id + ".json")):
        raise Refused("PROCESSING_TASK_INPUT_LOCATION_INVALID")
    try:
        document = read_document(validate_file_ref(task.inputs_ref.model_dump()))
    except Exception as error:   # noqa: BLE001 - unreadable, duplicate keys, wrong hash: one input fault
        raise Refused("PROCESSING_TASK_INPUT_INVALID") from error
    if (set(document) != _TASK_FIELDS or type(document["schema_version"]) is not int or document["schema_version"] != 1
            or document["kind"] != TASK_KIND or document["task_id"] != task.task_id
            or document["processor_id"] != processor_id or type(document["launch_generation"]) is not int
            or document["launch_generation"] != launch_generation):
        raise Refused("PROCESSING_TASK_CONTEXT_MISMATCH")
    scene, number = document["scene_id"], document["proc_attempt"]
    if (type(scene) is not str or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", scene) is None
            or type(number) is not int or number <= 0 or type(document["phase1_attempt"]) is not str
            or type(document["phase1_result_sha256"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", document["phase1_result_sha256"]) is None):
        raise Refused("PROCESSING_TASK_INPUT_INVALID")
    sealed = Path(document["phase1_attempt"])
    match = PHASE1_ATTEMPT.search(str(sealed))
    if (not sealed.is_absolute() or ".." in sealed.parts or match is None or match.end() != len(str(sealed))
            or match["scene"] != scene or sealed.resolve() != sealed or not sealed.is_dir()):
        raise Refused("PROCESSING_TASK_ATTEMPT_INVALID")
    output = Path(document["output_dir"])
    if output != processing_root / scene / f"{match['attempt']}-proc-{number}":
        raise Refused("PROCESSING_TASK_OUTPUT_LOCATION_INVALID")
    try:
        inputs, scope = (validate_file_ref(document[name]) for name in ("inputs_manifest", "scope"))
    except Exception as error:   # noqa: BLE001
        raise Refused("PROCESSING_TASK_REFERENCE_INVALID") from error
    return ProcessingTask(task_id=task.task_id, scene_id=scene, proc_attempt=number, sealed=sealed,
                          phase1_result_sha256=document["phase1_result_sha256"], inputs_manifest=inputs, scope=scope,
                          output_dir=output, deadline_monotonic_s=task.deadline_monotonic_s)


def verify_phase1(task):
    """Re-read the phase-1 result and receipt. Returns the facts processing binds; raises `Refused` on any disagreement."""
    sealed = task.sealed
    try:
        raw = (sealed / "result.json").read_bytes()
        result = json.loads(raw)
        result_sha256 = hashlib.sha256(raw).hexdigest()
        if (result_sha256 != task.phase1_result_sha256 or type(result) is not dict
                or result.get("kind") != "ACT_COLLECTION_RESULT" or result.get("schema_version") != 3
                or result.get("act_data_status") != "PENDING_QC" or result.get("episode_seal_sha256") is not None
                or result.get("act_data_qc") != "NOT_RUN" or result.get("export_eligible") is not False):
            raise ValueError("PHASE1_RESULT_NOT_PENDING_QC")
        lease = result["lease_identity"]
        if lease["attempt_id"] != sealed.parent.name or lease["point_id"] != task.scene_id:
            raise ValueError("PHASE1_RESULT_ATTEMPT_MISMATCH")
        receipt_raw = (sealed / RECEIPT_RELATIVE).read_bytes()
        receipt = json.loads(receipt_raw)
        verified = verify_recording_receipt(
            sealed, lease_identity=lease, identity=receipt["identity"],
            external={"scope": _sha256_file(task.scope), "inputs_manifest": _sha256_file(task.inputs_manifest)})
        if verified["sha256"] != hashlib.sha256(receipt_raw).hexdigest() or receipt["identity"]["attempt_id"] != lease["attempt_id"]:
            raise ValueError("RECORDING_RECEIPT_CHANGED")
        deferred = None
        try:
            record = json.loads((sealed / "recorder-orchestration.json").read_bytes())
            deferred = record.get("fault_deferred_to_processing")
        except (OSError, ValueError, AttributeError):
            pass
        if deferred is not None and deferred not in DEFERRED_FAULTS:
            raise ValueError("PHASE1_DEFERRED_FAULT_UNKNOWN")
        return dict(result_sha256=result_sha256, receipt_sha256=verified["sha256"], status=result["status"],
                    lease_identity=lease, identity=dict(receipt["identity"]), fault=deferred or "none",
                    receipt_files=verified["files"], receipt_bytes=verified["bytes"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise Refused(f"PHASE1_RECORD_REFUSED: {str(error)[:200] or type(error).__name__}") from error


class SubprocessRunner:
    """Runs the offline processor as a child process group. `run` returns its exit code, or None when it had to be stopped."""

    def __init__(self):
        self._lock = threading.Lock()
        self._process = None

    def run(self, argv, *, timeout_s, environment, stop):
        with self._lock:
            if stop.is_set():
                return None
            self._process = subprocess.Popen(argv, env=environment, start_new_session=True, stdin=subprocess.DEVNULL)
        process = self._process
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                return process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                if stop.is_set() or time.monotonic() >= deadline:
                    self.terminate()
                    return None

    def terminate(self):
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        for sig, grace in ((signal.SIGTERM, TERM_GRACE_S), (signal.SIGKILL, TERM_GRACE_S)):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                break
            try:
                process.wait(timeout=grace)
                break
            except subprocess.TimeoutExpired:
                continue

    def alive(self):
        process = self._process
        return process is not None and process.poll() is None


def grade_episode(*, out, qc_output, lease, identity, scope, inputs_manifest, teacher_status, trust_memo=True):
    """The data verdict of an episode the processor built, graded as `ActCollectionResultStore._grade_data` graded an inline one.

    Returns `{status, reason, qc, episode_sha256, binding}`; `binding` is None unless the QC ran. Never raises on a data problem."""
    from so101_demo.act.result_store import (
        _REASON_MAX_CHARS, _read_regular, _seal_facts, _verify_audit_lease, _verify_result_qc)
    from so101_demo.parallel_batch.contracts.identity import LeaseIdentity

    episode_root = Path(out) / "episode"
    seal = episode_root / "seal.json"
    audit = episode_root / "audit" / "audit-manifest.json"
    episode_sha256 = None
    try:
        episode_sha256 = hashlib.sha256(_read_regular(seal)).hexdigest()
    except OSError:
        pass

    def invalid(why):
        return dict(status="INVALID", reason=str(why)[:_REASON_MAX_CHARS], qc="NOT_RUN", episode_sha256=episode_sha256, binding=None)

    try:
        execution_lease = LeaseIdentity(**lease)
        episode = _seal_facts(seal)
        _verify_audit_lease(audit, execution_lease)
        if episode["attempt_id"] != execution_lease.attempt_id:
            raise ValueError("LEASE_IDENTITY_MISMATCH")
        if episode["session_id"] != identity["session_id"] or episode["reset_epoch"] != identity["reset_epoch"]:
            raise ValueError("ACT_RESET_IDENTITY_MISMATCH")
    except (OSError, ValueError, TypeError, KeyError) as error:
        return invalid("RESULT_EPISODE_INVALID: " + (str(error) or type(error).__name__))
    try:
        report, digest, mode = _verify_result_qc(Path(qc_output), episode_root=episode_root, audit_manifest=audit, scope=scope,
                                                 inputs_manifest=inputs_manifest, execution_lease=execution_lease,
                                                 trust_memo=trust_memo)
    except (OSError, ValueError, TypeError, KeyError) as error:
        return invalid("RESULT_QC_NOT_RUN: " + (str(error) or type(error).__name__))
    binding = dict(qc_report_path=Path(qc_output).relative_to(out).as_posix(), qc_report_sha256=digest,
                   inputs_sha256=report["inputs_sha256"], scope_sha256=report["scope_sha256"],
                   audit_manifest_sha256=report["audit_manifest_sha256"], collection_mode=mode)
    return dict(status="VALID", reason=None, qc="PASS" if report["status"] == "PASS" else "FAIL",
                episode_sha256=episode_sha256, binding=binding)


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def write_processed_result(output_dir, document):
    """Atomically publish `processed-result.json` (temporary file, fsync, rename, fsync of the directory)."""
    payload = _canonical(document)
    target = Path(output_dir) / PROCESSED_NAME
    staged = target.with_name(target.name + ".tmp")
    with open(staged, "xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staged, target)
    descriptor = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return dict(path=PROCESSED_NAME, sha256=hashlib.sha256(payload).hexdigest())


class ProcessingExecution:
    """One processing task over injected parts. `run` is called on one thread, `request_stop` and `shutdown_owned` from others."""

    def __init__(self, *, task, python, runner=None, environment=None, grader=grade_episode, memo_check=_memo_covers,
                 clock=time.monotonic):
        self.task, self.python = task, str(python)
        self.runner = SubprocessRunner() if runner is None else runner
        self.environment = dict(os.environ if environment is None else environment)
        self.grader, self.memo_check, self.clock = grader, memo_check, clock
        self.stop = threading.Event()
        self.retire_proofs = None
        self._done = threading.Event()

    # ---- control ---------------------------------------------------------------------------------------------------------

    def request_stop(self):
        self.stop.set()
        terminate = getattr(self.runner, "terminate", None)
        if callable(terminate):
            terminate()

    def shutdown_owned(self):
        """True once no processor child is left running. Never raises."""
        try:
            alive = getattr(self.runner, "alive", None)
            clear = not (callable(alive) and alive())
            self.retire_proofs = dict(processor_child_exited=clear)
            return clear
        except BaseException:   # noqa: BLE001
            return False

    # ---- the task ----------------------------------------------------------------------------------------------------------

    def run(self):
        task = self.task
        try:
            phase1 = verify_phase1(task)
        except Refused as error:
            return self._result(REFUSED, str(error), None, None, None)
        try:
            return self._process(phase1)
        except Refused as error:
            return self._result(REFUSED, str(error), None, None, phase1)
        except InfrastructureFailure as error:
            return self._result(INFRASTRUCTURE_FAILURE, str(error), getattr(error, "rc", None), None, phase1)
        except OSError as error:   # an output that cannot be written
            return self._result(INFRASTRUCTURE_FAILURE, f"PROCESSING_OUTPUT_WRITE_FAILED: {error}"[:_REASON_CHARS], None, None, phase1)

    def _argv(self, phase1, bag, out, qc_output):
        sealed = self.task.sealed
        return [self.python, "-m", "so101_demo.cli.act_offline_episode",
                "--bag", str(bag), "--inputs", str(self.task.inputs_manifest), "--out", str(out),
                "--lease", str(sealed / "raw" / "lease.json"), "--scope", str(self.task.scope),
                "--record-stats", str(sealed / "raw" / "record-stats.json"),
                "--teacher-manifest", str(sealed / "dynamic" / "dynamic-execute-manifest.json"),
                "--qc-output", str(qc_output)]

    def _process(self, phase1):
        task, fault = self.task, phase1["fault"]
        base = task.output_dir
        try:
            base.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            base.mkdir(mode=0o755)
        except FileExistsError as error:
            raise Refused("PROCESSING_OUTPUT_EXISTS") from error
        bag = task.sealed / "raw" / "bag"
        if not (bag / "metadata.yaml").is_file():
            return self._finish(phase1, None, dict(status="INVALID", reason="RAW_BAG_MISSING", qc="NOT_RUN",
                                                   episode_sha256=None, binding=None), None)
        facts = {}
        if fault in BAG_FAULTS:
            copy = base / "fault-bag"
            facts["bag_fault"] = drop_bag_messages(bag, copy, topic=FAULT_TOPIC[fault], count=FAULT_DROP_COUNT[fault])
            bag = copy
        out = base if fault == "none" else base / "out"
        qc_output = out / "qc-report.json" if fault == "none" else out / "offline-qc-report.json"
        out.mkdir(parents=True, exist_ok=True)
        argv = self._argv(phase1, bag, out, qc_output)
        timeout_s = task.deadline_monotonic_s - self.clock() - DEADLINE_MARGIN_S
        read_only = fault == "output_write_failure"
        if read_only:
            os.chmod(out, 0o555)   # the processor must fail to write its episode
        try:
            rc = self.runner.run(argv, timeout_s=timeout_s, environment=self.environment, stop=self.stop) if timeout_s >= 1 else None
        except OSError as error:
            raise InfrastructureFailure(f"OFFLINE_PROCESSOR_START_FAILED: {error}"[:_REASON_CHARS]) from error
        finally:
            if read_only:
                os.chmod(out, 0o755)
        if rc is None:
            why = "stopped" if self.stop.is_set() else "no time left or timed out"
            raise InfrastructureFailure(f"OFFLINE_PROCESSOR_TIMEOUT: {why}")
        report = _read_report(out / "offline-processor-report.json")
        if fault != "none" and rc != 0:
            # the fault's expected outcome: a passing Teacher and INVALID data
            data = dict(status="INVALID", reason=f"OFFLINE_PROCESSOR_FAILED: rc={rc}", qc="NOT_RUN", episode_sha256=None, binding=None)
            return self._finish(phase1, rc, data, out)
        if rc == 2:
            raise Refused("OFFLINE_PROCESSOR_REFUSED: rc=2")
        if rc == 3:
            reasons = [] if report is None else [str(item)[:120] for item in (report.get("reasons") or ())[:4]]
            reason = ("OFFLINE_PROCESSOR_INVALID: rc=3" + ("; " + "; ".join(reasons) if reasons else ""))[:_REASON_CHARS]
            return self._finish(phase1, rc, self._invalid(reason, out), out)
        if rc != 0:
            error = InfrastructureFailure(f"OFFLINE_PROCESSOR_FAILED: rc={rc}")
            error.rc = rc
            raise error
        result = read_processor_result(out / "recorder-result.json", phase1["identity"])
        if isinstance(result, str):
            if result in ("OFFLINE_RESULT_MISSING", "OFFLINE_RESULT_UNREADABLE"):
                raise InfrastructureFailure(result)
            return self._finish(phase1, rc, self._invalid(result, out), out)
        qc = (report or {}).get("qc") or {}
        if (result["status"] != "VALID" or report is None or report.get("verdict") != "VALID" or qc.get("status") != "PASS"
                or not qc_output.is_file()):
            return self._finish(phase1, rc, self._invalid("OFFLINE_PROCESSOR_RESULT_NOT_VALID_AND_QC_PASS", out), out)
        covered = self.memo_check(qc_output=qc_output, episode_root=out / "episode", scope=task.scope,
                                  inputs_manifest=task.inputs_manifest,
                                  teacher_manifest=None if fault == "none" else task.sealed / "dynamic" / "dynamic-execute-manifest.json")
        if covered is not True:
            return self._finish(phase1, rc, self._invalid("OFFLINE_QC_MEMO_NOT_VALID", out), out)
        data = self.grader(out=out, qc_output=qc_output, lease=phase1["lease_identity"], identity=phase1["identity"],
                           scope=task.scope, inputs_manifest=task.inputs_manifest, teacher_status=phase1["status"])
        return self._finish(phase1, rc, data, out)

    @staticmethod
    def _invalid(reason, out):
        episode = None
        try:
            episode = hashlib.sha256((Path(out) / "episode" / "seal.json").read_bytes()).hexdigest()
        except OSError:
            pass
        return dict(status="INVALID", reason=reason[:_REASON_CHARS], qc="NOT_RUN", episode_sha256=episode, binding=None)

    def _finish(self, phase1, rc, data, out):
        """Write `processed-result.json` from a data verdict and report the task."""
        from so101_demo.act.result_store import export_eligible

        binding = data["binding"] or {key: None for key in (
            "qc_report_path", "qc_report_sha256", "inputs_sha256", "scope_sha256", "audit_manifest_sha256", "collection_mode")}
        base = self.task.output_dir
        artifacts = {}
        for name, path in (("recorder_result", (out or base) / "recorder-result.json"),
                           ("processor_report", (out or base) / "offline-processor-report.json")):
            try:
                artifacts[name] = dict(path=path.relative_to(base).as_posix(), sha256=_sha256_file(path))
            except OSError:
                artifacts[name] = None
        document = {
            "kind": PROCESSED_KIND, "schema_version": 1,
            "task_id": self.task.task_id, "scene_id": self.task.scene_id, "proc_attempt": self.task.proc_attempt,
            "phase1_result_sha256": phase1["result_sha256"], "receipt_sha256": phase1["receipt_sha256"],
            "lease_identity": phase1["lease_identity"], "identity": phase1["identity"], "status": phase1["status"],
            "processor_rc": rc, "diagnostic_fault": phase1["fault"], "artifacts": artifacts,
            "act_data_status": data["status"], "act_data_reason": data["reason"], "act_data_qc": data["qc"],
            "episode_seal_sha256": data["episode_sha256"],
            "export_eligible": export_eligible(phase1["status"], data["qc"], binding["collection_mode"]),
            **binding,
        }
        written = write_processed_result(base, document)
        outcome = VALID if data["status"] == "VALID" and data["qc"] == "PASS" else INVALID
        return self._result(outcome, data["reason"], rc, written, phase1)

    def _result(self, outcome, reason, rc, processed, phase1):
        task = self.task
        return dict(kind=TASK_RESULT_KIND, schema_version=1, task_id=task.task_id, scene_id=task.scene_id,
                    proc_attempt=task.proc_attempt, outcome=outcome, retryable=outcome == INFRASTRUCTURE_FAILURE,
                    reason=None if reason is None else str(reason)[:_REASON_CHARS], processor_rc=rc,
                    output_dir=str(task.output_dir), processed_result=processed,
                    phase1=None if phase1 is None else dict(result_sha256=phase1["result_sha256"], receipt_sha256=phase1["receipt_sha256"]))
