"""Behavior contracts for isolated parallel Worker resources."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import itertools
import json
import math
import os
from pathlib import Path
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
    )


def resource_root(tmp_path, suffix='batch'):
    """Keep UDS fixtures in this registered scratch tree without pytest's deep suffix."""
    key = str(tmp_path / suffix)
    if key not in _ROOTS:
        _ROOTS[key] = Path(os.environ['TMPDIR']).parent / f'r{next(_ROOT_IDS):x}'
    return _ROOTS[key]


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
    manifest = allocator(tmp_path, config).allocate(worker_count=3)

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
    original = Path.mkdir

    def observed_mkdir(path, *args, **kwargs):
        calls.append((Path(path), kwargs.get('exist_ok', False)))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'mkdir', observed_mkdir)
    allocator(tmp_path, config).allocate()

    assert calls
    assert all(exist_ok is False for _path, exist_ok in calls)


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
