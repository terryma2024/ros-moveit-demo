"""The CampaignSupervisor: real parent, real spawner, real reaper, durable intent.

Task 3 of the macOS MPS / private IPC plan. The approved design (section 6.1) makes the
supervisor the actual parent of the Broker and both Workers, and requires that every spawn is
preceded by an atomically written ``SPAWNING`` intent in a durable ownership receipt. A child
that never acknowledges its registration is never allowed to run, and an unclosed intent
blocks the next campaign.

The tests below drive real child processes (small Python programs) so the flock, the atomic
receipt write, the acknowledge handshake, the timeout kill and the exact reap are all
exercised against the kernel rather than a mock.
"""

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from so101_demo.parallel_batch.campaign_supervisor import (
    ACK_TIMEOUT,
    ACTIVE,
    FAILED,
    SPAWNING,
    STOPPED,
    CampaignBlocked,
    CampaignSupervisor,
    RegistrationAck,
    SpawnIntent,
)

PYTHON = sys.executable

# Under `python -c`, sys.argv[0] is "-c" and the script arguments start at sys.argv[1].
ACK_CHILD = textwrap.dedent(
    """
    import json, os, sys, time
    ack_path = sys.argv[1]
    payload = {
        "pid": os.getpid(),
        "pgid": os.getpgid(0),
        "argv": ["ack-child"],
        "registered_utc": time.time(),
    }
    temporary = ack_path + ".part"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, ack_path)
    time.sleep(float(sys.argv[2]))
    """
)

SILENT_CHILD = textwrap.dedent(
    """
    import sys, time
    time.sleep(float(sys.argv[1]))
    """
)

#: The intent's argv is what the child sees; the test compares against this marker.
ACK_ARGV_MARKER = "ack-child"


def _supervisor(tmp_path, **kwargs):
    return CampaignSupervisor(
        campaign_id="w2-campaign",
        state_root=tmp_path / "supervisor",
        ack_timeout_s=kwargs.pop("ack_timeout_s", 5.0),
        **kwargs,
    )


def _ack_command(ack_path: Path, sleep_s: float = 30.0) -> list[str]:
    return [PYTHON, "-c", ACK_CHILD, str(ack_path), str(sleep_s)]


# --------------------------------------------------------------------------------------
# flock ownership
# --------------------------------------------------------------------------------------


def test_a_second_campaign_supervisor_cannot_hold_the_same_claim(tmp_path):
    """The MPS:DEFAULT claim is exclusive: the second holder fails closed immediately."""

    first = _supervisor(tmp_path)
    first.acquire_claim()
    try:
        second = _supervisor(tmp_path)
        with pytest.raises(CampaignBlocked, match="CAMPAIGN_CLAIM_HELD"):
            second.acquire_claim()
    finally:
        first.release_claim()

    # After a clean release the claim is available again, and the receipt was cleared.
    third = _supervisor(tmp_path)
    third.acquire_claim()
    assert third.receipt_path.exists()
    third.release_claim()


def test_claim_is_not_transferred_by_a_stale_lockfile(tmp_path):
    """The lock is the flock, not the file: deleting the path does not free a held claim."""

    first = _supervisor(tmp_path)
    first.acquire_claim()
    lock_path = first.lock_path
    try:
        lock_path.unlink()
        second = _supervisor(tmp_path)
        # A brand-new lock file means a brand-new flock, which succeeds. What must NOT happen
        # is the first holder losing its claim: its descriptor still owns the old inode.
        second.acquire_claim()
        assert first.holds_claim is True
        second.release_claim()
    finally:
        first.release_claim()


# --------------------------------------------------------------------------------------
# durable receipt
# --------------------------------------------------------------------------------------


def test_receipt_is_written_atomically_and_reads_back(tmp_path):
    """The receipt is replaced atomically and never observed half written."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    try:
        intent = supervisor.begin_spawn(role="worker", slot=1,
                                        argv=("python", "-m", "worker"), nonce="n-1")
        assert isinstance(intent, SpawnIntent)
        assert intent.status == SPAWNING

        on_disk = json.loads(supervisor.receipt_path.read_text())
        assert on_disk["campaign_id"] == "w2-campaign"
        assert on_disk["children"][0]["status"] == SPAWNING
        assert on_disk["children"][0]["role"] == "worker"
        assert on_disk["children"][0]["nonce"] == "n-1"
        assert on_disk["children"][0]["argv"] == ["python", "-m", "worker"]
        # The durable receipt must never contain an unlinked temporary file next to it.
        assert list(supervisor.receipt_path.parent.glob("*.part")) == []
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_unclosed_spawning_intent_blocks_the_next_campaign(tmp_path):
    """A receipt with an unresolved SPAWNING intent refuses a new campaign."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    supervisor.begin_spawn(role="broker", slot=0, argv=("python", "-m", "broker"), nonce="n-2")
    supervisor.release_claim()

    fresh = _supervisor(tmp_path)
    with pytest.raises(CampaignBlocked, match="CAMPAIGN_RECEIPT_UNRESOLVED"):
        fresh.acquire_claim()


def test_receipt_survives_a_supervisor_crash_and_still_blocks(tmp_path):
    """A receipt left behind by a crashed supervisor blocks without signalling anything."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    supervisor.begin_spawn(role="worker", slot=0, argv=("python", "-m", "worker"), nonce="n-3")
    # Simulate the crash: drop the claim without resolving or cleaning up.
    supervisor.abandon_claim_for_test()
    assert supervisor.receipt_path.exists()

    fresh = _supervisor(tmp_path)
    with pytest.raises(CampaignBlocked, match="CAMPAIGN_RECEIPT_UNRESOLVED"):
        fresh.acquire_claim()


def test_unknown_child_in_receipt_is_reported_but_never_signalled(tmp_path):
    """A foreign PID in an old receipt must be reported, not killed."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    supervisor.begin_spawn(role="worker", slot=0, argv=("python", "-m", "worker"), nonce="n-4")
    supervisor.release_claim()

    # Rewrite the receipt as if a foreign process had been adopted by a broken writer.
    document = json.loads(supervisor.receipt_path.read_text())
    document["children"][0]["pid"] = os.getpid()  # this pytest process: definitely not ours
    document["children"][0]["birth_identity"] = 1
    supervisor.receipt_path.write_text(json.dumps(document))

    fresh = _supervisor(tmp_path)
    report = fresh.inspect_orphans()
    assert report.foreign == (os.getpid(),)
    assert report.signalled == ()
    assert os.getpid() == os.getpid()  # still alive, obviously; the point is we never killed it


# --------------------------------------------------------------------------------------
# spawn -> SPAWNING -> registered ACK -> ACTIVE
# --------------------------------------------------------------------------------------


def test_spawn_waits_for_the_registered_ack_before_active(tmp_path):
    """A child that registers is promoted to ACTIVE with its real birth identity recorded."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "child-ack.json"
        record = supervisor.spawn(
            role="worker", slot=0, argv=_ack_command(ack_path, sleep_s=30.0),
            nonce="n-5", ack_path=ack_path,
        )
        assert record.status == ACTIVE
        assert record.pid > 0
        assert record.process_group == record.pid
        assert record.birth_identity > 0
        assert record.ack is not None and isinstance(record.ack, RegistrationAck)
        assert record.ack.pid == record.pid
        on_disk = json.loads(supervisor.receipt_path.read_text())
        assert on_disk["children"][0]["status"] == ACTIVE
        assert on_disk["children"][0]["pid"] == record.pid
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_child_that_never_acknowledges_is_killed_and_reaped(tmp_path):
    """An unacknowledged child never becomes ACTIVE, and is stopped by exact identity."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "never.json"
        record = supervisor.spawn(
            role="broker", slot=0,
            argv=[PYTHON, "-c", SILENT_CHILD, "30"],
            nonce="n-6", ack_path=ack_path, ack_timeout_s=0.5,
        )
        assert record.status == FAILED
        assert record.reason == ACK_TIMEOUT
        assert not ack_path.exists()
        # Exact reap: the pid must be gone, and no zombie may be left behind.
        assert supervisor.is_gone(record.pid) is True
        document = json.loads(supervisor.receipt_path.read_text())
        assert document["children"][0]["status"] == FAILED
        assert document["children"][0]["reason"] == ACK_TIMEOUT
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_stop_uses_exact_identity_and_leaves_nothing_behind(tmp_path):
    """terminate_all stops and reaps owned children, then clears the receipt."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    ack_path = tmp_path / "ack.json"
    record = supervisor.spawn(role="worker", slot=0,
                              argv=_ack_command(ack_path, sleep_s=30.0),
                              nonce="n-7", ack_path=ack_path)
    assert record.status == ACTIVE
    pid = record.pid

    receipt = supervisor.terminate_all()
    assert supervisor.is_gone(pid) is True
    assert receipt.live_children == ()
    assert receipt.cleanup_complete is True
    assert json.loads(supervisor.receipt_path.read_text())["children"] == []
    supervisor.release_claim()


# --------------------------------------------------------------------------------------
# coordinator heartbeat loss
# --------------------------------------------------------------------------------------


def test_coordinator_heartbeat_loss_triggers_owned_cleanup(tmp_path):
    """A dead coordinator makes the supervisor stop its own children, not foreign ones."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    ack_path = tmp_path / "ack.json"
    record = supervisor.spawn(role="worker", slot=0,
                              argv=_ack_command(ack_path, sleep_s=30.0),
                              nonce="n-8", ack_path=ack_path)
    supervisor.note_heartbeat(owner_pid=os.getpid(), monotonic_s=100.0)

    status = supervisor.check_coordinator(now_monotonic_s=200.0, timeout_s=5.0)
    assert status == "HEARTBEAT_LOST"
    assert supervisor.is_gone(record.pid) is True
    assert supervisor.holds_claim is True, "cleanup happens while the claim is still held"
    supervisor.release_claim()


def test_heartbeat_from_the_owning_process_is_accepted(tmp_path):
    """A live coordinator within the timeout keeps the campaign in place."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    try:
        supervisor.note_heartbeat(owner_pid=os.getpid(), monotonic_s=100.0)
        assert supervisor.check_coordinator(now_monotonic_s=101.0, timeout_s=5.0) == "ALIVE"
        # If the owner process itself is gone, the heartbeat is stale no matter the clock.
        assert supervisor.check_coordinator(now_monotonic_s=101.0, timeout_s=5.0,
                                            owner_alive=lambda _pid: False) == "OWNER_GONE"
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


# --------------------------------------------------------------------------------------
# spawn contract
# --------------------------------------------------------------------------------------


def test_spawn_requires_a_known_role_and_slot_bounds(tmp_path):
    """Only the three real roles may be spawned, once each."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    try:
        for role in ("broker", "worker", "worker"):
            pass
        supervisor.begin_spawn(role="broker", slot=0, argv=("x",), nonce="a")
        supervisor.begin_spawn(role="worker", slot=0, argv=("x",), nonce="b")
        with pytest.raises(CampaignBlocked, match="UNOWNED_ROLE"):
            supervisor.begin_spawn(role="controller", slot=0, argv=("x",), nonce="c")
        with pytest.raises(CampaignBlocked, match="DUPLICATE_ROLE_SLOT"):
            supervisor.begin_spawn(role="worker", slot=0, argv=("x",), nonce="d")
        with pytest.raises(CampaignBlocked, match="UNOWNED_ROLE"):
            supervisor.begin_spawn(role="worker", slot=5, argv=("x",), nonce="e")
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_clean_release_clears_the_receipt_for_the_next_campaign(tmp_path):
    """A campaign that stops its children and releases leaves no blocking state behind."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    ack_path = tmp_path / "ack.json"
    supervisor.spawn(role="worker", slot=0, argv=_ack_command(ack_path, sleep_s=30.0),
                     nonce="n-9", ack_path=ack_path)
    supervisor.terminate_all()
    supervisor.release_claim()

    successor = _supervisor(tmp_path)
    successor.acquire_claim()
    assert successor.receipt.children == ()
    successor.release_claim()
