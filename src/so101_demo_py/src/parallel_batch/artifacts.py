"""Durable mode-specific sealing; recovery never edits sealed evidence.

Each workspace has one owning producer, who must finish external writes before
sealing. Read-only permissions prevent accidental writes; verification detects
later changes even by an owner who can change permissions. The coordinator
supplies trusted Worker roots to the read-only result adapter.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import ClassVar, Mapping

from .contracts import (
    AttemptIdentity, AttemptStatus, LeaseIdentity, RunMode, ValidationIdentity,
    ValidationStatus,
)
from ..runtime.task_artifacts import atomic_json, fsync_directory


class ArtifactError(ValueError):
    """A sealed artifact contract was violated."""


_ATTEMPT_MANIFEST = 'attempt_result_manifest.json'
_VALIDATION_MANIFEST = 'validation_result_manifest.json'
_WORKSPACE_IDENTITY = 'workspace_identity.json'
_RESERVED = {_ATTEMPT_MANIFEST, _VALIDATION_MANIFEST, _WORKSPACE_IDENTITY}


def _json_bytes(document):
    def validate_keys(value):
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ArtifactError('INVALID_JSON_KEY')
            for child in value.values():
                validate_keys(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                validate_keys(child)

    validate_keys(document)
    try:
        return json.dumps(document, sort_keys=True, separators=(',', ':'),
                          allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as error:
        raise ArtifactError('INVALID_JSON') from error


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or '\x00' in value
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ArtifactError('UNSAFE_PATH')
    return Path(value)


def _safe_path(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ArtifactError('UNSAFE_PATH')
    for item in (*reversed(path.parents), path):
        if item.is_symlink():
            raise ArtifactError('SYMLINK_PATH')
    return path


def _read_json(path):
    _safe_path(path)
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise ArtifactError('NOT_REGULAR_FILE')
        result = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(result, dict):
            raise ArtifactError('INVALID_JSON')
        _json_bytes(result)
        return result
    except (OSError, UnicodeError, ValueError) as error:
        raise ArtifactError(f'INVALID_OR_MISSING_JSON: {path.name}') from error


def _worker_root(path):
    root = _safe_path(Path(path))
    if any((parent / _WORKSPACE_IDENTITY).exists() for parent in (root, *root.parents)):
        raise ArtifactError('WORKER_ROOT_INSIDE_ARTIFACT_TREE')
    return root


def _layout(identity):
    if type(identity) is AttemptIdentity:
        return 'attempts', identity.attempt_id, _ATTEMPT_MANIFEST, 'attempt-result.json'
    if type(identity) is ValidationIdentity:
        return ('validations', identity.validation_id, _VALIDATION_MANIFEST,
                'validation-result.json')
    raise ArtifactError('WRONG_IDENTITY')


def _mode(identity, run_mode):
    _layout(identity)
    if (not isinstance(run_mode, RunMode)
            or (type(identity) is AttemptIdentity) != (run_mode is RunMode.EXECUTE)):
        raise ArtifactError('WRONG_RUN_MODE')


def _metadata(identity, run_mode, reset_epoch, source_stamp):
    _mode(identity, run_mode)
    if not isinstance(reset_epoch, str) or not reset_epoch.strip():
        raise ArtifactError('RESET_EPOCH')
    if not isinstance(source_stamp, Mapping) or not source_stamp:
        raise ArtifactError('SOURCE_STAMP')
    return {'identity': asdict(identity), 'run_mode': run_mode.value,
            'worker_slot': identity.worker_id, 'reset_epoch': reset_epoch,
            'source_stamp': json.loads(_json_bytes(dict(source_stamp)))}


def _inventory(root, manifest_name, producer_pid, producer_pgid):
    _safe_path(root)
    if not root.is_dir():
        raise ArtifactError('MISSING_TREE')
    files, directories = [], []
    for path in sorted(root.rglob('*')):
        _safe_path(path)
        relative = path.relative_to(root).as_posix()
        _relative(relative)
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            directories.append(relative)
        elif stat.S_ISREG(mode):
            if relative == manifest_name:
                continue
            if path.name in {_ATTEMPT_MANIFEST, _VALIDATION_MANIFEST}:
                raise ArtifactError('RESERVED_MANIFEST')
            payload = path.read_bytes()
            files.append({'relative_path': relative, 'size': len(payload),
                          'sha256': hashlib.sha256(payload).hexdigest(),
                          'producer_pid': producer_pid, 'producer_pgid': producer_pgid})
        else:
            raise ArtifactError('NOT_REGULAR_FILE')
    return files, directories


def _tree_hash(files, directories):
    return hashlib.sha256(_json_bytes({'files': files, 'directories': directories})).hexdigest()


def _status(root, identity):
    document = _read_json(root / _layout(identity)[3])
    cls = AttemptStatus if type(identity) is AttemptIdentity else ValidationStatus
    try:
        return cls(document['status']).value
    except (KeyError, ValueError, TypeError) as error:
        raise ArtifactError('INVALID_RESULT_STATUS') from error


@dataclass(frozen=True)
class _Sealed:
    path: Path
    identity: AttemptIdentity | ValidationIdentity

    def __post_init__(self):
        expected = AttemptIdentity if type(self) is SealedAttempt else ValidationIdentity
        if type(self.identity) is not expected:
            raise ArtifactError('WRONG_IDENTITY')

    def write_json(self, relative_path, document):
        """Sealed evidence cannot be edited through an artifact handle."""
        raise ArtifactError('SEALED_IMMUTABLE')

    def verify(self):
        """Read back every file and its full mode-specific identity."""
        return _verify(self.path, self.identity)


@dataclass(frozen=True)
class SealedAttempt(_Sealed):
    """An immutable physical attempt, never a validation result."""


@dataclass(frozen=True)
class SealedValidation(_Sealed):
    """An immutable dry-run or plan-only result."""


def _verify(path, identity):
    folder, execution_id, manifest_name, result_name = _layout(identity)
    path = _safe_path(Path(path))
    if path.parts[-4:] != (folder, identity.point_id, execution_id, 'sealed'):
        raise ArtifactError('WRONG_SEALED_PATH')
    manifest = _read_json(path / manifest_name)
    metadata = _read_json(path / _WORKSPACE_IDENTITY)
    if any(_json_bytes(item.get('identity')) != _json_bytes(asdict(identity))
           for item in (manifest, metadata)):
        raise ArtifactError('IDENTITY_MISMATCH')
    try:
        mode = RunMode(manifest['run_mode'])
        expected = _metadata(identity, mode, manifest['reset_epoch'], manifest['source_stamp'])
        for name, value in expected.items():
            if any(_json_bytes(item.get(name)) != _json_bytes(value)
                   for item in (manifest, metadata)):
                raise ArtifactError('IDENTITY_METADATA_MISMATCH')
        pid, pgid = metadata['producer_pid'], metadata['producer_pgid']
        if any(type(value) is not int or value <= 0 for value in (pid, pgid)):
            raise ArtifactError('PRODUCER_IDENTITY')
        if any(type(manifest.get(name)) is not int or manifest[name] != metadata[name]
               for name in ('producer_pid', 'producer_pgid')):
            raise ArtifactError('PRODUCER_IDENTITY_MISMATCH')
        files, directories = _inventory(path, manifest_name, pid, pgid)
        for entry in manifest['files']:
            _relative(entry['relative_path'])
        if (type(manifest['schema_version']) is not int or manifest['schema_version'] != 1
                or _json_bytes(manifest['files']) != _json_bytes(files)
                or manifest['directories'] != directories
                or manifest['tree_sha256'] != _tree_hash(files, directories)):
            raise ArtifactError('TREE_HASH_OR_SIZE_MISMATCH')
        required = manifest['required']
        if not isinstance(required, list) or result_name not in required:
            raise ArtifactError('MISSING_REQUIRED_RESULT')
        names = {entry['relative_path'] for entry in files}
        for name in required:
            _relative(name)
            if name not in names:
                raise ArtifactError('MISSING_REQUIRED_ARTIFACT')
        if manifest['status'] != _status(path, identity):
            raise ArtifactError('RESULT_STATUS_MISMATCH')
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise ArtifactError(f'INVALID_MANIFEST: {error}') from error
    cls = SealedAttempt if type(identity) is AttemptIdentity else SealedValidation
    return cls(path, identity)


def verify_attempt(path: Path, identity: AttemptIdentity) -> SealedAttempt:
    """Validate a physical result's identity, inventory, sizes, and hashes."""
    if type(identity) is not AttemptIdentity:
        raise ArtifactError('WRONG_IDENTITY')
    return _verify(path, identity)


def verify_validation(path: Path, identity: ValidationIdentity) -> SealedValidation:
    """Validate a validation result without producing physical evidence."""
    if type(identity) is not ValidationIdentity:
        raise ArtifactError('WRONG_IDENTITY')
    return _verify(path, identity)


@dataclass(frozen=True)
class _Workspace:
    path: Path
    identity: AttemptIdentity | ValidationIdentity
    _metadata: dict
    identity_type: ClassVar[type | None] = None

    def __post_init__(self):
        if type(self.identity) is not self.identity_type:
            raise ArtifactError('WRONG_IDENTITY')

    @classmethod
    def create(cls, root, identity, *, reset_epoch, source_stamp, run_mode):
        """Allocate/resume only the matching identity under the current Worker root."""
        if type(identity) is not cls.identity_type:
            raise ArtifactError('WRONG_IDENTITY')
        root = _worker_root(root)
        metadata = _metadata(identity, run_mode, reset_epoch, source_stamp)
        folder, execution_id, _, _ = _layout(identity)
        parent = _safe_path(root / folder / identity.point_id / execution_id)
        working, sealed = parent / 'working', parent / 'sealed'
        if sealed.exists() or sealed.is_symlink():
            _verify(sealed, identity)
        prior = sealed if sealed.exists() else working
        if prior.exists():
            existing = _read_json(prior / _WORKSPACE_IDENTITY)
            if any(existing.get(key) != value for key, value in metadata.items()):
                raise ArtifactError('IDENTITY_METADATA_MISMATCH')
            metadata = existing
        else:
            metadata.update(producer_pid=os.getpid(), producer_pgid=os.getpgid(os.getpid()))
            working.mkdir(parents=True)
            atomic_json(working / _WORKSPACE_IDENTITY, metadata)
            for directory in (parent, *parent.parents):
                fsync_directory(directory)
                if directory == root.parent:
                    break
        return cls(working, identity, metadata)

    def write_json(self, relative_path, document):
        """Write a complete JSON artifact before sealing starts."""
        relative = _relative(relative_path)
        if relative.name in _RESERVED:
            raise ArtifactError('RESERVED_ARTIFACT')
        if (self.path.parent / 'sealed').exists():
            raise ArtifactError('SEALED_IMMUTABLE')
        path = _safe_path(self.path / relative)
        if not self.path.is_dir() or (self.path / _layout(self.identity)[2]).exists():
            raise ArtifactError('SEALED_IMMUTABLE')
        atomic_json(path, json.loads(_json_bytes(document)))


class AttemptWorkspace(_Workspace):
    """Worker-local physical attempt workspace."""

    identity_type = AttemptIdentity

    def seal(self, *, required=()):
        """Publish only a physical attempt manifest."""
        return seal_attempt(self, required=required)


class ValidationWorkspace(_Workspace):
    """Worker-local dry-run or plan-only validation workspace."""

    identity_type = ValidationIdentity

    def seal(self, *, required=()):
        """Publish only a validation manifest."""
        return seal_validation(self, required=required)


def _seal(workspace, required):
    root, identity = workspace.path, workspace.identity
    _, _, manifest_name, result_name = _layout(identity)
    required = sorted({*required, result_name})
    for name in required:
        _relative(name)
    sealed = _safe_path(root.parent / 'sealed')
    if sealed.exists():
        result = _verify(sealed, identity)
        if not root.exists():
            manifest = _read_json(sealed / manifest_name)
            if not set(required).issubset(item['relative_path'] for item in manifest['files']):
                raise ArtifactError('MISSING_REQUIRED_ARTIFACT')
            fsync_directory(root.parent)
            return result
    metadata = _read_json(root / _WORKSPACE_IDENTITY)
    if metadata != workspace._metadata:
        raise ArtifactError('IDENTITY_METADATA_MISMATCH')
    files, directories = _inventory(root, manifest_name,
                                    metadata['producer_pid'], metadata['producer_pgid'])
    names = {entry['relative_path'] for entry in files}
    if not set(required).issubset(names):
        raise ArtifactError('MISSING_REQUIRED_ARTIFACT')
    manifest = {**metadata, 'schema_version': 1, 'required': required,
                'files': files, 'directories': directories,
                'tree_sha256': _tree_hash(files, directories),
                'status': _status(root, identity)}
    manifest_path = root / manifest_name
    if manifest_path.exists():
        if _read_json(manifest_path) != manifest:
            raise ArtifactError('TREE_OR_IDENTITY_MISMATCH')
    else:
        atomic_json(manifest_path, manifest)
    if sealed.exists():
        if _read_json(sealed / manifest_name) != manifest:
            raise ArtifactError('TREE_OR_IDENTITY_MISMATCH')
        fsync_directory(root.parent)
        return _verify(sealed, identity)
    # A pre-rename crash leaves a frozen working tree that can be retried without
    # rewriting its manifest. All file and directory metadata is synced first.
    for path in sorted(root.rglob('*')):
        _safe_path(path)
        if path.is_file():
            path.chmod(0o444)
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
    for path in sorted((root / name for name in directories),
                       key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o555)
        fsync_directory(path)
    root.chmod(0o555)
    fsync_directory(root)
    os.replace(root, sealed)
    fsync_directory(root.parent)
    return _verify(sealed, identity)


def seal_attempt(workspace: AttemptWorkspace, *, required=()) -> SealedAttempt:
    """Fsync and atomically publish an attempt, or verify an exact prior seal."""
    if type(workspace) is not AttemptWorkspace:
        raise ArtifactError('WRONG_IDENTITY')
    return _seal(workspace, required)


def seal_validation(workspace: ValidationWorkspace, *, required=()) -> SealedValidation:
    """Fsync and atomically publish a validation with a disjoint manifest."""
    if type(workspace) is not ValidationWorkspace:
        raise ArtifactError('WRONG_IDENTITY')
    return _seal(workspace, required)


def write_recovery_receipt(root, identity, *, succeeded):
    """Append a unique recovery receipt outside both kinds of sealed evidence."""
    folder, execution_id, _, _ = _layout(identity)
    if type(succeeded) is not bool:
        raise ArtifactError('BOOLEAN_RECOVERY_SUCCESS')
    root = _worker_root(root)
    destination = _safe_path(root / 'recoveries' / folder / identity.point_id
                             / execution_id / uuid.uuid4().hex)
    destination.mkdir(parents=True)
    path = destination / 'recovery_receipt.json'
    atomic_json(path, {
        'identity': asdict(identity), 'succeeded': succeeded,
        'producer_pid': os.getpid(), 'producer_pgid': os.getpgid(os.getpid()),
    })
    for parent in destination.parents:
        fsync_directory(parent)
        if parent == Path(root):
            break
    return path


class SealedResultAdapter:
    """Coordinator result port; Task 11 supplies the trusted Worker-root mapping.

    discover accepts only the deterministic execution parent reserved by the
    journal: Worker root / attempts|validations / point / execution ID. It never
    recursively scans other workspaces or changes coordinator history.
    """

    def __init__(self, worker_roots: Mapping[str, Path], run_mode: RunMode):
        """Bind verification to trusted Worker roots and a single batch mode."""
        if not isinstance(run_mode, RunMode):
            raise ArtifactError('WRONG_RUN_MODE')
        self.worker_roots = {key: _safe_path(Path(value)) for key, value in worker_roots.items()}
        self.run_mode = run_mode

    def _expected(self, lease):
        if not isinstance(lease, LeaseIdentity) or lease.worker_id not in self.worker_roots:
            raise ArtifactError('LEASE_IDENTITY_MISMATCH')
        data = asdict(lease)
        del data['lease_issued_monotonic_s'], data['lease_deadline_monotonic_s']
        cls = AttemptIdentity
        if self.run_mode is not RunMode.EXECUTE:
            data['validation_id'] = data.pop('attempt_id')
            cls = ValidationIdentity
        identity = cls(**data)
        folder, execution_id, _, _ = _layout(identity)
        parent = self.worker_roots[lease.worker_id] / folder / lease.point_id / execution_id
        return identity, parent

    def verify(self, lease, location, run_mode):
        """Verify lease, registered location, mode, status, and complete tree hash."""
        if run_mode is not self.run_mode:
            raise ArtifactError('WRONG_RUN_MODE')
        identity, parent = self._expected(lease)
        path = _safe_path(Path(location))
        if path != parent / 'sealed':
            raise ArtifactError('LEASE_LOCATION_MISMATCH')
        _verify(path, identity)
        manifest_path = path / _layout(identity)[2]
        manifest = _read_json(manifest_path)
        if manifest['run_mode'] != run_mode.value:
            raise ArtifactError('WRONG_RUN_MODE')
        return {'status': manifest['status'],
                'sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest()}

    def discover(self, lease, workspace):
        """Return a fully verified seal only at the journal-reserved location."""
        try:
            _, parent = self._expected(lease)
            if _safe_path(Path(workspace)) != parent:
                return None
            location = str(parent / 'sealed')
            self.verify(lease, location, self.run_mode)
            return location
        except (ArtifactError, OSError):
            return None
