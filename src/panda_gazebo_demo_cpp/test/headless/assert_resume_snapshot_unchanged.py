#!/usr/bin/env python3
"""Assert that plan-only resume caused no observable physical movement."""

import json
import math
from pathlib import Path
import sys


JOINT_POSITION_TOLERANCE = 1.0e-2
JOINT_VELOCITY_TOLERANCE = 1.0e-2
GAZEBO_POSITION_TOLERANCE = 5.0e-4
GAZEBO_ORIENTATION_TOLERANCE = 1.0e-2
MOVEIT_POSITION_TOLERANCE = 1.0e-8
MOVEIT_ORIENTATION_TOLERANCE = 1.0e-8


def fail(message: str) -> None:
    print(f'FAIL: {message}', file=sys.stderr)
    raise SystemExit(1)


def quaternion_distance(first: list[float], second: list[float]) -> float:
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if first_norm <= 1.0e-12 or second_norm <= 1.0e-12:
        return math.inf
    dot = abs(sum(a * b for a, b in zip(first, second)))
    dot /= first_norm * second_norm
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


def pose_errors(first: list[float], second: list[float]) -> tuple[float, float]:
    return (
        math.dist(first[:3], second[:3]),
        quaternion_distance(first[3:], second[3:]),
    )


if len(sys.argv) != 3:
    fail('expected BEFORE_SNAPSHOT_JSON AFTER_SNAPSHOT_JSON')

before = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
after = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))

for field in (
    'gazebo_attached',
    'moveit_coke_attached',
    'moveit_coke_in_world',
):
    if before.get(field) != after.get(field):
        fail(f'{field} changed during plan-only resume')

before_positions = before.get('joint_positions', {})
after_positions = after.get('joint_positions', {})
before_velocities = before.get('joint_velocities', {})
after_velocities = after.get('joint_velocities', {})
if before_positions.keys() != after_positions.keys():
    fail('joint position names changed during plan-only resume')
if before_velocities.keys() != after_velocities.keys():
    fail('joint velocity names changed during plan-only resume')
for name in before_positions:
    drift = abs(before_positions[name] - after_positions[name])
    if drift > JOINT_POSITION_TOLERANCE:
        fail(
            f'{name} moved by {drift:.9f} rad; tolerance is '
            f'{JOINT_POSITION_TOLERANCE:.9f}'
        )
for name in before_velocities:
    before_velocity = abs(before_velocities[name])
    after_velocity = abs(after_velocities[name])
    if max(before_velocity, after_velocity) > JOINT_VELOCITY_TOLERANCE:
        fail(
            f'{name} is not stationary: before={before_velocity:.9f} '
            f'after={after_velocity:.9f}'
        )

for field, position_tolerance, orientation_tolerance in (
    (
        'gazebo_coke_pose',
        GAZEBO_POSITION_TOLERANCE,
        GAZEBO_ORIENTATION_TOLERANCE,
    ),
    (
        'moveit_coke_pose',
        MOVEIT_POSITION_TOLERANCE,
        MOVEIT_ORIENTATION_TOLERANCE,
    ),
):
    first = before.get(field)
    second = after.get(field)
    if not isinstance(first, list) or not isinstance(second, list):
        fail(f'{field} is missing')
    if len(first) != 7 or len(second) != 7:
        fail(f'{field} is not a 7-value 6DoF pose')
    position_error, orientation_error = pose_errors(first, second)
    if position_error > position_tolerance:
        fail(
            f'{field} position changed by {position_error:.9f} m; '
            f'tolerance is {position_tolerance:.9f}'
        )
    if orientation_error > orientation_tolerance:
        fail(
            f'{field} orientation changed by {orientation_error:.9f} rad; '
            f'tolerance is {orientation_tolerance:.9f}'
        )

print('PASS: plan-only resume left all independent observations unchanged')
