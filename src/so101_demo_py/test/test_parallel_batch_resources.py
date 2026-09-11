"""Behavior contracts for isolated parallel Worker resources."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from dataclasses import FrozenInstanceError
import fcntl
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
from queue import Queue
from threading import Barrier, Event
from types import SimpleNamespace

import pytest

from so101_demo.parallel_batch import resources as resources_api
from so101_demo.parallel_batch.contracts import load_parallel_runtime_config
from so101_demo.parallel_batch.resources import (
    main,
    ResourceAllocationError,
    ResourceSnapshot,
    SystemResourceProbe,
    WorkerResourceAllocator,
)


PACKAGE = Path(__file__).resolve().parents[1]
CONFIG_PATH = PACKAGE / 'config/mujoco/parallel_batch_v1.yaml'
_ROOT_IDS = itertools.count()
_ROOTS = {}


class FakeProbe:
    """Deterministic live-probe boundary for allocator tests."""

    def __init__(
        self,
        *,
        cpu: int = 32,
        ram: float = 64.0,
        gpu: float = 12.0,
        domains: tuple[int, ...] = (),
        sockets: tuple[Path, ...] = (),
    ) -> None:
        self.resources = ResourceSnapshot(cpu, ram, gpu)
        self.domains = set(domains)
        self.sockets = {Path(path) for path in sockets}
        self.domain_calls: list[int] = []
        self.socket_calls: list[Path] = []

    def snapshot(self) -> ResourceSnapshot:
        return self.resources

    def ros_domain_in_use(self, domain_id: int) -> bool:
        self.domain_calls.append(domain_id)
        return domain_id in self.domains

    def socket_in_use(self, path: Path) -> bool:
        path = Path(path)
        self.socket_calls.append(path)
        return path in self.sockets


@pytest.fixture
def config():
    return load_parallel_runtime_config(CONFIG_PATH)


def allocator(tmp_path, config, probe=None, environment=None, suffix='batch'):
    return WorkerResourceAllocator(
        config,
        resource_root(tmp_path, suffix),
        probe=probe or FakeProbe(),
        base_environment=environment or {},
        claim_root=claim_root(),
    )


def resource_root(tmp_path, suffix='batch'):
    """Keep UDS fixtures in this registered scratch tree without pytest's deep suffix."""
    key = str(tmp_path / suffix)
    if key not in _ROOTS:
        _ROOTS[key] = Path(os.environ['TMPDIR']).parent / f'r{next(_ROOT_IDS):x}'
    return _ROOTS[key]


def claim_root():
    return Path(os.environ['TMPDIR']).parent / 'claims'


def live_evidence(tmp_path, config, **changes):
    payload = {
        'worker_count': 2,
        'runtime_config_sha256': hashlib.sha256(
            json.dumps(asdict(config), sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest(),
        'source_identity': {
            'batch_id': 'accepted-two-worker-live-001',
            'code_sha256': 'a' * 64,
            'simulation_metrics_sha256': 'b' * 64,
            'render_metrics_sha256': 'c' * 64,
        },
        'headroom': {
            'cpu_ratio': 0.30,
            'ram_ratio': 0.30,
            'gpu_ratio': 0.30,
            'simulation_realtime_ratio': 0.25,
            'render_frame_ratio': 0.21,
        },
        'simulation': {'backend': 'mujoco', 'stable': True},
        'rendering': {'backend': 'headless_egl', 'stable': True},
    }
    for key, value in changes.items():
        if key.startswith('headroom_'):
            payload['headroom'][key.removeprefix('headroom_')] = value
        elif key.startswith('source_'):
            payload['source_identity'][key.removeprefix('source_')] = value
        else:
            payload[key] = value
    document = {
        'schema_version': 1,
        'payload': payload,
        'payload_sha256': hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=True).encode()
        ).hexdigest(),
    }
    path = tmp_path / 'two-worker-live-headroom.json'
    path.write_text(json.dumps(document), encoding='utf-8')
    path.chmod(0o600)
    return path


def proc_process(proc_root, pid, *, comm, argv, starttime=424242, state='S'):
    process = proc_root / str(pid)
    process.mkdir(parents=True)
    (process / 'comm').write_text(f'{comm}\n', encoding='utf-8')
    (process / 'cmdline').write_bytes(b'\0'.join(item.encode() for item in argv) + b'\0')
    fields = [state, *(['0'] * 18), str(starttime), '0']
    (process / 'stat').write_text(
        f'{pid} ({comm}) ' + ' '.join(fields) + '\n', encoding='ascii'
    )
    (process / 'environ').write_bytes(b'')
    return process


def test_concurrent_batches_cannot_claim_the_same_ros_domains(tmp_path, config):
    first = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'claim-a'),
        probe=FakeProbe(),
        claim_root=claim_root(),
    )
    second = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'claim-b'),
        probe=FakeProbe(),
        claim_root=claim_root(),
    )

    barrier = Barrier(2)
    release = Event()
    outcomes = Queue()

    def attempt(resource_allocator):
        barrier.wait()
        try:
            resource_allocator.allocate()
        except ResourceAllocationError as error:
            outcomes.put(('rejected', resource_allocator, str(error)))
            return
        outcomes.put(('admitted', resource_allocator, None))
        release.wait(timeout=5)
        resource_allocator.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt, item) for item in (first, second)]
        observed = [outcomes.get(timeout=5), outcomes.get(timeout=5)]
        assert sorted(item[0] for item in observed) == ['admitted', 'rejected']
        rejected = next(item for item in observed if item[0] == 'rejected')
        assert 'ROS_DOMAIN_CLAIMED' in rejected[2]
        winner = next(item[1] for item in observed if item[0] == 'admitted')
        first_document = winner.manifest.to_dict()
        release.set()
        for future in futures:
            future.result(timeout=5)

    assert first_document['domain_claim_scope'] == 'cooperating_same_uid_processes'
    assert [claim['domain_id'] for claim in first_document['domain_claims']] == [181, 182]
    for claim in first_document['domain_claims']:
        assert claim['protocol'] == 'uid_flock_v1'
        assert claim['uid'] == os.getuid()
        assert claim['pid'] == os.getpid()
        assert claim['process_starttime_ticks'] > 0
        assert claim['batch_id'] == winner.batch_id
        assert claim['evidence_root'] == str(winner.evidence_root)
    retry = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'claim-retry'),
        probe=FakeProbe(),
        claim_root=claim_root(),
    )
    assert retry.allocate().worker_count == 2
    retry.close()


def test_domain_flocks_are_held_before_process_scan(tmp_path, config):
    locks = claim_root()

    class LockObservingProbe(FakeProbe):
        def ros_domain_in_use(self, domain_id):
            descriptor = os.open(locks / f'domain-{domain_id}.lock', os.O_RDWR)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(descriptor)
            return False

    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'claim-before-scan'),
        probe=LockObservingProbe(),
        claim_root=locks,
    )
    assert resource_allocator.allocate().worker_count == 2
    resource_allocator.close()


def test_partial_domain_claim_does_not_publish_any_new_claim_record(tmp_path, config):
    locks = claim_root().with_name('claims-partial')
    locks.mkdir(mode=0o700)
    first_record = locks / 'domain-181.lock'
    blocked_record = locks / 'domain-182.lock'
    first_record.write_bytes(b'prior-owner-record\n')
    blocked_record.write_bytes(b'blocked-owner-record\n')
    first_record.chmod(0o600)
    blocked_record.chmod(0o600)
    blocked_fd = os.open(blocked_record, os.O_RDWR)
    fcntl.flock(blocked_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(ResourceAllocationError, match='ROS_DOMAIN_CLAIMED: 182'):
            WorkerResourceAllocator(
                config,
                resource_root(tmp_path, 'partial-domain-claim'),
                probe=FakeProbe(),
                claim_root=locks,
            ).allocate()
    finally:
        os.close(blocked_fd)

    assert first_record.read_bytes() == b'prior-owner-record\n'


def test_protected_systemd_user_is_recorded_as_frozen_non_candidate(
    tmp_path, config, monkeypatch
):
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    process = proc_process(
        proc_root,
        15163,
        comm='systemd',
        argv=('/usr/lib/systemd/systemd', '--user'),
        starttime=104116,
    )
    environ = process / 'environ'
    original = Path.read_bytes

    def protected(path):
        if path == environ:
            raise PermissionError('EXP-011 kernel protection')
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', protected)
    probe = SystemResourceProbe(proc_root=proc_root)

    assert probe.ros_domain_in_use(181) is False
    report = probe.process_scan_report()
    assert report['cross_uid_policy'] == 'not_inspected'
    assert report['candidate_policy'] == 'same_uid_high_recall_requires_environ'
    assert report['frozen_non_candidate_policy'] == 'recorded_without_environ'
    assert report['unclassified_unreadable_policy'] == 'fail_closed'
    assert report['skipped_processes'] == [
        {
            'pid': 15163,
            'uid': os.getuid(),
            'process_starttime_ticks': 104116,
            'comm': 'systemd',
            'cmdline_summary': '/usr/lib/systemd/systemd --user',
            'skip_reason': 'frozen_systemd_user_non_candidate',
        }
    ]
    monkeypatch.setattr(probe, 'snapshot', lambda: ResourceSnapshot(32, 64.0, 12.0))
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'systemd-skip-manifest'),
        probe=probe,
        claim_root=claim_root(),
    )
    manifest = resource_allocator.allocate()
    assert manifest.to_dict()['process_scan']['skipped_processes'] == report[
        'skipped_processes'
    ]
    resource_allocator.close()


def test_same_uid_unreadable_proc_environment_fails_closed(tmp_path, monkeypatch):
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    process = proc_process(
        proc_root,
        4242,
        comm='python3',
        argv=('/usr/bin/python3', 'ros2-worker.py'),
    )
    environ = process / 'environ'
    environ.write_bytes(b'ROS_DOMAIN_ID=181\0')
    original = Path.read_bytes

    def unreadable(path):
        if path == environ:
            raise PermissionError('synthetic same-uid denial')
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', unreadable)

    with pytest.raises(ResourceAllocationError, match='PROC_ENV_UNVERIFIABLE'):
        SystemResourceProbe(proc_root=proc_root).ros_domain_in_use(181)


def test_disappearing_proc_candidate_is_not_an_unreadable_live_process(tmp_path, monkeypatch):
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    process = proc_process(
        proc_root,
        4243,
        comm='python3',
        argv=('/usr/bin/python3', 'ros2-worker.py'),
    )
    original = Path.read_bytes
    original_lexists = os.path.lexists

    def disappeared(path):
        if path == process / 'environ':
            raise FileNotFoundError(path)
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', disappeared)
    monkeypatch.setattr(
        resources_api.os.path,
        'lexists',
        lambda path: False if Path(path) == process else original_lexists(path),
    )
    assert SystemResourceProbe(proc_root=proc_root).ros_domain_in_use(181) is False


def test_unverifiable_proc_identity_fails_closed(tmp_path, monkeypatch):
    proc_root = tmp_path / 'proc'
    process = proc_root / '4244'
    process.mkdir(parents=True)
    original = Path.stat

    def unreadable_identity(path, *args, **kwargs):
        if path == process:
            raise PermissionError('synthetic identity denial')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', unreadable_identity)
    with pytest.raises(ResourceAllocationError, match='PROC_IDENTITY_UNVERIFIABLE'):
        SystemResourceProbe(proc_root=proc_root).ros_domain_in_use(181)


def test_candidate_proc_metadata_unreadable_fails_closed(tmp_path, monkeypatch):
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    process = proc_process(
        proc_root,
        4245,
        comm='python3',
        argv=('/usr/bin/python3', 'ros2-worker.py'),
    )
    original = Path.read_text

    def unreadable_metadata(path, *args, **kwargs):
        if path == process / 'comm':
            raise PermissionError('synthetic comm denial')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', unreadable_metadata)
    with pytest.raises(ResourceAllocationError, match='PROC_METADATA_UNVERIFIABLE'):
        SystemResourceProbe(proc_root=proc_root).ros_domain_in_use(181)


def test_unclassified_unreadable_process_fails_closed(tmp_path, monkeypatch):
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    process = proc_process(
        proc_root,
        4246,
        comm='opaque-runtime',
        argv=('/opt/opaque-runtime',),
    )
    environ = process / 'environ'
    original = Path.read_bytes

    def unreadable_environment(path):
        if path == environ:
            raise PermissionError('synthetic unknown process denial')
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', unreadable_environment)
    with pytest.raises(
        ResourceAllocationError, match='PROC_CLASSIFICATION_UNVERIFIABLE'
    ):
        SystemResourceProbe(proc_root=proc_root).ros_domain_in_use(181)


def test_pid_starttime_change_during_scan_fails_closed(tmp_path, monkeypatch):
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    process = proc_process(
        proc_root,
        4247,
        comm='python3',
        argv=('/usr/bin/python3', 'ros2-worker.py'),
        starttime=100,
    )
    stat_path = process / 'stat'
    original = Path.read_text
    reads = 0

    def changed_identity(path, *args, **kwargs):
        nonlocal reads
        value = original(path, *args, **kwargs)
        if path == stat_path:
            reads += 1
            if reads > 1:
                return value.replace(' 100 0\n', ' 101 0\n')
        return value

    monkeypatch.setattr(Path, 'read_text', changed_identity)
    with pytest.raises(ResourceAllocationError, match='PROC_IDENTITY_CHANGED'):
        SystemResourceProbe(proc_root=proc_root).ros_domain_in_use(181)


def test_three_workers_require_prior_two_worker_live_headroom_evidence(tmp_path, config):
    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_REQUIRED'):
        allocator(tmp_path, config).allocate(worker_count=3)


def test_three_workers_accept_strict_hashed_live_headroom_evidence(tmp_path, config):
    evidence = live_evidence(tmp_path, config)
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-live'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
    )
    manifest = resource_allocator.allocate(worker_count=3)

    assert manifest.worker_count == 3
    assert manifest.live_headroom_evidence['payload_sha256']
    resource_allocator.close()


@pytest.mark.parametrize(
    ('change', 'value'),
    [
        ('headroom_cpu_ratio', 0.19),
        ('headroom_ram_ratio', float('nan')),
        ('headroom_gpu_ratio', float('inf')),
        ('headroom_simulation_realtime_ratio', -0.1),
        ('headroom_render_frame_ratio', 0.0),
        ('worker_count', 3),
        ('runtime_config_sha256', '0' * 64),
        ('simulation', {'backend': 'gazebo', 'stable': True}),
        ('rendering', {'backend': 'headless_egl', 'stable': False}),
        ('source_simulation_metrics_sha256', 'not-a-hash'),
    ],
)
def test_three_worker_live_evidence_fails_closed_on_schema_identity_or_headroom(
    tmp_path, config, change, value
):
    evidence = live_evidence(tmp_path, config, **{change: value})

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, f'three-invalid-{change}'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
        ).allocate(worker_count=3)


def test_three_worker_live_evidence_rejects_payload_hash_mismatch(tmp_path, config):
    evidence = live_evidence(tmp_path, config)
    document = json.loads(evidence.read_text())
    document['payload_sha256'] = '0' * 64
    evidence.write_text(json.dumps(document))

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-hash'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
        ).allocate(worker_count=3)


def test_worker_slots_have_unique_headless_egl_context_resources(tmp_path, config):
    manifest = allocator(tmp_path, config).allocate()
    documents = [worker.to_dict() for worker in manifest.workers]

    assert {item.get('render_backend') for item in documents} == {'headless_egl'}
    assert len({item.get('render_context_id') for item in documents}) == 2
    assert len({item.get('render_context_namespace') for item in documents}) == 2
    for worker in manifest.workers:
        assert worker.environment['MUJOCO_GL'] == 'egl'
        assert worker.environment['SO101_RENDER_CONTEXT_ID'] == worker.render_context_id


def test_evidence_root_rejects_symlink_ancestor(tmp_path, config):
    short = Path(os.environ['TMPDIR']).parent
    real = short / 'real'
    real.mkdir(mode=0o700)
    link = short / 'link'
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(ResourceAllocationError, match='SYMLINK_PATH'):
        WorkerResourceAllocator(config, link / 'batch', probe=FakeProbe()).allocate()


def test_evidence_root_rejects_unsafe_parent_mode(tmp_path, config):
    unsafe = Path(os.environ['TMPDIR']).parent / 'unsafe'
    unsafe.mkdir(mode=0o777)
    unsafe.chmod(0o777)

    with pytest.raises(ResourceAllocationError, match='UNSAFE_DIRECTORY_MODE'):
        WorkerResourceAllocator(config, unsafe / 'batch', probe=FakeProbe()).allocate()


def test_evidence_root_rejects_wrong_parent_owner(tmp_path, config, monkeypatch):
    actual_uid = os.getuid()
    monkeypatch.setattr(resources_api.os, 'getuid', lambda: actual_uid + 1)

    with pytest.raises(ResourceAllocationError, match='UNSAFE_DIRECTORY_OWNER'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'wrong-owner'),
            probe=FakeProbe(),
            claim_root=claim_root(),
        ).allocate()


def test_new_directory_with_wrong_mode_fails_closed(tmp_path, config, monkeypatch):
    original = os.mkdir

    def unsafe_mkdir(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == 'workers':
            os.chmod(path, 0o755, dir_fd=kwargs['dir_fd'])
        return result

    monkeypatch.setattr(os, 'mkdir', unsafe_mkdir)
    with pytest.raises(ResourceAllocationError, match='UNSAFE_DIRECTORY_MODE'):
        allocator(tmp_path, config, suffix='wrong-new-mode').allocate()


def test_partial_directory_failure_releases_domain_claims(tmp_path, config, monkeypatch):
    original = os.mkdir

    def interrupted_mkdir(path, *args, **kwargs):
        if path == 'ipc':
            raise OSError('synthetic partial directory failure')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, 'mkdir', interrupted_mkdir)
    resource_allocator = allocator(tmp_path, config, suffix='partial-directory')
    with pytest.raises(ResourceAllocationError, match='DIRECTORY_CREATION_FAILED'):
        resource_allocator.allocate()
    assert not (resource_allocator.evidence_root / 'resource_manifest.json').exists()

    monkeypatch.setattr(os, 'mkdir', original)
    retry = allocator(tmp_path, config, suffix='partial-directory-retry')
    assert retry.allocate().worker_count == 2
    retry.close()


def test_manifest_write_uses_held_root_and_rejects_path_replacement(tmp_path, config):
    resource_allocator = allocator(tmp_path, config)
    resource_allocator.allocate()
    root = resource_allocator.evidence_root
    displaced = root.with_name(root.name + '-displaced')
    root.rename(displaced)
    root.mkdir(mode=0o700)

    writer = getattr(
        resource_allocator,
        'write_manifest',
        lambda: resources_api._write_manifest(
            root / 'resource_manifest.json', resource_allocator.manifest.to_dict()
        ),
    )
    with pytest.raises(ResourceAllocationError, match='PATH_IDENTITY_CHANGED'):
        writer()
    assert not (root / 'resource_manifest.json').exists()
    resource_allocator.close()


def test_manifest_write_revalidates_held_root_mode_before_publish(tmp_path, config):
    resource_allocator = allocator(tmp_path, config, suffix='manifest-root-mode')
    resource_allocator.allocate()
    resource_allocator.evidence_root.chmod(0o777)

    with pytest.raises(ResourceAllocationError, match='UNSAFE_DIRECTORY_MODE'):
        resource_allocator.write_manifest()
    assert not (resource_allocator.evidence_root / 'resource_manifest.json').exists()
    resource_allocator.evidence_root.chmod(0o700)


def test_partial_manifest_write_is_not_published_and_releases_claims(
    tmp_path, config, monkeypatch
):
    resource_allocator = allocator(tmp_path, config, suffix='manifest-partial')
    resource_allocator.allocate()
    original_write = os.write
    failed = False

    def interrupted_write(descriptor, payload):
        nonlocal failed
        if not failed and payload.startswith(b'{'):
            failed = True
            return 0
        return original_write(descriptor, payload)

    monkeypatch.setattr(os, 'write', interrupted_write)
    with pytest.raises(ResourceAllocationError, match='MANIFEST_WRITE_FAILED'):
        resource_allocator.write_manifest()
    assert not (resource_allocator.evidence_root / 'resource_manifest.json').exists()

    retry = allocator(tmp_path, config, suffix='manifest-partial-retry')
    assert retry.allocate().worker_count == 2
    retry.close()


def system_probe(tmp_path, monkeypatch, meminfo):
    """Build a real system probe around controlled Linux and GPU observations."""
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    if meminfo is not None:
        (proc_root / 'meminfo').write_text(meminfo, encoding='ascii')
    monkeypatch.setattr(resources_api.os, 'cpu_count', lambda: 24)
    monkeypatch.setattr(resources_api.os, 'sysconf', lambda _name: 0)
    monkeypatch.setattr(
        resources_api.subprocess,
        'run',
        lambda *args, **kwargs: SimpleNamespace(stdout='15269\n'),
    )
    return SystemResourceProbe(proc_root=proc_root)


def test_system_probe_uses_linux_memavailable_kib_without_sysconf_fallback(
    tmp_path, monkeypatch
):
    probe = system_probe(
        tmp_path,
        monkeypatch,
        'MemTotal:       32646552 kB\nMemAvailable:   28538252 kB\nMemFree: 0 kB\n',
    )

    snapshot = probe.snapshot()

    assert snapshot.logical_cpu_count == 24
    assert snapshot.available_ram_gib == pytest.approx(28538252 / 1024**2)
    assert snapshot.gpu_free_gib == pytest.approx(15269 / 1024)


@pytest.mark.parametrize(
    'meminfo',
    [
        '',
        'MemFree: 28538252 kB\n',
        'MemAvailable: 1 kB\nMemAvailable: 2 kB\n',
        'MemAvailable: nope kB\n',
        'MemAvailable: nan kB\n',
        'MemAvailable: inf kB\n',
        'MemAvailable: -1 kB\n',
        'MemAvailable: 28538252 MB\n',
        'MemAvailable: 28538252\n',
        'MemAvailable: 28538252.0 kB\n',
    ],
)
def test_system_probe_rejects_missing_duplicate_or_malformed_memavailable(
    tmp_path, monkeypatch, meminfo
):
    probe = system_probe(tmp_path, monkeypatch, meminfo)

    with pytest.raises(ResourceAllocationError, match='PROBE_FAILED: MemAvailable'):
        probe.snapshot()


def test_system_probe_fails_closed_when_meminfo_cannot_be_read(tmp_path, monkeypatch):
    probe = system_probe(tmp_path, monkeypatch, None)

    with pytest.raises(ResourceAllocationError, match='PROBE_FAILED: MemAvailable'):
        probe.snapshot()


def test_default_two_slots_have_unique_real_resources_and_mujoco_literals(tmp_path, config):
    manifest = allocator(tmp_path, config).allocate()

    assert manifest.requested_worker_count == manifest.worker_count == 2
    assert manifest.admission.admitted is True
    assert len(manifest.workers) == 2
    unique_fields = (
        'worker_id',
        'ros_domain_id',
        'session_id',
        'controller_namespace',
        'ros_home',
        'ros_log_dir',
        'temp_dir',
        'socket_namespace',
        'worker_root',
    )
    for field in unique_fields:
        assert len({getattr(worker, field) for worker in manifest.workers}) == 2, field
    for worker in manifest.workers:
        assert worker.simulation_port == 'not_applicable'
        assert worker.bridge_port == 'not_applicable'
        assert worker.gz_partition == 'not_applicable'
        assert worker.environment['GZ_PARTITION'] == 'not_applicable'


def test_manifest_and_nested_resources_are_immutable(tmp_path, config):
    manifest = allocator(tmp_path, config).allocate()

    with pytest.raises(FrozenInstanceError):
        manifest.worker_count = 1
    with pytest.raises(FrozenInstanceError):
        manifest.workers[0].generation = 9
    with pytest.raises(TypeError):
        manifest.workers[0].environment['ROS_DOMAIN_ID'] = '7'


def test_resources_use_frozen_domain_sequence_and_private_worker_layout(tmp_path, config):
    evidence = live_evidence(tmp_path, config)
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-layout'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
    )
    manifest = resource_allocator.allocate(worker_count=3)

    assert [worker.ros_domain_id for worker in manifest.workers] == [181, 182, 183]
    assert [worker.worker_id for worker in manifest.workers] == [
        'worker-01',
        'worker-02',
        'worker-03',
    ]
    for worker in manifest.workers:
        assert worker.worker_root == manifest.evidence_root / 'workers' / worker.worker_id
        assert worker.ros_home == worker.worker_root / 'ros-home'
        assert worker.ros_log_dir == worker.ros_home / 'log'
        assert worker.temp_dir == worker.worker_root / 'tmp'
        assert worker.socket_namespace.parent == manifest.evidence_root / 'ipc'
        for path in (
            worker.worker_root,
            worker.ros_home,
            worker.ros_log_dir,
            worker.temp_dir,
            worker.socket_namespace,
        ):
            assert path.is_dir()
            assert path.stat().st_mode & 0o777 == 0o700
    resource_allocator.close()


def test_environment_is_whitelisted_and_does_not_inherit_arbitrary_ros_values(tmp_path, config):
    base = {
        'PATH': '/usr/bin',
        'AMENT_PREFIX_PATH': '/opt/ros/jazzy',
        'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp',
        'ROS_NAMESPACE': '/ambient-danger',
        'ROS_LOCALHOST_ONLY': '0',
        'ROS_DOMAIN_ID': '4',
        'ROS_HOME': '/tmp/shared-ros',
        'ROS_LOG_DIR': '/tmp/shared-log',
        'GZ_PARTITION': 'shared',
        'TMPDIR': '/tmp/shared',
        'UNRELATED_SECRET': 'do-not-copy',
    }

    worker = allocator(tmp_path, config, environment=base).allocate().workers[0]

    assert worker.environment['PATH'] == '/usr/bin'
    assert worker.environment['AMENT_PREFIX_PATH'] == '/opt/ros/jazzy'
    assert worker.environment['RMW_IMPLEMENTATION'] == 'rmw_fastrtps_cpp'
    assert worker.environment['ROS_DOMAIN_ID'] == '181'
    assert worker.environment['ROS_HOME'] == str(worker.ros_home)
    assert worker.environment['ROS_LOG_DIR'] == str(worker.ros_log_dir)
    assert worker.environment['TMPDIR'] == str(worker.temp_dir)
    assert worker.environment['TMP'] == str(worker.temp_dir)
    assert worker.environment['TEMP'] == str(worker.temp_dir)
    assert worker.environment['GZ_PARTITION'] == 'not_applicable'
    assert 'ROS_NAMESPACE' not in worker.environment
    assert 'ROS_LOCALHOST_ONLY' not in worker.environment
    assert 'UNRELATED_SECRET' not in worker.environment


def test_worker_replacement_reuses_slot_resources_and_advances_generation(tmp_path, config):
    resource_allocator = allocator(tmp_path, config)
    original = resource_allocator.allocate().workers[0]

    replacement = resource_allocator.replace('worker-01', expected_generation=1)

    assert replacement.generation == 2
    for field in (
        'worker_id',
        'ros_domain_id',
        'controller_namespace',
        'ros_home',
        'ros_log_dir',
        'temp_dir',
        'render_backend',
        'render_context_id',
        'render_context_namespace',
        'virtual_display',
        'socket_namespace',
        'worker_root',
    ):
        assert getattr(replacement, field) == getattr(original, field)
    assert replacement.session_id != original.session_id
    assert replacement.environment['ROS_DOMAIN_ID'] == '181'


@pytest.mark.parametrize(
    ('worker_id', 'generation', 'message'),
    [
        ('worker-99', 1, 'UNKNOWN_WORKER'),
        ('worker-01', 2, 'GENERATION_MISMATCH'),
        ('worker-01', True, 'GENERATION'),
    ],
)
def test_worker_replacement_rejects_wrong_slot_or_generation(
    tmp_path, config, worker_id, generation, message
):
    resource_allocator = allocator(tmp_path, config)
    resource_allocator.allocate()

    with pytest.raises(ResourceAllocationError, match=message):
        resource_allocator.replace(worker_id, expected_generation=generation)


def test_three_workers_are_explicit_and_never_silently_downgraded(tmp_path, config):
    resource_allocator = allocator(tmp_path, config, FakeProbe(cpu=11, ram=64.0, gpu=12.0))

    with pytest.raises(ResourceAllocationError, match='INSUFFICIENT_LOGICAL_CPU') as caught:
        resource_allocator.allocate(worker_count=3)
    assert caught.value.admission.admitted is False
    assert caught.value.admission.observed.logical_cpu_count == 11
    assert caught.value.admission.required.logical_cpu_count == 12
    assert caught.value.admission.required.available_ram_gib == 18.0
    assert caught.value.admission.required.gpu_free_gib == 8.0
    assert caught.value.admission.required_live_headroom_ratio == 0.20
    assert caught.value.admission.failures == ('INSUFFICIENT_LOGICAL_CPU',)
    assert not resource_allocator.evidence_root.exists()


@pytest.mark.parametrize('worker_count', [True, 0, -1, 4])
def test_worker_count_must_be_positive_and_within_frozen_maximum(tmp_path, config, worker_count):
    with pytest.raises(ResourceAllocationError, match='WORKER_COUNT'):
        allocator(tmp_path, config).allocate(worker_count=worker_count)


@pytest.mark.parametrize(
    ('probe', 'message'),
    [
        (FakeProbe(cpu=7), 'INSUFFICIENT_LOGICAL_CPU'),
        (FakeProbe(ram=13.99), 'INSUFFICIENT_AVAILABLE_RAM'),
        (FakeProbe(gpu=7.99), 'INSUFFICIENT_GPU_MEMORY'),
    ],
)
def test_each_resource_threshold_fails_closed_without_creating_directories(
    tmp_path, config, probe, message
):
    resource_allocator = allocator(tmp_path, config, probe)
    with pytest.raises(ResourceAllocationError, match=message):
        resource_allocator.allocate()
    assert not resource_allocator.evidence_root.exists()


def test_admission_records_observations_thresholds_and_frozen_headroom(tmp_path, config):
    manifest = allocator(tmp_path, config, FakeProbe(cpu=16, ram=14.0, gpu=8.0)).allocate()

    admission = manifest.admission
    assert admission.observed == ResourceSnapshot(16, 14.0, 8.0)
    assert admission.required.logical_cpu_count == 8
    assert admission.required.available_ram_gib == 14.0
    assert admission.required.gpu_free_gib == 8.0
    assert admission.required_live_headroom_ratio == 0.20
    assert admission.failures == ()


@pytest.mark.parametrize(
    'snapshot',
    [
        ResourceSnapshot(True, 64.0, 12.0),
        ResourceSnapshot(32, math.nan, 12.0),
        ResourceSnapshot(32, 64.0, math.inf),
        ResourceSnapshot(32, -1.0, 12.0),
    ],
)
def test_malformed_resource_probe_values_fail_closed(tmp_path, config, snapshot):
    probe = FakeProbe()
    probe.resources = snapshot
    with pytest.raises(ResourceAllocationError, match='INVALID_RESOURCE_SNAPSHOT'):
        allocator(tmp_path, config, probe).allocate()


def test_existing_ros_domain_fails_before_any_directory_is_created(tmp_path, config):
    probe = FakeProbe(domains=(182,))
    resource_allocator = allocator(tmp_path, config, probe)

    with pytest.raises(ResourceAllocationError, match='ROS_DOMAIN_IN_USE: 182'):
        resource_allocator.allocate()
    assert probe.domain_calls == [181, 182]
    assert not resource_allocator.evidence_root.exists()


def test_existing_evidence_or_worker_directory_fails_closed(tmp_path, config):
    root = resource_root(tmp_path)
    root.mkdir()

    with pytest.raises(ResourceAllocationError, match='DIRECTORY_CONFLICT'):
        WorkerResourceAllocator(config, root, probe=FakeProbe()).allocate()


def test_existing_socket_reservation_fails_before_directory_creation(tmp_path, config):
    root = resource_root(tmp_path)
    resource_allocator = WorkerResourceAllocator(config, root, probe=FakeProbe())
    socket_path = resource_allocator._paths(2)['socket_path']
    probe = FakeProbe(sockets=(socket_path,))

    with pytest.raises(ResourceAllocationError, match='SOCKET_CONFLICT'):
        WorkerResourceAllocator(config, root, probe=probe).allocate()
    assert not root.exists()


def test_socket_path_must_fit_linux_unix_domain_limit(tmp_path, config, monkeypatch):
    root = resource_root(tmp_path)
    resource_allocator = WorkerResourceAllocator(config, root, probe=FakeProbe())
    original_paths = resource_allocator._paths

    def paths_with_long_socket(slot_index):
        paths = original_paths(slot_index)
        paths['socket_namespace'] = tmp_path / ('x' * 100)
        paths['socket_path'] = paths['socket_namespace'] / 'control.sock'
        return paths

    monkeypatch.setattr(resource_allocator, '_paths', paths_with_long_socket)

    with pytest.raises(ResourceAllocationError, match='UNIX_SOCKET_PATH_TOO_LONG'):
        resource_allocator.allocate()
    assert not root.exists()


def test_probe_exceptions_fail_closed_without_allocating(tmp_path, config):
    class BrokenProbe(FakeProbe):
        def ros_domain_in_use(self, domain_id):
            raise OSError('probe unavailable')

    with pytest.raises(ResourceAllocationError, match='PROBE_FAILED'):
        resource_allocator = allocator(tmp_path, config, BrokenProbe())
        resource_allocator.allocate()
    assert not resource_allocator.evidence_root.exists()


def test_allocation_uses_exclusive_directory_creation(tmp_path, config, monkeypatch):
    calls = []
    original = os.mkdir

    def observed_mkdir(path, *args, **kwargs):
        calls.append((path, kwargs.get('mode'), kwargs.get('dir_fd')))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, 'mkdir', observed_mkdir)
    allocator(tmp_path, config).allocate()

    assert calls
    assert all(mode == 0o700 and dir_fd is not None for _path, mode, dir_fd in calls)


def test_manifest_document_is_json_safe_and_contains_no_numeric_ports(tmp_path, config):
    manifest = allocator(tmp_path, config).allocate()
    document = manifest.to_dict()

    assert json.loads(json.dumps(document)) == document
    assert document['backend'] == 'mujoco'
    assert document['workers'][0]['simulation_port'] == 'not_applicable'
    assert document['workers'][0]['bridge_port'] == 'not_applicable'
    assert document['workers'][0]['gz_partition'] == 'not_applicable'


def test_dry_run_cli_writes_private_manifest_without_starting_processes(tmp_path, monkeypatch):
    root = resource_root(tmp_path, 'dry')
    calls = []

    monkeypatch.setattr(
        'so101_demo.parallel_batch.resources.SystemResourceProbe.snapshot',
        lambda self: ResourceSnapshot(32, 64.0, 12.0),
    )
    monkeypatch.setattr(
        'so101_demo.parallel_batch.resources.SystemResourceProbe.ros_domain_in_use',
        lambda self, domain_id: False,
    )
    monkeypatch.setattr(
        'so101_demo.parallel_batch.resources.SystemResourceProbe.socket_in_use',
        lambda self, path: False,
    )
    monkeypatch.setattr(
        'so101_demo.parallel_batch.resources.subprocess.Popen',
        lambda *args, **kwargs: calls.append((args, kwargs)),
        raising=False,
    )

    exit_code = main(
        [
            '--config',
            str(CONFIG_PATH),
            '--worker-count',
            '2',
            '--evidence-root',
            str(root),
            '--dry-run',
        ]
    )

    manifest_path = root / 'resource_manifest.json'
    document = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert exit_code == 0
    assert calls == []
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert document['mode'] == 'dry_run'
    assert document['worker_count'] == 2
    assert [worker['ros_domain_id'] for worker in document['workers']] == [181, 182]


def test_three_worker_cli_requires_and_consumes_live_headroom_evidence(
    tmp_path, config, monkeypatch
):
    root = resource_root(tmp_path, 'dry-three')
    evidence = live_evidence(tmp_path, config)
    monkeypatch.setattr(
        'so101_demo.parallel_batch.resources.SystemResourceProbe.snapshot',
        lambda self: ResourceSnapshot(32, 64.0, 12.0),
    )
    monkeypatch.setattr(
        'so101_demo.parallel_batch.resources.SystemResourceProbe.ros_domain_in_use',
        lambda self, domain_id: False,
    )

    exit_code = main(
        [
            '--config',
            str(CONFIG_PATH),
            '--worker-count',
            '3',
            '--live-headroom-evidence',
            str(evidence),
            '--evidence-root',
            str(root),
            '--dry-run',
        ]
    )

    document = json.loads((root / 'resource_manifest.json').read_text(encoding='utf-8'))
    assert exit_code == 0
    assert document['worker_count'] == 3
    assert document['live_headroom_evidence']['file_sha256']


def test_cli_requires_dry_run_and_does_not_create_output(tmp_path):
    root = resource_root(tmp_path, 'not-dry')

    with pytest.raises(SystemExit):
        main(
            [
                '--config',
                str(CONFIG_PATH),
                '--evidence-root',
                str(root),
            ]
        )
    assert not root.exists()
