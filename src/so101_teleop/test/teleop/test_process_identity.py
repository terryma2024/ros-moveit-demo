"""The process identity reader must be exact on every platform, and must fail closed.

Ownership decisions in this package - "is this still the process I spawned", "may I signal it",
"is its group really gone" - are made from this reader alone. The original implementation read
``/proc/<pid>``, so on macOS every read raised and the ownership barrier could never be satisfied;
the readers that were added instead (``ps -o lstart=``) resolve one second and cannot separate two
processes started in the same second, which is exactly the window this task's leaked helpers were
spawned in.

These tests pin the contract on the host they run on: a live child is described exactly (pid, group,
state, start marker, argv), and anything the platform will not report fails closed instead of being
guessed. The negative assertions sit behind a positive control on the same reader, so a reader that
simply raises for everything cannot pass this file.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from so101_teleop.owned_group import terminate_group
from so101_teleop.process_identity import (
    ProcessIdentity,
    ProcessIdentityError,
    argv_matches,
    canonical_hash,
    command_fingerprint,
    group_has_live_descendants,
    group_members,
    identity_alive,
    read_identity,
)

HELPER = Path(__file__).parents[1] / "fixtures/process_tree_helper.py"
ARGV_TAIL = (
    "--mode",
    "coordinator",
    "--root",
    "/tmp/so101 identity/batch a",
    "--label",
    "héllo→",
    "",
)


def _spawn(argv: list[str], **kwargs) -> subprocess.Popen:
    return subprocess.Popen(
        argv,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


def _sleep_child(*extra: str) -> subprocess.Popen:
    return _spawn([sys.executable, "-c", "import time; time.sleep(120)", *extra])


def _end(process: subprocess.Popen, timeout: float = 5.0) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=timeout)


def _unused_pid() -> int:
    """A pid this host cannot have allocated: macOS stops below 100000, Linux well below 4M."""
    candidates = (999_999,) if sys.platform == "darwin" else range(9_000_000, 9_000_100)
    for candidate in candidates:
        if not Path(f"/proc/{candidate}").exists():
            return candidate
    raise AssertionError("no unused pid found on this host")


def test_read_identity_describes_a_live_child_exactly():
    process = _spawn([sys.executable, "-c", "import time; time.sleep(120)", *ARGV_TAIL])
    try:
        identity = read_identity(process.pid)
        assert identity.pid == process.pid
        assert identity.pgid == process.pid, "start_new_session makes the child its own group leader"
        assert os.getpgid(process.pid) == process.pid
        assert identity.state != "Z"
        assert identity.start_marker > 0
        assert identity.argv[-len(ARGV_TAIL) :] == ARGV_TAIL
        assert identity.argv_sha256 == canonical_hash(identity.argv)
        assert identity.command_sha256 == command_fingerprint(identity.argv)
        assert argv_matches(identity, (sys.executable, *ARGV_TAIL))
        repeated = read_identity(process.pid)
        assert (repeated.start_marker, repeated.command_sha256, repeated.pgid) == (
            identity.start_marker,
            identity.command_sha256,
            identity.pgid,
        )
    finally:
        _end(process)


def test_read_identity_fails_closed_when_the_platform_will_not_report_it():
    """A pid nobody owns must raise, never return a placeholder; a reaped pid must stop matching."""
    live = _sleep_child()
    try:
        assert read_identity(live.pid).pid == live.pid, "positive control: the reader works here"
        recorded = read_identity(live.pid)
    finally:
        _end(live)

    with pytest.raises(ProcessIdentityError):
        read_identity(_unused_pid())

    # The very same reader that just worked must now refuse this pid rather than invent an identity.
    with pytest.raises(ProcessIdentityError):
        read_identity(live.pid)
    assert identity_alive(live.pid, recorded.start_marker, recorded.command_sha256) is False


def test_start_markers_separate_two_children_started_inside_one_second():
    # The children differ in one argument, so each identity field has to carry its own weight; two
    # identical command lines could not tell the command fingerprint apart from the start marker.
    first = _sleep_child("--first")
    time.sleep(0.05)
    second = _sleep_child("--second")
    try:
        first_identity = read_identity(first.pid)
        second_identity = read_identity(second.pid)
        assert first_identity.start_marker != second_identity.start_marker, (
            "a one-second-resolution start marker cannot tell these two apart"
        )
        assert first_identity.command_sha256 != second_identity.command_sha256
        assert identity_alive(first.pid, first_identity.start_marker, first_identity.command_sha256)
        assert not identity_alive(
            second.pid, first_identity.start_marker, second_identity.command_sha256
        )
        assert not identity_alive(
            second.pid, second_identity.start_marker, first_identity.command_sha256
        )
    finally:
        _end(first)
        _end(second)


def test_group_scan_reports_live_descendants_and_then_their_absence(tmp_path):
    """A descendant only shares the group when the group leader forks it itself.

    ``setpgid`` cannot move a process into a group that lives in another session, so a test that
    wants a real in-group descendant has to let the leader create one - which is also how the
    helpers this task leaked came to exist.
    """
    lonely = _sleep_child()
    leader = None
    try:
        assert group_has_live_descendants(os.getpgid(lonely.pid), lonely.pid) is False
    finally:
        _end(lonely)

    leader = _spawn(
        [
            sys.executable,
            str(HELPER),
            "--mode",
            "coordinator",
            "--root",
            str(tmp_path / "batch"),
            "--batch-id",
            "b1",
        ]
    )
    try:
        pgid = os.getpgid(leader.pid)
        handshake = tmp_path / "batch" / "handshake.json"
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not handshake.is_file():
            time.sleep(0.02)
        assert handshake.is_file(), "the leader never forked its helper"
        descendant_pid = json.loads(handshake.read_text(encoding="utf-8"))["runner_pid"]
        assert descendant_pid != leader.pid
        assert group_members(pgid).get(descendant_pid) not in {None, "Z"}
        assert group_has_live_descendants(pgid, leader.pid) is True

        os.kill(descendant_pid, signal.SIGKILL)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and group_has_live_descendants(pgid, leader.pid):
            time.sleep(0.05)
        # The leader has not reaped it yet, so this asserts the zombie is excluded, not collected.
        assert group_has_live_descendants(pgid, leader.pid) is False
    finally:
        if leader is not None:
            # The runner is the leader's child, so killing the leader alone would leak it.
            terminate_group(pgid=os.getpgid(leader.pid), timeout_s=1.0)
            _end(leader)


def test_argv_match_requires_an_exact_argument_suffix():
    tail = ("--mode", "coordinator", "--root", "/tmp/a b", "")
    identity = ProcessIdentity(
        pid=1,
        pgid=1,
        start_marker=1,
        state="S",
        argv=("/resolved/launcher", "script.py", *tail),
        command_sha256=command_fingerprint(("/resolved/launcher", "script.py", *tail)),
        argv_sha256=canonical_hash(("/resolved/launcher", "script.py", *tail)),
    )
    assert argv_matches(identity, ("/requested/launcher", "script.py", *tail))
    assert argv_matches(identity, ("/requested/launcher", *tail))
    assert not argv_matches(identity, ("/requested/launcher", "script.py", "--mode", "wrapper"))
    assert not argv_matches(identity, ("/requested/launcher", "script.py", *tail, "extra"))
    assert not argv_matches(identity, ("/requested/launcher",))


def test_canonical_hash_is_stable_and_argument_order_sensitive():
    tail = ("--root", "/tmp/a b")
    assert canonical_hash(tail) == hashlib.sha256(
        json.dumps(list(tail), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert canonical_hash(tail) != canonical_hash(tail[::-1])


def test_a_stopped_process_keeps_its_identity():
    """Only the operating system's own liveness signal may invalidate an identity."""
    process = _sleep_child()
    try:
        recorded = read_identity(process.pid)
        assert identity_alive(process.pid, recorded.start_marker, recorded.command_sha256)
        os.kill(process.pid, signal.SIGSTOP)
        time.sleep(0.05)
        assert read_identity(process.pid).state not in {"Z", ""}
        assert identity_alive(process.pid, recorded.start_marker, recorded.command_sha256)
        os.kill(process.pid, signal.SIGCONT)
    finally:
        _end(process)


def test_a_rewritten_launcher_does_not_change_the_durable_fingerprint():
    """This host really does rewrite ``argv[0]``, so the durable fingerprint must not include it.

    The same live child was observed reporting ``/Users/.../venv/bin/python`` on one read and the
    resolved framework binary on the next. A fingerprint over the whole vector then made a live,
    correctly owned process look like a different one, and the ownership barrier refused while the
    process was running - a false negative in the middle of a campaign.
    """
    requested = ("/requested/launcher", "--mode", "coordinator", "--root", "/tmp/a b")
    rewritten = ("/resolved/launcher", *requested[1:])
    before = ProcessIdentity(
        pid=1,
        pgid=1,
        start_marker=7,
        state="R",
        argv=requested,
        command_sha256=command_fingerprint(requested),
        argv_sha256=canonical_hash(list(requested)),
    )
    after = ProcessIdentity(
        pid=1,
        pgid=1,
        start_marker=7,
        state="R",
        argv=rewritten,
        command_sha256=command_fingerprint(rewritten),
        argv_sha256=canonical_hash(list(rewritten)),
    )
    assert before.argv_sha256 != after.argv_sha256, "the raw vector really did change"
    assert before.command_sha256 == after.command_sha256, "the identity must not"
    assert argv_matches(before, requested) and argv_matches(after, requested)
    assert identity_alive.__doc__, "the fingerprint contract is what identity_alive documents"
