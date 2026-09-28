"""Phase 3b: the real install/arm/confirm order, modelled on the C++ gate.

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

from so101_demo.adapters.act.broker_authority_wiring import (confirm_role_identities,
                                                             install_bound_authority)
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
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        for _ in range(6):
            try:
                connection, _ = self.socket.accept()
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
        self.socket.close()
        self.thread.join(5.0)


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


def test_identity_query_before_arm_really_fails():
    services = _services(("arm", "gripper"))
    try:
        client = _client(services)
        history, admission, registry = _domain()
        composition = install_bound_authority(reservation_port=client, session_id="clock-session",
                                              roles=("arm", "gripper"), history=history,
                                              admission=admission, registry=registry)
        assert composition.sealed() is True
        with pytest.raises(Exception):            # C++ gate is unarmed -> no identity
            client.query_identity("arm")
        assert services["arm"].queries == 1
    finally:
        for service in services.values():
            service.close()


def test_after_arm_every_role_confirms_with_the_ticket_generation():
    services = _services(("arm", "gripper"))
    try:
        client = _client(services)
        history, admission, registry = _domain()
        composition = install_bound_authority(reservation_port=client, session_id="clock-session",
                                              roles=("arm", "gripper"), history=history,
                                              admission=admission, registry=registry)
        ticket = (4, "session", "broker", "permit", 1)
        assert client.arm_generation(ticket) is True
        confirmed = confirm_role_identities(reservation_port=client, composition=composition,
                                            roles=("arm", "gripper"), ticket=ticket)
        assert confirmed["arm"][0] == 4 and confirmed["gripper"][0] == 4
        assert composition.confirmed_identity("arm") == (4, "inc-arm", "boot-arm")
    finally:
        for service in services.values():
            service.close()


def test_partial_role_query_returns_no_lease_and_really_closes():
    services = _services(("arm", "gripper"))
    try:
        client = _client(services)
        history, admission, registry = _domain()
        composition = install_bound_authority(reservation_port=client, session_id="clock-session",
                                              roles=("arm", "gripper"), history=history,
                                              admission=admission, registry=registry)
        ticket = (4, "session", "broker", "permit", 1)
        assert client.arm_generation(ticket) is True     # real order: armed first
        assert services["arm"].armed_generation == 4 and services["gripper"].armed_generation == 4
        services["gripper"].refuse_identity = True       # fail only at the query stage
        with pytest.raises(Exception):
            confirm_role_identities(reservation_port=client, composition=composition,
                                    roles=("arm", "gripper"), ticket=ticket)
        assert services["arm"].closed == [4], "close must reach every attempted role"
        assert services["gripper"].closed == [4], "close must reach every attempted role"
        with pytest.raises(Exception):
            composition.confirmed_identity("gripper")   # no lease was handed out
    finally:
        for service in services.values():
            service.close()


def test_generation_drift_is_refused_and_closed():
    services = _services(("arm", "gripper"))     # the production role set
    try:
        client = _client(services)
        history, admission, registry = _domain()
        composition = install_bound_authority(reservation_port=client, session_id="clock-session",
                                              roles=("arm", "gripper"), history=history,
                                              admission=admission, registry=registry)
        ticket = (4, "session", "broker", "permit", 1)
        assert client.arm_generation(ticket) is True     # real order: armed first
        services["arm"].reported_generation_override = 9  # service reports another generation
        with pytest.raises(Exception):
            confirm_role_identities(reservation_port=client, composition=composition,
                                    roles=("arm", "gripper"), ticket=ticket)
        with pytest.raises(Exception):
            composition.confirmed_identity("arm")      # nothing was committed
        with pytest.raises(Exception):
            composition.confirmed_identity("gripper")  # and not partially either
        assert services["arm"].closed == [4] and services["gripper"].closed == [4]
    finally:
        for service in services.values():
            service.close()
