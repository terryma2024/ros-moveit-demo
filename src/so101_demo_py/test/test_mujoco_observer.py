from types import SimpleNamespace

from rclpy.qos import DurabilityPolicy, ReliabilityPolicy


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
