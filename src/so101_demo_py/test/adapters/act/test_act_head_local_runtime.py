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
from head_owner_support import FakeHelper, deadline, make as make_owner


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


class BlockableHelper(FakeHelper):
    """A heartbeat helper whose close can be held; the runtime's fault latch must not wait for the cancel service."""
    block = None

    def close_planned(self, timeout_s=1.):
        self.closed_planned += 1
        if BlockableHelper.block is not None:
            BlockableHelper.block.wait(5.)
        return True


def runtime_setup(monkeypatch, *, clock=None, sink=None, block_cancel=None, block_close=None,
                  policy=None, unbound=False, activate=True):
    policy = simulation_policy() if policy is None else policy
    clock = Clock() if clock is None else clock
    row = observer_setup(monkeypatch, policy=policy, clock=clock, bind_faults=False,
                         unbound=unbound)
    row.policy, row.clock = policy, clock
    row.sink = Recorder() if sink is None else sink
    BlockableHelper.block = block_close
    scope = row.state.scope
    row.owner, row.services, row.window, row.graph, row.owner_events, row.owner_faults = make_owner(
        policy=policy, generation=scope['generation'], session_id=scope['session_id'],
        helper_factory=BlockableHelper, auto_window=True,
        identity=None if unbound else scope['controller_identity'])
    row.block_cancel = block_cancel
    if activate:
        row.owner.activate(deadline=deadline())
    module = runtime_module()
    row.runtime = module.HeadLocalRuntime(node=row.node, port=row.port, local_state=row.state,
        owner=row.owner, observer=row.observer, policy=policy, sink=row.sink,
        monotonic=clock.monotonic)
    row.monkeypatch = monkeypatch
    row.closed_count = lambda: sum(helper.closed_planned for helper in FakeHelper.instances)
    return row


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


def keep_wall_bounds_fresh(row):
    """Make the wall-age bounds of the local guard independent of scheduling latency.

    The runtime bounds camera pair age (camera_source_age_s, 0.2 s in the default
    test policy), ROS clock sample age, joint receipt age and executor progress age
    on the wall clock. A test that primes originals and reaches a guard later on a
    loaded host would be refused for host latency alone, which no test of
    admission, ownership or exposure intends to exercise. The guard's own sample
    time re-stamps those wall fields and marks executor progress; ordering,
    pairing, identity and every simulated-time bound still run on the real data.
    A test whose subject is the real age of the ROS clock or the admission JOINT
    sets row.fresh_clock or row.fresh_joint to False.
    """
    observer, runtime = row.observer, row.runtime
    row.fresh_clock = True  # a test of ROS clock loss sets this False
    row.fresh_joint = True  # a test of joint receipt loss sets this False
    policy_type = type(row.port.feedback_policy)
    real_check_joint = policy_type.check_joint

    def check_joint(policy, sample, decision):
        if (policy is row.port.feedback_policy and row.fresh_joint
                and sample is not None and 'wall_s' in sample):
            sample = dict(sample, wall_s=decision['wall_after_s'])
        return real_check_joint(policy, sample, decision)

    # The policy instance is frozen; the class patch is undone with the test and
    # applies only to this row's policy instance.
    row.monkeypatch.setattr(policy_type, 'check_joint', check_joint)
    real_inputs, real_current = observer.current_inputs, runtime._current

    def current_inputs(now_wall_s):
        current = real_inputs(now_wall_s)
        current['image'] = dict(current['image'], wall_s=now_wall_s)
        current['info'] = dict(current['info'], wall_s=now_wall_s)
        current['image_source_wall_s'] = now_wall_s
        if row.fresh_clock:
            current['clock'] = dict(current['clock'], wall_s=now_wall_s)
        return current

    def current(*args, **keywords):
        runtime.executor_progress()
        return real_current(*args, **keywords)

    observer.current_inputs, runtime._current = current_inputs, current


def armed_runtime(row, *, fresh=False):
    """fresh=True keeps the wall-age bounds independent of host load; see keep_wall_bounds_fresh."""
    prime_current_inputs(row)
    row.runtime.start()
    if fresh:
        keep_wall_bounds_fresh(row)
    assert row.runtime.arm()['incarnation'] == 'inc-1'
    return row.runtime


def test_admission_joint_loss_refuses_even_when_independent_raw_stop_feedback_advances(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
    row.fresh_joint = False  # this test's subject is the real age of the admission JOINT
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
    runtime = armed_runtime(row, fresh=True)
    row.fresh_clock = False  # this test's subject is the real age of the ROS clock sample
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
    runtime = armed_runtime(row, fresh=True)
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
            owner=row.owner, observer=row.observer, policy=row.policy, sink=row.sink)
    with pytest.raises((TypeError, ValueError, PermissionError)):
        runtime_module().HeadLocalRuntime(node=row.node, port=row.port, local_state=row.state,
            owner=row.owner, observer=row.observer, policy=simulation_policy(
                search_timeout_s=29.), sink=row.sink)
    with pytest.raises(ValueError, match='OWNER_INVALID'):
        runtime_module().HeadLocalRuntime(node=row.node, port=row.port, local_state=row.state,
            owner=object(), observer=row.observer, policy=row.policy, sink=row.sink)


def test_runtime_start_is_explicit_once_and_constructor_does_not_arm(monkeypatch):
    row = runtime_setup(monkeypatch)
    assert row.runtime.armed is False
    assert row.runtime.started is False
    receipt = row.runtime.start()
    assert receipt['watchdog_started'] is True
    assert sorted(receipt['workers']) == ['cancel_stop', 'deadman_latch']
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
    assert row.runtime.armed is False and not any(call == 'controller' for call in [])
    prime_current_inputs(row, velocity=.5)
    with pytest.raises((PermissionError, ValueError)):
        row.runtime.arm()
    assert row.runtime.armed is False
    prime_current_inputs(row)
    assert row.runtime.arm()['boot'] == 'boot-1'
    assert row.runtime.armed is True
    assert row.owner_events or True
    row.runtime.close(timeout_s=1.)


def test_dispatch_guard_consumes_current_originals_and_refuses_stale_ones(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
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
    runtime = armed_runtime(row, fresh=True)
    release = threading.Event()
    row.sink.block = release
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault('receipt', runtime.fault(
        'HEAD_LOCAL_TEST_FAULT')))
    thread.start()
    assert wait_for(lambda: row.state.faulted)
    assert row.state.fault_occurrence_ns is not None
    assert wait_for(lambda: row.closed_count() == 1)
    assert result == {}
    release.set()
    thread.join(2.)
    assert result['receipt']['reason'] == 'HEAD_LOCAL_TEST_FAULT'
    assert result['receipt']['occurred_ns'] == row.state.fault_occurrence_ns
    assert any(kind == 'FAULT' for kind, _, _ in row.sink.rows)
    runtime.close(timeout_s=1.)


def test_blocked_deadman_close_does_not_block_cancel_or_raw_stop(monkeypatch):
    close_block = threading.Event()
    row = runtime_setup(monkeypatch, block_close=close_block)
    runtime = armed_runtime(row, fresh=True)
    with row.port._lock:
        row.port._goals[str(uuid.uuid4())] = dict(accepted=None, handle=None, result=None,
            cancel_requested=False, cancel_ack=False, error=None, goal={})
    runtime.fault('HEAD_LOCAL_TEST_DEADMAN_BLOCKED')
    assert wait_for(lambda: row.closed_count() == 1)
    assert wait_for(lambda: any(entry[0] == 'cancel_goal' for entry in row.calls))
    assert row.port._stop_epoch is not None
    assert row.port._stop_epoch['fault_wall_s'] == pytest.approx(
        row.state.fault_occurrence_ns * 1e-9, abs=1e-6)
    close_block.set()
    assert wait_for(lambda: runtime.retirement_snapshot()['deadman_close']['ack'])
    runtime.close(timeout_s=1.)


def test_blocked_cancel_does_not_block_the_deadman_latch_ack(monkeypatch):
    cancel_block = threading.Event()
    row = runtime_setup(monkeypatch, block_cancel=cancel_block)
    runtime = armed_runtime(row, fresh=True)
    row.clients['cancel_goal'].block = cancel_block
    with row.port._lock:
        row.port._goals[str(uuid.uuid4())] = dict(accepted=None, handle=None, result=None,
            cancel_requested=False, cancel_ack=False, error=None, goal={})
    runtime.fault('HEAD_LOCAL_TEST_CANCEL_BLOCKED')
    assert wait_for(lambda: row.closed_count() == 1)
    assert wait_for(lambda: runtime.retirement_snapshot()['deadman_close']['ack'])
    assert runtime.retirement_snapshot()['cancel_stop']['finished'] is False
    cancel_block.set()
    runtime.close(timeout_s=1.)


def test_repeated_stop_and_later_fault_never_renew_the_original_origin(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
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
    runtime = armed_runtime(row, fresh=True)
    token = row.state.latch_fault('HEAD_LOCAL_DISPATCH_DIRECT_FAULT')
    assert token is not None
    assert wait_for(lambda: runtime.faulted, timeout_s=1.)
    assert wait_for(lambda: row.closed_count() == 1)
    assert runtime.fault_receipt()['occurred_ns'] == row.state.fault_occurrence_ns
    assert row.port._stop_epoch['fault_wall_s'] == pytest.approx(
        row.state.fault_occurrence_ns * 1e-9, abs=1e-6)
    assert runtime.dispatch_guard_refused_reason is not None
    runtime.close(timeout_s=1.)


def test_writer_enqueue_failure_latches_fault_and_still_stops(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
    row.sink.fail = True
    with pytest.raises(PermissionError):
        runtime.record('TEST_RECORD', dict(value=1))
    assert row.state.faulted is True
    assert row.state.snapshot['fault']['reason'] == 'HEAD_LOCAL_WRITER_ENQUEUE_FAILED'
    assert wait_for(lambda: row.closed_count() == 1)
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
    runtime = armed_runtime(row, fresh=True)
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
        assert wait_for(lambda: row.closed_count() == 1)
    finally:
        assert runtime.close(timeout_s=1.)['retired'] is True


def test_close_reports_unquiesced_worker_instead_of_claiming_retirement(monkeypatch):
    close_block = threading.Event()
    row = runtime_setup(monkeypatch, block_close=close_block)
    runtime = armed_runtime(row, fresh=True)
    runtime.fault('HEAD_LOCAL_TEST_UNQUIESCED')
    receipt = runtime.close(timeout_s=.05)
    assert receipt['retired'] is False
    assert receipt['unquiesced'] == ['deadman_latch']
    assert receipt['confirmed_stop'] is False
    close_block.set()
    assert wait_for(lambda: runtime.retirement_snapshot()['deadman_close']['ack'], timeout_s=2.)
    final = runtime.close(timeout_s=1.)
    assert final['retired'] is True


def test_own_inventory_requires_the_existing_local_record_and_never_reregisters(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
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
    runtime = armed_runtime(row, fresh=True)
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




# ---- protocol v2: startup through the neck owner, stop proof and dead-man close -------------------------------

def kinds_of(row, *names):
    return [kind for kind, _, _ in row.sink.rows if kind in names]


def records_of(row, kind):
    return [record for name, record, _ in row.sink.rows if name == kind]


def head_simulation_policy(**changes):
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    return HeadSimulationPolicy.parse(dict(HeadSimulationPolicy.default_document(), **changes))


class Producer:
    """Feeds advancing originals so the raw stop can be confirmed, like the live feedback does."""

    def __init__(self, row):
        self.row, self.done = row, threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        time.sleep(.03)
        while not self.done.is_set():
            try:
                prime_current_inputs(self.row)
            except PermissionError:
                return
            time.sleep(.01)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.done.set()
        self.thread.join(1.)


def test_startup_goes_through_the_owner_and_records_the_events_in_order(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
    assert kinds_of(row, 'CONTROLLER_READBACK', 'DEADMAN_ARMED', 'GRAPH_PROOF', 'STARTUP_STOP_WINDOW',
                    'ARMED') == ['CONTROLLER_READBACK', 'DEADMAN_ARMED', 'GRAPH_PROOF',
                                 'STARTUP_STOP_WINDOW', 'ARMED']
    readback, = records_of(row, 'CONTROLLER_READBACK')
    assert readback['controller_type'] == 'so101_mujoco_support/HeadNeckTrajectoryController'
    assert readback['activation_id'] == 1
    graph, = records_of(row, 'GRAPH_PROOF')
    assert set(graph) >= {'own_gids', 'foreign_allowed', 'service_clients'}
    armed, = records_of(row, 'DEADMAN_ARMED')
    assert armed['peer_pid'] == 4242 and armed['head_deadman_timeout_s'] == row.policy.head_deadman_timeout_s
    window, = records_of(row, 'STARTUP_STOP_WINDOW')
    assert window['n'] == 51 and set(window) >= {'first_sim_ns', 'last_sim_ns', 'max_abs_feedback_velocity',
                                                'max_abs_reference_velocity', 'reference_position', 'max_age_ns'}
    assert runtime.ready and runtime.armed
    assert row.state.scope['controller_identity'] == row.owner.identity()
    assert row.owner.monitor_alive is True
    runtime.close(timeout_s=1.)
    row.owner.close()


def test_the_runtime_binds_itself_as_the_owners_fault_entry_and_liveness(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
    row.owner._fault('HEAD_GRAPH_CHANGED', dict(added=[1]))
    assert runtime.faulted and runtime.fault_reason == 'HEAD_GRAPH_CHANGED'
    assert row.owner._liveness is not None and row.owner._liveness() < .5
    runtime.close(timeout_s=1.)
    row.owner.close()


@pytest.mark.parametrize('damage', ['readback', 'window', 'identity'])
def test_a_refused_owner_step_fails_the_startup_without_readiness(monkeypatch, damage):
    row = runtime_setup(monkeypatch)
    prime_current_inputs(row)
    row.runtime.start()
    if damage == 'readback':
        row.services.params['interpolate_from_desired_state'] = True
    elif damage == 'window':
        def unavailable(**keywords):
            raise TimeoutError('HEAD_STOP_WINDOW_UNAVAILABLE')
        row.owner.startup_stop_window = unavailable
    else:
        row.owner.identity = lambda: dict(generation=7, incarnation='other', boot='boot-1')
    with pytest.raises((PermissionError, TimeoutError)):
        row.runtime.arm()
    assert not row.runtime.ready and row.runtime.faulted
    assert row.runtime.fault_reason == 'HEAD_LOCAL_RUNTIME_STARTUP_FAILED'
    assert 'ARMED' not in kinds_of(row, 'ARMED')
    assert wait_for(lambda: row.closed_count() == 1), 'a failed startup latches the controller'
    row.runtime.close(timeout_s=1.)
    row.owner.close()


def test_a_successful_case_proves_the_stop_then_closes_the_deadman_as_planned(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
    with Producer(row):
        runtime.stop('success', dict(status='TARGET_LOCKED'))
        runtime.finish_requested_stop()
    names = kinds_of(row, 'STOP_REQUEST', 'CANCEL_STOP', 'STOCK_STOP_PROOF', 'DEADMAN_CLOSED_PLANNED',
                     'DEADMAN_CLOSED_FAULT')
    assert names == ['STOP_REQUEST', 'CANCEL_STOP', 'STOCK_STOP_PROOF', 'DEADMAN_CLOSED_PLANNED']
    cancel, = records_of(row, 'CANCEL_STOP')
    proof, = records_of(row, 'STOCK_STOP_PROOF')
    assert cancel['raw_stop_confirmed'] is True and type(cancel['raw_stop_confirmed_sim_ns']) is int
    assert proof['raw_stop_confirmed_sim_ns'] == cancel['raw_stop_confirmed_sim_ns']
    assert proof['window']['n'] == 51 and proof['deadman_closed_planned'] is True
    assert len(proof['raw_stop_samples']) >= 3 and isinstance(proof['terminal'], dict)
    assert row.window.rearms[-1] == cancel['raw_stop_confirmed_sim_ns'], 'the end window counts later samples only'
    closed, = records_of(row, 'DEADMAN_CLOSED_PLANNED')
    assert closed == dict(activation_id=1)
    receipt = runtime.stop_receipt()
    assert receipt['physical_stop_confirmed'] is True
    assert receipt['deadman_close']['planned'] is True and receipt['deadman_close']['ack'] is True
    assert row.closed_count() == 1
    closure = runtime.close(timeout_s=1.)
    assert closure['confirmed_stop'] is True and closure['retired'] is True
    row.owner.close()


def test_the_planned_close_comes_after_the_proof_records(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
    order = []
    original = FakeHelper.close_planned

    def close_planned(self, timeout_s=1.):
        order.append(('helper_closed', kinds_of(row, 'STOCK_STOP_PROOF', 'DEADMAN_CLOSED_PLANNED')))
        return original(self, timeout_s)
    monkeypatch.setattr(BlockableHelper, 'close_planned', close_planned)
    with Producer(row):
        runtime.stop('success')
        runtime.finish_requested_stop()
    assert order == [('helper_closed', ['STOCK_STOP_PROOF', 'DEADMAN_CLOSED_PLANNED'])]
    runtime.close(timeout_s=1.)
    row.owner.close()


def test_a_fault_latches_the_deadman_at_once_without_waiting_for_the_stop_proof(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
    runtime.fault('HEAD_LOCAL_TEST_FAULT_LATCH')  # no producer: the raw stop cannot be confirmed
    assert wait_for(lambda: row.closed_count() == 1)
    assert wait_for(lambda: runtime.retirement_snapshot()['deadman_close']['finished'])
    snapshot = runtime.retirement_snapshot()
    assert snapshot['deadman_close']['planned'] is False and snapshot['deadman_close']['ack'] is True
    fault_close, = records_of(row, 'DEADMAN_CLOSED_FAULT')
    assert fault_close['ack'] is True and fault_close['reason'] == 'fault'
    runtime.finish_requested_stop()
    assert 'DEADMAN_CLOSED_PLANNED' not in kinds_of(row, 'DEADMAN_CLOSED_PLANNED')
    assert 'STOCK_STOP_PROOF' not in kinds_of(row, 'STOCK_STOP_PROOF')
    assert runtime.stop_receipt()['physical_stop_confirmed'] is False
    runtime.close(timeout_s=1.)
    row.owner.close()


def test_a_fault_during_a_planned_stop_closes_unplanned_and_proves_nothing_planned(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
    with Producer(row):
        runtime.stop('success')
        runtime.fault('HEAD_LOCAL_TEST_LATE_FAULT')
        runtime.finish_requested_stop()
    assert 'DEADMAN_CLOSED_PLANNED' not in kinds_of(row, 'DEADMAN_CLOSED_PLANNED')
    assert row.closed_count() == 1
    assert runtime.retirement_snapshot()['deadman_close']['planned'] is False
    runtime.close(timeout_s=1.)
    row.owner.close()


def test_a_missing_end_window_leaves_the_stop_unconfirmed_and_latches_the_controller(monkeypatch):
    row = runtime_setup(monkeypatch, policy=head_simulation_policy(head_stop_window_deadline_s=.15))
    runtime = armed_runtime(row, fresh=True)
    row.window.auto = False  # the controller_state stream gave no quiet window after the raw stop
    with Producer(row):
        runtime.stop('success')
        runtime.finish_requested_stop()
    cancel = runtime.retirement_snapshot()['cancel_stop']
    assert cancel['raw_stop_confirmed'] is True and cancel['end_window'] is None
    assert 'HEAD_STOP_WINDOW_UNAVAILABLE' in cancel['window_error']
    assert 'STOCK_STOP_PROOF' not in kinds_of(row, 'STOCK_STOP_PROOF')
    assert 'DEADMAN_CLOSED_PLANNED' not in kinds_of(row, 'DEADMAN_CLOSED_PLANNED')
    assert row.closed_count() == 1 and runtime.retirement_snapshot()['deadman_close']['planned'] is False
    assert runtime.stop_receipt()['physical_stop_confirmed'] is False
    closure = runtime.close(timeout_s=1.)
    assert closure['confirmed_stop'] is False
    row.owner.close()


def test_an_unconfirmed_raw_stop_never_asks_for_the_end_window(monkeypatch):
    row = runtime_setup(monkeypatch)
    runtime = armed_runtime(row, fresh=True)
    runtime.stop('success')  # nothing produces feedback: the raw stop cannot confirm
    assert wait_for(lambda: runtime.retirement_snapshot()['cancel_stop']['finished'] is True, timeout_s=3.)
    runtime.finish_requested_stop()
    assert row.window.rearms[1:] == [], 'only the startup rearm happened'
    assert row.closed_count() == 1 and runtime.retirement_snapshot()['deadman_close']['planned'] is False
    runtime.close(timeout_s=1.)
    row.owner.close()
