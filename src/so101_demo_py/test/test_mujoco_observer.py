from dataclasses import replace
from types import SimpleNamespace

from rclpy.qos import DurabilityPolicy, ReliabilityPolicy
import pytest


def test_atomic_evidence_observer_requests_latest_transient_sample() -> None:
    from so101_demo.backends.mujoco.observer import MujocoWorldObserver

    captured = {}

    class Node:
        def create_subscription(self, message, topic, callback, qos):
            captured.update(
                message=message,
                topic=topic,
                callback=callback,
                qos=qos,
            )
            return SimpleNamespace(get_publisher_count=lambda: 1)

    MujocoWorldObserver(Node(), "session-1")

    assert captured["topic"] == "/so101/simulation/evidence"
    assert captured["qos"].depth == 1
    assert captured["qos"].reliability == ReliabilityPolicy.RELIABLE
    assert captured["qos"].durability == DurabilityPolicy.TRANSIENT_LOCAL


def test_lossless_recorder_can_request_bounded_atomic_receive_queue(monkeypatch) -> None:
    from so101_demo.backends.mujoco import observer as world_module
    from so101_demo.core.simulation.types import ObjectState, SimulationEvidence

    MujocoWorldObserver = world_module.MujocoWorldObserver

    captured = {}

    class Node:
        def create_subscription(self, _message, _topic, _callback, qos):
            captured["qos"] = qos
            return SimpleNamespace(get_publisher_count=lambda: 1)

    world = MujocoWorldObserver(Node(), "session-1", subscription_depth=256,
                                monotonic=lambda: 10.)
    assert captured["qos"].depth == 256
    assert captured["qos"].reliability == ReliabilityPolicy.RELIABLE
    assert captured["qos"].durability == DurabilityPolicy.TRANSIENT_LOCAL
    for invalid in (0, True, 257):
        with pytest.raises(ValueError, match="subscription depth"):
            MujocoWorldObserver(Node(), "session-1", subscription_depth=invalid)
    monkeypatch.setattr(world_module, "convert_message", lambda message: message)
    first = SimulationEvidence(
        simulation_time_s=1., frame_id="world", publisher_sequence=1,
        simulation_step=1, reset_epoch=1, simulation_session_id="session-1",
        paused=False, object_state=ObjectState(
            body_id=1, body="cup", position_world=(0., 0., 0.),
            orientation_xyzw=(0., 0., 0., 1.),
            linear_velocity_world=(0., 0., 0.),
            angular_velocity_world=(0., 0., 0.)),
        has_contact=False, minimum_signed_distance_m=0.,
        maximum_normal_force_n=0., truncated=False,
        left_fingertip_contacts=(), right_fingertip_contacts=(),
        other_object_contacts=(),
    )
    skipped = replace(first, simulation_time_s=1.01, publisher_sequence=3,
                      simulation_step=2)
    world.accept(first, received_at_s=10.)
    world.accept(skipped, received_at_s=10.)
    with pytest.raises(world_module.EvidenceRejected, match="sequence gap"):
        world.recent_with_receipts()
