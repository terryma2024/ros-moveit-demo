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
import os
import re
import secrets
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .arbiter import GlobalMutationArbiter
from .controller_reservation_paths import (
    controller_reservation_directory, controller_reservation_root,
)
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
    ProcessAbsent,
    ProcessIdentityError,
    argv_matches,
    group_members,
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
            runtime_id=(f"{self.runtime_id}-{hashlib.sha256(child.campaign_id.encode()).hexdigest()}"
                        f"-{child.worker_id}-g{child.execution_generation}"),
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
        self._lock = threading.RLock()

    def _register_locked(self, launch: ActChildLaunch) -> None:
        key = (launch.campaign_id, launch.worker_id, launch.execution_generation)
        if key in self._launches:
            raise ValueError("DUPLICATE_CHILD")
        for existing in self._launches.values():
            if existing.ros_domain_id == launch.ros_domain_id:
                raise ValueError("ROS_DOMAIN_SHARED")
            if existing.namespace == launch.namespace:
                raise ValueError("ROS_NAMESPACE_SHARED")
            if existing.controller_name == launch.controller_name:
                raise ValueError("ROS_CONTROLLER_SHARED")
            if existing.mujoco_session_id == launch.mujoco_session_id:
                raise ValueError("MUJOCO_SESSION_SHARED")
            if existing.socket_root == launch.socket_root:
                raise ValueError("IPC_SOCKET_SHARED")
        self._launches[key] = launch

    def register(self, launch: ActChildLaunch) -> None:
        with self._lock:
            self._register_locked(launch)

    @contextlib.contextmanager
    def reserve_many(self, launches: tuple[ActChildLaunch, ...]):
        """Hold child identities through admission; roll back only this batch on failure."""
        with self._lock:
            added = []
            try:
                for launch in launches:
                    self._register_locked(launch)
                    added.append((launch.campaign_id, launch.worker_id, launch.execution_generation))
                yield
            except BaseException:
                for key in reversed(added):
                    del self._launches[key]
                raise

    def launches(self) -> tuple[ActChildLaunch, ...]:
        with self._lock:
            return tuple(self._launches.values())

    def release_many(self, launches: tuple[ActChildLaunch, ...]) -> None:
        """Remove an exact stopped batch; never release a reused or foreign identity."""
        with self._lock:
            keys = [(item.campaign_id, item.worker_id, item.execution_generation)
                    for item in launches]
            if len(set(keys)) != len(keys) or any(
                self._launches.get(key) != launch
                for key, launch in zip(keys, launches, strict=True)
            ):
                raise ValueError("CHILD_RELEASE_MISMATCH")
            for key in keys:
                del self._launches[key]


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
        self._startup_stack_owner: OwnerKey | None = None

    def bind_startup_owner(self, owner: OwnerKey) -> None:
        if (self._startup_stack_owner is not None or not isinstance(owner, OwnerKey)
                or type(owner.pid) is not int or type(owner.pgid) is not int
                or owner.pid <= 0 or owner.pgid != owner.pid
                or type(owner.started_ticks) is not int or owner.started_ticks <= 0
                or any(not isinstance(value, str)
                       or re.fullmatch(r"[0-9a-f]{64}", value) is None
                       for value in (owner.argv_sha256, owner.environment_sha256))):
            raise MutationError("ACT_TASK8_STARTUP_OWNER_INVALID")
        self._startup_stack_owner = owner

    def _base(self, request: dict, *, fields: frozenset[str], cancel: bool = False) -> tuple[str, str, int]:
        if not isinstance(request, dict) or set(request) != fields:
            raise MutationError("ACT_WORKER_REQUEST_SCHEMA")
        session_id = request["session_id"]
        attempt_id = request["attempt_id"]
        deadline_ns = request["deadline_ns"]
        if session_id != self.launch.mujoco_session_id or not isinstance(attempt_id, str) or not attempt_id:
            raise MutationError("ACT_WORKER_SESSION_MISMATCH")
        now_ns = time.monotonic_ns()
        # A safety stop remains available after the business deadline. Its own
        # short deadline is bounded by the ROS driver's maximum stop window.
        latest_ns = now_ns + 30_000_000_000 if cancel else int(self.context.deadline_monotonic_s * 1e9)
        if type(deadline_ns) is not int or not now_ns < deadline_ns <= latest_ns:
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

    async def run_pick_place(self, request: dict) -> dict:
        fields = frozenset({
            "session_id", "attempt_id", "scenario_id", "mode", "stop_after",
            "contact_policy_fingerprint", "deadline_ns",
            # P1-3: the case's admitted support distance travels with the request, because the evidence that says
            # "the cup is supported" is derived from it and the payload schema requires it
            "support_distance_max_m",
            # the case's admitted gripper target travels with the request for the same reason (CP-1514)
            "gripper_closed_rad",
        })
        session_id, attempt_id, deadline_ns = self._base(request, fields=fields)
        if request["contact_policy_fingerprint"] != self.context.contact_policy_fingerprint:
            raise MutationError("ACT_POLICY_MISMATCH")
        if self._startup_stack_owner is None:
            raise MutationError("ACT_TASK8_STARTUP_OWNER_UNBOUND")
        mode = request["mode"]
        if mode == "phase_prefix" and isinstance(request["stop_after"], str):
            operation = "task8_phase"
        elif mode == "full" and request["stop_after"] is None:
            operation = "task8_full"
        else:
            raise MutationError("ACT_TASK8_MODE_INVALID")
        payload = {
            "scenario_id": request["scenario_id"],
            "support_distance_max_m": request["support_distance_max_m"],
            "gripper_closed_rad": request["gripper_closed_rad"],
            "manifest_sha256": self.context.manifest_sha256,
            "runtime_config_sha256": self.context.runtime_config_sha256,
            "contact_policy_fingerprint": self.context.contact_policy_fingerprint,
            "stack_owner": asdict(self._startup_stack_owner),
        }
        if operation == "task8_phase":
            payload["stop_after"] = request["stop_after"]
        return await self._call(
            operation, session_id=session_id, attempt_id=attempt_id,
            deadline_ns=deadline_ns, payload=payload,
        )

    async def task8(self, request: dict) -> dict:
        """Compatibility entry point for version-one callers."""
        return await self.run_pick_place(request)

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
            cancel=True,
        )
        return await self._call(
            "cancel", session_id=session_id, attempt_id=attempt_id,
            deadline_ns=deadline_ns, payload={"reason": request["reason"]},
        )


class ActCampaignChildOwner:
    """Spawn and retain exactly the child map frozen by campaign admission."""

    def __init__(self, base_launch: BridgeLaunch, arbiter, safety, *, owner_factory=None) -> None:
        self.base_launch = base_launch
        self.arbiter = arbiter
        self.safety = safety
        self.owner_factory = owner_factory or BridgeProcessOwner
        self._owners: list[BridgeProcessOwner] = []
        self._clients: list[BridgeClient] = []
        self._ports: tuple[ActWorkerPort, ...] = ()

    async def start(
        self, context: AdmittedCampaignContext, launches: tuple[ActChildLaunch, ...],
        *, artifacts=None,
    ) -> tuple[ActWorkerPort, ...]:
        if self._owners:
            raise MutationError("ACT_CHILDREN_ALREADY_STARTED")
        if time.monotonic() >= context.deadline_monotonic_s:
            raise MutationError("ACT_CAMPAIGN_DEADLINE_EXPIRED")
        if len(launches) != context.worker_count:
            raise MutationError("ACT_CHILD_MAP_MISMATCH")
        registry = ActChildRegistry()
        for child in launches:
            if child.campaign_id != context.campaign_id or child.execution_generation != context.execution_generation:
                raise MutationError("ACT_CHILD_MAP_MISMATCH")
            registry.register(child)
        document = [item.__dict__ for item in launches]
        digest = hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if digest != context.domain_session_map_sha256:
            raise MutationError("ACT_CHILD_MAP_MISMATCH")
        prepared: list[tuple[ActChildLaunch, BridgeLaunch, str]] = []
        if artifacts is not None:
            from .act_artifacts import ActArtifactBinding
            if not isinstance(artifacts, ActArtifactBinding):
                raise MutationError("ACT_ARTIFACT_BINDING_INVALID")
            artifacts.verify()
        for child in launches:
            token = secrets.token_urlsafe(32)
            launch = self.base_launch.for_act_worker(child)
            environment = dict(launch.environment)
            reservation_root = controller_reservation_root(
                Path(context.evidence_root), environment)
            environment.update({
                "SO101_CHILD_SERVICE_EPOCH": context.service_epoch,
                "SO101_CHILD_SERVICE_TOKEN": token,
                "SO101_CHILD_WEB_PID": str(os.getpid()),
                "SO101_ACT_OPERATION_ID": context.operation_id,
                "SO101_ACT_EVIDENCE_ROOT": context.evidence_root,
                "SO101_ACT_RESERVATION_ROOT": str(reservation_root),
                "SO101_ACT_CONTROLLER_RESERVATION_DIR": str(
                    controller_reservation_directory(
                        reservation_root, child.mujoco_session_id)),
                "SO101_ACT_SOURCE_SHA256": context.source_sha256,
                "SO101_ACT_MANIFEST_SHA256": context.manifest_sha256,
                "SO101_ACT_RUNTIME_CONFIG_SHA256": context.runtime_config_sha256,
                "SO101_ACT_COLLECTION_CONFIG_SHA256": context.collection_config_sha256,
                "SO101_ACT_POLICY_FINGERPRINT": context.contact_policy_fingerprint,
                "CUDA_VISIBLE_DEVICES": context.physical_gpu_uuid,
            })
            if artifacts is not None:
                environment.update(artifacts.environment())
            prepared.append((child, replace(launch, environment=environment), token))
        try:
            ports = []
            for child, launch, token in prepared:
                if time.monotonic() >= context.deadline_monotonic_s:
                    raise MutationError("ACT_CAMPAIGN_DEADLINE_EXPIRED")
                owner = self.owner_factory(launch, self.arbiter, self.safety)
                self._owners.append(owner)
                owner_key = await owner.start()
                normal, safety = owner.socket_paths()
                client = BridgeClient(
                    normal_socket=normal, safety_socket=safety,
                    service_epoch=context.service_epoch, runtime_id=launch.runtime_id,
                    service_token=token, owner=owner_key,
                )
                self._clients.append(client)
                ports.append(ActWorkerPort(context, child, client))
            self._ports = tuple(ports)
            return self._ports
        except BaseException:
            await self.stop_owned()
            raise

    async def stop_owned(self) -> None:
        for client in self._clients:
            client.close()
        self._clients.clear()
        failures = []
        for owner in reversed(self._owners):
            try:
                await owner.stop_owned()
            except BaseException as error:
                failures.append(error)
        if failures:
            raise MutationError("ACT_CHILD_CLEANUP_NOT_CONFIRMED") from failures[0]
        self._owners.clear()
        self._ports = ()


class ActCampaignLifecycle:
    """Join the single admission decision to exact child ownership and cleanup."""

    def __init__(self, workload_service, child_owner: ActCampaignChildOwner) -> None:
        self.workload_service = workload_service
        self.child_owner = child_owner
        self.context: AdmittedCampaignContext | None = None

    async def start(self, spec) -> tuple[AdmittedCampaignContext, tuple[ActWorkerPort, ...]]:
        if self.context is not None:
            raise MutationError("ACT_CAMPAIGN_ALREADY_STARTED")
        # A repeated command may be read back through admission, but only a
        # freshly reserved campaign may launch children. Recovery has its own path.
        context = self.workload_service.start(spec, allow_existing=False)
        self.context = context
        try:
            from .act_artifacts import ActArtifactBinding
            artifacts = ActArtifactBinding.from_admission(spec.payload, context)
            launches = tuple(ActChildLaunch(**item) for item in spec.payload["children"])
            ports = await self.child_owner.start(context, launches, artifacts=artifacts)
        except BaseException:
            try:
                await self.child_owner.stop_owned()
            except BaseException as error:
                raise MutationError("ACT_CHILD_CLEANUP_NOT_CONFIRMED") from error
            try:
                self.workload_service.finish(context, cleanup_confirmed=True)
            except BaseException as error:
                raise MutationError("ACT_CAMPAIGN_SETTLEMENT_UNCONFIRMED") from error
            self.context = None
            raise
        return context, ports

    async def finish(self, context: AdmittedCampaignContext):
        if self.context != context:
            raise MutationError("ACT_CAMPAIGN_CONTEXT_MISMATCH")
        await self.child_owner.stop_owned()
        projection = self.workload_service.finish(context, cleanup_confirmed=True)
        self.context = None
        return projection


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
    if identity.pgid != pid:
        raise MutationError(f"PROCESS_GROUP_NOT_ISOLATED: pid {pid} has pgid {identity.pgid}")
    return OwnerKey(
        pid=pid,
        pgid=identity.pgid,
        started_ticks=identity.start_marker,
        argv_sha256=identity.command_sha256,
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


def _retirement_owner_state(owner: OwnerKey) -> str:
    """Distinguish a proven exit from drift or unreadable process metadata."""
    try:
        identity = read_identity(owner.pid)
    except ProcessAbsent:
        return "exited"
    except ProcessIdentityError:
        return "unknown"
    if identity.start_marker != owner.started_ticks or identity.pgid != owner.pgid:
        return "drifted"
    if identity.command_sha256 != owner.argv_sha256:
        return "unknown"
    return "live" if identity.live else "exited"


def _require_group_clear(pgid: int) -> None:
    """Prove no executable member remains, including after leader exit."""
    try:
        members = group_members(pgid)
    except ProcessIdentityError as error:
        raise MutationError("STOP_NOT_CONFIRMED: group scan unreadable") from error
    if any(state != "Z" for state in members.values()):
        raise MutationError("STOP_NOT_CONFIRMED: live group member")
    if not members:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        except PermissionError as error:
            raise MutationError("STOP_NOT_CONFIRMED: group existence unreadable") from error
        raise MutationError("STOP_NOT_CONFIRMED: group exists without readable members")


def _write_retirement_receipt(root: Path, document: dict) -> None:
    path = root / "cleanup-receipt.json"
    raw = (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


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
                if code not in ("PROCESS_ARGV_MISMATCH", "PROCESS_IDENTITY_UNREADABLE",
                                "PROCESS_GROUP_NOT_ISOLATED") or time.monotonic() >= identity_deadline:
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
                ) == self.launch.runtime_id and self._ready_matches(document):
                    self._ready_document = document
                    return self.owner
            await asyncio.sleep(0.02)
        raise MutationError("BRIDGE_READY_TIMEOUT: child did not publish its sockets")

    def ready(self) -> bool:
        if self.process is None or self.process.poll() is not None:
            return False
        if self._ready_document is None:
            return False
        return self._ready_matches(self._ready_document)

    def _ready_matches(self, document: dict) -> bool:
        expected_epoch = self.launch.environment.get("SO101_CHILD_SERVICE_EPOCH")
        if expected_epoch is not None and document.get("service_epoch") != expected_epoch:
            return False
        if document.get("service_epoch") is None or document.get("runtime_id") != self.launch.runtime_id:
            return False
        campaign_id = self.launch.environment.get("SO101_ACT_CAMPAIGN_ID")
        if campaign_id is None:
            return True
        generation = self.launch.environment.get("SO101_ACT_GENERATION")
        if not isinstance(generation, str) or not generation.isdecimal():
            return False
        expected = {
            "campaign_id": campaign_id,
            "worker_id": self.launch.environment.get("SO101_ACT_WORKER_ID"),
            "execution_generation": int(generation),
            "normal_socket": str(Path(self.launch.socket_root) / NORMAL_SOCKET_NAME),
            "safety_socket": str(Path(self.launch.socket_root) / SAFETY_SOCKET_NAME),
        }
        return all(document.get(key) == value for key, value in expected.items())

    async def stop_owned(self, *, timeout_s: float = 5.0) -> None:
        """Stop the exact group this service started, after re-proving the owner's identity.

        The child leads its own session, so its group is the set of helpers it forked; signalling
        only its pid left those helpers behind, and refusing to escalate left the child itself
        behind while reporting a failure. Both are now the same call: terminate the group, escalate
        once, and confirm from a fresh platform scan before this owner forgets the process.
        """
        if self.process is None:
            return
        if self.owner is None:
            raise MutationError("OWNER_IDENTITY_UNVERIFIED: child process exists without a trusted owner")
        owner = self.owner
        state = _retirement_owner_state(owner)
        if state not in ("live", "exited"):
            raise MutationError(
                f"OWNER_IDENTITY_DRIFT: pid {owner.pid} no longer matches the recorded start marker"
            )
        receipt = None
        if state == "live":
            receipt = terminate_group(
                pgid=owner.pgid, leader_pid=owner.pid, timeout_s=timeout_s
            )
            if not receipt.clear:
                raise MutationError(f"STOP_NOT_CONFIRMED: {receipt.describe()}")
        self._reap_owned(owner.pid)
        _require_group_clear(owner.pgid)
        root = Path(self.launch.socket_root)
        try:
            ready = root / READY_FILE_NAME
            ready_raw = ready.read_bytes() if ready.is_file() and not ready.is_symlink() else b""
            if len(ready_raw) > (1 << 20):
                raise ValueError("ready document too large")
            removed = []
            for name in (NORMAL_SOCKET_NAME, SAFETY_SOCKET_NAME, READY_FILE_NAME):
                path = root / name
                try:
                    path.unlink()
                    removed.append(name)
                except FileNotFoundError:
                    pass
            _write_retirement_receipt(root, {
                "schema_version": 1,
                "leader_pid": owner.pid,
                "pgid": owner.pgid,
                "started_ticks": owner.started_ticks,
                "argv_sha256": owner.argv_sha256,
                "group_clear": True,
                "parent_exited": state == "exited",
                "term_sent": receipt.term_sent if receipt else False,
                "kill_sent": receipt.kill_sent if receipt else False,
                "ready_sha256": hashlib.sha256(ready_raw).hexdigest() if ready_raw else None,
                "removed_endpoints": removed,
                "finished_at_monotonic_ns": time.monotonic_ns(),
            })
        except (OSError, TypeError, ValueError) as error:
            raise MutationError("ACT_RETIREMENT_RECEIPT_FAILED") from error
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
