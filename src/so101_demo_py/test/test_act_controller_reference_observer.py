"""Controller frames keep original names, stamps, receipts and reset identity."""

from types import SimpleNamespace
import threading

import pytest

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
