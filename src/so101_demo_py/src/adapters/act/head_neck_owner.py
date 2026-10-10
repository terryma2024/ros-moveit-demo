"""The owner's side of the Head neck protocol (design sections 1.3, 1.4, 3 and 4).

One object owns what the broker's reservation, witness and native-close stack used to own:

* the activation of ``HeadNeckTrajectoryController``: the heartbeat helper is started first (its pid is
  the controller's peer pid), the switch is planned in the event log, the pid parameter is set once, the
  controller is activated and the helper's connection to the new per-activation socket is awaited;
* the readback of the controller type and its immutable parameters, the dead-man record and the graph proof;
* the controller_state stop window (startup before the first goal, end after the raw stop) on its own
  subscriber;
* a monitor thread that faults the run on an unplanned controller switch, a deactivated or silent controller,
  and any change of the watched graph endpoints;
* the planned (or fault) close of the dead-man.

It grants no motion authority: the owner-only admission is the controller's, and the guard's.
"""

import hashlib
import os
import stat
import threading
import time
from types import SimpleNamespace

from so101_demo.act import head_neck_limits as limits

CONTROLLER = 'neck_controller'
CONTROLLER_TYPE = 'so101_mujoco_support/HeadNeckTrajectoryController'
#: the immutable configuration the controller must read back (design section 1.1)
EXPECTED_PARAMETERS = {
    'open_loop_control': False, 'interpolate_from_desired_state': False,
    'interpolation_method': 'splines', 'allow_partial_joints_goal': False,
    'allow_integration_in_goal_trajectories': False, 'joints': ['neck_yaw_joint'],
    'command_interfaces': ['position'], 'state_interfaces': ['position', 'velocity'],
    'speed_scaling.initial_scaling_factor': 1.0,
}
READBACK_PARAMETERS = tuple(EXPECTED_PARAMETERS) + (
    'head_deadman_directory', 'head_deadman_timeout_s', 'head_deadman_peer_pid', 'head_activation_id')
#: the runtime's progress must be at most this old for the owner to keep ticking the helper
LIVENESS_AGE_S = 0.1
#: the local claim window of one goal (the former reservation window)
_CLAIM_WINDOW_NS = 400_000_000


def _refuse(code, detail=''):
    raise PermissionError(f'{code}: {detail}' if detail else code)


class HeadNeckOwner:
    def __init__(self, *, services, directory, session_id, generation, policy, node_name, graph, window,
                 helper_factory, emit=None, fault_callback=None, monotonic=time.monotonic):
        self.directory = str(directory)
        info = os.lstat(self.directory) if os.path.lexists(self.directory) else None
        if info is None or not stat.S_ISDIR(info.st_mode):
            _refuse('HEAD_NECK_DIRECTORY_MISSING', self.directory)
        if info.st_uid != os.geteuid():
            _refuse('HEAD_NECK_DIRECTORY_OWNER', self.directory)
        if stat.S_IMODE(info.st_mode) != 0o700:
            _refuse('HEAD_NECK_DIRECTORY_MODE', self.directory)
        self.services, self.policy, self.graph, self.window = services, policy, graph, window
        self.session_id, self.generation, self.node_name = session_id, generation, node_name
        self._helper_factory, self._emit, self._fault_callback = helper_factory, emit, fault_callback
        self.monotonic = monotonic
        self._lock = threading.RLock()
        self._helper = None
        self._ticker = None
        self._activation_id = None
        self._expected_id = None
        self._planned_ids = set()
        self._closure = None
        self._liveness = None
        self._graph_proofed = False
        self._monitor = None
        self._stop_monitor = threading.Event()
        self._faulted = None
        self._close_receipt = None

    @staticmethod
    def ensure_directory(path):
        """Create the dead-man directory with mode 0700 before any activation (design section 1.4)."""
        os.makedirs(path, mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)
        return path

    # ---- activation -----------------------------------------------------------------------------------

    def _plan(self, action, old_id, new_id):
        with self._lock:
            self._planned_ids.add(new_id)
        if self._emit is not None:
            self._emit('CONTROLLER_SWITCH_PLANNED', dict(controller=CONTROLLER, action=action,
                                                         old_activation_id=old_id, new_activation_id=new_id))

    def plan_switch(self, *, old_activation_id, new_activation_id, action):
        """Write an expected deactivate/activate before it happens (the reset path)."""
        self._plan(action, old_activation_id, new_activation_id)

    def _alive(self):
        age = None if self._liveness is None else self._liveness()
        return age is None or age <= LIVENESS_AGE_S

    def bind_liveness(self, age_s):
        """After the runtime exists the owner keeps ticking only while ``age_s()`` (its progress age) is small."""
        if not callable(age_s):
            raise ValueError('HEAD_NECK_LIVENESS_INVALID')
        self._liveness = age_s

    def activate(self, *, deadline):
        with self._lock:
            if self._helper is not None:
                _refuse('HEAD_NECK_ALREADY_ACTIVE')
        previous = self.services.get_parameters(('head_activation_id',), deadline=deadline)['head_activation_id']
        new_id = int(previous) + 1
        helper = self._helper_factory(
            directory=self.directory, activation_id=new_id, connect_timeout_s=max(0.5, deadline - self.monotonic()),
            period_s=self.policy.head_deadman_period_s, liveness_s=self.policy.head_deadman_liveness_s)
        pid = helper.start()
        try:
            self.window.start()
            self._plan('ACTIVATE', int(previous), new_id)
            accepted, reason = self.services.set_integer('head_deadman_peer_pid', pid, deadline=deadline)
            if not accepted:
                _refuse('HEAD_NECK_PEER_PID_REFUSED', reason)
            if not self.services.switch(activate=(CONTROLLER,), deactivate=(), deadline=deadline):
                _refuse('HEAD_NECK_ACTIVATION_REFUSED')
            while True:
                row = self.services.controller(deadline=deadline)
                if row is not None and row['state'] == 'active':
                    break
                if self.monotonic() >= deadline:
                    raise TimeoutError('HEAD_NECK_ACTIVATION_TIMEOUT')
                time.sleep(.005)
            observed = self.services.get_parameters(('head_activation_id',), deadline=deadline)['head_activation_id']
            if observed != new_id:
                _refuse('HEAD_NECK_ACTIVATION_ID_MISMATCH', f'expected {new_id}, controller says {observed}')
            if not helper.wait_connected(max(0.1, deadline - self.monotonic())):
                _refuse('HEAD_NECK_DEADMAN_NOT_CONNECTED', str(helper.status))
            self._ticker = helper.start_ticker(period_s=self.policy.head_deadman_period_s, alive=self._alive)
        except BaseException:
            helper.kill()
            raise
        with self._lock:
            self._helper, self._activation_id, self._expected_id = helper, new_id, new_id
        return dict(activation_id=new_id, helper_pid=pid, socket_path=os.path.join(
            self.directory, f'neck-{new_id}.sock'))

    # ---- readback and arming ---------------------------------------------------------------------------------

    def readback(self, *, deadline):
        row = self.services.controller(deadline=deadline)
        values = self.services.get_parameters(READBACK_PARAMETERS, deadline=deadline)
        problems = []
        if row is None or row['type'] != CONTROLLER_TYPE:
            problems.append('controller_type')
        if row is None or row['state'] != 'active':
            problems.append('state')
        for name, expected in EXPECTED_PARAMETERS.items():
            if values.get(name) != expected:
                problems.append(name)
        with self._lock:
            helper, activation_id = self._helper, self._activation_id
        if helper is None or values.get('head_deadman_peer_pid') != helper.pid:
            problems.append('head_deadman_peer_pid')
        if values.get('head_activation_id') != activation_id:
            problems.append('head_activation_id')
        if values.get('head_deadman_directory') != self.directory:
            problems.append('head_deadman_directory')
        if problems:
            _refuse('HEAD_CONTROLLER_READBACK_INVALID', ', '.join(problems))
        return dict(controller=CONTROLLER, controller_type=row['type'], state=row['state'],
                    activation_id=activation_id, parameters=dict(values))

    def deadman_armed(self):
        with self._lock:
            helper, activation_id = self._helper, self._activation_id
        if helper is None:
            _refuse('HEAD_NECK_NOT_ACTIVE')
        return dict(socket_path=os.path.join(self.directory, f'neck-{activation_id}.sock'),
                    peer_pid=helper.pid, activation_id=activation_id,
                    head_deadman_period_s=self.policy.head_deadman_period_s,
                    head_deadman_timeout_s=self.policy.head_deadman_timeout_s)

    def identity(self):
        with self._lock:
            helper, activation_id = self._helper, self._activation_id
        if helper is None:
            _refuse('HEAD_NECK_NOT_ACTIVE')
        boot = hashlib.sha256(f'{self.session_id}|{self.generation}'.encode()).hexdigest()[:24]
        return dict(generation=self.generation, incarnation=f'act-{activation_id}-{helper.pid}',
                    boot=f'boot-{boot}')

    def admit_local(self, *, goal, goal_uuid, before_reserve):
        """The per-goal local claim that replaces the broker's reservation.

        The stock controller has no reservation. The owner builds the same claim binding the dispatcher
        registers in its typed inventory (400 ms window), voids the stop window (a goal is about to be sent)
        and refuses once the dead-man is closed or the owner has faulted. ``before_reserve`` registers the
        inventory; it must return True.
        """
        with self._lock:
            helper, closure, faulted = self._helper, self._closure, self._faulted
        if helper is None:
            _refuse('HEAD_NECK_NOT_ACTIVE')
        if closure is not None:
            _refuse('HEAD_NECK_CLOSED')
        if faulted is not None:
            _refuse('HEAD_NECK_FAULTED', faulted[0])
        identity = self.identity()
        now = time.monotonic_ns()
        binding = SimpleNamespace(
            role='neck', generation=self.generation, session_id=self.session_id, goal_cdr=bytes(goal),
            goal_uuid=bytes(goal_uuid), controller_incarnation=identity['incarnation'],
            controller_boot_incarnation=identity['boot'], claim_monotonic_ns=now,
            deadline_ns=now + _CLAIM_WINDOW_NS)
        self.note_goal()
        return before_reserve(binding) is True

    def graph_proof(self):
        proof = self.graph.proof()
        self._graph_proofed = True
        return proof

    # ---- the stop window ----------------------------------------------------------------------------------------

    def startup_stop_window(self, *, deadline, cancel_event=None):
        """A fresh, complete window collected after this call began; the owner sends no goal meanwhile."""
        self.window.rearm()
        while True:
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                raise TimeoutError('HEAD_STOP_WINDOW_UNAVAILABLE')
            if cancel_event is not None and cancel_event.is_set():
                raise TimeoutError('HEAD_STOP_WINDOW_CANCELLED')
            done = self.window.wait_completed(min(remaining, 0.05))
            if done is None:
                continue
            if time.monotonic_ns() - done['completed_mono_ns'] <= limits.STOP_WINDOW_MAX_AGE_NS:
                return dict(done)
            self.window.rearm()

    def note_goal(self):
        self.window.void('GOAL_SENT')

    def begin_end_window(self, *, raw_stop_sim_ns):
        self.window.rearm(floor_sim_ns=raw_stop_sim_ns)

    def end_stop_window(self, *, timeout_s):
        done = self.window.wait_completed(timeout_s)
        if done is None:
            raise TimeoutError('HEAD_STOP_WINDOW_UNAVAILABLE')
        return dict(done)

    def latest_controller_state(self):
        return self.window.latest()

    # ---- closing ---------------------------------------------------------------------------------------------------

    def _close_deadman(self, reason):
        with self._lock:
            if self._closure is not None:
                return dict(self._closure)
            helper, activation_id = self._helper, self._activation_id
        if helper is None:
            return dict(activation_id=None, helper_closed=False)
        closed = helper.close_planned()
        closure = dict(activation_id=activation_id, helper_closed=bool(closed))
        if reason is not None:
            closure['reason'] = reason
        with self._lock:
            self._closure = closure
        self._ticker = None
        return dict(closure)

    def close_planned(self):
        """The expected latch after the stop proof: the helper closes the socket and exits."""
        closure = self._close_deadman(None)
        return {key: value for key, value in closure.items() if key != 'reason'}

    def close_fault(self, reason):
        """Latch the controller at once (abort the goal and hold) without a stop proof."""
        return self._close_deadman(reason)

    # ---- monitor -----------------------------------------------------------------------------------------------------

    def _fault(self, code, evidence):
        with self._lock:
            if self._faulted is not None:
                return
            self._faulted = (code, evidence)
        if self._fault_callback is not None:
            self._fault_callback(code, evidence)

    def _check_controller(self):
        deadline = self.monotonic() + 0.5
        row = self.services.controller(deadline=deadline)
        if row is None or row['state'] != 'active':
            self._fault('HEAD_NECK_CONTROLLER_DEACTIVATED',
                        dict(state=None if row is None else row['state'], reason='NOT_ACTIVE'))
            return
        observed = self.services.get_parameters(('head_activation_id',), deadline=deadline)['head_activation_id']
        with self._lock:
            expected = self._expected_id
            planned = observed in self._planned_ids
        if observed != expected:
            if planned:
                with self._lock:
                    self._expected_id = observed
            else:
                self._fault('HEAD_UNPLANNED_CONTROLLER_SWITCH',
                            dict(expected_activation_id=expected, observed_activation_id=observed))
                return
        latest = self.window.latest()
        silent_ns = round(self.policy.head_stop_window_deadline_s * 1e9)
        if latest is not None and time.monotonic_ns() - latest['receive_mono_ns'] > silent_ns:
            self._fault('HEAD_NECK_CONTROLLER_DEACTIVATED',
                        dict(state='active', reason='CONTROLLER_STATE_SILENT'))

    def _monitor_loop(self, controller_period_s, graph_period_s):
        next_controller = self.monotonic()
        while not self._stop_monitor.wait(graph_period_s):
            try:
                if self._graph_proofed:
                    change = self.graph.poll()
                    if change is not None:
                        self._fault(change['code'], dict(added=change['added'], removed=change['removed']))
                if self.monotonic() >= next_controller:
                    next_controller = self.monotonic() + controller_period_s
                    self._check_controller()
            except Exception as error:
                self._fault('HEAD_NECK_MONITOR_FAILED', dict(error_type=type(error).__name__,
                                                             reason=str(error)[:200]))

    def start_monitor(self, *, controller_period_s=0.1, graph_period_s=None):
        graph_period_s = self.policy.watchdog_period_s if graph_period_s is None else graph_period_s
        with self._lock:
            if self._monitor is not None:
                _refuse('HEAD_NECK_MONITOR_ALREADY_STARTED')
            self._monitor = threading.Thread(target=self._monitor_loop, name='head-neck-owner-monitor',
                                             args=(controller_period_s, graph_period_s), daemon=True)
        self._monitor.start()

    @property
    def monitor_alive(self):
        return self._monitor is not None and self._monitor.is_alive()

    @property
    def faulted(self):
        return self._faulted

    def close(self):
        with self._lock:
            if self._close_receipt is not None:
                return dict(self._close_receipt)
        self._stop_monitor.set()
        if self._monitor is not None:
            self._monitor.join(2.)
        window = self.window.stop()
        helper = self._helper
        killed = False
        if helper is not None:
            helper.kill()
            killed = True
        receipt = dict(monitor_alive=self.monitor_alive, window=window, helper_killed=killed)
        with self._lock:
            self._close_receipt = receipt
        return dict(receipt)
