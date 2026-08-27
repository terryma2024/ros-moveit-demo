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
        if self.headless:
            raise ValueError("the macOS task station requires headless=false")
        if not self.evidence_root.is_absolute():
            raise ValueError("stack evidence root must be absolute")
        if len({spec.role for spec in self.processes}) != len(self.processes):
            raise ValueError("stack process roles must be unique")


class PersistentTaskStack:
    def __init__(
        self,
        *,
        popen: Callable = subprocess.Popen,
        killpg: Callable[[int, signal.Signals], None] = os.killpg,
        interrupt_timeout_s: float = 20.0,
        terminate_timeout_s: float = 5.0,
    ) -> None:
        self._popen = popen
        self._killpg = killpg
        self._interrupt_timeout_s = interrupt_timeout_s
        self._terminate_timeout_s = terminate_timeout_s
        self._children: list[tuple[str, object]] = []

    @property
    def started(self) -> bool:
        return bool(self._children)

    def start(
        self,
        config: PersistentStackConfig,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if self._children:
            raise RuntimeError("persistent stack is already started")
        merged_environment = dict(os.environ)
        if environment is not None:
            merged_environment.update(environment)
        try:
            for spec in config.processes:
                child = self._popen(
                    list(spec.argv),
                    start_new_session=True,
                    env=merged_environment,
                )
                self._children.append((spec.role, child))
        except BaseException:
            self.shutdown()
            raise

    def process_pid(self, role: str) -> int:
        matches = [int(child.pid) for child_role, child in self._children if child_role == role]
        if len(matches) != 1:
            raise RuntimeError(f"stack role does not resolve to one process: {role}")
        return matches[0]

    def shutdown(self) -> None:
        failures = []
        for role, child in reversed(self._children):
            if child.poll() is not None:
                continue
            try:
                self._killpg(int(child.pid), signal.SIGINT)
                child.wait(timeout=self._interrupt_timeout_s)
            except subprocess.TimeoutExpired:
                try:
                    self._killpg(int(child.pid), signal.SIGTERM)
                    child.wait(timeout=self._terminate_timeout_s)
                except BaseException as error:
                    failures.append((role, error))
            except ProcessLookupError:
                continue
            except BaseException as error:
                failures.append((role, error))
        self._children.clear()
        if failures:
            raise RuntimeError(
                "; ".join(f"{role}: {error}" for role, error in failures)
            )

    def wait_for_descendant(
        self,
        pattern: str,
        timeout_s: float,
        *,
        process_table: Callable[[], Sequence[tuple[int, int, str]]] | None = None,
    ) -> int:
        roots = {int(child.pid) for _, child in self._children}
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
