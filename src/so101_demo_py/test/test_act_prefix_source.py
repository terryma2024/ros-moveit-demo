"""A source receipt remains tied to its first observation and owner."""

import pytest


SOURCE_KEYS = ("world", "scene", "contact", "head", "wrist", "arm", "neck")


def _prefix():
    return {
        "session_id": "session", "attempt_id": "attempt", "sequence": 0,
        "observation_time_s": 4.0, "target_times_s": (4.1,),
        "positions": ((.001,) * 6,),
    }


def _source(receipts=None):
    return {
        "session_id": "session", "attempt_id": "attempt",
        "reset_epoch": 3, "phase": "APPROACH", "physics_step": 21,
        "simulation_time_s": 4.0,
        "observation_sha256": "a" * 64,
        "source_received_wall_s": receipts or {
            name: 9.8 + index * .01 for index, name in enumerate(SOURCE_KEYS)
        },
    }


def _authority(clock, current):
    from so101_demo.act.prefix_source import PrefixSourceAuthority

    def guard(ticket):
        if ticket != current[0]:
            raise PermissionError("LEASE_GENERATION_INVALID")

    return PrefixSourceAuthority(
        ticket_guard=guard, monotonic=lambda: clock[0],
        max_observation_age_s=.5, max_prefix_age_s=.3,
    )


def _issue(authority, ticket, *, prefix=None, source=None, source_kind="EXPERT_ROUTE",
           output_received_wall_s=None):
    return authority.issue(
        ticket=ticket, prefix=_prefix() if prefix is None else prefix,
        source=_source() if source is None else source,
        source_kind=source_kind, source_artifact_sha256="b" * 64,
        contact_policy_fingerprint="c" * 64,
        output_received_wall_s=output_received_wall_s,
    )


def test_expert_receipt_is_broker_private_and_one_use():
    from so101_demo.act.prefix_source import PrefixSourceReceipt

    clock = [10.0]
    ticket = (7, "lease", "act", "session", "attempt")
    current = [ticket]
    authority = _authority(clock, current)
    receipt = _issue(authority, ticket)
    assert isinstance(receipt, PrefixSourceReceipt)
    assert receipt.command_authority is False
    assert receipt.source_kind == "EXPERT_ROUTE"
    assert receipt.prefix_issued_wall_s == 10.0
    assert receipt.source_received_wall_s[0] == ("world", 9.8)
    assert receipt.owner_ticket == ticket
    assert authority.consume(ticket=ticket, prefix=_prefix(), source=_source()) is receipt
    with pytest.raises(PermissionError, match="PREFIX_SOURCE_UNAVAILABLE"):
        authority.consume(ticket=ticket, prefix=_prefix(), source=_source())
    with pytest.raises(PermissionError, match="PREFIX_SOURCE_REPLAY"):
        _issue(authority, ticket)


def test_changed_prefix_or_source_closes_receipt():
    ticket = (7, "lease", "act", "session", "attempt")
    for changed in ("prefix", "observation", "receipt"):
        clock = [10.0]
        authority = _authority(clock, [ticket])
        _issue(authority, ticket)
        prefix, source = _prefix(), _source()
        if changed == "prefix":
            prefix["positions"] = ((.002,) * 6,)
        elif changed == "observation":
            source["observation_sha256"] = "d" * 64
        else:
            source["source_received_wall_s"]["head"] = 9.9
        with pytest.raises(PermissionError, match="PREFIX_SOURCE_CHANGED"):
            authority.consume(ticket=ticket, prefix=prefix, source=source)
        with pytest.raises(PermissionError, match="PREFIX_SOURCE_UNAVAILABLE"):
            authority.consume(ticket=ticket, prefix=_prefix(), source=_source())


def test_original_observation_age_and_prefix_age_both_fence_use():
    ticket = (7, "lease", "act", "session", "attempt")
    clock = [10.0]
    authority = _authority(clock, [ticket])
    _issue(authority, ticket)
    clock[0] = 10.31
    with pytest.raises(PermissionError, match="PREFIX_SOURCE_STALE"):
        authority.consume(ticket=ticket, prefix=_prefix(), source=_source())

    clock = [10.0]
    authority = _authority(clock, [ticket])
    old = _source({name: 9.49 if name == "head" else 9.8
                   for name in SOURCE_KEYS})
    with pytest.raises(ValueError, match="PREFIX_OBSERVATION_STALE"):
        _issue(authority, ticket, source=old)
    future = _source({name: 10.01 if name == "world" else 9.8
                      for name in SOURCE_KEYS})
    with pytest.raises(ValueError, match="PREFIX_SOURCE_TIME_INVALID"):
        _issue(authority, ticket, source=future)


def test_policy_output_keeps_its_first_receive_time():
    ticket = (7, "lease", "act", "session", "attempt")
    clock = [10.0]
    authority = _authority(clock, [ticket])
    with pytest.raises(ValueError, match="PREFIX_OUTPUT_TIME_REQUIRED"):
        _issue(authority, ticket, source_kind="ACT_POLICY")
    receipt = _issue(authority, ticket, source_kind="ACT_POLICY",
                     output_received_wall_s=9.9)
    assert receipt.prefix_issued_wall_s == 9.9
    clock[0] = 10.21
    with pytest.raises(PermissionError, match="PREFIX_SOURCE_STALE"):
        authority.consume(ticket=ticket, prefix=_prefix(), source=_source())


def test_owner_generation_and_revocation_close_receipt():
    ticket = (7, "lease", "act", "session", "attempt")
    next_ticket = (8, "next", "act", "session", "attempt")
    clock = [10.0]
    current = [ticket]
    authority = _authority(clock, current)
    _issue(authority, ticket)
    current[0] = next_ticket
    with pytest.raises(PermissionError, match="PREFIX_SOURCE_OWNER_CHANGED"):
        authority.consume(ticket=ticket, prefix=_prefix(), source=_source())
    current[0] = ticket
    with pytest.raises(PermissionError, match="PREFIX_SOURCE_UNAVAILABLE"):
        authority.consume(ticket=ticket, prefix=_prefix(), source=_source())
    authority = _authority(clock, current)
    _issue(authority, ticket)
    authority.revoke()
    with pytest.raises(PermissionError, match="PREFIX_SOURCE_UNAVAILABLE"):
        authority.consume(ticket=ticket, prefix=_prefix(), source=_source())
    with pytest.raises(PermissionError, match="PREFIX_SOURCE_REPLAY"):
        _issue(authority, ticket)


def test_scope_mismatch_cannot_issue():
    ticket = (7, "lease", "act", "session", "attempt")
    clock = [10.0]
    authority = _authority(clock, [ticket])
    source = _source()
    source["reset_epoch"] = 0
    with pytest.raises(ValueError, match="PREFIX_SOURCE_SCOPE_INVALID"):
        _issue(authority, ticket, source=source)
    prefix = _prefix()
    prefix["observation_time_s"] = 3.0
    prefix["target_times_s"] = (3.1,)
    with pytest.raises(ValueError, match="PREFIX_SOURCE_SCOPE_INVALID"):
        _issue(authority, ticket, prefix=prefix)
    with pytest.raises(ValueError, match="PREFIX_SOURCE_KIND_INVALID"):
        _issue(authority, ticket, source_kind=[])


def test_broker_uses_private_receipt_before_proof_approval():
    from so101_demo.act.ownership import Ownership
    from so101_demo.adapters.act.command_broker import CommandBroker
    from so101_demo.act.prefix_source import PrefixSourceAuthority

    class Driver:
        hazard_reason = None

        def stopped(self):
            return True

    class Executor:
        receipt = None

        def approve_with_source(self, ticket, prefix, receipt):
            self.receipt = receipt
            return {"permit_id": "private"}

    clock = [10.0]
    ownership = Ownership(monotonic=lambda: clock[0])
    token = ownership.acquire("act", "session", "attempt")
    ticket = ownership.ticket(token, "act", "session", "attempt")
    authority = PrefixSourceAuthority(
        ticket_guard=ownership.require_ticket,
        monotonic=lambda: clock[0], max_observation_age_s=.5,
        max_prefix_age_s=.3,
    )
    executor = Executor()
    broker = CommandBroker(
        Driver(), ownership=ownership, simulation_session_id="session",
        prefix_executor=executor, prefix_source_authority=authority,
        prefix_source_port=lambda current_ticket: _source(),
    )
    receipt = broker.issue_prefix_source(
        ticket=ticket, prefix=_prefix(), source=_source(),
        source_kind="EXPERT_ROUTE", source_artifact_sha256="b" * 64,
        contact_policy_fingerprint="c" * 64,
    )
    request = {
        "protocol_version": 1, "request_id": "request", "operation": "approve_prefix",
        "owner": "act", "session_id": "session", "attempt_id": "attempt",
        "lease_token": token, "prefix": _prefix(),
    }
    result = broker.handle(request, "local-connection")
    assert result["accepted"] is True
    assert executor.receipt is receipt
    assert result["permit"] == {"permit_id": "private"}
    assert broker.handle(request, "local-connection")["error"] == "PREFIX_SOURCE_UNAVAILABLE"
    assert broker.handle(dict(request, operation="issue_prefix_source"),
                         "local-connection")["error"] == "OPERATION_INVALID"


def test_broker_rejects_unwired_proof_and_revoked_source():
    from so101_demo.act.ownership import Ownership
    from so101_demo.adapters.act.command_broker import CommandBroker
    from so101_demo.act.prefix_source import PrefixSourceAuthority

    class Driver:
        hazard_reason = None

        def stopped(self):
            return True

        def stop_all(self, reason):
            pass

    class LegacyExecutor:
        def approve(self, ticket, prefix):
            pytest.fail("legacy approval cannot accept an unproved prefix")

        def invalidate(self, reason):
            pass

    clock = [10.0]
    ownership = Ownership(monotonic=lambda: clock[0])
    token = ownership.acquire("act", "session", "attempt")
    ticket = ownership.ticket(token, "act", "session", "attempt")
    authority = PrefixSourceAuthority(
        ticket_guard=ownership.require_ticket,
        monotonic=lambda: clock[0], max_observation_age_s=.5,
        max_prefix_age_s=.3,
    )
    with pytest.raises(ValueError, match="PREFIX_SOURCE_CONFIG_INVALID"):
        CommandBroker(Driver(), ownership=ownership,
                      prefix_source_authority=authority)
    broker = CommandBroker(
        Driver(), ownership=ownership, prefix_executor=LegacyExecutor(),
        prefix_source_authority=authority,
        prefix_source_port=lambda current_ticket: _source(),
    )
    _issue(authority, ticket)
    request = {
        "protocol_version": 1, "request_id": "request", "operation": "approve_prefix",
        "owner": "act", "session_id": "session", "attempt_id": "attempt",
        "lease_token": token, "prefix": _prefix(),
    }
    assert broker.handle(request, "local-connection")["error"] == "PREFIX_SOURCE_PROOF_UNWIRED"
    broker.stop_attempt("TEST_STOP")
    with pytest.raises(PermissionError, match="PREFIX_SOURCE_UNAVAILABLE"):
        authority.consume(ticket=ticket, prefix=_prefix(), source=_source())
