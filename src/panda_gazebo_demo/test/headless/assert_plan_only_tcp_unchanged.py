#!/usr/bin/env python3
"""Compare observed START_TCP_POSE evidence from two plan-only processes."""

import math
from pathlib import Path
import re
import sys


NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
POSITION_TOLERANCE = 0.010
ORIENTATION_TOLERANCE = 0.035


def fail(message: str) -> None:
    print(f'FAIL: {message}', file=sys.stderr)
    raise SystemExit(1)


def quaternion_from_rpy(
    roll: float, pitch: float, yaw: float
) -> tuple[float, ...]:
    cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def orientation_distance(
    first: tuple[float, ...], second: tuple[float, ...]
) -> float:
    dot = abs(sum(a * b for a, b in zip(first, second)))
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


def start_pose(path: Path, state: str) -> tuple[float, ...]:
    text = path.read_text(encoding='utf-8')
    matches = list(re.finditer(
        rf'START_TCP_POSE[^\n]*\bstate={re.escape(state)}\b'
        rf'[^\n]*\bx=({NUMBER})[^\n]*\by=({NUMBER})'
        rf'[^\n]*\bz=({NUMBER})[^\n]*\broll=({NUMBER})'
        rf'[^\n]*\bpitch=({NUMBER})[^\n]*\byaw=({NUMBER})',
        text,
    ))
    if not matches:
        fail(f'{path} has no finite START_TCP_POSE for {state}')
    values = tuple(float(value) for value in matches[-1].groups())
    if not all(math.isfinite(value) for value in values):
        fail(f'{path} has a non-finite START_TCP_POSE for {state}')
    return values


if len(sys.argv) != 4:
    fail('expected FIRST_PLAN_LOG SECOND_PLAN_LOG EXPECTED_STATE')

first = start_pose(Path(sys.argv[1]), sys.argv[3])
second = start_pose(Path(sys.argv[2]), sys.argv[3])
position_error = math.dist(first[:3], second[:3])
orientation_error = orientation_distance(
    quaternion_from_rpy(*first[3:]), quaternion_from_rpy(*second[3:])
)
if position_error > POSITION_TOLERANCE:
    fail(
        f'TCP moved by {position_error:.6f} m across plan-only processes; '
        f'tolerance is {POSITION_TOLERANCE:.6f}'
    )
if orientation_error > ORIENTATION_TOLERANCE:
    fail(
        f'TCP rotated by {orientation_error:.6f} rad across plan-only '
        f'processes; tolerance is {ORIENTATION_TOLERANCE:.6f}'
    )
print(
    f'PASS: {sys.argv[3]} START_TCP_POSE remained within '
    f'{POSITION_TOLERANCE:.3f} m / {ORIENTATION_TOLERANCE:.3f} rad'
)
