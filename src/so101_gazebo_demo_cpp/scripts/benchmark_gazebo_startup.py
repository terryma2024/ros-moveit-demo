#!/usr/bin/env python3
"""Measure SO101 Gazebo startup through active controller evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import tempfile
import time


REQUIRED_CONTROLLERS = (
    'joint_state_broadcaster',
    'arm_controller',
    'gripper_controller',
)


def controllers_ready(output: str) -> bool:
    """Return true only when every required controller is active."""
    lines = output.splitlines()
    return all(
        any(name in line and 'active' in line.split() for line in lines)
        for name in REQUIRED_CONTROLLERS
    )


def summarize(durations: list[float], *, piece_count: int) -> dict:
    """Build the stable JSON summary used for before/after comparison."""
    return {
        'durations_seconds': durations,
        'median_seconds': statistics.median(durations),
        'piece_count': piece_count,
        'success': True,
    }


def stop_process_group(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def measure_runs(
    command: list[str],
    *,
    runs: int,
    timeout: float,
    domain_start: int,
    partition_prefix: str,
) -> list[float]:
    durations: list[float] = []
    for index in range(runs):
        environment = os.environ.copy()
        environment['ROS_DOMAIN_ID'] = str(domain_start + index)
        environment['ROS2CLI_DISABLE_DAEMON'] = '1'
        environment['GZ_PARTITION'] = f'{partition_prefix}_{index}'
        started = time.monotonic()
        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as log:
            process = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                env=environment,
                start_new_session=True,
            )
            try:
                deadline = started + timeout
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(
                            f'Gazebo launch exited before controllers were active:\n{log.read()}'
                        )
                    observed = subprocess.run(
                        ['ros2', 'control', 'list_controllers'],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        env=environment,
                    )
                    if observed.returncode == 0 and controllers_ready(observed.stdout):
                        durations.append(round(time.monotonic() - started, 6))
                        break
                    time.sleep(0.2)
                else:
                    log.seek(0)
                    raise TimeoutError(
                        f'controllers were not active within {timeout:.1f}s:\n{log.read()}'
                    )
            finally:
                stop_process_group(process)
    return durations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, required=True)
    parser.add_argument('--timeout', type=float, required=True)
    parser.add_argument('--domain-start', type=int, required=True)
    parser.add_argument('--partition-prefix', required=True)
    parser.add_argument('--piece-count', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.runs <= 0 or args.timeout <= 0 or args.piece_count <= 0:
        raise ValueError('runs, timeout, and piece count must be positive')
    command = [
        'ros2', 'launch', 'so101_gazebo_demo', 'so101_gazebo.launch.py',
        'headless:=true',
    ]
    durations = measure_runs(
        command,
        runs=args.runs,
        timeout=args.timeout,
        domain_start=args.domain_start,
        partition_prefix=args.partition_prefix,
    )
    result = summarize(durations, piece_count=args.piece_count)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
