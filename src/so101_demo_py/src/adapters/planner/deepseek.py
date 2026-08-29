import math
import time
from collections.abc import Mapping

from ...ports.task_planner import PlannerCandidate, PlannerMetadata, PlannerProviderError
from .http_json import post_json
from .prompt import PLANNER_SYSTEM_PROMPT, decode_candidate

DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"


def is_production_deepseek_configuration(
    model: object,
    endpoint: object,
    timeout_s: object,
) -> bool:
    return (
        model == DEEPSEEK_MODEL
        and endpoint == DEEPSEEK_ENDPOINT
        and type(timeout_s) is float
        and math.isfinite(timeout_s)
        and timeout_s > 0
    )


class DeepSeekPlanner:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEEPSEEK_MODEL,
        endpoint: str = DEEPSEEK_ENDPOINT,
        timeout_s: float = 8.0,
        _transport=post_json,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._endpoint = endpoint
        self._timeout_s = timeout_s
        self._transport = _transport

    def plan(self, instruction: str) -> PlannerCandidate:
        if not is_production_deepseek_configuration(
            self._model, self._endpoint, self._timeout_s
        ):
            raise PlannerProviderError("DEEPSEEK_CONFIGURATION_INVALID")
        if not self._api_key:
            raise PlannerProviderError("DEEPSEEK_CREDENTIAL_MISSING")
        started = time.perf_counter_ns()
        payload = self._transport(
            self._endpoint,
            {"Authorization": f"Bearer {self._api_key}"},
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": instruction},
                ],
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
                "temperature": 0,
                "max_tokens": 128,
            },
            self._timeout_s,
        )
        if not isinstance(payload, Mapping):
            raise PlannerProviderError("DEEPSEEK_RESPONSE_INVALID")
        try:
            content = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage", {})
            if not isinstance(usage, Mapping):
                raise TypeError
            for counter in ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens"):
                if counter in usage and usage[counter] is not None and type(usage[counter]) is not int:
                    raise TypeError
            metadata = PlannerMetadata(
                "deepseek",
                self._model,
                (time.perf_counter_ns() - started) // 1_000_000,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                usage.get("prompt_cache_hit_tokens"),
                False,
            )
        except (KeyError, IndexError, TypeError):
            raise PlannerProviderError("DEEPSEEK_RESPONSE_INVALID") from None
        return PlannerCandidate(decode_candidate(content), metadata)
