"""Stopping an owned execution must clear its whole process group.

The owned child is spawned with ``start_new_session=True`` and is itself a process-tree helper, so it
leads a group that contains its own descendants. The stop path signals the leader's pid and, when the
leader does not exit in time, raises without escalating - which is how this task leaked helpers whose
PGID leader is long gone (``descendant_helper.py``, ``process_tree_helper.py``). The contract has to
terminate the group, escalate to SIGKILL, reap, and re-scan by identity before claiming the tree is gone.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # this directory owns the request/owner fixtures
    sys.path.insert(0, str(HERE))

from test_expert_validation_process_owner import ExecutionProcessOwner, request  # noqa: E402


def _group_members(pgid: int) -> list[int]:
    out = subprocess.run(
        ["ps", "-o", "pid=,pgid=", "-A"], capture_output=True, text=True, check=True
    ).stdout
    members = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) == pgid:
            members.append(int(parts[0]))
    return members


def test_stopping_owned_execution_clears_its_process_group(tmp_path):
    owner = ExecutionProcessOwner(cleanup_checker=lambda _owned: True)
    owned = owner.spawn(request(tmp_path))
    pgid = os.getpgid(owned.pid)
    members_before = _group_members(pgid)
    assert owned.pid in members_before, members_before

    try:
        owner.stop(owned)
        deadline = time.monotonic() + 10.0
        remaining = _group_members(pgid)
        while remaining and time.monotonic() < deadline:
            time.sleep(0.05)
            remaining = _group_members(pgid)
        assert remaining == [], (
            f"process group {pgid} still holds {remaining} after stop "
            f"(spawned {len(members_before)} members)"
        )
    finally:
        for pid in _group_members(pgid):
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass
