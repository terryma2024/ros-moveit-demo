import importlib.util
import math
import os
from pathlib import Path
import subprocess
import re
import numpy as np
import yaml

import pytest


PACKAGE_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PACKAGE_DIR / 'scripts' / 'gripper_preopen_calc.py'
MESH_DIR = PACKAGE_DIR / 'meshes' / 'so101'
URDF_PATH = PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
CALIBRATION_HEADER = (
    PACKAGE_DIR / 'include' / 'so101_gazebo_demo' / 'pick_place'
    / 'gripper_width_calibration_data.hpp'
)


def load_calculator_module():
    spec = importlib.util.spec_from_file_location('gripper_preopen_calc', SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_d20_section_produces_task_object_preopen_and_contact_targets():
    """Catch centroid/tip-fraction geometry replacing the d=20 mm centre ray."""
    calculator = load_calculator_module()

    result = calculator.calculate_gripper_targets(
        mesh_dir=MESH_DIR,
        grasp_depth=0.020,
        task_object_diameter=0.066,
        preopen_clearance=0.004,
    )

    assert result.q_preopen == pytest.approx(0.707194871, abs=1e-6)
    assert math.degrees(result.q_preopen) == pytest.approx(40.519281, abs=1e-4)
    assert result.q_contact == pytest.approx(0.662818810, abs=1e-6)
    assert math.degrees(result.q_contact) == pytest.approx(37.976720, abs=1e-4)
    assert result.preopen_width == pytest.approx(0.070, abs=1e-7)
    assert result.contact_width == pytest.approx(0.066, abs=1e-7)
    assert result.q_contact < result.q_preopen
    assert result.fixed_inward_dot > 0.99
    assert result.preopen_moving_inward_dot > 0.70
    assert result.contact_moving_inward_dot > 0.70


def test_configured_q6_orders_the_native_fingertip_pad_commands():
    """The native-only geometry owns a negative safe floor and a wall-safe close."""
    object_policy = yaml.safe_load(
        (PACKAGE_DIR / 'config/task_objects/light_plastic_cup.yaml').read_text()
    )
    motion = yaml.safe_load(
        (PACKAGE_DIR / 'config/motion_policies/light_cup_wall_pick.yaml').read_text()
    )
    calibration = load_calculator_module().calculate_fingertip_pad_gap_calibration(
        PACKAGE_DIR / 'config/task_objects/light_plastic_cup.yaml',
        PACKAGE_DIR.parents[1] / 'build' / 'so101_gazebo_demo' / 'fingertip_pad_assets',
        URDF_PATH,
    )
    pads = object_policy['fingertip_pads']
    assert pads['safe_lower_q6'] < motion['gripper_actions']['grasp_close_q6']
    assert motion['gripper_actions']['grasp_close_q6'] < motion['gripper_actions']['preopen_q6']
    assert pads['safe_gap_m'] == pytest.approx(0.001)
    assert pads['grasp_gap_m'] == pytest.approx(calibration.grasp_gap_m, abs=2e-12)
    assert motion['gripper_actions']['grasp_close_q6'] == pytest.approx(
        calibration.grasp_q6, abs=2e-12
    )


def test_native_fingertip_pads_keep_the_measured_same_wall_envelope():
    """The old suspended-box TCP calculation is deliberately not retained."""
    object_policy = yaml.safe_load(
        (PACKAGE_DIR / 'config/task_objects/light_plastic_cup.yaml').read_text()
    )
    pads = object_policy['fingertip_pads']
    assert pads['fixed_pad']['profile_points'][0][0] == pytest.approx(0.06622)
    assert pads['fixed_pad']['profile_points'][-1][0] == pytest.approx(0.104875)
    assert pads['moving_pad']['profile_points'][0][0] == pytest.approx(-0.0815)
    assert pads['moving_pad']['profile_points'][-1][0] == pytest.approx(-0.0625)


def test_native_fingertip_pad_profiles_are_contained_without_a_stem():
    object_policy = yaml.safe_load(
        (PACKAGE_DIR / 'config/task_objects/light_plastic_cup.yaml').read_text()
    )
    pads = object_policy['fingertip_pads']
    assert all('stem' not in name and 'tongue' not in name for name in pads)
    for pad in (pads['fixed_pad'], pads['moving_pad']):
        native = pad['native_axial_bounds_m']
        profile = pad['profile_points']
        assert native[0] < profile[0][0] < profile[-1][0] < native[1]


def test_default_mesh_dir_resolves_installed_package_meshes():
    calculator = load_calculator_module()

    mesh_dir = calculator.default_mesh_dir()

    assert (mesh_dir / 'moving_jaw_so101_v1.stl').is_file()
    assert (mesh_dir / 'wrist_roll_follower_so101_v1.stl').is_file()


def test_calculator_runs_without_python_user_site_packages():
    environment = os.environ.copy()
    environment['PYTHONNOUSERSITE'] = '1'

    completed = subprocess.run(
        [
            'python3',
            str(SCRIPT_PATH),
            '--mesh-dir',
            str(MESH_DIR),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert 'q_preopen = 40.519281 deg  (0.707194871 rad)' in completed.stdout
    assert 'q_contact = 37.976720 deg  (0.662818811 rad)' in completed.stdout


def test_versioned_dense_table_matches_real_mesh_at_nonendpoint():
    calculator = load_calculator_module()
    calibration = calculator.calculate_width_calibration(
        mesh_dir=MESH_DIR,
        urdf_path=URDF_PATH,
        grasp_depth=0.020,
        task_object_diameter=0.066,
        q_min=0.290000000,
        q_max=0.890000000,
        sample_count=240,
    )
    header = CALIBRATION_HEADER.read_text()
    assert header == calculator.render_width_calibration_header(calibration)
    samples = [
        (float(q6), float(width))
        for q6, width in re.findall(
            r'CalibrationSample\{([0-9.]+), ([0-9.]+)\}', header
        )
    ]

    assert calibration.model_version in header
    assert calibration.fixed_mesh_sha256 in header
    assert calibration.moving_mesh_sha256 in header
    assert calibration.urdf_sha256 in header
    assert calibration.constants_sha256 in header
    assert calibration.model_fingerprint in header
    assert len(samples) == 240
    midpoint = len(samples) // 2
    assert samples[midpoint][1] == pytest.approx(
        calculator.gripper_width_at_q6(
            mesh_dir=MESH_DIR,
            grasp_depth=0.020,
            task_object_diameter=0.066,
            q6=samples[midpoint][0],
        ),
        abs=1e-10,
    )
    for actual, expected in zip(samples, calibration.samples):
        assert actual[0] == pytest.approx(expected[0], abs=1e-12)
        assert actual[1] == pytest.approx(expected[1], abs=1e-12)


def test_calibration_header_regenerates_without_user_site_packages():
    environment = os.environ.copy()
    environment['PYTHONNOUSERSITE'] = '1'
    completed = subprocess.run(
        [
            '/usr/bin/python3', str(SCRIPT_PATH),
            '--mesh-dir', str(MESH_DIR),
            '--urdf-path', str(URDF_PATH),
            '--print-calibration-header',
            '--calibration-q-min', '0.290000000',
            '--calibration-q-max', '0.890000000',
            '--calibration-samples', '240',
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == CALIBRATION_HEADER.read_text()
