"""Fail-closed host admission and isolated Worker resource allocation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from types import MappingProxyType
from typing import Mapping
import uuid

from .contracts import load_parallel_runtime_config, ParallelRuntimeConfig


_DEFAULT_WORKER_COUNT = 2
_NOT_APPLICABLE = 'not_applicable'
_UNIX_SOCKET_PATH_MAX_BYTES = 107
_MEM_AVAILABLE = re.compile(r'^MemAvailable:[ \t]+([0-9]+)[ \t]+kB$')
_BASE_ENVIRONMENT_ALLOWLIST = (
    'PATH',
    'AMENT_PREFIX_PATH',
    'COLCON_PREFIX_PATH',
    'LD_LIBRARY_PATH',
    'PYTHONPATH',
    'RMW_IMPLEMENTATION',
)


class ResourceAllocationError(ValueError):
    """A Worker resource allocation or admission check failed."""

    def __init__(self, message: str, *, admission=None) -> None:
        super().__init__(message)
        self.admission = admission


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """Host resources observed at admission time."""

    logical_cpu_count: int
    available_ram_gib: float
    gpu_free_gib: float

    def to_dict(self) -> dict[str, int | float]:
        """Return a JSON-safe snapshot."""
        return {
            'logical_cpu_count': self.logical_cpu_count,
            'available_ram_gib': self.available_ram_gib,
            'gpu_free_gib': self.gpu_free_gib,
        }


@dataclass(frozen=True, slots=True)
class ResourceThresholds:
    """Frozen minimum host resources for the exact requested Worker count."""

    logical_cpu_count: int
    available_ram_gib: float
    gpu_free_gib: float

    def to_dict(self) -> dict[str, int | float]:
        """Return JSON-safe threshold values."""
        return {
            'logical_cpu_count': self.logical_cpu_count,
            'available_ram_gib': self.available_ram_gib,
            'gpu_free_gib': self.gpu_free_gib,
        }


@dataclass(frozen=True, slots=True)
class ResourceAdmission:
    """Immutable admission decision and the evidence used to make it."""

    admitted: bool
    observed: ResourceSnapshot
    required: ResourceThresholds
    required_live_headroom_ratio: float
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the complete JSON-safe admission record."""
        return {
            'admitted': self.admitted,
            'observed': self.observed.to_dict(),
            'required': self.required.to_dict(),
            'required_live_headroom_ratio': self.required_live_headroom_ratio,
            'failures': list(self.failures),
        }


@dataclass(frozen=True, slots=True)
class WorkerResources:
    """Stable resources assigned to one Worker slot and process generation."""

    worker_id: str
    slot_index: int
    generation: int
    ros_domain_id: int
    simulation_port: str
    bridge_port: str
    gz_partition: str
    session_id: str
    controller_namespace: str
    ros_home: Path
    ros_log_dir: Path
    temp_dir: Path
    socket_namespace: Path
    socket_path: Path
    worker_root: Path
    environment: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'environment', MappingProxyType(dict(self.environment)))

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe Worker resource document."""
        return {
            'worker_id': self.worker_id,
            'slot_index': self.slot_index,
            'generation': self.generation,
            'ros_domain_id': self.ros_domain_id,
            'simulation_port': self.simulation_port,
            'bridge_port': self.bridge_port,
            'gz_partition': self.gz_partition,
            'session_id': self.session_id,
            'controller_namespace': self.controller_namespace,
            'ros_home': str(self.ros_home),
            'ros_log_dir': str(self.ros_log_dir),
            'temp_dir': str(self.temp_dir),
            'socket_namespace': str(self.socket_namespace),
            'socket_path': str(self.socket_path),
            'worker_root': str(self.worker_root),
            'environment': dict(self.environment),
        }


@dataclass(frozen=True, slots=True)
class ResourceManifest:
    """Exact admitted Worker count and all resulting isolated resources."""

    schema_version: int
    mode: str
    backend: str
    evidence_root: Path
    requested_worker_count: int
    worker_count: int
    admission: ResourceAdmission
    workers: tuple[WorkerResources, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe manifest without losing the requested count."""
        return {
            'schema_version': self.schema_version,
            'mode': self.mode,
            'backend': self.backend,
            'evidence_root': str(self.evidence_root),
            'requested_worker_count': self.requested_worker_count,
            'worker_count': self.worker_count,
            'admission': self.admission.to_dict(),
            'workers': [worker.to_dict() for worker in self.workers],
        }


class SystemResourceProbe:
    """Read-only Linux probes used by ai-station dry admission."""

    def __init__(self, *, proc_root: Path = Path('/proc')) -> None:
        self._proc_root = Path(proc_root)

    def snapshot(self) -> ResourceSnapshot:
        """Measure logical CPUs, available RAM and free NVIDIA GPU memory."""
        logical_cpu_count = os.cpu_count()
        if logical_cpu_count is None:
            raise ResourceAllocationError('PROBE_FAILED: logical CPU count unavailable')
        available_ram_gib = self._available_ram_gib()
        try:
            result = subprocess.run(
                [
                    'nvidia-smi',
                    '--query-gpu=memory.free',
                    '--format=csv,noheader,nounits',
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            free_mib = [float(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise ResourceAllocationError('PROBE_FAILED: NVIDIA GPU memory') from error
        if not free_mib:
            raise ResourceAllocationError('PROBE_FAILED: NVIDIA GPU memory unavailable')
        return ResourceSnapshot(
            logical_cpu_count=logical_cpu_count,
            available_ram_gib=available_ram_gib,
            gpu_free_gib=min(free_mib) / 1024.0,
        )

    def _available_ram_gib(self) -> float:
        try:
            lines = (self._proc_root / 'meminfo').read_text(encoding='ascii').splitlines()
        except (OSError, UnicodeError) as error:
            raise ResourceAllocationError('PROBE_FAILED: MemAvailable read') from error
        candidates = [line for line in lines if line.startswith('MemAvailable:')]
        if len(candidates) != 1:
            raise ResourceAllocationError('PROBE_FAILED: MemAvailable count')
        match = _MEM_AVAILABLE.fullmatch(candidates[0])
        if match is None:
            raise ResourceAllocationError('PROBE_FAILED: MemAvailable format')
        available_ram_gib = int(match.group(1)) / 1024**2
        if not math.isfinite(available_ram_gib) or available_ram_gib < 0:
            raise ResourceAllocationError('PROBE_FAILED: MemAvailable value')
        return available_ram_gib

    def ros_domain_in_use(self, domain_id: int) -> bool:
        """Detect a live process whose environment already claims a domain."""
        if not self._proc_root.is_dir():
            raise ResourceAllocationError('PROBE_FAILED: proc filesystem unavailable')
        expected = str(domain_id).encode('ascii')
        for process in self._proc_root.iterdir():
            if not process.name.isdigit() or int(process.name) == os.getpid():
                continue
            try:
                entries = (process / 'environ').read_bytes().split(b'\0')
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
            if b'ROS_DOMAIN_ID=' + expected in entries:
                return True
        return False

    def socket_in_use(self, path: Path) -> bool:
        """Treat every existing filesystem object as a socket reservation."""
        return os.path.lexists(path)


class WorkerResourceAllocator:
    """Allocate one private resource set for every requested stable slot."""

    def __init__(
        self,
        config: ParallelRuntimeConfig,
        evidence_root: Path,
        *,
        probe=None,
        base_environment: Mapping[str, str] | None = None,
    ) -> None:
        if not isinstance(config, ParallelRuntimeConfig):
            raise ResourceAllocationError('CONFIG')
        raw_root = str(evidence_root)
        root = Path(evidence_root)
        if (
            not root.is_absolute()
            or '\x00' in raw_root
            or any(part in {'.', '..'} for part in raw_root.split('/'))
        ):
            raise ResourceAllocationError('EVIDENCE_ROOT')
        self.config = config
        self.evidence_root = root
        self.probe = probe if probe is not None else SystemResourceProbe()
        source_environment = os.environ if base_environment is None else base_environment
        if not isinstance(source_environment, Mapping):
            raise ResourceAllocationError('BASE_ENVIRONMENT')
        self.base_environment = dict(source_environment)
        self._manifest: ResourceManifest | None = None
        self._workers: dict[str, WorkerResources] = {}

    @property
    def manifest(self) -> ResourceManifest | None:
        """Return the current immutable manifest, including replacements."""
        return self._manifest

    def allocate(self, worker_count: int | None = None) -> ResourceManifest:
        """Admit and allocate exactly the requested count; never downgrade it."""
        if self._manifest is not None:
            raise ResourceAllocationError('ALREADY_ALLOCATED')
        requested = _DEFAULT_WORKER_COUNT if worker_count is None else worker_count
        if (
            type(requested) is not int
            or requested <= 0
            or requested > self.config.max_worker_count
        ):
            raise ResourceAllocationError('WORKER_COUNT')
        if len(self.config.ros_domain_ids) < requested:
            raise ResourceAllocationError('ROS_DOMAIN_IDS')

        observed = self._probe_snapshot()
        required = ResourceThresholds(
            logical_cpu_count=self.config.min_logical_cpu_per_worker * requested,
            available_ram_gib=float(
                self.config.available_ram_base_gib
                + self.config.available_ram_per_worker_gib * requested
            ),
            gpu_free_gib=float(self.config.min_available_gpu_gib),
        )
        failures = _resource_failures(observed, required)
        admission = ResourceAdmission(
            admitted=not failures,
            observed=observed,
            required=required,
            required_live_headroom_ratio=self.config.required_live_headroom_ratio,
            failures=failures,
        )
        if failures:
            raise ResourceAllocationError(', '.join(failures), admission=admission)

        paths = tuple(self._paths(slot + 1) for slot in range(requested))
        self._preflight(paths)
        self._create_directories(paths)
        workers = tuple(
            self._worker(slot + 1, paths[slot], generation=1) for slot in range(requested)
        )
        self._workers = {worker.worker_id: worker for worker in workers}
        self._manifest = ResourceManifest(
            schema_version=1,
            mode='dry_run',
            backend=self.config.backend,
            evidence_root=self.evidence_root,
            requested_worker_count=requested,
            worker_count=requested,
            admission=admission,
            workers=workers,
        )
        return self._manifest

    def replace(self, worker_id: str, *, expected_generation: int) -> WorkerResources:
        """Reuse one stable slot while fencing it with the next generation."""
        if type(expected_generation) is not int or expected_generation <= 0:
            raise ResourceAllocationError('GENERATION')
        try:
            current = self._workers[worker_id]
        except (KeyError, TypeError) as error:
            raise ResourceAllocationError('UNKNOWN_WORKER') from error
        if current.generation != expected_generation:
            raise ResourceAllocationError('GENERATION_MISMATCH')
        generation = current.generation + 1
        session_id = _session_id(current.worker_id, generation)
        environment = dict(current.environment)
        environment['SO101_WORKER_GENERATION'] = str(generation)
        environment['SO101_SESSION_ID'] = session_id
        replacement = replace(
            current,
            generation=generation,
            session_id=session_id,
            environment=environment,
        )
        self._workers[worker_id] = replacement
        if self._manifest is not None:
            ordered = tuple(self._workers[worker.worker_id] for worker in self._manifest.workers)
            self._manifest = replace(self._manifest, workers=ordered)
        return replacement

    def _probe_snapshot(self) -> ResourceSnapshot:
        try:
            snapshot = self.probe.snapshot()
        except ResourceAllocationError:
            raise
        except Exception as error:
            raise ResourceAllocationError('PROBE_FAILED: resource snapshot') from error
        if not isinstance(snapshot, ResourceSnapshot) or (
            type(snapshot.logical_cpu_count) is not int
            or snapshot.logical_cpu_count <= 0
            or isinstance(snapshot.available_ram_gib, bool)
            or not isinstance(snapshot.available_ram_gib, (int, float))
            or not math.isfinite(float(snapshot.available_ram_gib))
            or snapshot.available_ram_gib < 0
            or isinstance(snapshot.gpu_free_gib, bool)
            or not isinstance(snapshot.gpu_free_gib, (int, float))
            or not math.isfinite(float(snapshot.gpu_free_gib))
            or snapshot.gpu_free_gib < 0
        ):
            raise ResourceAllocationError('INVALID_RESOURCE_SNAPSHOT')
        return ResourceSnapshot(
            snapshot.logical_cpu_count,
            float(snapshot.available_ram_gib),
            float(snapshot.gpu_free_gib),
        )

    def _paths(self, slot_index: int) -> dict[str, Path | str | int]:
        worker_id = f'worker-{slot_index:02d}'
        worker_root = self.evidence_root / 'workers' / worker_id
        socket_namespace = self.evidence_root / 'ipc' / str(slot_index)
        return {
            'worker_id': worker_id,
            'slot_index': slot_index,
            'worker_root': worker_root,
            'ros_home': worker_root / 'ros-home',
            'ros_log_dir': worker_root / 'ros-home' / 'log',
            'temp_dir': worker_root / 'tmp',
            'socket_namespace': socket_namespace,
            'socket_path': socket_namespace / 's',
        }

    def _preflight(self, paths: tuple[dict[str, Path | str | int], ...]) -> None:
        if os.path.lexists(self.evidence_root):
            raise ResourceAllocationError(f'DIRECTORY_CONFLICT: {self.evidence_root}')
        if not self.evidence_root.parent.is_dir():
            raise ResourceAllocationError('EVIDENCE_PARENT_MISSING')
        for item in paths:
            socket_path = item['socket_path']
            assert isinstance(socket_path, Path)
            if len(os.fsencode(socket_path)) > _UNIX_SOCKET_PATH_MAX_BYTES:
                raise ResourceAllocationError(f'UNIX_SOCKET_PATH_TOO_LONG: {socket_path}')
        try:
            domain_conflicts = [
                domain_id
                for domain_id in self.config.ros_domain_ids[: len(paths)]
                if self.probe.ros_domain_in_use(domain_id)
            ]
            socket_conflicts = [
                item['socket_path']
                for item in paths
                if self.probe.socket_in_use(item['socket_path'])
            ]
        except ResourceAllocationError:
            raise
        except Exception as error:
            raise ResourceAllocationError('PROBE_FAILED: namespace collision') from error
        if domain_conflicts:
            joined = ','.join(str(value) for value in domain_conflicts)
            raise ResourceAllocationError(f'ROS_DOMAIN_IN_USE: {joined}')
        if socket_conflicts:
            raise ResourceAllocationError(f'SOCKET_CONFLICT: {socket_conflicts[0]}')

    def _create_directories(self, paths: tuple[dict[str, Path | str | int], ...]) -> None:
        ordered: list[Path | str | int] = [
            self.evidence_root,
            self.evidence_root / 'workers',
            self.evidence_root / 'ipc',
        ]
        for item in paths:
            ordered.extend(
                [
                    item['worker_root'],
                    item['ros_home'],
                    item['ros_log_dir'],
                    item['temp_dir'],
                ]
            )
        ordered.extend(item['socket_namespace'] for item in paths)
        try:
            for path in ordered:
                assert isinstance(path, Path)
                path.mkdir(mode=0o700, parents=False, exist_ok=False)
                os.chmod(path, 0o700)
        except (FileExistsError, OSError) as error:
            raise ResourceAllocationError(f'DIRECTORY_CREATION_FAILED: {path}') from error

    def _worker(
        self,
        slot_index: int,
        paths: dict[str, Path | str | int],
        *,
        generation: int,
    ) -> WorkerResources:
        worker_id = str(paths['worker_id'])
        session_id = _session_id(worker_id, generation)
        controller_namespace = f'/parallel/{worker_id}'
        environment = {
            key: value
            for key in _BASE_ENVIRONMENT_ALLOWLIST
            if isinstance((value := self.base_environment.get(key)), str) and value
        }
        environment.update(
            {
                'ROS_DOMAIN_ID': str(self.config.ros_domain_ids[slot_index - 1]),
                'ROS_HOME': str(paths['ros_home']),
                'ROS_LOG_DIR': str(paths['ros_log_dir']),
                'TMPDIR': str(paths['temp_dir']),
                'TMP': str(paths['temp_dir']),
                'TEMP': str(paths['temp_dir']),
                'GZ_PARTITION': _NOT_APPLICABLE,
                'SO101_WORKER_ID': worker_id,
                'SO101_WORKER_GENERATION': str(generation),
                'SO101_SESSION_ID': session_id,
                'SO101_CONTROLLER_NAMESPACE': controller_namespace,
                'SO101_SOCKET_NAMESPACE': str(paths['socket_namespace']),
            }
        )
        return WorkerResources(
            worker_id=worker_id,
            slot_index=slot_index,
            generation=generation,
            ros_domain_id=self.config.ros_domain_ids[slot_index - 1],
            simulation_port=_NOT_APPLICABLE,
            bridge_port=_NOT_APPLICABLE,
            gz_partition=_NOT_APPLICABLE,
            session_id=session_id,
            controller_namespace=controller_namespace,
            ros_home=Path(paths['ros_home']),
            ros_log_dir=Path(paths['ros_log_dir']),
            temp_dir=Path(paths['temp_dir']),
            socket_namespace=Path(paths['socket_namespace']),
            socket_path=Path(paths['socket_path']),
            worker_root=Path(paths['worker_root']),
            environment=environment,
        )


def _session_id(worker_id: str, generation: int) -> str:
    return f'{worker_id}-g{generation:04d}-{uuid.uuid4().hex}'


def _resource_failures(
    observed: ResourceSnapshot, required: ResourceThresholds
) -> tuple[str, ...]:
    failures = []
    if observed.logical_cpu_count < required.logical_cpu_count:
        failures.append('INSUFFICIENT_LOGICAL_CPU')
    if observed.available_ram_gib < required.available_ram_gib:
        failures.append('INSUFFICIENT_AVAILABLE_RAM')
    if observed.gpu_free_gib < required.gpu_free_gib:
        failures.append('INSUFFICIENT_GPU_MEMORY')
    return tuple(failures)


def _write_manifest(path: Path, document: Mapping[str, object]) -> None:
    payload = (json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + '\n').encode(
        'utf-8'
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, 'wb', closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    if path.read_bytes() != payload:
        raise ResourceAllocationError('MANIFEST_READBACK_FAILED')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--worker-count', type=int, default=_DEFAULT_WORKER_COUNT)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true', required=True)
    return parser


def main(argv=None) -> int:
    """Write a resource manifest without starting ROS, MuJoCo or Broker."""
    arguments = _parser().parse_args(argv)
    try:
        config = load_parallel_runtime_config(arguments.config)
        manifest = WorkerResourceAllocator(config, arguments.evidence_root).allocate(
            arguments.worker_count
        )
        document = manifest.to_dict()
        _write_manifest(arguments.evidence_root / 'resource_manifest.json', document)
    except (ResourceAllocationError, ValueError, OSError) as error:
        failure = {'admitted': False, 'error': str(error)}
        if isinstance(error, ResourceAllocationError) and error.admission is not None:
            failure['admission'] = error.admission.to_dict()
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(document, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
