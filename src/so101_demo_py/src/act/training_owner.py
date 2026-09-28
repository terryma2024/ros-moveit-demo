"""Task 12 ownership: one run root, one live owner, one GPU.

Training and collection must never share a GPU, and two run roots must never believe they own the same
one. The owner receipt written here is the evidence of that claim, and it is re-read on every later
acquire, so a recycled PID or a stale heartbeat is refused instead of inheriting a finished run's lease.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

RECEIPT_NAME = "training-owner.json"
_LEASE_KEYS = frozenset({"device", "binding_id", "leases"})
_ACTIVE_KINDS = ("collection", "broker", "training")
_OWNER_KEYS = frozenset({"schema_version", "kind", "run_root", "device", "dataset_sha256",
                         "config_sha256", "owner_pid", "owner_started_ticks", "acquired_at"})


def _sha256(value, code: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(code)
    return value


class TrainingRunOwner:
    """Acquires the training lease, or refuses with the reason it cannot."""

    def __init__(self, *, arbiter, identity, clock=time.monotonic,
                 heartbeat_timeout_s: float = 30.0) -> None:
        self.arbiter = arbiter
        self.identity = identity                     # callable -> {"pid": int, "started_ticks": int}
        self.clock = clock
        self.heartbeat_timeout_s = heartbeat_timeout_s

    def _receipt(self, run_root: Path):
        path = run_root / RECEIPT_NAME
        if not path.is_file():
            return None, path
        try:
            return json.loads(path.read_bytes()), path
        except ValueError as error:
            raise ValueError("TRAINING_OWNER_RECEIPT_INVALID") from error

    def acquire(self, *, run_root, dataset_sha256: str, config_sha256: str,
                gpu_lease: dict) -> dict:
        root = Path(run_root)
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            raise ValueError("TRAINING_RUN_ROOT_INVALID")
        _sha256(dataset_sha256, "TRAINING_DATASET_INVALID")
        _sha256(config_sha256, "TRAINING_CONFIG_INVALID")
        if (not isinstance(gpu_lease, dict) or set(gpu_lease) != _LEASE_KEYS
                or gpu_lease.get("device") != "cuda"):
            raise ValueError("TRAINING_GPU_LEASE_INVALID")
        if not isinstance(gpu_lease.get("binding_id"), str) or not gpu_lease["binding_id"]:
            raise ValueError("TRAINING_GPU_LEASE_INVALID")
        leases = gpu_lease.get("leases")
        if not isinstance(leases, (list, tuple)):
            raise ValueError("TRAINING_GPU_LEASE_INVALID")
        if any(isinstance(lease, dict) and lease.get("kind") in _ACTIVE_KINDS for lease in leases):
            # collection, the broker, or another training run already holds this GPU
            raise ValueError("TRAINING_GPU_BUSY")
        state = self.arbiter.state()
        if state != "IDLE":
            raise ValueError("TRAINING_ARBITER_BUSY")

        existing, path = self._receipt(root)
        if existing is not None:
            if (not isinstance(existing, dict) or set(existing) != _OWNER_KEYS
                    or existing.get("device") != "cuda"):
                raise ValueError("TRAINING_OWNER_RECEIPT_INVALID")
            if existing.get("dataset_sha256") != dataset_sha256:
                raise ValueError("TRAINING_DATASET_MISMATCH")
            if existing.get("config_sha256") != config_sha256:
                raise ValueError("TRAINING_CONFIG_MISMATCH")
            identity = self.identity()
            if (existing.get("owner_started_ticks") != identity["started_ticks"]
                    or existing.get("owner_pid") != identity["pid"]):
                # a recycled PID must not inherit the finished run's lease
                raise ValueError("TRAINING_OWNER_IDENTITY_DRIFT")
            if self.clock() - float(existing.get("acquired_at", 0.0)) > self.heartbeat_timeout_s:
                raise ValueError("TRAINING_HEARTBEAT_EXPIRED")

        identity = self.identity()
        receipt = {"schema_version": 1, "kind": "act_training_owner", "run_root": str(root),
                   "device": "cuda", "dataset_sha256": dataset_sha256,
                   "config_sha256": config_sha256, "owner_pid": identity["pid"],
                   "owner_started_ticks": identity["started_ticks"], "acquired_at": self.clock()}
        temporary = path.with_name(RECEIPT_NAME + ".partial")
        with open(temporary, "w") as handle:
            handle.write(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        return {**receipt, "gpu_binding_id": gpu_lease["binding_id"]}
