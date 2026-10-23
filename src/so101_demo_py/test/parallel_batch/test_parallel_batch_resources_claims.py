"""Trusted roots, domain claims and the production command resources."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time

from parallel_batch_resources_support import (  # noqa: F401  (pytest fixtures)
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

from so101_demo.parallel_batch.resource_allocation import filesystem as resources_api_filesystem
from so101_demo.parallel_batch.resource_allocation import manifest as resources_api_manifest
from so101_demo.parallel_batch.resource_allocation import probe as resources_api_probe
from so101_demo.parallel_batch.resource_allocation.models import (
    AllocationPolicy,
    ResourceAllocationError,
)
from so101_demo.parallel_batch.resources import WorkerResourceAllocator


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS /tmp is a system alias')
def test_trusted_parent_accepts_the_root_owned_macos_tmp_alias():
    """The handoff's /tmp evidence root reaches the same trusted /private/tmp inode."""

    with tempfile.TemporaryDirectory(prefix='so101-tmp-alias-', dir='/private/tmp') as root:
        real_path = Path(root)
        relative = real_path.relative_to('/private/tmp')
        alias_target = Path('/tmp') / relative / 'batch'

        descriptor = resources_api_filesystem._open_trusted_parent(alias_target)
        try:
            assert os.fstat(descriptor).st_ino == real_path.stat().st_ino
        finally:
            os.close(descriptor)


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS has no procfs stat')
def test_domain_claim_owner_has_a_portable_process_birth_identity():
    """Persistent ROS-domain claims remain PID-reuse safe without procfs."""

    assert resources_api_manifest._process_starttime_ticks() > 0


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

    from so101_demo.parallel_batch.resource_allocation.models import ResourceAllocationError
    from so101_demo.parallel_batch.resource_allocation.probe import SystemResourceProbe

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

    reason = resources_api_probe._frozen_non_candidate_reason('S', 'sshd', argv)

    assert reason == 'frozen_sshd_transport_non_candidate'


@pytest.mark.parametrize(
    "argv",
    [("sshd: robot.user@tty7",), ("sshd: robot.user@notty extra",)],
)
def test_unknown_sshd_transport_shapes_remain_unclassified(argv):
    assert resources_api_probe._frozen_non_candidate_reason('S', 'sshd', argv) is None


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
        manifest = owner.allocate(worker_count=2)
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
    policy = AllocationPolicy(1, (215,), True)
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
    policy = AllocationPolicy(1, (215,), True)
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
    policy = AllocationPolicy(1, (215,), True)
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


def test_production_cli_composes_one_worker_with_an_admitted_exact_n_gate(tmp_path):
    """Version two composes N=1 through the exact-N gate, not the retired evidence chain (N>1 is refused)."""

    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    root = resource_root(tmp_path, 'cli-one-valid')
    prepared = prepare_batch(
        production_batch_argv(root, worker_count='1'),
        provenance_verifier=lambda _inputs: {'source_commit': 'a' * 40},
    )
    composition = ProductionBatchComposition(
        prepared, resource_probe=FakeProbe(), claim_root=claim_root())
    try:
        assert composition.resource_manifest.worker_count == 1
        assert composition.resource_manifest.requested_worker_count == 1
    finally:
        composition._release_partial()


def test_production_cli_needs_no_budget_authority_for_one_worker(tmp_path, monkeypatch):
    """The retired default-gate hook no longer decides anything: the guard does."""

    import so101_demo.cli.mujoco_batch.request as parallel_cli
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    monkeypatch.setattr(parallel_cli, '_DEFAULT_START_GUARD', None)
    prepared = prepare_batch(
        production_batch_argv(resource_root(tmp_path, 'cli-one-guarded')),
        provenance_verifier=lambda _inputs: {'source_commit': 'a' * 40},
    )
    assert prepared.start_guard is not None
    assert prepared.start_guard_evidence['status'] in ('PASS', 'WARN')


def test_production_cli_refuses_retired_headroom_authority(tmp_path, config):
    """The retired headroom evidence chain is refused before it is even read (N>1 never gets this far)."""

    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    for worker_count in ('1',):
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
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

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
