"""Host durability for the end of phase 1.

Phase 1 writes the raw bags without fsync (hashing them back into the recording receipt goes through the page cache). After the last
phase-1 container has stopped, the host makes everything it wrote durable with one `syncfs` on the run root filesystem before phase 2
starts reading it.
"""

import ctypes
import os
import time


def sync_filesystem(path):
    """Flush the filesystem that holds `path`; returns the host record's facts. Raises OSError when the flush fails.

    `os.syncfs` where Python has it, else libc `syncfs` (Linux), else the whole-system `os.sync()` (macOS has no `syncfs`; it is not
    error-reporting, so its record says so)."""
    started = time.monotonic()
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        if hasattr(os, 'syncfs'):
            os.syncfs(descriptor)
            method = 'os.syncfs'
        else:
            libc = ctypes.CDLL(None, use_errno=True)
            if hasattr(libc, 'syncfs'):
                if libc.syncfs(descriptor) != 0:
                    error = ctypes.get_errno()
                    raise OSError(error, os.strerror(error))
                method = 'libc.syncfs'
            else:
                os.sync()
                method = 'os.sync'
    finally:
        os.close(descriptor)
    return dict(method=method, path=str(path), elapsed_s=round(time.monotonic()-started, 6))
