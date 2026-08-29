import math
import time
from collections.abc import Mapping
from urllib.parse import urlsplit

from ...core.planner_outcome import PLANNER_OUTCOME_JSON_SCHEMA
from ...ports.task_planner import PlannerCandidate, PlannerMetadata, PlannerProviderError
from .http_json import post_json
from .prompt import PLANNER_SYSTEM_PROMPT, decode_candidate

OLLAMA_MODEL = "qwen3.5:4b"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def is_production_ollama_configuration(
    model: object,
    endpoint: object,
    timeout_s: object,
) -> bool:
    if (
        model != OLLAMA_MODEL
        or not isinstance(endpoint, str)
        or type(timeout_s) is not float
        or not math.isfinite(timeout_s)
        or timeout_s <= 0
    ):
        return False
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname in _LOOPBACK_HOSTS
        and parsed.username is None
        and parsed.password is None
        and parsed.path == "/api/chat"
        and parsed.query == ""
        and parsed.fragment == ""
        and (port is None or 1 <= port <= 65535)
    )


class OllamaPlanner:
    def __init__(
        self,
        *,
        model: str = OLLAMA_MODEL,
        endpoint: str = "http://127.0.0.1:11434/api/chat",
        timeout_s: float = 12.0,
        _transport=post_json,
    ) -> None:
        self._model = model
        self._endpoint = endpoint
        self._timeout_s = timeout_s
        self._transport = _transport

    def plan(self, instruction: str) -> PlannerCandidate:
        if not is_production_ollama_configuration(
            self._model, self._endpoint, self._timeout_s
        ):
            raise PlannerProviderError("OLLAMA_CONFIGURATION_INVALID")
        started = time.perf_counter_ns()
        payload = self._transport(
            self._endpoint,
            {},
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": instruction},
                ],
                "stream": False,
                "format": PLANNER_OUTCOME_JSON_SCHEMA,
                "options": {"temperature": 0},
            },
            self._timeout_s,
        )
        if not isinstance(payload, Mapping):
            raise PlannerProviderError("OLLAMA_RESPONSE_INVALID")
        try:
            content = payload["message"]["content"]
            for counter in ("prompt_eval_count", "eval_count"):
                if counter in payload and payload[counter] is not None and type(payload[counter]) is not int:
                    raise TypeError
            metadata = PlannerMetadata(
                "ollama",
                self._model,
                (time.perf_counter_ns() - started) // 1_000_000,
                payload.get("prompt_eval_count"),
                payload.get("eval_count"),
                None,
                False,
            )
        except (KeyError, TypeError):
            raise PlannerProviderError("OLLAMA_RESPONSE_INVALID") from None
        return PlannerCandidate(decode_candidate(content), metadata)
