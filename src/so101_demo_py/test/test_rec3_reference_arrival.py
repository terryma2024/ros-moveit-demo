"""Recorder round 3 (CP-3405): a reference that has not arrived yet is waited for; only a real gap is a missing publication.

L2 rerun evidence: `COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE` 80 ms after the capture started, at the first row's
t+0.1 instant. The request is due when the SIM CLOCK (the /clock subscription) reaches the instant, while the controller_state
frame stamped at that instant arrives on its own subscription, behind a 1500 messages/s flood; the Recorder asked for it the
moment the clock said so and refused. Rows already wait for a late reference (`_reference_state`); the data side now asks only
for instants that a received frame of every required controller proves must have arrived (a later or equal stamp).
"""
from types import SimpleNamespace

import pytest

from so101_demo.ros import episode_recorder_sources as module
from test_act_episode_recorder_sources import RecordingNode, _binding, _engine, _episode, _options
from test_b2_controller_reference import PERIOD_NS, feed
from so101_demo.act.episode_recorder_process import FaultInjector


def port_with(frames_arm, frames_gripper, clock_ns):
    node = RecordingNode()
    node.clock_ns = 1_000
    port = module.ControllerReferencePort(node, session_id="s", reset_epoch=1)
    node.clock_ns = clock_ns
    base = 1_000_000_000_000
    feed(port.observer, "arm", [base + i * PERIOD_NS for i in range(frames_arm)])
    feed(port.observer, "gripper", [base + i * PERIOD_NS for i in range(frames_gripper)], names=("6",))
    return node, port, base


def test_received_through_is_the_older_of_the_two_required_controllers():
    node, port, base = port_with(100, 60, 1_000_000_000_000 + 400_000_000)
    assert port.received_through_s() == pytest.approx((base + 59 * PERIOD_NS) / 1e9)


def test_received_through_is_none_before_both_controllers_delivered():
    node, port, base = port_with(100, 0, 1_000_000_000_000)
    assert port.received_through_s() is None


def collect_with(port, clock_ns, requests):
    asked = []
    capture = SimpleNamespace(active=True, drain=lambda: None, on_reference=lambda record: None,
                              reference_requests=lambda through: asked.append(through) or ())
    sources = module.RosRecorderSources.__new__(module.RosRecorderSources)
    sources.episode = SimpleNamespace(capture=capture)
    sources.node = SimpleNamespace(get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=clock_ns)))
    sources.reference_port = port
    sources._receiver = object()
    sources._refresh_scene = lambda: None
    sources.collect(SimpleNamespace())
    return asked


def test_collect_asks_only_for_instants_a_received_frame_proves_arrived():
    node, port, base = port_with(100, 60, 1_000_000_000_000 + 400_000_000)
    asked = collect_with(port, base + 400_000_000, None)
    assert asked == [pytest.approx((base + 59 * PERIOD_NS) / 1e9)], "the gripper's newest frame bounds the request, not the clock"


def test_collect_still_stops_at_the_clock_when_every_frame_is_newer_than_it():
    node, port, base = port_with(300, 300, 0)
    asked = collect_with(port, base + 100_000_000, None)
    assert asked == [pytest.approx((base + 100_000_000) / 1e9)]


def test_collect_asks_nothing_before_any_frame_arrived():
    node, port, base = port_with(0, 0, 0)
    assert collect_with(port, base, None) == []


def test_a_real_gap_is_still_the_exact_publication_failure():
    node, port, base = port_with(0, 0, 0)
    stamps = [base + i * PERIOD_NS for i in range(300) if i != 150]            # one missing 2 ms publication
    feed(port.observer, "arm", stamps)
    feed(port.observer, "gripper", stamps, names=("6",))
    node.clock_ns = stamps[-1] + 1_000_000
    with pytest.raises(RuntimeError, match="COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE"):
        port.read((base + 150 * PERIOD_NS) / 1e9)


def test_a_collect_failure_latches_the_capture_so_its_queues_cannot_overflow_behind_it(tmp_path):
    from test_act_episode_recorder import build, result_of
    engine, sources, working = build(tmp_path)

    def failing(engine_):
        raise RuntimeError("COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE")

    sources.collect = failing
    engine.run()
    reasons = [item["reason"] for item in result_of(working)["reasons"]]
    assert reasons[0] == "COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE"
    with pytest.raises(ValueError, match="COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE"):
        engine.episode.capture.check_health()
