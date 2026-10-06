"""Directed tests for the process-local stopped-demand runtime."""

import hashlib
import importlib
import importlib.util
import json
import threading
import time
import uuid
from types import SimpleNamespace

import pytest
from rosidl_runtime_py.convert import message_to_ordereddict

from so101_demo.act.head_evidence_identity import canonical_bytes
from so101_demo.adapters.act import ros_neck
from test_act_head_local_observer import (CAMERA_FRAME, clock_record, image_record, info_record,
                                          joint_record, local_state, observer_setup,
                                          simulation_policy, wait_for)
from test_act_head_prepared_sdk import prepared


def runtime_module():
    return importlib.import_module('so101_demo.adapters.act.head_local_runtime')


class Clock:
    """Wall stays in the builtin monotonic domain so fault origins and stop
    epochs agree; the simulated camera/clock stamp is advanced explicitly."""

    def __init__(self, sim=10.0):
        self.sim = sim

    @property
    def wall(self):
        return time.monotonic()

    def monotonic(self):
        return time.monotonic()


class Recorder:
    def __init__(self, *, fail=False, block=None):
        self.rows, self.fail, self.block = [], fail, block

    def __call__(self, kind, record, source_stamp_ns=None):
        if self.block is not None:
            self.block.wait(2.)
        if self.fail:
            raise OSError('writer queue is closed')
        self.rows.append((kind, record, source_stamp_ns))


class Revoker:
    def __init__(self, *, block=None):
        self.generation = 7
        self.native_owner = dict(uid=1000, pid=4242, start_ticks=99)
        self.transport_origin = dict(path='/tmp/native.so', sha256='b' * 64, abi=1,
                                     clock='CLOCK_MONOTONIC')
        self.block = block
        self.closed, self.close_wall_s = 0, []

    def close_strict(self):
        self.closed += 1
        self.close_wall_s.append(time.monotonic())
        if self.block is not None:
            self.block.wait(5.)
        return dict(request_wall_s=time.monotonic(), ack_wall_s=time.monotonic(),
                    ack_validated=True, generation=self.generation)

    def identity(self):
        return dict(generation=7, incarnation='inc-1', boot='boot-1',
                    request_wall_s=time.monotonic(), ack_wall_s=time.monotonic())


class Authority:
    def __init__(self, *, arm_guard, fault_callback, generation=7, session_id='session',
                 controller_identity=None):
        self.generation, self.session_id = generation, session_id
        self.native_owner = dict(uid=1000, pid=4242, start_ticks=99)
        self.arm_guard, self.fault_callback = arm_guard, fault_callback
        self.controller_identity = dict(controller_identity or dict(
            generation=7, incarnation='inc-1', boot='boot-1'))
        self._armed, self._identities, self.arm_calls = set(), {}, 0

    def arm(self, role):
        if self.arm_guard() is not True:
            raise PermissionError('HEAD_MAIN_ARM_PRECONDITION_REFUSED')
        self.arm_calls += 1
        self._armed.add(role)
        self._identities[role] = dict(self.controller_identity)
        return True

    def identity(self, role):
        if role not in self._armed:
            raise PermissionError('HEAD_MAIN_EXPLICIT_ARM_REQUIRED')
        return dict(self._identities[role])

    def close(self):
        self._armed.clear()
        return dict(ack_validated=True)


def runtime_setup(monkeypatch, *, clock=None, sink=None, block_cancel=None, block_close=None,
                  policy=None, unbound=False, native_policy_bound=True):
    policy = simulation_policy() if policy is None else policy
    clock = Clock() if clock is None else clock
    row = observer_setup(monkeypatch, policy=policy, clock=clock, bind_faults=False,
                         unbound=unbound)
    row.policy, row.clock = policy, clock
    row.sink = Recorder() if sink is None else sink
    row.revoker = Revoker(block=block_close)
    row.block_cancel = block_cancel
    module = runtime_module()
    row.runtime = module.HeadLocalRuntime(node=row.node, port=row.port, local_state=row.state,
        revoker=row.revoker, observer=row.observer, policy=policy, sink=row.sink,
        monotonic=clock.monotonic)
    row.authority = Authority(arm_guard=row.runtime.prearm_guard,
                              fault_callback=row.runtime.fault,
                              generation=row.state.scope['generation'],
                              session_id=row.state.scope['session_id'],
                              controller_identity=row.state.scope['controller_identity'])
    row.runtime.bind_authority(row.authority)
    if native_policy_bound:
        row.runtime.bind_native_policy_readback(native_policy_receipt(row.node, policy))
    return row


def native_policy_receipt(node, policy):
    """Directed fixture for the existing strict readonly receipt validator."""
    from so101_demo.act.head_evidence_identity import digest
    now = time.monotonic()
    return dict(remote_node='/neck_controller', reader_node=node.get_fully_qualified_name(),
                values=dict(head_simulation_mode=policy.mode,
                    head_fault_connection_timeout_ns=round(policy.native_close_timeout_s * 1e9),
                    head_measured_prefix_guard='quintic_measured_prefix_v1',
                    speed_scaling_input_enabled=False, read_only=True, dynamic_typing=False),
                simulation_policy_sha256=digest(policy.readback()), query_wall_s=now,
                completed_wall_s=now, deadline_wall_s=now + 5., motion_authority=False)


def test_runtime_retirement_keeps_originals_until_owned_stack_exits(monkeypatch):
    from so101_demo.adapters.act.head_execution_provider import _OwnedLocalROS
    row = runtime_setup(monkeypatch)
    prime_current_inputs(row)
    receipt = row.runtime.close(timeout_s=1., retire_originals=False)
    assert receipt['original_retirement'] == 'DEFERRED_TO_PROVIDER'
    # A producer still running during child teardown must retain its original.
    row.observer.observe_original('CLOCK', clock_record(row.clock, 10.02))
    assert row.observer.current_inputs(row.clock.monotonic())['clock']['source_ns'] == 10_020_000_000
    owned = _OwnedLocalROS()
    owned.retain_originals_until_close(row.runtime)
    owned.close()
    assert row.observer.closed is True
    assert row.runtime.retire_originals()['observer']['already_closed'] is True



def prime_current_inputs(row, *, sim=None, velocity=0.0):
    """Feed one advancing original of every kind plus one joint sample."""
    sim = getattr(row, 'prime_sim', 10.0) + .01 if sim is None else sim
    row.prime_sim = sim
    row.clock.sim = sim
    row.observer.observe_original('CLOCK', clock_record(row.clock, sim))
    row.observer.observe_original('IMAGE', image_record(row.clock, sim))
    row.observer.observe_original('INFO', info_record(row.clock, sim))
    message = ros_neck.JointState(name=['neck_yaw_joint'], position=[.2], velocity=[velocity])
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(round(sim * 1e9), 10**9)
    row.port._feedback(message)
    row.runtime.executor_progress()
    return message


def armed_runtime(row):
    prime_current_inputs(row)
    row.runtime.start()
    assert row.runtime.arm()['incarnation'] == 'inc-1'
    return row.runtime


def test_admission_joint_loss_refuses_even_when_independent_raw_stop_feedback_advances(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    original_sink = row.port._head_original_sink
    observed_before = row.observer.current_inputs(row.clock.monotonic())['joint']

    # Pause delivery to the admission observer only. The real shared port's
    # raw sample archive and physical Stop predicate continue to receive it.
    def paused_admission(kind, original):
        if kind != 'JOINT':
            return original_sink(kind, original)

    monkeypatch.setattr(row.port, '_head_original_sink', paused_admission)
    try:
        prime_current_inputs(row, sim=row.prime_sim + .06)
        current = row.port.feedback_snapshot()
        assert current['valid'] is True
        assert current['source_ns'] > observed_before['source_ns']
        assert row.observer.current_inputs(row.clock.monotonic())['joint'] == observed_before
        with pytest.raises(PermissionError, match='HEAD_LOCAL_RUNTIME_FEEDBACK_STALE'):
            runtime.dispatch_guard()
        assert runtime.faulted
        assert wait_for(lambda: row.port._stop_epoch is not None)
        original_deadline = runtime.stop_receipt()['stop_deadline_wall_s']
        for _ in range(4):
            prime_current_inputs(row)
            time.sleep(.025)
        receipt = runtime.finish_requested_stop()
        assert receipt['physical_stop_confirmed'] is True
        assert receipt['stop_deadline_wall_s'] == original_deadline
        assert row.port._head_stop_proof.count >= 3
        assert row.observer.current_inputs(row.clock.monotonic())['joint'] == observed_before
    finally:
        runtime.close(timeout_s=1.)


def inventory_record(row, message, goal_uuid, cdr):
    claim = time.monotonic_ns() - 1_000_000
    return dict(goal_uuid=str(uuid.UUID(bytes=bytes(goal_uuid.uuid))),
        typed_goal=json.loads(json.dumps(message_to_ordereddict(message))),
        payload_sha256=hashlib.sha256(cdr).hexdigest(), generation=7,
        controller_identity=dict(generation=7, incarnation='inc-1', boot='boot-1'),
        attempt_epoch=row.state.scope['epoch'], session_id=row.state.scope['session_id'],
        role='neck', operation_sequence=1, claim_monotonic_ns=claim,
        deadline_ns=claim + 400_000_000)


def test_admission_clock_loss_refuses_without_disabling_raw_stop_clock(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    original_observe = row.observer.observe_original
    original_clock = row.observer.current_inputs(row.clock.monotonic())['clock']

    def paused_clock(kind, original):
        if kind != 'CLOCK':
            return original_observe(kind, original)

    monkeypatch.setattr(row.observer, 'observe_original', paused_clock)
    try:
        # The ROS node clock and original JOINT/paired camera streams still
        # advance; only admission's original CLOCK delivery is paused.
        until = original_clock['wall_s'] + row.port.feedback_policy.clock_interarrival_deadline_s
        while time.monotonic() <= until:
            prime_current_inputs(row)
            time.sleep(.01)
        prime_current_inputs(row)
        assert row.port.feedback_snapshot()['valid'] is True
        assert row.observer.current_inputs(row.clock.monotonic())['clock'] == original_clock
        with pytest.raises(PermissionError, match='HEAD_LOCAL_RUNTIME_CLOCK_STALE'):
            runtime.dispatch_guard()
        assert runtime.faulted
        assert wait_for(lambda: row.port._stop_epoch is not None)
        original_deadline = runtime.stop_receipt()['stop_deadline_wall_s']
        for _ in range(4):
            prime_current_inputs(row)
            time.sleep(.025)
        assert runtime.finish_requested_stop()['physical_stop_confirmed'] is True
        assert runtime.stop_receipt()['stop_deadline_wall_s'] == original_deadline
        assert row.port._head_stop_proof.count >= 3
    finally:
        runtime.close(timeout_s=1.)


def test_admission_uses_received_causal_joint_when_latest_original_precedes_ros_clock_update(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    try:
        causal = row.port.feedback_snapshot()
        message = ros_neck.JointState(name=['neck_yaw_joint'], position=[.2], velocity=[0.])
        future_source_ns = causal['source_ns'] + 2_000_000
        message.header.stamp.sec, message.header.stamp.nanosec = divmod(future_source_ns, 10**9)
        row.port._feedback(message)
        # Both original JOINTs were delivered. The node TimeSource callback
        # has not caught up yet; existing port policy selects the older one.
        assert row.observer.current_inputs(row.clock.monotonic())['joint']['source_ns'] == future_source_ns
        assert row.port.feedback_snapshot()['source_ns'] == causal['source_ns']
        assert runtime.dispatch_guard() is True
        assert runtime.faulted is False
    finally:
        runtime.close(timeout_s=1.)


def test_local_runtime_is_a_real_component_api():
    spec = importlib.util.find_spec("so101_demo.adapters.act.head_local_runtime")
    assert spec is not None, "HeadLocalRuntime component module must exist"
    module = __import__("so101_demo.adapters.act.head_local_runtime", fromlist=["HeadLocalRuntime"])
    assert callable(getattr(module, "HeadLocalRuntime", None))


def test_runtime_exports_its_local_admission_and_stop_contract():
    spec = importlib.util.find_spec("so101_demo.adapters.act.head_local_runtime")
    assert spec is not None, "HeadLocalRuntime component module must exist"
    module = __import__("so101_demo.adapters.act.head_local_runtime", fromlist=["HeadLocalRuntime"])
    runtime = module.HeadLocalRuntime
    for name in ("dispatch_guard", "own_inventory", "fault", "stop", "close", "start"):
        assert callable(getattr(runtime, name, None)), name


def test_runtime_owns_the_shared_local_state_and_allocates_no_second_stack(monkeypatch):
    row = runtime_setup(monkeypatch)
    created = [entry for entry in row.calls if entry[0] == 'action_client']
    assert len(created) == 1
    assert len([entry for entry in row.subscriptions if entry[1] == '/joint_states']) == 1
    assert row.runtime.started is False and row.runtime.armed is False
    assert row.port._head_fault_callback == row.runtime.fault
    with pytest.raises((TypeError, ValueError, PermissionError)):
        runtime_module().HeadLocalRuntime(node=row.node, port=row.port, local_state=object(),
            revoker=row.revoker, observer=row.observer, policy=row.policy, sink=row.sink)
    with pytest.raises((TypeError, ValueError, PermissionError)):
        runtime_module().HeadLocalRuntime(node=row.node, port=row.port, local_state=row.state,
            revoker=row.revoker, observer=row.observer, policy=simulation_policy(
                search_timeout_s=29.), sink=row.sink)


def test_runtime_start_is_explicit_once_and_constructor_does_not_arm(monkeypatch):
    row = runtime_setup(monkeypatch)
    assert row.authority.arm_calls == 0 and row.runtime.armed is False
    assert row.runtime.started is False
    receipt = row.runtime.start()
    assert receipt['watchdog_started'] is True
    assert sorted(receipt['workers']) == ['cancel_stop', 'native_close']
    assert row.runtime.started is True
    with pytest.raises(PermissionError):
        row.runtime.start()
    with pytest.raises(PermissionError):
        row.runtime.dispatch_guard()
    row.runtime.close(timeout_s=1.)


def test_arm_requires_current_originals_quiet_feedback_and_matching_identity(monkeypatch):
    row = runtime_setup(monkeypatch)
    row.runtime.start()
    with pytest.raises((PermissionError, ValueError)):
        row.runtime.arm()
    assert row.runtime.armed is False and row.authority.arm_calls == 0
    prime_current_inputs(row, velocity=.5)
    with pytest.raises((PermissionError, ValueError)):
        row.runtime.arm()
    assert row.runtime.armed is False
    prime_current_inputs(row)
    assert row.runtime.arm()['boot'] == 'boot-1'
    assert row.runtime.armed is True
    assert row.authority.arm_calls == 1
    row.runtime.close(timeout_s=1.)


def test_dispatch_guard_consumes_current_originals_and_refuses_stale_ones(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    assert runtime.dispatch_guard() is True
    row.clock.sim = 11.0
    with pytest.raises((PermissionError, ValueError)):
        runtime.dispatch_guard()
    assert row.state.faulted is True
    with pytest.raises((PermissionError, ValueError)):
        runtime.dispatch_guard()
    runtime.close(timeout_s=1.)


def test_invalid_original_latches_first_fault_before_a_blocked_sink_and_still_stops(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    release = threading.Event()
    row.sink.block = release
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault('receipt', runtime.fault(
        'HEAD_LOCAL_TEST_FAULT')))
    thread.start()
    assert wait_for(lambda: row.state.faulted)
    assert row.state.fault_occurrence_ns is not None
    assert wait_for(lambda: row.revoker.closed == 1)
    assert result == {}
    release.set()
    thread.join(2.)
    assert result['receipt']['reason'] == 'HEAD_LOCAL_TEST_FAULT'
    assert result['receipt']['occurred_ns'] == row.state.fault_occurrence_ns
    assert any(kind == 'FAULT' for kind, _, _ in row.sink.rows)
    runtime.close(timeout_s=1.)


def test_blocked_native_close_does_not_block_cancel_or_raw_stop(monkeypatch):
    close_block = threading.Event()
    row = runtime_setup(monkeypatch, block_close=close_block)
    runtime = armed_runtime(row)
    with row.port._lock:
        row.port._goals[str(uuid.uuid4())] = dict(accepted=None, handle=None, result=None,
            cancel_requested=False, cancel_ack=False, error=None, goal={})
    runtime.fault('HEAD_LOCAL_TEST_NATIVE_BLOCKED')
    assert wait_for(lambda: row.revoker.closed == 1)
    assert wait_for(lambda: any(entry[0] == 'cancel_goal' for entry in row.calls))
    assert row.port._stop_epoch is not None
    assert row.port._stop_epoch['fault_wall_s'] == pytest.approx(
        row.state.fault_occurrence_ns * 1e-9, abs=1e-6)
    close_block.set()
    assert wait_for(lambda: runtime.retirement_snapshot()['native_close']['ack'])
    runtime.close(timeout_s=1.)


def test_blocked_cancel_does_not_block_native_close_ack(monkeypatch):
    cancel_block = threading.Event()
    row = runtime_setup(monkeypatch, block_cancel=cancel_block)
    runtime = armed_runtime(row)
    row.clients['cancel_goal'].block = cancel_block
    with row.port._lock:
        row.port._goals[str(uuid.uuid4())] = dict(accepted=None, handle=None, result=None,
            cancel_requested=False, cancel_ack=False, error=None, goal={})
    runtime.fault('HEAD_LOCAL_TEST_CANCEL_BLOCKED')
    assert wait_for(lambda: row.revoker.closed == 1)
    assert wait_for(lambda: runtime.retirement_snapshot()['native_close']['ack'])
    assert runtime.retirement_snapshot()['cancel_stop']['finished'] is False
    cancel_block.set()
    runtime.close(timeout_s=1.)


def test_repeated_stop_and_later_fault_never_renew_the_original_origin(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    first = runtime.stop('success')
    origin = first['stop_origin_wall_s']
    time.sleep(.02)
    runtime.stop('not_found')
    runtime.fault('HEAD_LOCAL_TEST_LATE_FAULT')
    receipt = runtime.stop_receipt()
    assert receipt['stop_origin_wall_s'] == origin
    assert row.port._stop_epoch['fault_wall_s'] == pytest.approx(origin, abs=1e-9)
    assert receipt['stop_deadline_wall_s'] == pytest.approx(
        origin + row.policy.stop_confirmation_timeout_s, abs=1e-9)
    runtime.close(timeout_s=1.)


def test_watchdog_detects_a_direct_local_state_latch_and_starts_the_real_stop(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    token = row.state.latch_fault('HEAD_LOCAL_DISPATCH_DIRECT_FAULT')
    assert token is not None
    assert wait_for(lambda: runtime.faulted, timeout_s=1.)
    assert wait_for(lambda: row.revoker.closed == 1)
    assert runtime.fault_receipt()['occurred_ns'] == row.state.fault_occurrence_ns
    assert row.port._stop_epoch['fault_wall_s'] == pytest.approx(
        row.state.fault_occurrence_ns * 1e-9, abs=1e-6)
    assert runtime.dispatch_guard_refused_reason is not None
    runtime.close(timeout_s=1.)


def test_writer_enqueue_failure_latches_fault_and_still_stops(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    row.sink.fail = True
    with pytest.raises(PermissionError):
        runtime.record('TEST_RECORD', dict(value=1))
    assert row.state.faulted is True
    assert row.state.snapshot['fault']['reason'] == 'HEAD_LOCAL_WRITER_ENQUEUE_FAILED'
    assert wait_for(lambda: row.revoker.closed == 1)
    runtime.close(timeout_s=1.)


def test_persistent_writer_failure_reports_once_and_preserves_stop_origin(monkeypatch):
    entry = threading.get_ident()
    calls = []
    sink = Recorder()

    def counting_sink(*args):
        if sink.fail:
            calls.append(threading.get_ident())
        return sink(*args)

    row = runtime_setup(monkeypatch, sink=counting_sink)
    runtime = armed_runtime(row)
    try:
        sink.fail = True
        with pytest.raises(PermissionError, match='HEAD_LOCAL_WRITER_ENQUEUE_FAILED'):
            runtime.record('TEST_RECORD', dict(value=1))
        origin = runtime.stop_receipt()['stop_origin_wall_s']
        occurrence = runtime.fault_receipt()['occurred_ns']
        assert runtime._stop_event.is_set()
        assert calls.count(entry) <= 2
        for _ in range(10):
            runtime.fault('LATER_FAULT')
        assert calls.count(entry) <= 2
        assert runtime.stop_receipt()['stop_origin_wall_s'] == origin
        assert runtime.fault_receipt()['occurred_ns'] == occurrence
        assert wait_for(lambda: row.revoker.closed == 1)
    finally:
        assert runtime.close(timeout_s=1.)['retired'] is True


def test_close_reports_unquiesced_worker_instead_of_claiming_retirement(monkeypatch):
    close_block = threading.Event()
    row = runtime_setup(monkeypatch, block_close=close_block)
    runtime = armed_runtime(row)
    runtime.fault('HEAD_LOCAL_TEST_UNQUIESCED')
    receipt = runtime.close(timeout_s=.05)
    assert receipt['retired'] is False
    assert receipt['unquiesced'] == ['native_close']
    assert receipt['confirmed_stop'] is False
    close_block.set()
    assert wait_for(lambda: runtime.retirement_snapshot()['native_close']['ack'], timeout_s=2.)
    final = runtime.close(timeout_s=1.)
    assert final['retired'] is True


def test_own_inventory_requires_the_existing_local_record_and_never_reregisters(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    message, goal_uuid, cdr = prepared()
    record = inventory_record(row, message, goal_uuid, cdr)
    row.state.register_prepared(record, cdr)
    assert runtime.own_inventory(record, cdr) is True
    gid = record['goal_uuid']
    assert gid in row.port._goals and row.port.accepted(gid) is None
    assert list(row.state.inventory) == [gid]
    owner = row.port._goals[gid]
    with pytest.raises((PermissionError, ValueError)):
        runtime.own_inventory(record, cdr)
    assert row.port._goals[gid] is owner and list(row.state.inventory) == [gid]
    with pytest.raises((PermissionError, ValueError)):
        runtime.own_inventory(dict(record, payload_sha256='c' * 64), cdr)
    assert list(row.state.inventory) == [gid]
    row.port.close_head_io(timeout_s=1.)
    runtime.close(timeout_s=1.)


def test_hard_fault_preserves_the_complete_inventory_and_refuses_admission(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row)
    message, goal_uuid, cdr = prepared()
    record = inventory_record(row, message, goal_uuid, cdr)
    row.state.register_prepared(record, cdr)
    runtime.own_inventory(record, cdr)
    before = canonical_bytes(row.state.inventory)
    runtime.fault('HEAD_LOCAL_TEST_INVENTORY_PRESERVED')
    assert canonical_bytes(row.state.inventory) == before
    with pytest.raises((PermissionError, ValueError)):
        runtime.dispatch_guard()
    with pytest.raises((PermissionError, ValueError)):
        runtime.own_inventory(record, cdr)
    assert canonical_bytes(row.state.inventory) == before
    row.port.close_head_io(timeout_s=1.)
    runtime.close(timeout_s=1.)
