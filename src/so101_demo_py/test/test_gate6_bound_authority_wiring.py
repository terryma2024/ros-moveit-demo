"""Phase 3b: the single production composition root, using the real client.

Each role is confirmed through a real authenticated ACK over a real UNIX socket;
a missing or failed role must leave the authority uninstalled (fail-closed).
"""

import os
import socket
import struct
import threading
import uuid
from pathlib import Path

import pytest

from so101_demo.adapters.act.broker_authority_composition import BrokerAuthorityComposition
from so101_demo.adapters.act.broker_authority_wiring import install_bound_authority
from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient

ROLE_CODES = {"arm": 1, "gripper": 2, "neck": 3}


def _bounded(value):
    raw = value.encode("ascii")
    return bytes((len(raw),)) + raw


def _identity_body(role, generation, incarnation, boot):
    return (b"SOID" + bytes((1, 1)) + bytes((role,)) + struct.pack(">Q", generation)
            + _bounded(incarnation) + _bounded(boot))


class _AckServer:
    def __init__(self, role, capability):
        self.role = role
        self.capability = capability
        self.short_dir = Path(f"/tmp/so101-debug-act-b3-wire-{uuid.uuid4().hex[:8]}")
        self.short_dir.mkdir(mode=0o700, exist_ok=True)
        self.path = self.short_dir / f"{role}.sock"
        assert len(os.fsencode(str(self.path))) <= 107
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.socket.listen(1)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        # the real service is long-lived: arm, per-role query and close each arrive on
        # their own short connection
        self.socket.settimeout(0.05)
        self._stop = threading.Event()
        for _ in range(8):
            if self._stop.is_set():
                return
            try:
                connection, _ = self.socket.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return
            self._handle(connection)

    def _handle(self, connection):
        with connection:
            header = connection.recv(4)
            if len(header) != 4:
                return
            size = struct.unpack(">I", header)[0]
            body = b""
            while len(body) < size:
                chunk = connection.recv(size - len(body))
                if not chunk:
                    return
                body += chunk
            if body[:4] == b"SOGR" and len(body) > 5 and body[5] == 3:
                # arm: the real service records the generation its identity reports
                generation = int.from_bytes(body[38:46], "big")
                self.armed_generation = generation
                connection.sendall(b"SOGA" + bytes((1, 0)) + b"\x00\x00"
                                   + struct.pack(">Q", generation))
            elif body[:4] == b"SOGR" and len(body) > 5 and body[5] == 2:
                generation = int.from_bytes(body[38:46], "big")
                self.armed_generation = None
                connection.sendall(b"SOGA" + bytes((1, 0)) + b"\x00\x00"
                                   + struct.pack(">Q", generation))
            elif body[:4] == b"SOIA":
                generation = getattr(self, "armed_generation", 1) or 1
                payload = _identity_body(ROLE_CODES[self.role], generation,
                                         f"inc-{self.role}", f"boot-{self.role}")
                connection.sendall(struct.pack(">I", len(payload)) + payload)

    def close(self):
        if hasattr(self, "_stop"):
            self._stop.set()
        try:
            self.socket.close()
        except OSError:
            pass
        self.thread.join(1.0)
        # retained task evidence: the /tmp directory is never removed here


def _clock():
    return 9906000000


def _real_client(roles):
    servers = {}
    capabilities = {}
    for index, role in enumerate(sorted(roles)):
        capability = bytes([index + 1]) * 32
        servers[role] = _AckServer(role, capability)
        capabilities[role] = capability
    client = ControllerReservationClient({role: str(server.path) for role, server in servers.items()},
                                         capability=capabilities, timeout_s=1.0)
    return client, servers


def _domain():
    from so101_demo.adapters.act.authority_transaction import AuthorityTransactionRegistry

    class _History:
        version = 1
        incarnation = "clock-session"

    class _Admission:
        def admit_sample(self, **kwargs):
            return {"step": 1, "history_version": 1,
                    "identity": ("clock-session",) * 3 + (1, 1),
                    "commit_receipt": {"step": 1, "commit_monotonic_ns": 1,
                                       "incarnation": "clock-session"}}

        def owner_is_active(self):
            return True

        def revoke_current(self, reason):
            return True

    history = _History()
    return history, _Admission(), AuthorityTransactionRegistry(clock_ns=_clock, history=history)


def test_install_does_no_io_then_arm_and_confirm_bind_every_role():
    """A-prime order: install seals only; identities confirm after arm."""

    from so101_demo.adapters.act.broker_authority_wiring import BoundAuthoritySession

    client, servers = _real_client(("arm", "gripper"))
    try:
        history, admission, registry = _domain()
        session = BoundAuthoritySession(reservation_port=client, session_id="clock-session",
                                        roles=("arm", "gripper"), history=history,
                                        admission=admission, registry=registry)
        # install performed no controller I/O: nothing is cached for either role yet
        for role in ("arm", "gripper"):
            with pytest.raises(Exception):
                client.identity_snapshot(role)
        assert session.composition.sealed() is True

        ticket = (4, "clock-session", "broker", "permit", 1)
        assert session.arm(ticket) == 4
        confirmed = session.confirm()
        assert set(confirmed) == {"arm", "gripper"}
        assert client.identity_snapshot("arm") == (4, "inc-arm", "boot-arm")
        assert session.composition.confirmed_identity("arm") == (4, "inc-arm", "boot-arm")
        assert session.composition.confirmed_identity("gripper")[0] == 4
    finally:
        for server in servers.values():
            server.close()


def test_a_role_without_an_ack_server_leaves_authority_uninstalled():
    """A partial role set must never reach a confirmed identity."""

    from so101_demo.adapters.act.broker_authority_wiring import BoundAuthoritySession

    client, servers = _real_client(("arm",))
    try:
        history, admission, registry = _domain()
        session = BoundAuthoritySession(reservation_port=client, session_id="clock-session",
                                        roles=("arm", "gripper"), history=history,
                                        admission=admission, registry=registry)
        ticket = (4, "clock-session", "broker", "permit", 1)
        with pytest.raises(Exception):
            session.arm(ticket)          # the gripper socket does not exist
        for role in ("arm", "gripper"):
            with pytest.raises(Exception):
                session.composition.confirmed_identity(role)
            with pytest.raises(Exception):
                client.identity_snapshot(role)
        assert session.fenced_reason is not None, "a failed arm must fence the session"
    finally:
        for server in servers.values():
            server.close()


def test_invalid_or_empty_role_sets_are_refused():
    client, servers = _real_client(("arm",))
    try:
        history, admission, registry = _domain()
        for roles in ((), ("base",), ("arm", "base")):
            with pytest.raises(ValueError, match="BOUND_AUTHORITY_ROLES_INVALID"):
                install_bound_authority(reservation_port=client, session_id="clock-session",
                                        roles=roles, history=history,
                                        admission=admission, registry=registry)
    finally:
        for server in servers.values():
            server.close()


def test_a_missing_domain_piece_is_refused_rather_than_fabricated():
    client, servers = _real_client(("arm",))
    try:
        history, admission, registry = _domain()
        with pytest.raises(ValueError, match="BOUND_AUTHORITY_DOMAIN_REQUIRED"):
            install_bound_authority(reservation_port=client, session_id="clock-session",
                                    roles=("arm",), history=None,
                                    admission=admission, registry=registry)
    finally:
        for server in servers.values():
            server.close()
