"""Owned persistent process groups for the visible MuJoCo task station."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from ..application.qualification_stack import ros2_command


@dataclass(frozen=True, slots=True)
class StackProcessSpec:
    role: str
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.role or not self.argv:
            raise ValueError("stack process role and argv are required")


@dataclass(frozen=True, slots=True)
class PersistentStackConfig:
    session_id: str
    headless: bool
    evidence_root: Path
    processes: tuple[StackProcessSpec, ...]

    def __post_init__(self) -> None:
        if not self.session_id or not self.processes:
            raise ValueError("stack session and process specs are required")
        if not self.evidence_root.is_absolute():
            raise ValueError("stack evidence root must be absolute")
        if len({spec.role for spec in self.processes}) != len(self.processes):
            raise ValueError("stack process roles must be unique")


@dataclass(frozen=True, slots=True)
class OwnedProcessIdentity:
    """Stable Linux process identity used to prevent PID-reuse cleanup."""

    role: str
    pid: int
    pgid: int
    cmdline: tuple[str, ...]
    start_time_ticks: int

    def __post_init__(self) -> None:
        if (
            not self.role
            or self.pid <= 0
            or self.pgid <= 0
            or not self.cmdline
            or self.start_time_ticks <= 0
        ):
            raise ValueError("complete owned process identity is required")


@dataclass(frozen=True, slots=True)
class OwnedProcessManifest:
    """Exact processes one owner is permitted to signal."""

    processes: tuple[OwnedProcessIdentity, ...]


def _linux_process_identity(pid: int) -> tuple[int, tuple[str, ...], int]:
    stat_fields = (
        Path(f"/proc/{pid}/stat")
        .read_text(encoding="utf-8")
        .rsplit(")", 1)[1]
        .split()
    )
    cmdline = tuple(
        value.decode("utf-8", errors="surrogateescape")
        for value in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if value
    )
    if len(stat_fields) <= 19 or not cmdline:
        raise RuntimeError(f"incomplete process identity for PID {pid}")
    return int(stat_fields[2]), cmdline, int(stat_fields[19])


class OwnedProcessGroup:
    """Start and stop only process groups whose full identity is unchanged."""

    def __init__(
        self,
        *,
        popen: Callable = subprocess.Popen,
        killpg: Callable[[int, signal.Signals], None] = os.killpg,
        identity_probe: Callable[
            [int], tuple[int, tuple[str, ...], int]
        ] = _linux_process_identity,
        interrupt_timeout_s: float = 20.0,
        terminate_timeout_s: float = 5.0,
        strict_identity: bool = True,
    ) -> None:
        self._popen = popen
        self._killpg = killpg
        self._identity_probe = identity_probe
        self._interrupt_timeout_s = interrupt_timeout_s
        self._terminate_timeout_s = terminate_timeout_s
        self._strict_identity = strict_identity
        self._children: list[tuple[OwnedProcessIdentity, object]] = []

    @property
    def manifest(self) -> OwnedProcessManifest:
        return OwnedProcessManifest(
            tuple(identity for identity, _child in self._children)
        )

    @property
    def started(self) -> bool:
        return bool(self._children)

    def start(
        self,
        spec: StackProcessSpec,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> OwnedProcessIdentity:
        if any(identity.role == spec.role for identity, _child in self._children):
            raise RuntimeError(f"owned process role already exists: {spec.role}")
        merged_environment = dict(os.environ)
        if environment is not None:
            merged_environment.update(environment)
        child = self._popen(
            list(spec.argv),
            start_new_session=True,
            env=merged_environment,
        )
        try:
            if self._strict_identity:
                pgid, cmdline, start_time_ticks = self._identity_probe(int(child.pid))
            else:
                pgid, cmdline, start_time_ticks = (
                    int(child.pid),
                    spec.argv,
                    time.monotonic_ns(),
                )
            identity = OwnedProcessIdentity(
                spec.role,
                int(child.pid),
                int(pgid),
                tuple(cmdline),
                int(start_time_ticks),
            )
        except BaseException:
            if child.poll() is None:
                try:
                    self._killpg(int(child.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            raise
        self._children.append((identity, child))
        return identity

    def _identity_is_current(self, identity: OwnedProcessIdentity) -> bool:
        if not self._strict_identity:
            return True
        try:
            pgid, cmdline, start_time_ticks = self._identity_probe(identity.pid)
        except (OSError, ProcessLookupError):
            return False
        return (
            pgid == identity.pgid
            and tuple(cmdline) == identity.cmdline
            and start_time_ticks == identity.start_time_ticks
        )

    def shutdown(self) -> None:
        failures = []
        for identity, child in reversed(self._children):
            if child.poll() is not None:
                continue
            if not self._identity_is_current(identity):
                failures.append((identity.role, RuntimeError("owned process identity changed")))
                continue
            try:
                self._killpg(identity.pgid, signal.SIGINT)
                child.wait(timeout=self._interrupt_timeout_s)
            except subprocess.TimeoutExpired:
                if not self._identity_is_current(identity):
                    failures.append(
                        (identity.role, RuntimeError("owned process identity changed"))
                    )
                    continue
                try:
                    self._killpg(identity.pgid, signal.SIGTERM)
                    child.wait(timeout=self._terminate_timeout_s)
                except BaseException as error:
                    failures.append((identity.role, error))
            except ProcessLookupError:
                continue
            except BaseException as error:
                failures.append((identity.role, error))
        self._children.clear()
        if failures:
            raise RuntimeError(
                "; ".join(f"{role}: {error}" for role, error in failures)
            )


class PersistentTaskStack:
    def __init__(
        self,
        *,
        popen: Callable = subprocess.Popen,
        killpg: Callable[[int, signal.Signals], None] = os.killpg,
        interrupt_timeout_s: float = 20.0,
        terminate_timeout_s: float = 5.0,
    ) -> None:
        self._group = OwnedProcessGroup(
            popen=popen,
            killpg=killpg,
            interrupt_timeout_s=interrupt_timeout_s,
            terminate_timeout_s=terminate_timeout_s,
            strict_identity=False,
        )

    @property
    def started(self) -> bool:
        return self._group.started

    def start(
        self,
        config: PersistentStackConfig,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if self._group.started:
            raise RuntimeError("persistent stack is already started")
        try:
            for spec in config.processes:
                self._group.start(spec, environment=environment)
        except BaseException:
            self.shutdown()
            raise

    def process_pid(self, role: str) -> int:
        matches = [
            identity.pid
            for identity in self._group.manifest.processes
            if identity.role == role
        ]
        if len(matches) != 1:
            raise RuntimeError(f"stack role does not resolve to one process: {role}")
        return matches[0]

    def shutdown(self) -> None:
        self._group.shutdown()

    def wait_for_descendant(
        self,
        pattern: str,
        timeout_s: float,
        *,
        process_table: Callable[[], Sequence[tuple[int, int, str]]] | None = None,
    ) -> int:
        roots = {identity.pid for identity in self._group.manifest.processes}
        process_table = process_table or _process_table
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            rows = tuple(process_table())
            parents = {pid: parent for pid, parent, _command in rows}
            matches = []
            for pid, _parent, command in rows:
                current = pid
                ancestry = set()
                while current in parents and current not in ancestry:
                    ancestry.add(current)
                    current = parents[current]
                    if current in roots:
                        if pattern in command:
                            matches.append(pid)
                        break
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise RuntimeError(f"ambiguous stack descendant for {pattern}")
            time.sleep(0.1)
        raise TimeoutError(f"stack descendant unavailable: {pattern}")


def _process_table() -> tuple[tuple[int, int, str], ...]:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,args="],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = []
    for line in completed.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) == 3:
            rows.append((int(fields[0]), int(fields[1]), fields[2]))
    return tuple(rows)


def default_task_station_config(
    session_id: str,
    evidence_root: Path,
    *,
    include_teleop: bool = False,
) -> PersistentStackConfig:
    command = ros2_command(
        "launch",
        "so101_demo_py",
        "so101_mujoco_task_station.launch.py",
        "headless:=false",
        f"session_id:={session_id}",
        f"task_evidence_root:={evidence_root}",
        f"include_teleop:={'true' if include_teleop else 'false'}",
    )
    return PersistentStackConfig(
        session_id,
        False,
        evidence_root,
        (StackProcessSpec("task-station", tuple(command)),),
    )
