from __future__ import annotations

import inspect
import math
from dataclasses import FrozenInstanceError

import pytest

from so101_mujoco_demo_py.simulation.protocols import (
    ReceiptTimedWorldObserver,
    WorldObserver,
    WorldReset,
)
from so101_mujoco_demo_py.simulation.types import (
    ContactEvidence,
    ObjectState,
    ReceivedSimulationEvidence,
    ResetReceipt,
    SimulationEvidence,
)


def object_state() -> ObjectState:
    return ObjectState(
        body_id=4,
        body="task_object",
        position_world=(0.4, 0.0, 0.1),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        linear_velocity_world=(0.0, 0.0, 0.0),
        angular_velocity_world=(0.0, 0.0, 0.0),
    )


def contact(
    *, geom2: str = "left_fingertip", distance: float = -0.001, force: float = 2.0
) -> ContactEvidence:
    return ContactEvidence(
        body1_id=4,
        geom1_id=8,
        body1="task_object",
        geom1="task_object_collision",
        body2_id=2,
        geom2_id=5,
        body2="gripper",
        geom2=geom2,
        position_world=(0.4, 0.0, 0.1),
        normal_world=(1.0, 0.0, 0.0),
        signed_distance_m=distance,
        normal_force_n=force,
    )


def evidence(**overrides: object) -> SimulationEvidence:
    left = (contact(),)
    values: dict[str, object] = {
        "simulation_time_s": 1.25,
        "frame_id": "world",
        "publisher_sequence": 10,
        "simulation_step": 1200,
        "reset_epoch": 3,
        "simulation_session_id": "session-a",
        "paused": False,
        "object_state": object_state(),
        "has_contact": True,
        "minimum_signed_distance_m": -0.001,
        "maximum_normal_force_n": 2.0,
        "truncated": False,
        "left_fingertip_contacts": left,
        "right_fingertip_contacts": (),
        "other_object_contacts": (),
    }
    values.update(overrides)
    return SimulationEvidence(**values)


def test_atomic_evidence_is_deeply_immutable_and_matches_expanded_schema() -> None:
    value = evidence()
    with pytest.raises(FrozenInstanceError):
        value.paused = True  # type: ignore[misc]
    assert isinstance(value.left_fingertip_contacts, tuple)
    assert value.ordering_key == ("session-a", 3, 1200)
    assert value.object_state.body_id == value.left_fingertip_contacts[0].body1_id


def test_zero_contact_evidence_requires_empty_arrays_and_zero_aggregates() -> None:
    value = evidence(
        has_contact=False,
        minimum_signed_distance_m=0.0,
        maximum_normal_force_n=0.0,
        left_fingertip_contacts=(),
    )
    assert not value.has_contact
    with pytest.raises(ValueError, match="zero-contact"):
        evidence(has_contact=False)


def test_contact_aggregates_and_object_identity_are_validated() -> None:
    right = contact(geom2="right_fingertip", distance=-0.002, force=3.0)
    value = evidence(
        right_fingertip_contacts=(right,),
        minimum_signed_distance_m=-0.002,
        maximum_normal_force_n=3.0,
    )
    assert value.maximum_normal_force_n == 3.0
    with pytest.raises(ValueError, match="aggregate"):
        evidence(maximum_normal_force_n=99.0)
    with pytest.raises(ValueError, match="object identity"):
        evidence(
            left_fingertip_contacts=(contact(),),
            object_state=ObjectState(
                body_id=99,
                body="other",
                position_world=(0.0, 0.0, 0.0),
                orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
                linear_velocity_world=(0.0, 0.0, 0.0),
                angular_velocity_world=(0.0, 0.0, 0.0),
            ),
        )


@pytest.mark.parametrize(
    "change",
    [
        {"simulation_time_s": math.nan},
        {"frame_id": "map"},
        {"publisher_sequence": -1},
        {"simulation_step": -1},
        {"reset_epoch": -1},
        {"simulation_session_id": ""},
        {"left_fingertip_contacts": []},
    ],
)
def test_invalid_atomic_fields_are_rejected(change: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        evidence(**change)


def test_contact_rejects_negative_force_and_nonfinite_values() -> None:
    with pytest.raises(ValueError):
        contact(force=-0.1)
    with pytest.raises(ValueError):
        contact(distance=math.inf)


def test_reset_receipt_proves_epoch_transition_and_session() -> None:
    receipt = ResetReceipt(
        old_epoch=3,
        new_epoch=4,
        keyframe="home",
        simulation_step=0,
        simulation_session_id="session-a",
    )
    assert receipt.new_epoch == receipt.old_epoch + 1
    with pytest.raises(ValueError, match="increment"):
        ResetReceipt(3, 5, "home", 0, "session-a")


def test_received_evidence_adds_an_immutable_local_receipt_without_mutating_atomic_schema() -> None:
    received = ReceivedSimulationEvidence(evidence(), 10.0)
    assert received.evidence == evidence()
    assert received.received_monotonic_s == 10.0
    with pytest.raises(FrozenInstanceError):
        received.received_monotonic_s = 11.0


def test_protocol_calls_have_no_freshness_or_session_callsite_arguments() -> None:
    assert tuple(inspect.signature(WorldObserver.snapshot).parameters) == ("self",)
    assert tuple(inspect.signature(ReceiptTimedWorldObserver.snapshot_with_receipt).parameters) == (
        "self",
    )
    assert tuple(inspect.signature(WorldReset.reset).parameters) == ("self", "keyframe")
