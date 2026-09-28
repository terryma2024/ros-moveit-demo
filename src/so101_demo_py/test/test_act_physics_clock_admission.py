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
    identity = _identity(admission)
    with pytest.raises(AdmissionRefused):
        admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    with pytest.raises(AdmissionRefused):
        admission.arm(ticket="ticket-1", generation=6, reset_epoch=1)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_TAKEOVER_BLOCKED"):
        admission.arm(ticket="ticket-1", generation=8, reset_epoch=1)
    admission.retire(identity=identity, stop_evidence=_retire_evidence(identity, now))
    assert admission.arm(ticket="ticket-1", generation=8, reset_epoch=1) == (
        "ticket-1", "clock-session", "clock-session", 8, 1)


def test_revocation_is_irreversible_and_carries_the_identity():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _admission(now)
    identity = _identity(admission)
    history.accept_chunk(_chunk(0, _sample(1)))
    admission.note_hazard("PHYSICS_CLOCK_SILENT", origin_identity=admission.identity)
    record = admission.revoked_record
    assert record["reason"] == "PHYSICS_CLOCK_SILENT"
    assert record["identity"] == identity
    assert record["expiry"] is True
    for stage in ("proof", "permit", "submit", "final_acceptance", "sample"):
        with pytest.raises(AdmissionRefused):
            admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage=stage)
    # A later hazard cannot replace the first one for the same identity.
    admission.note_hazard("PHYSICS_CLOCK_CALLBACK_INVALID", origin_identity=admission.identity)
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_SILENT"
    # Only a strictly newer identity clears revocation, and only after the old
    # target has been authoritatively stopped.
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_TAKEOVER_BLOCKED"):
        admission.arm(ticket="ticket-1", generation=8, reset_epoch=1)
    admission.confirm_stop(identity=identity, stopped=True, evidence=_stop_evidence(identity, now))
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
                side_effect_free=True, checker=blocking_checker)
        except AdmissionRefused as error:
            outcome["refused"] = str(error)

    worker = threading.Thread(target=run_stage)
    worker.start()
    assert entered.wait(5.0)
    began = time.monotonic()
    admission.note_hazard("PHYSICS_CLOCK_STALE", origin_identity=admission.identity)
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
        cancel=lambda routes: cancelled.append(tuple(routes)) or True)
    assert cancelled == [("arm",)]
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_PARTIAL_SUBMIT"
    assert admission.stop_confirmed is False
    with pytest.raises(AdmissionRefused):
        admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="submit")
    with pytest.raises(AdmissionRefused):
        admission.confirm_stop(identity=("ticket-1", "clock-session", "clock-session", 8, 1), stopped=True, evidence=_stop_evidence(("ticket-1", "clock-session", "clock-session", 8, 1), now))
    admission.confirm_stop(identity=identity, stopped=True, evidence=_stop_evidence(identity, now))
    assert admission.stop_confirmed is True
    assert admission.revoked_record["confirmed_stop_monotonic_ns"] is not None


def test_expiry_to_confirmed_stop_is_measured_separately():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    identity = _identity(admission)
    admission.note_hazard("PHYSICS_CLOCK_SILENT", origin_identity=admission.identity)
    revoked_ns = admission.revoked_record["monotonic_ns"]
    now[0] = revoked_ns + 40_000_000
    admission.confirm_stop(identity=identity, stopped=True, evidence=_stop_evidence(identity, now))
    assert admission.revoked_record["revoke_to_stop_record_ns"] >= 40_000_000
    assert admission.stop_confirmed is True


def test_selected_state_freshness_is_tighter_than_ingestion_freshness():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _admission(now, selected_max_age_s=.05)
    admission.arm(ticket="clock-session", generation=1, reset_epoch=1)
    history.accept_chunk(_chunk(0, _sample(1)))
    last_end_ns = history._last_source_end_ns
    now[0] = last_end_ns + 20_000_000            # fresh for ingestion, fresh for selection
    admitted = admission.admit_sample(
        sample=history.step_at(1)["sample"],
        ticket="clock-session", generation=1, reset_epoch=1)
    assert admitted["command_authority"] is False
    now[0] = last_end_ns + 80_000_000            # still fresh for ingestion, stale for selection
    with pytest.raises(AdmissionRefused):
        admission.admit_sample(
            sample=history.step_at(1)["sample"],
            ticket="clock-session", generation=1, reset_epoch=1)
    assert admission.revoked_record is None      # a refusal is not a hazard



def _current(admission):
    return admission.identity


def test_delayed_hazard_from_an_old_identity_does_not_revoke_the_new_one():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    old = admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    admission.retire(identity=old, stop_evidence=_retire_evidence(old, now))
    new = admission.arm(ticket="ticket-1", generation=8, reset_epoch=1)
    record = admission.note_hazard("PHYSICS_CLOCK_SILENT", origin_identity=old)
    assert record["applied"] is False
    assert admission.revoked_record is None
    assert admission.stale_hazards[-1]["origin_identity"] == old
    assert admission.stale_hazards[-1]["current_identity"] == new
    assert admission.fence(ticket="ticket-1", generation=8, reset_epoch=1, stage="proof")


def test_hazard_with_the_current_origin_identity_still_revokes():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    identity = admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    record = admission.note_hazard("PHYSICS_CLOCK_STALE", origin_identity=identity)
    assert record["applied"] is True
    assert record["identity"] == identity
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_STALE"


def test_revocation_triggered_before_the_commit_check_refuses_the_checked_stage():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    base_clock = admission._clock_ns
    state = {"armed": False}

    def revoking_clock():
        if state["armed"]:
            state["armed"] = False
            admission.note_hazard("PHYSICS_CLOCK_SILENT", origin_identity=admission.identity)
        return base_clock()

    admission._clock_ns = revoking_clock
    state["armed"] = True                     # fires inside the commit critical section
    with pytest.raises(AdmissionRefused):
        admission.run_checked_stage(ticket="ticket-1", generation=7, reset_epoch=1,
                                    stage="proof", side_effect_free=True,
                                    checker=lambda: "checked")
    assert admission.checked_stages == 0
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_SILENT"


def test_revocation_after_the_commit_keeps_the_result_and_closes_the_identity():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    assert admission.run_checked_stage(ticket="ticket-1", generation=7, reset_epoch=1,
                                       stage="proof", side_effect_free=True,
                                       checker=lambda: "checked") == "checked"
    assert admission.checked_stages == 1
    admission.note_hazard("PHYSICS_CLOCK_SILENT", origin_identity=admission.identity)
    with pytest.raises(AdmissionRefused):
        admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="permit")


def test_sample_revoked_before_the_age_check_is_refused():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _admission(now)
    admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    history.accept_chunk(_chunk(0, _sample(1)))
    sample = history.step_at(1)["sample"]
    base_clock = admission._clock_ns
    state = {"armed": False}

    def revoking_clock():
        if state["armed"]:
            state["armed"] = False
            admission.note_hazard("PHYSICS_CLOCK_STALE", origin_identity=admission.identity)
        return base_clock()

    admission._clock_ns = revoking_clock
    state["armed"] = True
    with pytest.raises(AdmissionRefused):
        admission.admit_sample(sample=sample, ticket="ticket-1", generation=7, reset_epoch=1)
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_STALE"


@pytest.mark.parametrize("ticket,generation,epoch,accepted", [
    ("ticket-1", 7, 1, False),        # same identity
    ("ticket-0", 6, 1, False),        # older ticket and generation
    ("ticket-9", 8, 1, True),         # ticket rotation with a newer generation
    ("ticket-9", 7, 1, False),        # ticket rotation may not keep the generation
    ("ticket-1", 7, 2, True),         # same generation, newer reset epoch
    ("ticket-1", 7, 0, False),        # epoch rollback
    ("ticket-1", 8, 1, True),         # newer generation
    ("", 8, 1, False),                # empty ticket
    ("ticket-1", -1, 1, False),       # negative generation
])
def test_identity_successor_semantics_are_explicit(ticket, generation, epoch, accepted):
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    current = admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    if accepted:
        admission.retire(identity=current,
                         stop_evidence=_retire_evidence(current, now))
        assert admission.arm(ticket=ticket, generation=generation, reset_epoch=epoch) == (
            "clock-session" if False else (ticket, "clock-session", "clock-session",
                                           generation, epoch))
    else:
        with pytest.raises(AdmissionRefused):
            admission.arm(ticket=ticket, generation=generation, reset_epoch=epoch)


def test_partial_cancel_failure_is_fail_closed():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    identity = admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)

    def raising_cancel(_routes):
        raise RuntimeError("cancel failed")

    admission.record_partial_submit(ticket="ticket-1", generation=7, reset_epoch=1,
                                    accepted_routes=("arm",), rejected_routes=("gripper",),
                                    cancel=raising_cancel)
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_PARTIAL_CANCEL_FAILED"
    assert admission.stop_confirmed is False
    with pytest.raises(AdmissionRefused):
        admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="submit")

    now2 = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission2 = _admission(now2)
    admission2.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    admission2.record_partial_submit(ticket="ticket-1", generation=7, reset_epoch=1,
                                     accepted_routes=("arm",), rejected_routes=("gripper",),
                                     cancel=lambda _routes: False)
    assert admission2.revoked_record["reason"] == "PHYSICS_CLOCK_PARTIAL_CANCEL_FAILED"
    assert admission2.stop_confirmed is False

    now3 = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission3 = _admission(now3)
    identity3 = admission3.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    admission3.record_partial_submit(ticket="ticket-1", generation=7, reset_epoch=1,
                                     accepted_routes=("arm",), rejected_routes=("gripper",),
                                     cancel=lambda _routes: True)
    assert admission3.revoked_record["reason"] == "PHYSICS_CLOCK_PARTIAL_SUBMIT"
    assert admission3.stop_confirmed is False
    with pytest.raises(AdmissionRefused):
        admission3.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="submit")
    admission3.confirm_stop(identity=identity3, stopped=True, evidence=_stop_evidence(identity3, now))
    assert admission3.stop_confirmed is True



def test_hazard_without_origin_identity_is_refused_and_does_not_revoke():
    """A caller omission must never recreate the delayed-old-callback failure."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    identity = admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_ORIGIN_IDENTITY_REQUIRED"):
        admission.note_hazard("PHYSICS_CLOCK_SILENT")
    assert admission.revoked_record is None
    assert admission.stale_hazards == []
    assert admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="proof")
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_ORIGIN_IDENTITY_REQUIRED"):
        admission.note_hazard("PHYSICS_CLOCK_SILENT", origin_identity=None)
    assert admission.revoked_record is None
    assert admission.identity == identity


def test_administrative_revoke_current_is_explicit_and_irreversible():
    """The broker's synchronous current-identity revoke is a separate, named API."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_UNARMED"):
        admission.revoke_current("PHYSICS_CLOCK_OPERATOR_STOP")
    identity = admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    record = admission.revoke_current("PHYSICS_CLOCK_OPERATOR_STOP")
    assert record["applied"] is True
    assert record["identity"] == identity
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_OPERATOR_STOP"
    admission.revoke_current("PHYSICS_CLOCK_SILENT")
    assert admission.revoked_record["reason"] == "PHYSICS_CLOCK_OPERATOR_STOP"
    with pytest.raises(AdmissionRefused):
        admission.fence(ticket="ticket-1", generation=7, reset_epoch=1, stage="permit")


def _ready(now, *, selected_max_age_s=.20):
    history, admission = _admission(now, selected_max_age_s=selected_max_age_s)
    admission.arm(ticket="clock-session", generation=1, reset_epoch=1)
    history.accept_chunk(_chunk(0, _sample(1)))
    return history, admission


def test_takeover_is_refused_while_the_old_target_is_not_confirmed_stopped():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    admission.arm(ticket="ticket-1", generation=7, reset_epoch=9)
    entered = threading.Event()
    release = threading.Event()
    outcome = {}

    def blocking_cancel(_routes):
        entered.set()
        release.wait(5.0)
        return True

    def run_partial():
        try:
            admission.record_partial_submit(
                ticket="ticket-1", generation=7, reset_epoch=9,
                accepted_routes=("arm",), rejected_routes=("gripper",), cancel=blocking_cancel)
        except BaseException as error:  # noqa: BLE001
            outcome["error"] = repr(error)

    worker = threading.Thread(target=run_partial)
    worker.start()
    assert entered.wait(5.0)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_TAKEOVER_BLOCKED"):
        admission.arm(ticket="ticket-1", generation=8, reset_epoch=9)
    release.set()
    worker.join(5.0)
    assert outcome.get("error") is None
    assert admission.revoked_record["identity"] == ("ticket-1", "clock-session", "clock-session", 7, 9)
    assert admission.stop_confirmed is False
    admission.confirm_stop(identity=("ticket-1", "clock-session", "clock-session", 7, 9), stopped=True, evidence=_stop_evidence(("ticket-1", "clock-session", "clock-session", 7, 9), now))
    assert admission.arm(ticket="ticket-1", generation=8, reset_epoch=9) == (
        "ticket-1", "clock-session", "clock-session", 8, 9)


def test_same_session_epoch_rollback_is_rejected():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_IDENTITY_NOT_NEWER"):
        owner = admission.arm(ticket="ticket-1", generation=7, reset_epoch=9)
        admission.retire(identity=owner, stop_evidence=_retire_evidence(owner, now))
        admission.arm(ticket="ticket-1", generation=8, reset_epoch=1)


def test_broker_ticket_rotation_within_one_incarnation_keeps_the_epoch():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    current = admission.arm(ticket="ticket-1", generation=7, reset_epoch=9)
    admission.retire(identity=current, stop_evidence=_retire_evidence(current, now))
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_IDENTITY_NOT_NEWER"):
        admission.arm(ticket="ticket-9", generation=8, reset_epoch=1)
    assert admission.arm(ticket="ticket-9", generation=8, reset_epoch=9) == (
        "ticket-9", "clock-session", "clock-session", 8, 9)


def test_admission_requires_accepted_history_evidence():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _admission(now)
    admission.arm(ticket="clock-session", generation=1, reset_epoch=1)
    assert history.evidence_ready is False
    sample = _sample(1)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_"):
        admission.admit_sample(sample=sample, ticket="clock-session", generation=1, reset_epoch=1)


def test_admission_refuses_a_foreign_or_unknown_sample_identity():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    foreign = _sample(1)
    foreign.simulation_session_id = "foreign"
    with pytest.raises(AdmissionRefused):
        admission.admit_sample(sample=foreign, ticket="clock-session", generation=1, reset_epoch=1)
    wrong_epoch = _sample(1, epoch=2)
    with pytest.raises(AdmissionRefused):
        admission.admit_sample(sample=wrong_epoch, ticket="clock-session", generation=1,
                               reset_epoch=1)
    unknown_step = _sample(9)
    with pytest.raises(AdmissionRefused):
        admission.admit_sample(sample=unknown_step, ticket="clock-session", generation=1,
                               reset_epoch=1)
    admitted = admission.admit_sample(sample=_sample(1), ticket="clock-session", generation=1,
                                      reset_epoch=1)
    assert admitted["command_authority"] is False
    assert admitted["identity"] == ("clock-session", "clock-session", "clock-session", 1, 1)
    assert admitted["sample"].physics_step == 1


def test_admitted_evidence_is_isolated_from_caller_mutation():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    caller = _sample(1)
    admitted = admission.admit_sample(sample=caller, ticket="clock-session", generation=1,
                                      reset_epoch=1)
    caller.model_qpos[0] = 9.
    caller.physics_step = 999
    assert tuple(admitted["sample"].model_qpos) == (.1, .2)
    assert admitted["sample"].physics_step == 1


def test_history_hazard_closes_every_admission_stage():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    now[0] += 400_000_000
    assert history.check_health() is False          # silence bound expired
    for stage in ("proof", "permit", "submit", "final_acceptance"):
        with pytest.raises(AdmissionRefused):
            admission.fence(ticket="clock-session", generation=1, reset_epoch=1, stage=stage)
    with pytest.raises(AdmissionRefused):
        admission.admit_sample(sample=_sample(1), ticket="clock-session", generation=1, reset_epoch=1)


def test_consume_stage_is_atomic_and_revocation_wins_within_it():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    consumed = []
    assert admission.consume_authority(
            ticket="clock-session", generation=1, reset_epoch=1,
            stage="permit",
            evidence_token=_token(admission._history, 1),
            controller_generation=1)["stage_executed"] == "permit"
    base_clock = admission._clock_ns
    state = {"armed": False}

    def revoking_clock():
        if state["armed"]:
            state["armed"] = False
            admission.revoke_current("PHYSICS_CLOCK_SILENT")
        return base_clock()

    admission._clock_ns = revoking_clock
    state["armed"] = True
    with pytest.raises(AdmissionRefused):
        admission.consume_authority(
            ticket="clock-session", generation=1, reset_epoch=1,
            stage="submit",
            evidence_token=_token(admission._history, 1), controller_generation=1)


def test_checked_stage_must_be_declared_side_effect_free():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _ready(now)
    with pytest.raises(ValueError):
        admission.run_checked_stage(ticket="clock-session", generation=1, reset_epoch=1,
                                    stage="proof", checker=lambda: "x")
    assert admission.run_checked_stage(ticket="clock-session", generation=1, reset_epoch=1,
                                       stage="proof", side_effect_free=True,
                                       checker=lambda: "x") == "x"



def test_active_owner_cannot_be_replaced_without_authoritative_retirement():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    identity = admission.arm(ticket="ticket-1", generation=7, reset_epoch=1)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_TAKEOVER_BLOCKED"):
        admission.arm(ticket="ticket-1", generation=8, reset_epoch=1)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_STOP_EVIDENCE_INVALID"):
        admission.retire(identity=identity, stop_evidence={"stopped": True})
    record = admission.retire(identity=identity,
                              stop_evidence=_retire_evidence(identity, now))
    assert record["identity"] == identity
    assert admission.arm(ticket="ticket-1", generation=8, reset_epoch=1) == identity[:2] + (
        "clock-session", 8, 1)


def test_ticket_session_and_history_incarnation_are_separate():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _admission(now)
    first = admission.arm(ticket="ticket-1", generation=7, reset_epoch=9)
    admission.retire(identity=first, stop_evidence=_retire_evidence(first, now))
    # same history incarnation may not change simulation session or roll the epoch back
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_IDENTITY_NOT_NEWER"):
        admission.arm(ticket="ticket-1", generation=8, reset_epoch=9, session="other-session")
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_IDENTITY_NOT_NEWER"):
        admission.arm(ticket="ticket-1", generation=8, reset_epoch=1)
    # an explicit new history incarnation is the only path that may reset the epoch
    assert admission.arm(ticket="ticket-2", generation=1, reset_epoch=1,
                         incarnation="incarnation-2") == (
        "ticket-2", "clock-session", "incarnation-2", 1, 1)


def test_authority_consume_actively_validates_history_at_its_own_point():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    consumed = []
    # no watchdog poll happens here: the consume itself must detect the expiry
    now[0] = history._last_source_end_ns + 301_000_000
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_HISTORY_UNHEALTHY"):
        admission.consume_authority(
            ticket="clock-session", generation=1, reset_epoch=1,
            stage="submit",
            evidence_token=_token(admission._history, 1), controller_generation=1)
    assert history.hazard == "PHYSICS_CLOCK_SILENT"


def test_authority_consume_refuses_without_accepted_evidence():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _admission(now)
    admission.arm(ticket="clock-session", generation=1, reset_epoch=1)
    assert history.evidence_ready is False
    consumed = []
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_"):
        admission.consume_authority(
            ticket="clock-session", generation=1, reset_epoch=1,
            stage="submit",
            evidence_token=_token(admission._history, 1), controller_generation=1)


def test_controller_generation_is_checked_inside_the_consume_section():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _ready(now)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_CONTROLLER_GENERATION_CHANGED"):
        admission.consume_authority(ticket="clock-session", generation=1, reset_epoch=1,
                                    stage="submit",
                                    evidence_token=_token(admission._history, 1),
                                    controller_generation=99)
    assert admission.consume_authority(
        ticket="clock-session", generation=1, reset_epoch=1, stage="submit",
        evidence_token=_token(admission._history, 1),
        controller_generation=1)["stage_executed"] == "submit"


def test_authority_consume_requires_token_and_controller_generation():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    with pytest.raises((TypeError, ValueError)):
        admission.consume_authority(ticket="clock-session", generation=1, reset_epoch=1,
                                    stage="submit")
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_CONTROLLER_GENERATION_CHANGED"):
        admission.consume_authority(ticket="clock-session", generation=1, reset_epoch=1,
                                    stage="submit", evidence_token=_token(history, 1),
                                    controller_generation=99)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_"):
        admission.consume_authority(ticket="clock-session", generation=1, reset_epoch=1,
                                    stage="submit",
                                    evidence_token=dict(_token(history, 1), incarnation="other"),
                                    controller_generation=1)


def test_admit_sample_rejects_a_history_version_change_at_commit():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    sample = _sample(1)
    original = history.commit_state

    def bumping_snapshot():
        snap = original()
        if not state["bumped"]:
            state["bumped"] = True
            history.accept_chunk(_chunk(1, _sample(2)))   # version changes under us
        return snap

    state = {"bumped": False}
    history.commit_state = bumping_snapshot
    with pytest.raises(AdmissionRefused):
        admission.admit_sample(sample=sample, ticket="clock-session", generation=1, reset_epoch=1)


def test_selected_age_crossing_during_read_is_rejected():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now, selected_max_age_s=.05)
    sample = _sample(1)
    last_end_ns = history._last_source_end_ns
    original_step_at = history.step_at
    reached = {"read": False}

    def slow_step_at(step):
        entry = original_step_at(step)
        reached["read"] = True
        now[0] = last_end_ns + 80_000_000      # the isolated read took 60 ms
        return entry

    history.step_at = slow_step_at
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_SELECTED_STALE"):
        admission.admit_sample(sample=sample, ticket="clock-session", generation=1, reset_epoch=1)
    assert reached["read"] is True


def test_consume_is_atomic_against_revocation_with_a_real_barrier():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    entered = threading.Event()
    release = threading.Event()
    outcome = {}
    original = history.commit_receipt

    def blocking_commit_receipt(**kwargs):
        entered.set()
        release.wait(5.0)
        return original(**kwargs)

    history.commit_receipt = blocking_commit_receipt

    def worker():
        try:
            admission.consume_authority(ticket="clock-session", generation=1, reset_epoch=1,
                                        stage="submit",
                                        evidence_token=_token(history, 1),
                                        controller_generation=1)
            outcome["result"] = "committed"
        except AdmissionRefused as error:
            outcome["result"] = f"refused:{error}"

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(5.0), "the consume never reached the history commit"
    revoker = threading.Thread(target=lambda: admission.revoke_current("PHYSICS_CLOCK_SILENT"))
    revoker.start()
    revoker.join(0.2)
    assert revoker.is_alive() is True, "revocation interleaved the in-flight consume"
    release.set()
    thread.join(5.0)
    revoker.join(5.0)
    assert outcome["result"] == "committed"
    with pytest.raises(AdmissionRefused):
        admission.consume_authority(ticket="clock-session", generation=1, reset_epoch=1,
                                    stage="submit", evidence_token=_token(history, 1),
                                    controller_generation=1)


def test_takeover_waits_for_an_in_flight_consume_and_then_refuses():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    entered = threading.Event()
    release = threading.Event()
    outcome = {}
    original = history.commit_receipt

    def blocking_commit_receipt(**kwargs):
        entered.set()
        release.wait(5.0)
        return original(**kwargs)

    history.commit_receipt = blocking_commit_receipt

    def worker():
        try:
            admission.consume_authority(ticket="clock-session", generation=1, reset_epoch=1,
                                        stage="permit",
                                        evidence_token=_token(history, 1),
                                        controller_generation=1)
            outcome["result"] = "committed"
        except AdmissionRefused as error:
            outcome["result"] = f"refused:{error}"

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(5.0)
    takeover = {}
    usurper = threading.Thread(
        target=lambda: takeover.setdefault(
            "result", _try(lambda: admission.arm(ticket="clock-session", generation=2,
                                                 reset_epoch=1))))
    usurper.start()
    usurper.join(0.2)
    assert usurper.is_alive() is True, "takeover interleaved the in-flight consume"
    release.set()
    thread.join(5.0)
    usurper.join(5.0)
    assert outcome["result"] == "committed"
    assert takeover["result"].startswith("refused")


def _try_arm(admission):
    try:
        admission.arm(ticket="clock-session", generation=2, reset_epoch=1)
        return "armed"
    except AdmissionRefused as error:
        return error


def _try(call):
    try:
        call()
        return "allowed"
    except AdmissionRefused as error:
        return f"refused:{error}"


def _stop_evidence(identity, now):
    """Authoritative, identity-bound stop evidence for the frozen contract."""

    return {"authoritative": True, "stopped": True, "identity": identity,
            "monotonic_ns": now[0], "valid_until_monotonic_ns": now[0] + 60_000_000_000}


def _retire_evidence(identity, now):
    return _stop_evidence(identity, now)


def _token(history, step, *, incarnation=None, version=None):
    """Explicit evidence/proof token bound to one selected step."""

    snapshot = history.commit_state()
    return {"physics_step": step,
            "history_version": snapshot["version"] if version is None else version,
            "incarnation": snapshot["incarnation"] if incarnation is None else incarnation,
            "reset_epoch": snapshot["epoch"]}


# --- restored regression tests (review 5 finding 4: these were claimed but absent) ---


def test_retired_identity_is_permanently_closed():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _ready(now)
    identity = admission.identity
    admission.retire(identity=identity, stop_evidence=_retire_evidence(identity, now))
    for stage in ("sample", "proof", "permit", "submit", "final_acceptance"):
        with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_RETIRED"):
            admission.fence(ticket="clock-session", generation=1, reset_epoch=1, stage=stage)
    with pytest.raises(AdmissionRefused):
        admission.admit_sample(sample=_sample(1), ticket="clock-session", generation=1,
                               reset_epoch=1)


def test_takeover_requires_still_valid_identity_bound_stop_evidence():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _ready(now)
    identity = admission.identity
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_STOP_EVIDENCE_INVALID"):
        admission.retire(identity=identity,
                         stop_evidence={"authoritative": True, "stopped": True,
                                        "identity": ("ticket-other",), "monotonic_ns": now[0]})
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_STOP_EVIDENCE_INVALID"):
        admission.retire(identity=identity,
                         stop_evidence={"authoritative": True, "stopped": True,
                                        "identity": identity, "monotonic_ns": now[0],
                                        "valid_until_monotonic_ns": now[0] - 1})
    admission.retire(identity=identity, stop_evidence=_retire_evidence(identity, now))
    now[0] += 120_000_000_000
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_STOP_EVIDENCE_EXPIRED"):
        admission.arm(ticket="clock-session", generation=2, reset_epoch=1)


def test_confirm_stop_requires_authoritative_identity_bound_evidence():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _ready(now)
    identity = admission.identity
    admission.revoke_current("PHYSICS_CLOCK_SILENT")
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_STOP_EVIDENCE_INVALID"):
        admission.confirm_stop(identity=identity, stopped=True,
                               evidence={"authoritative": True, "stopped": True,
                                         "identity": ("ticket-other",), "monotonic_ns": now[0]})
    record = admission.confirm_stop(identity=identity, stopped=True,
                                    evidence=_stop_evidence(identity, now))
    assert record["stop_evidence_monotonic_ns"] == now[0]
    assert "expiry_to_stop_ns" not in record


def test_selected_age_crossing_after_the_final_snapshot_is_rejected():
    """The age decision must use a time read at the commit point, not a cached one."""

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now, selected_max_age_s=.05)
    last_end_ns = history._last_source_end_ns
    reached = {"copied": False}
    original = history.step_at

    def slow_copy(step):
        entry = original(step)
        reached["copied"] = True
        now[0] = last_end_ns + 80_000_000          # the isolated copy consumed 60 ms
        return entry

    history.step_at = slow_copy
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_SELECTED_STALE"):
        admission.admit_sample(sample=_sample(1), ticket="clock-session", generation=1,
                               reset_epoch=1)
    assert reached["copied"] is True


def test_admission_age_is_never_taken_from_a_cached_pre_copy_time():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now, selected_max_age_s=.05)
    last_end_ns = history._last_source_end_ns
    now[0] = last_end_ns + 80_000_000              # stale before the call even starts
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_SELECTED_STALE"):
        admission.admit_sample(sample=_sample(1), ticket="clock-session", generation=1,
                               reset_epoch=1)


def test_history_version_changes_on_every_readiness_or_hazard_transition():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, _ = _admission(now)          # already armed on epoch 1 by the helper
    seen = [history.snapshot()["version"]]
    history.accept_chunk(_chunk(0, _sample(1)))
    seen.append(history.snapshot()["version"])
    now[0] = history._last_source_end_ns + 400_000_000
    assert history.check_health() is False
    seen.append(history.snapshot()["version"])
    assert len(set(seen)) == 3, seen


def test_checked_stage_revocation_after_checker_completion_refuses():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _ready(now)
    base = admission._clock_ns
    calls = {"n": 0, "done": False}

    def seam_clock():
        calls["n"] += 1
        if calls["n"] >= 2 and calls["done"]:
            calls["done"] = False          # disarm before the re-entrant revocation
            admission.revoke_current("PHYSICS_CLOCK_SILENT")
        return base()

    def checker():
        calls["done"] = True
        return "checked"

    admission._clock_ns = seam_clock
    with pytest.raises(AdmissionRefused):
        admission.run_checked_stage(ticket="clock-session", generation=1, reset_epoch=1,
                                    stage="proof", side_effect_free=True, checker=checker)
    assert admission.checked_stages == 0


def test_admit_sample_does_not_copy_under_the_broker_lock():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    reached = {"copied": False}
    original = history.step_at

    def tracking_step_at(step):
        entry = original(step)
        reached["copied"] = True
        assert not admission._lock._is_owned(), "step_at must not run under the admission lock"
        return entry

    history.step_at = tracking_step_at
    admitted = admission.admit_sample(sample=_sample(1), ticket="clock-session", generation=1,
                                      reset_epoch=1)
    assert reached["copied"] is True
    assert admitted["command_authority"] is False


# --- review 5 / design-review RED cases (implementation deliberately not present yet) ---


def test_retirement_evidence_expiry_is_mandatory_and_finite():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _ready(now)
    identity = admission.identity
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_STOP_EVIDENCE_INVALID"):
        admission.retire(identity=identity,
                         stop_evidence={"authoritative": True, "stopped": True,
                                        "identity": identity, "monotonic_ns": now[0]})
    admission.revoke_current("PHYSICS_CLOCK_SILENT")
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_STOP_EVIDENCE_INVALID"):
        admission.confirm_stop(identity=identity, stopped=True,
                               evidence={"authoritative": True, "stopped": True,
                                         "identity": identity, "monotonic_ns": now[0]})


def test_stop_evidence_rejects_stale_and_future_observation_times():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _ready(now)
    identity = admission.identity
    admission.revoke_current("PHYSICS_CLOCK_SILENT")
    stale = dict(_stop_evidence(identity, now), monotonic_ns=1)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_STOP_EVIDENCE_STALE"):
        admission.confirm_stop(identity=identity, stopped=True, evidence=stale)
    future = dict(_stop_evidence(identity, now), monotonic_ns=now[0] + 60_000_000_000,
                  valid_until_monotonic_ns=now[0] + 120_000_000_000)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_STOP_EVIDENCE_FUTURE"):
        admission.confirm_stop(identity=identity, stopped=True, evidence=future)


def test_every_hazard_path_advances_the_history_version():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, _ = _admission(now)          # already armed on epoch 1 by the helper
    history.accept_chunk(_chunk(0, _sample(1)))
    before = history.snapshot()["version"]
    now[0] = history._last_source_end_ns + 400_000_000
    assert history.check_health() is False
    assert history.snapshot()["version"] > before
    now[0] += 400_000_000
    with pytest.raises(ValueError):
        history.step_at(1)
    assert history.snapshot()["version"] > before


def test_read_copy_commit_uses_time_read_after_the_final_copy():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now, selected_max_age_s=.05)
    last_end_ns = history._last_source_end_ns
    original = history.step_at
    state = {"copied": False}

    def slow_copy(step):
        entry = original(step)
        state["copied"] = True
        now[0] = last_end_ns + 80_000_000      # the copy itself took 60 ms
        return entry

    history.step_at = slow_copy
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_SELECTED_STALE"):
        admission.admit_sample(sample=_sample(1), ticket="clock-session", generation=1,
                               reset_epoch=1)
    assert state["copied"] is True


def test_consume_rejects_negative_and_foreign_versions():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission = _ready(now)
    consumed = []
    negative = dict(_token(history, 1), history_version=-1)
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_"):
        admission.consume_stage(ticket="clock-session", generation=1, reset_epoch=1,
                                stage="submit", consume=lambda: consumed.append("x"),
                                evidence_token=negative, controller_generation=1)
    foreign = dict(_token(history, 1), incarnation="other-incarnation")
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_"):
        admission.consume_stage(ticket="clock-session", generation=1, reset_epoch=1,
                                stage="submit", consume=lambda: consumed.append("x"),
                                evidence_token=foreign, controller_generation=1)

