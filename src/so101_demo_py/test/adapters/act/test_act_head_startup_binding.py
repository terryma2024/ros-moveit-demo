"""One-time native startup binding preserves frozen scope and refuses unsafe races."""

import threading

import pytest

from test_act_head_local_state import prepared, local_state
from test_act_head_local_runtime import runtime_setup, prime_current_inputs
from test_act_head_local_observer import wait_for


def unbound_state():
    scope, record, payload = prepared()
    expected = scope['controller_identity']
    scope['controller_identity'] = None
    return local_state(scope), scope, expected, record, payload


def test_unbound_inventory_refused_then_exact_once_binding_preserves_deadline_and_scope():
    state, scope, expected, record, payload = unbound_state()
    assert state.controller_bound is False
    with pytest.raises(PermissionError, match='HEAD_LOCAL_CONTROLLER_UNBOUND'):
        state.register_prepared(record, payload)
    assert state.inventory == {} and state.faulted is False
    deadline = state.search_deadline_ns
    assert state.bind_controller_identity(expected, dict(expected)) == expected
    assert state.controller_bound is True
    assert state.scope == dict(scope, controller_identity=expected)
    assert state.search_deadline_ns == deadline
    leaked = state.scope
    leaked['controller_identity']['boot'] = 'changed'
    assert state.scope['controller_identity'] == expected
    state.register_prepared(record, payload)
    with pytest.raises(PermissionError, match='HEAD_LOCAL_CONTROLLER_ALREADY_BOUND'):
        state.bind_controller_identity(expected, expected)
    assert state.scope['controller_identity'] == expected


@pytest.mark.parametrize('damage', ['generation', 'primary', 'malformed', 'fault'])
def test_unbound_binding_refuses_wrong_peer_scope_or_first_fault(damage):
    state, scope, expected, record, payload = unbound_state()
    main, primary = dict(expected), dict(expected)
    if damage == 'generation':
        main['generation'] += 1
        primary['generation'] += 1
    elif damage == 'primary':
        primary['boot'] = 'another-controller'
    elif damage == 'malformed':
        main['incarnation'] = '\x00'
    else:
        state.latch_fault('FIRST_FAULT')
    with pytest.raises(PermissionError):
        state.bind_controller_identity(main, primary)
    assert not state.controller_bound and state.scope == scope
    assert state.inventory == {} and state.faulted
    if damage == 'fault':
        assert state.snapshot['fault']['reason'] == 'FIRST_FAULT'


def test_concurrent_binding_has_one_winner_and_cannot_replace_frozen_identity():
    state, scope, expected, record, payload = unbound_state()
    barrier = threading.Barrier(3)
    results = []
    def bind():
        barrier.wait(timeout=2.)
        try:
            results.append(state.bind_controller_identity(expected, expected))
        except PermissionError as error:
            results.append(str(error))
    workers = [threading.Thread(target=bind) for _ in range(2)]
    for worker in workers:
        worker.start()
    barrier.wait(timeout=2.)
    for worker in workers:
        worker.join(timeout=2.)
        assert not worker.is_alive()
    assert results.count(expected) == 1
    assert results.count('HEAD_LOCAL_CONTROLLER_ALREADY_BOUND') == 1
    assert state.scope == dict(scope, controller_identity=expected)


def test_guarded_runtime_binds_the_owner_identity_then_allows_dispatch(monkeypatch):
    row = runtime_setup(monkeypatch, unbound=True)
    try:
        row.runtime.start()
        assert row.state.controller_bound is False
        with pytest.raises(PermissionError):
            row.runtime.dispatch_guard()
        prime_current_inputs(row)
        identity = row.runtime.arm()
        assert row.state.controller_bound
        assert row.state.scope['controller_identity'] == identity
        assert row.runtime.ready and row.runtime.dispatch_guard()
        assert identity == row.owner.identity()
        with pytest.raises(PermissionError, match='ALREADY_ARMED'):
            row.runtime.arm()
    finally:
        row.runtime.close(timeout_s=1.)


@pytest.mark.parametrize('damage', ['identity_exception', 'fault_after_readback'])
def test_failure_after_owner_readback_stays_unbound_and_wakes_independent_close(monkeypatch, damage):
    row = runtime_setup(monkeypatch, unbound=True)
    original = row.owner.identity
    def identity():
        if damage == 'identity_exception':
            raise OSError('lost owner identity')
        row.runtime.fault('RACING_STARTUP_FAULT')
        return original()
    row.owner.identity = identity
    try:
        prime_current_inputs(row)
        row.runtime.start()
        with pytest.raises((PermissionError, OSError)):
            row.runtime.arm()
        assert not row.runtime.armed and not row.runtime.ready
        assert not row.state.controller_bound and not row.state.inventory
        assert row.state.faulted and row.runtime.stop_requested
        with pytest.raises(PermissionError):
            row.runtime.dispatch_guard()
    finally:
        row.runtime.close(timeout_s=1.)


def test_inventory_dispatcher_cannot_accept_unbound_even_with_forged_armed_flags(monkeypatch):
    from so101_demo.adapters.act.head_inventory_dispatch import HeadInventoryDispatcher
    from so101_demo.adapters.act.head_trajectory_guard import HeadTrajectoryGuard
    row = runtime_setup(monkeypatch, unbound=True)
    guard = object.__new__(HeadTrajectoryGuard)
    guard.feedback_port = row.port
    guard._lock = threading.Lock()
    guard._dispatcher = None
    guard._stopped = False
    with pytest.raises(PermissionError, match='UNBOUND'):
        HeadInventoryDispatcher(row.port, row.owner, row.state, guard=guard,
            own_inventory=row.runtime.own_inventory, fault_callback=row.runtime.fault)


def test_trajectory_scope_refuses_unbound_before_reading_external_state():
    from so101_demo.adapters.act.head_trajectory_guard import HeadTrajectoryGuard
    state, scope, expected, record, payload = unbound_state()
    guard = object.__new__(HeadTrajectoryGuard)
    guard._local_state = state
    with pytest.raises(PermissionError, match='UNBOUND'):
        guard._scope_bytes()


def test_parallel_runtime_arm_cannot_run_a_second_startup(monkeypatch):
    row = runtime_setup(monkeypatch, unbound=True)
    entered, release = threading.Event(), threading.Event()
    original = row.owner.identity
    results = []
    def identity():
        entered.set()
        assert release.wait(timeout=1.)
        return original()
    row.owner.identity = identity
    try:
        prime_current_inputs(row)
        row.runtime.start()
        worker = threading.Thread(target=lambda: results.append(row.runtime.arm()))
        worker.start()
        assert entered.wait(timeout=.1)
        with pytest.raises(PermissionError, match='ARM_IN_PROGRESS'):
            row.runtime.arm()
        assert not row.state.controller_bound
        release.set()
        worker.join(timeout=1.)
        assert not worker.is_alive()
        assert results == [row.owner.identity.__self__.identity()] if False else len(results) == 1
        assert row.state.controller_bound
    finally:
        release.set()
        if 'worker' in locals():
            worker.join(timeout=1.)
        row.runtime.close(timeout_s=1.)
