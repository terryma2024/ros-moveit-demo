from __future__ import annotations

import json
import runpy
import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE_ROOT / "config/model-parity.yaml"
CHECKER = PACKAGE_ROOT / "scripts/check_model_parity.py"


def test_parity_configuration_pins_independent_inputs_and_thresholds() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert config["urdf"] == "urdf/so101.urdf"
    assert config["mjcf"] == "mjcf/so101.xml"
    assert config["position_tolerance_m"] == 0.0005
    assert config["orientation_tolerance_deg"] == 0.2
    assert len(config["samples"]) == 11
    assert config["samples"][0] == [0.0] * 6
    assert set(config["mesh_sha256"]) >= {
        "base_motor_holder_so101_v1.stl",
        "moving_jaw_so101_v1.stl",
        "fixed_fingertip_pad.stl",
        "moving_fingertip_pad.stl",
    }
    assert set(config["mesh_sha256"]) == {
        path.name for path in (PACKAGE_ROOT / "mjcf/assets").glob("*.stl")
    }


def test_home_and_ten_fixed_samples_pass_urdf_mjcf_fk_parity() -> None:
    result = subprocess.run(
        ["python3", str(CHECKER), "--config", str(CONFIG)],
        cwd=PACKAGE_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["compiled"]
    assert report["joint_names_exact"]
    assert report["joint_axes_exact"]
    assert report["joint_limits_exact"]
    assert report["q6_direction_exact"]
    assert report["mesh_hashes_exact"]
    assert report["tcp_exact"]
    assert report["sample_count"] == 11
    assert report["maximum_position_error_m"] <= 0.0005
    assert report["maximum_orientation_error_deg"] <= 0.2
    assert report["validation_errors"] == []


def test_setup_installs_all_model_inputs_in_the_independent_share() -> None:
    captured: dict[str, object] = {}
    with patch("setuptools.setup", lambda **kwargs: captured.update(kwargs)):
        runpy.run_path(str(PACKAGE_ROOT / "setup.py"), run_name="__main__")
    installed = {source for _destination, sources in captured["data_files"] for source in sources}
    required = {
        "config/model-parity.yaml",
        "mjcf/so101.xml",
        "mjcf/assets/README.md",
        "urdf/so101.urdf",
    }
    required.update(
        f"mjcf/assets/{path.name}" for path in (PACKAGE_ROOT / "mjcf/assets").glob("*.stl")
    )
    assert required <= installed
