"""Exact-identity supervision for Broker and Worker process groups."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from typing import Callable, Mapping


class SupervisorError(RuntimeError):
    """A process is not demonstrably owned or failed its lifecycle contract."""


_ROLES = {"broker", "worker"}


@dataclass(frozen=True, slots=True)
class OwnedProcess:
    batch_id: str
    role: str
    pid: int
    pgid: int
    cmdline: tuple[str, ...]
    start_time: int

    def __post_init__(self):
        if not isinstance(self.batch_id, str) or not self.batch_id:
            raise SupervisorError("BATCH_ID")
        if self.role not in _ROLES:
            raise SupervisorError("UNOWNED_ROLE")
        for name in ("pid", "pgid", "start_time"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise SupervisorError("INCOMPLETE_MANIFEST")
        if not isinstance(self.cmdline, tuple) or not self.cmdline or any(
            not isinstance(item, str) or not item for item in self.cmdline
        ):
            raise SupervisorError("INCOMPLETE_MANIFEST")


def read_proc_identity(pid: int) -> OwnedProcess | None:
    """Read an identity fragment; batch/role are supplied from the owner manifest."""

    raise SupervisorError("MANIFEST_CONTEXT_REQUIRED")


def _parse_proc_stat_start_time(document: str) -> int:
    """Read field 22 without treating spaces in the parenthesized comm as fields."""
    if not isinstance(document, str):
        raise ValueError("PROC_STAT")
    close = document.rfind(")")
    if close < 0:
        raise ValueError("PROC_STAT")
    fields = document[close + 1:].split()
    if len(fields) <= 19:
        raise ValueError("PROC_STAT")
    value = int(fields[19])
    if value <= 0:
        raise ValueError("PROC_STAT")
    return value


def _proc_values(pid: int) -> tuple[int, tuple[str, ...], int]:
    try:
        stat_document = (Path("/proc") / str(pid) / "stat").read_text()
        pgid = os.getpgid(pid)
        cmdline = tuple(
            item.decode("utf-8", errors="strict")
            for item in (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
            if item
        )
        start_time = _parse_proc_stat_start_time(stat_document)
    except (OSError, UnicodeError, ValueError):
        return 0, (), 0
    return pgid, cmdline, start_time


def _proc_group_members(pgid: int) -> tuple[int, ...]:
    """Return same-user members of an exact numeric process group."""

    members = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            candidate = int(entry.name)
            if os.getpgid(candidate) == pgid and os.getsid(candidate) == pgid:
                members.append(candidate)
        except (OSError, ProcessLookupError, ValueError):
            continue
    return tuple(sorted(members))


class ProcessSupervisor:
    """Own only explicitly recorded process groups and recheck before signals."""

    def __init__(
        self,
        batch_id: str,
        *,
        identity_reader: Callable[[int], OwnedProcess | None] | None = None,
        signal_group: Callable[[int, int], None] = os.killpg,
        popen: Callable[..., object] = subprocess.Popen,
        manifest_path: Path | None = None,
        group_members_reader: Callable[[int], tuple[int, ...]] = _proc_group_members,
    ):
        if not isinstance(batch_id, str) or not batch_id:
            raise SupervisorError("BATCH_ID")
        self.batch_id = batch_id
        self._identity_reader = identity_reader or self._read_owned_identity
        self._signal_group = signal_group
        self._popen = popen
        self.manifest_path = None if manifest_path is None else Path(manifest_path)
        self._group_members_reader = group_members_reader
        self._owned: dict[int, tuple[OwnedProcess, Callable[[], int | None]]] = {}

    def _read_owned_identity(self, pid: int) -> OwnedProcess | None:
        if pid not in self._owned:
            return None
        expected, _ = self._owned[pid]
        pgid, cmdline, start_time = _proc_values(pid)
        if not pgid or not cmdline or not start_time:
            return None
        return OwnedProcess(
            expected.batch_id,
            expected.role,
            pid,
            pgid,
            cmdline,
            start_time,
        )

    @property
    def processes(self) -> tuple[OwnedProcess, ...]:
        return tuple(item[0] for item in self._owned.values())

    def start(self, role: str, argv, *, environment: Mapping[str, str] | None = None) -> OwnedProcess:
        if role not in _ROLES or not isinstance(argv, (list, tuple)) or not argv:
            raise SupervisorError("UNOWNED_ROLE")
        child = self._popen(
            list(argv),
            env=None if environment is None else dict(environment),
            start_new_session=True,
        )
        pid = child.pid
        pgid, cmdline, start_time = _proc_values(pid)
        if pgid != pid or not cmdline or not start_time:
            # A PID is not signal authority.  Re-read once and signal only a
            # complete, self-led process group that is still this child.
            second_pgid, second_cmdline, second_start = _proc_values(pid)
            if (
                child.poll() is None
                and second_pgid == pid
                and second_cmdline
                and second_start
            ):
                try:
                    self._signal_group(second_pgid, signal.SIGKILL)
                except OSError:
                    pass
            self._reap_failed_start(child)
            raise SupervisorError("CHILD_IDENTITY")
        owned = OwnedProcess(self.batch_id, role, pid, pgid, cmdline, start_time)
        try:
            self._record_started(owned, poll=child.poll)
            self.write_manifest()
        except Exception:
            try:
                if self._identity_reader(pid) == owned:
                    self._signal_group(pgid, signal.SIGKILL)
            except OSError:
                pass
            self._reap_failed_start(child)
            self._owned.pop(pid, None)
            raise
        return owned

    @staticmethod
    def _reap_failed_start(child, timeout_s: float = 1.0) -> None:
        """Boundedly terminate/reap only the exact Popen child just created."""
        try:
            if child.poll() is None and hasattr(child, "terminate"):
                child.terminate()
            if hasattr(child, "wait"):
                child.wait(timeout=timeout_s)
        except (OSError, subprocess.TimeoutExpired):
            try:
                if child.poll() is None and hasattr(child, "kill"):
                    child.kill()
                if hasattr(child, "wait"):
                    child.wait(timeout=timeout_s)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _record_started(self, process: OwnedProcess, *, poll=lambda: None) -> None:
        """Record only a child proven to come from this supervisor's start path.

        Tests may seed this private boundary with fake identities; no public
        manifest/adoption API grants signal authority.
        """
        if not isinstance(process, OwnedProcess):
            raise SupervisorError("INCOMPLETE_MANIFEST")
        if process.batch_id != self.batch_id:
            raise SupervisorError("BATCH_MISMATCH")
        if process.role not in _ROLES:
            raise SupervisorError("UNOWNED_ROLE")
        if process.pid in self._owned and self._owned[process.pid][0] != process:
            raise SupervisorError("PID_REUSE")
        self._owned[process.pid] = (process, poll)

    def load_manifest(self, document) -> None:
        if type(document) is not dict or set(document) != {"schema_version", "batch_id", "processes"}:
            raise SupervisorError("MANIFEST_INVALID")
        if document["schema_version"] != 1 or document["batch_id"] != self.batch_id:
            raise SupervisorError("MANIFEST_INVALID")
        if not isinstance(document["processes"], list):
            raise SupervisorError("MANIFEST_INVALID")
        for value in document["processes"]:
            try:
                if type(value) is not dict or set(value) != {
                    "batch_id", "role", "pid", "pgid", "cmdline", "start_time"
                }:
                    raise TypeError
                OwnedProcess(**(value | {"cmdline": tuple(value["cmdline"])}))
            except (TypeError, SupervisorError) as error:
                raise SupervisorError("MANIFEST_INVALID") from error

    def write_manifest(self) -> None:
        if self.manifest_path is None:
            return
        document = {
            "schema_version": 1,
            "batch_id": self.batch_id,
            "processes": [asdict(process) for process in self.processes],
        }
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix="." + self.manifest_path.name + "-", dir=self.manifest_path.parent
        )
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, self.manifest_path)
            parent = os.open(self.manifest_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _confirm_identity(self, expected: OwnedProcess) -> None:
        actual = self._identity_reader(expected.pid)
        if actual is None:
            raise SupervisorError("OWNED_PROCESS_ABSENT")
        if actual != expected:
            raise SupervisorError("PID_REUSE_OR_IDENTITY_MISMATCH")

    def assert_healthy(self) -> None:
        for expected, poll in self._owned.values():
            code = poll()
            if code is not None:
                raise SupervisorError(f"EARLY_EXIT: {expected.role}: {code}")
            self._confirm_identity(expected)

    def wait_for_children(
        self, *, deadline_monotonic_s: float, role: str = "worker",
        health_role: str | None = "broker",
        health_recovery: Callable[[OwnedProcess, int], bool] | None = None,
    ) -> tuple[int, ...]:
        """Wait for one role while continuously proving its dependency healthy."""
        if isinstance(deadline_monotonic_s, bool) or not isinstance(
            deadline_monotonic_s, (int, float)
        ):
            raise SupervisorError("DEADLINE")
        if role not in _ROLES or health_role not in _ROLES | {None}:
            raise SupervisorError("UNOWNED_ROLE")
        codes = []
        while any(item[0].role == role for item in self._owned.values()):
            if time.monotonic() >= deadline_monotonic_s:
                raise SupervisorError("CHILD_DEADLINE")
            completed = []
            for pid, (expected, poll) in tuple(self._owned.items()):
                code = poll()
                if expected.role == health_role:
                    if code is not None:
                        if health_recovery is None:
                            raise SupervisorError(
                                f"EARLY_EXIT: {expected.role}: {code}"
                            )
                        try:
                            recovered = health_recovery(expected, int(code))
                        except Exception as error:
                            raise SupervisorError(
                                f"HEALTH_RECOVERY_FAILED: {expected.role}: {code}"
                            ) from error
                        replacements = tuple(
                            item
                            for item in self._owned.values()
                            if item[0].role == health_role
                        )
                        if (
                            recovered is not True
                            or pid in self._owned
                            or len(replacements) != 1
                            or replacements[0][0] == expected
                            or replacements[0][1]() is not None
                        ):
                            raise SupervisorError(
                                f"HEALTH_RECOVERY_FAILED: {expected.role}: {code}"
                            )
                        self._confirm_identity(replacements[0][0])
                        continue
                    self._confirm_identity(expected)
                    continue
                if expected.role != role:
                    continue
                if code is None:
                    self._confirm_identity(expected)
                    continue
                if self._group_members_reader(expected.pgid):
                    raise SupervisorError(
                        f"OWNED_GROUP_SURVIVORS: {expected.role}"
                    )
                codes.append(int(code))
                completed.append(pid)
            for pid in completed:
                self._owned.pop(pid, None)
            if not completed:
                time.sleep(0.01)
        self.write_manifest()
        return tuple(codes)

    def retire_owned(
        self,
        expected: OwnedProcess,
        *,
        term_timeout_s: float = 5.0,
        kill_timeout_s: float = 2.0,
    ) -> bool:
        """Retire one exited child and any survivors of its exact owned PGID."""
        current = self._owned.get(getattr(expected, "pid", None))
        if current is None or current[0] != expected:
            raise SupervisorError("UNOWNED_PROCESS")
        poll = current[1]
        if poll() is None:
            raise SupervisorError("OWNED_PROCESS_STILL_RUNNING")
        members = self._group_members_reader(expected.pgid)
        try:
            if members:
                self._signal_group(expected.pgid, signal.SIGTERM)
                deadline = time.monotonic() + term_timeout_s
                while (
                    self._group_members_reader(expected.pgid)
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
            if self._group_members_reader(expected.pgid):
                self._signal_group(expected.pgid, signal.SIGKILL)
                deadline = time.monotonic() + kill_timeout_s
                while (
                    self._group_members_reader(expected.pgid)
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
        except OSError:
            return False
        if self._group_members_reader(expected.pgid):
            return False
        self._owned.pop(expected.pid)
        self.write_manifest()
        return True

    def _wait_group_stopped(self, expected, poll, timeout_s):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            code = poll()
            if code is not None:
                return (
                    self._identity_reader(expected.pid) is None
                    and not self._group_members_reader(expected.pgid)
                )
            actual = self._identity_reader(expected.pid)
            if actual is None:
                # The process may be between /proc teardown and child reaping.
                # Signal authority is released only after both observations agree.
                time.sleep(0.01)
                continue
            if actual != expected:
                return False
            time.sleep(0.01)
        return False

    def shutdown(
        self,
        *,
        stop_leases=lambda: True,
        cancel_goal=lambda: True,
        confirm_goal_cancelled=lambda: True,
        request_recovery=lambda: True,
        wait_group=None,
        interrupt_timeout_s: float = 5.0,
        term_timeout_s: float = 5.0,
        kill_timeout_s: float = 2.0,
    ) -> bool:
        cleanup_ok = True
        for action in (stop_leases, cancel_goal, confirm_goal_cancelled, request_recovery):
            try:
                cleanup_ok = action() is True and cleanup_ok
            except Exception:
                cleanup_ok = False
        stopped_pids = []
        for expected, poll in tuple(self._owned.values()):
            if poll() is not None:
                members = self._group_members_reader(expected.pgid)
                if not members:
                    stopped_pids.append(expected.pid)
                    continue
                # This group was created and recorded by this supervisor.  The
                # leader may already be reaped, but exact /proc membership keeps
                # signal authority until every member has exited.
                try:
                    first_signal = (
                        signal.SIGINT if expected.role == "worker" else signal.SIGTERM
                    )
                    self._signal_group(expected.pgid, first_signal)
                    deadline = time.monotonic() + (
                        interrupt_timeout_s
                        if expected.role == "worker" else term_timeout_s
                    )
                    while (
                        self._group_members_reader(expected.pgid)
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    if self._group_members_reader(expected.pgid):
                        self._signal_group(expected.pgid, signal.SIGKILL)
                        deadline = time.monotonic() + kill_timeout_s
                        while (
                            self._group_members_reader(expected.pgid)
                            and time.monotonic() < deadline
                        ):
                            time.sleep(0.01)
                    if self._group_members_reader(expected.pgid):
                        cleanup_ok = False
                    else:
                        stopped_pids.append(expected.pid)
                except OSError:
                    cleanup_ok = False
                continue
            stopped = False
            if expected.role == "worker":
                try:
                    self._confirm_identity(expected)
                    self._signal_group(expected.pgid, signal.SIGINT)
                    stopped = (
                        self._wait_group_stopped(expected, poll, interrupt_timeout_s)
                        if wait_group is None
                        else (
                            wait_group(expected, interrupt_timeout_s) is True
                            and not self._group_members_reader(expected.pgid)
                        )
                    )
                except (OSError, SupervisorError):
                    cleanup_ok = False
                    continue
                except Exception:
                    stopped = False
            if stopped:
                stopped_pids.append(expected.pid)
                continue
            try:
                self._confirm_identity(expected)
                self._signal_group(expected.pgid, signal.SIGTERM)
                stopped = (
                    self._wait_group_stopped(expected, poll, term_timeout_s)
                    if wait_group is None
                    else (
                        wait_group(expected, term_timeout_s) is True
                        and not self._group_members_reader(expected.pgid)
                    )
                )
            except (OSError, SupervisorError):
                cleanup_ok = False
                continue
            except Exception:
                stopped = False
            if not stopped:
                try:
                    self._confirm_identity(expected)
                    self._signal_group(expected.pgid, signal.SIGKILL)
                except (OSError, SupervisorError):
                    cleanup_ok = False
                    continue
                try:
                    stopped = (
                        self._wait_group_stopped(expected, poll, kill_timeout_s)
                        if wait_group is None
                        else (
                            wait_group(expected, kill_timeout_s) is True
                            and not self._group_members_reader(expected.pgid)
                        )
                    )
                except Exception:
                    stopped = False
            cleanup_ok = stopped and cleanup_ok
            if stopped:
                stopped_pids.append(expected.pid)
        for pid in stopped_pids:
            self._owned.pop(pid, None)
        try:
            self.write_manifest()
        except OSError:
            cleanup_ok = False
        return cleanup_ok
