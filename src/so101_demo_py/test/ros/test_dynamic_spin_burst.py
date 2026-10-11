"""S3 burst spinning: one scheduling pass runs every queued callback within a bounded budget (actual62)."""

import json
import time
from types import SimpleNamespace

import pytest


class QueueSpin:
    """`rclpy.spin_once` stand-in that runs at most one queued callback per call."""

    def __init__(self, count):
        self.queue = list(range(count))
        self.ran = []
        self.calls = 0

    def __call__(self, _node, timeout_sec):
        self.calls += 1
        if self.queue:
            self.ran.append(self.queue.pop(0))


def _execution(monkeypatch, spin):
    import rclpy
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution

    monkeypatch.setattr(rclpy, "spin_once", spin)
    execution = RosDynamicMujocoExecution.__new__(RosDynamicMujocoExecution)
    execution._node = object()
    execution._document = {}
    return execution


def test_progress_runs_every_queued_callback_in_one_call(monkeypatch):
    spin = QueueSpin(50)
    _execution(monkeypatch, spin)._progress()
    assert len(spin.ran) == 50


def test_progress_callback_exception_propagates(monkeypatch):
    def failing(_node, timeout_sec):
        raise RuntimeError("CALLBACK_BOOM")

    with pytest.raises(RuntimeError, match="CALLBACK_BOOM"):
        _execution(monkeypatch, failing)._progress()


def test_burst_is_bounded_by_budget_and_idle_costs_at_most_the_budget():
    from so101_demo.ros.dynamic_execution.common import _spin_burst

    spin = QueueSpin(10_000_000)
    began = time.monotonic()
    _spin_burst(object(), budget_s=0.02, spin=spin)
    elapsed = time.monotonic() - began
    assert 0 < len(spin.ran) < 10_000_000
    assert elapsed < 0.02 + 0.05
    idle = QueueSpin(0)
    began = time.monotonic()
    _spin_burst(object(), budget_s=0.02, spin=idle)
    assert time.monotonic() - began < 0.02 + 0.05
    tiny = QueueSpin(50)
    _spin_burst(object(), budget_s=0.0, spin=tiny)
    assert tiny.calls == 1, "first spin only when the budget is exhausted"


def test_burst_first_spin_uses_first_timeout_then_zero():
    from so101_demo.ros.dynamic_execution.common import _spin_burst

    timeouts = []
    _spin_burst("node", first_timeout_s=0.01, budget_s=0.005, spin=lambda node, timeout_sec: timeouts.append(timeout_sec))
    assert timeouts[0] == 0.01 and len(timeouts) > 1 and set(timeouts[1:]) == {0.0}


def _census_node(now_ns):
    registered = []

    class Node:
        def create_subscription(self, msg_type, topic, callback, qos_profile, **kwargs):
            registered.append((topic, callback))

        def get_clock(self):
            return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=now_ns[0]))

    return Node(), registered


def test_census_records_backlog_lag_for_header_stamped_messages_only():
    from so101_demo.ros.dynamic_runtime import _install_callback_census

    now_ns = [20_000_000_000]
    node, registered = _census_node(now_ns)
    census = _install_callback_census(node)
    delivered = []
    node.create_subscription(object, "/stamped", delivered.append, 10)
    node.create_subscription(object, "/plain", delivered.append, 10)
    stamped = lambda sec, nanosec: SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=sec, nanosec=nanosec)))
    callbacks = dict(registered)
    callbacks["/stamped"](stamped(17, 500_000_000))
    now_ns[0] = 20_500_000_000
    callbacks["/stamped"](stamped(19, 0))
    callbacks["/plain"](SimpleNamespace(data=1))
    assert census["/stamped"]["count"] == 2
    assert census["/stamped"]["max_lag_s"] == pytest.approx(2.5)
    assert census["/stamped"]["last_lag_s"] == pytest.approx(1.5)
    assert "max_lag_s" not in census["/plain"] and "last_lag_s" not in census["/plain"]
    assert len(delivered) == 3
    json.dumps(census)


def test_census_lag_is_non_raising_when_clock_is_broken():
    from so101_demo.ros.dynamic_runtime import _install_callback_census

    node, registered = _census_node([0])
    node.get_clock = lambda: (_ for _ in ()).throw(RuntimeError("no clock"))
    census = _install_callback_census(node)
    delivered = []
    node.create_subscription(object, "/stamped", delivered.append, 10)
    msg = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=0)))
    registered[0][1](msg)
    assert delivered == [msg] and census["/stamped"]["count"] == 1
