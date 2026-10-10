"""B1: the Teacher's original MoveIt ExecuteTrajectory + JTC path, its stop paths and its safety port.

Fixture level: the real `RosDynamicMujocoExecution`, `MoveItExecutionClient` and `GripperClient` over fake action
clients and a fake world observer. No ROS graph, no hardware.
"""

import os
import signal
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.general_runtime_policy import load_general_runtime_policy
from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.backends.mujoco.observer import EvidenceStale
from so101_demo.control.gripper.client import GripperClient
from so101_demo.control.trajectory.executor import MoveItExecutionClient
from so101_demo.core.domain import ActionStatus, State
from so101_demo.core.simulation.types import ReceivedSimulationEvidence
from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution

from test_b1_teacher_stop_core import (
    COMPRESSION_LIMIT_M, FORCE_LIMIT_N, evidence,
)
from paths import PACKAGE_ROOT

GENERAL_RUNTIME_POLICY = PACKAGE_ROOT / "config/act/general_runtime_policy.yaml"
TEACHER_POLICY = PACKAGE_ROOT / "config/act/teacher_execution_policy.yaml"
ARM = ("1", "2", "3", "4", "5")


class FakeObserver:
    """The newest accepted evidence with the real observer's freshness rule (max age 0.5 s)."""

    def __init__(self, clock):
        self.clock, self.sample, self.received, self.snapshot_calls = clock, None, None, 0

    def put(self, sample, received=None):
        self.sample, self.received = sample, self.clock() if received is None else received

    def snapshot_with_receipt(self):
        self.snapshot_calls += 1
        if self.sample is None or self.clock() - self.received > 0.5:
            raise EvidenceStale("stale")
        return ReceivedSimulationEvidence(self.sample, self.received)

    def snapshot(self):
        return self.snapshot_with_receipt().evidence


def make_adapter(tmp_path, *, limits=True, flags=True, clock_start=100.0):
    from so101_demo.ros.teacher_safety import CupSafetyLimits
    from so101_demo.ros.teacher_stop import StopFlags

    now = [clock_start]
    value = object.__new__(RosDynamicMujocoExecution)
    value._now = now
    value._monotonic = lambda: now[0]
    value._session_id, value._expected_reset_epoch = "s", 1
    value._execution_policy = load_general_runtime_policy(GENERAL_RUNTIME_POLICY)
    value._document = {}
    value._evidence_file = tmp_path / "dynamic-execute-manifest.json"
    value._state_events, value._planning_attempts = [], []
    value._positions = {name: 0.0 for name in (*ARM, "6")}
    value._joint_velocities = {name: 0.0 for name in (*ARM, "6")}
    value._joint_state_generation = 1
    value._joint_state_received_monotonic_s = now[0]
    value._progress = lambda: None
    value._initial = None
    value._attached = True
    value.observer = FakeObserver(lambda: now[0])
    value.observer.put(evidence())
    value._safety_limits = (CupSafetyLimits(FORCE_LIMIT_N, COMPRESSION_LIMIT_M) if limits else None)
    value._collision_watch = None
    value._stop_flags = StopFlags(parent_pid=os.getppid(), clock=lambda: now[0]) if flags else None
    value._attempt_id = "attempt-1"
    value._safety_state = State.MOVE_ABOVE_PLACE
    value._release_runtime_policy = {"safety_release": {"support_distance_max_m": 0.002}}
    return value


def no_snapshot(value):
    def refuse():
        pytest.fail("the monitor must not use the blocking _snapshot()")
    value._snapshot = refuse


# ---- monitor: force, cup safety, unavailable state, identity, collision --------------------------------------

def run_monitor(value, state=State.MOVE_ABOVE_PLACE):
    no_snapshot(value)
    return value._motion_monitor(state)()


def test_monitor_passes_a_nominal_sample_without_the_blocking_snapshot(tmp_path):
    value = make_adapter(tmp_path)
    run_monitor(value)
    assert value.observer.snapshot_calls >= 1


def test_original_maximum_force_limit_still_cancels(tmp_path):
    value = make_adapter(tmp_path, limits=False)
    value.observer.put(evidence(left=(12.0,), right=(), other=()))
    with pytest.raises(RuntimeError, match="DYNAMIC_FORCE_LIMIT_EXCEEDED"):
        run_monitor(value)
    assert value._document["monitor_violation"]["reason"] == "DYNAMIC_FORCE_LIMIT_EXCEEDED"


def test_cup_summed_force_above_the_activated_limit_stops_below_the_original_limit(tmp_path):
    value = make_adapter(tmp_path)
    value.observer.put(evidence(left=(0.6,), right=(0.6,), other=(0.1,)))  # max 0.6 N, sum 1.3 N
    with pytest.raises(RuntimeError, match="DYNAMIC_CUP_FORCE_EXCEEDED"):
        run_monitor(value)
    # the same sample is not a stop without the frozen contact policy (ordinary pick-place keeps only 11.6 N)
    plain = make_adapter(tmp_path, limits=False)
    plain.observer.put(evidence(left=(0.6,), right=(0.6,), other=(0.1,)))
    run_monitor(plain)


def test_cup_compression_above_the_activated_limit_stops(tmp_path):
    value = make_adapter(tmp_path)
    value.observer.put(evidence(right_distance=-2e-4))
    with pytest.raises(RuntimeError, match="DYNAMIC_CUP_COMPRESSION_EXCEEDED"):
        run_monitor(value)


def test_unavailable_state_is_tolerated_for_one_second_then_stops(tmp_path):
    value = make_adapter(tmp_path)
    value.observer.put(evidence())
    value._now[0] += 0.6  # evidence is now older than state_max_age_s (0.5 s): the safety checks are unavailable
    run_monitor(value)  # first unavailable instant: no stop yet
    value._now[0] += 0.9
    value._joint_state_received_monotonic_s = value._now[0]
    run_monitor(value)  # 0.9 s unavailable: still tolerated
    value._now[0] += 0.2
    value._joint_state_received_monotonic_s = value._now[0]
    with pytest.raises(RuntimeError, match="DYNAMIC_STATE_UNAVAILABLE_STOP"):
        run_monitor(value)


def test_recovered_state_restarts_the_unavailable_timer(tmp_path):
    value = make_adapter(tmp_path)
    value._now[0] += 0.6
    run_monitor(value)
    value._now[0] += 0.5
    value.observer.put(evidence())
    value._joint_state_received_monotonic_s = value._now[0]
    run_monitor(value)  # fresh again
    value._now[0] += 0.6
    run_monitor(value)  # a new unavailable period starts here
    value._now[0] += 0.9
    value._joint_state_received_monotonic_s = value._now[0]
    run_monitor(value)  # 0.9 s into the new period: no stop


def test_stale_joint_state_is_also_unavailable_state(tmp_path):
    value = make_adapter(tmp_path)
    value._joint_state_received_monotonic_s = value._now[0] - 0.6
    run_monitor(value)
    value._now[0] += 1.1
    value.observer.put(evidence())
    with pytest.raises(RuntimeError, match="DYNAMIC_STATE_UNAVAILABLE_STOP"):
        run_monitor(value)


@pytest.mark.parametrize("change,code", [
    ({"simulation_session_id": "other"}, "DYNAMIC_SESSION_MISMATCH"),
    ({"paused": True}, "DYNAMIC_RESET_EPOCH_MISMATCH"),
    ({"reset_epoch": 2}, "DYNAMIC_RESET_EPOCH_MISMATCH"),
])
def test_monitor_keeps_the_identity_checks_of_snapshot_on_the_latest_sample(tmp_path, change, code):
    from dataclasses import replace
    value = make_adapter(tmp_path)
    value.observer.put(replace(evidence(), **change))
    with pytest.raises(RuntimeError, match=code):
        run_monitor(value)


def test_collision_watch_hazard_stops_the_monitor(tmp_path):
    from so101_demo.ros.teacher_safety import CollisionWatch
    value = make_adapter(tmp_path)
    watch = CollisionWatch(process_pairs=frozenset(), known_geoms=frozenset(), session_id="s", reset_epoch=1)
    value._collision_watch = watch
    run_monitor(value)
    watch.accept({"simulation_session_id": "s", "reset_epoch": 1, "physics_step": 5, "simulation_time_s": 0.01,
                  "geom_a": ["table_collision"], "geom_b": ["upper_arm_collision"], "signed_distance_m": [-1e-4],
                  "normal_force_n": [2.0], "truncated": False, "evidence_loss": False})
    with pytest.raises(RuntimeError, match="DYNAMIC_COLLISION_STOP"):
        run_monitor(value)


def test_audit_only_process_rows_never_raise(tmp_path):
    value = make_adapter(tmp_path)
    run_monitor(value, State.MOVE_ABOVE_PLACE)  # carried state, bilateral contact present: nothing recorded
    value.observer.put(evidence(left=(), right=()))
    run_monitor(value, State.MOVE_ABOVE_PLACE)  # bilateral lost for 0s: guard grace, no raise


def test_user_flag_deadline_flag_and_parent_death_are_raised_by_the_monitor(tmp_path):
    for how, code in (("user", "TEACHER_USER_STOP"), ("deadline", "TEACHER_DEADLINE"), ("parent", "TEACHER_PARENT_DIED")):
        value = make_adapter(tmp_path)
        run_monitor(value)
        if how == "user":
            value._stop_flags.request_user_stop()
        elif how == "deadline":
            value._stop_flags.set_deadline_flag()
        else:
            value._stop_flags._getppid = lambda: 1
        with pytest.raises(RuntimeError, match=code):
            run_monitor(value)


def test_progress_never_raises_the_stop_flag(tmp_path):
    """The flag is raised only where a cancel follows: `executor.execute` calls progress() before monitor()."""
    import inspect
    assert "stop" not in inspect.getsource(RosDynamicMujocoExecution._progress).lower()
    value = object.__new__(RosDynamicMujocoExecution)
    value._stop_flags = make_adapter(tmp_path)._stop_flags
    value._stop_flags.request_user_stop()
    value._node = object()
    import rclpy
    original = rclpy.spin_once
    rclpy.spin_once = lambda *_args, **_kwargs: None
    try:
        value._progress()  # does not raise
    finally:
        rclpy.spin_once = original


# ---- fake MoveIt ExecuteTrajectory / JTC clients ---------------------------------------------------------------

class Future:
    def __init__(self, value=None, done=True):
        self._value, self._done = value, done

    def done(self):
        return self._done

    def result(self):
        return self._value

    def finish(self, value):
        self._value, self._done = value, True


class TimedFuture(Future):
    """Finishes by itself after `after_s` of real time (a goal the controller completes on its own)."""

    def __init__(self, after_s, success_value):
        super().__init__(done=False)
        self._at, self._success = time.monotonic() + after_s, success_value

    def done(self):
        if not self._done and time.monotonic() >= self._at:
            self.finish(self._success)
        return self._done


class GoalHandle:
    accepted = True

    def __init__(self, *, settle_on_cancel=True, error_code=1, done=False, finish_after_s=None, gripper=False):
        # MoveIt's ExecuteTrajectory result carries error_code.val (1 = SUCCESS); FollowJointTrajectory an int (0)
        self.gripper = gripper
        success = SimpleNamespace(result=SimpleNamespace(error_code=0 if gripper else SimpleNamespace(val=1)))
        self.result_future = Future(done=False) if finish_after_s is None else TimedFuture(finish_after_s, success)
        self.cancel_calls, self.cancel_threads = 0, []
        self.settle_on_cancel = settle_on_cancel
        self.error_code = error_code
        if done:
            self.result_future.finish(SimpleNamespace(result=SimpleNamespace(
                error_code=SimpleNamespace(val=error_code))))

    def cancel_goal_async(self):
        self.cancel_calls += 1
        self.cancel_threads.append(threading.get_ident())
        if self.settle_on_cancel:
            self.result_future.finish(SimpleNamespace(result=SimpleNamespace(
                error_code=-4 if self.gripper else SimpleNamespace(val=-4))))
        return Future("cancelled")

    def get_result_async(self):
        return self.result_future


class ActionClientDouble:
    def __init__(self, **handle_options):
        self.handle_options, self.goals, self.handles = handle_options, [], []

    def wait_for_server(self, timeout_sec=None):
        return True

    def send_goal_async(self, goal):
        self.goals.append(goal)
        handle = GoalHandle(**self.handle_options)
        self.handles.append(handle)
        return Future(handle)


def trajectory(start=(0.0,) * 5):
    return SimpleNamespace(joint_trajectory=SimpleNamespace(
        joint_names=list(ARM), points=[SimpleNamespace(positions=list(start)),
                                       SimpleNamespace(positions=[0.1] * 5)]))


def arm_adapter(tmp_path, **options):
    value = make_adapter(tmp_path)
    client = ActionClientDouble(**{key: options.pop(key) for key in list(options) if key in
                                   ("settle_on_cancel", "error_code", "done", "finish_after_s")})
    value._trajectory = MoveItExecutionClient(client, goal_factory=None, progress=value._progress,
                                              cancellation_timeout_s=options.get("cancellation_timeout_s", 0.1))
    return value, client


def test_monitor_raise_cancels_the_execute_trajectory_goal_and_reports_the_monitor_reason(tmp_path):
    value, client = arm_adapter(tmp_path)
    value.observer.put(evidence(left=(4.0,)))
    with pytest.raises(RuntimeError) as raised:
        value._execute_planned(trajectory(), State.MOVE_ABOVE_PLACE, value._motion_monitor(State.MOVE_ABOVE_PLACE))
    assert str(raised.value).startswith("DYNAMIC_CUP_FORCE_EXCEEDED")
    assert [handle.cancel_calls for handle in client.handles] == [1]
    assert client.handles[0].cancel_threads == [threading.get_ident()]


def test_cancel_that_does_not_settle_is_terminal_and_names_the_original_reason(tmp_path):
    value, client = arm_adapter(tmp_path, settle_on_cancel=False)
    value.observer.put(evidence(left=(4.0,)))
    with pytest.raises(RuntimeError) as raised:
        value._execute_planned(trajectory(), State.MOVE_ABOVE_PLACE, value._motion_monitor(State.MOVE_ABOVE_PLACE))
    assert str(raised.value).startswith("TEACHER_CANCEL_UNSETTLED")
    assert "DYNAMIC_CUP_FORCE_EXCEEDED" in str(raised.value)
    assert value._document["cancel_unsettled"]["reason"] == "DYNAMIC_CUP_FORCE_EXCEEDED"


def test_controller_failure_result_is_not_a_stop_and_keeps_the_recover_route(tmp_path):
    from so101_demo.core.domain import Failure, FailureCategory
    from so101_demo.core.workflow import resolve_transition
    value, client = arm_adapter(tmp_path, error_code=-6, done=True)
    with pytest.raises(RuntimeError) as raised:
        value._execute_planned(trajectory(), State.DESCEND_TO_PLACE, lambda: None)
    code = str(raised.value).split(":")[0]
    assert code == "MOVEIT_EXECUTION_FAILED"
    assert resolve_transition(State.DESCEND_TO_PLACE, ActionStatus.FAILED,
                              Failure(FailureCategory.EXECUTION, code)) is State.RECOVER_LIFT_TO_SAFE_HEIGHT
    assert client.handles[0].cancel_calls == 0


@pytest.mark.parametrize("drift,sent", [(0.009, True), (0.011, False)])
def test_plan_start_drift_above_0_01_rad_is_refused_before_any_goal(tmp_path, drift, sent):
    value, client = arm_adapter(tmp_path, done=True)
    value._positions.update({"1": drift})
    plan = trajectory(start=(0.0,) * 5)
    if sent:
        value._execute_planned(plan, State.MOVE_ABOVE_PLACE, lambda: None)
        assert len(client.goals) == 1
    else:
        with pytest.raises(RuntimeError, match="DYNAMIC_PLAN_START_DRIFT"):
            value._execute_planned(plan, State.MOVE_ABOVE_PLACE, lambda: None)
        assert client.goals == []


def test_arm_segment_timeout_cancels_and_a_settled_cancel_is_an_ordinary_timeout(tmp_path):
    value, client = arm_adapter(tmp_path)
    value._execute_timeout_s = 0.05
    with pytest.raises(RuntimeError) as raised:
        value._execute_planned(trajectory(), State.MOVE_ABOVE_PLACE, lambda: None)
    assert str(raised.value).startswith("MOVEIT_EXECUTION_TIMEOUT")
    assert client.handles[0].cancel_calls == 1


def test_arm_segment_timeout_with_an_unsettled_cancel_is_terminal(tmp_path):
    value, client = arm_adapter(tmp_path, settle_on_cancel=False)
    value._execute_timeout_s = 0.05
    with pytest.raises(RuntimeError, match="TEACHER_CANCEL_UNSETTLED"):
        value._execute_planned(trajectory(), State.MOVE_ABOVE_PLACE, lambda: None)


# ---- deadline, user stop and parent death through the real executor ---------------------------------------------

def test_deadline_flag_cancels_the_active_goal_from_the_executing_thread_and_no_new_goal_follows(tmp_path):
    value, client = arm_adapter(tmp_path)
    value._stop_flags.arm_deadline(180.0)
    # the fake clock passes the frozen deadline while the goal is active
    value._trajectory._progress = lambda: value._now.__setitem__(0, value._now[0] + 181.0)
    with pytest.raises(RuntimeError, match="TEACHER_DEADLINE"):
        value._execute_planned(trajectory(), State.MOVE_ABOVE_PLACE, value._motion_monitor(State.MOVE_ABOVE_PLACE))
    assert client.handles[0].cancel_threads == [threading.get_ident()]
    goals_before = len(client.goals)
    result = value.perform(State.MOVE_ABOVE_OBJECT, None)  # the state machine asks for the next state
    assert result.status is ActionStatus.FAILED and result.failure.code == "TEACHER_DEADLINE"
    assert len(client.goals) == goals_before


def test_a_deadline_that_has_already_passed_sends_no_goal(tmp_path):
    value, client = arm_adapter(tmp_path)
    value._stop_flags.arm_deadline(180.0)
    value._now[0] += 181.0
    with pytest.raises(RuntimeError, match="TEACHER_DEADLINE"):
        value._execute_planned(trajectory(), State.MOVE_ABOVE_PLACE, value._motion_monitor(State.MOVE_ABOVE_PLACE))
    assert client.goals == []


def test_sigint_during_an_active_goal_cancels_and_returns_within_six_seconds(tmp_path):
    value, client = arm_adapter(tmp_path)
    previous = signal.getsignal(signal.SIGINT)
    restore = value._stop_flags.install_signal_handlers()
    started = time.monotonic()
    timer = threading.Timer(0.05, lambda: os.kill(os.getpid(), signal.SIGINT))
    timer.start()
    try:
        with pytest.raises(RuntimeError, match="TEACHER_USER_STOP"):
            value._execute_planned(trajectory(), State.MOVE_ABOVE_PLACE, value._motion_monitor(State.MOVE_ABOVE_PLACE))
    finally:
        timer.cancel()
        restore()
    assert time.monotonic() - started <= 6.0
    assert client.handles[0].cancel_calls == 1
    assert signal.getsignal(signal.SIGINT) == previous


def test_sigint_during_a_service_or_planning_wait_without_a_goal_exits_within_six_seconds(tmp_path):
    from moveit_msgs.srv import GetPlanningScene

    class SilentService:
        def wait_for_service(self, **kwargs):
            return True

        def call_async(self, request):
            return Future(done=False)

    value = make_adapter(tmp_path)
    value._node = object()
    value._scene_service_calls = []
    value._apply_scene = value._get_scene = SilentService()
    restore = value._stop_flags.install_signal_handlers()
    started = time.monotonic()
    timer = threading.Timer(0.05, lambda: os.kill(os.getpid(), signal.SIGINT))
    timer.start()
    try:
        with pytest.raises(RuntimeError, match="TEACHER_USER_STOP"):
            value._call(value._get_scene, GetPlanningScene.Request(), 3.0, "DYNAMIC_SCENE_READBACK")
    finally:
        timer.cancel()
        restore()
    assert time.monotonic() - started <= 6.0


@pytest.mark.parametrize("wait", ["joint_state", "controllers_stopped", "settled_snapshot"])
def test_every_wait_loop_without_a_goal_checks_the_stop_flag(tmp_path, wait):
    value = make_adapter(tmp_path)
    value._progress = lambda: value._now.__setitem__(0, value._now[0] + 0.05)
    value._positions = {}  # nothing to read: each loop would wait for its full timeout
    value._joint_velocities = {name: 1.0 for name in (*ARM, "6")}
    value.observer.sample = None
    value._stop_flags.request_user_stop()
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="TEACHER_USER_STOP"):
        if wait == "joint_state":
            value._joint_state(timeout_s=3.0)
        elif wait == "controllers_stopped":
            value._controllers_stopped({"state_unavailable_stop_s": 30.0, "state_max_age_s": 0.5})
        else:
            value._settled_snapshot(0.2, 30.0)
    assert time.monotonic() - started < 2.0


def test_first_source_after_stop_checks_the_stop_flag(tmp_path):
    value = make_adapter(tmp_path)
    value._progress = lambda: value._now.__setitem__(0, value._now[0] + 0.05)
    value._stop_flags.request_user_stop()
    value.observer = SimpleNamespace(recent_with_receipts=lambda: ())
    from so101_demo.adapters.act.scene_state import SceneStateObserver
    value._scene_source_observer = SceneStateObserver(model_sha256="a" * 64, nq=1, nv=1, max_age_s=0.5,
                                                      monotonic=value._monotonic)
    value._scene_source_observer.reset("s", 1, source_floor_s=0.0)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="TEACHER_USER_STOP"):
        value._first_source_after_stop({"stop_confirmed_wall_s": 100.0}, previous_step=0, previous_sequence=0)
    assert time.monotonic() - started < 2.0


# ---- gripper stop hook -----------------------------------------------------------------------------------------

def gripper_adapter(tmp_path, **handle_options):
    value = make_adapter(tmp_path)
    # a gripper goal that would complete by itself after 0.3 s: a missing stop hook shows as a wrong outcome, not a hang
    client = ActionClientDouble(**{"finish_after_s": 0.3, "gripper": True, **handle_options})
    value._gripper = GripperClient(client, progress=value._progress)
    return value, client


def test_compression_during_close_gripper_cancels_the_gripper_goal(tmp_path):
    value, client = gripper_adapter(tmp_path)
    value.observer.put(evidence(right_distance=-2e-4))
    with pytest.raises(RuntimeError, match="DYNAMIC_CUP_COMPRESSION_EXCEEDED"):
        value._command_gripper(State.CLOSE_GRIPPER, value._CLOSE_Q6, before=evidence())
    assert [handle.cancel_calls for handle in client.handles] == [1]


@pytest.mark.parametrize("how,code", [("user", "TEACHER_USER_STOP"), ("deadline", "TEACHER_DEADLINE")])
def test_user_and_deadline_flags_each_cancel_a_gripper_goal(tmp_path, how, code):
    value, client = gripper_adapter(tmp_path)
    send = client.send_goal_async

    def send_then_flag(goal):
        future = send(goal)
        # the flag arrives while the goal is active
        (value._stop_flags.request_user_stop if how == "user" else value._stop_flags.set_deadline_flag)()
        return future

    client.send_goal_async = send_then_flag
    with pytest.raises(RuntimeError, match=code):
        value._command_gripper(State.CLOSE_GRIPPER, value._CLOSE_Q6, before=evidence())
    assert [handle.cancel_calls for handle in client.handles] == [1]


def test_a_stop_flag_set_before_a_gripper_command_sends_no_goal(tmp_path):
    value, client = gripper_adapter(tmp_path)
    value._stop_flags.request_user_stop()
    with pytest.raises(RuntimeError, match="TEACHER_USER_STOP"):
        value._command_gripper(State.CLOSE_GRIPPER, value._CLOSE_Q6, before=evidence())
    assert client.goals == []


def test_gripper_cancel_that_never_settles_is_terminal(tmp_path):
    value, client = gripper_adapter(tmp_path, settle_on_cancel=False)
    value._gripper._cancellation_timeout_s = 0.05
    value.observer.put(evidence(right_distance=-2e-4))
    with pytest.raises(RuntimeError, match="TEACHER_CANCEL_UNSETTLED"):
        value._command_gripper(State.CLOSE_GRIPPER, value._CLOSE_Q6, before=evidence())


def test_gripper_client_without_a_monitor_behaves_as_in_main():
    import inspect
    parameters = inspect.signature(GripperClient.command).parameters
    assert "monitor" in parameters and "dispatch_guard" not in parameters and "start_q6" not in parameters


# ---- release: no broker, scope, stop proof, support-before-open ------------------------------------------------

def release_adapter(tmp_path, *, supported=True, velocity=0.0, trajectory_result="SUCCEEDED"):
    from so101_demo.adapters.act.scene_state import SceneStateObserver
    value = make_adapter(tmp_path)
    value._release_runtime_policy = {"safety_release": {"support_distance_max_m": 0.002}}
    value._joint_velocities = {name: velocity for name in (*ARM, "6")}
    value._joint_state_received_monotonic_s = 99.98  # the joint state that confirmed the stop
    value._progress = lambda: value._now.__setitem__(0, value._now[0] + 0.005)
    value._last_arm_result = trajectory_result
    value._release_authorization = None
    value._write = lambda: None
    base = evidence(other=(0.2,) if supported else ())
    value.observer.put(base, received=99.6)
    receipts = (ReceivedSimulationEvidence(base, 99.6),
                ReceivedSimulationEvidence(_later(base, 1), 99.99),
                ReceivedSimulationEvidence(_later(base, 2), 99.995))
    value.observer.recent_with_receipts = lambda: receipts
    scene = SceneStateObserver(model_sha256="a" * 64, nq=1, nv=1, max_age_s=0.5, monotonic=value._monotonic)
    scene.reset("s", 1, source_floor_s=0.0)
    for index, step in enumerate((1001, 1002)):
        end = round((99.99 + index * 0.005 - 0.0005) * 1e9)
        scene.accept({"simulation_session_id": "s", "reset_epoch": 1, "simulation_step": step, "paused": False,
                      "simulation_time_s": step * 0.002, "model_sha256": "a" * 64, "qpos": [0.0], "qvel": [0.0],
                      "clock_interval_begin_monotonic_ns": end - 1_000_000, "clock_interval_end_monotonic_ns": end})
    value._scene_source_observer = scene
    value._confirm_detached_shadow = lambda: True
    commands = []
    value._command_gripper = lambda *args, **kwargs: commands.append((args, kwargs))
    return value, commands


def _later(sample, offset):
    from dataclasses import replace
    return replace(sample, simulation_step=sample.simulation_step + offset,
                   publisher_sequence=sample.publisher_sequence + offset,
                   simulation_time_s=sample.simulation_time_s + offset * 0.002)


def test_release_scope_is_session_epoch_and_attempt_without_a_lease(tmp_path):
    value = make_adapter(tmp_path)
    assert not hasattr(value, "_collection_port")
    assert value._release_scope() == ("s", 1, "attempt-1")


def test_normal_stop_proof_needs_the_preceding_trajectory_result_and_confirmed_joint_stop(tmp_path):
    value, _ = release_adapter(tmp_path)
    proof = value._normal_stop_proof()
    assert proof["trajectory_result"] == "SUCCEEDED"
    assert proof["epoch"]["session_id"] == "s" and proof["epoch"]["reset_epoch"] == 1
    assert set(proof["joint_positions"]) == {*ARM, "6"} and set(proof["joint_velocities"]) == {*ARM, "6"}
    assert type(proof["stop_confirmed_wall_s"]) is float
    # same monotonic clock as the observer receipts: the joint-state receipt that confirmed the stop
    assert proof["stop_confirmed_wall_s"] == value._joint_state_received_monotonic_s
    assert proof["sim_stamp_s"] == value.observer.sample.simulation_time_s


@pytest.mark.parametrize("kwargs", [{"velocity": 0.01}, {"trajectory_result": None}, {"trajectory_result": "TIMED_OUT"}])
def test_normal_stop_proof_refuses_a_moving_arm_or_a_missing_or_unfinished_trajectory_result(tmp_path, kwargs):
    value, _ = release_adapter(tmp_path, **kwargs)
    value._execution_policy = {**value._execution_policy, "state_unavailable_stop_s": 0.05}
    with pytest.raises(RuntimeError, match="DYNAMIC_NORMAL_STOP_UNCONFIRMED"):
        value._normal_stop_proof()


def test_normal_stop_event_payload_carries_joint_positions_velocities_and_sim_stamp(tmp_path):
    value, _ = release_adapter(tmp_path)
    events = []
    value._publish_teacher_event = lambda kind, payload: events.append((kind, payload))
    value.final_stop_proof_enabled = True
    value._publish_final_normal_stop()
    kind, payload = events[0]
    assert kind == "normal_stop"
    proof = payload["proof"]
    assert proof["joint_positions"] and proof["joint_velocities"] and proof["sim_stamp_s"] is not None
    assert "stop_evidence" not in proof and "references" not in proof


def test_release_has_no_dispatch_guard_and_no_broker_permit(tmp_path):
    import so101_demo.ros.dynamic_mujoco_execution as module
    assert not hasattr(RosDynamicMujocoExecution, "_release_dispatch_guard")
    assert not hasattr(module, "_DISPATCH_PERMIT_MAX_S")


def test_first_source_after_stop_uses_the_stop_confirmed_time_on_the_receipt_clock(tmp_path):
    value, _ = release_adapter(tmp_path)
    proof = value._normal_stop_proof()
    source = value._first_source_after_stop(proof, previous_step=1000, previous_sequence=1000)
    assert source.simulation_step == 1001
    late = {**proof, "stop_confirmed_wall_s": value._now[0] + 5.0}
    value._selected_release_source = None
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE"):
        value._first_source_after_stop(late, previous_step=1000, previous_sequence=1000)


def test_supported_forward_release_runs_without_any_collection_port(tmp_path):
    value, commands = release_adapter(tmp_path)
    value._supported_release_preflight()
    value._attached = False
    value._open_supported_gripper(State.OPEN_GRIPPER)
    assert len(commands) == 1


def test_recover_open_gripper_opens_only_when_support_is_proved(tmp_path):
    value, commands = release_adapter(tmp_path, supported=True)
    value._open_supported_gripper(State.RECOVER_OPEN_GRIPPER)
    assert len(commands) == 1
    unsupported, commands = release_adapter(tmp_path, supported=False)
    with pytest.raises(RuntimeError, match="DYNAMIC_RELEASE_SUPPORT_NOT_PROVED"):
        unsupported._open_supported_gripper(State.RECOVER_OPEN_GRIPPER)
    assert commands == []


def test_recover_open_gripper_without_support_ends_in_error_through_the_runner(tmp_path):
    unsupported, commands = release_adapter(tmp_path, supported=False)
    unsupported._initial = evidence()
    result = unsupported.perform(State.RECOVER_OPEN_GRIPPER, None)
    assert result.status is ActionStatus.FAILED
    assert result.failure.code == "DYNAMIC_RELEASE_SUPPORT_NOT_PROVED" and commands == []
    from so101_demo.core.workflow import resolve_transition
    assert resolve_transition(State.RECOVER_OPEN_GRIPPER, result.status, result.failure) is State.ERROR


def test_teacher_execution_status_maps_the_new_stops(tmp_path):
    def status(code):
        return RosDynamicMujocoExecution._teacher_execution_status(
            SimpleNamespace(status=SimpleNamespace(value="ERROR"), failure=SimpleNamespace(code=code)),
            {"physical_action_proven_absent": False})
    assert status("TEACHER_USER_STOP") == "STOPPED_USER" and status("TEACHER_PARENT_DIED") == "STOPPED_USER"
    assert status("TEACHER_DEADLINE") == "DEADLINE"
    assert status("DYNAMIC_CUP_FORCE_EXCEEDED") == "STOPPED_SAFETY"
    assert status("DYNAMIC_CUP_COMPRESSION_EXCEEDED") == "STOPPED_SAFETY"
    assert status("DYNAMIC_COLLISION_STOP") == "STOPPED_SAFETY"
    assert status("DYNAMIC_STATE_UNAVAILABLE_STOP") == "STOPPED_SAFETY"
    assert status("TEACHER_CANCEL_UNSETTLED") == "INDETERMINATE"
    assert status("MOVEIT_EXECUTION_FAILED") == "FAILED"


# ---- C3(b): which close target the gripper uses -----------------------------------------------------------------

def test_c3_frozen_inputs_use_the_policy_close_target_and_the_plain_pick_place_keeps_the_original(tmp_path):
    value = make_adapter(tmp_path)
    assert value._close_target_q6() == -0.0485          # no frozen inputs: unchanged from main
    value._execution_snapshot_root = tmp_path           # frozen inputs
    value._execution_policy = load_teacher_execution_policy(TEACHER_POLICY)
    assert value._close_target_q6() == value._execution_policy["gripper_close_target_rad"]
    assert value._close_target_q6() == pytest.approx(-0.0476086, abs=1e-7)


def test_c3_frozen_inputs_without_the_policy_value_refuse(tmp_path):
    value = make_adapter(tmp_path)
    value._execution_snapshot_root = tmp_path
    value._execution_policy = None
    with pytest.raises(RuntimeError, match="TEACHER_POLICY_UNAVAILABLE"):
        value._close_target_q6()


# ---- C6: which MoveIt scaling each state plans with ---------------------------------------------------------------

def _planned_requests(tmp_path, state, *, frozen):
    value = make_adapter(tmp_path)
    value._template = SimpleNamespace(velocity_scaling=0.03, acceleration_scaling=0.03, planning_timeout_s=1.0,
                                      planning_group="arm", tcp_link="tcp")
    if frozen:
        value._execution_snapshot_root = tmp_path
        value._execution_policy = load_teacher_execution_policy(TEACHER_POLICY)
    seen = []

    class Planning:
        def plan_joint_path(self, request, timeout_s):
            seen.append(request)
            return SimpleNamespace(failure=SimpleNamespace(code="PLAN_REFUSED"), trajectory=None)

    value._planning = Planning()
    value._record_planning_attempt = lambda document: None
    with pytest.raises(RuntimeError, match="PLAN_REFUSED"):   # only the request MoveIt is asked for matters here
        value._plan_candidate_set(state=state, step=SimpleNamespace(waypoint=SimpleNamespace(segment_index=0)),
                                  current=(0.0,) * 5, joint_target=(0.1,) * 5)
    return seen


@pytest.mark.parametrize("state", [State.LIFT, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE])
def test_c6_the_frozen_carry_scaling_reaches_the_moveit_request_of_the_carry_states(tmp_path, state):
    request, = _planned_requests(tmp_path, state, frozen=True)
    assert (request.velocity_scaling, request.acceleration_scaling) == (0.03, 0.0075)


@pytest.mark.parametrize("state", [State.PREPARE_OPEN_GRIPPER, State.MOVE_ABOVE_OBJECT, State.DESCEND,
                                   State.MICRO_LIFT, State.RETREAT, State.RECOVER_RETREAT,
                                   State.RECOVER_LIFT_TO_SAFE_HEIGHT])
def test_c6_other_states_keep_the_template_scaling(tmp_path, state):
    request = _planned_requests(tmp_path, state, frozen=True)[0]
    assert (request.velocity_scaling, request.acceleration_scaling) == (0.03, 0.03)


@pytest.mark.parametrize("state", [State.LIFT, State.MOVE_ABOVE_PLACE, State.DESCEND_TO_PLACE])
def test_c6_without_frozen_inputs_the_carry_keeps_main_scaling(tmp_path, state):
    request, = _planned_requests(tmp_path, state, frozen=False)
    assert (request.velocity_scaling, request.acceleration_scaling) == (0.03, 0.03)


def test_c6_frozen_inputs_without_the_carry_values_refuse(tmp_path):
    value = make_adapter(tmp_path)
    value._execution_snapshot_root = tmp_path
    value._template = SimpleNamespace(velocity_scaling=0.03, acceleration_scaling=0.03)
    value._execution_policy = {"policy_sha256": "x"}
    with pytest.raises(RuntimeError, match="TEACHER_POLICY_UNAVAILABLE"):
        value._planning_scaling(State.MOVE_ABOVE_PLACE)


# ---- the place target is untouched without frozen inputs ---------------------------------------------------------------

def _pose(z=0.2176):
    from so101_demo.ports.evidence import PoseEvidence
    return PoseEvidence((-0.0737, -0.2325, z), (0.0, 0.0, 0.0, 1.0))


def test_r11_without_frozen_inputs_the_place_target_is_unchanged(tmp_path):
    value = make_adapter(tmp_path)
    original = _pose()
    assert value._place_target(State.DESCEND_TO_PLACE, original) is original
