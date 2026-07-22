#!/usr/bin/env python3
"""Convert a real forward boundary and observed fault fixture to recovery v3."""

import json
import math
from pathlib import Path
import sys


def fail(message: str) -> None:
    print(f'FAIL: {message}', file=sys.stderr)
    raise SystemExit(1)


def pose(value: list[float]) -> dict[str, float]:
    if len(value) != 7 or not all(math.isfinite(item) for item in value):
        fail('recovery fixture contains an invalid 6DoF pose')
    x, y, z, qx, qy, qz, qw = value
    return {
        'x': x,
        'y': y,
        'z': z,
        'qx': qx,
        'qy': qy,
        'qz': qz,
        'qw': qw,
    }


if len(sys.argv) != 4:
    fail('expected CHECKPOINT SNAPSHOT FAILED_STATE')

checkpoint_path = Path(sys.argv[1])
snapshot_path = Path(sys.argv[2])
checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8'))
snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
if checkpoint.get('schema_version') != 3:
    fail('only checkpoint schema v3 can seed recovery')
if checkpoint.get('phase') != 'FORWARD':
    fail('recovery fixture must start from a forward checkpoint')
if not isinstance(snapshot.get('tcp_pose'), list):
    fail('recovery fixture requires an independently captured TCP pose')

joint_positions = snapshot.get('joint_positions')
joint_velocities = snapshot.get('joint_velocities')
if not isinstance(joint_positions, dict) or not joint_positions:
    fail('recovery fixture requires joint positions')
if not isinstance(joint_velocities, dict) or not joint_velocities:
    fail('recovery fixture requires joint velocities')
if joint_positions.keys() != joint_velocities.keys():
    fail('recovery fixture joint position/velocity names differ')
if any(abs(value) > 0.01 for value in joint_velocities.values()):
    fail('recovery fixture robot is not stationary')

expected = checkpoint.setdefault('expected', {})
moveit_world_poses = expected.setdefault('moveit_world_object_poses', {})
moveit_attached = bool(snapshot.get('moveit_coke_attached'))
if moveit_attached:
    moveit_world_poses.pop('coke', None)
else:
    moveit_world_poses['coke'] = pose(snapshot['moveit_coke_pose'])
expected.update({
    'tcp_pose_world': pose(snapshot['tcp_pose']),
    'joint_positions': joint_positions,
    'gripper_open': all(
        joint_positions.get(name, -math.inf) >= 0.038
        for name in ('panda_finger_joint1', 'panda_finger_joint2')
    ),
    'gazebo_coke_pose_world': pose(snapshot['gazebo_coke_pose']),
    'gazebo_coke_attached': bool(snapshot.get('gazebo_attached')),
    'gazebo_coke_stationary': True,
    'moveit_coke_attached': moveit_attached,
    'required_world_objects': sorted(moveit_world_poses),
})
checkpoint.update({
    'phase': 'RECOVERY',
    'failed_state': sys.argv[3],
    # Deliberately wrong. RecoveryPolicy must classify the live facts instead.
    'next_state': 'RECOVER_RETREAT',
    'original_failure': {
        'category': 4,
        'code': 'HEADLESS_RECOVERY_TRIGGER',
        'message': 'Recovery seeded from observed low carrying fault fixture',
        'metrics': {},
    },
})
temporary = checkpoint_path.with_suffix(checkpoint_path.suffix + '.tmp')
temporary.write_text(
    json.dumps(checkpoint, indent=2, sort_keys=True) + '\n', encoding='utf-8'
)
temporary.replace(checkpoint_path)
print(f'PASS: seeded observed schema-v3 recovery checkpoint: {checkpoint_path}')
