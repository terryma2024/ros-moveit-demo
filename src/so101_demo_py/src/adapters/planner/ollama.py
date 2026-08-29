import time
from collections.abc import Mapping

from ...core.task_command import TASK_COMMAND_JSON_SCHEMA
from ...ports.task_planner import PlannerCandidate, PlannerMetadata, PlannerProviderError
from .http_json import post_json
from .prompt import PLANNER_SYSTEM_PROMPT, decode_candidate


class OllamaPlanner:
    def __init__(self, *, model: str = "qwen3.5:4b", endpoint: str = "http://127.0.0.1:11434/api/chat", timeout_s: float = 12.0, transport=post_json) -> None:
        self._model, self._endpoint, self._timeout_s, self._transport = model, endpoint, timeout_s, transport

    def plan(self, instruction: str) -> PlannerCandidate:
        started = time.perf_counter_ns()
        payload = self._transport(self._endpoint, {}, {
            "model": self._model, "messages": [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}, {"role": "user", "content": instruction}],
            "stream": False, "format": TASK_COMMAND_JSON_SCHEMA, "options": {"temperature": 0}}, self._timeout_s)
        if not isinstance(payload, Mapping):
            raise PlannerProviderError("OLLAMA_RESPONSE_INVALID")
        try:
            content = payload["message"]["content"]
            for counter in ("prompt_eval_count", "eval_count"):
                if counter in payload and payload[counter] is not None and type(payload[counter]) is not int:
                    raise TypeError
            metadata = PlannerMetadata("ollama", self._model, (time.perf_counter_ns() - started) // 1_000_000,
                payload.get("prompt_eval_count"), payload.get("eval_count"), None, False)
        except (KeyError, TypeError):
            raise PlannerProviderError("OLLAMA_RESPONSE_INVALID") from None
        return PlannerCandidate(decode_candidate(content), metadata)
