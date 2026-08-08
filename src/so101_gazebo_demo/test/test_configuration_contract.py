import importlib.util
from pathlib import Path
import json
import subprocess
import xml.etree.ElementTree as ET

import pytest
import yaml


PACKAGE_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_DIR / 'config'
XACRO_PATH = PACKAGE_DIR / 'urdf' / 'so101.urdf.xacro'
COLLISION_DIR = PACKAGE_DIR / 'meshes' / 'so101' / 'collision'
PREOPEN_CALCULATOR_PATH = PACKAGE_DIR / 'scripts' / 'gripper_preopen_calc.py'


def load_preopen_calculator_module():
    spec = importlib.util.spec_from_file_location(
        'gripper_preopen_calc_configuration_contract', PREOPEN_CALCULATOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_yaml(name):
    return yaml.safe_load((CONFIG_DIR / name).read_text())


def test_physical_outcome_policy_matches_cal_physical_003():
    validation = load_yaml('validation_policies/light_cup_wall_pick.yaml')
    assert validation['schema_version'] == 2
    physical = validation['physical_outcome']
    assert physical['intended_support_collision'] == 'table::table_top::collision'
    assert physical == {
        'intended_support_collision': 'table::table_top::collision',
        'minimum_support_contact_depth_m': pytest.approx(-1.0e-7),
        'final_target_region': {
            'kind': 'axis_aligned_box',
            'min_xy_m': pytest.approx([-0.085, -0.255]),
            'max_xy_m': pytest.approx([-0.075, -0.245]),
        },
        'support_height_range_m': pytest.approx([0.155, 0.175]),
        'max_upright_tilt_rad': pytest.approx(0.08726646259971647),
        'max_linear_speed_m_s': pytest.approx(0.001),
        'max_angular_speed_rad_s': pytest.approx(0.05),
        'consecutive_samples': 5,
        'minimum_stable_duration_s': pytest.approx(0.20),
        'sample_interval_s': pytest.approx(0.05),
        'settle_timeout_s': pytest.approx(2.0),
        'max_observation_age_s': pytest.approx(0.10),
        'max_telemetry_samples': 40,
        'catastrophic_loss': {
            'workspace_bounds_m': pytest.approx([-0.21, -0.46, 0.12, 0.21, 0.06, 0.30]),
            'max_relative_position_drift_m': pytest.approx(0.005),
            'max_relative_orientation_drift_rad': pytest.approx(0.070),
        },
        'planning_shadow': {
            'max_position_divergence_m': pytest.approx(0.005),
            'max_orientation_divergence_rad': pytest.approx(0.070),
            'max_pair_age_s': pytest.approx(0.10),
        },
    }


def test_descend_monotonic_tolerance_covers_measured_endpoint_settling_only():
    """Accept the observed 22.7-um endpoint settle, well inside the 0.1-mm gate."""
    validation = load_yaml('validation_policies/light_cup_wall_pick.yaml')
    for state in ('DESCEND', 'RECOVER_DESCEND_TO_PICK'):
        policy = validation['states'][state]
        assert policy['monotonic_tolerance_m'] == pytest.approx(0.00003)
        assert 0.0000227 < policy['monotonic_tolerance_m']
        assert policy['monotonic_tolerance_m'] < policy[
            'contact_wall_normal_endpoint_tolerance_m'
        ]


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

    assert controllers['gz_ros_control']['ros__parameters'][
        'position_proportional_gain'
    ] == 1.0

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


def test_gripper_trajectory_success_requires_mesh_bounded_joint6_convergence():
    """Contact-limited convergence must stay inside the mesh-derived safe gap band."""
    controller = load_yaml('so101_controllers.yaml')['gripper_controller']['ros__parameters']
    calculator = load_preopen_calculator_module()
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_DIR / 'task_objects' / 'light_plastic_cup.yaml',
        PACKAGE_DIR.parents[1] / 'build' / 'so101_gazebo_demo' / 'fingertip_pad_assets',
        PACKAGE_DIR / 'urdf' / 'so101_base.xacro',
    )
    contact_limit = load_yaml('validation_policies/light_cup_wall_pick.yaml')[
        'grasp_contact'
    ]['max_penetration_m']
    goal_tolerance = controller['constraints']['6']['goal']

    assert controller['open_loop_control'] is False
    assert controller['constraints'] == {
        'goal_time': pytest.approx(1.0),
        '6': {
            'trajectory': pytest.approx(0.05),
            'goal': pytest.approx(0.001),
        },
    }
    gap_open = calibration.gap_at(calibration.grasp_q6 + goal_tolerance)
    gap_closed = calibration.gap_at(calibration.grasp_q6 - goal_tolerance)
    assert gap_open - calibration.grasp_gap_m < 0.00017
    assert calibration.grasp_gap_m - gap_closed < 0.00017
    assert max(0.0, 0.002 - gap_closed) < contact_limit


def test_arm_path_tolerance_allows_bounded_contact_tracking_error_at_1khz():
    """Controller accepts bounded load error; state postconditions stay strict."""
    controller = load_yaml('so101_controllers.yaml')['arm_controller']['ros__parameters']

    assert controller['open_loop_control'] is False
    assert load_yaml('so101_controllers.yaml')['controller_manager']['ros__parameters'][
        'update_rate'
    ] == 1000
    assert controller['constraints'] == {
        'goal_time': pytest.approx(1.0),
        '1': {'trajectory': pytest.approx(0.012), 'goal': pytest.approx(0.002)},
        '2': {'trajectory': pytest.approx(0.012), 'goal': pytest.approx(0.002)},
        '3': {'trajectory': pytest.approx(0.012), 'goal': pytest.approx(0.002)},
        '4': {'trajectory': pytest.approx(0.012), 'goal': pytest.approx(0.002)},
        '5': {'trajectory': pytest.approx(0.012), 'goal': pytest.approx(0.002)},
    }


def test_initial_free_space_approach_limits_tracking_lag_without_relaxing_contact_paths():
    """The long home-to-pick sweep runs slower after an observed unloaded lag spike."""
    motion = load_yaml('motion_policies/light_cup_wall_pick.yaml')['states']

    assert motion['MOVE_ABOVE_OBJECT']['velocity_scaling'] == pytest.approx(0.03)
    assert motion['MOVE_ABOVE_OBJECT']['acceleration_scaling'] == pytest.approx(0.03)
    assert motion['DESCEND']['velocity_scaling'] == pytest.approx(0.10)
    assert motion['LIFT']['velocity_scaling'] == pytest.approx(0.10)


def test_attached_cup_transfers_limit_tracking_lag():
    """Loaded translation and placement descent stay below the bounded path envelope."""
    motion = load_yaml('motion_policies/light_cup_wall_pick.yaml')['states']

    assert motion['MOVE_ABOVE_PLACE']['velocity_scaling'] == pytest.approx(0.02)
    assert motion['MOVE_ABOVE_PLACE']['acceleration_scaling'] == pytest.approx(0.02)
    assert motion['LIFT']['velocity_scaling'] == pytest.approx(0.10)
    assert motion['DESCEND_TO_PLACE']['velocity_scaling'] == pytest.approx(0.03)
    assert motion['DESCEND_TO_PLACE']['acceleration_scaling'] == pytest.approx(0.03)


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


def test_gazebo_contact_profile_uses_two_manifest_bounded_fingertip_sets():
    """Require low-count offline convex meshes for both load-bearing fingertips."""
    robot = generated_robot('gazebo_collision_primitives:=true')

    gripper = robot.find("./link[@name='gripper']")
    jaw = robot.find("./link[@name='jaw']")
    assert gripper is not None
    assert jaw is not None
    fixed = [
        piece for piece in gripper.findall('./collision')
        if piece.attrib.get('name', '').startswith('fixed_finger_contact_convex_')
    ]
    moving = [
        piece for piece in jaw.findall('./collision')
        if piece.attrib.get('name', '').startswith('moving_jaw_contact_convex_')
    ]
    fixed_manifest = json.loads(
        (COLLISION_DIR / 'fixed_finger_contact' / 'manifest.json').read_text()
    )
    moving_manifest = json.loads(
        (COLLISION_DIR / 'moving_jaw_contact' / 'manifest.json').read_text()
    )
    assert [piece.attrib['name'] + '.stl' for piece in fixed] == [
        record['filename'] for record in fixed_manifest['pieces']
    ]
    assert [piece.attrib['name'] + '.stl' for piece in moving] == [
        record['filename'] for record in moving_manifest['pieces']
    ]
    assert 1 <= len(fixed) <= 8
    assert 1 <= len(moving) <= 8
    assert len(fixed) + len(moving) <= 16
    assert robot.find("./link[@name='gripper']/collision[@name='fixed_finger_contact']") is None
    assert all(piece.find('./geometry/box') is None for piece in fixed + moving)

    visual_mesh = jaw.find('./visual/geometry/mesh')
    assert visual_mesh is not None
    collision_meshes = [piece.find('./geometry/mesh') for piece in fixed + moving]
    assert all(mesh is not None for mesh in collision_meshes)
    assert all('/collision/' in mesh.attrib['filename'] for mesh in collision_meshes)
    assert all(piece.find('origin').attrib == jaw.find('./visual/origin').attrib for piece in moving)
    fixed_visual = next(
        visual for visual in gripper.findall('./visual')
        if 'wrist_roll_follower' in visual.find('./geometry/mesh').attrib['filename']
    )
    assert all(piece.find('origin').attrib == fixed_visual.find('origin').attrib for piece in fixed)

    moveit_robot = generated_robot()
    for link_name in ('gripper', 'jaw'):
        link = moveit_robot.find(f"./link[@name='{link_name}']")
        assert link is not None
        assert link.find('./collision/geometry/mesh') is not None


def test_tpu95a_native_fingertip_pads_are_equivalent_in_moveit_and_gazebo():
    """Require the measured native-only envelopes in both descriptions."""
    object_path = CONFIG_DIR / 'task_objects' / 'light_plastic_cup.yaml'
    object_policy = load_yaml('task_objects/light_plastic_cup.yaml')
    pads = object_policy['fingertip_pads']
    mappings = [f'object_config:={object_path}']

    for gazebo_primitives in ('false', 'true'):
        robot = generated_robot(
            *mappings, f'gazebo_collision_primitives:={gazebo_primitives}'
        )
        expected = {
            'gripper': ('fixed_fingertip_pad', 7),
            'jaw': ('moving_fingertip_pad', 6),
        }
        for link_name, (name, collision_count) in expected.items():
            link = robot.find(f"./link[@name='{link_name}']")
            assert link is not None
            visual = link.find(f"./visual[@name='{name}_visual']")
            assert visual is not None
            assert visual.find('./material').attrib['name'] == 'tpu_95a_adapter'
            mesh = visual.find('./geometry/mesh')
            assert mesh is not None and '/generated/' in mesh.attrib['filename']
            collisions = [
                collision for collision in link.findall('./collision')
                if collision.attrib.get('name', '').startswith(f'{name}_collision_')
            ]
            assert len(collisions) == collision_count
            assert all(collision.find('./geometry/mesh') is not None for collision in collisions)

        assert not any(
            'stem' in collision.attrib.get('name', '') or
            'direct_tongue' in collision.attrib.get('name', '')
            for collision in robot.findall('.//collision')
        )

    assert pads['enabled'] is True
    assert pads['material'] == 'TPU_95A'
    assert pads['contact_model'] == 'rigid_link_local_mesh'
    assert pads['fixed_pad']['opening_axis_thickness_m'] == pytest.approx(0.005)
    assert pads['moving_pad']['opening_axis_thickness_m'] == pytest.approx(0.005)


def test_cup_walls_share_the_bounded_contact_material_without_owning_friction_direction():
    """Cup walls contribute material limits but leave fdir1 to the fingertip."""
    pads = load_yaml('task_objects/light_plastic_cup.yaml')['fingertip_pads']
    material = pads['contact_material']
    assert material == {
        'axial_friction_coefficient': 3.0,
        'transverse_friction_coefficient': 1.2,
        'contact_stiffness_n_m': 1000000.0,
        'contact_damping_n_s_m': 100.0,
        'max_correcting_velocity_m_s': 0.01,
        'min_depth_m': 0.0001,
    }

    world = ET.parse(PACKAGE_DIR / 'worlds' / 'so101_pick_place.sdf').getroot()
    cup = world.find(".//model[@name='plastic_cup']/link[@name='body']")
    assert cup is not None
    walls = [collision for collision in cup.findall('collision')
             if collision.attrib['name'].startswith('wall')]
    assert len(walls) == 12
    for wall in walls:
        bullet = wall.find('./surface/friction/bullet')
        ode = wall.find('./surface/friction/ode')
        contact = wall.find('./surface/contact/ode')
        assert bullet is not None and ode is not None and contact is not None
        assert bullet.find('fdir1') is None
        assert ode.find('fdir1') is None
        assert float(bullet.findtext('friction')) == pytest.approx(1.2)
        assert float(bullet.findtext('friction2')) == pytest.approx(1.2)
        assert float(ode.findtext('mu')) == pytest.approx(1.2)
        assert float(ode.findtext('mu2')) == pytest.approx(1.2)
        assert float(contact.findtext('kp')) == pytest.approx(1000000.0)
        assert float(contact.findtext('kd')) == pytest.approx(100.0)
        assert float(contact.findtext('max_vel')) == pytest.approx(0.01)
        assert float(contact.findtext('min_depth')) == pytest.approx(0.0001)


def test_detachable_joint_uses_runtime_gripper_entity_and_raw_event_topic():
    """Catch a planning-only link name or durable-state topic in Gazebo config."""
    robot = generated_robot('gazebo_collision_primitives:=true')
    plugin = robot.find(
        ".//plugin[@name='gz::sim::systems::DetachableJoint']"
    )
    assert plugin is not None
    assert plugin.attrib['filename'] == 'gz-sim-detachable-joint-system'
    assert plugin.findtext('parent_link') == 'gripper'
    assert plugin.findtext('child_model') == 'plastic_cup'
    assert plugin.findtext('child_link') == 'body'
    assert plugin.findtext('initially_detached') == 'true'
    assert plugin.findtext('attach_topic') == '/so101/attach_object'
    assert plugin.findtext('detach_topic') == '/so101/detach_object'
    assert plugin.findtext('output_topic') == '/so101/object_attached_event'


def test_attached_task_object_collision_gate_uses_the_same_attach_lifecycle():
    """Avoid locking fingertip penetration into the rigid carry constraint."""
    robot = generated_robot('gazebo_collision_primitives:=true')
    plugin = robot.find(
        ".//plugin[@name='so101_gazebo_demo::AttachmentCollisionSystem']"
    )
    assert plugin is not None
    assert plugin.attrib['filename'] == 'libso101_attachment_collision_system.so'
    assert plugin.findtext('child_model') == 'plastic_cup'
    assert plugin.findtext('attach_topic') == '/so101/attach_object'
    assert plugin.findtext('detach_topic') == '/so101/detach_object'
    assert plugin.findtext('joint_state_topic') == '/so101/object_attached'
    assert plugin.findtext('collision_state_topic') == '/so101/object_collision_enabled'


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
    assert states[('gripper', 'home')] == {'6': pytest.approx(-0.059600220867817)}
    assert states[('gripper', 'fullclose')] == {'6': pytest.approx(-0.059600220867817)}
    assert states[('gripper', 'fullopen')] == {'6': pytest.approx(1.7)}
    assert states[('gripper', 'preopen')] == {'6': pytest.approx(0.465038)}
    calculator = load_preopen_calculator_module()
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        PACKAGE_DIR / 'config/task_objects/light_plastic_cup.yaml',
        PACKAGE_DIR.parents[1] / 'build' / 'so101_gazebo_demo' / 'fingertip_pad_assets',
        PACKAGE_DIR / 'urdf' / 'so101_base.xacro',
    )
    assert states[('gripper', 'contact')] == {
        '6': pytest.approx(calibration.grasp_q6, abs=2e-12)
    }


def test_joint6_fingertip_pad_lower_limit_is_identical_in_all_command_paths():
    floor = pytest.approx(-0.059600220867817)
    robot = generated_robot()
    joint = robot.find("./joint[@name='6']")
    assert joint is not None
    assert float(joint.find('limit').attrib['lower']) == floor
    control = robot.find("./ros2_control[@name='RobotSystem']/joint[@name='6']")
    assert control is not None
    assert float(control.find("./command_interface/param[@name='min']").text) == floor


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
