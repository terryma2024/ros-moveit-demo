#!/usr/bin/env python3
"""Compute reproducible Gazebo camera poses and patch MinimalScene worlds.

The Gazebo camera convention places local +X forward, yaw turns in the
world XY plane, and negative pitch looks downward. Distances are derived
from the coverage AABB so callers never hand-tune camera coordinates.
"""

import argparse
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


NEAR_EPSILON_M = 0.01
PRESET_NAMES = ('left-front', 'right-front', 'left-rear', 'right-rear')
MINIMAL_SCENE_PLUGIN_RE = re.compile(
    r'<plugin\b[^>]*\bfilename="[^"]*MinimalScene[^"]*"[^>]*>.*?</plugin>',
    re.DOTALL,
)
CAMERA_POSE_RE = re.compile(r'<camera_pose>(.*?)</camera_pose>', re.DOTALL)


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __len__(self):
        return 3

    def __getitem__(self, index):
        return (self.x, self.y, self.z)[index]


@dataclass(frozen=True)
class Aabb:
    minimum: Vec3
    maximum: Vec3


@dataclass(frozen=True)
class CameraPreset:
    azimuth_rad: float
    elevation_rad: float


@dataclass(frozen=True)
class CameraPoseResult:
    distance_m: float
    position: Vec3
    rpy: Vec3
    camera_pose: str


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def camera_basis(azimuth_rad, elevation_rad):
    """Return the world-frame (forward, right, up) axes of the camera."""
    cos_elevation = math.cos(elevation_rad)
    forward = Vec3(
        cos_elevation * math.cos(azimuth_rad),
        cos_elevation * math.sin(azimuth_rad),
        -math.sin(elevation_rad),
    )
    right = Vec3(-math.sin(azimuth_rad), math.cos(azimuth_rad), 0.0)
    up = Vec3(
        math.sin(elevation_rad) * math.cos(azimuth_rad),
        math.sin(elevation_rad) * math.sin(azimuth_rad),
        cos_elevation,
    )
    return forward, right, up


def vertical_fov(horizontal_fov_rad, aspect_ratio):
    return 2 * math.atan(math.tan(horizontal_fov_rad / 2) / aspect_ratio)


def _validate_aabb(coverage):
    if any(high <= low for low, high in zip(coverage.minimum, coverage.maximum)):
        raise ValueError(
            f'coverage AABB is degenerate: {coverage.minimum}..{coverage.maximum}'
        )


def _validate_inputs(horizontal_fov_rad, viewport, margin):
    if not 0.0 < horizontal_fov_rad < math.pi:
        raise ValueError(
            f'horizontal_fov_rad must be in (0, pi), got {horizontal_fov_rad}'
        )
    if len(viewport) != 2 or any(value <= 0 for value in viewport):
        raise ValueError(f'viewport must be two positive numbers, got {viewport}')
    if not 0.0 < margin <= 1.0:
        raise ValueError(f'margin must be in (0, 1], got {margin}')


def _required_distance(corners, tan_half_hfov, tan_half_vfov, margin):
    distance = NEAR_EPSILON_M
    for forward, right, up in corners:
        candidates = (
            abs(right) / (tan_half_hfov * margin) - forward,
            abs(up) / (tan_half_vfov * margin) - forward,
            NEAR_EPSILON_M - forward,
        )
        distance = max(distance, *candidates)
    return distance


def ensure_camera_outside_coverage(position, coverage):
    """Guard against poses that would render from inside the coverage box."""
    if all(
        low <= value <= high
        for value, low, high in zip(position, coverage.minimum, coverage.maximum)
    ):
        raise RuntimeError(
            f'camera position {tuple(position)} lies inside coverage AABB '
            f'{tuple(coverage.minimum)}..{tuple(coverage.maximum)}'
        )


def _format_pose(values):
    return ' '.join(f'{value:.6f}' for value in values)


def calculate_camera_pose(focus, coverage, preset, horizontal_fov_rad,
                          viewport, margin):
    """Compute the nearest camera pose that frames the whole coverage AABB."""
    _validate_aabb(coverage)
    _validate_inputs(horizontal_fov_rad, viewport, margin)
    width, height = viewport
    vfov = vertical_fov(horizontal_fov_rad, width / height)
    forward, right, up = camera_basis(preset.azimuth_rad, preset.elevation_rad)
    corners = []
    for x in (coverage.minimum.x, coverage.maximum.x):
        for y in (coverage.minimum.y, coverage.maximum.y):
            for z in (coverage.minimum.z, coverage.maximum.z):
                relative = Vec3(x - focus.x, y - focus.y, z - focus.z)
                corners.append((
                    _dot(relative, forward),
                    _dot(relative, right),
                    _dot(relative, up),
                ))
    distance = _required_distance(
        corners,
        math.tan(horizontal_fov_rad / 2),
        math.tan(vfov / 2),
        margin,
    )
    position = Vec3(
        focus.x - forward.x * distance,
        focus.y - forward.y * distance,
        focus.z - forward.z * distance,
    )
    ensure_camera_outside_coverage(position, coverage)
    rpy = Vec3(0.0, -preset.elevation_rad, preset.azimuth_rad)
    return CameraPoseResult(
        distance_m=distance,
        position=position,
        rpy=rpy,
        camera_pose=_format_pose((*position, *rpy)),
    )


def _vec3(value, label):
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or not all(isinstance(item, (int, float)) for item in value)
    ):
        raise ValueError(f'{label} must be three numbers, got {value!r}')
    return Vec3(*(float(item) for item in value))


def _require(mapping, key, label):
    if not isinstance(mapping, dict) or key not in mapping:
        raise ValueError(f'{label} is missing required key {key!r}')
    return mapping[key]


def parse_config(mapping):
    """Validate a config mapping; never invent missing calibration angles."""
    focus = _vec3(_require(mapping, 'focus', 'config'), 'focus')
    aabb = _require(mapping, 'coverage_aabb', 'config')
    coverage = Aabb(
        _vec3(_require(aabb, 'min', 'coverage_aabb'), 'coverage_aabb.min'),
        _vec3(_require(aabb, 'max', 'coverage_aabb'), 'coverage_aabb.max'),
    )
    hfov = _require(mapping, 'horizontal_fov_rad', 'config')
    viewport = _require(mapping, 'viewport', 'config')
    margin = _require(mapping, 'margin', 'config')
    preset_mappings = _require(mapping, 'presets', 'config')
    presets = {}
    for name in PRESET_NAMES:
        entry = _require(preset_mappings, name, 'presets')
        presets[name] = CameraPreset(
            azimuth_rad=float(_require(entry, 'azimuth_rad', f'preset {name}')),
            elevation_rad=float(_require(entry, 'elevation_rad', f'preset {name}')),
        )
    _validate_aabb(coverage)
    _validate_inputs(hfov, viewport, margin)
    return focus, coverage, presets, hfov, tuple(viewport), margin


def load_config(path):
    """Read a YAML config when PyYAML exists, otherwise JSON only."""
    text = Path(path).read_text()
    try:
        import yaml
    except ImportError:
        yaml = None
    if yaml is not None:
        mapping = yaml.safe_load(text)
    else:
        try:
            mapping = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(
                'PyYAML is unavailable; only JSON config files are supported: '
                f'{error}'
            ) from error
    if not isinstance(mapping, dict):
        raise ValueError(f'config must be a mapping, got {type(mapping).__name__}')
    return mapping


def replace_camera_pose(world_path, new_pose):
    """Rewrite the unique MinimalScene camera_pose; leave all else untouched."""
    path = Path(world_path)
    text = path.read_text()
    matches = []
    for plugin in MINIMAL_SCENE_PLUGIN_RE.finditer(text):
        for pose in CAMERA_POSE_RE.finditer(plugin.group(0)):
            start = plugin.start() + pose.start(1)
            end = plugin.start() + pose.end(1)
            matches.append((start, end, pose.group(1)))
    if len(matches) != 1:
        raise RuntimeError(
            f'expected exactly one MinimalScene camera_pose in {path}, '
            f'found {len(matches)}'
        )
    start, end, old_pose = matches[0]
    updated = text[:start] + new_pose + text[end:]
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f'{path.name}.', suffix='.tmp'
    )
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(updated)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise
    return old_pose


def _result_payload(preset_name, result, focus, coverage, preset,
                    horizontal_fov_rad, viewport, margin):
    return {
        'preset': preset_name,
        'distance_m': result.distance_m,
        'position': list(result.position),
        'rpy': list(result.rpy),
        'camera_pose': result.camera_pose,
        'inputs': {
            'focus': list(focus),
            'coverage_aabb': {
                'min': list(coverage.minimum),
                'max': list(coverage.maximum),
            },
            'horizontal_fov_rad': horizontal_fov_rad,
            'viewport': list(viewport),
            'margin': margin,
            'azimuth_rad': preset.azimuth_rad,
            'elevation_rad': preset.elevation_rad,
        },
    }


def _compute(arguments):
    focus, coverage, presets, hfov, viewport, margin = parse_config(
        load_config(arguments.config)
    )
    if arguments.preset not in presets:
        raise ValueError(
            f"unknown preset {arguments.preset!r}; "
            f"expected one of {', '.join(PRESET_NAMES)}"
        )
    preset = presets[arguments.preset]
    result = calculate_camera_pose(focus, coverage, preset, hfov, viewport, margin)
    output = Path(arguments.json)
    if output.exists():
        raise RuntimeError(f'refusing to overwrite existing file: {output}')
    output.write_text(json.dumps(
        _result_payload(
            arguments.preset, result, focus, coverage, preset,
            hfov, viewport, margin,
        ),
        indent=2,
    ) + '\n')
    print(f'camera_pose={result.camera_pose}')
    print(f'json={output}')


def _apply(arguments):
    payload = json.loads(Path(arguments.pose_json).read_text())
    new_pose = payload['camera_pose']
    old_pose = replace_camera_pose(arguments.world, new_pose)
    print(f'old_camera_pose={old_pose}')
    print(f'new_camera_pose={new_pose}')
    print(f'world={arguments.world}')


def _build_parser():
    parser = argparse.ArgumentParser(
        description='Compute Gazebo camera poses or patch a MinimalScene world.'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    compute = subparsers.add_parser(
        'compute', help='calculate a camera pose from a config file'
    )
    compute.add_argument('--config', required=True, help='YAML/JSON config path')
    compute.add_argument('--preset', required=True, help='semantic preset name')
    compute.add_argument('--json', required=True, help='output JSON path')
    compute.set_defaults(handler=_compute)
    apply_parser = subparsers.add_parser(
        'apply', help='write a computed pose into a world SDF'
    )
    apply_parser.add_argument('--world', required=True, help='world SDF path')
    apply_parser.add_argument(
        '--pose-json', required=True, help='JSON produced by compute'
    )
    apply_parser.set_defaults(handler=_apply)
    return parser


def main(argv=None):
    arguments = _build_parser().parse_args(argv)
    try:
        arguments.handler(arguments)
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
