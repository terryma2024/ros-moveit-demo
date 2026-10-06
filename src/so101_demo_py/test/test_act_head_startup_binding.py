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


def test_guarded_runtime_binds_matching_native_channels_then_allows_dispatch(monkeypatch):
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
        assert row.authority.arm_calls == 1
        with pytest.raises(PermissionError, match='ALREADY_ARMED'):
            row.runtime.arm()
        assert row.authority.arm_calls == 1
    finally:
        row.runtime.close(timeout_s=1.)


@pytest.mark.parametrize('damage', ['primary', 'identity_exception', 'fault_after_readback'])
def test_failure_after_native_arm_stays_unbound_and_wakes_independent_close(monkeypatch, damage):
    row = runtime_setup(monkeypatch, unbound=True)
    def identity():
        if damage == 'identity_exception':
            raise OSError('lost primary identity reply')
        result = dict(generation=7, incarnation='inc-1', boot='boot-1')
        if damage == 'primary':
            result['boot'] = 'foreign'
        else:
            row.runtime.fault('RACING_STARTUP_FAULT')
        return result
    row.revoker.identity = identity
    try:
        prime_current_inputs(row)
        row.runtime.start()
        with pytest.raises((PermissionError, OSError)):
            row.runtime.arm()
        assert row.authority.arm_calls == 1
        assert not row.runtime.armed and not row.runtime.ready
        assert not row.state.controller_bound and not row.state.inventory
        assert row.state.faulted and row.runtime.stop_requested
        assert wait_for(lambda: row.revoker.closed == 1)
        with pytest.raises(PermissionError):
            row.runtime.dispatch_guard()
    finally:
        row.runtime.close(timeout_s=1.)


def test_inventory_dispatcher_cannot_accept_unbound_even_with_forged_armed_flags(monkeypatch):
    from so101_demo.adapters.act.head_inventory_dispatch import HeadInventoryDispatcher
    from so101_demo.adapters.act.head_trajectory_guard import HeadTrajectoryGuard
    row = runtime_setup(monkeypatch, unbound=True)
    row.authority._armed.add('neck')
    row.authority._identities['neck'] = None
    guard = object.__new__(HeadTrajectoryGuard)
    guard.feedback_port = row.port
    guard._lock = threading.Lock()
    guard._dispatcher = None
    guard._stopped = False
    with pytest.raises(PermissionError, match='UNBOUND'):
        HeadInventoryDispatcher(row.port, row.authority, row.state, guard=guard,
            own_inventory=row.runtime.own_inventory, fault_callback=row.runtime.fault)


def test_trajectory_scope_refuses_unbound_before_reading_external_state():
    from so101_demo.adapters.act.head_trajectory_guard import HeadTrajectoryGuard
    state, scope, expected, record, payload = unbound_state()
    guard = object.__new__(HeadTrajectoryGuard)
    guard._local_state = state
    with pytest.raises(PermissionError, match='UNBOUND'):
        guard._scope_bytes()


def test_prearm_requires_verified_native_readonly_policy_before_arm(monkeypatch):
    row = runtime_setup(monkeypatch, unbound=True, native_policy_bound=False)
    try:
        prime_current_inputs(row)
        row.runtime.start()
        with pytest.raises(PermissionError, match='HEAD_LOCAL_RUNTIME_NATIVE_POLICY_REQUIRED'):
            row.runtime.arm()
        assert not row.state.controller_bound and row.authority.arm_calls == 0
    finally:
        row.runtime.close(timeout_s=1.)


@pytest.mark.parametrize('damage', ['reader', 'digest', 'readonly', 'timeout', 'prefix'])
def test_invalid_native_policy_receipt_cannot_grant_arm(monkeypatch, damage):
    from test_act_head_local_runtime import native_policy_receipt
    row = runtime_setup(monkeypatch, unbound=True, native_policy_bound=False)
    receipt = native_policy_receipt(row.node, row.policy)
    if damage == 'reader':
        receipt['reader_node'] = '/foreign_reader'
    elif damage == 'digest':
        receipt['simulation_policy_sha256'] = '0' * 64
    elif damage == 'readonly':
        receipt['values']['read_only'] = False
    elif damage == 'timeout':
        receipt['values']['head_fault_connection_timeout_ns'] += 1
    else:
        receipt['values']['head_measured_prefix_guard'] = 'position_only'
    with pytest.raises(PermissionError, match='HEAD_NATIVE_POLICY_RECEIPT_INVALID'):
        row.runtime.bind_native_policy_readback(receipt)
    assert row.authority.arm_calls == 0 and not row.state.controller_bound


def test_native_policy_binding_is_immutable_and_cannot_be_replaced(monkeypatch):
    from test_act_head_local_runtime import native_policy_receipt
    row = runtime_setup(monkeypatch, unbound=True, native_policy_bound=False)
    receipt = native_policy_receipt(row.node, row.policy)
    try:
        row.runtime.bind_native_policy_readback(receipt)
        with pytest.raises(PermissionError, match='NATIVE_POLICY_REBOUND'):
            row.runtime.bind_native_policy_readback(receipt)
        receipt['values']['read_only'] = False
        prime_current_inputs(row)
        row.runtime.start()
        assert row.runtime.arm()['boot'] == 'boot-1'
    finally:
        row.runtime.close(timeout_s=1.)


def test_parallel_runtime_arm_cannot_issue_a_second_native_arm(monkeypatch):
    row = runtime_setup(monkeypatch, unbound=True)
    entered, release = threading.Event(), threading.Event()
    original = row.authority.identity
    results = []
    def identity(role):
        entered.set()
        assert release.wait(timeout=1.)
        return original(role)
    row.authority.identity = identity
    try:
        prime_current_inputs(row)
        row.runtime.start()
        worker = threading.Thread(target=lambda: results.append(row.runtime.arm()))
        worker.start()
        assert entered.wait(timeout=.1)
        with pytest.raises(PermissionError, match='ARM_IN_PROGRESS'):
            row.runtime.arm()
        assert row.authority.arm_calls == 1 and not row.state.controller_bound
        release.set()
        worker.join(timeout=1.)
        assert not worker.is_alive()
        assert results == [dict(generation=7, incarnation='inc-1', boot='boot-1')]
        assert row.state.controller_bound
    finally:
        release.set()
        if 'worker' in locals():
            worker.join(timeout=1.)
        row.runtime.close(timeout_s=1.)
