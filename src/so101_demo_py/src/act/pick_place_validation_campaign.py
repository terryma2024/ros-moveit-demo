"""Read back frozen pick-place validation cases; refuse execution without a full-stack owner.

FULL_RESTART means a new, subsequently retired simulator and ROS stack for
every case. A world reset or repeated request to one child cannot prove it.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from .pick_place_validation_manifest import require_pick_place_validation_manifest


class PickPlaceValidationError(RuntimeError):
    """A pick-place validation case or its required lifecycle could not be proved."""


class PickPlaceValidationCampaign:
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

    @staticmethod
    def require_full_restart_lifecycle() -> None:
        """Admit no case until an owner can prove a fresh complete stack."""
        raise PickPlaceValidationError("FULL_RESTART_PROOF_UNAVAILABLE")

    def _manifest(self) -> dict:
        path = self.manifest_path
        if not path.is_absolute() or ".." in path.parts:
            raise PickPlaceValidationError("TASK8_MANIFEST_BINDING_INVALID")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("not regular")
                raw = stream.read((1 << 20) + 1)
            if len(raw) > (1 << 20) or hashlib.sha256(raw).hexdigest() != self.context.manifest_sha256:
                raise ValueError("file hash")
            manifest = require_pick_place_validation_manifest(json.loads(raw))
            if any(manifest[name] != getattr(self.context, name) for name in self._HASH_FIELDS):
                raise ValueError("context binding")
            return manifest
        except (AttributeError, OSError, TypeError, UnicodeDecodeError, ValueError) as error:
            raise PickPlaceValidationError("TASK8_MANIFEST_BINDING_INVALID") from error

    def planned_cases(self, *, deadline_ns: int) -> tuple[dict, ...]:
        context = self.context
        if (type(deadline_ns) is not int or deadline_ns <= self.clock_ns()
                or context.worker_count != 1
                or not isinstance(context.campaign_id, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", context.campaign_id) is None
                or self.worker.context != context
                or not isinstance(self.worker.launch.mujoco_session_id, str)
                or not self.worker.launch.mujoco_session_id):
            raise PickPlaceValidationError("TASK8_CAMPAIGN_OWNER_INVALID")
        manifest = self._manifest()
        return tuple(dict(case) for case in (*manifest["prefix_cases"], *manifest["full_cases"]))

    async def run(self, *, deadline_ns: int) -> dict:
        self.planned_cases(deadline_ns=deadline_ns)
        self.require_full_restart_lifecycle()


# Legacy API for validated version-one campaigns.
Task8LiveError = PickPlaceValidationError
Task8LiveCampaign = PickPlaceValidationCampaign
