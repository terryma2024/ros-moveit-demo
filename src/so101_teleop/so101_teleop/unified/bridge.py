"""Web-side owner and client of the non-web ROS child.

The launch description is built only from validated server configuration; no HTTP input,
shell command, or Python expression can influence the child's argv or environment. The
owner records an exact process identity and re-verifies it before it ever signals.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .arbiter import GlobalMutationArbiter
from .child_runtime import READY_FILE_NAME, NORMAL_SOCKET_NAME, SAFETY_SOCKET_NAME
from .contracts import (
    AdmittedCampaignContext,
    CancelReceipt,
    IntentCancelReceipt,
    MutationError,
    OwnerKey,
    PendingChildKey,
    RevokeTarget,
)
from .ipc import DEFAULT_MAX_BYTES, IpcReply, IpcRequest, SafetyPacket
from .safety import SafetyLane
from ..owned_group import terminate_group
from ..process_identity import (
    ProcessIdentityError,
    argv_matches,
    command_fingerprint,
    read_identity,
)


@dataclass(frozen=True)
class BridgeLaunch:
    ros_python: Path
    install_prefix: Path
    runtime_id: str
    environment: dict[str, str]
    socket_root: Path

    def __post_init__(self) -> None:
        if not Path(self.ros_python).is_file():
            raise MutationError(f"BRIDGE_ROS_PYTHON_MISSING: {self.ros_python}")
        if not Path(self.install_prefix).is_dir():
            raise MutationError(f"BRIDGE_INSTALL_PREFIX_MISSING: {self.install_prefix}")
        if not self.runtime_id:
            raise MutationError("BRIDGE_RUNTIME_ID_MISSING")

    def argv(self) -> list[str]:
        """The only argv this service will ever spawn for the ROS child."""
        return [
            str(self.ros_python),
            "-m",
            "so101_teleop.unified.ros_child",
            "--socket-root",
            str(self.socket_root),
            "--runtime-id",
            self.runtime_id,
        ]

    def for_act_worker(self, child: "ActChildLaunch") -> "BridgeLaunch":
        """Freeze a distinct process environment for one admitted ACT Worker."""
        environment = dict(self.environment)
        environment.update({
            "ROS_DOMAIN_ID": str(child.ros_domain_id),
            "ROS_NAMESPACE": child.namespace,
            "SO101_ACT_CONTROLLER_NAME": child.controller_name,
            "SO101_SIMULATION_SESSION_ID": child.mujoco_session_id,
            "SO101_ACT_CAMPAIGN_ID": child.campaign_id,
            "SO101_ACT_WORKER_ID": child.worker_id,
            "SO101_ACT_GENERATION": str(child.execution_generation),
        })
        return BridgeLaunch(
            ros_python=self.ros_python,
            install_prefix=self.install_prefix,
            runtime_id=f"{self.runtime_id}-{child.worker_id}-g{child.execution_generation}",
            environment=environment,
            socket_root=Path(child.socket_root),
        )


@dataclass(frozen=True)
class ActChildLaunch:
    """One frozen ROS/MuJoCo execution identity for one ACT Worker."""

    campaign_id: str
    worker_id: str
    execution_generation: int
    ros_domain_id: int
    namespace: str
    controller_name: str
    mujoco_session_id: str
    socket_root: str

    def __post_init__(self) -> None:
        if not self.campaign_id or not self.worker_id or not self.mujoco_session_id:
            raise ValueError("CHILD_IDENTITY_INVALID")
        if type(self.execution_generation) is not int or self.execution_generation < 0:
            raise ValueError("CHILD_GENERATION_INVALID")
        if type(self.ros_domain_id) is not int or not 0 <= self.ros_domain_id <= 232:
            raise ValueError("ROS_DOMAIN_INVALID")
        if not self.namespace.startswith("/") or not self.controller_name:
            raise ValueError("CHILD_NAMESPACE_INVALID")
        if not Path(self.socket_root).is_absolute() or len((self.socket_root + "/safety.sock").encode()) > 103:
            raise ValueError("IPC_SOCKET_PATH_TOO_LONG")


class ActChildRegistry:
    """Reserve child identities and isolated resources before launching any process."""

    def __init__(self) -> None:
        self._launches: dict[tuple[str, str, int], ActChildLaunch] = {}

    def register(self, launch: ActChildLaunch) -> None:
        key = (launch.campaign_id, launch.worker_id, launch.execution_generation)
        if key in self._launches:
            raise ValueError("DUPLICATE_CHILD")
        for existing in self._launches.values():
            if existing.ros_domain_id == launch.ros_domain_id:
                raise ValueError("ROS_DOMAIN_SHARED")
            if existing.mujoco_session_id == launch.mujoco_session_id:
                raise ValueError("MUJOCO_SESSION_SHARED")
            if existing.socket_root == launch.socket_root:
                raise ValueError("IPC_SOCKET_SHARED")
        self._launches[key] = launch

    def launches(self) -> tuple[ActChildLaunch, ...]:
        return tuple(self._launches.values())


class ActWorkerPort:
    """Typed Web/CLI transport for one admitted campaign Worker."""

    def __init__(self, context: AdmittedCampaignContext, launch: ActChildLaunch, client: "BridgeClient") -> None:
        if (
            launch.campaign_id != context.campaign_id
            or launch.execution_generation != context.execution_generation
        ):
            raise MutationError("ACT_WORKER_CONTEXT_MISMATCH")
        if client.service_epoch != context.service_epoch:
            raise MutationError("ACT_WORKER_EPOCH_MISMATCH")
        self.context = context
        self.launch = launch
        self.client = client

    def _base(self, request: dict, *, fields: frozenset[str]) -> tuple[str, str, int]:
        if not isinstance(request, dict) or set(request) != fields:
            raise MutationError("ACT_WORKER_REQUEST_SCHEMA")
        session_id = request["session_id"]
        attempt_id = request["attempt_id"]
        deadline_ns = request["deadline_ns"]
        if session_id != self.launch.mujoco_session_id or not isinstance(attempt_id, str) or not attempt_id:
            raise MutationError("ACT_WORKER_SESSION_MISMATCH")
        if type(deadline_ns) is not int or not time.monotonic_ns() < deadline_ns <= int(self.context.deadline_monotonic_s * 1e9):
            raise MutationError("ACT_WORKER_DEADLINE_INVALID")
        return session_id, attempt_id, deadline_ns

    async def _call(self, operation: str, *, session_id: str, attempt_id: str, deadline_ns: int, payload: dict) -> dict:
        from .ipc import IpcRequest

        token = {
            "operation_id": self.context.operation_id,
            "child_id": self.launch.worker_id,
            "runtime_id": self.client.runtime_id,
            "execution_generation": self.context.execution_generation,
            "deadline_ns": deadline_ns,
            "revocation_revision": 0,
        }
        packet = IpcRequest(
            version=1, operation=operation,
            command_id=hashlib.sha256(
                f"{self.context.operation_id}:{self.launch.worker_id}:{attempt_id}:{operation}".encode()
            ).hexdigest(),
            deadline_ns=deadline_ns, service_epoch=self.context.service_epoch,
            runtime_id=self.client.runtime_id, service_token=self.client.service_token,
            campaign_id=self.context.campaign_id, worker_id=self.launch.worker_id,
            session_id=session_id, attempt_id=attempt_id,
            execution_generation=self.context.execution_generation,
            token=token, payload=payload,
        )
        reply = await self.client.call(packet)
        if not reply.accepted:
            raise MutationError(f"ACT_CHILD_REJECTED: {reply.code}")
        result = reply.result
        expected = {
            "operation_id": self.context.operation_id,
            "campaign_id": self.context.campaign_id,
            "worker_id": self.launch.worker_id,
            "execution_generation": self.context.execution_generation,
        }
        if not isinstance(result, dict) or any(result.get(key) != value for key, value in expected.items()) or not isinstance(result.get("body"), dict):
            raise MutationError("ACT_REPLY_IDENTITY_MISMATCH")
        return result["body"]

    async def task8(self, request: dict) -> dict:
        fields = frozenset({
            "session_id", "attempt_id", "scenario_id", "mode", "stop_after",
            "contact_policy_fingerprint", "deadline_ns",
        })
        session_id, attempt_id, deadline_ns = self._base(request, fields=fields)
        if request["contact_policy_fingerprint"] != self.context.contact_policy_fingerprint:
            raise MutationError("ACT_POLICY_MISMATCH")
        mode = request["mode"]
        if mode == "phase_prefix" and isinstance(request["stop_after"], str):
            operation = "task8_phase"
        elif mode == "full" and request["stop_after"] is None:
            operation = "task8_full"
        else:
            raise MutationError("ACT_TASK8_MODE_INVALID")
        payload = {
            "scenario_id": request["scenario_id"],
            "manifest_sha256": self.context.manifest_sha256,
            "runtime_config_sha256": self.context.runtime_config_sha256,
            "contact_policy_fingerprint": self.context.contact_policy_fingerprint,
        }
        if operation == "task8_phase":
            payload["stop_after"] = request["stop_after"]
        return await self._call(
            operation, session_id=session_id, attempt_id=attempt_id,
            deadline_ns=deadline_ns, payload=payload,
        )

    async def act_collection(self, request: dict) -> dict:
        fields = frozenset({
            "session_id", "attempt_id", "scenario_id", "mode", "checkpoint_sha256",
            "contact_policy_fingerprint", "deadline_ns",
        })
        session_id, attempt_id, deadline_ns = self._base(request, fields=fields)
        if request["contact_policy_fingerprint"] != self.context.contact_policy_fingerprint:
            raise MutationError("ACT_POLICY_MISMATCH")
        if request["mode"] == "start" and request["checkpoint_sha256"] is None:
            operation = "act_collection_start"
        elif request["mode"] == "resume" and isinstance(request["checkpoint_sha256"], str):
            operation = "act_collection_resume"
        else:
            raise MutationError("ACT_COLLECTION_MODE_INVALID")
        payload = {
            "scenario_id": request["scenario_id"],
            "manifest_sha256": self.context.manifest_sha256,
            "runtime_config_sha256": self.context.runtime_config_sha256,
            "contact_policy_fingerprint": self.context.contact_policy_fingerprint,
            "collection_config_sha256": self.context.collection_config_sha256,
        }
        if operation == "act_collection_resume":
            payload["checkpoint_sha256"] = request["checkpoint_sha256"]
        return await self._call(
            operation, session_id=session_id, attempt_id=attempt_id,
            deadline_ns=deadline_ns, payload=payload,
        )

    async def cancel(self, request: dict) -> dict:
        session_id, attempt_id, deadline_ns = self._base(
            request, fields=frozenset({"session_id", "attempt_id", "reason", "deadline_ns"}),
        )
        return await self._call(
            "cancel", session_id=session_id, attempt_id=attempt_id,
            deadline_ns=deadline_ns, payload={"reason": request["reason"]},
        )


def _hash_environment(environment: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(environment, sort_keys=True).encode()
    ).hexdigest()


def process_start_marker(pid: int) -> int:
    """A start marker that survives PID reuse; platform specific, never guessed."""
    try:
        return read_identity(pid).start_marker
    except ProcessIdentityError as error:
        raise MutationError(f"PROCESS_IDENTITY_UNREADABLE: {pid}") from error


def identity_for(pid: int, argv: list[str], environment: dict[str, str]) -> OwnerKey:
    """Record what the kernel reports about ``pid``, after checking it is the process we launched."""
    try:
        identity = read_identity(pid)
    except ProcessIdentityError as error:
        raise MutationError(f"PROCESS_IDENTITY_UNREADABLE: {pid}") from error
    if not argv_matches(identity, argv):
        raise MutationError(f"PROCESS_ARGV_MISMATCH: pid {pid} is not running the launch argv")
    return OwnerKey(
        pid=pid,
        pgid=identity.pgid,
        started_ticks=identity.start_marker,
        argv_sha256=command_fingerprint(argv),
        environment_sha256=_hash_environment(environment),
    )


def identity_matches(owner: OwnerKey) -> bool:
    """Re-prove every recorded field, not just liveness, before anything may be signalled."""
    try:
        identity = read_identity(owner.pid)
    except ProcessIdentityError:
        return False
    return (
        identity.live
        and identity.pgid == owner.pgid
        and identity.start_marker == owner.started_ticks
        and identity.command_sha256 == owner.argv_sha256
    )


class BridgeProcessOwner:
    def __init__(self, launch: BridgeLaunch, arbiter: GlobalMutationArbiter, safety: SafetyLane) -> None:
        self.launch = launch
        self.arbiter = arbiter
        self.safety = safety
        self.process: subprocess.Popen | None = None
        self.owner: OwnerKey | None = None
        self._ready_document: dict | None = None

    async def start(self, *, timeout_s: float = 10.0) -> OwnerKey:
        if self.owner is not None and identity_matches(self.owner):
            return self.owner
        argv = self.launch.argv()
        environment = dict(self.launch.environment)
        self.process = subprocess.Popen(
            argv,
            env=environment,
            shell=False,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
        )
        started = time.monotonic()
        identity_deadline = started + min(timeout_s, 1.0)
        while True:
            try:
                self.owner = identity_for(self.process.pid, argv, environment)
                break
            except MutationError as error:
                if self.process.poll() is not None:
                    raise MutationError(f"BRIDGE_CHILD_EXITED: {self.process.returncode}") from error
                code = str(error).split(":", 1)[0]
                if code not in ("PROCESS_ARGV_MISMATCH", "PROCESS_IDENTITY_UNREADABLE") or time.monotonic() >= identity_deadline:
                    raise
                # The just-spawned interpreter can briefly expose an incomplete argv.
                # No signal is sent until exact kernel identity has been established.
                await asyncio.sleep(0.01)
        deadline = started + timeout_s
        ready_path = Path(self.launch.socket_root) / READY_FILE_NAME
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise MutationError(f"BRIDGE_CHILD_EXITED: {self.process.returncode}")
            if ready_path.is_file():
                document = json.loads(ready_path.read_text())
                if document.get("pid") == self.process.pid and document.get(
                    "runtime_id"
                ) == self.launch.runtime_id:
                    self._ready_document = document
                    return self.owner
            await asyncio.sleep(0.02)
        raise MutationError("BRIDGE_READY_TIMEOUT: child did not publish its sockets")

    def ready(self) -> bool:
        if self.process is None or self.process.poll() is not None:
            return False
        if self._ready_document is None:
            return False
        return self._ready_document.get("service_epoch") is not None

    async def stop_owned(self, *, timeout_s: float = 5.0) -> None:
        """Stop the exact group this service started, after re-proving the owner's identity.

        The child leads its own session, so its group is the set of helpers it forked; signalling
        only its pid left those helpers behind, and refusing to escalate left the child itself
        behind while reporting a failure. Both are now the same call: terminate the group, escalate
        once, and confirm from a fresh platform scan before this owner forgets the process.
        """
        if self.process is None or self.owner is None:
            return
        if not identity_matches(self.owner):
            raise MutationError(
                f"OWNER_IDENTITY_DRIFT: pid {self.owner.pid} no longer matches the recorded start marker"
            )
        owner = self.owner
        receipt = terminate_group(
            pgid=owner.pgid, leader_pid=owner.pid, timeout_s=timeout_s
        )
        self._reap_owned(owner.pid)
        if not receipt.clear:
            raise MutationError(f"STOP_NOT_CONFIRMED: {receipt.describe()}")
        self.process = None
        self.owner = None

    def _reap_owned(self, pid: int) -> None:
        """Collect the child if it is still ours to collect; a survivor is reported, not awaited."""
        process = self.process
        if process is None or process.pid != pid:
            return
        with contextlib.suppress(Exception):
            process.wait(timeout=1.0)

    def socket_paths(self) -> tuple[Path, Path]:
        root = Path(self.launch.socket_root)
        return root / NORMAL_SOCKET_NAME, root / SAFETY_SOCKET_NAME


class BridgeClient:
    """Sends closed packets over the two child sockets. Never reuses a normal queue."""

    def __init__(
        self,
        *,
        normal_socket: Path,
        safety_socket: Path,
        service_epoch: str,
        runtime_id: str,
        service_token: str,
        timeout_s: float = 5.0,
        max_bytes: int = DEFAULT_MAX_BYTES,
        owner: OwnerKey | None = None,
    ) -> None:
        self.normal_socket = Path(normal_socket)
        self.safety_socket = Path(safety_socket)
        self.service_epoch = service_epoch
        self.runtime_id = runtime_id
        self.service_token = service_token
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self.owner = owner
        self._closed = False

    async def call(self, packet: IpcRequest) -> IpcReply:
        if self._closed:
            raise MutationError("BRIDGE_CLIENT_CLOSED")
        return await asyncio.wait_for(self._round_trip(self.normal_socket, packet), self.timeout_s)

    async def _round_trip(self, socket_path: Path, packet) -> IpcReply:
        try:
            reader, writer = await asyncio.open_unix_connection(str(socket_path))
        except OSError as error:
            raise MutationError(f"IPC_CONNECT_FAILED: {socket_path}: {error}") from error
        try:
            writer.write(packet.model_dump_json().encode() + b"\n")
            await writer.drain()
            line = await reader.readline()
            if not line:
                raise MutationError("IPC_EMPTY_REPLY: the child closed the connection")
            if len(line) > self.max_bytes * 4:
                raise MutationError("IPC_REPLY_OVERSIZE")
            reply = IpcReply.model_validate_json(line)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        return reply

    async def cancel(self, key, authority) -> CancelReceipt:
        """Deliver a cancel for a known goal identity over the independent safety socket."""
        target = RevokeTarget(
            key=PendingChildKey(
                operation_id=key.operation_id,
                child_id=key.child_id,
                runtime_id=self.runtime_id,
                execution_generation=key.execution_generation,
            ),
            revocation_revision=authority.execution_generation,
        )
        reply = await self._send_safety(target)
        accepted = bool(reply.accepted)
        return CancelReceipt(key, accepted, None, None if accepted else reply.code)

    async def revoke(self, target: RevokeTarget, authority) -> IntentCancelReceipt:
        reply = await self._send_safety(target)
        if not reply.accepted:
            return IntentCancelReceipt(target, False, False, None, reply.code)
        result = reply.result or {}
        return IntentCancelReceipt(
            target,
            bool(result.get("linearized")),
            bool(result.get("submitted")),
            None,
            result.get("blocked_reason"),
        )

    async def _send_safety(self, target: RevokeTarget) -> IpcReply:
        if self._closed:
            raise MutationError("BRIDGE_CLIENT_CLOSED")
        if self.owner is None:
            raise MutationError("BRIDGE_OWNER_UNKNOWN: refusing to cancel without the exact owner")
        packet = SafetyPacket(
            operation="revoke",
            service_epoch=self.service_epoch,
            owner={
                "pid": self.owner.pid,
                "pgid": self.owner.pgid,
                "started_ticks": self.owner.started_ticks,
                "argv_sha256": self.owner.argv_sha256,
                "environment_sha256": self.owner.environment_sha256,
            },
            claim=self.service_token,
            target={
                "key": {
                    "operation_id": target.key.operation_id,
                    "child_id": target.key.child_id,
                    "runtime_id": target.key.runtime_id,
                    "execution_generation": target.key.execution_generation,
                },
                "revocation_revision": target.revocation_revision,
            },
        )
        return await asyncio.wait_for(self._round_trip(self.safety_socket, packet), self.timeout_s)

    def close(self) -> None:
        self._closed = True
