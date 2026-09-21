"""Exact-identity ownership of fixed coordinators and adaptive wrappers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid
from typing import Callable

from .adaptive import AdaptiveStartRequest
from .coordinator import CoordinatorStartRequest
from .owner_tree import ConfirmedOwnerProcess, DirectoryOwnerRecords, OwnerIntent
from ..owned_group import terminate_group
from ..process_identity import (
    ProcessIdentityError,
    argv_matches,
    command_fingerprint,
    group_has_live_descendants,
    identity_alive,
    read_identity,
)


class CoordinatorOwnershipError(RuntimeError):
    """A process cannot be proven to be the recorded execution owner."""

    def __init__(self, message: str, *, owned=None):
        super().__init__(message)
        self.owned = owned


def _canonical_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _owner_tree_environment(intent: OwnerIntent, tree_root: Path) -> dict[str, str]:
    """The child environment that attributes this adapter and its children to one owner tree.

    The adapter reads its own token here and writes the intents of everything it spawns with that
    token as ``parent_spawn_token``, so the whole tree stays reachable from the service side even
    when the adapter dies. The owner sets these keys after the request environment, so a caller can
    never point a child at another tree.
    """
    return {
        "SO101_OWNER_TOKEN": intent.spawn_token,
        # An adapter is the root of its own tree: it has no parent spawn to attribute.
        "SO101_OWNER_PARENT_TOKEN": (
            "" if intent.parent_spawn_token is None else intent.parent_spawn_token
        ),
        "SO101_OWNER_TREE_ROOT": str(tree_root),
        "SO101_OWNER_CAMPAIGN_ID": intent.campaign_id,
        "SO101_OWNER_BATCH_ID": intent.batch_id,
        "SO101_OWNER_GENERATION": str(intent.generation),
    }


def _owner_generation(request) -> int:
    """The coordinator epoch is the generation; an adaptive launch has none, so it is 1."""
    epoch = getattr(request, "coordinator_epoch", None)
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        return 1
    return epoch


@dataclass(frozen=True)
class OwnedCoordinator:
    campaign_id: str
    batch_id: str
    pid: int
    pgid: int
    started_ticks: int
    argv_sha256: str
    environment_sha256: str
    control_socket: Path
    coordinator_epoch: int


@dataclass(frozen=True)
class OwnedAdaptiveWrapper:
    campaign_id: str
    batch_id: str
    pid: int
    pgid: int
    started_ticks: int
    argv_sha256: str
    environment_sha256: str
    runner_pid: int | None
    runner_batch_id: str | None
    runner_journal_root: Path


OwnedExecution = OwnedCoordinator | OwnedAdaptiveWrapper


@dataclass(frozen=True, slots=True)
class ProcessStatus:
    running: bool
    exit_code: int | None
    descendants_alive: bool


@dataclass(frozen=True, slots=True)
class _ProcessIdentity:
    pid: int
    pgid: int
    started_ticks: int
    state: str
    argv: tuple[str, ...]
    command_sha256: str


def _read_identity(pid: int) -> _ProcessIdentity:
    """The exact, platform-specific identity read, with this module's error contract."""
    try:
        identity = read_identity(pid)
    except ProcessIdentityError as error:
        raise CoordinatorOwnershipError("PROCESS_IDENTITY_MISMATCH") from error
    return _ProcessIdentity(
        pid=identity.pid,
        pgid=identity.pgid,
        started_ticks=identity.start_marker,
        state=identity.state,
        argv=identity.argv,
        command_sha256=identity.command_sha256,
    )


def _group_has_live_descendants(pgid: int, leader_pid: int) -> bool:
    return group_has_live_descendants(pgid, leader_pid)


class ExecutionProcessOwner:
    """Own exactly one coordinator group or one adaptive wrapper PID."""

    def __init__(
        self,
        *,
        store=None,
        cleanup_checker: Callable[[OwnedExecution], bool] | None = None,
        stop_timeout_s: float = 3.0,
        owner_tree_root: Path | None = None,
    ) -> None:
        self._store = store
        self._cleanup_checker = cleanup_checker or (lambda _owned: False)
        self._stop_timeout_s = stop_timeout_s
        if owner_tree_root is not None and not Path(owner_tree_root).is_absolute():
            # A relative root would be resolved differently by every child that inherits it.
            raise CoordinatorOwnershipError("OWNER_TREE_ROOT_INVALID")
        self._owner_tree_root = None if owner_tree_root is None else Path(owner_tree_root)
        self._active: OwnedExecution | None = None
        self._children: dict[int, subprocess.Popen] = {}

    @property
    def owner_tree_root(self) -> Path | None:
        return self._owner_tree_root

    @property
    def active_execution(self) -> OwnedExecution | None:
        return self._active

    def has_active_execution(self) -> bool:
        return self._active is not None and self.poll(self._active).running

    def _owner_tree_records(self):
        """The shared tree root this owner writes its ADAPTER record into, when it has one."""
        if self._owner_tree_root is None:
            return None
        return DirectoryOwnerRecords(root=self._owner_tree_root)

    def _owner_tree_store(self):
        """The store, when it can index the owner tree in its own durable state."""
        if callable(getattr(self._store, "record_owner_intent", None)) and callable(
            getattr(self._store, "confirm_owner_process", None)
        ):
            return self._store
        return None

    def spawn(self, request: CoordinatorStartRequest | AdaptiveStartRequest) -> OwnedExecution:
        if self._active is not None and self.poll(self._active).running:
            raise CoordinatorOwnershipError("EXECUTION_OWNER_EXISTS")
        if not isinstance(request, (CoordinatorStartRequest, AdaptiveStartRequest)):
            raise CoordinatorOwnershipError("START_REQUEST_INVALID")
        if self._store is not None:
            self._store.record_execution_owner_intent(request)
        owner_records = self._owner_tree_records()
        owner_store = self._owner_tree_store() if owner_records is not None else None
        owner_intent = None
        if owner_records is not None:
            # Intent before spawn: a crash between these two lines must leave an intent with no
            # process, never a process no reaper can find. The shared tree root is written first:
            # it is the record the demo-side spawn boundaries and the offline recovery read.
            owner_intent = OwnerIntent.for_argv(
                campaign_id=request.campaign_id,
                batch_id=request.batch_id,
                role="ADAPTER",
                generation=_owner_generation(request),
                spawn_token="spawn-" + uuid.uuid4().hex,
                argv=request.argv,
                parent_spawn_token=None,
                own_session=True,
            )
            owner_records.record_owner_intent(owner_intent)
            if owner_store is not None:
                owner_store.record_owner_intent(owner_intent)
        if isinstance(request, CoordinatorStartRequest):
            request.batch_root.parent.mkdir(parents=True, exist_ok=True)
            process_log = request.batch_root.parent / f"{request.batch_id}.coordinator.log"
        else:
            # The upstream adaptive CLI claims exclusive creation of
            # runtime_root (DUPLICATE_BATCH_EVIDENCE_ROOT otherwise) but
            # accepts a pre-existing evidence root with mode 0700, so only
            # that root is prepared here and the wrapper log lives inside it.
            request.evidence_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            process_log = (
                request.evidence_root / f"{request.batch_id}.adaptive-wrapper.log"
            )
        environment = os.environ.copy()
        environment.update(request.environment)
        if owner_intent is not None:
            environment.update(_owner_tree_environment(owner_intent, self._owner_tree_root))
        with open(
            process_log,
            "xb",
            buffering=0,
            opener=lambda path, flags: os.open(path, flags | os.O_NOFOLLOW, 0o600),
        ) as output:
            process = subprocess.Popen(
                request.argv,
                env=environment,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                close_fds=True,
            )
        self._children[process.pid] = process
        try:
            identity = self._await_identity(process.pid, request.argv)
        except Exception as error:
            receipt = self._abandon(process, request, error)
            raise
        environment_hash = _canonical_hash(dict(request.environment))
        if isinstance(request, CoordinatorStartRequest):
            owned: OwnedExecution = OwnedCoordinator(
                campaign_id=request.campaign_id,
                batch_id=request.batch_id,
                pid=process.pid,
                pgid=identity.pgid,
                started_ticks=identity.started_ticks,
                argv_sha256=command_fingerprint(request.argv),
                environment_sha256=environment_hash,
                control_socket=request.control_socket,
                coordinator_epoch=request.coordinator_epoch,
            )
        else:
            runner_pid, runner_batch_id = self._read_adaptive_handshake(request, process.pid)
            owned = OwnedAdaptiveWrapper(
                campaign_id=request.campaign_id,
                batch_id=request.batch_id,
                pid=process.pid,
                pgid=identity.pgid,
                started_ticks=identity.started_ticks,
                argv_sha256=command_fingerprint(request.argv),
                environment_sha256=environment_hash,
                runner_pid=runner_pid,
                runner_batch_id=runner_batch_id,
                runner_journal_root=request.runtime_root,
            )
        self._active = owned
        if owner_intent is not None:
            confirmation = ConfirmedOwnerProcess(
                spawn_token=owner_intent.spawn_token,
                pid=process.pid,
                pgid=identity.pgid,
                started_ticks=identity.started_ticks,
                # The same fingerprint the owner verifies against later, so a recovery
                # compares the live kernel command with the readback.
                command_sha256=command_fingerprint(request.argv),
                confirmed_at_ns=time.time_ns(),
            )
            try:
                owner_records.confirm_owner_process(confirmation)
                if owner_store is not None:
                    owner_store.confirm_owner_process(confirmation)
            except Exception as error:
                raise CoordinatorOwnershipError("OWNER_CONFIRMATION_LOST", owned=owned) from error
        if self._store is not None:
            try:
                self._store.acknowledge_execution_owner(owned)
            except Exception as error:
                raise CoordinatorOwnershipError("SPAWN_ACK_LOST", owned=owned) from error
        return owned

    def _await_identity(self, pid: int, argv: tuple[str, ...]) -> _ProcessIdentity:
        """Wait until the child is provably the process that was asked for.

        The kernel's argv is authoritative, and a launcher may legitimately rewrite the head of it:
        a shebang script becomes ``[interpreter, script, ...]`` and an interpreter that re-execs
        itself reports the binary rather than the path it was invoked through. So every argument
        after ``argv[0]`` must match exactly, and the child must lead its own group, because that
        group is what a later cleanup signals.
        """
        deadline = time.monotonic() + 10.0
        last_error = None
        while time.monotonic() < deadline:
            try:
                identity = _read_identity(pid)
                if (
                    identity.state != "Z"
                    and identity.pgid == pid
                    and argv_matches(identity, argv)
                ):
                    return identity
            except CoordinatorOwnershipError as error:
                last_error = error
            time.sleep(0.005)
        raise CoordinatorOwnershipError("EXEC_BARRIER_ACK_MISSING") from last_error

    def _read_adaptive_handshake(
        self, request: AdaptiveStartRequest, wrapper_pid: int
    ) -> tuple[int | None, str | None]:
        path = request.runtime_root / "handshake.json"
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                if document.get("wrapper_pid") != wrapper_pid or document.get("batch_id") != request.batch_id:
                    raise CoordinatorOwnershipError("RUNNER_BINDING_MISMATCH")
                runner_pid = document.get("runner_pid")
                if isinstance(runner_pid, bool) or not isinstance(runner_pid, int) or runner_pid <= 0:
                    raise CoordinatorOwnershipError("RUNNER_BINDING_MISMATCH")
                return runner_pid, request.batch_id
            except FileNotFoundError:
                time.sleep(0.01)
            except (json.JSONDecodeError, OSError) as error:
                raise CoordinatorOwnershipError("RUNNER_BINDING_MISMATCH") from error
        raise CoordinatorOwnershipError("RUNNER_BINDING_ACK_MISSING")

    def _reap(self, pid: int) -> int | None:
        """Collect the child if this owner still holds it; never block on a survivor."""
        child = self._children.pop(pid, None)
        if child is None:
            return None
        try:
            return child.wait(timeout=self._stop_timeout_s)
        except Exception:
            return None

    def _abandon(self, process, request, error: Exception):
        """Clear the group created for a failed spawn, then re-raise the original failure.

        The pid of a process spawned with ``start_new_session=True`` is its own group id, so the
        cleanup does not depend on reading an identity - which is exactly what failed here. If the
        group cannot be cleared, that is recorded as a recovery fence rather than hidden behind the
        original error, because the operator has to see a live orphan.
        """
        receipt = terminate_group(
            pgid=process.pid, leader_pid=process.pid, timeout_s=self._stop_timeout_s
        )
        self._reap(process.pid)
        if receipt.clear:
            return receipt
        reason = f"SPAWN_ORPHANED_OWNED_GROUP: {receipt.describe()}"
        if self._store is not None:
            try:
                self._store.record_recovery_fence(
                    request.campaign_id,
                    request.batch_id,
                    reason=reason,
                    command_id="spawn-" + str(process.pid),
                )
                return receipt
            except Exception:
                reason = f"{reason} (recovery fence could not be recorded)"
        raise CoordinatorOwnershipError(f"{type(error).__name__}: {error} / {reason}") from error

    def reconnect(self, binding: OwnedExecution) -> OwnedExecution:
        self._verify(binding)
        if self._active is not None and self._active != binding and self.poll(self._active).running:
            raise CoordinatorOwnershipError("EXECUTION_OWNER_EXISTS")
        self._active = binding
        return binding

    def _verify(self, owned: OwnedExecution) -> _ProcessIdentity:
        """Prove the live process is the recorded owner: pid, group, start marker and command.

        The command is compared through :func:`command_fingerprint`, which ignores ``argv[0]``: an
        interpreter that re-execs itself is still the same process, and on this platform that
        re-exec legitimately rewrites the launcher it reports.
        """
        identity = _read_identity(owned.pid)
        if (
            identity.state == "Z"
            or identity.pgid != owned.pgid
            or identity.started_ticks != owned.started_ticks
            or identity.command_sha256 != owned.argv_sha256
        ):
            # The refusal names the field that drifted; a bare code cannot be audited.
            raise CoordinatorOwnershipError(
                "PROCESS_IDENTITY_MISMATCH: "
                f"pid {owned.pid} state {identity.state!r} "
                f"pgid {identity.pgid} != {owned.pgid} "
                f"start {identity.started_ticks} != {owned.started_ticks} "
                f"command {identity.command_sha256[:12]} != {owned.argv_sha256[:12]}"
            )
        return identity

    def poll(self, owned: OwnedExecution) -> ProcessStatus:
        child = self._children.get(owned.pid)
        exit_code = child.poll() if child is not None else None
        try:
            identity = _read_identity(owned.pid)
            running = identity.state != "Z" and exit_code is None
        except CoordinatorOwnershipError:
            running = False
        descendants = _group_has_live_descendants(owned.pgid, owned.pid)
        return ProcessStatus(running=running, exit_code=exit_code, descendants_alive=descendants)

    @staticmethod
    def identity_alive(pid: int, started_ticks: int, argv_sha256: str) -> bool:
        """Prove whether a durable owner record still names a live process."""
        return identity_alive(pid, started_ticks, argv_sha256)

    def request_status(self, owned: OwnedExecution) -> ProcessStatus:
        return self.poll(owned)

    def verify_execution_identity(self, owned: OwnedExecution) -> None:
        """Prove the recorded leader without signalling or changing ownership."""
        self._verify(owned)

    def request_cancel(self, owned: OwnedExecution) -> None:
        if not isinstance(owned, OwnedAdaptiveWrapper):
            raise CoordinatorOwnershipError("FIXED_CANCEL_REQUIRES_CONTROL_SOCKET")
        self._verify(owned)
        os.kill(owned.pid, signal.SIGINT)

    def stop_after_cleanup(self, owned: OwnedExecution, authorization=None) -> None:
        if not isinstance(owned, OwnedCoordinator):
            raise CoordinatorOwnershipError("ADAPTIVE_STOP_REQUIRES_WRAPPER_CLEANUP")
        authorized = self._cleanup_checker(owned)
        if authorization is not None:
            authorized = (
                getattr(authorization, "batch_id", None) == owned.batch_id
                and getattr(authorization, "coordinator_epoch", None)
                == owned.coordinator_epoch
                and getattr(authorization, "batch_cleanup_complete", False) is True
                and getattr(authorization, "owned_descendants_gone", False) is True
                and getattr(authorization, "assigned_ros_domains_clear", False) is True
                and isinstance(getattr(authorization, "receipt_sha256", None), str)
            )
        if not authorized:
            raise CoordinatorOwnershipError("CLEANUP_NOT_CONFIRMED")
        self._verify(owned)
        receipt = terminate_group(
            pgid=owned.pgid, leader_pid=owned.pid, timeout_s=self._stop_timeout_s
        )
        try:
            if not receipt.clear:
                raise CoordinatorOwnershipError(
                    f"OWNED_GROUP_STOP_TIMEOUT: {receipt.describe()}"
                )
        finally:
            # Whatever the outcome, this owner stops holding a handle it no longer owns.
            self._reap(owned.pid)
        self._active = None
