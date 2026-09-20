"""The ROS child's own runtime: two channels, one linearized submission state.

The child never opens the web's durable store and never asks the web whether a cancel
happened. It keeps a monotonic tombstone per pending child so a delayed normal packet that
lost the race to a safety revoke can never reach the driver. The safety channel has its own
reader and its own task, so a saturated normal queue cannot delay a cancel.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Protocol

from .contracts import (
    ActionKey,
    ActionTerminal,
    DispatchAck,
    DispatchToken,
    IntentCancelReceipt,
    MutationError,
    OwnerKey,
    PendingChildKey,
    RevokeTarget,
)
from .ipc import (
    DEFAULT_MAX_BYTES,
    IpcProtocolError,
    IpcReply,
    IpcRequest,
    SafetyPacket,
    decode_request,
    decode_safety_packet,
    encode,
)

READY_FILE_NAME = "child-ready.json"
NORMAL_SOCKET_NAME = "normal.sock"
SAFETY_SOCKET_NAME = "safety.sock"


def peer_uid(sock) -> int | None:
    """Best-effort peer UID check; a private 0700 directory is the portable backstop."""
    if sock is None:
        return None
    if hasattr(os, "geteuid") and hasattr(sock, "getsockopt"):
        try:
            import socket as _socket
            import struct

            credentials = sock.getsockopt(_socket.SOL_SOCKET, getattr(_socket, "SO_PEERCRED", 17), 12)
            return struct.unpack("3i", credentials)[1]
        except (OSError, AttributeError, struct.error):
            return None
    return None


class ActionDriver(Protocol):
    def allocate_goal_uuid(self, key: PendingChildKey) -> str: ...

    def submit(self, token: DispatchToken, goal_uuid: str) -> Awaitable[DispatchAck]: ...

    def cancel(self, goal_uuid: str) -> Awaitable[bool]: ...

    def terminal(self, goal_uuid: str) -> Awaitable[ActionTerminal]: ...


@dataclass
class PendingSubmission:
    token: DispatchToken
    goal_uuid: str
    phase: str
    cancel_requested: bool
    task: "asyncio.Task | None" = None


@dataclass(frozen=True)
class ChildStats:
    submit_count: int
    cancel_uuids: tuple[str, ...]
    pending_uuids: tuple[str, ...]


def pending_key(token: DispatchToken) -> PendingChildKey:
    return PendingChildKey(
        operation_id=token.operation_id,
        child_id=token.child_id,
        runtime_id=token.runtime_id,
        execution_generation=token.execution_generation,
    )


class ChildRuntime:
    def __init__(
        self,
        driver: ActionDriver,
        *,
        owner: OwnerKey,
        service_epoch: str,
        runtime_id: str,
        normal_queue_limit: int,
    ) -> None:
        self.driver = driver
        self.owner = owner
        self.service_epoch = service_epoch
        self.runtime_id = runtime_id
        self.normal_queue_limit = normal_queue_limit
        self.pending: dict[PendingChildKey, PendingSubmission] = {}
        self.tombstones: dict[PendingChildKey, int] = {}
        self.transition_lock = asyncio.Lock()
        self.normal_inflight = 0
        self.web_dead = False
        self.web_dead_latch = asyncio.Event()

    # -- normal channel ----------------------------------------------------------

    async def submit(self, token: DispatchToken) -> DispatchAck:
        if token.runtime_id != self.runtime_id:
            raise MutationError(f"RUNTIME_MISMATCH: {token.runtime_id} != {self.runtime_id}")
        if self.web_dead:
            raise MutationError("WEB_DEAD: this child stopped accepting new mutations")
        if self.normal_inflight >= self.normal_queue_limit:
            raise MutationError(f"NORMAL_QUEUE_FULL: {self.normal_queue_limit} in flight")
        async with self.transition_lock:
            key = pending_key(token)
            if token.revocation_revision <= self.tombstones.get(key, -1):
                raise MutationError(f"INTENT_REVOKED: {key.child_id} was revoked before submit")
            pending = self.pending.get(key)
            if pending is None:
                pending = PendingSubmission(
                    token=token,
                    goal_uuid=self.driver.allocate_goal_uuid(key),
                    phase="SUBMITTING",
                    cancel_requested=False,
                )
                self.pending[key] = pending
        # The driver is called outside the transition lock; a repeated token reuses the
        # same submission instead of submitting the goal twice.
        if pending.task is None:
            self.normal_inflight += 1
            pending.task = asyncio.get_running_loop().create_task(self._drive(pending))
        return await asyncio.shield(pending.task)

    async def _drive(self, pending: PendingSubmission) -> DispatchAck:
        try:
            ack = await self.driver.submit(pending.token, pending.goal_uuid)
        except BaseException:
            # Keep the goal UUID and the pending record: an unknown result must stay visible.
            pending.phase = "UNKNOWN"
            raise
        finally:
            self.normal_inflight -= 1
        if not ack.accepted:
            pending.phase = "REJECTED"
            return ack
        pending.phase = "ACKED"
        if pending.cancel_requested:
            # Accepted after a cancel was already recorded: cancel the real goal now.
            await self.driver.cancel(pending.goal_uuid)
        return ack

    # -- safety channel ----------------------------------------------------------

    async def revoke(self, target: RevokeTarget) -> IntentCancelReceipt:
        async with self.transition_lock:
            key = target.key
            self.tombstones[key] = max(self.tombstones.get(key, -1), target.revocation_revision)
            pending = self.pending.get(key)
            if pending is not None:
                pending.cancel_requested = True
                goal_uuid = pending.goal_uuid
            else:
                goal_uuid = None
        submitted = goal_uuid is not None
        if goal_uuid is not None:
            confirmed = await self.driver.cancel(goal_uuid)
            if not confirmed:
                return IntentCancelReceipt(
                    target, True, True, None, "STOP_NOT_CONFIRMED"
                )
        return IntentCancelReceipt(target, True, submitted, None, None)

    async def observe(self) -> dict:
        return {
            "runtime_id": self.runtime_id,
            "service_epoch": self.service_epoch,
            "web_dead": self.web_dead,
            "pending": [key.child_id for key in self.pending],
        }

    async def mark_web_dead(self, reason: str) -> None:
        """Irreversible latch: known pending goals are revoked and no new work is accepted."""
        if self.web_dead:
            return
        self.web_dead = True
        self.web_dead_latch.set()
        known = list(self.pending.items())
        for key, pending in known:
            self.tombstones[key] = max(self.tombstones.get(key, -1), pending.token.revocation_revision + 1)
            pending.cancel_requested = True
            with contextlib.suppress(Exception):
                await self.driver.cancel(pending.goal_uuid)

    async def stats(self) -> ChildStats:
        journal = getattr(self.driver, "journal", None)
        if journal is None:
            return ChildStats(0, (), tuple(p.goal_uuid for p in self.pending.values()))
        return ChildStats(
            submit_count=journal.submit_count,
            cancel_uuids=tuple(journal.cancel_uuids),
            pending_uuids=tuple(p.goal_uuid for p in self.pending.values()),
        )


class ChildIpcServer:
    """Serves the normal and safety channels with independent readers and tasks."""

    def __init__(
        self,
        runtime: ChildRuntime,
        *,
        socket_root: Path,
        owner: OwnerKey,
        service_epoch: str,
        service_token: str,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.runtime = runtime
        self.socket_root = Path(socket_root)
        self.owner = owner
        self.service_epoch = service_epoch
        self.service_token = service_token
        self.max_bytes = max_bytes
        self.normal_socket = self.socket_root / NORMAL_SOCKET_NAME
        self.safety_socket = self.socket_root / SAFETY_SOCKET_NAME
        self._servers: list[asyncio.AbstractServer] = []
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        for path in (self.normal_socket, self.safety_socket):
            if len(str(path).encode()) > 103:
                raise MutationError(
                    f"IPC_SOCKET_PATH_TOO_LONG: {path} exceeds this platform's AF_UNIX limit"
                )
        os.makedirs(self.socket_root, mode=0o700, exist_ok=True)
        os.chmod(self.socket_root, 0o700)
        for path in (self.normal_socket, self.safety_socket):
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
        self._servers.append(
            await asyncio.start_unix_server(self._handle_normal, path=str(self.normal_socket))
        )
        self._servers.append(
            await asyncio.start_unix_server(self._handle_safety, path=str(self.safety_socket))
        )
        for path in (self.normal_socket, self.safety_socket):
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        ready = {
            "pid": os.getpid(),
            "service_epoch": self.service_epoch,
            "runtime_id": self.runtime.runtime_id,
            "normal_socket": str(self.normal_socket),
            "safety_socket": str(self.safety_socket),
            "owner": {
                "pid": self.owner.pid,
                "pgid": self.owner.pgid,
                "started_ticks": self.owner.started_ticks,
                "argv_sha256": self.owner.argv_sha256,
                "environment_sha256": self.owner.environment_sha256,
            },
        }
        (self.socket_root / READY_FILE_NAME).write_text(json.dumps(ready, sort_keys=True) + "\n")

    async def close(self) -> None:
        for server in self._servers:
            server.close()
        for server in self._servers:
            with contextlib.suppress(Exception):
                await server.wait_closed()
        for task in self._tasks:
            task.cancel()
        for path in (self.normal_socket, self.safety_socket):
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
        with contextlib.suppress(FileNotFoundError):
            (self.socket_root / READY_FILE_NAME).unlink()

    # -- handlers ----------------------------------------------------------------

    async def _handle_normal(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                reply = await self._normal_reply(line, writer)
                writer.write(encode(reply))
                await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _normal_reply(self, line: bytes, writer) -> IpcReply:
        try:
            request = decode_request(line, max_bytes=self.max_bytes, now_ns=time.monotonic_ns())
        except IpcProtocolError as error:
            return IpcReply(accepted=False, code=str(error))
        rejection = self._reject_envelope(request.service_epoch, request.runtime_id, request.service_token, writer)
        if rejection is not None:
            return rejection
        if request.operation in ("observe", "plan_joints", "plan_tcp"):
            return IpcReply(accepted=True, code="OK", result=await self.runtime.observe())
        assert request.token is not None
        token = DispatchToken(
            operation_id=request.token.operation_id,
            child_id=request.token.child_id,
            runtime_id=request.token.runtime_id,
            execution_generation=request.token.execution_generation,
            deadline_ns=request.token.deadline_ns,
            revocation_revision=request.token.revocation_revision,
        )
        try:
            ack = await self.runtime.submit(token)
        except MutationError as error:
            return IpcReply(accepted=False, code=error.code)
        return IpcReply(
            accepted=ack.accepted,
            code="OK" if ack.accepted else "DISPATCH_REJECTED",
            ack={
                "operation_id": ack.key.operation_id,
                "child_id": ack.key.child_id,
                "goal_uuid": ack.key.goal_uuid,
                "runtime_id": ack.key.runtime_id,
                "execution_generation": ack.key.execution_generation,
                "owner": {
                    "pid": ack.key.owner.pid,
                    "pgid": ack.key.owner.pgid,
                    "started_ticks": ack.key.owner.started_ticks,
                    "argv_sha256": ack.key.owner.argv_sha256,
                    "environment_sha256": ack.key.owner.environment_sha256,
                },
            },
        )

    async def _handle_safety(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                try:
                    packet = decode_safety_packet(line, max_bytes=self.max_bytes)
                except IpcProtocolError as error:
                    writer.write(encode(IpcReply(accepted=False, code=str(error))))
                    await writer.drain()
                    continue
                rejection = self._reject_envelope(
                    packet.service_epoch,
                    self.runtime.runtime_id,
                    packet.claim,
                    writer,
                    token_field="claim",
                )
                if rejection is not None:
                    writer.write(encode(rejection))
                    await writer.drain()
                    continue
                target = _target_from_packet(packet)
                receipt = await self.runtime.revoke(target)
                writer.write(
                    encode(
                        IpcReply(
                            accepted=True,
                            code="OK",
                            result={
                                "linearized": receipt.linearized,
                                "submitted": receipt.submitted,
                                "blocked_reason": receipt.blocked_reason,
                            },
                        )
                    )
                )
                await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def _reject_envelope(
        self, service_epoch: str, runtime_id: str, token: str, writer, *, token_field: str = "service_token"
    ) -> IpcReply | None:
        uid = peer_uid(writer.get_extra_info("socket"))
        if uid is not None and hasattr(os, "geteuid") and uid != os.geteuid():
            return IpcReply(accepted=False, code=f"IPC_PEER_REJECTED: uid {uid}")
        if service_epoch != self.service_epoch:
            return IpcReply(accepted=False, code=f"IPC_EPOCH_REJECTED: {service_epoch}")
        if runtime_id != self.runtime.runtime_id:
            return IpcReply(accepted=False, code=f"IPC_RUNTIME_REJECTED: {runtime_id}")
        if token != self.service_token:
            return IpcReply(accepted=False, code=f"IPC_TOKEN_REJECTED: {token_field}")
        return None


def _target_from_packet(packet: SafetyPacket) -> RevokeTarget:
    target = packet.target
    key = target.get("key") if isinstance(target, dict) else None
    if not isinstance(key, dict):
        raise IpcProtocolError("IPC_SAFETY_TARGET_INVALID")
    return RevokeTarget(
        key=PendingChildKey(
            operation_id=str(key.get("operation_id")),
            child_id=str(key.get("child_id")),
            runtime_id=str(key.get("runtime_id")),
            execution_generation=int(key.get("execution_generation", 0)),
        ),
        revocation_revision=int(target.get("revocation_revision", 0)),
    )
