"""The selection rule, operating point, ownership check and run entry subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from head_search_calibration_cli_support import _run_arguments

from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
)
from so101_demo.cli.head_search_calibration import main


def _rule_inputs(tmp_path: Path) -> dict:
    """The sealed production config the rule's grid comes from, and two brand-new directories."""

    config = tmp_path / "head_search_runtime.json"
    config.write_text(
        json.dumps(
            {
                "values": {
                    "min_confidence": 0.4,
                    "tracking_iou": 0.3,
                    "min_bbox_aspect": 0.5,
                    "min_area_px2": 64.0,
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "--production-search-config": config,
        "--measurements-output-dir": tmp_path / "operating-point-20260101T000000Z",
        "--output-dir": tmp_path / "rules",
    }


def test_measure_selection_rule_refuses_missing_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-selection-rule", "--output-dir", str(tmp_path / "rules")]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_selection_rule_refuses_a_measurement_directory_that_already_exists(
    tmp_path: Path, capsys
) -> None:
    inputs = _rule_inputs(tmp_path)
    Path(inputs["--measurements-output-dir"]).mkdir()
    arguments = ["measure-selection-rule"]
    for flag, value in inputs.items():
        arguments += [flag, str(value)]
    assert main(arguments) == 2
    assert "CAL_RULE_AFTER_MEASUREMENT" in capsys.readouterr().err


def test_measure_selection_rule_writes_the_two_rule_records(tmp_path: Path, capsys) -> None:
    inputs = _rule_inputs(tmp_path)
    arguments = ["measure-selection-rule"]
    for flag, value in inputs.items():
        arguments += [flag, str(value)]
    assert main(arguments) == 0
    output = capsys.readouterr().out
    assert "SELECTION_RULE_RECORDED" in output
    assert "points=18" in output
    head = json.loads((Path(inputs["--output-dir"]) / "selection-rule.json").read_text())
    task = json.loads((Path(inputs["--output-dir"]) / "selection-rule-task.json").read_text())
    assert head["domain"] == "head"
    assert task["domain"] == "task"
    assert head["measurements_admitted"] == 0
    assert head["selection_splits"] == ["val", "calibration"]


def _operating_point_inputs(tmp_path: Path) -> dict:
    """Every path the measurement entry requires, written as the sealed shape it verifies."""

    geometry = tmp_path / "head-camera-geometry.json"
    geometry.write_text(
        json.dumps(
            {
                "seal_sha256": "d" * 64,
                "camera_name": "head_camera",
                "horizontal_fov_rad": 1.31,
                "required_search_domain_rad": [-0.3, 0.3],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    config = tmp_path / "head_camera_yolo_seg.yaml"
    config.write_text("scene: {}\n", encoding="utf-8")
    inputs = {
        "--geometry-seal": geometry,
        "--head-dataset": tmp_path / "head-dataset" / "dataset-manifest.json",
        "--task-dataset": tmp_path / "task-dataset" / "dataset-manifest.json",
        "--dataset-config": config,
        "--production-search-config": _rule_inputs(tmp_path)["--production-search-config"],
        "--episode-partitions": tmp_path / "head-search-scenario-partitions.json",
        "--selection-rule": tmp_path / "rules" / "selection-rule.json",
        "--task-selection-rule": tmp_path / "rules" / "selection-rule-task.json",
        "--frozen-candidate": tmp_path / "frozen-a.json",
        "--output-dir": tmp_path / "operating-point-20260101T000000Z",
    }
    for flag, value in inputs.items():
        if flag == "--output-dir":
            continue
        Path(value).parent.mkdir(parents=True, exist_ok=True)
        if not Path(value).exists():
            Path(value).write_text("{}\n", encoding="utf-8")
    return inputs


def _operating_point_arguments(tmp_path: Path, inputs: dict, *, weights: Path) -> list[str]:
    arguments = ["measure-operating-point"]
    for flag, value in inputs.items():
        arguments += [flag, str(value)]
    arguments += ["--weights-dir", str(weights)]
    return arguments


def test_measure_operating_point_refuses_missing_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-operating-point", "--output-dir", str(tmp_path / "out")]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_operating_point_refuses_an_input_that_does_not_exist(
    tmp_path: Path, capsys
) -> None:
    inputs = _operating_point_inputs(tmp_path)
    arguments = _operating_point_arguments(tmp_path, inputs, weights=tmp_path / "absent-weights")
    assert main(arguments) == 2
    assert "no such input" in capsys.readouterr().err


def test_measure_operating_point_refuses_an_existing_output_directory(
    tmp_path: Path, capsys
) -> None:
    inputs = _operating_point_inputs(tmp_path)
    Path(inputs["--output-dir"]).mkdir()
    weights = tmp_path / "weights"
    weights.mkdir()
    arguments = _operating_point_arguments(tmp_path, inputs, weights=weights)
    assert main(arguments) == 2
    assert "exists; a measurement is never resumed" in capsys.readouterr().err


def test_measure_operating_point_prints_the_librarys_selection(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    from so101_demo.act.head_search.operating_point_measurement import (
        measurement as measurement_measurement,
    )

    inputs = _operating_point_inputs(tmp_path)
    weights = tmp_path / "weights"
    weights.mkdir()
    arguments = _operating_point_arguments(tmp_path, inputs, weights=weights)
    seen = {}

    def fake_measure(**request):
        seen.update(request)
        return {
            "document": {"frames": [{}, {}], "sha256": "0" * 64},
            "receipt": {
                "status": "MEASURED",
                "frame_count": 2,
                "candidate_count": 3,
                "grid_point_count": 18,
                "chosen": {
                    "head": {"A": {"min_confidence": 0.25, "tracking_iou": 0.5}},
                    "task": {"A": {"min_confidence": 0.25, "tracking_iou": 0.5}},
                },
            },
        }

    monkeypatch.setattr(measurement_measurement, "measure_operating_point_measurements", fake_measure)
    rc = main(arguments)

    assert rc == 0
    assert seen["device"] == "cuda"
    assert seen["weights_dir"] == weights
    assert seen["selection_rule_path"] == inputs["--selection-rule"]
    assert seen["task_selection_rule_path"] == inputs["--task-selection-rule"]
    assert seen["output_dir"] == inputs["--output-dir"]
    assert "OPERATING_POINTS_MEASURED" in capsys.readouterr().out


def test_the_run_entry_observes_the_measured_values_off_the_running_components(tmp_path: Path) -> None:
    """The run's phase inputs carry the observer, so phases 6 and 7 record proof rather than a restatement."""

    from so101_demo.act.head_search.measured_readback import observe_measured_readbacks
    from so101_demo.cli.head_search.run import _phase_inputs, _run_parser

    parsed = _run_parser().parse_args(_run_arguments(tmp_path)[1:])
    phase_inputs = _phase_inputs(parsed)

    assert phase_inputs.readback_observer is observe_measured_readbacks
    assert phase_inputs.startup_readbacks is None


def test_check_ownership_publishes_a_stack_free_receipt(tmp_path: Path, monkeypatch) -> None:
    """Step 1's gate is an installed entry: a clean machine is recorded, a second owner is refused."""

    from so101_demo.act.head_search import ownership as ownership
    evidence = tmp_path / "evidence"
    evidence.mkdir()

    def observation(name: str, **overrides):
        fields = {"command": (), "rc": 0, "rows": (), "value": None, "note": ""}
        fields.update(overrides)
        return ownership.ResourceObservation(name=name, **fields)

    def clean_observers(**kwargs):
        return {
            "process_table": lambda: observation("process_table"),
            "ros_graph": lambda: observation("ros_graph", value="clean"),
            "gpu_processes": lambda: observation("gpu_processes"),
            "tmux_panes": lambda: observation("tmux_panes"),
            "evidence_root": lambda: observation("evidence_root", value="usable"),
            "planned_run_root": lambda: observation("planned_run_root", value="absent"),
            "ament_prefix": lambda: observation("ament_prefix", value="/frozen/so101_demo_py"),
        }

    monkeypatch.setattr(ownership, "default_observers", clean_observers)
    run_root = tmp_path / "gate"
    assert (
        main(
            [
                "check-ownership",
                "--run-root",
                str(run_root),
                "--evidence-root",
                str(evidence),
                "--expected-package-prefix",
                "/frozen/so101_demo_py",
            ]
        )
        == 0
    )
    receipt = json.loads((run_root / ownership.RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt["status"] == ownership.EXCLUSIVE_OWNERSHIP_OK
    assert receipt["refusals"] == []

    def busy_observers(**kwargs):
        observers = clean_observers(**kwargs)
        observers["process_table"] = lambda: observation(
            "process_table", rows=({"pid": 5, "kind": "stack", "command": "move_group"},)
        )
        return observers

    monkeypatch.setattr(ownership, "default_observers", busy_observers)
    other = tmp_path / "gate-busy"
    assert (
        main(
            [
                "check-ownership",
                "--run-root",
                str(other),
                "--evidence-root",
                str(evidence),
            ]
        )
        == 2
    )
    refused = json.loads((other / ownership.RECEIPT_NAME).read_text(encoding="utf-8"))
    assert refused["status"] == ownership.EXCLUSIVE_OWNERSHIP_REFUSED
    assert [item["code"] for item in refused["refusals"]] == ["STACK_OWNER_ACTIVE"]


def test_check_ownership_refuses_a_reused_gate_root_and_an_unreadable_runtime(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "gate"
    existing.mkdir()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    assert (
        main(
            [
                "check-ownership",
                "--run-root",
                str(existing),
                "--evidence-root",
                str(evidence),
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "check-ownership",
                "--run-root",
                str(tmp_path / "fresh"),
                "--evidence-root",
                str(evidence),
                "--final-run",
                str(tmp_path / "missing-toolchain"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "fresh").exists(), "a refused identity must not leave a half-claimed root"
