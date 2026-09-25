"""Execute the frozen Task 8 qualification cases through one admitted Worker.

The physical phase port and its evidence checks remain in the isolated ROS child.
This owner only fixes case order, result shape, stop behavior and durable readback.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from .task8 import Task8Runner
from .task8_manifest import require_task8_live_manifest


class Task8LiveError(RuntimeError):
    """A case, result or durable outcome could not be proved."""


class Task8LiveCampaign:
    _RESULT_KEYS = frozenset({
        "status", "completed_phases", "stopped_confirmed", "formal_episode_eligible",
    })
    _HASH_FIELDS = (
        "source_sha256", "runtime_config_sha256", "collection_config_sha256",
        "contact_policy_fingerprint",
    )

    def __init__(self, manifest_path: Path, context, worker, journal_path: Path,
                 *, clock_ns=time.monotonic_ns) -> None:
        self.manifest_path = Path(manifest_path)
        self.context = context
        self.worker = worker
        self.journal_path = Path(journal_path)
        self.clock_ns = clock_ns

    def _manifest(self) -> dict:
        path = self.manifest_path
        if not path.is_absolute() or ".." in path.parts:
            raise Task8LiveError("TASK8_MANIFEST_BINDING_INVALID")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("not regular")
                raw = stream.read((1 << 20) + 1)
            if len(raw) > (1 << 20) or hashlib.sha256(raw).hexdigest() != self.context.manifest_sha256:
                raise ValueError("file hash")
            manifest = require_task8_live_manifest(json.loads(raw))
            if any(manifest[name] != getattr(self.context, name) for name in self._HASH_FIELDS):
                raise ValueError("context binding")
            return manifest
        except (AttributeError, OSError, TypeError, UnicodeDecodeError, ValueError) as error:
            raise Task8LiveError("TASK8_MANIFEST_BINDING_INVALID") from error

    def _validate_owner(self, deadline_ns: int) -> None:
        context = self.context
        if (type(deadline_ns) is not int or deadline_ns <= self.clock_ns()
                or context.worker_count != 1
                or not isinstance(context.campaign_id, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", context.campaign_id) is None
                or self.worker.context != context
                or not isinstance(self.worker.launch.mujoco_session_id, str)
                or not self.worker.launch.mujoco_session_id):
            raise Task8LiveError("TASK8_CAMPAIGN_OWNER_INVALID")

    @staticmethod
    def _expected_phases(case: dict) -> list[str]:
        phases = list(Task8Runner.PHASES)
        if case["mode"] == "phase_prefix":
            return phases[:phases.index(case["stop_after"]) + 1]
        return phases

    def _verify_result(self, result: object, case: dict) -> None:
        if (not isinstance(result, dict) or set(result) != self._RESULT_KEYS
                or result["status"] != "PASSED"
                or result["completed_phases"] != self._expected_phases(case)
                or result["stopped_confirmed"] is not True
                or result["formal_episode_eligible"] is not (case["mode"] == "full")):
            raise Task8LiveError("TASK8_CASE_RESULT_INVALID")

    def _open_journal(self):
        path = self.journal_path
        if not path.is_absolute() or ".." in path.parts or not path.parent.is_dir():
            raise Task8LiveError("TASK8_JOURNAL_PATH_INVALID")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError as error:
            raise Task8LiveError("TASK8_JOURNAL_EXISTS") from error
        except OSError as error:
            raise Task8LiveError("TASK8_JOURNAL_UNAVAILABLE") from error
        try:
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _record(stream, record: dict) -> None:
        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

    async def _cancel(self, request: dict) -> bool:
        try:
            result = await self.worker.cancel({
                "session_id": request["session_id"], "attempt_id": request["attempt_id"],
                "reason": "TASK8_CASE_ABORT", "deadline_ns": self.clock_ns() + 2_000_000_000,
            })
        except BaseException:
            return False
        return isinstance(result, dict) and result.get("stopped_confirmed") is True

    async def run(self, *, deadline_ns: int) -> dict:
        self._validate_owner(deadline_ns)
        manifest = self._manifest()
        cases = (*manifest["prefix_cases"], *manifest["full_cases"])
        with self._open_journal() as journal:
            for case in cases:
                if deadline_ns <= self.clock_ns():
                    raise Task8LiveError("TASK8_DEADLINE_EXPIRED")
                request = {
                    "session_id": self.worker.launch.mujoco_session_id,
                    "attempt_id": f"{self.context.campaign_id}-{case['case_id']}",
                    "scenario_id": case["case_id"], "mode": case["mode"],
                    "stop_after": case["stop_after"],
                    "contact_policy_fingerprint": self.context.contact_policy_fingerprint,
                    "deadline_ns": deadline_ns,
                }
                try:
                    result = await self.worker.task8(request)
                    self._verify_result(result, case)
                except BaseException as error:
                    stopped = await self._cancel(request)
                    try:
                        self._record(journal, {
                            "case_id": case["case_id"], "anchor": case["anchor"],
                            "attempt_id": request["attempt_id"],
                            "status": "FAILED" if stopped else "INDETERMINATE",
                            "reason": "TASK8_CASE_ABORT",
                        })
                    except BaseException as record_error:
                        raise Task8LiveError("TASK8_JOURNAL_WRITE_FAILED") from record_error
                    if not stopped:
                        raise Task8LiveError("TASK8_STOP_NOT_CONFIRMED") from error
                    if isinstance(error, Task8LiveError):
                        raise
                    raise Task8LiveError("TASK8_CASE_EXECUTION_UNCERTAIN") from error
                try:
                    self._record(journal, {
                        "case_id": case["case_id"], "anchor": case["anchor"],
                        "attempt_id": request["attempt_id"], "status": "PASSED",
                        "result": result,
                    })
                except BaseException as error:
                    # A failed fsync can leave bytes in the file. Never append a
                    # contradictory second terminal for this same case.
                    if not await self._cancel(request):
                        raise Task8LiveError("TASK8_STOP_NOT_CONFIRMED") from error
                    raise Task8LiveError("TASK8_JOURNAL_WRITE_FAILED") from error
        return {"status": "PASSED", "prefix_passes": 9, "full_passes": 5,
                "journal_path": str(self.journal_path)}
