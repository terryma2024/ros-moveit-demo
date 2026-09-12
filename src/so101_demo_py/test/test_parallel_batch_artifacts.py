"""Immutable result publication using real files, with crash-boundary injection."""

import hashlib
import json
import os
import shutil
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path

import pytest

from so101_demo.parallel_batch import artifacts as api
from so101_demo.parallel_batch.contracts import (
    AttemptIdentity, BatchRequest, LeaseIdentity, PointStatus, RunMode, ValidationIdentity,
    load_parallel_runtime_config,
)
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal


def identity(validation=False):
    """Build a complete identity from hand-picked generation and epoch values."""
    cls = ValidationIdentity if validation else AttemptIdentity
    return cls('batch-a', 3, 'w1', 2, 'point-1', 'result-1', 4)


def lease():
    """Add lease timing without changing the immutable execution identity."""
    return LeaseIdentity(**asdict(identity()), lease_issued_monotonic_s=1,
                         lease_deadline_monotonic_s=301)


def workspace(root, *, validation=False, mode=None, who=None):
    """Create a real workspace with explicit reset and source provenance."""
    cls = api.ValidationWorkspace if validation else api.AttemptWorkspace
    return cls.create(root, who or identity(validation), reset_epoch='reset-7',
                      source_stamp={'commit': 'a' * 40, 'overlay': '/isolated/install'},
                      run_mode=mode or (RunMode.PLAN_ONLY if validation else RunMode.EXECUTE))


def populated(root, **kwargs):
    """Write a minimal reset and the mode-specific result through the public API."""
    result = workspace(root, **kwargs)
    result.write_json('initial_state/reset.json', {'epoch': 'reset-7'})
    validation = kwargs.get('validation', False)
    result.write_json('validation-result.json' if validation else 'attempt-result.json',
                      {'status': 'VALIDATION_PASSED' if validation else 'FAILED'})
    return result


def digest_tree(root):
    """Snapshot all file bytes independently of the production manifest."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_sealed_attempt_is_immutable_and_recovery_is_separate(tmp_path):
    """Late artifact writes and recovery must not alter committed evidence."""
    work = populated(tmp_path)
    sealed = work.seal(required=('initial_state/reset.json', 'attempt-result.json'))
    before = digest_tree(sealed.path)
    receipt = api.write_recovery_receipt(tmp_path, sealed.identity, succeeded=True)
    assert receipt.is_relative_to(tmp_path / 'recoveries')
    assert json.loads(receipt.read_text())['identity'] == asdict(identity())
    assert digest_tree(sealed.path) == before
    for target in (work, sealed):
        with pytest.raises(api.ArtifactError, match='SEALED_IMMUTABLE'):
            target.write_json('late.json', {})
    assert all(not (p.stat().st_mode & 0o222) for p in [sealed.path, *sealed.path.rglob('*')])


@pytest.mark.parametrize('validation,mode,folder,manifest_name', [
    (False, RunMode.EXECUTE, 'attempts', 'attempt_result_manifest.json'),
    (True, RunMode.PLAN_ONLY, 'validations', 'validation_result_manifest.json'),
    (True, RunMode.DRY_RUN, 'validations', 'validation_result_manifest.json'),
])
def test_mode_specific_layout_and_manifest_provenance(
        tmp_path, validation, mode, folder, manifest_name):
    """Mode, identity, process, reset, and source provenance survive publication."""
    root = tmp_path / 'workers/w1'
    work = populated(root, validation=validation, mode=mode)
    assert work.path == root / folder / 'point-1/result-1/working'
    sealed = work.seal(required=('initial_state/reset.json',))
    assert sealed.path == root / folder / 'point-1/result-1/sealed'
    manifest = json.loads((sealed.path / manifest_name).read_text())
    assert manifest['identity'] == asdict(identity(validation))
    assert manifest['worker_slot'] == 'w1'
    assert manifest['reset_epoch'] == 'reset-7'
    assert manifest['source_stamp'] == {'commit': 'a' * 40, 'overlay': '/isolated/install'}
    assert manifest['run_mode'] == mode.value
    entry = next(item for item in manifest['files']
                 if item['relative_path'] == 'initial_state/reset.json')
    payload = (sealed.path / entry['relative_path']).read_bytes()
    assert entry['size'] == len(payload)
    assert entry['sha256'] == hashlib.sha256(payload).hexdigest()
    assert entry['producer_pid'] == os.getpid()
    assert entry['producer_pgid'] == os.getpgid(os.getpid())
    assert sealed.verify().identity == sealed.identity
    other = 'attempt_result_manifest.json' if validation else 'validation_result_manifest.json'
    assert not (sealed.path / other).exists()


@pytest.mark.parametrize('validation', [False, True])
def test_identity_and_seal_functions_cannot_cross_convert(tmp_path, validation):
    """A validation cannot enter the physical layout or physical seal function."""
    with pytest.raises(api.ArtifactError, match='IDENTITY'):
        workspace(tmp_path, validation=validation, who=identity(not validation))
    work = populated(tmp_path, validation=validation)
    wrong_seal = api.seal_attempt if validation else api.seal_validation
    with pytest.raises(api.ArtifactError, match='IDENTITY'):
        wrong_seal(work)
    other_manifest = ('attempt_result_manifest.json' if validation
                      else 'validation_result_manifest.json')
    with pytest.raises(api.ArtifactError, match='RESERVED'):
        work.write_json(other_manifest, {})


@pytest.mark.parametrize('validation,mode', [(False, RunMode.PLAN_ONLY), (True, RunMode.EXECUTE)])
def test_workspace_rejects_wrong_run_mode(tmp_path, validation, mode):
    """An identity cannot be published under an incompatible run mode."""
    with pytest.raises(api.ArtifactError, match='RUN_MODE'):
        workspace(tmp_path, validation=validation, mode=mode)


def test_required_artifact_and_result_cannot_be_omitted(tmp_path):
    """Missing evidence must retain working state without publishing a seal."""
    work = workspace(tmp_path)
    with pytest.raises(api.ArtifactError, match='MISSING'):
        work.seal(required=('initial_state/reset.json',))
    assert work.path.is_dir()
    assert not (work.path.parent / 'sealed').exists()


@pytest.mark.parametrize('bad', [
    '../escape', '/tmp/escape', './file', 'a/../b', 'a//b', 'a/./b', 'a\\b', '', 'a/',
])
def test_writes_and_required_paths_reject_traversal(tmp_path, bad):
    """Neither a write nor a required-path declaration may escape the workspace."""
    work = populated(tmp_path)
    with pytest.raises(api.ArtifactError, match='PATH'):
        work.write_json(bad, {})
    with pytest.raises(api.ArtifactError, match='PATH'):
        work.seal(required=(bad,))


@pytest.mark.parametrize('kind', ['file', 'directory', 'dangling', 'root', 'parent'])
def test_symlinks_never_enter_artifact_tree(tmp_path, kind):
    """Symlinked roots, parents, files, and directories must all fail closed."""
    outside = tmp_path / 'outside'
    outside.mkdir()
    if kind in ('root', 'parent'):
        link = tmp_path / 'link'
        link.symlink_to(outside, target_is_directory=True)
        with pytest.raises(api.ArtifactError, match='SYMLINK'):
            workspace(link if kind == 'root' else link / 'worker')
        return
    work = populated(tmp_path / 'worker')
    target = outside / 'secret'
    if kind == 'file':
        target.write_text('secret')
    elif kind == 'directory':
        target = outside
    (work.path / 'link').symlink_to(target)
    with pytest.raises(api.ArtifactError, match='SYMLINK'):
        work.seal()
    with pytest.raises(api.ArtifactError, match='SYMLINK'):
        work.write_json('link' if kind != 'directory' else 'link/escape.json', {})


@pytest.mark.parametrize('damage', ['missing', 'size', 'hash', 'extra', 'symlink', 'traversal'])
def test_verify_rejects_tree_or_manifest_tampering(tmp_path, damage):
    """A matching identity cannot authorize missing, changed, or redirected files."""
    sealed = populated(tmp_path).seal()
    for item in [sealed.path, *sealed.path.rglob('*')]:
        item.chmod(0o755 if item.is_dir() else 0o644)
    target = sealed.path / 'initial_state/reset.json'
    if damage == 'missing':
        target.unlink()
    elif damage == 'size':
        target.write_text('x')
    elif damage == 'hash':
        target.write_bytes(b'x' * target.stat().st_size)
    elif damage == 'extra':
        (sealed.path / 'extra.json').write_text('{}')
    elif damage == 'symlink':
        target.unlink()
        target.symlink_to(sealed.path / 'attempt-result.json')
    else:
        path = sealed.path / 'attempt_result_manifest.json'
        doc = json.loads(path.read_text())
        doc['files'][0]['relative_path'] = '../escape'
        path.write_text(json.dumps(doc))
    with pytest.raises(api.ArtifactError):
        sealed.verify()


def test_crash_before_rename_preserves_working_and_retry_succeeds(tmp_path, monkeypatch):
    """A interrupted publication retains a retryable complete working tree."""
    work = populated(tmp_path)
    original = os.replace

    def fail_publication(source, destination):
        if Path(source) == work.path:
            raise OSError('injected pre-rename crash')
        return original(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(os, 'replace', fail_publication)
        with pytest.raises(OSError, match='pre-rename'):
            work.seal()
    assert work.path.is_dir()
    assert not (work.path.parent / 'sealed').exists()
    assert work.seal().verify().identity == identity()


def test_file_and_directory_fsync_precede_rename_and_parent_follows(tmp_path, monkeypatch):
    """Visibility must follow file and working-directory durability."""
    work = populated(tmp_path)
    events = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        events.append(('fsync', Path(os.readlink(f'/proc/self/fd/{fd}'))))
        return real_fsync(fd)

    def rename(source, destination):
        events.append(('replace', Path(source), Path(destination)))
        return real_replace(source, destination)

    monkeypatch.setattr(os, 'fsync', fsync)
    monkeypatch.setattr(os, 'replace', rename)
    sealed = work.seal()
    publication = events.index(('replace', work.path, sealed.path))
    for item in sealed.path.rglob('*'):
        assert ('fsync', work.path / item.relative_to(sealed.path)) in events[:publication]
    assert ('fsync', work.path) in events[:publication]
    assert events[publication + 1] == ('fsync', work.path.parent)


def test_repeat_seal_accepts_exact_identity_and_tree_only(tmp_path):
    """Idempotency cannot replace prior evidence or authorize a new generation."""
    work = populated(tmp_path)
    sealed = work.seal()
    before = digest_tree(sealed.path)
    assert work.seal().path == sealed.path
    assert workspace(tmp_path).seal().path == sealed.path
    assert digest_tree(sealed.path) == before
    with pytest.raises(api.ArtifactError, match='IDENTITY'):
        workspace(tmp_path, who=replace(identity(), worker_generation=3))
    shutil.copytree(sealed.path, work.path)
    for item in [work.path, *work.path.rglob('*')]:
        item.chmod(0o755 if item.is_dir() else 0o644)
    assert work.seal().path == sealed.path
    (work.path / 'attempt-result.json').write_text('{"status":"PASSED"}')
    with pytest.raises(api.ArtifactError):
        work.seal()
    assert digest_tree(sealed.path) == before


@pytest.mark.parametrize('field,value', [
    ('coordinator_epoch', 4), ('worker_generation', 3),
    ('lease_generation', 5), ('worker_id', 'w2'), ('point_id', 'point-2'),
    ('attempt_id', 'result-2'), ('batch_id', 'batch-b'),
])
def test_verifier_rejects_any_lease_identity_mismatch(tmp_path, field, value):
    """Every immutable lease field must match the artifact being committed."""
    root = tmp_path / 'workers/w1'
    sealed = populated(root).seal()
    adapter = api.SealedResultAdapter({'w1': root}, RunMode.EXECUTE)
    with pytest.raises(api.ArtifactError):
        adapter.verify(replace(lease(), **{field: value}), str(sealed.path), RunMode.EXECUTE)


@pytest.mark.parametrize('validation', [False, True])
def test_adapter_verifies_status_and_discovers_only_reserved_sealed_workspace(
        tmp_path, validation):
    """The result port discovers only complete evidence in its trusted location."""
    root = tmp_path / 'workers/w1'
    mode = RunMode.PLAN_ONLY if validation else RunMode.EXECUTE
    work = populated(root, validation=validation)
    adapter = api.SealedResultAdapter({'w1': root}, mode)
    assert adapter.discover(lease(), work.path.parent) is None
    sealed = work.seal()
    result = adapter.verify(lease(), str(sealed.path), mode)
    assert result['status'] == ('VALIDATION_PASSED' if validation else 'FAILED')
    assert len(result['sha256']) == 64
    assert adapter.discover(lease(), work.path.parent) == str(sealed.path)
    assert adapter.discover(lease(), root) is None
    with pytest.raises(api.ArtifactError, match='RUN_MODE'):
        adapter.verify(lease(), str(sealed.path),
                       RunMode.EXECUTE if validation else RunMode.PLAN_ONLY)
    with pytest.raises(api.ArtifactError):
        adapter.verify(lease(), str(work.path), mode)


def test_recovery_receipts_append_and_strictly_validate_success(tmp_path):
    """Recovery retries append receipts and cannot turn truthy values into success."""
    first = api.write_recovery_receipt(tmp_path, identity(), succeeded=False)
    second = api.write_recovery_receipt(tmp_path, identity(), succeeded=True)
    assert first != second
    assert json.loads(first.read_text())['succeeded'] is False
    assert json.loads(second.read_text())['succeeded'] is True
    for value in ('false', 1, None):
        with pytest.raises(api.ArtifactError):
            api.write_recovery_receipt(tmp_path, identity(), succeeded=value)


@pytest.mark.parametrize('field,value', [
    ('producer_pid', 999999), ('producer_pgid', 999999), ('schema_version', True),
    ('worker_slot', 'w2'), ('reset_epoch', 'reset-8'),
    ('source_stamp', {'commit': 'b' * 40}),
    ('identity', {**asdict(identity()), 'coordinator_epoch': True}),
])
def test_manifest_provenance_cannot_disagree_with_workspace(tmp_path, field, value):
    """Manifest headers must agree with the hashed workspace provenance record."""
    sealed = populated(tmp_path).seal()
    path = sealed.path / 'attempt_result_manifest.json'
    path.chmod(0o644)
    document = json.loads(path.read_text())
    document[field] = value
    path.write_text(json.dumps(document))
    with pytest.raises(api.ArtifactError):
        sealed.verify()


def test_retry_after_parent_fsync_failure_must_sync_parent_before_ack(tmp_path, monkeypatch):
    """An already visible seal must still complete failed directory durability."""
    work = populated(tmp_path)
    real_fsync = os.fsync
    parent = work.path.parent

    def fail_after_publication(fd):
        if (Path(os.readlink(f'/proc/self/fd/{fd}')) == parent
                and (parent / 'sealed').exists()):
            raise OSError('injected parent fsync failure')
        return real_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, 'fsync', fail_after_publication)
        with pytest.raises(OSError, match='parent fsync'):
            work.seal()
    assert (parent / 'sealed').is_dir()
    synced = []

    def observe(fd):
        synced.append(Path(os.readlink(f'/proc/self/fd/{fd}')))
        return real_fsync(fd)

    monkeypatch.setattr(os, 'fsync', observe)
    work.seal()
    assert parent in synced


def test_json_nonstring_keys_are_rejected_before_any_artifact_write(tmp_path):
    """JSON coercion cannot silently change evidence field names."""
    work = workspace(tmp_path)
    with pytest.raises(api.ArtifactError):
        work.write_json('bad.json', {'nested': {1: 'ambiguous'}})
    assert not (work.path / 'bad.json').exists()


def test_receipt_root_cannot_be_a_sealed_tree_even_if_owner_changes_permissions(tmp_path):
    """A mistaken root argument cannot put recovery records in sealed content."""
    sealed = populated(tmp_path).seal()
    sealed.path.chmod(0o755)
    before = digest_tree(sealed.path)
    with pytest.raises(api.ArtifactError, match='ROOT'):
        api.write_recovery_receipt(sealed.path, identity(), succeeded=True)
    assert digest_tree(sealed.path) == before


@pytest.mark.parametrize('validation', [False, True])
def test_public_verifiers_preserve_identity_class_and_reject_other_mode(tmp_path, validation):
    """Explicit verification APIs enforce the same physical/validation boundary."""
    sealed = populated(tmp_path, validation=validation).seal()
    correct = api.verify_validation if validation else api.verify_attempt
    wrong = api.verify_attempt if validation else api.verify_validation
    assert correct(sealed.path, identity(validation)).identity == identity(validation)
    with pytest.raises(api.ArtifactError, match='IDENTITY'):
        wrong(sealed.path, identity(validation))


def test_discovery_rejects_corrupted_known_result_and_does_not_scan_neighbors(tmp_path):
    """Corrupt or neighboring evidence cannot suppress an active lease expiry."""
    root = tmp_path / 'workers/w1'
    work = populated(root)
    sealed = work.seal()
    adapter = api.SealedResultAdapter({'w1': root}, RunMode.EXECUTE)
    file = sealed.path / 'attempt-result.json'
    file.chmod(0o644)
    file.write_text('{"status":"PASSED"}')
    assert adapter.discover(lease(), work.path.parent) is None
    assert adapter.discover(lease(), root / 'attempts') is None


@pytest.mark.parametrize('validation,status', [(False, 'VALIDATION_PASSED'), (True, 'PASSED')])
def test_status_cannot_promote_validation_to_physical_result(tmp_path, validation, status):
    """A foreign status must fail before any sealed directory becomes visible."""
    work = populated(tmp_path, validation=validation)
    name = 'validation-result.json' if validation else 'attempt-result.json'
    work.write_json(name, {'status': status})
    with pytest.raises(api.ArtifactError, match='STATUS'):
        work.seal()
    assert not (work.path.parent / 'sealed').exists()


@pytest.mark.parametrize('mode', [RunMode.EXECUTE, RunMode.PLAN_ONLY, RunMode.DRY_RUN])
def test_real_result_adapter_commits_only_matching_coordinator_event(tmp_path, mode):
    """Real sealed manifests drive disjoint coordinator events and point statuses."""
    root = tmp_path / 'workers/w1'
    adapter = api.SealedResultAdapter({'w1': root}, mode)
    journal = CoordinatorJournal.create(tmp_path / 'journal', 'batch-a')
    try:
        request = BatchRequest('batch-a', mode, ('point-1',), 1, 1, tmp_path)
        config = load_parallel_runtime_config(
            Path(__file__).resolve().parents[1] / 'config/mujoco/parallel_batch_v1.yaml')
        coordinator = BatchCoordinator(journal, request, config=config,
                                       clock=lambda: 0.0, result_port=adapter)
        coordinator.register_worker('w1', generation=1)
        granted = coordinator.grant_lease('w1', generation=1)
        coordinator.ack_lease(granted, request_key='ack')
        gate_summary = {
            'schema_version': 1, 'kind': 'POINT_INITIAL_GATE',
            'batch_id': granted.batch_id,
            'coordinator_epoch': granted.coordinator_epoch,
            'worker_id': granted.worker_id,
            'worker_generation': granted.worker_generation,
            'point_id': granted.point_id, 'attempt_id': granted.attempt_id,
            'lease_generation': granted.lease_generation,
            'reset_epoch': 'reset-1', 'simulation_session_id': 'session-1',
            'reset_completed_monotonic_s': 1.0,
            'source_frame_monotonic_s': 2.0, 'canonical_joints': True,
            'no_controller_goal': True, 'no_attachment': True,
            'no_contact': True, 'no_stale_node': True,
        }
        if mode is RunMode.DRY_RUN:
            gate_summary = {
                'schema_version': 1, 'kind': 'SCHEDULER_START',
                'batch_id': granted.batch_id,
                'coordinator_epoch': granted.coordinator_epoch,
                'worker_id': granted.worker_id,
                'worker_generation': granted.worker_generation,
                'point_id': granted.point_id, 'attempt_id': granted.attempt_id,
                'lease_generation': granted.lease_generation,
                'point_gate_applicable': False,
                'physical_runtime_started': False, 'scheduler_only': True,
            }
        if mode is RunMode.EXECUTE:
            coordinator.ack_attempt_started(
                granted, request_key='start', gate_summary=gate_summary)
        else:
            coordinator.ack_validation_started(
                granted, request_key='start', gate_summary=gate_summary)
        fields = asdict(granted)
        del fields['lease_issued_monotonic_s'], fields['lease_deadline_monotonic_s']
        validation = mode is not RunMode.EXECUTE
        if validation:
            fields['validation_id'] = fields.pop('attempt_id')
        cls = ValidationIdentity if validation else AttemptIdentity
        sealed = populated(root, validation=validation, mode=mode, who=cls(**fields)).seal()
        wrong_commit = (coordinator.commit_result if validation
                        else coordinator.commit_validation)
        with pytest.raises(ValueError, match='WRONG_EXECUTION_MODE'):
            wrong_commit(granted, sealed.path, request_key='wrong')
        commit = coordinator.commit_validation if validation else coordinator.commit_result
        response = commit(granted, sealed.path, request_key='result')
        assert response['status'] == ('VALIDATION_PASSED' if validation else 'FAILED')
        events = [event.type for event in journal.replay().events]
        assert ('VALIDATION_COMMITTED' if validation else 'RESULT_COMMITTED') in events
        assert ('RESULT_COMMITTED' if validation else 'VALIDATION_COMMITTED') not in events
        point = coordinator.snapshot().points['point-1']
        assert point.status is (PointStatus.UNRUN if validation else PointStatus.FAILED)
        # Replay of an acknowledged request uses history even if the artifact is
        # subsequently damaged; this must not consult the filesystem again.
        file = sealed.path / ('validation-result.json' if validation else 'attempt-result.json')
        file.chmod(0o644)
        file.write_text('{}')
        assert commit(granted, sealed.path, request_key='result') == response
    finally:
        journal.close()


@pytest.mark.parametrize('validation', [False, True])
def test_typed_sealed_handles_cannot_be_constructed_with_foreign_identity(tmp_path, validation):
    """Constructing a typed result directly cannot bypass the identity boundary."""
    cls = api.SealedValidation if validation else api.SealedAttempt
    with pytest.raises(api.ArtifactError, match='IDENTITY'):
        cls(tmp_path, identity(not validation))


def test_workspace_identity_and_location_cannot_change_after_allocation(tmp_path):
    """A live handle cannot redirect publication or change physical identity kind."""
    work = populated(tmp_path)
    for name, value in (('identity', identity(True)), ('path', tmp_path / 'other')):
        with pytest.raises(FrozenInstanceError):
            setattr(work, name, value)


def test_unreadable_artifact_fails_with_the_result_port_contract(tmp_path, monkeypatch):
    """A file read error must be an invalid result, not an uncaught coordinator I/O error."""
    sealed = populated(tmp_path).seal()
    real_read = Path.read_bytes

    def unreadable(path):
        if path == sealed.path / 'initial_state/reset.json':
            raise PermissionError('injected unreadable evidence')
        return real_read(path)

    monkeypatch.setattr(Path, 'read_bytes', unreadable)
    with pytest.raises(api.ArtifactError):
        sealed.verify()


@pytest.mark.parametrize('mode', [RunMode.EXECUTE, RunMode.PLAN_ONLY, RunMode.DRY_RUN])
@pytest.mark.parametrize('access', ['discover', 'verify', 'commit'])
def test_adapter_requires_parent_durability_after_rename_failure(
        tmp_path, monkeypatch, mode, access):
    """Visible evidence cannot be accepted until publication-parent fsync succeeds."""
    root = tmp_path / 'workers/w1'
    adapter = api.SealedResultAdapter({'w1': root}, mode)
    journal = CoordinatorJournal.create(tmp_path / 'journal', 'batch-a')
    try:
        request = BatchRequest('batch-a', mode, ('point-1',), 1, 1, tmp_path)
        config = load_parallel_runtime_config(
            Path(__file__).resolve().parents[1] / 'config/mujoco/parallel_batch_v1.yaml')
        coordinator = BatchCoordinator(journal, request, config=config,
                                       clock=lambda: 0.0, result_port=adapter)
        coordinator.register_worker('w1', generation=1)
        granted = coordinator.grant_lease('w1', generation=1)
        coordinator.ack_lease(granted, request_key='ack')
        validation = mode is not RunMode.EXECUTE
        start = (coordinator.ack_validation_started if validation
                 else coordinator.ack_attempt_started)
        gate_summary = {
            'schema_version': 1, 'kind': 'POINT_INITIAL_GATE',
            'batch_id': granted.batch_id,
            'coordinator_epoch': granted.coordinator_epoch,
            'worker_id': granted.worker_id,
            'worker_generation': granted.worker_generation,
            'point_id': granted.point_id, 'attempt_id': granted.attempt_id,
            'lease_generation': granted.lease_generation,
            'reset_epoch': 'reset-1', 'simulation_session_id': 'session-1',
            'reset_completed_monotonic_s': 1.0,
            'source_frame_monotonic_s': 2.0, 'canonical_joints': True,
            'no_controller_goal': True, 'no_attachment': True,
            'no_contact': True, 'no_stale_node': True,
        }
        if mode is RunMode.DRY_RUN:
            gate_summary = {
                'schema_version': 1, 'kind': 'SCHEDULER_START',
                'batch_id': granted.batch_id,
                'coordinator_epoch': granted.coordinator_epoch,
                'worker_id': granted.worker_id,
                'worker_generation': granted.worker_generation,
                'point_id': granted.point_id, 'attempt_id': granted.attempt_id,
                'lease_generation': granted.lease_generation,
                'point_gate_applicable': False,
                'physical_runtime_started': False, 'scheduler_only': True,
            }
        start(granted, request_key='start', gate_summary=gate_summary)
        fields = asdict(granted)
        del fields['lease_issued_monotonic_s'], fields['lease_deadline_monotonic_s']
        if validation:
            fields['validation_id'] = fields.pop('attempt_id')
        cls = ValidationIdentity if validation else AttemptIdentity
        work = populated(root, validation=validation, mode=mode, who=cls(**fields))
        parent = work.path.parent
        location = parent / 'sealed'
        fail_parent = True
        synced = []
        real_fsync = os.fsync

        def sync(fd):
            path = Path(os.readlink(f'/proc/self/fd/{fd}'))
            if path == parent and location.exists():
                if fail_parent:
                    raise OSError('injected publication-parent failure')
                synced.append(path)
            return real_fsync(fd)

        monkeypatch.setattr(os, 'fsync', sync)
        with pytest.raises(OSError, match='publication-parent failure'):
            work.seal()
        assert location.is_dir()
        assert not work.path.exists()
        before = digest_tree(location)
        history = journal.replay().events

        def accept():
            if access == 'discover':
                return adapter.discover(granted, parent)
            if access == 'verify':
                return adapter.verify(granted, str(location), mode)
            commit = coordinator.commit_validation if validation else coordinator.commit_result
            return commit(granted, location, request_key='result')

        if access == 'discover':
            assert accept() is None
        else:
            with pytest.raises(api.ArtifactError):
                accept()
        assert journal.replay().events == history
        assert coordinator.snapshot().points['point-1'].status is PointStatus.UNRUN
        assert digest_tree(location) == before
        fail_parent = False
        # No in-memory durable flag is retained: a new adapter must sync again.
        adapter = api.SealedResultAdapter({'w1': root}, mode)
        coordinator.result_port = adapter
        result = accept()
        assert result is not None
        assert parent in synced
        assert digest_tree(location) == before
        if access == 'commit':
            kinds = [event.type for event in journal.replay().events]
            assert ('VALIDATION_COMMITTED' if validation else 'RESULT_COMMITTED') in kinds
    finally:
        journal.close()


@pytest.mark.parametrize('error_type', [OSError, PermissionError])
def test_adapter_manifest_digest_read_failure_obeys_result_port_contract(
        tmp_path, monkeypatch, error_type):
    """Final digest reads must fail as ArtifactError, even after inventory verification."""
    root = tmp_path / 'workers/w1'
    work = populated(root)
    sealed = work.seal()
    adapter = api.SealedResultAdapter({'w1': root}, RunMode.EXECUTE)
    real_read = Path.read_bytes

    def unreadable(path):
        if path == sealed.path / 'attempt_result_manifest.json':
            raise error_type('injected manifest digest read failure')
        return real_read(path)

    monkeypatch.setattr(Path, 'read_bytes', unreadable)
    with pytest.raises(api.ArtifactError):
        adapter.verify(lease(), str(sealed.path), RunMode.EXECUTE)
    assert adapter.discover(lease(), work.path.parent) is None
