"""Argument builders and helpers shared by the benchmark command tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from so101_demo.perception_benchmark.contracts import (
    RunKind,
)

PACKAGE_ROOT = Path(__file__).parents[1]


CONFIG = PACKAGE_ROOT / "config/perception_benchmark/benchmark.yaml"


FIXTURE = PACKAGE_ROOT / "benchmark_test/fixtures/perception_benchmark/dry-run-adapters.json"


ARCHIVE_DIRNAME = "datasets/so101-v5-t005-grounded-sam-postfix"


ARCHIVE_FILENAME = "so101-v5-t005-grounded-sam-postfix-r4.tar.gz"


ARCHIVE_SHA256 = "8424de68a8cc18961ab4732cba3c2486161f733b638638c82da6e1761e3ac832"


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
        dataset_archive_sha256=ARCHIVE_SHA256,
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
