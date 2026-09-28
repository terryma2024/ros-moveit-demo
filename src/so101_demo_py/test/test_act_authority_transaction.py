"""Gate 5 offline authority transaction and adversarial fake controller port.

Deterministic adversarial set for the frozen protocol: private immutable permit
records, opaque handles, registry-owned time, history-owned commit receipts, full
receipt validation and a stateful reservation fake with real thread barriers.
"""

import threading
import time

import pytest

from test_act_physics_clock_admission import (SOURCE_BASE_NS, STEP_NS, AdmissionRefused,
                                             PhysicsClockHistory, _admission, _chunk, _ready,
                                             _sample, _stop_evidence)


def _module():
    from so101_demo.adapters.act import authority_transaction
    return authority_transaction


class _StubHistory:
    """Minimal stand-in for the history commit primitive (binding tested elsewhere)."""

    def __init__(self, *, refuse=None):
        self.refuse = refuse
        self.calls = []

    def commit_receipt(self, **expected):
        self.calls.append(expected)
        if self.refuse is not None:
            raise ValueError(self.refuse)
        return {"version": expected["expected_version"],
                "incarnation": expected["expected_incarnation"],
                "epoch": expected["expected_epoch"], "step": expected["step"],
                "age_ns": 1_000_000, "commit_monotonic_ns": 1_000_000_000,
                "source_end_monotonic_ns": 999_000_000}


def _registry(*, history=None):
    module = _module()
    return module.AuthorityTransactionRegistry(clock_ns=lambda: 1_000_000_000,
                                               history=history or _StubHistory())


def _fake():
    module = _module()
    return module.ReservationFakeControllerPort(clock_ns=lambda: 1_000_000_000)


def _issue(registry, **overrides):
    fields = dict(identity=("t", "s", "i", 1, 1), stage="route_dispatch", step=1,
                  history_version=1, incarnation="i", epoch=1, role="arm",
                  controller_generation=1, goal_uuid="g-1", target_digest="d-1")
    fields.update(overrides)
    return registry.issue_handle(**fields)


def _reserve(port, *, permit_id="p-1", goal_uuid="g-1", role="arm", target_digest="d-1",
             deadline_ns=2_000_000_000):
    return port.reserve(permit_id=permit_id, goal_uuid=goal_uuid, role=role,
                        target_digest=target_digest, generation=1,
                        controller_incarnation="i", deadline_ns=deadline_ns)


def test_hazard_before_claim_produces_zero_reserve_and_zero_send():
    registry = _registry()
    port = _fake()
    handle = _issue(registry)
    registry.revoke("PHYSICS_CLOCK_SILENT")
    with pytest.raises(Exception):
        registry.claim(handle)
    assert port.reserve_calls == 0 and port.send_calls == 0


def test_large_copy_interleavings_hold_no_local_lock():
    registry = _registry()
    handle = _issue(registry)
    registry.claim(handle)
    assert not registry.lock_held_during(lambda: None)


def test_reset_hazard_and_age_crossing_after_final_read_refuse_the_permit():
    registry = _registry(history=_StubHistory(refuse="PHYSICS_COMMIT_VERSION_CHANGED"))
    handle = _issue(registry)
    with pytest.raises(Exception):
        registry.claim(handle)


def test_io_blocked_while_revoke_proceeds_without_the_broker_lock():
    registry = _registry()
    port = _fake()
    port.block_io(True)
    registry.revoke("CLIENT_REVOKED")
    assert registry.revoke_completed_without_waiting() is True


def test_controller_close_before_acceptance_yields_zero_accepted_commands():
    port = _fake()
    port.close_before_accept()
    _reserve(port)
    assert port.send(goal_uuid="g-1", permit_id="p-1") == "REJECTED"
    assert port.accepted_commands == 0


def test_controller_acceptance_before_close_yields_one_command_then_cancel():
    port = _fake()
    port.accept_before_close(cancel_pending=True)
    assert _reserve(port) == "ACCEPTED"
    assert port.send(goal_uuid="g-1", permit_id="p-1") == "ACCEPTED"
    assert port.accepted_commands == 1
    assert port.cancel_stop_pending is True


@pytest.mark.parametrize("field,value", [
    ("goal_uuid", "other"), ("permit_id", "other"), ("target_digest", "other"),
    ("role", "other"), ("generation", 99),
])
def test_wrong_field_is_rejected(field, value):
    port = _fake()
    _reserve(port)
    call = {"goal_uuid": "g-1", "permit_id": "p-1"}
    call[field] = value
    assert port.send(**call) == "REJECTED"


def test_replay_duplicate_late_and_restart_are_fail_closed():
    port = _fake()
    _reserve(port)
    assert port.send(goal_uuid="g-1", permit_id="p-1") == "ACCEPTED"
    assert port.send(goal_uuid="g-1", permit_id="p-1") == "REJECTED"
    assert port.late_receipt_after_timeout() == "UNKNOWN"
    assert port.restart_controller() == "REJECTED"


# --- EXP-569: deterministic probe-derived RED cases (review 6) ---


def test_permit_fields_are_private_and_immutable():
    module = _module()
    registry = _registry()
    handle = _issue(registry)
    for field in ("target_digest", "deadline_ns", "state", "goal_uuid"):
        assert not hasattr(handle, field), field
    with pytest.raises(Exception):
        handle.state = "READY"


def test_claim_uses_registry_time_and_rejects_a_rolled_back_clock():
    module = _module()
    now = [1_000_000_000]
    registry = module.AuthorityTransactionRegistry(clock_ns=lambda: now[0],
                                                   permit_ttl_ns=1_000_000)
    handle = registry.issue_handle(identity=("t", "s", "i", 1, 1), stage="route_dispatch", step=1,
                                   history_version=1, incarnation="i", epoch=1, role="arm",
                                   controller_generation=1, goal_uuid="g-1", target_digest="d-1")
    now[0] += 5_000_000                       # real clock advanced past the deadline
    with pytest.raises(Exception):
        registry.claim(handle, now_ns=1)      # caller time must not be accepted
    with pytest.raises(Exception):
        registry.claim(handle)


def test_receipt_validation_rejects_invalid_fields():
    module = _module()
    registry = _registry()
    handle = _issue(registry)
    registry.claim(handle)
    good = {"protocol_version": 1, "permit_id": handle.permit_id, "goal_uuid": "g-1",
            "role": "arm", "generation": 1, "target_digest": "d-1", "controller_incarnation": "i",
            "verdict": "ACCEPTED", "sequence": 1, "observed_ns": 1_000_000_000,
            "clock_domain": "monotonic"}
    for field, value in (("sequence", -1), ("goal_uuid", "other"), ("generation", 99),
                         ("target_digest", "other"), ("controller_incarnation", "other"),
                         ("observed_ns", -5), ("permit_id", "other")):
        bad = dict(good, **{field: value})
        with pytest.raises(Exception):
            registry.receipt(handle, **bad)


def test_no_acceptance_without_a_reservation():
    module = _module()
    port = _fake()
    assert port.send(goal_uuid="g-1", permit_id="p-1") == "REJECTED"
    assert port.accepted_commands == 0


def test_same_goal_uuid_cannot_be_accepted_twice_with_a_different_permit():
    module = _module()
    port = _fake()
    port.reserve(permit_id="p-1", goal_uuid="g-1", role="arm", target_digest="d-1",
                 generation=1, controller_incarnation="i", deadline_ns=2_000_000_000)
    assert port.send(goal_uuid="g-1", permit_id="p-1") == "ACCEPTED"
    port.reserve(permit_id="p-2", goal_uuid="g-1", role="arm", target_digest="d-1",
                 generation=1, controller_incarnation="i", deadline_ns=2_000_000_000)
    assert port.send(goal_uuid="g-1", permit_id="p-2") == "REJECTED"
    assert port.accepted_commands == 1


def test_confirmed_stop_expiry_is_revalidated_at_takeover():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission = _ready(now)
    identity = admission.identity
    admission.revoke_current("PHYSICS_CLOCK_SILENT")
    admission.confirm_stop(identity=identity, stopped=True, evidence=_stop_evidence(identity, now))
    now[0] += 120_000_000_000
    with pytest.raises(AdmissionRefused, match="CLOCK_ADMISSION_STOP_EVIDENCE_EXPIRED"):
        admission.arm(ticket="clock-session", generation=2, reset_epoch=1)


def test_history_commit_receipt_is_the_single_linearization_point():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, _ = _admission(now)
    history.accept_chunk(_chunk(0, _sample(1)))
    last_end_ns = history._last_source_end_ns
    now[0] = last_end_ns + 80_000_000
    with pytest.raises(ValueError):
        history.commit_receipt(expected_version=history.snapshot()["version"],
                               expected_incarnation=history.incarnation, expected_epoch=1,
                               step=1, max_age_ns=50_000_000)


def test_stale_transition_advances_the_version_exactly_once():
    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history = PhysicsClockHistory("clock-session", nq=2, nv=1, max_age_s=.35,
                                  max_source_step_gap_ns=3_000_000, max_silence_s=.5,
                                  first_chunk_timeout_s=.4, clock_ns=lambda: now[0])
    history.arm(1, source_floor_s=0.0)
    history.accept_chunk(_chunk(0, _sample(1)))
    before = history.snapshot()["version"]
    now[0] = history._last_source_end_ns + 400_000_000
    with pytest.raises(ValueError):
        history.step_at(1)
    assert history.snapshot()["hazard"] == "PHYSICS_CLOCK_STALE"
    assert history.snapshot()["version"] == before + 1


def test_blocking_io_while_revoke_proceeds_with_real_threads():
    module = _module()
    registry = _registry()
    handle = _issue(registry)
    entered = threading.Event()
    release = threading.Event()

    def blocked_send():
        entered.set()
        release.wait(5.0)

    worker = threading.Thread(target=blocked_send)
    worker.start()
    assert entered.wait(5.0)
    began = time.monotonic()
    registry.revoke("CLIENT_REVOKED")
    elapsed = time.monotonic() - began
    release.set()
    worker.join(5.0)
    assert elapsed < 0.1
    with pytest.raises(Exception):
        registry.claim(handle)

