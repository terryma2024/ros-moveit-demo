"""Runtime memory setting (T0b): collect + freeze, and its place in the episode record."""

import gc

from so101_demo.act.runtime_memory import freeze_heap

from test_act_rollout_episode import Ports, Sink, _run


def test_freeze_heap_collects_cycles_then_freezes_and_reports():
    cycle = []
    cycle.append(cycle)
    del cycle
    gc.unfreeze()
    record = freeze_heap()
    try:
        assert record["collected"] >= 1 and record["frozen_after"] >= record["frozen_before"] and record["frozen_after"] > 0
        assert record["duration_s"] >= 0 and gc.get_freeze_count() == record["frozen_after"]
    finally:
        gc.unfreeze()


class FreezingPorts(Ports):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.memory_record = [{"collected": 3, "frozen_after": 10}]


def test_the_episode_carries_the_memory_record_only_when_the_ports_have_one():
    assert _run(FreezingPorts(), Sink())["runtime_memory"] == [{"collected": 3, "frozen_after": 10}]
    assert "runtime_memory" not in _run(Ports(), Sink())


def test_the_heap_is_frozen_at_the_episode_reset_before_the_physics_resume():
    from types import SimpleNamespace

    from so101_demo.act.rollout_shared import NativeEpisodePorts

    order = []
    runtime = SimpleNamespace(resume_physics=lambda lease, receipt: order.append("resume") or True)
    ports = NativeEpisodePorts(runtime=runtime, lease=None, scene={}, directory=".", inputs=None, environment={}, binding=None,
                               runner=None, inference=None, transport=None, pilot_factory=None,
                               freeze_heap=lambda: order.append("freeze") or {"frozen_after": 7})
    assert ports.resume_physics(None) is True and order == ["freeze", "resume"] and ports.memory_record == [{"frozen_after": 7}]
    plain = NativeEpisodePorts(runtime=runtime, lease=None, scene={}, directory=".", inputs=None, environment={}, binding=None,
                               runner=None, inference=None, transport=None, pilot_factory=None)
    order.clear()
    assert plain.resume_physics(None) is True and order == ["resume"] and plain.memory_record == []


def test_the_episode_carries_the_observation_rejects_of_the_session(monkeypatch):
    from test_act_goal_pair_telemetry import TelemetrySession, _open_with

    class Rejecting(TelemetrySession):
        def observation_rejects(self):
            return {"rgb_sync_rejects": 2, "input_rejects": 0, "poll_skips": {"rgb_skew": 2}}

    plain = _run(Ports(), Sink())
    monkeypatch.setattr(Ports, "open_session", _open_with(Rejecting))
    assert _run(Ports(), Sink())["observation_rejects"]["rgb_sync_rejects"] == 2
    assert "observation_rejects" not in plain


def test_the_episode_carries_the_controller_readiness_of_the_session(monkeypatch):
    from test_act_goal_pair_telemetry import TelemetrySession, _open_with

    class Readied(TelemetrySession):
        def controller_readiness(self):
            return {"server_ready_wait_s": {"arm": 0.01}, "probes": {}}

    monkeypatch.setattr(Ports, "open_session", _open_with(Readied))
    assert _run(Ports(), Sink())["controller_readiness"] == {"server_ready_wait_s": {"arm": 0.01}, "probes": {}}
