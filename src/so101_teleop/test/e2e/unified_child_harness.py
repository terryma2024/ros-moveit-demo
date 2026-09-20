"""Two-channel test harness: real child runtime sockets, real web-side client.

Only the innermost ``ActionDriver`` is test-owned. The child runs the same
``ChildRuntime`` socket servers the production child uses, the web side uses the real
``BridgeClient``, and the optional proxy may only hold or release bytes on the normal
channel. The safety channel never goes through the proxy.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.bridge import BridgeClient
from so101_teleop.unified.child_runtime import (
    ChildIpcServer,
    ChildRuntime,
    ChildStats,
    NORMAL_SOCKET_NAME,
    SAFETY_SOCKET_NAME,
)
from so101_teleop.unified.contracts import (
    ActionKey,
    ActionTerminal,
    DispatchAck,
    DispatchToken,
    Domain,
    IntentCancelReceipt,
    MutationError,
    OperationSpec,
    OwnerKey,
)
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.ipc import IpcRequest
from so101_teleop.unified.safety import SafetyAuthority

SERVICE_EPOCH = "e1"
RUNTIME_ID = "R1"
SERVICE_TOKEN = "test-service-token"
NORMAL_QUEUE_LIMIT = 2


@dataclass
class DriverJournal:
    submit_count: int = 0
    cancel_uuids: list[str] = field(default_factory=list)
    submit_uuids: list[str] = field(default_factory=list)


class BarrierActionDriver:
    """The single test-owned leaf: records real calls and can hold a terminal open."""

    def __init__(self) -> None:
        self.journal = DriverJournal()
        self.terminal_gate = asyncio.Event()
        self.terminal_gate.set()

    def allocate_goal_uuid(self, key) -> str:
        return f"goal-{key.child_id}"

    async def submit(self, token: DispatchToken, goal_uuid: str) -> DispatchAck:
        self.journal.submit_count += 1
        self.journal.submit_uuids.append(goal_uuid)
        return DispatchAck(
            ActionKey(
                operation_id=token.operation_id,
                child_id=token.child_id,
                goal_uuid=goal_uuid,
                owner=OwnerKey(os.getpid(), os.getpgrp(), 1, "argv", "env"),
                runtime_id=token.runtime_id,
                execution_generation=token.execution_generation,
            ),
            True,
        )

    async def cancel(self, goal_uuid: str) -> bool:
        self.journal.cancel_uuids.append(goal_uuid)
        return True

    async def terminal(self, goal_uuid: str) -> ActionTerminal:
        await self.terminal_gate.wait()
        raise MutationError("TERMINAL_NOT_MODELLED_IN_HARNESS")


class HoldProxy:
    """Forwards the normal channel, optionally holding client bytes back."""

    def __init__(self, listen: Path, upstream: Path) -> None:
        self.listen = Path(listen)
        self.upstream = Path(upstream)
        self.holding = False
        self._buffers: list[tuple[list[bytes], asyncio.StreamWriter]] = []
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.listen.unlink()
        self._server = await asyncio.start_unix_server(self._handle, path=str(self.listen))

    def hold(self) -> None:
        self.holding = True

    async def release(self) -> None:
        self.holding = False
        for buffer, writer in self._buffers:
            for chunk in buffer:
                writer.write(chunk)
            buffer.clear()
            with contextlib.suppress(Exception):
                await writer.drain()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream_reader, upstream_writer = await asyncio.open_unix_connection(str(self.upstream))
        buffer: list[bytes] = []
        self._buffers.append((buffer, upstream_writer))

        async def client_to_upstream() -> None:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    return
                if self.holding:
                    buffer.append(chunk)
                    continue
                upstream_writer.write(chunk)
                await upstream_writer.drain()

        async def upstream_to_client() -> None:
            while True:
                chunk = await upstream_reader.read(4096)
                if not chunk:
                    return
                writer.write(chunk)
                await writer.drain()

        try:
            await asyncio.gather(client_to_upstream(), upstream_to_client())
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        finally:
            upstream_writer.close()
            writer.close()
            with contextlib.suppress(Exception):
                await upstream_writer.wait_closed()

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
        with contextlib.suppress(FileNotFoundError):
            self.listen.unlink()


class TwoChannelHarness:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.driver = BarrierActionDriver()
        self.store: IntentStore | None = None
        self.arbiter: GlobalMutationArbiter | None = None
        self.runtime: ChildRuntime | None = None
        self.server: ChildIpcServer | None = None
        self.proxy: HoldProxy | None = None
        self.client: BridgeClient | None = None
        self.socket_root: Path | None = None
        self.prepared = 0

    @classmethod
    async def start(cls, root: Path) -> "TwoChannelHarness":
        self = cls(root)
        # Darwin caps AF_UNIX paths at 104 bytes, so the socket root is a short scratch
        # directory (under the registered evidence root when one is configured).
        base = os.environ.get("SO101_IPC_SOCKET_BASE") or tempfile.gettempdir()
        Path(base).mkdir(parents=True, exist_ok=True)
        self.socket_root = Path(tempfile.mkdtemp(prefix="so101ipc-", dir=base))
        socket_root = self.socket_root
        self.store = IntentStore.open(self.root / "state")
        self.arbiter = GlobalMutationArbiter(self.store, clock_ns=lambda: 1_000_000)
        owner = OwnerKey(os.getpid(), os.getpgrp(), 1, "argv", "env")
        self.runtime = ChildRuntime(
            self.driver,
            owner=owner,
            service_epoch=SERVICE_EPOCH,
            runtime_id=RUNTIME_ID,
            normal_queue_limit=NORMAL_QUEUE_LIMIT,
        )
        self.server = ChildIpcServer(
            self.runtime,
            socket_root=socket_root,
            owner=owner,
            service_epoch=SERVICE_EPOCH,
            service_token=SERVICE_TOKEN,
        )
        await self.server.start()
        self.proxy = HoldProxy(socket_root / "normal-proxy.sock", socket_root / NORMAL_SOCKET_NAME)
        await self.proxy.start()
        self.client = BridgeClient(
            normal_socket=self.proxy.listen,
            safety_socket=socket_root / SAFETY_SOCKET_NAME,
            service_epoch=SERVICE_EPOCH,
            runtime_id=RUNTIME_ID,
            service_token=SERVICE_TOKEN,
            owner=owner,
            timeout_s=2.0,
        )
        return self

    def prepare_child(self, child_id: str = "arm") -> DispatchToken:
        assert self.arbiter is not None
        self.prepared += 1
        parent = self.arbiter.begin(
            OperationSpec(
                f"op-{self.prepared}",
                Domain.TELEOP,
                "execute",
                {"child": child_id},
                RUNTIME_ID,
                1,
                10**18,
            )
        )
        return self.arbiter.prepare_child(parent.operation_id, child_id)

    def hold_normal_delivery(self) -> None:
        assert self.proxy is not None
        self.proxy.hold()

    async def release_normal_delivery(self) -> None:
        assert self.proxy is not None
        await self.proxy.release()

    async def send(self, token: DispatchToken) -> DispatchAck:
        assert self.client is not None
        request = IpcRequest(
            version=1,
            operation="execute_arm",
            command_id=f"cmd-{token.operation_id}-{token.child_id}",
            deadline_ns=10**18,
            service_epoch=SERVICE_EPOCH,
            runtime_id=RUNTIME_ID,
            service_token=SERVICE_TOKEN,
            token={
                "operation_id": token.operation_id,
                "child_id": token.child_id,
                "runtime_id": token.runtime_id,
                "execution_generation": token.execution_generation,
                "deadline_ns": token.deadline_ns,
                "revocation_revision": token.revocation_revision,
            },
        )
        reply = await self.client.call(request)
        if not reply.accepted:
            raise MutationError(reply.code)
        assert reply.ack is not None
        return DispatchAck(
            ActionKey(
                operation_id=reply.ack["operation_id"],
                child_id=reply.ack["child_id"],
                goal_uuid=reply.ack["goal_uuid"],
                owner=OwnerKey(**reply.ack["owner"]),
                runtime_id=reply.ack["runtime_id"],
                execution_generation=reply.ack["execution_generation"],
            ),
            True,
        )

    async def revoke(self, token: DispatchToken) -> IntentCancelReceipt:
        assert self.arbiter is not None and self.client is not None
        intent = self.arbiter.cancel_parent(token.operation_id)
        target = next(
            (item for item in intent.targets if item.key.child_id == token.child_id), None
        )
        if target is None:
            raise MutationError(f"NO_REVOKE_TARGET: {token.child_id}")
        authority = SafetyAuthority("watchdog", Domain.TELEOP, SERVICE_EPOCH, 1, None)
        return await self.client.revoke(target, authority)

    async def stats(self) -> ChildStats:
        assert self.runtime is not None
        return await self.runtime.stats()

    async def close(self) -> None:
        if self.client is not None:
            self.client.close()
        if self.proxy is not None:
            await self.proxy.close()
        if self.server is not None:
            await self.server.close()
        if self.store is not None:
            self.store.close()
        if self.socket_root is not None:
            shutil.rmtree(self.socket_root, ignore_errors=True)
