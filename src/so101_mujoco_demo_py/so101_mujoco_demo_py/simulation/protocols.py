"""Backend-neutral observation and reset structural protocols."""

from typing import Protocol, runtime_checkable

from .types import ResetReceipt, SimulationEvidence


@runtime_checkable
class WorldObserver(Protocol):
    def snapshot(self) -> SimulationEvidence:
        """Return fresh evidence for the observer's configured session and timeout."""
        raise NotImplementedError


@runtime_checkable
class WorldReset(Protocol):
    def reset(self, keyframe: str) -> ResetReceipt:
        """Reset to a named keyframe and return epoch-correlated proof."""
        raise NotImplementedError
