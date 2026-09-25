"""Lossless Task 9 episode spool and immutable, uncommitted terminal seal."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import tempfile
import zlib

from .contracts import finite, identifier, integer, sha256, validate_action, validate_observation, vector


class RecorderInfraError(RuntimeError):
    """Lossless evidence or seal durability could not be established."""


_AUDIT_KEYS = frozenset({
    "session_id", "attempt_id", "reset_epoch", "release_epoch", "release_event",
    "release_time_s", "physical_stamps",
    "phase", "reference_time_s", "reference_source", "reference_positions", "source_stamps",
    "mujoco_truth", "contacts", "planning_scene", "controller_state",
})
_PROVENANCE_KEYS = frozenset({
    "source_sha256", "scene_sha256", "config_sha256", "policy_fingerprint", "seed",
})
_OUTCOME_KEYS = frozenset({"status", "reason", "task8_success", "stopped_confirmed"})


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_grid(times: list[float] | tuple[float, ...], dt: float = 0.1) -> None:
    step = finite(dt)
    if step <= 0 or not isinstance(times, (list, tuple)) or len(times) < 2:
        raise ValueError("EPISODE_TIME_GAP")
    checked = [finite(value, nonnegative=True) for value in times]
    if any(not math.isclose(b - a, step, rel_tol=0, abs_tol=1e-6)
           for a, b in zip(checked, checked[1:])):
        raise ValueError("EPISODE_TIME_GAP")


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def _rgb_png(frame) -> bytes:
    # validate_observation has already checked 480x640x3 uint8. PNG color type 2
    # with filter 0 preserves every original RGB byte and needs no image library.
    raw = b"".join(b"\x00" + frame[row].tobytes() for row in range(480))
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 640, 480, 8, 2, 0, 0, 0))
            + _png_chunk(b"IDAT", zlib.compress(raw, level=6))
            + _png_chunk(b"IEND", b""))


def _regular_hash(path: Path) -> tuple[str, int]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("EPISODE_FILE_INVALID")
        data = stream.read()
    return _hash(data), len(data)


class EpisodeRecorder:
    def __init__(self, root: Path, *, session_id: str, attempt_id: str,
                 reset_epoch: int, provenance: dict, dt_s: float = 0.1,
                 max_source_age_s: float = 0.1) -> None:
        self.root = Path(root)
        if not self.root.is_absolute() or ".." in self.root.parts:
            raise ValueError("EPISODE_ROOT_INVALID")
        self.session_id = identifier(session_id)
        self.attempt_id = identifier(attempt_id)
        self.reset_epoch = integer(reset_epoch)
        if not isinstance(provenance, dict) or set(provenance) != _PROVENANCE_KEYS:
            raise ValueError("EPISODE_PROVENANCE_INVALID")
        for key in _PROVENANCE_KEYS - {"seed"}:
            sha256(provenance[key])
        integer(provenance["seed"])
        self.provenance = dict(provenance)
        self.dt_s = finite(dt_s)
        self.max_source_age_s = finite(max_source_age_s)
        if self.dt_s != 0.1 or self.max_source_age_s != 0.1:
            raise ValueError("EPISODE_CONFIG_INVALID")
        self.root.mkdir(parents=False, exist_ok=False)
        (self.root / "frames").mkdir()
        self._records = (self.root / "records.jsonl").open("xb")
        self._times: list[float] = []
        self._release_epoch: int | None = None
        self._release_time_s: float | None = None
        self._files: dict[str, dict] = {}
        self._failed = False
        self._closed = False

    def _audit(self, observation: dict, action: tuple, audit: dict) -> None:
        if not isinstance(audit, dict) or set(audit) != _AUDIT_KEYS:
            raise ValueError("EPISODE_AUDIT_SCHEMA")
        if (audit["session_id"] != self.session_id
                or audit["attempt_id"] != self.attempt_id
                or type(audit["reset_epoch"]) is not int
                or audit["reset_epoch"] != self.reset_epoch):
            raise ValueError("EPISODE_SCOPE_INVALID")
        epoch = integer(audit["release_epoch"])
        if type(audit["release_event"]) is not bool:
            raise ValueError("RELEASE_EPOCH_INVALID")
        if self._release_epoch is None:
            if audit["release_event"]:
                raise ValueError("RELEASE_EPOCH_INVALID")
        elif epoch == self._release_epoch:
            if audit["release_event"]:
                raise ValueError("RELEASE_EPOCH_INVALID")
        elif not (epoch == self._release_epoch + 1 and audit["release_event"] is True
                  and audit["phase"] == "RELEASE"):
            raise ValueError("RELEASE_EPOCH_INVALID")
        t = observation["sim_time_s"]
        if (audit["reference_source"] != "CONTROLLER_REFERENCE"
                or not math.isclose(finite(audit["reference_time_s"]), t + self.dt_s,
                                    rel_tol=0, abs_tol=1e-6)
                or any(not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-6)
                       for actual, expected in zip(action,
                           validate_action(audit["reference_positions"]), strict=True))):
            raise ValueError("EPISODE_REFERENCE_INVALID")
        stamps = audit["source_stamps"]
        if not isinstance(stamps, dict) or set(stamps) != {"head", "wrist", "arm", "neck"}:
            raise ValueError("EPISODE_SOURCE_STAMPS_INVALID")
        if any(not 0 <= t - finite(stamp, nonnegative=True) <= self.max_source_age_s
               for stamp in stamps.values()):
            raise ValueError("EPISODE_SOURCE_STALE")
        physical = audit["physical_stamps"]
        if not isinstance(physical, dict) or set(physical) != {"cup", "contacts", "planning_scene"}:
            raise ValueError("EPISODE_PHYSICAL_STAMPS_INVALID")
        if any(not 0 <= t - finite(stamp, nonnegative=True) <= self.max_source_age_s
               for stamp in physical.values()):
            raise ValueError("EPISODE_SOURCE_STALE")
        if audit["release_event"]:
            release_time = finite(audit["release_time_s"], nonnegative=True)
            if (not self._times or not self._times[-1] < release_time <= t
                    or any(stamp < release_time for stamp in physical.values())):
                raise ValueError("RELEASE_EVIDENCE_STALE")
        elif self._release_time_s is None:
            if audit["release_time_s"] is not None:
                raise ValueError("RELEASE_EPOCH_INVALID")
        elif (audit["release_time_s"] != self._release_time_s
              or any(stamp < self._release_time_s for stamp in physical.values())):
            raise ValueError("RELEASE_EVIDENCE_STALE")
        identifier(audit["phase"])
        if (not isinstance(audit["mujoco_truth"], dict)
                or not isinstance(audit["contacts"], list)
                or not isinstance(audit["planning_scene"], dict)
                or not isinstance(audit["controller_state"], dict)):
            raise ValueError("EPISODE_AUDIT_SCHEMA")

    def _write_file(self, relative: str, data: bytes) -> None:
        path = self.root / relative
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
        self._files[relative] = {"sha256": _hash(data), "size": len(data)}

    def append(self, observation: dict, action: tuple, audit: dict) -> None:
        if self._failed or self._closed:
            raise RecorderInfraError("RECORDER_NOT_WRITABLE")
        checked = validate_observation(observation)
        if checked["session_id"] != self.session_id or checked["attempt_id"] != self.attempt_id:
            raise ValueError("EPISODE_SCOPE_INVALID")
        label = validate_action(action)
        t = checked["sim_time_s"]
        if self._times and not math.isclose(t - self._times[-1], self.dt_s,
                                            rel_tol=0, abs_tol=1e-6):
            raise ValueError("EPISODE_TIME_GAP")
        self._audit(checked, label, audit)
        index = len(self._times)
        head_path = f"frames/{index:06d}-head.png"
        wrist_path = f"frames/{index:06d}-wrist.png"
        row = {
            "observation": {"sim_time_s": t, "state": checked["state"],
                            "head_png": head_path, "wrist_png": wrist_path},
            "action": label, "audit": audit,
        }
        try:
            self._write_file(head_path, _rgb_png(checked["head"]))
            self._write_file(wrist_path, _rgb_png(checked["wrist"]))
            self._records.write(_canonical(row) + b"\n")
            self._records.flush()
        except (OSError, ValueError, TypeError) as error:
            self._failed = True
            raise RecorderInfraError("RECORDER_WRITE_FAILED") from error
        self._times.append(t)
        self._release_epoch = audit["release_epoch"]
        if audit["release_event"]:
            self._release_time_s = audit["release_time_s"]

    def finish(self, outcome: dict) -> Path:
        if self._failed or self._closed:
            raise RecorderInfraError("RECORDER_NOT_SEALABLE")
        if not isinstance(outcome, dict) or set(outcome) != _OUTCOME_KEYS:
            raise ValueError("EPISODE_OUTCOME_SCHEMA")
        if (outcome["status"] not in ("PASSED", "FAILED")
                or not isinstance(outcome["reason"], str) or not outcome["reason"]
                or type(outcome["task8_success"]) is not bool
                or outcome["stopped_confirmed"] is not True
                or outcome["task8_success"] != (outcome["status"] == "PASSED")):
            raise ValueError("EPISODE_OUTCOME_INVALID")
        if outcome["status"] == "PASSED":
            require_grid(self._times, self.dt_s)
        try:
            self._records.flush()
            os.fsync(self._records.fileno())
            self._records.close()
            self._files["records.jsonl"] = dict(zip(
                ("sha256", "size"), _regular_hash(self.root / "records.jsonl"), strict=True))
            for relative in self._files:
                if relative != "records.jsonl":
                    fd = os.open(self.root / relative, os.O_RDONLY | os.O_NOFOLLOW)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
            frames_fd = os.open(self.root / "frames", os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(frames_fd)
            finally:
                os.close(frames_fd)
            seal = {
                "schema_version": 1, "kind": "ACT_EPISODE_SEAL",
                "status": outcome["status"], "reason": outcome["reason"],
                "task8_success": outcome["task8_success"],
                "stopped_confirmed": True, "qc_passed": outcome["status"] == "PASSED",
                "committed": False, "session_id": self.session_id,
                "attempt_id": self.attempt_id, "reset_epoch": self.reset_epoch,
                "record_count": len(self._times), "provenance": self.provenance,
                "files": dict(sorted(self._files.items())),
            }
            seal["manifest_sha256"] = _hash(_canonical(seal))
            data = _canonical(seal) + b"\n"
            fd, staging = tempfile.mkstemp(prefix=".seal.", dir=self.root)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            path = self.root / "seal.json"
            os.link(staging, path)
            os.unlink(staging)
            root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(root_fd)
            finally:
                os.close(root_fd)
            verify_episode_seal(path)
            self._closed = True
            return path
        except (OSError, ValueError, TypeError) as error:
            self._failed = True
            raise RecorderInfraError("RECORDER_SEAL_FAILED") from error


def verify_episode_seal(path: Path) -> dict:
    path = Path(path)
    if path.name != "seal.json" or not path.is_file() or path.is_symlink():
        raise ValueError("EPISODE_SEAL_MISSING")
    source_bytes = path.read_bytes()
    document = json.loads(source_bytes)
    keys = {"schema_version", "kind", "status", "reason", "task8_success",
            "stopped_confirmed", "qc_passed", "committed", "session_id",
            "attempt_id", "reset_epoch", "record_count", "provenance", "files",
            "manifest_sha256"}
    if not isinstance(document, dict) or set(document) != keys:
        raise ValueError("EPISODE_SEAL_SCHEMA")
    if source_bytes != _canonical(document) + b"\n":
        raise ValueError("EPISODE_SEAL_NONCANONICAL")
    digest = document["manifest_sha256"]
    sha256(digest)
    if digest != _hash(_canonical({key: value for key, value in document.items()
                                   if key != "manifest_sha256"})):
        raise ValueError("EPISODE_SEAL_HASH_MISMATCH")
    if (document["schema_version"] != 1 or document["kind"] != "ACT_EPISODE_SEAL"
            or document["status"] not in ("PASSED", "FAILED")
            or document["committed"] is not False
            or document["stopped_confirmed"] is not True
            or document["qc_passed"] is not (document["status"] == "PASSED")):
        raise ValueError("EPISODE_SEAL_ROLE_INVALID")
    root = path.parent
    files = document["files"]
    if not isinstance(files, dict) or "records.jsonl" not in files:
        raise ValueError("EPISODE_SEAL_FILES_INVALID")
    frames_dir = root / "frames"
    if not frames_dir.is_dir() or frames_dir.is_symlink():
        raise ValueError("EPISODE_SEAL_FILES_INVALID")
    for relative, expected in files.items():
        rel = Path(relative)
        if (rel.is_absolute() or ".." in rel.parts
                or (relative != "records.jsonl"
                    and (len(rel.parts) != 2 or rel.parts[0] != "frames"
                         or rel.suffix != ".png"))
                or not isinstance(expected, dict) or set(expected) != {"sha256", "size"}):
            raise ValueError("EPISODE_SEAL_FILES_INVALID")
        actual_hash, actual_size = _regular_hash(root / rel)
        if expected != {"sha256": actual_hash, "size": actual_size}:
            raise ValueError("EPISODE_FILE_HASH_MISMATCH")
    rows = [json.loads(line) for line in (root / "records.jsonl").read_text().splitlines()]
    if len(rows) != document["record_count"]:
        raise ValueError("EPISODE_RECORD_COUNT_MISMATCH")
    checker = object.__new__(EpisodeRecorder)
    checker.session_id = identifier(document["session_id"])
    checker.attempt_id = identifier(document["attempt_id"])
    checker.reset_epoch = integer(document["reset_epoch"])
    checker.dt_s = 0.1
    checker.max_source_age_s = 0.1
    checker._times = []
    checker._release_epoch = None
    checker._release_time_s = None
    expected_files = {"records.jsonl"}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"observation", "action", "audit"}:
            raise ValueError("EPISODE_RECORD_SCHEMA")
        obs = row["observation"]
        if not isinstance(obs, dict) or set(obs) != {"sim_time_s", "state", "head_png", "wrist_png"}:
            raise ValueError("EPISODE_RECORD_SCHEMA")
        t = finite(obs["sim_time_s"], nonnegative=True)
        state = vector(obs["state"], 8)
        if not math.isclose(state[6] ** 2 + state[7] ** 2, 1., abs_tol=1e-6):
            raise ValueError("EPISODE_RECORD_SCHEMA")
        head = f"frames/{index:06d}-head.png"
        wrist = f"frames/{index:06d}-wrist.png"
        if obs["head_png"] != head or obs["wrist_png"] != wrist:
            raise ValueError("EPISODE_SEAL_FILES_INVALID")
        expected_files.update((head, wrist))
        if checker._times and not math.isclose(t - checker._times[-1], checker.dt_s,
                                                rel_tol=0, abs_tol=1e-6):
            raise ValueError("EPISODE_TIME_GAP")
        label = validate_action(row["action"])
        checker._audit({"sim_time_s": t}, label, row["audit"])
        checker._times.append(t)
        checker._release_epoch = row["audit"]["release_epoch"]
        if row["audit"]["release_event"]:
            checker._release_time_s = row["audit"]["release_time_s"]
    if set(files) != expected_files:
        raise ValueError("EPISODE_SEAL_FILES_INVALID")
    if document["status"] == "PASSED":
        require_grid([row["observation"]["sim_time_s"] for row in rows])
    return document
