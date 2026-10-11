"""Paths, preflight, directories and the manifest write of the allocator."""

from __future__ import annotations

import os
from pathlib import Path
import stat

from so101_demo.parallel_batch.contracts.macos_two_worker import (
    IpcTransport,
    ParallelRuntimeConfigMacosMpsTwoWorker,
)
from so101_demo.parallel_batch.resource_allocation.filesystem import (
    _mkdir_private_at,
    _open_trusted_parent,
    _verify_trusted_directory,
)
from so101_demo.parallel_batch.resource_allocation.manifest import _session_id, _write_manifest_at
from so101_demo.parallel_batch.resource_allocation.models import (
    _BASE_ENVIRONMENT_ALLOWLIST,
    _NOT_APPLICABLE,
    ResourceAllocationError,
    WorkerResources,
)
from so101_demo.runtime.parallel_ipc import IpcError, require_transport_basename
from so101_demo.runtime.unix_address import (
    DARWIN_SUN_PATH_CAPACITY_BYTES,
    LINUX_SUN_PATH_CAPACITY_BYTES,
    UnixAddressError,
    require_encoded_length,
)


class AllocatorLayout:
    def write_manifest(self) -> Path:
        """Publish through the held root descriptor and verify the visible identity."""
        if self._manifest is None or self._root_fd is None or self._closed:
            raise ResourceAllocationError('ALLOCATOR_NOT_ACTIVE')
        path = self.evidence_root / 'resource_manifest.json'
        try:
            self._verify_root_identity()
            _write_manifest_at(self._root_fd, 'resource_manifest.json', self._manifest.to_dict())
            self._verify_root_identity()
        except Exception:
            self.close()
            raise
        return path

    def _paths(self, slot_index: int) -> dict[str, Path | str | int]:
        worker_id = f'worker-{slot_index:02d}'
        worker_root = self.evidence_root / 'workers' / worker_id
        socket_namespace = self.ipc_root / str(slot_index)
        return {
            'worker_id': worker_id,
            'slot_index': slot_index,
            'worker_root': worker_root,
            'ros_home': worker_root / 'ros-home',
            'ros_log_dir': worker_root / 'ros-home' / 'log',
            'temp_dir': worker_root / 'tmp',
            'render_context_namespace': worker_root / 'render',
            'socket_namespace': socket_namespace,
            'socket_path': socket_namespace / 's',
        }

    def _preflight(
        self, paths: tuple[dict[str, Path | str | int], ...], parent_fd: int,
        domains: tuple[int, ...],
    ) -> None:
        try:
            existing = os.stat(
                self.evidence_root.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            existing = None
        except OSError as error:
            raise ResourceAllocationError('EVIDENCE_ROOT_CHECK_FAILED') from error
        if existing is not None:
            if stat.S_ISLNK(existing.st_mode):
                raise ResourceAllocationError(f'SYMLINK_PATH: {self.evidence_root}')
            raise ResourceAllocationError(f'DIRECTORY_CONFLICT: {self.evidence_root}')
        if self._external_ipc_root and (
            self.ipc_root.exists() or self.ipc_root.is_symlink()
        ):
            raise ResourceAllocationError(f'DIRECTORY_CONFLICT: {self.ipc_root}')
        for item in paths:
            socket_path = item['socket_path']
            assert isinstance(socket_path, Path)
            # The durable canonical path may exceed 107 bytes; only the exact kernel
            # sockaddr built from the owned parent descriptor must fit sun_path.
            try:
                if isinstance(self.config, ParallelRuntimeConfigMacosMpsTwoWorker):
                    # Schema v4 replaced the dirfd transport with the Darwin private-path strategy:
                    # the same namespace stays basename-shaped, but the bound is the encoded
                    # `sun_path` capacity rather than the presence of `/proc/self/fd`.
                    require_encoded_length(socket_path, capacity_bytes=(
                        DARWIN_SUN_PATH_CAPACITY_BYTES
                        if self.config.ipc_transport is IpcTransport.DARWIN_PRIVATE_PATH_UNIX
                        else LINUX_SUN_PATH_CAPACITY_BYTES
                    ))
                else:
                    require_transport_basename(socket_path)
            except (IpcError, UnixAddressError) as error:
                raise ResourceAllocationError(str(error)) from error
        self._probe_namespace_collisions(
            paths, domains
        )

    def _create_directories(
        self, paths: tuple[dict[str, Path | str | int], ...], parent_fd: int
    ) -> None:
        try:
            root_fd = _mkdir_private_at(parent_fd, self.evidence_root.name)
            self._directory_fds.append(root_fd)
            self._root_fd = root_fd
            root_stat = os.fstat(root_fd)
            self._root_identity = (root_stat.st_dev, root_stat.st_ino)
            workers_fd = _mkdir_private_at(root_fd, 'workers')
            if self._external_ipc_root:
                ipc_parent_fd = _open_trusted_parent(self.ipc_root)
                try:
                    ipc_fd = _mkdir_private_at(ipc_parent_fd, self.ipc_root.name)
                    os.fsync(ipc_parent_fd)
                finally:
                    os.close(ipc_parent_fd)
            else:
                ipc_fd = _mkdir_private_at(root_fd, 'ipc')
            self._directory_fds.extend((workers_fd, ipc_fd))
            for item in paths:
                worker_fd = _mkdir_private_at(workers_fd, str(item['worker_id']))
                ros_fd = _mkdir_private_at(worker_fd, 'ros-home')
                log_fd = _mkdir_private_at(ros_fd, 'log')
                temp_fd = _mkdir_private_at(worker_fd, 'tmp')
                render_fd = _mkdir_private_at(worker_fd, 'render')
                socket_fd = _mkdir_private_at(ipc_fd, str(item['slot_index']))
                self._directory_fds.extend(
                    (worker_fd, ros_fd, log_fd, temp_fd, render_fd, socket_fd)
                )
            os.fsync(workers_fd)
            os.fsync(ipc_fd)
            os.fsync(root_fd)
            os.fsync(parent_fd)
            self._verify_root_identity()
        except ResourceAllocationError:
            raise
        except OSError as error:
            raise ResourceAllocationError('DIRECTORY_CREATION_FAILED') from error

    def _verify_root_identity(self) -> None:
        if self._root_fd is None or self._root_identity is None:
            raise ResourceAllocationError('ROOT_FD_MISSING')
        held = _verify_trusted_directory(
            self._root_fd, str(self.evidence_root), private=True
        )
        parent_fd = _open_trusted_parent(self.evidence_root)
        try:
            visible = os.stat(
                self.evidence_root.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except OSError as error:
            raise ResourceAllocationError('PATH_IDENTITY_CHANGED') from error
        finally:
            os.close(parent_fd)
        identity = (held.st_dev, held.st_ino)
        if (
            identity != self._root_identity
            or (visible.st_dev, visible.st_ino) != self._root_identity
            or not stat.S_ISDIR(visible.st_mode)
        ):
            raise ResourceAllocationError('PATH_IDENTITY_CHANGED')

    def _worker(
        self,
        slot_index: int,
        paths: dict[str, Path | str | int],
        *,
        generation: int,
    ) -> WorkerResources:
        worker_id = str(paths['worker_id'])
        session_id = _session_id(worker_id, generation)
        controller_namespace = f'/parallel/{worker_id}'
        render_context_id = f'{self.batch_id}-egl-{slot_index:02d}'
        environment = {
            key: value
            for key in _BASE_ENVIRONMENT_ALLOWLIST
            if isinstance((value := self.base_environment.get(key)), str) and value
        }
        environment.update(
            {
                'ROS_DOMAIN_ID': str(
                    self.allocation_policy.ros_domain_ids[slot_index - 1]
                ),
                'ROS_HOME': str(paths['ros_home']),
                'ROS_LOG_DIR': str(paths['ros_log_dir']),
                'TMPDIR': str(paths['temp_dir']),
                'TMP': str(paths['temp_dir']),
                'TEMP': str(paths['temp_dir']),
                'GZ_PARTITION': _NOT_APPLICABLE,
                'SO101_WORKER_ID': worker_id,
                'SO101_WORKER_GENERATION': str(generation),
                'SO101_SESSION_ID': session_id,
                'SO101_CONTROLLER_NAMESPACE': controller_namespace,
                'SO101_SOCKET_NAMESPACE': str(paths['socket_namespace']),
                'MUJOCO_GL': 'egl',
                'SO101_RENDER_CONTEXT_ID': render_context_id,
                'SO101_RENDER_CONTEXT_NAMESPACE': str(paths['render_context_namespace']),
            }
        )
        return WorkerResources(
            worker_id=worker_id,
            slot_index=slot_index,
            generation=generation,
            ros_domain_id=self.allocation_policy.ros_domain_ids[slot_index - 1],
            simulation_port=_NOT_APPLICABLE,
            bridge_port=_NOT_APPLICABLE,
            gz_partition=_NOT_APPLICABLE,
            session_id=session_id,
            controller_namespace=controller_namespace,
            render_backend='headless_egl',
            render_context_id=render_context_id,
            render_context_namespace=Path(paths['render_context_namespace']),
            virtual_display=_NOT_APPLICABLE,
            ros_home=Path(paths['ros_home']),
            ros_log_dir=Path(paths['ros_log_dir']),
            temp_dir=Path(paths['temp_dir']),
            socket_namespace=Path(paths['socket_namespace']),
            socket_path=Path(paths['socket_path']),
            worker_root=Path(paths['worker_root']),
            environment=environment,
        )
