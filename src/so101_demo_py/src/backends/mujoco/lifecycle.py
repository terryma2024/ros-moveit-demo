"""MuJoCo readiness, pause, and shutdown adapter."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from ...ports.lifecycle import PauseReceipt, ReadinessResult, ShutdownResult


def _identity(evidence: Any) -> tuple[str, int]:
    session_id = getattr(evidence, "session_id", None) or getattr(
        evidence, "simulation_session_id", ""
    )
    return str(session_id), int(evidence.reset_epoch)


def _paused(evidence: Any) -> bool | None:
    value = getattr(evidence, "paused", None)
    if value is None:
        value = getattr(evidence, "backend_metadata", {}).get("paused")
    return value if isinstance(value, bool) else None


class MujocoLifecycleAdapter:
    def __init__(
        self,
        services: Any,
        observer: Any,
        *,
        controller_names: Sequence[str] = ("arm_controller", "gripper_controller"),
        shutdown_callback: Callable[[float], bool] | None = None,
    ) -> None:
        self._services = services
        self._observer = observer
        self._controller_names = tuple(controller_names)
        self._shutdown_callback = shutdown_callback

    def readiness(self, timeout_s: float) -> ReadinessResult:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            return ReadinessResult(False, error_code="READINESS_TIMEOUT_INVALID")
        try:
            evidence = self._observer.snapshot()
            session_id, reset_epoch = _identity(evidence)
            if not session_id or not self._services.controllers_active(self._controller_names):
                raise RuntimeError("world or controller state is not confirmed")
        except Exception:
            return ReadinessResult(False, error_code="WORLD_STATE_NOT_CONFIRMED")
        return ReadinessResult(True, session_id, reset_epoch)

    def pause(self, paused: bool) -> PauseReceipt:
        try:
            if not self._services.pause(paused):
                return PauseReceipt(False, paused, error_code="PAUSE_SERVICE_FAILED")
            evidence = self._observer.snapshot()
            session_id, reset_epoch = _identity(evidence)
            if not session_id or _paused(evidence) is not paused:
                raise RuntimeError("post-request world state is not confirmed")
        except Exception:
            return PauseReceipt(False, paused, error_code="WORLD_STATE_NOT_CONFIRMED")
        return PauseReceipt(True, paused, session_id, reset_epoch)

    def shutdown(self, timeout_s: float) -> ShutdownResult:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            return ShutdownResult(False, "SHUTDOWN_TIMEOUT_INVALID")
        if self._shutdown_callback is None:
            return ShutdownResult(False, "SHUTDOWN_NOT_CONFIGURED")
        try:
            accepted = self._shutdown_callback(timeout_s)
        except Exception:
            return ShutdownResult(False, "SHUTDOWN_FAILED")
        return ShutdownResult(bool(accepted), None if accepted else "SHUTDOWN_FAILED")
