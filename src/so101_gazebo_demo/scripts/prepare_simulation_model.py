#!/usr/bin/env python3
"""Convert the SO-101 Xacro to SDF and mark offline VHACD pieces convex."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET


DEFAULT_MAX_CONVEX_HULLS = 64
DEFAULT_VOXEL_RESOLUTION = 400000


def enable_jaw_convex_decomposition(
    sdf_text, *, max_convex_hulls, voxel_resolution
):
    """Return SDF text whose offline jaw pieces request convex-hull loading."""
    if max_convex_hulls <= 0 or voxel_resolution <= 0:
        raise ValueError('VHACD parameters must be positive')

    root = ET.fromstring(sdf_text)
    jaw_meshes = root.findall(
        "./model/link[@name='jaw']/collision/geometry/mesh"
    )
    jaw_collisions = root.findall("./model/link[@name='jaw']/collision")
    if len(jaw_meshes) != 64 or len(jaw_collisions) != 64:
        raise ValueError(
            'expected 64 offline jaw convex collision meshes, '
            f'found {len(jaw_meshes)} meshes in {len(jaw_collisions)} collisions'
        )

    for collision, mesh in zip(jaw_collisions, jaw_meshes):
        if 'moving_jaw_convex_' not in collision.attrib.get('name', ''):
            raise ValueError('jaw collision is not an offline VHACD piece')
        mesh.set('optimization', 'convex_hull')
        for existing in mesh.findall('convex_decomposition'):
            mesh.remove(existing)
    return ET.tostring(root, encoding='unicode')


def prepare_simulation_model(
    xacro_path,
    output_path,
    *,
    base_height,
    max_convex_hulls,
    voxel_resolution,
):
    """Generate URDF, convert it to SDF 1.11, inject VHACD, and write atomically."""
    xacro_result = subprocess.run(
        [
            'xacro',
            str(xacro_path),
            f'base_height:={base_height}',
            'gazebo_collision_primitives:=true',
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    temporary_urdf = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.urdf', encoding='utf-8', delete=False
        ) as stream:
            stream.write(xacro_result.stdout)
            temporary_urdf = Path(stream.name)

        sdf_result = subprocess.run(
            ['gz', 'sdf', '-p', str(temporary_urdf)],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        if temporary_urdf is not None:
            temporary_urdf.unlink(missing_ok=True)

    prepared = enable_jaw_convex_decomposition(
        sdf_result.stdout,
        max_convex_hulls=max_convex_hulls,
        voxel_resolution=voxel_resolution,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.sdf.tmp',
        dir=output.parent,
        encoding='utf-8',
        delete=False,
    ) as stream:
        stream.write('<?xml version="1.0"?>\n')
        stream.write(prepared)
        stream.write('\n')
        temporary_output = Path(stream.name)
    os.replace(temporary_output, output)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--xacro', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--base-height', required=True)
    parser.add_argument(
        '--max-convex-hulls',
        type=int,
        default=DEFAULT_MAX_CONVEX_HULLS,
    )
    parser.add_argument(
        '--voxel-resolution',
        type=int,
        default=DEFAULT_VOXEL_RESOLUTION,
    )
    return parser.parse_args()


def main():
    args = parse_args()
    prepare_simulation_model(
        args.xacro,
        args.output,
        base_height=args.base_height,
        max_convex_hulls=args.max_convex_hulls,
        voxel_resolution=args.voxel_resolution,
    )


if __name__ == '__main__':
    main()
