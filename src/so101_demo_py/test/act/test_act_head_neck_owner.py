"""The owner's side of the Head neck protocol (design sections 1.3, 1.4, 3, 4)."""

import re
import threading
import time

import pytest

from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
from so101_demo.adapters.act.head_neck_owner import HeadNeckOwner

from head_owner_support import (CONTROLLER_TYPE, FakeGraph, FakeHelper, FakeServices, FakeTicker, FakeWindow,
                                 deadline, make, policy)


# ---- activation -----------------------------------------------------------------------------------------

def test_activation_plans_the_switch_first_sets_the_helper_pid_then_activates_and_waits_for_the_connection():
    owner, services, window, graph, events, faults = make()
    info = owner.activate(deadline=deadline())
    assert events[0] == ('CONTROLLER_SWITCH_PLANNED', dict(
        controller='neck_controller', action='ACTIVATE', old_activation_id=0, new_activation_id=1))
    order = [call for call in services.calls if call != 'controller']
    assert order.index(('set', 'head_deadman_peer_pid', 4242)) < order.index(('switch', ('neck_controller',), ()))
    assert info == dict(activation_id=1, helper_pid=4242, socket_path=info['socket_path'])
    assert info['socket_path'].endswith('/neck-1.sock')
    helper = FakeHelper.instances[0]
    assert helper.keywords['activation_id'] == 1 and helper.ticker is not None
    assert services.state == 'active' and window.started


def test_the_helper_is_started_before_the_activation_and_gets_the_directory_and_next_activation_id():
    owner, services, *_ = make()
    seen = []
    services.on_switch = lambda: seen.append(FakeHelper.instances[0].status)
    owner.activate(deadline=deadline())
    assert seen == ['STARTED']
    assert FakeHelper.instances[0].keywords['directory'] == owner.directory


@pytest.mark.parametrize('failure,code', [
    ('set_pid', 'HEAD_NECK_PEER_PID_REFUSED'),
    ('switch', 'HEAD_NECK_ACTIVATION_REFUSED'),
])
def test_a_refused_pid_or_switch_fails_the_activation_and_kills_the_helper(failure, code):
    owner, services, *_ = make()
    services.refuse.add(failure)
    with pytest.raises(PermissionError, match=code):
        owner.activate(deadline=deadline())
    assert FakeHelper.instances[0].killed


def test_an_activation_that_never_reaches_active_times_out():
    owner, services, *_ = make()
    services.switch = lambda **keywords: True  # accepted but the state never changes
    with pytest.raises(TimeoutError, match='HEAD_NECK_ACTIVATION_TIMEOUT'):
        owner.activate(deadline=deadline(.2))
    assert FakeHelper.instances[0].killed


def test_a_wrong_activation_id_or_an_unconnected_helper_fails_the_activation():
    owner, services, *_ = make()
    services.on_switch = lambda: services.params.__setitem__('head_activation_id', 9)
    with pytest.raises(PermissionError, match='HEAD_NECK_ACTIVATION_ID_MISMATCH'):
        owner.activate(deadline=deadline())
    owner, services, *_ = make()
    FakeHelper.connected_default = False
    original = FakeHelper.wait_connected
    FakeHelper.wait_connected = lambda self, timeout_s: False
    try:
        with pytest.raises(PermissionError, match='HEAD_NECK_DEADMAN_NOT_CONNECTED'):
            owner.activate(deadline=deadline())
    finally:
        FakeHelper.wait_connected = original


def test_activation_twice_without_a_plan_is_refused():
    owner, *_ = make()
    owner.activate(deadline=deadline())
    with pytest.raises(PermissionError, match='HEAD_NECK_ALREADY_ACTIVE'):
        owner.activate(deadline=deadline())


def test_the_directory_must_be_a_private_directory_of_the_owner():
    import os
    import tempfile
    loose = tempfile.mkdtemp(prefix='dml')
    os.chmod(loose, 0o755)
    with pytest.raises(PermissionError, match='HEAD_NECK_DIRECTORY_MODE'):
        make(directory=loose)
    with pytest.raises(PermissionError, match='HEAD_NECK_DIRECTORY_MISSING'):
        make(directory=loose + '/missing')


# ---- readback, arming, identity ------------------------------------------------------------------------------

def test_the_readback_reports_the_type_the_immutable_values_and_the_activation_id():
    owner, services, *_ = make()
    owner.activate(deadline=deadline())
    readback = owner.readback(deadline=deadline())
    assert readback['controller_type'] == CONTROLLER_TYPE and readback['state'] == 'active'
    assert readback['activation_id'] == 1
    assert readback['parameters']['interpolate_from_desired_state'] is False
    assert readback['parameters']['joints'] == ['neck_yaw_joint']
    assert readback['parameters']['head_deadman_peer_pid'] == 4242


@pytest.mark.parametrize('name,value', [
    ('open_loop_control', True), ('interpolate_from_desired_state', True),
    ('interpolation_method', 'none'), ('allow_partial_joints_goal', True),
    ('allow_integration_in_goal_trajectories', True), ('joints', ['other']),
    ('speed_scaling.initial_scaling_factor', 0.5), ('head_deadman_peer_pid', 1)])
def test_a_wrong_immutable_value_refuses_the_readback(name, value):
    owner, services, *_ = make()
    owner.activate(deadline=deadline())
    services.params[name] = value
    with pytest.raises(PermissionError, match='HEAD_CONTROLLER_READBACK_INVALID.*' + re.escape(name)):
        owner.readback(deadline=deadline())


def test_a_wrong_controller_type_or_state_refuses_the_readback():
    owner, services, *_ = make()
    owner.activate(deadline=deadline())
    services.type = 'joint_trajectory_controller/JointTrajectoryController'
    with pytest.raises(PermissionError, match='HEAD_CONTROLLER_READBACK_INVALID.*controller_type'):
        owner.readback(deadline=deadline())
    services.type = CONTROLLER_TYPE
    services.state = 'inactive'
    with pytest.raises(PermissionError, match='HEAD_CONTROLLER_READBACK_INVALID.*state'):
        owner.readback(deadline=deadline())


def test_the_deadman_armed_record_and_the_identity_triple():
    owner, services, *_ = make()
    owner.activate(deadline=deadline())
    armed = owner.deadman_armed()
    assert armed['peer_pid'] == 4242 and armed['activation_id'] == 1
    assert armed['socket_path'].endswith('/neck-1.sock')
    assert armed['head_deadman_period_s'] == .02 and armed['head_deadman_timeout_s'] == .2
    identity = owner.identity()
    assert set(identity) == {'generation', 'incarnation', 'boot'} and identity['generation'] == 7
    assert all(re.fullmatch(r'[\x20-\x7e]{1,64}', identity[key]) for key in ('incarnation', 'boot'))
    assert owner.identity() == identity


def test_the_identity_names_the_activation_and_the_helper():
    owner, *_ = make()
    with pytest.raises(PermissionError, match='HEAD_NECK_NOT_ACTIVE'):
        owner.identity()
    owner.activate(deadline=deadline())
    assert 'act-1' in owner.identity()['incarnation'] and '4242' in owner.identity()['incarnation']


def test_the_graph_proof_is_delegated_once():
    owner, services, window, graph, *_ = make()
    owner.activate(deadline=deadline())
    assert owner.graph_proof()['own_gids'] == {} and graph.proofs == 1


# ---- the stop window ----------------------------------------------------------------------------------------------

def complete_later(window, delay, **keywords):
    threading.Timer(delay, lambda: window.complete(**keywords)).start()


def test_the_startup_window_starts_from_a_rearmed_window_and_returns_the_fresh_completion():
    owner, services, window, *_ = make()
    owner.activate(deadline=deadline())
    window.complete(first=1)  # an early window from before the startup phase is forgotten
    complete_later(window, .05, first=2_000_000_000)
    done = owner.startup_stop_window(deadline=deadline(1.))
    assert done['n'] == 51 and done['first_sim_ns'] == 2_000_000_000 and window.rearms[0] is None


def test_a_completion_older_than_200ms_when_the_owner_looks_is_stale_and_collected_again():
    owner, services, window, *_ = make()
    owner.activate(deadline=deadline())
    stale = time.monotonic_ns() - 400_000_000
    complete_later(window, .03, first=1_000_000_000, mono_ns=stale)
    threading.Timer(.15, lambda: window.complete(first=3_000_000_000)).start()
    done = owner.startup_stop_window(deadline=deadline(1.))
    assert done['first_sim_ns'] == 3_000_000_000 and len(window.rearms) >= 2


def test_the_startup_window_refuses_after_the_deadline_and_a_goal_voids_it():
    owner, services, window, *_ = make()
    owner.activate(deadline=deadline())
    with pytest.raises(TimeoutError, match='HEAD_STOP_WINDOW_UNAVAILABLE'):
        owner.startup_stop_window(deadline=deadline(.15))
    owner.note_goal()
    assert window.voids == ['GOAL_SENT']


def test_the_end_window_counts_only_samples_after_the_raw_stop_and_has_its_own_deadline():
    owner, services, window, *_ = make()
    owner.activate(deadline=deadline())
    owner.begin_end_window(raw_stop_sim_ns=5_000_000_000)
    assert window.rearms[-1] == 5_000_000_000
    with pytest.raises(TimeoutError, match='HEAD_STOP_WINDOW_UNAVAILABLE'):
        owner.end_stop_window(timeout_s=.1)
    window.complete(first=5_002_000_000)
    assert owner.end_stop_window(timeout_s=.5)['first_sim_ns'] == 5_002_000_000


def test_the_latest_controller_state_comes_from_the_window_subscriber():
    owner, services, window, *_ = make()
    assert owner.latest_controller_state() is None
    window._latest = dict(sim_ns=1)
    assert owner.latest_controller_state() == dict(sim_ns=1)


# ---- closing -------------------------------------------------------------------------------------------------------

def test_a_planned_close_closes_the_helper_and_is_idempotent():
    owner, services, *_ = make()
    owner.activate(deadline=deadline())
    first = owner.close_planned()
    assert first == dict(activation_id=1, helper_closed=True) and FakeHelper.instances[0].closed_planned == 1
    assert owner.close_planned() == first and FakeHelper.instances[0].closed_planned == 1


def test_a_fault_close_latches_at_once_and_a_later_planned_close_is_the_same_close():
    owner, services, *_ = make()
    owner.activate(deadline=deadline())
    fault = owner.close_fault('HEAD_TEST')
    assert fault == dict(activation_id=1, helper_closed=True, reason='HEAD_TEST')
    assert owner.close_planned()['helper_closed'] is True
    assert FakeHelper.instances[0].closed_planned == 1


def test_close_retires_helper_window_and_monitor():
    owner, services, window, *_ = make()
    owner.activate(deadline=deadline())
    owner.start_monitor()
    receipt = owner.close()
    assert FakeHelper.instances[0].killed and window.stopped and receipt['monitor_alive'] is False
    assert owner.close() == receipt


# ---- monitor: unplanned switch, deactivation, stale state, graph -----------------------------------------------------

def run_monitor(owner, services, faults, until, **keywords):
    owner.start_monitor(controller_period_s=.02, graph_period_s=.01, **keywords)
    limit = time.monotonic() + 2.
    while time.monotonic() < limit and not until():
        time.sleep(.005)


def test_an_unplanned_reactivation_is_an_unplanned_switch():
    owner, services, window, graph, events, faults = make()
    owner.activate(deadline=deadline())
    window._latest = None
    services.params['head_activation_id'] = 2
    run_monitor(owner, services, faults, lambda: faults)
    owner.close()
    assert faults[0][0] == 'HEAD_UNPLANNED_CONTROLLER_SWITCH'
    assert faults[0][1]['expected_activation_id'] == 1 and faults[0][1]['observed_activation_id'] == 2


def test_a_planned_switch_is_not_a_fault():
    owner, services, window, graph, events, faults = make()
    owner.activate(deadline=deadline())
    owner.plan_switch(old_activation_id=1, new_activation_id=2, action='REACTIVATE')
    assert ('CONTROLLER_SWITCH_PLANNED', dict(controller='neck_controller', action='REACTIVATE',
                                             old_activation_id=1, new_activation_id=2)) in events
    services.params['head_activation_id'] = 2
    owner.start_monitor(controller_period_s=.02, graph_period_s=.01)
    time.sleep(.2)
    owner.close()
    assert not faults


def test_a_deactivated_controller_faults_the_run():
    owner, services, window, graph, events, faults = make()
    owner.activate(deadline=deadline())
    services.state = 'inactive'
    run_monitor(owner, services, faults, lambda: faults)
    owner.close()
    assert faults[0][0] == 'HEAD_NECK_CONTROLLER_DEACTIVATED' and faults[0][1]['state'] == 'inactive'


def test_a_silent_controller_state_stream_faults_the_run_after_the_window_deadline():
    owner, services, window, graph, events, faults = make()
    owner.activate(deadline=deadline())
    window._latest = dict(sim_ns=1, receive_mono_ns=time.monotonic_ns() - 700_000_000)
    run_monitor(owner, services, faults, lambda: faults)
    owner.close()
    assert faults[0][0] == 'HEAD_NECK_CONTROLLER_DEACTIVATED' and faults[0][1]['reason'] == 'CONTROLLER_STATE_SILENT'


def test_a_fresh_controller_state_stream_does_not_fault():
    owner, services, window, graph, events, faults = make()
    owner.activate(deadline=deadline())
    owner.start_monitor(controller_period_s=.02, graph_period_s=.01)
    for _ in range(20):
        window._latest = dict(sim_ns=1, receive_mono_ns=time.monotonic_ns())
        time.sleep(.01)
    owner.close()
    assert not faults


def test_a_graph_change_faults_the_run_once():
    owner, services, window, graph, events, faults = make()
    owner.activate(deadline=deadline())
    owner.graph_proof()
    graph.changed = dict(code='HEAD_GRAPH_CHANGED', added=[dict(topic='/x', kind='subscription',
                                                                node_name='rogue', gid='ff')], removed=[])
    run_monitor(owner, services, faults, lambda: faults)
    time.sleep(.1)
    owner.close()
    assert [code for code, _ in faults] == ['HEAD_GRAPH_CHANGED'] and faults[0][1]['added'][0]['node_name'] == 'rogue'


def test_the_ticker_is_gated_by_the_runtime_liveness():
    owner, services, window, graph, events, faults = make()
    owner.activate(deadline=deadline())
    ticker = FakeHelper.instances[0].ticker
    assert ticker.alive() is True, 'before a runtime is bound the owner ticks on its own'
    state = dict(age=0.01)
    owner.bind_liveness(lambda: state['age'])
    assert ticker.alive() is True
    state['age'] = 0.5
    assert ticker.alive() is False


# ---- local per-goal admission (replaces the broker's reservation) ------------------------------------------------

def test_admit_local_builds_the_claim_binding_voids_the_window_and_calls_the_registrar_once():
    owner, services, window, graph, events, faults = make()
    owner.activate(deadline=deadline())
    seen = []

    def register(binding):
        seen.append(binding)
        return True
    assert owner.admit_local(goal=b'CDR', goal_uuid=b'u' * 16, before_reserve=register) is True
    binding, = seen
    identity = owner.identity()
    assert (binding.role, binding.generation, binding.session_id) == ('neck', 7, 'session-1')
    assert binding.goal_cdr == b'CDR' and binding.goal_uuid == b'u' * 16
    assert binding.controller_incarnation == identity['incarnation'] and binding.controller_boot_incarnation == identity['boot']
    assert binding.deadline_ns - binding.claim_monotonic_ns == 400_000_000
    assert abs(binding.claim_monotonic_ns - time.monotonic_ns()) < 1_000_000_000
    assert window.voids == ['GOAL_SENT']


def test_admit_local_is_refused_before_activation_after_a_close_and_after_a_fault():
    owner, *_ = make()
    with pytest.raises(PermissionError, match='HEAD_NECK_NOT_ACTIVE'):
        owner.admit_local(goal=b'x', goal_uuid=b'u' * 16, before_reserve=lambda binding: True)
    owner.activate(deadline=deadline())
    owner.close_fault('HEAD_TEST')
    with pytest.raises(PermissionError, match='HEAD_NECK_CLOSED'):
        owner.admit_local(goal=b'x', goal_uuid=b'u' * 16, before_reserve=lambda binding: True)
    owner2, services, window, graph, events, faults = make()
    owner2.activate(deadline=deadline())
    owner2._fault('HEAD_GRAPH_CHANGED', {})
    with pytest.raises(PermissionError, match='HEAD_NECK_FAULTED'):
        owner2.admit_local(goal=b'x', goal_uuid=b'u' * 16, before_reserve=lambda binding: True)


def test_admit_local_reports_a_registrar_that_does_not_accept():
    owner, *_ = make()
    owner.activate(deadline=deadline())
    assert owner.admit_local(goal=b'x', goal_uuid=b'u' * 16, before_reserve=lambda binding: False) is False


def test_closers_run_on_close_and_listeners_reach_the_window():
    closed = []
    owner, services, window, *_ = make(closers=(lambda: closed.append('services') or dict(closed=True),))
    seen = []
    owner.add_controller_state_listener(seen.append)
    assert window.listeners == [seen.append] or len(window.listeners) == 1
    receipt = owner.close()
    assert closed == ['services'] and receipt['closers'] == [dict(closed=True)]
