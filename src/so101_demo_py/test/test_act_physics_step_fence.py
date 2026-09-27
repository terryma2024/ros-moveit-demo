"""A physics callback must mark the interval after SEARCH stop confirmation."""

import time
from types import SimpleNamespace

import pytest

from so101_mujoco_support.msg import PhysicsStepFenceAck

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
                    simulation_time_s=1.098):
        ack = PhysicsStepFenceAck()
        ack.simulation_session_id = request.simulation_session_id
        ack.reset_epoch = request.reset_epoch if epoch is None else epoch
        ack.request_sequence = request.request_sequence if sequence is None else sequence
        ack.marked_physics_step = step
        ack.marked_simulation_time_s = simulation_time_s
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
