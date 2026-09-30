"""Controller frames keep original names, stamps, receipts and reset identity."""

from types import SimpleNamespace
import threading

import pytest

import so101_demo.adapters.act.ros_broker as ros_broker
from so101_demo.adapters.act.controller_reference_observer import (
    ControllerReferenceObserver,
)
from so101_demo.adapters.act.ros_broker import RosBrokerDriver
from so101_mujoco_support.msg import SimulationEvidence


def frame(stamp_ns, *, names=("1", "2", "3", "4", "5")):
    return SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(
            sec=stamp_ns // 1_000_000_000,
            nanosec=stamp_ns % 1_000_000_000)),
        joint_names=list(names),
        reference=SimpleNamespace(
            positions=[0.0] * len(names),
            velocities=[0.0] * len(names)),
    )


def test_original_51_frames_and_receipts_survive_one_epoch():
    observer = ControllerReferenceObserver(max_frames=256)
    observer.reset("session-a", 2, source_floor_ns=1_000_000_000)
    for index in range(51):
        observer.accept("arm", frame(1_100_000_000 + index * 2_000_000),
                        received_monotonic_s=10.0 + index * 0.002)
    identity, rows = observer.recent("arm", now_monotonic_s=10.11,
                                     max_wall_age_s=0.2)
    assert identity == ("session-a", 2)
    assert len(rows) == 51
    assert rows[0]["sim_stamp_ns"] == 1_100_000_000
    assert rows[-1]["sim_stamp_ns"] == 1_200_000_000
    assert rows[-1]["received_monotonic_ns"] == 10_100_000_000
    assert rows[-1]["joint_names"] == ("1", "2", "3", "4", "5")
    assert rows[-1]["positions"] == (0.0,) * 5


def test_reset_removes_old_frames_and_invalid_source_latches():
    observer = ControllerReferenceObserver(max_frames=256)
    observer.reset("session-a", 2, source_floor_ns=1_000_000_000)
    observer.accept("arm", frame(1_100_000_000), received_monotonic_s=10.0)
    observer.reset("session-a", 3, source_floor_ns=2_000_000_000)
    identity, rows = observer.recent("arm", now_monotonic_s=10.1,
                                     max_wall_age_s=0.2)
    assert identity == ("session-a", 3) and rows == ()
    observer.accept("arm", frame(1_900_000_000), received_monotonic_s=10.1)
    with pytest.raises(ValueError):
        observer.recent("arm", now_monotonic_s=10.1, max_wall_age_s=0.2)


def test_duplicate_stamp_wrong_names_and_stale_receipts_refuse():
    observer = ControllerReferenceObserver(max_frames=256)
    observer.reset("session-a", 2, source_floor_ns=1_000_000_000)
    observer.accept("arm", frame(1_100_000_000), received_monotonic_s=10.0)
    observer.accept("arm", frame(1_100_000_000), received_monotonic_s=10.01)
    with pytest.raises(ValueError):
        observer.recent("arm", now_monotonic_s=10.02, max_wall_age_s=0.2)
    observer.reset("session-a", 3, source_floor_ns=2_000_000_000)
    observer.accept("arm", frame(2_100_000_000, names=("5", "4", "3", "2", "1")),
                    received_monotonic_s=10.1)
    with pytest.raises(ValueError):
        observer.recent("arm", now_monotonic_s=10.11, max_wall_age_s=0.2)
    observer.reset("session-a", 4, source_floor_ns=3_000_000_000)
    observer.accept("arm", frame(3_100_000_000), received_monotonic_s=10.0)
    with pytest.raises(ValueError):
        observer.recent("arm", now_monotonic_s=10.3, max_wall_age_s=0.2)


def test_driver_callback_keeps_original_reference_and_epoch():
    driver = object.__new__(RosBrokerDriver)
    driver._lock = threading.RLock()
    driver.monotonic = lambda: 10.1
    driver.max_age = 0.2
    driver._epoch = None
    driver._references = {}
    driver._reference_frames = ControllerReferenceObserver(max_frames=256)
    epoch = SimulationEvidence()
    epoch.simulation_session_id = "session-a"
    epoch.reset_epoch = 2
    epoch.header.stamp.sec = 1
    epoch.header.stamp.nanosec = 0
    driver._live_epoch(epoch)
    driver._reference("arm", frame(1_100_000_000))
    identity, rows = driver.recent_controller_references("arm")
    assert identity == ("session-a", 2)
    assert len(rows) == 1
    assert rows[0]["sim_stamp_ns"] == 1_100_000_000
    assert rows[0]["received_monotonic_ns"] == 10_100_000_000


def test_pre_reset_epoch_cannot_crash_or_enter_reference_history():
    driver = object.__new__(RosBrokerDriver)
    driver._lock = threading.RLock()
    driver.monotonic = lambda: 10.1
    driver.max_age = 0.2
    driver._epoch = None
    driver._references = {}
    driver._reference_frames = ControllerReferenceObserver(max_frames=256)
    epoch = SimulationEvidence()
    epoch.simulation_session_id = "session-a"
    epoch.reset_epoch = 0
    driver._live_epoch(epoch)
    with pytest.raises(RuntimeError):
        driver.recent_controller_references("arm")
    epoch.reset_epoch = 1
    epoch.header.stamp.sec = 1
    driver._live_epoch(epoch)
    driver._reference("arm", frame(1_100_000_000))
    identity, rows = driver.recent_controller_references("arm")
    assert identity == ("session-a", 1) and len(rows) == 1


def test_driver_subscribes_to_all_three_reference_streams(monkeypatch):
    subscriptions = {}

    class Node:
        def create_client(self, *_args):
            return object()

        def create_subscription(self, _message_type, topic, callback, _qos):
            subscriptions[topic] = callback
            return object()

    monkeypatch.setattr(ros_broker, "ActionClient", lambda *_args: object())
    driver = RosBrokerDriver(Node(), stop_velocity_rad_s=.002, max_age_s=.2,
                             monotonic=lambda: 10.1)
    epoch = SimulationEvidence()
    epoch.simulation_session_id = "session-a"
    epoch.reset_epoch = 2
    epoch.header.stamp.sec = 1
    driver._live_epoch(epoch)
    for kind, topic, names in (
        ("arm", "/arm_controller/controller_state", ("1", "2", "3", "4", "5")),
        ("gripper", "/gripper_controller/controller_state", ("6",)),
        ("neck", "/neck_controller/controller_state", ("neck_yaw_joint",)),
    ):
        assert topic in subscriptions
        subscriptions[topic](frame(1_100_000_000, names=names))
        identity, rows = driver.recent_controller_references(kind)
        assert identity == ("session-a", 2)
        assert len(rows) == 1
        assert rows[0]["joint_names"] == names


def test_the_broker_keeps_the_per_kind_names_and_sequence_it_received():
    """Proposal A needs the broker to hold the published names and its own sequence per kind."""

    import json
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src/adapters/act/ros_broker.py"
    text = source.read_text()
    assert "self._reference_names={};self._reference_sequences={}" in text
    assert 'self._reference_names={};self._reference_sequences={}' in text
    assert "self._reference_names[kind]=tuple(message.joint_names)" in text
    assert "self._reference_sequences[kind]=self._reference_sequences.get(kind,0)+1" in text


def test_the_observer_sequence_counts_publications_not_the_retained_buffer():
    """T3-F9: the sequence must keep advancing after the bounded buffer starts evicting."""

    observer = ControllerReferenceObserver(max_frames=51)
    observer.reset("session-a", 2, source_floor_ns=1_000_000_000)
    total = 60
    for index in range(total):
        observer.accept("arm", frame(1_100_000_000 + index * 2_000_000),
                        received_monotonic_s=10.0 + index * 0.002)
    identity, rows = observer.recent("arm", now_monotonic_s=10.0 + total * 0.002,
                                     max_wall_age_s=1.0)
    # the buffer holds 51 frames, but the publication counter reached the real count
    assert len(rows) == 51
    assert rows[-1]["observer_sequence"] == total
    observer.reset("session-a", 3, source_floor_ns=2_000_000_000)
    observer.accept("arm", frame(2_100_000_000), received_monotonic_s=20.0)
    identity, rows = observer.recent("arm", now_monotonic_s=20.1, max_wall_age_s=1.0)
    assert rows[-1]["observer_sequence"] == 1


def test_the_broker_exposes_a_ratified_frame_for_the_publication_basis():
    """A.1: the publication stays immutable beside the value evaluated for the instant."""

    import threading

    driver = object.__new__(RosBrokerDriver)
    driver._lock = threading.RLock()
    driver.max_age = 0.2
    driver.monotonic = lambda: 10.05
    driver._references = {"arm": ((0.1, 0.2, 0.3, 0.4, 0.5), (0.0,) * 5, 10.0, 1.0)}
    driver._reference_names = {"arm": ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex",
                                       "wrist_roll")}
    driver._reference_sequences = {"arm": 4}
    driver._reference_interval = lambda kind: None
    frame = driver.reference_frames("arm", 1.1)
    assert frame["published_positions"] == frame["evaluated_positions"]
    assert frame["evaluation"] == {"requested_sim_time_s": 1.1, "basis": "published",
                                   "goal_id": None, "accepted_sim_s": None, "revoked_sim_s": None}
    assert frame["observer_sequence"] == 4 and frame["sim_stamp_ns"] == 1_000_000_000
    # an accepted interval yields the evaluated value for the target while the publication stays
    driver._records = {"goal-1": {"kind": "arm", "accepted": True, "result": None,
                                  "cancel_requested": False, "accepted_sim_s": 1.0,
                                  "submitted_goal": None}}
    driver._reference_interval = lambda kind: [("goal-1", 1.0)]
    original = ros_broker.direct_goal_reference
    ros_broker.direct_goal_reference = lambda record, kind, at: {
        "positions": [0.5] * 5, "velocities": [0.25] * 5, "accelerations": [0.0] * 5}
    try:
        interval_frame = driver.reference_frames("arm", 1.1)
    finally:
        ros_broker.direct_goal_reference = original
    assert interval_frame["published_positions"] == (0.1, 0.2, 0.3, 0.4, 0.5)
    assert interval_frame["evaluated_positions"] == (0.5,) * 5
    assert interval_frame["evaluation"] == {"requested_sim_time_s": 1.1, "basis": "interval",
                                            "goal_id": "goal-1", "accepted_sim_s": 1.0,
                                            "revoked_sim_s": None}
    driver._reference_interval = lambda kind: [("goal-1", 1.0), ("goal-2", 1.0)]
    with pytest.raises(RuntimeError, match="REFERENCE_INTERVAL_INVALID"):
        driver.reference_frames("arm", 1.1)
