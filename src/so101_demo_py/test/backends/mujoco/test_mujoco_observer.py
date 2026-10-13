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


def test_original_source_history_retention_has_no_age_filter_and_refuses_lost_prefix(monkeypatch):
    from so101_demo.backends.mujoco import observer as world_module
    from so101_demo.core.simulation.types import ObjectState, SimulationEvidence
    clock = [10.]
    node = SimpleNamespace(create_subscription=lambda *args: object())
    world = world_module.MujocoWorldObserver(node, "session", subscription_depth=256,
        monotonic=lambda: clock[0])
    monkeypatch.setattr(world_module, "convert_message", lambda value: value)
    first = SimulationEvidence(simulation_time_s=1., frame_id="world", publisher_sequence=1,
        simulation_step=1, reset_epoch=1, simulation_session_id="session", paused=False,
        object_state=ObjectState(body_id=1, body="plastic_cup", position_world=(0., 0., 0.),
            orientation_xyzw=(0., 0., 0., 1.), linear_velocity_world=(0., 0., 0.), angular_velocity_world=(0., 0., 0.)),
        has_contact=False, minimum_signed_distance_m=0., maximum_normal_force_n=0., truncated=False,
        left_fingertip_contacts=(), right_fingertip_contacts=(), other_object_contacts=())
    world.accept(first, received_at_s=10.)
    world.accept(replace(first, publisher_sequence=2, simulation_step=2, simulation_time_s=1.01), received_at_s=10.)
    clock[0] = 11.
    retained = world.original_records_after(0)
    assert [record.evidence.publisher_sequence for record in retained] == [1, 2]
    assert [record.received_monotonic_s for record in retained] == [10., 10.]
    assert world.original_records_after(2) == ()
    for sequence in range(3, 260):
        world.accept(replace(first, publisher_sequence=sequence, simulation_step=sequence,
            simulation_time_s=1. + sequence * .01), received_at_s=11.)
    with pytest.raises(world_module.EvidenceRejected, match="retention prefix"):
        world.original_records_after(2)
    assert world.original_records_after(258)[0].evidence.publisher_sequence == 259


def test_retained_with_receipts_is_unfiltered_and_ignores_hazard_and_age(monkeypatch):
    from so101_demo.backends.mujoco import observer as world_module
    from so101_demo.core.simulation.types import ObjectState, SimulationEvidence
    clock = [10.]
    node = SimpleNamespace(create_subscription=lambda *args: object())
    world = world_module.MujocoWorldObserver(node, "session", subscription_depth=256,
        monotonic=lambda: clock[0])
    assert world.retained_with_receipts() == ()
    monkeypatch.setattr(world_module, "convert_message", lambda value: value)
    first = SimulationEvidence(simulation_time_s=1., frame_id="world", publisher_sequence=1,
        simulation_step=1, reset_epoch=1, simulation_session_id="session", paused=False,
        object_state=ObjectState(body_id=1, body="plastic_cup", position_world=(0., 0., 0.),
            orientation_xyzw=(0., 0., 0., 1.), linear_velocity_world=(0., 0., 0.), angular_velocity_world=(0., 0., 0.)),
        has_contact=False, minimum_signed_distance_m=0., maximum_normal_force_n=0., truncated=False,
        left_fingertip_contacts=(), right_fingertip_contacts=(), other_object_contacts=())
    world.accept(first, received_at_s=10.)
    world.accept(replace(first, publisher_sequence=3, simulation_step=2, simulation_time_s=1.01), received_at_s=10.)
    clock[0] = 99.
    with pytest.raises(world_module.EvidenceRejected, match="sequence gap"):
        world.recent_with_receipts()
    retained = world.retained_with_receipts()
    assert type(retained) is tuple
    assert [record.evidence.publisher_sequence for record in retained] == [1, 3]
    assert [record.received_monotonic_s for record in retained] == [10., 10.]


def _world_pair(world_module, monkeypatch, **observer_kwargs):
    from so101_demo.core.simulation.types import ObjectState, SimulationEvidence
    monkeypatch.setattr(world_module, "convert_message", lambda message: message)
    node = SimpleNamespace(create_subscription=lambda *args: object())
    world = world_module.MujocoWorldObserver(node, "session-1", monotonic=lambda: 10., **observer_kwargs)
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
    return world, first


def test_a_world_sequence_gap_is_audited_without_a_hazard_when_the_audit_port_is_given(monkeypatch):
    # RED on the unchanged source: the constructor has no on_sequence_gap port.
    from so101_demo.backends.mujoco import observer as world_module
    gaps, hazards = [], []
    world, first = _world_pair(world_module, monkeypatch, on_sequence_gap=lambda *args: gaps.append(args),
                               on_hazard=hazards.append)
    skipped = replace(first, simulation_time_s=1.01, publisher_sequence=3, simulation_step=2)
    world.accept(first, received_at_s=10.)
    world.accept(skipped, received_at_s=10.)
    assert gaps == [(1, 3)] and hazards == []
    assert len(world.recent_with_receipts()) == 2
    assert world.snapshot().publisher_sequence == 3
    world.accept(replace(skipped, simulation_time_s=1.02, publisher_sequence=4, simulation_step=3), received_at_s=10.)
    assert gaps == [(1, 3)]


@pytest.mark.parametrize("problem", ["foreign_session", "sequence_backwards", "truncated", "epoch_backwards", "step_backwards"])
def test_world_audit_port_does_not_soften_inconsistent_or_foreign_evidence(problem, monkeypatch):
    from so101_demo.backends.mujoco import observer as world_module
    gaps = []
    world, first = _world_pair(world_module, monkeypatch, on_sequence_gap=lambda *args: gaps.append(args))
    world.accept(first, received_at_s=10.)
    bad = {"foreign_session": dict(simulation_session_id="other", publisher_sequence=2),
           "sequence_backwards": dict(publisher_sequence=1, simulation_step=2),
           "truncated": dict(publisher_sequence=2, simulation_step=2, truncated=True),
           "epoch_backwards": dict(publisher_sequence=2, reset_epoch=0),
           "step_backwards": dict(publisher_sequence=2, simulation_step=0)}[problem]
    with pytest.raises(world_module.EvidenceRejected):
        world.accept(replace(first, **bad), received_at_s=10.)
    assert gaps == []


def test_world_sequence_gap_is_still_a_hazard_without_the_audit_port(monkeypatch):
    # Keep-test: the default (execution-child) observer keeps its strict gap hazard.
    from so101_demo.backends.mujoco import observer as world_module
    hazards = []
    world, first = _world_pair(world_module, monkeypatch, on_hazard=hazards.append)
    skipped = replace(first, simulation_time_s=1.01, publisher_sequence=3, simulation_step=2)
    world.accept(first, received_at_s=10.)
    world.accept(skipped, received_at_s=10.)
    with pytest.raises(world_module.EvidenceRejected, match="sequence gap"):
        world.recent_with_receipts()


def test_recent_summaries_name_the_newest_frames_whatever_their_age(monkeypatch):
    from so101_demo.backends.mujoco import observer as world_module
    world, first = _world_pair(world_module, monkeypatch)
    for sequence in range(1, 8):
        world.accept(replace(first, publisher_sequence=sequence, simulation_step=sequence, paused=sequence == 7,
                             simulation_time_s=1. + sequence * .01), received_at_s=9. + sequence * .1)
    recent = world.recent_summaries(3)
    assert [item["publisher_sequence"] for item in recent] == [5, 6, 7]
    assert recent[-1]["paused"] is True and recent[0]["paused"] is False
    assert recent[-1]["age_s"] == pytest.approx(0.3, abs=1e-6)
    assert set(recent[0]) == {"paused", "reset_epoch", "simulation_step", "publisher_sequence", "age_s"}


def _joining_pair(world_module, monkeypatch, **kwargs):
    from so101_demo.core.simulation.types import ObjectState, SimulationEvidence
    monkeypatch.setattr(world_module, "convert_message", lambda message: message)
    node = SimpleNamespace(create_subscription=lambda *args: object())
    world = world_module.MujocoWorldObserver(node, "session-1", monotonic=lambda: 10., **kwargs)
    replayed = SimulationEvidence(
        simulation_time_s=141.54, frame_id="world", publisher_sequence=14164, simulation_step=60504, reset_epoch=1,
        simulation_session_id="session-1", paused=False,
        object_state=ObjectState(body_id=1, body="cup", position_world=(0., 0., 0.), orientation_xyzw=(0., 0., 0., 1.),
                                 linear_velocity_world=(0., 0., 0.), angular_velocity_world=(0., 0., 0.)),
        has_contact=False, minimum_signed_distance_m=0., maximum_normal_force_n=0., truncated=False,
        left_fingertip_contacts=(), right_fingertip_contacts=(), other_object_contacts=())
    live = replace(replayed, simulation_time_s=0.1, publisher_sequence=14180, simulation_step=42, reset_epoch=2, paused=True)
    return world, replayed, live


def test_a_one_shot_observer_that_joined_on_a_replayed_previous_epoch_takes_the_new_epoch_as_baseline(monkeypatch):
    from so101_demo.backends.mujoco import observer as world_module
    world, replayed, live = _joining_pair(world_module, monkeypatch, rebaseline_stale_join=True)
    world.accept(replayed, received_at_s=10.)
    world.accept(live, received_at_s=10.)
    assert world.diagnostics()["rejections"] == [] and world.snapshot().reset_epoch == 2 and world.snapshot().paused
    # the allowance is spent: a later epoch jump is judged as before
    with pytest.raises(world_module.EvidenceRejected, match="new reset epoch must begin at simulation step zero"):
        world.accept(replace(live, publisher_sequence=14181, reset_epoch=3, simulation_step=7), received_at_s=10.)


def test_a_continuous_observer_still_rejects_a_new_epoch_that_does_not_begin_at_step_zero(monkeypatch):
    from so101_demo.backends.mujoco import observer as world_module
    world, replayed, live = _joining_pair(world_module, monkeypatch)
    world.accept(replayed, received_at_s=10.)
    with pytest.raises(world_module.EvidenceRejected, match="new reset epoch must begin at simulation step zero"):
        world.accept(live, received_at_s=10.)
    world2, replayed2, live2 = _joining_pair(world_module, monkeypatch, rebaseline_stale_join=True)
    world2.accept(replayed2, received_at_s=10.)
    world2.accept(replace(replayed2, publisher_sequence=14165, simulation_step=60505), received_at_s=10.)
    with pytest.raises(world_module.EvidenceRejected, match="step zero"):
        world2.accept(live2, received_at_s=10.)   # continuity already proven: the allowance is only for the joining sample
