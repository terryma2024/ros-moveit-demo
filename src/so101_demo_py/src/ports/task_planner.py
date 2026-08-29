from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PlannerMetadata:
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    cache_hit_tokens: int | None
    fallback_used: bool


@dataclass(frozen=True, slots=True)
class PlannerCandidate:
    value: object
    metadata: PlannerMetadata


class PlannerProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PlannerPort(Protocol):
    def plan(self, instruction: str) -> PlannerCandidate: ...
