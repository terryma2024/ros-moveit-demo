"""The rollout episode state machine, driven through fake ports (no ROS graph, no policy, no GPU)."""

import copy

import pytest

from so101_demo.act.policy import ActPolicyRunner
from so101_demo.act.rollout_episode import RolloutSettings, run_episode
from so101_demo.act.rollout_targets import rollout_targets
from so101_demo.act.teacher_endpoint import load_teacher_endpoint_policy

from test_act_rollout_targets import SNAPSHOT_TARGETS

SETTINGS = RolloutSettings(execution_deadline_s=3.0, state_unavailable_stop_s=1.0, settle_s=0.5,
                           no_motion_threshold_rad=0.01, stop_wait_s=1.0, ready_wait_s=2.0)
SCENE = {"scene_id": "rollout-standard-right", "group": "rollout_standard", "xy": [0.07, -0.28],
         "cup_position_world_m": [0.07, -0.28, 0.165], "seed": None, "nearest_training_m": 0.05}
START_POSE = tuple(SCENE["cup_position_world_m"])
UPRIGHT = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}


def _endpoint_policy():
    return load_teacher_endpoint_policy(b"""kind: ACT_TEACHER_ENDPOINT_POLICY
schema_version: 1
rule_version: teacher_endpoint
tolerances: {initial_position_m: 0.010, initial_axis_rad: 0.15, final_xy_m: 0.020, final_z_m: 0.010,
  final_axis_rad: 0.15, settle_s: 0.5}
""")


class Clock:
    def __init__(self):
        self.sim, self.wall = 1.0, 100.0


class Model:
    def reset(self):
        pass

    def infer(self, observation):
        raise AssertionError("the chunk is computed behind the inference boundary, never by the runner")


class Inference:
    """One in-flight request; each request follows the next scripted behaviour ("ok", "stale", "timeout")."""

    def __init__(self, clock, script=(), polls_before_reply=2):
        self.clock, self.script, self.delay = clock, list(script), polls_before_reply
        self.pending, self.submitted, self.abandoned, self.waited = None, [], 0, 0

    def submit(self, observation, *, sequence):
        if self.pending is not None:
            raise ValueError("INFERENCE_REQUEST_IN_FLIGHT")
        behaviour = self.script.pop(0) if self.script else "ok"
        self.pending = {"sequence": sequence, "behaviour": behaviour, "observation": observation}
        self.submitted.append(sequence)
        self.waited = 0

    def poll(self):
        self.waited += 1
        if self.waited <= self.delay:
            return {}
        request = self.pending
        if request["behaviour"] == "stale":
            raise ValueError("INFERENCE_REPLY_STALE")
        if request["behaviour"] == "timeout":
            raise ValueError("INFERENCE_TIMEOUT")
        if request["behaviour"] == "garbage":
            raise ValueError("INFERENCE_REPLY_INVALID")
        self.pending = None
        state = request["observation"]["state"]
        step = 0.05 if request["behaviour"] == "ok" else 0.0
        chunk = tuple(tuple(value + step * (row + 1) for value in state[:6]) for row in range(10))
        return {"sequence": request["sequence"], "actions": chunk, "age_s": 0.05}

    def abandon(self):
        self.pending = None
        self.abandoned += 1


class Recorder:
    def __init__(self, ports, fail_finish=False):
        self.ports, self.fail_finish = ports, fail_finish

    def finish(self):
        self.ports.calls.append("recorder.finish")
        if self.fail_finish:
            raise RuntimeError("bag did not close")
        return {"ready": True, "failure": None}


class Session:
    def __init__(self, ports, clock, *, moves=True, places=True, stale_after=None, stop_confirms=True,
                 submit_error=None, state0=(0.0, 0.1, -0.2, 0.3, 0.0, 0.5, 0.0, 1.0), ready_after_spins=0,
                 pose_after_spins=0, observe_error=None, observe_error_after=None, stop_error=None,
                 sim_time_error_after=None):
        self.ready_after_spins, self.pose_after_spins, self.spins = ready_after_spins, pose_after_spins, 0
        self.observe_error, self.observe_error_after, self.stop_error = observe_error, observe_error_after, stop_error
        self.sim_time_error_after, self.observations = sim_time_error_after, 0
        self.ports, self.clock = ports, clock
        self.moves, self.places, self.stale_after, self.stop_confirms = moves, places, stale_after, stop_confirms
        self.submit_error, self.state = submit_error, list(state0)
        self.next_observation, self.prefixes, self.stops, self.closed = clock.sim, [], [], False
        self.state_value = "READY"

    def begin(self, session_id, attempt_id):
        self.ports.calls.append("session.begin")

    def ready(self):
        return self.spins >= self.ready_after_spins

    def sim_time(self):
        if self.sim_time_error_after is not None and self.clock.sim >= self.sim_time_error_after:
            raise RuntimeError("ROLLOUT_SIM_CLOCK_UNAVAILABLE")
        if not self.ready():
            raise RuntimeError("ROLLOUT_SIM_CLOCK_UNAVAILABLE")
        return self.clock.sim

    def spin(self):
        self.spins += 1
        self.clock.sim += 0.02
        self.clock.wall += 0.02

    def observe(self):
        if self.observe_error is not None and self.observations >= self.observe_error_after:
            raise self.observe_error
        if self.clock.sim < self.next_observation:
            return None
        self.observations += 1
        self.next_observation += 0.1
        if self.stale_after is not None and self.clock.sim >= self.stale_after:
            return None
        observation = {"sim_time_s": round(self.clock.sim, 6), "state": list(self.state),
                       "head": "H", "wrist": "W"}
        audit = {"stamps": {"head": self.clock.sim, "wrist": self.clock.sim}, "head_sha256": "a" * 64,
                 "wrist_sha256": "b" * 64}
        return observation, audit

    def submit_prefix(self, prefix):
        if self.submit_error is not None:
            raise self.submit_error
        self.prefixes.append(prefix)
        if self.moves:
            self.state[:6] = list(prefix["positions"][-1])
        self.state_value = "EXECUTING"
        return "goal-%d" % len(self.prefixes)

    def stop(self, reason):
        self.stops.append(reason)
        if self.stop_error is not None:
            raise self.stop_error
        self.state_value = "STOPPED" if self.stop_confirms else "STOPPING"
        return self.state_value

    def stop_confirmed(self):
        return self.state_value == "STOPPED"

    def cup_pose(self):
        if self.spins < self.pose_after_spins:
            return None
        position = START_POSE
        if self.places and self.prefixes:
            position = tuple(SNAPSHOT_TARGETS["final_target"][:2]) + (START_POSE[2],)
        return {"position": list(position), "orientation": dict(UPRIGHT),
                "simulation_time_s": round(self.clock.sim, 6), "frame_id": "world", "object_id": "plastic_cup",
                "session_id": "sim-1", "reset_epoch": 1}

    def close(self):
        self.closed = True
        self.ports.calls.append("session.close")


class Ports:
    def __init__(self, *, script=(), gate_error=None, recorder_error=None, resume_ok=True, fail_finish=False,
                 confirm_goals=True, session_kwargs=None, bundle_prefix=1):
        self.clock = Clock()
        self.calls, self.gate_error, self.recorder_error = [], gate_error, recorder_error
        self.resume_ok, self.fail_finish, self.confirm_goals = resume_ok, fail_finish, confirm_goals
        self.session_kwargs = session_kwargs or {}
        self.inference = Inference(self.clock, script)
        bundle = {"action": {"chunk_size": 10, "execution_prefix": bundle_prefix, "temporal_ensembling": False,
                             "tail_padding_mask": True}}
        self.runner = ActPolicyRunner(bundle, Model())
        self.session = None

    def monotonic(self):
        return self.clock.wall

    def reset(self, scene):
        self.calls.append("reset")
        return {"reset_epoch": 1, "simulation_session_id": "sim-1", "simulation_time_s": self.clock.sim}

    def initial_gate(self, scene, receipt):
        self.calls.append("initial_gate")
        if self.gate_error is not None:
            raise self.gate_error
        return {"canonical_joints": True, "worker_nodes": "exact"}

    def resume_physics(self, receipt):
        self.calls.append("resume_physics")
        return self.resume_ok

    def start_recorder(self, scene):
        self.calls.append("start_recorder")
        if self.recorder_error is not None:
            raise self.recorder_error
        return Recorder(self, self.fail_finish)

    def open_session(self, scene, receipt, attempt_id):
        self.calls.append("open_session")
        self.session = Session(self, self.clock, **self.session_kwargs)
        return self.session

    def cancel_motion(self):
        self.calls.append("cancel_motion")
        return True

    def confirm_no_controller_goal(self):
        self.calls.append("confirm_no_controller_goal")
        return self.confirm_goals


class Sink:
    def __init__(self):
        self.steps, self.world_rows, self.events = [], [], []

    def step(self, row):
        self.steps.append(row)

    def world(self, row):
        self.world_rows.append(row)

    def event(self, row):
        self.events.append(row)


def _run(ports, sink=None, settings=SETTINGS):
    return run_episode(scene=SCENE, attempt_id="attempt-1", ports=ports, settings=settings,
                       snapshot_targets=SNAPSHOT_TARGETS, endpoint_policy=_endpoint_policy(), sink=sink)


def test_a_policy_that_places_the_cup_is_done_and_the_nodes_follow_the_gate():
    ports = Ports()
    sink = Sink()
    result = _run(ports, sink)
    assert (result["verdict"], result["done"], result["reason"]) == ("DONE", True, None)
    assert result["status"] == "COMPLETED" and result["stop"]["confirmed"] is True
    assert result["endpoint"]["result"] == "PASS"
    order = [call for call in ports.calls if call in {
        "reset", "initial_gate", "resume_physics", "start_recorder", "open_session", "session.begin",
        "recorder.finish", "session.close", "cancel_motion", "confirm_no_controller_goal"}]
    assert order[:5] == ["reset", "initial_gate", "resume_physics", "start_recorder", "open_session"]
    assert order[-4:] == ["recorder.finish", "session.close", "cancel_motion", "confirm_no_controller_goal"]
    assert result["counts"]["applied"] > 5 and result["counts"]["late_replies"] == 0
    assert len(sink.steps) >= result["counts"]["observations"] and sink.world_rows
    assert result["substitutions"]["start_target"] == "commanded_reset_pose"
    assert ports.inference.pending is None                      # a request left in flight is abandoned, not carried over


def test_the_applied_prefix_is_a_valid_prefix_of_the_observation():
    ports = Ports()
    _run(ports)
    prefix = ports.session.prefixes[0]
    assert prefix["session_id"] == "sim-1" and prefix["attempt_id"] == "attempt-1" and prefix["sequence"] == 0
    assert prefix["target_times_s"] == pytest.approx((prefix["observation_time_s"] + 0.1,))


def test_a_late_reply_sends_nothing_and_is_counted():
    ports = Ports(script=["stale", "timeout", "ok"])
    sink = Sink()
    result = _run(ports, sink)
    assert result["counts"]["late_replies"] == 2 and ports.inference.abandoned == 2
    assert result["verdict"] == "DONE"
    sequences = [row["sequence"] for row in sink.steps if row.get("applied")]
    assert 0 not in sequences and 1 not in sequences and sequences          # the two late chunks were never applied
    late_rows = [row for row in sink.steps if row.get("late")]
    assert [row["sequence"] for row in late_rows] == [0, 1]


def test_a_prefix_that_is_late_at_submission_holds_the_previous_goal():
    ports = Ports(session_kwargs={"submit_error": ValueError("PREFIX_LATE")})
    result = _run(ports)
    assert result["counts"]["prefix_late"] > 0 and result["counts"]["applied"] == 0
    assert result["verdict"] == "NO_MOTION" and ports.session.stops          # nothing was ever sent


def test_a_joint_limit_refusal_is_counted_and_the_loop_goes_on():
    ports = Ports(session_kwargs={"submit_error": ValueError("JOINT_LIMIT_INVALID")})
    result = _run(ports)
    assert result["counts"]["limit_refused"] > 0 and result["verdict"] == "NO_MOTION"


def test_no_fresh_observation_for_the_frozen_bound_aborts_with_a_safety_stop():
    ports = Ports(session_kwargs={"stale_after": 1.8})
    result = _run(ports)
    assert result["status"] == "STOPPED_SAFETY" and result["verdict"] == "INVALID"
    assert result["reason"] == "OBSERVATION_STALE" and result["done"] is False
    assert ports.session.stops == ["STOPPED_SAFETY"]
    # the abort came at about the frozen bound after the last fresh observation, well before the horizon
    assert result["timing"]["loop_sim_s"] < SETTINGS.execution_deadline_s
    assert result["stop"]["confirmed"] is True and "recorder.finish" in ports.calls


def test_a_stop_that_is_not_confirmed_makes_the_episode_invalid_and_is_not_judged():
    ports = Ports(session_kwargs={"stop_confirms": False})
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["reason"] == "STOP_UNCONFIRMED"
    assert result["stop"]["confirmed"] is False and result["done"] is False
    assert result["endpoint"] is None


def test_a_policy_that_never_moves_is_no_motion_and_not_a_failure():
    ports = Ports(session_kwargs={"moves": False, "places": False})
    result = _run(ports)
    assert result["verdict"] == "NO_MOTION" and result["done"] is False
    assert result["status"] == "COMPLETED" and result["motion"]["max_arm_displacement_rad"] < 0.01
    assert result["endpoint"]["result"] == "FAIL"                              # still judged, and reported with the reason


def test_a_moving_policy_that_leaves_the_cup_fails():
    ports = Ports(session_kwargs={"places": False})
    result = _run(ports)
    assert result["verdict"] == "FAILED" and result["done"] is False
    assert "FINAL_XY_OUT_OF_TOLERANCE" in result["reason"]
    assert result["motion"]["max_arm_displacement_rad"] > 0.01


def test_a_gate_failure_is_invalid_and_no_node_or_recorder_is_created():
    ports = Ports(gate_error=RuntimeError("POINT_INITIAL_GATE_OBSERVATION_REJECTED:worker_nodes"))
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["reason"].startswith("GATE_FAILED")
    assert "open_session" not in ports.calls and "start_recorder" not in ports.calls
    assert "resume_physics" not in ports.calls
    assert ports.calls[-2:] == ["cancel_motion", "confirm_no_controller_goal"]


def test_a_recorder_that_does_not_start_is_invalid_and_no_node_is_created():
    ports = Ports(recorder_error=RuntimeError("RAW_PILOT_READY_TIMEOUT"))
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["reason"].startswith("RECORDER_FAILED")
    assert "open_session" not in ports.calls and ports.inference.submitted == []


def test_a_resume_that_fails_is_invalid():
    result = _run(Ports(resume_ok=False))
    assert result["verdict"] == "INVALID" and result["reason"] == "RESUME_FAILED"


def test_a_controller_pair_failure_is_a_fault_not_a_policy_failure():
    ports = Ports(session_kwargs={"submit_error": RuntimeError("CONTROLLER_PAIR_FAILED: goal rejected")})
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["reason"].startswith("CONTROLLER_PAIR_FAILED")
    assert ports.session.stops


def test_a_reply_the_runner_refuses_is_a_fault():
    ports = Ports(script=["garbage"])
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["reason"].startswith("INFERENCE_FAILED")


def test_retirement_runs_on_every_path_and_a_failed_recorder_close_is_reported():
    for ports in (Ports(), Ports(session_kwargs={"stale_after": 1.8}), Ports(gate_error=RuntimeError("x"))):
        _run(ports)
        assert ports.calls[-2:] == ["cancel_motion", "confirm_no_controller_goal"]
    ports = Ports(fail_finish=True)
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["reason"].startswith("RECORDER_FAILED")
    assert "session.close" in ports.calls
    ports = Ports(confirm_goals=False)
    assert _run(ports)["reason"] == "RETIRE_UNCONFIRMED"


def test_the_horizon_ends_the_loop_at_the_frozen_deadline():
    ports = Ports()
    result = _run(ports)
    assert result["timing"]["loop_sim_s"] == pytest.approx(SETTINGS.execution_deadline_s, abs=0.1)
    assert result["timing"]["wall_s"] > 0


def test_the_neck_is_never_commanded_and_its_drift_is_logged():
    ports = Ports()
    result = _run(ports)
    assert all(len(prefix["positions"][0]) == 6 for prefix in ports.session.prefixes)
    assert result["motion"]["neck_deviation_max"] == 0.0


def test_settings_are_validated():
    for field in ("execution_deadline_s", "state_unavailable_stop_s", "settle_s", "no_motion_threshold_rad", "stop_wait_s",
                  "ready_wait_s"):
        kwargs = dict(execution_deadline_s=3.0, state_unavailable_stop_s=1.0, settle_s=0.5,
                      no_motion_threshold_rad=0.01, stop_wait_s=1.0, ready_wait_s=2.0)
        kwargs[field] = float("nan")
        with pytest.raises(ValueError, match="ROLLOUT_SETTINGS_INVALID"):
            RolloutSettings(**kwargs)


def test_targets_are_unchanged_by_a_run():
    before = copy.deepcopy(SNAPSHOT_TARGETS)
    _run(Ports())
    assert SNAPSHOT_TARGETS == before and rollout_targets(before, cup_position_world_m=START_POSE)


# ---- hardening (CP-3743): catch-all fault handling and the wait for the first inputs -------------------------------------


def test_an_unexpected_error_in_the_loop_is_an_invalid_episode_and_the_stop_is_proven():
    ports = Ports(session_kwargs={"observe_error": KeyError("camera ring vanished"), "observe_error_after": 3})
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["done"] is False
    assert result["reason"].startswith("EPISODE_FAULT: KeyError") and "camera ring vanished" in result["reason"]
    assert result["status"] == "FAULT" and result["stop"]["confirmed"] is True and result["stop"]["after_fault"] is True
    assert ports.session.stops == ["ROLLOUT_FAULT"] and ports.session.closed
    assert ports.calls[-2:] == ["cancel_motion", "confirm_no_controller_goal"]
    assert "session.close" in ports.calls and "recorder.finish" in ports.calls
    assert result["endpoint"] is None                       # a faulted run is never judged


def test_a_fault_whose_stop_cannot_be_issued_says_so_in_the_reason():
    ports = Ports(session_kwargs={"observe_error": ValueError("boom"), "observe_error_after": 2,
                                  "stop_error": RuntimeError("controller port gone")})
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["stop"]["confirmed"] is False
    assert "controller port gone" in result["stop"]["error"]
    assert result["reason"].startswith("EPISODE_FAULT: ValueError") and result["reason"].endswith("STOP_UNCONFIRMED")
    assert ports.calls[-2:] == ["cancel_motion", "confirm_no_controller_goal"]


def test_a_fault_with_an_unconfirmed_stop_ack_says_so_in_the_reason():
    ports = Ports(session_kwargs={"observe_error": ValueError("boom"), "observe_error_after": 2, "stop_confirms": False})
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["stop"]["confirmed"] is False
    assert result["reason"].endswith("STOP_UNCONFIRMED")


def test_a_clock_that_fails_while_the_loop_is_closing_does_not_hide_the_first_error():
    ports = Ports(session_kwargs={"observe_error": KeyError("first"), "observe_error_after": 2,
                                  "sim_time_error_after": 1.2})
    result = _run(ports)
    assert result["verdict"] == "INVALID" and "first" in result["reason"]
    assert "session.close" in ports.calls and ports.calls[-2:] == ["cancel_motion", "confirm_no_controller_goal"]


def test_the_loop_waits_for_the_first_joint_state_and_the_cup_pose_before_it_starts():
    ports = Ports(session_kwargs={"ready_after_spins": 12, "pose_after_spins": 20})
    sink = Sink()
    result = _run(ports, sink)
    assert result["verdict"] == "DONE" and result["phases"].count("nodes") == 1
    assert result["timing"]["loop_start_sim_s"] >= 1.0 + 20 * 0.02 - 1e-9      # the loop began after both inputs existed
    assert result["timing"]["loop_sim_s"] == pytest.approx(SETTINGS.execution_deadline_s, abs=0.1)
    assert result["counts"]["observations"] > 5


def test_a_session_that_never_gets_a_joint_state_is_refused_in_bounded_time():
    ports = Ports(session_kwargs={"ready_after_spins": 10**9})
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["reason"].startswith("SESSION_NOT_READY: joint_state")
    assert result["counts"]["inferences"] == 0 and ports.inference.submitted == []
    assert result["timing"]["wall_s"] <= SETTINGS.ready_wait_s + 0.5
    assert "session.close" in ports.calls and ports.calls[-2:] == ["cancel_motion", "confirm_no_controller_goal"]


def test_a_session_that_never_sees_the_cup_is_refused_in_bounded_time():
    ports = Ports(session_kwargs={"pose_after_spins": 10**9})
    result = _run(ports)
    assert result["verdict"] == "INVALID" and result["reason"].startswith("SESSION_NOT_READY: cup_pose")
    assert result["counts"]["inferences"] == 0
    assert result["timing"]["wall_s"] <= SETTINGS.ready_wait_s + 0.5


def test_a_fault_keeps_the_trace_of_its_cause():
    ports = Ports(gate_error=RuntimeError("deep cause"))
    result = _run(ports)
    assert result["verdict"] == "INVALID" and "deep cause" in result["fault_trace"] and "GATE_FAILED" in result["fault_trace"]


def test_an_unconfirmed_stop_carries_the_sessions_diagnostics(monkeypatch):
    monkeypatch.setattr(Session, "stop_diagnostics", lambda self: {"arm": {"max_abs_velocity_rad_s": 0.01}}, raising=False)
    result = _run(Ports(session_kwargs={"stop_confirms": False}))
    assert result["reason"].startswith("STOP_UNCONFIRMED")
    assert result["stop"]["diagnostics"]["arm"]["max_abs_velocity_rad_s"] == 0.01
