"""Typed boundaries between FastAPI and the single ROS worker thread."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, TypeVar

from .models import TelemetrySnapshot

ResultT = TypeVar("ResultT")


class RosRuntime(ABC):
    """The only interface API code may use to schedule ROS work."""

    @abstractmethod
    async def call(self, operation: Callable[[], ResultT]) -> ResultT:
        """Run one operation on the ROS owner and return its completed result."""

    @abstractmethod
    async def snapshot(self) -> TelemetrySnapshot:
        """Return the latest immutable telemetry snapshot."""
