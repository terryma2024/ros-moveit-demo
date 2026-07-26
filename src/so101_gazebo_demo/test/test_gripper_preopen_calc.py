import importlib.util
import math
from pathlib import Path

import pytest


PACKAGE_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PACKAGE_DIR / 'scripts' / 'gripper_preopen_calc.py'
MESH_DIR = PACKAGE_DIR / 'meshes' / 'so101'


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
