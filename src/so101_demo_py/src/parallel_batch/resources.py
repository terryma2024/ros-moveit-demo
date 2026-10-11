"""Fail-closed host admission and isolated Worker resource allocation."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
from typing import Mapping

from so101_demo.parallel_batch.contracts.linux_cuda import ParallelRuntimeConfigLinuxCuda
from so101_demo.parallel_batch.contracts.macos_two_worker import (
    ParallelRuntimeConfigMacosMpsTwoWorker,
)
from so101_demo.parallel_batch.resource_allocation.allocator import _parser
from so101_demo.parallel_batch.resource_allocation.allocator_adoption import AllocatorAdoption
from so101_demo.parallel_batch.resource_allocation.allocator_claims import AllocatorClaims
from so101_demo.parallel_batch.resource_allocation.allocator_layout import AllocatorLayout
from so101_demo.parallel_batch.resource_allocation.filesystem import _open_trusted_parent
from so101_demo.parallel_batch.resource_allocation.manifest import (
    ResourceManifest,
    StartGuardAdmission,
)
from so101_demo.parallel_batch.resource_allocation.models import (
    _BATCH_ID,
    _DEFAULT_WORKER_COUNT,
    _DOMAIN_CLAIM_SCOPE,
    AllocationPolicy,
    ResourceAllocationError,
    ResourceSnapshot,
    WorkerResources,
    runtime_ipc_base,
)
from so101_demo.parallel_batch.resource_allocation.probe import (
    SystemResourceProbe,
    _default_process_scan_report,
)


class WorkerResourceAllocator(AllocatorClaims, AllocatorLayout, AllocatorAdoption):
    """Allocate one private resource set for every requested stable slot."""

    def __init__(
        self,
        config: ParallelRuntimeConfigLinuxCuda,
        evidence_root: Path,
        *,
        probe=None,
        base_environment: Mapping[str, str] | None = None,
        claim_root: Path | None = None,
        batch_id: str | None = None,
        allocation_policy: AllocationPolicy | None = None,
        ipc_root: Path | None = None,
        start_guard=None,
    ) -> None:
        if not isinstance(config, (ParallelRuntimeConfigLinuxCuda, ParallelRuntimeConfigMacosMpsTwoWorker)):
            raise ResourceAllocationError('CONFIG')
        raw_root = str(evidence_root)
        root = Path(evidence_root)
        if (
            not root.is_absolute()
            or '\x00' in raw_root
            or any(part in {'.', '..'} for part in raw_root.split('/'))
        ):
            raise ResourceAllocationError('EVIDENCE_ROOT')
        self.config = config
        self.evidence_root = root
        self._external_ipc_root = ipc_root is not None
        self.ipc_root = root / 'ipc' if ipc_root is None else Path(ipc_root)
        if (
            not self.ipc_root.is_absolute()
            or self.ipc_root != self.ipc_root.absolute()
            or self.ipc_root == root
        ):
            raise ResourceAllocationError('IPC_ROOT')
        selected_batch_id = root.name if batch_id is None else batch_id
        if not isinstance(selected_batch_id, str) or _BATCH_ID.fullmatch(selected_batch_id) is None:
            raise ResourceAllocationError('BATCH_ID')
        self.batch_id = selected_batch_id
        self._start_guard = start_guard
        self.allocation_policy = (
            AllocationPolicy(
            # v4's exact two-worker platform claim, not the inherited v3 field: `max_worker_count` stays
            # frozen at its v3 value, and `AllocationPolicy` requires
            # `len(ros_domain_ids) >= max_worker_count`.
            config.worker_count if isinstance(config, ParallelRuntimeConfigMacosMpsTwoWorker)
            else config.max_worker_count,
            config.ros_domain_ids,
        )
            if allocation_policy is None
            else allocation_policy
        )
        if not isinstance(self.allocation_policy, AllocationPolicy):
            raise ResourceAllocationError('ALLOCATION_POLICY')
        self.probe = probe if probe is not None else SystemResourceProbe()
        source_environment = os.environ if base_environment is None else base_environment
        if not isinstance(source_environment, Mapping):
            raise ResourceAllocationError('BASE_ENVIRONMENT')
        self.base_environment = dict(source_environment)
        if ('SO101_IK_BACKEND' in self.base_environment
                and self.base_environment['SO101_IK_BACKEND'] not in ('native', 'quik')):
            raise ResourceAllocationError('IK_BACKEND_UNSUPPORTED')
        self.claim_root = (
            runtime_ipc_base() / 'so101-parallel-domain-claims'
            if claim_root is None
            else Path(claim_root)
        )
        if not self.claim_root.is_absolute():
            raise ResourceAllocationError('CLAIM_ROOT')

        self._manifest: ResourceManifest | None = None
        self._workers: dict[str, WorkerResources] = {}
        self._claim_fds: dict[int, int] = {}
        self._domain_claims: tuple[Mapping[str, object], ...] = ()
        self._process_scan: Mapping[str, object] = _default_process_scan_report()
        self._directory_fds: list[int] = []
        self._root_fd: int | None = None
        self._root_identity: tuple[int, int] | None = None
        self._closed = False

    @property
    def manifest(self) -> ResourceManifest | None:
        """Return the current immutable manifest, including replacements."""
        return self._manifest

    def allocate(self, worker_count: int | None = None) -> ResourceManifest:
        """Admit and allocate exactly the requested count; never downgrade it."""
        if self._closed:
            raise ResourceAllocationError('ALLOCATOR_NOT_ACTIVE')
        if self._manifest is not None:
            raise ResourceAllocationError('ALREADY_ALLOCATED')
        requested = _DEFAULT_WORKER_COUNT if worker_count is None else worker_count
        if (
            type(requested) is not int
            or requested <= 0
            or requested > self.allocation_policy.max_worker_count
        ):
            raise ResourceAllocationError('WORKER_COUNT')
        if len(self.allocation_policy.ros_domain_ids) < requested:
            raise ResourceAllocationError('ROS_DOMAIN_IDS')
        # There is no formula budget: the one bounded startup check decides.
        admission, guard_document = self._start_guard_check(requested)
        if not admission.admitted:
            raise ResourceAllocationError(admission.reason, admission=admission)
        live_headroom = guard_document

        paths = tuple(self._paths(slot + 1) for slot in range(requested))
        parent_fd = None
        try:
            parent_fd = _open_trusted_parent(self.evidence_root)
            domains = self.allocation_policy.ros_domain_ids[:requested]
            self._claim_domains(domains)
            self._preflight(paths, parent_fd, domains)
            scan_report = getattr(self.probe, 'process_scan_report', None)
            if callable(scan_report):
                self._process_scan = scan_report()
            self._create_directories(paths, parent_fd)
            workers = tuple(
                self._worker(slot + 1, paths[slot], generation=1)
                for slot in range(requested)
            )
        except Exception:
            self._release_persistent_claims_no_processes_started()
            self.close()
            raise
        finally:
            if parent_fd is not None:
                os.close(parent_fd)
        self._workers = {worker.worker_id: worker for worker in workers}
        self._manifest = ResourceManifest(
            schema_version=3,
            mode='dry_run',
            backend=self.config.backend,
            evidence_root=self.evidence_root,
            requested_worker_count=requested,
            worker_count=requested,
            admission=admission,
            domain_claim_scope=_DOMAIN_CLAIM_SCOPE,
            domain_claims=self._domain_claims,
            process_scan=self._process_scan,
            start_guard=live_headroom,
            workers=workers,
        )
        return self._manifest

    def close(self) -> None:
        """Release held directory descriptors and authoritative domain claims."""
        if self._closed:
            return
        self._closed = True
        for descriptor in reversed(self._directory_fds):
            try:
                os.close(descriptor)
            except OSError:
                pass
        self._directory_fds.clear()
        self._root_fd = None
        for descriptor in self._claim_fds.values():
            try:
                os.close(descriptor)
            except OSError:
                pass
        self._claim_fds.clear()

    def __enter__(self):
        return self

    def __exit__(self, _error_type, _error, _traceback) -> None:
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _start_guard_check(self, worker_count: int):
        """One bounded CPU/RAM/GPU check through the shared guard; never fabricate a pass."""

        if self._start_guard is None:
            raise ResourceAllocationError('START_GUARD_UNAVAILABLE')
        device = getattr(self.config, 'gpu_device', None)
        if device is None:
            # v4 replaced the v3 CUDA `gpu_device` with the closed platform combination, so the
            # guard's selector comes from the resolved accelerator (`mps:default` on Darwin).
            accelerator = getattr(self.config, 'accelerator', None)
            if accelerator is None:
                raise ResourceAllocationError('CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION')
            gpu_selector = f'MPS:{accelerator.resolved_selector}'
        else:
            gpu_selector = f'{device.selector_kind}:{device.selector}'
        from so101_demo.parallel_batch.start_guard import GuardScope
        from so101_demo.parallel_batch.start_guard_probe import read_process_identity

        identity = read_process_identity(os.getpid())
        scope = GuardScope(
            batch_id=self.batch_id,
            epoch=1,
            owner_pid=os.getpid(),
            owner_starttime_ticks=identity.start_time_ticks if identity is not None else 0,
            gpu_selector=gpu_selector,
            worker_count=worker_count,
        )
        result = self._start_guard.require_before_spawn(scope)
        admission = StartGuardAdmission(
            status=result.status,
            reason=(result.checks.get('probe').reason if 'probe' in result.checks
                    else 'START_GUARD_REFUSED'),
            checks={name: check.__dict__ if hasattr(check, '__dict__') else {
                'status': check.status, 'reason': check.reason, 'observed': check.observed,
                'cutoff': check.cutoff, 'unit': check.unit}
                for name, check in result.checks.items()},
            observed_monotonic_s=result.completed_monotonic_s,
            gpu_uuid=None if result.snapshot is None else result.snapshot.gpu_uuid,
            cleanup_state=result.cleanup_state,
        )
        document = {
            'status': result.status,
            'reason': admission.reason,
            'checks': {
                name: {'status': check.status, 'reason': check.reason,
                       'cutoff': check.cutoff, 'unit': check.unit}
                for name, check in sorted(result.checks.items())
            },
            'checked_monotonic_s': result.completed_monotonic_s,
            'cleanup_state': result.cleanup_state,
            'gpu_uuid': admission.gpu_uuid,
            'effective_cpu_cores': None if result.snapshot is None
            else result.snapshot.effective_cpu_cores,
            'ram_available_bytes': None if result.snapshot is None
            else result.snapshot.ram_available_bytes,
            'gpu_free_bytes': None if result.snapshot is None else result.snapshot.gpu_free_bytes,
        }
        return admission, document

    def _probe_snapshot(self) -> ResourceSnapshot:
        try:
            snapshot = self.probe.snapshot()
        except ResourceAllocationError:
            raise
        except Exception as error:
            raise ResourceAllocationError('PROBE_FAILED: resource snapshot') from error
        if not isinstance(snapshot, ResourceSnapshot) or (
            type(snapshot.logical_cpu_count) is not int
            or snapshot.logical_cpu_count <= 0
            or isinstance(snapshot.available_ram_gib, bool)
            or not isinstance(snapshot.available_ram_gib, (int, float))
            or not math.isfinite(float(snapshot.available_ram_gib))
            or snapshot.available_ram_gib < 0
            or isinstance(snapshot.gpu_free_gib, bool)
            or not isinstance(snapshot.gpu_free_gib, (int, float))
            or not math.isfinite(float(snapshot.gpu_free_gib))
            or snapshot.gpu_free_gib < 0
        ):
            raise ResourceAllocationError('INVALID_RESOURCE_SNAPSHOT')
        return ResourceSnapshot(
            snapshot.logical_cpu_count,
            float(snapshot.available_ram_gib),
            float(snapshot.gpu_free_gib),
        )


def _load_cli_config(path):
    """The active execution document: v3 unchanged, v4 added for macOS MPS two-worker; v1 stays read-only.

    The schema gate lives in one place (`two_worker_composition.load_execution_config`) so the CLI, this
    allocator and the offline tests cannot disagree about which documents may execute.
    """

    from so101_demo.parallel_batch.two_worker_composition import load_execution_config

    try:
        return load_execution_config(Path(path))
    except Exception as error:  # noqa: BLE001 - re-expressed in this module's error vocabulary
        from so101_demo.parallel_batch.contracts.common import ContractError

        if isinstance(error, ContractError):
            raise ResourceAllocationError(str(error)) from error
        raise


def _compose_default_start_guard(config):
    """Installed composition used when the caller does not supply a guard."""

    from so101_demo.parallel_batch.start_guard_probe import compose_default_start_guard

    return compose_default_start_guard(config.start_guard)


def main(
    argv=None, *, claim_root: Path | None = None, start_guard=None,
    environment: Mapping[str, str] | None = None,
) -> int:
    """Write a resource manifest without starting ROS, MuJoCo or Broker."""
    arguments = _parser().parse_args(argv)
    allocator = None
    try:
        config = _load_cli_config(arguments.config)
        if arguments.measurement_authorization is not None or (
            arguments.measurement_authorization_sha256 is not None
        ):
            raise ResourceAllocationError('MEASUREMENT_AUTHORIZATION_RETIRED')
        if arguments.live_headroom_evidence is not None:
            raise ResourceAllocationError('LIVE_HEADROOM_EVIDENCE_UNEXPECTED')
        allocator = WorkerResourceAllocator(
            config,
            arguments.evidence_root,
            claim_root=claim_root,
            start_guard=start_guard or _compose_default_start_guard(config),
        )
        manifest = allocator.allocate(arguments.worker_count)
        document = manifest.to_dict()
        allocator.write_manifest()
    except (ResourceAllocationError, ValueError, OSError) as error:
        failure = {'admitted': False, 'error': str(error)}
        if isinstance(error, ResourceAllocationError) and error.admission is not None:
            failure['admission'] = error.admission.to_dict()
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 2
    finally:
        if allocator is not None:
            allocator.close()
    print(json.dumps(document, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
