"""Stopping an owned execution must clear its whole process group.

The owned child is spawned with ``start_new_session=True`` and is itself a process-tree helper, so it
leads a group that contains its own descendants. The stop path signals the group but, when a member
does not exit in time, raises without escalating - which is how this task leaked helpers whose PGID
leader is long gone (``descendant_helper.py``, ``process_tree_helper.py``) and whose stop attempt had
already been reported as a failure.

The helpers used here deliberately ignore SIGTERM, the way a stuck coordinator does. A stop that only
signals, or only signals one pid, cannot pass these tests; only terminate-then-escalate-then-reap can.
"""

from __future__ import annotations

from dataclasses import replace
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # this directory owns the request/owner fixtures
    sys.path.insert(0, str(HERE))

import so101_teleop.expert_validation.process_owner as process_owner_module  # noqa: E402
from so101_teleop.expert_validation.process_owner import (  # noqa: E402
    CoordinatorOwnershipError,
    ExecutionProcessOwner,
)
from test_expert_validation_process_owner import request  # noqa: E402


def _group_members(pgid: int) -> list[int]:
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=", "-o", "pgid="], capture_output=True, text=True, check=True
    ).stdout
    members = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit() and int(parts[1]) == pgid:
            members.append(int(parts[0]))
    return members


def _await_group_size(pgid: int, size: int, timeout: float = 10.0) -> list[int]:
    deadline = time.monotonic() + timeout
    members = _group_members(pgid)
    while len(members) != size and time.monotonic() < deadline:
        time.sleep(0.05)
        members = _group_members(pgid)
    return members


def _stubborn_request(tmp_path):
    """A coordinator whose leader and forked runner both ignore SIGTERM."""
    start_request = request(tmp_path)
    return replace(start_request, argv=(*start_request.argv, "--ignore-term"))


def _descendant_pid(tmp_path) -> int:
    """The forked runner's pid, after it has announced that it is ignoring SIGTERM."""
    handshake = tmp_path / "batch-a" / "handshake.json"
    runner_ready = tmp_path / "batch-a" / "batch-a.runner.ready.json"
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and not (handshake.is_file() and runner_ready.is_file()):
        time.sleep(0.02)
    assert handshake.is_file(), "the owned coordinator never forked its runner"
    assert runner_ready.is_file(), "the runner never announced that it ignores SIGTERM"
    return int(json.loads(handshake.read_text(encoding="utf-8"))["runner_pid"])


def test_stopping_an_owned_group_clears_a_member_that_ignores_sigterm(tmp_path):
    owner = ExecutionProcessOwner(cleanup_checker=lambda _owned: True, stop_timeout_s=1.0)
    owned = owner.spawn(_stubborn_request(tmp_path))
    pgid = os.getpgid(owned.pid)
    descendant = _descendant_pid(tmp_path)
    members_before = _await_group_size(pgid, 2)
    assert sorted(members_before) == sorted([owned.pid, descendant]), members_before

    try:
        owner.stop_after_cleanup(owned)
        remaining = _await_group_size(pgid, 0)
        assert remaining == [], (
            f"process group {pgid} still holds {remaining} after stop_after_cleanup "
            f"(spawned {members_before})"
        )
    finally:
        for pid in _group_members(pgid):
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass


def test_a_failed_spawn_does_not_leave_its_group_behind(tmp_path, monkeypatch):
    """The spawn barrier fails on this host's error paths; that path may not leak either."""
    probed: list[int] = []

    def refuse(pid):
        probed.append(pid)
        raise CoordinatorOwnershipError("PROCESS_IDENTITY_MISMATCH")

    owner = ExecutionProcessOwner(cleanup_checker=lambda _owned: True, stop_timeout_s=1.0)
    with monkeypatch.context() as patch:
        patch.setattr(process_owner_module, "_read_identity", refuse)
        with pytest.raises(CoordinatorOwnershipError):
            owner.spawn(_stubborn_request(tmp_path))
        assert owner.active_execution is None

    assert probed, "the barrier never read the identity of the process it spawned"
    leader_pid = probed[0]
    descendant = _descendant_pid(tmp_path)
    assert descendant != leader_pid
    remaining = _await_group_size(leader_pid, 0)
    try:
        assert remaining == [], (
            f"the failed spawn left {remaining} in group {leader_pid} (descendant {descendant})"
        )
        assert descendant not in remaining
    finally:
        for pid in _group_members(leader_pid):
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass
