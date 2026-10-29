"""The workspace projection and fine correction subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from head_search_calibration_cli_support import _fine_correction_inputs

from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
)
from so101_demo.cli.head_search_calibration import main


def test_measure_workspace_projection_needs_its_declared_inputs(capsys) -> None:
    assert main(["measure-workspace-projection"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_workspace_projection_refuses_a_missing_input_and_an_existing_output(
    tmp_path: Path, capsys
) -> None:
    declared = {
        "--scene": tmp_path / "head_search_scene.xml",
        "--geometry-seal": tmp_path / "head-camera-geometry.json",
        "--geometry-contract": tmp_path / "head-camera-geometry-contract.json",
        "--output-dir": tmp_path / "measurement",
    }
    arguments = ["measure-workspace-projection"]
    for flag, path in declared.items():
        arguments += [flag, str(path)]
    assert main(arguments) == 2
    assert "no such input" in capsys.readouterr().err

    for flag, path in declared.items():
        if flag != "--output-dir":
            path.write_text("{}", encoding="utf-8")
    declared["--output-dir"].mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_workspace_projection_hands_the_flight_to_the_library(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The CLI is a parser and a validator: the projection itself is the library module's."""

    from so101_demo.act.head_search.workspace_projection import (
        writer as head_search_workspace_projection_writer,
    )

    inputs = {}
    for flag, name in (
        ("--scene", "head_search_scene.xml"),
        ("--geometry-seal", "head-camera-geometry.json"),
        ("--geometry-contract", "head-camera-geometry-contract.json"),
    ):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        inputs[flag] = path
    output = tmp_path / "measurement"
    seen = {}

    def fake_write(**arguments):
        seen.update(arguments)
        return {
            "receipt": {
                "top_px": 191.699852915671,
                "bottom_px": 272.6768492617673,
                "pose_count": 3,
                "point_count": 120,
                "union_px": [191.699852915671, 272.6768492617673],
                "intersection_px": [192.79306238636892, 266.49194356287984],
                "chosen_step_rad": 0.6560533740603397,
                "step_source": "phase_2_selection_rule",
            }
        }

    monkeypatch.setattr(
        head_search_workspace_projection_writer, "write_head_search_workspace_projection", fake_write
    )
    arguments = ["measure-workspace-projection"]
    for flag, path in inputs.items():
        arguments += [flag, str(path)]
    arguments += ["--output-dir", str(output)]

    assert main(arguments) == 0

    printed = capsys.readouterr().out
    assert "WORKSPACE_PROJECTION_PRODUCED top_px=191.699852915671" in printed
    assert "poses=3" in printed and "points=120" in printed
    assert "step=0.6560533740603397 (phase_2_selection_rule)" in printed
    assert seen["coarse_step_rad"] is None, "the step is phase 2's own choice unless it is declared"
    assert seen["scene_path"] == inputs["--scene"]
    assert seen["geometry_seal_path"] == inputs["--geometry-seal"]
    assert seen["geometry_contract_path"] == inputs["--geometry-contract"]
    assert seen["output_dir"] == output
    assert "measure-workspace-projection" in seen["command"]

    # a run that holds its own plan declares the step it was receipted at, and the entry passes it on
    output_declared = tmp_path / "measurement-declared"
    arguments_declared = [*arguments[:-2], "--coarse-step-rad", "0.3", "--output-dir", str(output_declared)]
    assert main(arguments_declared) == 0
    assert seen["coarse_step_rad"] == 0.3
    assert seen["output_dir"] == output_declared


def test_measure_workspace_projection_reports_the_library_refusal(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.act.head_search.workspace_projection import (
        writer as head_search_workspace_projection_writer,
    )
    from so101_demo.act.head_search.workspace_projection.projection import (
        CAL_PROJECTION_POSE_SET_AMBIGUOUS,
        CalibrationWorkspaceProjectionRefused,
    )

    inputs = {}
    for flag, name in (
        ("--scene", "head_search_scene.xml"),
        ("--geometry-seal", "head-camera-geometry.json"),
        ("--geometry-contract", "head-camera-geometry-contract.json"),
    ):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        inputs[flag] = path

    def fake_write(**_arguments):
        raise CalibrationWorkspaceProjectionRefused(
            CAL_PROJECTION_POSE_SET_AMBIGUOUS, "the in-domain stop set depends on the coarse step"
        )

    monkeypatch.setattr(
        head_search_workspace_projection_writer, "write_head_search_workspace_projection", fake_write
    )
    arguments = ["measure-workspace-projection"]
    for flag, path in inputs.items():
        arguments += [flag, str(path)]
    arguments += ["--output-dir", str(tmp_path / "measurement")]

    assert main(arguments) == 2
    assert CAL_PROJECTION_POSE_SET_AMBIGUOUS in capsys.readouterr().err


def _fine_correction_arguments(inputs: dict, output: Path, *extra: str) -> list:
    return [
        "measure-fine-correction-episodes",
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
        "--dataset-config",
        str(inputs["dataset_config"]),
        "--scenario-partitions",
        str(inputs["partitions"]),
        "--output-dir",
        str(output),
        *extra,
    ]


class _FineCorrectionPlant:
    """A yaw-only plant whose cup sits on the principal point: every episode locks immediately."""

    def __init__(self, request) -> None:
        self.request = request
        self.simulation_timestep_s = 0.002
        self.yaw_rad = 0.0
        self.velocity_rad_s = 0.0
        self.time_s = 0.0
        self.cup_position_m = [-0.08, -0.28, 0.165]
        self.arm_drift_rad = 0.0

    @property
    def frame_stamp_ns(self) -> int:
        return int(round(self.time_s * 1e9))

    def settle_to(self, target_rad: float) -> dict:
        start, rad = self.time_s, self.yaw_rad
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


def _patch_fine_correction_flight(monkeypatch, *, blind_seeds=()):
    """Stub the three heavy seams of the flight: the scene preparation, the plant and the detector.

    The flight builds its detector once, before any plant exists, so the stubbed detector reads the plant
    the stubbed plant factory last produced rather than being handed one.
    """

    from so101_demo.act.head_search import fine_correction_episodes as measurement
    from so101_demo.act.head_search.fine_correction_episodes import writer as measurement_writer

    state = {"plant": None}

    class Plant(_FineCorrectionPlant):
        def __init__(self, request) -> None:
            super().__init__(request)
            state["plant"] = self

    class Detector:
        """One frame with the cup 30 px right of the principal point, then the cup held centred.

        The first frame makes the production controller perform exactly one fine correction; the frames
        after it are the three consecutive centred frames the lock rule needs.
        """

        def __init__(self) -> None:
            self.calls = 0

        def reset(self) -> None:
            self.calls = 0

        def __call__(self, image, stamp_ns):
            plant = state["plant"]
            if int(plant.request["seed"]) in blind_seeds:
                return []
            self.calls += 1
            column = 350.0 if self.calls == 1 else 320.0
            return [
                {
                    "xyxy": (column - 50.0, 190.0, column + 50.0, 290.0),
                    "confidence": 0.9,
                    "class_id": 0,
                    "track_id": "head-cup-0",
                }
            ]

    monkeypatch.setattr(measurement_writer, "prepare_episode_scene", lambda **request: {"prepared": True})
    monkeypatch.setattr(measurement_writer, "MujocoEpisodePlant", Plant)
    monkeypatch.setattr(measurement_writer, "build_production_head_detector", lambda **kwargs: Detector())
    return measurement


def test_measure_fine_correction_episodes_needs_its_declared_inputs(capsys) -> None:
    assert main(["measure-fine-correction-episodes"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_fine_correction_episodes_refuses_a_missing_input_and_an_existing_output(
    tmp_path: Path, capsys
) -> None:
    inputs = _fine_correction_inputs(tmp_path)
    output = tmp_path / "episodes"
    arguments = _fine_correction_arguments(inputs, output)

    missing = list(arguments)
    missing[missing.index("--weights") + 1] = str(tmp_path / "absent.pt")
    assert main(missing) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err

    output.mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_fine_correction_episodes_hands_the_flight_to_the_library(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _fine_correction_inputs(tmp_path)
    output = tmp_path / "episodes"
    _patch_fine_correction_flight(monkeypatch)

    assert main(_fine_correction_arguments(inputs, output)) == 0

    printed = capsys.readouterr().out
    assert "FINE_CORRECTION_EPISODES_MEASURED" in printed
    assert "episodes=2" in printed
    assert "succeeded=2" in printed
    assert "refused=0" in printed
    assert "split=held_out_evaluation" in printed
    assert f"output_dir={output}" in printed
    document = json.loads(
        (output / "fine-correction-episodes.json").read_text(encoding="utf-8")
    )
    assert [record["episode_id"] for record in document["records"]] == [
        "held_out_evaluation-800000",
        "held_out_evaluation-800001",
    ]
    assert all(record["split"] == "held_out_evaluation" for record in document["records"])
    assert document["succeeded_count"] == 2
    assert document["refused_count"] == 0
    assert document["split_declaration"]["calibration_seeds_used"] == []
    assert document["anchors"] == ["left"]
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["document_sha256"] == document["sha256"]
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False
    assert receipt["mujoco_neck_commanded"] is True


def test_measure_fine_correction_episodes_reports_a_refused_episode_and_still_writes_the_document(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _fine_correction_inputs(tmp_path)
    output = tmp_path / "episodes"
    _patch_fine_correction_flight(monkeypatch, blind_seeds=(800001,))

    assert main(_fine_correction_arguments(inputs, output)) == 0

    captured = capsys.readouterr()
    assert "succeeded=1" in captured.out
    assert "refused=1" in captured.out
    assert "CAL_FINE_EPISODE_CUP_NOT_FOUND" in captured.err


def test_measure_fine_correction_episodes_refuses_a_calibration_seed(tmp_path: Path, capsys) -> None:
    inputs = _fine_correction_inputs(tmp_path)
    output = tmp_path / "episodes"

    assert main(_fine_correction_arguments(inputs, output, "--seed", "700000")) == 2
    assert "CAL_FINE_EPISODE_SPLIT_LEAK" in capsys.readouterr().err
    assert not output.exists()


def test_measure_fine_correction_episodes_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    from so101_demo.act.head_search.fine_correction_episodes import (
        contracts as measurement_contracts,
    )
    from so101_demo.act.head_search.fine_correction_episodes import writer as measurement_writer

    inputs = _fine_correction_inputs(tmp_path)
    output = tmp_path / "episodes"
    _patch_fine_correction_flight(monkeypatch)

    def refuse(**request):
        raise measurement_contracts.CalibrationFineCorrectionRefused(
            measurement_contracts.CAL_FINE_EPISODE_OUT_OF_CORRIDOR, "the loop left the declared corridor"
        )

    monkeypatch.setattr(measurement_writer, "prepare_episode_scene", refuse)

    assert main(_fine_correction_arguments(inputs, output)) == 2
    assert measurement_contracts.CAL_FINE_EPISODE_OUT_OF_CORRIDOR in capsys.readouterr().err
