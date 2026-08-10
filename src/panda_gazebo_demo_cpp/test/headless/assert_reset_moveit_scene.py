#!/usr/bin/env python3
"""Validate complete MoveIt reset evidence captured after world reset."""

import math
import pathlib
import re
import sys


def fail(message: str) -> None:
    print(f'FAIL: {message}', file=sys.stderr)
    raise SystemExit(1)


def orientation_distance(quaternion: tuple[float, ...]) -> float:
    norm = math.sqrt(sum(value * value for value in quaternion))
    if not math.isfinite(norm) or norm <= 1.0e-12:
        return math.inf
    dot = abs(quaternion[3]) / norm
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


if len(sys.argv) != 2:
    fail('expected PLANNING_SCENE')

scene_text = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')
if 'attached_collision_objects=[]' not in scene_text:
    fail('MoveIt reset evidence contains an attached collision object')

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
    fail('MoveIt reset evidence does not contain world Coke')
if 'table' not in moveit_objects:
    fail('MoveIt reset evidence does not contain world table')

position, orientation = moveit_objects['coke']
if not all(math.isfinite(value) for value in position + orientation):
    fail('MoveIt reset Coke pose is non-finite')
if math.dist(position, (0.3, 0.0, 0.836)) > 0.002:
    fail(f'MoveIt reset Coke position is outside tolerance: {position}')
if orientation_distance(orientation) > 0.02:
    fail('MoveIt reset Coke orientation is outside tolerance')

table_position, table_orientation = moveit_objects['table']
if not all(math.isfinite(value) for value in table_position + table_orientation):
    fail('MoveIt reset table pose is non-finite')
if math.dist(table_position, (0.0, 0.0, 0.75)) > 0.002:
    fail(f'MoveIt reset table position is outside tolerance: {table_position}')
if orientation_distance(table_orientation) > 0.02:
    fail('MoveIt reset table orientation is outside tolerance')

print('PASS: MoveIt reset table and detached Coke are at canonical 6D poses')
