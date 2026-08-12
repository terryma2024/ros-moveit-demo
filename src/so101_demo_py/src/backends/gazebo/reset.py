"""Gazebo reset request with an observed epoch/step postcondition."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

from ...ports.world import ResetReceipt


class GazeboResetAdapter:
    def __init__(
        self,
        observer: Any,
        request_reset: Callable[[str], bool],
        *,
        timeout_s: float,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")
        self._observer = observer
        self._request_reset = request_reset
        self._timeout_s = timeout_s
        self._clock = clock
        self._wait = wait

    def reset(self, keyframe: str) -> ResetReceipt:
        if not keyframe:
            raise ValueError("keyframe must be non-empty")
        before = self._observer.snapshot()
        old_epoch = int(before.reset_epoch)
        if not self._request_reset(keyframe):
            return ResetReceipt(
                old_epoch,
                old_epoch,
                keyframe,
                int(before.simulation_step),
                str(before.simulation_session_id),
                False,
            )
        deadline = self._clock() + self._timeout_s
        latest = before
        while self._clock() < deadline:
            latest = self._observer.snapshot()
            if (
                str(latest.simulation_session_id) == str(before.simulation_session_id)
                and int(latest.reset_epoch) == old_epoch + 1
                and int(latest.simulation_step) == 0
            ):
                return ResetReceipt(
                    old_epoch,
                    int(latest.reset_epoch),
                    keyframe,
                    0,
                    str(latest.simulation_session_id),
                    True,
                )
            self._wait(min(0.01, self._timeout_s))
        return ResetReceipt(
            old_epoch,
            int(latest.reset_epoch),
            keyframe,
            int(latest.simulation_step),
            str(latest.simulation_session_id),
            False,
        )
