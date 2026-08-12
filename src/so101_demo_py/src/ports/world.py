"""Physical-world observation and reset boundary."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .evidence import ReceivedWorldEvidence, WorldEvidence


@dataclass(frozen=True, slots=True)
class ResetReceipt:
    old_epoch: int
    new_epoch: int
    keyframe: str
    simulation_step: int
    session_id: str
    observed_after_request: bool


@runtime_checkable
class WorldPort(Protocol):
    def snapshot(self) -> WorldEvidence: ...

    def snapshot_with_receipt(self) -> ReceivedWorldEvidence: ...

    def reset(self, keyframe: str) -> ResetReceipt: ...
