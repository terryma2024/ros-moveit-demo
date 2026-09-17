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
    arguments = parser.parse_args()
    arguments.root.mkdir(parents=True, exist_ok=True)

    stopped = False

    def stop(_number, _frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    child = None
    if arguments.mode in {"coordinator", "wrapper"}:
        child = subprocess.Popen(
            [
                sys.executable,
                __file__,
                "--mode",
                "runner",
                "--root",
                str(arguments.root),
                "--batch-id",
                arguments.batch_id,
            ]
        )
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
