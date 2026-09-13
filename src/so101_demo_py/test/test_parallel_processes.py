"""Focused ownership contracts for replacing an exited shared Broker."""

import signal
import time

import pytest


def test_proc_stat_start_time_parser_ignores_spaces_and_parentheses_in_comm():
    from so101_demo.runtime.parallel_processes import _parse_proc_stat_start_time

    suffix = "S " + " ".join(str(value) for value in range(1, 19)) + " 4242"
    assert _parse_proc_stat_start_time(
        f"123 (broker (generation 2) worker) {suffix}"
    ) == 4242


def test_wait_can_retire_exact_exited_broker_and_continue_with_replacement():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    old = OwnedProcess("batch-1", "broker", 101, 101, ("broker-g1",), 11)
    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 12)
    replacement = OwnedProcess("batch-1", "broker", 201, 201, ("broker-g2",), 21)
    identities = {102: worker, 201: replacement}
    members = {101: (103,), 102: (), 201: (201,)}
    signals = []
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda pid: identities.get(pid),
        signal_group=lambda pgid, value: (
            signals.append((pgid, value)), members.__setitem__(pgid, ())
        ),
        group_members_reader=lambda pgid: members.get(pgid, ()),
    )
    supervisor._record_started(old, poll=lambda: 17)
    supervisor._record_started(worker, poll=lambda: 0)

    def recover(exited, code):
        assert (exited, code) == (old, 17)
        assert supervisor.retire_owned(exited, term_timeout_s=0.01) is True
        supervisor._record_started(replacement, poll=lambda: None)
        return True

    assert supervisor.wait_for_children(
        deadline_monotonic_s=time.monotonic() + 1.0,
        health_recovery=recover,
    ) == (0,)
    assert signals == [(101, signal.SIGTERM)]
    assert supervisor.processes == (replacement,)
    assert supervisor.shutdown(wait_group=lambda *_args: True) is True
    assert signals == [
        (101, signal.SIGTERM),
        (201, signal.SIGTERM),
    ]
    assert supervisor.processes == ()


def test_wait_replaces_an_exact_broker_that_is_alive_but_reports_unhealthy():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    old = OwnedProcess("batch-1", "broker", 101, 101, ("broker-g1",), 11)
    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 12)
    replacement = OwnedProcess("batch-1", "broker", 201, 201, ("broker-g2",), 21)
    identities = {101: old, 102: worker, 201: replacement}
    members = {101: (101,), 102: (), 201: (201,)}
    signals = []
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda pid: identities.get(pid),
        signal_group=lambda pgid, value: (
            signals.append((pgid, value)),
            identities.pop(pgid, None),
            members.__setitem__(pgid, ()),
        ),
        group_members_reader=lambda pgid: members.get(pgid, ()),
    )
    supervisor._record_started(
        old, poll=lambda: None if old.pid in identities else -signal.SIGTERM
    )
    supervisor._record_started(worker, poll=lambda: 0)
    health = {old: False, replacement: True}
    recovered = []

    def recover(expected, code):
        recovered.append((expected, code))
        assert supervisor.retire_owned(expected, term_timeout_s=0.01) is True
        supervisor._record_started(replacement, poll=lambda: None)
        return True

    assert supervisor.wait_for_children(
        deadline_monotonic_s=time.monotonic() + 1.0,
        health_recovery=recover,
        health_probe=lambda expected: health[expected],
    ) == (0,)
    assert recovered == [(old, None)]
    assert signals == [(101, signal.SIGTERM)]
    assert supervisor.processes == (replacement,)


def test_retirement_never_adopts_a_similar_unowned_identity():
    from so101_demo.runtime.parallel_processes import (
        OwnedProcess,
        ProcessSupervisor,
        SupervisorError,
    )

    owned = OwnedProcess("batch-1", "broker", 101, 101, ("broker-g1",), 11)
    unowned = OwnedProcess("batch-1", "broker", 101, 101, ("other",), 12)
    signals = []
    supervisor = ProcessSupervisor(
        "batch-1",
        signal_group=lambda pgid, value: signals.append((pgid, value)),
        group_members_reader=lambda _pgid: (),
    )
    supervisor._record_started(owned, poll=lambda: 17)

    with pytest.raises(SupervisorError, match="UNOWNED_PROCESS"):
        supervisor.retire_owned(unowned)
    assert signals == []
    assert supervisor.processes == (owned,)


def test_retirement_rejects_a_reused_session_leader_before_any_group_signal():
    from so101_demo.runtime.parallel_processes import (
        OwnedProcess,
        ProcessSupervisor,
        SupervisorError,
    )

    exited = OwnedProcess("batch-1", "broker", 101, 101, ("broker-g1",), 11)
    reused = OwnedProcess("batch-1", "broker", 101, 101, ("unowned",), 99)
    signals = []
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: reused,
        signal_group=lambda pgid, value: signals.append((pgid, value)),
        group_members_reader=lambda _pgid: (101,),
    )
    supervisor._record_started(exited, poll=lambda: 17)

    with pytest.raises(SupervisorError, match="PID_REUSE"):
        supervisor.retire_owned(exited)

    assert signals == []
    assert supervisor.processes == (exited,)


def test_terminal_health_failure_waits_for_workers_after_exact_broker_retirement():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    broker = OwnedProcess("batch-1", "broker", 101, 101, ("broker",), 11)
    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 12)
    identities = {102: worker}
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda pid: identities.get(pid),
        group_members_reader=lambda _pgid: (),
    )
    supervisor._record_started(broker, poll=lambda: 17)
    supervisor._record_started(worker, poll=lambda: 0)

    def terminal_failure(exited, code):
        assert (exited, code) == (broker, 17)
        assert supervisor.retire_owned(exited) is True
        return False

    assert supervisor.wait_for_children(
        deadline_monotonic_s=time.monotonic() + 1.0,
        health_recovery=terminal_failure,
    ) == (0,)
    assert supervisor.processes == ()


def test_wait_repolls_worker_that_exits_between_poll_and_identity_readback():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 12)
    observations = iter((None, 7))
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: None,
        group_members_reader=lambda _pgid: (),
    )
    supervisor._record_started(worker, poll=lambda: next(observations))

    assert supervisor.wait_for_children(
        deadline_monotonic_s=time.monotonic() + 1.0
    ) == (7,)
    assert supervisor.processes == ()


def test_wait_boundedly_repolls_until_absent_child_becomes_waitable():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 12)
    observations = iter((None, None, 7))
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: None,
        group_members_reader=lambda _pgid: (),
    )
    supervisor._record_started(worker, poll=lambda: next(observations))

    assert supervisor.wait_for_children(
        deadline_monotonic_s=time.monotonic() + 1.0
    ) == (7,)
    assert supervisor.processes == ()


def test_wait_still_rejects_absent_worker_that_remains_nonterminal():
    from so101_demo.runtime.parallel_processes import (
        OwnedProcess,
        ProcessSupervisor,
        SupervisorError,
    )

    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 12)
    supervisor = ProcessSupervisor(
        "batch-1", identity_reader=lambda _pid: None
    )
    supervisor._record_started(worker, poll=lambda: None)

    with pytest.raises(SupervisorError, match="OWNED_PROCESS_ABSENT"):
        supervisor.wait_for_children(
            deadline_monotonic_s=time.monotonic() + 1.0
        )


def test_wait_repolls_broker_exit_before_invoking_exact_recovery():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    broker = OwnedProcess("batch-1", "broker", 101, 101, ("broker",), 11)
    worker = OwnedProcess("batch-1", "worker", 102, 102, ("worker",), 12)
    broker_observations = [None, 17]

    def broker_poll():
        if len(broker_observations) > 1:
            return broker_observations.pop(0)
        return broker_observations[0]

    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda pid: worker if pid == worker.pid else None,
        group_members_reader=lambda _pgid: (),
    )
    supervisor._record_started(broker, poll=broker_poll)
    supervisor._record_started(worker, poll=lambda: 0)
    recovered = []

    def terminal_failure(exited, code):
        recovered.append((exited, code))
        assert supervisor.retire_owned(exited) is True
        return False

    assert supervisor.wait_for_children(
        deadline_monotonic_s=time.monotonic() + 1.0,
        health_recovery=terminal_failure,
    ) == (0,)
    assert recovered == [(broker, 17)]
    assert supervisor.processes == ()


def test_live_retirement_keeps_authority_when_leader_exits_before_descendants():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    broker = OwnedProcess("batch-1", "broker", 101, 101, ("broker",), 11)
    state = {"alive": True, "members": (101, 103)}
    signals = []

    def send(pgid, value):
        signals.append((pgid, value))
        if len(signals) == 1:
            state.update(alive=False, members=(103,))
        else:
            state["members"] = ()

    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: broker if state["alive"] else None,
        signal_group=send,
        group_members_reader=lambda _pgid: state["members"],
    )
    supervisor._record_started(
        broker, poll=lambda: None if state["alive"] else 17
    )

    assert supervisor.retire_owned(
        broker, term_timeout_s=0.01, kill_timeout_s=0.01
    ) is True
    assert signals == [
        (101, signal.SIGTERM),
        (101, signal.SIGTERM),
    ]
    assert supervisor.processes == ()


def test_shutdown_rejects_reused_exited_leader_without_signalling_group():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    exited = OwnedProcess("batch-1", "broker", 101, 101, ("broker",), 11)
    reused = OwnedProcess("batch-1", "broker", 101, 101, ("unowned",), 99)
    signals = []
    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: reused,
        signal_group=lambda pgid, value: signals.append((pgid, value)),
        group_members_reader=lambda _pgid: (101,),
    )
    supervisor._record_started(exited, poll=lambda: 17)

    assert supervisor.shutdown() is False
    assert signals == []
    assert supervisor.processes == (exited,)


def test_shutdown_retires_descendants_when_live_worker_leader_exits_on_sigint():
    from so101_demo.runtime.parallel_processes import OwnedProcess, ProcessSupervisor

    worker = OwnedProcess("batch-1", "worker", 101, 101, ("worker",), 11)
    state = {"alive": True, "members": (101, 103)}
    signals = []

    def send(pgid, value):
        signals.append((pgid, value))
        if value == signal.SIGINT:
            state.update(alive=False, members=(103,))
        else:
            state["members"] = ()

    supervisor = ProcessSupervisor(
        "batch-1",
        identity_reader=lambda _pid: worker if state["alive"] else None,
        signal_group=send,
        group_members_reader=lambda _pgid: state["members"],
    )
    supervisor._record_started(
        worker, poll=lambda: None if state["alive"] else 0
    )

    assert supervisor.shutdown(
        interrupt_timeout_s=0.01,
        term_timeout_s=0.01,
        kill_timeout_s=0.01,
    ) is True
    assert signals == [(101, signal.SIGINT), (101, signal.SIGTERM)]
    assert supervisor.processes == ()
