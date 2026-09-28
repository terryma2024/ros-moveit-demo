"""Bounded off-graph registration of native controller action goals."""

import os
from pathlib import Path
import socket
import stat
import threading
import time
import uuid

from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import serialize_message


MAX_BODY_BYTES = 1_048_640
_ROLE_CODES = {"arm": 1, "gripper": 2, "neck": 3}
_MAX_INGRESS_SNAPSHOT_AGE_NS = 200_000_000


def _encode_bound_frame(*, generation, goal_uuid, role, permit_uuid, target_digest,
                        claim_monotonic_ns, deadline_ns, session_id, broker_incarnation,
                        controller_incarnation, controller_boot_incarnation, goal_cdr,
                        capability):
    """Private v2 binary codec (frozen schema); never a public authority API.

    The capability is mandatory: it is never defaulted, must be exactly 32 bytes
    and must not be all zeroes.
    """

    import struct

    if not isinstance(capability, bytes) or len(capability) != 32 or not any(capability):
        raise ValueError("BOUND_CAPABILITY_INVALID")
    if type(generation) is not int or generation <= 0:
        raise ValueError("BOUND_GENERATION_INVALID")
    if len(bytes(goal_uuid)) != 16 or not any(goal_uuid):
        raise ValueError("BOUND_GOAL_UUID_INVALID")
    if type(role) is not int or role not in (1, 2, 3):
        raise ValueError("BOUND_ROLE_INVALID")
    if len(bytes(permit_uuid)) != 16 or not any(permit_uuid) \
            or (permit_uuid[6] >> 4) != 4 or (permit_uuid[8] & 0xC0) != 0x80:
        raise ValueError("BOUND_PERMIT_UUID_INVALID")
    if len(bytes(target_digest)) != 32 or not any(target_digest):
        raise ValueError("BOUND_DIGEST_INVALID")
    if (type(claim_monotonic_ns) is not int or type(deadline_ns) is not int
            or claim_monotonic_ns <= 0 or deadline_ns <= 0
            or claim_monotonic_ns > deadline_ns):
        raise ValueError("BOUND_TIME_INVALID")
    if not goal_cdr or len(goal_cdr) > 1048576:
        raise ValueError("BOUND_GOAL_INVALID")

    def bounded(value):
        raw = value.encode("ascii")
        if not 0 < len(raw) <= 64 or any(byte < 0x20 or byte > 0x7E for byte in raw):
            raise ValueError("BOUND_STRING_INVALID")
        return bytes((len(raw),)) + raw

    body = b"SOGB" + bytes((2, 1)) + capability
    body += struct.pack(">Q", generation) + bytes(goal_uuid) + bytes((role,))
    body += bytes(permit_uuid) + bytes(target_digest)
    body += struct.pack(">q", claim_monotonic_ns) + struct.pack(">q", deadline_ns)
    body += bounded(session_id) + bounded(broker_incarnation)
    body += bounded(controller_incarnation) + bounded(controller_boot_incarnation)
    body += struct.pack(">I", len(goal_cdr)) + goal_cdr
    if len(body) > 1048640:
        raise ValueError("BOUND_BODY_TOO_LARGE")
    return struct.pack(">I", len(body)) + body


class ControllerReservationClient:
    def __init__(self, endpoints, *, capability, timeout_s, deadline_port=None):
        if not isinstance(endpoints, dict) or not endpoints:
            raise ValueError("CONTROLLER_RESERVATION_ENDPOINTS_INVALID")
        paths = {kind: Path(path) for kind, path in endpoints.items()}
        if any(not isinstance(kind, str) or not kind or not path.is_absolute()
               or "\x00" in str(path) or len(os.fsencode(path)) > 107
               for kind, path in paths.items()):
            raise ValueError("CONTROLLER_RESERVATION_ENDPOINTS_INVALID")
        if isinstance(capability, bytes) and len(paths) == 1:
            capabilities = {next(iter(paths)): capability}
        elif isinstance(capability, dict) and capability.keys() == paths.keys():
            capabilities = capability.copy()
        else:
            raise ValueError("CONTROLLER_RESERVATION_CAPABILITY_INVALID")
        if (any(not isinstance(key, bytes) or len(key) != 32 or not any(key)
                for key in capabilities.values())
                or len(set(capabilities.values())) != len(capabilities)):
            raise ValueError("CONTROLLER_RESERVATION_CAPABILITY_INVALID")
        if not isinstance(timeout_s, (int, float)) or not 0 < timeout_s <= 1:
            raise ValueError("CONTROLLER_RESERVATION_TIMEOUT_INVALID")
        if deadline_port is not None and not callable(deadline_port):
            raise TypeError("CONTROLLER_RESERVATION_DEADLINE_INVALID")
        self._paths = paths
        self._capabilities = capabilities
        self._timeout_s = float(timeout_s)
        self._deadline_port = deadline_port
        self._lock = threading.RLock()
        self._attempted = {}
        self._authority = None
        self._confirmed_identities = {}
        self._identity_invalidations = {}

    # --- role-scoped, ACK-confirmed controller identity ---------------------
    @staticmethod
    def _identity_value_problem(field, value):
        if field == "generation":
            return None if type(value) is int and value > 0 else "IDENTITY_GENERATION_INVALID"
        if not isinstance(value, str) or not 0 < len(value) <= 64:
            return "IDENTITY_STRING_INVALID"
        for character in value:
            code = ord(character)
            if code < 0x20 or code > 0x7E:
                return "IDENTITY_STRING_NOT_ASCII"
        return None

    def _cache_confirmed_identity(self, role, *, generation, incarnation, boot):
        """Store one ACK-confirmed identity tuple for exactly this role.

        Only an authenticated arm/query reply may reach this method in production;
        it is never fed by a caller of the public surface.
        """

        if role not in self._paths:
            raise ValueError("CONTROLLER_RESERVATION_ROLE_UNKNOWN")
        for field, value in (("generation", generation), ("incarnation", incarnation),
                             ("boot", boot)):
            problem = self._identity_value_problem(field, value)
            if problem is not None:
                raise ValueError(f"CONTROLLER_RESERVATION_{problem}")
        with self._lock:
            self._confirmed_identities[role] = (generation, incarnation, boot)

    def _invalidate_identity(self, role, *, reason):
        with self._lock:
            self._confirmed_identities.pop(role, None)
            self._identity_invalidations[role] = reason
        return True

    def identity_snapshot(self, role):
        """Lock-only read of this role's confirmed identity: no I/O, no caller data."""

        if role not in self._paths:
            raise ValueError("CONTROLLER_RESERVATION_ROLE_UNKNOWN")
        with self._lock:
            confirmed = self._confirmed_identities.get(role)
            reason = self._identity_invalidations.get(role)
        if confirmed is None:
            raise ValueError(f"CONTROLLER_RESERVATION_IDENTITY_UNAVAILABLE:{role}:{reason}")
        return confirmed

    def _drop_transport(self):
        """A short-lived connection ends; confirmed identity deliberately survives."""

        return True

    def _exchange(self, kind, frame, *, expect):
        """Send one prebuilt frame and parse a bounded authenticated reply."""

        if kind not in self._paths:
            raise PermissionError("CONTROLLER_RESERVATION_KIND_INVALID")
        if not isinstance(frame, (bytes, bytearray)) or len(frame) > MAX_BODY_BYTES:
            raise ValueError("CONTROLLER_RESERVATION_FRAME_TOO_LARGE")
        path = self._paths[kind]
        self._check_path(path)
        deadline = self._deadline()
        body = bytes(frame)
        wire = len(body).to_bytes(4, "big") + body
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self._remaining(deadline))
            connection.connect(str(path))
            connection.settimeout(self._remaining(deadline))
            connection.sendall(wire)
            if expect == "identity":
                header = self._read_exactly(connection, 4, deadline)
                size = int.from_bytes(header, "big")
                if not 0 < size <= MAX_BODY_BYTES:
                    raise RuntimeError("CONTROLLER_IDENTITY_REPLY_INVALID")
                reply = self._read_exactly(connection, size, deadline)
                return self._parse_identity_reply(kind, reply)
            response = self._read_exactly(connection, 16, deadline)
        if (response[:5] != b"SOGA\x01" or response[6:8] != b"\x00\x00"
                or response[5] not in (0, 1)):
            raise RuntimeError("CONTROLLER_RESERVATION_REPLY_INVALID")
        return response[5] == 0

    def _send_prebuilt(self, kind, frame, *, expected_generation):
        """Send a complete wire frame exactly once and validate the 16-byte ACK.

        The frame already carries its own 4-byte length prefix (the frozen golden
        contract), so the declared length must equal len(frame) - 4 and no second
        prefix may be added.
        """

        if kind not in self._paths:
            raise PermissionError("CONTROLLER_RESERVATION_KIND_INVALID")
        body = bytes(frame)
        if len(body) < 4 or int.from_bytes(body[:4], "big") != len(body) - 4:
            raise ValueError("CONTROLLER_RESERVATION_FRAME_LENGTH_INVALID")
        if len(body) - 4 > MAX_BODY_BYTES:
            raise ValueError("CONTROLLER_RESERVATION_FRAME_TOO_LARGE")
        path = self._paths[kind]
        self._check_path(path)
        deadline = self._deadline()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self._remaining(deadline))
            connection.connect(str(path))
            connection.settimeout(self._remaining(deadline))
            connection.sendall(body)                     # one prefix, sent once
            response = self._read_exactly(connection, 16, deadline)
            try:                                          # no trailing bytes permitted
                trailing = connection.recv(1, socket.MSG_DONTWAIT)   # never blocks
            except (BlockingIOError, socket.timeout, TimeoutError):
                trailing = b""
        if trailing:
            raise RuntimeError("CONTROLLER_RESERVATION_REPLY_TRAILING")
        if (response[:4] != b"SOGA" or response[5] not in (0, 1) or response[4] != 1):
            raise RuntimeError("CONTROLLER_RESERVATION_REPLY_INVALID")
        if int.from_bytes(response[8:16], "big") != expected_generation:
            raise RuntimeError("CONTROLLER_RESERVATION_REPLY_GENERATION_MISMATCH")
        return response[5] == 0

    def _read_exactly(self, connection, size, deadline):
        data = bytearray()
        while len(data) < size:
            connection.settimeout(self._remaining(deadline))
            chunk = connection.recv(size - len(data))
            if not chunk:
                raise RuntimeError("CONTROLLER_RESERVATION_REPLY_INCOMPLETE")
            data.extend(chunk)
        return bytes(data)

    def _parse_identity_reply(self, role, reply):
        """Frozen bounded binary identity reply: SOID, version 1, op 1, role, gen, strings."""

        if len(reply) < 6 + 1 + 8 or reply[:4] != b"SOID" or reply[4] != 1 or reply[5] != 1:
            raise RuntimeError("CONTROLLER_IDENTITY_REPLY_INVALID")
        expected_role = {"arm": 1, "gripper": 2, "neck": 3}.get(role)
        if reply[6] != expected_role:
            raise RuntimeError("CONTROLLER_IDENTITY_ROLE_MISMATCH")
        generation = int.from_bytes(reply[7:15], "big")
        offset = 15
        values = []
        for _ in range(2):
            if offset + 1 > len(reply):
                raise RuntimeError("CONTROLLER_IDENTITY_REPLY_INVALID")
            length = reply[offset]
            offset += 1
            if not 0 < length <= 64 or offset + length > len(reply):
                raise RuntimeError("CONTROLLER_IDENTITY_REPLY_INVALID")
            values.append(reply[offset:offset + length].decode("ascii"))
            offset += length
        if offset != len(reply):
            raise RuntimeError("CONTROLLER_IDENTITY_REPLY_TRAILING")
        incarnation, boot = values
        with self._lock:
            previous = self._confirmed_identities.get(role)
        if previous is not None and previous != (generation, incarnation, boot):
            # an authenticated identity change invalidates the cached value
            self._invalidate_identity(role, reason="identity_change")
            raise RuntimeError("CONTROLLER_IDENTITY_CHANGED")
        self._cache_confirmed_identity(role, generation=generation, incarnation=incarnation,
                                       boot=boot)
        return (generation, incarnation, boot)

    def query_identity(self, role):
        """arm/query is where the I/O happens; the cache is only written from its ACK."""

        if role not in self._paths:
            raise ValueError("CONTROLLER_RESERVATION_ROLE_UNKNOWN")
        capability = self._capabilities[role]
        frame = (b"SOIA" + bytes((1, 1)) + capability
                 + bytes((_ROLE_CODES[role],)))      # exactly one role byte
        try:
            return self._exchange(role, frame, expect="identity")
        except Exception:
            self._invalidate_identity(role, reason="arm_failure")
            raise

    def _deadline(self):
        deadline = time.monotonic() + self._timeout_s
        if self._deadline_port is not None:
            remaining = float(self._deadline_port())
            if not remaining > time.monotonic():
                raise TimeoutError("CONTROLLER_RESERVATION_WINDOW_EXPIRED")
            deadline = min(deadline, remaining)
        return deadline

    @staticmethod
    def _remaining(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("CONTROLLER_RESERVATION_TIMEOUT")
        return remaining

    @staticmethod
    def _check_path(path):
        if path != Path(os.path.normpath(path)):
            raise PermissionError("CONTROLLER_RESERVATION_PATH_INVALID")
        ancestor = path.parent
        while True:
            if not stat.S_ISDIR(ancestor.lstat().st_mode):
                raise PermissionError("CONTROLLER_RESERVATION_PATH_INVALID")
            if ancestor == ancestor.parent:
                break
            ancestor = ancestor.parent
        parent = path.parent.lstat()
        endpoint = path.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid()
                or stat.S_IMODE(parent.st_mode) != 0o700
                or not stat.S_ISSOCK(endpoint.st_mode)
                or endpoint.st_uid != os.geteuid()
                or stat.S_IMODE(endpoint.st_mode) != 0o600):
            raise PermissionError("CONTROLLER_RESERVATION_PATH_INVALID")

    def _request(self, kind, operation, generation, goal_uuid, payload):
        if kind not in self._paths:
            raise PermissionError("CONTROLLER_RESERVATION_KIND_INVALID")
        if not isinstance(generation, int) or not 0 < generation < 2**64:
            raise ValueError("CONTROLLER_RESERVATION_GENERATION_INVALID")
        body = (b"SOGR" + bytes((1, operation)) + self._capabilities[kind]
                + generation.to_bytes(8, "big") + goal_uuid + payload)
        if len(body) > MAX_BODY_BYTES:
            raise ValueError("CONTROLLER_RESERVATION_FRAME_TOO_LARGE")
        frame = len(body).to_bytes(4, "big") + body
        path = self._paths[kind]
        self._check_path(path)
        deadline = self._deadline()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self._remaining(deadline))
            connection.connect(str(path))
            connection.settimeout(self._remaining(deadline))
            connection.sendall(frame)
            response = bytearray()
            while len(response) < 16:
                connection.settimeout(self._remaining(deadline))
                chunk = connection.recv(16 - len(response))
                if not chunk:
                    raise RuntimeError("CONTROLLER_RESERVATION_REPLY_INCOMPLETE")
                response.extend(chunk)
        if (response[:5] != b"SOGA\x01" or response[6:8] != b"\x00\x00"
                or int.from_bytes(response[8:16], "big") != generation
                or response[5] not in (0, 1)):
            raise RuntimeError("CONTROLLER_RESERVATION_REPLY_INVALID")
        return response[5] == 0

    def snapshot_generation(self, ticket, kind: str) -> dict:
        """Read one authenticated controller ingress cursor without changing admission."""
        if (not isinstance(ticket, tuple) or len(ticket) != 5
                or kind not in _ROLE_CODES or kind not in self._paths):
            raise ValueError("CONTROLLER_INGRESS_SNAPSHOT_SCOPE_INVALID")
        generation = ticket[0]
        if type(generation) is not int or not 0 < generation < 2**64:
            raise ValueError("CONTROLLER_INGRESS_SNAPSHOT_SCOPE_INVALID")
        role_code = _ROLE_CODES[kind]
        body = (b"SOGR\x01\x04" + self._capabilities[kind]
                + generation.to_bytes(8, "big") + bytes([role_code]) + bytes(15))
        frame = len(body).to_bytes(4, "big") + body
        # snapshot the immutable transport inputs under the lock, then do all socket
        # I/O outside it so a concurrent close/query is never blocked by this exchange
        with self._lock:
            path = self._paths[kind]
            deadline = self._deadline()
        self._check_path(path)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self._remaining(deadline))
            connection.connect(str(path))
            connection.settimeout(self._remaining(deadline))
            connection.sendall(frame)
            response = bytearray()
            while len(response) < 40:
                connection.settimeout(self._remaining(deadline))
                chunk = connection.recv(40 - len(response))
                if not chunk:
                    break
                response.extend(chunk)
        received_ns = time.monotonic_ns()
        if (len(response) != 40 or response[:6] != b"SOGI\x01\x00"
                or response[6] != role_code or response[7] != 0
                or int.from_bytes(response[8:16], "big") != generation):
            raise RuntimeError("CONTROLLER_INGRESS_SNAPSHOT_INVALID")
        sequence = int.from_bytes(response[16:24], "big")
        last_ns = int.from_bytes(response[24:32], "big")
        observed_ns = int.from_bytes(response[32:40], "big")
        if (observed_ns <= 0 or last_ns > observed_ns
                or not 0 <= received_ns - observed_ns <= _MAX_INGRESS_SNAPSHOT_AGE_NS):
            raise ValueError("CONTROLLER_INGRESS_SNAPSHOT_INVALID")
        return {
            "role": kind, "owner_generation": generation,
            "ingress_sequence": sequence,
            "last_ingress_monotonic_ns": last_ns,
            "observed_monotonic_ns": observed_ns,
            "received_monotonic_ns": received_ns,
            "command_authority": False,
        }

    RESERVATION_BINDING_FIELDS = ("permit_id", "goal_uuid", "role", "target_digest",
                                  "session_id", "broker_incarnation", "generation",
                                  "controller_incarnation", "controller_boot_incarnation",
                                  "claim_monotonic_ns", "deadline_ns")

    def install_authority(self, authority):
        """Install the sealed broker-owned composition exactly once.

        The dependency is type-checked against the real class (not duck-typed) and
        cannot be rebound or replaced afterwards.
        """

        from so101_demo.adapters.act.broker_authority_composition import BrokerAuthorityComposition

        with self._lock:
            if self._authority is not None:
                raise ValueError("CONTROLLER_RESERVATION_AUTHORITY_ALREADY_INSTALLED")
            if type(authority) is not BrokerAuthorityComposition:
                raise TypeError("CONTROLLER_RESERVATION_AUTHORITY_INVALID")
            self._authority = authority
        return True

    def reserve(self, ticket, kind, goal, goal_uuid):
        if (not isinstance(ticket, tuple) or not ticket
                or not isinstance(goal, FollowJointTrajectory.Goal)):
            raise TypeError("CONTROLLER_RESERVATION_GOAL_INVALID")
        native_uuid = uuid.UUID(goal_uuid).bytes
        if str(uuid.UUID(goal_uuid)) != goal_uuid:
            raise ValueError("CONTROLLER_RESERVATION_UUID_INVALID")
        payload = serialize_message(goal)
        generation = ticket[0]
        with self._lock:
            self._attempted.setdefault(generation, set()).add(kind)
        return self._request(kind, 1, generation, native_uuid, payload)

    def reserve_bound(self, ticket, kind, goal, goal_uuid, *, handle):
        """Reserve with the frozen SOGB v2 frame built from the installed authority."""

        if (not isinstance(ticket, tuple) or not ticket
                or not isinstance(goal, FollowJointTrajectory.Goal)):
            raise TypeError("CONTROLLER_RESERVATION_GOAL_INVALID")
        if str(uuid.UUID(goal_uuid)) != goal_uuid:
            raise ValueError("CONTROLLER_RESERVATION_UUID_INVALID")
        authority = self._authority
        if authority is None:
            raise ValueError("CONTROLLER_RESERVATION_AUTHORITY_MISSING")
        binding = authority.reservation_binding(handle)
        if binding["role"] != kind or binding["goal_uuid"] != goal_uuid:
            raise ValueError("CONTROLLER_RESERVATION_BINDING_GOAL_MISMATCH")
        generation, controller_incarnation, boot = self.identity_snapshot(kind)
        if (generation != binding["generation"]
                or controller_incarnation != binding["controller_incarnation"]
                or boot != binding["controller_boot_incarnation"]):
            raise ValueError("CONTROLLER_RESERVATION_IDENTITY_MISMATCH")
        role_number = {"arm": 1, "gripper": 2, "neck": 3}[kind]
        frame = _encode_bound_frame(
            generation=binding["generation"], goal_uuid=bytes.fromhex(goal_uuid.replace("-", "")),
            role=role_number, permit_uuid=bytes.fromhex(binding["permit_id"].replace("-", "")),
            target_digest=bytes.fromhex(binding["target_digest"]),
            claim_monotonic_ns=binding["claim_monotonic_ns"],
            deadline_ns=binding["deadline_ns"], session_id=binding["session_id"],
            broker_incarnation=binding["broker_incarnation"],
            controller_incarnation=controller_incarnation,
            controller_boot_incarnation=boot, goal_cdr=serialize_message(goal),
            capability=self._capabilities[kind])
        with self._lock:
            self._attempted.setdefault(generation, set()).add(kind)
        return self._send_prebuilt(kind, frame, expected_generation=generation)

    def arm_generation(self, ticket):
        if set(self._paths) not in ({"arm", "gripper"}, {"arm", "gripper", "neck"}):
            raise ValueError("CONTROLLER_RESERVATION_ROLES_INVALID")
        if not isinstance(ticket, tuple) or len(ticket) != 5:
            raise TypeError("CONTROLLER_RESERVATION_TICKET_INVALID")
        generation = ticket[0]
        # snapshot the role list under the lock, then do every socket exchange
        # outside it: no client lock is held across controller I/O
        with self._lock:
            roles = [kind for kind in ("arm", "gripper", "neck") if kind in self._paths]
            self._attempted.setdefault(generation, set()).update(roles)
        for kind in roles:
            try:
                if self._request(kind, 3, generation, bytes(16), b"") is not True:
                    self.close_generation(generation)      # close outside the lock
                    return False
            except Exception:
                self.close_generation(generation)
                raise
        return True

    def close_all_attempted(self):
        """Public read-only view: close every generation this client attempted."""

        with self._lock:
            generations = sorted(self._attempted)
        closed = []
        for generation in generations:
            if self.close_generation(generation) is not False:
                closed.append(generation)
        return closed

    def close_generation(self, generation):
        # invalidate this generation's confirmed identities *without* consuming the
        # attempted-role record: the close frames below must still be emitted, and
        # the record is dropped only after the close is confirmed
        with self._lock:
            roles = sorted(self._attempted.get(generation, ()))
        for role in roles:
            self._invalidate_identity(role, reason="close")
        with self._lock:
            kinds = tuple(sorted(self._attempted.get(generation, ())))
        failures = 0
        for kind in kinds:
            try:
                if self._request(kind, 2, generation, bytes(16), b"") is not True:
                    failures += 1
            except Exception:
                failures += 1
        if failures:
            raise RuntimeError("CONTROLLER_RESERVATION_CLOSE_UNCONFIRMED")
        with self._lock:
            self._attempted.pop(generation, None)
