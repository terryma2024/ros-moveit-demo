from __future__ import annotations

from types import SimpleNamespace

import pytest

from so101_mujoco_demo_py.mujoco.observer import (
    EvidenceRejected,
    EvidenceStale,
    MujocoWorldObserver,
)


class FakeNode:
    def create_subscription(self, message_type, topic, callback, qos):
        self.message_type = message_type
        self.topic = topic
        self.callback = callback
        self.qos = qos
        return object()


def vector(x=0.0, y=0.0, z=0.0):
    return SimpleNamespace(x=x, y=y, z=z)


def message(*, session="session-a", epoch=0, step=1, sequence=1, paused=False):
    return SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=2, nanosec=500_000_000), frame_id="world"),
        publisher_sequence=sequence,
        simulation_step=step,
        reset_epoch=epoch,
        simulation_session_id=session,
        paused=paused,
        object_body_id=9,
        object_body="cup",
        object_pose_world=SimpleNamespace(
            position=vector(0.27, 0.0, 0.08),
            orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        ),
        object_twist_world=SimpleNamespace(linear=vector(), angular=vector()),
        has_contact=False,
        minimum_signed_distance_m=0.0,
        maximum_normal_force_n=0.0,
        truncated=False,
        left_fingertip_contacts=[],
        right_fingertip_contacts=[],
        other_object_contacts=[],
    )


def observer(now):
    return MujocoWorldObserver(FakeNode(), "session-a", max_age_s=0.2, monotonic=lambda: now[0])


def test_observer_maps_one_atomic_message_to_immutable_evidence() -> None:
    now = [10.0]
    target = observer(now)
    target.accept(message(), received_at_s=10.0)
    evidence = target.snapshot()
    assert evidence.simulation_time_s == 2.5
    assert evidence.ordering_key == ("session-a", 0, 1)
    assert evidence.object_state.body == "cup"
    assert evidence.object_state.position_world == (0.27, 0.0, 0.08)
    assert evidence.left_fingertip_contacts == ()
    with pytest.raises(AttributeError):
        evidence.simulation_step = 2


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda item: setattr(item, "simulation_session_id", "wrong"), "session"),
        (lambda item: setattr(item, "truncated", True), "truncated"),
        (lambda item: delattr(item, "right_fingertip_contacts"), "right"),
    ],
)
def test_observer_rejects_wrong_session_truncation_and_missing_sides(mutation, match) -> None:
    target = observer([10.0])
    item = message()
    mutation(item)
    with pytest.raises(EvidenceRejected, match=match):
        target.accept(item, received_at_s=10.0)


def test_observer_enforces_sequence_step_and_reset_epoch_ordering() -> None:
    target = observer([10.0])
    target.accept(message(step=4, sequence=8), received_at_s=10.0)
    with pytest.raises(EvidenceRejected, match="sequence"):
        target.accept(message(step=5, sequence=8), received_at_s=10.0)
    with pytest.raises(EvidenceRejected, match="step"):
        target.accept(message(step=3, sequence=9), received_at_s=10.0)
    with pytest.raises(EvidenceRejected, match="paused"):
        target.accept(message(step=4, sequence=9), received_at_s=10.0)
    target.accept(message(step=4, sequence=9, paused=True), received_at_s=10.0)
    with pytest.raises(EvidenceRejected, match="epoch"):
        target.accept(message(epoch=2, step=0, sequence=10), received_at_s=10.0)
    target.accept(message(epoch=1, step=0, sequence=10), received_at_s=10.0)


def test_snapshot_rejects_missing_and_old_receipts() -> None:
    now = [10.0]
    target = observer(now)
    with pytest.raises(EvidenceStale, match="no atomic evidence"):
        target.snapshot()
    target.accept(message(), received_at_s=10.0)
    now[0] = 10.201
    with pytest.raises(EvidenceStale, match="0.201"):
        target.snapshot()


def test_callback_rejection_is_diagnostic_and_does_not_replace_latest() -> None:
    now = [10.0]
    target = observer(now)
    target.accept(message(step=1, sequence=1), received_at_s=10.0)
    target._callback(message(session="wrong", step=2, sequence=2))
    assert target.rejected_count == 1
    assert "session mismatch" in target.last_rejection
    assert target.snapshot().simulation_step == 1
