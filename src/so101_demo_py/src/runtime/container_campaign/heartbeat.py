"""One owner connection, generation and receive-clock deadline; no Host PID probe."""

import threading
import time
import asyncio
import json
import os
from pathlib import Path
import stat


def validate_owner_heartbeat(document):
    if (type(document) is not dict or set(document) != {
            "kind", "generation", "sequence", "sent_monotonic_ns"}
            or document["kind"] != "owner_heartbeat"
            or any(type(document[name]) is not int or document[name] <= 0
                   for name in ("generation", "sequence", "sent_monotonic_ns"))):
        raise ValueError("OWNER_HEARTBEAT_INVALID")
    return document.copy()


class OwnerHeartbeatMonitor:
    def __init__(self, *, generation, timeout_ns, monotonic_ns=time.monotonic_ns):
        if any(type(value) is not int or value <= 0 for value in (generation, timeout_ns)):
            raise ValueError("OWNER_HEARTBEAT_CONFIG_INVALID")
        self.generation, self.timeout_ns, self.clock = generation, timeout_ns, monotonic_ns
        self._lock = threading.RLock()
        self._last_received = self._last_observed = self.clock()
        if type(self._last_received) is not int or self._last_received <= 0:
            raise ValueError("OWNER_HEARTBEAT_CONFIG_INVALID")
        self._sequence = 0
        self._connection = None
        self._reason = None

    def _expired(self):
        if self._reason is not None:
            return True
        now = self.clock()
        if type(now) is not int or now < self._last_observed:
            self._reason = self._reason or "OWNER_CLOCK_REGRESSION"
        elif now - self._last_received >= self.timeout_ns:
            self._reason = self._reason or "OWNER_HEARTBEAT_EXPIRED"
        self._last_observed = now
        return self._reason is not None

    @property
    def expired(self):
        with self._lock:
            return self._expired()

    @property
    def reason(self):
        with self._lock:
            self._expired()
            return self._reason

    def receive(self, document, *, connection):
        packet = validate_owner_heartbeat(document)
        with self._lock:
            if self._expired():
                raise ValueError("OWNER_HEARTBEAT_FENCED")
            if packet["generation"] != self.generation or packet["sequence"] <= self._sequence:
                raise ValueError("OWNER_HEARTBEAT_INVALID")
            if connection is None:
                raise ValueError("OWNER_HEARTBEAT_INVALID")
            if self._connection is not None and self._connection is not connection:
                raise ValueError("OWNER_HEARTBEAT_CONNECTION_OWNED")
            self._last_received = self._last_observed
            self._sequence, self._connection = packet["sequence"], connection
            return {"kind": "owner_heartbeat_ack", "generation": self.generation, "sequence": self._sequence}

    def disconnected(self, connection):
        with self._lock:
            if self._connection is connection and connection is not None:
                self._reason = self._reason or "OWNER_CONNECTION_LOST"


class OwnerHeartbeatChannel:
    """Host's one persistent control connection; loss never reconnects a generation."""

    def __init__(self, *, socket_path, generation, timeout_ns, max_bytes):
        if any(type(value) is not int or value <= 0 for value in (generation, timeout_ns, max_bytes)):
            raise ValueError("OWNER_HEARTBEAT_CONFIG_INVALID")
        self.socket_path = Path(socket_path)
        self.generation, self.timeout_ns, self.max_bytes = generation, timeout_ns, max_bytes
        self._reader = self._writer = self._task = None
        self._sequence = 0
        self._started = False
        self._lock = asyncio.Lock()
        self.error = None

    async def start(self):
        from so101_demo.runtime.inference.codec import open_socket_parent
        from so101_demo.runtime.parallel_ipc.frames import transport_address

        if self._started:
            raise ValueError("OWNER_HEARTBEAT_ALREADY_STARTED")
        self._started = True
        try:
            fd = open_socket_parent(self.socket_path)
            try:
                metadata = os.stat(self.socket_path.name, dir_fd=fd, follow_symlinks=False)
                if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid():
                    raise ValueError("OWNER_HEARTBEAT_SOCKET_INVALID")
                self._reader, self._writer = await asyncio.wait_for(asyncio.open_unix_connection(
                    transport_address(self.socket_path, fd), limit=self.max_bytes+1), self.timeout_ns/1e9)
            finally:
                os.close(fd)
            await self.send_once()
            self._task = asyncio.create_task(self._loop())
        except BaseException as error:
            self.error = error
            await self.close()
            raise

    async def send_once(self):
        from so101_teleop.unified.ipc import IpcReply
        from so101_demo.runtime.parallel_ipc.frames import _pairs

        async with self._lock:
            if self._writer is None or self._writer.is_closing() or self.error is not None:
                raise ValueError("OWNER_HEARTBEAT_FENCED")
            self._sequence += 1
            packet = dict(kind="owner_heartbeat", generation=self.generation,
                          sequence=self._sequence, sent_monotonic_ns=time.monotonic_ns())
            self._writer.write(json.dumps(packet, separators=(",", ":")).encode()+b"\n")
            await asyncio.wait_for(self._writer.drain(), self.timeout_ns/1e9)
            line = await asyncio.wait_for(self._reader.readline(), self.timeout_ns/1e9)
            if not line or len(line) > self.max_bytes:
                raise ValueError("OWNER_HEARTBEAT_ACK_INVALID")
            document = json.loads(line, object_pairs_hook=_pairs,
                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("nonfinite")))
            reply = IpcReply.model_validate(document, strict=True)
            if (type(reply.result) is not dict
                    or type(reply.result.get("generation")) is not int
                    or type(reply.result.get("sequence")) is not int
                    or not reply.accepted or reply.code != "OK" or reply.ack is not None or reply.terminal is not None
                    or reply.result != dict(
                    kind="owner_heartbeat_ack", generation=self.generation, sequence=self._sequence)):
                raise ValueError("OWNER_HEARTBEAT_ACK_INVALID")

    async def _loop(self):
        try:
            while True:
                await asyncio.sleep(self.timeout_ns/2e9)
                await self.send_once()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.error = error
            self._writer.close()

    async def close(self):
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
