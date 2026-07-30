from so101_teleop.models import JointSample, Pose6D, ServerMode, TelemetrySnapshot
from so101_teleop.telemetry import ReadinessEvaluator, TelemetryCollector


def ready_snapshot():
    """A complete, fresh simulation snapshot is the minimum writable server boundary."""
    return TelemetrySnapshot(
        sequence=3,
        simulation_session_id="sim-1",
        source_ages_s={"joints": 0.01, "tcp": 0.01, "object": 0.01, "scene": 0.01},
        joints={str(index): JointSample(name=str(index), position_rad=0.0) for index in range(1, 7)},
        tcp=Pose6D(frame_id="world", tcp_frame="so101_tcp", x_m=0.0, y_m=0.0, z_m=0.2,
                   roll_rad=0.0, pitch_rad=0.0, yaw_rad=0.0),
        object_pose=Pose6D(frame_id="world", tcp_frame="plastic_cup", x_m=0.0, y_m=0.0, z_m=0.02,
                          roll_rad=0.0, pitch_rad=0.0, yaw_rad=0.0),
        controllers={"arm_controller": "active", "gripper_controller": "active"},
        gazebo_attached=False,
        moveit_attached=False,
    )


def test_missing_q6_forces_read_only_mode():
    """Dropping gripper feedback must disable mutation rather than authorizing a partial robot."""
    snapshot = ready_snapshot().copy(update={"joints": {
        str(index): JointSample(name=str(index), position_rad=0.0) for index in range(1, 6)
    }})

    result = ReadinessEvaluator().evaluate(snapshot)

    assert result.mode is ServerMode.READ_ONLY
    assert "JOINT_6_MISSING" in result.reasons


def test_stale_tcp_forces_read_only_even_with_active_controllers():
    """Ignoring source age would allow a motion command based on stale Cartesian state."""
    snapshot = ready_snapshot().copy(update={"source_ages_s": {
        "joints": 0.01, "tcp": 2.0, "object": 0.01, "scene": 0.01
    }})

    assert ReadinessEvaluator(max_age_s=0.5).evaluate(snapshot).mode is ServerMode.READ_ONLY


def test_collector_increments_sequence_without_mutating_prior_snapshot():
    """Returning a mutable prior snapshot would let one WebSocket client corrupt another's telemetry."""
    collector = TelemetryCollector()
    first = collector.publish(ready_snapshot())
    second = collector.publish(ready_snapshot())

    assert first.sequence == 1
    assert second.sequence == 2
    assert first.sequence == 1
