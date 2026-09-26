"""Capture an installed ACT stack observation and issue its one-use owner proof."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from .act_stack import ActStackLaunch
from .bridge import _retirement_owner_state
from .contracts import MutationError, OwnerKey
from .pick_place_startup_proof import (
    _ARTIFACT_HASHES, _CHECKS, _MAX_AGE_NS, _MAX_BYTES,
    _MAX_ISSUE_LAG_NS, _READINESS_KEYS, PickPlaceStartupProofConsumer,
)


def _validated_observation(raw: bytes, *, session_id: str, ros_domain_id: int,
                           now_ns: int) -> dict:
    try:
        if not isinstance(raw, bytes) or not 0 < len(raw) <= _MAX_BYTES:
            raise ValueError("length")
        value = json.loads(raw)
        if (type(value) is not dict or set(value) != _READINESS_KEYS
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or type(value["session_id"]) is not str
                or value["session_id"] != session_id
                or type(value["ros_domain_id"]) is not int
                or value["ros_domain_id"] != ros_domain_id
                or type(value["captured_monotonic_ns"]) is not int
                or type(value["checks"]) is not dict
                or set(value["checks"]) != _CHECKS
                or any(check is not True for check in value["checks"].values())
                or not 0 < value["captured_monotonic_ns"] <= now_ns
                or now_ns - value["captured_monotonic_ns"] > _MAX_AGE_NS):
            raise ValueError("scope or freshness")
        return value
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("ACT_STACK_READINESS_OUTPUT_INVALID") from error


class InstalledActStackReadinessProbe:
    """Run the installed no-motion observer once in the owned stack's exact domain."""

    def __init__(self, launch: ActStackLaunch, executable: Path, *,
                 run=subprocess.run, clock_ns=time.monotonic_ns,
                 timeout_s: float = 60.0,
                 process_timeout_s: float | None = None) -> None:
        binary = Path(executable)
        process_timeout_s = timeout_s + 10.0 if process_timeout_s is None else process_timeout_s
        if (not isinstance(launch, ActStackLaunch) or not binary.is_absolute()
                or ".." in binary.parts or binary.is_symlink()
                or not binary.is_file() or not os.access(binary, os.X_OK)
                or not callable(run) or not callable(clock_ns)
                or not 0 < timeout_s <= 60
                or not timeout_s < process_timeout_s <= 75
                or not launch.environment.get("GZ_PARTITION")):
            raise ValueError("ACT_STACK_READINESS_PROBE_CONFIG_INVALID")
        self.launch = launch
        self.executable = binary
        self.run = run
        self.clock_ns = clock_ns
        self.timeout_s = timeout_s
        self.process_timeout_s = process_timeout_s
        self.readiness_bytes: bytes | None = None
        self._attempted = False

    def __call__(self) -> bool:
        if self._attempted:
            raise ValueError("ACT_STACK_READINESS_PROBE_REUSED")
        self._attempted = True
        argv = [str(self.executable), "--session-id", self.launch.session_id,
                "--ros-domain-id", str(self.launch.ros_domain_id),
                "--timeout-s", str(self.timeout_s)]
        try:
            result = self.run(
                argv, env=self.launch.process_environment(), shell=False,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=self.process_timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError("ACT_STACK_READINESS_COMMAND_FAILED") from error
        if result.returncode != 0:
            raise ValueError("ACT_STACK_READINESS_COMMAND_FAILED")
        raw = result.stdout
        _validated_observation(raw, session_id=self.launch.session_id,
                               ros_domain_id=self.launch.ros_domain_id,
                               now_ns=self.clock_ns())
        self.readiness_bytes = raw
        return True


def _write_once(root: Path, name: str, raw: bytes) -> None:
    fd = os.open(root / name,
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class PickPlaceStartupProofIssuer:
    """Bind fresh observation bytes to admitted artifacts and live process owners."""

    def __init__(self, context, child, stack_owner: OwnerKey, child_owner: OwnerKey,
                 *, live_probe=None, clock_ns=time.monotonic_ns) -> None:
        if (not isinstance(stack_owner, OwnerKey) or not isinstance(child_owner, OwnerKey)
                or not callable(clock_ns)
                or live_probe is not None and not callable(live_probe)):
            raise ValueError("TASK8_STARTUP_ISSUER_CONFIG_INVALID")
        self.context, self.child = context, child
        self.stack_owner, self.child_owner = stack_owner, child_owner
        self.live_probe = live_probe or (lambda owner: _retirement_owner_state(owner) == "live")
        self.clock_ns = clock_ns

    def issue(self, raw: bytes) -> dict:
        consumer = PickPlaceStartupProofConsumer(
            self.context, self.child, stack_owner=self.stack_owner,
            child_owner=self.child_owner, live_probe=self.live_probe,
            clock_ns=self.clock_ns,
        )
        root = consumer._root()
        if any((root / name).exists() or (root / name).is_symlink() for name in (
            "readiness.json", "startup-receipt.json", "startup-consumed.json",
        )):
            raise MutationError("TASK8_STARTUP_PROOF_ALREADY_ISSUED")
        now_ns = self.clock_ns()
        try:
            if (type(now_ns) is not int or now_ns <= 0
                    or self.live_probe(self.stack_owner) is not True
                    or self.live_probe(self.child_owner) is not True):
                raise ValueError("owner or clock")
            observation = _validated_observation(
                raw, session_id=self.child.mujoco_session_id,
                ros_domain_id=self.child.ros_domain_id, now_ns=now_ns,
            )
            if now_ns - observation["captured_monotonic_ns"] > _MAX_ISSUE_LAG_NS:
                raise ValueError("issue lag")
            receipt = {
                "schema_version": 1,
                "campaign_id": self.context.campaign_id,
                "operation_id": self.context.operation_id,
                "worker_id": self.child.worker_id,
                "execution_generation": self.child.execution_generation,
                "session_id": self.child.mujoco_session_id,
                "ros_domain_id": self.child.ros_domain_id,
                **{key: getattr(self.context, key) for key in _ARTIFACT_HASHES},
                "stack_owner": asdict(self.stack_owner),
                "child_owner": asdict(self.child_owner),
                "readiness_sha256": hashlib.sha256(raw).hexdigest(),
                "issued_monotonic_ns": now_ns,
            }
            _write_once(root, "readiness.json", raw)
            _write_once(root, "startup-receipt.json",
                        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode())
            return receipt
        except (AttributeError, KeyError, OSError, TypeError, ValueError) as error:
            raise MutationError("TASK8_STARTUP_PROOF_INVALID") from error


# Legacy Python API for version-one pick-place callers.
Task8StartupProofIssuer = PickPlaceStartupProofIssuer
