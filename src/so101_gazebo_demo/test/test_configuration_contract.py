from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
import yaml


PACKAGE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_DIR / 'config'


def load_yaml(name):
    return yaml.safe_load((CONFIG_DIR / name).read_text())


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
