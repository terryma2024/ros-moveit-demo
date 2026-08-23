"""Gazebo readiness and process lifecycle adapter."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from ...ports.lifecycle import PauseReceipt, ReadinessResult, ShutdownResult


class GazeboLifecycleAdapter:
    def __init__(
        self,
        observer: Any,
        *,
        controllers_active: Callable[[], bool],
        bridge_ready: Callable[[], bool],
        shutdown_callback: Callable[[float], bool] | None = None,
    ) -> None:
        self._observer = observer
        self._controllers_active = controllers_active
        self._bridge_ready = bridge_ready
        self._shutdown_callback = shutdown_callback

    def readiness(self, timeout_s: float) -> ReadinessResult:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            return ReadinessResult(False, error_code="READINESS_TIMEOUT_INVALID")
        try:
            evidence = self._observer.snapshot()
            session_id = str(evidence.simulation_session_id)
            if not session_id or not self._controllers_active() or not self._bridge_ready():
                raise RuntimeError("Gazebo runtime is not converged")
        except Exception:
            return ReadinessResult(False, error_code="WORLD_STATE_NOT_CONFIRMED")
        return ReadinessResult(True, session_id, int(evidence.reset_epoch))

    def pause(self, paused: bool) -> PauseReceipt:
        return PauseReceipt(False, paused, error_code="PAUSE_NOT_SUPPORTED")

    def shutdown(self, timeout_s: float) -> ShutdownResult:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            return ShutdownResult(False, "SHUTDOWN_TIMEOUT_INVALID")
        if self._shutdown_callback is None:
            return ShutdownResult(False, "SHUTDOWN_NOT_CONFIGURED")
        try:
            accepted = bool(self._shutdown_callback(timeout_s))
        except Exception:
            return ShutdownResult(False, "SHUTDOWN_FAILED")
        return ShutdownResult(accepted, None if accepted else "SHUTDOWN_FAILED")
