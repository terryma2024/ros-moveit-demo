"""Persistent ROS domain claims of the allocator."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from so101_demo.parallel_batch.contracts.macos_two_worker import (
    ParallelRuntimeConfigMacosMpsTwoWorker,
)
from so101_demo.parallel_batch.resource_allocation.filesystem import (
    _json_bytes,
    _open_or_create_private_directory,
    _open_trusted_parent,
    _replace_fd_contents,
    _verify_private_regular,
)
from so101_demo.parallel_batch.resource_allocation.manifest import _process_starttime_ticks
from so101_demo.parallel_batch.resource_allocation.models import (
    _DOMAIN_CLAIM_PROTOCOL,
    _DOMAIN_CLAIM_SCOPE,
    ResourceAllocationError,
)
from so101_demo.parallel_batch.resource_allocation.probe import (
    _ros_domain_in_use_after_cleanup_quiescence,
)


class AllocatorClaims:
    def _claim_domains(self, domains: tuple[int, ...]) -> None:
        claim_parent_fd = _open_trusted_parent(self.claim_root)
        claim_root_fd = None
        acquired: dict[int, int] = {}
        records = []
        try:
            claim_root_fd = _open_or_create_private_directory(
                claim_parent_fd, self.claim_root.name
            )
            for domain_id in sorted(domains):
                name = f'domain-{domain_id}.lock'
                descriptor = os.open(
                    name,
                    os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=claim_root_fd,
                )
                try:
                    _verify_private_regular(descriptor, name)
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError as error:
                        raise ResourceAllocationError(
                            f'ROS_DOMAIN_CLAIMED: {domain_id}'
                        ) from error
                    if self.allocation_policy.persistent_cleanup_claims:
                        try:
                            os.lseek(descriptor, 0, os.SEEK_SET)
                            payload = os.read(descriptor, 8193)
                            if len(payload) > 8192:
                                raise ValueError('oversized claim')
                            if payload:
                                prior = json.loads(payload.decode('utf-8'))
                                if type(prior) is not dict:
                                    raise ValueError('claim mapping')
                                if prior.get('claim_state') == 'ACTIVE':
                                    raise ResourceAllocationError(
                                        f'ROS_DOMAIN_UNCLEAN: {domain_id}'
                                    )
                                if prior.get('claim_state') != 'RELEASED':
                                    raise ValueError('claim state')
                        except ResourceAllocationError:
                            raise
                        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                            raise ResourceAllocationError(
                                f'ROS_DOMAIN_CLAIM_INVALID: {domain_id}'
                            ) from error
                    acquired[domain_id] = descriptor
                except Exception:
                    os.close(descriptor)
                    raise
            process_starttime = _process_starttime_ticks()
            for domain_id, descriptor in acquired.items():
                name = f'domain-{domain_id}.lock'
                record = {
                    'protocol': _DOMAIN_CLAIM_PROTOCOL,
                    'scope': _DOMAIN_CLAIM_SCOPE,
                    'domain_id': domain_id,
                    'uid': os.getuid(),
                    'pid': os.getpid(),
                    'process_starttime_ticks': process_starttime,
                    'batch_id': self.batch_id,
                    'evidence_root': str(self.evidence_root),
                    'claim_path': str(self.claim_root / name),
                }
                if self.allocation_policy.persistent_cleanup_claims:
                    record.update(claim_state='ACTIVE', generation=1)
                _replace_fd_contents(descriptor, _json_bytes(record) + b'\n')
                records.append(record)
            os.fsync(claim_root_fd)
        except Exception:
            for descriptor in acquired.values():
                os.close(descriptor)
            raise
        finally:
            if claim_root_fd is not None:
                os.close(claim_root_fd)
            os.close(claim_parent_fd)
        self._claim_fds = acquired
        self._domain_claims = tuple(records)

    def _release_persistent_claims_no_processes_started(self) -> None:
        """Roll back claims only while allocation has not returned to a launcher."""

        if (
            not self.allocation_policy.persistent_cleanup_claims
            or not self._domain_claims
        ):
            return
        released = []
        for record in self._domain_claims:
            value = dict(record)
            descriptor = self._claim_fds.get(value['domain_id'])
            if descriptor is None or value.get('claim_state') != 'ACTIVE':
                raise ResourceAllocationError('ROS_DOMAIN_CLAIM_ROLLBACK')
            value.update(claim_state='RELEASED', no_processes_started=True)
            _replace_fd_contents(descriptor, _json_bytes(value) + b'\n')
            released.append(value)
        self._domain_claims = tuple(released)

    def release_persistent_claims(self, *, cleanup_verified: bool) -> bool:
        """Publish RELEASED only while holding claims after exact cleanup readback."""

        if type(cleanup_verified) is not bool or not cleanup_verified:
            raise ResourceAllocationError('CLEANUP_NOT_VERIFIED')
        if self._closed or self._manifest is None:
            raise ResourceAllocationError('ALLOCATOR_NOT_ACTIVE')
        if not self.allocation_policy.persistent_cleanup_claims:
            return True
        for worker in self._manifest.workers:
            if self.probe.socket_in_use(worker.socket_path):
                raise ResourceAllocationError('CLEANUP_SOCKET_ACTIVE')
            if _ros_domain_in_use_after_cleanup_quiescence(
                self.probe, worker.ros_domain_id
            ):
                raise ResourceAllocationError('CLEANUP_ROS_DOMAIN_ACTIVE')
        released = []
        for record in self._domain_claims:
            value = dict(record)
            if value.get('claim_state') == 'RELEASED':
                released.append(value)
                continue
            descriptor = self._claim_fds.get(value.get('domain_id'))
            if (
                descriptor is None
                or value.get('claim_state') != 'ACTIVE'
                or value.get('batch_id') != self.batch_id
                or value.get('evidence_root') != str(self.evidence_root)
            ):
                raise ResourceAllocationError('ROS_DOMAIN_CLAIM_RELEASE')
            value.update(claim_state='RELEASED', cleanup_verified=True)
            _replace_fd_contents(descriptor, _json_bytes(value) + b'\n')
            released.append(value)
        self._domain_claims = tuple(released)
        return True

    def _probe_namespace_collisions(
        self,
        paths: tuple[dict[str, Path | str | int], ...],
        domains: tuple[int, ...],
    ) -> None:
        """Recheck live ROS and IPC ownership after the advisory claim is held."""
        try:
            domain_conflicts = [
                domain_id
                for domain_id in domains
                if (
                    self._domain_claimed_by_another_campaign(domain_id)
                    if isinstance(self.config, ParallelRuntimeConfigMacosMpsTwoWorker)
                    else self.probe.ros_domain_in_use(domain_id)
                )
            ]
            socket_conflicts = [
                item['socket_path']
                for item in paths
                if self.probe.socket_in_use(item['socket_path'])
            ]
        except ResourceAllocationError:
            raise
        except Exception as error:
            raise ResourceAllocationError('PROBE_FAILED: namespace collision') from error
        if domain_conflicts:
            joined = ','.join(str(value) for value in domain_conflicts)
            raise ResourceAllocationError(f'ROS_DOMAIN_IN_USE: {joined}')
        if socket_conflicts:
            raise ResourceAllocationError(f'SOCKET_CONFLICT: {socket_conflicts[0]}')

    def _domain_claimed_by_another_campaign(self, domain_id: int) -> bool:
        """Portable domain-claim check for schema v4: read the durable claim, never `/proc`.

        The allocator holds the flock on its own claims by the time this runs, so the recorded
        owner decides the answer: our own pid is not a conflict, a live other pid is, and a dead
        pid is a stale file from a finished campaign. Anything unreadable or malformed fails closed,
        because "cannot verify" must never be reported as "free".
        """

        path = self.claim_root / f'domain-{domain_id}.lock'
        if not os.path.lexists(path):
            return False
        try:
            payload = Path(path).read_bytes()
        except OSError as error:
            raise ResourceAllocationError(f'PROBE_FAILED: claim unreadable: {error}') from error
        try:
            owner = int(json.loads(payload.decode('utf-8'))['pid'])
        except (UnicodeError, ValueError, KeyError, TypeError) as error:
            raise ResourceAllocationError(f'PROBE_FAILED: claim malformed: {error}') from error
        if owner == os.getpid():
            return False
        from so101_demo.parallel_batch.start_guard_probe import read_process_identity

        return read_process_identity(owner) is not None
