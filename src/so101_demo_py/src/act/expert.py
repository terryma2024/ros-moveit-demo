"""Causal expert labels from the controller's accepted desired/reference interval."""

from __future__ import annotations

import math

from .contracts import finite, validate_action


class MoveItExpertActionTap:
    def __init__(self, reference_port, *, dt_s: float = 0.1) -> None:
        self.reference_port = reference_port
        self.dt_s = finite(dt_s)
        if self.dt_s <= 0:
            raise ValueError("EXPERT_GRID_INVALID")

    def reference(self, at_s: float) -> dict:
        target = finite(at_s, nonnegative=True) + self.dt_s
        try:
            reference = self.reference_port.reference_state(target)
        except Exception as error:
            raise ValueError("EXPERT_REFERENCE_UNAVAILABLE") from error
        if (not isinstance(reference, dict)
                or reference.get("source") != "CONTROLLER_REFERENCE"
                or not isinstance(reference.get("requested_sim_time_s"), (int, float))
                or not math.isclose(reference["requested_sim_time_s"], target,
                                    rel_tol=0, abs_tol=1e-6)):
            raise ValueError("EXPERT_REFERENCE_SOURCE_INVALID")
        return {"requested_sim_time_s": target, "source": "CONTROLLER_REFERENCE",
                "positions": validate_action(reference.get("positions"))}

    def label(self, at_s: float) -> tuple[float, ...]:
        return self.reference(at_s)["positions"]


class CausalEpisodeCapture:
    """Build a training label and its audit claim from the same reference read."""

    _REFERENCE_KEYS = frozenset({"reference_time_s", "reference_source", "reference_positions"})

    def __init__(self, recorder, tap: MoveItExpertActionTap) -> None:
        self.recorder = recorder
        self.tap = tap

    def append(self, observation: dict, physical_audit: dict) -> tuple[float, ...]:
        if not isinstance(physical_audit, dict) or self._REFERENCE_KEYS.intersection(physical_audit):
            raise ValueError("EXPERT_AUDIT_REFERENCE_FORBIDDEN")
        reference = self.tap.reference(observation["sim_time_s"])
        positions = reference["positions"]
        audit = {**physical_audit,
                 "reference_time_s": reference["requested_sim_time_s"],
                 "reference_source": reference["source"],
                 "reference_positions": positions}
        self.recorder.append(observation, positions, audit)
        return positions
