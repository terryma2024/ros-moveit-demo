"""Own the unified MuJoCo stack and Teleop server in one process group."""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--headless", choices=("true", "false"), required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    commands = [
        [
            "ros2",
            "launch",
            "so101_demo_py",
            "so101_mujoco.launch.py",
            "run_mode:=execute",
            "execute:=true",
            f"headless:={options.headless}",
            f"session_id:={options.session_id}",
        ],
        [
            "ros2",
            "launch",
            "so101_teleop",
            "so101_teleop.launch.py",
            "backend:=mujoco_py",
            "bind_address:=127.0.0.1",
            f"port:={options.port}",
            f"simulation_session_id:={options.session_id}",
            "build_web_if_needed:=false",
        ],
    ]
    children = [subprocess.Popen(command) for command in commands]
    interrupted = False

    def on_interrupt(_signum, _frame) -> None:
        nonlocal interrupted
        interrupted = True

    previous = signal.signal(signal.SIGINT, on_interrupt)
    try:
        while not interrupted and all(child.poll() is None for child in children):
            time.sleep(0.2)
    finally:
        signal.signal(signal.SIGINT, previous)
        for child in children:
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
        returncodes = []
        for child in children:
            try:
                returncodes.append(child.wait(timeout=60.0))
            except subprocess.TimeoutExpired:
                child.terminate()
                returncodes.append(child.wait(timeout=10.0))
    return 0 if interrupted and all(code == 0 for code in returncodes) else 1


if __name__ == "__main__":
    sys.exit(main())
