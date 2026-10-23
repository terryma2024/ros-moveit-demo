"""Process identity reads and the system resource probe."""

from __future__ import annotations

import math
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from so101_demo.parallel_batch.resource_allocation.models import (
    _CLEANUP_PROC_SCAN_QUIESCENCE_ATTEMPTS,
    _CLEANUP_PROC_SCAN_QUIESCENCE_INTERVAL_S,
    _CLEANUP_TRANSIENT_PROC_SCAN_BOUNDARIES,
    _DOMAIN_CLAIM_SCOPE,
    _MEM_AVAILABLE,
    ResourceAllocationError,
    ResourceSnapshot,
)


class SystemResourceProbe:
    """Read-only Linux probes used by ai-station dry admission."""

    def __init__(self, *, proc_root: Path = Path('/proc')) -> None:
        self._proc_root = Path(proc_root)
        self._skipped_processes: dict[tuple[int, int], dict[str, object]] = {}

    def snapshot(self) -> ResourceSnapshot:
        """Measure logical CPUs, available RAM and free NVIDIA GPU memory."""
        logical_cpu_count = os.cpu_count()
        if logical_cpu_count is None:
            raise ResourceAllocationError('PROBE_FAILED: logical CPU count unavailable')
        available_ram_gib = self._available_ram_gib()
        try:
            result = subprocess.run(
                [
                    'nvidia-smi',
                    '--query-gpu=memory.free',
                    '--format=csv,noheader,nounits',
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            free_mib = [float(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise ResourceAllocationError('PROBE_FAILED: NVIDIA GPU memory') from error
        if not free_mib:
            raise ResourceAllocationError('PROBE_FAILED: NVIDIA GPU memory unavailable')
        return ResourceSnapshot(
            logical_cpu_count=logical_cpu_count,
            available_ram_gib=available_ram_gib,
            gpu_free_gib=min(free_mib) / 1024.0,
        )

    def _available_ram_gib(self) -> float:
        try:
            lines = (self._proc_root / 'meminfo').read_text(encoding='ascii').splitlines()
        except (OSError, UnicodeError) as error:
            raise ResourceAllocationError('PROBE_FAILED: MemAvailable read') from error
        candidates = [line for line in lines if line.startswith('MemAvailable:')]
        if len(candidates) != 1:
            raise ResourceAllocationError('PROBE_FAILED: MemAvailable count')
        match = _MEM_AVAILABLE.fullmatch(candidates[0])
        if match is None:
            raise ResourceAllocationError('PROBE_FAILED: MemAvailable format')
        available_ram_gib = int(match.group(1)) / 1024**2
        if not math.isfinite(available_ram_gib) or available_ram_gib < 0:
            raise ResourceAllocationError('PROBE_FAILED: MemAvailable value')
        return available_ram_gib

    def ros_domain_in_use(self, domain_id: int) -> bool:
        """Detect same-UID claims; unverifiable live same-UID processes fail closed."""
        if not self._proc_root.is_dir():
            return self._portable_ros_domain_in_use(domain_id)
        expected = str(domain_id).encode('ascii')
        for process in self._proc_root.iterdir():
            if not process.name.isdigit() or int(process.name) == os.getpid():
                continue
            try:
                process_stat = process.stat(follow_symlinks=False)
            except (FileNotFoundError, ProcessLookupError):
                continue
            except OSError as error:
                raise ResourceAllocationError(
                    f'PROC_IDENTITY_UNVERIFIABLE: {process.name}'
                ) from error
            if process_stat.st_uid != os.getuid():
                continue
            if not stat.S_ISDIR(process_stat.st_mode):
                raise ResourceAllocationError(f'PROC_IDENTITY_UNVERIFIABLE: {process.name}')
            try:
                before, comm, argv = _read_process_identity_with_retry(process)
            except (FileNotFoundError, ProcessLookupError):
                if not os.path.lexists(process):
                    continue
                raise ResourceAllocationError(
                    f'PROC_METADATA_UNVERIFIABLE: {process.name}'
                )
            except (OSError, UnicodeError, ValueError) as error:
                raise ResourceAllocationError(
                    f'PROC_METADATA_UNVERIFIABLE: {process.name}'
                ) from error
            skip_reason = _frozen_non_candidate_reason(before[2], comm, argv)
            if skip_reason is not None:
                try:
                    after, _comm_after, _argv_after = (
                        _read_process_identity_with_retry(process)
                    )
                except (OSError, UnicodeError, ValueError) as error:
                    raise ResourceAllocationError(
                        f'PROC_IDENTITY_CHANGED: {process.name}'
                    ) from error
                if before[:2] != after[:2]:
                    raise ResourceAllocationError(
                        f'PROC_IDENTITY_CHANGED: {process.name}'
                    )
                key = (before[0], before[1])
                self._skipped_processes[key] = {
                    'pid': before[0],
                    'uid': process_stat.st_uid,
                    'process_starttime_ticks': before[1],
                    'comm': comm,
                    'cmdline_summary': ' '.join(argv),
                    'skip_reason': skip_reason,
                }
                continue
            candidate = _is_high_recall_ros_candidate(comm, argv)
            try:
                entries = _read_process_environ_with_retry(process)
            except (FileNotFoundError, ProcessLookupError) as error:
                if not os.path.lexists(process):
                    continue
                try:
                    after, comm_after, argv_after = _read_process_identity_with_retry(
                        process
                    )
                except (FileNotFoundError, ProcessLookupError):
                    if not os.path.lexists(process):
                        continue
                    raise ResourceAllocationError(
                        f'PROC_ENV_UNVERIFIABLE: {process.name}'
                    ) from error
                except (OSError, UnicodeError, ValueError) as identity_error:
                    raise ResourceAllocationError(
                        f'PROC_IDENTITY_CHANGED: {process.name}'
                    ) from identity_error
                if before[:2] != after[:2]:
                    raise ResourceAllocationError(
                        f'PROC_IDENTITY_CHANGED: {process.name}'
                    ) from error
                if after[2] == 'Z':
                    key = (after[0], after[1])
                    self._skipped_processes[key] = {
                        'pid': after[0],
                        'uid': process_stat.st_uid,
                        'process_starttime_ticks': after[1],
                        'comm': comm_after,
                        'cmdline_summary': ' '.join(argv_after),
                        'skip_reason': 'frozen_zombie_non_candidate',
                    }
                    continue
                raise ResourceAllocationError(
                    f'PROC_ENV_UNVERIFIABLE: {process.name}'
                ) from error
            except OSError as error:
                boundary = (
                    'PROC_ENV_UNVERIFIABLE'
                    if candidate
                    else 'PROC_CLASSIFICATION_UNVERIFIABLE'
                )
                raise ResourceAllocationError(
                    f'{boundary}: {process.name}'
                ) from error
            try:
                after, _comm_after, _argv_after = _read_process_identity_with_retry(
                    process
                )
            except (OSError, UnicodeError, ValueError) as error:
                raise ResourceAllocationError(
                    f'PROC_IDENTITY_CHANGED: {process.name}'
                ) from error
            if before[:2] != after[:2]:
                raise ResourceAllocationError(f'PROC_IDENTITY_CHANGED: {process.name}')
            if b'ROS_DOMAIN_ID=' + expected in entries:
                return True
        return False

    def _portable_ros_domain_in_use(self, domain_id: int) -> bool:
        """Scan same-UID environments through psutil on hosts without procfs."""

        try:
            import psutil
        except ImportError as error:
            raise ResourceAllocationError(
                'PROBE_FAILED: portable process scanner unavailable'
            ) from error
        expected = str(domain_id)
        for process in psutil.process_iter(attrs=('pid', 'uids')):
            if process.pid == os.getpid():
                continue
            try:
                uids = process.info['uids']
                # A setuid login process may retain the user as its real UID while
                # running with root authority; Linux procfs is root-owned in that case.
                # Match the effective owner so the portable scan keeps the same scope.
                if uids is None or uids.effective != os.getuid():
                    continue
                environment = process.environ()
            except psutil.NoSuchProcess:
                continue
            except (OSError, psutil.Error) as error:
                raise ResourceAllocationError(
                    f'PROC_ENV_UNVERIFIABLE: {process.pid}'
                ) from error
            if environment.get('ROS_DOMAIN_ID') == expected:
                return True
        return False

    def process_scan_report(self) -> dict[str, object]:
        """Describe the bounded process trust model and every frozen skip."""
        return {
            'scope': _DOMAIN_CLAIM_SCOPE,
            'cross_uid_policy': 'not_inspected',
            'candidate_policy': 'same_uid_high_recall_requires_environ',
            'frozen_non_candidate_policy': 'recorded_without_environ',
            'unclassified_unreadable_policy': 'fail_closed',
            'skipped_processes': [
                dict(value)
                for _key, value in sorted(self._skipped_processes.items())
            ],
        }

    def socket_in_use(self, path: Path) -> bool:
        """Treat every existing filesystem object as a socket reservation."""
        return os.path.lexists(path)


def _ros_domain_in_use_after_cleanup_quiescence(
    probe: SystemResourceProbe, domain_id: int
) -> bool:
    """Rescan bounded transient process races only during verified cleanup."""

    for attempt in range(_CLEANUP_PROC_SCAN_QUIESCENCE_ATTEMPTS):
        try:
            return probe.ros_domain_in_use(domain_id)
        except ResourceAllocationError as error:
            transient = str(error).startswith(
                _CLEANUP_TRANSIENT_PROC_SCAN_BOUNDARIES
            )
            if (
                not transient
                or attempt + 1 >= _CLEANUP_PROC_SCAN_QUIESCENCE_ATTEMPTS
            ):
                raise
            time.sleep(_CLEANUP_PROC_SCAN_QUIESCENCE_INTERVAL_S)
    raise AssertionError('unreachable process scan retry loop')


def _default_process_scan_report() -> dict[str, object]:
    return {
        'scope': _DOMAIN_CLAIM_SCOPE,
        'cross_uid_policy': 'not_inspected',
        'candidate_policy': 'same_uid_high_recall_requires_environ',
        'frozen_non_candidate_policy': 'recorded_without_environ',
        'unclassified_unreadable_policy': 'fail_closed',
        'skipped_processes': [],
    }


def _read_process_identity(
    process: Path,
) -> tuple[tuple[int, int, str], str, tuple[str, ...]]:
    pid = int(process.name)
    stat_line = (process / 'stat').read_text(encoding='ascii').strip()
    closing = stat_line.rfind(')')
    if closing <= 0 or not stat_line.startswith(f'{pid} ('):
        raise ValueError('invalid proc stat identity')
    fields = stat_line[closing + 2 :].split()
    if len(fields) <= 19 or len(fields[0]) != 1:
        raise ValueError('invalid proc stat fields')
    starttime = int(fields[19])
    if starttime <= 0:
        raise ValueError('invalid proc starttime')
    comm = (process / 'comm').read_text(encoding='utf-8').strip()
    if not comm or '\x00' in comm or '\n' in comm or len(comm) > 64:
        raise ValueError('invalid proc comm')
    raw_cmdline = (process / 'cmdline').read_bytes()
    if len(raw_cmdline) > 4096:
        # A same-UID process may legitimately carry a very large argv (an inline
        # program, a long pytest payload). Its identity is still verifiable from
        # stat+comm, and the high-recall classifier keeps the conservative candidate
        # path and inspects the process environment for ownership markers, so an
        # oversized cmdline must not refuse the whole allocation.
        return (pid, starttime, fields[0]), comm, ()
    argv = tuple(
        item.decode('utf-8')
        for item in raw_cmdline.split(b'\0')
        if item
    )
    return (pid, starttime, fields[0]), comm, argv


def _read_process_identity_with_retry(
    process: Path,
) -> tuple[tuple[int, int, str], str, tuple[str, ...]]:
    """Retry one transient procfs I/O race without weakening fail-closed reads."""

    try:
        return _read_process_identity(process)
    except OSError:
        return _read_process_identity(process)


def _read_process_environ_with_retry(process: Path) -> list[bytes]:
    """Retry one transient environ read; a repeated denial still propagates."""

    try:
        payload = (process / 'environ').read_bytes()
    except OSError:
        payload = (process / 'environ').read_bytes()
    return payload.split(b'\0')


def _frozen_non_candidate_reason(
    state: str, comm: str, argv: tuple[str, ...]
) -> str | None:
    if state == 'Z':
        return 'frozen_zombie_non_candidate'
    if comm == 'systemd' and argv == ('/usr/lib/systemd/systemd', '--user'):
        return 'frozen_systemd_user_non_candidate'
    if comm == '(sd-pam)' and argv == ('(sd-pam)',):
        return 'frozen_systemd_pam_non_candidate'
    if (
        comm == 'sshd'
        and len(argv) == 1
        and re.fullmatch(
            r'sshd: [A-Za-z0-9._-]+@(pts/[0-9]+|notty)', argv[0]
        ) is not None
    ):
        return 'frozen_sshd_transport_non_candidate'
    return None


def _is_high_recall_ros_candidate(comm: str, argv: tuple[str, ...]) -> bool:
    summary = ' '.join((comm, *argv)).lower()
    executable = Path(argv[0]).name.lower() if argv else comm.lower()
    if executable.startswith('python') or executable in {
        'sh',
        'bash',
        'dash',
        'fish',
        'zsh',
    }:
        return True
    return any(
        marker in summary
        for marker in (
            'ros2',
            'ros-args',
            'launch',
            'component_container',
            'so101',
            'move_group',
            'moveit',
            'mujoco',
            'gazebo',
            'gz sim',
            'rmw_',
            'fastdds',
            'cyclonedds',
            ' dds',
        )
    )
