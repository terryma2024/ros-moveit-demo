#!/usr/bin/env python3
"""Deterministically build the native-only SO-101 fingertip pad meshes.

The source profiles are measured in the original STL coordinate frames.  The
robot description applies the original finger visual transforms to both the
STL and these meshes, so this generator never alters the visual meshes or the
cached finger VHACD assets.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct
from typing import Iterable

import yaml


def _normal(a, b, c):
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    length = sum(component * component for component in cross) ** 0.5
    if length == 0.0:
        raise ValueError('fingertip-pad mesh contains a degenerate triangle')
    return tuple(component / length for component in cross)


def _triangles_for_segment(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    *,
    axial_axis: str,
    contact_direction_x: float,
    thickness: float,
):
    """Return a closed convex frustum between consecutive measured sections."""
    start_axis, start_half_width, start_substrate = start
    end_axis, end_half_width, end_substrate = end
    if not start_axis < end_axis or start_half_width <= 0.0 or end_half_width <= 0.0:
        raise ValueError('fingertip-pad profile points must be ordered with positive half-width')
    if contact_direction_x not in (-1.0, 1.0) or thickness <= 0.0:
        raise ValueError('fingertip-pad contact direction and thickness are invalid')

    def section(axis, half_width, substrate):
        contact_x = substrate + contact_direction_x * thickness
        if axial_axis == 'y':
            return (
                (substrate, axis, -half_width),
                (substrate, axis, half_width),
                (contact_x, axis, half_width),
                (contact_x, axis, -half_width),
            )
        if axial_axis == 'z':
            return (
                (substrate, -half_width, axis),
                (substrate, half_width, axis),
                (contact_x, half_width, axis),
                (contact_x, -half_width, axis),
            )
        raise ValueError('fingertip-pad axial axis must be y or z')

    vertices = section(*start) + section(*end)
    quads = (
        (0, 1, 2, 3), (4, 7, 6, 5),
        (0, 4, 5, 1), (1, 5, 6, 2),
        (2, 6, 7, 3), (3, 7, 4, 0),
    )
    triangles = []
    for first, second, third, fourth in quads:
        triangles.append((vertices[first], vertices[second], vertices[third]))
        triangles.append((vertices[first], vertices[third], vertices[fourth]))
    return triangles


def _write_binary_stl(path: Path, triangles: Iterable[tuple]):
    records = list(triangles)
    header = b'SO101 native fingertip pad'.ljust(80, b' ')
    payload = bytearray(header + struct.pack('<I', len(records)))
    for triangle in records:
        payload.extend(struct.pack('<3f', *_normal(*triangle)))
        for vertex in triangle:
            payload.extend(struct.pack('<3f', *vertex))
        payload.extend(struct.pack('<H', 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generate_pad(name: str, pad: dict, root: Path):
    required = {
        'opening_axis_thickness_m', 'contact_direction_x', 'axial_axis',
        'native_axial_bounds_m', 'profile_points',
    }
    if set(pad) != required:
        raise ValueError(f'{name}_pad has an unexpected geometry schema')
    thickness = float(pad['opening_axis_thickness_m'])
    direction = float(pad['contact_direction_x'])
    axis = str(pad['axial_axis'])
    points = tuple(tuple(float(value) for value in point) for point in pad['profile_points'])
    if len(points) < 2 or any(len(point) != 3 for point in points):
        raise ValueError(f'{name}_pad requires at least two three-value profile points')
    native = tuple(float(value) for value in pad['native_axial_bounds_m'])
    if len(native) != 2 or not native[0] < points[0][0] < points[-1][0] < native[1]:
        raise ValueError(f'{name}_pad exceeds the native fingertip axial envelope')

    output = root / name
    all_triangles = []
    collision_meshes = []
    for index, (start, end) in enumerate(zip(points, points[1:])):
        triangles = _triangles_for_segment(
            start, end, axial_axis=axis, contact_direction_x=direction, thickness=thickness
        )
        filename = f'fingertip_pad_collision_{index:03d}.stl'
        _write_binary_stl(output / filename, triangles)
        collision_meshes.append(filename)
        all_triangles.extend(triangles)
    visual_name = 'fingertip_pad.stl'
    _write_binary_stl(output / visual_name, all_triangles)
    manifest = {
        'schema_version': 1,
        'logical_pad_count': 1,
        'mounting_stem_count': 0,
        'opening_axis_thickness_m': thickness,
        'contact_direction_x': direction,
        'axial_axis': axis,
        'native_axial_bounds_m': list(native),
        'axial_bounds_m': [points[0][0], points[-1][0]],
        'profile_points': [list(point) for point in points],
        'profile_fingerprint': hashlib.sha256(
            yaml.safe_dump(pad, sort_keys=True).encode('utf-8')
        ).hexdigest(),
        'visual_mesh': visual_name,
        'visual_mesh_sha256': _sha256(output / visual_name),
        'collision_meshes': collision_meshes,
        'collision_mesh_sha256': [_sha256(output / mesh) for mesh in collision_meshes],
    }
    (output / 'manifest.yaml').write_text(
        yaml.safe_dump(manifest, sort_keys=True), encoding='utf-8'
    )


def generate(config_path: Path, output_root: Path):
    policy = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    pads = policy.get('fingertip_pads')
    if not isinstance(pads, dict) or pads.get('enabled') is not True:
        raise ValueError('object config must enable fingertip_pads')
    if pads.get('contact_model') != 'rigid_link_local_mesh':
        raise ValueError('fingertip pads must use deterministic link-local meshes')
    _generate_pad('fixed', pads['fixed_pad'], output_root)
    _generate_pad('moving', pads['moving_pad'], output_root)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    generate(args.config, args.output_root)


if __name__ == '__main__':
    main()
