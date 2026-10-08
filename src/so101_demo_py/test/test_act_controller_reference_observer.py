"""Controller frames keep original names, stamps, receipts and reset identity."""

from types import SimpleNamespace
import threading

import pytest

from so101_demo.adapters.act.controller_reference_observer import (
    ControllerReferenceObserver,
)
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


