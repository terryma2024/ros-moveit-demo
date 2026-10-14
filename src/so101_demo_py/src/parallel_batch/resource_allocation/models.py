"""Runtime IPC roots, snapshots, the allocation policy and the worker resources."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import sys
from types import MappingProxyType
from typing import Mapping

_DEFAULT_WORKER_COUNT = 1


_NOT_APPLICABLE = 'not_applicable'


_MEM_AVAILABLE = re.compile(r'^MemAvailable:[ \t]+([0-9]+)[ \t]+kB$')


_BATCH_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')


_DOMAIN_CLAIM_SCOPE = 'cooperating_same_uid_processes'


_DOMAIN_CLAIM_PROTOCOL = 'uid_flock'


_CLEANUP_PROC_SCAN_QUIESCENCE_ATTEMPTS = 601


_CLEANUP_PROC_SCAN_QUIESCENCE_INTERVAL_S = 0.05


_CLEANUP_TRANSIENT_PROC_SCAN_BOUNDARIES = (
    'PROC_IDENTITY_UNVERIFIABLE:',
    'PROC_METADATA_UNVERIFIABLE:',
    'PROC_ENV_UNVERIFIABLE:',
    'PROC_CLASSIFICATION_UNVERIFIABLE:',
    'PROC_IDENTITY_CHANGED:',
)


_BASE_ENVIRONMENT_ALLOWLIST = (
    'PATH',
    'AMENT_PREFIX_PATH',
    'COLCON_PREFIX_PATH',
    'LD_LIBRARY_PATH',
    'PYTHONPATH',
    'RMW_IMPLEMENTATION',
    'SO101_IK_BACKEND',
)


class ResourceAllocationError(ValueError):
    """A Worker resource allocation or admission check failed."""

    def __init__(self, message: str, *, admission=None) -> None:
        super().__init__(message)
        self.admission = admission


def runtime_ipc_base() -> Path:
    """Return the fixed same-user IPC base for the current host platform."""

    if sys.platform == 'darwin':
        return Path('/opt/data/tmp')
    return Path(f'/run/user/{os.getuid()}')


def configured_runtime_ipc_root(
    batch_id: str, environment: Mapping[str, str] | None = None
) -> Path | None:
    """Resolve an explicitly configured short, same-user runtime socket root."""

    source = os.environ if environment is None else environment
    value = source.get('SO101_PARALLEL_IPC_BASE')
    if value is None:
        return None
    expected = runtime_ipc_base()
    base = Path(value)
    try:
        info = base.lstat()
    except OSError as error:
        raise ResourceAllocationError('IPC_BASE') from error
    if (
        base != expected
        or base.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
        or not isinstance(batch_id, str)
        or _BATCH_ID.fullmatch(batch_id) is None
    ):
        raise ResourceAllocationError('IPC_BASE')
    return base / f'so101-{batch_id}'


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
class AllocationPolicy:
    """Worker-count and Domain policy independent of observational resources."""

    max_worker_count: int
    ros_domain_ids: tuple[int, ...]
    persistent_cleanup_claims: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_worker_count, bool)
            or not isinstance(self.max_worker_count, int)
            or self.max_worker_count <= 0
        ):
            raise ResourceAllocationError('ALLOCATION_POLICY_WORKER_COUNT')
        domains = tuple(self.ros_domain_ids)
        if (
            len(domains) < self.max_worker_count
            or len(domains) != len(set(domains))
            or any(
                isinstance(domain, bool)
                or not isinstance(domain, int)
                or not 0 <= domain <= 232
                for domain in domains
            )
        ):
            raise ResourceAllocationError('ALLOCATION_POLICY_ROS_DOMAIN_IDS')
        if type(self.persistent_cleanup_claims) is not bool:
            raise ResourceAllocationError('ALLOCATION_POLICY_PERSISTENT_CLAIMS')
        object.__setattr__(self, 'ros_domain_ids', domains)


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
    render_backend: str
    render_context_id: str
    render_context_namespace: Path
    virtual_display: str
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
            'render_backend': self.render_backend,
            'render_context_id': self.render_context_id,
            'render_context_namespace': str(self.render_context_namespace),
            'virtual_display': self.virtual_display,
            'ros_home': str(self.ros_home),
            'ros_log_dir': str(self.ros_log_dir),
            'temp_dir': str(self.temp_dir),
            'socket_namespace': str(self.socket_namespace),
            'socket_path': str(self.socket_path),
            'worker_root': str(self.worker_root),
            'environment': dict(self.environment),
        }
