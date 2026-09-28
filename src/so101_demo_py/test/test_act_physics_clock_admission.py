"""Broker-owned clock admission: identity scope, irreversible revocation, re-fencing."""

import threading
import time

import pytest

from so101_demo.adapters.act.physics_clock_admission import (
    AdmissionRefused, PhysicsClockAdmission,
)
from so101_demo.adapters.act.physics_clock_history import PhysicsClockHistory

from test_act_physics_clock_history import NOW_NS, SOURCE_BASE_NS, STEP_NS, _chunk, _sample


def _history(now, *, max_age_s=.35, max_silence_s=.30, first_chunk_timeout_s=.40):
    history = PhysicsClockHistory(
        "clock-session", nq=2, nv=1, max_age_s=max_age_s,
        max_source_step_gap_ns=3_000_000, max_silence_s=max_silence_s,
        first_chunk_timeout_s=first_chunk_timeout_s, clock_ns=lambda: now[0])
    history.arm(1, source_floor_s=0.0)
    return history


def _admission(now, *, selected_max_age_s=.10, history=None):
    history = history or _history(now)
    admission = PhysicsClockAdmission(
        history, selected_max_age_s=selected_max_age_s, clock_ns=lambda: now[0])
    return history, admission


def _identity(admission):
    return admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)


def test_identity_is_required_and_strictly_newer_before_rearming():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    with pytest.raises(AdmissionRefused):
        admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="proof")
    _identity(admission)
    with pytest.raises(AdmissionRefused):
        admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    with pytest.raises(AdmissionRefused):
        admission.arm(ticket="ticket-1", generation=6, reset_epoch=1)
    assert admission.arm(ticket="ticket-1", generation=8, reset_epoch=1) == (
        "ticket-1", 8, 1)


def test_revocation_is_irreversible_and_carries_the_identity():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _admission(now)
    identity = _identity(admission)
    history.accept_chunk(_chunk(0, _sample(1)))
    admission.note_hazard("PHYSICS_CLOCK_SILENT")
    record = admission.revoked_record
    assert record["reason"] == "PHYSICS_CLOCK_SILENT"
    assert record["identity"] == identity
    assert record["expiry"] is True
    for stage in ("proof", "permit", "submit", "final_acceptance", "sample"):
        with pytest.raises(AdmissionRefused):
            admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage=stage)
    # A later hazard cannot replace the first one for the same identity.
    admission.note_hazard("PHYSICS_CLOCK_CALLBACK_INVALID")
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_SILENT"
    # Only a strictly newer identity clears revocation.
    admission.arm(ticket="ticket-1", generation=8, reset_epoch=1)
    assert admission.revoked_record is None


def test_every_stage_refences_the_current_identity():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _admission(now)
    _identity(admission)
    history.accept_chunk(_chunk(0, _sample(1)))
    assert admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="proof")
    assert admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="permit")
    assert admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="submit")
    assert admission.fence(ticket="ticket-1", generation=7, reset_epoch=1,
                           stage="final_acceptance")
    with pytest.raises(AdmissionRefused):
        admission.fence(ticket="ticket-2", generation=7, reset_epoch=1, stage="submit")
    with pytest.raises(AdmissionRefused):
        admission.fence(ticket="ticket-1", generation=7, reset_epoch=2, stage="submit")


def test_revocation_is_not_blocked_by_a_running_checker():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    _identity(admission)
    entered = threading.Event()
    release = threading.Event()
    outcome = {}

    def blocking_checker():
        entered.set()
        release.wait(5.0)
        return "checked"

    def run_stage():
        try:
            outcome["result"] = admission.run_checked_stage(
                ticket="ticket-1", generation=7, reset_epoch=1, stage="proof",
                checker=blocking_checker)
        except AdmissionRefused as error:
            outcome["refused"] = str(error)

    worker = threading.Thread(target=run_stage)
    worker.start()
    assert entered.wait(5.0)
    began = time.monotonic()
    admission.note_hazard("PHYSICS_CLOCK_STALE")
    revoke_elapsed = time.monotonic() - began
    release.set()
    worker.join(5.0)
    assert revoke_elapsed < 0.1, revoke_elapsed
    assert "refused" in outcome and "result" not in outcome
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_STALE"


def test_partial_submit_cancels_and_requires_a_confirmed_stop():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    identity = _identity(admission)
    cancelled = []
    admission.record_partial_submit(
        ticket="ticket-1", generation=7, reset_epoch=1,
        accepted_routes=("arm",), rejected_routes=("gripper",),
        cancel=lambda routes: cancelled.append(tuple(routes)))
    assert cancelled == [("arm",)]
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_PARTIAL_SUBMIT"
    assert admission.stop_confirmed is False
    with pytest.raises(AdmissionRefused):
        admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="submit")
    with pytest.raises(AdmissionRefused):
        admission.confirm_stop(identity=("ticket-1", 8, 1), stopped=True)
    admission.confirm_stop(identity=identity, stopped=True)
    assert admission.stop_confirmed is True
    assert admission.revoked_record["confirmed_stop_monotonic_ns"] is not None


def test_expiry_to_confirmed_stop_is_measured_separately():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    identity = _identity(admission)
    admission.note_hazard("PHYSICS_CLOCK_SILENT")
    revoked_ns = admission.revoked_record["monotonic_ns"]
    now[0] = revoked_ns + 40_000_000
    admission.confirm_stop(identity=identity, stopped=True)
    assert admission.revoked_record["expiry_to_stop_ns"] == 40_000_000
    assert admission.stop_confirmed is True


def test_selected_state_freshness_is_tighter_than_ingestion_freshness():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _admission(now, selected_max_age_s=.05)
    _identity(admission)
    history.accept_chunk(_chunk(0, _sample(1)))
    last_end_ns = history._last_source_end_ns
    now[0] = last_end_ns + 20_000_000            # fresh for ingestion, fresh for selection
    admitted = admission.admit_sample(
        sample=history.step_at(1)["sample"],
        ticket="ticket-1", generation=7, reset_epoch=1)
    assert admitted["command_authority"] is False
    now[0] = last_end_ns + 80_000_000            # still fresh for ingestion, stale for selection
    with pytest.raises(AdmissionRefused):
        admission.admit_sample(
            sample=history.step_at(1)["sample"],
            ticket="ticket-1", generation=7, reset_epoch=1)
    assert admission.revoked_record is None      # a refusal is not a hazard

