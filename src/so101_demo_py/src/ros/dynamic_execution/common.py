"""Constants, errors and small helpers shared by the dynamic execution modules."""

from __future__ import annotations

import math
import time

from so101_demo.core.domain import ActionResult
from so101_demo.core.place_height import PlaceHeightRefused

#: The Teacher run's failure codes of the evidence and joint-state streams (the codes raised by the shared helpers are mapped to these
#: where the failure becomes the attempt's: the helpers keep their own codes for the general runtime)
_TEACHER_CODE_MAP = {
    "DYNAMIC_SESSION_MISMATCH": "SIM_INTEGRITY_SESSION_MISMATCH",
    "DYNAMIC_RESET_EPOCH_MISMATCH": "SIM_INTEGRITY_RESET_EPOCH_MISMATCH",
    "DYNAMIC_EVIDENCE_TIMEOUT": "SIM_INTEGRITY_EVIDENCE_UNAVAILABLE",
    "JOINT_STATE_TIMEOUT": "TEACHER_JOINT_STATE_UNAVAILABLE",
}


_TEACHER_STOP_VELOCITY_RAD_S = 0.002


_STREAM_FLUSH_S = 1.0


_CONTROLLER_UNSETTLED_CODES = frozenset({
    "GRIPPER_GOAL_TIMEOUT", "GRIPPER_RESULT_TIMEOUT", "MOVEIT_EXECUTION_GOAL_TIMEOUT", "MOVEIT_EXECUTION_TIMEOUT",
    "TEACHER_CANCEL_UNSETTLED",
})


_PLAN_START_DRIFT_MAX_RAD = 0.01


# `teacher_execution_policy.yaml` of a Teacher run) is always used when it is loaded, and the Teacher refuses to start without it.
_DEFAULT_STATE_MAX_AGE_S = 0.5


_WINDOW_TOLERANCE_S = 1e-6


_DEFAULT_STATE_UNAVAILABLE_STOP_S = 1.0


_SUMMARY_JOIN_S = 5.0


_TEACHER_FAILED_CODES = frozenset({"TEACHER_ARM_NOT_STOPPED", "TEACHER_DWELL_TIMEOUT", "TEACHER_INJECTED_EXECUTION_FAILURE"})


INJECTED_EXECUTION_FAILURE = "TEACHER_INJECTED_EXECUTION_FAILURE"


def _evidence_is_finite(value) -> bool:
    """False when the cup state of a world sample holds a non-finite number (Teacher run: `SIM_INTEGRITY_NON_FINITE_STATE`)."""
    state = value.object_state
    return all(math.isfinite(item) for group in (state.position_world, state.orientation_xyzw, state.linear_velocity_world,
                                                 state.angular_velocity_world) for item in group)


class _ExecutionFailed(RuntimeError):
    """A non-stop failure of one trajectory execution; carries the `ActionResult` for the terminal-pose reconciliation."""

    def __init__(self, message: str, result: ActionResult) -> None:
        super().__init__(message)
        self.result = result


class _JointStateStale(PlaceHeightRefused):
    """The joint state ``k`` needs was older than ``state_max_age_s`` (the Teacher run selects ``JOINT_STATE_STALE``)."""


def _mark_phase(name):
    """D30, observation only: mark the active phase timer if any; never raises."""
    try:
        from so101_demo.ros.dynamic_runtime import _mark_active_phase
        _mark_active_phase(name)
    except Exception:
        pass


# Burst-spin budget (S3). `rclpy.spin_once` runs at most one callback, while evidence, scene, joint-state, chunk and
# camera callbacks arrive at hundreds per second in total (scenes alone at 100 Hz), so one spin per progress call left
# the depth-256 queues seconds behind. A zero-timeout spin costs well under 0.2 ms when a callback is ready, so 10 ms
# drains dozens of queued callbacks per call and keeps the added latency of one progress call at about 10 ms.
_SPIN_BURST_BUDGET_S = 0.010


_DATA_REASON_MAX_CHARS = 300


def _spin_burst(node, first_timeout_s=0.01, budget_s=_SPIN_BURST_BUDGET_S, spin=None):
    """One `spin_once(timeout_sec=first_timeout_s)`, then zero-timeout spins until `budget_s` has elapsed.

    Scheduling only: every callback runs exactly as before, just sooner and in larger batches. Exceptions from
    `spin` propagate unchanged. `spin` defaults to `rclpy.spin_once`.
    """
    if spin is None:
        import rclpy
        spin = rclpy.spin_once
    began = time.monotonic()
    spin(node, timeout_sec=first_timeout_s)
    while time.monotonic() - began < budget_s:
        spin(node, timeout_sec=0.0)
