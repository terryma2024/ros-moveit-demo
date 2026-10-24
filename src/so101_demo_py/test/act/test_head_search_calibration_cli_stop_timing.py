"""The controller stop, feedback, frame contract and skew subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from head_search_calibration_cli_support import _deadband_inputs
import pytest

from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
)
from so101_demo.cli.head_search_calibration import main

#: the installed controller's own stopped tolerance, as its header declares it
STOP_DECLARATION = """STOP_WINDOW_SAMPLES = 51
STOP_WINDOW_STEP_NS = 2_000_000
STOP_WINDOW_MAX_AGE_NS = 200_000_000
STOP_WINDOW_MAX_VELOCITY_RAD_S = 0.002
"""


#: the shared fixture declares the controller manager's rate only; the stop path's feedback period is the
#: broadcaster's rate, so the stop measurements declare both rates the way the installed configuration does
STOP_CONTROLLERS = """controller_manager:
  ros__parameters:
    update_rate: 500
joint_state_broadcaster:
  ros__parameters:
    update_rate: 100
"""


def _stop_inputs(tmp_path: Path) -> dict:
    """The declared inputs of the stop measurements: the shared fixture plus the declared stop values."""

    inputs = _deadband_inputs(tmp_path)
    controllers = tmp_path / "stop_ros2_controllers.yaml"
    controllers.write_text(STOP_CONTROLLERS, encoding="utf-8")
    inputs["controllers"] = controllers
    production = json.loads(inputs["production"].read_text(encoding="utf-8"))
    production["values"].update(
        {"stop_velocity_rad_s": 0.05, "stop_latency_s": 0.06, "submit_lead_s": 0.02}
    )
    declared = tmp_path / "head_search_v2_stop.json"
    declared.write_text(json.dumps(production), encoding="utf-8")
    inputs["production"] = declared
    inputs["declaration"] = tmp_path / "head_neck_limits.py"
    inputs["declaration"].write_text(STOP_DECLARATION, encoding="utf-8")
    return inputs


class _StopPlant:
    """A plant that admits every goal at the next control cycle and then reports stopped feedback."""

    def __init__(self, request) -> None:
        self.request = request
        self.simulation_timestep_s = 0.002
        self.control_period_s = float(request.get("control_period_s") or 0.002)
        self.feedback_period_s = float(request.get("feedback_period_s") or 0.01)
        self.time_s = 0.0
        self.reference_rad = float(request["start_rad"])
        self.admissions: list[dict] = []
        self.holds: list[float] = []

    @property
    def yaw_rad(self) -> float:
        return self.reference_rad

    def command_through_admission(self, target_rad, *, purpose, max_cycles=None):
        snapshot = self.time_s
        cycles = 4 if max_cycles is None else int(max_cycles)
        self.admissions.append({"purpose": purpose, "target_rad": float(target_rad)})
        reference_before = self.reference_rad
        for _ in range(cycles):
            self.step_control_cycle()
        return {
            "purpose": purpose,
            "target_rad": float(target_rad),
            "reference_before_rad": reference_before,
            "submit_snapshot_sim_s": snapshot,
            "first_target_sim_s": snapshot + self.simulation_timestep_s,
            "plant_consumed_sim_s": snapshot + self.simulation_timestep_s,
            "lead_s": self.simulation_timestep_s,
            "steps": cycles,
            "control_cycles": cycles,
            "settled": max_cycles is None,
            "reached": True,
            "final_velocity_rad_s": 0.0,
            "final_position_error_rad": 0.0,
            "quiet_steps": 5,
        }

    def hold_command(self, rad: float) -> None:
        self.holds.append(float(rad))
        self.reference_rad = float(rad)

    def step_control_cycle(self) -> None:
        self.time_s += self.control_period_s

    def feedback_sample(self) -> dict:
        return {
            "sim_s": self.time_s,
            "monotonic_s": 0.0,
            "yaw_rad": self.yaw_rad,
            "reference_rad": self.reference_rad,
            "position_error_rad": 0.0,
            "velocity_rad_s": [0.0] * 6 + [0.001],
            "joint_positions": [0.0] * 7,
            "joint_velocities": [0.0] * 6 + [0.001],
        }

    def real_time_factor(self) -> float:
        return 1.0

    def close(self) -> None:
        pass


def _stop_flight_arguments(subcommand: str, inputs: dict, output: Path) -> list:
    return [
        subcommand,
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--production-search-config",
        str(inputs["production"]),
        "--controller-config",
        str(inputs["controllers"]),
        "--output-dir",
        str(output),
        "--anchor",
        "left",
    ]


def test_measure_controller_stop_config_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-controller-stop-config"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "stop-config").exists()


def test_measure_controller_stop_config_writes_the_declared_tolerance(tmp_path: Path, capsys) -> None:
    inputs = _stop_inputs(tmp_path)
    output = tmp_path / "stop-config"

    assert (
        main(
            [
                "measure-controller-stop-config",
                "--controller-declaration",
                str(inputs["declaration"]),
                "--source-declaration",
                str(inputs["declaration"]),
                "--controller-config",
                str(inputs["controllers"]),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    assert "CONTROLLER_STOP_CONFIG_DECLARED" in capsys.readouterr().out
    document = json.loads((output / "controller-stop-config.json").read_text(encoding="utf-8"))
    assert document["stopped_tolerance_rad_s"] == 0.002
    assert document["measured_here"] is False
    assert document["declared_by"]["path"] == str(inputs["declaration"])
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["document_sha256"] == document["sha256"]


def test_measure_controller_stop_config_refuses_a_header_without_the_tolerance(
    tmp_path: Path, capsys
) -> None:
    inputs = _stop_inputs(tmp_path)
    bare = tmp_path / "no-tolerance.py"
    bare.write_text(
        STOP_DECLARATION.replace("STOP_WINDOW_MAX_VELOCITY_RAD_S = 0.002\n", ""),
        encoding="utf-8",
    )
    from so101_demo.act.head_search.stop_measurement.contracts import (
        CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
    )

    assert (
        main(
            [
                "measure-controller-stop-config",
                "--controller-declaration",
                str(bare),
                "--source-declaration",
                str(bare),
                "--controller-config",
                str(inputs["controllers"]),
                "--output-dir",
                str(tmp_path / "stop-config"),
            ]
        )
        == 2
    )
    assert CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED in capsys.readouterr().err


def test_measure_feedback_refuses_an_undeclared_quantisation_and_accepts_a_declared_one(
    tmp_path: Path, capsys
) -> None:
    inputs = _stop_inputs(tmp_path)
    from so101_demo.act.head_search.stop_measurement.contracts import (
        CAL_FEEDBACK_QUANTISATION_UNDECLARED,
    )

    output = tmp_path / "feedback"
    assert (
        main(
            [
                "measure-feedback",
                "--controller-config",
                str(inputs["controllers"]),
                "--output-dir",
                str(output),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert CAL_FEEDBACK_QUANTISATION_UNDECLARED in captured.err
    assert "FEEDBACK_MEASUREMENTS_MEASURED" in captured.out
    document = json.loads((output / "feedback-measurements.json").read_text(encoding="utf-8"))
    assert document["period_s"] == 0.01
    assert document["quantisation_rad"] is None
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["fields_refused"] == ["quantisation_rad"]

    declaration = tmp_path / "encoder.json"
    declaration.write_text(json.dumps({"quantisation_rad": 0.0001}), encoding="utf-8")
    second = tmp_path / "feedback-declared"
    assert (
        main(
            [
                "measure-feedback",
                "--controller-config",
                str(inputs["controllers"]),
                "--quantisation-declaration",
                str(declaration),
                "--output-dir",
                str(second),
            ]
        )
        == 0
    )
    document = json.loads((second / "feedback-measurements.json").read_text(encoding="utf-8"))
    assert document["quantisation_rad"] == 0.0001
    assert document["refusals"] == []


def test_measure_stationary_hands_the_flight_to_the_library(tmp_path: Path, capsys, monkeypatch) -> None:
    inputs = _stop_inputs(tmp_path)
    output = tmp_path / "stationary"
    from so101_demo.act.head_search.stop_measurement import contracts as measurement_contracts
    from so101_demo.act.head_search.stop_measurement import flights as measurement_flights

    monkeypatch.setattr(measurement_flights, "MujocoStopFlight", _StopPlant)

    assert (
        main(_stop_flight_arguments("measure-stationary", inputs, output) + ["--samples-per-pose", "3"])
        == 0
    )
    captured = capsys.readouterr()
    assert "STATIONARY_MEASUREMENTS_MEASURED" in captured.out
    document = json.loads((output / "stationary-measurements.json").read_text(encoding="utf-8"))
    assert document["samples_per_pose"] == 3
    assert document["pose_count"] == 3
    assert len(document["samples"]) == 9
    assert document["monitored_joints"] == list(measurement_contracts.MONITORED_JOINTS)
    assert document["samples"][0]["velocity_rad_s"][-1] == 0.001
    assert document["path"] == str(output / "stationary-measurements.json")
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["document_sha256"] == document["sha256"]
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False


def test_measure_controller_submissions_hands_the_flight_to_the_library(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _stop_inputs(tmp_path)
    output = tmp_path / "submissions"
    from so101_demo.act.head_search.stop_measurement import flights as measurement_flights

    monkeypatch.setattr(measurement_flights, "MujocoStopFlight", _StopPlant)

    assert main(_stop_flight_arguments("measure-controller-submissions", inputs, output)) == 0
    assert "CONTROLLER_SUBMISSIONS_MEASURED" in capsys.readouterr().out
    document = json.loads((output / "controller-submissions.json").read_text(encoding="utf-8"))
    assert document["time_base"] == "simulation"
    assert document["samples"]
    for sample in document["samples"]:
        assert sample["time_base"] == "simulation"
        assert sample["first_target_sim_s"] - sample["submit_snapshot_sim_s"] == pytest.approx(
            document["simulation_timestep_s"]
        )


def test_measure_stop_proofs_hands_the_flight_to_the_library(tmp_path: Path, capsys, monkeypatch) -> None:
    inputs = _stop_inputs(tmp_path)
    output = tmp_path / "stop-proofs"
    from so101_demo.act.head_search.stop_measurement import flights as measurement_flights

    monkeypatch.setattr(measurement_flights, "MujocoStopFlight", _StopPlant)

    assert (
        main(
            _stop_flight_arguments("measure-stop-proofs", inputs, output)
            + ["--revoke-offset-s", "0.02", "--stop-budget-s", "0.5"]
        )
        == 0
    )
    assert "STOP_PROOFS_MEASURED" in capsys.readouterr().out
    document = json.loads((output / "stop-proofs.json").read_text(encoding="utf-8"))
    assert document["feedback_period_s"] == 0.01
    assert len(document["samples"]) == 2
    for sample in document["samples"]:
        assert sample["third_confirming_receive_monotonic_s"] > sample["stop_request_monotonic_s"]
        assert len(sample["feedback_samples"]) >= 3


def test_the_stop_measurements_refuse_an_existing_output_directory(tmp_path: Path, capsys) -> None:
    inputs = _stop_inputs(tmp_path)
    output = tmp_path / "stationary"
    output.mkdir()

    assert main(_stop_flight_arguments("measure-stationary", inputs, output)) == 2
    assert "never resumed" in capsys.readouterr().err


def test_the_stop_flight_entries_need_a_scene_and_a_seal(tmp_path: Path, capsys) -> None:
    inputs = _stop_inputs(tmp_path)
    for subcommand in ("measure-stationary", "measure-controller-submissions", "measure-stop-proofs"):
        assert main([subcommand]) == 2
        assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
        arguments = _stop_flight_arguments(subcommand, inputs, tmp_path / subcommand)
        arguments[2] = str(tmp_path / "absent.xml")
        assert main(arguments) == 2
        assert "no such input" in capsys.readouterr().err


TRANSPORT_PLUGIN_CONFIG = {
    "/**": {
        "ros__parameters": {
            "mujoco_plugins": {
                "mujoco_camera_plugin": {
                    "type": "mujoco_ros2_control_plugins/CameraPlugin",
                    "camera_publish_rate": 10.0,
                    "head_camera": {
                        "policy": "streaming",
                        "frame_name": "head_camera_frame",
                        "image_topic": "/head_camera/color",
                        "info_topic": "/head_camera/camera_info",
                    },
                }
            }
        }
    }
}


def _transport_inputs(tmp_path: Path, *, rate: float = 10.0) -> dict:
    import yaml

    document = json.loads(json.dumps(TRANSPORT_PLUGIN_CONFIG))
    camera = document["/**"]["ros__parameters"]["mujoco_plugins"]["mujoco_camera_plugin"]
    camera["camera_publish_rate"] = rate
    plugin = tmp_path / "mujoco_plugins.yaml"
    plugin.write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")
    inputs = {"--plugin-config": plugin, "--output-dir": tmp_path / "measurement"}
    for flag, name in (
        ("--scene", "head_search_scene.xml"),
        ("--geometry-seal", "head-camera-geometry.json"),
        ("--controller-config", "ros2_controllers.yaml"),
        ("--urdf", "so101.urdf"),
        ("--frame-contract", "frame-contract.json"),
    ):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        inputs[flag] = path
    return inputs


def test_measure_frame_contract_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-frame-contract"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_frame_contract_refuses_a_missing_input_and_an_existing_output(
    tmp_path: Path, capsys
) -> None:
    import yaml

    plugin = tmp_path / "mujoco_plugins.yaml"
    output = tmp_path / "measurement"
    arguments = [
        "measure-frame-contract",
        "--plugin-config",
        str(plugin),
        "--output-dir",
        str(output),
    ]
    assert main(arguments) == 2
    assert "no such input" in capsys.readouterr().err

    plugin.write_text(yaml.safe_dump(TRANSPORT_PLUGIN_CONFIG, sort_keys=True), encoding="utf-8")
    output.mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_frame_contract_refuses_a_skew_document_that_is_not_there(
    tmp_path: Path, capsys
) -> None:
    inputs = _transport_inputs(tmp_path)
    rc = main(
        [
            "measure-frame-contract",
            "--plugin-config",
            str(inputs["--plugin-config"]),
            "--output-dir",
            str(inputs["--output-dir"]),
            "--skew-measurements",
            str(tmp_path / "absent.json"),
        ]
    )
    assert rc == 2
    assert "no such input" in capsys.readouterr().err


def test_measure_frame_contract_writes_the_declaration_and_returns_zero(
    tmp_path: Path, capsys
) -> None:
    inputs = _transport_inputs(tmp_path)
    rc = main(
        [
            "measure-frame-contract",
            "--plugin-config",
            str(inputs["--plugin-config"]),
            "--output-dir",
            str(inputs["--output-dir"]),
        ]
    )

    assert rc == 0
    document = json.loads((inputs["--output-dir"] / "frame-contract.json").read_text("utf-8"))
    assert document["frame_rate_hz"] == 10.0
    assert document["measured_here"] is False
    assert document["declared_by"]["sha256"]
    assert "FRAME_CONTRACT_DECLARED" in capsys.readouterr().out


def test_measure_frame_contract_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, capsys
) -> None:
    inputs = _transport_inputs(tmp_path, rate=5.0)
    rc = main(
        [
            "measure-frame-contract",
            "--plugin-config",
            str(inputs["--plugin-config"]),
            "--output-dir",
            str(inputs["--output-dir"]),
        ]
    )

    assert rc == 2
    assert "CAL_FRAME_CONTRACT_CONTRADICTORY" in capsys.readouterr().err


def test_measure_skew_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-skew"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_skew_refuses_a_missing_input_and_an_existing_output(tmp_path: Path, capsys) -> None:
    arguments = ["measure-skew"]
    for flag, name in (
        ("--scene", "scene.xml"),
        ("--geometry-seal", "seal.json"),
        ("--plugin-config", "mujoco_plugins.yaml"),
        ("--controller-config", "ros2_controllers.yaml"),
        ("--urdf", "so101.urdf"),
        ("--frame-contract", "frame-contract.json"),
        ("--output-dir", "measurement"),
    ):
        arguments += [flag, str(tmp_path / name)]
    assert main(arguments) == 2
    assert "no such input" in capsys.readouterr().err

    for flag, name in (
        ("--scene", "scene.xml"),
        ("--geometry-seal", "seal.json"),
        ("--plugin-config", "mujoco_plugins.yaml"),
        ("--controller-config", "ros2_controllers.yaml"),
        ("--urdf", "so101.urdf"),
        ("--frame-contract", "frame-contract.json"),
    ):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    (tmp_path / "measurement").mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_skew_hands_the_flight_to_the_library(tmp_path: Path, monkeypatch, capsys) -> None:
    """The CLI parses and validates; the capture itself belongs to the library module."""

    from so101_demo.act.head_search import transport_measurement as measurement
    inputs = _transport_inputs(tmp_path)
    arguments = ["measure-skew"]
    for flag, path in inputs.items():
        arguments += [flag, str(path)]
    arguments += ["--frames", "5", "--timeout-s", "3.5"]
    seen = {}

    def fake_write(**request):
        seen.update(request)
        return {
            "measurement": {
                "phase": "skew_measurements",
                "sha256": "0" * 64,
                "clock_resolution_s": 0.002,
                "samples": [{}] * 5,
                "observed": {"max_skew_s": 0.004, "inside_cap": True},
                "capture": {"achieved_rate_hz": 9.98},
            },
            "receipt": {
                "status": "MEASURED",
                "sample_count": 5,
                "measurement_sha256": "0" * 64,
                "observed": {"max_skew_s": 0.004},
            },
        }

    monkeypatch.setattr(measurement, "write_transport_measurements", fake_write)
    rc = main(arguments)

    assert rc == 0
    assert seen["mode"] == "skew"
    assert seen["frames"] == 5
    assert seen["timeout_s"] == 3.5
    assert seen["frame_contract_path"] == inputs["--frame-contract"]
    assert seen["transport"] is not None
    assert "SKEW_MEASURED" in capsys.readouterr().out


def test_measure_skew_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.act.head_search import transport_measurement as measurement
    inputs = _transport_inputs(tmp_path)
    arguments = ["measure-skew"]
    for flag, path in inputs.items():
        arguments += [flag, str(path)]

    def refuse(**request):
        raise measurement.CalibrationInputsRefused(
            measurement.CAL_SKEW_TRANSPORT_UNREACHABLE, "the transport never published a frame"
        )

    monkeypatch.setattr(measurement, "write_transport_measurements", refuse)

    assert main(arguments) == 2
    assert "CAL_SKEW_TRANSPORT_UNREACHABLE" in capsys.readouterr().err
