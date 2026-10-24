"""The deadband candidate and camera measurement subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from head_search_calibration_cli_support import _deadband_inputs
import pytest

from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
)
from so101_demo.cli.head_search_calibration import main


def _deadband_arguments(inputs: dict, output: Path) -> list:
    return [
        "measure-deadband-candidates",
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--production-search-config",
        str(inputs["production"]),
        "--controller-config",
        str(inputs["controllers"]),
        "--frozen-candidate",
        str(inputs["frozen"]),
        "--weights",
        str(inputs["weights"]),
        "--output-dir",
        str(output),
        "--candidate",
        "18",
        "--candidate",
        "2",
    ]


def test_measure_deadband_candidates_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-deadband-candidates"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "deadband").exists()


def test_measure_deadband_candidates_refuses_a_missing_input_an_existing_output_and_no_candidate(
    tmp_path: Path, capsys
) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "deadband"
    arguments = _deadband_arguments(inputs, output)

    assert main([arguments[0], "--scene", str(tmp_path / "absent.xml"), *arguments[3:]]) == 2
    assert "no such input" in capsys.readouterr().err

    output.mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err

    output.rmdir()
    assert main(arguments[:-4]) == 2  # the two declared candidates are the last four arguments
    assert "--candidate" in capsys.readouterr().err


def test_measure_deadband_candidates_hands_the_flight_to_the_library(tmp_path: Path, capsys, monkeypatch) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "deadband"
    from so101_demo.act.head_search.deadband_measurement import writer as measurement_writer

    class Plant:
        """A yaw-only plant whose cup sits at the principal point once the neck reaches the anchor."""

        def __init__(self, request) -> None:
            self.request = request
            self.simulation_timestep_s = 0.002
            self.yaw_rad = 0.0
            self.velocity_rad_s = 0.0
            self.time_s = 0.0
            self.stops = 0

        @property
        def frame_stamp_ns(self) -> int:
            return int(round(self.time_s * 1e9))

        def settle_to(self, target_rad: float) -> dict:
            start, rad = self.time_s, self.yaw_rad
            self.yaw_rad, self.time_s = float(target_rad), self.time_s + 0.01
            self.stops += 1
            return {
                "target_rad": float(target_rad),
                "start_rad": rad,
                "sim_start_s": start,
                "sim_end_s": self.time_s,
                "steps": 5,
                "settle_s": self.time_s - start,
                "settled": True,
                "reached": True,
                "final_velocity_rad_s": 0.0,
                "final_position_error_rad": 0.0,
                "quiet_steps": 5,
            }

        def render_frame(self):
            return {"yaw_rad": self.yaw_rad}

        def optical_geometry(self) -> dict:
            return {
                "k": (415.69219381653056, 0.0, 320.0, 0.0, 415.69219381653056, 240.0, 0.0, 0.0, 1.0),
                "distortion": (0.0, 0.0, 0.0, 0.0, 0.0),
                "rotation_optical_to_base": (
                    (-1.0, 0.0, 0.0),
                    (0.0, 0.6, -0.8),
                    (0.0, -0.8, -0.6),
                ),
            }

    class Detector:
        """A cup that sits on the principal point: every candidate locks on the first frame."""

        def __init__(self, plant) -> None:
            self.plant = plant

        def reset(self) -> None:
            pass

        def __call__(self, image, stamp_ns):
            return [
                {
                    "xyxy": (270.0, 190.0, 370.0, 290.0),
                    "confidence": 0.9,
                    "class_id": 0,
                    "track_id": "head-cup-0",
                }
            ]

    monkeypatch.setattr(measurement_writer, "MujocoClosedLoopPlant", Plant)
    monkeypatch.setattr(
        measurement_writer,
        "build_production_head_detector",
        lambda **kwargs: Detector(None),
    )

    assert main(_deadband_arguments(inputs, output)) == 0

    printed = capsys.readouterr().out
    assert "DEADBAND_CANDIDATES_MEASURED" in printed
    assert "candidates=2" in printed
    assert f"output_dir={output}" in printed
    document = json.loads((output / "deadband-candidates.json").read_text(encoding="utf-8"))
    assert [record["center_deadband_px"] for record in document["records"]] == [18.0, 2.0]
    assert all(record["longest_locked_run_frames"] >= 3 for record in document["records"])
    assert all(record["direction_reversals"] == 0 for record in document["records"])
    assert document["detector_operating_point"] == {"min_confidence": 0.25, "iou": 0.5}
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["document_sha256"] == document["sha256"]
    assert receipt["anchor_names"] == ["left"]
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False


def test_measure_deadband_candidates_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "deadband"
    from so101_demo.act.head_search.deadband_measurement import contracts as measurement_contracts
    from so101_demo.act.head_search.deadband_measurement import writer as measurement_writer

    def refuse(request):
        raise measurement_contracts.CalibrationDeadbandMeasurementRefused(
            measurement_contracts.CAL_DEADBAND_CUP_LOST, "the detector found no cup at all"
        )

    monkeypatch.setattr(measurement_writer, "MujocoClosedLoopPlant", refuse)
    monkeypatch.setattr(measurement_writer, "build_production_head_detector", lambda **kwargs: None)

    assert main(_deadband_arguments(inputs, output)) == 2
    assert measurement_contracts.CAL_DEADBAND_CUP_LOST in capsys.readouterr().err


def _camera_arguments(inputs: dict, output: Path, *, safety_margin=None) -> list:
    arguments = [
        "measure-camera",
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--production-search-config",
        str(inputs["production"]),
        "--controller-config",
        str(inputs["controllers"]),
        "--frozen-candidate",
        str(inputs["frozen"]),
        "--weights",
        str(inputs["weights"]),
        "--output-dir",
        str(output),
        "--anchor",
        "left",
        "--device",
        "cuda",
    ]
    if safety_margin is not None:
        arguments += ["--safety-margin-declaration", str(safety_margin)]
    return arguments


class _CameraPlant:
    """A yaw-only plant that holds every commanded pose; the entry's own plant is stubbed in here."""

    def __init__(self, request) -> None:
        self.request = request
        self.simulation_timestep_s = 0.002
        self.yaw_rad = float(request["start_rad"])
        self.velocity_rad_s = 0.0
        self.time_s = 0.0
        self.commands: list[float] = []

    def settle_to(self, target_rad: float) -> dict:
        start, rad = self.time_s, self.yaw_rad
        self.commands.append(float(target_rad))
        self.yaw_rad, self.time_s = float(target_rad), self.time_s + 0.01
        return {
            "target_rad": float(target_rad),
            "start_rad": rad,
            "sim_start_s": start,
            "sim_end_s": self.time_s,
            "steps": 5,
            "settle_s": self.time_s - start,
            "settled": True,
            "reached": True,
            "final_velocity_rad_s": 0.0,
            "final_position_error_rad": 0.0,
            "quiet_steps": 5,
        }

    @property
    def frame_stamp_ns(self) -> int:
        return int(round(self.time_s * 1e9))

    def render_frame(self):
        return {"yaw_rad": self.yaw_rad, "frame": self.time_s}

    def optical_geometry(self) -> dict:
        return {
            "k": (415.69219381653056, 0.0, 320.0, 0.0, 415.69219381653056, 240.0, 0.0, 0.0, 1.0),
            "distortion": (0.0, 0.0, 0.0, 0.0, 0.0),
            "rotation_optical_to_base": ((-1.0, 0.0, 0.0), (0.0, 0.6, -0.8), (0.0, -0.8, -0.6)),
        }

    def close(self) -> None:
        pass


class _CameraDetector:
    """One cup whose centre wobbles by a declared pixel offset: a real, non-zero spread."""

    #: every pose is held for three whole periods of this cycle, so every pose measures the same spread
    OFFSETS_PX = (0.0, 1.0, 1.0, 0.0)

    def __init__(self, plant) -> None:
        self.plant = plant
        self.calls = 0

    def reset(self) -> None:
        self.calls = 0

    def __call__(self, image, stamp_ns):
        column = 320.0 + self.OFFSETS_PX[self.calls % len(self.OFFSETS_PX)]
        self.calls += 1
        return [
            {
                "xyxy": (column - 50.0, 190.0, column + 50.0, 290.0),
                "confidence": 0.9,
                "class_id": 0,
                "track_id": "head-cup-0",
            }
        ]


def test_measure_camera_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-camera"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "camera").exists()


def test_measure_camera_refuses_a_missing_input_and_an_existing_output(tmp_path: Path, capsys) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "camera"
    arguments = _camera_arguments(inputs, output)

    assert main([arguments[0], "--scene", str(tmp_path / "absent.xml"), *arguments[3:]]) == 2
    assert "no such input" in capsys.readouterr().err

    output.mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_camera_hands_the_flight_to_the_library_and_refuses_an_undeclared_margin(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """The measured jitter is written; the undeclared safety margin is recorded and refused, never made up."""

    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "camera"
    from so101_demo.act.head_search.camera_measurement import (
        declarations as measurement_declarations,
    )
    from so101_demo.act.head_search.camera_measurement import writer as measurement_writer

    monkeypatch.setattr(measurement_writer, "MujocoClosedLoopPlant", _CameraPlant)
    monkeypatch.setattr(
        measurement_writer, "build_production_head_detector", lambda **kwargs: _CameraDetector(None)
    )

    assert main(_camera_arguments(inputs, output)) == 2

    captured = capsys.readouterr()
    assert measurement_declarations.CAL_CAMERA_SAFETY_MARGIN_UNDECLARED in captured.err
    assert "CAMERA_MEASUREMENTS_MEASURED" in captured.out

    document = json.loads((output / "camera-measurements.json").read_text(encoding="utf-8"))
    assert document["safety_margin_px"] is None
    assert document["horizontal_fov_rad"] == 1.3121067481206794
    assert document["image_width_px"] == 640
    assert document["image_height_px"] == 480
    # twelve frames per pose is three whole periods of the wobble cycle
    assert document["centre_jitter_px"] == pytest.approx(
        measurement_declarations.spread(_CameraDetector.OFFSETS_PX * 3)["std"]
    )
    assert document["centre_jitter_rad"] == pytest.approx(
        document["centre_jitter_px"] * 1.3121067481206794 / 640
    )
    assert document["frames_per_pose"] == 12
    assert document["pose_count"] == 3
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["document_sha256"] == document["sha256"]
    assert receipt["status"] == "MEASURED_WITH_REFUSED_FIELD"
    assert receipt["fields_refused"] == ["safety_margin_px"]
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False


def test_measure_camera_accepts_a_declared_safety_margin_and_returns_zero(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "camera"
    declaration = tmp_path / "camera-safety.json"
    declaration.write_text(json.dumps({"safety_margin_px": 4.0}), encoding="utf-8")
    from so101_demo.act.head_search.camera_measurement import (
        declarations as measurement_declarations,
    )
    from so101_demo.act.head_search.camera_measurement import writer as measurement_writer

    monkeypatch.setattr(measurement_writer, "MujocoClosedLoopPlant", _CameraPlant)
    monkeypatch.setattr(
        measurement_writer, "build_production_head_detector", lambda **kwargs: _CameraDetector(None)
    )

    assert main(_camera_arguments(inputs, output, safety_margin=declaration)) == 0

    captured = capsys.readouterr()
    assert "CAMERA_MEASUREMENTS_MEASURED" in captured.out
    assert measurement_declarations.CAL_CAMERA_SAFETY_MARGIN_UNDECLARED not in captured.err

    document = json.loads((output / "camera-measurements.json").read_text(encoding="utf-8"))
    assert document["safety_margin_px"] == 4.0
    assert document["safety_margin"]["measured_here"] is False
    assert document["safety_margin"]["declared_by"]["path"] == str(declaration)
    assert document["refusals"] == []


def test_measure_camera_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "camera"
    from so101_demo.act.head_search.camera_measurement import (
        declarations as measurement_declarations,
    )
    from so101_demo.act.head_search.camera_measurement import writer as measurement_writer

    def refuse(request):
        raise measurement_declarations.CalibrationCameraMeasurementRefused(
            measurement_declarations.CAL_CAMERA_CUP_LOST, "the detector found no cup in any frame"
        )

    monkeypatch.setattr(measurement_writer, "MujocoClosedLoopPlant", refuse)
    monkeypatch.setattr(measurement_writer, "build_production_head_detector", lambda **kwargs: None)

    assert main(_camera_arguments(inputs, output)) == 2
    assert measurement_declarations.CAL_CAMERA_CUP_LOST in capsys.readouterr().err
