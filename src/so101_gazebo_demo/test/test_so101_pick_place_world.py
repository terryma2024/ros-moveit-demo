"""Contract tests for the SO-101 pick-place Gazebo world."""

import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pytest


PACKAGE_DIR = Path(__file__).resolve().parents[1]
WORLD_PATH = PACKAGE_DIR / 'worlds' / 'so101_pick_place.sdf'
XACRO_PATH = PACKAGE_DIR / 'urdf' / 'so101.urdf.xacro'


def parse_vector(text):
    """Parse an SDF vector into floats."""
    return tuple(float(value) for value in text.split())


def model(world, name):
    """Return a named top-level model or fail with a useful message."""
    result = world.find(f"./model[@name='{name}']")
    assert result is not None, f'missing model {name}'
    return result


def joint(robot, name):
    """Return a named URDF joint or fail with a useful message."""
    result = robot.find(f"./joint[@name='{name}']")
    assert result is not None, f'missing joint {name}'
    return result


def test_pick_place_world_has_canonical_support_and_coke_geometry():
    """Catch missing, separated, or dimensionally inconsistent geometry."""
    world = ET.parse(WORLD_PATH).getroot().find(
        "./world[@name='so101_pick_place']"
    )
    assert world is not None
    pedestal = model(world, 'base_pedestal')
    table = model(world, 'table')
    coke = model(world, 'coke')

    assert pedestal.findtext('static') == 'true'
    pedestal_pose = parse_vector(pedestal.findtext('pose'))
    pedestal_size = parse_vector(pedestal.findtext('.//box/size'))
    assert pedestal_pose == pytest.approx((0, 0, 0.17, 0, 0, 0))
    assert pedestal_size == pytest.approx((0.18, 0.18, 0.10))

    assert table.findtext('static') == 'true'
    table_pose = parse_vector(table.findtext('pose'))
    table_size = parse_vector(table.findtext('.//box/size'))
    assert table_pose == pytest.approx((0, -0.20, 0.10, 0, 0, 0))
    assert table_size == pytest.approx((0.50, 0.60, 0.04))

    coke_pose = parse_vector(coke.findtext('pose'))
    assert coke.find('static') is None
    assert coke_pose == pytest.approx((0.02, -0.28, 0.181, 0, 0, 0))
    assert float(coke.findtext('.//cylinder/radius')) == pytest.approx(0.033)
    assert float(coke.findtext('.//cylinder/length')) == pytest.approx(0.122)
    assert float(coke.findtext('.//mass')) == pytest.approx(0.1)
    assert float(coke.findtext('.//sensor/update_rate')) == pytest.approx(200.0)

    table_top = table_pose[2] + table_size[2] / 2
    table_rear_edge = table_pose[1] + table_size[1] / 2
    pedestal_bottom = pedestal_pose[2] - pedestal_size[2] / 2
    pedestal_top = pedestal_pose[2] + pedestal_size[2] / 2
    pedestal_rear_edge = pedestal_pose[1] + pedestal_size[1] / 2
    coke_bottom = coke_pose[2] - 0.122 / 2

    assert table_top == pytest.approx(0.12)
    assert pedestal_bottom == pytest.approx(table_top)
    assert pedestal_top == pytest.approx(0.22)
    assert coke_bottom == pytest.approx(table_top)
    assert table_rear_edge - pedestal_rear_edge == pytest.approx(0.01)


def test_pick_place_world_starts_without_system_initialization_errors():
    """Catch systems attached to unsupported SDF entities."""
    environment = os.environ.copy()
    environment['GZ_PARTITION'] = 'so101_pick_place_world_contract'
    completed = subprocess.run(
        [
            'gz',
            'sim',
            '-s',
            '-r',
            '--iterations',
            '1',
            str(WORLD_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    output = completed.stdout + completed.stderr
    assert 'Failed to initialize' not in output
    assert 'should be attached to a model entity' not in output


def test_pick_place_world_has_approved_gui_presentation():
    world = ET.parse(WORLD_PATH).getroot().find(
        "./world[@name='so101_pick_place']"
    )
    gui = world.find('gui')
    assert gui is not None
    assert gui.attrib['fullscreen'] == '0'

    plugins = {plugin.attrib['filename'] for plugin in gui.findall('plugin')}
    assert plugins == {
        'MinimalScene',
        'GzSceneManager',
        'InteractiveViewControl',
        'CameraTracking',
        'SelectEntities',
        'WorldControl',
        'WorldStats',
        'EntityTree',
        'ViewAngle',
        'Screenshot',
    }

    scene = gui.find("./plugin[@filename='MinimalScene']")
    assert scene.findtext('engine') == 'ogre2'
    assert parse_vector(scene.findtext('ambient_light')) == pytest.approx(
        (0.4, 0.4, 0.4)
    )
    assert parse_vector(scene.findtext('background_color')) == pytest.approx(
        (0.8, 0.8, 0.8)
    )
    assert parse_vector(scene.findtext('camera_pose')) == pytest.approx(
        (0.322, 0.222, 0.62, 0, 0.40, -2.30)
    )


@pytest.mark.parametrize(
    'filename',
    (
        'GzSceneManager',
        'InteractiveViewControl',
        'CameraTracking',
        'SelectEntities',
    ),
)
def test_pick_place_world_keeps_service_plugins_compact(filename):
    world = ET.parse(WORLD_PATH).getroot().find(
        "./world[@name='so101_pick_place']"
    )
    plugin = world.find(f"./gui/plugin[@filename='{filename}']")
    assert plugin is not None

    panel = plugin.find('gz-gui')
    assert panel is not None
    properties = {
        prop.attrib['key']: (prop.attrib['type'], prop.text)
        for prop in panel.findall('property')
    }
    assert properties == {
        'resizable': ('bool', 'false'),
        'width': ('double', '5'),
        'height': ('double', '5'),
        'state': ('string', 'floating'),
        'showTitleBar': ('bool', 'false'),
    }


def test_xacro_places_base_mesh_on_pedestal_without_changing_tcp():
    """Catch a base-frame/mesh offset gap or accidental TCP drift."""
    completed = subprocess.run(
        ['xacro', str(XACRO_PATH)],
        check=True,
        capture_output=True,
        text=True,
    )
    robot = ET.fromstring(completed.stdout)
    base_origin = joint(robot, 'base_joint').find('origin')
    tcp_origin = joint(robot, 'so101_tcp_joint').find('origin')

    world = ET.parse(WORLD_PATH).getroot().find(
        "./world[@name='so101_pick_place']"
    )
    pedestal = model(world, 'base_pedestal')
    pedestal_pose = parse_vector(pedestal.findtext('pose'))
    pedestal_size = parse_vector(pedestal.findtext('.//box/size'))
    pedestal_top = pedestal_pose[2] + pedestal_size[2] / 2

    # Lowest transformed vertex of the base link's visual/collision meshes.
    base_mesh_bottom_from_base_frame = 0.0300814
    expected_base_z = pedestal_top - base_mesh_bottom_from_base_frame
    base_xyz = parse_vector(base_origin.attrib['xyz'])

    assert base_xyz == pytest.approx((0, 0, expected_base_z))
    assert base_xyz[2] + base_mesh_bottom_from_base_frame == pytest.approx(
        pedestal_top
    )
    assert parse_vector(tcp_origin.attrib['xyz']) == pytest.approx(
        (0.0214, 0, -0.083949)
    )
    assert parse_vector(tcp_origin.attrib['rpy']) == pytest.approx((0, 0, 0))
