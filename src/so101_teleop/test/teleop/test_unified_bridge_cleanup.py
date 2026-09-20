"""Stopping the owned child must clear its whole process group, not just the leader.

The child is spawned with ``start_new_session=True``, so it leads a session of its own, and
``stop_owned`` used to signal exactly one pid - which is what four of this task's leaked helpers look
like: their PGID leader is long gone and they are still running. It also refused to escalate, so a
child that ignored ``SIGTERM`` survived the very call that reported it had not stopped.

A group can only gain a member when its leader forks one, so the helper used here forks a descendant
that ignores ``SIGTERM`` itself. A stop that signals one pid, or that gives up after ``SIGTERM``,
cannot pass these tests.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # the bridge test owns the Rig this one reuses
    sys.path.insert(0, str(HERE))

from test_unified_bridge import HelperLaunch, Rig  # noqa: E402


class DescendantLaunch(HelperLaunch):
    """The production helper plus one helper it forks into its own group."""

    def argv(self) -> list[str]:
        return [*super().argv(), "--fork-descendant"]


class StubbornLaunch(HelperLaunch):
    """The production helper, refusing to die on SIGTERM like a stuck child."""

    def argv(self) -> list[str]:
        return [*super().argv(), "--ignore-term"]


def _group_members(pgid: int, *, live_only: bool = False) -> list[int]:
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=", "-o", "pgid=", "-o", "state="],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    members = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        if int(parts[1]) != pgid:
            continue
        if live_only and parts[2][0] == "Z":
            continue
        members.append(int(parts[0]))
    return members


def _await_group_size(pgid: int, size: int, *, live_only: bool, timeout: float = 10.0) -> list[int]:
    deadline = time.monotonic() + timeout
    members = _group_members(pgid, live_only=live_only)
    while len(members) != size and time.monotonic() < deadline:
        time.sleep(0.05)
        members = _group_members(pgid, live_only=live_only)
    return members


def _descendant_pid(rig: Rig, timeout: float = 10.0) -> int:
    record = Path(rig.root) / "descendant.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not record.is_file():
        time.sleep(0.02)
    assert record.is_file(), "the owned child never forked its descendant"
    return int(json.loads(record.read_text(encoding="utf-8"))["pid"])


def _run_scenario(launch_class, tmp_path, *, expect_descendant: bool):
    async def run():
        rig = Rig(tmp_path, launch_class=launch_class)
        pgid = None
        descendant = None
        try:
            owner = await rig.owner_process.start()
            pgid = owner.pgid
            if expect_descendant:
                descendant = _descendant_pid(rig)
                members = _await_group_size(pgid, 2, live_only=True)
                assert sorted(members) == sorted([owner.pid, descendant]), members
            await rig.owner_process.stop_owned()
            remaining = _await_group_size(pgid, 0, live_only=True)
            assert remaining == [], (
                f"process group {pgid} still holds {remaining} after stop_owned "
                f"(descendant {descendant})"
            )
        finally:
            # This test may not leak either, whatever the stop path did.
            if pgid is not None:
                for pid in _group_members(pgid):
                    try:
                        os.kill(pid, 9)
                    except ProcessLookupError:
                        pass
            for handle in (rig.owner_process.process,):
                if handle is not None and handle.poll() is None:
                    handle.wait(timeout=5)
            await rig.close()

    asyncio.run(run())


def test_stopping_the_owner_clears_a_descendant_that_ignores_sigterm(tmp_path):
    _run_scenario(DescendantLaunch, tmp_path, expect_descendant=True)


def test_stop_owned_escalates_when_the_child_itself_ignores_sigterm(tmp_path):
    _run_scenario(StubbornLaunch, tmp_path, expect_descendant=False)


def test_stop_owned_still_refuses_a_drifted_owner_without_signalling(tmp_path):
    """Escalation must not weaken the identity check that guards it."""

    async def run():
        rig = Rig(tmp_path, launch_class=StubbornLaunch)
        try:
            owner = await rig.owner_process.start()
            drifted = type(owner)(
                pid=owner.pid,
                pgid=owner.pgid,
                started_ticks=owner.started_ticks + 1,
                argv_sha256=owner.argv_sha256,
                environment_sha256=owner.environment_sha256,
            )
            rig.owner_process.owner = drifted
            with pytest.raises(Exception, match="OWNER_IDENTITY_DRIFT"):
                await rig.owner_process.stop_owned()
            assert rig.owner_process.process.poll() is None
        finally:
            pgid = getattr(rig.owner_process.owner, "pgid", None)
            if pgid is not None:
                for pid in _group_members(pgid):
                    try:
                        os.kill(pid, 9)
                    except ProcessLookupError:
                        pass
            handle = rig.owner_process.process
            if handle is not None and handle.poll() is None:
                handle.wait(timeout=5)
            await rig.close()

    asyncio.run(run())
