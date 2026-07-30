from so101_teleop.models import (
    CommandResult,
    Pose6D,
    ServerMode,
    StepFrame,
    TelemetrySnapshot,
)


def test_pose_keeps_explicit_frames_and_si_units():
    """Removing explicit frame/unit fields would make a TCP command unsafe."""
    pose = Pose6D(
        frame_id="world",
        tcp_frame="so101_tcp",
        x_m=0.02,
        y_m=-0.28,
        z_m=0.20,
        roll_rad=0.0,
        pitch_rad=0.0,
        yaw_rad=0.0,
    )

    assert {"frame_id", "tcp_frame", "x_m", "roll_rad"} <= set(pose.dict())


def test_command_result_separates_transport_acceptance_from_robot_result():
    """A stale plan must not be reported as a robot success merely because HTTP accepted it."""
    result = CommandResult(
        command_id="c1",
        accepted=True,
        succeeded=False,
        code="PLAN_STALE_TARGET",
        message="target changed",
        layers={},
    )

    assert result.accepted is True
    assert result.succeeded is False


def test_telemetry_defaults_to_starting_mode_and_keeps_sequence_metadata():
    """Dropping sequence/session fields would permit stale browser control decisions."""
    snapshot = TelemetrySnapshot(sequence=7, simulation_session_id="sim-a")

    assert snapshot.mode is ServerMode.STARTING
    assert snapshot.sequence == 7
    assert snapshot.simulation_session_id == "sim-a"
    assert StepFrame.WORLD.value == "WORLD"
