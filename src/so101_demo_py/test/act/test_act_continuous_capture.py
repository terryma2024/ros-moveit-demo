"""Continuous, causal capture at the 10 Hz sim-time grid.

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
    frames_at(capture, minter, [1.0, 1.1, 1.2, 1.3])
    for target in (1.1, 1.2, 1.3):
        capture.on_reference(reference(target))
    # the camera reached 1.3, so rows targeting 1.1 and 1.2 are established; 1.3 is still pending
    assert capture.drain() == 2
    rows = capture.recorder.rows
    assert [row["observation"]["sim_time_s"] for row in rows] == [1.0, 1.1]
    # the identifiers belong to the audit's row-bindings records, and the channel the recorder validates is closed at
    # its own sixteen keys - so they must not appear here
    assert all("head_acquisition_id" not in row["audit"] and "wrist_acquisition_id" not in row["audit"]
               for row in rows)
    assert all(row["audit"]["reference_time_s"]
               == round(row["observation"]["sim_time_s"] + 0.1, 6) for row in rows)
    assert capture.pending_rows == 2


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
    frames_at(capture, minter, [1.3])                # the camera proves 1.2 has passed
    assert capture.drain() == 1
    assert capture.recorder.rows[1]["observation"]["sim_time_s"] == 1.1


def test_identical_pixels_with_new_identity_are_the_positive_control():
    capture, minter = build()
    start(capture)
    first = feed(capture, minter, camera="head", stamp_s=1.0)
    feed(capture, minter, camera="wrist", stamp_s=1.0)
    second = feed(capture, minter, camera="head", stamp_s=1.1)
    feed(capture, minter, camera="wrist", stamp_s=1.1)
    frames_at(capture, minter, [1.2])                # the camera reaches past 1.1
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
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.1))
    capture.on_reference(reference(1.2))
    assert capture.drain() == 1
    feed(capture, minter, camera="head", stamp_s=1.4)      # the head jumps a whole step
    feed(capture, minter, camera="wrist", stamp_s=1.3)
    capture.on_reference(reference(1.4))
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
    frames_at(capture, minter, [1.0, 1.1, 1.2, 1.3])
    capture.on_reference(reference(1.1, accepted=False))   # the 1.1 trajectory was revoked
    capture.on_reference(reference(1.2))                   # the next row is labelable, and 1.3 passed
    with pytest.raises(ValueError, match="CAPTURE_LABEL_GAP"):
        capture.drain()
    assert capture.recorder.rows == []


def test_an_accepted_reference_revoked_before_its_instant_is_void():
    """Acceptance followed by revocation before the target instant must not label the row (T2-F2)."""

    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2, 1.3])
    capture.on_reference(reference(1.1))
    capture.on_reference(reference(1.1, accepted=False))
    assert capture.drain() == 0                       # the void head row is not a gap yet
    capture.on_reference(reference(1.2))               # the next row becomes labelable
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
    frames_at(capture, minter, [1.0, 1.1, 1.2, 1.3])
    capture.on_reference(reference(1.1, accepted=False))
    capture.on_reference(reference(1.2))
    with pytest.raises(ValueError, match="CAPTURE_LABEL_GAP"):
        capture.drain()
    with pytest.raises(ValueError, match="CAPTURE_LABEL_GAP"):
        capture.finish(1.4)


def test_the_motion_budget_cannot_be_extended_or_made_unbounded():
    for bad in (float("inf"), float("nan"), 121.0, 0.0, -1.0, "120"):
        with pytest.raises(ValueError, match="CAPTURE_DEADLINE_INVALID"):
            build(deadline_s=bad)


def test_original_dispatch_clock_starts_deadline_before_delayed_reply():
    capture,_=build(clock=lambda:121.)
    capture.start('s','attempt-1',1,1.)
    with pytest.raises(ValueError,match='CAPTURE_DEADLINE_EXCEEDED'):
        capture.on_event({'kind':'first_command','sim_time_s':1.,'source_clock':{
            'sim_time_ns':1_000_000_000,'begin_monotonic_ns':1,'end_monotonic_ns':2}})


@pytest.mark.parametrize('bad',[{'sim_time_ns':1,'begin_monotonic_ns':True,'end_monotonic_ns':2},
    {'sim_time_ns':1_000_000_000,'begin_monotonic_ns':11_000_000_000,'end_monotonic_ns':11_000_000_001},
    {'sim_time_ns':2_000_000_000,'begin_monotonic_ns':1,'end_monotonic_ns':2}])
def test_first_command_refuses_invalid_original_dispatch_clock(bad):
    capture,_=build(clock=lambda:10.)
    capture.start('s','attempt-1',1,1.)
    with pytest.raises(ValueError,match='CAPTURE_DISPATCH_CLOCK_INVALID'):
        capture.on_event({'kind':'first_command','sim_time_s':1.,'source_clock':bad})


def test_normal_motion_end_keeps_original_tail_but_prohibits_future_action_labels():
    ticks={'now':0.}
    capture,minter=build(clock=lambda:ticks['now'])
    start(capture)
    frames_at(capture,minter,[1.,1.1,1.2])
    for target in (1.1,1.2):capture.on_reference(reference(target))
    assert capture.drain()==1
    boundary={'sim_time_ns':1_250_000_000,'begin_monotonic_ns':1,'end_monotonic_ns':2}
    ticks['now']=.01
    mark=getattr(capture,'on_normal_motion_end',None)
    assert callable(mark),'confirmed normal motion end cannot retain a causal endpoint tail'
    mark(boundary)
    ticks['now']=200.
    frames_at(capture,minter,[1.3,1.4])
    assert capture.drain()==1
    assert capture.reference_requests(1.4)==()
    assert capture.window['physics_end_s']==1.25 and capture.window['collection_end_s']==1.4
    assert [row['observation']['sim_time_s'] for row in capture.recorder.rows]==[1.,1.1]
    summary=capture.finish(1.25)
    assert summary.sample_count==2 and len(capture.unlabelled_rows)==1


@pytest.mark.parametrize('fault',['duplicate','future','pre_label','changed_end'])
def test_normal_end_cannot_refresh_extend_or_revoke_already_written_labels(fault):
    capture,minter=build(clock=lambda:10.)
    start(capture);frames_at(capture,minter,[1.,1.1,1.2])
    for target in (1.1,1.2):capture.on_reference(reference(target))
    assert capture.drain()==1
    mark=getattr(capture,'on_normal_motion_end',None)
    assert callable(mark),'no exact one-shot normal end boundary exists'
    clock={'sim_time_ns':1_250_000_000,'begin_monotonic_ns':1,'end_monotonic_ns':2}
    if fault=='future':clock['end_monotonic_ns']=11_000_000_000
    if fault=='pre_label':clock['sim_time_ns']=1_100_000_000
    if fault in ('duplicate','changed_end'):mark(clock)
    with pytest.raises(ValueError,match='CAPTURE_NORMAL_END|CAPTURE_LABEL_REVOKED'):
        if fault=='changed_end':capture.finish(1.3)
        else:mark(clock)


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


def test_a_long_run_retires_completed_rows_and_references():
    """A continuous episode must not be bounded by the pending join (T2-F1 residual)."""

    capture, minter = build()                        # default capacities: 32 pending, 128 references
    start(capture)
    for index in range(60):
        stamp = round(1.0 + index * 0.1, 6)
        frames_at(capture, minter, [stamp])
        capture.on_reference(reference(round(stamp + 0.1, 6)))
        capture.drain()
    summary = capture.finish(round(1.0 + 60 * 0.1, 6))
    assert summary.sample_count >= 59                # every row whose instant provably passed
    assert capture.pending_rows <= 2
    assert len(capture._references) <= 2


def test_a_future_reference_horizon_is_not_clock_progress():
    """A requested future action instant is not evidence that physics reached it (T2-F2 residual)."""

    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0])
    capture.on_reference(reference(1.1))
    capture.on_reference(reference(1.2))             # a far future query, not clock progress
    assert capture.drain() == 0
    summary = capture.finish(1.05)
    assert summary.sample_count == 0                 # the 1.1 instant never happened
    assert summary.label_cutoff_s == 0.0


def test_a_revocation_after_a_row_was_labelled_fails_the_capture():
    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])      # the camera reaches past 1.1
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1
    with pytest.raises(ValueError, match="CAPTURE_LABEL_REVOKED"):
        capture.on_reference(reference(1.1, accepted=False))
    with pytest.raises(ValueError, match="CAPTURE_LABEL_REVOKED"):
        capture.finish(1.3)


def test_a_receipt_integrity_failure_is_terminal():
    capture, minter = build()
    start(capture)
    frame = minter.mint("head", session_id="s", reset_epoch=1, stamp_s=1.0,
                        received_monotonic_ns=1, pixels=ZERO)
    with pytest.raises(ValueError, match="ACQUISITION_PIXEL_MISMATCH"):
        capture.on_acquisition(frame, np.ones((480, 640, 3), dtype=np.uint8))
    # valid data afterwards must not resurrect a corrupted episode
    with pytest.raises(ValueError, match="ACQUISITION_PIXEL_MISMATCH"):
        frames_at(capture, minter, [1.1])
    with pytest.raises(ValueError, match="ACQUISITION_PIXEL_MISMATCH"):
        capture.drain()
    with pytest.raises(ValueError, match="ACQUISITION_PIXEL_MISMATCH"):
        capture.finish(1.2)


def test_an_invalid_reference_is_terminal_too():
    capture, minter = build()
    start(capture)
    with pytest.raises(ValueError, match="CAPTURE_REFERENCE_INVALID"):
        capture.on_reference({"source": "CONTROLLER_REFERENCE", "requested_sim_time_s": 1.1,
                              "positions": [0.0] * 5, "accepted": True})
    with pytest.raises(ValueError, match="CAPTURE_REFERENCE_INVALID"):
        capture.on_reference(reference(1.1))
    with pytest.raises(ValueError, match="CAPTURE_REFERENCE_INVALID"):
        capture.finish(1.2)


def test_a_delayed_stop_invalidates_an_already_written_label():
    """A stop delivered after the label still voids the action instant it covers (T2-F2 residual)."""

    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1
    with pytest.raises(ValueError, match="CAPTURE_LABEL_REVOKED"):
        capture.on_event({"kind": "stop", "sim_time_s": 1.05})
    with pytest.raises(ValueError, match="CAPTURE_LABEL_REVOKED"):
        capture.finish(1.3)


def test_a_stop_after_every_labelled_instant_is_a_normal_stop():
    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1
    capture.on_event({"kind": "stop", "sim_time_s": 1.5})
    summary = capture.finish(1.6)
    assert summary.sample_count == 1
    assert summary.label_cutoff_s == 1.0


def test_a_wrong_shaped_pixel_array_is_terminal():
    capture, minter = build()
    start(capture)
    frame = minter.mint("head", session_id="s", reset_epoch=1, stamp_s=1.0,
                        received_monotonic_ns=1, pixels=ZERO)
    with pytest.raises(ValueError, match="ACQUISITION_PIXELS_INVALID"):
        capture.on_acquisition(frame, np.zeros((480, 640), dtype=np.uint8))
    with pytest.raises(ValueError, match="ACQUISITION_PIXELS_INVALID"):
        frames_at(capture, minter, [1.1])
    with pytest.raises(ValueError, match="ACQUISITION_PIXELS_INVALID"):
        capture.finish(1.2)


def test_a_non_numeric_reference_position_is_terminal():
    capture, minter = build()
    start(capture)
    with pytest.raises(ValueError, match="CAPTURE_REFERENCE_INVALID"):
        capture.on_reference(reference(1.1, positions=[0.0, 0.1, 0.2, 0.3, 0.4, "x"]))
    with pytest.raises(ValueError, match="CAPTURE_REFERENCE_INVALID"):
        capture.on_reference(reference(1.1))
    with pytest.raises(ValueError, match="CAPTURE_REFERENCE_INVALID"):
        capture.drain()


def test_a_wrong_shaped_selected_image_is_terminal():
    """A malformed image from the sampler must latch the first reason, like the receipt path."""

    capture, minter = build(sampler_pixels=np.zeros((480, 640), dtype=np.uint8))
    start(capture)
    frames_at(capture, minter, [1.0])                # valid receipts with matching stamps
    capture.on_reference(reference(1.1))
    frames_at(capture, minter, [1.1])
    with pytest.raises(ValueError, match="ACQUISITION_PIXELS_INVALID"):
        capture.drain()
    # the original reason survives: later callbacks, drain and finish all refuse with it
    with pytest.raises(ValueError, match="ACQUISITION_PIXELS_INVALID"):
        capture.on_reference(reference(1.2))
    with pytest.raises(ValueError, match="ACQUISITION_PIXELS_INVALID"):
        frames_at(capture, minter, [1.2])
    with pytest.raises(ValueError, match="ACQUISITION_PIXELS_INVALID"):
        capture.finish(1.3)


class RaisingSampler(FakeSampler):
    def __init__(self, error):
        super().__init__()
        self.error = error

    def sample_with_audit(self, *args, **kwargs):
        raise self.error


class RejectingRecorder(FakeRecorder):
    def __init__(self, error):
        super().__init__()
        self.error = error

    def append(self, *args, **kwargs):
        raise self.error


@pytest.mark.parametrize("code", ("INPUT_STALE", "INPUT_SKEW"))
def test_a_sampler_refusal_is_terminal_and_keeps_its_reason(code):
    """The production synchronizer refuses with INPUT_STALE/INPUT_SKEW; that must latch."""

    capture, minter = build()
    capture.sampler = RaisingSampler(ValueError(code))
    start(capture)
    frames_at(capture, minter, [1.0])
    with pytest.raises(ValueError, match=code):
        capture.drain()
    with pytest.raises(ValueError, match=code):
        capture.on_reference(reference(1.1))
    with pytest.raises(ValueError, match=code):
        frames_at(capture, minter, [1.1])
    with pytest.raises(ValueError, match=code):
        capture.finish(1.2)


@pytest.mark.parametrize("code", ("EPISODE_SCOPE_INVALID", "RECORDER_WRITE_FAILED"))
def test_a_recorder_refusal_is_terminal_and_loses_no_row(code):
    """A rejected row must not vanish from pending work, and the reason must survive."""

    capture, minter = build()
    capture.recorder = RejectingRecorder(ValueError(code))
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])     # the camera reaches past the 1.1 instant
    capture.on_reference(reference(1.1))
    with pytest.raises(ValueError, match=code):
        capture.drain()
    assert capture.pending_rows >= 1 and capture.recorder.rows == []
    with pytest.raises(ValueError, match=code):
        capture.drain()
    with pytest.raises(ValueError, match=code):
        capture.finish(1.3)


class ReferenceAudit:
    def __init__(self):
        self.references = []

    def append_source(self, kind, record):
        assert kind == "references"
        self.references.append(record)

    def append_acquisition(self, frame):
        pass

    def bind_row(self, *values):
        pass


def test_the_audit_keeps_the_raw_reference_history_including_revocations():
    audit = ReferenceAudit()
    capture, minter = build()
    capture.audit = audit
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.1))
    capture.on_reference(reference(1.1, accepted=False))
    capture.on_reference(reference(1.2))
    assert audit.references == []
    capture.drain()
    assert [row["accepted"] for row in audit.references] == [True, False, True]
    assert [row["reference_time_s"] for row in audit.references] == [1.1, 1.1, 1.2]
    assert all(row["source"] == "CONTROLLER_REFERENCE" for row in audit.references)
    assert all(len(row["positions"]) == 6 for row in audit.references)


def test_an_invalid_reference_never_reaches_the_audit():
    audit = ReferenceAudit()
    capture, minter = build()
    capture.audit = audit
    start(capture)
    with pytest.raises(ValueError, match="CAPTURE_REFERENCE_INVALID"):
        capture.on_reference(reference(1.1, positions=[0.0, 0.1, 0.2, 0.3, 0.4, "x"]))
    assert audit.references == []


def test_a_refusing_tail_writer_is_reported_by_every_later_call():
    """Finalization must not be declared before the tail handoff succeeded (Task 2 minor)."""

    def refusing_writer(observation, audit):
        raise ValueError("AUDIT_WRITE_FAILED")

    capture, minter = build(audit_writer=refusing_writer)
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1
    for call in (lambda: capture.finish(1.4), lambda: capture.finish(1.4), capture.drain,
                 lambda: capture.on_reference(reference(1.5)),
                 lambda: feed(capture, minter, camera="head", stamp_s=1.5)):
        with pytest.raises(ValueError, match="AUDIT_WRITE_FAILED"):
            call()


def test_an_expired_budget_does_not_replace_the_first_failure():
    ticks = {"now": 0.0}
    capture, minter = build(deadline_s=120.0, clock=lambda: ticks["now"])
    start(capture)
    frames_at(capture, minter, [1.0])
    feed(capture, minter, camera="head", stamp_s=1.1)      # only the head moved on
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.drain()
    ticks["now"] = 999.0
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.on_event({"kind": "phase", "sim_time_s": 9.0})
    with pytest.raises(ValueError, match="NO_NEW_ACQUISITION"):
        capture.finish(1.4)


class RawReferenceAudit:
    def __init__(self):
        self.references = []

    def append_source(self, kind, record):
        assert kind == "references"
        self.references.append(record)

    def append_acquisition(self, frame):
        pass

    def bind_row(self, *values):
        pass


def test_the_observer_raw_frame_reaches_the_audit_when_it_is_supplied():
    """A reference message carrying the observer's raw frame must not lose it (T3-F1)."""

    audit = RawReferenceAudit()
    capture, minter = build()
    capture.audit = audit
    start(capture)
    frames_at(capture, minter, [1.0])
    raw = {"joint_names": ["shoulder_pan", "shoulder_lift"], "sim_stamp_ns": 1100000000,
           "received_monotonic_ns": 900000, "velocities": [0.0, 0.0]}
    capture.on_reference({**reference(1.1), **raw})
    capture.on_reference(reference(1.2))
    assert audit.references == []
    capture.drain()
    assert audit.references[0]["joint_names"] == raw["joint_names"]
    assert audit.references[0]["sim_stamp_ns"] == raw["sim_stamp_ns"]
    assert "joint_names" not in audit.references[1]


class _RawReferencePort:
    def __init__(self, document):
        self.document = document

    def reference_state(self, target):
        return {**self.document, "requested_sim_time_s": target}


def test_the_expert_tap_preserves_the_raw_frame_its_port_supplies():
    from so101_demo.act.expert import MoveItExpertActionTap

    raw = {"joint_names": ["shoulder_pan", "shoulder_lift"], "sim_stamp_ns": 1100000000,
           "received_monotonic_ns": 900000, "velocities": [0.0, 0.0]}
    tap = MoveItExpertActionTap(_RawReferencePort(
        {"source": "CONTROLLER_REFERENCE", "positions": [0.1] * 6, **raw}))
    document = tap.reference(1.0)
    assert document["joint_names"] == raw["joint_names"]
    assert document["sim_stamp_ns"] == raw["sim_stamp_ns"]
    assert document["requested_sim_time_s"] == 1.1
    plain = MoveItExpertActionTap(_RawReferencePort(
        {"source": "CONTROLLER_REFERENCE", "positions": [0.1] * 6})).reference(1.0)
    assert "joint_names" not in plain
    with pytest.raises(ValueError, match="EXPERT_REFERENCE_RAW_INCOMPLETE"):
        MoveItExpertActionTap(_RawReferencePort(
            {"source": "CONTROLLER_REFERENCE", "positions": [0.1] * 6,
             "joint_names": ["a", "b"]})).reference(1.0)


def test_the_capture_reports_only_the_window_facts_it_observed():
    """A fact that never happened is null rather than an invented instant (Proposal B)."""

    capture, minter = build()
    start(capture)
    frames_at(capture, minter, [1.0, 1.1, 1.2])
    capture.on_reference(reference(1.1))
    assert capture.drain() == 1
    capture.finish(1.4)
    window = capture.window
    assert window["collection_start_s"] == 1.0
    assert window["collection_end_s"] == 1.4
    assert window["first_command_s"] == 1.0
    assert window["physics_end_s"] == 1.4
    assert window["label_cutoff_s"] == 1.0

    silent, no_minter = build()
    silent.start("s", "attempt-1", 1, 1.0)
    quiet = silent.window
    assert quiet["first_command_s"] is None and quiet["label_cutoff_s"] is None
    assert quiet["physics_end_s"] is None and quiet["collection_start_s"] is None


def test_the_capture_forwards_the_ratified_packed_reference_shape():
    """Proposal A: the packed frames/evaluation group must reach the audit unchanged."""

    from test_act_episode_audit import _ratified_reference

    audit = RawReferenceAudit()
    capture, minter = build()
    capture.audit = audit
    start(capture)
    frames_at(capture, minter, [1.0])
    capture.on_reference({**reference(1.1), **_ratified_reference()})
    assert audit.references == []
    capture.drain()
    recorded = audit.references[0]
    assert set(recorded["frames"]) == {"arm", "gripper"}
    assert recorded["frames"]["gripper"]["observer_sequence"] == 7
    assert recorded["projection_map"][-1] == ["gripper", 0]
    # A.1: the evaluation lives inside the frame, so no record-level evaluation may be forwarded
    assert "evaluation" not in recorded
    assert recorded["frames"]["arm"]["evaluation"]["requested_sim_time_s"] == 1.1
    assert recorded["frames"]["arm"]["published_positions"] == \
        recorded["frames"]["arm"]["evaluated_positions"]


def test_a_capture_driven_to_its_seal_binds_the_audit_the_endpoint_qc_reads(tmp_path):
    """E2 correction 2 end to end: the capture seals its audit and the episode carries it.

    Three things the earlier attempts lacked: the writer and the recorder get different roots (each creates its own
    with exist_ok=False), the frozen scope document is written to a file first, and the recorder is handed that file's
    path because its finish() converts its arguments with Path(...) and cross-checks the file against the episode.
    """

    import json


    from so101_demo.act.episode_audit import EpisodeAuditWriter, verify_audit_manifest
    from so101_demo.act import episode_qc
    from so101_demo.act.recorder import EpisodeRecorder
    from test_act_recorder import PROVENANCE

    scope = {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1, "mode": "preselected_target_diagnostic",
             "scene_id": "default", "seed": 0, "inputs_sha256": "a" * 64}
    identity = {"session_id": "s", "attempt_id": "attempt-1", "reset_epoch": 1, "release_epoch": 1,
                "scene_id": "default", "seed": 0, "mode": "preselected_target_diagnostic"}
    sealed = []

    class RecordingAudit(EpisodeAuditWriter):
        def seal(self, window):
            path = super().seal(window)
            sealed.append(path)
            return path

    audit_root = tmp_path / "audit-root"
    audit = RecordingAudit(audit_root, scope, identity, {"inputs_sha256": "a" * 64})
    # the recorder cross-checks the scope file against the audit's own payload byte for byte, so the file it is
    # handed IS the audit's source.json
    scope_path = audit_root / "audit" / "source.json"
    assert scope_path.is_file()
    recorder = EpisodeRecorder(tmp_path / "episode", session_id="s", attempt_id="attempt-1",
                               reset_epoch=1, provenance=PROVENANCE)
    capture = ContinuousEpisodeCapture(
        recorder=recorder, sampler=FakeSampler(), guard=AcquisitionGuard(),
        physical_audit=physical_audit, audit=audit, scope=str(scope_path),
        deadline_s=120.0, monotonic=lambda: 0.0)
    minter = AcquisitionMinter()
    capture.start("s", "attempt-1", 1, 1.0)
    frames_at(capture, minter, (1.0, 1.1, 1.2))
    capture.finish(1.2, window={"start_s": 1.0, "end_s": 1.2, "label_cutoff_s": 1.2},
                   outcome={"status": "FAILED", "reason": "search_failed",
                            "pick_place_validation_success": False, "stopped_confirmed": True})
    print("SEALED audit:", [str(p) for p in sealed])
    assert sealed, "the capture must seal the audit it was given"
    manifest_path = Path(sealed[0])
    assert verify_audit_manifest(manifest_path)["kind"] == "ACT_EPISODE_AUDIT"
    # QC no longer carries an endpoint_pose_v1 document; the sealed audit is checked for data integrity and, with no
    # Teacher manifest beside it, the Teacher-reference cross-check names that absence instead of passing
    manifest = verify_audit_manifest(manifest_path)
    check = episode_qc.verify_teacher_references(None, identity=manifest["identity"], window=manifest["window"],
                                                 physics_steps=[])
    print("EPISODE QC reference check:", check["status"], check["reason"])
    assert check["status"] == "FAIL" and check["reason"] == "TEACHER_REFERENCE_MANIFEST_MISSING"
    assert not hasattr(episode_qc, "endpoint_qc_document")
