"""Chunk callback receipts and reset transitions must survive pre-arm buffering."""

from dataclasses import replace
import threading

import pytest
from rclpy.qos import DurabilityPolicy, ReliabilityPolicy
from so101_mujoco_support.msg import PhysicsStepEvidenceChunk

from so101_demo.adapters.act.physics_clock_history import PhysicsClockHistory
from so101_demo.adapters.act.ros_physics_clock import RosPhysicsClockAdapter
from so101_demo.core.simulation.types import ObjectState, SimulationEvidence

from test_act_physics_clock_history import NOW_NS, _chunk, _sample


class FakeNode:
    def create_subscription(self, message_type, topic, callback, qos):
        self.message_type, self.topic, self.callback, self.qos = (
            message_type, topic, callback, qos)
        return object()


def _reset(epoch):
    return SimulationEvidence(
        simulation_time_s=0., frame_id="world", publisher_sequence=0,
        simulation_step=0, reset_epoch=epoch, simulation_session_id="clock-session",
        paused=True, object_state=ObjectState(
            body_id=1, body="cup", position_world=(0., 0., 0.),
            orientation_xyzw=(0., 0., 0., 1.),
            linear_velocity_world=(0., 0., 0.),
            angular_velocity_world=(0., 0., 0.)),
        has_contact=False, minimum_signed_distance_m=0.,
        maximum_normal_force_n=0., truncated=False,
        left_fingertip_contacts=(), right_fingertip_contacts=(),
        other_object_contacts=())


def _fixture(*, sample_capacity=10, chunk_capacity=4):
    now = [NOW_NS]
    history = PhysicsClockHistory(
        "clock-session", nq=2, nv=1, max_age_s=.2,
        max_source_step_gap_ns=3_000_000, clock_ns=lambda: now[0])
    node = FakeNode()
    hazards = []
    adapter = RosPhysicsClockAdapter(
        node, history, on_hazard=hazards.append,
        pending_sample_capacity=sample_capacity,
        pending_chunk_capacity=chunk_capacity)
    return adapter, node, history, hazards, now


def test_prearm_chunk_keeps_callback_receipt_and_reliable_volatile_qos():
    adapter, node, history, hazards, now = _fixture()
    assert node.message_type is PhysicsStepEvidenceChunk
    assert node.topic == "/so101/simulation/physics_step_chunks"
    assert node.qos.reliability is ReliabilityPolicy.RELIABLE
    assert node.qos.durability is DurabilityPolicy.VOLATILE
    chunk = _chunk(0, _sample(1))
    node.callback(chunk)
    chunk.samples[0].model_qpos[0] = 9.
    now[0] += 50_000_000
    adapter.arm(_reset(1))
    selected = history.step_at(1)
    assert selected["received_monotonic_ns"] == NOW_NS
    assert tuple(selected["sample"].model_qpos) == (.1, .2)
    assert hazards == []
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_STEP_UNAVAILABLE"):
        history.step_at(2)  # No callback can fabricate a publisher's partial tail.


def test_no_callback_does_not_imply_a_replayed_chunk_zero():
    adapter, node, history, hazards, now = _fixture()
    adapter.arm(_reset(1))
    with pytest.raises(ValueError, match="PHYSICS_CLOCK_UNAVAILABLE"):
        history.recent_with_receipts()
    assert hazards == []


def test_callback_waiting_on_arm_lock_is_consumed_once_with_original_receipt():
    adapter, node, history, hazards, now = _fixture()
    entered = threading.Event()
    history.clock_ns = lambda: entered.set() or now[0]
    with adapter._lock:
        worker = threading.Thread(target=lambda: node.callback(_chunk(0, _sample(1))))
        worker.start()
        assert entered.wait(timeout=2.)
        adapter.arm(_reset(1))
    worker.join(timeout=2.)
    assert not worker.is_alive()
    assert history.step_at(1)["received_monotonic_ns"] == NOW_NS
    assert hazards == []


def test_prearm_source_stale_at_drain_latches_and_notifies_once():
    adapter, node, history, hazards, now = _fixture()
    node.callback(_chunk(0, _sample(1)))
    now[0] += 250_000_000
    with pytest.raises(ValueError):
        adapter.arm(_reset(1))
    assert history.hazard is not None
    assert len(hazards) == 1
    node.callback(_chunk(0, _sample(1)))
    assert len(hazards) == 1


def test_pending_overflow_poison_is_epoch_scoped_even_if_survivors_are_contiguous():
    adapter, node, history, hazards, now = _fixture(sample_capacity=1)
    node.callback(_chunk(0, _sample(1)))
    node.callback(_chunk(1, _sample(2)))
    with pytest.raises(ValueError):
        adapter.arm(_reset(1))
    assert history.hazard is not None and len(hazards) == 1
    node.callback(_chunk(0, _sample(1, epoch=2)))
    adapter.arm(_reset(2))
    assert history.step_at(1)["sample"].reset_epoch == 2


def test_pending_chunk_capacity_overflow_cannot_be_hidden_by_later_chunks():
    adapter, node, history, hazards, now = _fixture(chunk_capacity=1)
    node.callback(_chunk(0, _sample(1)))
    node.callback(_chunk(1, _sample(2)))
    with pytest.raises(ValueError):
        adapter.arm(_reset(1))
    assert history.hazard is not None and len(hazards) == 1


@pytest.mark.parametrize("damage", ["missing_first", "duplicate", "foreign", "mixed_old"])
def test_missing_duplicate_foreign_or_mixed_old_chunk_latches(damage):
    adapter, node, history, hazards, now = _fixture()
    if damage == "missing_first":
        node.callback(_chunk(1, _sample(2)))
        with pytest.raises(ValueError):
            adapter.arm(_reset(1))
    else:
        adapter.arm(_reset(1))
        if damage == "duplicate":
            node.callback(_chunk(0, _sample(1)))
            node.callback(_chunk(0, _sample(1)))
        elif damage == "foreign":
            chunk = _chunk(0, _sample(1))
            chunk.simulation_session_id = "foreign"
            node.callback(chunk)
        else:
            chunk = _chunk(0, _sample(1, epoch=2))
            chunk.reset_epoch = 0
            node.callback(chunk)
    assert history.hazard is not None
    assert len(hazards) == 1


def test_future_epoch_is_retained_for_explicit_rearm_after_current_hazard():
    adapter, node, history, hazards, now = _fixture()
    adapter.arm(_reset(1))
    node.callback(_chunk(0, _sample(1, epoch=2)))
    assert history.hazard is not None and len(hazards) == 1
    with pytest.raises(ValueError):
        adapter.arm(_reset(1))
    adapter.arm(_reset(2))
    assert history.step_at(1)["sample"].reset_epoch == 2
    assert len(hazards) == 1


def test_identified_old_epoch_delivery_is_ignored_after_reset():
    adapter, node, history, hazards, now = _fixture()
    adapter.arm(_reset(1))
    adapter.arm(_reset(2))
    node.callback(_chunk(0, _sample(1)))
    node.callback(_chunk(0, _sample(1, epoch=2)))
    assert history.step_at(1)["sample"].reset_epoch == 2
    assert hazards == []


def test_old_epoch_with_inconsistent_envelope_is_not_silently_ignored():
    adapter, node, history, hazards, now = _fixture()
    adapter.arm(_reset(1))
    adapter.arm(_reset(2))
    old = _chunk(0, _sample(1))
    old.last_physics_step = 2
    node.callback(old)
    assert history.hazard is not None and len(hazards) == 1


def test_prearm_future_epoch_invalidates_intermediate_reset_without_losing_chunk():
    adapter, node, history, hazards, now = _fixture()
    node.callback(_chunk(0, _sample(1, epoch=2)))
    with pytest.raises(ValueError):
        adapter.arm(_reset(1))
    assert history.hazard is not None and len(hazards) == 1
    adapter.arm(_reset(2))
    assert history.step_at(1)["sample"].reset_epoch == 2


def test_history_rejects_an_explicit_receipt_after_current_clock():
    adapter, node, history, hazards, now = _fixture()
    adapter.arm(_reset(1))
    with pytest.raises(ValueError):
        history.accept_chunk(_chunk(0, _sample(1)),
                             received_monotonic_ns=now[0] + 1)
    assert history.hazard is not None


def test_invalid_reset_proof_does_not_clear_current_history():
    adapter, node, history, hazards, now = _fixture()
    adapter.arm(_reset(1))
    node.callback(_chunk(0, _sample(1)))
    with pytest.raises(ValueError):
        adapter.arm(replace(_reset(2), paused=False))
    assert history.step_at(1)["sample"].reset_epoch == 1
    assert hazards == []
