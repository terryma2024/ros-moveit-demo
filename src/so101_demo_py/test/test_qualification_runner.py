from __future__ import annotations

import json
from pathlib import Path

import pytest
from so101_demo.application.qualification import (
    Lifecycle,
    RunStatus,
    build_parser,
    summarize_records,
    verify_batch,
)

BUNDLE = "a" * 64


def _record(index: int, lifecycle: Lifecycle) -> dict:
    return {
        "lifecycle": lifecycle.value,
        "status": RunStatus.SUCCESS.value,
        "bundle_sha256": BUNDLE,
        "simulation_session_id": (
            f"full-{index}" if lifecycle is Lifecycle.FULL_RESTART else "reset-shared"
        ),
        "reset_epoch": index,
        "physical_outcome": {"primary_failure": None},
        "clean_shutdown": {"passed": True},
        "artifact_sha256": {"manifest": "b" * 64},
    }


def test_run_parser_accepts_direct_bundle_sha() -> None:
    options = build_parser().parse_args(
        [
            "--batch-id",
            "batch",
            "--lifecycle",
            "FULL_RESTART",
            "--count",
            "5",
            "--fingerprint",
            BUNDLE,
            "--evidence-root",
            "/data/work/evidence",
            "--base-domain-id",
            "180",
            "--base-port",
            "27500",
        ]
    )

    assert options.fingerprint == BUNDLE


def test_summary_binds_every_record_to_direct_bundle() -> None:
    records = [_record(index, Lifecycle.FULL_RESTART) for index in range(1, 6)]

    summary = summarize_records(
        records,
        lifecycle=Lifecycle.FULL_RESTART,
        bundle_sha256=BUNDLE,
        target_count=5,
    )

    assert summary["qualified"] is True
    records[2]["bundle_sha256"] = "c" * 64
    assert summarize_records(
        records,
        lifecycle=Lifecycle.FULL_RESTART,
        bundle_sha256=BUNDLE,
        target_count=5,
    )["batch_invalid"] is True


def test_verify_batch_rejects_bundle_or_lifecycle_drift(tmp_path: Path) -> None:
    records = [_record(index, Lifecycle.RESET_WORLD) for index in range(1, 6)]
    manifest = {
        "schema_version": 2,
        "batch_id": "reset",
        "lifecycle": Lifecycle.RESET_WORLD.value,
        "bundle_sha256": BUNDLE,
        "records": records,
    }
    (tmp_path / "qualification-manifest.json").write_text(json.dumps(manifest))

    result = verify_batch(
        evidence_root=tmp_path,
        expected_lifecycle=Lifecycle.RESET_WORLD,
        expected_count=5,
        expected_bundle=BUNDLE,
    )

    assert result["qualified"] is True
    with pytest.raises(RuntimeError, match="bundle"):
        verify_batch(
            evidence_root=tmp_path,
            expected_lifecycle=Lifecycle.RESET_WORLD,
            expected_count=5,
            expected_bundle="d" * 64,
        )


def test_module_cli_supports_verify_batch_subcommand() -> None:
    options = build_parser().parse_args(
        [
            "verify-batch",
            "--evidence-root",
            "/data/work/evidence",
            "--expected-lifecycle",
            "FULL_RESTART",
            "--expected-count",
            "5",
            "--expected-bundle",
            BUNDLE,
        ]
    )

    assert options.command == "verify-batch"
