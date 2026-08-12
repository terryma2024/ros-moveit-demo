"""Optional observation-only phase trace boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class TraceReceipt:
    trace_id: str
    phase: str
    session_id: str
    reset_epoch: int

    def __post_init__(self) -> None:
        if not self.trace_id or not self.phase or not self.session_id or self.reset_epoch < 0:
            raise ValueError("trace receipt identity is invalid")


@dataclass(frozen=True, slots=True)
class BoundaryReceipt:
    trace_id: str
    boundary: str
    physics_step: int

    def __post_init__(self) -> None:
        if not self.trace_id or not self.boundary or self.physics_step < 0:
            raise ValueError("boundary receipt is invalid")


@dataclass(frozen=True, slots=True)
class PhaseTrace:
    trace_id: str
    phase: str
    session_id: str
    reset_epoch: int
    lossless: bool
    evidence_refs: tuple[str, ...]
    backend_metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "backend_metadata", MappingProxyType(dict(self.backend_metadata)))


@runtime_checkable
class PhaseEvidencePort(Protocol):
    def begin_trace(self, phase: str) -> TraceReceipt: ...

    def mark_boundary(self, trace_id: str, boundary: str) -> BoundaryReceipt: ...

    def finish_trace(self, trace_id: str) -> PhaseTrace: ...
