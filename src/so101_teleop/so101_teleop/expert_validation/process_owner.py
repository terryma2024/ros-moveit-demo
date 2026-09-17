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
from typing import Callable

from .adaptive import AdaptiveStartRequest
from .coordinator import CoordinatorStartRequest


class CoordinatorOwnershipError(RuntimeError):
    """A process cannot be proven to be the recorded execution owner."""

    def __init__(self, message: str, *, owned=None):
        super().__init__(message)
        self.owned = owned


def _canonical_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    argv_sha256: str


def _read_identity(pid: int) -> _ProcessIdentity:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        tail = stat[stat.rfind(")") + 2 :].split()
        command_line = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError) as error:
        raise CoordinatorOwnershipError("PROCESS_IDENTITY_MISMATCH") from error
    argv = tuple(
        item.decode("utf-8", errors="surrogateescape")
        for item in command_line.rstrip(b"\0").split(b"\0")
    )
    return _ProcessIdentity(
        pid=pid,
        pgid=int(tail[2]),
        started_ticks=int(tail[19]),
        state=tail[0],
        argv_sha256=_canonical_hash(argv),
    )


def _group_has_live_descendants(pgid: int, leader_pid: int) -> bool:
    for stat_path in Path("/proc").glob("[0-9]*/stat"):
        try:
            document = stat_path.read_text(encoding="utf-8")
            pid = int(document.split(" ", 1)[0])
            tail = document[document.rfind(")") + 2 :].split()
            if pid != leader_pid and int(tail[2]) == pgid and tail[0] != "Z":
                return True
        except (FileNotFoundError, ProcessLookupError, PermissionError, OSError, ValueError):
            continue
    return False


class ExecutionProcessOwner:
    """Own exactly one coordinator group or one adaptive wrapper PID."""

    def __init__(
        self,
        *,
        store=None,
        cleanup_checker: Callable[[OwnedExecution], bool] | None = None,
        stop_timeout_s: float = 3.0,
    ) -> None:
        self._store = store
        self._cleanup_checker = cleanup_checker or (lambda _owned: False)
        self._stop_timeout_s = stop_timeout_s
        self._active: OwnedExecution | None = None
        self._children: dict[int, subprocess.Popen] = {}

    @property
    def active_execution(self) -> OwnedExecution | None:
        return self._active

    def has_active_execution(self) -> bool:
        return self._active is not None and self.poll(self._active).running

    def spawn(self, request: CoordinatorStartRequest | AdaptiveStartRequest) -> OwnedExecution:
        if self._active is not None and self.poll(self._active).running:
            raise CoordinatorOwnershipError("EXECUTION_OWNER_EXISTS")
        if not isinstance(request, (CoordinatorStartRequest, AdaptiveStartRequest)):
            raise CoordinatorOwnershipError("START_REQUEST_INVALID")
        if self._store is not None:
            self._store.record_execution_owner_intent(request)
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
        except Exception:
            process.terminate()
            process.wait(timeout=self._stop_timeout_s)
            raise
        environment_hash = _canonical_hash(dict(request.environment))
        if isinstance(request, CoordinatorStartRequest):
            owned: OwnedExecution = OwnedCoordinator(
                campaign_id=request.campaign_id,
                batch_id=request.batch_id,
                pid=process.pid,
                pgid=identity.pgid,
                started_ticks=identity.started_ticks,
                argv_sha256=identity.argv_sha256,
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
                argv_sha256=identity.argv_sha256,
                environment_sha256=environment_hash,
                runner_pid=runner_pid,
                runner_batch_id=runner_batch_id,
                runner_journal_root=request.runtime_root,
            )
        self._active = owned
        if self._store is not None:
            try:
                self._store.acknowledge_execution_owner(owned)
            except Exception as error:
                raise CoordinatorOwnershipError("SPAWN_ACK_LOST", owned=owned) from error
        return owned

    def _await_identity(self, pid: int, argv: tuple[str, ...]) -> _ProcessIdentity:
        expected_hash = _canonical_hash(argv)
        deadline = time.monotonic() + 10.0
        last_error = None
        while time.monotonic() < deadline:
            try:
                identity = _read_identity(pid)
                if identity.state != "Z" and identity.argv_sha256 == expected_hash:
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

    def reconnect(self, binding: OwnedExecution) -> OwnedExecution:
        self._verify(binding)
        if self._active is not None and self._active != binding and self.poll(self._active).running:
            raise CoordinatorOwnershipError("EXECUTION_OWNER_EXISTS")
        self._active = binding
        return binding

    def _verify(self, owned: OwnedExecution) -> _ProcessIdentity:
        identity = _read_identity(owned.pid)
        if (
            identity.state == "Z"
            or identity.pgid != owned.pgid
            or identity.started_ticks != owned.started_ticks
            or identity.argv_sha256 != owned.argv_sha256
        ):
            raise CoordinatorOwnershipError("PROCESS_IDENTITY_MISMATCH")
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
        try:
            identity = _read_identity(pid)
        except CoordinatorOwnershipError:
            return False
        return (
            identity.state != "Z"
            and identity.started_ticks == started_ticks
            and identity.argv_sha256 == argv_sha256
        )

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
        os.killpg(owned.pgid, signal.SIGTERM)
        deadline = time.monotonic() + self._stop_timeout_s
        while time.monotonic() < deadline:
            state = self.poll(owned)
            if not state.running and not state.descendants_alive:
                self._active = None
                return
            time.sleep(0.01)
        raise CoordinatorOwnershipError("OWNED_GROUP_STOP_TIMEOUT")
