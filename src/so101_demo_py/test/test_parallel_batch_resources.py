"""Behavior contracts for isolated parallel Worker resources."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from dataclasses import FrozenInstanceError
import fcntl
import hashlib
import json
import math
import os
import time
from pathlib import Path
from queue import Queue
import signal
import shutil
import subprocess
import sys
import tempfile
from threading import Barrier, Event
from types import SimpleNamespace

import pytest

from so101_demo.parallel_batch import resources as resources_api
from so101_demo.parallel_batch.start_guard_probe import (
    CLEAR,
    ProbeCoordinator,
)
from so101_demo.parallel_batch.contracts import load_parallel_runtime_config
from so101_demo.parallel_batch.resources import (
    AllocationPolicy,
    main,
    ResourceAllocationError,
    ResourceSnapshot,
    SystemResourceProbe,
    WorkerResourceAllocator,
    configured_runtime_ipc_root,
    runtime_ipc_base,
)


PACKAGE = Path(__file__).resolve().parents[1]
CONFIG_PATH = PACKAGE / 'config/mujoco/parallel_batch_v1.yaml'
CLI_CONFIG_PATH = PACKAGE / 'config/mujoco/parallel_batch_v3.yaml'
V2_CONFIG_PATH = PACKAGE / 'config/mujoco/parallel_batch_v2.yaml'


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
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v3

    return load_parallel_runtime_config_v3(CLI_CONFIG_PATH)


@pytest.fixture
def legacy_config():
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v2

    return load_parallel_runtime_config_v2(V2_CONFIG_PATH)


@pytest.fixture(autouse=True)
def production_claim_records_are_never_mutated_by_unit_tests():
    paths = tuple(
        runtime_ipc_base() / f'so101-parallel-domain-claims/domain-{domain}.lock'
        for domain in (181, 182, 183)
    )

    def snapshot(path):
        if not os.path.lexists(path):
            return {'exists': False}
        value = path.stat()
        content = path.read_bytes()
        return {
            'exists': True,
            'content': content,
            'sha256': hashlib.sha256(content).hexdigest(),
            'mtime_ns': value.st_mtime_ns,
        }

    before = {path: snapshot(path) for path in paths}
    yield
    after = {path: snapshot(path) for path in paths}
    assert after == before


_COMPOSED_START_GUARD = object()


def allocator(
    tmp_path, config, probe=None, environment=None, suffix='batch', start_guard=_COMPOSED_START_GUARD
):
    return WorkerResourceAllocator(
        config,
        resource_root(tmp_path, suffix),
        probe=probe or FakeProbe(),
        base_environment=environment or {},
        claim_root=claim_root(),
        start_guard=(
            _start_guard_for(config) if start_guard is _COMPOSED_START_GUARD else start_guard
        ),
    )


def _local_guard_check(self, policy, scope):
    """Run the real guard decision against real host reads, without spawning a helper.

    Only the probe *process* boundary is replaced. The snapshot still comes from the real
    cgroup/meminfo/NVML reads through ``probe_snapshot`` and the decision is still the real
    ``evaluate_snapshot``; the helper process itself is proven in
    ``test_parallel_start_guard_probe.py`` and in the CLI-level composition test.
    """

    import dataclasses as _dataclasses
    import time as _time

    from so101_demo.parallel_batch import start_guard as _guard

    started = _time.monotonic()
    ports = _dataclasses.replace(_guard.host_ports(), busy_window_s=0.0)
    if sys.platform == "darwin":
        class MacTestGpu:
            def devices(self):
                return (_guard.GpuDevice(0, "GPU-MACOS-TEST", 16 << 30, 8 << 30),)

        ports = _dataclasses.replace(ports, nvml=MacTestGpu())
    try:
        snapshot = _guard.probe_snapshot(policy, scope, started + policy.timeout_s, ports=ports)
        return _guard.evaluate_snapshot(snapshot, policy, scope, started_monotonic_s=started,
                                        completed_monotonic_s=_time.monotonic())
    except _guard.ProbeError as error:
        return _guard.GuardResult(
            scope=scope, status=_guard.FAIL, started_monotonic_s=started,
            completed_monotonic_s=_time.monotonic(),
            checks={"probe": _guard.GuardCheck(_guard.FAIL, error.reason, None, None, "state")},
            snapshot=None, cleanup_state="CLEAR")


@pytest.fixture(autouse=True)
def local_start_guard(monkeypatch, tmp_path_factory):
    """Offline seam: real reads and the real decision, no helper process per test."""

    from so101_demo.parallel_batch.start_guard_probe import ProbeCoordinator

    monkeypatch.setenv("SO101_TASK_ROOT", str(tmp_path_factory.mktemp("guard-root")))
    monkeypatch.setattr(ProbeCoordinator, "check", _local_guard_check)

def resource_root(tmp_path, suffix='batch'):
    """Keep UDS paths short while giving every test case its own root."""
    key = os.fsencode(tmp_path / suffix)
    return Path(os.environ['TMPDIR']).parent / f'rr-{hashlib.sha256(key).hexdigest()[:16]}'


def claim_root():
    # Persistent claim records intentionally survive descriptor release. Give
    # each pytest case its own stable claim namespace so a crash-recovery case
    # cannot make a later, independent allocator case look unclean.
    node_id = os.environ.get('PYTEST_CURRENT_TEST', 'standalone').split(' (', 1)[0]
    suffix = hashlib.sha256(node_id.encode('utf-8')).hexdigest()[:12]
    return Path(os.environ['TMPDIR']).parent / f'claims-{suffix}'


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS /tmp is a system alias')
def test_trusted_parent_accepts_the_root_owned_macos_tmp_alias():
    """The handoff's /tmp evidence root reaches the same trusted /private/tmp inode."""

    with tempfile.TemporaryDirectory(prefix='so101-tmp-alias-', dir='/private/tmp') as root:
        real_path = Path(root)
        relative = real_path.relative_to('/private/tmp')
        alias_target = Path('/tmp') / relative / 'batch'

        descriptor = resources_api._open_trusted_parent(alias_target)
        try:
            assert os.fstat(descriptor).st_ino == real_path.stat().st_ino
        finally:
            os.close(descriptor)


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS has no procfs stat')
def test_domain_claim_owner_has_a_portable_process_birth_identity():
    """Persistent ROS-domain claims remain PID-reuse safe without procfs."""

    assert resources_api._process_starttime_ticks() > 0


@pytest.mark.skipif(sys.platform != 'linux', reason='requires Linux /proc/<pid>/cmdline')
def test_oversized_cmdline_process_is_classified_not_refused():
    """A same-UID process with a huge argv must not make the whole probe fail closed.

    RED before the repair: SystemResourceProbe.ros_domain_in_use raised
    ResourceAllocationError(PROC_METADATA_UNVERIFIABLE) because /proc/<pid>/cmdline
    exceeded the 4 KiB read bound, which any inline-program or long pytest payload
    triggers on this host.
    """

    import subprocess
    import sys as _sys

    from so101_demo.parallel_batch.resources import ResourceAllocationError, SystemResourceProbe

    filler = "x" * 6000
    child = subprocess.Popen(
        [_sys.executable, "-c", "import time;time.sleep(30)", filler],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # Popen returns before the child execs; an empty cmdline is a race, not a result.
        deadline = time.monotonic() + 10
        cmdline = b""
        while time.monotonic() < deadline:
            cmdline = Path(f"/proc/{child.pid}/cmdline").read_bytes()
            if cmdline:
                break
            time.sleep(0.01)
        assert len(cmdline) > 4096
        probe = SystemResourceProbe()
        # The oversized-cmdline process is not a ROS/parallel-batch claimant.
        assert probe.ros_domain_in_use(213) is False
        report = probe.process_scan_report()
        assert report["unclassified_unreadable_policy"] == "fail_closed"
        del ResourceAllocationError
    finally:
        child.terminate()
        child.wait(timeout=10)


@pytest.mark.parametrize(
    "argv",
    [("sshd: robot.user@pts/7",), ("sshd: robot.user@notty",)],
)
def test_interactive_and_headless_sshd_transports_are_frozen_non_candidates(argv):
    """Remote execution must not read the protected environment of its sshd transport."""

    reason = resources_api._frozen_non_candidate_reason('S', 'sshd', argv)

    assert reason == 'frozen_sshd_transport_non_candidate'


@pytest.mark.parametrize(
    "argv",
    [("sshd: robot.user@tty7",), ("sshd: robot.user@notty extra",)],
)
def test_unknown_sshd_transport_shapes_remain_unclassified(argv):
    assert resources_api._frozen_non_candidate_reason('S', 'sshd', argv) is None


def test_claim_root_is_stable_per_test_and_isolated_between_tests(monkeypatch):
    monkeypatch.setenv('PYTEST_CURRENT_TEST', 'test/module.py::test_a (call)')
    first = claim_root()
    assert claim_root() == first

    monkeypatch.setenv('PYTEST_CURRENT_TEST', 'test/module.py::test_b (call)')
    assert claim_root() != first


def test_allocator_fixture_does_not_reuse_retained_cli_claim_namespace(
    tmp_path, config
):
    # Earlier CLI tests retain their 'rc' claim namespace in this same scratch.
    # The test-derived short root must stay distinct from that namespace.
    retained = Path(os.environ['TMPDIR']).parent / 'rc'
    retained.mkdir(mode=0o700, exist_ok=True)
    original = retained / 'retained-claim.json'
    original.write_bytes(b'{"role":"earlier-cli-claim"}\n')
    owner = allocator(tmp_path, config, suffix='after-cli')
    try:
        manifest = owner.allocate()
        assert [worker.ros_domain_id for worker in manifest.workers] == [181, 182]
        assert manifest.evidence_root != retained
        assert original.read_bytes() == b'{"role":"earlier-cli-claim"}\n'
    finally:
        owner.close()


def test_observational_policy_allocates_eight_without_headroom_rejection(
    tmp_path, config
):
    policy = AllocationPolicy(
        max_worker_count=8,
        ros_domain_ids=tuple(range(215, 223)),
        enforce_resource_thresholds=False,
        persistent_cleanup_claims=True,
    )
    target = resource_root(tmp_path, 'adaptive-eight')
    resource_allocator = WorkerResourceAllocator(
        config, target, probe=FakeProbe(cpu=1, ram=0.0, gpu=0.0),
        claim_root=resource_root(tmp_path, 'adaptive-claims'),
        allocation_policy=policy, batch_id='a001',
        start_guard=_start_guard_for(config),
    )

    manifest = resource_allocator.allocate(8)

    assert len(manifest.workers) == 8
    assert tuple(worker.ros_domain_id for worker in manifest.workers) == tuple(
        range(215, 223)
    )
    assert manifest.admission.admitted is True
    assert manifest.admission.status in ('PASS', 'WARN')
    assert manifest.worker_count == 8


def test_persistent_active_domain_record_rejects_reuse_after_lock_release(
    tmp_path, config
):
    policy = AllocationPolicy(1, (215,), False, True)
    claims = resource_root(tmp_path, 'persistent-claims')
    first = WorkerResourceAllocator(
        config, resource_root(tmp_path, 'first-active'), probe=FakeProbe(),
        claim_root=claims, allocation_policy=policy, batch_id='a001',
        start_guard=_start_guard_for(config),
    )
    first.allocate(1)
    first.close()
    second = WorkerResourceAllocator(
        config, resource_root(tmp_path, 'second-active'), probe=FakeProbe(),
        claim_root=claims, allocation_policy=policy, batch_id='a002',
        start_guard=_start_guard_for(config),
    )

    with pytest.raises(ResourceAllocationError, match='ROS_DOMAIN_UNCLEAN'):
        second.allocate(1)


def test_verified_cleanup_releases_persistent_domain_for_a_new_batch(
    tmp_path, config
):
    policy = AllocationPolicy(1, (215,), False, True)
    claims = Path(os.environ['TMPDIR']).parent / 'verified-release-claims'
    first = WorkerResourceAllocator(
        config, resource_root(tmp_path, 'release-first'), probe=FakeProbe(),
        claim_root=claims, allocation_policy=policy, batch_id='a001-g01-w01',
        start_guard=_start_guard_for(config),
    )
    first.allocate(1)

    assert first.release_persistent_claims(cleanup_verified=True) is True
    first.close()
    record = json.loads((claims / 'domain-215.lock').read_text(encoding='utf-8'))
    assert record['claim_state'] == 'RELEASED'
    assert record['cleanup_verified'] is True

    retry = WorkerResourceAllocator(
        config, resource_root(tmp_path, 'release-second'), probe=FakeProbe(),
        claim_root=claims, allocation_policy=policy, batch_id='a002-g02-w01',
        start_guard=_start_guard_for(config),
    )
    assert retry.allocate(1).worker_count == 1
    retry.release_persistent_claims(cleanup_verified=True)
    retry.close()


def test_prelaunch_allocation_failure_releases_persistent_claim(tmp_path, config):
    policy = AllocationPolicy(1, (215,), False, True)
    target = resource_root(tmp_path, 'prelaunch-failure')
    claims = Path(os.environ['TMPDIR']).parent / 'rollback-claims'
    socket_path = target / 'ipc/1/s'
    failing = WorkerResourceAllocator(
        config, target, probe=FakeProbe(sockets=(socket_path,)),
        claim_root=claims, allocation_policy=policy, batch_id='a001',
        start_guard=_start_guard_for(config),
    )

    with pytest.raises(ResourceAllocationError, match='SOCKET_CONFLICT'):
        failing.allocate(1)

    record = json.loads((claims / 'domain-215.lock').read_text(encoding='utf-8'))
    assert record['claim_state'] == 'RELEASED'
    assert record['no_processes_started'] is True


def production_batch_argv(
    root,
    *,
    worker_count='3',
    evidence=None,
    acceptance=None,
    current_provenance_root=None,
):
    points = PACKAGE / 'config/mujoco/moveit_expert_validation_points_v1.yaml'
    values = [
        '--points', str(points),
        '--config', str(CLI_CONFIG_PATH),
        '--batch-id', 'three-worker-headroom-test',
        '--worker-count', worker_count,
        '--evidence-root', str(root),
        '--broker-image', 'so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1',
        '--yolo-weights', '/models/yolo.pt',
        '--yolo-weights-sha256',
        'f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781',
        '--grounded-root', '/models/grounded',
        '--grounded-manifest-sha256',
        'b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05',
        '--run-mode', 'dry_run',
    ]
    if evidence is not None:
        values.extend(('--live-headroom-evidence', str(evidence)))
    if acceptance is not None:
        values.extend(('--live-headroom-acceptance', str(acceptance)))
    if current_provenance_root is not None:
        values.extend((
            '--live-headroom-current-provenance-root',
            str(current_provenance_root),
        ))
    return values


def test_production_cli_composes_three_workers_with_an_admitted_exact_n_gate(tmp_path):
    """Version two composes N=3 through the exact-N gate, not the retired evidence chain."""

    from so101_demo.cli.mujoco_parallel_batch import (
        ProductionBatchComposition, prepare_batch)

    root = resource_root(tmp_path, 'cli-three-valid')
    prepared = prepare_batch(
        production_batch_argv(root, worker_count='3'),
        provenance_verifier=lambda _inputs: {'source_commit': 'a' * 40},
    )
    composition = ProductionBatchComposition(
        prepared, resource_probe=FakeProbe(), claim_root=claim_root())
    try:
        assert composition.resource_manifest.worker_count == 3
        assert composition.resource_manifest.requested_worker_count == 3
    finally:
        composition._release_partial()


def test_production_cli_needs_no_budget_authority_for_three_workers(tmp_path, monkeypatch):
    """The retired default-gate hook no longer decides anything: the guard does."""

    import so101_demo.cli.mujoco_parallel_batch as parallel_cli
    from so101_demo.cli.mujoco_parallel_batch import prepare_batch

    monkeypatch.setattr(parallel_cli, '_DEFAULT_START_GUARD', None)
    prepared = prepare_batch(
        production_batch_argv(resource_root(tmp_path, 'cli-three-guarded')),
        provenance_verifier=lambda _inputs: {'source_commit': 'a' * 40},
    )
    assert prepared.start_guard is not None
    assert prepared.start_guard_evidence['status'] in ('PASS', 'WARN')


def test_production_cli_refuses_retired_headroom_authority_for_any_n(tmp_path, config):
    """The retired three-worker evidence chain is refused before it is even read."""

    from so101_demo.cli.mujoco_parallel_batch import CliError, prepare_batch

    for worker_count in ('2', '3'):
        with pytest.raises(CliError, match='LIVE_HEADROOM_EVIDENCE_UNEXPECTED'):
            prepare_batch(
                production_batch_argv(
                    resource_root(tmp_path, f'cli-legacy-{worker_count}'),
                    worker_count=worker_count,
                    evidence=tmp_path / 'retired-evidence.json',
                    acceptance=tmp_path / 'retired-acceptance.json',
                    current_provenance_root=tmp_path,
                ),
                provenance_verifier=lambda _inputs: {'source_commit': 'a' * 40},
            )
def test_production_cli_refuses_forged_or_stale_legacy_evidence(tmp_path, config):
    from so101_demo.cli.mujoco_parallel_batch import CliError, prepare_batch

    with pytest.raises(CliError, match='LIVE_HEADROOM_EVIDENCE_UNEXPECTED'):
        prepare_batch(
            production_batch_argv(
                resource_root(tmp_path, 'cli-three-forged'),
                evidence=tmp_path / 'forged.json',
                acceptance=tmp_path / 'forged-acceptance.json',
                current_provenance_root=tmp_path,
            ),
            provenance_verifier=lambda _inputs: {'source_commit': 'a' * 40},
        )
def rewrite_accepted_artifact(evidence, acceptance_path, name, **changes):
    sealed = evidence.parent
    artifacts_root = sealed / 'artifacts'
    artifact = artifacts_root / f'{name}.json'
    document = json.loads(artifact.read_text(encoding='utf-8'))
    document.update(changes)
    payload = json.dumps(document, sort_keys=True, separators=(',', ':')).encode()
    artifacts_root.chmod(0o755)
    artifact.chmod(0o600)
    artifact.write_bytes(payload)
    artifact.chmod(0o444)
    artifacts_root.chmod(0o555)
    manifest = json.loads(evidence.read_text(encoding='utf-8'))
    artifact_sha256 = hashlib.sha256(payload).hexdigest()
    manifest['artifacts'][name]['sha256'] = artifact_sha256
    manifest_payload = json.dumps(
        manifest, sort_keys=True, separators=(',', ':')
    ).encode()
    evidence.chmod(0o600)
    evidence.write_bytes(manifest_payload)
    evidence.chmod(0o444)
    acceptance = json.loads(acceptance_path.read_text(encoding='utf-8'))
    acceptance[f'{name}_sha256'] = artifact_sha256
    acceptance['candidate_manifest_sha256'] = hashlib.sha256(
        manifest_payload
    ).hexdigest()
    acceptance_path.write_text(json.dumps(acceptance), encoding='utf-8')


def drift_current_content_inventory(tmp_path, provenance_probe, identity_name):
    content_root = tmp_path / 'current-runtime-content'
    cases = {
        'install_tree_sha256': (
            content_root / 'install/lib/libparallel_runtime.so',
            b'v1',
            b'v2',
            'install_entry',
        ),
        'models_sha256': (
            content_root / 'source/models/detector.weights',
            b'v1',
            b'v2',
            'weights_sha256',
        ),
        'catalog_sha256': (
            content_root / 'source/config/validation-points.json',
            b'0.30',
            b'0.31',
            'coordinates_sha256',
        ),
        'policy_sha256': (
            content_root / 'source/config/policy.yaml',
            b'0.2',
            b'0.3',
            'content_sha256',
        ),
        'scene_sha256': (
            content_root / 'source/config/scene.sdf',
            b'task',
            b'task-drift',
            'content_sha256',
        ),
    }
    content_path, before, after, binding = cases[identity_name]
    content_path.chmod(0o600)
    original = content_path.read_bytes()
    replacement = original.replace(before, after, 1)
    assert replacement != original
    content_path.write_bytes(replacement)
    content_path.chmod(0o400)
    content_sha256 = hashlib.sha256(replacement).hexdigest()
    inventory_path = provenance_probe.current_paths[identity_name]
    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    if binding == 'install_entry':
        original_count = len(inventory['entries'])
        inventory['entries'][0]['sha256'] = content_sha256
        inventory['tree_sha256'] = hashlib.sha256(
            json.dumps(
                inventory['entries'], sort_keys=True, separators=(',', ':')
            ).encode()
        ).hexdigest()
        assert len(inventory['entries']) == original_count
    else:
        inventory[binding] = content_sha256
    inventory_path.chmod(0o600)
    inventory_path.write_text(
        json.dumps(inventory, sort_keys=True, separators=(',', ':')),
        encoding='utf-8',
    )
    inventory_path.chmod(0o400)


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
from so101_demo.parallel_batch import resources
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
            resources_api._write_manifest_at(
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
            resources_api._write_manifest_at(root_fd, final.name, {'replacement': True})
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
        resources_api.subprocess,
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
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v3

    return load_parallel_runtime_config_v3(CLI_CONFIG_PATH).start_guard


def refusing_allocator(tmp_path, config, reason='RAM_BELOW_MINIMUM', probe=None):
    return WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'refused'),
        probe=probe or FakeProbe(),
        base_environment={},
        claim_root=claim_root(),
        start_guard=_refusing_guard(tmp_path, reason),
    )

def _start_guard_for(config):
    """The real composition over the real reads (the probe process is the seam)."""

    from so101_demo.parallel_batch.start_guard_probe import compose_default_start_guard

    return compose_default_start_guard(config.start_guard)


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
        resource_allocator.allocate()
    assert not resource_allocator.evidence_root.exists()


def test_admission_records_the_start_guard_decision(tmp_path, config):
    """The manifest carries the guard's own decision, not a fabricated budget pass."""

    from so101_demo.parallel_batch.resources import StartGuardAdmission

    manifest = allocator(tmp_path, config).allocate()

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


@pytest.mark.parametrize(
    'snapshot',
    [
        ResourceSnapshot(True, 64.0, 12.0),
        ResourceSnapshot(32, math.nan, 12.0),
        ResourceSnapshot(32, 64.0, math.inf),
        ResourceSnapshot(32, -1.0, 12.0),
    ],
)
def test_malformed_resource_probe_values_fail_closed(tmp_path, legacy_config, snapshot):
    # The formula-budget path is the one that reads the injected probe. A v3 or v4
    # config decides through the start guard instead, which probes the host itself,
    # so an injected snapshot never reaches allocation there.
    probe = FakeProbe()
    probe.resources = snapshot
    with pytest.raises(ResourceAllocationError, match='INVALID_RESOURCE_SNAPSHOT'):
        allocator(tmp_path, legacy_config, probe, start_guard=None).allocate()


def test_existing_ros_domain_fails_before_any_directory_is_created(tmp_path, config):
    probe = FakeProbe(domains=(182,))
    resource_allocator = allocator(tmp_path, config, probe)

    with pytest.raises(ResourceAllocationError, match='ROS_DOMAIN_IN_USE: 182'):
        resource_allocator.allocate()
    assert probe.domain_calls == [181, 182]
    assert not resource_allocator.evidence_root.exists()


@pytest.mark.parametrize('collision', ['domain', 'socket'])
def test_recovery_reprobes_live_namespace_and_preserves_existing_root(
    tmp_path, config, collision, monkeypatch
):
    monkeypatch.setattr(resources_api, '_UNIX_SOCKET_PATH_MAX_BYTES', 4096)
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
    monkeypatch.setattr(resources_api, '_UNIX_SOCKET_PATH_MAX_BYTES', 4096)
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
    monkeypatch.setattr(resources_api, '_UNIX_SOCKET_PATH_MAX_BYTES', 4096)
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
        ).allocate()


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
        ).allocate()
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
        resource_allocator.allocate()
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
            resources_api.DARWIN_SUN_PATH_CAPACITY_BYTES
            if sys.platform == 'darwin'
            else resources_api.LINUX_SUN_PATH_CAPACITY_BYTES
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

    # The allocator creates its own directories exclusively at a dir_fd with mode 0700.
    # The guard's private state root is also 0700 but is created through pathlib, so it is
    # excluded here rather than loosening the allocator's rule.
    allocator_calls = [entry for entry in calls if entry[2] is not None]
    assert allocator_calls, calls
    assert all(mode == 0o700 for _path, mode, _dir_fd in allocator_calls)
    assert all(not os.path.isabs(path) for path, _mode, _dir_fd in allocator_calls)


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

    if sys.platform == 'darwin':
        # This test never binds a socket; Darwin's missing dirfd transport is covered
        # separately and must not hide which schema-v3 resource probe was invoked.
        monkeypatch.setattr(resources_api, 'require_transport_basename', lambda _path: None)

    def retired_probe(_self):
        raise AssertionError('schema-v3 must use only the lightweight start guard')

    monkeypatch.setattr(
        'so101_demo.parallel_batch.resources.SystemResourceProbe.snapshot',
        retired_probe,
    )
    monkeypatch.setattr(
        'so101_demo.parallel_batch.resources.SystemResourceProbe.ros_domain_in_use',
        lambda self, domain_id: False,
    )
    monkeypatch.setattr(
        'so101_demo.parallel_batch.resources.SystemResourceProbe.socket_in_use',
        lambda self, path: False,
    )
    if sys.platform != 'darwin':
        monkeypatch.setattr(
            'so101_demo.parallel_batch.resources.subprocess.Popen',
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


def test_default_three_worker_cli_refuses_retired_self_signed_evidence(tmp_path, config):
    """The CLI refuses the retired evidence chain with the explicit retired error."""

    from so101_demo.cli.mujoco_parallel_batch import CliError, prepare_batch

    with pytest.raises(CliError, match='LIVE_HEADROOM_EVIDENCE_UNEXPECTED'):
        prepare_batch(
            production_batch_argv(
                resource_root(tmp_path, 'dry-three'),
                worker_count='3',
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


def test_v3_adopt_existing_rechecks_the_start_guard(tmp_path, config):
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


def test_start_guard_scope_takes_its_selector_from_the_v4_accelerator() -> None:
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
    import subprocess
    import sys
    import time
    from pathlib import Path as _Path
    from types import SimpleNamespace

    from so101_demo.parallel_batch.resources import (
        ResourceAllocationError,
        WorkerResourceAllocator,
    )

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
