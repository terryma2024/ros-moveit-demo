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

from .recorder import verify_episode_seal
from so101_demo.parallel_batch.contracts import LeaseIdentity, RunMode


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

    def __init__(self, workspace: Path, lease: LeaseIdentity, *, clock) -> None:
        self.workspace = _safe(workspace)
        self.lease = lease
        self.identity = _identity(lease)
        if self.workspace.name != lease.attempt_id or self.workspace.parent.name != lease.point_id or self.workspace.parent.parent.name != "attempts":
            raise ValueError("LEASE_LOCATION_MISMATCH")
        if not callable(clock):
            raise ValueError("RESULT_CLOCK_INVALID")
        self.clock = clock
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
