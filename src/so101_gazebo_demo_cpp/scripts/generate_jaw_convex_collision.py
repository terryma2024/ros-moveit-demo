#!/usr/bin/env python3
"""Generate reproducible VHACD collision pieces for the SO-101 moving jaw."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

import trimesh


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--max-convex-hulls', type=int, default=64)
    parser.add_argument('--voxel-resolution', type=int, default=400000)
    args = parser.parse_args()

    mesh = trimesh.load_mesh(args.source, force='mesh', process=False)
    pieces = mesh.convex_decomposition(
        maxConvexHulls=args.max_convex_hulls,
        resolution=args.voxel_resolution,
        minimumVolumePercentErrorAllowed=0.05,
        maxRecursionDepth=15,
        maxNumVerticesPerCH=64,
        shrinkWrap=True,
    )
    if not pieces:
        raise RuntimeError('VHACD generated no convex pieces')

    temporary = args.output_dir.with_name(args.output_dir.name + '.tmp')
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    for index, piece in enumerate(pieces):
        piece.export(temporary / f'moving_jaw_convex_{index:03d}.stl')
    if args.output_dir.exists():
        shutil.rmtree(args.output_dir)
    temporary.rename(args.output_dir)
    print(f'generated_pieces={len(pieces)} output={args.output_dir}')


if __name__ == '__main__':
    main()
