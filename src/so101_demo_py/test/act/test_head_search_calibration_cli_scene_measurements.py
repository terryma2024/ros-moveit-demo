"""The coarse step, MuJoCo, search timing and deadband plant subcommands."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from head_search_calibration_cli_support import (
    TIMING_CONTROLLERS,
    _deadband_inputs,
    _fine_correction_inputs,
)
import pytest

from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
)
from so101_demo.cli.head_search_calibration import main


def test_measure_coarse_step_needs_its_declared_inputs(tmp_path, capsys) -> None:
    assert main(["measure-coarse-step"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "measurement").exists()


def test_measure_coarse_step_refuses_a_missing_input_and_an_existing_output(tmp_path, capsys) -> None:
    declared = {
        "--geometry-seal": tmp_path / "geometry-seal.json",
        "--head-dataset": tmp_path / "head-dataset.json",
        "--dataset-config": tmp_path / "head_camera_yolo_seg.yaml",
        "--weights": tmp_path / "C.pt",
        "--frozen-candidate": tmp_path / "frozen-c.json",
        "--output-dir": tmp_path / "measurement",
    }
    arguments = ["measure-coarse-step"]
    for flag, path in declared.items():
        arguments += [flag, str(path)]
    assert main(arguments) == 2
    assert "no such input" in capsys.readouterr().err

    for flag, path in declared.items():
        if flag == "--output-dir":
            continue
        path.write_text("{}", encoding="utf-8")
    declared["--output-dir"].mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_coarse_step_parses_and_hands_the_flight_to_the_library(tmp_path, monkeypatch, capsys) -> None:
    """The CLI is a parser and a validator: the measurement itself is the library module's."""

    from so101_demo.act.head_search_coarse_step_measurement import measurement as coarse_step_sweep

    input_paths = {}
    for flag, name in (
        ("--geometry-seal", "geometry-seal.json"),
        ("--head-dataset", "head-dataset.json"),
        ("--dataset-config", "head_camera_yolo_seg.yaml"),
        ("--weights", "C.pt"),
        ("--frozen-candidate", "frozen-c.json"),
    ):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        input_paths[flag] = path
    output = tmp_path / "measurement"
    seen = {}

    def fake_measure(**arguments):
        seen.update(arguments)
        return {"receipt": {"chosen_coarse_step_rad": 0.6560533740603397, "scene_count": 200,
                            "candidate_count": 6, "passes": 2}}

    monkeypatch.setattr(
        coarse_step_sweep, "measure_coarse_step_val_sweep", fake_measure
    )
    arguments = ["measure-coarse-step"]
    for flag, path in input_paths.items():
        arguments += [flag, str(path)]
    arguments += ["--output-dir", str(output), "--passes", "2", "--scene-limit", "8"]

    assert main(arguments) == 0

    assert seen["geometry_seal_path"] == input_paths["--geometry-seal"]
    assert seen["dataset_manifest_path"] == input_paths["--head-dataset"]
    assert seen["dataset_config_path"] == input_paths["--dataset-config"]
    assert seen["weights_path"] == input_paths["--weights"]
    assert seen["frozen_candidate_path"] == input_paths["--frozen-candidate"]
    assert seen["output_dir"] == output
    assert seen["passes"] == 2
    assert seen["scene_limit"] == 8
    assert seen["command"].startswith(
        "ros2 run so101_demo_py so101_head_search_calibration measure-coarse-step"
    )
    assert "COARSE_STEP_MEASURED 0.6560533740603397" in capsys.readouterr().out


def _mujoco_inputs(tmp_path: Path) -> dict:
    """A tiny sealed scene and the geometry seal that pins it: the CLI's own end-to-end fixtures."""

    import hashlib

    scene = tmp_path / "head_search_scene.xml"
    scene.write_text(
        '<mujoco model="fixture">\n  <option timestep="0.002" gravity="0 0 -9.81"/>\n</mujoco>\n',
        encoding="utf-8",
    )
    seal = tmp_path / "head-camera-geometry.json"
    seal.write_text(
        json.dumps({"source_digests": {"scene_sha256": hashlib.sha256(scene.read_bytes()).hexdigest()}}),
        encoding="utf-8",
    )
    return {"scene": scene, "seal": seal}


def test_measure_mujoco_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-mujoco"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "measurement").exists()


def test_measure_mujoco_refuses_a_missing_input_and_an_existing_output(tmp_path: Path, capsys) -> None:
    inputs = _mujoco_inputs(tmp_path)
    arguments = [
        "measure-mujoco",
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--output-dir",
        str(tmp_path / "measurement"),
    ]
    assert main([arguments[0], "--scene", str(tmp_path / "absent.xml"), *arguments[3:]]) == 2
    assert "no such input" in capsys.readouterr().err

    (tmp_path / "measurement").mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_mujoco_refuses_a_scene_nothing_seals(tmp_path: Path, capsys) -> None:
    inputs = _mujoco_inputs(tmp_path)

    assert (
        main(
            [
                "measure-mujoco",
                "--scene",
                str(inputs["scene"]),
                "--output-dir",
                str(tmp_path / "measurement"),
            ]
        )
        == 2
    )
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "measurement").exists()


def test_measure_mujoco_produces_the_document_the_run_declares(tmp_path: Path, capsys) -> None:
    inputs = _mujoco_inputs(tmp_path)
    output = tmp_path / "measurement"

    assert (
        main(
            [
                "measure-mujoco",
                "--scene",
                str(inputs["scene"]),
                "--geometry-seal",
                str(inputs["seal"]),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )

    printed = capsys.readouterr().out
    assert "MUJOCO_TIMESTEP_PRODUCED 0.002" in printed
    document = json.loads((output / "mujoco-measurements.json").read_text(encoding="utf-8"))
    assert document["simulation_timestep_s"] == pytest.approx(0.002)
    assert document["path"] == str(output / "mujoco-measurements.json")
    assert document["mujoco_readback"] is False
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["measurement_sha256"] == document["sha256"]
    assert receipt["runtime_identity"]["motion_commanded"] is False


#: a minimal sealed-scene stand-in: a yaw hinge with a position actuator and the head camera, so the
#: installed entry's own sweep runs against a real MuJoCo model without a detector, a GPU or a renderer
TIMING_SCENE = """<mujoco model="timing-fixture">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="head_mount">
      <joint name="neck_yaw_joint" type="hinge" axis="0 0 1" damping="0.05" armature="0.001"/>
      <geom name="head_geom" type="box" size="0.05 0.05 0.05"/>
      <camera name="head_camera" pos="0 0 0.05" fovy="60" xyaxes="1 0 0 0 1 0"/>
    </body>
  </worldbody>
  <actuator>
    <position name="neck_yaw_joint" joint="neck_yaw_joint" kp="8" kv="0.6"
              forcelimited="false" ctrllimited="false"/>
  </actuator>
</mujoco>
"""


def _timing_inputs(tmp_path: Path) -> dict:
    """The four declared inputs of the sweep-timing measurement, with one sealed anchor."""

    scene = tmp_path / "head_search_scene.xml"
    scene.write_text(TIMING_SCENE, encoding="utf-8")
    seal = tmp_path / "head-camera-geometry.json"
    seal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "camera_name": "head_camera",
                "camera": {"camera_name": "head_camera", "parent_body": "head_mount", "width": 64, "height": 48},
                "image_width": 64,
                "image_height": 48,
                "horizontal_fov_rad": 1.3121067481206794,
                "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
                "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                "in_frame_matrix": {"default": {"neck_start_rad": 0.1}},
                "source_digests": {"scene_sha256": hashlib.sha256(scene.read_bytes()).hexdigest()},
            }
        ),
        encoding="utf-8",
    )
    production = tmp_path / "head_search_runtime.json"
    production.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "camera": {
                    "name": "head_camera",
                    "frame_id": "head_camera_frame",
                    "ray_origin_frame_id": "head_camera_frame",
                },
                "motion": {"settle_velocity_rad_s": 0.05, "goal_tolerance_rad": 0.05},
                "tracker": {"name": "bytetrack", "iou_threshold": 0.3},
                "values": {
                    "coarse_step_rad": 0.3,
                    "horizontal_fov_rad": 1.3121067481206794,
                    "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                    "max_age_s": 0.05,
                    "max_skew_s": 0.02,
                    "search_timeout_s": 12.0,
                    "center_deadband_px": 18.0,
                    "vertical_bounds_px": [11.0, 37.0],
                    "min_area_px2": 64.0,
                    "min_confidence": 0.4,
                    "tracking_iou": 0.3,
                    "max_fine_corrections": 4,
                    "max_fine_total_rad": 0.4,
                    "stop_velocity_rad_s": 0.05,
                    "min_bbox_aspect": 0.5,
                    "stop_latency_s": 0.06,
                    "submit_lead_s": 0.02,
                },
            }
        ),
        encoding="utf-8",
    )
    controllers = tmp_path / "ros2_controllers.yaml"
    controllers.write_text(TIMING_CONTROLLERS, encoding="utf-8")
    return {
        "scene": scene,
        "seal": seal,
        "production": production,
        "controllers": controllers,
    }


def _timing_arguments(inputs: dict, output: Path) -> list:
    return [
        "measure-search-timing",
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
    ]


def test_measure_search_timing_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-search-timing"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "sweep-timing").exists()


def test_measure_search_timing_refuses_a_missing_input_and_an_existing_output(
    tmp_path: Path, capsys
) -> None:
    inputs = _timing_inputs(tmp_path)
    output = tmp_path / "sweep-timing"
    arguments = _timing_arguments(inputs, output)

    assert main([arguments[0], "--scene", str(tmp_path / "absent.xml"), *arguments[3:]]) == 2
    assert "no such input" in capsys.readouterr().err

    output.mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_search_timing_sweeps_without_a_detector_and_invents_no_frame_age(
    tmp_path: Path, capsys
) -> None:
    inputs = _timing_inputs(tmp_path)
    output = tmp_path / "sweep-timing"

    assert main(_timing_arguments(inputs, output)) == 0

    printed = capsys.readouterr().out
    assert "SEARCH_TIMING_MEASURED" in printed
    assert "p99_frame_s=None" in printed
    document = json.loads((output / "search-timing.json").read_text(encoding="utf-8"))
    assert document["p99_settle_s"] > 0.0
    assert document["p99_frame_s"] is None
    assert document["stable_stop_count"] == 2
    assert document["time_base"] == "simulation"
    assert not (output / "frame-age-measurements.json").exists()
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["search_timing_sha256"] == document["sha256"]
    assert receipt["ros_nodes_started"] is False


def test_the_deadband_detector_wrapper_drives_the_production_head_detector() -> None:
    """The wrapper is called against the real `HeadRgbDetector`, with only its model port stubbed.

    `HeadRgbDetector.detect` takes the RGB array and its identity as keyword arguments and builds the
    detection frame itself; a wrapper that passed a frame positionally would only fail once a real model
    was loaded. This pins the call convention without a detector, a GPU or a weights file.
    """

    import numpy as np

    from so101_demo.act.head_search_deadband_measurement.plant import ProductionHeadDetector
    from so101_demo.adapters.act.detector import HeadRgbDetector
    from so101_demo.core.detection import DetectionBatch, DetectionCandidate

    def _cup_mask():
        mask = np.zeros((480, 640), dtype=bool)
        mask[190:290, 270:370] = True
        return mask

    class Port:
        """The model port `HeadRgbDetector` wraps: one cup, one instance, one frame."""

        def detect(self, frame, query):
            assert query.class_id == "plastic_cup"
            return DetectionBatch(
                model_id="selected",
                weights_sha256="a" * 64,
                runtime_device="cuda",
                inference_latency_ms=1.0,
                image_width=640,
                image_height=480,
                candidates=(
                    DetectionCandidate(
                        instance_id="i0",
                        class_id="plastic_cup",
                        confidence=0.9,
                        bbox_xyxy=(270.0, 190.0, 370.0, 290.0),
                        mask=_cup_mask(),
                        source_stamp_ns=frame.source_stamp_ns,
                        source_frame_id=frame.source_frame_id,
                        image_width=640,
                        image_height=480,
                    ),
                ),
            )

    head = HeadRgbDetector(
        Port(),
        model_id="selected",
        weights_sha256="a" * 64,
        tracking_iou=0.5,
        min_bbox_aspect=0.5,
    )
    wrapper = ProductionHeadDetector(
        head,
        session_id="session",
        attempt_id="attempt",
        frame_id="head_camera_frame",
    )
    image = np.zeros((480, 640, 3), dtype=np.uint8)

    found = wrapper(image, 1_000_000)
    assert [detection["track_id"] for detection in found] == ["head-cup-0"]
    assert tuple(found[0]["xyxy"]) == (270.0, 190.0, 370.0, 290.0)
    assert found[0]["confidence"] == 0.9
    assert found[0]["class_id"] == 0

    # the same cup in the next frame keeps its track, and a reset starts a new one
    assert [detection["track_id"] for detection in wrapper(image, 2_000_000)] == ["head-cup-0"]
    wrapper.reset()
    assert [detection["track_id"] for detection in wrapper(image, 3_000_000)] == ["head-cup-0"]


def test_the_real_mujoco_plant_places_the_anchor_cup_and_settles(tmp_path: Path) -> None:
    """The entry's own plant is built for real here, so a typo in its MuJoCo calls cannot hide.

    Only the plant is exercised - the renderer is not opened and no detector is loaded - but this is the
    code path the installed entry really runs, and it constructs the model, places the anchor's cup,
    commands the neck actuator, applies the declared settle rule and reads the camera's own geometry.
    """

    from so101_demo.act.head_search_deadband_measurement import plant as measurement_plant

    inputs = _deadband_inputs(tmp_path)
    plant = measurement_plant.MujocoClosedLoopPlant(
        {
            "scene_path": str(inputs["scene"]),
            "camera_name": "head_camera",
            "image_width": 640,
            "image_height": 48,
            "fovy_rad": 1.0471975511965976,
            "control_period_s": 0.002,
            "frame_period_s": 0.1,
            "max_settle_s": 5.0,
            "settle_consecutive_steps": 5,
            "settle_velocity_rad_s": 0.05,
            "goal_tolerance_rad": 0.05,
            "start_rad": 0.0,
            "cup_start_m": [-0.08, -0.28, 0.165],
            "cup_joint": "cup_free_joint",
            "cup_body": "cup",
        }
    )
    assert plant.simulation_timestep_s == 0.002
    assert plant.yaw_rad == 0.0
    assert plant.cup_position_m == [-0.08, -0.28, 0.165]

    stop = plant.settle_to(0.0)
    assert stop["settled"] is True and stop["reached"] is True
    assert math.isclose(stop["settle_s"], stop["steps"] * 0.002, rel_tol=0.0, abs_tol=1e-12)
    assert plant.time_s > 0.0
    assert plant.frame_stamp_ns == int(round(plant.time_s * 1e9))

    geometry = plant.optical_geometry()
    assert geometry["k"][2] == 320.0 and geometry["k"][5] == 24.0
    assert geometry["k"][0] > 0.0
    rotation = geometry["rotation_optical_to_base"]
    assert len(rotation) == 3 and all(len(row) == 3 for row in rotation)
    plant.close()


def test_the_real_episode_plant_captures_the_prepared_cup_after_it_enters_the_scene(
    tmp_path: Path,
) -> None:
    """The prepared-cup capture has to happen *after* the prepared state is in the model.

    The real run's first document reported a 0.066-0.140 m drift for every episode: the capture was taken
    before `mj_forward`, so it recorded the anchor placement the base plant had put the cup at instead of
    the one the dataset preparation had. This builds the real plant on the fixture scene, hands it a
    prepared state that moves the cup, and pins which position is reported as the prepared one.
    """

    import mujoco

    from so101_demo.act.head_search_fine_correction_episodes.scene import MujocoEpisodePlant

    inputs = _fine_correction_inputs(tmp_path)
    request = {
        "scene_path": str(inputs["scene"]),
        "camera_name": "head_camera",
        "image_width": 640,
        "image_height": 480,
        "fovy_rad": 1.0471975511965976,
        "control_period_s": 0.002,
        "frame_period_s": 0.1,
        "max_settle_s": 5.0,
        "settle_consecutive_steps": 5,
        "settle_velocity_rad_s": 0.05,
        "goal_tolerance_rad": 0.05,
        "start_rad": 0.0,
        "cup_start_m": [-0.08, -0.28, 0.165],
        "cup_joint": "cup_free_joint",
        "cup_body": "cup",
    }
    plain = MujocoEpisodePlant(request)
    assert plain.prepared_cup_position_m == [-0.08, -0.28, 0.165]
    prepared_cup = [0.05, -0.30, 0.165]
    joint = mujoco.mj_name2id(plain._model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    address = int(plain._model.jnt_qposadr[joint])
    state = {
        "qpos": [float(value) for value in plain._data.qpos],
        "qvel": [0.0] * int(plain._model.nq),
        "cam_pos": [[float(value) for value in row] for row in plain._model.cam_pos],
        "mat_rgba": [[float(value) for value in row] for row in plain._model.mat_rgba],
    }
    state["qpos"][address : address + 3] = prepared_cup
    plain.close()

    plant = MujocoEpisodePlant({**request, "scene_state": state})

    assert plant.prepared_cup_position_m == pytest.approx(prepared_cup)
    assert plant.cup_position_m == pytest.approx(prepared_cup)
    assert plant.prepared_cup_position_m != request["cup_start_m"]
    plant.close()
