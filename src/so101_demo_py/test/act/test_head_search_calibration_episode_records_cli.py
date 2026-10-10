"""The `measure-episode-records` entry: it declares inputs, calls one library function and nothing else."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.cli.head_search_calibration import main


def _write_json(path: Path, document) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _inputs(tmp_path: Path) -> dict:
    return {
        "--operating-point-measurements": _write_json(tmp_path / "measurements.json", {"frames": []}),
        "--episode-partitions": _write_json(tmp_path / "partitions.json", {"calibration": [700000]}),
        "--output-dir": tmp_path / "episodes" / "calibration",
    }


def _arguments(inputs: dict) -> list[str]:
    arguments = ["measure-episode-records"]
    for flag, value in inputs.items():
        arguments += [flag, str(value)]
    return arguments


def test_measure_episode_records_hands_the_declaration_to_the_library(tmp_path: Path, capsys, monkeypatch) -> None:
    from so101_demo.act import head_search_episode_records as producer

    inputs = _inputs(tmp_path)
    seen = {}

    def fake_record(**request):
        seen.update(request)
        return {
            "documents": {},
            "receipt": {"seed_count": 20, "frame_count": 120, "split": "calibration"},
            "receipt_path": Path(request["output_dir"]) / producer.RECEIPT_NAME,
        }

    monkeypatch.setattr(producer, "record_episode_records", fake_record)
    assert main(_arguments(inputs) + ["--split", "calibration"]) == 0
    assert seen["measurements"] == inputs["--operating-point-measurements"]
    assert seen["partitions"] == inputs["--episode-partitions"]
    assert seen["output_dir"] == inputs["--output-dir"]
    assert seen["split"] == "calibration"
    assert seen["command"].endswith("--split calibration")
    printed = capsys.readouterr().out
    assert printed.startswith("EPISODE_RECORDS_RECORDED split=calibration seeds=20 frames=120 ")
    assert str(inputs["--output-dir"]) in printed


def test_measure_episode_records_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-episode-records"]) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE: a measurement declares ")
    for flag in ("--operating-point-measurements", "--episode-partitions", "--output-dir"):
        assert flag in printed


def test_measure_episode_records_refuses_an_input_that_does_not_exist(tmp_path: Path, capsys) -> None:
    inputs = _inputs(tmp_path)
    arguments = _arguments(inputs)
    arguments[arguments.index("--episode-partitions") + 1] = str(tmp_path / "absent.json")
    assert main(arguments) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE: no such input ")
    assert "absent.json" in printed


def test_measure_episode_records_refuses_an_existing_output_directory(tmp_path: Path, capsys) -> None:
    inputs = _inputs(tmp_path)
    Path(inputs["--output-dir"]).mkdir(parents=True)
    assert main(_arguments(inputs)) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE: ")
    assert "never resumed, continued or overwritten" in printed


def test_measure_episode_records_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    from so101_demo.act import head_search_episode_records as producer

    def refusing(**request):
        raise CalibrationInputsRefused(
            producer.CAL_EPISODE_RECORDS_INCOMPLETE, "the partition declares a seed that was never measured"
        )

    monkeypatch.setattr(producer, "record_episode_records", refusing)
    assert main(_arguments(_inputs(tmp_path))) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("CAL_EPISODE_RECORDS_INCOMPLETE: ")
    assert "never measured" in printed


def test_measure_episode_records_is_dispatched_by_the_console_entry(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["measure-episode-records", "--help"])
    assert exit_info.value.code == 0
    assert "measure-episode-records" in capsys.readouterr().out
