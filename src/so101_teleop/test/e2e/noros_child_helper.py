"""Test-owned ROS-free child used to exercise the real owner and client plumbing.

It runs the production ``ChildIpcServer``/``ChildRuntime`` over real sockets but with a
trivial leaf driver, so bridge ownership, ready handshakes, cancel delivery and crash
handling can be verified on a host without ROS.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from so101_teleop.unified.child_runtime import ChildIpcServer, ChildRuntime  # noqa: E402
from so101_teleop.unified.contracts import (  # noqa: E402
    ActionKey,
    ActionTerminal,
    DispatchAck,
    OwnerKey,
    PendingChildKey,
    DispatchToken,
)


DESCENDANT_FILE_NAME = "descendant.json"
STUBBORN_HELPER = Path(__file__).resolve().parents[1] / "fixtures/stubborn_helper.py"


def _fork_stubborn_descendant(socket_root: Path, *, timeout_s: float = 15.0) -> int:
    """Start a descendant the owner never tracks, in the owner's own process group.

    It ignores ``SIGTERM`` only after it has announced readiness, and this waits for that
    announcement, so the escalation under test is the only thing that can end it.
    """
    ready = Path(socket_root) / "descendant-ready.json"
    process = subprocess.Popen(
        [sys.executable, str(STUBBORN_HELPER), str(ready)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and not ready.is_file():
        time.sleep(0.02)
    if not ready.is_file():
        process.kill()
        raise RuntimeError("STUBBORN_DESCENDANT_NOT_READY")
    (Path(socket_root) / DESCENDANT_FILE_NAME).write_text(
        json.dumps({"pid": process.pid, "pgid": os.getpgrp()}, sort_keys=True) + "\n"
    )
    return process.pid


class NoRosDriver:
    def __init__(self) -> None:
        self.submitted: list[str] = []
        self.cancelled: list[str] = []

    def allocate_goal_uuid(self, key: PendingChildKey) -> str:
        return f"goal-{key.child_id}"

    async def submit(self, token: DispatchToken, goal_uuid: str) -> DispatchAck:
        self.submitted.append(goal_uuid)
        return DispatchAck(
            ActionKey(
                token.operation_id,
                token.child_id,
                goal_uuid,
                OwnerKey(os.getpid(), os.getpgrp(), 1, "argv", "env"),
                token.runtime_id,
                token.execution_generation,
            ),
            True,
        )

    async def cancel(self, goal_uuid: str) -> bool:
        self.cancelled.append(goal_uuid)
        return True

    async def terminal(self, goal_uuid: str) -> ActionTerminal:
        raise RuntimeError("terminal is not modelled by the no-ROS helper")


async def run(args) -> int:
    owner = OwnerKey(
        pid=os.getpid(),
        pgid=os.getpgrp(),
        started_ticks=int(args.started_ticks),
        argv_sha256=args.argv_sha256,
        environment_sha256=args.environment_sha256,
    )
    runtime = ChildRuntime(
        NoRosDriver(),
        owner=owner,
        service_epoch=args.service_epoch,
        runtime_id=args.runtime_id,
        normal_queue_limit=args.normal_queue_limit,
    )
    server = ChildIpcServer(
        runtime,
        socket_root=Path(args.socket_root),
        owner=owner,
        service_epoch=args.service_epoch,
        service_token=args.service_token,
    )
    await server.start()
    if args.fork_descendant:
        _fork_stubborn_descendant(Path(args.socket_root))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    if args.ignore_term:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    else:
        for name in ("SIGTERM", "SIGINT"):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(getattr(signal, name), stop.set)
    if args.exit_after_s is not None:
        loop.call_later(args.exit_after_s, stop.set)
    await stop.wait()
    await server.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-root", required=True)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--service-epoch", required=True)
    parser.add_argument("--service-token", required=True)
    parser.add_argument("--started-ticks", required=True)
    parser.add_argument("--argv-sha256", default="argv")
    parser.add_argument("--environment-sha256", default="env")
    parser.add_argument("--normal-queue-limit", type=int, default=2)
    parser.add_argument("--exit-after-s", type=float, default=None)
    parser.add_argument("--crash-immediately", action="store_true")
    parser.add_argument("--fork-descendant", action="store_true")
    parser.add_argument(
        "--ignore-term",
        action="store_true",
        help="survive SIGTERM/SIGINT the way a stuck child does, so only SIGKILL can clear it",
    )
    args = parser.parse_args()
    if args.crash_immediately:
        os._exit(9)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
