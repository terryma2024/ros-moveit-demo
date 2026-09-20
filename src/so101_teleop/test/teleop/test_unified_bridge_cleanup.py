"""Stopping the owned child must clear its whole process group, not just the leader.

The child is spawned with ``start_new_session=True``, so it leads a session of its own, and
``stop_owned`` signals exactly one pid. A descendant that joined that group therefore survives a
"successful" stop - which is what four of this task's leaked helpers look like: their PGID leader is
long gone and they are still running. The stop contract has to terminate the group, escalate to
SIGKILL, reap, and then re-scan by identity before it may claim the tree is gone.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # the bridge test owns the Rig this one reuses
    sys.path.insert(0, str(HERE))

from test_unified_bridge import Rig  # noqa: E402

def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _join_group(pid: int, pgid: int) -> subprocess.Popen:
    """Start a helper that joins the owned child's process group, like a real descendant."""

    def _set_group() -> None:
        os.setpgid(0, pgid)

    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        preexec_fn=_set_group,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            if os.getpgid(process.pid) == pgid:
                return process
        except ProcessLookupError:
            break
        time.sleep(0.02)
    process.kill()
    raise AssertionError(f"descendant {process.pid} never joined group {pgid}")


def test_stopping_the_owner_clears_its_process_group(tmp_path):
    asyncio.run(_clears_its_process_group(tmp_path))


async def _clears_its_process_group(tmp_path):
    rig = Rig(tmp_path)
    descendant: subprocess.Popen | None = None
    try:
        owner = await rig.owner_process.start()
        descendant = _join_group(owner.pid, os.getpgid(owner.pid))
        await rig.owner_process.stop_owned()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _alive(descendant.pid):
            await asyncio.sleep(0.05)
        assert not _alive(descendant.pid), (
            f"descendant {descendant.pid} survived the stop of group {os.getpgid(owner.pid) if _alive(owner.pid) else 'gone'}"
        )
    finally:
        # This test may not leak either: the owner's own stop path is what is under test, so the
        # teardown goes around it and kills the child's whole group directly.
        owner_key = rig.owner_process.owner
        if owner_key is not None and _alive(owner_key.pid):
            try:
                os.killpg(owner_key.pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            rig.owner_process.process.wait(timeout=5)
        if descendant is not None and _alive(descendant.pid):
            try:
                os.kill(descendant.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await rig.close()
