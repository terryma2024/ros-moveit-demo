"""Phase 3b: the shared one-shot BoundAuthoritySession used by both production roots.

The fake service mirrors the frozen C++ behaviour: a SOIA identity query is refused
while the gate is unarmed, so identity can only be confirmed after arm_generation.
"""

import os
import socket
import struct
import threading
import uuid
from pathlib import Path

import pytest

from so101_demo.adapters.act.broker_authority_wiring import BoundAuthoritySession
from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient

ROLE_CODES = {"arm": 1, "gripper": 2, "neck": 3}


def _bounded(value):
    raw = value.encode("ascii")
    return bytes((len(raw),)) + raw


class _Service:
    """Unarmed refuses SOIA; arm(op 3) opens the generation; close(op 2) records it."""

    def __init__(self, role, generation=None):
        self.role = role
        self.armed_generation = generation
        self.refuse_identity = False          # explicit query-stage failure switch
        self.reported_generation_override = None   # explicit query-stage drift switch
        self.closed = []
        self.queries = 0
        self.short_dir = Path(f"/tmp/so101-debug-act-b3-order-{uuid.uuid4().hex[:8]}")
        self.short_dir.mkdir(mode=0o700, exist_ok=True)
        self.path = self.short_dir / f"{role}.sock"
        assert len(os.fsencode(str(self.path))) <= 107
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.socket.listen(4)
        self.socket.settimeout(0.05)                 # short accept: teardown is immediate
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        for _ in range(6):
            if self._stop.is_set():
                return
            try:
                connection, _ = self.socket.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return
            with connection:
                header = connection.recv(4)
                if len(header) != 4:
                    continue
                size = struct.unpack(">I", header)[0]
                body = b""
                while len(body) < size:
                    chunk = connection.recv(size - len(body))
                    if not chunk:
                        break
                    body += chunk
                if body[:4] == b"SOIA":
                    self.queries += 1
                    if self.armed_generation is None or self.refuse_identity:
                        payload = b"SOID" + bytes((1, 0))          # no identity on offer
                    else:
                        reported = (self.reported_generation_override
                                    if self.reported_generation_override is not None
                                    else self.armed_generation)
                        payload = (b"SOID" + bytes((1, 1)) + bytes((ROLE_CODES[self.role],))
                                   + struct.pack(">Q", reported)
                                   + _bounded(f"inc-{self.role}")
                                   + _bounded(f"boot-{self.role}"))
                    connection.sendall(struct.pack(">I", len(payload)) + payload)
                elif body[5] == 3:                                  # arm (body offsets!)
                    generation = struct.unpack(">Q", body[38:46])[0]
                    self.armed_generation = generation
                    connection.sendall(b"SOGA" + bytes((1, 0)) + b"\x00\x00"
                                       + struct.pack(">Q", generation))
                elif body[5] == 2:                                  # close (body offsets!)
                    generation = struct.unpack(">Q", body[38:46])[0]
                    self.closed.append(generation)
                    self.armed_generation = None
                    connection.sendall(b"SOGA" + bytes((1, 0)) + b"\x00\x00"
                                       + struct.pack(">Q", generation))

    def close(self):
        self._stop.set()                             # self-wake, no 5 s join per instance
        try:
            self.socket.close()
        except OSError:
            pass
        self.thread.join(1.0)


def _clock():
    return 9906000000


def _client(services):
    capabilities = {role: bytes([index + 1]) * 32 for index, role in enumerate(sorted(services))}
    return ControllerReservationClient({role: str(service.path) for role, service in services.items()},
                                       capability=capabilities, timeout_s=1.0)


def _domain():
    from so101_demo.adapters.act.authority_transaction import AuthorityTransactionRegistry

    class _History:
        version = 1
        incarnation = "clock-session"

    class _Admission:
        def owner_is_active(self):
            return True

        def revoke_current(self, reason):
            self.revoked = reason
            return True

    history = _History()
    return history, _Admission(), AuthorityTransactionRegistry(clock_ns=_clock, history=history)


def _services(roles):
    return {role: _Service(role) for role in roles}


def _session(services, roles=("arm", "gripper")):
    client = _client(services)
    history, admission, registry = _domain()
    session = BoundAuthoritySession(reservation_port=client, session_id="clock-session",
                                    roles=roles, history=history, admission=admission,
                                    registry=registry)
    session.admission = admission            # test handles for observable-state assertions
    return client, session, registry


def test_install_performs_no_io_and_pre_arm_query_fails():
    services = _services(("arm", "gripper"))
    try:
        client, session, _ = _session(services)
        assert session.composition.sealed() is True
        assert services["arm"].queries == 0 and services["gripper"].queries == 0  # no I/O at install
        with pytest.raises(Exception):
            client.query_identity("arm")          # the C++ gate is still unarmed
    finally:
        for service in services.values():
            service.close()


def test_arm_then_confirm_binds_every_frozen_role_atomically():
    services = _services(("arm", "gripper"))
    try:
        client, session, _ = _session(services)
        ticket = (4, "session", "broker", "permit", 1)
        assert session.arm(ticket) == 4
        confirmed = session.confirm()
        assert set(confirmed) == {"arm", "gripper"}
        assert session.composition.confirmed_identity("arm") == (4, "inc-arm", "boot-arm")
        assert session.composition.confirmed_identity("gripper") == (4, "inc-gripper", "boot-gripper")
    finally:
        for service in services.values():
            service.close()


def test_partial_query_returns_no_lease_closes_and_revokes():
    services = _services(("arm", "gripper"))
    try:
        client, session, _ = _session(services)
        ticket = (4, "session", "broker", "permit", 1)
        assert session.arm(ticket) == 4
        services["gripper"].refuse_identity = True
        with pytest.raises(Exception):
            session.confirm()
        assert services["arm"].closed == [4] and services["gripper"].closed == [4]
        for role in ("arm", "gripper"):
            with pytest.raises(Exception):
                session.composition.confirmed_identity(role)      # nothing committed
    finally:
        for service in services.values():
            service.close()


def test_generation_drift_returns_no_lease_and_closes():
    services = _services(("arm", "gripper"))
    try:
        client, session, _ = _session(services)
        ticket = (4, "session", "broker", "permit", 1)
        assert session.arm(ticket) == 4
        services["arm"].reported_generation_override = 9
        with pytest.raises(Exception):
            session.confirm()
        assert services["arm"].closed == [4] and services["gripper"].closed == [4]
        with pytest.raises(Exception):
            session.composition.confirmed_identity("arm")
    finally:
        for service in services.values():
            service.close()


def test_arming_twice_and_confirming_unarmed_are_refused():
    services = _services(("arm", "gripper"))
    try:
        client, session, _ = _session(services)
        with pytest.raises(ValueError, match="NOT_ARMED"):
            session.confirm()
        ticket = (4, "session", "broker", "permit", 1)
        assert session.arm(ticket) == 4
        with pytest.raises(ValueError, match="ALREADY_ARMED"):
            session.arm(ticket)
    finally:
        for service in services.values():
            service.close()


def test_confirm_cannot_widen_or_narrow_the_frozen_role_set():
    services = _services(("arm", "gripper"))
    try:
        client, session, registry = _session(services)
        ticket = (4, "session", "broker", "permit", 1)
        assert session.arm(ticket) == 4
        with pytest.raises(Exception):
            # a caller cannot substitute a different role set at confirm time
            session.composition.register_live_roles(entries=[
                {"role": "arm", "generation": 4, "incarnation": "inc-arm", "boot": "boot-arm",
                 "ticket": ticket}])
        with pytest.raises(Exception):
            session.composition.confirmed_identity("arm")
    finally:
        for service in services.values():
            service.close()


def test_revoke_clears_live_identities_and_really_closes():
    services = _services(("arm", "gripper"))
    try:
        client, session, _ = _session(services)
        ticket = (4, "session", "broker", "permit", 1)
        assert session.arm(ticket) == 4
        session.confirm()
        assert session.composition.confirmed_identity("arm")[0] == 4
        session.composition.revoke("BOUND_AUTHORITY_ABORTED:4")
        with pytest.raises(Exception):
            session.composition.confirmed_identity("arm")     # cache cleared, no revival
        assert services["arm"].closed == [4], "revoke closes the live generation for real"
    finally:
        for service in services.values():
            service.close()


def test_revoke_close_failure_still_terminalizes_registry_and_admission():
    """A controller close failure must not leave a logically live authority."""

    services = _services(("arm", "gripper"))
    try:
        client, session, registry = _session(services)
        admission = session.admission
        ticket = (4, "session", "broker", "permit", 1)
        assert session.arm(ticket) == 4
        session.confirm()
        calls = []

        class _FailingClose:
            def identity_snapshot(self, role):
                return client.identity_snapshot(role)

            def close(self, reason="CLOSED", generation=None):
                calls.append(generation)
                raise RuntimeError("controller unreachable")

        session.composition.controller_port = _FailingClose()
        # the controller close fails, but the authority is already terminated
        with pytest.raises(Exception):
            session.composition.revoke("FENCE_TEST")
        assert calls == [4], "the real close was attempted"
        assert session.composition.fencing_required() is True
        failures = session.composition.revocation_failures()
        assert any(entry.startswith("CLOSE_FAILED:4:") for entry in failures), failures
        with pytest.raises(Exception):
            session.composition.confirmed_identity("arm")       # identity cleared
        # the logical termination really happened despite the controller failure
        assert admission.revoked == "FENCE_TEST", "admission must be revoked with the reason"
        assert registry.revoke_completed_without_waiting() is True, \
            "registry must be revoked despite the controller close failure"
        with pytest.raises(Exception):
            session.composition.reservation_binding("any-handle")
    finally:
        for service in services.values():
            service.close()


def test_arm_failure_fences_the_session_permanently():
    services = _services(("arm", "gripper"))
    try:
        client, session, _ = _session(services)

        class _RefusingArm:
            def arm_generation(self, ticket):
                return False

        session._reservation_port = _RefusingArm()
        with pytest.raises(RuntimeError, match="ARM_FAILED"):
            session.arm((4, "session", "broker", "permit", 1))
        assert session.fenced_reason == "ARM_REFUSED"
        with pytest.raises(RuntimeError, match="SESSION_FENCED"):
            session.arm((4, "session", "broker", "permit", 1))
        with pytest.raises(RuntimeError, match="SESSION_FENCED"):
            session.confirm()
    finally:
        for service in services.values():
            service.close()


def test_confirm_failure_fences_and_a_second_confirm_is_refused():
    services = _services(("arm", "gripper"))
    try:
        client, session, _ = _session(services)
        ticket = (4, "session", "broker", "permit", 1)
        assert session.arm(ticket) == 4
        services["gripper"].refuse_identity = True
        with pytest.raises(Exception):
            session.confirm()
        assert session.fenced_reason is not None
        with pytest.raises(RuntimeError, match="SESSION_FENCED"):
            session.confirm()
        with pytest.raises(RuntimeError, match="SESSION_FENCED"):
            session.arm(ticket)
    finally:
        for service in services.values():
            service.close()


def test_a_successful_confirm_consumes_the_session():
    services = _services(("arm", "gripper"))
    try:
        client, session, _ = _session(services)
        ticket = (4, "session", "broker", "permit", 1)
        assert session.arm(ticket) == 4
        session.confirm()
        with pytest.raises(RuntimeError, match="SESSION_CONSUMED"):
            session.confirm()
        with pytest.raises(RuntimeError, match="SESSION_CONSUMED"):
            session.arm(ticket)
    finally:
        for service in services.values():
            service.close()
