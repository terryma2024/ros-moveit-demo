"""Teacher on MoveIt/JTC: stop flags, terminal stop routing, cup-safety and collision rules.

ROS-free. The numeric vectors are the activated contact-policy thresholds the broker used
(`config/mujoco/contact_calibration.yaml:195-196`) and the nominal/fault contacts of the old
`test_act_teacher_cup_safety.py::held_source` fixture (left 0.22 N, right 0.23 N, table 0.20 N,
signed distance -3e-5 m).
"""

import os
import signal
import threading
import time

import pytest

from so101_demo.core.domain import (
    ActionResult, ActionStatus, Failure, FailureCategory, RunMode, RunRequest, State,
)
from so101_demo.core.runner import StateMachineRunner, dry_run_actions
from so101_demo.core.simulation.types import ContactEvidence, ObjectState, SimulationEvidence
from so101_demo.core.workflow import SO101_WORKFLOW, resolve_transition

FORCE_LIMIT_N = 1.1579004532160448
COMPRESSION_LIMIT_M = 0.00012528745142373227

TERMINAL_CODES = (
    "DYNAMIC_FORCE_LIMIT_EXCEEDED", "DYNAMIC_CUP_FORCE_EXCEEDED", "DYNAMIC_CUP_COMPRESSION_EXCEEDED",
    "DYNAMIC_COLLISION_STOP", "DYNAMIC_STATE_UNAVAILABLE_STOP", "DYNAMIC_SESSION_MISMATCH",
    "DYNAMIC_RESET_EPOCH_MISMATCH", "TEACHER_DEADLINE", "TEACHER_USER_STOP", "TEACHER_PARENT_DIED",
    "TEACHER_CANCEL_UNSETTLED", "DYNAMIC_RELEASE_SUPPORT_NOT_PROVED",
)
FORWARD_ACTION_STATES = [
    state for state in SO101_WORKFLOW.forward_states if state in SO101_WORKFLOW.action_states
]


def failure(code):
    return Failure(FailureCategory.EXECUTION, code, code)


@pytest.mark.parametrize("code", TERMINAL_CODES)
@pytest.mark.parametrize("state", FORWARD_ACTION_STATES)
def test_safety_deadline_user_and_unsettled_stops_go_straight_to_error(state, code):
    assert resolve_transition(state, ActionStatus.FAILED, failure(code)) is State.ERROR


@pytest.mark.parametrize("code", ["MOVEIT_EXECUTION_FAILED", "MOVEIT_EXECUTION_REJECTED", "CUP_POSE_PLAN_FAILED"])
def test_controller_and_ordinary_failures_keep_the_original_recover_route(code):
    expected = SO101_WORKFLOW.transitions[State.DESCEND_TO_PLACE][1]
    assert expected is State.RECOVER_LIFT_TO_SAFE_HEIGHT
    assert resolve_transition(State.DESCEND_TO_PLACE, ActionStatus.FAILED, failure(code)) is expected
    assert resolve_transition(State.DESCEND_TO_PLACE, ActionStatus.FAILED) is expected  # no failure given: unchanged


class _Counting:
    def __init__(self, status=ActionStatus.SUCCEEDED, code=None):
        self.calls = 0
        self.status, self.code = status, code

    def run(self, _context):
        self.calls += 1
        return ActionResult(self.status, None if self.code is None else failure(self.code))


@pytest.mark.parametrize("code,recovers", [
    ("DYNAMIC_CUP_FORCE_EXCEEDED", False), ("TEACHER_DEADLINE", False), ("TEACHER_USER_STOP", False),
    ("MOVEIT_EXECUTION_FAILED", True)])
def test_runner_sends_no_recover_goal_after_a_stop_but_still_recovers_from_a_controller_failure(code, recovers):
    actions = dry_run_actions()
    actions[State.DESCEND_TO_PLACE] = _Counting(ActionStatus.FAILED, code)
    recover = {state: _Counting() for state in actions if state.name.startswith("RECOVER_")}
    actions.update(recover)
    result = StateMachineRunner(actions).run(RunRequest(mode=RunMode.DRY_RUN))
    assert result.status.value == "ERROR"
    assert result.failure.code == code
    assert (State.RECOVER_LIFT_TO_SAFE_HEIGHT in result.state_trace) is recovers
    assert any(item.calls for item in recover.values()) is recovers
    if not recovers:
        assert result.state_trace[-2:] == (State.DESCEND_TO_PLACE, State.ERROR)


# ---- stop flags ------------------------------------------------------------------------------------------------

def _stop_module():
    from so101_demo.ros import teacher_stop
    return teacher_stop


def test_user_stop_flag_raises_a_coded_runtime_error_on_the_calling_thread():
    stop = _stop_module()
    flags = stop.StopFlags(parent_pid=os.getppid())
    assert flags.reason() is None
    flags.raise_if_stopped()
    flags.request_user_stop()
    assert flags.reason() == "TEACHER_USER_STOP"
    with pytest.raises(RuntimeError) as raised:
        flags.raise_if_stopped()
    assert isinstance(raised.value, stop.TeacherStop) and raised.value.code == "TEACHER_USER_STOP"
    assert str(raised.value).startswith("TEACHER_USER_STOP")
    flags.request_user_stop("TEACHER_PARENT_DIED")  # the first reason wins
    assert flags.reason() == "TEACHER_USER_STOP"


def test_parent_death_sets_the_user_stop_flag_with_reason_parent_died():
    stop = _stop_module()
    parent = [4242]
    flags = stop.StopFlags(parent_pid=4242, getppid=lambda: parent[0])
    assert flags.reason() is None
    parent[0] = 1  # re-parented to init
    assert flags.reason() == "TEACHER_PARENT_DIED"
    with pytest.raises(stop.TeacherStop) as raised:
        flags.raise_if_stopped()
    assert raised.value.code == "TEACHER_PARENT_DIED"


def test_deadline_is_frozen_at_arming_and_seen_through_a_fake_clock():
    stop = _stop_module()
    now = [100.0]
    flags = stop.StopFlags(parent_pid=os.getppid(), clock=lambda: now[0])
    assert flags.reason() is None
    flags.arm_deadline(180.0)
    now[0] = 279.9
    assert flags.reason() is None
    now[0] = 280.0
    assert flags.reason() == "TEACHER_DEADLINE"
    flags.arm_deadline(10_000.0)  # frozen: a later call cannot move it
    assert flags.reason() == "TEACHER_DEADLINE"


def test_deadline_watchdog_thread_only_sets_the_flag_and_never_cancels():
    stop = _stop_module()
    now = [0.0]
    flags = stop.StopFlags(parent_pid=os.getppid(), clock=lambda: now[0])
    flags.arm_deadline(180.0)
    seen = []
    watchdog = stop.DeadlineWatchdog(flags, poll_s=0.001)
    watchdog.start()
    try:
        now[0] = 181.0
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not flags.deadline_flag_set:
            time.sleep(0.001)
        assert flags.deadline_flag_set is True
        seen.append(threading.current_thread() is not watchdog.thread)
    finally:
        watchdog.stop()
    assert seen == [True]
    assert not hasattr(watchdog, "cancel") and not hasattr(flags, "cancel")


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_signal_handler_only_sets_the_stop_flag(signum):
    stop = _stop_module()
    flags = stop.StopFlags(parent_pid=os.getppid())
    previous = signal.getsignal(signum)
    restore = flags.install_signal_handlers()
    try:
        os.kill(os.getpid(), signum)  # no KeyboardInterrupt, no exit: the flag is the only effect
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and flags.reason() is None:
            time.sleep(0.001)
        assert flags.reason() == "TEACHER_USER_STOP"
    finally:
        restore()
    assert signal.getsignal(signum) == previous


# ---- cup safety (force / compression), same numbers as the broker ----------------------------------------------

def contact(body2, geom2, force, distance):
    return ContactEvidence(12, 93, "plastic_cup", "bottom_collision", 7, 70, body2, geom2,
                           (0.0, 0.0, 0.1), (0.0, 0.0, 1.0), distance, force)


def evidence(*, left=(0.22,), right=(0.23,), other=(0.20,), distance=-3e-5, truncated=False,
             right_distance=None, other_distance=-5e-5, step=1000):
    left_c = tuple(contact("gripper", "fixed_fingertip_pad_collision_006", f, distance) for f in left)
    right_c = tuple(contact("jaw", "moving_fingertip_pad_collision_000", f,
                            distance if right_distance is None else right_distance) for f in right)
    other_c = tuple(contact("table", "table_collision", f, other_distance) for f in other)
    every = left_c + right_c + other_c
    return SimulationEvidence(
        simulation_time_s=step * 0.002, frame_id="world", publisher_sequence=step, simulation_step=step,
        reset_epoch=1, simulation_session_id="s", paused=False,
        object_state=ObjectState(12, "plastic_cup", (0.02, -0.28, 0.165), (0.0, 0.0, 0.0, 1.0),
                                 (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        has_contact=bool(every),
        minimum_signed_distance_m=min((c.signed_distance_m for c in every), default=0.0),
        maximum_normal_force_n=max((c.normal_force_n for c in every), default=0.0),
        truncated=truncated, left_fingertip_contacts=left_c, right_fingertip_contacts=right_c,
        other_object_contacts=other_c)


def limits():
    from so101_demo.ros.teacher_safety import CupSafetyLimits
    return CupSafetyLimits(maximum_safe_force_n=FORCE_LIMIT_N, maximum_compression_distance_m=COMPRESSION_LIMIT_M)


def verdict(sample):
    from so101_demo.ros.teacher_safety import evaluate_cup_contacts
    return evaluate_cup_contacts(sample, limits())


def test_nominal_hold_is_not_a_stop():
    result = verdict(evidence())
    assert result.code is None and result.unavailable is False
    assert result.summed_force_n == pytest.approx(0.65) and result.compression_m == pytest.approx(3e-5)


def test_summed_force_over_left_right_and_other_contacts_above_the_limit_stops():
    assert verdict(evidence(left=(4.0,))).code == "DYNAMIC_CUP_FORCE_EXCEEDED"
    # each contact is below the limit, the sum is not: left 0.6 + right 0.6 + table 0.1 = 1.3 N
    assert verdict(evidence(left=(0.6,), right=(0.6,), other=(0.1,))).code == "DYNAMIC_CUP_FORCE_EXCEEDED"


def test_force_boundary_is_strictly_greater_than():
    assert verdict(evidence(left=(FORCE_LIMIT_N - 0.45,), right=(0.23,), other=(0.22,))).code is None
    assert verdict(evidence(left=(FORCE_LIMIT_N,), right=(), other=())).code is None
    over = FORCE_LIMIT_N + 1e-9
    assert verdict(evidence(left=(over,), right=(), other=())).code == "DYNAMIC_CUP_FORCE_EXCEEDED"


def test_compression_over_the_limit_on_a_fingertip_contact_stops():
    assert verdict(evidence(right_distance=-2e-4)).code == "DYNAMIC_CUP_COMPRESSION_EXCEEDED"
    assert verdict(evidence(distance=-COMPRESSION_LIMIT_M)).code is None
    assert verdict(evidence(distance=-(COMPRESSION_LIMIT_M + 1e-9))).code == "DYNAMIC_CUP_COMPRESSION_EXCEEDED"


def test_table_contact_compression_is_not_a_cup_compression_stop():
    assert verdict(evidence(other_distance=-0.01)).code is None


def test_truncated_evidence_is_unavailable_never_zero_force():
    result = verdict(evidence(left=(4.0,), truncated=True))
    assert result.unavailable is True and result.code is None


def test_limits_come_from_the_activated_policy_thresholds_and_refuse_a_missing_value():
    from so101_demo.ros.teacher_safety import limits_from_thresholds
    value = limits_from_thresholds({"maximum_safe_force_n": FORCE_LIMIT_N,
                                    "maximum_compression_distance_m": COMPRESSION_LIMIT_M,
                                    "minimum_bilateral_force_n": 0.05})
    assert (value.maximum_safe_force_n, value.maximum_compression_distance_m) == (FORCE_LIMIT_N, COMPRESSION_LIMIT_M)
    for bad in ({}, {"maximum_safe_force_n": FORCE_LIMIT_N}, {"maximum_safe_force_n": 0.0,
                "maximum_compression_distance_m": 1e-4}, {"maximum_safe_force_n": float("nan"),
                "maximum_compression_distance_m": 1e-4}):
        with pytest.raises(ValueError, match="TEACHER_SAFETY_LIMITS_INVALID"):
            limits_from_thresholds(bad)


# ---- collision watch --------------------------------------------------------------------------------------------

PROCESS_PAIRS = frozenset({("bottom_collision", "table_collision"),
                           ("bottom_collision", "fixed_fingertip_pad_collision_006"),
                           ("bottom_collision", "moving_fingertip_pad_collision_000")})
KNOWN = frozenset({"bottom_collision", "table_collision", "fixed_fingertip_pad_collision_006",
                   "moving_fingertip_pad_collision_000", "upper_arm_collision", "base_collision"})


def frame(pairs, *, epoch=1, session="s", truncated=False, loss=False, step=10):
    return {"simulation_session_id": session, "reset_epoch": epoch, "physics_step": step,
            "simulation_time_s": step * 0.002, "geom_a": [a for a, _ in pairs], "geom_b": [b for _, b in pairs],
            "signed_distance_m": [-1e-4] * len(pairs), "normal_force_n": [0.5] * len(pairs),
            "truncated": truncated, "evidence_loss": loss}


def watch():
    from so101_demo.ros.teacher_safety import CollisionWatch
    return CollisionWatch(process_pairs=PROCESS_PAIRS, known_geoms=KNOWN, session_id="s", reset_epoch=1)


def test_cup_process_pairs_are_audit_only_not_a_collision_stop():
    value = watch()
    value.accept(frame([("bottom_collision", "table_collision"), ("bottom_collision", "fixed_fingertip_pad_collision_006")]))
    assert value.hazard is None


def test_robot_against_table_or_robot_is_a_collision_stop():
    value = watch()
    value.accept(frame([("table_collision", "upper_arm_collision")], step=11))
    assert value.hazard == "DYNAMIC_COLLISION_STOP"
    assert "upper_arm_collision" in value.detail and value.hazard_step == 11
    value.accept(frame([], step=12))  # latched: a clean frame does not clear it
    assert value.hazard == "DYNAMIC_COLLISION_STOP"


@pytest.mark.parametrize("kind", ["truncated", "evidence_loss"])
def test_truncated_or_lossy_contact_frame_is_a_stop_because_collisions_are_not_evaluable(kind):
    value = watch()
    value.accept(frame([], truncated=kind == "truncated", loss=kind == "evidence_loss"))
    assert value.hazard == "DYNAMIC_COLLISION_STOP"


def test_frames_of_an_earlier_reset_epoch_are_ignored_and_foreign_identity_is_a_stop():
    value = watch()
    value.accept(frame([("table_collision", "upper_arm_collision")], epoch=0))
    assert value.hazard is None
    value.accept(frame([], session="other"))
    assert value.hazard == "DYNAMIC_COLLISION_STOP"


def test_c2_direct_terminal_stop_edge_records_its_failure_boundary():
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution

    trace = (State.IDLE, State.LIFT, State.MOVE_ABOVE_PLACE, State.ERROR)
    stop = Failure(FailureCategory.COLLISION, "DYNAMIC_CUP_COMPRESSION_EXCEEDED", "x")
    assert RosDynamicMujocoExecution._failure_boundary(trace, stop) is State.MOVE_ABOVE_PLACE
    assert RosDynamicMujocoExecution._failure_boundary(trace, None) is None
