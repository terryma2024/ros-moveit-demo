"""Non-web ROS child entrypoint.

This module is the only place where ROS is imported. The web process never imports it;
it is executed as ``python -m so101_teleop.unified.ros_child`` with an argv built from
validated server configuration. The child owns its own ROS client, threads and IPC
endpoints, and it never gains the right to stop a simulator, controller or foreign
process it does not own.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import time
from pathlib import Path

from .child_runtime import ChildIpcServer, ChildRuntime
from .contracts import (
    ActionKey,
    ActionTerminal,
    DispatchAck,
    DispatchToken,
    MutationError,
    OwnerKey,
    PendingChildKey,
)
from .ipc import DEFAULT_MAX_BYTES

CHILD_SERVICE_TOKEN_ENV = "SO101_CHILD_SERVICE_TOKEN"
CHILD_SERVICE_EPOCH_ENV = "SO101_CHILD_SERVICE_EPOCH"
CHILD_WEB_PID_ENV = "SO101_CHILD_WEB_PID"
CHILD_HEARTBEAT_ENV = "SO101_CHILD_HEARTBEAT"
CHILD_HEARTBEAT_TIMEOUT_ENV = "SO101_CHILD_HEARTBEAT_TIMEOUT_S"
CHILD_NORMAL_QUEUE_ENV = "SO101_CHILD_NORMAL_QUEUE_LIMIT"
DEFAULT_HEARTBEAT_TIMEOUT_S = 5.0


class RclpyActionDriver:
    """Adapter over the existing Teleop ROS worker.

    Imported lazily so that importing this module never pulls ROS into the web process.
    """

    def __init__(self) -> None:
        from so101_teleop import server as ros_server  # noqa: F401  (ROS import boundary)

        self._server_module = ros_server
        self._worker = None

    def allocate_goal_uuid(self, key: PendingChildKey) -> str:
        import uuid

        # The real ROS goal UUID is pre-allocated and registered before send; a proxy
        # identity is never substituted for it.
        return str(uuid.uuid4())

    async def submit(self, token: DispatchToken, goal_uuid: str) -> DispatchAck:
        raise MutationError(
            "ROS_DRIVER_NOT_PROVISIONED: this host has no verified ROS worker wiring"
        )

    async def cancel(self, goal_uuid: str) -> bool:
        raise MutationError("ROS_DRIVER_NOT_PROVISIONED: cannot cancel without a ROS worker")

    async def terminal(self, goal_uuid: str) -> ActionTerminal:
        raise MutationError("ROS_DRIVER_NOT_PROVISIONED: cannot observe without a ROS worker")


def local_owner(runtime_id: str) -> OwnerKey:
    import hashlib
    import json

    argv = list(os.environ.get("SO101_CHILD_ARGV", "").split("\0"))
    return OwnerKey(
        pid=os.getpid(),
        pgid=os.getpgid(0),
        started_ticks=int(time.monotonic_ns()),
        argv_sha256=hashlib.sha256("\0".join(argv).encode()).hexdigest(),
        environment_sha256=hashlib.sha256(json.dumps(dict(os.environ), sort_keys=True).encode()).hexdigest(),
    )


async def watchdog(runtime: ChildRuntime, *, web_pid: int | None, heartbeat: Path | None, timeout_s: float) -> None:
    """Stop accepting mutations and revoke known goals when the web owner disappears."""
    while True:
        await asyncio.sleep(min(timeout_s, 1.0) / 2)
        if runtime.web_dead:
            return
        dead = False
        if web_pid is not None:
            try:
                os.kill(web_pid, 0)
            except (ProcessLookupError, PermissionError):
                dead = True
        if heartbeat is not None:
            if not heartbeat.is_file():
                dead = True
            elif time.time() - heartbeat.stat().st_mtime > timeout_s:
                dead = True
        if dead:
            await runtime.mark_web_dead("web owner heartbeat lost")
            return


async def serve(server: ChildIpcServer, runtime: ChildRuntime, watchdog_task: asyncio.Task) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in ("SIGTERM", "SIGINT"):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(getattr(signal, signal_name), stop.set)
    await stop.wait()
    watchdog_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watchdog_task
    await server.close()
    del runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SO-101 unified non-web ROS child")
    parser.add_argument("--socket-root", required=True, type=Path)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)

    service_token = os.environ.get(CHILD_SERVICE_TOKEN_ENV)
    service_epoch = os.environ.get(CHILD_SERVICE_EPOCH_ENV)
    if not service_token or not service_epoch:
        parser.error(f"{CHILD_SERVICE_TOKEN_ENV} and {CHILD_SERVICE_EPOCH_ENV} are required")
    normal_queue_limit = int(os.environ.get(CHILD_NORMAL_QUEUE_ENV, "2"))
    web_pid = os.environ.get(CHILD_WEB_PID_ENV)
    heartbeat = os.environ.get(CHILD_HEARTBEAT_ENV)
    timeout_s = float(os.environ.get(CHILD_HEARTBEAT_TIMEOUT_ENV, DEFAULT_HEARTBEAT_TIMEOUT_S))

    runtime = ChildRuntime(
        RclpyActionDriver(),
        owner=local_owner(args.runtime_id),
        service_epoch=service_epoch,
        runtime_id=args.runtime_id,
        normal_queue_limit=normal_queue_limit,
    )
    server = ChildIpcServer(
        runtime,
        socket_root=args.socket_root,
        owner=runtime.owner,
        service_epoch=service_epoch,
        service_token=service_token,
        max_bytes=args.max_bytes,
    )

    async def run() -> None:
        await server.start()
        watchdog_task = asyncio.get_running_loop().create_task(
            watchdog(
                runtime,
                web_pid=int(web_pid) if web_pid else None,
                heartbeat=Path(heartbeat) if heartbeat else None,
                timeout_s=timeout_s,
            )
        )
        await serve(server, runtime, watchdog_task)

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
