"""Transactional pause/reset/snapshot coordinator for pinned MuJoCo services."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from typing import Any

from so101_demo.backends.mujoco.observer import EvidenceStale
from so101_demo.core.simulation.types import ResetReceipt


class ResetFailed(RuntimeError):
    """Raised after a failed reset transaction has been forced back to paused."""


class MujocoResetClient:
    """Correlate service success with controller, joint, and atomic epoch evidence."""

    def __init__(
        self,
        services: Any,
        observer: Any,
        *,
        simulation_session_id: str,
        controller_names: Sequence[str],
        expected_joint_positions: Sequence[float],
        expected_object_position: Sequence[float],
        timeout_s: float = 5.0,
        joint_tolerance: float = 0.002,
        object_tolerance_m: float = 0.003,
        monotonic: Callable[[], float] = time.monotonic,
        progress: Callable[[], None] = lambda: time.sleep(0.01),
    ) -> None:
        if not simulation_session_id or not controller_names:
            raise ValueError("session id and controller names must be non-empty")
        if len(expected_joint_positions) != 6 or len(expected_object_position) != 3:
            raise ValueError("expected reset state must contain six joints and one position")
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout must be positive")
        self._services = services
        self._observer = observer
        self._session_id = simulation_session_id
        self._controllers = tuple(controller_names)
        self._expected_joints = tuple(float(value) for value in expected_joint_positions)
        self._expected_object = tuple(float(value) for value in expected_object_position)
        self._timeout_s = timeout_s
        self._joint_tolerance = joint_tolerance
        self._object_tolerance_m = object_tolerance_m
        self._monotonic = monotonic
        self._progress = progress

    def _failure(self, reason: str) -> ResetFailed:
        try:
            self._services.pause(True)
        except Exception:
            pass
        return ResetFailed(reason)

    def _require(self, success: bool, operation: str) -> None:
        if not success:
            raise self._failure(f"{operation} failed")

    def _wait_for_reset_snapshot(
        self,
        *,
        old: Any,
        expected_epoch: int,
        deadline: float,
    ) -> Any:
        """Capture the authoritative paused step-zero frame before physics resumes."""
        retry_period_s = min(0.05, self._timeout_s / 2.0)
        next_snapshot_retry_s = self._monotonic() + retry_period_s

        def retry_snapshot_if_due() -> None:
            nonlocal next_snapshot_retry_s
            now = self._monotonic()
            if now < next_snapshot_retry_s:
                return
            self._require(self._services.pause(True), "reset snapshot retry")
            next_snapshot_retry_s = now + retry_period_s

        while self._monotonic() <= deadline:
            self._progress()
            try:
                current = self._observer.snapshot()
            except EvidenceStale:
                retry_snapshot_if_due()
                continue
            if current.simulation_session_id != self._session_id:
                raise self._failure("evidence session mismatch")
            if current.reset_epoch > expected_epoch:
                raise self._failure("reset epoch mismatch")
            if current.reset_epoch != expected_epoch:
                retry_snapshot_if_due()
                continue
            if current.publisher_sequence <= old.publisher_sequence:
                raise self._failure("publisher sequence did not advance")
            if current.simulation_step != 0:
                raise self._failure("reset evidence is not step zero")
            if not current.paused:
                raise self._failure("atomic reset evidence is not authoritatively paused")
            object_values = (
                *current.object_state.position_world,
                *current.object_state.orientation_xyzw,
                *current.object_state.linear_velocity_world,
                *current.object_state.angular_velocity_world,
                current.minimum_signed_distance_m,
                current.maximum_normal_force_n,
            )
            if not all(math.isfinite(value) for value in object_values):
                raise self._failure("atomic object evidence is not finite")
            if (
                math.dist(current.object_state.position_world, self._expected_object)
                > self._object_tolerance_m
            ):
                raise self._failure("object pose convergence failed")
            return current
        raise self._failure("reset timeout waiting for authoritative step-zero evidence")

    def _wait_for_initial_snapshot(self, *, deadline: float) -> Any:
        """Acquire current provenance even when a fresh client joins a paused world."""
        try:
            current = self._observer.snapshot()
        except EvidenceStale:
            pass
        else:
            if current.simulation_session_id != self._session_id:
                raise self._failure("initial evidence session mismatch")
            return current

        retry_period_s = min(0.05, self._timeout_s / 2.0)
        next_snapshot_request_s = self._monotonic()
        while self._monotonic() <= deadline:
            now = self._monotonic()
            if now >= next_snapshot_request_s:
                self._require(self._services.pause(True), "initial snapshot request")
                next_snapshot_request_s = now + retry_period_s
            self._progress()
            try:
                current = self._observer.snapshot()
            except EvidenceStale:
                continue
            if current.simulation_session_id != self._session_id:
                raise self._failure("initial evidence session mismatch")
            if not current.paused:
                continue
            return current
        raise self._failure("initial evidence unavailable")

    def reset(self, keyframe: str) -> ResetReceipt:
        if not keyframe:
            raise ValueError("keyframe must be non-empty")
        deadline = self._monotonic() + self._timeout_s
        try:
            old = self._wait_for_initial_snapshot(deadline=deadline)
            expected_epoch = old.reset_epoch + 1
            if old.paused:
                self._require(self._services.pause(False), "prepare running")
            self._require(
                self._services.switch_controllers(activate=(), deactivate=self._controllers),
                "deactivate",
            )
            self._require(self._services.pause(True), "pause")
            self._require(self._services.reset_world(keyframe), "reset")
            reset_snapshot = self._wait_for_reset_snapshot(
                old=old,
                expected_epoch=expected_epoch,
                deadline=deadline,
            )
            joint_callback_count_after_reset = self._services.joint_callback_count
            self._require(self._services.pause(False), "resume")
            self._require(
                self._services.switch_controllers(activate=self._controllers, deactivate=()),
                "activate",
            )
            while self._monotonic() <= deadline:
                self._progress()
                if (
                    self._services.joint_callback_count > joint_callback_count_after_reset
                    and self._services.joints_converged(
                        self._expected_joints,
                        self._joint_tolerance,
                        after_callback_count=joint_callback_count_after_reset,
                    )
                ):
                    break
            else:
                raise self._failure("fresh joint convergence timeout")
            self._require(self._services.pause(True), "re-pause")
            saw_expected_epoch_unpaused = False
            while self._monotonic() <= deadline:
                self._progress()
                try:
                    current = self._observer.snapshot()
                except EvidenceStale:
                    self._require(self._services.pause(True), "re-pause retry")
                    continue
                if current.simulation_session_id != self._session_id:
                    raise self._failure("evidence session mismatch")
                if current.reset_epoch > expected_epoch:
                    raise self._failure("reset epoch mismatch")
                if current.reset_epoch == expected_epoch:
                    if not current.paused:
                        # The pause service can complete before the observer
                        # drains the last running frame emitted after the
                        # bounded resume.  That frame is expected and must not
                        # turn an otherwise valid transaction into a failure;
                        # only a fresh, authoritatively paused frame may pass.
                        saw_expected_epoch_unpaused = True
                        continue
                    if not self._services.controllers_active(self._controllers):
                        raise self._failure("controller convergence failed")
                    if not self._services.joints_converged(
                        self._expected_joints,
                        self._joint_tolerance,
                        after_callback_count=joint_callback_count_after_reset,
                    ):
                        raise self._failure("joint convergence failed")
                    return ResetReceipt(
                        old_epoch=old.reset_epoch,
                        new_epoch=reset_snapshot.reset_epoch,
                        keyframe=keyframe,
                        simulation_step=reset_snapshot.simulation_step,
                        simulation_session_id=self._session_id,
                    )
        except ResetFailed:
            raise
        except Exception as error:
            raise self._failure(f"reset transaction error: {error}") from error
        if saw_expected_epoch_unpaused:
            raise self._failure("final transaction evidence is not paused")
        raise self._failure("reset timeout waiting for epoch and state convergence")
