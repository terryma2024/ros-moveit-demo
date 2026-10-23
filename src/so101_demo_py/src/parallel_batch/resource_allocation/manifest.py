"""The start guard admission, the resource manifest and its writer."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Mapping
import uuid

from so101_demo.parallel_batch.resource_allocation.filesystem import (
    _freeze_json,
    _replace_fd_contents,
    _thaw_json,
    _verify_private_regular,
)
from so101_demo.parallel_batch.resource_allocation.models import (
    ResourceAllocationError,
    WorkerResources,
)


@dataclass(frozen=True, slots=True)
class StartGuardAdmission:
    """The allocator's record of the one bounded startup check it actually ran."""

    status: str
    reason: str
    checks: Mapping[str, object]
    observed_monotonic_s: float
    gpu_uuid: str | None
    cleanup_state: str

    def __post_init__(self) -> None:
        if self.status not in ('PASS', 'WARN', 'FAIL'):
            raise ValueError('START_GUARD_STATUS')
        if self.cleanup_state not in ('CLEAR', 'PROBE_CLEANUP_BLOCKED'):
            raise ValueError('START_GUARD_CLEANUP_STATE')
        object.__setattr__(self, 'checks', _freeze_json(dict(self.checks)))

    @property
    def admitted(self) -> bool:
        return self.status != 'FAIL' and self.cleanup_state == 'CLEAR'

    def to_dict(self) -> dict:
        return {
            'status': self.status,
            'reason': self.reason,
            'checks': _thaw_json(self.checks),
            'observed_monotonic_s': self.observed_monotonic_s,
            'gpu_uuid': self.gpu_uuid,
            'cleanup_state': self.cleanup_state,
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
    admission: StartGuardAdmission
    domain_claim_scope: str
    domain_claims: tuple[Mapping[str, object], ...]
    process_scan: Mapping[str, object]
    start_guard: Mapping[str, object] | None
    workers: tuple[WorkerResources, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, 'domain_claims', tuple(_freeze_json(value) for value in self.domain_claims)
        )
        object.__setattr__(self, 'process_scan', _freeze_json(self.process_scan))
        if self.start_guard is not None:
            object.__setattr__(
                self, 'start_guard', _freeze_json(self.start_guard)
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
            'start_guard': _thaw_json(self.start_guard),
            'workers': [worker.to_dict() for worker in self.workers],
        }


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
        from so101_demo.parallel_batch.start_guard_probe import read_process_identity

        identity = read_process_identity(os.getpid())
        if identity is None:
            raise ResourceAllocationError('PROCESS_STARTTIME_UNAVAILABLE') from error
        value = identity.start_time_ticks
    if value <= 0:
        raise ResourceAllocationError('PROCESS_STARTTIME_UNAVAILABLE')
    return value


def _session_id(worker_id: str, generation: int) -> str:
    return f'{worker_id}-g{generation:04d}-{uuid.uuid4().hex}'
