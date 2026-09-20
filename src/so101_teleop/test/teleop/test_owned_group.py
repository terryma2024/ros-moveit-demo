"""The group-termination contract, pinned directly: escalate, then prove, never claim.

This module is what stands between "the stop call returned" and "the tree is really gone", so its own
fail-closed behaviour is tested directly rather than only through its callers.
"""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time



import so101_teleop.owned_group as owned_group_module
from so101_teleop.owned_group import terminate_group
from so101_teleop.process_identity import ProcessIdentityError

HELPER = Path(__file__).parents[1] / "fixtures/stubborn_helper.py"


def _spawn_stubborn_group(tmp_path) -> subprocess.Popen:
    """Start a helper that ignores SIGTERM, after it has confirmed it is ignoring it."""
    ready = Path(tmp_path) / "stubborn-ready.json"
    process = subprocess.Popen(
        [sys.executable, str(HELPER), str(ready)],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and not ready.is_file():
        time.sleep(0.02)
    if not ready.is_file():
        process.kill()
        raise AssertionError("the stubborn helper never announced readiness")
    return process


def test_terminate_group_escalates_once_and_proves_the_group_is_gone(tmp_path):
    process = _spawn_stubborn_group(tmp_path)
    pgid = os.getpgid(process.pid)
    try:
        receipt = terminate_group(pgid=pgid, leader_pid=process.pid, timeout_s=0.5)
        assert receipt.term_sent is True, "SIGTERM must always be tried first"
        assert receipt.kill_sent is True, "a SIGTERM-ignoring member requires the escalation"
        assert receipt.clear is True
        assert receipt.survivors == ()
        assert receipt.pgid == pgid and receipt.leader_pid == process.pid
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def test_terminate_group_reports_an_unlistable_group_instead_of_claiming_success(monkeypatch):
    def refuse(_pgid):
        raise ProcessIdentityError()

    monkeypatch.setattr(owned_group_module, "group_members", refuse)
    receipt = terminate_group(pgid=os.getpid(), leader_pid=os.getppid(), timeout_s=0.05)
    assert receipt.clear is False, "a group that cannot be read cannot be reported as cleared"
    assert receipt.survivors == (os.getpid(),)


def test_terminate_group_is_a_no_op_for_a_group_that_is_already_gone():
    process = subprocess.Popen(
        [sys.executable, "-c", "pass"], start_new_session=True, stdin=subprocess.DEVNULL
    )
    pgid = os.getpgid(process.pid)
    process.wait(timeout=5)
    time.sleep(0.05)
    receipt = terminate_group(pgid=pgid, leader_pid=process.pid, timeout_s=0.2)
    assert receipt.term_sent is False
    assert receipt.kill_sent is False
    assert receipt.clear is True


def test_a_stubborn_member_cannot_survive_the_escalation(tmp_path):
    """The other direction: SIGKILL really does end a process that ignored SIGTERM."""
    process = _spawn_stubborn_group(tmp_path)
    try:
        os.kill(process.pid, signal.SIGTERM)
        time.sleep(0.1)
        # The fixture announced that it ignores SIGTERM, and it is still there after one.
        assert process.poll() is None, "the fixture must really ignore SIGTERM, or this is vacuous"
        terminate_group(pgid=os.getpgid(process.pid), timeout_s=0.5)
        # Reaping is what proves the escalation: a zombie still answers a pid liveness probe.
        assert process.wait(timeout=5) == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
