from __future__ import annotations

import json
from pathlib import Path

import pytest
from so101_demo.application import qualification as qualification_module
from so101_demo.application.qualification import (
    Lifecycle,
    ProductionQualificationRunner,
    RunStatus,
    build_parser,
    summarize_records,
    verify_batch,
)

BUNDLE = "a" * 64


def test_scene_readiness_accepts_shared_cli_json_receipt() -> None:
    success = (
        '[scene_setup-7] {"backend": "mujoco", "evidence": '
        '{"primitive_counts": {"pedestal": 1, "plastic_cup": 13, "table": 1}}, '
        '"failure_code": null, "phase": "READ_BACK", "success": true}'
    )
    failed = success.replace('"success": true', '"success": false')
    unrelated = success.replace("[scene_setup-7]", "[another_process-7]")

    assert qualification_module._scene_setup_succeeded(success)
    assert qualification_module._scene_setup_succeeded("SCENE_SETUP_OK")
    assert not qualification_module._scene_setup_succeeded(failed)
    assert not qualification_module._scene_setup_succeeded(unrelated)


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


def test_headless_qualification_does_not_call_interactive_viewer() -> None:
    runner = object.__new__(ProductionQualificationRunner)
    runner.headless = True
    runner._post_command = lambda *_args, **_kwargs: pytest.fail("viewer was called")

    result = runner._configure_camera(object(), "lease")

    assert result == {
        "skipped": True,
        "reason": "headless MuJoCo has no interactive viewer",
    }


def test_ordered_shutdown_signals_only_stack_supervisor(tmp_path: Path) -> None:
    class Process:
        returncode = None

        def __init__(self) -> None:
            self.signals = []

        def poll(self):
            return None

        def send_signal(self, value):
            self.signals.append(value)

        def wait(self, timeout):
            self.returncode = 0
            return 0

    process = Process()
    log = tmp_path / "launch.log"
    log.write_text("SO101_MOVE_GROUP_ORDERED_SHUTDOWN_OK\n")
    handle = type(
        "Handle",
        (),
        {"process": process, "process_group_id": 999999, "log_path": log},
    )()

    result = ProductionQualificationRunner.stop_stack(handle)

    assert process.signals == [2]
    assert result["passed"] is True
