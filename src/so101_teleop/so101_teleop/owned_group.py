"""Terminating an owned process group, and proving afterwards that nothing survived.

An owned child is spawned with ``start_new_session=True``, so it leads a group of its own and every
helper it forks inherits that group. Two things follow, and this module exists because both were
once wrong:

* signalling the leader's pid is not a group stop - a descendant that the leader forked keeps
  running, and the orphan inventory of this task is exactly those descendants;
* refusing to escalate is not a group stop either - a member that ignores ``SIGTERM`` survives the
  attempt, and the caller reports a failure while the process it failed to stop is still running.

So the only stop this module offers is: ``killpg(SIGTERM)``, a bounded wait, ``killpg(SIGKILL)``, a
second bounded wait, and then a fresh scan - returning what is still there instead of claiming
success. The scan uses the platform identity reader rather than a pid list the caller already had,
so the answer is read from the operating system after the signals were delivered.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import signal
import time

from .process_identity import ProcessIdentityError, group_members

__all__ = ["CleanupReceipt", "terminate_group"]

_POLL_INTERVAL_S = 0.02


@dataclass(frozen=True, slots=True)
class CleanupReceipt:
    """What the group looked like after the stop attempt, read fresh from the platform."""

    pgid: int
    leader_pid: int
    term_sent: bool
    kill_sent: bool
    survivors: tuple[int, ...]
    elapsed_s: float

    @property
    def clear(self) -> bool:
        """True only when no process in the group can still be running code."""
        return not self.survivors

    def describe(self) -> str:
        return (
            f"pgid {self.pgid} leader {self.leader_pid} term_sent={self.term_sent} "
            f"kill_sent={self.kill_sent} survivors={list(self.survivors)} "
            f"elapsed={self.elapsed_s:.3f}s"
        )


def _send(pgid: int, number: int) -> bool:
    try:
        os.killpg(pgid, number)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Not ours to signal; the caller learns this from the survivors, not from a silent success.
        return False
    return True


def _live_members(pgid: int) -> tuple[int, ...]:
    """Group members that are not zombies, read after the signals were sent."""
    try:
        members = group_members(pgid)
    except ProcessIdentityError:
        # A group this process cannot read cannot be reported as cleared.
        return (pgid,)
    return tuple(sorted(pid for pid, state in members.items() if state != "Z"))


def _await_clear(pgid: int, timeout_s: float) -> tuple[int, ...]:
    deadline = time.monotonic() + timeout_s
    survivors = _live_members(pgid)
    while survivors and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)
        survivors = _live_members(pgid)
    return survivors


def terminate_group(
    *,
    pgid: int,
    leader_pid: int | None = None,
    timeout_s: float = 3.0,
) -> CleanupReceipt:
    """Stop every process in ``pgid``, escalating once, and report what is left.

    This never raises and never decides whether survivors are acceptable: a spawn failure has to
    report its own error, and both callers need the receipt rather than an exception from the
    cleanup path itself. Each wait is bounded, so the whole call cannot outlive ``2 * timeout_s``
    plus the cost of the scans.
    """
    leader_pid = pgid if leader_pid is None else leader_pid
    started = time.monotonic()
    term_sent = _send(pgid, signal.SIGTERM)
    survivors = _await_clear(pgid, timeout_s)
    kill_sent = False
    if survivors:
        kill_sent = _send(pgid, signal.SIGKILL)
        survivors = _await_clear(pgid, timeout_s)
    return CleanupReceipt(
        pgid=pgid,
        leader_pid=leader_pid,
        term_sent=term_sent,
        kill_sent=kill_sent,
        survivors=survivors,
        elapsed_s=time.monotonic() - started,
    )
