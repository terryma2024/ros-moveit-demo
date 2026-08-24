"""ROS-free absolute-deadline acquisition boundary for one cup pose."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Protocol, TypeVar


class CupPoseSourceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CupPoseSource(Protocol):
    def get_one(self, timeout_s: float): ...


TMessage = TypeVar("TMessage")
TValue = TypeVar("TValue")


def acquire_one(
    *,
    receive: Callable[[], TMessage | None],
    spin_once: Callable[[float], None],
    convert: Callable[[TMessage], TValue],
    on_invalid: Callable[[Exception], None],
    timeout_s: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> TValue:
    """Return the first valid value without extending the absolute deadline."""

    if not math.isfinite(timeout_s) or timeout_s <= 0.0:
        raise ValueError("timeout_s must be finite and positive")
    deadline = monotonic() + timeout_s
    received_any = False
    last_error: Exception | None = None
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0.0:
            if received_any:
                raise CupPoseSourceError(
                    "CUP_POSE_INVALID",
                    "messages arrived but none satisfied the cup pose contract",
                ) from last_error
            raise CupPoseSourceError(
                "CUP_POSE_TIMEOUT", f"no /cup_pose message received within {timeout_s} seconds"
            )
        message = receive()
        if message is None:
            spin_once(min(0.05, remaining))
            continue
        received_any = True
        try:
            return convert(message)
        except Exception as error:
            last_error = error
            on_invalid(error)
            spin_once(min(0.01, remaining))
