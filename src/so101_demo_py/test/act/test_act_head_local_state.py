"""Local Head inventory claims stay bound to one attempt and fixed deadline."""

import hashlib
import json
import threading
import uuid

import pytest

from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import serialize_message
from rosidl_runtime_py.convert import message_to_ordereddict

from so101_demo.act.head_evidence_identity import canonical_bytes


def prepared():
    scope = {'epoch': 'attempt-' + uuid.uuid4().hex, 'generation': 11,
        'session_id': 'head-search-restarts', 'policy_sha256': 'a' * 64,
        'controller_identity': {'generation': 11, 'incarnation': 'ctrl', 'boot': 'boot'}}
    message = FollowJointTrajectory.Goal()
    message.trajectory.joint_names = ['neck_yaw_joint']
    payload = serialize_message(message)
    record = {'goal_uuid': str(uuid.uuid4()),
        'typed_goal': json.loads(canonical_bytes(message_to_ordereddict(message))),
        'payload_sha256': hashlib.sha256(payload).hexdigest(), 'generation': 11,
        'controller_identity': dict(scope['controller_identity']),
        'attempt_epoch': scope['epoch'], 'session_id': scope['session_id'], 'role': 'neck',
        'operation_sequence': 1, 'claim_monotonic_ns': 100,
        'deadline_ns': 400_000_100}
    return scope, record, payload


def local_state(scope, clock_ns=lambda: 100):
    module = __import__('so101_demo.act.head_local_state', fromlist=['HeadLocalState'])
    return module.HeadLocalState(scope=scope, search_deadline_ns=5_000_000_000, clock_ns=clock_ns)


def test_local_state_api_is_available_without_monitor_transport():
    from so101_demo.act.head_local_state import HeadLocalState
    assert callable(HeadLocalState)


def test_local_state_keeps_possibly_sent_inventory_and_original_deadline():
    scope, record, payload = prepared()
    state = local_state(scope)
    state.register_prepared(record, payload)
    state.mark_reserve_attempt(record['goal_uuid'], 150)
    state.mark_reserved(record['goal_uuid'], 175)
    state.mark_sdk_attempt(record['goal_uuid'], 200)
    assert state.claim_state(record['goal_uuid'], 400_000_100) is False
    row = state.inventory[record['goal_uuid']]
    assert row['deadline_ns'] == 400_000_100
    assert row['sdk_attempt_ns'] == 200
    assert state.snapshot['motion_epoch'] == 0
    with pytest.raises(PermissionError): state.register_prepared(dict(record, operation_sequence=2), payload)


@pytest.mark.parametrize('field,value', [
    ('goal_uuid', 'not-a-uuid'),
    ('payload_sha256', 'f' * 64), ('generation', 12),
    ('controller_incarnation', 'other-controller'), ('controller_boot', 'other-boot'),
    ('role', 'wrist'), ('attempt_epoch', 'other-attempt'),
])
def test_local_state_rejects_wrong_prepared_identity_before_inventory(field, value):
    scope, record, payload = prepared()
    damaged = dict(record)
    if field in ('controller_incarnation', 'controller_boot'):
        damaged['controller_identity'] = dict(record['controller_identity'])
        key = 'incarnation' if field == 'controller_incarnation' else 'boot'
        damaged['controller_identity'][key] = value
    else:
        damaged[field] = value
    state = local_state(scope)
    with pytest.raises((ValueError, PermissionError)):
        state.register_prepared(damaged, payload)
    assert not state.inventory


def test_local_state_rejects_scope_reuse_while_original_owner_is_live():
    scope, record, payload = prepared()
    first = local_state(scope)
    with pytest.raises(ValueError, match='SCOPE_REUSED'):
        local_state(scope)
    first.register_prepared(record, payload)


def test_reservation_and_sdk_attempts_are_single_ordered_events():
    scope, record, payload = prepared()
    state = local_state(scope)
    state.register_prepared(record, payload)
    gid = record['goal_uuid']
    state.mark_reserve_attempt(gid, 150)
    with pytest.raises(PermissionError): state.mark_reserve_attempt(gid, 151)
    state.mark_reserved(gid, 160)
    with pytest.raises(PermissionError): state.mark_reserved(gid, 170)
    state.mark_sdk_attempt(gid, 200)
    with pytest.raises(PermissionError): state.mark_sdk_attempt(gid, 210)


def test_claim_boundary_refuses_without_erasing_or_extending_inventory():
    scope, record, payload = prepared()
    state = local_state(scope)
    state.register_prepared(record, payload)
    gid = record['goal_uuid']
    assert state.claim_state(gid, 400_000_099) is True
    assert state.claim_state(gid, 400_000_100) is False
    assert state.claim_state(gid, 500_000_000) is False
    assert state.inventory[gid]['deadline_ns'] == 400_000_100


def test_prepared_cdr_is_readable_after_fault_but_inventory_mutations_stay_closed():
    scope, record, payload = prepared()
    state = local_state(scope)
    state.register_prepared(record, payload)
    state.mark_reserve_attempt(record['goal_uuid'], 150)
    state.fault('STOP_REQUIRED', {'stage': 'send'})

    assert state.fault_occurrence_ns == state.snapshot['fault']['occurred_ns']
    assert state.fault_occurrence_ns is not None
    assert state.prepared_cdr(record['goal_uuid']) == payload
    with pytest.raises(PermissionError, match='FAULTED'):
        state.mark_reserve_attempt(record['goal_uuid'], 201)
    with pytest.raises(PermissionError, match='FAULTED'):
        state.register_prepared(dict(record, goal_uuid=str(uuid.uuid4())), payload)


def test_fault_latches_before_diagnostics_and_never_calls_custom_copy_hooks():
    scope, _, _ = prepared()
    holder = {}
    clock_calls = []

    def clock():
        assert not holder['state']._lock.locked()
        clock_calls.append('clock')
        return 77

    state = local_state(scope, clock_ns=clock)
    holder['state'] = state

    class Hostile:
        def __deepcopy__(self, memo):
            raise AssertionError('arbitrary deepcopy hook ran')

    with pytest.raises(ValueError):
        state.fault('FIRST_FAULT', {'hostile': Hostile()})
    assert state.faulted
    assert clock_calls == []
    assert state.snapshot['fault']['reason'] == 'FIRST_FAULT'
    assert state.snapshot['fault']['occurred_ns'] == state.fault_occurrence_ns
    assert state.fault('SECOND_FAULT', {'ignored': True})['reason'] == 'FIRST_FAULT'


def test_fault_clock_and_record_serialization_run_outside_state_lock(monkeypatch):
    scope, record, payload = prepared()
    state = local_state(scope)
    state.register_prepared(record, payload)
    clock_checked = []

    def clock():
        assert not state._lock.locked()
        clock_checked.append(True)
        return 88

    state.clock_ns = clock
    state.fault('LOCK_BOUNDARY', {'stage': 'test'})
    assert clock_checked == []
    assert state.fault_occurrence_ns == state.snapshot['fault']['occurred_ns']

    module = __import__('so101_demo.act.head_local_state', fromlist=['canonical_bytes'])
    original = module.canonical_bytes

    def canonical_outside_lock(value):
        assert not state._lock.locked()
        return original(value)

    monkeypatch.setattr(module, 'canonical_bytes', canonical_outside_lock)
    scope2, record2, payload2 = prepared()
    state2 = local_state(scope2)
    state2.register_prepared(record2, payload2)
    state2.mark_reserve_attempt(record2['goal_uuid'], 150)


def test_fault_origin_and_pending_snapshot_precede_blocked_diagnostics(monkeypatch):
    from so101_demo.act import head_local_state as module

    scope, _, _ = prepared()
    origin_ns = 8_765_432_100
    monkeypatch.setattr(module.time, 'monotonic_ns', lambda: origin_ns)
    state = local_state(scope, clock_ns=lambda: (_ for _ in ()).throw(
        AssertionError('claim clock used for fault timing')))
    token = state.latch_fault('FIRST_FAULT')
    assert token is not None
    assert getattr(state, 'fault_occurrence_ns', None) == origin_ns
    assert state.snapshot['fault'] == {
        'reason': 'FIRST_FAULT', 'evidence': None, 'occurred_ns': origin_ns}
    assert state.latch_fault('SECOND_FAULT') is None
    assert state.snapshot['fault']['reason'] == 'FIRST_FAULT'
    assert state.fault_occurrence_ns == origin_ns

    entered = threading.Event()
    release = threading.Event()
    finished = []
    original_bounded_payload = module.bounded_payload

    def blocked_payload(evidence):
        entered.set()
        assert release.wait(timeout=2.)
        return original_bounded_payload(evidence)

    monkeypatch.setattr(module, 'bounded_payload', blocked_payload)
    worker = threading.Thread(target=lambda: finished.append(
        state.finish_fault(token, {'detail': 'bounded'})))
    worker.start()
    try:
        assert entered.wait(timeout=1.)
        assert state.fault_occurrence_ns == origin_ns
        assert state.snapshot['fault']['occurred_ns'] == origin_ns
    finally:
        release.set()
        worker.join(timeout=2.)
    assert not worker.is_alive()
    assert finished[0]['occurred_ns'] == origin_ns
    assert state.snapshot['fault']['reason'] == 'FIRST_FAULT'
    assert state.snapshot['fault']['occurred_ns'] == origin_ns


def test_fault_diagnostic_token_is_consumed_before_reentrant_serialization(monkeypatch):
    from so101_demo.act import head_local_state as module

    scope, _, _ = prepared()
    state = local_state(scope)
    token = state.latch_fault('FIRST_FAULT')
    assert token is not None
    original_bounded_payload = module.bounded_payload
    calls = []
    entered = threading.Event()
    release = threading.Event()
    finished = []

    def reentrant_payload(evidence):
        calls.append(evidence)
        if len(calls) == 1:
            nested = state.finish_fault(token, {'nested': True})
            assert nested['reason'] == 'FIRST_FAULT'
            entered.set()
            assert release.wait(timeout=2.)
        return original_bounded_payload(evidence)

    monkeypatch.setattr(module, 'bounded_payload', reentrant_payload)
    worker = threading.Thread(target=lambda: finished.append(
        state.finish_fault(token, {'detail': 'first'})))
    worker.start()
    try:
        assert entered.wait(timeout=1.)
        concurrent = state.finish_fault(token, {'concurrent': True})
        assert concurrent['reason'] == 'FIRST_FAULT'
        assert len(calls) == 1
        assert concurrent['occurred_ns'] == getattr(state, 'fault_occurrence_ns', None)
        assert state.snapshot['fault']['evidence'] is None
    finally:
        release.set()
        worker.join(timeout=2.)
    assert not worker.is_alive()
    assert len(calls) == 1
    assert len(finished) == 1
    result = finished[0]
    assert result['evidence'] == {'detail': 'first'}
    assert state.snapshot['fault']['evidence'] == {'detail': 'first'}
    assert state.snapshot['fault']['occurred_ns'] == state.fault_occurrence_ns


def test_foreign_fault_diagnostic_token_does_not_run_serializer(monkeypatch):
    from so101_demo.act import head_local_state as module

    scope, _, _ = prepared()
    state = local_state(scope)
    token = state.latch_fault('FIRST_FAULT')
    assert token is not None
    calls = []
    original_bounded_payload = module.bounded_payload

    def recording_payload(evidence):
        calls.append(evidence)
        return original_bounded_payload(evidence)

    monkeypatch.setattr(module, 'bounded_payload', recording_payload)
    foreign = state.finish_fault(object(), {'foreign': True})
    assert foreign['reason'] == 'FIRST_FAULT'
    assert calls == []


def test_failed_fault_diagnostic_token_cannot_retry_or_renew(monkeypatch):
    from so101_demo.act import head_local_state as module

    scope, _, _ = prepared()
    state = local_state(scope)
    token = state.latch_fault('FIRST_FAULT')
    assert token is not None
    calls = []

    def failing_payload(evidence):
        calls.append(evidence)
        raise ValueError('diagnostics unavailable')

    monkeypatch.setattr(module, 'bounded_payload', failing_payload)
    with pytest.raises(ValueError, match='diagnostics unavailable'):
        state.finish_fault(token, {'first': True})
    assert len(calls) == 1
    retained = state.finish_fault(token, {'retry': True})
    assert len(calls) == 1
    assert retained['reason'] == 'FIRST_FAULT'
    assert retained['occurred_ns'] == state.fault_occurrence_ns


@pytest.mark.parametrize('field,value', [
    ('generation', True),
    ('goal_uuid', 'not-a-uuid'),
    ('payload_sha256', 'f' * 64),
    ('claim_monotonic_ns', 0),
    ('claim_monotonic_ns', 2**63),
    ('deadline_ns', 2**63),
    ('deadline_ns', 400_000_099),
])
def test_invalid_prepared_claim_is_sticky_and_preserves_existing_inventory(field, value):
    scope, record, payload = prepared()
    state = local_state(scope)
    state.register_prepared(record, payload)
    bad = dict(record, goal_uuid=str(uuid.uuid4()), operation_sequence=2)
    bad[field] = value

    with pytest.raises((ValueError, PermissionError)):
        state.register_prepared(bad, payload)
    assert state.faulted
    assert set(state.inventory) == {record['goal_uuid']}
    assert state.fault_occurrence_ns == state.snapshot['fault']['occurred_ns']
    assert state.fault_occurrence_ns is not None
    assert state.prepared_cdr(record['goal_uuid']) == payload


@pytest.mark.parametrize('mode', [2, 1])
def test_first_sequence_and_sequence_gaps_fault_without_erasing_inventory(mode):
    scope, record, payload = prepared()
    state = local_state(scope)
    if mode == 1:
        record['operation_sequence'] = 2
        first = dict(record, goal_uuid=str(uuid.uuid4()), operation_sequence=1)
        state.register_prepared(first, payload)
        record['operation_sequence'] = 3
    else:
        record['operation_sequence'] = 2

    with pytest.raises(PermissionError):
        state.register_prepared(record, payload)
    assert state.faulted
    assert set(state.inventory) == ({first['goal_uuid']} if mode == 1 else set())
    assert state.fault_occurrence_ns == state.snapshot['fault']['occurred_ns']
    assert state.fault_occurrence_ns is not None
    if mode == 1:
        assert state.prepared_cdr(first['goal_uuid']) == payload


def test_search_deadline_is_read_only():
    scope, _, _ = prepared()
    state = local_state(scope)
    with pytest.raises(AttributeError):
        state.search_deadline_ns = 10_000_000_000
