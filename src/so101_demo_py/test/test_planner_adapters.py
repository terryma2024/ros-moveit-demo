import json
import traceback
from urllib.error import URLError

import pytest

from so101_demo.adapters.planner.deepseek import DeepSeekPlanner
from so101_demo.adapters.planner.ollama import OllamaPlanner
from so101_demo.adapters.planner.http_json import post_json
from so101_demo.ports.task_planner import PlannerProviderError


VALID = (
    '{"outcome":"supported","command":'
    '{"target_object":"plastic_cup","action":"pick","constraints":{}}}'
)


def test_deepseek_request_contract_and_tokens():
    captured = {}
    def transport(url, headers, body, timeout_s):
        captured.update(url=url, headers=headers, body=body, timeout_s=timeout_s)
        return {"choices":[{"message":{"content":VALID}}], "usage":{"prompt_tokens":10,"completion_tokens":8,"prompt_cache_hit_tokens":2}}
    result = DeepSeekPlanner("secret", _transport=transport).plan("帮我拿杯子")
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["body"]["model"] == "deepseek-v4-flash"
    assert captured["body"]["response_format"] == {"type":"json_object"}
    assert captured["body"]["thinking"] == {"type":"disabled"}
    assert captured["body"]["temperature"] == 0 and captured["body"]["max_tokens"] == 128
    assert [m["role"] for m in captured["body"]["messages"]] == ["system", "user"]
    assert result.metadata.input_tokens == 10 and result.metadata.cache_hit_tokens == 2


def test_ollama_request_contract_and_tokens():
    captured = {}
    def transport(url, headers, body, timeout_s):
        captured.update(url=url, headers=headers, body=body)
        return {"message":{"content":VALID}, "prompt_eval_count":12, "eval_count":7}
    result = OllamaPlanner(_transport=transport).plan("帮我拿杯子")
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["body"]["model"] == "qwen3.5:4b"
    assert captured["body"]["stream"] is False
    from so101_demo.core.planner_outcome import PLANNER_OUTCOME_JSON_SCHEMA
    assert captured["body"]["format"] == PLANNER_OUTCOME_JSON_SCHEMA
    assert captured["body"]["options"] == {"temperature": 0}
    assert result.metadata.input_tokens == 12 and result.metadata.output_tokens == 7


def test_deepseek_missing_credential():
    with pytest.raises(PlannerProviderError, match="DEEPSEEK_CREDENTIAL_MISSING"):
        DeepSeekPlanner("").plan("x")


@pytest.mark.parametrize("payload", [None, {}, {"choices": []}, {"choices":[{"message":{}}]}, {"choices":[{"message":{"content":VALID}}],"usage":[]}, {"choices":[{"message":{"content":VALID}}],"usage":"bad"}])
def test_deepseek_invalid_envelope_or_usage(payload):
    with pytest.raises(PlannerProviderError) as exc:
        DeepSeekPlanner("k", _transport=lambda *_: payload).plan("x")
    assert exc.value.code in {"DEEPSEEK_RESPONSE_INVALID", "PROVIDER_RESPONSE_INVALID"}


@pytest.mark.parametrize("payload", [None, {}, {"message": {}}, {"message":{"content":VALID},"prompt_eval_count":[]}])
def test_ollama_invalid_envelope_or_usage(payload):
    with pytest.raises(PlannerProviderError) as exc:
        OllamaPlanner(_transport=lambda *_: payload).plan("x")
    assert exc.value.code == "OLLAMA_RESPONSE_INVALID"


@pytest.mark.parametrize("content", ["", "  ", "not-json"])
def test_content_failures_are_stable(content):
    with pytest.raises(PlannerProviderError) as exc:
        DeepSeekPlanner("k", _transport=lambda *_: {"choices":[{"message":{"content":content}}]}).plan("x")
    assert exc.value.code in {"PROVIDER_CONTENT_EMPTY", "PROVIDER_JSON_INVALID"}


def test_valid_json_shape_is_not_semantically_validated():
    result = OllamaPlanner(_transport=lambda *_: {"message":{"content":"[]"}}).plan("x")
    assert result.value == []


class _Response:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.data


@pytest.mark.parametrize("exc", [TimeoutError("x"), ValueError("x")])
def test_post_json_transport_failures_are_redacted(monkeypatch, exc):
    def fail(*args, **kwargs): raise exc
    import so101_demo.adapters.planner.http_json as module
    monkeypatch.setattr(module, "urlopen", fail)
    with pytest.raises(PlannerProviderError) as error:
        post_json("https://x.test/key", {"Authorization":"Bearer secret"}, {}, 1)
    assert error.value.code == "PROVIDER_TRANSPORT_FAILED"
    assert "secret" not in str(error.value)


def test_post_json_malformed_http_json(monkeypatch):
    import so101_demo.adapters.planner.http_json as module
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: _Response(b"{"))
    with pytest.raises(PlannerProviderError) as error:
        post_json("https://x.test", {}, {}, 1)
    assert error.value.code == "PROVIDER_TRANSPORT_FAILED"


def test_post_json_rejects_non_mapping(monkeypatch):
    import so101_demo.adapters.planner.http_json as module
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: _Response(b"[]"))
    with pytest.raises(PlannerProviderError) as error:
        post_json("https://x.test", {}, {}, 1)
    assert error.value.code == "PROVIDER_RESPONSE_INVALID"


@pytest.mark.parametrize("counter_value", ["10", 1.5, True])
def test_deepseek_rejects_wrong_typed_usage_counters(counter_value):
    payload = {"choices": [{"message": {"content": VALID}}], "usage": {"prompt_tokens": counter_value}}
    with pytest.raises(PlannerProviderError) as error:
        DeepSeekPlanner("k", _transport=lambda *_: payload).plan("x")
    assert error.value.code == "DEEPSEEK_RESPONSE_INVALID"


@pytest.mark.parametrize("counter_value", ["10", 1.5, True])
def test_ollama_rejects_wrong_typed_usage_counters(counter_value):
    payload = {"message": {"content": VALID}, "prompt_eval_count": counter_value}
    with pytest.raises(PlannerProviderError) as error:
        OllamaPlanner(_transport=lambda *_: payload).plan("x")
    assert error.value.code == "OLLAMA_RESPONSE_INVALID"


def test_post_json_wraps_request_construction_failure():
    with pytest.raises(PlannerProviderError) as error:
        post_json("not a valid url with [", {}, {}, 1)
    assert error.value.code == "PROVIDER_TRANSPORT_FAILED"


def test_post_json_traceback_redacts_transport_details(monkeypatch):
    import so101_demo.adapters.planner.http_json as module
    secret_url = "https://api.example.test/token-secret"
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: (_ for _ in ()).throw(URLError(secret_url)))
    with pytest.raises(PlannerProviderError) as error:
        post_json(secret_url, {}, {}, 1)
    rendered = "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert secret_url not in rendered and "token-secret" not in rendered
