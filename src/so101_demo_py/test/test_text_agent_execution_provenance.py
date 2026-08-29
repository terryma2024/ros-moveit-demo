from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
from ament_index_python.packages import get_package_prefix

from so101_demo.application.text_agent import AgentResult, AgentStatus


FULL_SHA = re.compile(r"[0-9a-f]{64}")


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _options(
    evidence_root: Path,
    *,
    source_commit: str,
    installed_prefix: str,
):
    from so101_demo.cli.text_pick_agent import build_parser

    return build_parser().parse_args(
        [
            "--instruction",
            "Pick the plastic cup.",
            "--mode",
            "execute",
            "--execute",
            "--session-id",
            "provenance-session",
            "--expected-reset-epoch",
            "4",
            "--evidence-root",
            str(evidence_root),
            "--source-commit",
            source_commit,
            "--installed-prefix",
            installed_prefix,
        ]
    )


@pytest.mark.parametrize("source_commit", ["abc123", "a" * 39, "g" * 40])
def test_execute_rejects_noncomplete_git_commit_before_context_creation(
    tmp_path: Path, source_commit: str
) -> None:
    """Catches provenance strings that look recorded but are not full Git object IDs."""

    from so101_demo.cli.text_pick_agent import _valid_execute_context

    prefix = str(Path(get_package_prefix("so101_demo_py")).resolve())
    context, reason = _valid_execute_context(
        _options(tmp_path, source_commit=source_commit, installed_prefix=prefix)
    )

    assert context is None
    assert reason == "EXECUTION_SOURCE_COMMIT_INVALID"


def test_execute_rejects_nonexistent_and_wrong_canonical_prefix(tmp_path: Path) -> None:
    """Catches trusting an absolute prefix string without resolving package provenance."""

    from so101_demo.cli.text_pick_agent import _valid_execute_context

    nonexistent = tmp_path / "missing-prefix"
    context, reason = _valid_execute_context(
        _options(tmp_path, source_commit=_head(), installed_prefix=str(nonexistent))
    )
    assert context is None
    assert reason == "EXECUTION_INSTALLED_PREFIX_INVALID"

    wrong = tmp_path / "wrong-prefix"
    wrong.mkdir()
    context, reason = _valid_execute_context(
        _options(tmp_path, source_commit=_head(), installed_prefix=str(wrong))
    )
    assert context is None
    assert reason == "EXECUTION_INSTALLED_PREFIX_MISMATCH"


def test_execute_rejects_declared_source_commit_mismatch(tmp_path: Path) -> None:
    """Catches treating a caller-supplied full SHA as verified runtime source."""

    from so101_demo.cli.text_pick_agent import _valid_execute_context

    prefix = str(Path(get_package_prefix("so101_demo_py")).resolve())
    mismatched = "0" * 40 if _head() != "0" * 40 else "1" * 40
    context, reason = _valid_execute_context(
        _options(tmp_path, source_commit=mismatched, installed_prefix=prefix)
    )

    assert context is None
    assert reason == "EXECUTION_SOURCE_COMMIT_MISMATCH"


def test_verified_context_canonicalizes_symlink_and_projects_hashes(tmp_path: Path) -> None:
    """Catches lexical-prefix comparison and provenance that omits runtime artifact hashes."""

    from so101_demo.cli.text_pick_agent import _valid_execute_context

    prefix = Path(get_package_prefix("so101_demo_py")).resolve()
    prefix_link = tmp_path / "prefix-link"
    prefix_link.symlink_to(prefix, target_is_directory=True)
    context, reason = _valid_execute_context(
        _options(
            tmp_path,
            source_commit=_head().upper(),
            installed_prefix=str(prefix_link),
        )
    )

    assert reason is None
    assert context is not None
    assert context.source_commit == _head()
    assert context.installed_prefix == str(prefix)
    projection = context.execution_provenance.to_dict()
    assert projection["schema_version"] == 1
    assert projection["source_commit"] == _head()
    assert projection["installed_prefix"] == str(prefix)
    assert projection["session_id"] == "provenance-session"
    assert projection["expected_reset_epoch"] == 4
    assert projection["evidence_root"] == str(tmp_path.resolve())
    for artifact in ("entrypoint", "module", "executable"):
        assert Path(projection[artifact]["path"]).is_absolute()
        assert FULL_SHA.fullmatch(projection[artifact]["sha256"])


class RecordingAgent:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def handle(self, request: object) -> AgentResult:
        self.requests.append(request)
        return AgentResult(
            request_id=request.request_id,
            status=AgentStatus.RUNTIME_COMPLETED,
            reason_code=None,
            metadata=None,
            command=None,
            capability="dynamic_cup_pick_place",
            dispatch=True,
            runtime_session_id="provenance-session",
            state_trace=(AgentStatus.RUNTIME_STARTED, AgentStatus.RUNTIME_COMPLETED),
        )


def test_cli_persists_verified_provenance_before_agent_dispatch(tmp_path: Path, capsys) -> None:
    """Catches verified provenance existing only transiently in process memory."""

    from so101_demo.cli import text_pick_agent

    prefix = str(Path(get_package_prefix("so101_demo_py")).resolve())
    agent = RecordingAgent()
    exit_code = text_pick_agent.main(
        [
            "--instruction",
            "Pick the plastic cup.",
            "--request-id",
            "req-persist",
            "--mode",
            "execute",
            "--execute",
            "--confirmation-digest",
            "sha256:v1:" + "0" * 64,
            "--session-id",
            "provenance-session",
            "--expected-reset-epoch",
            "4",
            "--evidence-root",
            str(tmp_path),
            "--source-commit",
            _head(),
            "--installed-prefix",
            prefix,
        ],
        _agent=agent,
    )

    assert exit_code == 0
    assert len(agent.requests) == 1
    request_projection = agent.requests[0].execution_provenance.to_dict()
    persisted = list((tmp_path / "text-agent-provenance").glob("*.json"))
    assert len(persisted) == 1
    document = json.loads(persisted[0].read_text())
    assert document == {
        "request_id": "req-persist",
        "execution_provenance": request_projection,
    }
    assert hashlib.sha256(persisted[0].read_bytes()).hexdigest()
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["status"] == "RUNTIME_COMPLETED"
