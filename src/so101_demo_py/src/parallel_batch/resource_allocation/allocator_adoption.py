"""Adopt an existing allocation and replace one."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import re
import stat

from so101_demo.parallel_batch.contracts.macos_two_worker import (
    ParallelRuntimeConfigMacosMpsTwoWorker,
)
from so101_demo.parallel_batch.resource_allocation.filesystem import (
    _open_trusted_parent,
    _verify_trusted_directory,
)
from so101_demo.parallel_batch.resource_allocation.manifest import ResourceManifest, _session_id
from so101_demo.parallel_batch.resource_allocation.models import (
    _BASE_ENVIRONMENT_ALLOWLIST,
    _NOT_APPLICABLE,
    ResourceAllocationError,
    WorkerResources,
)


class AllocatorAdoption:
    def adopt_existing(self, manifest: ResourceManifest) -> ResourceManifest:
        """Reclaim an exact crashed batch root without recreating its allocation."""
        if self._closed or self._manifest is not None:
            raise ResourceAllocationError('ALLOCATOR_NOT_ACTIVE')
        expected_schema = 4 if isinstance(self.config, ParallelRuntimeConfigMacosMpsTwoWorker) else 3
        if (
            not isinstance(manifest, ResourceManifest)
            or manifest.schema_version != expected_schema
            or manifest.evidence_root != self.evidence_root
            or manifest.backend != self.config.backend
            or manifest.worker_count != manifest.requested_worker_count
            or manifest.worker_count != len(manifest.workers)
            or manifest.worker_count <= 0
            or manifest.worker_count > self.allocation_policy.max_worker_count
        ):
            raise ResourceAllocationError('RECOVERY_MANIFEST')
        expected_paths = tuple(
            self._paths(index) for index in range(1, manifest.worker_count + 1)
        )
        for worker, paths in zip(manifest.workers, expected_paths, strict=True):
            expected = {
                'worker_id': paths['worker_id'],
                'slot_index': paths['slot_index'],
                'worker_root': paths['worker_root'],
                'ros_home': paths['ros_home'],
                'ros_log_dir': paths['ros_log_dir'],
                'temp_dir': paths['temp_dir'],
                'render_context_namespace': paths['render_context_namespace'],
                'socket_namespace': paths['socket_namespace'],
                'socket_path': paths['socket_path'],
                'ros_domain_id': self.allocation_policy.ros_domain_ids[
                    worker.slot_index - 1
                ],
                'simulation_port': _NOT_APPLICABLE,
                'bridge_port': _NOT_APPLICABLE,
                'gz_partition': _NOT_APPLICABLE,
                'controller_namespace': f'/parallel/{worker.worker_id}',
                'render_backend': 'headless_egl',
                'render_context_id': (
                    f'{self.batch_id}-egl-{worker.slot_index:02d}'
                ),
                'virtual_display': _NOT_APPLICABLE,
            }
            if (
                any(getattr(worker, name) != value for name, value in expected.items())
                or re.fullmatch(
                    rf'{re.escape(worker.worker_id)}-g{worker.generation:04d}-[0-9a-f]{{32}}',
                    worker.session_id,
                ) is None
            ):
                raise ResourceAllocationError('RECOVERY_RESOURCE_IDENTITY')
            environment = worker.environment
            expected_environment = {
                key: value
                for key in _BASE_ENVIRONMENT_ALLOWLIST
                if isinstance((value := self.base_environment.get(key)), str) and value
            }
            expected_environment.update({
                    'ROS_DOMAIN_ID': str(worker.ros_domain_id),
                    'ROS_HOME': str(worker.ros_home),
                    'ROS_LOG_DIR': str(worker.ros_log_dir),
                    'TMPDIR': str(worker.temp_dir),
                    'TMP': str(worker.temp_dir),
                    'TEMP': str(worker.temp_dir),
                    'SO101_WORKER_ID': worker.worker_id,
                    'SO101_WORKER_GENERATION': str(worker.generation),
                    'SO101_SESSION_ID': worker.session_id,
                    'SO101_CONTROLLER_NAMESPACE': worker.controller_namespace,
                    'SO101_SOCKET_NAMESPACE': str(worker.socket_namespace),
                    'GZ_PARTITION': _NOT_APPLICABLE,
                    'MUJOCO_GL': 'egl',
                    'SO101_RENDER_CONTEXT_ID': worker.render_context_id,
                    'SO101_RENDER_CONTEXT_NAMESPACE': str(
                        worker.render_context_namespace
                    ),
                })
            if dict(environment) != expected_environment:
                raise ResourceAllocationError('RECOVERY_RESOURCE_ENVIRONMENT')
        # Restore re-runs one fresh bounded check; the recorded guard document is kept
        # as evidence, and ownership/domain checks below are unchanged.
        admission, guard_document = self._start_guard_check(manifest.worker_count)
        if not admission.admitted:
            raise ResourceAllocationError(admission.reason, admission=admission)
        manifest = replace(manifest, admission=admission, start_guard=guard_document)
        parent_fd = _open_trusted_parent(self.evidence_root)
        root_fd = None
        try:
            root_fd = os.open(
                self.evidence_root.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            root_info = _verify_trusted_directory(
                root_fd, str(self.evidence_root), private=True
            )
            for paths in expected_paths:
                for name in (
                    'worker_root', 'ros_home', 'ros_log_dir', 'temp_dir',
                    'render_context_namespace', 'socket_namespace',
                ):
                    path = Path(paths[name])
                    info = path.lstat()
                    if (
                        path.is_symlink()
                        or not stat.S_ISDIR(info.st_mode)
                        or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) != 0o700
                    ):
                        raise ResourceAllocationError('RECOVERY_RESOURCE_DIRECTORY')
            domains = tuple(worker.ros_domain_id for worker in manifest.workers)
            self._claim_domains(domains)
            self._probe_namespace_collisions(expected_paths, domains)
            scan_report = getattr(self.probe, 'process_scan_report', None)
            if callable(scan_report):
                self._process_scan = scan_report()
            self._root_fd = root_fd
            self._root_identity = (root_info.st_dev, root_info.st_ino)
            self._directory_fds.append(root_fd)
            root_fd = None
            self._workers = {worker.worker_id: worker for worker in manifest.workers}
            self._manifest = replace(
                manifest,
                admission=admission,
                domain_claims=self._domain_claims,
                process_scan=self._process_scan,
            )
            return self._manifest
        except OSError as error:
            self.close()
            raise ResourceAllocationError('RECOVERY_RESOURCE_DIRECTORY') from error
        except Exception:
            self.close()
            raise
        finally:
            if root_fd is not None:
                os.close(root_fd)
            os.close(parent_fd)

    def replace(self, worker_id: str, *, expected_generation: int) -> WorkerResources:
        """Reuse one stable slot while fencing it with the next generation."""
        if self._closed:
            raise ResourceAllocationError('ALLOCATOR_NOT_ACTIVE')
        if type(expected_generation) is not int or expected_generation <= 0:
            raise ResourceAllocationError('GENERATION')
        try:
            current = self._workers[worker_id]
        except (KeyError, TypeError) as error:
            raise ResourceAllocationError('UNKNOWN_WORKER') from error
        if current.generation != expected_generation:
            raise ResourceAllocationError('GENERATION_MISMATCH')
        generation = current.generation + 1
        session_id = _session_id(current.worker_id, generation)
        environment = dict(current.environment)
        environment['SO101_WORKER_GENERATION'] = str(generation)
        environment['SO101_SESSION_ID'] = session_id
        replacement = replace(
            current,
            generation=generation,
            session_id=session_id,
            environment=environment,
        )
        self._workers[worker_id] = replacement
        if self._manifest is not None:
            ordered = tuple(self._workers[worker.worker_id] for worker in self._manifest.workers)
            self._manifest = replace(self._manifest, workers=ordered)
        return replacement
