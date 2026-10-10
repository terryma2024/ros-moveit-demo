"""Fakes shared by the owner, dispatcher, runtime and runner tests: a controller manager that activates the
neck, a heartbeat helper that always connects, and a stop-window subscriber the test completes by hand."""

import re
import tempfile
import os
import threading
import time

from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
from so101_demo.adapters.act.head_neck_owner import HeadNeckOwner

CONTROLLER_TYPE = 'so101_mujoco_support/HeadNeckTrajectoryController'


def policy():
    return HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document())


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
    def __init__(self, auto=False):
        # auto: a rearm is answered by a completed window a few ms later (samples flowing)
        self.auto = auto
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
        if self.auto:
            first = (1_000_000_000 if floor_sim_ns is None else floor_sim_ns + 2_000_000)
            threading.Timer(.005, lambda: self.complete(first=first)).start()

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
    services, window, graph = FakeServices(), FakeWindow(auto=override.pop('auto_window', False)), FakeGraph()
    identity = override.pop('identity', None)
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
    if identity is not None:
        owner.identity = lambda: dict(identity)
    return owner, services, window, graph, events, faults


def deadline(seconds=5.):
    return time.monotonic() + seconds


