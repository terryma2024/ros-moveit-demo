import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'gazebo_camera_pose.py'
)
SPEC = importlib.util.spec_from_file_location('gazebo_camera_pose', SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

Vec3 = MODULE.Vec3
Aabb = MODULE.Aabb
CameraPreset = MODULE.CameraPreset
calculate_camera_pose = MODULE.calculate_camera_pose
camera_basis = MODULE.camera_basis
vertical_fov = MODULE.vertical_fov
ensure_camera_outside_coverage = MODULE.ensure_camera_outside_coverage
parse_config = MODULE.parse_config
replace_camera_pose = MODULE.replace_camera_pose

ORIGINAL_POSE = '0.4281 0.2175 0.4608 0 0.4 -2.3'
SDF_FIXTURE = f'''<?xml version="1.0"?>
<sdf version="1.10">
  <world name="so101_pick_place">
    <plugin filename="gz-sim-physics-system"
            name="gz::sim::systems::Physics"/>
    <gui fullscreen="0">
      <plugin filename="MinimalScene" name="3D View">
        <gz-gui>
          <title>3D View</title>
        </gz-gui>
        <engine>ogre2</engine>
        <scene>scene</scene>
        <camera_pose>{ORIGINAL_POSE}</camera_pose>
      </plugin>
      <plugin filename="GzSceneManager" name="Scene Manager"/>
    </gui>
    <model name="depth_camera">
      <link name="link">
        <sensor name="camera" type="camera">
          <pose>0 0 1 0 0 0</pose>
        </sensor>
      </link>
    </model>
  </world>
</sdf>
'''

UNIT_BOX = Aabb(Vec3(-1, -1, -1), Vec3(1, 1, 1))
PRESET_NAMES = ('left-front', 'right-front', 'left-rear', 'right-rear')


def config_mapping():
    return {
        'focus': [0.1, 0.2, 0.3],
        'coverage_aabb': {'min': [-0.5, -0.5, 0.0], 'max': [0.5, 0.5, 0.6]},
        'horizontal_fov_rad': 1.0,
        'viewport': [1280, 720],
        'margin': 0.9,
        'presets': {
            'left-front': {'azimuth_rad': 0.6, 'elevation_rad': 0.5},
            'right-front': {'azimuth_rad': -0.6, 'elevation_rad': 0.5},
            'left-rear': {'azimuth_rad': 2.4, 'elevation_rad': 0.5},
            'right-rear': {'azimuth_rad': -2.4, 'elevation_rad': 0.5},
        },
    }


def test_axis_aligned_view_fits_unit_aabb_at_distance_two():
    preset = CameraPreset(azimuth_rad=0.0, elevation_rad=0.0)
    box = Aabb(Vec3(-1, -1, -1), Vec3(1, 1, 1))
    result = calculate_camera_pose(
        focus=Vec3(0, 0, 0),
        coverage=box,
        preset=preset,
        horizontal_fov_rad=math.pi / 2,
        viewport=(1000, 1000),
        margin=1.0,
    )
    assert result.distance_m == pytest.approx(2.0)
    assert result.position == pytest.approx((-2.0, 0.0, 0.0))
    assert result.rpy == pytest.approx((0.0, 0.0, 0.0))


def test_apply_changes_only_unique_minimal_scene_camera_pose(tmp_path):
    world = tmp_path / 'world.sdf'
    world.write_text(SDF_FIXTURE)
    replace_camera_pose(world, '1 2 3 0 -0.4 2.3')
    changed = world.read_text()
    assert changed.count('<camera_pose>1 2 3 0 -0.4 2.3</camera_pose>') == 1
    assert changed.replace('1 2 3 0 -0.4 2.3', ORIGINAL_POSE) == SDF_FIXTURE


def test_apply_returns_previous_pose(tmp_path):
    world = tmp_path / 'world.sdf'
    world.write_text(SDF_FIXTURE)
    old_pose = replace_camera_pose(world, '1 2 3 0 -0.4 2.3')
    assert old_pose == ORIGINAL_POSE


@pytest.mark.parametrize(
    ('azimuth', 'elevation'),
    [(0.0, 0.0), (0.7, 0.0), (0.0, 0.9), (-2.1, 0.6), (3.0, -0.3)],
)
def test_camera_basis_is_orthonormal(azimuth, elevation):
    forward, right, up = camera_basis(azimuth, elevation)
    for axis in (forward, right, up):
        assert math.sqrt(sum(value * value for value in axis)) == pytest.approx(1.0)
    assert sum(a * b for a, b in zip(forward, right)) == pytest.approx(0.0)
    assert sum(a * b for a, b in zip(forward, up)) == pytest.approx(0.0)
    assert sum(a * b for a, b in zip(right, up)) == pytest.approx(0.0)


def test_camera_basis_matches_gazebo_conventions():
    forward, right, up = camera_basis(0.0, 0.0)
    assert forward == pytest.approx((1.0, 0.0, 0.0))
    assert right == pytest.approx((0.0, 1.0, 0.0))
    assert up == pytest.approx((0.0, 0.0, 1.0))
    forward, _, _ = camera_basis(math.pi / 2, 0.0)
    assert forward == pytest.approx((0.0, 1.0, 0.0))
    forward, _, up = camera_basis(0.0, 0.5)
    assert forward[2] == pytest.approx(-math.sin(0.5))
    assert up[2] == pytest.approx(math.cos(0.5))


def test_vertical_fov_derives_from_horizontal_fov_and_aspect():
    assert vertical_fov(math.pi / 2, 1.0) == pytest.approx(math.pi / 2)
    assert vertical_fov(math.pi / 2, 2.0) == pytest.approx(2 * math.atan(0.5))


def test_distance_takes_max_over_all_eight_corner_constraints():
    preset = CameraPreset(azimuth_rad=0.0, elevation_rad=0.0)
    box = Aabb(Vec3(-1, -3, -1), Vec3(1, 3, 1))
    result = calculate_camera_pose(
        focus=Vec3(0, 0, 0),
        coverage=box,
        preset=preset,
        horizontal_fov_rad=math.pi / 2,
        viewport=(1000, 1000),
        margin=1.0,
    )
    assert result.distance_m == pytest.approx(4.0)
    assert result.position == pytest.approx((-4.0, 0.0, 0.0))


def test_margin_scales_the_required_distance():
    preset = CameraPreset(azimuth_rad=0.0, elevation_rad=0.0)
    full = calculate_camera_pose(
        focus=Vec3(0, 0, 0),
        coverage=UNIT_BOX,
        preset=preset,
        horizontal_fov_rad=math.pi / 2,
        viewport=(1000, 1000),
        margin=1.0,
    )
    half = calculate_camera_pose(
        focus=Vec3(0, 0, 0),
        coverage=UNIT_BOX,
        preset=preset,
        horizontal_fov_rad=math.pi / 2,
        viewport=(1000, 1000),
        margin=0.5,
    )
    assert half.distance_m > full.distance_m


def test_elevated_preset_looks_down_with_negative_pitch():
    preset = CameraPreset(azimuth_rad=0.0, elevation_rad=0.5)
    result = calculate_camera_pose(
        focus=Vec3(0, 0, 0),
        coverage=UNIT_BOX,
        preset=preset,
        horizontal_fov_rad=math.pi / 2,
        viewport=(1000, 1000),
        margin=1.0,
    )
    assert result.rpy == pytest.approx((0.0, -0.5, 0.0))
    assert result.position[2] > 0.0


def test_camera_pose_string_uses_sdf_order():
    preset = CameraPreset(azimuth_rad=0.0, elevation_rad=0.0)
    result = calculate_camera_pose(
        focus=Vec3(0, 0, 0),
        coverage=UNIT_BOX,
        preset=preset,
        horizontal_fov_rad=math.pi / 2,
        viewport=(1000, 1000),
        margin=1.0,
    )
    values = [float(token) for token in result.camera_pose.split()]
    assert len(values) == 6
    assert values == pytest.approx([-2.0, 0.0, 0.0, 0.0, 0.0, 0.0])


@pytest.mark.parametrize('fov', [0.0, -0.1, math.pi, math.pi + 0.1])
def test_invalid_horizontal_fov_is_rejected(fov):
    with pytest.raises(ValueError, match='horizontal_fov_rad'):
        calculate_camera_pose(
            focus=Vec3(0, 0, 0),
            coverage=UNIT_BOX,
            preset=CameraPreset(azimuth_rad=0.0, elevation_rad=0.0),
            horizontal_fov_rad=fov,
            viewport=(1000, 1000),
            margin=1.0,
        )


@pytest.mark.parametrize(
    ('minimum', 'maximum'),
    [
        ((0.0, -1.0, -1.0), (0.0, 1.0, 1.0)),
        ((-1.0, 2.0, -1.0), (1.0, 1.0, 1.0)),
        ((-1.0, -1.0, -1.0), (1.0, 1.0, -2.0)),
    ],
)
def test_degenerate_aabb_is_rejected(minimum, maximum):
    with pytest.raises(ValueError, match='coverage'):
        calculate_camera_pose(
            focus=Vec3(0, 0, 0),
            coverage=Aabb(Vec3(*minimum), Vec3(*maximum)),
            preset=CameraPreset(azimuth_rad=0.0, elevation_rad=0.0),
            horizontal_fov_rad=math.pi / 2,
            viewport=(1000, 1000),
            margin=1.0,
        )


@pytest.mark.parametrize('margin', [0.0, -0.5, 1.5])
def test_margin_outside_open_unit_interval_is_rejected(margin):
    with pytest.raises(ValueError, match='margin'):
        calculate_camera_pose(
            focus=Vec3(0, 0, 0),
            coverage=UNIT_BOX,
            preset=CameraPreset(azimuth_rad=0.0, elevation_rad=0.0),
            horizontal_fov_rad=math.pi / 2,
            viewport=(1000, 1000),
            margin=margin,
        )


@pytest.mark.parametrize('viewport', [(0, 100), (100, -5), (-1, -1)])
def test_non_positive_viewport_is_rejected(viewport):
    with pytest.raises(ValueError, match='viewport'):
        calculate_camera_pose(
            focus=Vec3(0, 0, 0),
            coverage=UNIT_BOX,
            preset=CameraPreset(azimuth_rad=0.0, elevation_rad=0.0),
            horizontal_fov_rad=math.pi / 2,
            viewport=viewport,
            margin=1.0,
        )


def test_camera_inside_coverage_is_rejected():
    with pytest.raises(RuntimeError, match='inside coverage'):
        ensure_camera_outside_coverage(Vec3(0.0, 0.0, 0.0), UNIT_BOX)
    ensure_camera_outside_coverage(Vec3(2.0, 0.0, 0.0), UNIT_BOX)


def test_parse_config_accepts_all_four_semantic_presets():
    focus, coverage, presets, hfov, viewport, margin = parse_config(config_mapping())
    assert focus == pytest.approx((0.1, 0.2, 0.3))
    assert coverage.minimum == pytest.approx((-0.5, -0.5, 0.0))
    assert coverage.maximum == pytest.approx((0.5, 0.5, 0.6))
    assert tuple(sorted(presets)) == tuple(sorted(PRESET_NAMES))
    assert presets['left-front'] == CameraPreset(azimuth_rad=0.6, elevation_rad=0.5)
    assert hfov == pytest.approx(1.0)
    assert viewport == (1280, 720)
    assert margin == pytest.approx(0.9)


def test_parse_config_rejects_missing_semantic_preset():
    mapping = config_mapping()
    del mapping['presets']['right-rear']
    with pytest.raises(ValueError, match='right-rear'):
        parse_config(mapping)


def test_parse_config_rejects_preset_without_explicit_angles():
    mapping = config_mapping()
    del mapping['presets']['left-front']['azimuth_rad']
    with pytest.raises(ValueError, match='azimuth_rad'):
        parse_config(mapping)


def test_parse_config_rejects_invalid_values():
    mapping = config_mapping()
    mapping['margin'] = 2.0
    with pytest.raises(ValueError, match='margin'):
        parse_config(mapping)
    mapping = config_mapping()
    mapping['coverage_aabb']['max'] = [-1.0, 0.5, 0.6]
    with pytest.raises(ValueError, match='coverage'):
        parse_config(mapping)


def test_apply_fails_without_any_camera_pose(tmp_path):
    world = tmp_path / 'world.sdf'
    world.write_text(
        '<sdf version="1.10"><world name="plain">'
        '<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>'
        '</world></sdf>'
    )
    with pytest.raises(RuntimeError, match='camera_pose'):
        replace_camera_pose(world, '1 2 3 0 -0.4 2.3')


def test_apply_fails_with_multiple_camera_pose_matches(tmp_path):
    world = tmp_path / 'world.sdf'
    world.write_text(
        SDF_FIXTURE.replace(
            '<plugin filename="GzSceneManager" name="Scene Manager"/>',
            '<plugin filename="MinimalScene" name="3D View Copy">'
            '<camera_pose>9 9 9 0 0 0</camera_pose>'
            '</plugin>',
        )
    )
    with pytest.raises(RuntimeError, match='camera_pose'):
        replace_camera_pose(world, '1 2 3 0 -0.4 2.3')
    assert world.read_text().count(ORIGINAL_POSE) == 1


def test_apply_leaves_world_untouched_when_count_is_wrong(tmp_path):
    world = tmp_path / 'world.sdf'
    world.write_text(SDF_FIXTURE.replace(f'<camera_pose>{ORIGINAL_POSE}</camera_pose>', ''))
    with pytest.raises(RuntimeError, match='camera_pose'):
        replace_camera_pose(world, '1 2 3 0 -0.4 2.3')
    assert ORIGINAL_POSE not in world.read_text()


def test_load_config_reads_yaml_and_json(tmp_path):
    yaml_config = tmp_path / 'camera.yaml'
    yaml_config.write_text(
        'focus: [0.1, 0.2, 0.3]\n'
        'coverage_aabb:\n'
        '  min: [-0.5, -0.5, 0.0]\n'
        '  max: [0.5, 0.5, 0.6]\n'
        'horizontal_fov_rad: 1.0\n'
        'viewport: [1280, 720]\n'
        'margin: 0.9\n'
        'presets:\n'
        '  left-front: {azimuth_rad: 0.6, elevation_rad: 0.5}\n'
        '  right-front: {azimuth_rad: -0.6, elevation_rad: 0.5}\n'
        '  left-rear: {azimuth_rad: 2.4, elevation_rad: 0.5}\n'
        '  right-rear: {azimuth_rad: -2.4, elevation_rad: 0.5}\n'
    )
    json_config = tmp_path / 'camera.json'
    json_config.write_text(json.dumps(config_mapping()))
    assert MODULE.load_config(yaml_config) == MODULE.load_config(json_config)


def run_cli(*arguments):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *arguments],
        capture_output=True,
        text=True,
    )


def test_help_lists_compute_and_apply():
    completed = run_cli('--help')
    assert completed.returncode == 0
    assert 'compute' in completed.stdout
    assert 'apply' in completed.stdout


def test_compute_then_apply_round_trip(tmp_path):
    config = tmp_path / 'camera.json'
    config.write_text(json.dumps(config_mapping()))
    pose_json = tmp_path / 'pose.json'
    completed = run_cli(
        'compute', '--config', str(config), '--preset', 'left-front',
        '--json', str(pose_json),
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(pose_json.read_text())
    assert payload['preset'] == 'left-front'
    assert payload['distance_m'] > 0.0
    assert len(payload['position']) == 3
    assert len(payload['rpy']) == 3
    assert len(payload['camera_pose'].split()) == 6
    assert payload['inputs']['focus'] == [0.1, 0.2, 0.3]

    world = tmp_path / 'world.sdf'
    world.write_text(SDF_FIXTURE)
    completed = run_cli(
        'apply', '--world', str(world), '--pose-json', str(pose_json),
    )
    assert completed.returncode == 0, completed.stderr
    assert ORIGINAL_POSE in completed.stdout
    assert payload['camera_pose'] in completed.stdout
    assert str(world) in completed.stdout
    changed = world.read_text()
    assert changed.count(f"<camera_pose>{payload['camera_pose']}</camera_pose>") == 1


def test_compute_rejects_unknown_preset(tmp_path):
    config = tmp_path / 'camera.json'
    config.write_text(json.dumps(config_mapping()))
    completed = run_cli(
        'compute', '--config', str(config), '--preset', 'top-down',
        '--json', str(tmp_path / 'pose.json'),
    )
    assert completed.returncode != 0
    assert 'top-down' in completed.stderr
