"""Phase 3b: a bound acquire must perform socket I/O with the broker lock free.

The concurrent path is a real broker call that must take ``CommandBroker._lock``
(``stop_attempt``), and the ownership object is the real ``Ownership`` implementation
so its ``authorized``/``revoke`` lock semantics are genuinely present.
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


class _FakeClientPort:
    """The session-owned client surface the broker validates."""

    def __init__(self):
        self.closed = []

    def arm_generation(self, ticket):
        return True

    def reserve(self, *args, **kwargs):
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


class _History:
    version = 1
    incarnation = "clock-session"


class _Admission:
    def owner_is_active(self):
        return True

    def revoke_current(self, reason):
        self.revoked = reason
        return True


def _real_registry():
    from so101_demo.adapters.act.authority_transaction import AuthorityTransactionRegistry

    return AuthorityTransactionRegistry(clock_ns=lambda: 9906000000, history=_History())


def _real_session(arm_impl, confirm_impl=None):
    """A real-typed BoundAuthoritySession with a real composition and fake client."""

    from so101_demo.adapters.act.broker_authority_composition import BrokerAuthorityComposition

    class _Port:
        def identity_snapshot(self, role):
            return (1, f"inc-{role}", f"boot-{role}")

        def close(self, reason="CLOSED", generation=None):
            return True

    session = object.__new__(BoundAuthoritySession)
    session.roles = ("arm", "gripper")
    session.composition = BrokerAuthorityComposition(history=_History(), admission=_Admission(),
                                                     registry=_real_registry(),
                                                     controller_port=_Port(),
                                                     expected_roles=("arm", "gripper"))
    session._reservation_port = _FakeClientPort()
    session._armed = None
    session._confirmed = False
    session._fenced_reason = None
    session.arm = arm_impl
    session.confirm = confirm_impl or (lambda ownership=None: {"arm": (1, "inc-arm", "boot-arm")})
    return session


def _broker(session, driver=None, ownership=None):
    import so101_demo.adapters.act.command_broker as module

    driver = driver or _Driver()
    ownership = ownership or Ownership()
    broker = module.CommandBroker(driver, ownership=ownership,
                                  reservation_port=session.reservation_port,
                                  authority=session.composition,
                                  bound_authority_session=session)
    return broker, driver, ownership


def _request():
    return {"protocol_version": 1, "request_id": "r1", "owner": "act", "session_id": "session",
            "attempt_id": "attempt", "lease_token": None, "operation": "acquire"}


def _run_acquire_with_blocked_arm(hold_seconds=5.0):
    """Start a bound acquire whose arm blocks; return handles for assertions."""

    entered, release = threading.Event(), threading.Event()

    def slow_arm(ticket):
        entered.set()
        release.wait(hold_seconds)          # stands in for slow socket I/O
        return ticket[0]

    session = _real_session(slow_arm)
    broker, driver, ownership = _broker(session)
    outcome = {}

    def run_acquire():
        try:
            outcome["response"] = broker.handle(_request(), "conn-1")
        except Exception as failure:        # noqa: BLE001
            outcome["error"] = failure

    thread = threading.Thread(target=run_acquire, daemon=True)
    thread.start()
    assert entered.wait(5.0), "the bound arm barrier was never reached"
    return broker, driver, ownership, outcome, release, thread


def test_stop_attempt_completes_while_bound_arm_is_blocked():
    """The production fix: socket I/O runs with the broker lock released."""

    broker, driver, ownership, outcome, release, thread = _run_acquire_with_blocked_arm()
    stop_done = threading.Event()

    def run_stop():
        broker.stop_attempt("CONCURRENT_REVOKE")      # must acquire broker._lock
        stop_done.set()

    stop_thread = threading.Thread(target=run_stop, daemon=True)
    stop_thread.start()
    completed_while_io = stop_done.wait(1.0)
    release.set()
    thread.join(10.0)
    stop_thread.join(5.0)
    assert completed_while_io, (
        "stop_attempt could not complete while the bound arm was blocked: the broker "
        "lock is being held across socket I/O")
    response = outcome.get("response") or {}
    assert response.get("lease_token") is None, "a revoked acquire must not return a lease"
    assert "conn-1" not in broker._participants
    assert broker._armed_generation is None


def test_the_barrier_detects_a_lock_holding_acquire(monkeypatch):
    """Negative control: with the old lock-holding shape the barrier must fail.

    This proves the test above is sensitive to the violation rather than passing for
    an unrelated reason.
    """

    import so101_demo.adapters.act.command_broker as module

    def lock_holding_acquire(self, scope, connection_id, response):
        with self._lock:                              # the pre-fix shape
            token = self.ownership.acquire(*scope[1:])
            ticket = self.ownership.ticket(token, *scope[1:])
            self._bound_authority_session.arm(ticket)
        raise PermissionError('TEST_LOCK_HOLDING_SHIM')

    monkeypatch.setattr(module.CommandBroker, "_acquire_bound", lock_holding_acquire)
    broker, driver, ownership, outcome, release, thread = _run_acquire_with_blocked_arm()
    stop_done = threading.Event()

    def run_stop():
        broker.stop_attempt("CONCURRENT_REVOKE")
        stop_done.set()

    stop_thread = threading.Thread(target=run_stop, daemon=True)
    stop_thread.start()
    blocked = not stop_done.wait(1.0)
    release.set()
    thread.join(10.0)
    stop_thread.join(5.0)
    assert blocked, "the barrier failed to notice a lock-holding acquire"
