"""Recorder round 2 (CP-3403): the Recorder's main node is served by its own receiver thread, the planning scene is read
by its own poller from the moment the initial association is built, and the capture starts only on an instant whose first
row has every source.

L2 evidence: the first grid instant was the seed pair's stamp (10.0 s) while the capture-start clock read 10.038 s and
the first planning-scene query came after the start, so no query could have a response stamp in [9.9 s, 10.0 s] and
`ready(10.0)` stayed false until INPUT_STALE (ready + 3.5 s). Callbacks and queries ran on the loop's own cadence, so any
loop pass that took 100-250 ms (seen at 3.2, 6.6, 8.2, 10.0 and 11.8 s) aged every main-node receipt.
"""
import threading
import time
from types import SimpleNamespace

import pytest

from so101_demo.act.episode_recorder_process import FaultInjector
from so101_demo.ros import episode_recorder_sources as module
from test_act_episode_recorder_sources import RecordingNode, _binding, _engine, _episode, _options


class FakeReceiver:
    def __init__(self, node=None):
        self.started = self.stopped = False
        self.healthy = True

    def start(self):
        self.started = True

    def alive(self):
        return self.healthy

    def failure(self):
        return None if self.healthy else "boom"

    def stop(self, timeout=2.0):
        self.stopped = True

    def stats(self):
        return {"spins": 1}


def make(receiver=True, **kwargs):
    node, latched = RecordingNode(), []
    holder = []

    def factory(node_):
        holder.append(FakeReceiver(node_))
        return holder[-1]

    sources = module.RosRecorderSources(
        node, _episode([]), _options(), faults=FaultInjector(), bind=lambda *a, **k: _binding(),
        world_observer_factory=lambda node_, session: SimpleNamespace(callback_count=11),
        reference_port_factory=lambda node_, **kw: SimpleNamespace(read=lambda when: {}, close=lambda: None),
        receiver_factory=factory if receiver else None, **kwargs)
    engine = _engine(latched)
    sources.prepare(engine)
    return sources, engine, holder, latched


def test_a_receiver_serves_the_node_and_the_pump_does_not_spin(monkeypatch):
    spins = []
    monkeypatch.setattr(module, "spin_burst", lambda node, **kw: spins.append(node))
    sources, engine, holder, _ = make()
    assert holder[0].started
    sources.pump(engine)
    assert spins == []


def test_without_a_receiver_the_pump_still_spins_the_node(monkeypatch):
    spins = []
    monkeypatch.setattr(module, "spin_burst", lambda node, **kw: spins.append(node))
    sources, engine, holder, _ = make(receiver=False)
    sources.pump(engine)
    assert holder == [] and len(spins) == 1


def test_a_dead_receiver_is_a_data_failure_not_a_silent_loss(monkeypatch):
    monkeypatch.setattr(module, "spin_burst", lambda node, **kw: None)
    sources, engine, holder, _ = make()
    holder[0].healthy = False
    with pytest.raises(RuntimeError, match="RECORDER_RECEIVER_FAILED"):
        sources.pump(engine)


def test_a_failed_controller_spool_is_a_data_failure_from_the_next_pump(monkeypatch):
    monkeypatch.setattr(module, "spin_burst", lambda node, **kw: None)
    sources, engine, holder, _ = make()
    sources.reference_port = SimpleNamespace(failure=lambda: "CONTROLLER_SPOOL_PROCESS_EXITED", close=lambda: None)
    with pytest.raises(RuntimeError, match="RECORDER_CONTROLLER_SPOOL_FAILED: CONTROLLER_SPOOL_PROCESS_EXITED"):
        sources.pump(engine)


def test_a_callback_failure_in_the_receiver_surfaces_from_the_next_pump_and_the_loop_goes_on(monkeypatch):
    monkeypatch.setattr(module, "spin_burst", lambda node, **kw: None)
    sources, engine, holder, _ = make()
    holder[0].take_callback_errors = lambda: ["ValueError: boom"]
    with pytest.raises(RuntimeError, match="RECORDER_CALLBACK_FAILED: ValueError: boom"):
        sources.pump(engine)
    holder[0].take_callback_errors = lambda: []
    sources.pump(engine)


def test_close_stops_the_poller_and_the_receiver_before_any_subscription_is_torn_down():
    sources, engine, holder, _ = make()
    order = []
    holder[0].stop = lambda timeout=2.0: order.append("receiver")
    sources.binding.close = lambda: order.append("binding")
    sources.reference_port = SimpleNamespace(close=lambda: order.append("reference"))
    sources.close()
    assert order[0] == "receiver" and "binding" in order
    assert sources._scene_poller is None


# ---- the planning scene is read from the initial association on, by its own poller ------------------------------

def test_the_poller_reads_the_scene_from_the_start_of_the_recorder_without_any_pump(monkeypatch):
    """CP-3425: the initial alignment is the Recorder's own read before the Teacher's SETUP, so the poller reads from the start."""
    sources, engine, holder, _ = make()
    queries = []
    sources._query_scene = lambda: queries.append(time.monotonic())
    sources._SCENE_POLL_SLEEP_S = 0.002
    sources._SCENE_QUERY_PERIOD_NS = 5_000_000
    sources.node.clock_ns = 5_000_000_000
    assert sources._start_scene_poller() is not None
    try:
        end = time.monotonic() + 3.0
        while len(queries) < 3 and time.monotonic() < end:
            sources.node.clock_ns += 6_000_000
            time.sleep(0.003)
        assert len(queries) >= 3 and sources._initial_built is False
    finally:
        sources._stop_scene_poller()


def test_a_scene_service_that_is_not_up_yet_is_not_a_failure_before_the_initial_alignment(monkeypatch):
    sources, engine, holder, _ = make()
    state = {"calls": 0}

    def query():
        state["calls"] += 1
        if state["calls"] < 3:
            raise RuntimeError("RECORDER_SCENE_SERVICE_UNAVAILABLE")

    sources._query_scene = query
    sources._SCENE_POLL_SLEEP_S = 0.002
    sources._SCENE_QUERY_PERIOD_NS = 5_000_000
    sources.node.clock_ns = 5_000_000_000
    sources._start_scene_poller()
    try:
        end = time.monotonic() + 3.0
        while state["calls"] < 5 and time.monotonic() < end:
            sources.node.clock_ns += 6_000_000
            time.sleep(0.003)
        assert state["calls"] >= 5 and sources._scene_error is None
    finally:
        sources._stop_scene_poller()


def test_a_failed_poll_surfaces_from_the_next_pump(monkeypatch):
    monkeypatch.setattr(module, "spin_burst", lambda node, **kw: None)
    sources, engine, holder, _ = make()

    def failing():
        raise RuntimeError("RECORDER_SCENE_QUERY_TIMEOUT")

    sources._query_scene = failing
    sources._SCENE_POLL_SLEEP_S = 0.002
    sources._initial_built = True
    sources.node.clock_ns = 9_000_000_000
    sources._start_scene_poller()
    try:
        end = time.monotonic() + 3.0
        while sources._scene_error is None and time.monotonic() < end:
            time.sleep(0.005)
        with pytest.raises(RuntimeError, match="RECORDER_SCENE_QUERY_TIMEOUT"):
            sources.pump(engine)
    finally:
        sources._stop_scene_poller()


def test_without_a_receiver_the_start_step_reads_the_scene_once_the_initial_association_is_built(monkeypatch):
    sources, engine, holder, _ = make(receiver=False)
    calls = []
    sources._refresh_scene = lambda: calls.append(1)
    sources.binding.observation_adapter = SimpleNamespace(_lock=threading.RLock(), _pre_capture_frames={}, hazard=None, _closed=False)
    assert sources.try_start(engine) is None and calls == [], "no initial association yet: nothing to read"
    sources._initial_built = True
    sources.world = SimpleNamespace(snapshot=lambda: (_ for _ in ()).throw(RuntimeError("no world yet")))
    sources.try_start(engine)
    assert calls == [1]


# ---- the capture starts on an instant whose first row has every source -------------------------------------------

def _startable(ready):
    """The Recorder's own start step with a real-shaped seed pair at stamps 10.0 s."""
    from test_act_capture_seed_validity import FLOOR, _causal
    parts = _causal(sim_now=10.05, stamps={"head": 10.0, "wrist": 10.0}, world_time_s=FLOOR)
    sources = parts[0]
    sources.node = SimpleNamespace(get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=10_050_000_000)))
    sources._provider = SimpleNamespace(ready=ready)
    return parts


def test_the_capture_does_not_start_on_an_instant_without_a_planning_scene_read():
    from test_act_capture_seed_validity import _step_once
    asked = []
    parts = _startable(lambda at_s: asked.append(at_s) or False)
    assert _step_once(parts) is None
    assert asked == [10.0], "the first row's instant is the seed pair's stamp"
    assert not parts[2].observation_adapter.capture.started


def test_the_capture_starts_once_the_first_row_has_every_source():
    from test_act_capture_seed_validity import _step_once
    parts = _startable(lambda at_s: True)
    assert _step_once(parts) == 10.0
