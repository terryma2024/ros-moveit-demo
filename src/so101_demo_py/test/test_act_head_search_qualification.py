"""The no-resume formal CLI, the head-only report and the blocking Teleop owner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_qualification import (
    HEAD_SEARCH_QUALIFIED,
    qualification_parser,
    qualify_head_search,
    require_gate,
    serve_teleop,
)

PACKAGE = Path(__file__).parents[1]


def _qualified_report(root: Path, **overrides) -> dict:
    report = {
        "status": HEAD_SEARCH_QUALIFIED,
        "operation": "QUALIFICATION_RUN",
        "runtime_id": "runtime-0001",
        "head_search_runtime_id": "runtime-0001",
        "bundle_sha256": "a" * 64,
        "run_root": str(root),
        "owner": {"pid": 4242, "started_ticks": 900000},
        "bridge_socket_root": str(root / "bridge"),
    }
    report.update(overrides)
    return report


def test_cli_has_no_resume_or_stage_continuation() -> None:
    parser = qualification_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--resume", "old-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(["qualify", "--continue-from", "old-run"])


def test_the_runner_refuses_any_existing_run_root(tmp_path: Path) -> None:
    existing = tmp_path / "run"
    existing.mkdir()
    with pytest.raises(ValueError, match="RUN_ROOT_ALREADY_EXISTS"):
        serve_teleop(_qualified_report(existing), existing)


def test_head_only_report_does_not_grant_task8_ready(tmp_path: Path) -> None:
    report = qualify_head_search(
        {
            "run_root": tmp_path / "qualify",
            "evidence": {"production_smoke": "b" * 64, "scenarios": "c" * 64},
            "runtime_id": "runtime-0001",
            "bundle_sha256": "a" * 64,
        },
        tmp_path / "qualify",
    )
    assert report["status"] == HEAD_SEARCH_QUALIFIED
    with pytest.raises(ValueError, match="TASK8"):
        require_gate(report, "task8_live")
    for refused in ("release", "recorder", "retreat", "pick"):
        with pytest.raises(ValueError, match="TASK8"):
            require_gate(report, refused)


def test_serve_teleop_requires_closed_head_only_report(tmp_path: Path) -> None:
    unqualified = _qualified_report(tmp_path / "run", status="RUNNING")
    with pytest.raises(ValueError, match="HEAD_SEARCH_QUALIFIED_REQUIRED"):
        serve_teleop(unqualified, tmp_path / "run")


def test_serve_teleop_connection_descriptor_binds_exact_owner(tmp_path: Path) -> None:
    run_root = tmp_path / "fresh-run"
    connection = serve_teleop(_qualified_report(run_root), run_root, probe_only=True)
    assert connection["operation"] == "TELEOP_ACCEPTANCE"
    assert connection["runtime_id"] == connection["head_search_runtime_id"]
    assert connection["owner"]["pid"] > 0
    assert connection["owner"]["started_ticks"] > 0
    assert connection["bridge_socket_root"].startswith(str(tmp_path))
    with pytest.raises(ValueError, match="RUN_ROOT_ALREADY_EXISTS"):
        serve_teleop(_qualified_report(run_root), run_root, probe_only=True)


def test_the_qualification_parser_accepts_only_the_four_subcommands() -> None:
    parser = qualification_parser()
    for command in ("run", "verify-promoted-config", "qualify", "serve-teleop"):
        parsed = parser.parse_args([command, "--run-root", "/tmp/x"])
        assert parsed.command == command
    with pytest.raises(SystemExit):
        parser.parse_args(["resume", "--run-root", "/tmp/x"])


def test_the_binding_accepts_only_restricted_head_only_admission() -> None:
    from so101_demo.act.head_search_binding import validate_head_only_admission
    from so101_demo.act.head_search_qualification import restricted_admission

    for operation in ("GEOMETRY_SMOKE", "CALIBRATION_RUN", "QUALIFICATION_RUN"):
        accepted = validate_head_only_admission(restricted_admission(operation=operation))
        assert accepted["operation"] == operation
        assert accepted["one_stack"] is True and accepted["one_detector"] is True

    qualified = _qualified_report(Path("/tmp/does-not-matter"))
    teleop = validate_head_only_admission(
        restricted_admission(operation="TELEOP_ACCEPTANCE", report=qualified)
    )
    assert teleop["consumer"] == "teleop_head_camera"

    for refused in (
        {"operation": "RELEASE"},
        {"operation": "GEOMETRY_SMOKE", "one_stack": True, "one_detector": False},
        {
            "operation": "GEOMETRY_SMOKE",
            "one_stack": True,
            "one_detector": True,
            "consumers": ("recorder",),
        },
        {"operation": "TELEOP_ACCEPTANCE", "consumer": "recorder"},
    ):
        with pytest.raises(ValueError, match="HEAD_ONLY_OPERATION_REFUSED"):
            validate_head_only_admission(refused)


def test_serve_teleop_owns_teardown_and_cannot_resume(tmp_path: Path) -> None:
    """The blocking owner stops on SIGTERM, records its teardown, and the root can never be reused."""

    import multiprocessing
    import os
    import signal
    import time

    from so101_demo.act.head_search_qualification import serve_teleop as _serve

    run_root = tmp_path / "fresh-run"
    report = _qualified_report(run_root)

    def observed_teardown() -> dict:
        return {"controller_stopped": True, "graph_clear": True, "teardown": "clean"}

    context = multiprocessing.get_context("fork")
    process = context.Process(
        target=_serve, args=(report, run_root), kwargs={"teardown": observed_teardown}
    )
    process.start()
    try:
        descriptor = run_root / "head-camera-connection.json"
        deadline = time.monotonic() + 20.0
        while not descriptor.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert descriptor.is_file(), "the owner never published its connection descriptor"
        os.kill(process.pid, signal.SIGTERM)
        process.join(timeout=20.0)
        assert process.exitcode == 0
    finally:
        if process.is_alive():  # pragma: no cover - defensive teardown
            process.terminate()
            process.join(timeout=5.0)
    receipt = json.loads((run_root / "teardown-receipt.json").read_text(encoding="utf-8"))
    assert receipt["controller_stopped"] is True
    assert receipt["graph_clear"] is True
    with pytest.raises(ValueError, match="RUN_ROOT_ALREADY_EXISTS"):
        _serve(report, run_root, probe_only=True)


def test_teardown_is_reported_as_observed_not_assumed(tmp_path: Path) -> None:
    """Without a teardown that actually observed anything, the receipt must not claim success."""

    from so101_demo.act.head_search_qualification import serve_teleop as _serve

    run_root = tmp_path / "probe"
    report = _qualified_report(run_root)
    _serve(report, run_root, probe_only=True)
    state = json.loads((run_root / "calibration-state.json").read_text(encoding="utf-8"))
    assert state["state"] == "PROBED", "a probe must not be left looking like a running owner"

    other = tmp_path / "blocking"
    other_report = _qualified_report(other)
    import multiprocessing
    import os
    import signal
    import time

    process = multiprocessing.get_context("fork").Process(target=_serve, args=(other_report, other))
    process.start()
    try:
        descriptor = other / "head-camera-connection.json"
        deadline = time.monotonic() + 20.0
        while not descriptor.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        os.kill(process.pid, signal.SIGTERM)
        process.join(timeout=20.0)
    finally:
        if process.is_alive():  # pragma: no cover - defensive teardown
            process.terminate()
            process.join(timeout=5.0)
    receipt = json.loads((other / "teardown-receipt.json").read_text(encoding="utf-8"))
    assert receipt["controller_stopped"] is False
    assert receipt["graph_clear"] is False
    assert receipt["teardown"] == "not-attempted"


def test_the_owner_records_the_kernel_start_ticks_and_the_probe_reports_them(
    tmp_path: Path,
) -> None:
    from so101_demo.act.head_search_qualification import process_start_ticks, serve_teleop

    assert process_start_ticks() > 0
    run_root = tmp_path / "probe"
    connection = serve_teleop(_qualified_report(run_root), run_root, probe_only=True)
    assert connection["owner"]["started_ticks"] == process_start_ticks()
    assert connection["owner"]["pid"] > 0
