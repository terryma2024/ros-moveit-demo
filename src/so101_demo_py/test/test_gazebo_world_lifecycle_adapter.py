from types import SimpleNamespace

from so101_demo.backends.gazebo.lifecycle import GazeboLifecycleAdapter
from so101_demo.backends.gazebo.observer import GazeboWorldObserver
from so101_demo.backends.gazebo.reset import GazeboResetAdapter
from so101_demo.backends.gazebo.world import GazeboWorldAdapter
from so101_demo.ports.capabilities import CapabilityRequirements
from so101_demo.runtime.composition import backend_capabilities


def observation(*, epoch: int = 3, step: int = 80):
    return SimpleNamespace(
        simulation_session_id="gazebo-session",
        reset_epoch=epoch,
        simulation_step=step,
        simulation_time_s=step * 0.002,
        object_pose_world=(0.0, -0.25, 0.165, 0.0, 0.0, 0.0, 1.0),
        object_twist_world=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        contacts=(
            SimpleNamespace(
                collision1="plastic_cup::body::wall_near",
                collision2="moving_fingertip_pad_collision_1",
                position_world=(0.0, -0.25, 0.17),
                normal_world=(0.0, 1.0, 0.0),
                normal_force_n=0.42,
                contact_depth_m=0.0004,
            ),
        ),
        pose_receipt_sequence=40,
        contact_receipt_sequence=42,
        world_stats={"iterations": step, "paused": False},
        partition="fusion-gazebo",
        bridge_identity="ros_gz_bridge:/world/so101",
        evidence_loss=False,
        truncated=False,
    )


def test_gazebo_evidence_is_neutral_without_mujoco_semantics() -> None:
    raw = GazeboWorldObserver(observation())
    evidence = GazeboWorldAdapter(raw, resetter=None).snapshot()

    assert evidence.backend == "gazebo"
    assert evidence.contacts[0].backend_metadata["contact_depth_m"] == 0.0004
    assert "signed_distance_m" not in evidence.contacts[0].backend_metadata
    assert evidence.backend_metadata == {
        "bridge_identity": "ros_gz_bridge:/world/so101",
        "contact_receipt_sequence": 42,
        "partition": "fusion-gazebo",
        "pose_receipt_sequence": 40,
        "world_stats": {"iterations": 80, "paused": False},
    }


def test_snapshot_receipt_uses_local_monotonic_observation_time() -> None:
    raw = GazeboWorldObserver(observation(), clock=lambda: 12.5)

    received = GazeboWorldAdapter(raw, resetter=None).snapshot_with_receipt()

    assert received.received_monotonic_s == 12.5
    assert received.evidence.session_id == "gazebo-session"


def test_reset_requires_new_observed_epoch() -> None:
    raw = GazeboWorldObserver(observation())

    def request_reset(keyframe: str) -> bool:
        assert keyframe == "home"
        raw.update(observation(epoch=4, step=0))
        return True

    resetter = GazeboResetAdapter(raw, request_reset, timeout_s=0.1)
    receipt = GazeboWorldAdapter(raw, resetter).reset("home")

    assert receipt.observed_after_request
    assert (receipt.old_epoch, receipt.new_epoch, receipt.simulation_step) == (3, 4, 0)


def test_reset_ack_without_new_epoch_is_rejected() -> None:
    raw = GazeboWorldObserver(observation())
    resetter = GazeboResetAdapter(raw, lambda keyframe: True, timeout_s=0.001)

    receipt = GazeboWorldAdapter(raw, resetter).reset("home")

    assert not receipt.observed_after_request
    assert receipt.old_epoch == receipt.new_epoch == 3


def test_lifecycle_declares_pause_unsupported_and_checks_bridge() -> None:
    raw = GazeboWorldObserver(observation())
    lifecycle = GazeboLifecycleAdapter(
        raw,
        controllers_active=lambda: True,
        bridge_ready=lambda: True,
        shutdown_callback=lambda timeout_s: timeout_s == 2.0,
    )

    assert lifecycle.readiness(1.0).accepted
    pause = lifecycle.pause(True)
    assert not pause.accepted
    assert pause.error_code == "PAUSE_NOT_SUPPORTED"
    assert lifecycle.shutdown(2.0).accepted


def test_gazebo_capabilities_pass_base_execute_without_trace() -> None:
    capabilities = backend_capabilities("gazebo")

    assert CapabilityRequirements.base_execute().validate(capabilities).accepted
    assert not capabilities.lossless_physics_step_trace
    assert not capabilities.atomic_snapshot
