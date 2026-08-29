from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from unittest.mock import ANY

import pytest

from so101_demo.application.text_agent import AgentResult, AgentStatus
from so101_demo.core.task_command import TaskCommand


@dataclass
class StubAgent:
    result: AgentResult
    requests: list[object]

    def __init__(self, result: AgentResult) -> None:
        self.result = result
        self.requests = []

    def handle(self, request: object) -> AgentResult:
        self.requests.append(request)
        return self.result


def result(
    status: AgentStatus = AgentStatus.DISPATCH_PREVIEW,
    *,
    request_id: str = "req-fixed",
    dispatch: bool = False,
    reason_code: str | None = None,
) -> AgentResult:
    command = TaskCommand("plastic_cup", "pick", ())
    trace = (
        (AgentStatus.RUNTIME_STARTED, status)
        if dispatch
        else (status,)
    )
    return AgentResult(
        request_id=request_id,
        status=status,
        reason_code=reason_code,
        metadata=None,
        command=command,
        capability="dynamic_cup_pick_place",
        dispatch=dispatch,
        runtime_session_id="session-1" if dispatch else None,
        state_trace=trace,
    )


def output(capsys) -> dict[str, object]:
    rendered = capsys.readouterr().out
    assert rendered.count("\n") == 1
    return json.loads(rendered)


def test_cli_defaults_to_preview_and_prints_one_json_document(capsys) -> None:
    from so101_demo.cli import text_pick_agent

    agent = StubAgent(result())

    assert text_pick_agent.main(
        ["--instruction", "帮我拿杯子", "--request-id", "req-fixed"], _agent=agent
    ) == 0

    document = output(capsys)
    assert document["status"] == "DISPATCH_PREVIEW"
    assert document["dispatch"] is False
    assert document["state_trace"] == ["DISPATCH_PREVIEW"]
    assert agent.requests[0].mode == "preview"


@pytest.mark.parametrize(
    ("arguments", "reason_code"),
    [
        (["--mode", "execute"], "PARTIAL_EXECUTE_AUTHORIZATION"),
        (["--execute"], "PARTIAL_EXECUTE_AUTHORIZATION"),
    ],
)
def test_cli_rejects_partial_execute_before_agent_or_ros(
    capsys, arguments: list[str], reason_code: str
) -> None:
    from so101_demo.cli import text_pick_agent

    agent = StubAgent(result())

    assert text_pick_agent.main(
        ["--instruction", "帮我拿杯子", *arguments], _agent=agent
    ) == 1

    assert agent.requests == []
    assert output(capsys) == {
        "dispatch": False,
        "reason_code": reason_code,
        "request_id": ANY,
        "state_trace": ["DISPATCH_REJECTED"],
        "status": "DISPATCH_REJECTED",
    }


def test_cli_rejects_wrong_backend_before_agent(capsys) -> None:
    from so101_demo.cli import text_pick_agent

    agent = StubAgent(result())

    assert text_pick_agent.main(
        ["--instruction", "帮我拿杯子", "--backend", "gazebo"], _agent=agent
    ) == 1

    assert agent.requests == []
    assert output(capsys)["reason_code"] == "BACKEND_NOT_QUALIFIED"


@pytest.mark.parametrize(
    ("arguments", "reason_code"),
    [
        ([], "EXECUTION_SESSION_ID_REQUIRED"),
        (["--session-id", "  "], "EXECUTION_SESSION_ID_REQUIRED"),
        (["--session-id", "session-1"], "EXECUTION_RESET_EPOCH_INVALID"),
        (
            ["--session-id", "session-1", "--expected-reset-epoch", "true"],
            "EXECUTION_RESET_EPOCH_INVALID",
        ),
        (
            ["--session-id", "session-1", "--expected-reset-epoch", "-1"],
            "EXECUTION_RESET_EPOCH_INVALID",
        ),
        (
            ["--session-id", "session-1", "--expected-reset-epoch", "0"],
            "EXECUTION_EVIDENCE_ROOT_INVALID",
        ),
        (
            [
                "--session-id", "session-1", "--expected-reset-epoch", "0",
                "--evidence-root", "relative",
            ],
            "EXECUTION_EVIDENCE_ROOT_INVALID",
        ),
        (
            [
                "--session-id", "session-1", "--expected-reset-epoch", "0",
                "--evidence-root", "/tmp/evidence",
            ],
            "EXECUTION_SOURCE_COMMIT_INVALID",
        ),
        (
            [
                "--session-id", "session-1", "--expected-reset-epoch", "0",
                "--evidence-root", "/tmp/evidence", "--source-commit", "UNRECORDED_SOURCE",
            ],
            "EXECUTION_SOURCE_COMMIT_INVALID",
        ),
        (
            [
                "--session-id", "session-1", "--expected-reset-epoch", "0",
                "--evidence-root", "/tmp/evidence", "--source-commit", "abc123",
            ],
            "EXECUTION_INSTALLED_PREFIX_INVALID",
        ),
        (
            [
                "--session-id", "session-1", "--expected-reset-epoch", "0",
                "--evidence-root", "/tmp/evidence", "--source-commit", "abc123",
                "--installed-prefix", "relative",
            ],
            "EXECUTION_INSTALLED_PREFIX_INVALID",
        ),
    ],
)
def test_execute_requires_explicit_valid_runtime_provenance_before_agent(
    capsys, arguments: list[str], reason_code: str
) -> None:
    from so101_demo.cli import text_pick_agent

    agent = StubAgent(result())
    execute = ["--instruction", "帮我拿杯子", "--mode", "execute", "--execute"]

    assert text_pick_agent.main([*execute, *arguments], _agent=agent) == 1

    assert agent.requests == []
    assert output(capsys)["reason_code"] == reason_code


@pytest.mark.parametrize(
    ("status", "dispatch", "expected_exit"),
    [
        (AgentStatus.PLANNER_FAILED, False, 1),
        (AgentStatus.COMMAND_INVALID, False, 1),
        (AgentStatus.DISPATCH_REJECTED, False, 1),
        (AgentStatus.DISPATCH_PREVIEW, False, 0),
        (AgentStatus.RUNTIME_STARTED, True, 1),
        (AgentStatus.RUNTIME_FAILED, True, 1),
        (AgentStatus.RUNTIME_COMPLETED, True, 0),
    ],
)
def test_cli_maps_agent_statuses_to_stable_exit_codes(
    capsys, status: AgentStatus, dispatch: bool, expected_exit: int
) -> None:
    from so101_demo.cli import text_pick_agent

    agent = StubAgent(result(status, dispatch=dispatch))

    assert text_pick_agent.main(
        ["--instruction", "帮我拿杯子", "--request-id", "req-fixed"], _agent=agent
    ) == expected_exit
    assert output(capsys)["status"] == status.value


def test_preview_does_not_import_rclpy(monkeypatch, capsys) -> None:
    from so101_demo.cli import text_pick_agent

    agent = StubAgent(result())
    monkeypatch.setitem(sys.modules, "rclpy", None)

    assert text_pick_agent.main(["--instruction", "帮我拿杯子"], _agent=agent) == 0

    assert output(capsys)["status"] == "DISPATCH_PREVIEW"


def test_cli_composes_exact_default_planners_and_reads_only_environment_key(
    monkeypatch, capsys
) -> None:
    from so101_demo.cli import text_pick_agent

    calls: dict[str, object] = {}

    class DeepSeek:
        def __init__(self, api_key, **kwargs) -> None:
            calls["deepseek"] = (api_key, kwargs)

    class Ollama:
        def __init__(self, **kwargs) -> None:
            calls["ollama"] = kwargs

    class Chain:
        def __init__(self, primary, fallback) -> None:
            calls["chain"] = (primary, fallback)

    class Agent:
        def __init__(self, planner, executor) -> None:
            calls["agent"] = (planner, executor)

        def handle(self, request) -> AgentResult:
            return result(request_id=request.request_id)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-secret")
    monkeypatch.setattr(text_pick_agent, "DeepSeekPlanner", DeepSeek)
    monkeypatch.setattr(text_pick_agent, "OllamaPlanner", Ollama)
    monkeypatch.setattr(text_pick_agent, "PlannerChain", Chain)
    monkeypatch.setattr(text_pick_agent, "TextAgent", Agent)

    assert text_pick_agent.main(["--instruction", "帮我拿杯子", "--request-id", "req-fixed"]) == 0

    assert calls["deepseek"] == (
        "test-only-secret",
        {
            "model": "deepseek-v4-flash",
            "endpoint": "https://api.deepseek.com/chat/completions",
            "timeout_s": 8.0,
        },
    )
    assert calls["ollama"] == {
        "model": "qwen3.5:4b",
        "endpoint": "http://127.0.0.1:11434/api/chat",
        "timeout_s": 12.0,
    }
    assert "test-only-secret" not in capsys.readouterr().out


def test_cli_builds_runtime_executor_only_for_valid_execute(monkeypatch, capsys) -> None:
    from so101_demo.cli import text_pick_agent

    calls: dict[str, object] = {}

    class Context:
        def __init__(self, **kwargs) -> None:
            calls["context"] = kwargs

    class Executor:
        def __init__(self, context) -> None:
            calls["executor"] = context

    class Agent:
        def __init__(self, planner, executor) -> None:
            calls["agent_executor"] = executor

        def handle(self, request) -> AgentResult:
            return result(
                AgentStatus.RUNTIME_COMPLETED,
                request_id=request.request_id,
                dispatch=True,
            )

    monkeypatch.setattr(text_pick_agent, "DynamicRuntimeContext", Context)
    monkeypatch.setattr(text_pick_agent, "DynamicCupPickPlaceExecutor", Executor)
    monkeypatch.setattr(text_pick_agent, "TextAgent", Agent)
    monkeypatch.setattr(text_pick_agent, "DeepSeekPlanner", lambda *_a, **_k: object())
    monkeypatch.setattr(text_pick_agent, "OllamaPlanner", lambda **_k: object())
    monkeypatch.setattr(text_pick_agent, "PlannerChain", lambda *_a: object())

    assert text_pick_agent.main(
        [
            "--instruction", "帮我拿杯子", "--mode", "execute", "--execute",
            "--session-id", "session-1", "--expected-reset-epoch", "0",
            "--evidence-root", "/tmp/evidence", "--source-commit", "abc123",
            "--installed-prefix", "/tmp/install", "--request-id", "req-fixed",
        ]
    ) == 0

    assert calls["context"] == {
        "session_id": "session-1", "expected_reset_epoch": 0,
        "evidence_root": ANY, "source_commit": "abc123",
        "installed_prefix": "/tmp/install",
    }
    assert str(calls["context"]["evidence_root"]) == "/tmp/evidence"
    assert output(capsys)["runtime_session_id"] == "session-1"


def test_cli_uses_requested_id_or_generates_one(monkeypatch, capsys) -> None:
    from so101_demo.cli import text_pick_agent

    ids = iter(("generated-id",))
    monkeypatch.setattr(text_pick_agent, "new_request_id", lambda: next(ids))
    agent = StubAgent(result(request_id="generated-id"))

    assert text_pick_agent.main(["--instruction", "帮我拿杯子"], _agent=agent) == 0
    assert agent.requests[0].request_id == "generated-id"
    assert output(capsys)["request_id"] == "generated-id"
