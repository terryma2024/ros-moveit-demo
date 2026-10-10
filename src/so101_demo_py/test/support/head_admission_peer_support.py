"""Share the model-assembly lease with a live fixed-budget admission peer."""

import fcntl
import os
import threading
from contextlib import contextmanager


_local_gate = threading.RLock()
_leases = {}


def release_guard_buffers(guard, *, owns_model=False):
    """Retire fixture allocations even when cyclic Python proof objects remain."""
    guard.stop()
    guard._data = None
    guard._model = None
    if owns_model:
        guard.checker._data = None
        guard.checker.model = None


@contextmanager
def admission_peer_cpu_slot(tmp_path_factory):
    """Exclude other guard assemblies; allow the owning fixture to assemble."""
    scratch = tmp_path_factory.getbasetemp()
    shared = scratch.parent if os.environ.get('PYTEST_XDIST_WORKER') else scratch
    path = shared / 'head-admission-peer.lock'
    with _local_gate:
        outermost = path not in _leases
        if outermost:
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            except BaseException:
                os.close(descriptor)
                raise
            _leases[path] = descriptor
        try:
            yield
        finally:
            if outermost:
                os.close(_leases.pop(path))
