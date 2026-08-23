"""Observation-only adapter for qualified lossless MuJoCo physics-step traces."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from ...ports.phase_evidence import BoundaryReceipt, PhaseTrace, TraceReceipt


class MujocoPhaseEvidenceAdapter:
    def __init__(
        self,
        observer_factory: Callable[[str], Any],
        *,
        simulation_session_id: str,
        reset_epoch: int,
        physics_timestep_s: float,
    ) -> None:
        if not simulation_session_id or reset_epoch < 0 or physics_timestep_s <= 0.0:
            raise ValueError("MuJoCo phase-evidence identity is invalid")
        self._observer_factory = observer_factory
        self._session_id = simulation_session_id
        self._reset_epoch = reset_epoch
        self._physics_timestep_s = physics_timestep_s
        self._active: dict[str, tuple[str, Any]] = {}

    def begin_trace(self, phase: str) -> TraceReceipt:
        if not phase:
            raise ValueError("phase must be non-empty")
        trace_id = uuid.uuid4().hex
        self._active[trace_id] = (phase, self._observer_factory(phase))
        return TraceReceipt(trace_id, phase, self._session_id, self._reset_epoch)

    def mark_boundary(self, trace_id: str, boundary: str) -> BoundaryReceipt:
        try:
            _, observer = self._active[trace_id]
        except KeyError as error:
            raise ValueError("unknown or completed trace") from error
        kind, separator, waypoint_text = boundary.partition(":")
        if not separator or not waypoint_text.isdigit():
            raise ValueError("boundary must be '<kind>:<waypoint>'")
        waypoint = int(waypoint_text)
        methods = {
            "phase_start": observer.mark_goal_dispatched,
            "waypoint_start": observer.mark_goal_dispatched,
            "waypoint_end": observer.mark_waypoint_complete,
            "phase_end": observer.mark_phase_complete,
        }
        if kind not in methods:
            raise ValueError("unsupported phase boundary")
        raw = methods[kind](waypoint=waypoint)
        return BoundaryReceipt(trace_id, boundary, int(raw.physics_step))

    def finish_trace(self, trace_id: str) -> PhaseTrace:
        try:
            phase, observer = self._active.pop(trace_id)
        except KeyError as error:
            raise ValueError("unknown or completed trace") from error
        run = observer.build_run(
            physics_timestep_s=self._physics_timestep_s,
            physical_transport_outcome="SUCCEEDED",
        )
        chunks = tuple(getattr(run, "chunks", ()))
        lossless = not bool(getattr(run, "evidence_loss", False)) and all(
            not chunk.evidence_loss for chunk in chunks
        )
        run_id = str(getattr(run, "run_id", trace_id))
        return PhaseTrace(
            trace_id,
            phase,
            self._session_id,
            self._reset_epoch,
            lossless,
            (run_id,),
            {"physics_timestep_s": self._physics_timestep_s},
        )
