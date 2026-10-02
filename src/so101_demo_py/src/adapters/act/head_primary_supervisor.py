"""Owned primary workers on the existing ROS node, SDK port and originals.

Calibration readiness is distinct from production qualification. No constructor,
heartbeat, or local inventory implicitly arms the native controller.
"""
from copy import deepcopy
import math
import threading
import time

from rclpy.clock import Clock, ClockType

from so101_demo.act.head_feedback import nanoseconds
from so101_demo.act.head_monitor import HeadMonitorEpoch, canonical_bytes
from .head_monitor_process import MonitorProcess
from .head_monitor_ros import HeadROSMonitor
from .head_monitor_runtime import HeadMonitorRuntime
from .head_original_router import HeadOriginalRouter
from .head_reservation_authority import HeadReservationAuthority
from .head_revocation import NativeRevocationClient
from .ros_execution import RosControllerPort


class HeadPrimarySupervisor:
    def __init__(self, *, node, port, router, monitor, revoker, epoch, generation,
                 session_id, policy_reference, policy_ack, configuration_ack,
                 stop_latency_s, camera_max_age_s, camera_frame_id, emit):
        if (not isinstance(port, RosControllerPort) or port.node is not node
                or port.feedback_policy is None or port.names != ('neck_yaw_joint',)
                or not isinstance(router, HeadOriginalRouter) or router.port is not port
                or not isinstance(monitor, MonitorProcess) or not monitor.is_alive()
                or type(revoker) is not NativeRevocationClient
                or revoker.timeout != .002 or revoker.generation != generation
                or not callable(emit)):
            raise ValueError('HEAD_PRIMARY_CONFIG_INVALID')
        self.node = node; self.port = port; self.router = router; self.monitor = monitor
        self.primary = deepcopy(monitor.identity)
        self.epoch = HeadMonitorEpoch(epoch=epoch, generation=generation, session_id=session_id)
        self._policy = deepcopy(policy_reference); self._sink = emit; self._revoker = revoker
        self._fault = None; self._native_close = None; self._native_close_error = None
        self._shutdown = threading.Event(); self._fault_event = threading.Event()
        self._stop_done = threading.Event(); self._close_done = threading.Event()
        self._fault_lock = threading.Lock(); self._deadline_lock = threading.Lock()
        self._inference_deadline = None; self._watchdog_wall = None
        self._started = False; self._finished = False; self._ready = False; self._arming = False
        self._threads = []; self.threads = self._threads; self.timer = None
        self._observer = None; self._started_wall = None
        if type(self._policy) is not dict or set(self._policy) != {'path', 'sha256'}:
            raise ValueError('HEAD_PRIMARY_POLICY_REFERENCE_INVALID')
        self._ack(policy_ack, 'POLICY_STATUS', 'POLICY_READY',
                  policy_sha256=self._policy['sha256'])
        self._ack(configuration_ack, 'CONFIGURATION', 'CONFIGURED')
        self._provisions = deepcopy(configuration_ack['provisions'])
        self._dependencies = deepcopy(configuration_ack['dependencies'])
        if (set(self._provisions) != {'main', 'primary_fault', 'monitor_fault'}
                or self._provisions['primary_fault']['socket_path'] != str(revoker.path)):
            raise PermissionError('HEAD_PRIMARY_PROVISION_SCOPE_INVALID')
        self.epoch.bind_policy(port.feedback_policy, self._policy['sha256'])
        self._observer = HeadROSMonitor(node, epoch=epoch, generation=generation,
            stop_velocity_rad_s=port.stop_velocity, stop_latency_s=stop_latency_s,
            camera_max_age_s=camera_max_age_s, camera_frame_id=camera_frame_id,
            emit=self._emit, fault_callback=self.fault, controller_port=port,
            monotonic=port.monotonic)
        router.bind_primary(self._observer)

    @property
    def observer(self): return self._observer

    @property
    def failed(self): return self._fault is not None or self.epoch.stage == 'REVOKED'

    @property
    def ready(self): return self._ready and not self.failed and not self._finished

    def _ack(self, reply, operation, stage, **fields):
        expected = dict(request=operation, stage=stage, epoch=self.epoch.epoch,
            generation=self.epoch.generation, session_id=self.epoch.session_id,
            monitor_peer=self.primary, purpose='calibration', motion_authority=False, **fields)
        if type(reply) is not dict or any(key not in reply or
                canonical_bytes(reply[key]) != canonical_bytes(value) for key, value in expected.items()):
            raise PermissionError('HEAD_PRIMARY_MONITOR_ACK_INVALID')

    def _emit(self, event, **fields):
        self._sink(event, **{'epoch': self.epoch.epoch, 'generation': self.epoch.generation, **fields})

    def fault(self, reason, wall=None):
        # Admission closes before waking either independent I/O worker.
        self.port._head_policy_binding_failed = True; self._ready = False
        if self._observer is not None: self._observer.failed = True
        wall = time.monotonic() if wall is None else wall
        with self._fault_lock:
            if self._fault is None or wall < self._fault['fault_wall_s']:
                self._fault = dict(reason=reason, fault_wall_s=wall)
            # Revoke the inventory epoch before waking the inventory consumer.
            # Registration's short commit lock cannot perform SDK/native I/O.
            self.epoch.revoke(reason, fault_wall_s=wall)
            self._fault_event.set()
            if self._observer is not None and self._observer._stop_started:
                self._observer.begin_stop(fault_wall_s=self._fault['fault_wall_s'])

    _close_native = HeadMonitorRuntime._close_native

    def _cancel_and_stop(self):
        self._fault_event.wait()
        if self._shutdown.is_set(): return
        # A local registration may fail after the epoch owns its UUID but before
        # the SDK port inserts it. Preserve that uncertainty in the stop inventory.
        for gid, record in self.epoch.inventory.items():
            with self.port._lock:
                if gid not in self.port._goals:
                    self.port._goals[gid] = dict(accepted=None, handle=None, result=None,
                        cancel_requested=False, cancel_ack=False, error=None,
                        primary_inventory=canonical_bytes(record))
        HeadMonitorRuntime._cancel_and_stop(self)

    def start(self):
        if self._started or self.failed or self._finished:
            raise PermissionError('HEAD_PRIMARY_START_REUSED')
        self._started = True
        try:
            self.timer = self.node.create_timer(.002, self.observer.executor_progress,
                clock=Clock(clock_type=ClockType.STEADY_TIME))
            self._started_wall = time.monotonic()
            for target, name in ((self._watchdog, 'watchdog'), (self._heartbeat, 'heartbeat'),
                    (self._close_native, 'native-close'), (self._cancel_and_stop, 'cancel-stop')):
                self._threads.append(threading.Thread(target=target, name='head-primary-'+name, daemon=True))
            for thread in self._threads: thread.start()
        except BaseException:
            self.fault('HEAD_PRIMARY_START_FAILED'); raise

    def _heartbeat(self):
        while not self._shutdown.is_set() and not self.failed:
            # Copy original progress before reading the observation clock.
            executor = self.observer._executor_wall
            with self._deadline_lock: deadline = self._inference_deadline
            now = time.monotonic()
            if executor is None:
                if now-self._started_wall > .010:
                    self.fault('HEAD_PRIMARY_EXECUTOR_STALE', self._started_wall+.010); return
                self._shutdown.wait(.002); continue
            record = dict(wall_s=now, executor_wall_s=executor, inference_deadline_wall_s=deadline)
            try:
                self.observer.heartbeat(record)
                stage = self.epoch.stage; arming = self._arming
                reply = self.monitor.request_runtime(dict(operation='HEARTBEAT', heartbeat=record))
                allowed = {stage, self.epoch.stage}
                if arming or self._arming: allowed.update(('POLICY_READY', 'ARMED_READY'))
                if reply.get('stage') not in allowed: raise PermissionError('HEAD_PRIMARY_HEARTBEAT_STAGE_INVALID')
                self._ack(reply, 'HEARTBEAT', reply['stage'])
            except BaseException:
                self.fault('HEAD_PRIMARY_HEARTBEAT_FAILED', now); return
            self._shutdown.wait(.002)

    def _watchdog(self):
        while not self._shutdown.is_set():
            previous = self._watchdog_wall; executor = self.observer._executor_wall
            heartbeat = self.observer._primary
            now = time.monotonic(); self._watchdog_wall = now
            try:
                if not self.monitor.is_alive(): self.fault('HEAD_PRIMARY_MONITOR_LOST', now)
                if previous is not None and now-previous > .010:
                    self.fault('HEAD_PRIMARY_WATCHDOG_GAP', previous+.010)
                if now-self._started_wall > .010:
                    if executor is None: self.fault('HEAD_PRIMARY_EXECUTOR_STALE', self._started_wall+.010)
                    elif not 0 <= now-executor <= .010:
                        self.fault('HEAD_PRIMARY_EXECUTOR_STALE', executor+.010)
                    if heartbeat is None: self.fault('HEAD_PRIMARY_HEARTBEAT_STALE', self._started_wall+.010)
                    elif not 0 <= now-heartbeat['wall_s'] <= .010:
                        self.fault('HEAD_PRIMARY_HEARTBEAT_STALE', heartbeat['wall_s']+.010)
                self.observer.poll()
            except BaseException: self.fault('HEAD_PRIMARY_WATCHDOG_FAILED', now)
            self._shutdown.wait(.002)

    def inference_deadline(self, value):
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
            self.fault('HEAD_PRIMARY_INFERENCE_DEADLINE_INVALID')
            raise ValueError('HEAD_PRIMARY_INFERENCE_DEADLINE_INVALID')
        with self._deadline_lock: self._inference_deadline = value

    def _current(self):
        tick = self._watchdog_wall; now = time.monotonic()
        if (not self._started or self.failed or self._finished or not self.monitor.is_alive()
                or tick is None or not 0 <= nanoseconds(now)-nanoseconds(tick) <= 10_000_000):
            crossing = now if tick is None else min(now, tick+.010)
            self.fault('HEAD_PRIMARY_CURRENT_GUARD_REFUSED', crossing)
            raise PermissionError('HEAD_PRIMARY_CURRENT_GUARD_REFUSED')
        self.observer.activate(watchdog=False)
        if self.failed or self.observer.failed:
            raise PermissionError('HEAD_PRIMARY_CURRENT_GUARD_REFUSED')
        return self.port.feedback_snapshot()

    def prearm_guard(self):
        try:
            if self.epoch.stage != 'POLICY_READY': raise PermissionError('HEAD_PRIMARY_PREARM_STAGE_INVALID')
            feedback = self._current()
            if any(abs(value) > self.port.stop_velocity for value in feedback['velocities']):
                raise PermissionError('HEAD_PRIMARY_PREARM_NOT_QUIET')
            reply = self.monitor.request_runtime(dict(operation='PREARM_READY',
                policy=dict(policy_sha256=self.epoch.policy_hash)))
            self._ack(reply, 'PREARM_READY', 'POLICY_READY',
                policy_sha256=self.epoch.policy_hash, current_inputs_guarded=True)
            if not 0 <= nanoseconds(time.monotonic())-nanoseconds(reply['ack_wall_s']) <= 10_000_000:
                raise PermissionError('HEAD_PRIMARY_PREARM_ACK_STALE')
            self._current()
            return True
        except Exception:
            self.fault('HEAD_PRIMARY_PREARM_REFUSED'); raise

    def arm(self, authority):
        try:
            if (not isinstance(authority, HeadReservationAuthority) or authority.arm_guard != self.prearm_guard
                    or authority.generation != self.epoch.generation
                    or authority.session_id != self.epoch.session_id
                    or authority.native_owner != self._revoker.native_owner
                    or str(authority._channel.path) != self._provisions['main']['socket_path']
                    or authority.fault_callback != self.fault or self.ready):
                raise PermissionError('HEAD_PRIMARY_MAIN_AUTHORITY_INVALID')
            self._arming = True
            authority.arm('neck')
            main = authority.identity('neck'); primary_receipt = self._revoker.identity()
            primary = {key: primary_receipt[key] for key in ('generation', 'incarnation', 'boot')}
            if main != primary: raise PermissionError('HEAD_PRIMARY_NATIVE_IDENTITY_MISMATCH')
            reports = {key: dict(identity=identity, native_owner=self._revoker.native_owner,
                provision_sha256=self._provisions[key]['sha256'])
                for key, identity in (('main', main), ('primary_fault', primary))}
            reply = self.monitor.request_runtime(dict(operation='ARMED_READY', identities=reports))
            self._ack(reply, 'ARMED_READY', 'ARMED_READY', identity=main,
                policy_sha256=self.epoch.policy_hash, provisions=self._provisions, dependencies=self._dependencies)
            self._current()
            self.epoch.armed_ready(main, primary); self._ready = True
            self._emit('ARMED_READY', ack=reply, primary_identity_receipt=primary_receipt)
            return deepcopy(main)
        except Exception:
            self.fault('HEAD_PRIMARY_ARM_REFUSED'); raise
        finally: self._arming = False

    def dispatch_guard(self):
        if not self.ready:
            self.fault('HEAD_PRIMARY_DISPATCH_NOT_READY'); raise PermissionError('HEAD_PRIMARY_DISPATCH_NOT_READY')
        self._current(); return self.ready

    def own_inventory(self, record, payload):
        try:
            self.dispatch_guard()
            self.epoch.register(record)
            return self.port.inventory_prepared(record, payload)
        except Exception:
            self.fault('HEAD_PRIMARY_INVENTORY_REFUSED'); raise

    def close(self):
        if self._finished: return deepcopy(self._receipt)
        self._ready = False
        if self.epoch.stage == 'ARMED_READY' and not self.failed: self.fault('HEAD_PRIMARY_OWNED_SHUTDOWN')
        if self.failed and self._started:
            self._stop_done.wait(self.observer.stop_latency+.010); self._close_done.wait(.010)
        self._shutdown.set(); self._fault_event.set()
        for thread in self._threads:
            if thread.ident is not None: thread.join(.2)
        if any(thread.is_alive() for thread in self._threads):
            raise PermissionError('HEAD_PRIMARY_WORKER_RETIRE_UNCONFIRMED')
        if self.timer is not None:
            if self.node.destroy_timer(self.timer) is not True:
                raise PermissionError('HEAD_PRIMARY_TIMER_RETIRE_UNCONFIRMED')
            self.timer = None
        # Retire routing before closing the shared observer. Remaining original
        # callbacks still reach the journal while the caller stops its executor.
        self.port._head_policy_binding_failed = True; self.observer.failed = True
        self.router.retire()
        retired = self.observer.close(timeout_s=.010)
        if (type(retired) is not dict or set(retired) != {'result', 'cancel'}
                or any(value.get('retired') is not True for value in retired.values())):
            raise PermissionError('HEAD_PRIMARY_ACTION_IO_RETIRE_UNCONFIRMED')
        self._receipt = dict(stage='RETIRED', motion_authority=False, fault=deepcopy(self._fault),
            native_close=self._native_close, native_close_error=self._native_close_error,
            workers=[dict(name=t.name, alive=t.is_alive()) for t in self._threads], action_io=retired,
            stop_observations=deepcopy(list(self.port.stop_predicate_observations)))
        self._finished = True
        return deepcopy(self._receipt)
