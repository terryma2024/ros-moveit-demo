"""C5: the Recorder must keep up with the 100 Hz world and scene streams (CP-3381).

`rclpy.spin_once` runs ONE ready callback per call. The Recorder's pass called it once, so with world (100 Hz), scene
(100 Hz), controller_state, joint_states and the cameras queued on one node it handled about one message in ~83 ms per
topic: world records 7 of 8 were never seen (sequence gaps) and the source alignment join found no source."""
import time
from types import SimpleNamespace

import pytest

from test_act_recorder_scene import Teacher, ctx, sources_fixture  # noqa: F401  (pytest fixtures)
from test_act_scene_association import association, frozen_scene  # noqa: F401


def test_one_burst_consumes_every_queued_message_of_a_real_node():
    import rclpy
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from std_msgs.msg import String

    from so101_demo.ros.episode_recorder_sources import spin_burst

    rclpy.init()
    try:
        node = rclpy.create_node("c5_spin_burst")
        got = []
        qos = QoSProfile(depth=2000, reliability=ReliabilityPolicy.RELIABLE)
        node.create_subscription(String, "/c5/a", lambda m: got.append("a"), qos)
        node.create_subscription(String, "/c5/b", lambda m: got.append("b"), qos)
        pub_a, pub_b = node.create_publisher(String, "/c5/a", qos), node.create_publisher(String, "/c5/b", qos)
        time.sleep(0.5)
        for _ in range(400):
            pub_a.publish(String(data="x"))
            pub_b.publish(String(data="y"))
        time.sleep(0.3)
        spin_burst(node, budget_s=0.5)
        assert got.count("a") == 400 and got.count("b") == 400
    finally:
        rclpy.shutdown()


def test_the_burst_is_bounded_by_its_budget_and_waits_for_the_first_message():
    from so101_demo.ros.episode_recorder_sources import spin_burst

    calls = []
    spin_burst(SimpleNamespace(), budget_s=0.02, spin=lambda node, timeout_sec: calls.append(timeout_sec))
    assert calls[0] == 0.005 and len(calls) > 1 and set(calls[1:]) == {0.0}


def test_a_pump_pass_runs_a_burst_not_a_single_spin(ctx, monkeypatch):
    import rclpy

    ctx.stamp()
    sources, engine, *_ = sources_fixture(ctx, monkeypatch)
    calls = []
    monkeypatch.setattr(rclpy, "spin_once", lambda node, timeout_sec=0.0: calls.append(timeout_sec))
    sources.pump(engine)
    assert len(calls) > 10, "one spin_once runs one callback: a pass must drain what is queued"


def _replay_at_real_rates(spin_pass, seconds=2.0):
    """world 100 Hz + scene 100 Hz + 2 x 500 Hz controller_state + 2 x 500 Hz joint_states on one node, a pass that also
    spends ~8 ms on 'drain' work and sleeps poll_s: returns (published_world, received_world, lag_messages)."""
    import threading

    import rclpy
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from std_msgs.msg import Int64

    rclpy.init()
    try:
        node = rclpy.create_node("c5_real_rates")
        qos = QoSProfile(depth=256, reliability=ReliabilityPolicy.RELIABLE)
        deep = QoSProfile(depth=1000, reliability=ReliabilityPolicy.RELIABLE)
        topics = {"world": (100, qos), "scene": (100, qos), "c1": (500, deep), "c2": (500, deep), "j1": (500, deep),
                  "j2": (500, deep)}
        seen = {name: [] for name in topics}
        pubs = {}
        for name, (_, q) in topics.items():
            node.create_subscription(Int64, "/c5r/" + name, lambda m, name=name: seen[name].append(m.data), q)
            pubs[name] = node.create_publisher(Int64, "/c5r/" + name, q)
        time.sleep(0.5)
        stop, published = threading.Event(), {name: 0 for name in topics}

        def produce(name, hz):
            period, nxt = 1.0 / hz, time.monotonic()
            while not stop.is_set():
                published[name] += 1
                pubs[name].publish(Int64(data=published[name]))
                nxt += period
                time.sleep(max(0.0, nxt - time.monotonic()))

        threads = [threading.Thread(target=produce, args=(name, hz), daemon=True) for name, (hz, _) in topics.items()]
        for thread in threads:
            thread.start()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            spin_pass(node)
            time.sleep(0.008)            # the drain/service work of a pass
            time.sleep(0.005)            # poll_s
        stop.set()
        for thread in threads:
            thread.join()
        return published["world"], len(seen["world"]), published["world"] - (seen["world"][-1] if seen["world"] else 0)
    finally:
        rclpy.shutdown()


def test_at_the_real_stream_rates_the_pump_keeps_up_with_no_world_drops_and_a_bounded_lag():
    from so101_demo.ros.episode_recorder_sources import spin_burst

    published, received, lag = _replay_at_real_rates(spin_burst)
    assert received >= 0.95 * published, (published, received)
    assert lag <= 10, "the newest world record must be within ~100 ms of production"


def test_the_old_single_spin_pass_could_not_(monkeypatch):
    import rclpy

    published, received, lag = _replay_at_real_rates(lambda node: rclpy.spin_once(node, timeout_sec=0.005))
    assert received < 0.5 * published or lag > 100, (published, received, lag)
