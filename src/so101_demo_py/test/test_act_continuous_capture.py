"""Task 2: continuous, causal capture at the 10 Hz sim-time grid.

The capture owns cadence, causal input selection, the per-row acquisition binding, the pixel-to-
identity check and the bounded join to the controller reference the run actually accepted at
`t + 0.1 s`. Callbacks only bookkeep; `drain()` and finalization are the only steps that write. A row
is never labelled from a revoked or never-arrived trajectory, and an interior unlabelled row fails the
run rather than disappearing from the grid.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from so101_demo.act.acquisition import AcquisitionGuard, AcquisitionMinter
from so101_demo.act.continuous_capture import CaptureSummary, ContinuousEpisodeCapture

ZERO = np.zeros((480, 640, 3), dtype=np.uint8)


class FakeSampler:
    """Stands in for the production synchronizer: the newest causal frame of each stream."""

    def __init__(self, *, pixels=None):
        self.stamps = {"head": [], "wrist": []}
        self.pixels = pixels

    def sample_with_audit(self, session_id, attempt_id, at_s):
        stamps = {}
        for camera in ("head", "wrist"):
            causal = [stamp for stamp in self.stamps[camera] if stamp <= at_s + 1e-9]
            stamps[camera] = round(max(causal), 6) if causal else round(at_s - 0.1, 6)
        stamps["arm"] = stamps["head"]
        stamps["neck"] = stamps["head"]
        image = ZERO if self.pixels is None else self.pixels
        observation = {"session_id": session_id, "attempt_id": attempt_id, "sim_time_s": at_s,
                       "head": image, "wrist": image, "state": [0.0] * 6 + [0.0, 1.0]}
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


def build(*, deadline_s=120.0, clock=None, sampler_pixels=None, audit_writer=None,
          pending_capacity=32):
    capture = ContinuousEpisodeCapture(
        recorder=FakeRecorder(), sampler=FakeSampler(pixels=sampler_pixels),
        guard=AcquisitionGuard(), physical_audit=physical_audit, audit_writer=audit_writer,
        deadline_s=deadline_s, monotonic=clock or (lambda: 0.0),
        pending_capacity=pending_capacity)
    return capture, AcquisitionMinter()


def feed(capture, minter, *, camera, stamp_s, pixels=ZERO, session="s", reset_epoch=1):
    frame = minter.mint(camera, session_id=session, reset_epoch=reset_epoch, stamp_s=stamp_s,
                        received_monotonic_ns=int(stamp_s * 1e9) + 1, pixels=pixels)
    capture.on_acquisition(frame, pixels)
    capture.sampler.stamps[camera].append(float(stamp_s))
    return frame


def frames_at(capture, minter, stamps, *, pixels=ZERO):
    for stamp in stamps:
        feed(capture, minter, camera="head", stamp_s=stamp, pixels=pixels)
        feed(capture, minter, camera="wrist", stamp_s=stamp, pixels=pixels)


def start(capture, *, start_s=1.0, session="s", reset_epoch=1):
    capture.start(session, "attempt-1", reset_epoch, start_s)
    capture.on_event({"kind": "first_command", "sim_time_s": start_s})


def test_one_acquisition_cannot_fill_two_rows():
    """A still scene must supply a new acquisition per row; an old frame cannot fill the next one."""

    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0])
    capture.on_reference(reference(1.1))
    assert capture.drain() == 0                      # the 1.1 instant has not provably passed

    feed(capture, minter, camera="head", stamp_s=1.1)      # only the head moved on
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.drain()
    assert capture.recorder.rows == []


def test_a_slow_phase_joins_each_row_to_its_accepted_future_reference():
    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    for target in (1.1, 1.2, 1.3):
        capture.on_reference(reference(target))
    # 1.3 is observed, so rows whose targets are 1.1 and 1.2 are established; 1.3 is still pending
    assert capture.drain() == 2
    rows = capture.recorder.rows
    assert [row["observation"]["sim_time_s"] for row in rows] == [1.0, 1.1]
    ids = {(row["audit"]["head_acquisition_id"], row["audit"]["wrist_acquisition_id"])
           for row in rows}
    assert len(ids) == 2
    assert all(row["audit"]["reference_time_s"]
               == round(row["observation"]["sim_time_s"] + 0.1, 6) for row in rows)
    assert capture.pending_rows == 1


def test_a_late_reference_completes_an_earlier_pending_row():
    """A reference that arrives after the row was minted must still complete that row (T2-F1)."""

    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    assert capture.drain() == 0                      # nothing can be labelled yet
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1                      # the delayed label completes row 1.0
    assert capture.recorder.rows[0]["observation"]["sim_time_s"] == 1.0
    capture.on_reference(reference(1.2))
    capture.on_reference(reference(1.3))             # proves the 1.2 instant has passed
    assert capture.drain() == 1
    assert capture.recorder.rows[1]["observation"]["sim_time_s"] == 1.1


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
    assert capture.drain() == 1


def test_pixels_that_do_not_match_the_acquisition_identity_are_refused():
    """The stored image must be the one whose identity the row carries (T2-F3)."""

    capture, minter = build(sampler_pixels=ZERO)
    start(capture)
    other = np.full((480, 640, 3), 7, dtype=np.uint8)
    frames_at(capture, minter, [1.0], pixels=other)
    capture.on_reference(reference(1.1))
    capture.on_reference(reference(1.2))
    with pytest.raises(ValueError, match="ACQUISITION_PIXEL_MISMATCH"):
        capture.drain()
    assert capture.recorder.rows == []


def test_mismatched_pixels_at_receipt_are_refused():
    capture, minter = build()
    start(capture)
    frame = minter.mint("head", session_id="s", reset_epoch=1, stamp_s=1.0,
                        received_monotonic_ns=1, pixels=ZERO)
    with pytest.raises(ValueError, match="ACQUISITION_PIXEL_MISMATCH"):
        capture.on_acquisition(frame, np.ones((480, 640, 3), dtype=np.uint8))


def test_a_frame_that_is_stale_or_not_yet_old_enough_is_not_causal():
    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.05])               # after the 1.0 grid instant
    capture.on_reference(reference(1.1))
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.drain()

    stale, stale_minter = build()
    start(stale)
    frames_at(stale, stale_minter, [0.5])            # 0.5 s older than the 1.0 instant
    stale.on_reference(reference(1.1))
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        stale.drain()


def test_a_cross_reset_acquisition_is_refused():
    capture, minter = build()
    start(capture)
    with pytest.raises(ValueError, match="ACQUISITION_RESET_MISMATCH"):
        feed(capture, minter, camera="head", stamp_s=1.0, reset_epoch=2)


def test_a_grid_hole_is_a_failure_not_a_silent_skip():
    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0])
    capture.on_reference(reference(1.1))
    capture.on_reference(reference(1.2))
    assert capture.drain() == 1
    feed(capture, minter, camera="head", stamp_s=1.2)      # the head jumps a whole step
    feed(capture, minter, camera="wrist", stamp_s=1.1)
    capture.on_reference(reference(1.3))
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.drain()


def test_finish_does_not_hide_an_interior_hole():
    """Finalization enforces the same continuity as a normal drain (T2-F5)."""

    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.2])
    capture.on_reference(reference(1.1))
    capture.on_reference(reference(1.3))
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.finish(1.2)


def test_a_revoked_reference_cannot_label_a_row():
    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1])
    capture.on_reference(reference(1.1, accepted=False))   # the 1.1 trajectory was revoked
    capture.on_reference(reference(1.2))                   # the next row is labelable
    capture.on_reference(reference(1.3))                   # and its instant has provably passed
    with pytest.raises(ValueError, match="CAPTURE_LABEL_GAP"):
        capture.drain()
    assert capture.recorder.rows == []


def test_an_accepted_reference_revoked_before_its_instant_is_void():
    """Acceptance followed by revocation before the target instant must not label the row (T2-F2)."""

    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1])
    capture.on_reference(reference(1.1))
    capture.on_reference(reference(1.1, accepted=False))
    assert capture.drain() == 0                       # 1.1 has not provably passed yet
    capture.on_reference(reference(1.2))               # the next row is labelable
    capture.on_reference(reference(1.3))
    with pytest.raises(ValueError, match="CAPTURE_LABEL_GAP"):
        capture.drain()
    assert capture.recorder.rows == []


def test_a_stop_before_the_instant_voids_its_label_and_finalizes_as_audit_only():
    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0])
    capture.on_reference(reference(1.1))
    capture.on_event({"kind": "stop", "sim_time_s": 1.05})
    summary = capture.finish(1.2)
    assert summary.sample_count == 0
    assert summary.label_cutoff_s == 0.0
    assert capture.recorder.rows == []
    assert capture.pending_rows == 1


def test_tail_rows_without_a_reference_stay_audit_only():
    written = []

    def audit_writer(observation, audit):
        path = Path(f"/tmp/tail-{observation['sim_time_s']}.json")
        written.append(path)
        return path

    capture, minter = build(audit_writer=audit_writer)
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1
    summary = capture.finish(1.4)
    assert summary.sample_count == 1
    assert summary.label_cutoff_s == 1.0
    assert capture.pending_rows == 2
    assert summary.audit_files == tuple(written) and len(written) == 2
    assert all(isinstance(path, Path) for path in summary.audit_files)
    assert len(capture.unlabelled_rows) == 2


def test_the_pending_join_is_bounded():
    capture, minter = build(pending_capacity=1)
    start(capture)
    frames_at(capture, minter, [1.0, 1.1])
    with pytest.raises(ValueError, match="CAPTURE_PENDING_OVERFLOW"):
        capture.drain()


def test_finish_refuses_after_the_motion_budget_is_spent():
    ticks = {"now": 0.0}
    capture, minter = build(deadline_s=120.0, clock=lambda: ticks["now"])
    start(capture)
    frames_at(capture, minter, [1.0])
    capture.on_reference(reference(1.1))
    ticks["now"] = 121.0
    with pytest.raises(ValueError, match="CAPTURE_DEADLINE_EXCEEDED"):
        capture.finish(1.2)


def test_an_on_time_stop_may_finalize_later():
    ticks = {"now": 0.0}
    capture, minter = build(deadline_s=120.0, clock=lambda: ticks["now"])
    start(capture)
    frames_at(capture, minter, [1.0])
    capture.on_event({"kind": "stop", "sim_time_s": 1.05})
    ticks["now"] = 500.0                             # finalization is not a motion deadline
    summary = capture.finish(1.2)
    assert summary.sample_count == 0


def test_finish_refuses_after_a_latched_failure():
    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1])
    capture.on_reference(reference(1.1, accepted=False))
    capture.on_reference(reference(1.2))
    capture.on_reference(reference(1.3))
    with pytest.raises(ValueError, match="CAPTURE_LABEL_GAP"):
        capture.drain()
    with pytest.raises(ValueError, match="CAPTURE_LABEL_GAP"):
        capture.finish(1.4)


def test_the_motion_budget_cannot_be_extended_or_made_unbounded():
    for bad in (float("inf"), float("nan"), 121.0, 0.0, -1.0, "120"):
        with pytest.raises(ValueError, match="CAPTURE_DEADLINE_INVALID"):
            build(deadline_s=bad)


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


def test_the_summary_is_the_frozen_three_field_shape():
    assert set(CaptureSummary.__dataclass_fields__) == {"sample_count", "label_cutoff_s",
                                                        "audit_files"}
    capture, minter = build()
    start(capture)
    summary = capture.finish(1.0)
    assert (summary.sample_count, summary.label_cutoff_s) == (0, 0.0)
    assert isinstance(summary.audit_files, tuple)
