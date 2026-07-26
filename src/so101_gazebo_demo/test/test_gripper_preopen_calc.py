import importlib.util
import math
import os
from pathlib import Path
import subprocess
import re

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


def test_d20_section_produces_coke_preopen_and_contact_targets():
    """Catch centroid/tip-fraction geometry replacing the d=20 mm centre ray."""
    calculator = load_calculator_module()

    result = calculator.calculate_gripper_targets(
        mesh_dir=MESH_DIR,
        grasp_depth=0.020,
        coke_diameter=0.066,
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
        coke_diameter=0.066,
        q_min=0.662818811 - 0.002,
        q_max=0.707194871 + 0.002,
        sample_count=49,
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
    assert len(samples) == 49
    assert samples[24][0] == pytest.approx(0.685006841, abs=1e-12)
    assert samples[24][1] == pytest.approx(
        calculator.gripper_width_at_q6(
            mesh_dir=MESH_DIR,
            grasp_depth=0.020,
            coke_diameter=0.066,
            q6=samples[24][0],
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
            '--calibration-q-min', '0.660818811',
            '--calibration-q-max', '0.709194871',
            '--calibration-samples', '49',
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == CALIBRATION_HEADER.read_text()
