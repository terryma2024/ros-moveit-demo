"""Recorder round 2 (CP-3403, cleanup step 2): the offline sources are served by the replay node, and the capture starts only on
an instant whose first row has every source.

L2 evidence: the first grid instant was the seed pair's stamp (10.0 s) while the capture-start clock read 10.038 s and
the first planning-scene query came after the start, so no query could have a response stamp in [9.9 s, 10.0 s] and
`ready(10.0)` stayed false until INPUT_STALE (ready + 3.5 s). The receiver thread and the scene poller of the live Recorder are gone:
the replay delivers the messages at their recorded instants and the recorded scene reads become visible at the same pass.
"""
import json
from types import SimpleNamespace

import pytest

from test_act_episode_recorder_sources import RecordingNode, _binding, _engine, _episode, _options
from so101_demo.act.offline import sources as module


def make(**kwargs):
    node, latched = RecordingNode(), []
    sources = module.OfflineRosSources(
        node, _episode([]), _options(), bind=lambda *a, **k: _binding(),
        world_observer_factory=lambda node_, session: SimpleNamespace(callback_count=11),
        reference_port_factory=lambda node_, **kw: SimpleNamespace(read=lambda when: {}, close=lambda: None), **kwargs)
    engine = _engine(latched)
    sources.prepare(engine)
    return sources, engine, latched


def test_the_pump_delivers_the_due_messages_before_it_drains_the_sources():
    sources, engine, _ = make()
    order = []
    sources.node.deliver_due = lambda: order.append("deliver")
    sources._drain_stages = lambda engine_: order.append("drain")
    sources.pump(engine)
    assert order == ["deliver", "drain"]


def test_a_callback_failure_in_the_replay_surfaces_from_the_next_pump_and_the_loop_goes_on():
    sources, engine, _ = make()
    sources.node.take_callback_errors = lambda: ["ValueError: boom"]
    with pytest.raises(RuntimeError, match="RECORDER_CALLBACK_FAILED: ValueError: boom"):
        sources.pump(engine)
    sources.node.take_callback_errors = lambda: []
    sources.pump(engine)


def test_the_replayed_scene_reads_become_visible_in_recorded_order_at_the_pass_that_delivered_them(monkeypatch):
    from so101_demo.act import scene_operation

    sources, engine, _ = make()
    monkeypatch.setattr(scene_operation, "scene_operation_record",
                        lambda payload: ({"call_id": payload["call_id"]}, None, None))
    sources._on_scene_read(SimpleNamespace(data=json.dumps({"payload": {"call_id": "a"}})))
    sources._on_scene_read(SimpleNamespace(data=json.dumps({"payload": {"call_id": "b"}})))
    assert list(sources._planning_calls) == []
    sources._refresh_scene()
    assert [call["call_id"] for call in sources._planning_calls] == ["a", "b"]
    sources._refresh_scene()
    assert len(sources._planning_calls) == 2, "a read is made visible once"


def test_the_alignment_verification_runs_on_the_callers_thread():
    sources, _, _ = make()
    future = sources._executor.submit(lambda: 7)
    assert future.done() and future.result() == 7


def test_close_releases_the_replayed_scene_read_subscription_too():
    sources, engine, _ = make()
    sources.close()
    destroyed = [call[1] for call in sources.node.calls if call[0] == "destroy_subscription"]
    assert module.SCENE_READS_TOPIC in destroyed


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
