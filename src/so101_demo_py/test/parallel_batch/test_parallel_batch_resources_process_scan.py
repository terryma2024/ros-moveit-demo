"""Domain locks, the process scan and the classification of unreadable processes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import fcntl
import os
from pathlib import Path
from queue import Queue
import sys
from threading import Barrier, Event

from parallel_batch_resources_support import (  # noqa: F401  (pytest fixtures)
    FakeProbe,
    _start_guard_for,
    claim_root,
    config,
    local_start_guard,
    production_claim_records_are_never_mutated_by_unit_tests,
    resource_root,
)
import pytest

from so101_demo.parallel_batch import resources as resources_api
from so101_demo.parallel_batch.resource_allocation.models import (
    ResourceAllocationError,
    ResourceSnapshot,
)
from so101_demo.parallel_batch.resource_allocation.probe import SystemResourceProbe
from so101_demo.parallel_batch.resources import WorkerResourceAllocator


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
        start_guard=_start_guard_for(config),
    )
    second = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'claim-b'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        start_guard=_start_guard_for(config),
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
        release.wait()
        resource_allocator.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt, item) for item in (first, second)]
        try:
            observed = [outcomes.get(timeout=30), outcomes.get(timeout=30)]
            assert sorted(item[0] for item in observed) == ['admitted', 'rejected']
            rejected = next(item for item in observed if item[0] == 'rejected')
            assert 'ROS_DOMAIN_CLAIMED' in rejected[2]
            winner = next(item[1] for item in observed if item[0] == 'admitted')
            first_document = winner.manifest.to_dict()
        finally:
            release.set()
        for future in futures:
            future.result(timeout=30)

    assert first_document['domain_claim_scope'] == 'cooperating_same_uid_processes'
    assert [claim['domain_id'] for claim in first_document['domain_claims']] == [181, 182]
    for claim in first_document['domain_claims']:
        assert claim['protocol'] == 'uid_flock'
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
        start_guard=_start_guard_for(config),
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
        start_guard=_start_guard_for(config),
    )
    assert resource_allocator.allocate().worker_count == 2
    resource_allocator.close()


def test_partial_domain_claim_does_not_publish_any_new_claim_record(tmp_path, config):
    locks = resource_root(tmp_path, 'claims-partial')
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
                start_guard=_start_guard_for(config),
            ).allocate()
    finally:
        os.close(blocked_fd)

    assert first_record.read_bytes() == b'prior-owner-record\n'


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux procfs semantics')
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
            raise PermissionError('kernel protection')
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
        start_guard=_start_guard_for(config),
    )
    manifest = resource_allocator.allocate()
    assert manifest.to_dict()['process_scan']['skipped_processes'] == report[
        'skipped_processes'
    ]
    resource_allocator.close()


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux procfs semantics')
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


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux procfs semantics')
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


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux procfs semantics')
def test_candidate_exiting_during_environment_read_is_not_live(tmp_path, monkeypatch):
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    process = proc_process(
        proc_root, 4248, comm='python3',
        argv=('/usr/bin/python3', 'ros2-worker.py'),
    )
    environ = process / 'environ'
    stat_path = process / 'stat'
    original = Path.read_bytes

    def exit_during_read(path):
        if path == environ:
            stat_path.write_text(
                stat_path.read_text(encoding='ascii').replace(') S ', ') Z '),
                encoding='ascii',
            )
            raise FileNotFoundError(path)
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', exit_during_read)
    probe = SystemResourceProbe(proc_root=proc_root)
    assert probe.ros_domain_in_use(181) is False
    assert probe.process_scan_report()['skipped_processes'][0]['skip_reason'] == (
        'frozen_zombie_non_candidate')


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux procfs semantics')
def test_live_candidate_missing_environment_still_fails_closed(tmp_path, monkeypatch):
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    process = proc_process(
        proc_root, 4249, comm='python3',
        argv=('/usr/bin/python3', 'ros2-worker.py'),
    )
    original = Path.read_bytes

    def missing_environment(path):
        if path == process / 'environ':
            raise FileNotFoundError(path)
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', missing_environment)
    with pytest.raises(ResourceAllocationError, match='PROC_ENV_UNVERIFIABLE'):
        SystemResourceProbe(proc_root=proc_root).ros_domain_in_use(181)


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux procfs semantics')
def test_candidate_identity_change_after_missing_environment_fails_closed(
        tmp_path, monkeypatch):
    proc_root = tmp_path / 'proc'
    proc_root.mkdir()
    process = proc_process(
        proc_root, 4250, comm='python3',
        argv=('/usr/bin/python3', 'ros2-worker.py'), starttime=100,
    )
    stat_path = process / 'stat'
    original = Path.read_bytes

    def replaced_during_read(path):
        if path == process / 'environ':
            stat_path.write_text(
                stat_path.read_text(encoding='ascii').replace(' 100 0\n',
                                                              ' 101 0\n'),
                encoding='ascii',
            )
            raise FileNotFoundError(path)
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', replaced_during_read)
    with pytest.raises(ResourceAllocationError, match='PROC_IDENTITY_CHANGED'):
        SystemResourceProbe(proc_root=proc_root).ros_domain_in_use(181)


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux procfs semantics')
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


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux procfs semantics')
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


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux procfs semantics')
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


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux procfs semantics')
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
