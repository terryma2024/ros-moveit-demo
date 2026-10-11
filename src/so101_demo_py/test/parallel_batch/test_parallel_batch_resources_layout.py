"""Evidence roots, manifest publication and the system probe."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event
from types import SimpleNamespace

from parallel_batch_resources_support import (  # noqa: F401  (pytest fixtures)
    FakeProbe,
    _start_guard_for,
    allocator,
    claim_root,
    config,
    local_start_guard,
    production_claim_records_are_never_mutated_by_unit_tests,
    resource_root,
)
import pytest

from so101_demo.parallel_batch import resources as resources_api
from so101_demo.parallel_batch.resource_allocation import manifest as resources_api_manifest
from so101_demo.parallel_batch.resource_allocation.models import (
    ResourceAllocationError,
)
from so101_demo.parallel_batch.resource_allocation.probe import SystemResourceProbe
from so101_demo.parallel_batch.resources import WorkerResourceAllocator


@pytest.mark.skipif(sys.platform != 'linux', reason='headless EGL worker contract is Linux-only')
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
    real = resource_root(tmp_path, 'evidence-real')
    real.mkdir(mode=0o700)
    link = resource_root(tmp_path, 'evidence-link')
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(ResourceAllocationError, match='SYMLINK_PATH'):
        WorkerResourceAllocator(
            config, link / 'batch', probe=FakeProbe(), claim_root=claim_root(),
            start_guard=_start_guard_for(config),
        ).allocate()


def test_evidence_root_rejects_unsafe_parent_mode(tmp_path, config):
    unsafe = resource_root(tmp_path, 'evidence-unsafe')
    unsafe.mkdir(mode=0o777)
    unsafe.chmod(0o777)

    with pytest.raises(ResourceAllocationError, match='UNSAFE_DIRECTORY_MODE'):
        WorkerResourceAllocator(
            config, unsafe / 'batch', probe=FakeProbe(), claim_root=claim_root(),
            start_guard=_start_guard_for(config),
        ).allocate()


def test_evidence_root_rejects_wrong_parent_owner(tmp_path, config, monkeypatch):
    actual_uid = os.getuid()
    monkeypatch.setattr(resources_api.os, 'getuid', lambda: actual_uid + 1)

    with pytest.raises(ResourceAllocationError, match='UNSAFE_DIRECTORY_OWNER'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'wrong-owner'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            start_guard=_start_guard_for(config),
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
    assert list(resource_allocator.evidence_root.glob('.resource_manifest.*.tmp')) == []

    retry = allocator(tmp_path, config, suffix='manifest-partial-retry')
    assert retry.allocate().worker_count == 2
    retry.close()


def test_concurrent_reader_never_observes_partial_manifest(tmp_path, config, monkeypatch):
    resource_allocator = allocator(tmp_path, config, suffix='manifest-visible')
    resource_allocator.allocate()
    root = resource_allocator.evidence_root
    final = root / 'resource_manifest.json'
    write_started = Event()
    finish_write = Event()
    original_write = os.write

    def paused_write(descriptor, payload):
        if sys.platform == 'darwin':
            raw_path = fcntl.fcntl(descriptor, fcntl.F_GETPATH, bytes(1024))
            target = Path(os.fsdecode(raw_path.split(b'\0', 1)[0]))
        else:
            target = Path(os.readlink(f'/proc/self/fd/{descriptor}'))
        if target.name.startswith('.resource_manifest.') and not write_started.is_set():
            written = original_write(descriptor, payload[:32])
            write_started.set()
            assert finish_write.wait(timeout=5)
            return written
        return original_write(descriptor, payload)

    monkeypatch.setattr(os, 'write', paused_write)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(resource_allocator.write_manifest)
            assert write_started.wait(timeout=5)
            assert not final.exists()
            assert len(list(root.glob('.resource_manifest.*.tmp'))) == 1
            finish_write.set()
            assert future.result(timeout=5) == final

        assert json.loads(final.read_text())['worker_count'] == 2
        assert list(root.glob('.resource_manifest.*.tmp')) == []
    finally:
        finish_write.set()
        resource_allocator.close()


def test_process_death_before_publish_leaves_only_non_authoritative_temp(tmp_path):
    root = tmp_path / 'death-before-publish'
    root.mkdir(mode=0o700)
    script = """
import json
import os
import signal
import sys
from so101_demo.parallel_batch.resource_allocation import manifest as resources
root = sys.argv[1]
descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
resources.os.link = lambda *args, **kwargs: os.kill(os.getpid(), signal.SIGKILL)
resources._write_manifest_at(descriptor, 'resource_manifest.json', {'complete': True})
"""
    result = subprocess.run([sys.executable, '-c', script, str(root)], check=False)

    assert result.returncode == -signal.SIGKILL
    assert not (root / 'resource_manifest.json').exists()
    temporary = list(root.glob('.resource_manifest.*.tmp'))
    assert len(temporary) == 1
    assert json.loads(temporary[0].read_text()) == {'complete': True}


def test_directory_fsync_failure_after_publish_is_explicitly_uncertain(
    tmp_path, monkeypatch
):
    root = tmp_path / 'publication-uncertain'
    root.mkdir(mode=0o700)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    final = root / 'resource_manifest.json'
    original_fsync = os.fsync

    def fail_published_directory_sync(descriptor):
        if descriptor == root_fd and final.exists():
            raise OSError('synthetic published-directory fsync failure')
        return original_fsync(descriptor)

    monkeypatch.setattr(os, 'fsync', fail_published_directory_sync)
    try:
        with pytest.raises(ResourceAllocationError, match='PUBLICATION_UNCERTAIN'):
            resources_api_manifest._write_manifest_at(
                root_fd, final.name, {'complete': True}
            )
    finally:
        os.close(root_fd)

    temporary = list(root.glob('.resource_manifest.*.tmp'))
    assert json.loads(final.read_text()) == {'complete': True}
    assert len(temporary) == 1
    assert temporary[0].read_bytes() == final.read_bytes()


def test_manifest_publish_is_no_replace_and_cleans_temporary(tmp_path):
    root = tmp_path / 'manifest-no-replace'
    root.mkdir(mode=0o700)
    final = root / 'resource_manifest.json'
    final.write_bytes(b'prior-authoritative-manifest\n')
    final.chmod(0o600)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(ResourceAllocationError, match='MANIFEST_CONFLICT'):
            resources_api_manifest._write_manifest_at(root_fd, final.name, {'replacement': True})
    finally:
        os.close(root_fd)
    assert final.read_bytes() == b'prior-authoritative-manifest\n'
    assert list(root.glob('.resource_manifest.*.tmp')) == []


def test_successful_publish_holds_claims_until_explicit_close(tmp_path, config):
    first = allocator(tmp_path, config, suffix='manifest-claim-owner')
    first.allocate()
    first.write_manifest()
    second = allocator(tmp_path, config, suffix='manifest-claim-contender')
    with pytest.raises(ResourceAllocationError, match='ROS_DOMAIN_CLAIMED'):
        second.allocate()
    first.close()

    retry = allocator(tmp_path, config, suffix='manifest-claim-retry')
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
        subprocess,
        'run',
        lambda *args, **kwargs: SimpleNamespace(stdout='15269\n'),
    )
    return SystemResourceProbe(proc_root=proc_root)


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux /proc/meminfo')
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
@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux /proc/meminfo')
def test_system_probe_rejects_missing_duplicate_or_malformed_memavailable(
    tmp_path, monkeypatch, meminfo
):
    probe = system_probe(tmp_path, monkeypatch, meminfo)

    with pytest.raises(ResourceAllocationError, match='PROBE_FAILED: MemAvailable'):
        probe.snapshot()


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux /proc/meminfo')
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
