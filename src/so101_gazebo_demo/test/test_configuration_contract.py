from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pytest
import yaml


PACKAGE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_DIR / 'config'
XACRO_PATH = PACKAGE_DIR / 'urdf' / 'so101.urdf.xacro'


def load_yaml(name):
    return yaml.safe_load((CONFIG_DIR / name).read_text())


def generated_robot(*mappings):
    completed = subprocess.run(
        ['xacro', str(XACRO_PATH), *mappings],
        check=True,
        capture_output=True,
        text=True,
    )
    return ET.fromstring(completed.stdout)


def test_ros2_control_joint_and_interface_contract():
    controllers = load_yaml('so101_controllers.yaml')
    parameters = controllers['controller_manager']['ros__parameters']

    assert parameters['arm_controller']['type'] == (
        'joint_trajectory_controller/JointTrajectoryController'
    )
    assert parameters['gripper_controller']['type'] == (
        'joint_trajectory_controller/JointTrajectoryController'
    )
    assert controllers['arm_controller']['ros__parameters']['joints'] == [
        '1', '2', '3', '4', '5'
    ]
    assert controllers['gripper_controller']['ros__parameters']['joints'] == ['6']
    for controller_name in ('arm_controller', 'gripper_controller'):
        controller = controllers[controller_name]['ros__parameters']
        assert controller['command_interfaces'] == ['position']
        assert controller['state_interfaces'] == ['position']


def test_ros2_control_exposes_position_and_velocity_for_every_joint():
    """Catch missing velocity evidence being silently reported as stationary."""
    robot = generated_robot()
    control = robot.find("./ros2_control[@name='RobotSystem']")
    assert control is not None

    interfaces = {
        joint.attrib['name']: {
            interface.attrib['name'] for interface in joint.findall('state_interface')
        }
        for joint in control.findall('joint')
    }
    assert interfaces == {
        str(number): {'position', 'velocity'} for number in range(1, 7)
    }


def test_gazebo_contact_profile_uses_fixed_pad_and_offline_vhacd_moving_jaw():
    """Catch the moving jaw regressing to an offset box or a visual-only mesh."""
    robot = generated_robot('gazebo_collision_primitives:=true')

    gripper = robot.find("./link[@name='gripper']")
    jaw = robot.find("./link[@name='jaw']")
    assert gripper is not None
    assert jaw is not None
    fixed = robot.find("./link[@name='gripper']/collision[@name='fixed_finger_contact']")
    moving = jaw.findall('./collision')
    assert fixed is not None
    assert len(moving) == 64
    assert fixed.find('./geometry/box') is not None
    assert all(piece.find('./geometry/box') is None for piece in moving)

    visual_mesh = jaw.find('./visual/geometry/mesh')
    assert visual_mesh is not None
    collision_meshes = [piece.find('./geometry/mesh') for piece in moving]
    assert all(mesh is not None for mesh in collision_meshes)
    assert all('/collision/moving_jaw_convex_' in mesh.attrib['filename'] for mesh in collision_meshes)
    assert all(piece.find('origin').attrib == jaw.find('./visual/origin').attrib for piece in moving)

    assert [float(value) for value in fixed.find('origin').attrib['xyz'].split()] == pytest.approx(
        [-0.0216, 0.0, -0.084], abs=1e-7
    )

    moveit_robot = generated_robot()
    for link_name in ('gripper', 'jaw'):
        link = moveit_robot.find(f"./link[@name='{link_name}']")
        assert link is not None
        assert link.find('./collision/geometry/mesh') is not None


def test_detachable_joint_uses_runtime_gripper_entity_and_raw_event_topic():
    """Catch a planning-only link name or durable-state topic in Gazebo config."""
    robot = generated_robot('gazebo_collision_primitives:=true')
    plugin = robot.find(
        ".//plugin[@name='gz::sim::systems::DetachableJoint']"
    )
    assert plugin is not None
    assert plugin.attrib['filename'] == 'gz-sim-detachable-joint-system'
    assert plugin.findtext('parent_link') == 'gripper'
    assert plugin.findtext('child_model') == 'coke'
    assert plugin.findtext('child_link') == 'body'
    assert plugin.findtext('initially_detached') == 'true'
    assert plugin.findtext('attach_topic') == '/so101/attach_coke'
    assert plugin.findtext('detach_topic') == '/so101/detach_coke'
    assert plugin.findtext('output_topic') == '/so101/coke_attached_event'


def test_moveit_controller_mapping_contract():
    moveit = load_yaml('moveit_controllers.yaml')
    manager = moveit['moveit_simple_controller_manager']

    assert manager['controller_names'] == ['arm_controller', 'gripper_controller']
    assert manager['arm_controller'] == {
        'action_ns': 'follow_joint_trajectory',
        'type': 'FollowJointTrajectory',
        'default': True,
        'joints': ['1', '2', '3', '4', '5'],
    }
    assert manager['gripper_controller'] == {
        'action_ns': 'follow_joint_trajectory',
        'type': 'FollowJointTrajectory',
        'default': True,
        'joints': ['6'],
    }


def test_srdf_group_and_named_state_contract():
    root = ET.parse(CONFIG_DIR / 'so101.srdf').getroot()
    groups = {
        group.attrib['name']: [joint.attrib['name'] for joint in group.findall('joint')]
        for group in root.findall('group')
    }
    assert groups == {
        'arm': ['base_joint', '1', '2', '3', '4', '5', 'so101_tcp_joint'],
        'gripper': ['6'],
    }

    states = {}
    for state in root.findall('group_state'):
        states[(state.attrib['group'], state.attrib['name'])] = {
            joint.attrib['name']: float(joint.attrib['value'])
            for joint in state.findall('joint')
        }
    assert states[('arm', 'home')] == {
        '1': 0.0, '2': 0.0, '3': 0.0, '4': 0.0, '5': 0.0
    }
    assert states[('gripper', 'home')] == {'6': 0.0}
    assert states[('gripper', 'fullclose')] == {'6': pytest.approx(-0.17)}
    assert states[('gripper', 'fullopen')] == {'6': pytest.approx(1.7)}
    assert states[('gripper', 'preopen')] == {'6': pytest.approx(0.7072)}
    assert states[('gripper', 'contact')] == {'6': pytest.approx(0.662818811)}


def test_srdf_has_no_exact_duplicate_disabled_collision_pairs():
    root = ET.parse(CONFIG_DIR / 'so101.srdf').getroot()
    entries = [
        (element.attrib['link1'], element.attrib['link2'], element.attrib['reason'])
        for element in root.findall('disable_collisions')
    ]
    assert len(entries) == len(set(entries))


def test_all_yaml_files_end_with_exactly_one_newline():
    for path in CONFIG_DIR.glob('*.yaml'):
        payload = path.read_bytes()
        assert payload.endswith(b'\n'), path
        assert not payload.endswith(b'\n\n'), path
