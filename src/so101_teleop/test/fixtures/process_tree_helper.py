#!/usr/bin/env python3
"""Small non-ROS process tree used by process-owner integration tests."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def _write(path: Path, document: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("coordinator", "wrapper", "runner"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--batch-id", default="b001")
    parser.add_argument("--leader-exits", action="store_true")
    parser.add_argument(
        "--ignore-term",
        action="store_true",
        help="survive SIGTERM/SIGINT the way a stuck helper does, so only SIGKILL can clear it",
    )
    arguments = parser.parse_args()
    arguments.root.mkdir(parents=True, exist_ok=True)

    stopped = False

    def stop(_number, _frame):
        nonlocal stopped
        stopped = True

    if arguments.ignore_term:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        # Announce readiness only now: a test that signals before this point would measure how fast
        # the interpreter starts rather than whether the escalation under test works.
        _write(
            arguments.root / f"{arguments.batch_id}.{arguments.mode}.ready.json",
            {"pid": os.getpid(), "ignoring": ["SIGTERM", "SIGINT"]},
        )
    else:
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)

    child = None
    if arguments.mode in {"coordinator", "wrapper"}:
        child_argv = [
            sys.executable,
            __file__,
            "--mode",
            "runner",
            "--root",
            str(arguments.root),
            "--batch-id",
            arguments.batch_id,
        ]
        if arguments.ignore_term:
            child_argv.append("--ignore-term")
        child = subprocess.Popen(child_argv)
        _write(
            arguments.root / "handshake.json",
            {
                "wrapper_pid": os.getpid(),
                "runner_pid": child.pid,
                "batch_id": arguments.batch_id,
            },
        )
        if arguments.leader_exits:
            return 0

    while not stopped:
        time.sleep(0.02)
    if child is not None:
        child.send_signal(signal.SIGTERM)
        child.wait(timeout=3)
    _write(arguments.root / "cleanup.json", {"cleanup_complete": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
