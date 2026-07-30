#!/usr/bin/env python3
"""Convert the SO-101 Xacro to SDF and mark offline VHACD pieces convex."""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from ament_index_python.packages import get_package_share_directory


SCHEMA_VERSION = 1
MAX_TOTAL_PIECES = 24
_COLLISION_SUFFIX = re.compile(r'_collision(?:_\d+)?$')
_PREPARATION_SCHEMA_VERSION = 3
_NATIVE_PAD_COLLISION = re.compile(
    r'(?:^|__)(fixed|moving)_fingertip_pad_collision_(\d{3})'
    r'_collision(?:_\d+)?$'
)
_NATIVE_PAD_COUNTS = {'fixed': 7, 'moving': 6}


def load_manifest(path, *, collision_root=None):
    """Load a collision manifest and validate its structure and piece hashes."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f'manifest not found: {path}')
    with open(path, 'r', encoding='utf-8') as stream:
        manifest = json.load(stream)
    if manifest.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported manifest schema version {manifest.get('schema_version')}, "
            f"expected {SCHEMA_VERSION}"
        )
    if 'prefix' not in manifest or 'pieces' not in manifest:
        raise ValueError(f'manifest missing required fields: {path}')
    piece_root = Path(collision_root) if collision_root is not None else path.parent
    for piece in manifest['pieces']:
        piece_path = piece_root / piece['filename']
        if not piece_path.exists():
            raise FileNotFoundError(
                f"manifest piece not found: {piece_path}"
            )
        actual_sha = hashlib.sha256(piece_path.read_bytes()).hexdigest()
        if actual_sha != piece['sha256']:
            raise ValueError(
                f"sha256 mismatch for {piece['filename']}: "
                f"expected {piece['sha256']}, got {actual_sha}"
            )
    return manifest


def enable_fingertip_convex_hulls(sdf_text, manifests):
    """Mark every known convex fingertip collision mesh as a convex hull."""
    root = ET.fromstring(sdf_text)
    all_pieces = []
    for manifest in manifests:
        for piece in manifest['pieces']:
            all_pieces.append(piece['filename'].replace('.stl', ''))
    if len(all_pieces) > MAX_TOTAL_PIECES:
        raise ValueError(
            f'total piece count {len(all_pieces)} exceeds {MAX_TOTAL_PIECES}'
        )
    seen = set()
    for name in all_pieces:
        if name in seen:
            raise ValueError(f'duplicate collision name: {name}')
        seen.add(name)

    def _collision_matches_piece(collision_name, piece):
        if collision_name == piece:
            return True
        stripped = _COLLISION_SUFFIX.sub('_collision', collision_name)
        if stripped.endswith(f'__{piece}_collision'):
            return True
        return False

    collisions_by_piece = {}
    for collision in root.iter('collision'):
        collision_name = collision.attrib.get('name', '')
        for piece in seen:
            if _collision_matches_piece(collision_name, piece):
                if piece in collisions_by_piece:
                    raise ValueError(
                        f'duplicate collision in SDF for piece {piece}: '
                        f'{collision_name} vs '
                        f'{collisions_by_piece[piece].attrib.get("name")}'
                    )
                collisions_by_piece[piece] = collision
    missing = seen - set(collisions_by_piece.keys())
    if missing:
        raise ValueError(
            f'manifest pieces not found in SDF: {sorted(missing)}'
        )
    for name, collision in collisions_by_piece.items():
        mesh = collision.find('geometry/mesh')
        if mesh is None:
            raise ValueError(f'collision for piece {name} has no mesh geometry')
        mesh.set('optimization', 'convex_hull')
        for existing in mesh.findall('convex_decomposition'):
            mesh.remove(existing)

    native_pads = {side: {} for side in _NATIVE_PAD_COUNTS}
    for collision in root.iter('collision'):
        collision_name = collision.attrib.get('name', '')
        match = _NATIVE_PAD_COLLISION.search(collision_name)
        if match is None:
            continue
        side, index_text = match.groups()
        index = int(index_text)
        if index in native_pads[side]:
            raise ValueError(
                f'duplicate native {side} fingertip pad collision index '
                f'{index_text}'
            )
        native_pads[side][index] = collision

    if any(native_pads.values()):
        for side, expected_count in _NATIVE_PAD_COUNTS.items():
            expected = set(range(expected_count))
            actual = set(native_pads[side])
            if actual != expected:
                raise ValueError(
                    f'native {side} fingertip pad collision indices are '
                    f'{sorted(actual)}, expected {sorted(expected)}'
                )
            for index, collision in native_pads[side].items():
                mesh = collision.find('geometry/mesh')
                if mesh is None:
                    raise ValueError(
                        f'native {side} fingertip pad collision {index:03d} '
                        'has no mesh geometry'
                    )
                mesh.set('optimization', 'convex_hull')
                for existing in mesh.findall('convex_decomposition'):
                    mesh.remove(existing)
    return ET.tostring(root, encoding='unicode')


def model_cache_key(
    *, xacro_bytes, manifests_bytes, base_height, collision_mode,
    dependency_records=(), expanded_urdf_bytes=b'',
):
    """Compute a deterministic digest cache key for a prepared SDF."""
    hasher = hashlib.sha256()
    hasher.update(f'schema={_PREPARATION_SCHEMA_VERSION}\n'.encode())
    hasher.update(b'xacro:')
    hasher.update(hashlib.sha256(xacro_bytes).digest())
    for index, manifest_bytes in enumerate(manifests_bytes):
        hasher.update(f'manifest{index}:'.encode())
        hasher.update(hashlib.sha256(manifest_bytes).digest())
    for record in sorted(dependency_records, key=lambda item: item['path']):
        hasher.update(b'dependency:')
        hasher.update(record['path'].encode())
        hasher.update(b':')
        hasher.update(record['sha256'].encode())
        hasher.update(b'\n')
    hasher.update(b'expanded_urdf:')
    hasher.update(hashlib.sha256(expanded_urdf_bytes).digest())
    hasher.update(f'base_height:{base_height}\n'.encode())
    hasher.update(f'collision_mode:{collision_mode}\n'.encode())
    return hasher.hexdigest()


def _cache_root():
    xdg = os.environ.get('XDG_CACHE_HOME')
    if xdg:
        return Path(xdg) / 'so101_gazebo_demo' / 'prepared_sdf'
    return Path.home() / '.cache' / 'so101_gazebo_demo' / 'prepared_sdf'


def _cached_sdf(cache_key):
    cache_dir = _cache_root()
    entry = cache_dir / cache_key / 'prepared.sdf'
    if entry.exists():
        return entry.read_text(encoding='utf-8')
    return None


def _write_cache(cache_key, sdf_text, dependency_records):
    cache_dir = _cache_root() / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.sdf.tmp', dir=cache_dir,
        encoding='utf-8', delete=False,
    ) as stream:
        stream.write(sdf_text)
        stream.write('\n')
        temporary = Path(stream.name)
    target = cache_dir / 'prepared.sdf'
    os.replace(temporary, target)
    metadata = {
        'schema_version': _PREPARATION_SCHEMA_VERSION,
        'cache_key': cache_key,
        'dependencies': sorted(dependency_records, key=lambda item: item['path']),
    }
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.json.tmp', dir=cache_dir,
        encoding='utf-8', delete=False,
    ) as stream:
        json.dump(metadata, stream, indent=2, sort_keys=True)
        stream.write('\n')
        temporary_metadata = Path(stream.name)
    os.replace(temporary_metadata, cache_dir / 'dependencies.json')


def _dependency_record(path):
    """Return the auditable identity and digest of one local dependency."""
    resolved = Path(path).resolve(strict=True)
    return {
        'path': str(resolved),
        'sha256': hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


def _mesh_dependency_paths(expanded_urdf, xacro_path):
    """Resolve local mesh files referenced by the expanded robot model."""
    package_root = Path(__file__).resolve().parents[1]
    result = set()
    root = ET.fromstring(expanded_urdf)
    for mesh in root.iter('mesh'):
        uri = mesh.attrib.get('filename') or mesh.attrib.get('url')
        if not uri:
            continue
        if uri.startswith('package://so101_gazebo_demo/'):
            relative = uri.removeprefix('package://so101_gazebo_demo/')
            path = package_root / relative
            if not path.exists():
                path = Path(get_package_share_directory('so101_gazebo_demo')) / relative
        elif uri.startswith('file://'):
            path = Path(uri.removeprefix('file://'))
        elif '://' not in uri:
            path = Path(uri)
            if not path.is_absolute():
                path = xacro_path.parent / path
        else:
            raise ValueError(f'cannot hash unsupported mesh URI: {uri}')
        result.add(path.resolve(strict=True))
    return result


def _model_dependencies(
    xacro_path, xacro_args, expanded_urdf, manifest_paths, manifests,
    object_config,
):
    """Collect a deterministic content snapshot of every model input file."""
    deps_result = subprocess.run(
        [xacro_args[0], '--deps', *xacro_args[1:]],
        check=True, capture_output=True, text=True,
    )
    paths = {xacro_path.resolve(strict=True)}
    paths.update(Path(token).resolve(strict=True) for token in shlex.split(
        deps_result.stdout
    ))
    if object_config:
        paths.add(Path(object_config).resolve(strict=True))
    for manifest_path, manifest in zip(manifest_paths, manifests, strict=True):
        manifest_path = Path(manifest_path).resolve(strict=True)
        paths.add(manifest_path)
        paths.update(
            (manifest_path.parent / piece['filename']).resolve(strict=True)
            for piece in manifest['pieces']
        )
    paths.update(_mesh_dependency_paths(expanded_urdf, xacro_path))
    return [_dependency_record(path) for path in paths]


def prepare_simulation_model(
    xacro_path,
    output_path,
    *,
    base_height,
    manifest_paths,
    object_config=None,
):
    """Generate URDF, convert to SDF, inject convex hulls, and write atomically."""
    xacro_path = Path(xacro_path)
    manifests = [load_manifest(p) for p in manifest_paths]
    manifest_bytes = [Path(p).read_bytes() for p in manifest_paths]
    xacro_bytes = xacro_path.read_bytes()
    collision_mode = 'primitives'
    xacro_args = [
        'xacro', str(xacro_path),
        f'base_height:={base_height}',
        f'gazebo_collision_{collision_mode}:=true',
    ]
    if object_config:
        xacro_args.extend([f'object_config:={object_config}'])
    xacro_result = subprocess.run(
        xacro_args, check=True, capture_output=True, text=True,
    )
    dependencies = _model_dependencies(
        xacro_path, xacro_args, xacro_result.stdout, manifest_paths, manifests,
        object_config,
    )
    cache_key = model_cache_key(
        xacro_bytes=xacro_bytes,
        manifests_bytes=manifest_bytes,
        base_height=base_height,
        collision_mode=collision_mode,
        dependency_records=dependencies,
        expanded_urdf_bytes=xacro_result.stdout.encode(),
    )
    cached = _cached_sdf(cache_key)
    if cached is not None:
        prepared = cached
    else:
        temporary_urdf = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.urdf', encoding='utf-8', delete=False,
            ) as stream:
                stream.write(xacro_result.stdout)
                temporary_urdf = Path(stream.name)
            sdf_result = subprocess.run(
                ['gz', 'sdf', '-p', str(temporary_urdf)],
                check=True, capture_output=True, text=True,
            )
        finally:
            if temporary_urdf is not None:
                temporary_urdf.unlink(missing_ok=True)
        prepared = enable_fingertip_convex_hulls(sdf_result.stdout, manifests)
        _write_cache(cache_key, prepared, dependencies)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.sdf.tmp', dir=output.parent,
        encoding='utf-8', delete=False,
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
    parser.add_argument('--manifest', action='append', required=True, type=Path)
    parser.add_argument('--object-config', type=Path, default=None)
    return parser.parse_args()


def main():
    args = parse_args()
    prepare_simulation_model(
        args.xacro,
        args.output,
        base_height=args.base_height,
        manifest_paths=args.manifest,
        object_config=args.object_config,
    )


if __name__ == '__main__':
    main()
