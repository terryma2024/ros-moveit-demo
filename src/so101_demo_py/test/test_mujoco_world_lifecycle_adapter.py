from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from so101_demo.backends.mujoco.lifecycle import MujocoLifecycleAdapter
from so101_demo.backends.mujoco.world import MujocoWorldAdapter
from so101_demo.core.simulation.types import (
    ObjectState,
    ReceivedSimulationEvidence,
    SimulationEvidence,
)
from so101_demo.core.simulation.types import (
    ResetReceipt as LegacyResetReceipt,
)


def _raw_evidence(*, paused: bool = True, epoch: int = 2) -> SimulationEvidence:
    return SimulationEvidence(
        simulation_time_s=0.04,
        frame_id="world",
        publisher_sequence=12,
        simulation_step=0 if paused else 10,
        reset_epoch=epoch,
        simulation_session_id="session-1",
        paused=paused,
        object_state=ObjectState(
            body_id=7,
            body="plastic_cup",
            position_world=(0.1, 0.2, 0.3),
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            linear_velocity_world=(0.0, 0.0, 0.0),
            angular_velocity_world=(0.0, 0.0, 0.0),
        ),
        has_contact=False,
        minimum_signed_distance_m=0.0,
        maximum_normal_force_n=0.0,
        truncated=False,
        left_fingertip_contacts=(),
        right_fingertip_contacts=(),
        other_object_contacts=(),
    )


@dataclass
class FakeObserver:
    evidence: SimulationEvidence

    def snapshot(self) -> SimulationEvidence:
        return self.evidence

    def snapshot_with_receipt(self) -> ReceivedSimulationEvidence:
        return ReceivedSimulationEvidence(self.evidence, 5.0)


class FakeReset:
    def reset(self, keyframe: str) -> LegacyResetReceipt:
        return LegacyResetReceipt(2, 3, keyframe, 0, "session-1")


class StaleReset:
    def reset(self, keyframe: str):
        return SimpleNamespace(
            old_epoch=2,
            new_epoch=2,
            keyframe=keyframe,
            simulation_step=1,
            simulation_session_id="session-1",
        )


class FakeServices:
    def __init__(self, observer: FakeObserver) -> None:
        self.observer = observer

    def controllers_active(self, names) -> bool:
        return True

    def pause(self, paused: bool) -> bool:
        return True


def test_mujoco_world_adapter_preserves_neutral_and_raw_evidence() -> None:
    """Catch loss or reinterpretation of MuJoCo quantities during neutral conversion."""

    adapter = MujocoWorldAdapter(FakeObserver(_raw_evidence()), FakeReset())
    evidence = adapter.snapshot()
    assert evidence.backend == "mujoco"
    assert evidence.session_id == "session-1"
    assert evidence.object_pose.position_m == (0.1, 0.2, 0.3)
    assert evidence.backend_metadata["minimum_signed_distance_m"] == 0.0
    assert evidence.backend_metadata["publisher_sequence"] == 12
    receipt = adapter.reset("task_start")
    assert receipt.old_epoch == 2
    assert receipt.new_epoch == 3
    assert receipt.observed_after_request


def test_service_success_without_observed_world_state_is_invalid() -> None:
    """Catch treating controller/service availability as proof that the world is ready."""

    class MissingObserver:
        def snapshot(self):
            raise RuntimeError("no world evidence")

    adapter = MujocoLifecycleAdapter(FakeServices(MissingObserver()), MissingObserver())
    assert adapter.readiness(1.0).error_code == "WORLD_STATE_NOT_CONFIRMED"


def test_pause_requires_matching_post_request_observation() -> None:
    """Catch accepting a successful pause service response with a still-running world frame."""

    observer = FakeObserver(_raw_evidence(paused=False))
    adapter = MujocoLifecycleAdapter(FakeServices(observer), observer)
    result = adapter.pause(True)
    assert not result.accepted
    assert result.error_code == "WORLD_STATE_NOT_CONFIRMED"


def test_world_adapter_rejects_sequence_or_step_regression() -> None:
    """Catch replayed evidence being accepted as a fresh atomic observation."""

    observer = FakeObserver(_raw_evidence())
    adapter = MujocoWorldAdapter(observer, FakeReset())
    adapter.snapshot()
    observer.evidence = _raw_evidence(paused=False)
    observer.evidence = SimulationEvidence(
        **{
            field: getattr(observer.evidence, field)
            for field in observer.evidence.__dataclass_fields__
            if field not in {"publisher_sequence", "simulation_step"}
        },
        publisher_sequence=11,
        simulation_step=9,
    )
    with pytest.raises(ValueError, match="regressed"):
        adapter.snapshot()


def test_reset_receipt_requires_observed_new_epoch_and_zero_step() -> None:
    """Catch a service acknowledgement being mistaken for an observed reset."""

    receipt = MujocoWorldAdapter(FakeObserver(_raw_evidence()), StaleReset()).reset("task_start")
    assert not receipt.observed_after_request
