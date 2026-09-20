"""Web-side owner and client of the non-web ROS child.

The launch description is built only from validated server configuration; no HTTP input,
shell command, or Python expression can influence the child's argv or environment. The
owner records an exact process identity and re-verifies it before it ever signals.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .arbiter import GlobalMutationArbiter
from .child_runtime import READY_FILE_NAME, NORMAL_SOCKET_NAME, SAFETY_SOCKET_NAME
from .contracts import (
    CancelReceipt,
    IntentCancelReceipt,
    MutationError,
    OwnerKey,
    PendingChildKey,
    RevokeTarget,
)
from .ipc import DEFAULT_MAX_BYTES, IpcReply, IpcRequest, SafetyPacket
from .safety import SafetyLane


@dataclass(frozen=True)
class BridgeLaunch:
    ros_python: Path
    install_prefix: Path
    runtime_id: str
    environment: dict[str, str]
    socket_root: Path

    def __post_init__(self) -> None:
        if not Path(self.ros_python).is_file():
            raise MutationError(f"BRIDGE_ROS_PYTHON_MISSING: {self.ros_python}")
        if not Path(self.install_prefix).is_dir():
            raise MutationError(f"BRIDGE_INSTALL_PREFIX_MISSING: {self.install_prefix}")
        if not self.runtime_id:
            raise MutationError("BRIDGE_RUNTIME_ID_MISSING")

    def argv(self) -> list[str]:
        """The only argv this service will ever spawn for the ROS child."""
        return [
            str(self.ros_python),
            "-m",
            "so101_teleop.unified.ros_child",
            "--socket-root",
            str(self.socket_root),
            "--runtime-id",
            self.runtime_id,
        ]


def _hash_argv(argv: list[str]) -> str:
    return hashlib.sha256("\0".join(argv).encode()).hexdigest()


def _hash_environment(environment: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(environment, sort_keys=True).encode()
    ).hexdigest()


def process_start_marker(pid: int) -> int:
    """A start marker that survives PID reuse; platform specific, never guessed."""
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists():
        fields = stat_path.read_text().rsplit(")", 1)[-1].split()
        return int(fields[19])
    completed = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise MutationError(f"PROCESS_IDENTITY_UNREADABLE: {pid}")
    return int(hashlib.sha256(completed.stdout.strip().encode()).hexdigest()[:12], 16)


def identity_for(pid: int, argv: list[str], environment: dict[str, str]) -> OwnerKey:
    return OwnerKey(
        pid=pid,
        pgid=os.getpgid(pid),
        started_ticks=process_start_marker(pid),
        argv_sha256=_hash_argv(argv),
        environment_sha256=_hash_environment(environment),
    )


def identity_matches(owner: OwnerKey) -> bool:
    try:
        os.kill(owner.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    try:
        return process_start_marker(owner.pid) == owner.started_ticks
    except MutationError:
        return False


class BridgeProcessOwner:
    def __init__(self, launch: BridgeLaunch, arbiter: GlobalMutationArbiter, safety: SafetyLane) -> None:
        self.launch = launch
        self.arbiter = arbiter
        self.safety = safety
        self.process: subprocess.Popen | None = None
        self.owner: OwnerKey | None = None
        self._ready_document: dict | None = None

    async def start(self, *, timeout_s: float = 10.0) -> OwnerKey:
        if self.owner is not None and identity_matches(self.owner):
            return self.owner
        argv = self.launch.argv()
        environment = dict(self.launch.environment)
        self.process = subprocess.Popen(
            argv,
            env=environment,
            shell=False,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
        )
        self.owner = identity_for(self.process.pid, argv, environment)
        deadline = time.monotonic() + timeout_s
        ready_path = Path(self.launch.socket_root) / READY_FILE_NAME
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise MutationError(f"BRIDGE_CHILD_EXITED: {self.process.returncode}")
            if ready_path.is_file():
                document = json.loads(ready_path.read_text())
                if document.get("pid") == self.process.pid and document.get(
                    "runtime_id"
                ) == self.launch.runtime_id:
                    self._ready_document = document
                    return self.owner
            await asyncio.sleep(0.02)
        raise MutationError("BRIDGE_READY_TIMEOUT: child did not publish its sockets")

    def ready(self) -> bool:
        if self.process is None or self.process.poll() is not None:
            return False
        if self._ready_document is None:
            return False
        return self._ready_document.get("service_epoch") is not None

    async def stop_owned(self, *, timeout_s: float = 5.0) -> None:
        """Signal only the exact process this service started, after re-proving identity."""
        if self.process is None or self.owner is None:
            return
        if not identity_matches(self.owner):
            raise MutationError(
                f"OWNER_IDENTITY_DRIFT: pid {self.owner.pid} no longer matches the recorded start marker"
            )
        os.kill(self.owner.pid, signal.SIGTERM)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.process = None
                return
            await asyncio.sleep(0.02)
        raise MutationError(f"STOP_NOT_CONFIRMED: pid {self.owner.pid} did not exit in time")

    def socket_paths(self) -> tuple[Path, Path]:
        root = Path(self.launch.socket_root)
        return root / NORMAL_SOCKET_NAME, root / SAFETY_SOCKET_NAME


class BridgeClient:
    """Sends closed packets over the two child sockets. Never reuses a normal queue."""

    def __init__(
        self,
        *,
        normal_socket: Path,
        safety_socket: Path,
        service_epoch: str,
        runtime_id: str,
        service_token: str,
        timeout_s: float = 5.0,
        max_bytes: int = DEFAULT_MAX_BYTES,
        owner: OwnerKey | None = None,
    ) -> None:
        self.normal_socket = Path(normal_socket)
        self.safety_socket = Path(safety_socket)
        self.service_epoch = service_epoch
        self.runtime_id = runtime_id
        self.service_token = service_token
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self.owner = owner
        self._closed = False

    async def call(self, packet: IpcRequest) -> IpcReply:
        if self._closed:
            raise MutationError("BRIDGE_CLIENT_CLOSED")
        return await asyncio.wait_for(self._round_trip(self.normal_socket, packet), self.timeout_s)

    async def _round_trip(self, socket_path: Path, packet) -> IpcReply:
        try:
            reader, writer = await asyncio.open_unix_connection(str(socket_path))
        except OSError as error:
            raise MutationError(f"IPC_CONNECT_FAILED: {socket_path}: {error}") from error
        try:
            writer.write(packet.model_dump_json().encode() + b"\n")
            await writer.drain()
            line = await reader.readline()
            if not line:
                raise MutationError("IPC_EMPTY_REPLY: the child closed the connection")
            if len(line) > self.max_bytes * 4:
                raise MutationError("IPC_REPLY_OVERSIZE")
            reply = IpcReply.model_validate_json(line)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        return reply

    async def cancel(self, key, authority) -> CancelReceipt:
        """Deliver a cancel for a known goal identity over the independent safety socket."""
        target = RevokeTarget(
            key=PendingChildKey(
                operation_id=key.operation_id,
                child_id=key.child_id,
                runtime_id=self.runtime_id,
                execution_generation=key.execution_generation,
            ),
            revocation_revision=authority.execution_generation,
        )
        reply = await self._send_safety(target)
        accepted = bool(reply.accepted)
        return CancelReceipt(key, accepted, None, None if accepted else reply.code)

    async def revoke(self, target: RevokeTarget, authority) -> IntentCancelReceipt:
        reply = await self._send_safety(target)
        if not reply.accepted:
            return IntentCancelReceipt(target, False, False, None, reply.code)
        result = reply.result or {}
        return IntentCancelReceipt(
            target,
            bool(result.get("linearized")),
            bool(result.get("submitted")),
            None,
            result.get("blocked_reason"),
        )

    async def _send_safety(self, target: RevokeTarget) -> IpcReply:
        if self._closed:
            raise MutationError("BRIDGE_CLIENT_CLOSED")
        if self.owner is None:
            raise MutationError("BRIDGE_OWNER_UNKNOWN: refusing to cancel without the exact owner")
        packet = SafetyPacket(
            operation="revoke",
            service_epoch=self.service_epoch,
            owner={
                "pid": self.owner.pid,
                "pgid": self.owner.pgid,
                "started_ticks": self.owner.started_ticks,
                "argv_sha256": self.owner.argv_sha256,
                "environment_sha256": self.owner.environment_sha256,
            },
            claim=self.service_token,
            target={
                "key": {
                    "operation_id": target.key.operation_id,
                    "child_id": target.key.child_id,
                    "runtime_id": target.key.runtime_id,
                    "execution_generation": target.key.execution_generation,
                },
                "revocation_revision": target.revocation_revision,
            },
        )
        return await asyncio.wait_for(self._round_trip(self.safety_socket, packet), self.timeout_s)

    def close(self) -> None:
        self._closed = True
