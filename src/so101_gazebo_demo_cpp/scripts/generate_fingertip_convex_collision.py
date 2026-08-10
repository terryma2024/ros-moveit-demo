#!/usr/bin/env python3
"""Generate reproducible offline VHACD pieces for a fingertip mesh ROI."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import NamedTuple

import numpy as np
import trimesh


class Roi(NamedTuple):
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def extract_roi(mesh: trimesh.Trimesh, roi: Roi) -> trimesh.Trimesh:
    """Clip the mesh to the requested axis-aligned fingertip ROI."""
    minimum = np.asarray(roi.minimum, dtype=float)
    maximum = np.asarray(roi.maximum, dtype=float)
    if minimum.shape != (3,) or maximum.shape != (3,) or np.any(minimum >= maximum):
        raise ValueError('fingertip ROI bounds are invalid')
    if np.any(mesh.bounds[1] < minimum) or np.any(mesh.bounds[0] > maximum):
        raise ValueError('fingertip ROI is empty')
    extracted = mesh.copy()
    for axis in range(3):
        normal = np.zeros(3)
        normal[axis] = 1.0
        origin = np.zeros(3)
        origin[axis] = minimum[axis]
        vertices, faces, _ = trimesh.intersections.slice_faces_plane(
            extracted.vertices, extracted.faces, normal, origin
        )
        extracted = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        origin[axis] = maximum[axis]
        vertices, faces, _ = trimesh.intersections.slice_faces_plane(
            extracted.vertices, extracted.faces, -normal, origin
        )
        extracted = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    extracted.remove_unreferenced_vertices()
    extracted.fix_normals()
    if len(extracted.faces) == 0:
        raise ValueError('fingertip ROI is empty')
    return extracted


def decompose_mesh(
    mesh: trimesh.Trimesh, *, max_convex_hulls: int, voxel_resolution: int
) -> list[trimesh.Trimesh]:
    try:
        pieces = mesh.convex_decomposition(
            maxConvexHulls=max_convex_hulls,
            resolution=voxel_resolution,
            minimumVolumePercentErrorAllowed=0.05,
            maxRecursionDepth=15,
            maxNumVerticesPerCH=64,
            shrinkWrap=True,
        )
    except ModuleNotFoundError as error:
        raise RuntimeError(
            'offline VHACD generation requires vhacdx in an isolated build '
            'environment; install vhacdx with numpy<2'
        ) from error
    if isinstance(pieces, trimesh.Trimesh):
        return [pieces]
    return list(pieces)


def filter_small_pieces(
    pieces: list[trimesh.Trimesh], *, minimum_piece_volume_ratio: float
) -> list[trimesh.Trimesh]:
    if not 0.0 <= minimum_piece_volume_ratio < 1.0:
        raise ValueError('minimum piece volume ratio must be in [0, 1)')
    if not pieces:
        return []
    volumes = [float(abs(piece.volume)) for piece in pieces]
    threshold = max(volumes) * minimum_piece_volume_ratio
    return [piece for piece, volume in zip(pieces, volumes) if volume >= threshold]


def audit_convex_hull_outward_protrusion(
    source: trimesh.Trimesh,
    collision: trimesh.Trimesh,
    *,
    samples_per_edge: int = 32,
) -> dict:
    """Measure outward hull error using deterministic triangle-interior samples.

    Convex-hull vertices can all lie on the source while a hull face bridges a
    concavity.  This audit therefore samples a regular barycentric lattice on
    every collision face and signs the closest-point distance with the source
    face's outward normal.  A consistently wound source is required; it also
    makes the method usable for a non-watertight visual assembled from locally
    closed pieces without pretending that a global inside query is reliable.
    """
    if samples_per_edge < 2:
        raise ValueError('samples_per_edge must be at least two')
    if len(source.faces) == 0 or len(collision.faces) == 0:
        raise ValueError('source and collision meshes must be non-empty')
    if not source.is_winding_consistent:
        raise ValueError('source mesh must have consistent outward winding')

    points = []
    collision_faces = []
    for face_index, triangle in enumerate(collision.triangles):
        for first in range(samples_per_edge + 1):
            for second in range(samples_per_edge + 1 - first):
                a = first / samples_per_edge
                b = second / samples_per_edge
                points.append(a * triangle[0] + b * triangle[1] + (1.0 - a - b) * triangle[2])
                collision_faces.append(face_index)
    samples = np.asarray(points, dtype=float)
    closest, distances, source_faces = trimesh.proximity.closest_point_naive(source, samples)
    offsets = samples - closest
    signed = np.einsum('ij,ij->i', offsets, source.face_normals[source_faces])
    outward = np.maximum(signed, 0.0)
    worst = int(np.argmax(outward))
    return {
        'samples_per_edge': samples_per_edge,
        'sample_count': int(len(samples)),
        'source_watertight': bool(source.is_watertight),
        'orientation_method': 'closest_source_face_outward_normal',
        'max_outward_protrusion_m': float(outward[worst]),
        'unsigned_closest_distance_m': float(distances[worst]),
        'collision_face_index': int(collision_faces[worst]),
        'source_face_index': int(source_faces[worst]),
        'worst_point': [float(value) for value in samples[worst]],
        'closest_source_point': [float(value) for value in closest[worst]],
        'closest_source_normal': [
            float(value) for value in source.face_normals[source_faces[worst]]
        ],
    }


def generate_collision_set(
    source: Path,
    output_dir: Path,
    *,
    prefix: str,
    roi: Roi,
    max_convex_hulls: int,
    voxel_resolution: int,
    minimum_piece_volume_ratio: float = 0.0,
) -> dict:
    if max_convex_hulls <= 0 or voxel_resolution <= 0:
        raise ValueError('VHACD parameters must be positive')
    if not prefix or any(character not in 'abcdefghijklmnopqrstuvwxyz_0123456789' for character in prefix):
        raise ValueError('collision prefix must use lowercase letters, digits, and underscores')
    mesh = trimesh.load_mesh(source, force='mesh', process=True)
    fingertip = extract_roi(mesh, roi)
    pieces = decompose_mesh(
        fingertip,
        max_convex_hulls=max_convex_hulls,
        voxel_resolution=voxel_resolution,
    )
    pieces = filter_small_pieces(
        pieces, minimum_piece_volume_ratio=minimum_piece_volume_ratio
    )
    if not pieces:
        raise RuntimeError('VHACD generated no convex pieces')
    if len(pieces) > max_convex_hulls:
        raise RuntimeError('VHACD exceeded the configured convex hull budget')
    pieces = sorted(
        pieces,
        key=lambda piece: (
            *(round(float(value), 12) for value in piece.bounding_box.centroid),
            round(float(abs(piece.volume)), 12),
        ),
    )

    temporary = output_dir.with_name(output_dir.name + '.tmp')
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    piece_records = []
    for index, piece in enumerate(pieces):
        if len(piece.faces) == 0 or not piece.is_convex:
            raise RuntimeError('VHACD emitted an empty or non-convex piece')
        filename = f'{prefix}_{index:03d}.stl'
        path = temporary / filename
        path.write_bytes(trimesh.exchange.stl.export_stl(piece))
        piece_records.append(
            {
                'filename': filename,
                'sha256': sha256(path),
                'triangle_count': int(len(piece.faces)),
                'bounds': [[float(value) for value in row] for row in piece.bounds],
            }
        )

    manifest = {
        'schema_version': 1,
        'prefix': prefix,
        'source_sha256': sha256(source),
        'roi_min': [float(value) for value in roi.minimum],
        'roi_max': [float(value) for value in roi.maximum],
        'max_convex_hulls': max_convex_hulls,
        'voxel_resolution': voxel_resolution,
        'minimum_piece_volume_ratio': minimum_piece_volume_ratio,
        'pieces': piece_records,
    }
    (temporary / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    temporary.rename(output_dir)
    return manifest


def parse_triplet(values: list[str]) -> tuple[float, float, float]:
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--roi-min', nargs=3, required=True)
    parser.add_argument('--roi-max', nargs=3, required=True)
    parser.add_argument('--max-convex-hulls', type=int, default=8)
    parser.add_argument('--voxel-resolution', type=int, default=400000)
    parser.add_argument('--minimum-piece-volume-ratio', type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = generate_collision_set(
        args.source,
        args.output_dir,
        prefix=args.prefix,
        roi=Roi(parse_triplet(args.roi_min), parse_triplet(args.roi_max)),
        max_convex_hulls=args.max_convex_hulls,
        voxel_resolution=args.voxel_resolution,
        minimum_piece_volume_ratio=args.minimum_piece_volume_ratio,
    )
    print(
        f"generated_pieces={len(manifest['pieces'])} output={args.output_dir} "
        f"manifest={args.output_dir / 'manifest.json'}"
    )


if __name__ == '__main__':
    main()
