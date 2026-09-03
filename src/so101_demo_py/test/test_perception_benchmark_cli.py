from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from so101_demo.cli import perception_benchmark
from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.adapters.base import (
    CollectionMode,
    RawDetectionResult,
)
from so101_demo.perception_benchmark.calibration import ThresholdLock
from so101_demo.perception_benchmark.codec import atomic_write_json, encode_mask_rle, sha256_bytes
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
    MaskRef,
    RawCandidate,
    RunKind,
    RuntimeProvenance,
)
from so101_demo.perception_benchmark.reporting import verify_evidence_index
from so101_demo.perception_benchmark.timing import PhaseTimingBreakdown

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
            "--config",
            str(CONFIG),
            "--archive",
            str(
                tmp_path
                / "datasets/so101-v5-t004-yolo-seg-synthetic"
                / "so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz"
            ),
            "--expected-sha256",
            "c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1",
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


def test_actual_dry_run_uses_fixed_val_images_and_both_accelerated_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samples = tuple(
        SimpleNamespace(
            formal_sample_index=scenario_index * 2 + ordinal,
            scenario=scenario,
            image_relpath=f"images/{scenario}-{ordinal}.png",
            image_sha256=f"{scenario_index * 2 + ordinal + 1:064x}",
        )
        for scenario_index, scenario in enumerate(
            ("no_cup", "one_cup_distractors", "two_cups", "cup_near_bottle")
        )
        for ordinal in range(2)
    )
    inventory = SimpleNamespace(
        split="val",
        inventory_sha256="a" * 64,
        archive_sha256=("c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1"),
        scenario_counts={scenario: 50 for scenario in perception_benchmark._SCENARIOS},
        samples=samples,
    )
    monkeypatch.setattr(perception_benchmark, "_inventory", lambda *args: inventory)
    monkeypatch.setattr(
        perception_benchmark,
        "_load_actual_dry_frame",
        lambda *args: DetectionFrame(
            rgb8=np.zeros((4, 5, 3), dtype=np.uint8),
            source_stamp_ns=1,
            source_frame_id="val-image",
        ),
    )

    class FakeAdapter:
        def __init__(self, model: str, output: Path) -> None:
            self.model = model
            self.model_id = YOLO_MODEL_ID if model == "yolo_seg" else GROUNDED_SAM_MODEL_ID
            self.runtime_device = "mps"
            self.output = output
            self.index = 0

        def collect(self, frame: DetectionFrame, mode: CollectionMode) -> RawDetectionResult:
            mask = np.zeros((frame.image_height, frame.image_width), dtype=bool)
            mask[1:3, 1:4] = True
            relative = (
                f"benchmark-masks/{self.model}/collection-{self.index:06d}/candidate.rle.json"
            )
            atomic_write_json(self.output / relative, encode_mask_rle(mask))
            self.index += 1
            score_source = "class_confidence" if self.model == "yolo_seg" else "grounding_box_score"
            candidate = RawCandidate(
                candidate_id="candidate",
                label="plastic_cup",
                bbox_xyxy=(1.0, 1.0, 4.0, 3.0),
                mask=MaskRef(
                    relative_path=relative,
                    sha256=sha256_bytes(mask.astype(np.uint8).tobytes(order="C")),
                    pixel_count=int(mask.sum()),
                    image_width=frame.image_width,
                    image_height=frame.image_height,
                ),
                ranking_score=0.8,
                ranking_score_source=score_source,
                class_confidence=0.8 if self.model == "yolo_seg" else None,
                grounding_box_score=0.8 if self.model == "grounded_sam" else None,
                grounding_text_score=0.7 if self.model == "grounded_sam" else None,
                sam_quality=0.9 if self.model == "grounded_sam" else None,
            )
            return RawDetectionResult(
                model_id=self.model_id,
                runtime_device="mps",
                dtype="float32",
                collection_mode=mode,
                raw_candidates=(candidate,),
                phase_timings=PhaseTimingBreakdown(1.0, 2.0, None, 3.0, None, 6.0),
                resource_samples=(),
                fallback_used=False,
                irreversible_limits={},
            )

    monkeypatch.setattr(
        perception_benchmark,
        "_raw_adapter",
        lambda arguments, config: FakeAdapter(arguments.model, arguments.output_root),
    )
    monkeypatch.setattr(
        perception_benchmark,
        "_runtime_provenance",
        lambda arguments: RuntimeProvenance(
            runtime_device="mps",
            runtime_name="fake-runtime",
            runtime_version="1.0",
            weights_sha256=(
                arguments.weights_sha256
                if arguments.model == "yolo_seg"
                else arguments.manifest_sha256
            ),
            environment={"python": "test"},
        ),
    )
    output = tmp_path / "actual-dry-run"

    result = perception_benchmark.main(
        [
            "dry-run",
            "--config",
            str(CONFIG),
            "--output-root",
            str(output),
            "--platform",
            "macos",
            "--device",
            "mps",
            "--dtype",
            "float32",
            "--dataset-inventory",
            str(tmp_path / "val-open" / "inventory.json"),
            "--dataset-archive-sha256",
            inventory.archive_sha256,
            "--inventory-sha256",
            inventory.inventory_sha256,
            "--weights",
            str(tmp_path / "best.pt"),
            "--weights-sha256",
            "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781",
            "--model-root",
            str(tmp_path / "grounded-sam"),
            "--manifest-sha256",
            "838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3",
            "--source-commit",
            "1ab9cdfc939dc623bf6b51f5ca2025b826b1190f",
        ]
    )

    assert result == 0
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["execution_mode"] == "actual"
    assert manifest["formal"] is False
    assert manifest["platform"] == "macos"
    assert manifest["device"] == "mps"
    assert manifest["sample_count"] == 8
    assert manifest["model_record_count"] == 16
    assert manifest["records_per_model"] == {"grounded_sam": 8, "yolo_seg": 8}
    assert [item["image_sha256"] for item in manifest["samples"]] == [
        sample.image_sha256 for sample in samples
    ]
    assert len(tuple((output / "records").glob("*.json"))) == 16
    assert len(tuple((output / "benchmark-masks").rglob("*.json"))) == 16
    assert (output / "report.json").is_file()
    assert (output / "report.md").is_file()
    verify_evidence_index(output)


def test_actual_dry_run_rejects_fixture_mixing_before_output(tmp_path: Path) -> None:
    output = tmp_path / "mixed"
    result = perception_benchmark.main(
        [
            "dry-run",
            "--config",
            str(CONFIG),
            "--output-root",
            str(output),
            "--adapter-fixture",
            str(FIXTURE),
            "--platform",
            "macos",
        ]
    )

    assert result == 2
    assert not output.exists()


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


def test_config_registers_exact_task6_low_floor_limits() -> None:
    frozen = perception_benchmark._load_frozen_config(CONFIG)

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
        perception_benchmark,
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

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._handle_verify_assets(arguments)

    assert caught.value.code == "FROZEN_PROVENANCE_MISMATCH"


def test_formal_archive_rejects_internally_consistent_but_unregistered_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        perception_benchmark.DatasetArchiveVerifier,
        "verify_archive",
        lambda *args: pytest.fail("unregistered archive reached verifier"),
    )
    arguments = SimpleNamespace(
        config=CONFIG,
        archive=tmp_path / "different.tar.gz",
        expected_sha256=("c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1"),
        sealed_member_inventory=tmp_path / "sealed.json",
    )

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._handle_inspect_archive(arguments)

    assert caught.value.code == "FROZEN_PROVENANCE_MISMATCH"


def test_inspect_archive_prints_sealed_member_inventory_sha(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive = (
        tmp_path
        / "datasets/so101-v5-t004-yolo-seg-synthetic"
        / "so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz"
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"placeholder")
    sealed = tmp_path / "sealed.json"
    expected_sha = "1" * 64
    monkeypatch.setattr(
        perception_benchmark.DatasetArchiveVerifier,
        "verify_archive",
        lambda *args: SimpleNamespace(sealed_test_member_inventory_sha256=expected_sha),
    )
    arguments = SimpleNamespace(
        config=CONFIG,
        archive=archive,
        expected_sha256=("c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1"),
        sealed_member_inventory=sealed,
    )

    assert perception_benchmark._handle_inspect_archive(arguments) == 0
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
        perception_benchmark,
        "_inventory",
        lambda *args: pytest.fail("short source commit reached dataset I/O"),
    )

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._handle_collect(arguments)

    assert caught.value.code == "SOURCE_COMMIT_INVALID"


def _verified_val_run(
    root: Path,
    *,
    platform: str,
    source_commit: str,
    config_sha256: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        evidence_root=root,
        records=(),
        manifest=SimpleNamespace(
            model="yolo_seg",
            model_id="plastic-cup-yolo11s-seg-v2",
            platform=platform,
            device="mps" if platform == "macos" else "cuda",
            dtype="float32",
            run_kind=RunKind.VAL_RAW,
            source_commit=source_commit,
            config_sha256=config_sha256,
            weights_sha256=("f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"),
            record_inventory_sha256="a" * 64,
        ),
    )


def _calibration_arguments(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        config=CONFIG,
        model="yolo_seg",
        dataset_inventory=tmp_path / "dataset" / "inventory.json",
        dataset_archive_sha256=("c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1"),
        inventory_sha256="b" * 64,
        mac_run_root=tmp_path / "mac-run",
        mac_run_expectation=tmp_path / "mac-expectation.json",
        mac_run_expectation_sha256="c" * 64,
        linux_run_root=tmp_path / "linux-run",
        linux_run_expectation=tmp_path / "linux-expectation.json",
        linux_run_expectation_sha256="d" * 64,
        source_commit="6" * 40,
        output_root=tmp_path / "locks",
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
    monkeypatch.setattr(perception_benchmark, "load_dataset_inventory", lambda *a, **k: inventory)
    monkeypatch.setattr(perception_benchmark, "load_truth_samples", lambda *a, **k: ())
    monkeypatch.setattr(perception_benchmark, "_expectation", lambda *a, **k: object())
    loaded = iter((mac, linux))
    monkeypatch.setattr(
        perception_benchmark, "load_verified_run_evidence", lambda *a, **k: next(loaded)
    )


def test_calibration_rejects_cross_platform_provenance_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = _calibration_arguments(tmp_path)
    config_sha = perception_benchmark.sha256_bytes(CONFIG.read_bytes())
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
        perception_benchmark,
        "calibrate_joint_platform_val",
        lambda *a, **k: pytest.fail("mismatched runs reached calibration"),
    )

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._handle_calibrate(arguments)

    assert caught.value.code == "RUN_PROVENANCE_MISMATCH"
    assert not arguments.output_root.exists()


def test_calibration_output_must_be_disjoint_from_verified_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arguments = _calibration_arguments(tmp_path)
    arguments.mac_run_root.mkdir()
    arguments.linux_run_root.mkdir()
    arguments.output_root = arguments.mac_run_root / "locks"
    config_sha = perception_benchmark.sha256_bytes(CONFIG.read_bytes())
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
        perception_benchmark,
        "calibrate_joint_platform_val",
        lambda *a, **k: pytest.fail("overlapping output reached calibration"),
    )

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._handle_calibrate(arguments)

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
            / "datasets/so101-v5-t004-yolo-seg-synthetic"
            / "so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz"
        ),
        expected_sha256=("c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1"),
        sealed_member_inventory=tmp_path / "sealed.json",
        yolo_threshold_lock=tmp_path / "yolo.json",
        grounded_sam_threshold_lock=tmp_path / "grounded.json",
        access_log=tmp_path / "access.ndjson",
        output_root=output,
    )
    monkeypatch.setattr(
        perception_benchmark,
        "unlock_test_seal",
        lambda *a, **k: pytest.fail("access event appended before output preflight"),
    )

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._handle_unlock_test(arguments)

    assert caught.value.code == "OUTPUT_ROOT_ALREADY_EXISTS"


def test_unlock_checks_sealed_inventory_against_archive_before_access_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive = (
        tmp_path
        / "datasets/so101-v5-t004-yolo-seg-synthetic"
        / "so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz"
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"placeholder")
    for name in ("yolo.json", "grounded.json", "sealed.json"):
        (tmp_path / name).write_text("{}")
    arguments = SimpleNamespace(
        config=CONFIG,
        archive=archive,
        expected_sha256=("c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1"),
        sealed_member_inventory=tmp_path / "sealed.json",
        yolo_threshold_lock=tmp_path / "yolo.json",
        grounded_sam_threshold_lock=tmp_path / "grounded.json",
        access_log=tmp_path / "access.ndjson",
        output_root=tmp_path / "test-open",
    )
    monkeypatch.setattr(
        perception_benchmark,
        "sha256_file",
        lambda path: arguments.expected_sha256,
    )
    monkeypatch.setattr(
        perception_benchmark.DatasetArchiveVerifier,
        "verify_archive",
        lambda *args: SimpleNamespace(sealed_test_member_inventory_sha256="0" * 64),
    )
    monkeypatch.setattr(
        perception_benchmark,
        "unlock_test_seal",
        lambda *a, **k: pytest.fail("access event appended before seal preflight"),
    )

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._handle_unlock_test(arguments)

    assert caught.value.code == "TEST_SEAL_ARCHIVE_MISMATCH"
    assert not arguments.access_log.exists()


def test_expected_model_setup_error_is_stable_cli_error_without_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"not-used")
    monkeypatch.setattr(
        perception_benchmark,
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
            perception_benchmark.sha256_bytes(plan.read_bytes()),
            "--output-root",
            str(tmp_path / "report"),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "AGGREGATION_PLAN_INVALID:" in captured.err
    assert "Traceback" not in captured.err


def test_every_formal_subcommand_requires_the_frozen_config() -> None:
    parser = perception_benchmark.build_parser()
    commands = next(item for item in parser._actions if item.dest == "command").choices

    for name in (
        "verify-assets",
        "inspect-archive",
        "prepare-dataset",
        "unlock-test",
        "collect",
        "calibrate",
        "aggregate",
    ):
        config_action = next(item for item in commands[name]._actions if item.dest == "config")
        assert config_action.required is True


@pytest.mark.parametrize(
    ("field", "drift"),
    [
        ("model", "grounded_sam"),
        ("model_id", "different-model"),
        ("platform", "linux"),
        ("device", "cuda"),
        ("dtype", "float16"),
        ("run_kind", RunKind.TEST_RAW_FROZEN),
        ("source_commit", "7" * 40),
        ("config_sha256", "8" * 64),
        ("weights_sha256", "9" * 64),
    ],
)
def test_calibration_requires_every_frozen_run_provenance_field(
    tmp_path: Path, field: str, drift: object
) -> None:
    arguments = _calibration_arguments(tmp_path)
    run = _verified_val_run(
        arguments.mac_run_root,
        platform="macos",
        source_commit=arguments.source_commit,
        config_sha256=perception_benchmark.sha256_bytes(CONFIG.read_bytes()),
    )
    setattr(run.manifest, field, drift)
    config = perception_benchmark._load_frozen_config(CONFIG)

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._validate_val_run_provenance(
            run,
            platform_name="macos",
            device="mps",
            arguments=arguments,
            config=config,
        )

    assert caught.value.code == "RUN_PROVENANCE_MISMATCH"


def test_raw_adapter_result_must_match_registered_task6_limits() -> None:
    config = perception_benchmark._load_frozen_config(CONFIG)
    delegate = SimpleNamespace(
        model_id="plastic-cup-yolo11s-seg-v2",
        runtime_device="mps",
        _weights_sha256=("f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"),
        collect=lambda *args: SimpleNamespace(
            irreversible_limits={"nms_iou": 0.70, "max_det": 300},
            raw_candidates=(),
        ),
    )
    adapter = perception_benchmark._FrozenRawAdapter(
        delegate,
        "yolo_seg",
        config["models"]["yolo_seg"],
    )

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        adapter.collect(object(), object())

    assert caught.value.code == "LOW_FLOOR_CONFIG_MISMATCH"


def test_output_preflight_accepts_only_the_known_macos_tmp_alias() -> None:
    output = Path("/tmp") / "so101-task9-fix2-preflight-does-not-exist"
    assert not output.exists()

    assert perception_benchmark._preflight_output_root(output) == output


def test_output_preflight_rejects_user_created_symlink_parent(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    alias_parent = tmp_path / "user-alias"
    alias_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._preflight_output_root(alias_parent / "output")

    assert caught.value.code == "OUTPUT_ROOT_PARENT_INVALID"


def test_collect_uses_shared_output_preflight_before_dataset_or_adapter_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    alias_parent = tmp_path / "user-alias"
    alias_parent.symlink_to(real_parent, target_is_directory=True)
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
        source_commit="6" * 40,
        config=CONFIG,
        dataset_archive_sha256=("c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1"),
        output_root=alias_parent / "formal-run",
    )
    monkeypatch.setattr(
        perception_benchmark,
        "_inventory",
        lambda *a, **k: pytest.fail("unsafe output reached dataset boundary"),
    )
    monkeypatch.setattr(
        perception_benchmark,
        "_raw_adapter",
        lambda *a, **k: pytest.fail("unsafe output reached adapter boundary"),
    )

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._handle_collect(arguments)

    assert caught.value.code == "OUTPUT_ROOT_PARENT_INVALID"
    assert not arguments.output_root.exists()


def test_unlock_rechecks_output_after_archive_verify_before_access_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive = (
        tmp_path
        / "datasets/so101-v5-t004-yolo-seg-synthetic"
        / "so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz"
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"placeholder")
    for name in ("yolo.json", "grounded.json", "sealed.json"):
        (tmp_path / name).write_text("{}")
    output = tmp_path / "test-open"
    sealed_sha = perception_benchmark.sha256_bytes((tmp_path / "sealed.json").read_bytes())
    arguments = SimpleNamespace(
        config=CONFIG,
        archive=archive,
        expected_sha256=("c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1"),
        sealed_member_inventory=tmp_path / "sealed.json",
        yolo_threshold_lock=tmp_path / "yolo.json",
        grounded_sam_threshold_lock=tmp_path / "grounded.json",
        access_log=tmp_path / "access.ndjson",
        output_root=output,
    )
    monkeypatch.setattr(
        perception_benchmark,
        "sha256_file",
        lambda path: arguments.expected_sha256,
    )

    def verify_and_race(*args: object) -> object:
        output.mkdir()
        return SimpleNamespace(sealed_test_member_inventory_sha256=sealed_sha)

    monkeypatch.setattr(
        perception_benchmark.DatasetArchiveVerifier,
        "verify_archive",
        verify_and_race,
    )
    monkeypatch.setattr(
        perception_benchmark,
        "unlock_test_seal",
        lambda *a, **k: pytest.fail("access event appended after output race"),
    )

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._handle_unlock_test(arguments)

    assert caught.value.code == "OUTPUT_ROOT_ALREADY_EXISTS"
    assert not arguments.access_log.exists()


def _aggregation_plan_document(tmp_path: Path) -> dict[str, object]:
    return {
        "schema_version": "so101-perception-benchmark/aggregation-plan-v1",
        "dataset": {
            "root": str(tmp_path / "test-dataset"),
            "archive_sha256": ("c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1"),
            "inventory_sha256": "1" * 64,
            "test_access_event_sha256": "2" * 64,
            "sealed_member_inventory_sha256": "3" * 64,
            "threshold_lock_sha256s": ["4" * 64, "5" * 64],
        },
        "threshold_locks": {
            "yolo_seg": {"path": str(tmp_path / "yolo-lock.json"), "sha256": "4" * 64},
            "grounded_sam": {
                "path": str(tmp_path / "grounded-lock.json"),
                "sha256": "5" * 64,
            },
        },
        "runs": [
            {
                "platform": "macos",
                "model": "yolo_seg",
                "config": "TEST_RAW_FROZEN",
                "run_root": str(tmp_path / "run"),
                "expectation": str(tmp_path / "expectation.json"),
                "expectation_sha256": "6" * 64,
                "cold_process_samples": [],
                "resource_trace": None,
            }
        ],
        "source_commit": "7" * 40,
    }


def _resource_sample_document() -> dict[str, object]:
    return {
        "process_rss_bytes": 4096,
        "process_cpu_percent": 10.0,
        "gpu_memory_allocated_bytes": 1024,
        "gpu_memory_reserved_bytes": 2048,
        "gpu_utilization_percent": 30.0,
        "gpu_temperature_celsius": 40.0,
        "gpu_power_watts": 50.0,
        "unavailable_reasons": {},
        "tool_versions": {"resource-probe": "1.0"},
    }


def _plan_with_resource_sample(tmp_path: Path) -> dict[str, object]:
    plan = _aggregation_plan_document(tmp_path)
    plan["runs"][0]["resource_trace"] = {  # type: ignore[index]
        "sampling_frequency_hz": 10.0,
        "observations": [
            {
                "phase": "load",
                "monotonic_ns": 1,
                "formal_sample_index": None,
                "sample": _resource_sample_document(),
            }
        ],
    }
    return plan


@pytest.mark.parametrize(
    "mapping_drifts",
    [
        {"unavailable_reasons": [["gpu_power_watts", "probe unavailable"]]},
        {"tool_versions": [["resource-probe", "1.0"]]},
        {
            "unavailable_reasons": [["gpu_power_watts", "probe unavailable"]],
            "tool_versions": [["resource-probe", "1.0"]],
        },
    ],
)
def test_aggregate_rejects_resource_list_pairs_before_external_loaders(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mapping_drifts: dict[str, object],
) -> None:
    plan_document = _plan_with_resource_sample(tmp_path)
    sample = plan_document["runs"][0]["resource_trace"]["observations"][0][  # type: ignore[index]
        "sample"
    ]
    if "unavailable_reasons" in mapping_drifts:
        sample["gpu_power_watts"] = None
    sample.update(mapping_drifts)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(plan_document))
    monkeypatch.setattr(
        perception_benchmark,
        "verify_threshold_lock",
        lambda *a, **k: pytest.fail("resource type drift reached an external loader"),
    )

    result = perception_benchmark.main(
        [
            "aggregate",
            "--config",
            str(CONFIG),
            "--aggregation-plan",
            str(plan),
            "--aggregation-plan-sha256",
            perception_benchmark.sha256_bytes(plan.read_bytes()),
            "--output-root",
            str(tmp_path / "report"),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "AGGREGATION_PLAN_INVALID:" in captured.err
    assert "Traceback" not in captured.err


def test_aggregation_plan_accepts_raw_resource_mappings(tmp_path: Path) -> None:
    plan = _plan_with_resource_sample(tmp_path)

    _, _, runs, _ = perception_benchmark._validated_aggregation_plan(plan)

    assert runs[0]["resource_trace"] is not None


def test_aggregation_plan_rejects_resource_scalar_type_drift(tmp_path: Path) -> None:
    plan = _plan_with_resource_sample(tmp_path)
    sample = plan["runs"][0]["resource_trace"]["observations"][0][  # type: ignore[index]
        "sample"
    ]
    sample["process_rss_bytes"] = []

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._validated_aggregation_plan(plan)

    assert caught.value.code == "AGGREGATION_PLAN_INVALID"


@pytest.mark.parametrize(
    ("field", "drift"),
    [
        ("platform", []),
        ("model", {}),
        ("config", 7),
        ("cold_process_samples", {}),
        ("resource_trace", {"sampling_frequency_hz": "fast", "observations": []}),
    ],
)
def test_aggregation_plan_recursively_rejects_nested_type_drift(
    tmp_path: Path, field: str, drift: object
) -> None:
    plan = _aggregation_plan_document(tmp_path)
    plan["runs"][0][field] = drift  # type: ignore[index]

    with pytest.raises(perception_benchmark.BenchmarkError) as caught:
        perception_benchmark._validated_aggregation_plan(plan)

    assert caught.value.code == "AGGREGATION_PLAN_INVALID"


def test_aggregate_platform_list_is_stable_exit2_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_document = _aggregation_plan_document(tmp_path)
    plan_document["runs"][0]["platform"] = []  # type: ignore[index]
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(plan_document))
    locks = iter(
        (
            SimpleNamespace(
                lock_sha256="4" * 64,
                model="yolo_seg",
                source_commit="7" * 40,
            ),
            SimpleNamespace(
                lock_sha256="5" * 64,
                model="grounded_sam",
                source_commit="7" * 40,
            ),
        )
    )
    monkeypatch.setattr(
        perception_benchmark,
        "verify_threshold_lock",
        lambda *a, **k: next(locks),
    )
    monkeypatch.setattr(
        perception_benchmark,
        "load_dataset_inventory",
        lambda *a, **k: SimpleNamespace(
            dataset_root=tmp_path / "test-dataset",
            archive_sha256=plan_document["dataset"]["archive_sha256"],  # type: ignore[index]
            inventory_sha256="1" * 64,
        ),
    )
    monkeypatch.setattr(perception_benchmark, "load_truth_samples", lambda *a, **k: ())
    monkeypatch.setattr(perception_benchmark, "_expectation", lambda *a, **k: object())
    monkeypatch.setattr(
        perception_benchmark,
        "load_verified_run_evidence",
        lambda *a, **k: SimpleNamespace(),
    )

    result = perception_benchmark.main(
        [
            "aggregate",
            "--config",
            str(CONFIG),
            "--aggregation-plan",
            str(plan),
            "--aggregation-plan-sha256",
            perception_benchmark.sha256_bytes(plan.read_bytes()),
            "--output-root",
            str(tmp_path / "report"),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "AGGREGATION_PLAN_INVALID:" in captured.err
    assert "Traceback" not in captured.err
