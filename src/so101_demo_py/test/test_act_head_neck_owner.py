"""The owner's side of the Head neck protocol (design sections 1.3, 1.4, 3, 4)."""

import re
import threading
import time

import pytest

from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
from so101_demo.adapters.act.head_neck_owner import HeadNeckOwner

CONTROLLER_TYPE = 'so101_mujoco_support/HeadNeckTrajectoryController'


def policy():
    return HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document_v3())


class FakeServices:
    def __init__(self):
        self.state = 'inactive'
        self.activation_id = 0
        self.params = {
            'open_loop_control': False, 'interpolate_from_desired_state': False,
            'interpolation_method': 'splines', 'allow_partial_joints_goal': False,
            'allow_integration_in_goal_trajectories': False, 'joints': ['neck_yaw_joint'],
            'command_interfaces': ['position'], 'state_interfaces': ['position', 'velocity'],
            'speed_scaling.initial_scaling_factor': 1.0, 'head_deadman_directory': '/tmp/dm',
            'head_deadman_timeout_s': 0.2, 'head_deadman_peer_pid': 0, 'head_activation_id': 0}
        self.type = CONTROLLER_TYPE
        self.calls, self.refuse = [], set()
        self.on_switch = None

    def controller(self, *, deadline):
        self.calls.append('controller')
        return None if 'missing' in self.refuse else dict(type=self.type, state=self.state)

    def switch(self, *, activate, deactivate, deadline):
        self.calls.append(('switch', tuple(activate), tuple(deactivate)))
        if 'switch' in self.refuse:
            return False
        if activate:
            if self.params['head_deadman_peer_pid'] <= 0:
                return False
            self.state = 'active'
            self.activation_id += 1
            self.params['head_activation_id'] = self.activation_id
        if deactivate:
            self.state = 'inactive'
            self.params['head_deadman_peer_pid'] = 0
        if self.on_switch:
            self.on_switch()
        return True

    def get_parameters(self, names, *, deadline):
        self.calls.append(('get', tuple(names)))
        return {name: self.params[name] for name in names}

    def set_integer(self, name, value, *, deadline):
        self.calls.append(('set', name, value))
        if 'set_pid' in self.refuse:
            return False, 'refused'
        self.params[name] = value
        return True, ''

    def close(self):
        return dict(closed=True)


class FakeTicker:
    def __init__(self, alive):
        self.alive, self.stopped = alive, False

    def stop(self):
        self.stopped = True


class FakeHelper:
    instances = []

    def __init__(self, **keywords):
        self.keywords, self.pid, self.connected = keywords, 4242, True
        self.closed_planned, self.killed, self.ticker = 0, False, None
        self.status = None
        FakeHelper.instances.append(self)

    def start(self):
        self.status = 'STARTED'
        return self.pid

    def wait_connected(self, timeout_s):
        self.status = 'CONNECTED' if self.connected else 'CONNECT_TIMEOUT'
        return self.connected

    def start_ticker(self, period_s=.02, alive=None):
        self.ticker = FakeTicker(alive)
        return self.ticker

    def close_planned(self, timeout_s=1.):
        self.closed_planned += 1
        self.status = 'CLOSED'
        return True

    def kill(self):
        self.killed = True


class FakeWindow:
    def __init__(self):
        self.started = self.stopped = False
        self._completed, self.rearms, self.voids = None, [], []
        self.resets_total, self._latest = 0, None
        self.listeners = []

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
        return dict(thread_alive=False)

    @property
    def completed(self):
        return self._completed

    def complete(self, first=1_000_000_000, mono_ns=None):
        self._completed = dict(n=51, first_sim_ns=first, last_sim_ns=first + 100_000_000,
                               max_abs_feedback_velocity=1e-5, max_abs_reference_velocity=0.0,
                               reference_position=0.1, max_age_ns=90_000_000,
                               completed_mono_ns=time.monotonic_ns() if mono_ns is None else mono_ns)

    def wait_completed(self, timeout_s):
        deadline = time.monotonic() + timeout_s
        while self._completed is None and time.monotonic() < deadline:
            time.sleep(.002)
        return self._completed

    def rearm(self, floor_sim_ns=None):
        self.rearms.append(floor_sim_ns)
        self._completed = None

    def void(self, reason):
        self.voids.append(reason)

    def snapshot(self):
        return dict(resets=dict(VELOCITY=self.resets_total), voids=list(self.voids), completed=self._completed)

    def latest(self):
        return self._latest

    def add_listener(self, listener):
        self.listeners.append(listener)


class FakeGraph:
    def __init__(self):
        self.proofs, self.changed = 0, None

    def proof(self):
        self.proofs += 1
        return dict(own_gids={}, foreign_allowed=[], service_clients={})

    def poll(self):
        return self.changed


def make(tmp_path=None, **override):
    FakeHelper.instances.clear()
    events, faults = [], []
    services, window, graph = FakeServices(), FakeWindow(), FakeGraph()
    import tempfile
    directory = tempfile.mkdtemp(prefix='dmo')
    import os
    os.chmod(directory, 0o700)
    services.params['head_deadman_directory'] = directory
    keywords = dict(services=services, directory=directory, session_id='session-1', generation=7,
                    policy=policy(), node_name='head_run_r1', graph=graph, window=window,
                    helper_factory=FakeHelper, emit=lambda kind, record: events.append((kind, record)),
                    fault_callback=lambda code, evidence: faults.append((code, evidence)))
    keywords.update(override)
    owner = HeadNeckOwner(**keywords)
    return owner, services, window, graph, events, faults


def deadline(seconds=5.):
    return time.monotonic() + seconds


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
