"""Task 2: continuous, causal capture at the 10 Hz sim-time grid.

The capture owns cadence, causal input selection, the per-row acquisition binding and the bounded
join to the controller reference the run actually accepted at `t + 0.1 s`. Callbacks only bookkeep —
they never wait on IO — and `drain()` is the single place that mints and writes rows. It never
invents an action from feedback, from an unexecuted plan or from a fixed table, never reuses an
acquisition for a second row, and never labels a row from a phase the controller had already revoked.
"""

from __future__ import annotations

import numpy as np
import pytest

from so101_demo.act.acquisition import AcquisitionGuard, AcquisitionMinter
from so101_demo.act.continuous_capture import CaptureSummary, ContinuousEpisodeCapture

ZERO = np.zeros((480, 640, 3), dtype=np.uint8)


class FakeSampler:
    """Stands in for the production synchronizer: the newest causal frame of each stream."""

    def __init__(self):
        self.stamps = {"head": [], "wrist": []}

    def sample_with_audit(self, session_id, attempt_id, at_s):
        stamps = {}
        for camera in ("head", "wrist"):
            causal = [stamp for stamp in self.stamps[camera] if stamp <= at_s + 1e-9]
            stamps[camera] = round(max(causal), 6) if causal else round(at_s - 0.1, 6)
        stamps["arm"] = stamps["head"]
        stamps["neck"] = stamps["head"]
        observation = {"session_id": session_id, "attempt_id": attempt_id, "sim_time_s": at_s,
                       "head": ZERO, "wrist": ZERO, "state": [0.0] * 6 + [0.0, 1.0]}
        return observation, {"source_stamps": stamps, "source_received_wall_s": dict(stamps)}


class FakeRecorder:
    def __init__(self):
        self.rows = []

    def append(self, observation, action, audit):
        self.rows.append({"observation": observation, "action": list(action), "audit": audit})


def physical_audit(at_s):
    return {"physical_stamps": {"cup": at_s, "contacts": at_s, "planning_scene": at_s},
            "mujoco_truth": {"cup_xyz_m": [0.0, 0.0, 0.0]}, "contacts": [],
            "planning_scene": {"attached": []}, "controller_state": {"stopped": True}}


def reference(at_s, *, accepted=True, positions=None):
    return {"source": "CONTROLLER_REFERENCE", "requested_sim_time_s": round(at_s, 6),
            "positions": positions if positions is not None else [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            "accepted": accepted}


def build(*, dt_s=0.1, max_source_age_s=0.1, max_skew_s=0.0, deadline_s=120.0, clock=None):
    capture = ContinuousEpisodeCapture(
        recorder=FakeRecorder(), sampler=FakeSampler(), guard=AcquisitionGuard(),
        physical_audit=physical_audit, dt_s=dt_s, max_source_age_s=max_source_age_s,
        max_skew_s=max_skew_s, deadline_s=deadline_s, monotonic=clock or (lambda: 0.0))
    return capture, AcquisitionMinter()


def feed(capture, minter, *, camera, stamp_s, session="s", reset_epoch=1, pixels=ZERO):
    frame = minter.mint(camera, session_id=session, reset_epoch=reset_epoch, stamp_s=stamp_s,
                        received_monotonic_ns=int(stamp_s * 1e9) + 1, pixels=pixels)
    capture.on_acquisition(frame, pixels)
    capture.sampler.stamps[camera].append(float(stamp_s))
    return frame


def start(capture, *, start_s=1.0, session="s", reset_epoch=1):
    capture.start(session, "attempt-1", reset_epoch, start_s)
    capture.on_event({"kind": "first_command", "sim_time_s": start_s})


def as_grid_acquisitions(capture, minter, stamps):
    for stamp in stamps:
        feed(capture, minter, camera="head", stamp_s=stamp)
        feed(capture, minter, camera="wrist", stamp_s=stamp)


def test_one_acquisition_cannot_fill_two_rows():
    """A still scene must supply a new acquisition per row; an old frame cannot fill the next one."""

    capture, minter = build()
    start(capture)
    as_grid_acquisitions(capture, minter, [1.0])
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1

    feed(capture, minter, camera="head", stamp_s=1.1)          # only the head moved on
    capture.on_reference(reference(1.2))
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.drain()
    assert len(capture.recorder.rows) == 1


def test_a_slow_phase_mints_several_rows_with_distinct_acquisitions():
    capture, minter = build()
    start(capture)
    as_grid_acquisitions(capture, minter, [1.0, 1.1, 1.2])
    for stamp in (1.1, 1.2, 1.3):
        capture.on_reference(reference(stamp))
    assert capture.drain() == 3
    rows = capture.recorder.rows
    assert [row["observation"]["sim_time_s"] for row in rows] == [1.0, 1.1, 1.2]
    ids = {(row["audit"]["head_acquisition_id"], row["audit"]["wrist_acquisition_id"])
           for row in rows}
    assert len(ids) == 3
    assert all(row["audit"]["reference_time_s"] == row["observation"]["sim_time_s"] + 0.1
               for row in rows)


def test_identical_pixels_with_new_identity_are_the_positive_control():
    capture, minter = build()
    start(capture)
    first = feed(capture, minter, camera="head", stamp_s=1.0)
    feed(capture, minter, camera="wrist", stamp_s=1.0)
    second = feed(capture, minter, camera="head", stamp_s=1.1)
    feed(capture, minter, camera="wrist", stamp_s=1.1)
    assert first.pixel_sha256 == second.pixel_sha256
    assert first.acquisition_id != second.acquisition_id
    capture.on_reference(reference(1.1))
    capture.on_reference(reference(1.2))
    assert capture.drain() == 2


def test_a_frame_that_is_stale_or_not_yet_old_enough_is_not_causal():
    capture, minter = build()
    start(capture)
    # 1.05 is after the 1.0 grid time, so it cannot be that row's input
    as_grid_acquisitions(capture, minter, [1.05])
    capture.on_reference(reference(1.1))
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.drain()

    stale, stale_minter = build()
    start(stale)
    as_grid_acquisitions(stale, stale_minter, [0.5])           # 0.5 is 0.5 s older than row 1.0
    stale.on_reference(reference(1.1))
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        stale.drain()


def test_a_cross_reset_acquisition_is_refused():
    capture, minter = build()
    start(capture)
    with pytest.raises(ValueError, match="ACQUISITION_RESET_MISMATCH"):
        feed(capture, minter, camera="head", stamp_s=0.9, reset_epoch=2)


def test_a_grid_hole_is_a_failure_not_a_silent_skip():
    capture, minter = build()
    start(capture)
    as_grid_acquisitions(capture, minter, [1.0])
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1
    # the head jumps ahead to 1.2 while the wrist only reaches 1.1: the 1.1 row has no causal head
    feed(capture, minter, camera="head", stamp_s=1.2)
    feed(capture, minter, camera="wrist", stamp_s=1.1)
    capture.on_reference(reference(1.3))
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.drain()


def test_a_revoked_reference_cannot_label_a_row():
    capture, minter = build()
    start(capture)
    as_grid_acquisitions(capture, minter, [1.0])
    capture.on_reference(reference(1.1, accepted=False))
    assert capture.drain() == 0
    summary = capture.finish(1.5)
    assert summary.sample_count == 0
    assert summary.label_cutoff_s == 0.0


def test_tail_frames_without_a_future_reference_stay_audit_only():
    capture, minter = build()
    start(capture)
    as_grid_acquisitions(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1
    summary = capture.finish(1.4)
    assert summary.sample_count == 1
    assert summary.label_cutoff_s == 1.0
    assert capture.pending_rows == 2
    # a tail row must never appear as a training row with an invented action
    assert len(capture.recorder.rows) == 1


def test_stop_ends_capture_and_the_deadline_is_fixed():
    ticks = {"now": 0.0}
    capture, minter = build(deadline_s=120.0, clock=lambda: ticks["now"])
    start(capture)
    capture.on_event({"kind": "stop", "sim_time_s": 2.0})
    with pytest.raises(ValueError, match="CAPTURE_STOPPED"):
        capture.drain()
    with pytest.raises(ValueError, match="CAPTURE_STOPPED"):
        feed(capture, minter, camera="head", stamp_s=1.9)
    with pytest.raises(ValueError, match="CAPTURE_DEADLINE_FIXED"):
        capture.on_event({"kind": "first_command", "sim_time_s": 3.0})
    ticks["now"] = 121.0
    with pytest.raises(ValueError, match="CAPTURE_DEADLINE_EXCEEDED"):
        capture.on_event({"kind": "phase", "sim_time_s": 3.0})


def test_the_summary_is_the_frozen_three_field_shape():
    assert set(CaptureSummary.__dataclass_fields__) == {"sample_count", "label_cutoff_s",
                                                        "audit_files"}
    capture, minter = build()
    start(capture)
    summary = capture.finish(1.0)
    assert (summary.sample_count, summary.label_cutoff_s) == (0, 0.0)
    assert isinstance(summary.audit_files, tuple)
