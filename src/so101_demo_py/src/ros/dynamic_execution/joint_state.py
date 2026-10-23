"""Joint state intake, snapshots and progress waiting of the dynamic execution."""

from __future__ import annotations

import time
from typing import Any

from so101_demo.ros.dynamic_execution.common import (
    _DEFAULT_STATE_MAX_AGE_S,
    _evidence_is_finite,
    _JointStateStale,
)


class JointStateIntake:
    def _check_stop(self) -> None:
        flags = getattr(self, "_stop_flags", None)
        if flags is not None and not getattr(self, "_stop_suspended", False):
            flags.raise_if_stopped()

    def _wait_progress(self) -> None:
        """`_progress` plus the stop check, for waits that have no active goal."""
        self._progress()
        self._check_stop()

    def _on_joint_state(self, message: Any) -> None:
        if len(message.name) == len(message.position):
            positions = dict(
                (name, float(position))
                for name, position in zip(message.name, message.position, strict=True)
            )
            self._positions.update(positions)
            velocity = getattr(message, "velocity", None)
            if velocity is not None and len(velocity) == len(message.name):
                if not hasattr(self, "_joint_velocities"):
                    self._joint_velocities = {}
                self._joint_velocities.update(
                    (name, float(item)) for name, item in zip(message.name, velocity, strict=True))
            if all(name in positions for name in self._ARM_JOINTS):
                stamp = getattr(getattr(message, "header", None), "stamp", None)
                self._joint_state_source_stamp_ns = (
                    None if stamp is None else int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
                )
                self._joint_state_received_monotonic_s = time.monotonic()
                self._joint_state_generation += 1

    def _joint_state(
        self,
        timeout_s: float = 5.0,
        *,
        after_generation: int | None = None,
    ) -> tuple[float, ...]:
        if self._teacher_run():   # Teacher run: joint states unavailable for more than state_unavailable_stop_s end the attempt (design 2)
            timeout_s = min(timeout_s, float(self._execution_policy["state_unavailable_stop_s"]))
        deadline = time.monotonic() + timeout_s
        while any(name not in self._positions for name in self._ARM_JOINTS) or (
            after_generation is not None and self._joint_state_generation <= after_generation
        ):
            if time.monotonic() >= deadline:
                raise RuntimeError("JOINT_STATE_TIMEOUT")
            self._wait_progress()
        return tuple(self._positions[name] for name in self._ARM_JOINTS)

    def _snapshot(self):
        from so101_demo.backends.mujoco.observer import EvidenceStale

        teacher_run = self._teacher_run()
        deadline = time.monotonic() + (float(self._execution_policy["state_unavailable_stop_s"]) if teacher_run else 2.0)
        held = None
        while time.monotonic() < deadline:
            self._wait_progress()
            try:
                value = self.observer.snapshot()
            except EvidenceStale:
                continue
            if value.simulation_session_id != self._session_id:
                raise RuntimeError("DYNAMIC_SESSION_MISMATCH")
            if value.reset_epoch != self._expected_reset_epoch:
                raise RuntimeError("DYNAMIC_RESET_EPOCH_MISMATCH: " + self._identity_detail(value))
            if value.paused:
                held = value                   # the parent's inference hold: wait, bounded by this deadline, for a running frame
                continue
            if teacher_run and not _evidence_is_finite(value):
                raise RuntimeError("SIM_INTEGRITY_NON_FINITE_STATE")
            return value
        if held is not None:
            raise RuntimeError("DYNAMIC_RESET_EPOCH_MISMATCH: " + self._identity_detail(held))
        raise RuntimeError("DYNAMIC_EVIDENCE_TIMEOUT")

    def _require_fresh_joint_state(self) -> None:
        """k is computed from the joint state: it must be younger than the execution policy's ``state_max_age_s``."""

        from so101_demo.core.place_height import MEASUREMENT_FAILED

        policy = getattr(self, "_execution_policy", None) or {}
        max_age = policy.get("state_max_age_s", _DEFAULT_STATE_MAX_AGE_S)
        received = getattr(self, "_joint_state_received_monotonic_s", None)
        age = None if received is None else self._monotonic() - received
        if age is None or not 0.0 <= age <= max_age:
            raise _JointStateStale(MEASUREMENT_FAILED, f"the joint state is not fresh (age {age}, limit {max_age} s)")
