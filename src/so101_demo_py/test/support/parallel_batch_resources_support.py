"""Fakes and fixtures shared by the parallel batch resource tests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

from paths import PACKAGE_ROOT
import pytest

from so101_demo.parallel_batch.resource_allocation.models import (
    ResourceSnapshot,
    runtime_ipc_base,
)
from so101_demo.parallel_batch.resources import WorkerResourceAllocator

PACKAGE = PACKAGE_ROOT


CONFIG_PATH = PACKAGE / 'config/mujoco/parallel_batch_linux_cuda.yaml'


CLI_CONFIG_PATH = PACKAGE / 'config/mujoco/parallel_batch_linux_cuda.yaml'


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
    from so101_demo.parallel_batch.contracts.linux_cuda import (
        load_parallel_runtime_config_linux_cuda,
    )

    return load_parallel_runtime_config_linux_cuda(CLI_CONFIG_PATH)


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


def production_batch_argv(
    root,
    *,
    worker_count='3',
    evidence=None,
    acceptance=None,
    current_provenance_root=None,
):
    points = PACKAGE / 'config/mujoco/moveit_expert_validation_points.yaml'
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


def _start_guard_for(config):
    """The real composition over the real reads (the probe process is the seam)."""

    from so101_demo.parallel_batch.start_guard_probe import compose_default_start_guard

    return compose_default_start_guard(config.start_guard)
