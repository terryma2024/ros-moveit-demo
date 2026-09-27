"""A physics callback must mark the interval after SEARCH stop confirmation."""

import time
from types import SimpleNamespace

import pytest

from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepFenceAck

from so101_demo.adapters.act.physics_step_fence import RosPhysicsStepFence


class _Node:
    def __init__(self):
        self.callback = None
        self.on_publish = None
        self.requests = []

    def create_subscription(self, message_type, topic, callback, qos):
        assert topic == "/so101/simulation/physics_step_fence_ack"
        self.callback = callback
        return SimpleNamespace()

    def create_publisher(self, message_type, topic, qos):
        assert topic == "/so101/simulation/physics_step_fence_request"
        return SimpleNamespace(publish=self._publish)

    def _publish(self, message):
        self.requests.append(message)
        if self.on_publish:
            self.on_publish(message)

    def acknowledge(self, request, *, epoch=None, sequence=None, step=99,
                    simulation_time_s=1.098, clock_begin_ns=None,
                    clock_end_ns=None, sample_changes=None):
        ack = PhysicsStepFenceAck()
        ack.simulation_session_id = request.simulation_session_id
        ack.reset_epoch = request.reset_epoch if epoch is None else epoch
        ack.request_sequence = request.request_sequence if sequence is None else sequence
        ack.marked_physics_step = step
        ack.marked_simulation_time_s = simulation_time_s
        ack.clock_interval_begin_monotonic_ns = (
            time.monotonic_ns() if clock_begin_ns is None else clock_begin_ns)
        ack.clock_interval_end_monotonic_ns = (
            time.monotonic_ns() if clock_end_ns is None else clock_end_ns)
        sample = PhysicsStepEvidence()
        sample.simulation_session_id = ack.simulation_session_id
        sample.reset_epoch = ack.reset_epoch
        sample.physics_step = step
        sample.simulation_time_s = simulation_time_s
        sample.model_qpos = [.1, .2]
        sample.model_qvel = [.3]
        for field, value in (sample_changes or {}).items():
            setattr(sample, field, value)
        ack.marked_sample = sample
        self.callback(ack)


def _deadline():
    return time.monotonic_ns() + 100_000_000


def test_fence_accepts_only_matching_ack_after_confirmed_stop():
    node = _Node()
    fence = RosPhysicsStepFence(node, "session-1")
    fence.arm(2)
    node.on_publish = lambda request: node.acknowledge(request)
    stopped_wall_s = time.monotonic() - .001
    proof = fence.request_after_stop(2, stopped_wall_s, _deadline())
    assert proof["session_id"] == "session-1"
    assert proof["reset_epoch"] == 2
    assert proof["request_sequence"] == 1
    assert proof["marked_physics_step"] == 99
    assert proof["marked_simulation_time_s"] == 1.098
    assert stopped_wall_s <= proof["request_sent_wall_s"] <= proof["ack_received_wall_s"]
    assert (proof["request_sent_monotonic_ns"] <=
            proof["clock_interval_begin_monotonic_ns"] <=
            proof["clock_interval_end_monotonic_ns"] <=
            proof["ack_received_monotonic_ns"])
    assert proof["clock_interval_width_ns"] == (
        proof["clock_interval_end_monotonic_ns"] -
        proof["clock_interval_begin_monotonic_ns"])
    assert proof["model_qpos"] == (.1, .2)
    assert proof["model_qvel"] == (.3,)
    assert proof["command_authority"] is False
    with pytest.raises(ValueError, match="PHYSICS_STEP_FENCE_ALREADY_REQUESTED"):
        fence.request_after_stop(2, stopped_wall_s, _deadline())


@pytest.mark.parametrize("change", ["epoch", "sequence", "paused", "duplicate"])
def test_fence_rejects_wrong_or_missing_ack(change):
    node = _Node()
    fence = RosPhysicsStepFence(node, "session-1")
    fence.arm(2)

    def publish(request):
        if change == "epoch":
            node.acknowledge(request, epoch=3)
        elif change == "sequence":
            node.acknowledge(request, sequence=2)
        elif change == "duplicate":
            node.acknowledge(request)
            node.acknowledge(request)

    node.on_publish = publish
    with pytest.raises(ValueError, match="PHYSICS_STEP_FENCE_INVALID|PHYSICS_STEP_FENCE_TIMEOUT"):
        fence.request_after_stop(2, time.monotonic() - .001, _deadline())


def test_fence_rejects_reset_during_pending_request():
    node = _Node()
    fence = RosPhysicsStepFence(node, "session-1")
    fence.arm(2)
    node.on_publish = lambda request: fence.arm(3)
    with pytest.raises(ValueError, match="PHYSICS_STEP_FENCE_INVALID"):
        fence.request_after_stop(2, time.monotonic() - .001, _deadline())


@pytest.mark.parametrize("interval", [
    (0, 1), (5, 4), (1, 2), (2**62, 2**62 + 1),
])
def test_fence_rejects_unbounded_or_noncausal_source_clock(interval):
    node = _Node()
    fence = RosPhysicsStepFence(node, "session-1")
    fence.arm(2)
    node.on_publish = lambda request: node.acknowledge(
        request, clock_begin_ns=interval[0], clock_end_ns=interval[1])
    with pytest.raises(ValueError, match="PHYSICS_STEP_FENCE_INVALID"):
        fence.request_after_stop(2, time.monotonic() - .001, _deadline())


@pytest.mark.parametrize("change", [
    {"simulation_session_id": "other"},
    {"reset_epoch": 3},
    {"physics_step": 100},
    {"simulation_time_s": 1.1},
    {"model_qpos": []},
    {"model_qpos": [float("nan")]},
    {"model_qvel": []},
    {"model_qvel": [float("inf")]},
    {"truncated": True},
    {"diagnostic_hazard_breached": True},
])
def test_fence_rejects_mismatched_or_incomplete_marked_sample(change):
    node = _Node()
    fence = RosPhysicsStepFence(node, "session-1")
    fence.arm(2)
    node.on_publish = lambda request: node.acknowledge(
        request, sample_changes=change)
    with pytest.raises(ValueError, match="PHYSICS_STEP_FENCE_INVALID"):
        fence.request_after_stop(2, time.monotonic() - .001, _deadline())
