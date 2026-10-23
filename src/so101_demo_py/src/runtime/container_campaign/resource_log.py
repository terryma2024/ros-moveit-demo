"""Low-frequency observations and disk-only dispatch guard.

These logs never grant admission or quality qualification. The owner supplies
its approved disk floor; zero is the only floor when no positive one exists.
Read errors propagate so the owner can fence new dispatch and retain evidence.
"""

import json
import os
from pathlib import Path
import stat


def read_disk_free_bytes(evidence_root: Path) -> int:
    filesystem = os.statvfs(evidence_root)
    if (type(filesystem.f_bavail) is not int or filesystem.f_bavail < 0
            or type(filesystem.f_frsize) is not int or filesystem.f_frsize <= 0):
        raise ValueError('DISK_FREE_SPACE_UNREADABLE')
    return filesystem.f_bavail * filesystem.f_frsize


def check_disk_dispatch_guard(free_bytes: int, *, approved_floor_bytes: int) -> bool:
    if any(type(value) is not int or value < 0 for value in (free_bytes, approved_floor_bytes)):
        raise ValueError('DISK_DISPATCH_GUARD_INVALID')
    return free_bytes > approved_floor_bytes


def append_resource_log(path: Path, *, monotonic_ns: int, observed: dict, missing: dict) -> None:
    # Available producers retain their own source/unit fields. No required
    # metric registry or coverage contract is imposed on observation records.
    if (type(monotonic_ns) is not int or monotonic_ns <= 0
            or type(observed) is not dict or type(missing) is not dict
            or observed.keys() & missing.keys()):
        raise ValueError('RESOURCE_LOG_INVALID')
    data = (json.dumps(dict(monotonic_ns=monotonic_ns, observed=observed, missing=missing),
                       sort_keys=True, allow_nan=False, separators=(',', ':'))+'\n').encode('utf-8')
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise ValueError('RESOURCE_LOG_INVALID')
        with os.fdopen(descriptor, 'ab', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
