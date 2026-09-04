from __future__ import annotations

import json
from pathlib import Path

import pytest
from so101_demo.training.saved_checkpoint_revalidation import (
    CheckpointRevalidationError,
    select_deployable_checkpoint,
    write_checkpoint_revalidation,
)


def _report(epoch: int, *, f1: float, recall: float = 0.5, fp: int = 2):
    return {
        "epoch": epoch,
        "selected": {
            "epoch": epoch,
            "box_threshold": 0.25,
            "text_threshold": 0.25,
            "tp": 5,
            "fp": fp,
            "fn": 5,
            "precision": 0.5,
            "recall": recall,
            "f1": f1,
            "small_target_recall": 0.4,
            "multi_cup_recall": 0.3,
        },
    }


def test_deployable_selection_uses_frozen_rank_and_earlier_epoch_tie_break() -> None:
    winner = select_deployable_checkpoint(
        (_report(2, f1=0.7), _report(1, f1=0.7), _report(3, f1=0.6))
    )

    assert winner["epoch"] == 1
    assert select_deployable_checkpoint(
        (_report(1, f1=0.7), _report(2, f1=0.8))
    )["epoch"] == 2


def test_checkpoint_revalidation_output_is_exclusive_and_hash_bound(tmp_path: Path) -> None:
    output = tmp_path / "epoch-007"
    selected = _report(7, f1=0.8)["selected"]
    grid = [dict(selected, box_threshold=index / 100) for index in range(100)]

    report = write_checkpoint_revalidation(
        output_root=output,
        source_commit="a" * 40,
        checkpoint_root=tmp_path / "checkpoint",
        checkpoint_manifest_sha256="b" * 64,
        val_inventory_sha256="c" * 64,
        selected=selected,
        grid_results=grid,
        runtime={"device": "cuda:0", "dtype": "float32", "cpu_fallback": False},
        score_range={"minimum": 0.05, "maximum": 0.9, "count": 20},
    )

    assert report["epoch"] == 7
    assert len(report["grid_results"]) == 100
    assert json.loads((output / "manifest.json").read_text())["status"] == "VALID"
    with pytest.raises(CheckpointRevalidationError, match="OUTPUT_ROOT_ALREADY_EXISTS"):
        write_checkpoint_revalidation(
            output_root=output,
            source_commit="a" * 40,
            checkpoint_root=tmp_path / "checkpoint",
            checkpoint_manifest_sha256="b" * 64,
            val_inventory_sha256="c" * 64,
            selected=selected,
            grid_results=grid,
            runtime={"device": "cuda:0", "dtype": "float32", "cpu_fallback": False},
            score_range={"minimum": 0.05, "maximum": 0.9, "count": 20},
        )
