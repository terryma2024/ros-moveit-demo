#!/usr/bin/env python3
"""L2 adaptive helper: a real OS process playing the production wrapper boundary.

The Web layer owns only this wrapper PID; this helper owns one real child
("Runner") and exact cleanup.  It writes the wrapper handshake the production
process owner reads, forwards SIGINT into a real cleanup transaction, and
never fabricates Runner journal truth.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

_MARKER = "e2e-test-execution-port-v1"


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--preferred-worker-count", required=True, type=int)
    parser.add_argument("--point-id", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    runtime_root = args.runtime_root
    if not runtime_root.is_dir():
        raise RuntimeError("ADAPTIVE_RUNTIME_ROOT_MISSING")

    runner = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "descendant_helper.py")],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _atomic_write(
        runtime_root / "handshake.json",
        json.dumps({
            "wrapper_pid": os.getpid(),
            "batch_id": args.batch_id,
            "runner_pid": runner.pid,
            "qualification": _MARKER,
        }, sort_keys=True).encode("utf-8") + b"\n",
    )

    cancelled = {"value": False}

    def _on_sigint(_signum, _frame):
        cancelled["value"] = True

    signal.signal(signal.SIGINT, _on_sigint)

    while not cancelled["value"]:
        time.sleep(0.05)

    if spec.get("adaptive_cancel") == "no-cleanup":
        runner.terminate()
        runner.wait(timeout=5)
        return 1
    runner.terminate()
    runner.wait(timeout=5)
    _atomic_write(
        runtime_root / "cleanup-receipt.json",
        json.dumps({
            "batch_id": args.batch_id,
            "cleanup_complete": True,
            "runner_exited": True,
            "qualification": _MARKER,
        }, sort_keys=True).encode("utf-8") + b"\n",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
