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
from .owner_records import (
    OwnerRecordError,
    OwnerSpawnRecorder,
    owner_context_from_environment,
    spawner_token_from_environment,
)
from .runtime_closure import (
    RuntimeAttestation,
    RuntimeClosureError,
    RuntimeClosureIdentity,
    RunBinding,
    build_runtime_attestation,
    default_loaded_image_probe,
    read_process_birth_identity,
    verify_runtime_closure,
)


#: The stack's role vocabulary is not the owner-record vocabulary: these two stack roles name a
#: station. Any other role stays un-recorded rather than being given an invented record role.
_OWNER_ROLE_BY_STACK_ROLE = {"task-station": "STATION", "station": "STATION"}


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
    closure: RuntimeClosureIdentity | None = None
    run_binding: RunBinding | None = None
    install_root: Path | None = None
    forbidden_roots: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if not self.session_id or not self.processes:
            raise ValueError("stack session and process specs are required")
        if not self.evidence_root.is_absolute():
            raise ValueError("stack evidence root must be absolute")
        if len({spec.role for spec in self.processes}) != len(self.processes):
            raise ValueError("stack process roles must be unique")
        if (self.closure is None) != (self.run_binding is None):
            raise ValueError("stack closure and run binding must be provided together")
        if self.closure is None:
            if self.install_root is not None or self.forbidden_roots:
                raise ValueError("install root requires an expected runtime closure")
            return
        if not isinstance(self.closure, RuntimeClosureIdentity):
            raise ValueError("stack closure must be a RuntimeClosureIdentity")
        if not isinstance(self.run_binding, RunBinding):
            raise ValueError("stack run binding must be a RunBinding")
        if self.install_root is None or not Path(self.install_root).is_absolute():
            raise ValueError("stack install root must be absolute when a closure is bound")
        if not isinstance(self.forbidden_roots, tuple):
            raise ValueError("stack forbidden roots must be a tuple of absolute paths")
        if self.run_binding.evidence_root != self.evidence_root:
            raise ValueError("stack evidence root must match the run binding")
        if self.run_binding.station_session_id != self.session_id:
            raise ValueError("stack session id must match the run binding")


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
        birth_identity_probe: Callable[[int], int] | None = None,
        owner_environment: Mapping[str, str] | None = None,
        owner_identity_reader: Callable[[int], tuple[int, int] | None] | None = None,
        owner_confirm_deadline_s: float = 2.0,
    ) -> None:
        self._popen = popen
        self._killpg = killpg
        self._identity_probe = identity_probe
        self._interrupt_timeout_s = interrupt_timeout_s
        self._terminate_timeout_s = terminate_timeout_s
        self._strict_identity = strict_identity
        self._birth_identity_probe = birth_identity_probe
        #: The environment the owner-record context is read from. ``None`` means this process's
        #: own environment, which is what a spawned Worker inherited from its campaign.
        self._owner_environment = owner_environment
        self._owner_identity_reader = owner_identity_reader
        self._owner_confirm_deadline_s = owner_confirm_deadline_s
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
        birth_identity_probe: Callable[[int], int] | None = None,
    ) -> OwnedProcessIdentity:
        if any(identity.role == spec.role for identity, _child in self._children):
            raise RuntimeError(f"owned process role already exists: {spec.role}")
        merged_environment = dict(os.environ)
        if environment is not None:
            merged_environment.update(environment)
        # The STATION intent is written here, by the boundary that calls Popen, and only here:
        # `macos_w2_worker` owns the station but writes no record of its own, so one station spawn
        # produces exactly one intent.
        recorder = self._owner_recorder(spec)
        if recorder is not None:
            merged_environment = recorder.child_environment(merged_environment)
        try:
            child = self._popen(
                list(spec.argv),
                start_new_session=True,
                env=merged_environment,
            )
        except BaseException as error:
            self._abandon_owner_record(recorder, error)
            raise
        try:
            probe = birth_identity_probe or self._birth_identity_probe
            if self._strict_identity:
                pgid, cmdline, start_time_ticks = self._identity_probe(int(child.pid))
            elif probe is not None:
                pgid, cmdline, start_time_ticks = (
                    int(child.pid),
                    spec.argv,
                    int(probe(int(child.pid))),
                )
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
            if recorder is not None:
                recorder.confirm(int(child.pid), **self._owner_confirm_kwargs())
        except BaseException as error:
            self._abandon_owner_record(recorder, error)
            if child.poll() is None:
                try:
                    self._killpg(int(child.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            raise
        self._children.append((identity, child))
        return identity

    # -- owner records ---------------------------------------------------------------------

    def _owner_recorder(self, spec: StackProcessSpec) -> OwnerSpawnRecorder | None:
        """The durable intent for this spawn, written before ``Popen``; ``None`` when inert."""

        role = _OWNER_ROLE_BY_STACK_ROLE.get(spec.role)
        if role is None:
            return None
        environment = os.environ if self._owner_environment is None else self._owner_environment
        context = owner_context_from_environment(environment)
        if context is None:
            return None
        return OwnerSpawnRecorder.begin(
            context=context,
            role=role,
            argv=spec.argv,
            # The child's parent is this spawner, so the token this process was given by its own
            # parent is what the child records and receives as SO101_OWNER_PARENT_TOKEN.
            parent_spawn_token=spawner_token_from_environment(environment),
            own_session=True,
        )

    def _owner_confirm_kwargs(self) -> dict:
        kwargs: dict = {"deadline_s": self._owner_confirm_deadline_s}
        if self._owner_identity_reader is not None:
            kwargs["identity_reader"] = self._owner_identity_reader
        return kwargs

    @staticmethod
    def _abandon_owner_record(recorder: OwnerSpawnRecorder | None, error: BaseException) -> None:
        """Mark the record of a spawn that failed. The original failure must still propagate."""

        if recorder is None:
            return
        reason = error.code if isinstance(error, OwnerRecordError) else "SPAWN_FAILED"
        try:
            recorder.abandon(reason)
        except (OwnerRecordError, OSError):
            pass

    def _identity_status(self, identity: OwnedProcessIdentity) -> str:
        if not self._strict_identity:
            return "match"
        try:
            pgid, cmdline, start_time_ticks = self._identity_probe(identity.pid)
        except (FileNotFoundError, ProcessLookupError):
            return "absent"
        except OSError:
            return "unknown"
        matches = (
            pgid == identity.pgid
            and tuple(cmdline) == identity.cmdline
            and start_time_ticks == identity.start_time_ticks
        )
        return "match" if matches else "changed"

    def shutdown(self) -> None:
        failures = []
        survivors = []
        for identity, child in reversed(self._children):
            if child.poll() is not None:
                continue
            identity_status = self._identity_status(identity)
            if identity_status == "absent":
                continue
            if identity_status != "match":
                survivors.append((identity, child))
                failures.append(
                    (
                        identity.role,
                        RuntimeError(
                            "owned process identity changed"
                            if identity_status == "changed"
                            else "owned process identity unavailable"
                        ),
                    )
                )
                continue
            try:
                self._killpg(identity.pgid, signal.SIGINT)
                child.wait(timeout=self._interrupt_timeout_s)
            except subprocess.TimeoutExpired:
                identity_status = self._identity_status(identity)
                if identity_status == "absent":
                    continue
                if identity_status != "match":
                    survivors.append((identity, child))
                    failures.append(
                        (
                            identity.role,
                            RuntimeError(
                                "owned process identity changed"
                                if identity_status == "changed"
                                else "owned process identity unavailable"
                            ),
                        )
                    )
                    continue
                try:
                    self._killpg(identity.pgid, signal.SIGTERM)
                    child.wait(timeout=self._terminate_timeout_s)
                except BaseException as error:
                    survivors.append((identity, child))
                    failures.append((identity.role, error))
            except ProcessLookupError:
                continue
            except BaseException as error:
                survivors.append((identity, child))
                failures.append((identity.role, error))
        self._children = list(reversed(survivors))
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
        birth_identity_probe: Callable[[int], int] | None = None,
        loaded_image_probe: Callable[[int], Sequence[Path]] | None = None,
        owner_environment: Mapping[str, str] | None = None,
        owner_identity_reader: Callable[[int], tuple[int, int] | None] | None = None,
        owner_confirm_deadline_s: float = 2.0,
    ) -> None:
        self._birth_identity_probe = birth_identity_probe
        self._loaded_image_probe = loaded_image_probe or default_loaded_image_probe
        self._group = OwnedProcessGroup(
            popen=popen,
            killpg=killpg,
            interrupt_timeout_s=interrupt_timeout_s,
            terminate_timeout_s=terminate_timeout_s,
            strict_identity=False,
            birth_identity_probe=birth_identity_probe,
            owner_environment=owner_environment,
            owner_identity_reader=owner_identity_reader,
            owner_confirm_deadline_s=owner_confirm_deadline_s,
        )
        self._attestation: RuntimeAttestation | None = None

    @property
    def started(self) -> bool:
        return self._group.started

    @property
    def attestation(self) -> RuntimeAttestation | None:
        """The read-back attestation of the last successful start, if one was produced."""

        return self._attestation

    def start(
        self,
        config: PersistentStackConfig,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if self._group.started:
            raise RuntimeError("persistent stack is already started")
        merged_environment = dict(os.environ)
        if environment is not None:
            merged_environment.update(environment)
        if config.closure is not None:
            verify_runtime_closure(
                config.closure,
                install_root=config.install_root,
                source_commit=config.closure.source_commit,
                mujoco_ros2_control_commit=config.closure.mujoco_ros2_control_commit,
                environment=merged_environment,
                forbidden_roots=config.forbidden_roots,
            )
        try:
            for spec in config.processes:
                self._group.start(
                    spec,
                    environment=environment,
                    birth_identity_probe=(
                        (self._birth_identity_probe or read_process_birth_identity)
                        if config.closure is not None
                        else None
                    ),
                )
        except BaseException:
            self.shutdown()
            raise
        if config.closure is None:
            return
        try:
            self._attestation = self._attest(config, merged_environment)
        except BaseException:
            self.shutdown()
            raise

    def _attest(
        self, config: PersistentStackConfig, environment: Mapping[str, str]
    ) -> RuntimeAttestation:
        raw_domain = str(environment.get("ROS_DOMAIN_ID", "")).strip()
        if not raw_domain.isdigit():
            raise RuntimeClosureError(
                "ATTESTATION_ROS_DOMAIN_UNAVAILABLE",
                "ROS_DOMAIN_ID must be set for the station run",
            )
        images: list[Path] = []
        for identity in self._group.manifest.processes:
            images.extend(self._loaded_image_probe(identity.pid))
        return build_runtime_attestation(
            closure=config.closure,
            run_binding=config.run_binding,
            install_root=config.install_root,
            process_identities=self._group.manifest.processes,
            loaded_images=tuple(images),
            observed_ros_domain_id=int(raw_domain),
        )

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
    closure: RuntimeClosureIdentity | None = None,
    run_binding: RunBinding | None = None,
    install_root: Path | None = None,
    forbidden_roots: tuple[Path, ...] = (),
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
        closure=closure,
        run_binding=run_binding,
        install_root=install_root,
        forbidden_roots=forbidden_roots,
    )
