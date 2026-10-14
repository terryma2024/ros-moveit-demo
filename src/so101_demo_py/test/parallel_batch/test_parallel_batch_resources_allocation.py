"""Start guard decisions, worker environments, replacement, sockets and recovery."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

from parallel_batch_resources_support import (  # noqa: F401  (pytest fixtures)
    CLI_CONFIG_PATH,
    FakeProbe,
    _start_guard_for,
    allocator,
    claim_root,
    config,
    local_start_guard,
    production_batch_argv,
    production_claim_records_are_never_mutated_by_unit_tests,
    resource_root,
)
import pytest

from so101_demo.parallel_batch.resource_allocation import (
    allocator_layout as resources_api_allocator_layout,
)
from so101_demo.parallel_batch.resource_allocation.models import (
    ResourceAllocationError,
    configured_runtime_ipc_root,
    runtime_ipc_base,
)
from so101_demo.parallel_batch.resources import WorkerResourceAllocator, main
from so101_demo.parallel_batch.start_guard_probe import (
    CLEAR,
    ProbeCoordinator,
)


class _RefusingCoordinator(ProbeCoordinator):
    """A coordinator whose decision is a real FAIL, used to drive refusal paths."""

    def __init__(self, reason, state_root):
        super().__init__(state_root)
        self._reason = reason

    def check(self, policy, scope):
        from so101_demo.parallel_batch.start_guard import FAIL, GuardCheck, GuardResult

        return GuardResult(scope=scope, status=FAIL, started_monotonic_s=0.0,
                           completed_monotonic_s=0.0,
                           checks={"probe": GuardCheck(FAIL, self._reason, None, None, "bytes")},
                           snapshot=None, cleanup_state=CLEAR)


def _refusing_guard(tmp_path, reason):
    from so101_demo.parallel_batch.start_guard_probe import EpochStartGuard

    policy = config_policy()
    return EpochStartGuard(_RefusingCoordinator(reason, tmp_path / 'refusing-state'), policy)


def config_policy():
    from so101_demo.parallel_batch.contracts.linux_cuda import (
        load_parallel_runtime_config_linux_cuda,
    )

    return load_parallel_runtime_config_linux_cuda(CLI_CONFIG_PATH).start_guard


def refusing_allocator(tmp_path, config, reason='RAM_BELOW_MINIMUM', probe=None):
    return WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'refused'),
        probe=probe or FakeProbe(),
        base_environment={},
        claim_root=claim_root(),
        start_guard=_refusing_guard(tmp_path, reason),
    )


def test_selected_ik_backend_survives_worker_environment_allocation(tmp_path, config):
    resource_allocator = allocator(
        tmp_path, config, environment={'SO101_IK_BACKEND': 'quik'}, suffix='ik-backend'
    )
    manifest = resource_allocator.allocate(worker_count=1)
    assert manifest.workers[0].environment.get('SO101_IK_BACKEND') == 'quik'


def test_resources_use_frozen_domain_sequence_and_private_worker_layout(tmp_path, config):
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-layout'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        start_guard=_start_guard_for(config),
    )
    manifest = resource_allocator.allocate(worker_count=3)

    assert [worker.ros_domain_id for worker in manifest.workers] == [181, 182, 183]


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

    worker = allocator(tmp_path, config, environment=base).allocate(worker_count=2).workers[0]

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
    original = resource_allocator.allocate(worker_count=2).workers[0]

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
    resource_allocator.allocate(worker_count=2)

    with pytest.raises(ResourceAllocationError, match=message):
        resource_allocator.replace(worker_id, expected_generation=generation)


def test_three_workers_are_explicit_and_never_silently_downgraded(tmp_path, config):
    """A refused start neither downgrades the requested count nor leaves a partial root."""

    refused = refusing_allocator(tmp_path, config, 'RAM_BELOW_MINIMUM')
    with pytest.raises(ResourceAllocationError, match='RAM_BELOW_MINIMUM') as caught:
        refused.allocate(worker_count=3)
    assert caught.value.admission.admitted is False
    assert not refused.evidence_root.exists()

    manifest = allocator(tmp_path, config).allocate(worker_count=3)
    assert manifest.worker_count == 3
    assert len(manifest.workers) == 3


@pytest.mark.parametrize('worker_count', [True, 0, -1, 9])
def test_worker_count_must_be_positive_and_within_frozen_maximum(tmp_path, config, worker_count):
    with pytest.raises(ResourceAllocationError, match='WORKER_COUNT'):
        allocator(tmp_path, config).allocate(worker_count=worker_count)


@pytest.mark.parametrize(
    'reason',
    ['CPU_CAPACITY_UNAVAILABLE', 'RAM_BELOW_MINIMUM', 'GPU_FREE_BELOW_MINIMUM',
     'GPU_TARGET_NOT_VISIBLE'],
)
def test_each_guard_failure_fails_closed_without_creating_directories(
    tmp_path, config, reason
):
    resource_allocator = refusing_allocator(tmp_path, config, reason)
    with pytest.raises(ResourceAllocationError, match=reason):
        resource_allocator.allocate(worker_count=2)
    assert not resource_allocator.evidence_root.exists()


def test_admission_records_the_start_guard_decision(tmp_path, config):
    """The manifest carries the guard's own decision, not a fabricated budget pass."""

    from so101_demo.parallel_batch.resource_allocation.manifest import StartGuardAdmission

    manifest = allocator(tmp_path, config).allocate(worker_count=2)

    admission = manifest.admission
    assert isinstance(admission, StartGuardAdmission)
    assert admission.status in ('PASS', 'WARN')
    assert admission.cleanup_state == CLEAR
    assert set(admission.checks) == {'cpu_capacity', 'cpu_busy', 'ram', 'gpu'}
    assert admission.checks['ram']['unit'] == 'bytes'
    assert admission.checks['gpu']['unit'] == 'bytes'
    assert manifest.start_guard['status'] == admission.status
    assert manifest.start_guard['checks']['ram']['reason'] == admission.checks['ram']['reason']
    assert manifest.schema_version == 3


def test_existing_ros_domain_fails_before_any_directory_is_created(tmp_path, config):
    probe = FakeProbe(domains=(182,))
    resource_allocator = allocator(tmp_path, config, probe)

    with pytest.raises(ResourceAllocationError, match='ROS_DOMAIN_IN_USE: 182'):
        resource_allocator.allocate(worker_count=2)
    assert probe.domain_calls == [181, 182]
    assert not resource_allocator.evidence_root.exists()


@pytest.mark.parametrize('collision', ['domain', 'socket'])
def test_recovery_reprobes_live_namespace_and_preserves_existing_root(
    tmp_path, config, collision, monkeypatch
):
    original = allocator(tmp_path, config)
    manifest = original.allocate(worker_count=1)
    original.close()
    marker = original.evidence_root / 'unrelated-owner-marker'
    marker.write_bytes(b'preserve-me')
    before = (marker.stat().st_ino, marker.read_bytes())
    socket_path = original._paths(1)['socket_path']
    probe = FakeProbe(
        domains=(181,) if collision == 'domain' else (),
        sockets=(socket_path,) if collision == 'socket' else (),
    )
    recovered = WorkerResourceAllocator(
        config,
        original.evidence_root,
        probe=probe,
        base_environment={},
        claim_root=claim_root(),
        start_guard=_start_guard_for(config),
    )
    expected = 'ROS_DOMAIN_IN_USE: 181' if collision == 'domain' else 'SOCKET_CONFLICT'

    try:
        with pytest.raises(ResourceAllocationError, match=expected):
            recovered.adopt_existing(manifest)
    finally:
        recovered.close()

    assert (marker.stat().st_ino, marker.read_bytes()) == before
    assert recovered.manifest is None
    assert probe.domain_calls == [181]
    if collision == 'socket':
        assert probe.socket_calls == [socket_path]


def test_recovery_probe_failure_is_closed_without_touching_existing_root(
    tmp_path, config, monkeypatch
):
    original = allocator(tmp_path, config)
    manifest = original.allocate(worker_count=1)
    original.close()
    marker = original.evidence_root / 'unrelated-owner-marker'
    marker.write_bytes(b'preserve-me')

    class BrokenProbe(FakeProbe):
        def ros_domain_in_use(self, _domain_id):
            raise OSError('probe unavailable')

    recovered = WorkerResourceAllocator(
        config,
        original.evidence_root,
        probe=BrokenProbe(),
        base_environment={},
        claim_root=claim_root(),
        start_guard=_start_guard_for(config),
    )
    try:
        with pytest.raises(ResourceAllocationError, match='PROBE_FAILED'):
            recovered.adopt_existing(manifest)
    finally:
        recovered.close()
    assert marker.read_bytes() == b'preserve-me'
    assert recovered.manifest is None


def test_recovery_clean_namespace_probe_allows_exact_manifest_adoption(
    tmp_path, config, monkeypatch
):
    original = allocator(tmp_path, config)
    manifest = original.allocate(worker_count=1)
    original.close()
    probe = FakeProbe()
    recovered = WorkerResourceAllocator(
        config,
        original.evidence_root,
        probe=probe,
        base_environment={},
        claim_root=claim_root(),
        start_guard=_start_guard_for(config),
    )

    adopted = recovered.adopt_existing(manifest)

    assert adopted.workers == manifest.workers
    assert probe.domain_calls == [181]
    assert probe.socket_calls == [original._paths(1)['socket_path']]
    recovered.close()


def test_existing_evidence_or_worker_directory_fails_closed(tmp_path, config):
    root = resource_root(tmp_path)
    root.mkdir()

    with pytest.raises(ResourceAllocationError, match='DIRECTORY_CONFLICT'):
        WorkerResourceAllocator(
            config, root, probe=FakeProbe(), claim_root=claim_root(),
            start_guard=_start_guard_for(config),
        ).allocate(worker_count=2)


def test_existing_socket_reservation_fails_before_directory_creation(tmp_path, config):
    root = resource_root(tmp_path)
    resource_allocator = WorkerResourceAllocator(
        config, root, probe=FakeProbe(), claim_root=claim_root(),
        start_guard=_start_guard_for(config),
    )
    socket_path = resource_allocator._paths(2)['socket_path']
    probe = FakeProbe(sockets=(socket_path,))

    with pytest.raises(ResourceAllocationError, match='SOCKET_CONFLICT'):
        WorkerResourceAllocator(
            config, root, probe=probe, claim_root=claim_root(),
            start_guard=_start_guard_for(config),
        ).allocate(worker_count=2)
    assert not root.exists()


def test_socket_path_must_fit_unix_domain_limit(tmp_path, config, monkeypatch):
    root = resource_root(tmp_path)
    resource_allocator = WorkerResourceAllocator(
        config, root, probe=FakeProbe(), claim_root=claim_root(),
        start_guard=_start_guard_for(config),
    )
    original_paths = resource_allocator._paths

    def paths_with_long_socket(slot_index):
        paths = original_paths(slot_index)
        # The kernel limit applies to the short dirfd sockaddr, so the true oversized
        # boundary is an overlong basename, not a long durable canonical ancestor.
        paths['socket_namespace'] = tmp_path / ('x' * 100)
        paths['socket_path'] = paths['socket_namespace'] / ('control-' + 'y' * 120 + '.sock')
        return paths

    monkeypatch.setattr(resource_allocator, '_paths', paths_with_long_socket)

    with pytest.raises(ResourceAllocationError, match='UNIX_SOCKET_PATH_TOO_LONG'):
        resource_allocator.allocate(worker_count=2)
    assert not root.exists()


def test_short_external_ipc_root_preserves_long_durable_evidence_root(tmp_path, config):
    root = tmp_path / ("durable-" + "x" * 90)
    ipc_root = runtime_ipc_base() / f"so101-test-{os.getpid()}"
    assert not ipc_root.exists()
    resource_allocator = WorkerResourceAllocator(
        config,
        root,
        probe=FakeProbe(),
        claim_root=claim_root(),
        start_guard=_start_guard_for(config),
        ipc_root=ipc_root,
    )
    try:
        manifest = resource_allocator.allocate(1)
        worker = manifest.workers[0]

        assert worker.worker_root.is_relative_to(root)
        assert worker.socket_path == ipc_root / "1/s"
        capacity = (
            resources_api_allocator_layout.DARWIN_SUN_PATH_CAPACITY_BYTES
            if sys.platform == 'darwin'
            else resources_api_allocator_layout.LINUX_SUN_PATH_CAPACITY_BYTES
        )
        assert len(os.fsencode(worker.socket_path)) + 1 <= capacity
        assert not (root / "ipc").exists()
    finally:
        resource_allocator.close()
        shutil.rmtree(ipc_root, ignore_errors=True)


def test_runtime_ipc_base_is_closed_to_same_user_runtime_directory():
    expected = runtime_ipc_base()
    assert configured_runtime_ipc_root(
        "b1234", {"SO101_PARALLEL_IPC_BASE": str(expected)}
    ) == expected / "so101-b1234"
    with pytest.raises(ResourceAllocationError, match="IPC_BASE"):
        configured_runtime_ipc_root(
            "b1234", {"SO101_PARALLEL_IPC_BASE": "/tmp"}
        )


def test_probe_exceptions_fail_closed_without_allocating(tmp_path, config):
    class BrokenProbe(FakeProbe):
        def ros_domain_in_use(self, domain_id):
            raise OSError('probe unavailable')

    with pytest.raises(ResourceAllocationError, match='PROBE_FAILED'):
        resource_allocator = allocator(tmp_path, config, BrokenProbe())
        resource_allocator.allocate(worker_count=2)
    assert not resource_allocator.evidence_root.exists()


def test_allocation_uses_exclusive_directory_creation(tmp_path, config, monkeypatch):
    calls = []
    original = os.mkdir

    def observed_mkdir(path, *args, **kwargs):
        calls.append((path, kwargs.get('mode'), kwargs.get('dir_fd')))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, 'mkdir', observed_mkdir)
    allocator(tmp_path, config).allocate(worker_count=2)

    # The allocator creates its own directories exclusively at a dir_fd with mode 0700.
    # The guard's private state root is also 0700 but is created through pathlib, so it is
    # excluded here rather than loosening the allocator's rule.
    allocator_calls = [entry for entry in calls if entry[2] is not None]
    assert allocator_calls, calls
    assert all(mode == 0o700 for _path, mode, _dir_fd in allocator_calls)
    assert all(not os.path.isabs(path) for path, _mode, _dir_fd in allocator_calls)


def test_manifest_document_is_json_safe_and_contains_no_numeric_ports(tmp_path, config):
    manifest = allocator(tmp_path, config).allocate(worker_count=2)
    document = manifest.to_dict()

    assert json.loads(json.dumps(document)) == document
    assert document['backend'] == 'mujoco'
    assert document['workers'][0]['simulation_port'] == 'not_applicable'
    assert document['workers'][0]['bridge_port'] == 'not_applicable'
    assert document['workers'][0]['gz_partition'] == 'not_applicable'


def test_dry_run_cli_writes_private_manifest_without_starting_processes(tmp_path, monkeypatch):
    root = resource_root(tmp_path, 'dry')
    calls = []

    if sys.platform == 'darwin':
        # This test never binds a socket; Darwin's missing dirfd transport is covered
        # separately and must not hide which schema-v3 resource probe was invoked.
        monkeypatch.setattr(resources_api_allocator_layout, 'require_transport_basename', lambda _path: None)

    def retired_probe(_self):
        raise AssertionError('schema-v3 must use only the lightweight start guard')

    monkeypatch.setattr(
        'so101_demo.parallel_batch.resource_allocation.probe.SystemResourceProbe.snapshot',
        retired_probe,
    )
    monkeypatch.setattr(
        'so101_demo.parallel_batch.resource_allocation.probe.SystemResourceProbe.ros_domain_in_use',
        lambda self, domain_id: False,
    )
    monkeypatch.setattr(
        'so101_demo.parallel_batch.resource_allocation.probe.SystemResourceProbe.socket_in_use',
        lambda self, path: False,
    )
    if sys.platform != 'darwin':
        monkeypatch.setattr(
            'subprocess.Popen',
            lambda *args, **kwargs: calls.append((args, kwargs)),
            raising=False,
        )

    exit_code = main(
        [
            '--config',
            str(CLI_CONFIG_PATH),
            '--worker-count',
            '2',
            '--evidence-root',
            str(root),
            '--dry-run',
        ],
        claim_root=claim_root(),
    )

    manifest_path = root / 'resource_manifest.json'
    document = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert exit_code == 0
    assert calls == []
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert document['mode'] == 'dry_run'
    assert document['worker_count'] == 2
    assert [worker['ros_domain_id'] for worker in document['workers']] == [181, 182]


def test_default_single_worker_cli_refuses_retired_self_signed_evidence(tmp_path, config):
    """The CLI refuses the retired evidence chain with the explicit retired error."""

    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    with pytest.raises(CliError, match='LIVE_HEADROOM_EVIDENCE_UNEXPECTED'):
        prepare_batch(
            production_batch_argv(
                resource_root(tmp_path, 'dry-one'),
                worker_count='1',
            ) + ['--live-headroom-evidence', str(tmp_path / 'retired.json')],
            provenance_verifier=lambda _inputs: {'source_commit': 'a' * 40},
        )


def test_cli_requires_dry_run_and_does_not_create_output(tmp_path):
    root = resource_root(tmp_path, 'not-dry')

    with pytest.raises(SystemExit):
        main(
            [
                '--config',
                str(CLI_CONFIG_PATH),
                '--evidence-root',
                str(root),
            ],
            claim_root=claim_root(),
        )
    assert not root.exists()


@pytest.mark.parametrize(
    'reason', ['CPU_CAPACITY_UNAVAILABLE', 'RAM_BELOW_MINIMUM', 'GPU_FREE_BELOW_MINIMUM'])
def test_fixed_eight_refuses_without_reducing_the_count(tmp_path, config, reason):
    """A refused eight-worker start keeps the requested count and leaves no root behind."""

    owner = refusing_allocator(tmp_path, config, reason)
    try:
        with pytest.raises(ResourceAllocationError, match=reason) as caught:
            owner.allocate(8)
        assert caught.value.admission.admitted is False
        assert not owner.evidence_root.exists()
    finally:
        owner.close()


def test_fixed_eight_refusal_makes_no_domain_claims(tmp_path, config):
    """A refused eight-worker start claims no ROS domain and creates no root."""

    probe = FakeProbe()
    owner = refusing_allocator(tmp_path, config, 'GPU_FREE_BELOW_MINIMUM', probe=probe)
    try:
        with pytest.raises(ResourceAllocationError, match="GPU_FREE_BELOW_MINIMUM"):
            owner.allocate(8)
        assert probe.domain_calls == []
        assert not owner.evidence_root.exists()
    finally:
        owner.close()


def test_linux_cuda_adopt_existing_rechecks_the_start_guard(tmp_path, config):
    """The version-three restore path re-runs one fresh bounded check."""

    from so101_demo.parallel_batch.resources import WorkerResourceAllocator

    root = resource_root(tmp_path, 'v3-adopt')
    owner = WorkerResourceAllocator(
        config, root, probe=FakeProbe(), base_environment={},
        claim_root=claim_root(), start_guard=_start_guard_for(config))
    manifest = owner.allocate(worker_count=2)
    assert manifest.schema_version == 3
    assert manifest.start_guard['status'] in ('PASS', 'WARN')
    owner.write_manifest()
    owner.close()

    restored = WorkerResourceAllocator(
        config, root, probe=FakeProbe(), base_environment={},
        claim_root=claim_root(), start_guard=_start_guard_for(config))
    try:
        adopted = restored.adopt_existing(manifest)
        assert adopted.schema_version == 3
        assert adopted.start_guard['status'] in ('PASS', 'WARN')
    finally:
        restored.close()


def test_start_guard_scope_takes_its_selector_from_the_macos_mps_two_worker_accelerator() -> None:
    """The v4 document has no `gpu_device`; the guard scope must use the resolved accelerator.

    Schema v4 replaced the v3 CUDA device reference with the closed platform combination, so a
    Darwin document carries `accelerator` (`mps` + `default`) instead. The scope built for the
    guard therefore reads `MPS:default`, and the v3 CUDA form still wins when `gpu_device` exists.
    """

    from types import SimpleNamespace

    from so101_demo.parallel_batch.resources import WorkerResourceAllocator

    seen = []

    class _Recorded(Exception):
        """Stop the check right after the scope exists; the scope is the thing under test."""

    class _Guard:
        def require_before_spawn(self, scope):
            seen.append(scope)
            raise _Recorded

    v4_self = SimpleNamespace(
        _start_guard=_Guard(),
        config=SimpleNamespace(
            accelerator=SimpleNamespace(kind="mps", resolved_selector="default")
        ),
        batch_id="unit-v4",
    )
    with pytest.raises(_Recorded):
        WorkerResourceAllocator._start_guard_check(v4_self, 2)

    v3_self = SimpleNamespace(
        _start_guard=_Guard(),
        config=SimpleNamespace(
            gpu_device=SimpleNamespace(
                selector_kind="UUID", selector="GPU-00000000-0000-0000-0000-000000000000"
            )
        ),
        batch_id="unit-v3",
    )
    with pytest.raises(_Recorded):
        WorkerResourceAllocator._start_guard_check(v3_self, 4)

    assert [scope.gpu_selector for scope in seen] == [
        "MPS:default",
        "UUID:GPU-00000000-0000-0000-0000-000000000000",
    ]


def test_domain_claim_check_reads_the_durable_claim(tmp_path: Path) -> None:
    """The v4 domain check answers from the claim file, not from `/proc`.

    It must not report the allocator's own claim as a conflict (the allocator already holds the
    flock when the check runs), must see a live other owner, must ignore a stale file, and must
    fail closed on a malformed one.
    """

    import json
    import os
    from pathlib import Path as _Path
    import subprocess
    import sys
    import time
    from types import SimpleNamespace

    from so101_demo.parallel_batch.resource_allocation.models import ResourceAllocationError
    from so101_demo.parallel_batch.resources import WorkerResourceAllocator

    claim_root = _Path(tmp_path) / "claims"
    claim_root.mkdir(mode=0o700)
    stub = SimpleNamespace(claim_root=claim_root)

    assert WorkerResourceAllocator._domain_claimed_by_another_campaign(stub, 231) is False

    own = claim_root / "domain-231.lock"
    own.write_text(json.dumps({"pid": os.getpid()}))
    assert WorkerResourceAllocator._domain_claimed_by_another_campaign(stub, 231) is False

    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    try:
        own.write_text(json.dumps({"pid": live.pid}))
        assert WorkerResourceAllocator._domain_claimed_by_another_campaign(stub, 231) is True
        live.terminate()
        live.wait(timeout=10)
        time.sleep(0.2)
        assert WorkerResourceAllocator._domain_claimed_by_another_campaign(stub, 231) is False
    finally:
        if live.poll() is None:
            live.kill()

    own.write_text("not json")
    try:
        WorkerResourceAllocator._domain_claimed_by_another_campaign(stub, 231)
    except ResourceAllocationError as error:
        assert "PROBE_FAILED: claim malformed" in str(error)
    else:  # pragma: no cover - the failure must be explicit
        raise AssertionError("a malformed claim must fail closed")
