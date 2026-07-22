#!/usr/bin/env python3
"""Validate independently captured final Gazebo, ROS, and MoveIt evidence."""

import math
import pathlib
import re
import sys


def fail(message: str) -> None:
    print(f'FAIL: {message}', file=sys.stderr)
    raise SystemExit(1)


def quaternion_from_rpy(roll: float, pitch: float, yaw: float) -> tuple[float, ...]:
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
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if (
        not math.isfinite(first_norm)
        or not math.isfinite(second_norm)
        or first_norm <= 1.0e-12
        or second_norm <= 1.0e-12
    ):
        return math.inf
    dot = abs(sum(a * b for a, b in zip(first, second)))
    dot /= first_norm * second_norm
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


if len(sys.argv) not in (5, 8):
    fail('expected GAZEBO_POSE ATTACHMENT JOINT_STATES PLANNING_SCENE [X Y Z]')

gazebo_text, attachment_text, joint_text, scene_text = (
    pathlib.Path(path).read_text(encoding='utf-8') for path in sys.argv[1:5]
)
expected_coke_pose = (
    tuple(float(value) for value in sys.argv[5:8])
    if len(sys.argv) == 8 else (0.3, 0.2, 0.836)
)

gazebo_match = re.search(
    r'Pose \[ XYZ \(m\) \] \[ RPY \(rad\) \]:\s*'
    r'\[\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\]\s*'
    r'\[\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\]',
    gazebo_text,
)
if not gazebo_match:
    fail('Gazebo Coke pose is missing')
gazebo_values = tuple(float(value) for value in gazebo_match.groups())
if not all(math.isfinite(value) for value in gazebo_values):
    fail('Gazebo Coke pose is non-finite')
gazebo_pose = gazebo_values[:3]
gazebo_orientation = quaternion_from_rpy(*gazebo_values[3:])
if math.dist(gazebo_pose, expected_coke_pose) > 0.01:
    fail(f'Gazebo Coke is outside place tolerance: {gazebo_pose}')
if orientation_distance(gazebo_orientation, (0.0, 0.0, 0.0, 1.0)) > 0.0872665:
    fail('Gazebo Coke orientation is not upright')

if not re.search(r'data:\s*"?detached"?', attachment_text):
    fail('Gazebo attachment evidence is not detached')

names_match = re.search(r'name:\s*\n(?P<body>(?:- [^\n]+\n)+)position:', joint_text)
position_match = re.search(
    r'position:\s*\n(?P<body>(?:- [^\n]+\n)+)velocity:', joint_text
)
velocity_match = re.search(
    r'velocity:\s*\n(?P<body>(?:- [^\n]+\n)+)effort:', joint_text
)
if not names_match or not position_match or not velocity_match:
    fail('joint-state arrays are incomplete')


def list_values(match: re.Match[str]) -> list[str]:
    return [line[2:].strip() for line in match.group('body').splitlines()]


names = list_values(names_match)
positions = [float(value) for value in list_values(position_match)]
velocities = [float(value) for value in list_values(velocity_match)]
if len(names) != len(positions) or len(names) != len(velocities):
    fail('joint-state array lengths differ')
if not all(math.isfinite(value) for value in positions + velocities):
    fail('joint-state evidence is non-finite')
joint_positions = dict(zip(names, positions))
for finger in ('panda_finger_joint1', 'panda_finger_joint2'):
    if joint_positions.get(finger, -math.inf) < 0.038:
        fail(f'{finger} is not safely open')
if any(abs(velocity) > 0.01 for velocity in velocities):
    fail('robot is not stationary in final joint-state evidence')

if 'attached_collision_objects=[]' not in scene_text:
    fail('MoveIt still has an attached collision object')
scene_matches = re.findall(
    r'CollisionObject\(.*?pose=geometry_msgs\.msg\.Pose\('
    r'position=geometry_msgs\.msg\.Point\('
    r'x=([-+0-9.eE]+), y=([-+0-9.eE]+), z=([-+0-9.eE]+)\), '
    r'orientation=geometry_msgs\.msg\.Quaternion\('
    r'x=([-+0-9.eE]+), y=([-+0-9.eE]+), z=([-+0-9.eE]+), '
    r'w=([-+0-9.eE]+)\)\).*?'
    r"id='([^']+)'",
    scene_text,
)
moveit_objects = {
    object_id: (
        (float(x), float(y), float(z)),
        (float(qx), float(qy), float(qz), float(qw)),
    )
    for x, y, z, qx, qy, qz, qw, object_id in scene_matches
}
if 'coke' not in moveit_objects:
    fail('MoveIt world does not contain Coke')
moveit_pose, moveit_orientation = moveit_objects['coke']
if not all(math.isfinite(value) for value in moveit_pose + moveit_orientation):
    fail('MoveIt Coke pose is non-finite')
if math.dist(moveit_pose, expected_coke_pose) > 0.01:
    fail(f'MoveIt Coke is outside place tolerance: {moveit_pose}')
if orientation_distance(moveit_orientation, (0.0, 0.0, 0.0, 1.0)) > 0.0872665:
    fail('MoveIt Coke orientation is not upright')
if math.dist(moveit_pose, gazebo_pose) > 0.01:
    fail('Gazebo and MoveIt Coke poses differ by more than 10 mm')
if orientation_distance(moveit_orientation, gazebo_orientation) > 0.0872665:
    fail('Gazebo and MoveIt Coke orientations differ by more than 5 degrees')

print('PASS: independent Gazebo, joint-state, and Planning Scene evidence')
