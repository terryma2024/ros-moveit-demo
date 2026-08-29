import time
from collections.abc import Mapping

from ...ports.task_planner import PlannerCandidate, PlannerMetadata, PlannerProviderError
from .http_json import post_json
from .prompt import PLANNER_SYSTEM_PROMPT, decode_candidate


class DeepSeekPlanner:
    def __init__(self, api_key: str, *, model: str = "deepseek-v4-flash", endpoint: str = "https://api.deepseek.com/chat/completions", timeout_s: float = 8.0, transport=post_json) -> None:
        self._api_key, self._model, self._endpoint, self._timeout_s, self._transport = api_key, model, endpoint, timeout_s, transport

    def plan(self, instruction: str) -> PlannerCandidate:
        if not self._api_key:
            raise PlannerProviderError("DEEPSEEK_CREDENTIAL_MISSING")
        started = time.perf_counter_ns()
        payload = self._transport(self._endpoint, {"Authorization": f"Bearer {self._api_key}"}, {
            "model": self._model, "messages": [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}, {"role": "user", "content": instruction}],
            "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}, "temperature": 0, "max_tokens": 128}, self._timeout_s)
        if not isinstance(payload, Mapping):
            raise PlannerProviderError("DEEPSEEK_RESPONSE_INVALID")
        try:
            content = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage", {})
            if not isinstance(usage, Mapping):
                raise TypeError
            metadata = PlannerMetadata("deepseek", self._model, (time.perf_counter_ns() - started) // 1_000_000,
                usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("prompt_cache_hit_tokens"), False)
        except (KeyError, IndexError, TypeError):
            raise PlannerProviderError("DEEPSEEK_RESPONSE_INVALID")
        return PlannerCandidate(decode_candidate(content), metadata)
