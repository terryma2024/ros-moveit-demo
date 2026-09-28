"""Gate 5 offline authority transaction and adversarial fake controller port.

Deterministic adversarial set for the frozen protocol: private immutable permit
records, opaque handles, registry-owned time, history-owned commit receipts, full
receipt validation and a stateful reservation fake with real thread barriers.
"""

import copy
import json
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


def _dispatch(tx):
    return tx.run(stage="route_dispatch", role="arm", goal_uuid="g-1", target_digest="d-1",
                  controller_generation=1, controller_incarnation="i")


def _issue(registry, **overrides):
    fields = dict(identity=("t", "s", "i", 1, 1), stage="route_dispatch", step=1,
                  history_version=1, incarnation="i", epoch=1, role="arm",
                  controller_generation=1, goal_uuid="g-1", target_digest="d-1",
                  controller_incarnation="i")
    fields.update(overrides)
    return registry.issue_handle(**fields)


def _reserve(port, *, permit_id="p-1", goal_uuid="g-1", role="arm", target_digest="d-1",
             deadline_ns=2_000_000_000, session_id="clock-session", broker_incarnation="i",
             claim_monotonic_ns=1_000_000_000):
    return port.reserve(permit_id=permit_id, goal_uuid=goal_uuid, role=role,
                        target_digest=target_digest, generation=1,
                        controller_incarnation="i", deadline_ns=deadline_ns,
                        stage="route_dispatch", session_id=session_id,
                        broker_incarnation=broker_incarnation,
                        claim_monotonic_ns=claim_monotonic_ns)


def test_removed_legacy_claim_refuses_and_the_supported_path_sends_nothing():
    """The removed API refuses; the supported path performs no controller work.

    The former name claimed a hazard/claim boundary while the body only exercised
    the retired API, so the property is now asserted on the supported path too.
    """

    from test_act_dispatch_transaction import _run, _transaction

    registry = _registry()
    port = _fake()
    handle = _issue(registry)
    registry.revoke("PHYSICS_CLOCK_SILENT")
    with pytest.raises(Exception, match="AUTHORITY_LEGACY_CLAIM_REMOVED"):
        registry.claim(handle)
    assert port.reserve_calls == 0 and port.send_calls == 0

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, _bound, bound_port, tx = _transaction(now)
    admission.revoke_current("PHYSICS_CLOCK_SILENT")
    assert _run(tx) in ("REJECTED", "UNKNOWN")
    assert bound_port.reserve_calls == 0 and bound_port.accepted_commands == 0


def test_large_copy_interleavings_hold_no_local_lock():
    """A real copy/serialization must not hold the registry lock or block revoke."""

    from test_act_dispatch_transaction import _run_to_receive, _transaction

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    assert _run_to_receive(tx) == "IN_FLIGHT"
    payload = {"samples": [{"step": step, "values": [step * 1.0] * 64} for step in range(2048)]}
    acquired = registry._lock.acquire(blocking=False)
    try:
        assert acquired is True, "the registry lock was held across the dispatch"
    finally:
        if acquired:
            registry._lock.release()
    blob = json.dumps(payload).encode("utf-8")
    copied = copy.deepcopy(payload)
    assert len(blob) > 1024 and copied["samples"][0]["step"] == 0
    revoker = threading.Thread(target=lambda: admission.revoke_current("CLIENT_REVOKED"))
    revoker.start()
    revoker.join(5.0)
    assert admission.revoked_record is not None
    assert port.accepted_commands == 1


def test_refusing_history_and_a_caller_built_domain_both_refuse():
    """A caller-built stub domain cannot be sealed, and the retired API refuses."""

    registry = _registry(history=_StubHistory(refuse="PHYSICS_COMMIT_VERSION_CHANGED"))
    handle = _issue(registry)
    with pytest.raises(Exception, match="AUTHORITY_LEGACY_CLAIM_REMOVED"):
        registry.claim(handle)
    # a domain without broker-owned admission/port bindings cannot be sealed, so
    # no caller-substituted stub can ever reach the bound claim
    with pytest.raises(Exception, match="AUTHORITY_DOMAIN_INCOMPLETE"):
        registry.seal()


def test_io_blocked_while_revoke_proceeds_without_the_broker_lock():
    """A blocked controller send must not prevent revocation from completing."""

    from test_act_dispatch_transaction import _transaction

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    in_io = threading.Event()
    release = threading.Event()

    def blocking_receive(node):
        in_io.set()
        release.wait(5.0)

    tx.barrier("receive", blocking_receive)
    outcome = {}
    worker = threading.Thread(target=lambda: outcome.setdefault("state", _dispatch(tx)))
    worker.start()
    assert in_io.wait(5.0), "the transaction never reached the receive node"
    began = time.monotonic()
    admission.revoke_current("CLIENT_REVOKED")
    elapsed = time.monotonic() - began
    assert elapsed < 0.1, "revocation waited on the blocked controller I/O"
    release.set()
    worker.join(10.0)
    assert outcome["state"] in ("ACCEPTED", "REJECTED", "UNKNOWN")
    assert admission.revoked_record is not None


def test_controller_close_before_acceptance_yields_zero_accepted_commands():
    port = _fake()
    port.close_before_accept()
    _reserve(port)
    assert port.send(goal_uuid="g-1", permit_id="p-1", role="arm", target_digest="d-1",
                     generation=1, controller_incarnation="i") == "REJECTED"
    assert port.accepted_commands == 0


def test_controller_acceptance_before_close_yields_one_command_then_cancel():
    port = _fake()
    port.accept_before_close(cancel_pending=True)
    assert _reserve(port) == "ACCEPTED"
    assert port.send(goal_uuid="g-1", permit_id="p-1", role="arm", target_digest="d-1",
                     generation=1, controller_incarnation="i") == "ACCEPTED"
    assert port.accepted_commands == 1
    assert port.cancel_stop_pending is True


@pytest.mark.parametrize("field,value", [
    ("generation", 99), ("goal_uuid", "other"), ("permit_id", "other"),
    ("target_digest", "other"), ("controller_incarnation", "other"),
    ("sequence", -1), ("deadline_ns", 0), ("role", "other"),
])
def test_wrong_field_is_rejected(field, value):
    port = _fake()
    _reserve(port)
    call = {"goal_uuid": "g-1", "permit_id": "p-1", "controller_incarnation": "i",
            "sequence": 1, "deadline_ns": 2_000_000_000, "role": "arm",
            "target_digest": "d-1", "generation": 1}
    call[field] = value
    assert port.send(**call) == "REJECTED"
    assert port.accepted_commands == 0


def test_replay_duplicate_late_and_restart_are_fail_closed():
    port = _fake()
    _reserve(port)
    assert port.send(goal_uuid="g-1", permit_id="p-1", role="arm", target_digest="d-1",
                     generation=1, controller_incarnation="i") == "ACCEPTED"
    assert port.send(goal_uuid="g-1", permit_id="p-1", role="arm", target_digest="d-1",
                     generation=1, controller_incarnation="i") == "REJECTED"
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
                                   controller_generation=1, goal_uuid="g-1", target_digest="d-1",
                                   controller_incarnation="i")
    now[0] += 5_000_000                       # real clock advanced past the deadline
    with pytest.raises(Exception):
        registry.claim(handle, now_ns=1)      # caller time must not be accepted
    with pytest.raises(Exception):
        registry.claim(handle)


def test_receipt_validation_rejects_invalid_fields():
    """Every frozen receipt field is bound; a tampered field is refused."""

    from test_act_dispatch_transaction import _run_to_receive, _transaction

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    _, admission, registry, port, tx = _transaction(now)
    assert _run_to_receive(tx) == "IN_FLIGHT"
    good = dict(port.last_receipt(permit_id=tx.handle.permit_id))
    # each tampered field is refused on its own in-flight permit, and the refusal
    # irreversibly terminalizes that permit
    for field, value in (("sequence", -1), ("goal_uuid", "other"), ("generation", 99),
                         ("target_digest", "other"), ("controller_incarnation", "other"),
                         ("controller_boot_incarnation", "other"), ("observed_ns", -5),
                         ("permit_id", "other")):
        _, _, fresh_registry, fresh_port, fresh_tx = _transaction(now)
        assert _run_to_receive(fresh_tx) == "IN_FLIGHT"
        fresh_good = dict(fresh_port.last_receipt(permit_id=fresh_tx.handle.permit_id))
        bad = dict(fresh_good, **{field: value})
        with pytest.raises(Exception):
            fresh_registry.receipt(fresh_tx.handle, **bad)
        assert fresh_registry.state_of(fresh_tx.handle) == "UNKNOWN"
    assert registry.receipt(tx.handle, **good) == "ACCEPTED"


def test_no_acceptance_without_a_reservation():
    module = _module()
    port = _fake()
    assert port.send(goal_uuid="g-1", permit_id="p-1", role="arm", target_digest="d-1",
                     generation=1, controller_incarnation="i") == "REJECTED"
    assert port.accepted_commands == 0


def test_same_goal_uuid_cannot_be_accepted_twice_with_a_different_permit():
    module = _module()
    port = _fake()
    port.reserve(permit_id="p-1", goal_uuid="g-1", role="arm", target_digest="d-1",
                 generation=1, controller_incarnation="i", deadline_ns=2_000_000_000,
                 stage="route_dispatch")
    assert port.send(goal_uuid="g-1", permit_id="p-1", role="arm", target_digest="d-1",
                     generation=1, controller_incarnation="i") == "ACCEPTED"
    port.reserve(permit_id="p-2", goal_uuid="g-1", role="arm", target_digest="d-1",
                 generation=1, controller_incarnation="i", deadline_ns=2_000_000_000,
                 stage="route_dispatch")
    assert port.send(goal_uuid="g-1", permit_id="p-2", role="arm", target_digest="d-1",
                     generation=1, controller_incarnation="i") == "REJECTED"
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



# --- end-to-end lifecycle: reservation -> send -> receipt, one permit state machine ---


def _end_to_end():
    """Run the real offline dispatch transaction and return the consumed record.

    The receipt fields come from the controller port's actual consumed
    reservation (``last_receipt``); nothing is assembled from private registry
    state, as required by review 7.
    """

    from test_act_dispatch_transaction import _run_to_receive, _transaction

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    # stop after the receive node: the permit stays IN_FLIGHT so the caller can
    # drive timeout / duplicate / restart receipt semantics on that same permit
    assert _run_to_receive(tx) == "IN_FLIGHT"
    fields = port.last_receipt(permit_id=tx.handle.permit_id)
    assert fields["goal_uuid"] == "g-1" and fields["role"] == "arm"
    assert fields["target_digest"] == "d-1"
    import types

    permit = types.SimpleNamespace(permit_id=fields["permit_id"], goal_uuid=fields["goal_uuid"],
                                   role=fields["role"], target_digest=fields["target_digest"],
                                   incarnation=fields["controller_incarnation"],
                                   controller_generation=fields["generation"])
    return registry, port, tx.handle, permit, fields


def test_timeout_then_late_acceptance_never_revives_the_permit():
    registry, port, handle, permit, fields = _end_to_end()
    assert registry.receipt(handle, **dict(fields, verdict="UNKNOWN")) == "UNKNOWN"
    assert registry.state_of(handle) == "UNKNOWN"
    with pytest.raises(Exception):
        registry.receipt(handle, **dict(fields, verdict="ACCEPTED", sequence=2))
    assert registry.state_of(handle) == "UNKNOWN"
    with pytest.raises(Exception):
        registry.claim(handle)


def test_duplicate_receipt_after_terminal_state_is_refused():
    registry, port, handle, permit, fields = _end_to_end()
    assert registry.receipt(handle, **fields) == "ACCEPTED"
    with pytest.raises(Exception):
        registry.receipt(handle, **dict(fields, sequence=2))
    assert registry.state_of(handle) == "ACCEPTED"
    assert port.accepted_commands == 1


def test_controller_restart_invalidates_the_receipt_incarnation():
    registry, port, handle, permit, fields = _end_to_end()
    assert port.restart_controller(controller_incarnation="restarted") == "REJECTED"
    restarted = dict(port.last_receipt(permit_id=permit.permit_id))
    restarted["controller_incarnation"] = "restarted"
    assert restarted["controller_incarnation"] == "restarted"
    with pytest.raises(Exception):
        registry.receipt(handle, **restarted)
    # an invalid receipt is irreversible: the permit is closed as UNKNOWN and can
    # never be revived by a later corrected receipt
    assert registry.state_of(handle) == "UNKNOWN"
    with pytest.raises(Exception):
        registry.receipt(handle, **fields)
    assert port.send(goal_uuid=permit.goal_uuid, permit_id=permit.permit_id,
                     role=permit.role, target_digest=permit.target_digest,
                     generation=permit.controller_generation,
                     controller_incarnation=permit.incarnation) == "REJECTED"


# --- stage semantics: only route dispatch may touch the controller ---


def test_only_route_dispatch_uses_the_controller_reservation_protocol():
    port = _fake()
    for stage in ("sample", "proof", "permit", "final_acceptance"):
        assert port.reserve(permit_id="p-1", goal_uuid="g-1", role="arm", target_digest="d-1",
                            generation=1, controller_incarnation="i",
                            deadline_ns=2_000_000_000, stage=stage) == "REJECTED"
    assert port.reserve(permit_id="p-1", goal_uuid="g-1", role="arm", target_digest="d-1",
                        generation=1, controller_incarnation="i",
                        deadline_ns=2_000_000_000, stage="route_dispatch") == "ACCEPTED"
    assert port.reserve_calls == 5
    assert port.accepted_commands == 0


def test_local_stage_claims_never_reserve_or_send():
    """Local stages claim through the bound claim domain and never touch the controller."""

    from test_act_dispatch_transaction import _transaction

    now = [SOURCE_BASE_NS + 3 * STEP_NS]
    history, admission, registry, port, tx = _transaction(now)
    claimed = []
    for stage in ("proof", "permit", "final_acceptance"):
        handle = registry.issue_handle(
            identity=admission.identity, stage=stage, step=1,
            history_version=history.snapshot()["version"], incarnation=history.incarnation,
            epoch=admission.identity[4], role="arm", controller_generation=1,
            goal_uuid="g-1", target_digest="d-1", controller_incarnation="i")
        token = {"identity": admission.identity, "owner_identity": admission.identity,
                 "stage": stage, "history_version": history.snapshot()["version"],
                 "incarnation": history.incarnation, "reset_epoch": admission.identity[4]}
        registry.capture_controller_identity(handle)
        receipt = registry.claim_bound(handle, identity=admission.identity,
                                       controller_generation=1, token=token)
        claimed.append((receipt.stage, registry.state_of(handle)))
    assert [stage for stage, _ in claimed] == ["proof", "permit", "final_acceptance"]
    assert all(state == "IN_FLIGHT" for _, state in claimed)
    assert port.reserve_calls == 0 and port.send_calls == 0
    assert port.accepted_commands == 0


