from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ExecutorDispatchError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DynamicCupPickPlaceRequest:
    request_id: str
    capability: str
    backend: str
    scene_source: str
    target_object: str
    action: str


@dataclass(frozen=True, slots=True)
class RuntimeDispatchResult:
    exit_code: int
    runtime_session_id: str


class PickPlaceExecutorPort(Protocol):
    def dispatch(
        self,
        request: DynamicCupPickPlaceRequest,
    ) -> RuntimeDispatchResult:
        ...
