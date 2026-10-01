"""The `measure-admission` entry: it declares inputs, calls one library function and nothing else.

The entry produces the run's `--admission` from the six sealed inputs the run itself declares, so what
these tests pin is the entry's own behaviour - which flags it needs, what it refuses before the library
runs, and what it prints - with synthetic documents and no ROS, simulator or detector.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from so101_demo.cli.head_search_calibration import main
from so101_demo.perception_benchmark.contracts import canonical_sha256

FOVY_RAD = 1.0471975511965976
HORIZONTAL_FOV_RAD = 1.3121067481206794
LOCK_INTERVAL = [-6.283175307179587, 6.283175307179587]
REQUIRED_DOMAIN = [-0.17559216195018026, 0.08047101126546086]


def _geometry() -> dict:
    body = {
        "schema_version": 1,
        "camera_name": "head_camera",
        "image_width": 640,
        "image_height": 480,
        "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
        "lock_valid_neck_rad": list(LOCK_INTERVAL),
        "required_search_domain_rad": list(REQUIRED_DOMAIN),
        "coarse_step_candidate_rad": 0.4,
        "anchors": ["forward"],
        "in_frame_matrix": {
            "forward": {"centre_angle_rad": 0.18822150530477078, "neck_start_rad": 0.0,
                        "out_of_frame_rad": [], "samples": []}
        },
        "in_frame_failures": [],
        "workspace_matrix": {"in_frame": 120, "key_samples": []},
        "camera": {
            "camera_name": "head_camera",
            "width": 640,
            "height": 480,
            "fovy_rad": FOVY_RAD,
            "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
            "distortion_model": "plumb_bob",
            "local_position_m": [0.0, 0.0, 0.0],
            "local_xyaxes": [-1.0, 0.0, 0.0, 0.0, -0.6, 0.8],
            "parent_body": "head_mount",
        },
        "fov_union_covers_required_domain": True,
        "safe_interval_contains_required_domain": True,
    }
    return {**body, "seal_sha256": canonical_sha256(body)}


def _production_config() -> dict:
    return {
        "schema_version": 2,
        "values": {
            "horizontal_fov_rad": 0.9,
            "coarse_step_rad": 0.3,
            "search_timeout_s": 12.0,
            "max_age_s": 0.05,
            "max_skew_s": 0.02,
            "center_deadband_px": 18.0,
            "vertical_bounds_px": [110.0, 370.0],
            "min_area_px2": 64.0,
            "min_confidence": 0.4,
            "max_fine_corrections": 4,
            "max_fine_total_rad": 0.4,
        },
        "motion": {"goal_tolerance_rad": 0.05, "settle_velocity_rad_s": 0.05},
        "camera": {
            "frame_id": "head_camera_optical_frame",
            "ray_origin_frame_id": "base_link",
            "name": "head_camera",
            "width": 640,
            "height": 480,
        },
    }


def _write_json(path: Path, document) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _sealed(tmp_path: Path) -> dict:
    contents = {
        "dataset_manifest": {"kind": "dataset"},
        "model_manifest": {"kind": "model"},
        "geometry_seal": _geometry(),
        "scenario_partitions": {"kind": "partitions"},
        "production_config": _production_config(),
        "camera_config": {"camera_name": "head_camera"},
    }
    return {
        name: _write_json(tmp_path / "sealed" / f"{name}.json", document)
        for name, document in contents.items()
    }


def _arguments(tmp_path: Path, *, output_dir: Path | None = None, run_root: Path | None = None) -> list[str]:
    sealed = _sealed(tmp_path)
    return [
        "measure-admission",
        "--dataset", str(sealed["dataset_manifest"]),
        "--candidate", str(sealed["model_manifest"]),
        "--geometry-seal", str(sealed["geometry_seal"]),
        "--episode-partitions", str(sealed["scenario_partitions"]),
        "--production-config", str(sealed["production_config"]),
        "--camera-config", str(sealed["camera_config"]),
        "--run-root", str(run_root if run_root is not None else tmp_path / "runs" / "generation"),
        "--output-dir", str(output_dir if output_dir is not None else tmp_path / "admission"),
        "--cpu-cores", "8",
        "--gpu-device", "0",
    ]


def _read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_measure_admission_writes_the_plan_the_admission_and_the_receipt(tmp_path: Path, capsys) -> None:
    assert main(_arguments(tmp_path)) == 0
    printed = capsys.readouterr().out
    output = tmp_path / "admission"
    assert sorted(path.name for path in output.iterdir()) == [
        "admission-receipt.json",
        "admission.json",
        "measurement-plan.json",
    ]
    admission = _read(output / "admission.json")
    assert set(admission) == {
        "generation",
        "status",
        "measurement_plan_sha256",
        "safe_interval_rad",
        "controller_generation",
        "broker_generation",
    }
    assert admission["generation"] == "generation"
    assert printed.startswith("ADMISSION_RECORDED generation=generation ")
    assert admission["measurement_plan_sha256"] in printed
    receipt = _read(output / "admission-receipt.json")
    assert receipt["provenance"]["command"].endswith("--gpu-device 0")
    assert "measure-admission" in receipt["provenance"]["command"]


def test_measure_admission_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-admission"]) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE: a measurement declares ")
    for flag in ("--dataset", "--geometry-seal", "--production-config", "--run-root", "--output-dir"):
        assert flag in printed


def test_measure_admission_refuses_an_input_that_does_not_exist(tmp_path: Path, capsys) -> None:
    arguments = _arguments(tmp_path)
    arguments[arguments.index("--camera-config") + 1] = str(tmp_path / "absent.json")
    assert main(arguments) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE: no such input ")
    assert "absent.json" in printed


def test_measure_admission_refuses_an_existing_output_directory(tmp_path: Path, capsys) -> None:
    output = tmp_path / "admission"
    output.mkdir()
    assert main(_arguments(tmp_path, output_dir=output)) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("CAL_ADMISSION_INCOMPLETE: ")
    assert "never resumed or overwritten" in printed


def test_measure_admission_refuses_a_generation_whose_run_root_exists(tmp_path: Path, capsys) -> None:
    run_root = tmp_path / "runs" / "generation"
    run_root.mkdir(parents=True)
    assert main(_arguments(tmp_path, run_root=run_root)) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("CAL_ADMISSION_INCOMPLETE: ")
    assert "no reuse" in printed
    assert not (tmp_path / "admission").exists()


def test_measure_admission_prints_the_trajectory_contracts_refusal(tmp_path: Path, capsys) -> None:
    arguments = _arguments(tmp_path)
    config_path = tmp_path / "sealed" / "production_config.json"
    config = _read(config_path)
    config["values"]["coarse_step_rad"] = 0.9
    _write_json(config_path, config)
    assert main(arguments) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("CAL_TRAJECTORY_CONTRACT_UNSATISFIED: ")


def test_measure_admission_takes_a_declared_seal_document(tmp_path: Path, capsys) -> None:
    sealed = _sealed(tmp_path)
    seal_document = _write_json(
        tmp_path / "sealed-inputs.json",
        {
            "dataset_manifest": {"path": str(sealed["dataset_manifest"]),
                                 "sha256": hashlib.sha256(sealed["dataset_manifest"].read_bytes()).hexdigest()},
            "model_manifest": {"path": str(sealed["model_manifest"]),
                               "sha256": hashlib.sha256(sealed["model_manifest"].read_bytes()).hexdigest()},
            "geometry_seal": {"path": str(sealed["geometry_seal"]),
                              "sha256": hashlib.sha256(sealed["geometry_seal"].read_bytes()).hexdigest()},
            "scenario_partitions": {"path": str(sealed["scenario_partitions"]),
                                    "sha256": hashlib.sha256(sealed["scenario_partitions"].read_bytes()).hexdigest()},
            "production_config": {"path": str(sealed["production_config"]),
                                  "sha256": hashlib.sha256(sealed["production_config"].read_bytes()).hexdigest()},
            "camera_config": {"path": str(sealed["camera_config"]),
                              "sha256": hashlib.sha256(sealed["camera_config"].read_bytes()).hexdigest()},
        },
    )
    arguments = _arguments(tmp_path) + ["--seal", str(seal_document)]
    assert main(arguments) == 0
    capsys.readouterr()
    receipt = _read(tmp_path / "admission" / "admission-receipt.json")
    assert receipt["provenance"]["sealed_inputs"]["geometry_seal"]["sha256"] == hashlib.sha256(
        sealed["geometry_seal"].read_bytes()
    ).hexdigest()


def test_measure_admission_is_dispatched_by_the_console_entry(tmp_path: Path, capsys) -> None:
    """The entry is reached by its subcommand name, not by importing the module in a script."""

    with pytest.raises(SystemExit) as exit_info:
        main(["measure-admission", "--help"])
    assert exit_info.value.code == 0
    assert "measure-admission" in capsys.readouterr().out
