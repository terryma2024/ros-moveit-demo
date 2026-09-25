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


class ResultInfraError(RuntimeError):
    """A result could not be durably sealed; no business terminal is implied."""


_IDENTITY_KEYS = (
    "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
    "point_id", "attempt_id", "lease_generation",
)
_MANIFEST_KEYS = frozenset({
    "kind", "schema_version", "lease_identity", "status", "qc_passed",
    "episode_seal_sha256", "completed_monotonic_s",
})


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


class ActCollectionResultStore:
    """One writer at the workspace reserved by a Coordinator lease."""

    def __init__(self, workspace: Path, lease: LeaseIdentity, *, clock,
                 expected_session_id: str | None = None,
                 expected_reset_epoch: int | None = None) -> None:
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
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.working = self.workspace / "working"
        self.working.mkdir(exist_ok=False)
        self.episode_root = self.working / "episode"

    def seal(self, episode_seal_path: Path) -> Path:
        if _safe(episode_seal_path) != self.episode_root / "seal.json":
            raise ValueError("EPISODE_LOCATION_MISMATCH")
        try:
            episode = verify_episode_seal(episode_seal_path)
            if episode["attempt_id"] != self.lease.attempt_id:
                raise ValueError("LEASE_IDENTITY_MISMATCH")
            if (self.expected_session_id is not None
                    and episode["session_id"] != self.expected_session_id):
                raise ValueError("ACT_RESET_IDENTITY_MISMATCH")
            if (self.expected_reset_epoch is not None
                    and episode["reset_epoch"] != self.expected_reset_epoch):
                raise ValueError("ACT_RESET_IDENTITY_MISMATCH")
            episode_sha256 = hashlib.sha256(_read_regular(episode_seal_path)).hexdigest()
        except (OSError, ValueError, TypeError) as error:
            raise ResultInfraError("RESULT_EPISODE_INVALID") from error
        completed = self.clock()
        if (isinstance(completed, bool) or not isinstance(completed, (int, float))
                or not math.isfinite(completed)
                or not self.lease.lease_issued_monotonic_s < completed <= self.lease.lease_deadline_monotonic_s):
            raise ValueError("RESULT_AFTER_LEASE_DEADLINE")
        manifest = {
            "kind": "ACT_COLLECTION_RESULT", "schema_version": 1,
            "lease_identity": self.identity, "status": episode["status"],
            "qc_passed": episode["qc_passed"],
            "episode_seal_sha256": episode_sha256,
            "completed_monotonic_s": float(completed),
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

    def seal_attempt(self, lease: LeaseIdentity, decision) -> str:
        if _identity(lease) != self.identity:
            raise ValueError("LEASE_IDENTITY_MISMATCH")
        status = getattr(decision, "status", None)
        if status not in (AttemptStatus.PASSED, AttemptStatus.FAILED):
            raise ValueError("RESULT_TERMINAL_INVALID")
        episode_path = getattr(decision, "episode_seal_path", None)
        if episode_path is None or _safe(Path(episode_path)) != self.episode_root / "seal.json":
            raise ValueError("EPISODE_LOCATION_MISMATCH")
        try:
            episode = verify_episode_seal(episode_path)
        except (OSError, ValueError, TypeError) as error:
            raise ResultInfraError("RESULT_EPISODE_INVALID") from error
        if episode["status"] != status.value:
            raise ValueError("RESULT_TERMINAL_MISMATCH")
        return str(self.seal(episode_path))

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

    def __init__(self, worker_roots: Mapping[str, Path]) -> None:
        self.worker_roots = {name: _safe(Path(root)) for name, root in worker_roots.items()}
        self.run_mode = RunMode.EXECUTE

    def _expected(self, lease: LeaseIdentity) -> Path:
        _identity(lease)
        if lease.worker_id not in self.worker_roots:
            raise ValueError("LEASE_IDENTITY_MISMATCH")
        return _workspace(self.worker_roots[lease.worker_id], lease)

    def verify(self, lease: LeaseIdentity, location: str, run_mode: RunMode) -> dict:
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
        if not isinstance(document, dict) or set(document) != _MANIFEST_KEYS:
            raise ValueError("RESULT_SCHEMA_INVALID")
        if document["kind"] != "ACT_COLLECTION_RESULT" or document["schema_version"] != 1:
            raise ValueError("RESULT_SCHEMA_INVALID")
        if document["lease_identity"] != _identity(lease):
            raise ValueError("LEASE_IDENTITY_MISMATCH")
        completed = document["completed_monotonic_s"]
        if (isinstance(completed, bool) or not isinstance(completed, (int, float))
                or not math.isfinite(completed)
                or not lease.lease_issued_monotonic_s < completed <= lease.lease_deadline_monotonic_s):
            raise ValueError("RESULT_AFTER_LEASE_DEADLINE")
        episode_path = sealed / "episode" / "seal.json"
        episode_bytes = _read_regular(episode_path)
        if hashlib.sha256(episode_bytes).hexdigest() != document["episode_seal_sha256"]:
            raise ValueError("EPISODE_SEAL_HASH_MISMATCH")
        episode = verify_episode_seal(episode_path)
        if (episode["attempt_id"] != lease.attempt_id
                or document["status"] != episode["status"]
                or document["qc_passed"] is not episode["qc_passed"]):
            raise ValueError("RESULT_EPISODE_MISMATCH")
        _fsync_dir(workspace)
        return {"status": document["status"], "sha256": hashlib.sha256(data).hexdigest()}

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
