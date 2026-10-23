"""Collection, the oracle, asset verification and archive inspection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from perception_benchmark_cli_support import (
    ARCHIVE_DIRNAME,
    ARCHIVE_FILENAME,
    ARCHIVE_SHA256,
    CONFIG,
    FIXTURE,
)
import pytest

from so101_demo.cli import perception_benchmark
from so101_demo.cli.benchmark import aggregate as perception_benchmark_aggregate
from so101_demo.cli.benchmark import assets as perception_benchmark_assets
from so101_demo.cli.benchmark import calibrate as perception_benchmark_calibrate
from so101_demo.cli.benchmark import collect as perception_benchmark_collect
from so101_demo.cli.benchmark import common as perception_benchmark_common
from so101_demo.cli.benchmark import dry_run as perception_benchmark_dry_run
from so101_demo.perception_benchmark.calibration.results import ThresholdLock
from so101_demo.perception_benchmark.contracts import (
    RunKind,
)


def test_collect_rejects_fixture_and_val_lock_at_argument_gate() -> None:
    parser = perception_benchmark.build_parser()
    with pytest.raises(SystemExit) as fixture_error:
        parser.parse_args(["collect", "--adapter-fixture", str(FIXTURE)])
    assert fixture_error.value.code == 2


def test_inventory_forwards_explicit_relocated_test_access_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    access_log = tmp_path / "test-access.jsonl"
    arguments = SimpleNamespace(
        split="test",
        dataset_archive_sha256=ARCHIVE_SHA256,
        dataset_inventory=tmp_path / "test-open/inventory.json",
        inventory_sha256="1" * 64,
        test_access_event_sha256="2" * 64,
        sealed_member_inventory_sha256="3" * 64,
        yolo_lock_sha256="4" * 64,
        grounded_sam_lock_sha256="5" * 64,
        test_access_log=access_log,
    )
    captured: dict[str, object] = {}

    def capture(root: Path, **options: object) -> object:
        captured["root"] = root
        captured.update(options)
        return object()

    monkeypatch.setattr(perception_benchmark_calibrate, "load_dataset_inventory", capture)
    monkeypatch.setattr(perception_benchmark_dry_run, "load_dataset_inventory", capture)
    monkeypatch.setattr(perception_benchmark_aggregate, "load_dataset_inventory", capture)

    perception_benchmark_dry_run._inventory(arguments, perception_benchmark_common._load_frozen_config(CONFIG))

    assert captured["root"] == arguments.dataset_inventory.parent
    assert captured["expected_access_log_path"] == access_log


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
        perception_benchmark_collect.build_calibrated_detector_port("yolo_seg", lock, object())


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
        perception_benchmark_collect,
        "build_calibrated_detector_port",
        lambda *args, **kwargs: pytest.fail("unsafe lock reached calibrated builder"),
    )
    monkeypatch.setattr(perception_benchmark_collect, "verify_threshold_lock", lambda path: lock)
    monkeypatch.setattr(perception_benchmark_aggregate, "verify_threshold_lock", lambda path: lock)
    monkeypatch.setattr(perception_benchmark_collect, "YoloCalibratedDetector", fake_yolo)
    monkeypatch.setattr(
        perception_benchmark_collect, "_validate_characterization_runtime", lambda *args: None
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

    observer = perception_benchmark_collect._production_observer(arguments, RunKind.TEST_CHARACTERIZATION)

    assert observer.args[0] is detector
    assert captured["thresholds"] is selected
    assert captured["requested_device"] == "mps"


def test_config_registers_exact_low_floor_limits() -> None:
    frozen = perception_benchmark_common._load_frozen_config(CONFIG)

    assert frozen["models"]["yolo_seg"]["low_floor"] == {
        "confidence": 0.01,
        "nms_iou": 0.90,
        "max_det": 300,
    }
    assert frozen["models"]["grounded_sam"]["low_floor"] == {
        "box_threshold": 0.01,
        "text_threshold": 0.01,
        "sam_quality_threshold": 0.00,
        "selector": "off",
        "maximum_candidates": 300,
    }


def test_formal_asset_verification_rejects_caller_sha_not_frozen_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        perception_benchmark_assets,
        "verify_weights",
        lambda *args: pytest.fail("unfrozen asset reached verifier"),
    )
    arguments = SimpleNamespace(
        config=CONFIG,
        model="yolo_seg",
        weights=tmp_path / "best.pt",
        weights_sha256="0" * 64,
        model_root=None,
        manifest_sha256=None,
    )

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_assets._handle_verify_assets(arguments)

    assert caught.value.code == "FROZEN_PROVENANCE_MISMATCH"


def test_formal_archive_rejects_internally_consistent_but_unregistered_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        perception_benchmark_assets.DatasetArchiveVerifier,
        "verify_archive",
        lambda *args: pytest.fail("unregistered archive reached verifier"),
    )
    arguments = SimpleNamespace(
        config=CONFIG,
        archive=tmp_path / "different.tar.gz",
        expected_sha256=ARCHIVE_SHA256,
        sealed_member_inventory=tmp_path / "sealed.json",
    )

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_assets._handle_inspect_archive(arguments)

    assert caught.value.code == "FROZEN_PROVENANCE_MISMATCH"


def test_inspect_archive_prints_sealed_member_inventory_sha(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive = (
        tmp_path
        / ARCHIVE_DIRNAME
        / ARCHIVE_FILENAME
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"placeholder")
    sealed = tmp_path / "sealed.json"
    expected_sha = "1" * 64
    monkeypatch.setattr(
        perception_benchmark_assets.DatasetArchiveVerifier,
        "verify_archive",
        lambda *args: SimpleNamespace(sealed_test_member_inventory_sha256=expected_sha),
    )
    arguments = SimpleNamespace(
        config=CONFIG,
        archive=archive,
        expected_sha256=ARCHIVE_SHA256,
        sealed_member_inventory=sealed,
    )

    assert perception_benchmark_assets._handle_inspect_archive(arguments) == 0
    assert capsys.readouterr().out == f"{expected_sha}\n"


def test_collect_rejects_short_source_commit_before_dataset_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = SimpleNamespace(
        run_kind="VAL_RAW",
        allow_oracle_diagnostic=False,
        split="val",
        threshold_lock=None,
        platform="macos",
        device="mps",
        dtype="float32",
        model="yolo_seg",
        weights=tmp_path / "best.pt",
        weights_sha256=("f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"),
        model_root=None,
        manifest_sha256=None,
        source_commit="608fc83",
        config=CONFIG,
    )
    monkeypatch.setattr(
        perception_benchmark_collect,
        "_inventory",
        lambda *args: pytest.fail("short source commit reached dataset I/O"),
    )
    monkeypatch.setattr(
        perception_benchmark_dry_run,
        "_inventory",
        lambda *args: pytest.fail("short source commit reached dataset I/O"),
    )

    with pytest.raises(perception_benchmark_common.BenchmarkError) as caught:
        perception_benchmark_collect._handle_collect(arguments)

    assert caught.value.code == "SOURCE_COMMIT_INVALID"
