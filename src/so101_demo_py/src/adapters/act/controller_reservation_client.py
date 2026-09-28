"""Bounded off-graph registration of native controller action goals."""

import os
from pathlib import Path
import socket
import stat
import threading
import time
import json
import uuid

from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import serialize_message


MAX_BODY_BYTES = 1_048_640
_ROLE_CODES = {"arm": 1, "gripper": 2, "neck": 3}
_MAX_INGRESS_SNAPSHOT_AGE_NS = 200_000_000


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
        with self._lock:
            path = self._paths[kind]
            self._check_path(path)
            deadline = self._deadline()
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

    def _resolved_payload(self, kind, goal, *, handle, resolver, goal_uuid, now_ns):
        """Resolve an opaque handle through the sealed broker-owned resolver.

        No caller-supplied identity, snapshot, instant, deadline or receipt mapping
        is accepted anywhere on this path: the binding comes from the resolver.
        """

        if handle is None or resolver is None:
            raise ValueError("CONTROLLER_RESERVATION_HANDLE_REQUIRED")
        resolve = getattr(resolver, "reservation_binding", None)
        if not callable(resolve):
            raise ValueError("CONTROLLER_RESERVATION_RESOLVER_INVALID")
        binding = resolve(handle)
        for field in self.RESERVATION_BINDING_FIELDS:
            if field not in binding:
                raise ValueError(f"CONTROLLER_RESERVATION_BINDING_MISSING:{field}")
        if binding["goal_uuid"] != goal_uuid or binding["role"] != kind:
            raise ValueError("CONTROLLER_RESERVATION_BINDING_GOAL_MISMATCH")
        for field in ("claim_monotonic_ns", "deadline_ns"):
            if type(binding[field]) is not int:
                raise ValueError(f"CONTROLLER_RESERVATION_BINDING_TYPE:{field}")
        if now_ns is not None and (type(now_ns) is not int or now_ns > binding["deadline_ns"]):
            raise ValueError("CONTROLLER_RESERVATION_BINDING_LATE")
        blob = json.dumps({field: binding[field] for field in self.RESERVATION_BINDING_FIELDS},
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(blob) > 4096:
            raise ValueError("CONTROLLER_RESERVATION_BINDING_TOO_LARGE")
        return len(blob).to_bytes(4, "big") + blob + serialize_message(goal)

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

    def reserve_bound(self, ticket, kind, goal, goal_uuid, *, handle, now_ns=None):
        """Reserve using only an opaque handle resolved by the installed authority."""

        if (not isinstance(ticket, tuple) or not ticket
                or not isinstance(goal, FollowJointTrajectory.Goal)):
            raise TypeError("CONTROLLER_RESERVATION_GOAL_INVALID")
        native_uuid = uuid.UUID(goal_uuid).bytes
        if str(uuid.UUID(goal_uuid)) != goal_uuid:
            raise ValueError("CONTROLLER_RESERVATION_UUID_INVALID")
        resolver = self._authority
        if resolver is None:
            raise ValueError("CONTROLLER_RESERVATION_AUTHORITY_MISSING")
        payload = self._resolved_payload(kind, goal, handle=handle, resolver=resolver,
                                         goal_uuid=goal_uuid, now_ns=now_ns)
        generation = ticket[0]
        with self._lock:
            self._attempted.setdefault(generation, set()).add(kind)
        return self._request(kind, 1, generation, native_uuid, payload)

    def arm_generation(self, ticket):
        if set(self._paths) not in ({"arm", "gripper"}, {"arm", "gripper", "neck"}):
            raise ValueError("CONTROLLER_RESERVATION_ROLES_INVALID")
        if not isinstance(ticket, tuple) or len(ticket) != 5:
            raise TypeError("CONTROLLER_RESERVATION_TICKET_INVALID")
        generation = ticket[0]
        with self._lock:
            self._attempted.setdefault(generation, set()).update(self._paths)
            for kind in ("arm", "gripper", "neck"):
                if kind not in self._paths:
                    continue
                if self._request(kind, 3, generation, bytes(16), b"") is not True:
                    return False
            return True

    def close_generation(self, generation):
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
