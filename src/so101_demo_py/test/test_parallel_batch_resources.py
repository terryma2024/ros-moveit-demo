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
import signal
import subprocess
import sys
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


@pytest.fixture(autouse=True)
def production_claim_records_are_never_mutated_by_unit_tests():
    paths = tuple(
        Path(f'/run/user/{os.getuid()}/so101-parallel-domain-claims/domain-{domain}.lock')
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
    sealed = tmp_path / 'task14-live-batch' / 'sealed'
    artifacts_root = sealed / 'artifacts'
    artifacts_root.mkdir(parents=True)
    batch_id = 'accepted-two-worker-live-001'
    source_commit = hashlib.sha1(b'task14-real-source-identity').hexdigest()
    container_image_id = 'sha256:' + hashlib.sha256(
        b'task14-real-container-image'
    ).hexdigest()
    artifact_documents = {
        'source_manifest': {'source_commit': source_commit, 'tree': 'verified-source-tree'},
        'install_manifest': {'install_prefix': '/verified/install', 'files': 17},
        'container_identity': {'image_id': container_image_id},
        'model_manifest': {'model': 'verified-yolo-first', 'revision': 3},
        'catalog': {'catalog_id': 'verified-twenty-point-catalog', 'points': 20},
        'resource_metrics': {
            'batch_id': batch_id,
            'worker_count': 2,
            'cpu_headroom_ratio': 0.30,
            'ram_headroom_ratio': 0.30,
            'gpu_headroom_ratio': 0.30,
        },
        'simulation_metrics': {
            'batch_id': batch_id,
            'backend': 'mujoco',
            'stable': True,
            'realtime_headroom_ratio': 0.25,
        },
        'render_metrics': {
            'batch_id': batch_id,
            'backend': 'headless_egl',
            'stable': True,
            'frame_headroom_ratio': 0.21,
        },
    }
    artifacts = {}
    for name, document in artifact_documents.items():
        path = artifacts_root / f'{name}.json'
        payload = json.dumps(document, sort_keys=True, separators=(',', ':')).encode()
        path.write_bytes(payload)
        path.chmod(0o444)
        artifacts[name] = {
            'path': f'artifacts/{name}.json',
            'sha256': hashlib.sha256(payload).hexdigest(),
        }
    source_identity = {
        'source_commit': source_commit,
        'source_manifest_sha256': artifacts['source_manifest']['sha256'],
        'runtime_config_sha256': hashlib.sha256(
            json.dumps(asdict(config), sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest(),
        'resources_module_sha256': hashlib.sha256(
            Path(resources_api.__file__).read_bytes()
        ).hexdigest(),
        'install_manifest_sha256': artifacts['install_manifest']['sha256'],
        'container_image_id': container_image_id,
        'container_identity_sha256': artifacts['container_identity']['sha256'],
        'model_manifest_sha256': artifacts['model_manifest']['sha256'],
        'catalog_sha256': artifacts['catalog']['sha256'],
    }
    document = {
        'schema_version': 1,
        'kind': 'task14_two_worker_live_headroom',
        'status': 'VALID',
        'batch_id': batch_id,
        'worker_count': 2,
        'run_mode': 'execute',
        'lifecycle': 'ISOLATED_STACK',
        'cleanup_complete': True,
        'source_identity': source_identity,
        'artifacts': artifacts,
        'headroom': {
            'cpu_ratio': 0.30,
            'ram_ratio': 0.30,
            'gpu_ratio': 0.30,
            'simulation_realtime_ratio': 0.25,
            'render_frame_ratio': 0.21,
        },
        'simulation': {
            'backend': 'mujoco',
            'stable': True,
            'metrics_artifact': 'simulation_metrics',
        },
        'rendering': {
            'backend': 'headless_egl',
            'stable': True,
            'metrics_artifact': 'render_metrics',
        },
    }
    for key, value in changes.items():
        if key.startswith('headroom_'):
            document['headroom'][key.removeprefix('headroom_')] = value
        elif key.startswith('source_'):
            source_key = key.removeprefix('source_')
            if source_key in document['source_identity']:
                document['source_identity'][source_key] = value
            elif source_key.endswith('_sha256'):
                artifact_name = source_key.removesuffix('_sha256')
                document['artifacts'][artifact_name]['sha256'] = value
            else:
                raise AssertionError(f'unknown live evidence source change: {key}')
        else:
            document[key] = value
    path = sealed / 'task14_headroom_manifest.json'
    path.write_text(json.dumps(document), encoding='utf-8')
    path.chmod(0o444)
    artifacts_root.chmod(0o555)
    sealed.chmod(0o555)
    return path


def shallow_accepted_live_evidence(tmp_path, config, **changes):
    evidence = live_evidence(tmp_path, config, **changes)
    sealed = evidence.parent
    artifacts_root = sealed / 'artifacts'
    sealed.chmod(0o755)
    artifacts_root.chmod(0o755)
    document = json.loads(evidence.read_text(encoding='utf-8'))
    artifact_documents = {
        'policy_manifest': {
            'policy_id': 'frozen-mujoco-pick-policy',
            'policy_revision': 1,
        },
        'scene_manifest': {
            'scene_id': 'frozen-mujoco-task-scene',
            'scene_revision': 1,
        },
        'aggregate': {
            'batch_id': document['batch_id'],
            'worker_count': 2,
            'run_mode': 'execute',
            'lifecycle': 'ISOLATED_STACK',
            'batch_terminal': True,
            'coverage_complete': True,
            'execution_complete': True,
            'qualification_applicable': True,
            'qualification_passed': True,
            'batch_cleanup_complete': True,
        },
        'cleanup': {
            'batch_id': document['batch_id'],
            'cleanup_complete': True,
            'active_owned_processes': 0,
        },
    }
    for name, artifact_document in artifact_documents.items():
        artifact = artifacts_root / f'{name}.json'
        payload = json.dumps(
            artifact_document, sort_keys=True, separators=(',', ':')
        ).encode()
        artifact.write_bytes(payload)
        artifact.chmod(0o444)
        document['artifacts'][name] = {
            'path': f'artifacts/{name}.json',
            'sha256': hashlib.sha256(payload).hexdigest(),
        }

    current_root = tmp_path / 'current-runtime-inputs'
    current_root.mkdir(mode=0o700)
    provenance_artifacts = {
        'source_tree_sha256': 'source_manifest',
        'install_tree_sha256': 'install_manifest',
        'policy_sha256': 'policy_manifest',
        'scene_sha256': 'scene_manifest',
        'models_sha256': 'model_manifest',
        'container_sha256': 'container_identity',
        'catalog_sha256': 'catalog',
    }
    current_paths = {}
    for identity_name, artifact_name in provenance_artifacts.items():
        current = current_root / f'{identity_name}.json'
        current.write_bytes((artifacts_root / f'{artifact_name}.json').read_bytes())
        current.chmod(0o400)
        current_paths[identity_name] = current
    runtime_config = current_root / 'runtime_config.json'
    runtime_config.write_bytes(
        json.dumps(asdict(config), sort_keys=True, separators=(',', ':')).encode()
    )
    runtime_config.chmod(0o400)
    current_paths['runtime_config_sha256'] = runtime_config
    provenance_probe = resources_api.CurrentRuntimeProvenanceProbe(
        current_paths=current_paths
    )
    provenance = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in current_paths.items()
    }
    if 'source_runtime_config_sha256' in changes:
        provenance['runtime_config_sha256'] = changes[
            'source_runtime_config_sha256'
        ]
    document['source_identity'] = provenance
    evidence.chmod(0o600)
    evidence.write_text(
        json.dumps(document, sort_keys=True, separators=(',', ':')),
        encoding='utf-8',
    )
    evidence.chmod(0o444)
    artifacts_root.chmod(0o555)
    sealed.chmod(0o555)

    acceptance_root = tmp_path / 'controller-acceptance'
    acceptance_root.mkdir(mode=0o700)
    acceptance_path = acceptance_root / 'task14-accepted-identity.json'
    acceptance = {
        'schema_version': 1,
        'authority': 'task14_controller_acceptance_v1',
        'status': 'VALID',
        'accepted_batch_id': document['batch_id'],
        'candidate_manifest_sha256': hashlib.sha256(evidence.read_bytes()).hexdigest(),
        'aggregate_sha256': document['artifacts']['aggregate']['sha256'],
        'cleanup_sha256': document['artifacts']['cleanup']['sha256'],
        'provenance': provenance,
    }
    acceptance_path.write_text(
        json.dumps(acceptance, sort_keys=True, separators=(',', ':')),
        encoding='utf-8',
    )
    acceptance_path.chmod(0o600)
    return evidence, acceptance_path, provenance_probe


def accepted_live_evidence(tmp_path, config, **changes):
    evidence, acceptance_path, provenance_probe = shallow_accepted_live_evidence(
        tmp_path, config, **changes
    )
    sealed = evidence.parent
    artifacts_root = sealed / 'artifacts'
    content_root = tmp_path / 'current-runtime-content'
    content_root.mkdir(mode=0o700)
    source_root = content_root / 'source'
    install_root = content_root / 'install'
    source_script = source_root / 'scripts/runner.py'
    dirty_patch = source_root / '.dirty.patch'
    install_library = install_root / 'lib/libparallel_runtime.so'
    install_script = install_root / 'libexec/parallel-worker'
    policy = source_root / 'config/policy.yaml'
    scene = source_root / 'config/scene.sdf'
    model_weights = source_root / 'models/detector.weights'
    catalog_coordinates = source_root / 'config/validation-points.json'
    content_payloads = {
        source_script: b'#!/usr/bin/python3\nprint("parallel worker")\n',
        dirty_patch: b'diff --git a/runtime.py b/runtime.py\n+DIRTY = True\n',
        install_library: b'ELF-parallel-runtime-content-v1',
        install_script: b'#!/bin/sh\nexec parallel-worker-bin "$@"\n',
        policy: b'max_velocity: 0.2\ncollision_margin: 0.01\n',
        scene: b'<sdf version="1.10"><world name="task"/></sdf>\n',
        model_weights: b'actual-model-weight-bytes-v1',
        catalog_coordinates: (
            b'{"points":[{"id":"p01","x":0.30,"y":0.00,"z":0.12}]}'
        ),
    }
    for path, payload in content_payloads.items():
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(0o400)

    def content_sha256(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    source_entries = [
        {
            'path': 'scripts/runner.py',
            'kind': 'file',
            'mode': '100755',
            'sha256': content_sha256(source_script),
        },
        {
            'path': 'vendor/runtime-support',
            'kind': 'gitlink',
            'mode': '160000',
            'commit': '1' * 40,
        },
    ]
    install_entries = [
        {
            'path': 'lib/libparallel_runtime.so',
            'mode': '100644',
            'sha256': content_sha256(install_library),
        },
        {
            'path': 'libexec/parallel-worker',
            'mode': '100755',
            'sha256': content_sha256(install_script),
        },
    ]
    artifact_documents = {
        'source_manifest': {
            'schema_version': 1,
            'source_commit': '59e8b9323eb5ad61542e0a1b6d4e918568d7ca8d',
            'source_root': str(source_root),
            'tree_sha256': hashlib.sha256(
                json.dumps(
                    source_entries, sort_keys=True, separators=(',', ':')
                ).encode()
            ).hexdigest(),
            'dirty_patch_sha256': content_sha256(dirty_patch),
            'entries': source_entries,
        },
        'install_manifest': {
            'schema_version': 1,
            'install_prefix': str(install_root),
            'tree_sha256': hashlib.sha256(
                json.dumps(
                    install_entries, sort_keys=True, separators=(',', ':')
                ).encode()
            ).hexdigest(),
            'entries': install_entries,
        },
        'container_identity': {
            'schema_version': 1,
            'image_id': 'sha256:'
            + hashlib.sha256(b'immutable-container-image-v1').hexdigest(),
        },
        'model_manifest': {
            'schema_version': 1,
            'model_path': 'models/detector.weights',
            'weights_sha256': content_sha256(model_weights),
        },
        'catalog': {
            'schema_version': 1,
            'catalog_path': 'config/validation-points.json',
            'coordinates_sha256': content_sha256(catalog_coordinates),
        },
        'policy_manifest': {
            'schema_version': 1,
            'policy_path': 'config/policy.yaml',
            'content_sha256': content_sha256(policy),
        },
        'scene_manifest': {
            'schema_version': 1,
            'scene_path': 'config/scene.sdf',
            'content_sha256': content_sha256(scene),
        },
    }
    sealed.chmod(0o755)
    artifacts_root.chmod(0o755)
    manifest = json.loads(evidence.read_text(encoding='utf-8'))
    evidence.chmod(0o600)
    for artifact_name, artifact_document in artifact_documents.items():
        payload = json.dumps(
            artifact_document, sort_keys=True, separators=(',', ':')
        ).encode()
        artifact_path = artifacts_root / f'{artifact_name}.json'
        artifact_path.chmod(0o600)
        artifact_path.write_bytes(payload)
        artifact_path.chmod(0o444)
        manifest['artifacts'][artifact_name]['sha256'] = hashlib.sha256(
            payload
        ).hexdigest()
        current_path = provenance_probe.current_paths[
            {
                'source_manifest': 'source_tree_sha256',
                'install_manifest': 'install_tree_sha256',
                'container_identity': 'container_sha256',
                'model_manifest': 'models_sha256',
                'catalog': 'catalog_sha256',
                'policy_manifest': 'policy_sha256',
                'scene_manifest': 'scene_sha256',
            }[artifact_name]
        ]
        current_path.chmod(0o600)
        current_path.write_bytes(payload)
        current_path.chmod(0o400)
    provenance = provenance_probe.snapshot(config)
    if 'source_runtime_config_sha256' in changes:
        provenance['runtime_config_sha256'] = changes[
            'source_runtime_config_sha256'
        ]
    manifest['source_identity'] = provenance
    manifest_payload = json.dumps(
        manifest, sort_keys=True, separators=(',', ':')
    ).encode()
    evidence.write_bytes(manifest_payload)
    evidence.chmod(0o444)
    artifacts_root.chmod(0o555)
    sealed.chmod(0o555)
    acceptance = json.loads(acceptance_path.read_text(encoding='utf-8'))
    acceptance['candidate_manifest_sha256'] = hashlib.sha256(
        manifest_payload
    ).hexdigest()
    acceptance['provenance'] = provenance
    acceptance_path.write_text(
        json.dumps(acceptance, sort_keys=True, separators=(',', ':')),
        encoding='utf-8',
    )
    return evidence, acceptance_path, provenance_probe


def accepted_task14_verifier(acceptance_path, provenance_probe):
    return resources_api.Task14LiveHeadroomVerifier(
        acceptance_provider=resources_api.Task14AcceptanceProvider(
            acceptance_path=acceptance_path
        ),
        provenance_probe=provenance_probe,
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


def test_default_three_workers_reject_caller_fabricated_live_headroom_evidence(
    tmp_path, config
):
    evidence = live_evidence(tmp_path, config)
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-live'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
    )
    try:
        with pytest.raises(
            ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'
        ) as caught:
            resource_allocator.allocate(worker_count=3)
    finally:
        resource_allocator.close()
    assert str(caught.value.__cause__) == 'TASK14_ACCEPTANCE_UNAVAILABLE'


def test_independent_acceptance_rejects_shallow_label_only_provenance(
    tmp_path, config
):
    evidence, acceptance_path, provenance_probe = shallow_accepted_live_evidence(
        tmp_path, config
    )
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-shallow-identities'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
        live_headroom_verifier=accepted_task14_verifier(
            acceptance_path, provenance_probe
        ),
    )
    try:
        with pytest.raises(
            ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'
        ):
            resource_allocator.allocate(worker_count=3)
    finally:
        resource_allocator.close()


def test_invalid_candidate_path_does_not_query_acceptance_or_provenance(
    tmp_path, config
):
    calls = []

    class ExplodingAcceptance:
        def accepted_identity(self, path):
            calls.append(('acceptance', path))
            raise AssertionError('invalid path reached acceptance provider')

    class ExplodingProvenance:
        def snapshot(self, config):
            calls.append(('provenance', config))
            raise AssertionError('invalid path reached provenance probe')

    verifier = resources_api.Task14LiveHeadroomVerifier(
        acceptance_provider=ExplodingAcceptance(),
        provenance_probe=ExplodingProvenance(),
    )
    invalid = tmp_path / 'not-sealed/not-the-task14-manifest.json'

    with pytest.raises(ResourceAllocationError, match='TASK14_SEALED_PATH_INVALID'):
        verifier.verify(invalid, config=config)
    assert calls == []


def test_three_workers_require_independent_acceptance_and_current_provenance(
    tmp_path, config
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    verifier = resources_api.Task14LiveHeadroomVerifier(
        acceptance_provider=resources_api.Task14AcceptanceProvider(
            acceptance_path=acceptance_path
        ),
        provenance_probe=provenance_probe,
    )
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-independently-accepted'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
        live_headroom_verifier=verifier,
    )
    manifest = resource_allocator.allocate(worker_count=3)

    accepted = manifest.live_headroom_evidence['acceptance_identity']
    assert manifest.worker_count == 3
    assert accepted['authority'] == 'task14_controller_acceptance_v1'
    assert accepted['candidate_manifest_sha256'] == (
        manifest.live_headroom_evidence['manifest_sha256']
    )
    assert manifest.live_headroom_evidence['current_provenance'] == (
        accepted['provenance']
    )
    resource_allocator.close()


def test_independent_acceptance_without_current_provenance_stays_fail_closed(
    tmp_path, config
):
    evidence, acceptance_path, _provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    verifier = resources_api.Task14LiveHeadroomVerifier(
        acceptance_provider=resources_api.Task14AcceptanceProvider(
            acceptance_path=acceptance_path
        )
    )
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-no-current-provenance'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
        live_headroom_verifier=verifier,
    )
    with pytest.raises(
        ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'
    ) as caught:
        resource_allocator.allocate(worker_count=3)

    assert str(caught.value.__cause__) == 'CURRENT_RUNTIME_PROVENANCE_UNAVAILABLE'


@pytest.mark.parametrize(
    'field',
    ['candidate_manifest_sha256', 'aggregate_sha256', 'cleanup_sha256'],
)
def test_three_worker_acceptance_identity_hashes_must_match_candidate(
    tmp_path, config, field
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    acceptance = json.loads(acceptance_path.read_text(encoding='utf-8'))
    acceptance[field] = hashlib.sha256(f'wrong-{field}'.encode()).hexdigest()
    acceptance_path.write_text(json.dumps(acceptance), encoding='utf-8')
    verifier = resources_api.Task14LiveHeadroomVerifier(
        acceptance_provider=resources_api.Task14AcceptanceProvider(
            acceptance_path=acceptance_path
        ),
        provenance_probe=provenance_probe,
    )

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, f'three-acceptance-{field}'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=verifier,
        ).allocate(worker_count=3)


@pytest.mark.parametrize(
    ('artifact_name', 'changes'),
    [
        ('aggregate', {'batch_terminal': False}),
        ('aggregate', {'qualification_applicable': False}),
        ('aggregate', {'batch_cleanup_complete': False}),
        ('cleanup', {'cleanup_complete': False}),
        ('cleanup', {'active_owned_processes': 1}),
    ],
)
def test_independently_accepted_aggregate_and_cleanup_semantics_are_mandatory(
    tmp_path, config, artifact_name, changes
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    rewrite_accepted_artifact(
        evidence, acceptance_path, artifact_name, **changes
    )

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, f'three-{artifact_name}-semantics'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_three_worker_acceptance_rejects_current_provenance_drift(tmp_path, config):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    provenance_probe.current_paths['scene_sha256'].chmod(0o600)
    provenance_probe.current_paths['scene_sha256'].write_text(
        '{"scene_id":"drifted-after-task14"}', encoding='utf-8'
    )
    verifier = resources_api.Task14LiveHeadroomVerifier(
        acceptance_provider=resources_api.Task14AcceptanceProvider(
            acceptance_path=acceptance_path
        ),
        provenance_probe=provenance_probe,
    )

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-current-provenance-drift'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=verifier,
        ).allocate(worker_count=3)


@pytest.mark.parametrize(
    'identity_name',
    [
        'install_tree_sha256',
        'models_sha256',
        'catalog_sha256',
        'policy_sha256',
        'scene_sha256',
    ],
)
def test_three_worker_rejects_real_current_content_drift(
    tmp_path, config, identity_name
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    drift_current_content_inventory(tmp_path, provenance_probe, identity_name)
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, f'three-content-drift-{identity_name}'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
        live_headroom_verifier=accepted_task14_verifier(
            acceptance_path, provenance_probe
        ),
    )
    try:
        with pytest.raises(
            ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'
        ):
            resource_allocator.allocate(worker_count=3)
    finally:
        resource_allocator.close()


@pytest.mark.parametrize('source_change', ['script', 'gitlink', 'dirty_patch'])
def test_three_worker_source_inventory_binds_full_tree_and_dirty_state(
    tmp_path, config, source_change
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    inventory_path = provenance_probe.current_paths['source_tree_sha256']
    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    content_root = tmp_path / 'current-runtime-content/source'
    if source_change == 'script':
        script = content_root / 'scripts/runner.py'
        script.chmod(0o600)
        script.write_bytes(script.read_bytes().replace(b'worker', b'changed-worker'))
        script.chmod(0o400)
        inventory['entries'][0]['sha256'] = hashlib.sha256(
            script.read_bytes()
        ).hexdigest()
    elif source_change == 'gitlink':
        inventory['entries'][1]['commit'] = '2' * 40
    else:
        dirty_patch = content_root / '.dirty.patch'
        dirty_patch.chmod(0o600)
        dirty_patch.write_bytes(dirty_patch.read_bytes() + b'+MORE_DIRTY = True\n')
        dirty_patch.chmod(0o400)
        inventory['dirty_patch_sha256'] = hashlib.sha256(
            dirty_patch.read_bytes()
        ).hexdigest()
    if source_change != 'dirty_patch':
        inventory['tree_sha256'] = hashlib.sha256(
            json.dumps(
                inventory['entries'], sort_keys=True, separators=(',', ':')
            ).encode()
        ).hexdigest()
    inventory_path.chmod(0o600)
    inventory_path.write_text(
        json.dumps(inventory, sort_keys=True, separators=(',', ':')),
        encoding='utf-8',
    )
    inventory_path.chmod(0o400)

    with pytest.raises(
        ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'
    ):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, f'three-source-drift-{source_change}'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_current_provenance_snapshot_rejects_cross_input_mixed_epoch(
    tmp_path, config, monkeypatch
):
    _evidence, _acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    target = provenance_probe.current_paths['policy_sha256']
    trigger = provenance_probe.current_paths['source_tree_sha256']
    target_stat = target.stat()
    original = resources_api._read_fd
    changed = False

    def mutate_prior_input_when_last_input_is_read(descriptor, limit):
        nonlocal changed
        payload = original(descriptor, limit)
        descriptor_path = Path(os.readlink(f'/proc/self/fd/{descriptor}'))
        if descriptor_path == trigger and not changed:
            changed = True
            original_bytes = target.read_bytes()
            replacement = original_bytes.replace(b'1', b'2', 1)
            assert len(replacement) == len(original_bytes)
            target.chmod(0o600)
            target.write_bytes(replacement)
            target.chmod(0o400)
            os.utime(
                target,
                ns=(target_stat.st_atime_ns, target_stat.st_mtime_ns),
            )
        return payload

    monkeypatch.setattr(resources_api, '_read_fd', mutate_prior_input_when_last_input_is_read)
    with pytest.raises(ResourceAllocationError):
        provenance_probe.snapshot(config)
    assert changed is True


@pytest.mark.parametrize('mutation', ['chmod', 'rewrite'])
def test_three_worker_rechecks_late_current_provenance_mutation(
    tmp_path, config, mutation
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    target = provenance_probe.current_paths['policy_sha256']
    original_probe = provenance_probe.snapshot
    calls = 0

    def mutate_after_first_snapshot(runtime_config):
        nonlocal calls
        calls += 1
        result = original_probe(runtime_config)
        if calls == 1:
            if mutation == 'chmod':
                target.chmod(0o600)
            else:
                target_stat = target.stat()
                original_bytes = target.read_bytes()
                replacement = original_bytes.replace(b'1', b'2', 1)
                assert len(replacement) == len(original_bytes)
                target.chmod(0o600)
                target.write_bytes(replacement)
                target.chmod(0o400)
                os.utime(
                    target,
                    ns=(target_stat.st_atime_ns, target_stat.st_mtime_ns),
                )
        return result

    provenance_probe.snapshot = mutate_after_first_snapshot
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, f'three-late-current-{mutation}'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
        live_headroom_verifier=accepted_task14_verifier(
            acceptance_path, provenance_probe
        ),
    )
    try:
        with pytest.raises(
            ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'
        ):
            resource_allocator.allocate(worker_count=3)
    finally:
        resource_allocator.close()
    assert calls == 2


@pytest.mark.parametrize('mutation', ['chmod', 'rewrite'])
def test_three_worker_rechecks_late_acceptance_mutation(tmp_path, config, mutation):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    provider = resources_api.Task14AcceptanceProvider(
        acceptance_path=acceptance_path
    )
    original_provider = provider.accepted_identity
    calls = 0

    def mutate_after_first_read(candidate_path):
        nonlocal calls
        calls += 1
        result = original_provider(candidate_path)
        if calls == 1:
            if mutation == 'chmod':
                acceptance_path.chmod(0o400)
            else:
                acceptance_stat = acceptance_path.stat()
                original_bytes = acceptance_path.read_bytes()
                replacement = original_bytes.replace(b'VALID', b'INVAL', 1)
                assert len(replacement) == len(original_bytes)
                acceptance_path.write_bytes(replacement)
                os.utime(
                    acceptance_path,
                    ns=(acceptance_stat.st_atime_ns, acceptance_stat.st_mtime_ns),
                )
        return result

    provider.accepted_identity = mutate_after_first_read
    verifier = resources_api.Task14LiveHeadroomVerifier(
        acceptance_provider=provider,
        provenance_probe=provenance_probe,
    )
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, f'three-late-acceptance-{mutation}'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
        live_headroom_verifier=verifier,
    )
    try:
        with pytest.raises(
            ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'
        ):
            resource_allocator.allocate(worker_count=3)
    finally:
        resource_allocator.close()
    assert calls == 2


def test_acceptance_provider_rejects_identity_inside_candidate_tree(tmp_path, config):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    sealed = evidence.parent
    sealed.chmod(0o755)
    in_tree = sealed / 'acceptance.json'
    in_tree.write_bytes(acceptance_path.read_bytes())
    in_tree.chmod(0o600)
    sealed.chmod(0o555)
    verifier = resources_api.Task14LiveHeadroomVerifier(
        acceptance_provider=resources_api.Task14AcceptanceProvider(
            acceptance_path=in_tree
        ),
        provenance_probe=provenance_probe,
    )

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-in-tree-acceptance'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=verifier,
        ).allocate(worker_count=3)


@pytest.mark.parametrize(
    ('change', 'value'),
    [
        ('headroom_cpu_ratio', 0.19),
        ('headroom_ram_ratio', float('nan')),
        ('headroom_gpu_ratio', float('inf')),
        ('headroom_simulation_realtime_ratio', -0.1),
        ('headroom_render_frame_ratio', 0.0),
        ('worker_count', 3),
        ('source_runtime_config_sha256', '0' * 64),
        ('simulation', {'backend': 'gazebo', 'stable': True}),
        ('rendering', {'backend': 'headless_egl', 'stable': False}),
        ('source_simulation_metrics_sha256', 'not-a-hash'),
    ],
)
def test_three_worker_live_evidence_fails_closed_on_schema_identity_or_headroom(
    tmp_path, config, change, value
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config, **{change: value}
    )

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, f'three-invalid-{change}'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_three_worker_live_evidence_rejects_artifact_hash_mismatch(tmp_path, config):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    document = json.loads(evidence.read_text())
    document['artifacts']['resource_metrics']['sha256'] = '0' * 64
    evidence.chmod(0o600)
    evidence.write_text(json.dumps(document))
    evidence.chmod(0o444)

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-hash'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_three_worker_live_evidence_rejects_missing_sealed_manifest(tmp_path, config):
    missing = tmp_path / 'missing-task14' / 'sealed/task14_headroom_manifest.json'

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-missing-seal'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=missing,
        ).allocate(worker_count=3)


def test_three_worker_live_evidence_rejects_tampered_hashed_artifact(
    tmp_path, config
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    artifact = evidence.parent / 'artifacts/resource_metrics.json'
    artifact.chmod(0o600)
    artifact.write_text('{"tampered":true}', encoding='utf-8')
    artifact.chmod(0o444)

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-tampered-artifact'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_three_worker_live_evidence_rejects_symlinked_artifact(tmp_path, config):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    artifacts = evidence.parent / 'artifacts'
    artifact = artifacts / 'resource_metrics.json'
    target = evidence.parent.parent / 'unsealed-resource-metrics.json'
    target.write_bytes(artifact.read_bytes())
    target.chmod(0o444)
    artifacts.chmod(0o755)
    artifact.unlink()
    artifact.symlink_to(target)
    artifacts.chmod(0o555)

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-symlink-artifact'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_three_worker_live_evidence_rejects_unsealed_file_mode(tmp_path, config):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    artifact = evidence.parent / 'artifacts/resource_metrics.json'
    artifact.chmod(0o600)

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-unsealed-mode'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_three_worker_live_evidence_rejects_duplicate_json_key(tmp_path, config):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    payload = evidence.read_text(encoding='utf-8')
    evidence.chmod(0o600)
    evidence.write_text(payload[:-1] + ',"status":"VALID"}', encoding='utf-8')
    evidence.chmod(0o444)

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-duplicate-key'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_three_worker_live_evidence_detects_artifact_directory_swap(
    tmp_path, config, monkeypatch
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    sealed = evidence.parent
    artifacts = sealed / 'artifacts'
    original = resources_api._read_sealed_json_at
    swapped = False

    def swap_after_last_read(parent_fd, name):
        nonlocal swapped
        result = original(parent_fd, name)
        if name == 'cleanup.json' and not swapped:
            swapped = True
            sealed.chmod(0o755)
            artifacts.rename(sealed / 'artifacts-displaced')
            artifacts.mkdir(mode=0o555)
            sealed.chmod(0o555)
        return result

    monkeypatch.setattr(resources_api, '_read_sealed_json_at', swap_after_last_read)
    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-artifact-swap'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_three_worker_live_evidence_rejects_late_same_inode_chmod(
    tmp_path, config, monkeypatch
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    artifact = evidence.parent / 'artifacts/resource_metrics.json'
    original = resources_api._read_sealed_json_at
    changed = False

    def chmod_after_last_read(parent_fd, name):
        nonlocal changed
        result = original(parent_fd, name)
        if name == 'cleanup.json' and not changed:
            changed = True
            artifact.chmod(0o600)
        return result

    monkeypatch.setattr(resources_api, '_read_sealed_json_at', chmod_after_last_read)
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-late-chmod'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
        live_headroom_verifier=accepted_task14_verifier(
            acceptance_path, provenance_probe
        ),
    )
    try:
        with pytest.raises(
            ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'
        ):
            resource_allocator.allocate(worker_count=3)
    finally:
        resource_allocator.close()
    assert changed is True


def test_three_worker_live_evidence_rejects_late_same_inode_rewrite(
    tmp_path, config, monkeypatch
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    artifact = evidence.parent / 'artifacts/resource_metrics.json'
    original_bytes = artifact.read_bytes()
    original_stat = artifact.stat()
    replacement = original_bytes.replace(b'0.3', b'0.4', 1)
    assert len(replacement) == len(original_bytes)
    original = resources_api._read_sealed_json_at
    changed = False

    def rewrite_after_last_read(parent_fd, name):
        nonlocal changed
        result = original(parent_fd, name)
        if name == 'cleanup.json' and not changed:
            changed = True
            artifact.chmod(0o600)
            artifact.write_bytes(replacement)
            artifact.chmod(0o444)
            os.utime(
                artifact,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )
        return result

    monkeypatch.setattr(resources_api, '_read_sealed_json_at', rewrite_after_last_read)
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-late-rewrite'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
        live_headroom_verifier=accepted_task14_verifier(
            acceptance_path, provenance_probe
        ),
    )
    try:
        with pytest.raises(
            ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'
        ):
            resource_allocator.allocate(worker_count=3)
    finally:
        resource_allocator.close()
    assert changed is True


@pytest.mark.parametrize(
    ('change', 'value'),
    [
        ('status', 'UNKNOWN'),
        ('run_mode', 'dry_run'),
        ('lifecycle', 'SHARED_STACK'),
        ('cleanup_complete', False),
        ('unexpected_self_attestation', True),
    ],
)
def test_three_worker_live_evidence_rejects_unaccepted_or_extra_claims(
    tmp_path, config, change, value
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config, **{change: value}
    )

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, f'three-unaccepted-{change}'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_three_worker_live_evidence_rejects_artifact_path_redirection(
    tmp_path, config
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    document = json.loads(evidence.read_text())
    document['artifacts']['resource_metrics']['path'] = '../outside.json'
    evidence.chmod(0o600)
    evidence.write_text(json.dumps(document), encoding='utf-8')
    evidence.chmod(0o444)

    with pytest.raises(ResourceAllocationError, match='THREE_WORKER_LIVE_EVIDENCE_INVALID'):
        WorkerResourceAllocator(
            config,
            resource_root(tmp_path, 'three-path-redirect'),
            probe=FakeProbe(),
            claim_root=claim_root(),
            live_headroom_evidence=evidence,
            live_headroom_verifier=accepted_task14_verifier(
                acceptance_path, provenance_probe
            ),
        ).allocate(worker_count=3)


def test_two_workers_do_not_consult_live_headroom_verifier(tmp_path, config):
    class ExplodingVerifier:
        def verify(self, _path, *, config):
            raise AssertionError(f'unexpected verifier call for {config}')

    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'two-no-live-verifier'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_verifier=ExplodingVerifier(),
    )
    assert resource_allocator.allocate(worker_count=2).live_headroom_evidence is None
    resource_allocator.close()


def test_internal_live_headroom_verifier_port_preserves_real_verification(
    tmp_path, config
):
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    delegate = accepted_task14_verifier(acceptance_path, provenance_probe)
    calls = []

    class RecordingVerifier:
        def verify(self, path, *, config):
            calls.append((path, config))
            return delegate.verify(path, config=config)

    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-recording-verifier'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
        live_headroom_verifier=RecordingVerifier(),
    )
    manifest = resource_allocator.allocate(worker_count=3)

    assert calls == [(evidence, config)]
    assert manifest.live_headroom_evidence['accepted_batch_id'] == (
        'accepted-two-worker-live-001'
    )
    resource_allocator.close()


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
        WorkerResourceAllocator(
            config, link / 'batch', probe=FakeProbe(), claim_root=claim_root()
        ).allocate()


def test_evidence_root_rejects_unsafe_parent_mode(tmp_path, config):
    unsafe = Path(os.environ['TMPDIR']).parent / 'unsafe'
    unsafe.mkdir(mode=0o777)
    unsafe.chmod(0o777)

    with pytest.raises(ResourceAllocationError, match='UNSAFE_DIRECTORY_MODE'):
        WorkerResourceAllocator(
            config, unsafe / 'batch', probe=FakeProbe(), claim_root=claim_root()
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
    evidence, acceptance_path, provenance_probe = accepted_live_evidence(
        tmp_path, config
    )
    resource_allocator = WorkerResourceAllocator(
        config,
        resource_root(tmp_path, 'three-layout'),
        probe=FakeProbe(),
        claim_root=claim_root(),
        live_headroom_evidence=evidence,
        live_headroom_verifier=accepted_task14_verifier(
            acceptance_path, provenance_probe
        ),
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
        WorkerResourceAllocator(
            config, root, probe=FakeProbe(), claim_root=claim_root()
        ).allocate()


def test_existing_socket_reservation_fails_before_directory_creation(tmp_path, config):
    root = resource_root(tmp_path)
    resource_allocator = WorkerResourceAllocator(
        config, root, probe=FakeProbe(), claim_root=claim_root()
    )
    socket_path = resource_allocator._paths(2)['socket_path']
    probe = FakeProbe(sockets=(socket_path,))

    with pytest.raises(ResourceAllocationError, match='SOCKET_CONFLICT'):
        WorkerResourceAllocator(
            config, root, probe=probe, claim_root=claim_root()
        ).allocate()
    assert not root.exists()


def test_socket_path_must_fit_linux_unix_domain_limit(tmp_path, config, monkeypatch):
    root = resource_root(tmp_path)
    resource_allocator = WorkerResourceAllocator(
        config, root, probe=FakeProbe(), claim_root=claim_root()
    )
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


def test_default_three_worker_cli_rejects_self_signed_live_headroom_evidence(
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
        ],
        claim_root=claim_root(),
    )

    assert exit_code == 2
    assert not (root / 'resource_manifest.json').exists()


def test_cli_requires_dry_run_and_does_not_create_output(tmp_path):
    root = resource_root(tmp_path, 'not-dry')

    with pytest.raises(SystemExit):
        main(
            [
                '--config',
                str(CONFIG_PATH),
                '--evidence-root',
                str(root),
            ],
            claim_root=claim_root(),
        )
    assert not root.exists()
