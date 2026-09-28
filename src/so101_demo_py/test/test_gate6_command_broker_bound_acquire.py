"""Phase 3b: real broker.handle acquire tests driving the real session lifecycle.

The session's arm/confirm methods are never replaced: a configurable reservation
client (arm result, per-role query result, query barrier, close result) drives the
production BoundAuthoritySession.arm/confirm and the real composition registration.
"""

import threading
import time

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
    """Configurable real-surface reservation client double."""

    def __init__(self, *, arm=True, queries=None, close_error=False, query_barrier=None):
        self.arm_result = arm
        self.queries = queries or {}
        self.close_error = close_error
        self.query_barrier = query_barrier
        self.closed = []
        self.arm_calls = []
        self.query_calls = []

    def arm_generation(self, ticket):
        self.arm_calls.append(ticket)
        if isinstance(self.arm_result, Exception):
            raise self.arm_result
        if self.arm_result == "raise":
            raise RuntimeError("BOUND_AUTHORITY_ARM_FAILED")
        return self.arm_result is True

    def query_identity(self, role):
        self.query_calls.append(role)
        if self.query_barrier is not None:
            self.query_barrier(role)
        outcome = self.queries.get(role, "ok")
        if outcome == "raise":
            raise RuntimeError(f"IDENTITY_QUERY_FAILED:{role}")
        if isinstance(outcome, tuple):
            return outcome
        return (1, f"inc-{role}", f"boot-{role}")

    def reserve(self, *a, **k):
        return True

    def close_generation(self, generation):
        self.closed.append(generation)
        if self.close_error:
            raise RuntimeError("controller unreachable")
        return True

    def close(self, reason="CLOSED", generation=None):
        self.closed.append(generation)
        if self.close_error:
            raise RuntimeError("controller unreachable")
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
    def __init__(self, close_error=False):
        self.close_error = close_error
        self.closed = []

    def identity_snapshot(self, role):
        return (1, f"inc-{role}", f"boot-{role}")

    def close(self, reason="CLOSED", generation=None):
        self.closed.append(generation)
        if self.close_error:
            raise RuntimeError("controller unreachable")
        return True


def _registry():
    from so101_demo.adapters.act.authority_transaction import AuthorityTransactionRegistry

    return AuthorityTransactionRegistry(clock_ns=lambda: 9906000000, history=_History())


def _session(client=None, port=None, admission=None):
    """A real BoundAuthoritySession with real arm/confirm and real composition."""

    from so101_demo.adapters.act.broker_authority_composition import BrokerAuthorityComposition

    client = client or _Client()
    admission = admission or _Admission()
    port = port or _Port()
    composition = BrokerAuthorityComposition(history=_History(), admission=admission,
                                             registry=_registry(),
                                             controller_port=port,
                                             expected_roles=("arm", "gripper"))
    session = object.__new__(BoundAuthoritySession)     # real type; methods untouched
    session.roles = ("arm", "gripper")
    session.composition = composition
    session._reservation_port = client
    session._armed = None
    session._confirmed = False
    session._fenced_reason = None
    session._port = port
    return session, admission, client


def _broker(session, driver=None, ownership=None):
    import so101_demo.adapters.act.command_broker as module

    driver = driver or _Driver()
    ownership = ownership or Ownership()
    broker = module.CommandBroker(driver, ownership=ownership,
                                  reservation_port=session.reservation_port,
                                  authority=session.composition,
                                  bound_authority_session=session)
    return broker, driver, ownership


def _request(request_id="r1"):
    return {"protocol_version": 1, "request_id": request_id, "owner": "act",
            "session_id": "session", "attempt_id": "attempt", "lease_token": None,
            "operation": "acquire"}


def test_nominal_success_drives_the_real_lifecycle_and_registers_identities():
    session, admission, client = _session()
    broker, driver, ownership = _broker(session)
    response = broker.handle(_request(), "conn-1")
    assert response["accepted"] is True, response
    ticket = broker._participants["conn-1"]
    assert response["lease_token"] == ticket[1]
    assert ticket[2:] == ("act", "session", "attempt")
    assert broker._armed_generation == ticket[0]
    assert broker._acquire_pending is None
    assert client.arm_calls == [ticket], "the real arm_generation was called with the ticket"
    assert client.query_calls == ["arm", "gripper"], "both frozen roles were queried"
    # identities exist only because the nominal confirm really registered them
    assert session.composition.confirmed_identity("arm")[0] == ticket[0]
    assert session.composition.confirmed_identity("gripper")[0] == ticket[0]
    assert session.fenced_reason is None


def test_arm_refusal_via_real_session_closes_the_attempted_generation():
    client = _Client(arm="raise")
    session, admission, _ = _session(client=client)
    broker, driver, ownership = _broker(session)
    response = broker.handle(_request(), "conn-1")
    assert response["accepted"] is False and response.get("lease_token") is None
    assert "conn-1" not in broker._participants and broker._armed_generation is None
    assert broker._acquire_pending is None
    assert session.fenced_reason is not None, "the real session must fence itself"
    assert session._port.closed, "the composition close was attempted"
    assert admission.revoked is not None and driver.stop_all_calls
    for role in ("arm", "gripper"):
        with pytest.raises(Exception):
            session.composition.confirmed_identity(role)


@pytest.mark.parametrize("queries", [{"gripper": "raise"},
                                     {"arm": (9, "inc-arm", "boot-arm")}],
                         ids=["partial_identity", "generation_drift"])
def test_confirm_failure_via_real_query_aborts_and_terminates(queries):
    session, admission, client = _session(client=_Client(queries=queries))
    broker, driver, ownership = _broker(session)
    response = broker.handle(_request(), "conn-1")
    assert response["accepted"] is False and response.get("lease_token") is None
    assert "conn-1" not in broker._participants and broker._armed_generation is None
    assert session.fenced_reason is not None
    assert admission.revoked is not None and driver.stop_all_calls
    for role in ("arm", "gripper"):
        with pytest.raises(Exception):
            session.composition.confirmed_identity(role)


def test_close_failure_on_a_post_arm_non_commit_path_commits_nothing():
    """A close failure happens during an actual failed acquire, not after a lease."""

    client = _Client(queries={"gripper": "raise"})
    session, admission, _ = _session(client=client, port=_Port(close_error=True))
    broker, driver, ownership = _broker(session)
    response = broker.handle(_request(), "conn-1")
    assert response["accepted"] is False and response.get("lease_token") is None
    assert "conn-1" not in broker._participants
    assert broker._armed_generation is None
    assert broker._acquire_pending is None
    assert session.composition.fencing_required() is True
    assert any(entry.startswith("CLOSE_FAILED") for entry in
               session.composition.revocation_failures()), \
        session.composition.revocation_failures()
    assert admission.revoked is not None and driver.stop_all_calls


def test_second_acquire_while_pending_is_rejected():
    session, admission, _ = _session()
    broker, driver, ownership = _broker(session)
    with broker._lock:
        broker._acquire_pending = (1, "token", "act", "session", "attempt")
    response = broker.handle(_request("r2"), "conn-2")
    assert response["accepted"] is False
    assert "PENDING" in (response.get("error") or ""), response


def test_revoke_while_the_real_query_phase_blocks_commits_nothing():
    entered, release = threading.Event(), threading.Event()

    def barrier(role):
        if role == "arm":
            entered.set()
            release.wait(5.0)

    session, admission, client = _session(client=_Client(query_barrier=barrier))
    broker, driver, ownership = _broker(session)
    outcome = {}

    def run_acquire():
        try:
            outcome["response"] = broker.handle(_request(), "conn-1")
        except Exception as failure:                   # noqa: BLE001
            outcome["error"] = failure

    thread = threading.Thread(target=run_acquire, daemon=True)
    thread.start()
    assert entered.wait(5.0), "the real identity query barrier was never reached"
    stop_done = threading.Event()

    def run_stop():
        broker.stop_attempt("CONCURRENT_REVOKE")
        stop_done.set()

    stop_thread = threading.Thread(target=run_stop, daemon=True)
    stop_thread.start()
    assert stop_done.wait(2.0), "stop_attempt could not run during the query phase"
    release.set()
    thread.join(10.0)
    stop_thread.join(5.0)
    response = outcome.get("response") or {}
    assert response.get("lease_token") is None
    assert "conn-1" not in broker._participants
    assert broker._armed_generation is None
    assert broker._acquire_pending is None
    assert ownership.state != "RUNNING"
    for role in ("arm", "gripper"):
        with pytest.raises(Exception):
            session.composition.confirmed_identity(role)


def test_abort_is_idempotent_and_closes_exactly_once():
    session, admission, client = _session()
    broker, driver, ownership = _broker(session)
    assert broker.handle(_request(), "conn-1")["accepted"] is True
    session.abort("FIRST")
    session.abort("SECOND")
    session.abort("FIRST")
    # the composition clears its live generation, so the close happens once
    assert len(session._port.closed) == 1, session._port.closed
    assert session.fenced_reason == "FIRST", "the first terminal reason is preserved"
