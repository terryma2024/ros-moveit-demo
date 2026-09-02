from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from so101_demo.cli import perception_benchmark
from so101_demo.perception_benchmark.calibration import ThresholdLock
from so101_demo.perception_benchmark.contracts import RunKind
from so101_demo.perception_benchmark.reporting import verify_evidence_index

PACKAGE_ROOT = Path(__file__).parents[1]
CONFIG = PACKAGE_ROOT / "config/perception_benchmark/benchmark.yaml"
FIXTURE = PACKAGE_ROOT / "test/fixtures/perception_benchmark/dry-run-adapters.json"


def test_parser_exposes_exact_subcommands() -> None:
    parser = perception_benchmark.build_parser()
    action = next(item for item in parser._actions if item.dest == "command")
    assert set(action.choices) == {
        "verify-assets",
        "inspect-archive",
        "prepare-dataset",
        "unlock-test",
        "dry-run",
        "collect",
        "calibrate",
        "aggregate",
        "verify-evidence",
    }


def test_setup_has_one_console_entry_and_packages_benchmark_yaml() -> None:
    setup_text = (PACKAGE_ROOT / "setup.py").read_text()
    entry = "perception_benchmark = so101_demo.cli.perception_benchmark:main"
    assert setup_text.count(entry) == 1
    assert "installed_resources()" in setup_text
    assert CONFIG.is_file()


def test_config_contains_frozen_literals() -> None:
    text = CONFIG.read_text()
    for literal in (
        "c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1",
        "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781",
        "838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3",
        "a2bb814dd30d776dcf7e30523b00659f4f141c71",
        "de431c4043854a71d8101e17995dfe596bf101a5",
        "source: resolved_ultralytics_predictor_args",
        "warmup_images: 5",
        "cold_processes: 3",
        "seed: 20260902",
        "repetitions: 10000",
    ):
        assert literal in text
    assert "nms:\n        source:" in text


def test_unlock_without_verified_locks_is_typed_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = perception_benchmark.main(
        [
            "unlock-test",
            "--archive",
            str(tmp_path / "archive.tar.gz"),
            "--expected-sha256",
            "0" * 64,
            "--sealed-member-inventory",
            str(tmp_path / "sealed.json"),
            "--yolo-threshold-lock",
            str(tmp_path / "missing-yolo.json"),
            "--grounded-sam-threshold-lock",
            str(tmp_path / "missing-grounded.json"),
            "--access-log",
            str(tmp_path / "access.ndjson"),
            "--output-root",
            str(tmp_path / "test-open"),
        ]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert "TEST_SEALED:" in captured.err
    assert str(tmp_path) not in captured.err


def test_dry_run_publishes_eight_samples_and_sixteen_model_records(tmp_path: Path) -> None:
    output = tmp_path / "dry-run"
    assert (
        perception_benchmark.main(
            [
                "dry-run",
                "--config",
                str(CONFIG),
                "--output-root",
                str(output),
                "--adapter-fixture",
                str(FIXTURE),
            ]
        )
        == 0
    )
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["formal"] is False
    assert manifest["run_kind"] == "NON_FORMAL_DRY_RUN"
    assert manifest["sample_count"] == 8
    assert manifest["model_record_count"] == 16
    assert manifest["records_per_model"] == {"grounded_sam": 8, "yolo_seg": 8}
    assert Counter(row["scenario"] for row in manifest["samples"]) == {
        "no_cup": 2,
        "one_cup_distractors": 2,
        "two_cups": 2,
        "cup_near_bottle": 2,
    }
    assert not (output / "inventory.json").exists()
    assert len(tuple((output / "records").glob("*.json"))) == 16
    index = verify_evidence_index(output)
    assert len(index.entries) > 16


def test_dry_run_plan_is_two_per_scenario_and_never_formal() -> None:
    plan = perception_benchmark.build_dry_run_plan(
        {
            "scenario_counts": {
                scenario: 50
                for scenario in ("no_cup", "one_cup_distractors", "two_cups", "cup_near_bottle")
            }
        }
    )
    assert len(plan.samples) == 8
    assert Counter(item.scenario for item in plan.samples) == {
        "no_cup": 2,
        "one_cup_distractors": 2,
        "two_cups": 2,
        "cup_near_bottle": 2,
    }
    assert len({item.image_sha256 for item in plan.samples}) == 8
    assert plan.formal is False


def test_dry_run_is_byte_deterministic_and_index_detects_tampering(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for output in (first, second):
        assert (
            perception_benchmark.main(
                [
                    "dry-run",
                    "--config",
                    str(CONFIG),
                    "--output-root",
                    str(output),
                    "--adapter-fixture",
                    str(FIXTURE),
                ]
            )
            == 0
        )
    first_payloads = {
        path.relative_to(first).as_posix(): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_payloads = {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_payloads == second_payloads

    record = next((first / "records").glob("*.json"))
    record.write_bytes(record.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        verify_evidence_index(first)


def test_dry_run_rejects_config_drift_before_creating_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changed = tmp_path / "changed.yaml"
    changed.write_text(CONFIG.read_text() + "# changed\n")
    output = tmp_path / "output"
    assert (
        perception_benchmark.main(
            [
                "dry-run",
                "--config",
                str(changed),
                "--output-root",
                str(output),
                "--adapter-fixture",
                str(FIXTURE),
            ]
        )
        == 2
    )
    assert "CONFIG_SHA256_MISMATCH:" in capsys.readouterr().err
    assert not output.exists()


def test_collect_rejects_fixture_and_val_lock_at_argument_gate() -> None:
    parser = perception_benchmark.build_parser()
    with pytest.raises(SystemExit) as fixture_error:
        parser.parse_args(["collect", "--adapter-fixture", str(FIXTURE)])
    assert fixture_error.value.code == 2


def test_oracle_requires_explicit_acknowledgement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = perception_benchmark.main(
        [
            "collect",
            "--run-id",
            "oracle",
            "--platform",
            "macos",
            "--model",
            "yolo_seg",
            "--device",
            "mps",
            "--dtype",
            "float32",
            "--split",
            "test",
            "--run-kind",
            "ORACLE_DIAGNOSTIC",
            "--dataset-inventory",
            str(tmp_path / "inventory.json"),
            "--dataset-archive-sha256",
            "0" * 64,
            "--inventory-sha256",
            "1" * 64,
            "--test-access-event-sha256",
            "2" * 64,
            "--sealed-member-inventory-sha256",
            "3" * 64,
            "--yolo-lock-sha256",
            "4" * 64,
            "--grounded-sam-lock-sha256",
            "5" * 64,
            "--threshold-lock",
            str(tmp_path / "lock.json"),
            "--weights",
            str(tmp_path / "best.pt"),
            "--weights-sha256",
            "6" * 64,
            "--config",
            str(CONFIG),
            "--source-commit",
            "7" * 40,
            "--output-root",
            str(tmp_path / "oracle"),
        ]
    )
    assert result == 2
    assert "ORACLE_ACK_REQUIRED:" in capsys.readouterr().err


def test_val_collect_rejects_threshold_lock_before_io(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = perception_benchmark.main(
        [
            "collect",
            "--run-id",
            "val",
            "--platform",
            "macos",
            "--model",
            "yolo_seg",
            "--device",
            "mps",
            "--dtype",
            "float32",
            "--split",
            "val",
            "--run-kind",
            "VAL_RAW",
            "--dataset-inventory",
            str(tmp_path / "inventory.json"),
            "--dataset-archive-sha256",
            "0" * 64,
            "--inventory-sha256",
            "1" * 64,
            "--threshold-lock",
            str(tmp_path / "lock.json"),
            "--weights",
            str(tmp_path / "best.pt"),
            "--weights-sha256",
            "2" * 64,
            "--config",
            str(CONFIG),
            "--source-commit",
            "3" * 40,
            "--output-root",
            str(tmp_path / "val"),
        ]
    )
    assert result == 2
    assert "VAL_LOCK_FORBIDDEN:" in capsys.readouterr().err


def test_public_calibrated_builder_still_rejects_unsafe_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = object.__new__(ThresholdLock)
    object.__setattr__(lock, "model", "yolo_seg")
    object.__setattr__(lock, "formal", True)
    object.__setattr__(lock, "deployable", False)
    object.__setattr__(lock, "lock_sha256", "a" * 64)
    monkeypatch.setattr(ThresholdLock, "with_recomputed_sha256", lambda self: self)

    with pytest.raises(ValueError, match="formal deployable"):
        perception_benchmark.build_calibrated_detector_port("yolo_seg", lock, object())


def test_unsafe_characterization_uses_frozen_selected_port_not_calibrated_builder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    selected = SimpleNamespace(target_confidence_threshold=0.65)
    lock = SimpleNamespace(model="yolo_seg", formal=True, deployable=False, selected=selected)
    detector = SimpleNamespace(runtime_device="mps")
    captured: dict[str, object] = {}

    def fake_yolo(**kwargs: object) -> object:
        captured.update(kwargs)
        return detector

    monkeypatch.setattr(
        perception_benchmark,
        "build_calibrated_detector_port",
        lambda *args, **kwargs: pytest.fail("unsafe lock reached calibrated builder"),
    )
    monkeypatch.setattr(perception_benchmark, "verify_threshold_lock", lambda path: lock)
    monkeypatch.setattr(perception_benchmark, "YoloCalibratedDetector", fake_yolo)
    monkeypatch.setattr(
        perception_benchmark, "_validate_characterization_runtime", lambda *args: None
    )
    arguments = SimpleNamespace(
        model="yolo_seg",
        weights=tmp_path / "best.pt",
        weights_sha256="a" * 64,
        model_root=None,
        manifest_sha256=None,
        device="mps",
        threshold_lock=tmp_path / "unsafe-lock.json",
    )

    observer = perception_benchmark._production_observer(arguments, RunKind.TEST_CHARACTERIZATION)

    assert observer.args[0] is detector
    assert captured["thresholds"] is selected
    assert captured["requested_device"] == "mps"
