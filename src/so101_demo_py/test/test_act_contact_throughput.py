"""Plan A22: the broker's contacts consumer keeps up with the 500 Hz stream under GIL contention.

The callback itself costs ~25 us, but each executor cycle needs several GIL hand-offs; with another Python thread busy, every
hand-off waits a switch interval (5 ms), which capped the consumption at ~46 msg/s in the benchmark (the live broker saw
~380-400 msg/s against a 500 msg/s producer). The adapter now drains the already-queued messages inside the same mutually
exclusive callback. The throughput tests run the real subscription on a MultiThreadedExecutor (two threads, own callback
group, as the broker does) in a child process against a publisher in another process, on an isolated ROS domain.
"""

import json
import os
import random
import re
import subprocess
import sys
from collections import deque
from types import SimpleNamespace

import pytest
from paths import SUPPORT_DIR

BENCH = SUPPORT_DIR / "act_contact_throughput_bench.py"


def _run_bench(*, gil, count=2000, contacts=12, rate=0):
    env = dict(os.environ, A22_GIL=gil, A22_N=str(count), A22_CONTACTS=str(contacts), A22_RATE=str(rate),
               A22_DOMAIN=str(random.randint(60, 90)), ROS_LOCALHOST_ONLY="1")
    done = subprocess.run([sys.executable, str(BENCH)], env=env, capture_output=True, text=True, timeout=240)
    match = re.search(r"A22_RESULT .*received=(\d+)/(\d+) span_s=(\S+) sustained_hz=(\S+) callback_us=(\S+)", done.stdout)
    assert match, (done.returncode, done.stdout[-800:], done.stderr[-800:])
    received, total, span, hz, callback_us = int(match[1]), int(match[2]), float(match[3]), float(match[4]), float(match[5])
    assert received == total  # nothing was lost
    return dict(hz=hz, span=span, callback_us=callback_us)


def test_a_500_hz_stream_with_12_contacts_is_consumed_at_least_at_600_hz_while_another_python_thread_holds_the_gil():
    result = _run_bench(gil="pyloop")
    assert result["hz"] >= 600.0, result  # measured ~6000-6600; the undrained consumer measured 46


def test_an_idle_consumer_sustains_at_least_1000_hz_with_20_contacts_per_message():
    result = _run_bench(gil="none", contacts=20)
    assert result["hz"] >= 1000.0, result  # measured ~20000


# ---- content and order equivalence of the draining callback ----

def _message(step, *, truncated=False, geom=("g1", "g2")):
    from so101_mujoco_support.msg import RobotContactEvidence
    value = RobotContactEvidence()
    value.simulation_session_id, value.reset_epoch, value.physics_step = "s", 1, step
    value.simulation_time_s = step * .002
    value.geom_a, value.geom_b = list(geom[:1]) * 3, list(geom[1:]) * 3
    value.signed_distance_m, value.normal_force_n = [.01, .02, .03], [1., 2., 3.]
    value.truncated = truncated
    return value


def _adapter(subscription_factory=None):
    from so101_demo.adapters.act.contact_evidence import RobotContactObserver, RosRobotContactAdapter
    observer = RobotContactObserver(known_geoms={"g1", "g2", "g3"}, allowed_pairs={("g1", "g2")}, max_age_s=.5,
                                    max_sim_gap_s=.003, audit_integrity=True)
    observer.reset("s", 1, source_floor_s=0.)
    hazards = []

    class Node:
        def create_subscription(self, message_type, topic, callback, qos, **options):
            self.callback = callback
            return subscription_factory() if subscription_factory else SimpleNamespace()

    node = Node()
    adapter = RosRobotContactAdapter(node, observer, on_hazard=hazards.append)
    adapter._armed = True
    return adapter, observer, hazards, node


def _snapshot(observer):
    return ([dict(frame) for frame, _ in observer._history], dict(observer.last) if observer.last else None,
            observer.hazard)


@pytest.mark.parametrize("truncated_at", [None, 137])
def test_the_draining_callback_leaves_the_observer_exactly_as_per_message_delivery_does(truncated_at):
    messages = [_message(step, truncated=step == truncated_at) for step in range(1, 601)]
    reference, ref_observer, ref_hazards, _ = _adapter()
    for message in messages:
        reference.accept_message(message)
    queue = deque(messages[1:])
    subscription = SimpleNamespace(handle=SimpleNamespace(take_message=lambda message_type, raw: (queue.popleft(), None) if queue else None))
    drained, observer, hazards, node = _adapter(lambda: subscription)
    node.callback(messages[0])  # the executor's delivery; the rest are queued behind it
    while queue:  # the executor delivers the next message when the drain limit was reached
        node.callback(queue.popleft())
    assert _snapshot(observer) == _snapshot(ref_observer)  # same frames, same order, same last, same hazard
    assert hazards == ref_hazards and (truncated_at is None) == (observer.hazard is None)
    assert [frame["physics_step"] for frame, _ in observer._history] == [frame["physics_step"] for frame, _ in ref_observer._history]


def test_one_callback_drains_at_most_the_limit_in_order_and_leaves_the_rest_to_the_executor():
    messages = [_message(step) for step in range(1, 701)]
    queue = deque(messages[1:])
    subscription = SimpleNamespace(handle=SimpleNamespace(take_message=lambda message_type, raw: (queue.popleft(), None) if queue else None))
    adapter, observer, hazards, node = _adapter(lambda: subscription)
    node.callback(messages[0])
    assert adapter.drained == adapter._DRAIN_LIMIT == 256 and observer.last["physics_step"] == 257
    assert len(queue) == 700 - 257 and hazards == []


@pytest.mark.parametrize("failure", ["none_queue", "take_raises", "no_handle"])
def test_a_subscription_that_cannot_be_drained_still_delivers_the_one_message(failure):
    if failure == "no_handle":
        factory = lambda: SimpleNamespace()
    elif failure == "take_raises":
        def boom(message_type, raw):
            raise RuntimeError("take failed")
        factory = lambda: SimpleNamespace(handle=SimpleNamespace(take_message=boom))
    else:
        factory = lambda: SimpleNamespace(handle=SimpleNamespace(take_message=lambda message_type, raw: None))
    adapter, observer, hazards, node = _adapter(factory)
    node.callback(_message(1))
    assert observer.last["physics_step"] == 1 and adapter.drained == 0
