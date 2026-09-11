"""Fail-closed host admission and isolated Worker resource allocation."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
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
_SHA256 = re.compile(r'^[0-9a-f]{64}$')
_SHA1 = re.compile(r'^[0-9a-f]{40}$')
_BATCH_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
_DOMAIN_CLAIM_SCOPE = 'cooperating_same_uid_processes'
_DOMAIN_CLAIM_PROTOCOL = 'uid_flock_v1'
_MAX_LIVE_EVIDENCE_BYTES = 1024 * 1024
_TASK14_ARTIFACT_NAMES = (
    'source_manifest',
    'install_manifest',
    'container_identity',
    'model_manifest',
    'catalog',
    'policy_manifest',
    'scene_manifest',
    'resource_metrics',
    'simulation_metrics',
    'render_metrics',
    'aggregate',
    'cleanup',
)
_PROVENANCE_NAMES = {
    'source_tree_sha256',
    'install_tree_sha256',
    'runtime_config_sha256',
    'policy_sha256',
    'scene_sha256',
    'models_sha256',
    'container_sha256',
    'catalog_sha256',
}
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
    domain_claim_scope: str
    domain_claims: tuple[Mapping[str, object], ...]
    process_scan: Mapping[str, object]
    live_headroom_evidence: Mapping[str, object] | None
    workers: tuple[WorkerResources, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, 'domain_claims', tuple(_freeze_json(value) for value in self.domain_claims)
        )
        object.__setattr__(self, 'process_scan', _freeze_json(self.process_scan))
        if self.live_headroom_evidence is not None:
            object.__setattr__(
                self, 'live_headroom_evidence', _freeze_json(self.live_headroom_evidence)
            )

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
            'domain_claim_scope': self.domain_claim_scope,
            'domain_claims': [_thaw_json(value) for value in self.domain_claims],
            'process_scan': _thaw_json(self.process_scan),
            'live_headroom_evidence': _thaw_json(self.live_headroom_evidence),
            'workers': [worker.to_dict() for worker in self.workers],
        }


class SystemResourceProbe:
    """Read-only Linux probes used by ai-station dry admission."""

    def __init__(self, *, proc_root: Path = Path('/proc')) -> None:
        self._proc_root = Path(proc_root)
        self._skipped_processes: dict[tuple[int, int], dict[str, object]] = {}

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
        """Detect same-UID claims; unverifiable live same-UID processes fail closed."""
        if not self._proc_root.is_dir():
            raise ResourceAllocationError('PROBE_FAILED: proc filesystem unavailable')
        expected = str(domain_id).encode('ascii')
        for process in self._proc_root.iterdir():
            if not process.name.isdigit() or int(process.name) == os.getpid():
                continue
            try:
                process_stat = process.stat(follow_symlinks=False)
            except (FileNotFoundError, ProcessLookupError):
                continue
            except OSError as error:
                raise ResourceAllocationError(
                    f'PROC_IDENTITY_UNVERIFIABLE: {process.name}'
                ) from error
            if process_stat.st_uid != os.getuid():
                continue
            if not stat.S_ISDIR(process_stat.st_mode):
                raise ResourceAllocationError(f'PROC_IDENTITY_UNVERIFIABLE: {process.name}')
            try:
                before, comm, argv = _read_process_identity(process)
            except (FileNotFoundError, ProcessLookupError):
                if not os.path.lexists(process):
                    continue
                raise ResourceAllocationError(
                    f'PROC_METADATA_UNVERIFIABLE: {process.name}'
                )
            except (OSError, UnicodeError, ValueError) as error:
                raise ResourceAllocationError(
                    f'PROC_METADATA_UNVERIFIABLE: {process.name}'
                ) from error
            skip_reason = _frozen_non_candidate_reason(before[2], comm, argv)
            if skip_reason is not None:
                try:
                    after, _comm_after, _argv_after = _read_process_identity(process)
                except (OSError, UnicodeError, ValueError) as error:
                    raise ResourceAllocationError(
                        f'PROC_IDENTITY_CHANGED: {process.name}'
                    ) from error
                if before[:2] != after[:2]:
                    raise ResourceAllocationError(
                        f'PROC_IDENTITY_CHANGED: {process.name}'
                    )
                key = (before[0], before[1])
                self._skipped_processes[key] = {
                    'pid': before[0],
                    'uid': process_stat.st_uid,
                    'process_starttime_ticks': before[1],
                    'comm': comm,
                    'cmdline_summary': ' '.join(argv),
                    'skip_reason': skip_reason,
                }
                continue
            candidate = _is_high_recall_ros_candidate(comm, argv)
            try:
                entries = (process / 'environ').read_bytes().split(b'\0')
            except (FileNotFoundError, ProcessLookupError) as error:
                if not os.path.lexists(process):
                    continue
                raise ResourceAllocationError(
                    f'PROC_ENV_UNVERIFIABLE: {process.name}'
                ) from error
            except OSError as error:
                boundary = (
                    'PROC_ENV_UNVERIFIABLE'
                    if candidate
                    else 'PROC_CLASSIFICATION_UNVERIFIABLE'
                )
                raise ResourceAllocationError(
                    f'{boundary}: {process.name}'
                ) from error
            try:
                after, _comm_after, _argv_after = _read_process_identity(process)
            except (OSError, UnicodeError, ValueError) as error:
                raise ResourceAllocationError(
                    f'PROC_IDENTITY_CHANGED: {process.name}'
                ) from error
            if before[:2] != after[:2]:
                raise ResourceAllocationError(f'PROC_IDENTITY_CHANGED: {process.name}')
            if b'ROS_DOMAIN_ID=' + expected in entries:
                return True
        return False

    def process_scan_report(self) -> dict[str, object]:
        """Describe the bounded process trust model and every frozen skip."""
        return {
            'scope': _DOMAIN_CLAIM_SCOPE,
            'cross_uid_policy': 'not_inspected',
            'candidate_policy': 'same_uid_high_recall_requires_environ',
            'frozen_non_candidate_policy': 'recorded_without_environ',
            'unclassified_unreadable_policy': 'fail_closed',
            'skipped_processes': [
                dict(value)
                for _key, value in sorted(self._skipped_processes.items())
            ],
        }

    def socket_in_use(self, path: Path) -> bool:
        """Treat every existing filesystem object as a socket reservation."""
        return os.path.lexists(path)


class Task14AcceptanceProvider:
    """Future Task 11 port for a controller-owned Task 14 acceptance identity."""

    def __init__(self, *, acceptance_path: Path | None = None) -> None:
        self._acceptance_path = (
            None if acceptance_path is None else Path(acceptance_path)
        )

    def accepted_identity(self, candidate_path: Path) -> Mapping[str, object]:
        """Read an identity outside the candidate tree or fail closed when unwired."""
        if self._acceptance_path is None:
            raise ResourceAllocationError('TASK14_ACCEPTANCE_UNAVAILABLE')
        candidate_root = Path(candidate_path).parent.parent
        acceptance_path = self._acceptance_path
        if (
            not acceptance_path.is_absolute()
            or any(part in {'.', '..'} for part in str(acceptance_path).split('/'))
            or acceptance_path == candidate_root
            or acceptance_path.is_relative_to(candidate_root)
        ):
            raise ResourceAllocationError('TASK14_ACCEPTANCE_NOT_INDEPENDENT')
        document, _file_sha256 = _read_secure_json(acceptance_path)
        return document


class CurrentRuntimeProvenanceProbe:
    """Future Task 11 port for all current runtime provenance identities."""

    def __init__(self, *, current_paths: Mapping[str, Path] | None = None) -> None:
        self.current_paths = (
            None
            if current_paths is None
            else {name: Path(path) for name, path in current_paths.items()}
        )

    def snapshot(self, config: ParallelRuntimeConfig) -> Mapping[str, str]:
        """Hash every current runtime input or fail closed when the port is unwired."""
        if self.current_paths is None:
            raise ResourceAllocationError('CURRENT_RUNTIME_PROVENANCE_UNAVAILABLE')
        if set(self.current_paths) != _PROVENANCE_NAMES:
            raise ResourceAllocationError('CURRENT_RUNTIME_PROVENANCE_SCHEMA')
        payloads, observed = _read_current_inputs(self.current_paths)
        for name in sorted(_PROVENANCE_NAMES - {'runtime_config_sha256'}):
            _verify_provenance_inventory(name, _strict_json_object(payloads[name]))
        expected_config = _json_bytes(asdict(config))
        if payloads['runtime_config_sha256'] != expected_config:
            raise ResourceAllocationError('CURRENT_RUNTIME_CONFIG_DRIFT')
        if observed['runtime_config_sha256'] != _runtime_config_sha256(config):
            raise ResourceAllocationError('CURRENT_RUNTIME_CONFIG_DRIFT')
        return observed


class Task14LiveHeadroomVerifier:
    """Verify a sealed Task 14 two-Worker execution and every bound artifact."""

    def __init__(self, *, acceptance_provider=None, provenance_probe=None) -> None:
        self._acceptance_provider = (
            Task14AcceptanceProvider()
            if acceptance_provider is None
            else acceptance_provider
        )
        self._provenance_probe = (
            CurrentRuntimeProvenanceProbe()
            if provenance_probe is None
            else provenance_probe
        )

    def verify(
        self, manifest_path: Path, *, config: ParallelRuntimeConfig
    ) -> Mapping[str, object]:
        """Return a compact verified record or fail closed on any uncertainty."""
        path = Path(manifest_path)
        if (
            not path.is_absolute()
            or path.name != 'task14_headroom_manifest.json'
            or path.parent.name != 'sealed'
            or not path.parent.parent.name
            or any(part in {'.', '..'} for part in str(path).split('/'))
        ):
            raise ResourceAllocationError('TASK14_SEALED_PATH_INVALID')
        acceptance = self._acceptance_provider.accepted_identity(path)
        current_provenance = self._provenance_probe.snapshot(config)
        batch_root = path.parent.parent
        parent_fd = batch_fd = sealed_fd = artifacts_fd = None
        snapshots = []
        try:
            parent_fd = _open_trusted_parent(batch_root)
            batch_fd = _open_directory_at(parent_fd, batch_root.name)
            _verify_trusted_directory(batch_fd, str(batch_root), final_parent=True)
            snapshots.append(
                (parent_fd, batch_root.name, _fd_snapshot(batch_fd), True, None)
            )
            sealed_fd = _open_directory_at(batch_fd, 'sealed')
            _verify_sealed_directory(sealed_fd, 'sealed')
            snapshots.append(
                (batch_fd, 'sealed', _fd_snapshot(sealed_fd), True, None)
            )
            artifacts_fd = _open_directory_at(sealed_fd, 'artifacts')
            _verify_sealed_directory(artifacts_fd, 'artifacts')
            snapshots.append(
                (sealed_fd, 'artifacts', _fd_snapshot(artifacts_fd), True, None)
            )
            document, manifest_sha256, manifest_identity = _read_sealed_json_at(
                sealed_fd, path.name
            )
            snapshots.append(
                (sealed_fd, path.name, manifest_identity, False, manifest_sha256)
            )
            result = self._verify_document(
                document,
                config=config,
                artifacts_fd=artifacts_fd,
                snapshots=snapshots,
            )
            self._verify_acceptance(
                acceptance,
                current_provenance,
                manifest_sha256=manifest_sha256,
                verified=result,
            )
            final_current_provenance = self._provenance_probe.snapshot(config)
            if dict(final_current_provenance) != dict(current_provenance):
                raise ResourceAllocationError('CURRENT_PROVENANCE_CHANGED')
            for directory_fd, name, snapshot, is_directory, expected_hash in snapshots:
                _verify_stable_snapshot_at(
                    directory_fd,
                    name,
                    snapshot,
                    is_directory=is_directory,
                    expected_sha256=expected_hash,
                )
            final_acceptance = self._acceptance_provider.accepted_identity(path)
            if final_acceptance != acceptance:
                raise ResourceAllocationError('TASK14_ACCEPTANCE_CHANGED')
            self._verify_acceptance(
                final_acceptance,
                final_current_provenance,
                manifest_sha256=manifest_sha256,
                verified=result,
            )
            return {
                'sealed_batch_root': str(batch_root),
                'manifest_path': str(path),
                'manifest_sha256': manifest_sha256,
                'acceptance_identity': dict(final_acceptance),
                'current_provenance': dict(final_current_provenance),
                **result,
            }
        finally:
            for descriptor in (artifacts_fd, sealed_fd, batch_fd, parent_fd):
                if descriptor is not None:
                    os.close(descriptor)

    def _verify_document(
        self,
        document: dict[str, object],
        *,
        config: ParallelRuntimeConfig,
        artifacts_fd: int,
        snapshots: list,
    ) -> dict[str, object]:
        expected_document = {
            'schema_version',
            'kind',
            'status',
            'batch_id',
            'worker_count',
            'run_mode',
            'lifecycle',
            'cleanup_complete',
            'source_identity',
            'artifacts',
            'headroom',
            'simulation',
            'rendering',
        }
        if set(document) != expected_document:
            raise ValueError('Task14 manifest schema')
        if (
            type(document['schema_version']) is not int
            or document['schema_version'] != 1
            or document['kind'] != 'task14_two_worker_live_headroom'
            or document['status'] != 'VALID'
            or type(document['batch_id']) is not str
            or _BATCH_ID.fullmatch(document['batch_id']) is None
            or type(document['worker_count']) is not int
            or document['worker_count'] != 2
            or document['run_mode'] != 'execute'
            or document['lifecycle'] != 'ISOLATED_STACK'
            or document['cleanup_complete'] is not True
        ):
            raise ValueError('Task14 execution was not accepted')
        batch_id = document['batch_id']
        artifacts = document['artifacts']
        if not isinstance(artifacts, dict) or set(artifacts) != set(
            _TASK14_ARTIFACT_NAMES
        ):
            raise ValueError('Task14 artifact schema')
        artifact_documents = {}
        artifact_hashes = {}
        for name in _TASK14_ARTIFACT_NAMES:
            entry = artifacts[name]
            expected_path = f'artifacts/{name}.json'
            if (
                not isinstance(entry, dict)
                or set(entry) != {'path', 'sha256'}
                or entry['path'] != expected_path
                or type(entry['sha256']) is not str
                or _SHA256.fullmatch(entry['sha256']) is None
            ):
                raise ValueError(f'Task14 artifact binding: {name}')
            artifact_document, observed_hash, identity = _read_sealed_json_at(
                artifacts_fd, f'{name}.json'
            )
            if observed_hash != entry['sha256']:
                raise ValueError(f'Task14 artifact hash: {name}')
            snapshots.append(
                (artifacts_fd, f'{name}.json', identity, False, observed_hash)
            )
            artifact_documents[name] = artifact_document
            artifact_hashes[name] = observed_hash

        source = document['source_identity']
        if not isinstance(source, dict) or set(source) != _PROVENANCE_NAMES:
            raise ValueError('Task14 source identity schema')
        provenance_artifacts = {
            'source_tree_sha256': 'source_manifest',
            'install_tree_sha256': 'install_manifest',
            'policy_sha256': 'policy_manifest',
            'scene_sha256': 'scene_manifest',
            'models_sha256': 'model_manifest',
            'container_sha256': 'container_identity',
            'catalog_sha256': 'catalog',
        }
        for identity_name, artifact_name in provenance_artifacts.items():
            _verify_provenance_inventory(
                identity_name, artifact_documents[artifact_name]
            )
        expected_identity_values = {
            'source_tree_sha256': artifact_hashes['source_manifest'],
            'install_tree_sha256': artifact_hashes['install_manifest'],
            'runtime_config_sha256': _runtime_config_sha256(config),
            'policy_sha256': artifact_hashes['policy_manifest'],
            'scene_sha256': artifact_hashes['scene_manifest'],
            'models_sha256': artifact_hashes['model_manifest'],
            'container_sha256': artifact_hashes['container_identity'],
            'catalog_sha256': artifact_hashes['catalog'],
        }
        if source != expected_identity_values:
            raise ValueError('Task14 source identity mismatch')

        headroom = document['headroom']
        expected_ratios = {
            'cpu_ratio',
            'ram_ratio',
            'gpu_ratio',
            'simulation_realtime_ratio',
            'render_frame_ratio',
        }
        if not isinstance(headroom, dict) or set(headroom) != expected_ratios:
            raise ValueError('Task14 headroom schema')
        for value in headroom.values():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < config.required_live_headroom_ratio
            ):
                raise ValueError('Task14 headroom threshold')
        resource_metrics = artifact_documents['resource_metrics']
        if (
            set(resource_metrics)
            != {
                'batch_id',
                'worker_count',
                'cpu_headroom_ratio',
                'ram_headroom_ratio',
                'gpu_headroom_ratio',
            }
            or resource_metrics['batch_id'] != batch_id
            or resource_metrics['worker_count'] != 2
            or resource_metrics['cpu_headroom_ratio'] != headroom['cpu_ratio']
            or resource_metrics['ram_headroom_ratio'] != headroom['ram_ratio']
            or resource_metrics['gpu_headroom_ratio'] != headroom['gpu_ratio']
        ):
            raise ValueError('Task14 resource metrics binding')
        simulation = document['simulation']
        simulation_metrics = artifact_documents['simulation_metrics']
        if (
            simulation
            != {
                'backend': 'mujoco',
                'stable': True,
                'metrics_artifact': 'simulation_metrics',
            }
            or set(simulation_metrics)
            != {
                'batch_id',
                'backend',
                'stable',
                'realtime_headroom_ratio',
            }
            or simulation_metrics['batch_id'] != batch_id
            or simulation_metrics['backend'] != 'mujoco'
            or simulation_metrics['stable'] is not True
            or simulation_metrics['realtime_headroom_ratio']
            != headroom['simulation_realtime_ratio']
        ):
            raise ValueError('Task14 simulation metrics binding')
        rendering = document['rendering']
        render_metrics = artifact_documents['render_metrics']
        if (
            rendering
            != {
                'backend': 'headless_egl',
                'stable': True,
                'metrics_artifact': 'render_metrics',
            }
            or set(render_metrics)
            != {'batch_id', 'backend', 'stable', 'frame_headroom_ratio'}
            or render_metrics['batch_id'] != batch_id
            or render_metrics['backend'] != 'headless_egl'
            or render_metrics['stable'] is not True
            or render_metrics['frame_headroom_ratio']
            != headroom['render_frame_ratio']
        ):
            raise ValueError('Task14 render metrics binding')
        aggregate = artifact_documents['aggregate']
        if aggregate != {
            'batch_id': batch_id,
            'worker_count': 2,
            'run_mode': 'execute',
            'lifecycle': 'ISOLATED_STACK',
            'batch_terminal': True,
            'coverage_complete': True,
            'execution_complete': True,
            'qualification_applicable': True,
            'qualification_passed': True,
            'batch_cleanup_complete': True,
        }:
            raise ValueError('Task14 accepted aggregate')
        cleanup = artifact_documents['cleanup']
        if cleanup != {
            'batch_id': batch_id,
            'cleanup_complete': True,
            'active_owned_processes': 0,
        }:
            raise ValueError('Task14 cleanup evidence')
        if aggregate['batch_cleanup_complete'] is not cleanup['cleanup_complete']:
            raise ValueError('Task14 aggregate cleanup mismatch')
        return {
            'accepted_batch_id': batch_id,
            'source_identity': dict(source),
            'artifact_sha256': artifact_hashes,
            'headroom': dict(headroom),
            'simulation': dict(simulation),
            'rendering': dict(rendering),
        }

    def _verify_acceptance(
        self,
        acceptance,
        current_provenance,
        *,
        manifest_sha256: str,
        verified: Mapping[str, object],
    ) -> None:
        expected_acceptance = {
            'schema_version',
            'authority',
            'status',
            'accepted_batch_id',
            'candidate_manifest_sha256',
            'aggregate_sha256',
            'cleanup_sha256',
            'provenance',
        }
        if not isinstance(acceptance, dict) or set(acceptance) != expected_acceptance:
            raise ValueError('Task14 acceptance identity schema')
        if (
            type(acceptance['schema_version']) is not int
            or acceptance['schema_version'] != 1
            or acceptance['authority'] != 'task14_controller_acceptance_v1'
            or acceptance['status'] != 'VALID'
            or acceptance['accepted_batch_id'] != verified['accepted_batch_id']
            or acceptance['candidate_manifest_sha256'] != manifest_sha256
            or acceptance['aggregate_sha256']
            != verified['artifact_sha256']['aggregate']
            or acceptance['cleanup_sha256']
            != verified['artifact_sha256']['cleanup']
        ):
            raise ValueError('Task14 acceptance identity mismatch')
        for name in (
            'candidate_manifest_sha256',
            'aggregate_sha256',
            'cleanup_sha256',
        ):
            if (
                type(acceptance[name]) is not str
                or _SHA256.fullmatch(acceptance[name]) is None
            ):
                raise ValueError('Task14 acceptance hash')
        provenance = acceptance['provenance']
        if (
            not isinstance(provenance, dict)
            or set(provenance) != _PROVENANCE_NAMES
            or not isinstance(current_provenance, Mapping)
            or set(current_provenance) != _PROVENANCE_NAMES
            or any(
                type(value) is not str or _SHA256.fullmatch(value) is None
                for value in (*provenance.values(), *current_provenance.values())
            )
            or provenance != verified['source_identity']
            or dict(current_provenance) != provenance
        ):
            raise ValueError('Task14 current provenance mismatch')


class WorkerResourceAllocator:
    """Allocate one private resource set for every requested stable slot."""

    def __init__(
        self,
        config: ParallelRuntimeConfig,
        evidence_root: Path,
        *,
        probe=None,
        base_environment: Mapping[str, str] | None = None,
        claim_root: Path | None = None,
        live_headroom_evidence: Path | None = None,
        live_headroom_verifier=None,
        batch_id: str | None = None,
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
        selected_batch_id = root.name if batch_id is None else batch_id
        if not isinstance(selected_batch_id, str) or _BATCH_ID.fullmatch(selected_batch_id) is None:
            raise ResourceAllocationError('BATCH_ID')
        self.batch_id = selected_batch_id
        self.probe = probe if probe is not None else SystemResourceProbe()
        source_environment = os.environ if base_environment is None else base_environment
        if not isinstance(source_environment, Mapping):
            raise ResourceAllocationError('BASE_ENVIRONMENT')
        self.base_environment = dict(source_environment)
        self.claim_root = (
            Path(f'/run/user/{os.getuid()}/so101-parallel-domain-claims')
            if claim_root is None
            else Path(claim_root)
        )
        if not self.claim_root.is_absolute():
            raise ResourceAllocationError('CLAIM_ROOT')
        self.live_headroom_evidence = (
            None if live_headroom_evidence is None else Path(live_headroom_evidence)
        )
        self._live_headroom_verifier = (
            Task14LiveHeadroomVerifier()
            if live_headroom_verifier is None
            else live_headroom_verifier
        )
        self._manifest: ResourceManifest | None = None
        self._workers: dict[str, WorkerResources] = {}
        self._claim_fds: dict[int, int] = {}
        self._domain_claims: tuple[Mapping[str, object], ...] = ()
        self._process_scan: Mapping[str, object] = _default_process_scan_report()
        self._directory_fds: list[int] = []
        self._root_fd: int | None = None
        self._root_identity: tuple[int, int] | None = None
        self._closed = False

    @property
    def manifest(self) -> ResourceManifest | None:
        """Return the current immutable manifest, including replacements."""
        return self._manifest

    def allocate(self, worker_count: int | None = None) -> ResourceManifest:
        """Admit and allocate exactly the requested count; never downgrade it."""
        if self._closed:
            raise ResourceAllocationError('ALLOCATOR_NOT_ACTIVE')
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
        live_headroom = self._live_headroom(requested)

        paths = tuple(self._paths(slot + 1) for slot in range(requested))
        parent_fd = None
        try:
            parent_fd = _open_trusted_parent(self.evidence_root)
            self._claim_domains(self.config.ros_domain_ids[:requested])
            self._preflight(paths, parent_fd)
            scan_report = getattr(self.probe, 'process_scan_report', None)
            if callable(scan_report):
                self._process_scan = scan_report()
            self._create_directories(paths, parent_fd)
            workers = tuple(
                self._worker(slot + 1, paths[slot], generation=1)
                for slot in range(requested)
            )
        except Exception:
            self.close()
            raise
        finally:
            if parent_fd is not None:
                os.close(parent_fd)
        self._workers = {worker.worker_id: worker for worker in workers}
        self._manifest = ResourceManifest(
            schema_version=1,
            mode='dry_run',
            backend=self.config.backend,
            evidence_root=self.evidence_root,
            requested_worker_count=requested,
            worker_count=requested,
            admission=admission,
            domain_claim_scope=_DOMAIN_CLAIM_SCOPE,
            domain_claims=self._domain_claims,
            process_scan=self._process_scan,
            live_headroom_evidence=live_headroom,
            workers=workers,
        )
        return self._manifest

    def write_manifest(self) -> Path:
        """Publish through the held root descriptor and verify the visible identity."""
        if self._manifest is None or self._root_fd is None or self._closed:
            raise ResourceAllocationError('ALLOCATOR_NOT_ACTIVE')
        path = self.evidence_root / 'resource_manifest.json'
        try:
            self._verify_root_identity()
            _write_manifest_at(self._root_fd, 'resource_manifest.json', self._manifest.to_dict())
            self._verify_root_identity()
        except Exception:
            self.close()
            raise
        return path

    def close(self) -> None:
        """Release held directory descriptors and authoritative domain claims."""
        if self._closed:
            return
        self._closed = True
        for descriptor in reversed(self._directory_fds):
            try:
                os.close(descriptor)
            except OSError:
                pass
        self._directory_fds.clear()
        self._root_fd = None
        for descriptor in self._claim_fds.values():
            try:
                os.close(descriptor)
            except OSError:
                pass
        self._claim_fds.clear()

    def __enter__(self):
        return self

    def __exit__(self, _error_type, _error, _traceback) -> None:
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def replace(self, worker_id: str, *, expected_generation: int) -> WorkerResources:
        """Reuse one stable slot while fencing it with the next generation."""
        if self._closed:
            raise ResourceAllocationError('ALLOCATOR_NOT_ACTIVE')
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

    def _live_headroom(self, worker_count: int) -> Mapping[str, object] | None:
        if worker_count != 3:
            return None
        if self.live_headroom_evidence is None:
            raise ResourceAllocationError('THREE_WORKER_LIVE_EVIDENCE_REQUIRED')
        try:
            verified = self._live_headroom_verifier.verify(
                self.live_headroom_evidence, config=self.config
            )
            if not isinstance(verified, Mapping):
                raise TypeError('verifier result')
            return dict(verified)
        except Exception as error:
            raise ResourceAllocationError('THREE_WORKER_LIVE_EVIDENCE_INVALID') from error

    def _claim_domains(self, domains: tuple[int, ...]) -> None:
        claim_parent_fd = _open_trusted_parent(self.claim_root)
        claim_root_fd = None
        acquired: dict[int, int] = {}
        records = []
        try:
            claim_root_fd = _open_or_create_private_directory(
                claim_parent_fd, self.claim_root.name
            )
            for domain_id in sorted(domains):
                name = f'domain-{domain_id}.lock'
                descriptor = os.open(
                    name,
                    os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=claim_root_fd,
                )
                try:
                    _verify_private_regular(descriptor, name)
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError as error:
                        raise ResourceAllocationError(
                            f'ROS_DOMAIN_CLAIMED: {domain_id}'
                        ) from error
                    acquired[domain_id] = descriptor
                except Exception:
                    os.close(descriptor)
                    raise
            process_starttime = _process_starttime_ticks()
            for domain_id, descriptor in acquired.items():
                name = f'domain-{domain_id}.lock'
                record = {
                    'protocol': _DOMAIN_CLAIM_PROTOCOL,
                    'scope': _DOMAIN_CLAIM_SCOPE,
                    'domain_id': domain_id,
                    'uid': os.getuid(),
                    'pid': os.getpid(),
                    'process_starttime_ticks': process_starttime,
                    'batch_id': self.batch_id,
                    'evidence_root': str(self.evidence_root),
                    'claim_path': str(self.claim_root / name),
                }
                _replace_fd_contents(descriptor, _json_bytes(record) + b'\n')
                records.append(record)
            os.fsync(claim_root_fd)
        except Exception:
            for descriptor in acquired.values():
                os.close(descriptor)
            raise
        finally:
            if claim_root_fd is not None:
                os.close(claim_root_fd)
            os.close(claim_parent_fd)
        self._claim_fds = acquired
        self._domain_claims = tuple(records)

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
            'render_context_namespace': worker_root / 'render',
            'socket_namespace': socket_namespace,
            'socket_path': socket_namespace / 's',
        }

    def _preflight(
        self, paths: tuple[dict[str, Path | str | int], ...], parent_fd: int
    ) -> None:
        try:
            existing = os.stat(
                self.evidence_root.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            existing = None
        except OSError as error:
            raise ResourceAllocationError('EVIDENCE_ROOT_CHECK_FAILED') from error
        if existing is not None:
            if stat.S_ISLNK(existing.st_mode):
                raise ResourceAllocationError(f'SYMLINK_PATH: {self.evidence_root}')
            raise ResourceAllocationError(f'DIRECTORY_CONFLICT: {self.evidence_root}')
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

    def _create_directories(
        self, paths: tuple[dict[str, Path | str | int], ...], parent_fd: int
    ) -> None:
        try:
            root_fd = _mkdir_private_at(parent_fd, self.evidence_root.name)
            self._directory_fds.append(root_fd)
            self._root_fd = root_fd
            root_stat = os.fstat(root_fd)
            self._root_identity = (root_stat.st_dev, root_stat.st_ino)
            workers_fd = _mkdir_private_at(root_fd, 'workers')
            ipc_fd = _mkdir_private_at(root_fd, 'ipc')
            self._directory_fds.extend((workers_fd, ipc_fd))
            for item in paths:
                worker_fd = _mkdir_private_at(workers_fd, str(item['worker_id']))
                ros_fd = _mkdir_private_at(worker_fd, 'ros-home')
                log_fd = _mkdir_private_at(ros_fd, 'log')
                temp_fd = _mkdir_private_at(worker_fd, 'tmp')
                render_fd = _mkdir_private_at(worker_fd, 'render')
                socket_fd = _mkdir_private_at(ipc_fd, str(item['slot_index']))
                self._directory_fds.extend(
                    (worker_fd, ros_fd, log_fd, temp_fd, render_fd, socket_fd)
                )
            os.fsync(workers_fd)
            os.fsync(ipc_fd)
            os.fsync(root_fd)
            os.fsync(parent_fd)
            self._verify_root_identity()
        except ResourceAllocationError:
            raise
        except OSError as error:
            raise ResourceAllocationError('DIRECTORY_CREATION_FAILED') from error

    def _verify_root_identity(self) -> None:
        if self._root_fd is None or self._root_identity is None:
            raise ResourceAllocationError('ROOT_FD_MISSING')
        held = _verify_trusted_directory(
            self._root_fd, str(self.evidence_root), private=True
        )
        parent_fd = _open_trusted_parent(self.evidence_root)
        try:
            visible = os.stat(
                self.evidence_root.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except OSError as error:
            raise ResourceAllocationError('PATH_IDENTITY_CHANGED') from error
        finally:
            os.close(parent_fd)
        identity = (held.st_dev, held.st_ino)
        if (
            identity != self._root_identity
            or (visible.st_dev, visible.st_ino) != self._root_identity
            or not stat.S_ISDIR(visible.st_mode)
        ):
            raise ResourceAllocationError('PATH_IDENTITY_CHANGED')

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
        render_context_id = f'{self.batch_id}-egl-{slot_index:02d}'
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
                'MUJOCO_GL': 'egl',
                'SO101_RENDER_CONTEXT_ID': render_context_id,
                'SO101_RENDER_CONTEXT_NAMESPACE': str(paths['render_context_namespace']),
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
            render_backend='headless_egl',
            render_context_id=render_context_id,
            render_context_namespace=Path(paths['render_context_namespace']),
            virtual_display=_NOT_APPLICABLE,
            ros_home=Path(paths['ros_home']),
            ros_log_dir=Path(paths['ros_log_dir']),
            temp_dir=Path(paths['temp_dir']),
            socket_namespace=Path(paths['socket_namespace']),
            socket_path=Path(paths['socket_path']),
            worker_root=Path(paths['worker_root']),
            environment=environment,
        )


def _verify_trusted_directory(
    descriptor: int, name: str, *, final_parent: bool = False, private: bool = False
) -> os.stat_result:
    value = os.fstat(descriptor)
    if not stat.S_ISDIR(value.st_mode):
        raise ResourceAllocationError(f'NOT_DIRECTORY: {name}')
    uid = os.getuid()
    mode = stat.S_IMODE(value.st_mode)
    if private:
        if value.st_uid != uid:
            raise ResourceAllocationError(f'UNSAFE_DIRECTORY_OWNER: {name}')
        if mode != 0o700:
            raise ResourceAllocationError(f'UNSAFE_DIRECTORY_MODE: {name}')
        return value
    if value.st_uid not in {0, uid} or (final_parent and value.st_uid != uid):
        raise ResourceAllocationError(f'UNSAFE_DIRECTORY_OWNER: {name}')
    if mode & 0o002 or (value.st_uid == 0 and mode & 0o020):
        raise ResourceAllocationError(f'UNSAFE_DIRECTORY_MODE: {name}')
    return value


def _open_trusted_parent(path: Path) -> int:
    if not path.is_absolute() or not path.name:
        raise ResourceAllocationError('ABSOLUTE_PATH_REQUIRED')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open('/', flags)
    parts = path.parent.parts[1:]
    try:
        _verify_trusted_directory(descriptor, '/')
        for index, part in enumerate(parts):
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except OSError as error:
                if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise ResourceAllocationError(f'SYMLINK_PATH: {path}') from error
                raise ResourceAllocationError(f'PATH_ANCESTOR_UNAVAILABLE: {path}') from error
            os.close(descriptor)
            descriptor = child
            _verify_trusted_directory(
                descriptor,
                str(path.parent),
                final_parent=index == len(parts) - 1,
            )
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_or_create_private_directory(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileExistsError:
        pass
    try:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ResourceAllocationError(f'SYMLINK_PATH: {name}') from error
        raise ResourceAllocationError(f'DIRECTORY_OPEN_FAILED: {name}') from error
    try:
        _verify_trusted_directory(descriptor, name, private=True)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _mkdir_private_at(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        descriptor = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
    except FileExistsError as error:
        raise ResourceAllocationError(f'DIRECTORY_CONFLICT: {name}') from error
    except OSError as error:
        raise ResourceAllocationError(f'DIRECTORY_CREATION_FAILED: {name}') from error
    try:
        _verify_trusted_directory(descriptor, name, private=True)
        os.fsync(parent_fd)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _verify_private_regular(descriptor: int, name: str) -> os.stat_result:
    value = os.fstat(descriptor)
    if not stat.S_ISREG(value.st_mode):
        raise ResourceAllocationError(f'NOT_REGULAR_FILE: {name}')
    if value.st_uid != os.getuid():
        raise ResourceAllocationError(f'UNSAFE_FILE_OWNER: {name}')
    if stat.S_IMODE(value.st_mode) != 0o600:
        raise ResourceAllocationError(f'UNSAFE_FILE_MODE: {name}')
    return value


def _replace_fd_contents(descriptor: int, payload: bytes) -> None:
    os.ftruncate(descriptor, 0)
    os.lseek(descriptor, 0, os.SEEK_SET)
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError('short write')
        offset += written
    os.fsync(descriptor)
    os.lseek(descriptor, 0, os.SEEK_SET)
    if _read_fd(descriptor, len(payload) + 1) != payload:
        raise ResourceAllocationError('FILE_READBACK_FAILED')


def _read_fd(descriptor: int, limit: int) -> bytes:
    chunks = []
    remaining = limit
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def _json_bytes(document) -> bytes:
    def validate(value):
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError('non-string JSON key')
            for child in value.values():
                validate(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                validate(child)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError('non-finite JSON number')

    validate(document)
    return json.dumps(
        document, sort_keys=True, separators=(',', ':'), allow_nan=False
    ).encode('utf-8')


def _freeze_json(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(child) for key, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value):
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(child) for child in value]
    return value


def _runtime_config_sha256(config: ParallelRuntimeConfig) -> str:
    return hashlib.sha256(_json_bytes(asdict(config))).hexdigest()


def _verify_content_hash(value, label: str) -> None:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f'invalid content hash: {label}')


def _verify_inventory_path(value, label: str) -> None:
    if (
        type(value) is not str
        or not value
        or '\\' in value
        or PurePosixPath(value).is_absolute()
        or any(part in {'', '.', '..'} for part in value.split('/'))
    ):
        raise ValueError(f'invalid inventory path: {label}')


def _verify_inventory_entries(entries, *, source: bool) -> None:
    if not isinstance(entries, list) or not entries:
        raise ValueError('content inventory entries')
    paths = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('content inventory entry')
        if source and entry.get('kind') == 'gitlink':
            if (
                set(entry) != {'path', 'kind', 'mode', 'commit'}
                or entry['mode'] != '160000'
                or type(entry['commit']) is not str
                or _SHA1.fullmatch(entry['commit']) is None
            ):
                raise ValueError('source gitlink inventory entry')
        elif (
            set(entry)
            != (
                {'path', 'kind', 'mode', 'sha256'}
                if source
                else {'path', 'mode', 'sha256'}
            )
            or (source and entry['kind'] != 'file')
            or entry['mode'] not in {'100644', '100755'}
        ):
            raise ValueError('file content inventory entry')
        else:
            _verify_content_hash(entry['sha256'], 'inventory entry')
        _verify_inventory_path(entry['path'], 'inventory entry')
        paths.append(entry['path'])
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError('content inventory path order')


def _verify_provenance_inventory(name: str, document: dict[str, object]) -> None:
    if name == 'source_tree_sha256':
        if set(document) != {
            'schema_version',
            'source_commit',
            'source_root',
            'tree_sha256',
            'dirty_patch_sha256',
            'entries',
        }:
            raise ValueError('source content inventory schema')
        source_root = document['source_root']
        if (
            document['schema_version'] != 1
            or type(document['schema_version']) is not int
            or type(document['source_commit']) is not str
            or _SHA1.fullmatch(document['source_commit']) is None
            or type(source_root) is not str
            or not Path(source_root).is_absolute()
            or any(part in {'.', '..'} for part in source_root.split('/'))
        ):
            raise ValueError('source content inventory identity')
        _verify_inventory_entries(document['entries'], source=True)
        _verify_content_hash(document['tree_sha256'], 'source tree')
        _verify_content_hash(document['dirty_patch_sha256'], 'dirty patch')
        if document['tree_sha256'] != hashlib.sha256(
            _json_bytes(document['entries'])
        ).hexdigest():
            raise ValueError('source tree inventory hash')
        return
    if name == 'install_tree_sha256':
        if set(document) != {
            'schema_version',
            'install_prefix',
            'tree_sha256',
            'entries',
        }:
            raise ValueError('install content inventory schema')
        prefix = document['install_prefix']
        if (
            document['schema_version'] != 1
            or type(document['schema_version']) is not int
            or type(prefix) is not str
            or not Path(prefix).is_absolute()
            or any(part in {'.', '..'} for part in prefix.split('/'))
        ):
            raise ValueError('install content inventory identity')
        _verify_inventory_entries(document['entries'], source=False)
        _verify_content_hash(document['tree_sha256'], 'install tree')
        if document['tree_sha256'] != hashlib.sha256(
            _json_bytes(document['entries'])
        ).hexdigest():
            raise ValueError('install tree inventory hash')
        return
    simple_schemas = {
        'policy_sha256': ('policy_path', 'content_sha256'),
        'scene_sha256': ('scene_path', 'content_sha256'),
        'models_sha256': ('model_path', 'weights_sha256'),
        'catalog_sha256': ('catalog_path', 'coordinates_sha256'),
    }
    if name in simple_schemas:
        path_name, hash_name = simple_schemas[name]
        if set(document) != {'schema_version', path_name, hash_name}:
            raise ValueError(f'{name} content inventory schema')
        if document['schema_version'] != 1 or type(document['schema_version']) is not int:
            raise ValueError(f'{name} content inventory identity')
        _verify_inventory_path(document[path_name], path_name)
        _verify_content_hash(document[hash_name], hash_name)
        return
    if name == 'container_sha256':
        if set(document) != {'schema_version', 'image_id'}:
            raise ValueError('container identity schema')
        image_id = document['image_id']
        if (
            document['schema_version'] != 1
            or type(document['schema_version']) is not int
            or type(image_id) is not str
            or not image_id.startswith('sha256:')
            or _SHA256.fullmatch(image_id[7:]) is None
        ):
            raise ValueError('container image identity')
        return
    raise ValueError(f'unknown provenance inventory: {name}')


def _default_process_scan_report() -> dict[str, object]:
    return {
        'scope': _DOMAIN_CLAIM_SCOPE,
        'cross_uid_policy': 'not_inspected',
        'candidate_policy': 'same_uid_high_recall_requires_environ',
        'frozen_non_candidate_policy': 'recorded_without_environ',
        'unclassified_unreadable_policy': 'fail_closed',
        'skipped_processes': [],
    }


def _read_process_identity(
    process: Path,
) -> tuple[tuple[int, int, str], str, tuple[str, ...]]:
    pid = int(process.name)
    stat_line = (process / 'stat').read_text(encoding='ascii').strip()
    closing = stat_line.rfind(')')
    if closing <= 0 or not stat_line.startswith(f'{pid} ('):
        raise ValueError('invalid proc stat identity')
    fields = stat_line[closing + 2 :].split()
    if len(fields) <= 19 or len(fields[0]) != 1:
        raise ValueError('invalid proc stat fields')
    starttime = int(fields[19])
    if starttime <= 0:
        raise ValueError('invalid proc starttime')
    comm = (process / 'comm').read_text(encoding='utf-8').strip()
    if not comm or '\x00' in comm or '\n' in comm or len(comm) > 64:
        raise ValueError('invalid proc comm')
    raw_cmdline = (process / 'cmdline').read_bytes()
    if len(raw_cmdline) > 4096:
        raise ValueError('proc cmdline too large')
    argv = tuple(
        item.decode('utf-8')
        for item in raw_cmdline.split(b'\0')
        if item
    )
    return (pid, starttime, fields[0]), comm, argv


def _frozen_non_candidate_reason(
    state: str, comm: str, argv: tuple[str, ...]
) -> str | None:
    if state == 'Z':
        return 'frozen_zombie_non_candidate'
    if comm == 'systemd' and argv == ('/usr/lib/systemd/systemd', '--user'):
        return 'frozen_systemd_user_non_candidate'
    if comm == '(sd-pam)' and argv == ('(sd-pam)',):
        return 'frozen_systemd_pam_non_candidate'
    if (
        comm == 'sshd'
        and len(argv) == 1
        and re.fullmatch(r'sshd: [A-Za-z0-9._-]+@pts/[0-9]+', argv[0]) is not None
    ):
        return 'frozen_sshd_transport_non_candidate'
    return None


def _is_high_recall_ros_candidate(comm: str, argv: tuple[str, ...]) -> bool:
    summary = ' '.join((comm, *argv)).lower()
    executable = Path(argv[0]).name.lower() if argv else comm.lower()
    if executable.startswith('python') or executable in {
        'sh',
        'bash',
        'dash',
        'fish',
        'zsh',
    }:
        return True
    return any(
        marker in summary
        for marker in (
            'ros2',
            'ros-args',
            'launch',
            'component_container',
            'so101',
            'move_group',
            'moveit',
            'mujoco',
            'gazebo',
            'gz sim',
            'rmw_',
            'fastdds',
            'cyclonedds',
            ' dds',
        )
    )


def _fd_snapshot(descriptor: int) -> tuple[int, ...]:
    value = os.fstat(descriptor)
    return (
        value.st_dev,
        value.st_ino,
        value.st_uid,
        stat.S_IMODE(value.st_mode),
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _open_directory_at(parent_fd: int, name: str) -> int:
    try:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ResourceAllocationError(f'SYMLINK_PATH: {name}') from error
        raise ResourceAllocationError(f'DIRECTORY_OPEN_FAILED: {name}') from error


def _verify_sealed_directory(descriptor: int, name: str) -> os.stat_result:
    value = os.fstat(descriptor)
    if not stat.S_ISDIR(value.st_mode):
        raise ResourceAllocationError(f'NOT_DIRECTORY: {name}')
    if value.st_uid != os.getuid():
        raise ResourceAllocationError(f'UNSAFE_DIRECTORY_OWNER: {name}')
    if stat.S_IMODE(value.st_mode) != 0o555:
        raise ResourceAllocationError(f'UNSEALED_DIRECTORY_MODE: {name}')
    return value


def _verify_sealed_regular(descriptor: int, name: str) -> os.stat_result:
    value = os.fstat(descriptor)
    if not stat.S_ISREG(value.st_mode):
        raise ResourceAllocationError(f'NOT_REGULAR_FILE: {name}')
    if value.st_uid != os.getuid():
        raise ResourceAllocationError(f'UNSAFE_FILE_OWNER: {name}')
    if stat.S_IMODE(value.st_mode) != 0o444:
        raise ResourceAllocationError(f'UNSEALED_FILE_MODE: {name}')
    return value


def _strict_json_object(payload: bytes) -> dict[str, object]:
    def reject_constant(value):
        raise ValueError(f'non-finite value: {value}')

    def reject_duplicate_keys(pairs):
        document = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f'duplicate JSON key: {key}')
            document[key] = value
        return document

    document = json.loads(
        payload.decode('utf-8'),
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_keys,
    )
    if not isinstance(document, dict):
        raise ValueError('JSON object required')
    return document


def _read_sealed_json_at(
    parent_fd: int, name: str
) -> tuple[dict[str, object], str, tuple[int, ...]]:
    descriptor = None
    try:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
        value = _verify_sealed_regular(descriptor, name)
        payload = _read_fd(descriptor, _MAX_LIVE_EVIDENCE_BYTES + 1)
        if len(payload) > _MAX_LIVE_EVIDENCE_BYTES:
            raise ResourceAllocationError('LIVE_EVIDENCE_TOO_LARGE')
        if _fd_snapshot(descriptor) != (
            value.st_dev,
            value.st_ino,
            value.st_uid,
            stat.S_IMODE(value.st_mode),
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        ):
            raise ResourceAllocationError(f'PATH_IDENTITY_CHANGED: {name}')
        return (
            _strict_json_object(payload),
            hashlib.sha256(payload).hexdigest(),
            _fd_snapshot(descriptor),
        )
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _verify_stable_snapshot_at(
    parent_fd: int,
    name: str,
    snapshot: tuple[int, ...],
    *,
    is_directory: bool,
    expected_sha256: str | None,
    private: bool = False,
) -> None:
    try:
        visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as error:
        raise ResourceAllocationError(f'PATH_IDENTITY_CHANGED: {name}') from error
    if (
        (
            visible.st_dev,
            visible.st_ino,
            visible.st_uid,
            stat.S_IMODE(visible.st_mode),
            visible.st_size,
            visible.st_mtime_ns,
            visible.st_ctime_ns,
        )
        != snapshot
        or (is_directory and not stat.S_ISDIR(visible.st_mode))
        or (not is_directory and not stat.S_ISREG(visible.st_mode))
    ):
        raise ResourceAllocationError(f'PATH_IDENTITY_CHANGED: {name}')
    if is_directory:
        return
    descriptor = None
    try:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd
        )
        if private:
            _verify_private_regular(descriptor, name)
        else:
            _verify_sealed_regular(descriptor, name)
        payload = _read_fd(descriptor, _MAX_LIVE_EVIDENCE_BYTES + 1)
        if len(payload) > _MAX_LIVE_EVIDENCE_BYTES:
            raise ResourceAllocationError('LIVE_EVIDENCE_TOO_LARGE')
        if _fd_snapshot(descriptor) != snapshot:
            raise ResourceAllocationError(f'PATH_IDENTITY_CHANGED: {name}')
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise ResourceAllocationError(f'CONTENT_CHANGED: {name}')
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_secure_json(path: Path) -> tuple[dict[str, object], str]:
    if not path.is_absolute():
        raise ResourceAllocationError('ABSOLUTE_PATH_REQUIRED')
    parent_fd = _open_trusted_parent(path)
    descriptor = None
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        _verify_private_regular(descriptor, path.name)
        snapshot = _fd_snapshot(descriptor)
        payload = _read_fd(descriptor, _MAX_LIVE_EVIDENCE_BYTES + 1)
        if len(payload) > _MAX_LIVE_EVIDENCE_BYTES:
            raise ResourceAllocationError('LIVE_EVIDENCE_TOO_LARGE')
        if _fd_snapshot(descriptor) != snapshot:
            raise ResourceAllocationError('ACCEPTANCE_IDENTITY_CHANGED')
        os.lseek(descriptor, 0, os.SEEK_SET)
        if _read_fd(descriptor, len(payload) + 1) != payload:
            raise ResourceAllocationError('ACCEPTANCE_CONTENT_CHANGED')
        _verify_stable_snapshot_at(
            parent_fd,
            path.name,
            snapshot,
            is_directory=False,
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            private=True,
        )
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)

    document = _strict_json_object(payload)
    return document, hashlib.sha256(payload).hexdigest()


def _read_current_inputs(
    paths: Mapping[str, Path],
) -> tuple[dict[str, bytes], dict[str, str]]:
    states = []
    try:
        for name in sorted(_PROVENANCE_NAMES):
            path = paths[name]
            if (
                not path.is_absolute()
                or not path.name
                or any(part in {'.', '..'} for part in str(path).split('/'))
            ):
                raise ResourceAllocationError('CURRENT_RUNTIME_PATH_INVALID')
            parent_fd = _open_trusted_parent(path)
            state = {
                'name': name,
                'path': path,
                'parent_fd': parent_fd,
                'descriptor': None,
            }
            states.append(state)
            descriptor = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd
            )
            state['descriptor'] = descriptor
            value = os.fstat(descriptor)
            if not stat.S_ISREG(value.st_mode):
                raise ResourceAllocationError(f'NOT_REGULAR_FILE: {path.name}')
            if value.st_uid != os.getuid():
                raise ResourceAllocationError(f'UNSAFE_FILE_OWNER: {path.name}')
            if stat.S_IMODE(value.st_mode) != 0o400:
                raise ResourceAllocationError(f'UNSAFE_FILE_MODE: {path.name}')
            snapshot = _fd_snapshot(descriptor)
            payload = _read_fd(descriptor, _MAX_LIVE_EVIDENCE_BYTES + 1)
            if len(payload) > _MAX_LIVE_EVIDENCE_BYTES:
                raise ResourceAllocationError('CURRENT_RUNTIME_INPUT_TOO_LARGE')
            if _fd_snapshot(descriptor) != snapshot:
                raise ResourceAllocationError(
                    f'PATH_IDENTITY_CHANGED: {path.name}'
                )
            state['snapshot'] = snapshot
            state['payload'] = payload

        for state in states:
            path = state['path']
            parent_fd = state['parent_fd']
            descriptor = state['descriptor']
            snapshot = state['snapshot']
            payload = state['payload']
            visible = os.stat(
                path.name, dir_fd=parent_fd, follow_symlinks=False
            )
            if (
                (
                    visible.st_dev,
                    visible.st_ino,
                    visible.st_uid,
                    stat.S_IMODE(visible.st_mode),
                    visible.st_size,
                    visible.st_mtime_ns,
                    visible.st_ctime_ns,
                )
                != snapshot
                or not stat.S_ISREG(visible.st_mode)
            ):
                raise ResourceAllocationError(
                    f'PATH_IDENTITY_CHANGED: {path.name}'
                )
            os.lseek(descriptor, 0, os.SEEK_SET)
            if (
                _read_fd(descriptor, _MAX_LIVE_EVIDENCE_BYTES + 1) != payload
                or _fd_snapshot(descriptor) != snapshot
            ):
                raise ResourceAllocationError(f'CONTENT_CHANGED: {path.name}')
            second_descriptor = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd
            )
            try:
                if _fd_snapshot(second_descriptor) != snapshot:
                    raise ResourceAllocationError(
                        f'PATH_IDENTITY_CHANGED: {path.name}'
                    )
                if (
                    _read_fd(
                        second_descriptor, _MAX_LIVE_EVIDENCE_BYTES + 1
                    )
                    != payload
                    or _fd_snapshot(second_descriptor) != snapshot
                ):
                    raise ResourceAllocationError(
                        f'CONTENT_CHANGED: {path.name}'
                    )
            finally:
                os.close(second_descriptor)
        payloads = {state['name']: state['payload'] for state in states}
        hashes = {
            name: hashlib.sha256(payload).hexdigest()
            for name, payload in payloads.items()
        }
        return payloads, hashes
    except OSError as error:
        raise ResourceAllocationError('CURRENT_RUNTIME_INPUT_UNAVAILABLE') from error
    finally:
        for state in reversed(states):
            descriptor = state['descriptor']
            if descriptor is not None:
                os.close(descriptor)
            os.close(state['parent_fd'])


def _write_manifest_at(
    root_fd: int, name: str, document: Mapping[str, object]
) -> None:
    payload = (
        json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + '\n'
    ).encode('utf-8')
    temporary = f'.{name}.{os.getpid()}.{uuid.uuid4().hex}.tmp'
    descriptor = None
    created = False
    try:
        descriptor = os.open(
            temporary,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=root_fd,
        )
        created = True
        _verify_private_regular(descriptor, temporary)
        _replace_fd_contents(descriptor, payload)
    except Exception as error:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        if created:
            try:
                os.unlink(temporary, dir_fd=root_fd)
                os.fsync(root_fd)
            except OSError as cleanup_error:
                raise ResourceAllocationError('MANIFEST_CLEANUP_FAILED') from cleanup_error
        if isinstance(error, ResourceAllocationError):
            raise
        raise ResourceAllocationError('MANIFEST_WRITE_FAILED') from error
    finally:
        if descriptor is not None:
            os.close(descriptor)

    try:
        os.link(
            temporary,
            name,
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
            follow_symlinks=False,
        )
    except FileExistsError as error:
        try:
            os.unlink(temporary, dir_fd=root_fd)
            os.fsync(root_fd)
        except OSError as cleanup_error:
            raise ResourceAllocationError('MANIFEST_CLEANUP_FAILED') from cleanup_error
        raise ResourceAllocationError(f'MANIFEST_CONFLICT: {name}') from error
    except OSError as error:
        try:
            os.unlink(temporary, dir_fd=root_fd)
            os.fsync(root_fd)
        except OSError as cleanup_error:
            raise ResourceAllocationError('MANIFEST_CLEANUP_FAILED') from cleanup_error
        raise ResourceAllocationError('MANIFEST_PUBLISH_FAILED') from error

    try:
        os.fsync(root_fd)
    except OSError as error:
        raise ResourceAllocationError('PUBLICATION_UNCERTAIN') from error

    try:
        os.unlink(temporary, dir_fd=root_fd)
        os.fsync(root_fd)
    except OSError as error:
        raise ResourceAllocationError('TEMP_CLEANUP_UNCERTAIN') from error


def _process_starttime_ticks() -> int:
    try:
        line = Path('/proc/self/stat').read_text(encoding='ascii')
        closing = line.rfind(')')
        fields = line[closing + 2 :].split()
        value = int(fields[19])
    except (OSError, UnicodeError, ValueError, IndexError) as error:
        raise ResourceAllocationError('PROCESS_STARTTIME_UNAVAILABLE') from error
    if value <= 0:
        raise ResourceAllocationError('PROCESS_STARTTIME_UNAVAILABLE')
    return value


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--worker-count', type=int, default=_DEFAULT_WORKER_COUNT)
    parser.add_argument('--live-headroom-evidence', type=Path)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true', required=True)
    return parser


def main(argv=None, *, claim_root: Path | None = None) -> int:
    """Write a resource manifest without starting ROS, MuJoCo or Broker."""
    arguments = _parser().parse_args(argv)
    allocator = None
    try:
        config = load_parallel_runtime_config(arguments.config)
        allocator = WorkerResourceAllocator(
            config,
            arguments.evidence_root,
            claim_root=claim_root,
            live_headroom_evidence=arguments.live_headroom_evidence,
        )
        manifest = allocator.allocate(arguments.worker_count)
        document = manifest.to_dict()
        allocator.write_manifest()
    except (ResourceAllocationError, ValueError, OSError) as error:
        failure = {'admitted': False, 'error': str(error)}
        if isinstance(error, ResourceAllocationError) and error.admission is not None:
            failure['admission'] = error.admission.to_dict()
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 2
    finally:
        if allocator is not None:
            allocator.close()
    print(json.dumps(document, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
