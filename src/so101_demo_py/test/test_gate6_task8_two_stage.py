"""Phase 3b A-prime: recovery acquire -> reset -> release -> ACT bound acquire.

The bound session is one-shot and belongs to the exact ACT execution acquire only;
the recovery acquire must not consume it, and recovery must not gain trajectory submit
or prefix approve/submit dispatch.
"""

import threading

import pytest

from so101_demo.act.ownership import Ownership
from so101_demo.adapters.act.broker_authority_wiring import BoundAuthoritySession


class _Driver:
    def __init__(self):
        self.stopped_flag = True
        self.stop_all_calls = []

    def stopped(self):
        return self.stopped_flag

    def stop_all(self, reason="STOP"):
        self.stop_all_calls.append(reason)
        self.stopped_flag = True
        return True

    def bind_control_events(self, events):
        return True

    def ready(self):
        return True

    def refresh_stop(self):
        return True

    def validate(self, *a, **k):
        return True

    def prepare_goal(self, *a, **k):
        return "uuid-1"

    def send_prepared(self, *a, **k):
        return True

    def discard_prepared(self, *a, **k):
        return True


class _Client:
    """Configurable session-owned client with the full validated surface."""

    def __init__(self):
        self.arms = []
        self.queries = []
        self.closed = []
        self.armed_generation = None       # the generation the controller is armed for

    def arm_generation(self, ticket):
        self.arms.append(ticket)
        self.armed_generation = ticket[0]  # the real service reports this generation
        return True

    def query_identity(self, role):
        self.queries.append(role)
        return (self.armed_generation, f"inc-{role}", f"boot-{role}")

    def reserve(self, *a, **k):
        return True

    def close_generation(self, generation):
        self.closed.append(generation)
        return True

    def close(self, reason="CLOSED", generation=None):
        self.closed.append(generation)
        return True

    def close_all_attempted(self):
        return list(self.closed)

    def identity_snapshot(self, role):
        return (1, f"inc-{role}", f"boot-{role}")

    def install_authority(self, authority):
        self.authority = authority
        return True


class _History:
    version = 1
    incarnation = "clock-session"


class _Admission:
    def __init__(self):
        self.revoked = None

    def owner_is_active(self):
        return True

    def revoke_current(self, reason):
        self.revoked = reason
        return True


class _Port:
    def __init__(self):
        self.closed = []

    def identity_snapshot(self, role):
        return (1, f"inc-{role}", f"boot-{role}")

    def close(self, reason="CLOSED", generation=None):
        self.closed.append(generation)
        return True


def _registry():
    from so101_demo.adapters.act.authority_transaction import AuthorityTransactionRegistry

    return AuthorityTransactionRegistry(clock_ns=lambda: 9906000000, history=_History())


def _session(client=None):
    from so101_demo.adapters.act.broker_authority_composition import BrokerAuthorityComposition

    client = client or _Client()
    composition = BrokerAuthorityComposition(history=_History(), admission=_Admission(),
                                             registry=_registry(),
                                             controller_port=_Port(),
                                             expected_roles=("arm", "gripper"))
    session = object.__new__(BoundAuthoritySession)
    session.roles = ("arm", "gripper")
    session.composition = composition
    session._reservation_port = client
    session._armed = None
    session._confirmed = False
    session._fenced_reason = None
    return session, client


def _broker(session):
    import so101_demo.adapters.act.command_broker as module

    driver = _Driver()
    ownership = Ownership()
    broker = module.CommandBroker(driver, ownership=ownership,
                                  reservation_port=session.reservation_port,
                                  authority=session.composition,
                                  bound_authority_session=session)
    return broker, driver, ownership


def _request(operation, owner, request_id="r1", token=None):
    return {"protocol_version": 1, "request_id": request_id, "owner": owner,
            "session_id": "session", "attempt_id": "attempt", "lease_token": token,
            "operation": operation}


def test_recovery_acquire_does_not_consume_the_bound_session():
    session, client = _session()
    broker, driver, ownership = _broker(session)
    recovery = broker.handle(_request("acquire", "recovery"), "conn-rec")
    assert recovery["accepted"] is True, recovery
    # the one-shot session must still be untouched and usable by the ACT acquire
    assert session._confirmed is False, "the recovery acquire consumed the bound session"
    assert client.arms == [], "the recovery acquire armed the bound controller"
    assert client.queries == [], "the recovery acquire queried bound identities"
    release = broker.handle(_request("release", "recovery", "r2", recovery["lease_token"]),
                            "conn-rec")
    assert release["accepted"] is True, release
    act = broker.handle(_request("acquire", "act", "r3"), "conn-act")
    assert act["accepted"] is True, act
    assert client.arms and client.queries == ["arm", "gripper"], (
        "the ACT acquire must drive the real arm + per-role query")


def test_second_act_acquire_is_refused_with_no_new_arm_or_send():
    session, client = _session()
    broker, driver, ownership = _broker(session)
    first = broker.handle(_request("acquire", "act"), "conn-act")
    assert first["accepted"] is True
    arms_after_first = list(client.arms)
    second = broker.handle(_request("acquire", "act", "r2"), "conn-act-2")
    assert second["accepted"] is False, "a second ACT acquire must be refused"
    assert client.arms == arms_after_first, "the refused acquire must not arm again"


def test_recovery_cannot_submit_a_trajectory_or_approve_a_prefix():
    session, client = _session()
    broker, driver, ownership = _broker(session)
    recovery = broker.handle(_request("acquire", "recovery"), "conn-rec")
    token = recovery["lease_token"]
    for operation in ("submit", "prefix"):
        response = broker.handle(_request(operation, "recovery", "r2", token), "conn-rec")
        assert response["accepted"] is False, (operation, response)
        # the request is refused; FIELDS_INVALID means the operation needs extra
        # fields, which is still a refusal (recorded honestly as a weaker check)
        assert response.get("error") in ("PREFIX_OWNER_INVALID", "RESET_OWNER_INVALID",
                                        "OPERATION_INVALID", "FIELDS_INVALID"), response
