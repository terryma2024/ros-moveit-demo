"""Calibration, unlock preflight and aggregation plan errors."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from perception_benchmark_cli_support import (
    ARCHIVE_DIRNAME,
    ARCHIVE_FILENAME,
    ARCHIVE_SHA256,
    CONFIG,
    _calibration_arguments,
    _verified_val_run,
)
import pytest

from so101_demo.cli import perception_benchmark
from so101_demo.cli.benchmark import aggregate as perception_benchmark_aggregate
from so101_demo.cli.benchmark import assets as perception_benchmark_assets
from so101_demo.cli.benchmark import calibrate as perception_benchmark_calibrate
from so101_demo.cli.benchmark import common as perception_benchmark_common
from so101_demo.cli.benchmark import dry_run as perception_benchmark_dry_run
from so101_demo.perception_benchmark.codec import (
    read_mask,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    MaskRef,
    TruthInstance,
    TruthSample,
)


def _patch_calibration_loaders(
    monkeypatch: pytest.MonkeyPatch,
    arguments: SimpleNamespace,
    mac: SimpleNamespace,
    linux: SimpleNamespace,
) -> None:
    inventory = SimpleNamespace(
        dataset_root=arguments.dataset_inventory.parent,
        inventory_sha256=arguments.inventory_sha256,
    )
    monkeypatch.setattr(perception_benchmark_calibrate, "load_dataset_inventory", lambda *a, **k: inventory)
    monkeypatch.setattr(perception_benchmark_dry_run, "load_dataset_inventory", lambda *a, **k: inventory)
    monkeypatch.setattr(perception_benchmark_aggregate, "load_dataset_inventory", lambda *a, **k: inventory)
    monkeypatch.setattr(perception_benchmark_calibrate, "load_truth_samples", lambda *a, **k: ())
    monkeypatch.setattr(perception_benchmark_aggregate, "load_truth_samples", lambda *a, **k: ())
    monkeypatch.setattr(perception_benchmark_aggregate, "_expectation", lambda *a, **k: object())
    monkeypatch.setattr(perception_benchmark_calibrate, "_expectation", lambda *a, **k: object())
    loaded = iter((mac, linux))
    monkeypatch.setattr(
        perception_benchmark_calibrate, "load_verified_run_evidence", lambda *a, **k: next(loaded)
    )
    monkeypatch.setattr(
        perception_benchmark_aggregate, "load_verified_run_evidence", lambda *a, **k: next(loaded)
    )


def test_calibration_rehomes_truth_masks_with_prediction_masks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = _calibration_arguments(tmp_path)
    arguments.calibration_workers = 2
    arguments.dataset_inventory.parent.mkdir()
    mask = np.array([[True, False], [False, True]], dtype=bool)
    source_payload = b'{ "size": [2, 2], "counts": [0, 1, 2, 1] }\n'
    (arguments.dataset_inventory.parent / "truth-mask.rle.json").write_bytes(source_payload)
    truth = TruthSample(
        formal_sample_index=0,
        split="val",
        scenario="synthetic",
        image_relpath="images/0.png",
        image_sha256="1" * 64,
        image_width=2,
        image_height=2,
        instances=(
            TruthInstance(
                instance_id="truth-0",
                label="plastic_cup",
                mask=MaskRef(
                    relative_path="truth-mask.rle.json",
                    sha256=sha256_bytes(mask.astype(np.uint8).tobytes(order="C")),
                    pixel_count=2,
                    image_width=2,
                    image_height=2,
                ),
            ),
        ),
    )
    config_sha = perception_benchmark_assets.sha256_bytes(CONFIG.read_bytes())
    mac = _verified_val_run(
        arguments.mac_run_root,
        platform="macos",
        source_commit=arguments.source_commit,
        config_sha256=config_sha,
    )
    linux = _verified_val_run(
        arguments.linux_run_root,
        platform="linux",
        source_commit=arguments.source_commit,
        config_sha256=config_sha,
    )
    _patch_calibration_loaders(monkeypatch, arguments, mac, linux)
    monkeypatch.setattr(perception_benchmark_calibrate, "load_truth_samples", lambda *a, **k: (truth,))
    monkeypatch.setattr(perception_benchmark_aggregate, "load_truth_samples", lambda *a, **k: (truth,))

    def verify_rehomed(*values: object, **options: object) -> SimpleNamespace:
        rehomed_truth = values[3][0]  # type: ignore[index]
        evidence_root = options["evidence_root"]
        assert options["workers"] == 2
        assert rehomed_truth.instances[0].mask.relative_path.startswith("truth/")
        assert np.array_equal(read_mask(rehomed_truth.instances[0].mask, evidence_root), mask)
        assert (
            evidence_root / rehomed_truth.instances[0].mask.relative_path
        ).read_bytes() == source_payload
        return SimpleNamespace(lock_sha256="e" * 64)

    monkeypatch.setattr(perception_benchmark_calibrate, "calibrate_joint_platform_val", verify_rehomed)
    monkeypatch.setattr(perception_benchmark_calibrate, "write_threshold_lock", lambda *a: None)
    monkeypatch.setattr(perception_benchmark_calibrate, "_write_index", lambda *a: None)
    monkeypatch.setattr(perception_benchmark_dry_run, "_write_index", lambda *a: None)

    assert perception_benchmark_calibrate._handle_calibrate(arguments) == 0
    progress = capsys.readouterr().err
    assert "phase=verify" in progress
    assert "phase=rehome" in progress
    assert "elapsed=" in progress


def test_calibration_rejects_cross_platform_provenance_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = _calibration_arguments(tmp_path)
    config_sha = perception_benchmark_assets.sha256_bytes(CONFIG.read_bytes())
    mac = _verified_val_run(
        arguments.mac_run_root,
        platform="macos",
        source_commit=arguments.source_commit,
        config_sha256=config_sha,
    )
    linux = _verified_val_run(
        arguments.linux_run_root,
        platform="linux",
        source_commit="7" * 40,
        config_sha256=config_sha,
    )
    _patch_calibration_loaders(monkeypatch, arguments, mac, linux)
    monkeypatch.setattr(
        perception_benchmark_calibrate,
        "calibrate_joint_platform_val",
        lambda *a, **k: pytest.fail("mismatched runs reached calibration"),
    )

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_calibrate._handle_calibrate(arguments)

    assert caught.value.code == "RUN_PROVENANCE_MISMATCH"
    assert not arguments.output_root.exists()


def test_calibration_output_must_be_disjoint_from_verified_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = _calibration_arguments(tmp_path)
    arguments.mac_run_root.mkdir()
    arguments.linux_run_root.mkdir()
    arguments.output_root = arguments.mac_run_root / "locks"
    config_sha = perception_benchmark_assets.sha256_bytes(CONFIG.read_bytes())
    mac = _verified_val_run(
        arguments.mac_run_root,
        platform="macos",
        source_commit=arguments.source_commit,
        config_sha256=config_sha,
    )
    linux = _verified_val_run(
        arguments.linux_run_root,
        platform="linux",
        source_commit=arguments.source_commit,
        config_sha256=config_sha,
    )
    _patch_calibration_loaders(monkeypatch, arguments, mac, linux)
    monkeypatch.setattr(
        perception_benchmark_calibrate,
        "calibrate_joint_platform_val",
        lambda *a, **k: pytest.fail("overlapping output reached calibration"),
    )

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_calibrate._handle_calibrate(arguments)

    assert caught.value.code == "CALIBRATION_OUTPUT_OVERLAP"
    assert not arguments.output_root.exists()


def test_unlock_preflights_output_before_appending_access_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "already-exists"
    output.mkdir()
    for name in ("yolo.json", "grounded.json", "sealed.json"):
        (tmp_path / name).write_text("{}")
    arguments = SimpleNamespace(
        config=CONFIG,
        archive=(
            tmp_path
            / ARCHIVE_DIRNAME
            / ARCHIVE_FILENAME
        ),
        expected_sha256=ARCHIVE_SHA256,
        sealed_member_inventory=tmp_path / "sealed.json",
        yolo_threshold_lock=tmp_path / "yolo.json",
        grounded_sam_threshold_lock=tmp_path / "grounded.json",
        access_log=tmp_path / "access.ndjson",
        output_root=output,
    )
    monkeypatch.setattr(
        perception_benchmark_assets,
        "unlock_test_seal",
        lambda *a, **k: pytest.fail("access event appended before output preflight"),
    )

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_assets._handle_unlock_test(arguments)

    assert caught.value.code == "OUTPUT_ROOT_ALREADY_EXISTS"


def test_unlock_checks_sealed_inventory_against_archive_before_access_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive = (
        tmp_path
        / ARCHIVE_DIRNAME
        / ARCHIVE_FILENAME
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"placeholder")
    for name in ("yolo.json", "grounded.json", "sealed.json"):
        (tmp_path / name).write_text("{}")
    arguments = SimpleNamespace(
        config=CONFIG,
        archive=archive,
        expected_sha256=ARCHIVE_SHA256,
        sealed_member_inventory=tmp_path / "sealed.json",
        yolo_threshold_lock=tmp_path / "yolo.json",
        grounded_sam_threshold_lock=tmp_path / "grounded.json",
        access_log=tmp_path / "access.ndjson",
        output_root=tmp_path / "test-open",
    )
    monkeypatch.setattr(
        perception_benchmark_assets,
        "sha256_file",
        lambda path: arguments.expected_sha256,
    )
    monkeypatch.setattr(
        perception_benchmark_dry_run,
        "sha256_file",
        lambda path: arguments.expected_sha256,
    )
    monkeypatch.setattr(
        perception_benchmark_aggregate,
        "sha256_file",
        lambda path: arguments.expected_sha256,
    )
    monkeypatch.setattr(
        perception_benchmark_assets.DatasetArchiveVerifier,
        "verify_archive",
        lambda *args: SimpleNamespace(sealed_test_member_inventory_sha256="0" * 64),
    )
    monkeypatch.setattr(
        perception_benchmark_assets,
        "unlock_test_seal",
        lambda *a, **k: pytest.fail("access event appended before seal preflight"),
    )

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_assets._handle_unlock_test(arguments)

    assert caught.value.code == "TEST_SEAL_ARCHIVE_MISMATCH"
    assert not arguments.access_log.exists()


def test_expected_model_setup_error_is_stable_cli_error_without_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"not-used")
    monkeypatch.setattr(
        perception_benchmark_assets,
        "verify_weights",
        lambda *a, **k: (_ for _ in ()).throw(
            perception_benchmark.ModelSetupError("MODEL_UNAVAILABLE", str(tmp_path))
        ),
    )
    result = perception_benchmark.main(
        [
            "verify-assets",
            "--config",
            str(CONFIG),
            "--model",
            "yolo_seg",
            "--weights",
            str(weights),
            "--weights-sha256",
            "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781",
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "MODEL_UNAVAILABLE:" in captured.err
    assert "Traceback" not in captured.err
    assert str(tmp_path) not in captured.err


def test_malformed_aggregation_plan_is_typed_error_not_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "schema_version": "so101-perception-benchmark/aggregation-plan-v1",
                "dataset": {},
                "threshold_locks": {
                    "yolo_seg": {"path": 7, "sha256": "0" * 64},
                    "grounded_sam": {"path": 8, "sha256": "1" * 64},
                },
                "runs": [],
            }
        )
    )
    result = perception_benchmark.main(
        [
            "aggregate",
            "--config",
            str(CONFIG),
            "--aggregation-plan",
            str(plan),
            "--aggregation-plan-sha256",
            perception_benchmark_assets.sha256_bytes(plan.read_bytes()),
            "--output-root",
            str(tmp_path / "report"),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "AGGREGATION_PLAN_INVALID:" in captured.err
    assert "Traceback" not in captured.err
