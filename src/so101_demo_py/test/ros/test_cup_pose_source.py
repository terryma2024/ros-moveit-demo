from types import SimpleNamespace

import pytest
from rclpy.qos import DurabilityPolicy, ReliabilityPolicy


def _message(frame_id: str = "world"):
    return SimpleNamespace(header=SimpleNamespace(frame_id=frame_id))


def _pose_message(stamp_ns: int):
    return SimpleNamespace(
        header=SimpleNamespace(
            frame_id="world",
            stamp=SimpleNamespace(
                sec=stamp_ns // 1_000_000_000,
                nanosec=stamp_ns % 1_000_000_000,
            ),
        ),
        pose=SimpleNamespace(
            position=SimpleNamespace(x=0.1, y=0.2, z=0.3),
            orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        ),
    )


def test_ros_cup_pose_source_uses_reliable_volatile_control_qos() -> None:
    from so101_demo.ros.cup_pose_source import RosCupPoseSource

    captured = {}

    class Node:
        def create_subscription(self, message, topic, callback, qos):
            captured.update(message=message, topic=topic, callback=callback, qos=qos)
            return object()

    RosCupPoseSource(Node(), SimpleNamespace())

    assert captured["topic"] == "/cup_pose"
    assert captured["qos"].depth == 10
    assert captured["qos"].reliability == ReliabilityPolicy.RELIABLE
    assert captured["qos"].durability == DurabilityPolicy.VOLATILE


def test_invalid_messages_do_not_extend_absolute_acquisition_deadline() -> None:
    from so101_demo.ports.cup_pose_source import CupPoseSourceError, acquire_one

    now = [0.0]
    invalid = _message("")
    reports: list[str] = []

    with pytest.raises(CupPoseSourceError) as captured:
        acquire_one(
            receive=lambda: invalid,
            spin_once=lambda duration: now.__setitem__(0, now[0] + duration),
            convert=lambda _: (_ for _ in ()).throw(ValueError("bad frame")),
            on_invalid=lambda error: reports.append(str(error)),
            timeout_s=0.25,
            monotonic=lambda: now[0],
        )

    assert captured.value.code == "CUP_POSE_INVALID"
    assert now[0] == pytest.approx(0.25)
    assert reports


def test_no_message_before_deadline_is_timeout() -> None:
    from so101_demo.ports.cup_pose_source import CupPoseSourceError, acquire_one

    now = [0.0]
    with pytest.raises(CupPoseSourceError) as captured:
        acquire_one(
            receive=lambda: None,
            spin_once=lambda duration: now.__setitem__(0, now[0] + duration),
            convert=lambda value: value,
            on_invalid=lambda _: None,
            timeout_s=0.2,
            monotonic=lambda: now[0],
        )

    assert captured.value.code == "CUP_POSE_TIMEOUT"


def test_returns_first_valid_value_and_stops() -> None:
    from so101_demo.ports.cup_pose_source import acquire_one

    messages = iter((_message(""), _message("world")))
    reports: list[str] = []

    result = acquire_one(
        receive=lambda: next(messages, None),
        spin_once=lambda _: None,
        convert=lambda value: value.header.frame_id
        if value.header.frame_id
        else (_ for _ in ()).throw(ValueError("bad frame")),
        on_invalid=lambda error: reports.append(str(error)),
        timeout_s=1.0,
        monotonic=lambda: 0.0,
    )

    assert result == "world"
    assert reports == ["bad frame"]


def test_arm_waits_for_positive_ros_clock_and_clears_pre_ready_cache(monkeypatch):
    import rclpy
    from so101_demo.ros import cup_pose_source
    from so101_demo.ros.cup_pose_source import RosCupPoseSource

    ros_times = iter((0, 0, 7_000_000_000))
    monotonic = [10.0]
    source = object.__new__(RosCupPoseSource)
    source._node = SimpleNamespace(
        get_clock=lambda: SimpleNamespace(
            now=lambda: SimpleNamespace(nanoseconds=next(ros_times))
        )
    )
    source._messages = [(object(), 9.0)]
    source._boundary = None
    spins = []
    monkeypatch.setattr(cup_pose_source.time, "monotonic", lambda: monotonic[0])

    def spin_once(_node, *, timeout_sec):
        spins.append(timeout_sec)
        monotonic[0] += timeout_sec

    monkeypatch.setattr(rclpy, "spin_once", spin_once)

    boundary = source.arm(1.0)

    assert boundary.ready_ros_ns == 7_000_000_000
    assert boundary.ready_monotonic_s == pytest.approx(10.1)
    assert source._messages == []
    assert spins == [0.05, 0.05]


def test_convert_requires_post_ready_receive_and_nonolder_source_stamp():
    from so101_demo.ros.cup_pose_source import (
        PoseReceiveBoundary,
        RosCupPoseSource,
    )

    source = object.__new__(RosCupPoseSource)
    source._node = SimpleNamespace(
        get_clock=lambda: SimpleNamespace(
            now=lambda: SimpleNamespace(nanoseconds=7_000_000_000)
        )
    )
    source._template = SimpleNamespace(
        planning_frame="world",
        maximum_source_age_s=1.0,
        maximum_future_skew_s=0.1,
    )
    source._boundary = PoseReceiveBoundary(7_000_000_000, 10.0)

    accepted = source._convert((_pose_message(7_000_000_000), 10.001))
    assert accepted.source_stamp_ns == 7_000_000_000
    with pytest.raises(ValueError, match="READY"):
        source._convert((_pose_message(6_999_999_999), 10.001))
    with pytest.raises(ValueError, match="READY"):
        source._convert((_pose_message(7_000_000_000), 10.0))
