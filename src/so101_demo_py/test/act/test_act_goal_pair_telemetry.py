"""Goal-pair acceptance telemetry (T0a): recorded per pair, summarised per episode, and never a change of behaviour."""

import json
import threading
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from so101_demo.act.execution import ActExecutionAdapter, prefix_sha256
from so101_demo.act.goal_pair_telemetry import LoadSampler, latency_stats, percentile, summarize_goal_pairs

from test_act_rollout_episode import Ports, Session, Sink, _run


class Clock:
    def __init__(self):
        self.sim, self.wall = 1.0, 10.0

    def progress(self):
        self.sim += 0.005
        self.wall += 0.005


class PlainPort:
    """A port with no telemetry methods at all (what every existing fixture uses)."""

    def __init__(self, accepted=True):
        self.accept, self.goals, self.cancels, self.stationary = accepted, [], [], True

    def send(self, goal):
        self.goals.append(goal)
        return str(len(self.goals))

    def accepted(self, goal_id):
        return self.accept

    def cancel(self, goal_id):
        self.cancels.append(goal_id)

    def stopped(self):
        return bool(self.cancels) and self.stationary


class TimedPort(PlainPort):
    """The acceptance arrives on a thread at `accept_at` (wall); the port records it the way RosControllerPort does."""

    def __init__(self, clock, accept_at=None, thread="act-rollout-spin"):
        super().__init__(accepted=None)
        self.clock, self.accept_at, self.thread, self.sent_at = clock, accept_at, thread, {}
        self.in_flight = 2

    def send(self, goal):
        gid = super().send(goal)
        self.sent_at[gid] = self.clock.wall
        return gid

    def _arrived(self):
        return self.accept_at is not None and self.clock.wall >= self.accept_at

    def accepted(self, goal_id):
        return True if self._arrived() else None

    def goal_timing(self, goal_id):
        arrived = self._arrived()
        return {"send_wall_s": self.sent_at[goal_id], "accept_wall_s": self.accept_at if arrived else None,
                "accept_thread": self.thread if arrived else None}

    def unfinished_goals(self):
        return self.in_flight


class Permits:
    def __init__(self):
        self.revoked = False

    def require(self, permit, prefix):
        if self.revoked or permit.get("prefix_sha256") != prefix_sha256(prefix):
            raise PermissionError("PERMIT_INVALID")

    def revoke(self, reason):
        self.revoked = True


def prefix(sequence=0):
    return dict(session_id="s", attempt_id="a", sequence=sequence, observation_time_s=1., target_times_s=(1.1, 1.2),
                positions=((.01,) * 6, (.02,) * 6))


def build(arm, grip, clock, sampler=None):
    adapter = ActExecutionAdapter(arm, grip, permit_port=Permits(), sim_clock=lambda: clock.sim,
                                  monotonic=lambda: clock.wall, progress=clock.progress, submit_lead_s=.03,
                                  accept_timeout_s=.02, stop_timeout_s=.03, reference_port=lambda t: (0.,) * 6,
                                  **({} if sampler is None else {"load_sampler": sampler}))
    adapter.begin_attempt("s", "a")
    return adapter


def submit(adapter, p=None):
    p = p or prefix()
    return adapter.submit(p, dict(prefix_sha256=prefix_sha256(p)))


class FakeLoad:
    def __init__(self):
        self.calls = 0

    def sample(self):
        self.calls += 1
        return {"cpu_process_s": 1.5, "cpu_delta_s": 0.25, "cpu_delta_wall_s": 1.0, "loadavg": [1.0, 2.0, 3.0],
                "sample_age_s": 0.0}


def test_an_accepted_pair_records_the_timing_fields():
    clock = Clock()
    arm, grip = TimedPort(clock, accept_at=10.004), TimedPort(clock, accept_at=10.011, thread="MainThread")
    adapter = build(arm, grip, clock, FakeLoad())
    assert submit(adapter) == "1:1"
    pair = adapter.last_pair
    assert pair["sequence"] == 0 and pair["outcome"] == "accepted" and pair["late_controller"] is None
    assert pair["target_start_sim_s"] == pytest.approx(1.03) and pair["send_sim_s"] == pytest.approx(1.0)
    assert pair["send_wall_s"] == {"arm": 10.0, "gripper": 10.0}
    assert pair["accept_wall_s"] == {"arm": 10.004, "gripper": 10.011}
    assert pair["accept_latency_s"]["arm"] == pytest.approx(0.004)
    assert pair["accept_latency_s"]["gripper"] == pytest.approx(0.011)
    assert pair["accept_thread"] == {"arm": "act-rollout-spin", "gripper": "MainThread"}
    assert pair["in_flight_at_check"] == {"arm": 2, "gripper": 2}
    assert pair["load"]["loadavg"] == [1.0, 2.0, 3.0] and pair["load"]["cpu_delta_s"] == 0.25
    assert pair["check_sim_s"] == pytest.approx(clock.sim) and pair["accept_sim_s"] == pair["check_sim_s"]
    assert pair["decision_thread"] == threading.current_thread().name
    assert adapter.pair_log == [pair]
    json.dumps(pair)                      # the sub-object goes into a jsonl row


def test_a_timeout_pair_names_the_late_controller_and_keeps_the_error_and_the_time():
    base_clock = Clock()
    base = build(PlainPort(True), PlainPort(None), base_clock)
    with pytest.raises(RuntimeError) as base_error:
        submit(base)
    clock = Clock()
    arm, grip = TimedPort(clock, accept_at=10.003), TimedPort(clock, accept_at=10.05)
    adapter = build(arm, grip, clock, FakeLoad())
    with pytest.raises(RuntimeError) as error:
        submit(adapter)
    assert str(error.value) == str(base_error.value) and "goal response timeout" in str(error.value)
    assert clock.wall == pytest.approx(base_clock.wall) and clock.sim == pytest.approx(base_clock.sim)
    assert arm.cancels == grip.cancels == base.arm.cancels == ["1"] and adapter.state == base.state == "STOPPED"
    assert len(arm.goals) == len(grip.goals) == 1
    pair = adapter.last_pair
    assert pair["outcome"] == "timeout" and pair["late_controller"] == "gripper"
    assert pair["accept_wall_s"]["gripper"] is None and pair["accept_wall_s"]["arm"] == 10.003
    assert pair["check_wall_s"] >= 10.02 and pair["load"]["loadavg"] == [1.0, 2.0, 3.0]
    assert pair["load"]["cpu_process_s"] == 1.5


def test_both_controllers_late_and_a_rejection_are_named():
    clock = Clock()
    adapter = build(TimedPort(clock), TimedPort(clock), clock)
    with pytest.raises(RuntimeError):
        submit(adapter)
    assert adapter.last_pair["late_controller"] == "both"
    clock = Clock()
    adapter = build(PlainPort(True), PlainPort(False), clock)
    with pytest.raises(RuntimeError, match="goal rejected"):
        submit(adapter)
    assert adapter.last_pair["outcome"] == "rejected" and adapter.last_pair["late_controller"] == "gripper"


def test_an_acceptance_after_the_common_start_is_recorded_and_still_raises():
    clock = Clock()
    clock.progress = lambda: setattr(clock, "sim", clock.sim + 0.05)   # the simulation passes the common start
    adapter = build(TimedPort(clock, accept_at=10.001), TimedPort(clock), clock)
    with pytest.raises(RuntimeError, match="acceptance after common start"):
        submit(adapter)
    assert adapter.last_pair["outcome"] == "after_common_start"
    assert adapter.last_pair["check_wall_s"] is not None and adapter.last_pair["check_wall_s"] >= adapter.last_pair["sent_done_wall_s"]


def test_a_port_without_telemetry_gives_none_not_an_error_and_the_old_result():
    clock = Clock()
    adapter = build(PlainPort(True), PlainPort(True), clock)
    assert submit(adapter) == "1:1"
    pair = adapter.last_pair
    assert pair["outcome"] == "accepted" and pair["send_wall_s"] == {"arm": None, "gripper": None}
    assert pair["accept_latency_s"] == {"arm": None, "gripper": None}


def test_a_telemetry_failure_never_changes_the_submission():
    clock = Clock()

    class Broken(TimedPort):
        def goal_timing(self, goal_id):
            raise RuntimeError("telemetry broke")

        def unfinished_goals(self):
            raise RuntimeError("telemetry broke")

    class BrokenLoad:
        def sample(self):
            raise OSError("no loadavg")

    adapter = build(Broken(clock, accept_at=10.0), Broken(clock, accept_at=10.0), clock, BrokenLoad())
    assert submit(adapter) == "1:1" and adapter.state == "EXECUTING"


def test_the_summary_reports_late_arrivals_after_the_abort():
    clock = Clock()
    arm, grip = TimedPort(clock, accept_at=10.002), TimedPort(clock, accept_at=10.031)
    adapter = build(arm, grip, clock)
    with pytest.raises(RuntimeError):
        submit(adapter)
    clock.wall = 10.2                         # the passive part: the callback fires after the abort
    summary = adapter.goal_response_summary()
    assert summary["pairs"] == 1 and summary["timeouts"] == 1 and summary["accept_timeout_s"] == 0.02
    assert summary["late_arrivals"] == [{"sequence": 0, "controller": "gripper", "latency_s": pytest.approx(0.031),
                                         "accept_thread": "act-rollout-spin"}]
    assert summary["late_arrival_latencies_s"] == [pytest.approx(0.031)]
    assert summary["late_arrivals_unresolved"] == 0
    assert summary["accept_latency_s"]["gripper"]["n"] == 1
    assert summary["accept_latency_s"]["arm"]["max"] == pytest.approx(0.002)


def test_an_unresolved_late_arrival_is_counted():
    clock = Clock()
    adapter = build(TimedPort(clock, accept_at=10.002), TimedPort(clock), clock)
    with pytest.raises(RuntimeError):
        submit(adapter)
    summary = adapter.goal_response_summary()
    assert summary["timeouts"] == 1 and summary["late_arrivals"] == [] and summary["late_arrivals_unresolved"] == 1


def test_percentiles_use_linear_interpolation():
    values = [5.0, 1.0, 3.0, 2.0, 4.0]
    assert percentile(sorted(values), 50) == 3.0 and percentile(sorted(values), 95) == pytest.approx(4.8)
    assert percentile(sorted(values), 99) == pytest.approx(4.96) and percentile([7.0], 99) == 7.0
    stats = latency_stats(values)
    assert stats == {"n": 5, "p50": 3.0, "p95": pytest.approx(4.8), "p99": pytest.approx(4.96), "max": 5.0}
    assert latency_stats([]) == {"n": 0, "p50": None, "p95": None, "p99": None, "max": None}


def test_the_summary_maths_over_several_pairs():
    pairs = [
        {"sequence": i, "outcome": "accepted", "accept_latency_s": {"arm": 0.001 * (i + 1), "gripper": 0.002 * (i + 1)}}
        for i in range(4)]
    pairs.append({"sequence": 4, "outcome": "timeout", "late_controller": "arm",
                  "accept_latency_s": {"arm": 0.05, "gripper": 0.004}, "late_arrival_latency_s": {"arm": 0.05},
                  "accept_thread": {"arm": "act-rollout-spin", "gripper": "x"}})
    pairs.append({"sequence": 5, "outcome": "rejected", "accept_latency_s": {"arm": None, "gripper": None}})
    summary = summarize_goal_pairs(pairs, accept_timeout_s=0.02)
    assert summary["pairs"] == 6 and summary["timeouts"] == 1 and summary["rejected"] == 1
    assert summary["accept_latency_s"]["arm"] == latency_stats([0.001, 0.002, 0.003, 0.004, 0.05])
    assert summary["accept_latency_s"]["gripper"] == latency_stats([0.002, 0.004, 0.006, 0.008, 0.004])
    assert summary["late_arrival_latencies_s"] == [0.05]
    assert summary["accept_latency_s"]["arm"]["max"] == 0.05


def test_the_load_sample_is_taken_at_most_once_per_second():
    now = {"t": 100.0, "cpu": 5.0}
    loads = []

    def load():
        loads.append(1)
        return (0.5, 0.6, 0.7)

    sampler = LoadSampler(clock=lambda: now["t"], cpu=lambda: now["cpu"], load=load)
    first = sampler.sample()
    now["t"], now["cpu"] = 100.4, 5.2
    again = sampler.sample()
    assert len(loads) == 1 and again["cpu_process_s"] == first["cpu_process_s"] == 5.0
    assert again["sample_age_s"] == pytest.approx(0.4)
    now["t"], now["cpu"] = 101.2, 6.1
    fresh = sampler.sample()
    assert len(loads) == 2 and fresh["cpu_process_s"] == 6.1 and fresh["cpu_delta_s"] == pytest.approx(1.1)
    assert fresh["cpu_delta_wall_s"] == pytest.approx(1.2) and fresh["loadavg"] == [0.5, 0.6, 0.7]


def test_the_real_port_records_send_accept_and_the_delivering_thread():
    pytest.importorskip("control_msgs")        # the test venv has no ROS; this one runs where ROS is sourced
    response = Future()
    now = {"t": 10.0}
    client = SimpleNamespace(send_goal_async=lambda message: response)
    node = SimpleNamespace(create_subscription=lambda *args: None)
    from so101_demo.adapters.act.ros_execution import RosControllerPort

    port = RosControllerPort(node, client, ("6",), stop_velocity_rad_s=.001, max_age_s=.2, monotonic=lambda: now["t"])
    gid = port.send(dict(joint_names=("6",), header_stamp_s=1.1, time_from_start_s=(0., .1), positions=((.1,), (.2,))))
    assert port.goal_timing(gid) == {"send_wall_s": 10.0, "accept_wall_s": None, "accept_thread": None}
    assert port.unfinished_goals() == 1

    def deliver():
        now["t"] = 10.031
        response.set_result(SimpleNamespace(accepted=True, get_result_async=lambda: Future()))

    thread = threading.Thread(target=deliver, name="act-rollout-spin")
    thread.start()
    thread.join()
    assert port.goal_timing(gid) == {"send_wall_s": 10.0, "accept_wall_s": 10.031, "accept_thread": "act-rollout-spin"}
    assert port.accepted(gid) is True


class TelemetrySession(Session):
    pair = {"sequence": 0, "outcome": "accepted"}
    summary = {"pairs": 1, "timeouts": 0}

    def goal_pair(self):
        return dict(self.pair)

    def goal_response_summary(self):
        return dict(self.summary)


def _open_with(session_class):
    def open_session(self, scene, receipt, attempt_id):
        self.calls.append("open_session")
        self.session = session_class(self, self.clock, **self.session_kwargs)
        return self.session
    return open_session


def test_the_step_row_carries_the_pair_and_the_episode_carries_the_summary(monkeypatch):
    ports = Ports()
    monkeypatch.setattr(Ports, "open_session", _open_with(TelemetrySession))
    sink = Sink()
    result = _run(ports, sink)
    applied = [row for row in sink.steps if row.get("applied")]
    assert applied and all(row["goal_pair"] == TelemetrySession.pair for row in applied)
    assert result["goal_response"] == TelemetrySession.summary


def test_the_verdict_and_rows_are_the_same_with_or_without_telemetry(monkeypatch):
    plain_sink = Sink()
    plain = _run(Ports(), plain_sink)
    monkeypatch.setattr(Ports, "open_session", _open_with(TelemetrySession))
    sink = Sink()
    result = _run(Ports(), sink)
    assert "goal_response" not in plain and all("goal_pair" not in row for row in plain_sink.steps)
    for key in ("verdict", "reason", "done", "status", "counts", "phases", "stop"):
        assert result[key] == plain[key]
    stripped = [{k: v for k, v in row.items() if k != "goal_pair"} for row in sink.steps]
    assert stripped == plain_sink.steps


def test_a_timeout_abort_row_carries_the_pair_and_the_verdict_stays_invalid(monkeypatch):
    class Failing(TelemetrySession):
        pair = {"sequence": 3, "outcome": "timeout", "late_controller": "gripper"}

    ports = Ports(session_kwargs={"submit_error": RuntimeError("goal response timeout")})
    monkeypatch.setattr(Ports, "open_session", _open_with(Failing))
    sink = Sink()
    result = _run(ports, sink)
    assert result["verdict"] == "INVALID" and result["reason"] == "CONTROLLER_PAIR_FAILED: goal response timeout"
    failed = [row for row in sink.steps if row.get("reason") == "goal response timeout"]
    assert len(failed) == 1 and failed[0]["goal_pair"]["late_controller"] == "gripper" and failed[0]["held"] is True
    assert result["goal_response"] == Failing.summary


def test_nothing_but_plain_values_is_taken_before_the_goals_are_sent():
    """T0a must not add time to the send path: the in-flight counts and the load sample come after the decision."""
    clock, events = Clock(), []

    class Recording(TimedPort):
        def send(self, goal):
            events.append("send")
            return super().send(goal)

        def unfinished_goals(self):
            events.append("in_flight")
            return 1

    class RecordingLoad(FakeLoad):
        def sample(self):
            events.append("load")
            return super().sample()

    adapter = build(Recording(clock, accept_at=10.002), Recording(clock, accept_at=10.003), clock, RecordingLoad())
    submit(adapter)
    assert events[:2] == ["send", "send"] and set(events[2:]) == {"in_flight", "load"}
    assert adapter.last_pair["in_flight_at_check"] == {"arm": 1, "gripper": 1}
