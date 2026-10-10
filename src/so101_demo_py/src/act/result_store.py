"""Worker-private ACT result publication for the existing Coordinator result port.

An episode seal is evidence, not a result commit. This adapter gives the
Coordinator a deterministic, lease-bound location that it can independently
verify before appending RESULT_COMMITTED to its journal.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Mapping
import uuid

from .recorder import verify_episode_seal
from so101_demo.parallel_batch.contracts import AttemptStatus, LeaseIdentity, RunMode
from so101_demo.application.e2e_acceptance import SCHEMA_GENERAL, SCHEMA_TEACHER, is_manifest_of
from so101_demo.parallel_batch.dynamic_manifest import (
    DATA_STATUSES, EXECUTION_STATUSES, TASK_RESULTS, teacher_attempt_status)


class ResultInfraError(RuntimeError):
    """A result could not be durably sealed; no business terminal is implied."""


_IDENTITY_KEYS = (
    "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
    "point_id", "attempt_id", "lease_generation",
)
def export_eligible(status, qc, collection_mode) -> bool:
    """Export needs a Teacher PASS, an independent QC PASS and a trainable collection mode (never a diagnostic one,
    which is also the only mode a spot-check candidate receipt can run in)."""

    from .collection import TRAINABLE_COLLECTION_MODES

    return status in ("PASSED", AttemptStatus.PASSED) and qc == "PASS" and collection_mode in TRAINABLE_COLLECTION_MODES


#: schema 1 and 2 are the read-only legacy of the coupled contract (a QC verdict decided the attempt status)
_LEGACY_MANIFEST_KEYS = frozenset({
    "kind", "schema_version", "lease_identity", "status", "qc_passed",
    "episode_seal_sha256", "completed_monotonic_s",
})
_QC_MANIFEST_KEYS = frozenset({'qc_report_path','qc_report_sha256','inputs_sha256',
    'scope_sha256','audit_manifest_sha256','collection_mode'})
#: schema 3: the attempt status is the Teacher's, the data verdict is separate, export needs both
_DATA_FIELDS = ("teacher_execution_status", "teacher_task_result", "act_data_status", "act_data_reason",
                "act_data_qc", "export_eligible")
_RESULT_V3_KEYS = frozenset({
    "kind", "schema_version", "lease_identity", "status", "episode_seal_sha256", "completed_monotonic_s",
    *_DATA_FIELDS, *_QC_MANIFEST_KEYS})
_ACT_DATA_QC = ("PASS", "FAIL", "NOT_RUN")
#: the Teacher child's manifest, which the sealed result carries under the attempt's working directory
_TEACHER_MANIFEST = Path("dynamic") / "dynamic-execute-manifest.json"
_REASON_MAX_CHARS = 300
#: the keys the Coordinator projects into its journal and index for each committed ACT point
ACT_POINT_RESULT_KEYS = ("teacher_execution_status", "teacher_task_result", "act_data_status", "act_data_qc",
                         "export_eligible")
#: what the commit receipt carries about the result: the point keys plus the bounded data reason
ACT_RESULT_RECEIPT_KEYS = _DATA_FIELDS


def _safe(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("RESULT_PATH_INVALID")
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("RESULT_PATH_INVALID")
    return path


def _identity(lease: LeaseIdentity) -> dict:
    if not isinstance(lease, LeaseIdentity):
        raise ValueError("LEASE_IDENTITY_MISMATCH")
    data = asdict(lease)
    return {name: data[name] for name in _IDENTITY_KEYS}


def _workspace(worker_root: Path, lease: LeaseIdentity) -> Path:
    return _safe(_safe(worker_root) / "attempts" / lease.point_id / lease.attempt_id)


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def _read_regular(path: Path) -> bytes:
    import stat

    fd = os.open(_safe(path), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("RESULT_FILE_INVALID")
        return stream.read()


def _fsync_dir(path: Path) -> None:
    fd = os.open(_safe(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_audit_lease(audit_manifest: Path | None, lease: LeaseIdentity) -> None:
    if audit_manifest is None:
        return  # Historical v1 episodes have no audit artifact.
    document = json.loads(_read_regular(audit_manifest))
    observed = document["identity"].get("lease")
    inputs = json.loads(_read_regular(audit_manifest.parent / "inputs.json"))
    # New execution-bound evidence must carry the full issued lease, including
    # its original clock bounds. Historical unbound fixtures may omit it.
    if observed is not None or "execution_snapshot" in inputs:
        try:
            parsed = LeaseIdentity(**observed)
        except (TypeError, ValueError) as error:
            raise ValueError("LEASE_IDENTITY_MISMATCH") from error
        if parsed != lease:
            raise ValueError("LEASE_IDENTITY_MISMATCH")


def _current_qc_required(audit_manifest):
    from .teacher_collection_v2 import is_current_episode
    return audit_manifest is not None and is_current_episode(json.loads(
        _read_regular(audit_manifest.parent/'inputs.json')))


def _qc_required_when_readable(audit_manifest) -> bool:
    """Like `_current_qc_required`, but an absent audit means there is nothing to grade rather than a refusal."""
    try:
        return _current_qc_required(audit_manifest)
    except (OSError, ValueError, TypeError):
        return False


def _teacher_claim(teacher) -> dict:
    """Validate the Teacher's result and the data status its child reported; both come from the Teacher process."""
    keys = {"execution_status", "task_result", "data_status", "data_reason"}
    if (type(teacher) is not dict or set(teacher) != keys
            or teacher["execution_status"] not in EXECUTION_STATUSES
            or teacher["task_result"] not in TASK_RESULTS
            or teacher["data_status"] not in DATA_STATUSES
            or not (teacher["data_reason"] is None or type(teacher["data_reason"]) is str)):
        raise ValueError("RESULT_TEACHER_FIELDS_INVALID")
    teacher_attempt_status(teacher["execution_status"], teacher["task_result"])
    reason = teacher["data_reason"]
    return {**teacher, "data_reason": None if reason is None else reason[:_REASON_MAX_CHARS]}


def _check_teacher_manifest(path, claim) -> None:
    """The Teacher's claim must agree with the manifest its own child wrote.

    A claim of INDETERMINATE/UNCONFIRMED asserts nothing positive (the child produced nothing usable), so it needs
    no manifest. Every other claim must name the child's v2 manifest and agree with it on the Teacher fields. The data
    status is not the Teacher's to give (its manifest carries the constant DISABLED): it comes from the independent
    Recorder and is graded below.
    """
    if claim["execution_status"] == "INDETERMINATE" and claim["task_result"] == "UNCONFIRMED":
        return
    try:
        document = json.loads(_read_regular(path))
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError("RESULT_TEACHER_MANIFEST_REQUIRED") from error
    task = document.get("teacher_task_result") if type(document) is dict else None
    if (not is_manifest_of(document, SCHEMA_GENERAL, SCHEMA_TEACHER)
            or document.get("teacher_execution_status") != claim["execution_status"]
            or type(task) is not dict or task.get("result") != claim["task_result"]
            or document.get("act_data_status") not in DATA_STATUSES):
        raise ValueError("RESULT_TEACHER_MANIFEST_MISMATCH")


def _seal_facts(seal_path) -> dict:
    """The identity facts of a sealed episode, read from its seal document (used only where a valid QC memo already covers the full
    seal verification)."""
    return json.loads(_read_regular(seal_path))


def _qc_memo_covers(report_path, *, episode_root, scope, inputs_manifest) -> bool:
    """True if a content-bound memo of the independent fresh-process QC covers this report and the files on disk now (CP-3456)."""
    from . import qc_memo
    from .episode_qc import read_qc_report

    try:
        report = read_qc_report(report_path)
        return qc_memo.memo_matches(report_path, report, episode_root=episode_root, scope=scope, inputs_manifest=inputs_manifest)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _recomputed_or_memoised(report_path, report, *, episode_root, scope, inputs_manifest, trust_memo, reader):
    """The recomputed report the stored one is compared with: the full recomputation, except where the caller trusts the fresh-process
    QC's memo and the memo covers exactly this report and these files (then the report is the recomputation by construction)."""
    if trust_memo:
        from . import qc_memo

        if qc_memo.memo_matches(report_path, report, episode_root=episode_root, scope=scope, inputs_manifest=inputs_manifest):
            return report
    return reader(episode_root, scope=scope, inputs_manifest=inputs_manifest)


def _verify_result_qc(report_path, *, episode_root, audit_manifest, scope, inputs_manifest, execution_lease,
                      legacy=False, trust_memo=False):
    """Authenticate the report and independently recompute its complete verdict.

    Current (schema 3) results are graded by the data QC alone: the episode seal's task outcome is not a criterion, so a
    Teacher FAIL with valid data can carry a QC PASS. `legacy=True` is the read-only audit of a schema 2 result, whose
    report is the retired endpoint_pose_v1 one and is recomputed by the retained legacy reader.
    """
    from . import episode_qc
    from .episode_qc import read_qc_report,_report_canonical
    try:
        if any(value is None for value in (audit_manifest,scope,inputs_manifest)):
            raise ValueError('original binding absent')
        report=read_qc_report(report_path,legacy=legacy)
        if report['schema_version']!=(2 if legacy else 3):
            raise ValueError('report schema does not match the result schema')
        scope_document=json.loads(_read_regular(scope))
        frozen=json.loads(_read_regular(inputs_manifest))
        audit=json.loads(_read_regular(audit_manifest))
        seal=json.loads(_read_regular(episode_root/'seal.json'))
        if (report['identity']!=audit['identity'] or report['identity']['lease']!=asdict(execution_lease)
                or any(report['identity'][key]!=seal[key] for key in ('session_id','attempt_id','reset_epoch'))
                or report['counts']['records']!=seal['record_count']
                or report['inputs_sha256']!=frozen['inputs_sha256']
                or report['inputs_sha256']!=scope_document['inputs_sha256']
                or report['scope_sha256']!=hashlib.sha256(_read_regular(scope)).hexdigest()
                or report['audit_manifest_sha256']!=hashlib.sha256(_read_regular(audit_manifest)).hexdigest()
                or report['episode_seal_sha256']!=hashlib.sha256(_read_regular(episode_root/'seal.json')).hexdigest()
                or report['identity'].get('mode')!=scope_document['mode']
                or frozen['mode']!=scope_document['mode']
                or (legacy and report['status']=='PASS' and seal['status']!='PASSED')):
            raise ValueError('identity/hash/status mismatch')
        reader=episode_qc.recompute_legacy_native_qc_v2 if legacy else episode_qc.recompute_native_qc
        recomputed=_recomputed_or_memoised(report_path,report,episode_root=episode_root,scope=scope,
            inputs_manifest=inputs_manifest,trust_memo=trust_memo and not legacy,reader=reader)
        if _report_canonical(report)!=_report_canonical(recomputed):
            raise ValueError('recomputed verdict differs')
        return report,hashlib.sha256(_read_regular(report_path)).hexdigest(),scope_document['mode']
    except (OSError,ValueError,TypeError,KeyError) as error:
        raise ValueError('RESULT_QC_READBACK_INVALID') from error


class ActCollectionResultStore:
    """One writer at the workspace reserved by a Coordinator lease."""

    #: CP-3456: trust the offline processor's content-bound QC memo instead of repeating its five-minute recomputation
    TRUST_FRESH_QC_MEMO = False

    def __init__(self, workspace: Path, lease: LeaseIdentity, *, clock,
                 audit_manifest=None, scope=None,
                 expected_session_id: str | None = None,
                 expected_reset_epoch: int | None = None,
                 reserved_workspace=None, inputs_manifest=None, trust_fresh_qc_memo=None) -> None:
        if trust_fresh_qc_memo is not None:
            self.TRUST_FRESH_QC_MEMO = bool(trust_fresh_qc_memo)
        if self.TRUST_FRESH_QC_MEMO:
            from . import qc_memo
            qc_memo.note_trusting_gate()
        self.workspace = _safe(workspace)
        self.lease = lease
        self.identity = _identity(lease)
        if self.workspace.name != lease.attempt_id or self.workspace.parent.name != lease.point_id or self.workspace.parent.parent.name != "attempts":
            raise ValueError("LEASE_LOCATION_MISMATCH")
        if not callable(clock):
            raise ValueError("RESULT_CLOCK_INVALID")
        self.clock = clock
        self.expected_session_id = expected_session_id
        self.expected_reset_epoch = expected_reset_epoch
        #: a v2 seal is verified only when the caller supplies both artifacts (CP-2765), so the store
        #: carries the pair rather than assuming a convention about where an episode's audit lives
        self.audit_manifest = None if audit_manifest is None else _safe(Path(audit_manifest))
        self.scope = None if scope is None else _safe(Path(scope))
        self.inputs_manifest = None if inputs_manifest is None else _safe(Path(inputs_manifest))
        self.working = self.workspace / "working"
        self._reserved_workspace = reserved_workspace
        if reserved_workspace is None:
            self.workspace.mkdir(parents=True, exist_ok=True)
            self.working.mkdir(exist_ok=False)
        else:
            from so101_demo.parallel_batch.artifacts import AttemptWorkspace
            if (type(reserved_workspace) is not AttemptWorkspace
                    or reserved_workspace.path != self.working
                    or asdict(reserved_workspace.identity) != self.identity
                    or expected_session_id is None or type(expected_reset_epoch) is not int
                    or not self.working.is_dir() or (self.workspace / "sealed").exists()):
                raise ValueError("ACT_RESERVED_WORKSPACE_INVALID")
            metadata_bytes = _read_regular(self.working / "workspace_identity.json")
            metadata = json.loads(metadata_bytes)
            if (metadata != reserved_workspace._metadata
                    or metadata.get("identity") != self.identity
                    or metadata.get("run_mode") != RunMode.EXECUTE.value
                    or metadata.get("worker_slot") != lease.worker_id
                    or metadata.get("reset_epoch") != f"reset-{expected_reset_epoch}"
                    or metadata.get("source_stamp", {}).get("simulation_session_id") != expected_session_id
                    or metadata.get("producer_pid") != os.getpid()
                    or metadata.get("producer_pgid") != os.getpgid(os.getpid())):
                raise ValueError("ACT_RESERVED_WORKSPACE_INVALID")
            self._reserved_metadata_sha256 = hashlib.sha256(metadata_bytes).hexdigest()
        self.episode_root = self.working / "episode"

    def seal(self, episode_seal_path: Path, *, teacher: dict, qc_report_path=None) -> Path:
        """Publish the attempt's result (schema 3).

        `teacher` is the Teacher's own result and the data status its child reported. The attempt status is derived
        from the Teacher fields alone. The episode and its independent QC are graded separately: a data problem makes
        the data INVALID or the QC FAIL/NOT_RUN and never changes the attempt status.
        """
        claim = _teacher_claim(teacher)
        status = teacher_attempt_status(claim["execution_status"], claim["task_result"])
        if self._reserved_workspace is not None:
            try:
                current = _read_regular(self.working / "workspace_identity.json")
            except OSError as error:
                raise ValueError("ACT_RESERVED_WORKSPACE_INVALID") from error
            if hashlib.sha256(current).hexdigest() != self._reserved_metadata_sha256:
                raise ValueError("ACT_RESERVED_WORKSPACE_INVALID")
        if _safe(episode_seal_path) != self.episode_root / "seal.json":
            raise ValueError("EPISODE_LOCATION_MISMATCH")
        _check_teacher_manifest(self.working / _TEACHER_MANIFEST, claim)
        data = self._grade_data(episode_seal_path, claim, qc_report_path)
        completed = self.clock()
        if (isinstance(completed, bool) or not isinstance(completed, (int, float))
                or not math.isfinite(completed)
                or not self.lease.lease_issued_monotonic_s < completed <= self.lease.lease_deadline_monotonic_s):
            raise ValueError("RESULT_AFTER_LEASE_DEADLINE")
        binding = data["binding"] or {key: None for key in _QC_MANIFEST_KEYS}
        manifest = {
            "kind": "ACT_COLLECTION_RESULT", "schema_version": 3,
            "lease_identity": self.identity,
            "status": status.value,
            "teacher_execution_status": claim["execution_status"],
            "teacher_task_result": claim["task_result"],
            "act_data_status": data["status"], "act_data_reason": data["reason"],
            "act_data_qc": data["qc"],
            "export_eligible": export_eligible(status, data["qc"], binding["collection_mode"]),
            "episode_seal_sha256": data["episode_sha256"],
            "completed_monotonic_s": float(completed),
            **binding,
        }
        try:
            with (self.working / "result.json").open("xb") as stream:
                stream.write(_canonical(manifest))
                stream.flush()
                os.fsync(stream.fileno())
            _fsync_dir(self.working)
            sealed = self.workspace / "sealed"
            if sealed.exists():
                raise ResultInfraError("RESULT_ALREADY_SEALED")
            os.rename(self.working, sealed)
            _fsync_dir(self.workspace)
            return sealed
        except OSError as error:
            raise ResultInfraError("RESULT_SEAL_FAILED") from error

    def _grade_data(self, episode_seal_path: Path, claim: dict, qc_report_path) -> dict:
        """The data side of the result: episode verification and the independent QC. Never raises on data problems.

        Returns the act_data_status to record (the child's, or INVALID when the data cannot be verified), the
        reason, act_data_qc (PASS, FAIL or NOT_RUN), the episode seal hash and the QC binding when QC ran.
        """
        status, reason = claim["data_status"], claim["data_reason"]
        qc_required = (self.inputs_manifest is not None or qc_report_path is not None
                       or _qc_required_when_readable(self.audit_manifest))
        if qc_required and (self.inputs_manifest is None or self.scope is None or self.audit_manifest is None):
            raise ValueError('RESULT_QC_ORIGINAL_BINDING_REQUIRED')
        episode_sha256 = None
        try:
            episode_sha256 = hashlib.sha256(_read_regular(episode_seal_path)).hexdigest()
        except OSError:
            pass

        def invalid(why):
            return dict(status="INVALID", reason=str(why)[:_REASON_MAX_CHARS], qc="NOT_RUN",
                        episode_sha256=episode_sha256, binding=None)

        if status in ("INVALID", "DISABLED"):
            return dict(status=status, reason=reason, qc="NOT_RUN", episode_sha256=episode_sha256, binding=None)
        memoised = (self.TRUST_FRESH_QC_MEMO and qc_report_path is not None and qc_required
                    and _safe(Path(qc_report_path)) == self.working / 'qc-report.json'
                    and _qc_memo_covers(qc_report_path, episode_root=self.episode_root, scope=self.scope,
                                        inputs_manifest=self.inputs_manifest))
        try:
            # a valid memo says the fresh-process QC has just run exactly this verification (seal, physical audit, native QC)
            episode = (_seal_facts(episode_seal_path) if memoised else
                       verify_episode_seal(episode_seal_path, audit_manifest=self.audit_manifest, scope=self.scope))
            _verify_audit_lease(self.audit_manifest, self.lease)
            if episode["attempt_id"] != self.lease.attempt_id:
                raise ValueError("LEASE_IDENTITY_MISMATCH")
            if (self.expected_session_id is not None
                    and episode["session_id"] != self.expected_session_id):
                raise ValueError("ACT_RESET_IDENTITY_MISMATCH")
            if (self.expected_reset_epoch is not None
                    and episode["reset_epoch"] != self.expected_reset_epoch):
                raise ValueError("ACT_RESET_IDENTITY_MISMATCH")
            if self._reserved_workspace is not None and episode["status"] == "PASSED" and not memoised:
                from .episode_qc import verify_episode_physical_audit
                verify_episode_physical_audit(self.episode_root, self.audit_manifest, self.scope)
        except (OSError, ValueError, TypeError) as error:
            return invalid("RESULT_EPISODE_INVALID: " + (str(error) or type(error).__name__))
        if not qc_required:
            return dict(status=status, reason=reason, qc="NOT_RUN", episode_sha256=episode_sha256, binding=None)
        target = self.working / 'qc-report.json'
        supplied = qc_report_path is not None
        if supplied and _safe(Path(qc_report_path)) != target:
            raise ValueError('RESULT_QC_LOCATION_INVALID')
        try:
            if not supplied:
                from .episode_qc import recompute_native_qc, write_qc_report
                report = recompute_native_qc(self.episode_root, scope=self.scope, inputs_manifest=self.inputs_manifest)
                write_qc_report(report, target)
            verified, digest, mode = _verify_result_qc(target, episode_root=self.episode_root,
                audit_manifest=self.audit_manifest, scope=self.scope, inputs_manifest=self.inputs_manifest,
                execution_lease=self.lease, trust_memo=self.TRUST_FRESH_QC_MEMO)
        except (OSError, ValueError, TypeError, KeyError) as error:
            if supplied:
                raise
            return invalid("RESULT_QC_NOT_RUN: " + (str(error) or type(error).__name__))
        binding = dict(qc_report_path='qc-report.json', qc_report_sha256=digest,
            inputs_sha256=verified['inputs_sha256'], scope_sha256=verified['scope_sha256'],
            audit_manifest_sha256=verified['audit_manifest_sha256'], collection_mode=mode)
        return dict(status=status, reason=reason, qc="PASS" if verified['status'] == 'PASS' else "FAIL",
                    episode_sha256=episode_sha256, binding=binding)

    def seal_attempt(self, lease: LeaseIdentity, decision) -> str:
        if _identity(lease) != self.identity:
            raise ValueError("LEASE_IDENTITY_MISMATCH")
        if self._reserved_workspace is not None:
            if lease.lease_issued_monotonic_s != self.lease.lease_issued_monotonic_s:
                raise ValueError("LEASE_IDENTITY_MISMATCH")
            # The actual Worker supplies its accepted EXECUTING lease, not the earlier reset-phase cap.
            self.lease = lease
        status = getattr(decision, "status", None)
        if status not in (AttemptStatus.PASSED, AttemptStatus.FAILED, AttemptStatus.INDETERMINATE):
            raise ValueError("RESULT_TERMINAL_INVALID")
        fields = (getattr(decision, "teacher_execution_status", None), getattr(decision, "teacher_task_result", None),
                  getattr(decision, "act_data_status", None))
        if any(value is None for value in fields):
            raise ValueError("RESULT_TEACHER_FIELDS_REQUIRED")
        claim = _teacher_claim(dict(execution_status=fields[0], task_result=fields[1], data_status=fields[2],
                                    data_reason=getattr(decision, "act_data_reason", None)))
        if teacher_attempt_status(claim["execution_status"], claim["task_result"]) is not status:
            raise ValueError("RESULT_TERMINAL_MISMATCH")
        episode_path = getattr(decision, "episode_seal_path", None)
        if episode_path is None and self._reserved_workspace is not None:
            episode_path = self.episode_root / "seal.json"
        if episode_path is None or _safe(Path(episode_path)) != self.episode_root / "seal.json":
            raise ValueError("EPISODE_LOCATION_MISMATCH")
        return str(self.seal(episode_path, teacher=claim, qc_report_path=getattr(decision, "qc_report_path", None)))

    def write_recovery_receipt(self, lease: LeaseIdentity, *, succeeded: bool,
                               generation: int, deadline_monotonic_s: float, clock) -> Path:
        if _identity(lease) != self.identity or generation != lease.worker_generation:
            raise ValueError("RECOVERY_IDENTITY_MISMATCH")
        if type(succeeded) is not bool or not callable(clock):
            raise ValueError("RECOVERY_RECEIPT_INVALID")
        now = clock()
        if (isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now)
                or isinstance(deadline_monotonic_s, bool)
                or not isinstance(deadline_monotonic_s, (int, float))
                or not math.isfinite(deadline_monotonic_s)
                or not lease.lease_issued_monotonic_s < now < deadline_monotonic_s):
            raise ValueError("RECOVERY_DEADLINE_INVALID")
        worker_root = self.workspace.parents[2]
        receipt_parent = _safe(worker_root / "recoveries" / lease.point_id / lease.attempt_id)
        receipt_parent.mkdir(parents=True, exist_ok=True)
        destination = receipt_parent / uuid.uuid4().hex
        destination.mkdir(exist_ok=False)
        path = destination / "recovery_receipt.json"
        document = {"kind": "ACT_RECOVERY_RECEIPT", "schema_version": 1,
                    "lease_identity": self.identity, "succeeded": succeeded,
                    "generation": generation, "completed_monotonic_s": float(now),
                    "deadline_monotonic_s": float(deadline_monotonic_s)}
        try:
            with path.open("xb") as stream:
                stream.write(_canonical(document))
                stream.flush()
                os.fsync(stream.fileno())
            for directory in (destination, receipt_parent, receipt_parent.parent,
                              receipt_parent.parent.parent, worker_root):
                _fsync_dir(directory)
            return path
        except OSError as error:
            raise ResultInfraError("RECOVERY_RECEIPT_WRITE_FAILED") from error

    def verify_recovery_receipt(self, location, lease: LeaseIdentity, *, succeeded: bool,
                                generation: int, deadline_monotonic_s: float, clock) -> bool:
        try:
            if _identity(lease) != self.identity or generation != lease.worker_generation:
                return False
            if type(succeeded) is not bool or not callable(clock):
                return False
            worker_root = self.workspace.parents[2]
            receipt_parent = worker_root / "recoveries" / lease.point_id / lease.attempt_id
            path = _safe(Path(location))
            if (path.name != "recovery_receipt.json" or path.parent.parent != receipt_parent
                    or len(path.parent.name) != 32
                    or not all(char in "0123456789abcdef" for char in path.parent.name)):
                return False
            data = _read_regular(path)
            document = json.loads(data)
            if not isinstance(document, dict) or data != _canonical(document):
                return False
            if (set(document) != {"kind", "schema_version", "lease_identity", "succeeded",
                                  "generation", "completed_monotonic_s", "deadline_monotonic_s"}
                    or document["kind"] != "ACT_RECOVERY_RECEIPT" or document["schema_version"] != 1
                    or document["lease_identity"] != self.identity or document["succeeded"] is not succeeded
                    or document["generation"] != generation
                    or document["deadline_monotonic_s"] != deadline_monotonic_s):
                return False
            completed = document["completed_monotonic_s"]
            current = clock()
            return (isinstance(completed, (int, float)) and not isinstance(completed, bool)
                    and math.isfinite(completed)
                    and lease.lease_issued_monotonic_s < completed < deadline_monotonic_s
                    and isinstance(current, (int, float)) and not isinstance(current, bool)
                    and math.isfinite(current) and completed <= current < deadline_monotonic_s)
        except (OSError, ValueError, TypeError, KeyError):
            return False


class ActCollectionResults:
    """The static Worker result port, with one private store per terminal lease."""

    _RESET_KEYS = frozenset({
        "lease_identity", "session_id", "reset_epoch", "joint_positions",
        "reset_completed_monotonic_s",
    })

    def __init__(self, worker_roots: Mapping[str, Path], *, clock) -> None:
        if not callable(clock):
            raise ValueError("RESULT_CLOCK_INVALID")
        self.worker_roots = {name: _safe(Path(root)) for name, root in worker_roots.items()}
        self.clock = clock
        self._stores: dict[tuple, ActCollectionResultStore] = {}

    @staticmethod
    def _key(lease: LeaseIdentity) -> tuple:
        identity = _identity(lease)
        return tuple(identity[name] for name in _IDENTITY_KEYS)

    def _store(self, lease: LeaseIdentity) -> ActCollectionResultStore:
        try:
            return self._stores[self._key(lease)]
        except KeyError as error:
            raise ValueError("ACT_WORKSPACE_NOT_RESERVED") from error

    def reserve_workspace(self, lease: LeaseIdentity, reset_receipt: dict) -> bool:
        key = self._key(lease)
        if key in self._stores:
            raise ValueError("ACT_WORKSPACE_ALREADY_RESERVED")
        if not isinstance(reset_receipt, dict) or set(reset_receipt) != self._RESET_KEYS:
            raise ValueError("ACT_RESET_RECEIPT_SCHEMA")
        if reset_receipt["lease_identity"] != _identity(lease):
            raise ValueError("ACT_RESET_IDENTITY_MISMATCH")
        session = reset_receipt["session_id"]
        epoch = reset_receipt["reset_epoch"]
        if (not isinstance(session, str) or not session
                or type(epoch) is not int or epoch < 0):
            raise ValueError("ACT_RESET_IDENTITY_MISMATCH")
        joints = reset_receipt["joint_positions"]
        if (not isinstance(joints, (list, tuple)) or len(joints) != 7
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) for value in joints)):
            raise ValueError("ACT_RESET_JOINTS_INVALID")
        completed = reset_receipt["reset_completed_monotonic_s"]
        if (isinstance(completed, bool) or not isinstance(completed, (int, float))
                or not math.isfinite(completed)
                or not lease.lease_issued_monotonic_s < completed < lease.lease_deadline_monotonic_s):
            raise ValueError("ACT_RESET_TIME_INVALID")
        if lease.worker_id not in self.worker_roots:
            raise ValueError("ACT_WORKER_ROOT_UNKNOWN")
        store = ActCollectionResultStore(
            _workspace(self.worker_roots[lease.worker_id], lease), lease,
            clock=self.clock, expected_session_id=session, expected_reset_epoch=epoch,
        )
        self._stores[key] = store
        return True

    def episode_root(self, lease: LeaseIdentity) -> Path:
        return self._store(lease).episode_root

    def seal_attempt(self, lease: LeaseIdentity, decision) -> str:
        return self._store(lease).seal_attempt(lease, decision)

    def write_recovery_receipt(self, lease: LeaseIdentity, **kwargs) -> Path:
        return self._store(lease).write_recovery_receipt(lease, **kwargs)

    def verify_recovery_receipt(self, location, lease: LeaseIdentity, **kwargs) -> bool:
        try:
            return self._store(lease).verify_recovery_receipt(location, lease, **kwargs)
        except ValueError:
            return False


class ActCollectionResultVerifier:
    """Coordinator port: verify only its registered Worker and exact lease path."""

    #: CP-3456: trust the offline processor's content-bound QC memo instead of repeating its five-minute recomputation. The Coordinator
    #: asks for it; the read-only readback never does.
    TRUST_FRESH_QC_MEMO = False

    def __init__(self, worker_roots: Mapping[str, Path], *, audit_manifest=None, scope=None, inputs_manifest=None,
                 trust_fresh_qc_memo=None) -> None:
        if trust_fresh_qc_memo is not None:
            self.TRUST_FRESH_QC_MEMO = bool(trust_fresh_qc_memo)
        if self.TRUST_FRESH_QC_MEMO:
            from . import qc_memo
            qc_memo.note_trusting_gate()
        self.worker_roots = {name: _safe(Path(root)) for name, root in worker_roots.items()}
        self.run_mode = RunMode.EXECUTE
        #: a v2 seal is verified only when both artifacts are supplied (CP-2765)
        self.audit_manifest = None if audit_manifest is None else _safe(Path(audit_manifest))
        self.scope = None if scope is None else _safe(Path(scope))
        self.inputs_manifest = None if inputs_manifest is None else _safe(Path(inputs_manifest))
        self._execution_journal_binding = None

    def bind_execution_journal(self, journal):
        """Bind the same actual Coordinator owner once; verification re-reads its durable frames."""
        from so101_demo.parallel_batch.journal import CoordinatorJournal
        if (type(journal) is not CoordinatorJournal or self._execution_journal_binding is not None
                or self.scope is None or journal._pid != os.getpid()):
            raise ValueError("RESULT_JOURNAL_BINDING_INVALID")
        journal.replay()
        self._execution_journal_binding = (_safe(journal.root), journal.batch_id, journal.coordinator_epoch)
        return True

    def bind_read_only_execution_journal(self, root, batch_id, coordinator_epoch):
        """Bind verified retained history in a fresh reader; acquire no journal authority."""
        from so101_demo.parallel_batch.journal import CoordinatorJournal
        if self._execution_journal_binding is not None or self.scope is None:
            raise ValueError('RESULT_JOURNAL_BINDING_INVALID')
        replay=CoordinatorJournal.read_only_replay(_safe(Path(root)),batch_id)
        if type(coordinator_epoch) is not int or not any(event.coordinator_epoch==coordinator_epoch for event in replay.events):
            raise ValueError('RESULT_JOURNAL_BINDING_INVALID')
        self._execution_journal_binding=(_safe(Path(root)),batch_id,coordinator_epoch)
        return True

    def _original_execution_lease(self, audit_manifest, final_lease):
        if self._execution_journal_binding is None:
            return final_lease
        from so101_demo.parallel_batch.journal import CoordinatorJournal
        root, batch_id, epoch = self._execution_journal_binding
        if (final_lease.batch_id != batch_id or final_lease.coordinator_epoch != epoch
                or audit_manifest is None):
            raise ValueError("RESULT_PHASE_LEASE_MISMATCH")
        audit = json.loads(_read_regular(audit_manifest))
        try:
            original = LeaseIdentity(**audit["identity"]["lease"])
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError("LEASE_IDENTITY_MISMATCH") from error
        if (_identity(original) != _identity(final_lease)
                or original.lease_issued_monotonic_s != final_lease.lease_issued_monotonic_s):
            raise ValueError("LEASE_IDENTITY_MISMATCH")
        execution, finalization, starts = [], [], 0
        replay = CoordinatorJournal.read_only_replay(root, batch_id)
        for event in replay.events:
            if event.coordinator_epoch != epoch:
                continue
            worker = event.payload.get("delta", {}).get("workers", {}).get(final_lease.worker_id)
            if not isinstance(worker, dict) or not isinstance(worker.get("lease"), dict):
                continue
            observed = LeaseIdentity(**worker["lease"])
            if _identity(observed) != _identity(final_lease):
                continue
            if event.type == "ATTEMPT_STARTED":
                starts += 1
            if (event.type in ("ATTEMPT_STARTED", "LEASE_RENEWED") and worker.get("state") == "EXECUTING"
                    and worker.get("action_allowed") is True and worker.get("inference_allowed") is True
                    and worker.get("reset_allowed") is False and worker.get("stop_requested") is False):
                execution.append(observed)
            if (event.type in ("FINALIZING_STARTED", "LEASE_RENEWED") and worker.get("state") == "FINALIZING"
                    and all(worker.get(name) is False for name in
                            ("action_allowed", "inference_allowed", "reset_allowed", "stop_requested"))):
                finalization.append(observed)
        if starts != 1 or original not in execution or not finalization or finalization[-1] != final_lease:
            raise ValueError("RESULT_PHASE_LEASE_MISMATCH")
        return original

    def _expected(self, lease: LeaseIdentity) -> Path:
        _identity(lease)
        if lease.worker_id not in self.worker_roots:
            raise ValueError("LEASE_IDENTITY_MISMATCH")
        # the coordinator names this directory by mode (`attempts` for an execution batch, `validations` when it
        # commits separate validation evidence); the expectation must switch the same way
        collection = "attempts" if self.run_mode is RunMode.EXECUTE else "validations"
        return _safe(_safe(self.worker_roots[lease.worker_id]) / collection / lease.point_id
                     / lease.attempt_id)

    def discover(self, lease: LeaseIdentity, workspace) -> str | None:
        """Return a fully verified seal only at the location the lease reserves.

        The same contract the generic production adapter implements, so a composition can drive either port through
        the same call: a deterministic lookup under the trusted worker root, restricted to the execution parent the
        journal reserved, and None for anything else (CP-2801).
        """
        root = self.worker_roots.get(lease.worker_id)
        if root is None:
            # an unknown worker is "not here", but a missing endpoint input is a misconfiguration and must not be
            # mistaken for one - only the lookup above is allowed to say None (CP-2805)
            return None
        try:
            parent = Path(root) / "attempts" / lease.point_id / lease.attempt_id
            if _safe(Path(workspace)) != parent:
                return None
            location = str(parent / "sealed")
            self.verify(lease, location, RunMode.EXECUTE)
            return location
        except (OSError, ValueError, TypeError):
            return None

    def verify(self, lease: LeaseIdentity, location: str, run_mode: RunMode, *, allow_legacy: bool = False) -> dict:
        """Verify one sealed result without modifying it; see `_verify`. The verifiers a result check repeats (the seal, the physical
        audit and the QC recomputation read the same files) run once per session."""
        import contextlib

        from . import qc_memo
        from .qc_session import active, qc_session

        if self.TRUST_FRESH_QC_MEMO and qc_memo.strict_active():
            raise qc_memo.ReadbackMemoForbidden("READBACK_MEMO_TRUST_FORBIDDEN")
        with contextlib.nullcontext() if active() is not None else qc_session():
            return self._verify(lease, location, run_mode, allow_legacy=allow_legacy)

    def _verify(self, lease: LeaseIdentity, location: str, run_mode: RunMode, *, allow_legacy: bool = False) -> dict:
        """Verify one sealed result without modifying it.

        Schema 3 is the only schema the Coordinator may commit. Schema 1 and 2 are the read-only legacy of the coupled
        contract: they are verified only for audit (`allow_legacy`), are never exportable, and are never committed.
        Any other version is rejected.
        """
        if run_mode is not RunMode.EXECUTE:
            raise ValueError("WRONG_RUN_MODE")
        workspace = self._expected(lease)
        sealed = _safe(Path(location))
        if sealed != workspace / "sealed":
            raise ValueError("LEASE_LOCATION_MISMATCH")
        if not sealed.is_dir():
            raise ValueError("RESULT_MISSING")
        data = _read_regular(sealed / "result.json")
        document = json.loads(data)
        version = document.get('schema_version') if type(document) is dict else None
        if type(version) is not int or version not in (1, 2, 3):
            raise ValueError("RESULT_SCHEMA_INVALID")
        if document.get("kind") != "ACT_COLLECTION_RESULT":
            raise ValueError("RESULT_SCHEMA_INVALID")
        if version < 3:
            if not allow_legacy:
                raise ValueError("RESULT_SCHEMA_LEGACY_READ_ONLY")
            return self._verify_legacy(lease, sealed, data, document, version)
        return self._verify_current(lease, sealed, data, document)

    def _common_checks(self, lease: LeaseIdentity, sealed: Path, document: dict):
        if document["lease_identity"] != _identity(lease):
            raise ValueError("LEASE_IDENTITY_MISMATCH")
        completed = document["completed_monotonic_s"]
        if (isinstance(completed, bool) or not isinstance(completed, (int, float))
                or not math.isfinite(completed)
                or not lease.lease_issued_monotonic_s < completed <= lease.lease_deadline_monotonic_s):
            raise ValueError("RESULT_AFTER_LEASE_DEADLINE")
        episode_path = sealed / "episode" / "seal.json"
        # The run supplies the original common scope; each lease owns its audit.
        # Never promote the episode's copied source.json to a trusted run scope.
        audit_manifest = self.audit_manifest
        if audit_manifest is None and self.scope is not None:
            audit_manifest = _safe(episode_path.parent / "audit" / "audit-manifest.json")
        return episode_path, audit_manifest

    def _qc_binding(self, lease, sealed, document, episode_path, audit_manifest, legacy=False):
        """Re-read the QC report and recompute its verdict; returns (report, binding)."""
        execution_lease = self._original_execution_lease(audit_manifest, lease)
        if document['qc_report_path'] != 'qc-report.json':
            raise ValueError('RESULT_QC_CURRENT_REPORT_REQUIRED')
        report, digest, mode = _verify_result_qc(sealed / 'qc-report.json', episode_root=episode_path.parent,
            audit_manifest=audit_manifest, scope=self.scope, inputs_manifest=self.inputs_manifest,
            execution_lease=execution_lease, legacy=legacy, trust_memo=self.TRUST_FRESH_QC_MEMO)
        binding = dict(qc_report_sha256=digest, inputs_sha256=report['inputs_sha256'],
            scope_sha256=report['scope_sha256'], audit_manifest_sha256=report['audit_manifest_sha256'],
            collection_mode=mode, episode_seal_sha256=report['episode_seal_sha256'])
        if any(document[key] != value for key, value in binding.items()):
            raise ValueError('RESULT_QC_MANIFEST_MISMATCH')
        return report, binding

    def _verify_current(self, lease: LeaseIdentity, sealed: Path, data: bytes, document: dict) -> dict:
        if set(document) != _RESULT_V3_KEYS:
            raise ValueError("RESULT_SCHEMA_INVALID")
        execution, task = document["teacher_execution_status"], document["teacher_task_result"]
        data_status, qc = document["act_data_status"], document["act_data_qc"]
        reason, export = document["act_data_reason"], document["export_eligible"]
        if (type(execution) is not str or type(task) is not str or execution not in EXECUTION_STATUSES
                or task not in TASK_RESULTS or data_status not in DATA_STATUSES or qc not in _ACT_DATA_QC
                or not (reason is None or type(reason) is str) or type(export) is not bool):
            raise ValueError("RESULT_TEACHER_FIELDS_INVALID")
        # the attempt status is the Teacher's, recomputed here and never read as a claim
        if document["status"] != teacher_attempt_status(execution, task).value:
            raise ValueError("RESULT_TEACHER_STATUS_MISMATCH")
        if export is not export_eligible(document["status"], qc, document["collection_mode"]):
            raise ValueError("RESULT_DATA_INCONSISTENT")
        if (qc != "NOT_RUN") != (document["qc_report_path"] is not None):
            raise ValueError("RESULT_DATA_INCONSISTENT")
        if qc != "NOT_RUN" and data_status not in ("VALID", "PENDING_QC"):
            raise ValueError("RESULT_DATA_INCONSISTENT")
        if qc == "NOT_RUN" and any(document[key] is not None for key in _QC_MANIFEST_KEYS):
            raise ValueError("RESULT_DATA_INCONSISTENT")
        episode_path, audit_manifest = self._common_checks(lease, sealed, document)
        _check_teacher_manifest(sealed / _TEACHER_MANIFEST, dict(execution_status=execution, task_result=task,
            data_status=data_status, data_reason=reason))
        recorded = document["episode_seal_sha256"]
        if qc != "NOT_RUN" and recorded is None:
            raise ValueError("RESULT_DATA_INCONSISTENT")
        if recorded is not None and hashlib.sha256(_read_regular(episode_path)).hexdigest() != recorded:
            raise ValueError("EPISODE_SEAL_HASH_MISMATCH")
        verdict = {"status": document["status"], "sha256": hashlib.sha256(data).hexdigest(),
                   "schema_version": 3, **{key: document[key] for key in _DATA_FIELDS},
                   **{key: document[key] for key in _QC_MANIFEST_KEYS - {"qc_report_path"}},
                   "episode_seal_sha256": recorded}
        if data_status in ("VALID", "PENDING_QC") and recorded is not None:
            # Data the store graded as sound is re-verified from the sealed files, never read as a claim. Where this gate trusts the
            # fresh-process QC's memo and the memo covers these exact files, that verification (seal, physical audit, native QC) is the
            # one the memo records.
            memoised = (self.TRUST_FRESH_QC_MEMO and qc != "NOT_RUN" and document["qc_report_path"] == "qc-report.json"
                        and _qc_memo_covers(sealed / "qc-report.json", episode_root=episode_path.parent, scope=self.scope,
                                            inputs_manifest=self.inputs_manifest))
            episode = (_seal_facts(episode_path) if memoised else
                       verify_episode_seal(episode_path, audit_manifest=audit_manifest, scope=self.scope))
            if episode["attempt_id"] != lease.attempt_id:
                raise ValueError("RESULT_EPISODE_MISMATCH")
            execution_lease = self._original_execution_lease(audit_manifest, lease)
            _verify_audit_lease(audit_manifest, execution_lease)
            if self._execution_journal_binding is not None and episode["status"] == "PASSED" and not memoised:
                from .episode_qc import verify_episode_physical_audit
                verify_episode_physical_audit(episode_path.parent, audit_manifest, self.scope)
        if qc != "NOT_RUN":
            report, _ = self._qc_binding(lease, sealed, document, episode_path, audit_manifest)
            if (qc == "PASS") != (report["status"] == "PASS"):
                raise ValueError("RESULT_QC_MANIFEST_MISMATCH")
        return verdict

    def _verify_legacy(self, lease: LeaseIdentity, sealed: Path, data: bytes, document: dict, version: int) -> dict:
        """Read-only audit of a schema 1/2 result, whose status was gated by the episode and QC verdicts."""
        if set(document) != (_LEGACY_MANIFEST_KEYS | _QC_MANIFEST_KEYS if version == 2 else _LEGACY_MANIFEST_KEYS):
            raise ValueError("RESULT_SCHEMA_INVALID")
        if self.inputs_manifest is not None and version != 2:
            raise ValueError('RESULT_QC_CURRENT_REPORT_REQUIRED')
        episode_path, audit_manifest = self._common_checks(lease, sealed, document)
        if hashlib.sha256(_read_regular(episode_path)).hexdigest() != document["episode_seal_sha256"]:
            raise ValueError("EPISODE_SEAL_HASH_MISMATCH")
        episode = verify_episode_seal(episode_path, audit_manifest=audit_manifest, scope=self.scope)
        execution_lease = self._original_execution_lease(audit_manifest, lease)
        _verify_audit_lease(audit_manifest, execution_lease)
        if (episode["attempt_id"] != lease.attempt_id
                or (version == 1 and (document["status"] != episode["status"]
                    or document["qc_passed"] is not episode["qc_passed"]))):
            raise ValueError("RESULT_EPISODE_MISMATCH")
        if self._execution_journal_binding is not None and document["status"] == "PASSED":
            from .episode_qc import verify_episode_physical_audit
            verify_episode_physical_audit(episode_path.parent, audit_manifest, self.scope)
        verdict = {"status": document["status"], "sha256": hashlib.sha256(data).hexdigest(),
                   "legacy_schema_version": version, "export_eligible": False}
        if version == 2 or _current_qc_required(audit_manifest):
            if version != 2:
                raise ValueError('RESULT_QC_CURRENT_REPORT_REQUIRED')
            report, binding = self._qc_binding(lease, sealed, document, episode_path, audit_manifest, legacy=True)
            if (document['status'] != ('PASSED' if report['status'] == 'PASS' else 'FAILED')
                    or document['qc_passed'] is not (report['status'] == 'PASS')):
                raise ValueError('RESULT_QC_MANIFEST_MISMATCH')
            verdict.update(binding)
        return verdict

    def discover(self, lease: LeaseIdentity, workspace: Path) -> str | None:
        try:
            expected = self._expected(lease)
            if _safe(workspace) != expected:
                return None
            sealed = expected / "sealed"
            self.verify(lease, str(sealed), RunMode.EXECUTE)
            return str(sealed)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None


def resolve_native_run(run_root):
    """Locate retained originals from one actual dispatch and its journaled lease workspace."""
    from .first_episode_inputs import verify_frozen_inputs
    from .collection_scope import read_collection_scope,build_collection_scope
    from so101_demo.parallel_batch.journal import CoordinatorJournal,JournalCorruption
    try:
        root=_safe(Path(run_root));metadata={}
        for line in _read_regular(root/'run.log').decode().splitlines():
            key,separator,value=line.partition('=')
            if separator and key in ('batch_id','mode','lifecycle','inputs'):
                if key in metadata:raise ValueError('ambiguous run locator')
                metadata[key]=value
        if set(metadata)!={'batch_id','mode','lifecycle','inputs'} or metadata['lifecycle']!='FULL_RESTART':
            raise ValueError('run metadata absent')
        inputs_manifest=_safe(Path(metadata['inputs'])/'inputs-manifest.json')
        frozen=verify_frozen_inputs(inputs_manifest)
        if (_read_regular(root/'inputs-manifest.json')!=_read_regular(inputs_manifest)
                or frozen['mode']!=metadata['mode']):
            raise ValueError('original inputs mismatch')
        scope=root/'episode-scope.json'
        anchor=frozen['roles']['anchor_scene']['identity']
        if read_collection_scope(scope)!=build_collection_scope(frozen['mode'],scene_id=anchor['scene_id'],
                seed=anchor['seed'],inputs_sha256=frozen['inputs_sha256']):
            raise ValueError('original scope mismatch')
        coordinator_root=root/'run/coordinator'
        replay=CoordinatorJournal.read_only_replay(coordinator_root,metadata['batch_id'])
        grants=[event for event in replay.events if event.type=='LEASE_GRANTED']
        starts=[event for event in replay.events if event.type=='BATCH_STARTED']
        if len(grants)!=1 or len(starts)!=1:
            raise ValueError('one run lease required')
        request=starts[0].payload['delta']['request']
        current=LeaseIdentity(**grants[0].payload['response'])
        workspace=_workspace(root/'run/workers'/current.worker_id,current)
        observed=grants[0].payload['delta']['workers'][current.worker_id]['workspace']
        if (request['batch_id']!=metadata['batch_id'] or request['run_mode']!=RunMode.EXECUTE.value
                or request['worker_count']!=1 or request['selected_point_ids']!=[current.point_id]
                or _safe(Path(request['evidence_root']))!=root/'run'
                or _safe(Path(observed))!=workspace):
            raise ValueError('journaled run locator mismatch')
        location=workspace/'sealed'
        if not location.is_dir():raise ValueError('sealed result missing')
        return dict(episode=location/'episode',location=location,scope=scope,
            inputs_manifest=inputs_manifest,coordinator_root=coordinator_root)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,JournalCorruption) as error:
        raise ValueError('RESULT_RUN_CONTEXT_INVALID') from error


def verify_coordinator_commit(coordinator_root, *, location, scope, inputs_manifest):
    """Re-read the actual hash chain, projection, original phase leases and QC-bound receipt."""
    from copy import deepcopy
    from so101_demo.parallel_batch.journal import CoordinatorJournal,JournalCorruption
    from so101_demo.parallel_batch.contracts import BatchSummary,PointStatus,ValidationStatus
    try:
        root=_safe(Path(coordinator_root));location=_safe(Path(location))
        epoch=json.loads(_read_regular(root/'coordinator_epoch.json'))
        batch_id=epoch['batch_id']
        replay=CoordinatorJournal.read_only_replay(root,batch_id)
        commits=[event for event in replay.events if event.type=='RESULT_COMMITTED'
            and event.payload.get('identity',{}).get('location')==str(location)]
        if len(commits)!=1:
            raise ValueError('COMMIT_MISSING_OR_CONFLICTING')
        commit=commits[0]
        identity=commit.payload['identity']
        state=dict(workers={},points={});before_commit=None
        for event in replay.events:
            if event is commit:
                before_commit=deepcopy(state)
            delta=deepcopy(event.payload['delta'])
            for name in ('workers','points'):
                state[name].update(delta.pop(name,{}))
            state.update(delta)
        request=state['request']
        if (request['batch_id']!=batch_id or request['run_mode']!=RunMode.EXECUTE.value
                or _safe(Path(request['evidence_root']))!=root.parent):
            raise ValueError('COMMIT_REQUEST_MISMATCH')
        worker_id=identity['worker_id'];worker=before_commit['workers'][worker_id]
        final_lease=LeaseIdentity(**worker['lease'])
        if (worker['state']!='FINALIZING' or worker['stop_requested'] is not False
                or any(worker[name] is not False for name in ('action_allowed','inference_allowed','reset_allowed'))
                or commit.coordinator_epoch!=final_lease.coordinator_epoch
                or identity!={**_identity(final_lease),'location':str(location)}):
            raise ValueError('COMMIT_PHASE_MISMATCH')
        worker_root=root.parent/'workers'/worker_id
        expected=_workspace(worker_root,final_lease)
        if location!=expected/'sealed' or _safe(Path(worker['workspace']))!=expected:
            raise ValueError('COMMIT_LOCATION_MISMATCH')
        verifier=ActCollectionResultVerifier({worker_id:worker_root},scope=scope,inputs_manifest=inputs_manifest)
        verifier.bind_read_only_execution_journal(root,batch_id,commit.coordinator_epoch)
        # a read-only audit may replay a legacy (schema 1/2) commit; it is never reported as exportable
        result=verifier.verify(final_lease,str(location),RunMode.EXECUTE,allow_legacy=True)
        receipt=commit.payload['response']
        binding={key:result[key] for key in ('qc_report_sha256','episode_seal_sha256','inputs_sha256','scope_sha256',
            'audit_manifest_sha256','collection_mode')}
        current='legacy_schema_version' not in result
        data={key:result[key] for key in _DATA_FIELDS} if current else {}
        point_record={key:result[key] for key in ACT_POINT_RESULT_KEYS} if current else None
        if (set(receipt)!={'status','sha256','location','recovery_deadline_monotonic_s',*binding,*data}
                or receipt['location']!=str(location) or receipt['status']!=result['status']
                or receipt['sha256']!=result['sha256'] or any(receipt[key]!=value for key,value in binding.items())
                or any(receipt[key]!=value for key,value in data.items())
                or commit.payload['delta'].get('act_results',{}).get(final_lease.point_id)!=point_record
                or commit.payload['delta']['points'][final_lease.point_id]['status']!=result['status']
                or commit.payload['delta']['points'][final_lease.point_id]['terminal'] is not True
                or commit.payload['delta']['workers'][worker_id]['lease'] is not None
                or commit.payload['delta']['workers'][worker_id]['state']!='RECOVERING'
                or commit.payload['delta']['workers'][worker_id]['recovery_deadline_monotonic_s']!=receipt['recovery_deadline_monotonic_s']):
            raise ValueError('COMMIT_RECEIPT_MISMATCH')
        summary=BatchSummary(RunMode.EXECUTE,{key:PointStatus(value['status']) for key,value in state['points'].items()},
            batch_terminal=all(value['terminal'] for value in state['points'].values()),
            validation_statuses={key:ValidationStatus(value['validation_status']) for key,value in state['points'].items()
                if value['validation_status'] is not None},batch_cleanup_complete=state['batch_cleanup_complete'],
            terminal_reason=state['terminal_reason'])
        expected_index={**state,**{key:getattr(summary,key) for key in ('coverage_complete','execution_complete',
            'validation_complete','validation_passed','qualification_applicable','qualification_passed')}}
        index_path=root/'aggregate_results.json'
        if json.loads(_read_regular(index_path))!=expected_index:
            raise ValueError('COMMIT_INDEX_MISMATCH')
        return dict(kind='ACT_COORDINATOR_COMMIT_PROOF',schema_version=1,status='PASS',
            result_status=result['status'],
            result_schema_version=3 if current else result['legacy_schema_version'],
            export_eligible=result['export_eligible'],
            **({key:result[key] for key in ('teacher_execution_status','teacher_task_result','act_data_status',
                'act_data_qc')} if current else {}),
            identity=identity,receipt=receipt,**binding,
            result_sha256=result['sha256'],commit_sequence=commit.sequence,commit_frame_sha256=commit.frame_sha256,
            journal_terminal_sha256=replay.events[-1].frame_sha256,
            aggregate_sha256=hashlib.sha256(_read_regular(index_path)).hexdigest())
    except (OSError,ValueError,TypeError,KeyError,JournalCorruption) as error:
        raise ValueError('RESULT_COMMIT_READBACK_INVALID') from error


def verify_coordinator_cleanup(coordinator_root, *, commit_proof):
    """Read the original cleanup artifact and its post-commit terminal journal event."""
    from so101_demo.parallel_batch.journal import CoordinatorJournal, JournalCorruption

    try:
        root = _safe(Path(coordinator_root))
        identity = commit_proof['identity']
        if (commit_proof['kind'] != 'ACT_COORDINATOR_COMMIT_PROOF'
                or commit_proof['schema_version'] != 1 or commit_proof['status'] != 'PASS'):
            raise ValueError('verified commit required')
        replay = CoordinatorJournal.read_only_replay(root, identity['batch_id'])
        commits = [event for event in replay.events if event.type == 'RESULT_COMMITTED'
            and event.sequence == commit_proof['commit_sequence']]
        cleanups = [event for event in replay.events if event.type == 'BATCH_CLEANUP_COMPLETE']
        if (len(commits) != 1 or len(cleanups) != 1
                or commits[0].frame_sha256 != commit_proof['commit_frame_sha256']
                or commits[0].payload['identity'] != identity
                or commits[0].payload['response'] != commit_proof['receipt']
                or cleanups[0].sequence <= commits[0].sequence
                or cleanups[0] is not replay.events[-1]
                or replay.events[-1].frame_sha256 != commit_proof['journal_terminal_sha256']):
            raise ValueError('original terminal cleanup required')
        cleanup = cleanups[0]
        delta = cleanup.payload['delta']
        if (set(delta) != {'points', 'workers', 'batch_cleanup_complete'}
                or delta['batch_cleanup_complete'] is not True
                or not delta['workers'] or not delta['points']
                or identity['worker_id'] not in delta['workers']
                or delta['points'][identity['point_id']]['status'] != commit_proof['result_status']):
            raise ValueError('cleanup projection mismatch')
        for worker in delta['workers'].values():
            if (worker['state'] != 'STOPPED' or worker['stop_requested'] is not True
                    or worker['lease'] is not None
                    or any(worker[name] is not False for name in
                           ('action_allowed', 'inference_allowed', 'reset_allowed'))):
                raise ValueError('worker cleanup incomplete')
        if any(point['terminal'] is not True or point['active_attempt'] is not None
               for point in delta['points'].values()):
            raise ValueError('point cleanup incomplete')
        path = root.parent / 'cleanup-gates.json'
        raw = _read_regular(path)
        document = json.loads(raw)
        expected_keys = {'schema_version', 'batch_id', 'actions', 'process_cleanup',
            'container_cleanup', 'cleanup_gates_passed', 'coordinator_completion',
            'batch_cleanup_complete'}
        success = dict(succeeded=True, error_type=None, error_message=None)
        actions = {'stop_leases', 'cancel_goal', 'confirm_goal_cancelled', 'request_recovery'}
        if (set(document) != expected_keys or type(document['schema_version']) is not int
                or document['schema_version'] != 1 or document['batch_id'] != identity['batch_id']
                or document['cleanup_gates_passed'] is not True
                or document['batch_cleanup_complete'] is not True
                or set(document['actions']) != actions
                or document['coordinator_completion'] != dict(
                    attempted=True, succeeded=True, error_type=None, error_message=None)):
            raise ValueError('cleanup artifact incomplete')
        records = [document['process_cleanup'], document['container_cleanup'],
                   *document['actions'].values()]
        if (any(record != success or record['succeeded'] is not True for record in records)
                or document['coordinator_completion']['attempted'] is not True
                or document['coordinator_completion']['succeeded'] is not True):
            raise ValueError('cleanup action incomplete')
        return dict(kind='ACT_COORDINATOR_CLEANUP_PROOF', schema_version=1, status='PASS',
            identity=identity, cleanup_sequence=cleanup.sequence,
            cleanup_frame_sha256=cleanup.frame_sha256, cleanup_proof_path=str(path),
            cleanup_sha256=hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, TypeError, KeyError, JournalCorruption) as error:
        raise ValueError('RESULT_CLEANUP_READBACK_INVALID') from error


def write_commit_proof(proof, output):
    """Publish a new durable readback artifact; it grants no execution or commit authority."""
    if (type(proof) is not dict or proof.get('kind')!='ACT_COORDINATOR_COMMIT_PROOF'
            or proof.get('schema_version')!=1 or proof.get('status')!='PASS'):
        raise ValueError('COMMIT_PROOF_INVALID')
    return _publish_readback_proof(proof,output)


def write_export_rejection_proof(proof,output):
    """Publish the two actual common export refusals without granting training eligibility."""
    if (type(proof) is not dict or proof.get('kind')!='ACT_DIAGNOSTIC_EXPORT_REJECTION'
            or proof.get('schema_version')!=1 or proof.get('status')!='PASS'
            or proof.get('dataset_produced') is not False
            or proof.get('perception_or_policy_models_loaded') is not False
            or proof.get('checks')!={'resolver':'DIAGNOSTIC_EPISODE_NOT_TRAINABLE',
                                    'direct_export':'DIAGNOSTIC_EPISODE_NOT_TRAINABLE'}):
        raise ValueError('EXPORT_REJECTION_PROOF_INVALID')
    return _publish_readback_proof(proof,output)


def write_readback_receipt(receipt,output):
    """Publish the combined receipt of one independent readback; it grants no execution, commit or export authority."""
    if (type(receipt) is not dict or receipt.get('kind')!='ACT_READBACK_RECEIPT' or receipt.get('schema_version')!=1
            or receipt.get('status') not in ('PASS','FAIL')):
        raise ValueError('READBACK_RECEIPT_INVALID')
    return _publish_readback_proof(receipt,output)


def _publish_readback_proof(proof,output):
    target=_safe(Path(output))
    if target.exists():raise ValueError('COMMIT_PROOF_ALREADY_WRITTEN')
    payload=_canonical(proof)
    staged=target.parent/('.'+target.name+'.'+uuid.uuid4().hex+'.pending')
    try:
        fd=os.open(staged,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(payload);stream.flush();os.fsync(stream.fileno())
        _fsync_dir(target.parent)
        os.link(staged,target,follow_symlinks=False)
        _fsync_dir(target.parent)
    except OSError as error:
        raise ValueError('COMMIT_PROOF_UNWRITABLE') from error
    return hashlib.sha256(payload).hexdigest()
