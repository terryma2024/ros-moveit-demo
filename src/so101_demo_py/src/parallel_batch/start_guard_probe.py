"""Bounded, single-flight startup probe: the owner coordinates, a helper does the reads.

Task 4 of the lightweight start guard plan. The design requires that every potentially
blocking read (``/proc``, cgroup, NVML) happens in a short-lived helper process, that the
whole request is bounded by the policy deadline, that concurrent requests share one
task-level lock across processes, and that a helper which cannot be reaped becomes a durable
``PROBE_CLEANUP_BLOCKED`` state that forbids new probes, retries and spawns until ownership
aware cleanup resolves it.

The owner never reads the resource files itself and never blocks without a deadline: state
and lock I/O also run under the deadline.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import select
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .start_guard import (
    FAIL,
    PASS,
    WARN,
    GuardCheck,
    GuardResult,
    GuardScope,
    ProbeError,
    ResourceSnapshot,
    StartGuardPolicy,
    _read_cpu,
    _read_cpu_busy,
    _read_ram,
    evaluate_snapshot,
    host_ports,
    probe_snapshot,
)

# Imported for the schema-v4 accelerator hook. The import is a module reference only: the MPS
# vocabulary stays in accelerator_probe, so schema v3 never pays for it and never consults it.
from . import accelerator_probe as _accelerator_probe

CLEAR = "CLEAR"
PROBE_CLEANUP_BLOCKED = "PROBE_CLEANUP_BLOCKED"

STATE_FILENAME = "cleanup-state.json"
LOCK_FILENAME = "start-guard.lock"
HELPER_MODULE = "so101_demo.parallel_batch.start_guard_probe"

#: Bounded reserve for terminate -> kill -> reap after the request deadline.
TERMINATE_GRACE_S = 0.20
KILL_GRACE_S = 0.20
#: Cap on a single blocking filesystem call issued by the owner.
STATE_IO_BUDGET_S = 0.50
LOCK_POLL_S = 0.02


class CoordinatorError(RuntimeError):
    """The coordinator itself is misconfigured; the caller cannot treat this as a PASS."""


@dataclass(frozen=True)
class ProcessIdentityRecord:
    pid: int
    start_time_ticks: int


@dataclass(frozen=True)
class CleanupState:
    cleanup_state: str = CLEAR
    pid: int | None = None
    start_time_ticks: int | None = None
    recorded_monotonic_s: float | None = None
    detail: str = ""


def read_process_identity(pid: int) -> ProcessIdentityRecord | None:
    """Exact process identity from ``/proc/<pid>/stat`` field 22, or None when gone.

    A zombie keeps its ``/proc`` entry until it is reaped, but it is not a running owner:
    reporting it as gone is what lets the caller clear a stale cleanup record instead of
    signalling a process that can no longer receive a signal.
    """

    if type(pid) is not int or pid <= 0:
        return None
    try:
        document = (Path("/proc") / str(pid) / "stat").read_text()
    except (OSError, UnicodeError):
        return _read_portable_process_identity(pid)
    close = document.rfind(")")
    if close < 0:
        return None
    fields = document[close + 1:].split()
    if not fields or fields[0] == "Z":
        return None
    try:
        from ..runtime.parallel_processes import _parse_proc_stat_start_time

        ticks = _parse_proc_stat_start_time(document)
    except (ImportError, ValueError):
        return None
    return ProcessIdentityRecord(pid=pid, start_time_ticks=ticks)


def _read_portable_process_identity(pid: int) -> ProcessIdentityRecord | None:
    try:
        import psutil
    except ImportError:
        return None
    try:
        process = psutil.Process(pid)
        created_us = int(round(process.create_time() * 1_000_000))
        if process.status() == psutil.STATUS_ZOMBIE or created_us <= 0:
            return None
    except (psutil.Error, OSError, ValueError):
        return None
    return ProcessIdentityRecord(pid=pid, start_time_ticks=created_us)


def default_state_root() -> Path:
    root = os.environ.get("SO101_TASK_ROOT")
    if not root:
        raise CoordinatorError("PROBE_STATE_ROOT_UNSET: SO101_TASK_ROOT")
    return Path(root) / "start-guard-state"


def coordination_key(task_root: Path) -> str:
    """hostname + operator uid + task root, so INDEX/UUID aliases share one lock."""

    import hashlib

    material = f"{socket.gethostname()}\0{os.getuid()}\0{Path(task_root)}".encode()
    return hashlib.sha256(material).hexdigest()


class _BoundedIO:
    """Run a blocking filesystem call off the owner thread with a bounded wait."""

    def call(self, operation, remaining_s: float):
        box: list = []

        def run() -> None:
            try:
                box.append((True, operation()))
            except BaseException as error:  # noqa: BLE001 - reported to the caller
                box.append((False, error))

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(max(0.0, remaining_s))
        if thread.is_alive():
            return False, None
        ok, value = box[0]
        if not ok:
            raise value
        return True, value


@dataclass
class _ResultPort:
    """The child side of one request; the owner only polls and reaps it."""

    process: object
    identity: ProcessIdentityRecord | None


class ProbeCoordinator:
    """Owner-side coordinator. One task-level lock, one helper per request, bounded waits."""

    def __init__(self, state_root: Path | None = None, *, clock=time.monotonic,
                 popen=None, python: str | None = None,
                 terminate_grace_s: float = TERMINATE_GRACE_S,
                 kill_grace_s: float = KILL_GRACE_S) -> None:
        self._state_root = Path(state_root) if state_root is not None else default_state_root()
        self._state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock_path = self._state_root / LOCK_FILENAME
        self._state_path = self._state_root / STATE_FILENAME
        self._clock = clock
        self._popen = popen or subprocess.Popen
        self._python = python or sys.executable
        self._terminate_grace_s = terminate_grace_s
        self._kill_grace_s = kill_grace_s
        self._io = _BoundedIO()

    # -- state -------------------------------------------------------------------------

    @property
    def state_path(self) -> Path:
        return self._state_path

    @property
    def lock_path(self) -> Path:
        return self._lock_path

    def _read_state_sync(self) -> CleanupState:
        try:
            document = json.loads(self._state_path.read_text())
        except FileNotFoundError:
            return CleanupState()
        except (OSError, ValueError) as error:
            raise CoordinatorError(f"PROBE_STATE_UNREADABLE: {error}") from error
        if not isinstance(document, dict):
            raise CoordinatorError("PROBE_STATE_CORRUPT")
        state = document.get("cleanup_state")
        if state not in (CLEAR, PROBE_CLEANUP_BLOCKED):
            raise CoordinatorError("PROBE_STATE_CORRUPT")
        for name in ("pid", "start_time_ticks"):
            value = document.get(name)
            if value is not None and (type(value) is not int or value <= 0):
                raise CoordinatorError("PROBE_STATE_CORRUPT")
        return CleanupState(
            cleanup_state=state,
            pid=document.get("pid"),
            start_time_ticks=document.get("start_time_ticks"),
            recorded_monotonic_s=document.get("recorded_monotonic_s"),
            detail=str(document.get("detail") or ""),
        )

    def _write_state_sync(self, state: CleanupState) -> None:
        payload = {
            "cleanup_state": state.cleanup_state,
            "pid": state.pid,
            "start_time_ticks": state.start_time_ticks,
            "recorded_monotonic_s": (state.recorded_monotonic_s if state.recorded_monotonic_s
                                     is not None else self._clock()),
            "detail": state.detail,
        }
        temporary = self._state_path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(descriptor, json.dumps(payload, sort_keys=True).encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, self._state_path)

    def cleanup_state(self) -> str:
        """Best-effort read of the durable state; corrupt state fails closed."""

        try:
            return self._read_state_sync().cleanup_state
        except CoordinatorError:
            return PROBE_CLEANUP_BLOCKED

    # -- lock --------------------------------------------------------------------------

    def _acquire_lock(self, deadline: float):
        descriptor = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return descriptor
            except OSError:
                if self._clock() >= deadline:
                    os.close(descriptor)
                    return None
                time.sleep(min(LOCK_POLL_S, max(0.0, deadline - self._clock())))

    @staticmethod
    def _release_lock(descriptor) -> None:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    # -- cleanup recovery --------------------------------------------------------------

    def _terminate_exact(self, pid: int, start_time_ticks: int) -> bool:
        """Signal only the exact owned process; a reused PID is never signalled."""

        def matches() -> bool:
            identity = read_process_identity(pid)
            return identity is not None and identity.start_time_ticks == start_time_ticks

        if not matches():
            return True
        for signal_number, grace in ((signal.SIGTERM, self._terminate_grace_s),
                                     (signal.SIGKILL, self._kill_grace_s)):
            try:
                os.kill(pid, signal_number)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            moment = self._clock()
            while self._clock() - moment < grace:
                if not matches():
                    return True
                time.sleep(0.02)
        return not matches()

    def recover_owned_cleanup(self) -> str:
        """Verify a persisted cleanup record against the exact process identity."""

        state = self._read_state_sync()
        if state.cleanup_state == CLEAR:
            return CLEAR
        if state.pid is None or state.start_time_ticks is None:
            self._write_state_sync(CleanupState(detail="no owned identity recorded"))
            return CLEAR
        identity = read_process_identity(state.pid)
        if identity is None or identity.start_time_ticks != state.start_time_ticks:
            self._write_state_sync(CleanupState(
                detail=f"owned pid {state.pid} is gone or its identity was reused"))
            return CLEAR
        if self._terminate_exact(state.pid, state.start_time_ticks):
            self._write_state_sync(CleanupState(
                detail=f"recovered owned helper pid {state.pid}"))
            return CLEAR
        return PROBE_CLEANUP_BLOCKED

    # -- request -----------------------------------------------------------------------

    def _fail(self, scope: GuardScope, started: float, reason: str, detail: str,
              cleanup_state: str) -> GuardResult:
        completed = self._clock()
        return GuardResult(
            scope=scope, status=FAIL, started_monotonic_s=started,
            completed_monotonic_s=max(started, completed),
            checks={"probe": GuardCheck(FAIL, reason, None, None, "state")},
            snapshot=None, cleanup_state=cleanup_state)

    def _spawn(self, request: bytes, deadline: float):
        request_read, request_write = os.pipe()
        result_read, result_write = os.pipe()
        # The child inherits the read end of the request pipe and the write end of the
        # result pipe; the owner keeps the opposite ends and never passes a path.
        argv = [self._python, "-m", HELPER_MODULE,
                "--request-fd", str(request_read), "--result-fd", str(result_write)]
        try:
            process = self._popen(argv, pass_fds=(request_read, result_write),
                                  close_fds=True, stdin=subprocess.DEVNULL)
        except OSError as error:
            for descriptor in (request_read, request_write, result_read, result_write):
                os.close(descriptor)
            raise CoordinatorError(f"PROBE_SPAWN_FAILED: {error}") from error
        os.close(request_read)
        os.close(result_write)
        identity = read_process_identity(int(process.pid))
        try:
            os.write(request_write, request)
        except (BrokenPipeError, OSError):
            pass
        finally:
            os.close(request_write)
        return _ResultPort(process=process, identity=identity), result_read

    def _collect_result(self, descriptor, process, deadline: float) -> bytes | None:
        chunks: list[bytes] = []
        while True:
            remaining = deadline - self._clock()
            if remaining <= 0:
                os.close(descriptor)
                return None
            ready, _, _ = select.select([descriptor], [], [], min(remaining, 0.05))
            if not ready:
                if process.poll() is not None:
                    continue
                continue
            data = os.read(descriptor, 65536)
            if not data:
                os.close(descriptor)
                return b"".join(chunks)
            chunks.append(data)

    def _reap(self, process, deadline: float) -> bool:
        remaining = deadline - self._clock()
        if remaining > 0:
            try:
                process.wait(timeout=remaining)
                return True
            except subprocess.TimeoutExpired:
                pass
        for action, grace in ((process.terminate, self._terminate_grace_s),
                              (process.kill, self._kill_grace_s)):
            try:
                action()
            except (ProcessLookupError, OSError):
                return True
            try:
                process.wait(timeout=grace)
                return True
            except subprocess.TimeoutExpired:
                continue
        return False

    def _read_state_bounded(self, remaining_s: float):
        """Returns (kind, payload): 'ok' with the state, or 'timeout'/'corrupt'."""

        try:
            ok, state = self._io.call(self._read_state_sync, min(STATE_IO_BUDGET_S, remaining_s))
        except CoordinatorError as error:
            return "corrupt", str(error)
        if not ok:
            return "timeout", "cleanup state read"
        return "ok", state

    def check(self, policy: StartGuardPolicy, scope: GuardScope, *,
              accelerator: object | None = None) -> GuardResult:
        """One bounded request. Never raises for a resource problem; always returns a result.

        ``accelerator`` is the schema-v4 hook. When it is supplied (an
        :class:`~so101_demo.parallel_batch.accelerator_probe.AcceleratorProbe`, a bare callable
        taking ``deadline_monotonic_ns``, or a ready
        :class:`~so101_demo.parallel_batch.accelerator_probe.AcceleratorSnapshot`), its
        admission check runs inside the same policy deadline and is merged into the result. When
        it is omitted the result is exactly the schema-v3 result.
        """

        if not isinstance(policy, StartGuardPolicy) or not isinstance(scope, GuardScope):
            raise ValueError("policy and scope must be the closed models")
        started = self._clock()
        deadline = started + policy.timeout_s

        kind, state = self._read_state_bounded(policy.timeout_s)
        if kind == "corrupt":
            return self._fail(scope, started, "PROBE_STATE_CORRUPT", str(state),
                              PROBE_CLEANUP_BLOCKED)
        if kind == "timeout":
            return self._fail(scope, started, "PROBE_STATE_IO_TIMEOUT", "cleanup state read",
                              PROBE_CLEANUP_BLOCKED)
        if state.cleanup_state != CLEAR:
            return self._fail(scope, started, PROBE_CLEANUP_BLOCKED, state.detail,
                              PROBE_CLEANUP_BLOCKED)

        lock = self._acquire_lock(deadline)
        if lock is None:
            return self._fail(scope, started, "PROBE_BUSY",
                              "another guarded request holds the task lock", CLEAR)
        try:
            kind, state = self._read_state_bounded(max(0.0, deadline - self._clock()))
            if kind == "corrupt":
                return self._fail(scope, started, "PROBE_STATE_CORRUPT", str(state),
                                  PROBE_CLEANUP_BLOCKED)
            if kind == "timeout":
                return self._fail(scope, started, "PROBE_STATE_IO_TIMEOUT", "cleanup state read",
                                  PROBE_CLEANUP_BLOCKED)
            if state.cleanup_state != CLEAR:
                return self._fail(scope, started, PROBE_CLEANUP_BLOCKED, state.detail,
                                  PROBE_CLEANUP_BLOCKED)

            request = json.dumps({
                "policy": {
                    "timeout_s": policy.timeout_s,
                    "cpu_busy_warn_fraction": policy.cpu_busy_warn_fraction,
                    "ram_minimum_bytes": policy.ram_minimum_bytes,
                    "ram_minimum_fraction": policy.ram_minimum_fraction,
                    "gpu_minimum_bytes": policy.gpu_minimum_bytes,
                    # Schema v4 discriminator: the Darwin policy carries an MPS headroom floor,
                    # which tells the helper it is probing the unified-memory accelerator rather
                    # than an NVIDIA device. A v3 policy leaves it None and the helper keeps its
                    # NVML path unchanged.
                    "mps_minimum_headroom_bytes": policy.mps_minimum_headroom_bytes,
                },
                "scope": {
                    "batch_id": scope.batch_id,
                    "epoch": scope.epoch,
                    "owner_pid": scope.owner_pid,
                    "owner_starttime_ticks": scope.owner_starttime_ticks,
                    "gpu_selector": scope.gpu_selector,
                    "worker_count": scope.worker_count,
                },
                "request_started_monotonic_s": started,
                "deadline_monotonic_s": deadline,
            }).encode()

            port, descriptor = self._spawn(request, deadline)
            payload = self._collect_result(descriptor, port.process, deadline)
            reaped = self._reap(port.process, deadline)
            if not reaped:
                identity = port.identity
                self._io.call(lambda: self._write_state_sync(CleanupState(
                    cleanup_state=PROBE_CLEANUP_BLOCKED,
                    pid=identity.pid if identity else None,
                    start_time_ticks=identity.start_time_ticks if identity else None,
                    detail="helper could not be reaped within the bounded grace")),
                    STATE_IO_BUDGET_S)
                return self._fail(scope, started, PROBE_CLEANUP_BLOCKED,
                                  "helper not reaped", PROBE_CLEANUP_BLOCKED)
            if payload is None:
                return self._fail(scope, started, "PROBE_TIMEOUT",
                                  "helper produced no result before the deadline", CLEAR)
            try:
                document = json.loads(payload.decode())
            except (UnicodeDecodeError, ValueError) as error:
                return self._fail(scope, started, "PROBE_RESULT_INVALID", str(error), CLEAR)
            result = _result_from_document(document, scope)
            return self._merge_accelerator(result, policy, accelerator)
        finally:
            self._release_lock(lock)

    # -- schema-v4 accelerator admission -------------------------------------------------

    def _merge_accelerator(self, result: GuardResult, policy: StartGuardPolicy,
                           accelerator: object | None) -> GuardResult:
        """Run the MPS admission check inside the same deadline and merge it into the result.

        A v4 Darwin policy always carries ``mps_minimum_headroom_bytes``. If it does, the
        accelerator check is mandatory: a missing probe, a probe error, a malformed snapshot or
        a figure below the fixed floor all produce a FAIL rather than an unguarded start. A
        policy without the floor is the v3 shape and is returned untouched.
        """

        if policy.mps_minimum_headroom_bytes is None:
            return result

        def refused(reason: str, detail: str) -> GuardResult:
            checks = dict(result.checks)
            # The helper's own checks are kept for diagnosis; the refusal is what decides.
            checks["mps_accelerator"] = GuardCheck(FAIL, reason, detail or None, None, "state")
            return _with_checks(result, checks, FAIL)

        if accelerator is None:
            return refused("MPS_ACCELERATOR_PROBE_MISSING",
                           "the Darwin combination requires an accelerator probe")

        snapshot: object = accelerator
        if not isinstance(snapshot, _accelerator_probe.AcceleratorSnapshot):
            reader = getattr(accelerator, "probe", None)
            if reader is None and callable(accelerator):
                reader = accelerator
            if reader is None:
                return refused("MPS_ACCELERATOR_PROBE_MISSING",
                               f"{type(accelerator).__name__} is not a probe")
            remaining_ns = int((self._clock() + policy.timeout_s) * 1_000_000_000)
            try:
                snapshot = reader(deadline_monotonic_ns=remaining_ns)
            except _accelerator_probe.ProbeError as error:
                return refused(error.reason, error.detail)
            except Exception as error:  # noqa: BLE001 - any probe failure is a refusal
                return refused("MPS_ACCELERATOR_PROBE_FAILED",
                               f"{type(error).__name__}: {error}")

        if not isinstance(snapshot, _accelerator_probe.AcceleratorSnapshot):
            return refused("MPS_ACCELERATOR_SNAPSHOT_INVALID",
                           f"{type(snapshot).__name__} is not an AcceleratorSnapshot")
        try:
            evaluation = _accelerator_probe.evaluate_accelerator_snapshot(snapshot, policy)
        except _accelerator_probe.ProbeError as error:
            return refused(error.reason, error.detail)

        checks = dict(result.checks)
        checks.update(evaluation.checks)
        status = FAIL if FAIL in {check.status for check in checks.values()} else result.status
        return _with_checks(result, checks, status)


# --------------------------------------------------------------------------------------
# result transport
# --------------------------------------------------------------------------------------


def _with_checks(result: GuardResult, checks: dict, status: str) -> GuardResult:
    """A copy of ``result`` with merged checks; the snapshot and cleanup state are preserved."""

    return GuardResult(
        scope=result.scope,
        status=status,
        started_monotonic_s=result.started_monotonic_s,
        completed_monotonic_s=result.completed_monotonic_s,
        checks=checks,
        snapshot=result.snapshot,
        cleanup_state=result.cleanup_state,
    )


def _result_to_document(result: GuardResult) -> dict:
    return {
        "status": result.status,
        "started_monotonic_s": result.started_monotonic_s,
        "completed_monotonic_s": result.completed_monotonic_s,
        "cleanup_state": result.cleanup_state,
        "checks": {
            name: {"status": check.status, "reason": check.reason, "observed": check.observed,
                   "cutoff": check.cutoff, "unit": check.unit}
            for name, check in result.checks.items()
        },
        "snapshot": None if result.snapshot is None else {
            "observed_monotonic_s": result.snapshot.observed_monotonic_s,
            "effective_cpuset": list(result.snapshot.effective_cpuset),
            "effective_cpu_cores": result.snapshot.effective_cpu_cores,
            "cpu_busy_fraction": result.snapshot.cpu_busy_fraction,
            "ram_capacity_bytes": result.snapshot.ram_capacity_bytes,
            "ram_available_bytes": result.snapshot.ram_available_bytes,
            "gpu_uuid": result.snapshot.gpu_uuid,
            "gpu_total_bytes": result.snapshot.gpu_total_bytes,
            "gpu_free_bytes": result.snapshot.gpu_free_bytes,
            "limit_sources": list(result.snapshot.limit_sources),
        },
    }


def _result_from_document(document: object, scope: GuardScope) -> GuardResult:
    if not isinstance(document, dict):
        raise CoordinatorError("PROBE_RESULT_INVALID")
    checks = {}
    for name, payload in dict(document.get("checks") or {}).items():
        checks[str(name)] = GuardCheck(
            status=payload["status"], reason=payload["reason"], observed=payload.get("observed"),
            cutoff=payload.get("cutoff"), unit=payload["unit"])
    raw_snapshot = document.get("snapshot")
    snapshot = None
    if raw_snapshot is not None:
        snapshot = ResourceSnapshot(
            observed_monotonic_s=raw_snapshot["observed_monotonic_s"],
            effective_cpuset=tuple(raw_snapshot["effective_cpuset"]),
            effective_cpu_cores=raw_snapshot["effective_cpu_cores"],
            cpu_busy_fraction=raw_snapshot["cpu_busy_fraction"],
            ram_capacity_bytes=raw_snapshot["ram_capacity_bytes"],
            ram_available_bytes=raw_snapshot["ram_available_bytes"],
            gpu_uuid=raw_snapshot["gpu_uuid"],
            gpu_total_bytes=raw_snapshot["gpu_total_bytes"],
            gpu_free_bytes=raw_snapshot["gpu_free_bytes"],
            limit_sources=tuple(raw_snapshot["limit_sources"]),
        )
    return GuardResult(
        scope=scope, status=document["status"],
        started_monotonic_s=document["started_monotonic_s"],
        completed_monotonic_s=document["completed_monotonic_s"],
        checks=checks, snapshot=snapshot, cleanup_state=document["cleanup_state"])


# --------------------------------------------------------------------------------------
# helper entry point
# --------------------------------------------------------------------------------------


def _read_all(descriptor: int) -> bytes:
    chunks = []
    while True:
        data = os.read(descriptor, 65536)
        if not data:
            return b"".join(chunks)
        chunks.append(data)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        offset += os.write(descriptor, payload[offset:])


def _v4_cpu_ram_result(policy: StartGuardPolicy, scope: GuardScope,
                       deadline_monotonic_s: float, started_monotonic_s: float) -> GuardResult:
    """The Darwin half of the guard: real CPU/RAM checks, no NVIDIA probe, no fabricated GPU.

    Check names, cutoffs and units mirror `evaluate_snapshot` exactly so the parent's accelerator
    merge needs no second vocabulary; only the `gpu` check is absent, because on this platform the
    MPS proxy admission replaces it.
    """

    active = host_ports()
    clock = active.clock or time.monotonic
    checks: dict[str, GuardCheck] = {}
    try:
        cpuset, cores, _sources = _read_cpu(active, clock)
        ram_capacity, ram_available, _ram_sources = _read_ram(active)
        busy = _read_cpu_busy(active, clock, deadline_monotonic_s)
    except ProbeError as error:
        return GuardResult(
            scope=scope, status=FAIL, started_monotonic_s=started_monotonic_s,
            completed_monotonic_s=max(started_monotonic_s, time.monotonic()),
            checks={"probe": GuardCheck(FAIL, error.reason, None, None, "state")},
            snapshot=None, cleanup_state=CLEAR)

    if not cpuset or not math.isfinite(cores) or cores <= 0:
        checks["cpu_capacity"] = GuardCheck(
            FAIL, "CPU_CAPACITY_UNAVAILABLE", cores if math.isfinite(cores) else None,
            None, "cores")
    else:
        checks["cpu_capacity"] = GuardCheck(PASS, "CPU_CAPACITY_OK", cores, None, "cores")

    if busy is None:
        checks["cpu_busy"] = GuardCheck(
            WARN, "CPU_BUSY_UNKNOWN", None, policy.cpu_busy_warn_fraction, "fraction")
    elif busy > policy.cpu_busy_warn_fraction:
        checks["cpu_busy"] = GuardCheck(
            WARN, "CPU_BUSY", busy, policy.cpu_busy_warn_fraction, "fraction")
    else:
        checks["cpu_busy"] = GuardCheck(
            PASS, "CPU_BUSY_OK", busy, policy.cpu_busy_warn_fraction, "fraction")

    floor = max(policy.ram_minimum_bytes,
                int(math.floor(policy.ram_minimum_fraction * ram_capacity)))
    if ram_available < floor:
        checks["ram"] = GuardCheck(FAIL, "RAM_BELOW_MINIMUM", ram_available, floor, "bytes")
    else:
        checks["ram"] = GuardCheck(PASS, "RAM_OK", ram_available, floor, "bytes")

    status = FAIL if any(check.status == FAIL for check in checks.values()) else PASS
    return GuardResult(
        scope=scope, status=status, started_monotonic_s=started_monotonic_s,
        completed_monotonic_s=max(started_monotonic_s, time.monotonic()),
        checks=checks, snapshot=None, cleanup_state=CLEAR)


def run_helper(request_fd: int, result_fd: int) -> int:
    """Helper side: read one closed request, do every read, write one result."""

    try:
        request = json.loads(_read_all(request_fd).decode())
        policy = StartGuardPolicy(**request["policy"])
        scope = GuardScope(**request["scope"])
        deadline = float(request["deadline_monotonic_s"])
        request_started = float(request["request_started_monotonic_s"])
    except (KeyError, TypeError, ValueError) as error:
        payload = {"error": f"PROBE_REQUEST_INVALID: {error}"}
        _write_all(result_fd, json.dumps(payload).encode())
        return 2
    try:
        if request["policy"].get("mps_minimum_headroom_bytes") is None:
            snapshot = probe_snapshot(policy, scope, deadline)
            result = evaluate_snapshot(snapshot, policy, scope,
                                       started_monotonic_s=request_started,
                                       completed_monotonic_s=time.monotonic())
        else:
            # Schema v4 Darwin request: the accelerator admission is the parent's MPS proxy check,
            # evaluated against `mps_minimum_headroom_bytes`. This side must still measure and
            # enforce CPU/RAM - dropping them would make the Darwin guard weaker than v3 - but it
            # must not touch NVML, which is what `probe_snapshot`'s GPU read does. A GPU-less
            # snapshot is not representable in the frozen v3 model, so no snapshot is emitted and
            # no CUDA-shaped device is fabricated.
            result = _v4_cpu_ram_result(policy, scope, deadline, request_started)
    except ProbeError as error:
        completed = time.monotonic()
        result = GuardResult(
            scope=scope, status=FAIL, started_monotonic_s=request_started,
            completed_monotonic_s=max(request_started, completed),
            checks={"probe": GuardCheck(FAIL, error.reason, None, None, "state")},
            snapshot=None, cleanup_state=CLEAR)
    _write_all(result_fd, json.dumps(_result_to_document(result)).encode())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="so101-start-guard-probe", add_help=True)
    parser.add_argument("--request-fd", type=int, required=True)
    parser.add_argument("--result-fd", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    return run_helper(arguments.request_fd, arguments.result_fd)


if __name__ == "__main__":  # pragma: no cover - exercised through the module entry point
    sys.exit(main())

# --------------------------------------------------------------------------------------
# epoch composition
# --------------------------------------------------------------------------------------


class StartGuardRefused(RuntimeError):
    """A refused start. The caller must not allocate, spawn or create a partial batch."""

    def __init__(self, result: GuardResult) -> None:
        self.result = result
        self.reason = (result.checks.get("probe").reason if "probe" in result.checks
                       else "START_GUARD_REFUSED")
        super().__init__(self.reason)


def _scope_key(scope: GuardScope) -> tuple:
    return (scope.batch_id, scope.epoch, scope.owner_pid, scope.owner_starttime_ticks,
            scope.gpu_selector, scope.worker_count)


def _check_with_accelerator(coordinator, policy: StartGuardPolicy, scope: GuardScope,
                            accelerator: object | None) -> GuardResult:
    """Call the coordinator's ``check``, passing the accelerator hook only when it is needed.

    The keyword is only ever passed for a schema-v4 policy. That keeps every existing
    coordinator double (a plain object with ``check(policy, scope)``) valid for schema v3,
    which is the version still executed on Linux, instead of forcing a signature change on
    callers that have no accelerator concept.
    """

    if policy.mps_minimum_headroom_bytes is None:
        return coordinator.check(policy, scope)
    return coordinator.check(policy, scope, accelerator=accelerator)


class EpochStartGuard:
    """One fresh probe covers the spawns that immediately follow it in the same epoch.

    The result is never accepted from outside this object, is only reused while the scope is
    unchanged and the observation is still inside the policy deadline, and a FAIL is refused
    rather than downgraded.
    """

    def __init__(self, coordinator: ProbeCoordinator, policy: StartGuardPolicy, *,
                 clock=time.monotonic, accelerator: object | None = None) -> None:
        if not isinstance(coordinator, ProbeCoordinator):
            raise ValueError("coordinator must be a ProbeCoordinator")
        if not isinstance(policy, StartGuardPolicy):
            raise ValueError("policy must be a StartGuardPolicy")
        self._coordinator = coordinator
        self._policy = policy
        self._clock = clock
        self._accelerator = accelerator
        self._key: tuple | None = None
        self._result: GuardResult | None = None
        self._probes = 0

    @property
    def policy(self) -> StartGuardPolicy:
        return self._policy

    @property
    def probe_count(self) -> int:
        """How many fresh probes this guard has run; evidence that epochs are not re-probed."""

        return self._probes

    @property
    def last_result(self) -> GuardResult | None:
        return self._result

    def begin_epoch(self, scope: GuardScope) -> GuardResult:
        """Always take one fresh observation for the new epoch."""

        self._result = _check_with_accelerator(
            self._coordinator, self._policy, scope, self._accelerator)
        self._key = _scope_key(scope)
        self._probes += 1
        return self._result

    def require_before_spawn(self, scope: GuardScope) -> GuardResult:
        """Reuse the epoch result only while it is still valid; otherwise probe again."""

        if not isinstance(scope, GuardScope):
            raise ValueError("scope must be a GuardScope")
        reusable = (
            self._result is not None
            and self._key == _scope_key(scope)
            and self._result.status != FAIL
            and self._result.cleanup_state == CLEAR
            and (self._clock() - self._result.completed_monotonic_s) <= self._policy.timeout_s
        )
        if not reusable:
            return self.begin_epoch(scope)
        return self._result

    def require_startable(self, scope: GuardScope) -> GuardResult:
        """The fail-closed form every allocator/spawn path should use."""

        result = self.require_before_spawn(scope)
        if result.status == FAIL or result.cleanup_state != CLEAR:
            raise StartGuardRefused(result)
        return result


def compose_default_start_guard(policy: StartGuardPolicy, *,
                                state_root: Path | None = None,
                                accelerator: object | None = None) -> EpochStartGuard:
    """The installed composition: one task-level state root, one shared lock.

    ``accelerator`` selects the schema-v4 admission check. It is left ``None`` for schema v3,
    whose guard remains the NVML-backed snapshot guard.
    """

    return EpochStartGuard(ProbeCoordinator(state_root), policy, accelerator=accelerator)
