"""The no-resume formal CLI, the head-only report and the blocking Teleop owner."""

from __future__ import annotations

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
