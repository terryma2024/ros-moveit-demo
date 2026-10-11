"""The parser, the frozen configuration and the dry runs."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from perception_benchmark_cli_support import (
    ARCHIVE_DIRNAME,
    ARCHIVE_FILENAME,
    ARCHIVE_SHA256,
    CONFIG,
    FIXTURE,
    PACKAGE_ROOT,
)
import pytest

from so101_demo.cli import perception_benchmark
from so101_demo.cli.benchmark import collect as perception_benchmark_collect
from so101_demo.cli.benchmark import common as perception_benchmark_common
from so101_demo.cli.benchmark import dry_run as perception_benchmark_dry_run
from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.adapters.base import (
    CollectionMode,
    RawDetectionResult,
)
from so101_demo.perception_benchmark.codec import (
    atomic_write_json,
    encode_mask_rle,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    YOLO_MODEL_ID,
    MaskRef,
    RawCandidate,
    RuntimeProvenance,
)
from so101_demo.perception_benchmark.reporting.writer import verify_evidence_index
from so101_demo.perception_benchmark.timing import PhaseTimingBreakdown


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
    calibrate = action.choices["calibrate"]
    workers = next(item for item in calibrate._actions if item.dest == "calibration_workers")
    assert workers.default == 1
    assert workers.type is int


def test_setup_has_one_console_entry_and_packages_benchmark_yaml() -> None:
    setup_text = (PACKAGE_ROOT / "setup.py").read_text()
    entry = "perception_benchmark = so101_demo.cli.perception_benchmark:main"
    assert setup_text.count(entry) == 1
    assert "installed_resources()" in setup_text
    assert CONFIG.is_file()


def test_config_contains_frozen_literals() -> None:
    text = CONFIG.read_text()
    for literal in (
        "datasets/so101-v5-t005-grounded-sam-postfix/"
        "so101-v5-t005-grounded-sam-postfix-r4.tar.gz",
        "8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832",
        "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781",
        "b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05",
        "a2bb814dd30d776dcf7e30523b00659f4f141c71",
        "de431c4043854a71d8101e17995dfe596bf101a5",
        "source: resolved_ultralytics_predictor_args",
        "warmup_images: 5",
        "cold_processes: 3",
        "seed: 20260902",
        "repetitions: 10000",
        "/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079",
        "/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079",
    ):
        assert literal in text
    assert "nms:\n        source:" in text


def test_checked_in_config_matches_cli_frozen_hash() -> None:
    assert sha256_bytes(CONFIG.read_bytes()) == perception_benchmark_common._CONFIG_SHA256


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
                / ARCHIVE_DIRNAME
                / ARCHIVE_FILENAME
            ),
            "--expected-sha256",
            ARCHIVE_SHA256,
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
    plan = perception_benchmark_common.build_dry_run_plan(
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
        archive_sha256=ARCHIVE_SHA256,
        scenario_counts={scenario: 50 for scenario in perception_benchmark_common._SCENARIOS},
        samples=samples,
    )
    monkeypatch.setattr(perception_benchmark_collect, "_inventory", lambda *args: inventory)
    monkeypatch.setattr(perception_benchmark_dry_run, "_inventory", lambda *args: inventory)
    monkeypatch.setattr(
        perception_benchmark_dry_run,
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
        perception_benchmark_collect,
        "_raw_adapter",
        lambda arguments, config: FakeAdapter(arguments.model, arguments.output_root),
    )
    monkeypatch.setattr(
        perception_benchmark_dry_run,
        "_raw_adapter",
        lambda arguments, config: FakeAdapter(arguments.model, arguments.output_root),
    )
    monkeypatch.setattr(
        perception_benchmark_collect,
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
    monkeypatch.setattr(
        perception_benchmark_dry_run,
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
            "b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05",
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
