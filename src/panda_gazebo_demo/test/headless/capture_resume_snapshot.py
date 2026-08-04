#!/usr/bin/env python3
"""Normalize independent Gazebo, joint-state, and MoveIt observations."""

import json
import math
from pathlib import Path
import re
import sys


NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'


def fail(message: str) -> None:
    print(f'FAIL: {message}', file=sys.stderr)
    raise SystemExit(1)


def quaternion_from_rpy(
    roll: float, pitch: float, yaw: float
) -> list[float]:
    cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    return [
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    ]


def yaml_list(text: str, start: str, end: str) -> list[str]:
    match = re.search(
        rf'{re.escape(start)}:\s*\n(?P<body>(?:- [^\n]+\n)+)'
        rf'{re.escape(end)}:',
        text,
    )
    if not match:
        fail(f'joint-state {start} array is missing')
    return [line[2:].strip() for line in match.group('body').splitlines()]


if len(sys.argv) not in (6, 7):
    fail(
        'expected GAZEBO_POSE ATTACHMENT JOINT_STATES '
        'PLANNING_SCENE OUTPUT_JSON [TCP_TF]'
    )

gazebo_text, attachment_text, joint_text, scene_text = (
    Path(path).read_text(encoding='utf-8') for path in sys.argv[1:5]
)
output_path = Path(sys.argv[5])

gazebo_match = re.search(
    rf'Pose \[ XYZ \(m\) \] \[ RPY \(rad\) \]:\s*'
    rf'\[\s*({NUMBER})\s+({NUMBER})\s+({NUMBER})\s*\]\s*'
    rf'\[\s*({NUMBER})\s+({NUMBER})\s+({NUMBER})\s*\]',
    gazebo_text,
)
if not gazebo_match:
    fail('Gazebo Coke 6DoF pose is missing')
gazebo_values = [float(value) for value in gazebo_match.groups()]
if not all(math.isfinite(value) for value in gazebo_values):
    fail('Gazebo Coke pose contains a non-finite value')

attachment_samples = re.findall(
    r'data:\s*"?(attached|detached)"?', attachment_text
)
if not attachment_samples:
    fail('durable Gazebo attachment sample is missing')
gazebo_attached = attachment_samples[-1] == 'attached'

names = yaml_list(joint_text, 'name', 'position')
positions = [float(value) for value in yaml_list(
    joint_text, 'position', 'velocity'
)]
velocities = [float(value) for value in yaml_list(
    joint_text, 'velocity', 'effort'
)]
if len(names) != len(positions) or len(names) != len(velocities):
    fail('joint-state arrays have different lengths')
if len(set(names)) != len(names):
    fail('joint-state names are not unique')
if not all(math.isfinite(value) for value in positions + velocities):
    fail('joint-state observation contains a non-finite value')

moveit_attached = bool(re.search(
    r"attached_collision_objects=\[(?!\])[\s\S]*?id='coke'",
    scene_text,
))
collision_objects = re.findall(
    rf'CollisionObject\(.*?pose=geometry_msgs\.msg\.Pose\('
    rf'position=geometry_msgs\.msg\.Point\(x=({NUMBER}), y=({NUMBER}), '
    rf'z=({NUMBER})\), orientation=geometry_msgs\.msg\.Quaternion\('
    rf'x=({NUMBER}), y=({NUMBER}), z=({NUMBER}), w=({NUMBER})\)\).*?'
    r"id='([^']+)'",
    scene_text,
)
coke_poses = [
    [float(value) for value in values]
    for *values, object_id in collision_objects
    if object_id == 'coke'
]
if len(coke_poses) != 1:
    fail(
        'Planning Scene must contain exactly one Coke pose across world and '
        f'attached objects; observed {len(coke_poses)}'
    )
moveit_coke_pose = coke_poses[0]
if not all(math.isfinite(value) for value in moveit_coke_pose):
    fail('MoveIt Coke pose contains a non-finite value')

snapshot = {
    'gazebo_attached': gazebo_attached,
    'gazebo_coke_pose': gazebo_values[:3]
    + quaternion_from_rpy(*gazebo_values[3:]),
    'joint_positions': dict(zip(names, positions)),
    'joint_velocities': dict(zip(names, velocities)),
    'moveit_coke_attached': moveit_attached,
    'moveit_coke_in_world': not moveit_attached,
    'moveit_coke_pose': moveit_coke_pose,
}
if len(sys.argv) == 7:
    tcp_text = Path(sys.argv[6]).read_text(encoding='utf-8')
    tcp_match = re.search(
        rf'Translation:\s*\[\s*({NUMBER}),\s*({NUMBER}),\s*({NUMBER})\s*\]'
        rf'[\s\S]*?Quaternion \(xyzw\)\s*\[\s*({NUMBER}),\s*'
        rf'({NUMBER}),\s*({NUMBER}),\s*({NUMBER})\s*\]',
        tcp_text,
    )
    if not tcp_match:
        tcp_match = re.search(
            rf'FAULT_FIXTURE_EXECUTED_TCP_POSE\s+x=({NUMBER})\s+'
            rf'y=({NUMBER})\s+z=({NUMBER})\s+qx=({NUMBER})\s+'
            rf'qy=({NUMBER})\s+qz=({NUMBER})\s+qw=({NUMBER})',
            tcp_text,
        )
    tcp_rpy_match = None
    if not tcp_match:
        tcp_rpy_matches = re.findall(
            rf'EXECUTED_END_TCP_POSE[^\n]*\bx=({NUMBER})\s+'
            rf'y=({NUMBER})\s+z=({NUMBER})\s+roll=({NUMBER})\s+'
            rf'pitch=({NUMBER})\s+yaw=({NUMBER})',
            tcp_text,
        )
        tcp_rpy_match = tcp_rpy_matches[-1] if tcp_rpy_matches else None
    if not tcp_match and not tcp_rpy_match:
        fail('TCP world pose evidence is missing')
    if tcp_match:
        tcp_pose = [float(value) for value in tcp_match.groups()]
    else:
        tcp_rpy = [float(value) for value in tcp_rpy_match]
        tcp_pose = tcp_rpy[:3] + quaternion_from_rpy(*tcp_rpy[3:])
    if not all(math.isfinite(value) for value in tcp_pose):
        fail('TCP world transform contains a non-finite value')
    snapshot['tcp_pose'] = tcp_pose
output_path.write_text(
    json.dumps(snapshot, indent=2, sort_keys=True) + '\n',
    encoding='utf-8',
)
print(f'PASS: captured independent resume snapshot: {output_path}')
