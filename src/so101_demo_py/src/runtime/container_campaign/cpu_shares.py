"""Lower a shard container's CPU weight while it does offline processing, and restore it afterwards.

`docker update --cpu-shares` sets the container cgroup's relative CPU weight. A weight only matters while the CPUs are
contended: on an idle host every container still gets what it asks for. The point is to keep a shard's post-recording
offline processing from taking CPU away from the recordings of the other shards, without limiting concurrency.

Rules the Host keeps:
- Only the exact container the shard owner registered is touched, and its identity is re-checked before every update.
- Every update, its result and every refusal is appended (fsynced) to a Host-side journal line in the wave's Host directory.
- A failed update is a named reason in that journal; it never stops the campaign and leaves the weight where it was.
- The weight is restored on every exit path: task end, next claim, a recording phase, a fault, a stop and the wave's end.
"""

import json
import os
from pathlib import Path
import threading
import time

DEFAULT_CPU_SHARES = 1024
MIN_POST_RECORDING_SHARES, MAX_POST_RECORDING_SHARES = 2, DEFAULT_CPU_SHARES
JOURNAL_NAME = 'cpu-shares-journal.jsonl'


def valid_post_recording_shares(value):
    return type(value) is int and MIN_POST_RECORDING_SHARES <= value <= MAX_POST_RECORDING_SHARES


class CpuShareJournal:
    """Append-only JSON lines, one per update or refusal; shared by the wave's shards."""

    def __init__(self, path, *, clock_ns=time.time_ns):
        self.path, self.clock_ns = Path(path), clock_ns
        self._lock = threading.Lock()

    def append(self, **record):
        line = (json.dumps(dict(wall_ns=self.clock_ns(), **record), sort_keys=True, separators=(',', ':'))+'\n').encode()
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            try:
                os.write(fd, line)
                os.fsync(fd)
            finally:
                os.close(fd)


class ShardCpuShares:
    """The weight of one shard container. `target` is `ContainerShardOwner.cpu_target()`."""

    def __init__(self, *, worker_id, target, post_recording_shares, journal):
        if not valid_post_recording_shares(post_recording_shares):
            raise ValueError('CPU_SHARES_VALUE_INVALID')
        self.worker_id, self.target, self.low, self.journal = worker_id, target, post_recording_shares, journal
        self.original = target.original_cpu_shares
        self.current, self._failed, self._lock = self.original, None, threading.Lock()

    def want(self, low):
        """Move to the post-recording weight (`low`) or back to the original; a no-op when already there."""
        value = self.low if low else self.original
        with self._lock:
            if value == self.current:
                self._failed = None   # a phase change away from a refused target re-arms the next attempt
                return
            if value == self._failed:
                return
            self._apply(value, 'POST_RECORDING' if low else 'RESTORE')

    def restore(self, why='RESTORE'):
        """Restore the original weight, retrying even after an earlier failed restore."""
        with self._lock:
            if self.current != self.original:
                self._apply(self.original, why)

    def _apply(self, value, why):
        record = dict(worker_id=self.worker_id, container_id=self.target.container_id, why=why,
                      requested=value, previous=self.current)
        try:
            self.target.verify()
            result = self.target.docker(['docker', 'update', '--cpu-shares', str(value), self.target.container_id])
        except Exception as error:
            self._failed = value
            self.journal.append(**record, ok=False,
                                reason='CPU_SHARES_UPDATE_ERROR: '+type(error).__name__+': '+str(error)[:200])
            return
        if result.returncode != 0:
            self._failed = value
            self.journal.append(**record, ok=False, returncode=result.returncode,
                                reason='CPU_SHARES_UPDATE_FAILED: '+str(result.stderr)[:200])
            return
        self.current, self._failed = value, None
        self.journal.append(**record, ok=True, returncode=0)
