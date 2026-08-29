from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from so101_demo.adapters.planner.deepseek import DeepSeekPlanner
from so101_demo.adapters.planner.http_json import post_json
from so101_demo.adapters.planner.ollama import OllamaPlanner
from so101_demo.ports.task_planner import PlannerProviderError


SUPPORTED_JSON = json.dumps(
    {
        "outcome": "supported",
        "command": {
            "target_object": "plastic_cup",
            "action": "pick",
            "constraints": {},
        },
    }
)


def _deepseek_payload() -> dict[str, object]:
    return {"choices": [{"message": {"content": SUPPORTED_JSON}}], "usage": {}}


def _ollama_payload() -> dict[str, object]:
    return {"message": {"content": SUPPORTED_JSON}}


@pytest.mark.parametrize(
    ("model", "endpoint"),
    [
        ("deepseek-v3", "https://api.deepseek.com/chat/completions"),
        ("deepseek-v4-flash", "http://api.deepseek.com/chat/completions"),
        ("deepseek-v4-flash", "https://user@api.deepseek.com/chat/completions"),
        ("deepseek-v4-flash", "https://api.deepseek.com:444/chat/completions"),
        ("deepseek-v4-flash", "https://api.deepseek.com/v1/chat/completions"),
        ("deepseek-v4-flash", "https://api.deepseek.com/chat/completions?x=1"),
        ("deepseek-v4-flash", "https://api.deepseek.com/chat/completions#x"),
    ],
)
def test_deepseek_rejects_nonproduction_configuration_before_transport(
    model: str, endpoint: str
) -> None:
    """Catches a secret-bearing DeepSeek request reaching an unqualified origin/model."""

    calls: list[object] = []
    planner = DeepSeekPlanner("test-only-key", model=model, endpoint=endpoint)
    planner._transport = lambda *_args: calls.append(_args) or _deepseek_payload()

    with pytest.raises(PlannerProviderError) as captured:
        planner.plan("Pick the plastic cup.")

    assert captured.value.code == "DEEPSEEK_CONFIGURATION_INVALID"
    assert calls == []


@pytest.mark.parametrize(
    ("model", "endpoint"),
    [
        ("qwen2.5:4b", "http://127.0.0.1:11434/api/chat"),
        ("qwen3.5:4b", "https://127.0.0.1:11434/api/chat"),
        ("qwen3.5:4b", "http://10.0.0.4:11434/api/chat"),
        ("qwen3.5:4b", "http://user@localhost:11434/api/chat"),
        ("qwen3.5:4b", "http://localhost:11434/v1/chat"),
        ("qwen3.5:4b", "http://localhost:11434/api/chat?x=1"),
        ("qwen3.5:4b", "http://localhost:11434/api/chat#x"),
    ],
)
def test_ollama_rejects_nonloopback_or_nonproduction_configuration_before_transport(
    model: str, endpoint: str
) -> None:
    """Catches fallback traffic escaping loopback or selecting an unqualified model/path."""

    calls: list[object] = []
    planner = OllamaPlanner(model=model, endpoint=endpoint)
    planner._transport = lambda *_args: calls.append(_args) or _ollama_payload()

    with pytest.raises(PlannerProviderError) as captured:
        planner.plan("Pick the plastic cup.")

    assert captured.value.code == "OLLAMA_CONFIGURATION_INVALID"
    assert calls == []


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1/api/chat",
        "http://127.0.0.1:21434/api/chat",
        "http://localhost:11434/api/chat",
        "http://[::1]:11434/api/chat",
    ],
)
def test_ollama_keeps_loopback_port_override_for_reverse_tunnels(endpoint: str) -> None:
    """Catches an allowlist that accidentally blocks qualified localhost tunnels."""

    calls: list[object] = []
    planner = OllamaPlanner(endpoint=endpoint)
    planner._transport = lambda *_args: calls.append(_args) or _ollama_payload()

    result = planner.plan("Pick the plastic cup.")

    assert result.value["outcome"] == "supported"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "arguments",
    [
        ["--deepseek-model", "deepseek-v3"],
        ["--deepseek-endpoint", "https://example.test/chat/completions"],
        ["--ollama-model", "qwen2.5:4b"],
        ["--ollama-endpoint", "http://10.0.0.4:11434/api/chat"],
    ],
)
def test_cli_rejects_unqualified_provider_override_before_agent(
    arguments: list[str], capsys
) -> None:
    """Catches CLI flags bypassing the adapter production allowlists."""

    from so101_demo.cli import text_pick_agent

    class Agent:
        def __init__(self) -> None:
            self.calls = 0

        def handle(self, _request: object) -> object:
            self.calls += 1
            raise AssertionError("unqualified provider options must not reach agent")

    agent = Agent()
    exit_code = text_pick_agent.main(
        ["--instruction", "Pick the plastic cup.", *arguments],
        _agent=agent,  # type: ignore[arg-type]
    )

    assert exit_code == 1
    assert agent.calls == 0
    document = json.loads(capsys.readouterr().out)
    assert document["reason_code"] == "PROVIDER_OPTIONS_INVALID"


def test_cross_origin_redirect_never_receives_authorization_header() -> None:
    """Catches urllib forwarding a DeepSeek bearer credential to a redirect sink."""

    sink_requests: list[dict[str, str]] = []

    class SinkHandler(BaseHTTPRequestHandler):
        def _record(self) -> None:
            sink_requests.append({key: value for key, value in self.headers.items()})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        do_GET = _record
        do_POST = _record

        def log_message(self, *_args: object) -> None:
            return None

    sink = ThreadingHTTPServer(("127.0.0.1", 0), SinkHandler)
    sink_thread = Thread(target=sink.serve_forever, daemon=True)
    sink_thread.start()
    sink_url = f"http://127.0.0.1:{sink.server_port}/sink"

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(302)
            self.send_header("Location", sink_url)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return None

    source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    source_thread = Thread(target=source.serve_forever, daemon=True)
    source_thread.start()
    source_url = f"http://127.0.0.1:{source.server_port}/source"

    try:
        with pytest.raises(PlannerProviderError) as captured:
            post_json(
                source_url,
                {"Authorization": "Bearer test-only-redirect-key"},
                {},
                1.0,
            )
        assert captured.value.code == "PROVIDER_TRANSPORT_FAILED"
        assert sink_requests == []
    finally:
        source.shutdown()
        sink.shutdown()
        source.server_close()
        sink.server_close()
        source_thread.join(timeout=2)
        sink_thread.join(timeout=2)
