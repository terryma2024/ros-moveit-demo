"""The `measure-bundle-inputs` entry: it declares inputs, calls one library function and nothing else.

The heavy layers of the producer - the installed controller and the production detector - belong to the
library and to the real run, so these tests pin the entry itself: which flags it needs, what it refuses
before the library runs, what it hands over and what it prints.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.cli.head_search_calibration import main


def _write_json(path: Path, document) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _inputs(tmp_path: Path) -> dict:
    weights = tmp_path / "weights" / "C.pt"
    weights.parent.mkdir(parents=True, exist_ok=True)
    weights.write_bytes(b"weights\n")
    return {
        "--geometry-seal": _write_json(tmp_path / "geometry-seal.json", {"seal_sha256": "a" * 64}),
        "--production-config": _write_json(tmp_path / "production-config.json", {"values": {}}),
        "--operating-point": _write_json(tmp_path / "phase3-selection-head-C.json", {"chosen_point": {}}),
        "--frozen-candidate": _write_json(tmp_path / "frozen-c.json", {"candidate_id": "C"}),
        "--weights": weights,
        "--output-dir": tmp_path / "bundle-inputs",
    }


def _arguments(inputs: dict, *, device: str = "cuda") -> list[str]:
    arguments = ["measure-bundle-inputs"]
    for flag, value in inputs.items():
        arguments += [flag, str(value)]
    return arguments + ["--device", device]


def test_measure_bundle_inputs_hands_the_declaration_to_the_library(tmp_path: Path, capsys, monkeypatch) -> None:
    from so101_demo.act.head_search import calibration_bundle_inputs as producer
    inputs = _inputs(tmp_path)
    measurements = _write_json(tmp_path / "operating-point-measurements.json", {"frames": []})
    web = tmp_path / "web"
    web.mkdir()
    seen = {}

    def fake_record(**request):
        seen.update(request)
        return {
            "document": {"parameter_evidence": {}, "also_recorded": {}, "runtime_identity": {}},
            "receipt": {"unverified": []},
            "document_path": Path(request["output_dir"]) / "bundle-inputs.json",
            "receipt_path": Path(request["output_dir"]) / "bundle-inputs-receipt.json",
        }

    monkeypatch.setattr(producer, "record_bundle_inputs", fake_record)
    arguments = _arguments(inputs) + [
        "--operating-point-measurements", str(measurements),
        "--web-bundle-root", str(web),
        "--readback-identity", "generation-1",
    ]
    rc = main(arguments)

    assert rc == 0
    assert seen["geometry_seal"] == inputs["--geometry-seal"]
    assert seen["production_config"] == inputs["--production-config"]
    assert seen["operating_point"] == inputs["--operating-point"]
    assert seen["frozen_candidate"] == inputs["--frozen-candidate"]
    assert seen["weights"] == inputs["--weights"]
    assert seen["operating_point_measurements"] == measurements
    assert seen["output_dir"] == inputs["--output-dir"]
    assert seen["device"] == "cuda"
    assert seen["readback_identity"] == "generation-1"
    assert seen["web_bundle_root"] == web
    assert seen["command"].endswith("--readback-identity generation-1")
    printed = capsys.readouterr().out
    assert printed.startswith("BUNDLE_INPUTS_RECORDED parameters=6 ")
    assert "unverified=none" in printed
    assert str(inputs["--output-dir"]) in printed


def test_measure_bundle_inputs_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-bundle-inputs"]) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE: a measurement declares ")
    for flag in ("--geometry-seal", "--production-config", "--operating-point", "--frozen-candidate",
                 "--weights", "--output-dir"):
        assert flag in printed


def test_measure_bundle_inputs_refuses_an_input_that_does_not_exist(tmp_path: Path, capsys) -> None:
    inputs = _inputs(tmp_path)
    arguments = _arguments(inputs)
    arguments[arguments.index("--weights") + 1] = str(tmp_path / "absent.pt")
    assert main(arguments) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE: no such input ")
    assert "absent.pt" in printed


def test_measure_bundle_inputs_refuses_an_existing_output_directory(tmp_path: Path, capsys) -> None:
    inputs = _inputs(tmp_path)
    Path(inputs["--output-dir"]).mkdir()
    assert main(_arguments(inputs)) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE: ")
    assert "never resumed, continued or overwritten" in printed


def test_measure_bundle_inputs_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    from so101_demo.act.head_search import calibration_bundle_inputs as producer
    def refusing(**request):
        raise CalibrationInputsRefused(
            producer.CAL_BUNDLE_INPUTS_INCOMPLETE, "the frozen candidate seals another file"
        )

    monkeypatch.setattr(producer, "record_bundle_inputs", refusing)
    assert main(_arguments(_inputs(tmp_path))) == 2
    printed = capsys.readouterr().err
    assert printed.startswith("CAL_BUNDLE_INPUTS_INCOMPLETE: ")
    assert "seals another file" in printed


def test_measure_bundle_inputs_is_dispatched_by_the_console_entry(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["measure-bundle-inputs", "--help"])
    assert exit_info.value.code == 0
    assert "measure-bundle-inputs" in capsys.readouterr().out
