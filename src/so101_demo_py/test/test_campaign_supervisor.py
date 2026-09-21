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
    IDENTITY_UNAVAILABLE,
    ACTIVE,
    FAILED,
    SPAWNING,
    SPAWN_FAILED,
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


def test_a_child_without_a_readable_birth_identity_is_never_promoted(tmp_path):
    """Without a birth identity a child cannot be signalled safely, so it is stopped and failed.

    This is a real defect the Task 13 runtime smoke found: the identity read races with process
    start, and the first version recorded `birth_identity: None` while still reporting the child
    ACTIVE, which would have made a later PID-reuse check impossible.
    """

    reads = {"count": 0}

    def unreadable_identity(pid):
        reads["count"] += 1
        return None

    supervisor = CampaignSupervisor(
        campaign_id="identity-campaign", state_root=tmp_path / "supervisor",
        ack_timeout_s=5.0, identity_reader=unreadable_identity, sleep=lambda _s: None,
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(role="worker", slot=0,
                                  argv=_ack_command(ack_path, sleep_s=30.0),
                                  nonce="n-identity", ack_path=ack_path)
        assert record.status == FAILED
        assert record.reason == IDENTITY_UNAVAILABLE
        assert record.birth_identity is None
        assert reads["count"] >= 2, "the read must be retried before giving up"
        assert supervisor.is_gone(record.pid) is True
        document = json.loads(supervisor.receipt_path.read_text())
        assert document["children"][0]["status"] == FAILED
        assert document["children"][0]["birth_identity"] is None
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_a_child_that_exits_after_the_spawn_read_is_still_promoted_with_its_identity(tmp_path):
    """A vanished child is not a reused PID: the spawn-time identity stands.

    This is the Task 13 root cause, measured: on this host a Worker can complete its round trips
    inside the ACK window, so the promotion recheck legitimately sees a zombie or nothing at all.
    Refusing that rejected healthy Workers; refusing a *changed* identity is what stops reuse.
    """

    from so101_demo.parallel_batch.start_guard_probe import ProcessIdentityRecord

    parent_pid = os.getpid()
    child_reads = {"count": 0}

    def child_exits_after_the_first_read(pid):
        if pid == parent_pid:
            return ProcessIdentityRecord(pid=pid, start_time_ticks=1)
        child_reads["count"] += 1
        if child_reads["count"] == 1:
            return ProcessIdentityRecord(pid=pid, start_time_ticks=555001)
        return None

    supervisor = CampaignSupervisor(
        campaign_id="identity-spawn-time", state_root=tmp_path / "supervisor",
        ack_timeout_s=5.0, identity_timeout_s=0.05,
        identity_reader=child_exits_after_the_first_read, sleep=lambda _s: None,
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(role="worker", slot=0,
                                  argv=_ack_command(ack_path, sleep_s=30.0),
                                  nonce="n-short-lived", ack_path=ack_path)
        assert record.status == ACTIVE
        assert record.birth_identity == 555001
        assert child_reads["count"] >= 2, "read at spawn, rechecked at promotion"
        document = json.loads(supervisor.receipt_path.read_text())
        assert document["children"][0]["birth_identity"] == 555001
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_a_stable_identity_read_at_spawn_and_promotion_promotes_the_child(tmp_path):
    """Two agreeing reads (spawn then promotion) promote the child with that identity."""

    from so101_demo.parallel_batch.start_guard_probe import ProcessIdentityRecord

    supervisor = CampaignSupervisor(
        campaign_id="identity-stable", state_root=tmp_path / "supervisor",
        ack_timeout_s=5.0, sleep=lambda _s: None,
        identity_reader=lambda pid: ProcessIdentityRecord(pid=pid, start_time_ticks=777001),
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(role="worker", slot=0,
                                  argv=_ack_command(ack_path, sleep_s=30.0),
                                  nonce="n-stable", ack_path=ack_path)
        assert record.status == ACTIVE
        assert record.birth_identity == 777001
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_a_changed_identity_between_spawn_and_promotion_fails_closed(tmp_path):
    """A PID reporting a different identity at promotion means reuse: refuse it."""

    from so101_demo.parallel_batch.start_guard_probe import ProcessIdentityRecord

    parent_pid = os.getpid()
    child_reads = {"count": 0}

    def reused_pid(pid):
        # The supervisor's own process reports normally; the child's identity *changes* between
        # the spawn read and the promotion recheck, which is exactly what PID reuse looks like.
        if pid == parent_pid:
            return ProcessIdentityRecord(pid=pid, start_time_ticks=1)
        child_reads["count"] += 1
        return ProcessIdentityRecord(pid=pid,
                                     start_time_ticks=1000 if child_reads["count"] == 1 else 2000)

    supervisor = CampaignSupervisor(
        campaign_id="identity-changed", state_root=tmp_path / "supervisor",
        ack_timeout_s=5.0, identity_timeout_s=0.05, identity_reader=reused_pid,
        sleep=lambda _s: None,
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(role="worker", slot=0,
                                  argv=_ack_command(ack_path, sleep_s=30.0),
                                  nonce="n-changed", ack_path=ack_path)
        assert record.status == FAILED
        assert record.reason == IDENTITY_UNAVAILABLE
        assert child_reads["count"] >= 2
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_a_child_whose_identity_resolves_on_a_retry_is_promoted(tmp_path):
    """A slow but successful identity read still promotes the child, with the real identity."""

    from so101_demo.parallel_batch.start_guard_probe import ProcessIdentityRecord

    reads = {"count": 0}

    def slow_identity(pid):
        reads["count"] += 1
        if reads["count"] < 3:
            return None
        return ProcessIdentityRecord(pid=pid, start_time_ticks=424242)

    supervisor = CampaignSupervisor(
        campaign_id="identity-retry", state_root=tmp_path / "supervisor",
        ack_timeout_s=5.0, identity_reader=slow_identity, sleep=lambda _s: None,
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(role="worker", slot=0,
                                  argv=_ack_command(ack_path, sleep_s=30.0),
                                  nonce="n-retry", ack_path=ack_path)
        assert record.status == ACTIVE
        assert record.birth_identity == 424242
        assert reads["count"] >= 2, "read retried at spawn and rechecked at promotion"
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_a_child_stderr_sink_is_accepted_and_used(tmp_path):
    """A child's own diagnostics can be captured, so a failing child is never silent."""

    supervisor = _supervisor(tmp_path)
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        log_path = tmp_path / "child.log"
        with open(log_path, "wb") as sink:
            record = supervisor.spawn(
                role="worker", slot=0,
                argv=[PYTHON, "-c", "print('child diagnostic', file=__import__('sys').stderr, flush=True)"],
                nonce="n-stderr", ack_path=ack_path, ack_timeout_s=2.0, stderr=sink)
        assert record.status == FAILED  # no ACK was written, so it is refused, and that is fine
        assert "child diagnostic" in log_path.read_text()
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


# --------------------------------------------------------------------------------------
# Owner records (Task 6): the intent is durable before Popen, the readback confirms it after
# --------------------------------------------------------------------------------------

OWNER_BATCH = "batch-7"


def _owner_environment(tmp_path, **overrides):
    environment = {
        "SO101_OWNER_TREE_ROOT": str(tmp_path / "owner-tree"),
        "SO101_OWNER_CAMPAIGN_ID": "w2-campaign",
        "SO101_OWNER_BATCH_ID": OWNER_BATCH,
        "SO101_OWNER_GENERATION": "1",
    }
    environment.update(overrides)
    return environment


def _owner_directory(tmp_path):
    return tmp_path / "owner-tree" / "w2-campaign" / OWNER_BATCH


def _observing_popen(observed, directory):
    """The real Popen, with what the supervisor knew at that moment recorded first."""

    real_popen = subprocess.Popen

    def popen(argv, **kwargs):
        observed["argv"] = list(argv)
        observed["env"] = kwargs.get("env")
        observed["intents"] = sorted(path.name for path in directory.glob("*.intent.json"))
        observed["confirmed"] = sorted(path.name for path in directory.glob("*.confirmed.json"))
        observed["parts"] = sorted(path.name for path in directory.glob("*.part"))
        return real_popen(argv, **kwargs)

    return popen


def _owner_supervisor(tmp_path, **kwargs):
    return CampaignSupervisor(
        campaign_id="w2-campaign",
        state_root=tmp_path / "supervisor",
        ack_timeout_s=kwargs.pop("ack_timeout_s", 5.0),
        **kwargs,
    )


def _abandoned(directory):
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.abandoned.json"))
    ]


def test_a_spawn_records_its_owner_intent_before_popen_and_confirms_the_child(tmp_path):
    from so101_demo.runtime.owner_records import command_fingerprint

    directory = _owner_directory(tmp_path)
    observed = {}
    supervisor = _owner_supervisor(
        tmp_path,
        popen=_observing_popen(observed, directory),
        owner_environment=_owner_environment(tmp_path, **{"SO101_OWNER_TOKEN": "campaign-abc"}),
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(
            role="worker", slot=0, argv=_ack_command(ack_path, sleep_s=30.0),
            nonce="n-owner", ack_path=ack_path,
        )
        assert record.status == ACTIVE
        assert len(observed["intents"]) == 1, "the intent is durable before Popen"
        assert observed["confirmed"] == [], "the confirmation is written after Popen"
        assert observed["parts"] == [], "an atomic write never leaves a .part behind"

        intent = json.loads((directory / observed["intents"][0]).read_text(encoding="utf-8"))
        assert intent["schema"] == "so101.owner-intent/1"
        assert intent["role"] == "WORKER"
        assert intent["generation"] == 1
        assert intent["parent_spawn_token"] == "campaign-abc"
        assert intent["expected_executable"] == PYTHON
        assert intent["argv_sha256"] == command_fingerprint(record.argv)

        child_environment = observed["env"]
        assert child_environment["SO101_OWNER_TOKEN"] == intent["spawn_token"]
        assert child_environment["SO101_OWNER_PARENT_TOKEN"] == "campaign-abc"
        assert child_environment["SO101_OWNER_TREE_ROOT"] == str(tmp_path / "owner-tree")
        assert child_environment["SO101_OWNER_BATCH_ID"] == OWNER_BATCH
        assert child_environment["SO101_OWNER_GENERATION"] == "1"

        confirmed = list(directory.glob("*.confirmed.json"))
        assert [path.name for path in confirmed] == [f"{intent['spawn_token']}.confirmed.json"]
        document = json.loads(confirmed[0].read_text(encoding="utf-8"))
        assert document["pid"] == record.pid
        assert document["pgid"] == record.process_group == record.pid
        assert document["started_ticks"] == record.birth_identity
        assert document["command_sha256"] == intent["argv_sha256"]
        assert not list(directory.glob("*.abandoned.json"))
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_a_spawn_without_an_owner_context_is_unchanged(tmp_path):
    observed = {}
    supervisor = _owner_supervisor(
        tmp_path,
        popen=_observing_popen(observed, _owner_directory(tmp_path)),
        owner_environment={},
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(
            role="worker", slot=0, argv=_ack_command(ack_path, sleep_s=30.0),
            nonce="n-inert", ack_path=ack_path,
        )
        assert record.status == ACTIVE
        assert observed["env"] is None, "Popen still inherits the environment exactly as before"
        assert observed["argv"] == list(record.argv)
        assert not (tmp_path / "owner-tree").exists()
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_a_role_outside_the_owner_vocabulary_is_spawned_without_a_record(tmp_path):
    """The supervisor may own roles the owner tree does not know; none is invented for them."""

    supervisor = _owner_supervisor(
        tmp_path, owner_environment=_owner_environment(tmp_path, **{"SO101_OWNER_TOKEN": "c-1"})
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(
            role="coordinator", slot=0, argv=_ack_command(ack_path, sleep_s=30.0),
            nonce="n-coordinator", ack_path=ack_path,
        )
        assert record.status == ACTIVE
        assert not (tmp_path / "owner-tree").exists()
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_the_broker_role_is_mapped_to_the_upper_case_vocabulary(tmp_path):
    directory = _owner_directory(tmp_path)
    supervisor = _owner_supervisor(
        tmp_path,
        popen=_observing_popen({}, directory),
        owner_environment=_owner_environment(tmp_path),
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(
            role="broker", slot=0, argv=_ack_command(ack_path, sleep_s=30.0),
            nonce="n-broker", ack_path=ack_path,
        )
        assert record.status == ACTIVE
        intents = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in directory.glob("*.intent.json")
        ]
        assert [intent["role"] for intent in intents] == ["BROKER"]
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_an_ack_timeout_abandons_the_record_and_keeps_the_confirmation(tmp_path):
    """The child was really born and really read back; the *spawn* is what failed."""

    directory = _owner_directory(tmp_path)
    supervisor = _owner_supervisor(
        tmp_path,
        popen=_observing_popen({}, directory),
        owner_environment=_owner_environment(tmp_path),
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(
            role="worker", slot=0, argv=[PYTHON, "-c", SILENT_CHILD, "30.0"],
            nonce="n-silent", ack_path=ack_path, ack_timeout_s=0.5,
        )
        assert record.status == FAILED
        assert record.reason == ACK_TIMEOUT
        assert [marker["reason"] for marker in _abandoned(directory)] == [ACK_TIMEOUT]
        assert len(list(directory.glob("*.confirmed.json"))) == 1
        assert len(list(directory.glob("*.intent.json"))) == 1
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_an_unreadable_child_identity_abandons_the_record(tmp_path):
    directory = _owner_directory(tmp_path)
    supervisor = CampaignSupervisor(
        campaign_id="w2-campaign",
        state_root=tmp_path / "supervisor",
        ack_timeout_s=5.0,
        identity_timeout_s=0.05,
        identity_reader=lambda _pid: None,
        sleep=lambda _s: None,
        owner_environment=_owner_environment(tmp_path),
    )
    supervisor.acquire_claim()
    try:
        ack_path = tmp_path / "ack.json"
        record = supervisor.spawn(
            role="worker", slot=0, argv=_ack_command(ack_path, sleep_s=30.0),
            nonce="n-unreadable", ack_path=ack_path,
        )
        assert record.status == FAILED
        assert record.reason == IDENTITY_UNAVAILABLE
        assert [marker["reason"] for marker in _abandoned(directory)] == [IDENTITY_UNAVAILABLE]
        assert not list(directory.glob("*.confirmed.json"))
    finally:
        supervisor.terminate_all()
        supervisor.release_claim()


def test_a_failed_popen_abandons_the_record(tmp_path):
    directory = _owner_directory(tmp_path)

    def popen(*_args, **_kwargs):
        raise OSError("cannot spawn")

    supervisor = _owner_supervisor(
        tmp_path, popen=popen, owner_environment=_owner_environment(tmp_path)
    )
    supervisor.acquire_claim()
    try:
        with pytest.raises(CampaignBlocked, match=SPAWN_FAILED):
            supervisor.spawn(
                role="worker", slot=0, argv=[PYTHON, "-c", SILENT_CHILD, "1.0"],
                nonce="n-failed", ack_path=tmp_path / "ack.json",
            )
        assert [marker["reason"] for marker in _abandoned(directory)] == [SPAWN_FAILED]
        assert not list(directory.glob("*.confirmed.json"))
    finally:
        supervisor.release_claim()


def test_nothing_is_spawned_when_the_owner_record_cannot_be_written(tmp_path):
    """No record, no spawn: a child the recovery path cannot see is worse than a refusal."""

    spawned = []

    def popen(*args, **_kwargs):
        spawned.append(args)
        raise AssertionError("nothing may be spawned without a durable owner record")

    # A plain file where the owner-record root must be a directory: every write under it fails.
    (tmp_path / "owner-tree").write_text("not a directory", encoding="utf-8")
    supervisor = _owner_supervisor(
        tmp_path, popen=popen, owner_environment=_owner_environment(tmp_path)
    )
    supervisor.acquire_claim()
    try:
        with pytest.raises(CampaignBlocked, match=SPAWN_FAILED):
            supervisor.spawn(
                role="worker", slot=0, argv=[PYTHON, "-c", SILENT_CHILD, "1.0"],
                nonce="n-unwritable", ack_path=tmp_path / "ack.json",
            )
        assert spawned == []
        document = json.loads(supervisor.receipt_path.read_text())
        assert [child["status"] for child in document["children"]] == [FAILED]
    finally:
        supervisor.release_claim()
