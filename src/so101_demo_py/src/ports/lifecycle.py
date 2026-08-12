"""Readiness, pause, and shutdown boundary."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    accepted: bool
    session_id: str = ""
    reset_epoch: int = 0
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class PauseReceipt:
    accepted: bool
    paused: bool
    session_id: str = ""
    reset_epoch: int = 0
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ShutdownResult:
    accepted: bool
    error_code: str | None = None


@runtime_checkable
class LifecyclePort(Protocol):
    def readiness(self, timeout_s: float) -> ReadinessResult: ...

    def pause(self, paused: bool) -> PauseReceipt: ...

    def shutdown(self, timeout_s: float) -> ShutdownResult: ...
