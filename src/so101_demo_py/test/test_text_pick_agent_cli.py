from __future__ import annotations

import json
import sys
from pathlib import Path
from builtins import __import__ as builtin_import
from dataclasses import dataclass
from unittest.mock import ANY

import pytest

from so101_demo.application.text_agent import AgentResult, AgentStatus
from so101_demo.core.task_command import TaskCommand
from so101_demo.ports.task_planner import PlannerCandidate, PlannerMetadata


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


@pytest.mark.parametrize(
    ("arguments", "reason_code"),
    [
        (["--skip-confirmation"], "CONFIRMATION_BYPASS_REQUIRES_EXECUTE"),
        (
            [
                "--mode",
                "execute",
                "--execute",
                "--skip-confirmation",
                "--confirmation-digest",
                "sha256:v1:" + "0" * 64,
            ],
            "CONFIRMATION_MODE_CONFLICT",
        ),
    ],
)
def test_cli_rejects_invalid_confirmation_bypass_before_provenance_or_agent(
    capsys,
    arguments: list[str],
    reason_code: str,
) -> None:
    """Catches an invalid bypass reaching runtime provenance or the provider."""

    from so101_demo.cli import text_pick_agent

    agent = StubAgent(result())

    assert text_pick_agent.main(
        ["--instruction", "帮我拿杯子", *arguments], _agent=agent
    ) == 1

    assert agent.requests == []
    assert output(capsys)["reason_code"] == reason_code


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
                "--evidence-root", "/tmp/evidence", "--source-commit", "a" * 40,
            ],
            "EXECUTION_INSTALLED_PREFIX_INVALID",
        ),
        (
            [
                "--session-id", "session-1", "--expected-reset-epoch", "0",
                "--evidence-root", "/tmp/evidence", "--source-commit", "a" * 40,
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


def test_production_preview_composition_does_not_import_ros_runtime(
    monkeypatch, capsys
) -> None:
    from so101_demo.cli import text_pick_agent

    candidate = PlannerCandidate(
        {
            "outcome": "supported",
            "command": {
                "target_object": "plastic_cup",
                "action": "pick",
                "constraints": {},
            },
        },
        PlannerMetadata("deepseek", "test-model", 1, None, None, None, False),
    )

    class Planner:
        def plan(self, _instruction):
            return candidate

    original_import = builtin_import

    def guarded_import(name, *args, **kwargs):
        if name == "rclpy" or name.startswith("so101_demo.ros"):
            raise AssertionError(f"ROS import forbidden during preview: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(text_pick_agent, "DeepSeekPlanner", lambda *_a, **_k: Planner())
    monkeypatch.setattr(text_pick_agent, "OllamaPlanner", lambda **_k: Planner())
    monkeypatch.setattr("builtins.__import__", guarded_import)

    assert text_pick_agent.main(["--instruction", "帮我拿杯子"]) == 0

    document = output(capsys)
    assert document["status"] == "DISPATCH_PREVIEW"
    assert document["dispatch"] is False
    assert document["command"] == {
        "target_object": "plastic_cup", "action": "pick", "constraints": {}
    }


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


def test_cli_normalizes_provider_options_before_composition(monkeypatch, capsys) -> None:
    from so101_demo.cli import text_pick_agent

    calls: dict[str, object] = {}

    class Agent:
        def __init__(self, _planner, _executor) -> None:
            pass

        def handle(self, request) -> AgentResult:
            return result(request_id=request.request_id)

    monkeypatch.setattr(
        text_pick_agent,
        "DeepSeekPlanner",
        lambda _key, **kwargs: calls.setdefault("deepseek", kwargs),
    )
    monkeypatch.setattr(
        text_pick_agent,
        "OllamaPlanner",
        lambda **kwargs: calls.setdefault("ollama", kwargs),
    )
    monkeypatch.setattr(text_pick_agent, "PlannerChain", lambda primary, fallback: object())
    monkeypatch.setattr(text_pick_agent, "TextAgent", Agent)

    assert text_pick_agent.main(
        [
            "--instruction", "帮我拿杯子",
            "--deepseek-model", " deepseek-v4-flash ",
            "--deepseek-endpoint", " https://api.deepseek.com/chat/completions ",
            "--ollama-model", " qwen3.5:4b ",
            "--ollama-endpoint", " http://localhost:21434/api/chat ",
        ]
    ) == 0

    assert calls == {
        "deepseek": {
            "model": "deepseek-v4-flash",
            "endpoint": "https://api.deepseek.com/chat/completions",
            "timeout_s": 8.0,
        },
        "ollama": {
            "model": "qwen3.5:4b",
            "endpoint": "http://localhost:21434/api/chat",
            "timeout_s": 12.0,
        },
    }
    assert output(capsys)["status"] == "DISPATCH_PREVIEW"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--deepseek-model", "   "],
        ["--deepseek-endpoint", "   "],
        ["--ollama-model", "   "],
        ["--ollama-endpoint", "   "],
        ["--deepseek-timeout-s", "0"],
        ["--deepseek-timeout-s", "-1"],
        ["--deepseek-timeout-s", "nan"],
        ["--deepseek-timeout-s", "inf"],
        ["--ollama-timeout-s", "0"],
        ["--ollama-timeout-s", "-1"],
        ["--ollama-timeout-s", "nan"],
        ["--ollama-timeout-s", "inf"],
        ["--deepseek-model", "deepseek-v3"],
        ["--deepseek-endpoint", "https://example.test/chat/completions"],
        ["--ollama-model", "qwen2.5:4b"],
        ["--ollama-endpoint", "http://10.0.0.4:11434/api/chat"],
    ],
)
def test_provider_options_are_rejected_before_provider_or_agent(
    capsys, arguments: list[str]
) -> None:
    from so101_demo.cli import text_pick_agent

    agent = StubAgent(result())

    assert text_pick_agent.main(
        ["--instruction", "帮我拿杯子", *arguments], _agent=agent
    ) == 1

    assert agent.requests == []
    assert output(capsys)["reason_code"] == "PROVIDER_OPTIONS_INVALID"


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_cup_pose_timeout_is_rejected_before_provider_or_agent(
    capsys, value: str
) -> None:
    from so101_demo.cli import text_pick_agent

    agent = StubAgent(result())

    assert text_pick_agent.main(
        [
            "--instruction",
            "帮我拿杯子",
            "--cup-pose-timeout-s",
            value,
        ],
        _agent=agent,
    ) == 1

    assert agent.requests == []
    assert output(capsys)["reason_code"] == "CUP_POSE_TIMEOUT_INVALID"


def test_cli_builds_runtime_executor_only_for_valid_execute(
    monkeypatch, capsys, tmp_path
) -> None:
    from so101_demo.cli import text_pick_agent
    import subprocess
    from pathlib import Path
    from ament_index_python.packages import get_package_prefix

    calls: dict[str, object] = {}

    class Executor:
        def __init__(self, context, *, cup_pose_timeout_s) -> None:
            calls["executor"] = context
            calls["cup_pose_timeout_s"] = cup_pose_timeout_s

    class Agent:
        def __init__(self, planner, executor) -> None:
            calls["agent_executor"] = executor

        def handle(self, request) -> AgentResult:
            return result(
                AgentStatus.RUNTIME_COMPLETED,
                request_id=request.request_id,
                dispatch=True,
            )

    monkeypatch.setattr(text_pick_agent, "DynamicCupPickPlaceExecutor", Executor)
    monkeypatch.setattr(text_pick_agent, "TextAgent", Agent)
    monkeypatch.setattr(text_pick_agent, "DeepSeekPlanner", lambda *_a, **_k: object())
    monkeypatch.setattr(text_pick_agent, "OllamaPlanner", lambda **_k: object())
    monkeypatch.setattr(text_pick_agent, "PlannerChain", lambda *_a: object())
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    prefix = str(Path(get_package_prefix("so101_demo_py")).resolve())

    assert text_pick_agent.main(
        [
            "--instruction", "帮我拿杯子", "--mode", "execute", "--execute",
            "--confirmation-digest", "sha256:v1:" + "0" * 64,
            "--session-id", " session-1 ", "--expected-reset-epoch", "0",
            "--evidence-root", str(tmp_path), "--source-commit", f" {head.upper()} ",
            "--installed-prefix", prefix, "--request-id", "req-fixed",
            "--cup-pose-timeout-s", "42.5",
        ]
    ) == 0

    context = calls["executor"]
    assert context.session_id == "session-1"
    assert context.expected_reset_epoch == 0
    assert context.evidence_root == tmp_path.resolve()
    assert context.source_commit == head
    assert context.installed_prefix == prefix
    assert context.execution_provenance.source_commit == head
    assert calls["cup_pose_timeout_s"] == 42.5
    assert output(capsys)["runtime_session_id"] == "session-1"


def test_cli_forwards_explicit_confirmation_bypass_without_a_digest(
    monkeypatch, capsys
) -> None:
    """Catches the public bypass flag being dropped before AgentRequest."""

    from types import SimpleNamespace

    from so101_demo.cli import text_pick_agent

    context = SimpleNamespace(
        execution_provenance=SimpleNamespace(to_dict=lambda: {})
    )
    monkeypatch.setattr(
        text_pick_agent,
        "_valid_execute_context",
        lambda _options: (context, None),
    )
    monkeypatch.setattr(
        text_pick_agent,
        "_persist_execution_provenance",
        lambda *_args, **_kwargs: None,
    )
    agent = StubAgent(result(AgentStatus.RUNTIME_COMPLETED, dispatch=True))

    exit_code = text_pick_agent.main(
        [
            "--instruction",
            "帮我拿杯子",
            "--mode",
            "execute",
            "--execute",
            "--skip-confirmation",
        ],
        _agent=agent,
    )

    assert exit_code == 0
    assert len(agent.requests) == 1
    assert agent.requests[0].skip_confirmation is True
    assert agent.requests[0].confirmation_digest is None
    assert output(capsys)["status"] == "RUNTIME_COMPLETED"


def test_execute_rejects_whitespace_wrapped_source_commit_sentinel(capsys) -> None:
    from so101_demo.cli import text_pick_agent

    agent = StubAgent(result())

    assert text_pick_agent.main(
        [
            "--instruction", "帮我拿杯子", "--mode", "execute", "--execute",
            "--session-id", "session-1", "--expected-reset-epoch", "0",
            "--evidence-root", "/tmp/evidence",
            "--source-commit", "  UNRECORDED_SOURCE  ",
            "--installed-prefix", "/tmp/install",
        ],
        _agent=agent,
    ) == 1

    assert agent.requests == []
    assert output(capsys)["reason_code"] == "EXECUTION_SOURCE_COMMIT_INVALID"


def test_cli_uses_requested_id_or_generates_one(monkeypatch, capsys) -> None:
    from so101_demo.cli import text_pick_agent

    ids = iter(("generated-id",))
    monkeypatch.setattr(text_pick_agent, "new_request_id", lambda: next(ids))
    agent = StubAgent(result(request_id="generated-id"))

    assert text_pick_agent.main(["--instruction", "帮我拿杯子"], _agent=agent) == 0
    assert agent.requests[0].request_id == "generated-id"
    assert output(capsys)["request_id"] == "generated-id"


def test_cli_profiling_defaults_are_disabled() -> None:
    from so101_demo.cli import text_pick_agent

    options = text_pick_agent.build_parser().parse_args(["--instruction", "pick"])

    assert options.profiling == "off"
    assert options.profiling_output_root is None
    assert options.profiling_session_id is None


def test_cli_enabled_profiling_writes_correlated_agent_stream(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    from so101_demo.cli import text_pick_agent

    monkeypatch.setattr(
        text_pick_agent,
        "DeepSeekPlanner",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        text_pick_agent,
        "OllamaPlanner",
        lambda **_kwargs: object(),
    )
    candidate = PlannerCandidate(
        {
            "outcome": "supported",
            "command": {
                "target_object": "plastic_cup",
                "action": "pick",
                "constraints": {},
            },
        },
        PlannerMetadata("deepseek", "model", 1, None, None, None, False),
    )

    class Planner:
        def plan(self, instruction: str) -> PlannerCandidate:
            return candidate

    monkeypatch.setattr(text_pick_agent, "PlannerChain", lambda *_args: Planner())
    profiling_root = tmp_path / "profiling"

    assert text_pick_agent.main(
        [
            "--instruction",
            "pick the cup",
            "--request-id",
            "request-1",
            "--profiling",
            "trace",
            "--profiling-output-root",
            str(profiling_root),
            "--profiling-session-id",
            "session-1",
        ]
    ) == 0

    assert output(capsys)["status"] == "DISPATCH_PREVIEW"
    events = [
        json.loads(line)
        for line in (
            profiling_root / "processes/text-agent.events.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["session_id"] == "session-1"
    assert events[0]["request_id"] == "request-1"
    assert events[-1]["event_type"] == "process_close"
    assert {event.get("name") for event in events} >= {
        "agent.total",
        "agent.validate_input",
        "agent.plan",
        "agent.validate_command",
        "agent.dispatch",
    }


def test_cli_can_build_a_separate_dynamic_runtime_stream(tmp_path: Path) -> None:
    from so101_demo.cli import text_pick_agent

    options = text_pick_agent.build_parser().parse_args(
        [
            "--instruction",
            "pick",
            "--profiling",
            "summary",
            "--profiling-output-root",
            str(tmp_path / "profiling"),
            "--profiling-session-id",
            "session-1",
        ]
    )

    profiler = text_pick_agent._build_semantic_profiler(
        options,
        request_id="request-1",
        process_role="dynamic-runtime",
    )
    assert profiler is not None
    profiler.close()

    stream = tmp_path / "profiling/processes/dynamic-runtime.events.jsonl"
    assert stream.is_file()
    anchor = json.loads(stream.read_text().splitlines()[0])
    assert anchor["process_role"] == "dynamic-runtime"
