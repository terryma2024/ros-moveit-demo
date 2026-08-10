"""Deterministic native-fingertip pad clearance calibration contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


PACKAGE_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PACKAGE_DIR / 'scripts' / 'gripper_preopen_calc.py'
CONFIG = PACKAGE_DIR / 'config' / 'task_objects' / 'light_plastic_cup.yaml'
URDF = PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
ASSETS = PACKAGE_DIR.parents[1] / 'build' / 'so101_gazebo_demo_cpp' / 'fingertip_pad_assets'
HEADER = PACKAGE_DIR / 'include' / 'so101_gazebo_demo' / 'pick_place' / 'fingertip_pad_gap_calibration_data.hpp'


def _calculator():
    spec = importlib.util.spec_from_file_location('pad_gap_calculator', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_native_pad_gap_calibration_is_mesh_and_transform_fingerprinted():
    calculator = _calculator()
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        config_path=CONFIG, asset_root=ASSETS, urdf_path=URDF
    )

    assert calibration.safe_floor_q6 < calibration.grasp_q6 < calibration.preopen_q6
    assert calibration.safe_floor_gap_m >= 0.001 - 2e-6
    configured_gap = yaml.safe_load(CONFIG.read_text())['fingertip_pads']['grasp_gap_m']
    assert calibration.grasp_gap_m == pytest.approx(configured_gap, abs=2e-12)
    assert calibration.cup_wall_interference_m == pytest.approx(0.002 - configured_gap, abs=2e-12)
    assert calibration.gap_at(calibration.safe_floor_q6 - 0.001) < calibration.safe_floor_gap_m
    assert calibration.gap_at(calibration.safe_floor_q6) < calibration.gap_at(calibration.grasp_q6)
    assert calibration.gap_at(calibration.grasp_q6) < calibration.gap_at(calibration.preopen_q6)
    assert len(calibration.input_fingerprint) == 64
    assert calibration.fixed_visual_mesh_sha256
    assert calibration.moving_visual_mesh_sha256
    assert calibration.fixed_collision_mesh_sha256
    assert calibration.moving_collision_mesh_sha256
    assert calibration.urdf_sha256
    # Runtime must evaluate the *observed* q6 from a generated model, never
    # relabel every accepted contact endpoint as the nominal grasp gap.
    assert len(calibration.gap_samples) >= 129
    assert calibration.gap_samples[0][0] < calibration.safe_floor_q6
    assert calibration.gap_samples[-1][0] > calibration.preopen_q6
    assert any(q6 == calibration.safe_floor_q6 for q6, _ in calibration.gap_samples)
    assert any(q6 == calibration.grasp_q6 for q6, _ in calibration.gap_samples)
    assert any(q6 == calibration.preopen_q6 for q6, _ in calibration.gap_samples)
    gaps = [gap for _, gap in calibration.gap_samples]
    assert gaps == sorted(gaps)
    assert HEADER.read_text() == calculator.render_fingertip_pad_gap_calibration_header(calibration)


def test_gap_calibration_fingerprint_changes_when_a_profile_input_changes(tmp_path):
    calculator = _calculator()
    altered = tmp_path / 'object.yaml'
    payload = CONFIG.read_text().replace('0.104875', '0.104874', 1)
    altered.write_text(payload)

    calculator.calculate_fingertip_pad_gap_calibration(CONFIG, ASSETS, URDF)
    with pytest.raises(ValueError, match='do not match the configured profile'):
        calculator.calculate_fingertip_pad_gap_calibration(altered, ASSETS, URDF)


def test_gap_calibration_uses_the_supplied_urdf_transform_not_module_constants(tmp_path):
    calculator = _calculator()
    altered = tmp_path / 'so101_base.xacro'
    altered.write_text(URDF.read_text().replace(
        'xyz="0.0202 0.0188 -0.0234"', 'xyz="0.0203 0.0188 -0.0234"', 1
    ))

    baseline = calculator.calculate_fingertip_pad_gap_calibration(CONFIG, ASSETS, URDF)
    changed = calculator.calculate_fingertip_pad_gap_calibration(CONFIG, ASSETS, altered)

    assert changed.input_fingerprint != baseline.input_fingerprint
    assert changed.safe_floor_q6 != pytest.approx(baseline.safe_floor_q6, abs=1e-8)
    assert changed.grasp_q6 != pytest.approx(baseline.grasp_q6, abs=1e-8)
