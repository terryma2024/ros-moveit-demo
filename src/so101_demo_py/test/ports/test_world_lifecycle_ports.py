from dataclasses import FrozenInstanceError

import pytest
from so101_demo.ports.evidence import PoseEvidence, TwistEvidence, WorldEvidence
from so101_demo.ports.lifecycle import LifecyclePort
from so101_demo.ports.world import WorldPort


def _world() -> WorldEvidence:
    return WorldEvidence(
        backend="mujoco",
        session_id="session-1",
        reset_epoch=2,
        simulation_step=10,
        simulation_time_s=0.04,
        object_pose=PoseEvidence((0.1, 0.2, 0.3), (0.0, 0.0, 0.0, 1.0)),
        object_twist=TwistEvidence((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        contacts=(),
        evidence_loss=False,
        truncated=False,
        backend_metadata={"publisher_sequence": 12},
    )


def test_world_evidence_is_immutable_and_finite() -> None:
    """Catch mutable or non-finite evidence crossing the application boundary."""

    evidence = _world()
    with pytest.raises(FrozenInstanceError):
        evidence.reset_epoch = 3
    with pytest.raises(ValueError, match="finite"):
        PoseEvidence((float("nan"), 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def test_world_and_lifecycle_ports_expose_required_methods() -> None:
    """Catch accidental narrowing of the stable adapter contracts."""

    assert set(WorldPort.__protocol_attrs__) >= {"snapshot", "snapshot_with_receipt", "reset"}
    assert set(LifecyclePort.__protocol_attrs__) >= {
        "readiness",
        "pause",
        "shutdown",
    }
