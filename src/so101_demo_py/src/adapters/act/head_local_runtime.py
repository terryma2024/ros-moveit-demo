"""Process-local Head admission, watchdog and independent stop workers.

The runtime owns local admission/readiness for the file-protocol Head attempt.
It keeps one shared ``HeadLocalState``, one shared ROS node/controller port and
one `HeadLocalObserver`, and it never allocates a motion client, controller
stack, model or monitor process.

Three threads are started explicitly by :meth:`start` and never by a
constructor: a genuine watchdog and two independent stop workers (native close,
cancel/raw-stop). Constructors do not arm or grant motion; :meth:`arm` performs
the real pre-arm checks and binds the authenticated main/primary-fault identity
against the local scope.

A refusal during pre-arm is not a fault: no motion authority exists yet, so the
attempt stays open for a corrected pre-arm. Every other boundary failure
(invalid original, writer enqueue failure, native mismatch, watchdog/job expiry,
dispatch/inventory failure, signal or normal stop) latches the first immutable
``HeadLocalState`` fault occurrence before diagnostics, logging or native work
and wakes the stop workers.
"""

import hashlib
import math
import threading
import time

from so101_demo.act.head_evidence_identity import canonical_bytes, digest
from so101_demo.act.head_feedback import decision_clocks, nanoseconds
from so101_demo.act.head_local_state import HeadLocalState
from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
from .head_local_observer import HeadLocalObserver
from .ros_execution import RosControllerPort


STOP_ORIGINS = ('success', 'not_found', 'budget', 'camera', 'feedback', 'writer', 'unknown',
                'sigterm', 'signal', 'fault')
_WATCHDOG_GAP_HISTORY = 64


class HeadStartupCancelled(RuntimeError):
    """Operator cancellation before startup can publish readiness."""



def _identity_triple(value):
    if (type(value) is not dict
            or type(value.get('generation')) is not int
            or any(type(value.get(key)) is not str for key in ('incarnation', 'boot'))):
        raise PermissionError('HEAD_LOCAL_RUNTIME_NATIVE_IDENTITY_INVALID')
    return {key: value[key] for key in ('generation', 'incarnation', 'boot')}


class LocalHeadScope:
    """Read-only local scope view for callers that used to read a monitor epoch.

    It exposes exactly the frozen local scope plus the live local inventory; it
    carries no monitor stage machine, no ACK and no registration path.
    """

    __slots__ = ('_state', 'stage')

    def __init__(self, local_state, stage):
        self._state = local_state
        self.stage = stage

    @property
    def epoch(self):
        return self._state.scope['epoch']

    @property
    def generation(self):
        return self._state.scope['generation']

    @property
    def session_id(self):
        return self._state.scope['session_id']

    @property
    def policy_hash(self):
        return self._state.scope['policy_sha256']

    @property
    def inventory(self):
        return self._state.inventory

    def readback(self):
        return dict(epoch=self.epoch, generation=self.generation, session_id=self.session_id,
                    policy_hash=self.policy_hash, stage=self.stage,
                    inventory=sorted(self.inventory))


class HeadLocalRuntime:
    """Local admission and stop ownership for one file-protocol Head attempt."""

    def __init__(self, *, node, port, local_state, revoker, observer, policy, authority=None,
                 sink=None, emit=None, monotonic=None, clock_ns=None):
        if (type(port) is not RosControllerPort or port.node is not node
                or type(local_state) is not HeadLocalState
                or type(observer) is not HeadLocalObserver or observer.port is not port
                or observer.local_state is not local_state
                or type(policy) is not HeadSimulationPolicy or observer.policy is not policy
                or local_state.scope['policy_sha256'] != digest(policy.readback())):
            raise ValueError('HEAD_LOCAL_RUNTIME_CONFIG_INVALID')
        if port.feedback_policy is None or port._head_policy_binding_failed:
            raise PermissionError('HEAD_LOCAL_RUNTIME_POLICY_REQUIRED')
        if any(not callable(getattr(revoker, name, None)) for name in ('close_scoped_strict', 'bootstrap_identity', 'identity')):
            raise ValueError('HEAD_LOCAL_RUNTIME_REVOKER_INVALID')
        if (type(getattr(revoker, 'generation', None)) is not int
                or not 0 < revoker.generation < 2 ** 64
                or type(getattr(revoker, 'native_owner', None)) is not dict
                or set(revoker.native_owner) != {'uid', 'pid', 'start_ticks'}
                or any(type(value) is not int for value in revoker.native_owner.values())
                or type(getattr(revoker, 'transport_origin', None)) is not dict):
            raise ValueError('HEAD_LOCAL_RUNTIME_REVOKER_SCOPE_INVALID')
        if sink is not None and not callable(sink):
            raise ValueError('HEAD_LOCAL_RUNTIME_SINK_INVALID')
        if emit is not None and not callable(emit):
            raise ValueError('HEAD_LOCAL_RUNTIME_EMIT_INVALID')
        if monotonic is not None and not callable(monotonic):
            raise ValueError('HEAD_LOCAL_RUNTIME_CLOCK_INVALID')
        if clock_ns is not None and not callable(clock_ns):
            raise ValueError('HEAD_LOCAL_RUNTIME_CLOCK_INVALID')
        if port._head_fault_callback is not None:
            raise PermissionError('HEAD_LOCAL_RUNTIME_PORT_FAULT_OWNER_EXISTS')
        self.node = node
        self.port = port
        self.local_state = local_state
        self.revoker = revoker
        self.observer = observer
        self.policy = policy
        # Consumers that used to read a monitor-owned policy read this exact
        # frozen local policy object; there is no second policy source.
        self._simulation_policy = policy
        self.monotonic = time.monotonic if monotonic is None else monotonic
        self.clock_ns = time.monotonic_ns if clock_ns is None else clock_ns
        self._sink = sink
        self._emit = emit
        self._lock = threading.Lock()
        self._arm_in_progress = False
        self._startup_cancel_event = None
        self._stop_event = threading.Event()
        self._shutdown = threading.Event()
        self._started = False
        self._closed = False
        self._workers_retired = False
        self._admission_open = True
        self._faulted = False
        self._fault_report_claimed = False
        self._fault_reason = None
        self._fault_occurred_ns = None
        self._refused_reason = None
        self._armed_identity = None
        self._bootstrap_identity = None
        self._native_policy_receipt = None
        self._authority = None
        self._threads = {}
        self._watchdog_wall = None
        self._executor_wall = None
        self._watchdog_gaps = [] if sink is not None else ()
        self._inference_deadline_wall_s = None
        self._inference_deadlines = [] if sink is not None else ()
        self._observation_deadline_wall_s = None
        self._owned = set()
        self._stop_origin_kind = None
        self._stop_origin_wall_s = None
        self._stop_deadline_wall_s = None
        self._stop_request_wall_s = None
        self._stop_request_sim_s = None
        self._native_close = dict(requested_wall_s=None, finished=False, ack=False,
                                  error=None, receipt=None)
        self._cancel_stop = dict(started_wall_s=None, finished=False, cancel_error=None,
                                 raw_stop_confirmed=False, raw_stop_observations=(),
                                 deadline_wall_s=None, abandoned_on_retirement=False)
        if observer._fault_callback is None:
            observer.bind_fault_callback(self.fault)
        elif observer._fault_callback != self.fault:
            raise PermissionError('HEAD_LOCAL_RUNTIME_OBSERVER_FAULT_OWNER_EXISTS')
        port._head_fault_callback = self.fault
        if sink is not None:
            port.bind_head_action_sink(self.record)
        if authority is not None:
            self.bind_authority(authority)

    # ---- ownership ---------------------------------------------------------

    @property
    def started(self):
        return self._started

    @property
    def armed(self):
        return self._armed_identity is not None

    @property
    def ready(self):
        """True only while started, armed, admission-open and neither faulted nor closed."""
        with self._lock:
            return (self._started and self._armed_identity is not None
                    and self._admission_open and not self._faulted and not self._closed)

    @property
    def failed(self):
        return self._faulted

    def _local_stage(self):
        with self._lock:
            if self._closed:
                return 'LOCAL_CLOSED'
            if self._faulted:
                return 'LOCAL_FAULTED'
            if self._armed_identity is not None:
                return 'LOCAL_ARMED'
            return 'LOCAL_OPEN'

    @property
    def epoch(self):
        """The frozen local scope and live inventory in the shape the D callers read."""
        return LocalHeadScope(self.local_state, self._local_stage())

    @property
    def faulted(self):
        return self._faulted

    @property
    def fault_reason(self):
        return self._fault_reason

    @property
    def dispatch_guard_refused_reason(self):
        return self._refused_reason

    @property
    def stop_requested(self):
        return self._stop_event.is_set()

    def bind_authority(self, authority):
        """Bind the authenticated main authority and its exact local scope once."""
        if any(not callable(getattr(authority, name, None))
               for name in ('arm', 'prearm_status', 'identity', 'close')):
            raise ValueError('HEAD_LOCAL_RUNTIME_AUTHORITY_INVALID')
        scope = self.local_state.scope
        if (getattr(authority, 'generation', None) != scope['generation']
                or getattr(authority, 'session_id', None) != scope['session_id']
                or getattr(authority, 'native_owner', None) != self.revoker.native_owner
                or getattr(authority, 'arm_guard', None) != self.prearm_guard
                or getattr(authority, 'fault_callback', None) != self.fault):
            raise PermissionError('HEAD_LOCAL_RUNTIME_AUTHORITY_SCOPE_INVALID')
        with self._lock:
            if self._closed:
                raise PermissionError('HEAD_LOCAL_RUNTIME_CLOSED')
            if self._authority is not None:
                raise PermissionError('HEAD_LOCAL_RUNTIME_AUTHORITY_REBOUND')
            self._authority = authority
        return True

    def start(self):
        """Start the watchdog and the two independent stop workers exactly once."""
        with self._lock:
            if self._closed:
                raise PermissionError('HEAD_LOCAL_RUNTIME_CLOSED')
            if self._started:
                raise PermissionError('HEAD_LOCAL_RUNTIME_ALREADY_STARTED')
            self._started = True
            now = self.monotonic()
            self._watchdog_wall = now
            self._executor_wall = now
            threads = {
                'watchdog': threading.Thread(target=self._watchdog_loop, daemon=True,
                                             name='head-local-watchdog'),
                'native_close': threading.Thread(target=self._native_close_loop, daemon=True,
                                                 name='head-local-native-close'),
                'cancel_stop': threading.Thread(target=self._cancel_stop_loop, daemon=True,
                                                name='head-local-cancel-stop'),
            }
            self._threads = dict(threads)
        for thread in threads.values():
            thread.start()
        return dict(watchdog_started=threads['watchdog'].is_alive(),
                    workers=['native_close', 'cancel_stop'],
                    threads={name: thread.ident for name, thread in threads.items()})

    # ---- local admission ---------------------------------------------------

    def executor_progress(self):
        """Mark real local executor progress; polling cannot substitute for it."""
        with self._lock:
            self._executor_wall = self.monotonic()

    def _refuse(self, reason, *, faults=True):
        with self._lock:
            self._refused_reason = reason
        if faults:
            self.fault(reason)
        raise PermissionError(reason)

    def prearm_guard(self):
        """Real pre-arm checks; a refusal here does not latch a fault origin."""
        with self._lock:
            state_open = (self._started and self._admission_open and not self._faulted
                          and not self._closed)
            native_policy_bound = self._native_policy_receipt is not None
        if not state_open:
            self._refuse('HEAD_LOCAL_RUNTIME_PREARM_STATE_INVALID', faults=False)
        if not native_policy_bound:
            self._refuse('HEAD_LOCAL_RUNTIME_NATIVE_POLICY_REQUIRED', faults=False)
        feedback = self._current(require_armed=False, refusal_faults=False)
        if any(abs(value) > self._port_stop_velocity() for value in feedback['velocities']):
            self._refuse('HEAD_LOCAL_RUNTIME_PREARM_NOT_QUIET', faults=False)
        return True

    def bind_native_policy_readback(self, receipt):
        """Validate one immutable readonly query before granting native ARM."""
        from .head_native_policy_readback import validate_native_policy_receipt
        import json
        body = canonical_bytes(receipt)
        owned = json.loads(body)
        validate_native_policy_receipt(owned, self.policy,
                                       reader_node=self.node.get_fully_qualified_name())
        with self._lock:
            if self._closed or self._faulted or self._armed_identity is not None:
                raise PermissionError('HEAD_LOCAL_RUNTIME_STATE_INVALID')
            if self._native_policy_receipt is not None:
                raise PermissionError('HEAD_LOCAL_RUNTIME_NATIVE_POLICY_REBOUND')
            self._native_policy_receipt = body
        if self._sink is not None:
            self.record('NATIVE_POLICY_VERIFIED', owned)
        return True

    def _port_stop_velocity(self):
        return self.port.stop_velocity

    def arm(self, *, cancel_event=None):
        """One bounded startup, with a separately authenticated close identity."""
        cancel_event=threading.Event() if cancel_event is None else cancel_event
        if not isinstance(cancel_event,threading.Event):
            raise ValueError('HEAD_STARTUP_CANCEL_EVENT_INVALID')
        with self._lock:
            if self._arm_in_progress:
                raise PermissionError('HEAD_LOCAL_RUNTIME_ARM_IN_PROGRESS')
            self._arm_in_progress=True
            self._startup_cancel_event=cancel_event
        try:
            return self._arm_once(cancel_event)
        finally:
            with self._lock:
                self._arm_in_progress=False
                self._startup_cancel_event=None

    def _startup_check(self, cancel_event, deadline, *, ready_wait=False):
        if cancel_event.is_set():raise HeadStartupCancelled('HEAD_STARTUP_CANCELLED')
        if self.clock_ns()>=deadline:
            raise TimeoutError('PREARM_READY_DEADLINE' if ready_wait else 'HEAD_STARTUP_DEADLINE_EXPIRED')

    def _arm_once(self, cancel_event):
        deadline=self.clock_ns()+2_000_000_000
        with self._lock:
            authority=self._authority
            if self._closed:raise PermissionError('HEAD_LOCAL_RUNTIME_CLOSED')
            if self._armed_identity is not None:raise PermissionError('HEAD_LOCAL_RUNTIME_ALREADY_ARMED')
            if self._faulted or not self._admission_open:
                raise PermissionError('HEAD_LOCAL_RUNTIME_STATE_INVALID')
        if authority is None:raise PermissionError('HEAD_LOCAL_RUNTIME_AUTHORITY_UNBOUND')
        # A local precondition refusal remains correctable before native startup.
        self.prearm_guard()
        def check(*,ready_wait=False):
            self._startup_check(cancel_event,deadline,ready_wait=ready_wait)
            self.prearm_guard()
            self._startup_check(cancel_event,deadline,ready_wait=ready_wait)
        try:
            from .head_control_protocol import identity_fields
            check()
            bootstrap=self.revoker.bootstrap_identity(overall_deadline_ns=deadline)
            pinned=identity_fields(bootstrap,self.local_state.scope['generation'])
            expected=self.local_state.scope['controller_identity']
            if bootstrap.get('ack_validated') is not True or bootstrap.get('status')!='AVAILABLE' or (
                    expected is not None and _identity_triple(pinned)!=expected):
                raise PermissionError('HEAD_LOCAL_RUNTIME_BOOTSTRAP_IDENTITY_MISMATCH')
            if self.clock_ns()>=deadline:raise TimeoutError('HEAD_STARTUP_DEADLINE_EXPIRED')
            with self._lock:
                self._bootstrap_identity=dict(pinned)
            if self._sink is not None:self.record('BOOTSTRAP_IDENTITY',dict(bootstrap))
            check()
            for attempt in range(16):
                check(ready_wait=True)
                status=authority.prearm_status('neck',overall_deadline_ns=deadline,expected_identity=dict(pinned))
                self._startup_check(cancel_event,deadline,ready_wait=True)
                if identity_fields(status,self.local_state.scope['generation'])!=pinned:
                    raise PermissionError('HEAD_LOCAL_RUNTIME_PREARM_IDENTITY_MISMATCH')
                if self._sink is not None:self.record('PREARM_STATUS',dict(status))
                check(ready_wait=True)
                if status['status']=='READY':break
                if status['status']!='NOT_READY':raise PermissionError('HEAD_LOCAL_RUNTIME_PREARM_SCOPE_REFUSED')
                if status['proof']['wrapper_reason']==8:
                    raise PermissionError('HEAD_LOCAL_RUNTIME_SNAPSHOT_UNAVAILABLE')
                remaining=(deadline-self.clock_ns())*1e-9
                if remaining<=.125 or attempt==15:raise TimeoutError('PREARM_READY_DEADLINE')
                if cancel_event.wait(.125):raise HeadStartupCancelled('HEAD_STARTUP_CANCELLED')
                self._startup_check(cancel_event,deadline,ready_wait=True)
            check()
            try:
                authority.arm('neck',overall_deadline_ns=deadline)
            except Exception as error:
                if cancel_event.is_set():
                    if self._sink is not None:
                        self.record('ARM_RESULT',getattr(error,'record',None) or dict(
                            status='UNKNOWN',reason=getattr(error,'code',str(error)[:256])))
                    raise HeadStartupCancelled('HEAD_STARTUP_CANCELLED') from error
                self.fault('HEAD_LOCAL_RUNTIME_NATIVE_STARTUP_FAILED',
                    {'error_type':type(error).__name__,'reason':str(error)[:256]})
                if self._sink is not None:
                    self.record('ARM_RESULT',getattr(error,'record',None) or dict(
                        status='UNKNOWN',reason=getattr(error,'code',str(error)[:256])))
                raise
            if self._sink is not None:
                result=getattr(authority,'last_arm_result',None)
                if result is not None:self.record('ARM_RESULT',dict(result))
            check()
            main=_identity_triple(authority.identity('neck',overall_deadline_ns=deadline))
            check()
            primary=_identity_triple(self.revoker.identity(overall_deadline_ns=deadline))
            check()
            if main!=primary or main!=_identity_triple(pinned):
                raise PermissionError('HEAD_LOCAL_RUNTIME_NATIVE_IDENTITY_MISMATCH')
            # This records the native ARM identity; publish runtime readiness
            # only after diagnostics return and the startup fence still holds.
            if self._sink is not None:self.record('ARMED',dict(identity=dict(main)))
            with self._lock:
                self._startup_check(cancel_event,deadline)
                if self._closed or self._faulted or not self._admission_open:
                    raise PermissionError('HEAD_LOCAL_RUNTIME_STATE_INVALID')
                if expected is None:self.local_state.bind_controller_identity(main,primary)
                if self.local_state.faulted:raise PermissionError('HEAD_LOCAL_STATE_FAULTED')
                self._startup_check(cancel_event,deadline)
                self._armed_identity=dict(main)
        except HeadStartupCancelled:
            self.stop('sigterm',dict(startup_cancelled=True))
            raise
        except Exception as error:
            if cancel_event.is_set():
                self.stop('sigterm',dict(startup_cancelled=True,error_type=type(error).__name__,
                                        reason=str(error)[:256]))
                raise HeadStartupCancelled('HEAD_STARTUP_CANCELLED') from error
            self.fault('HEAD_LOCAL_RUNTIME_NATIVE_STARTUP_FAILED',
                       {'error_type':type(error).__name__,'reason':str(error)[:256]})
            raise
        return dict(main)

    def _current(self, *, require_armed=True, refusal_faults=True):
        with self._lock:
            tick, progress = self._watchdog_wall, self._executor_wall
            started, open_ = self._started, self._admission_open
            faulted = self._faulted
            armed = self._armed_identity is not None
            observation_deadline = self._observation_deadline_wall_s
        # Sample after each snapshot: callbacks may have advanced its receipt
        # during this read. An earlier clock would give fresh data a negative age.
        now = self.monotonic()
        if not started or faulted or not open_:
            self._refuse('HEAD_LOCAL_RUNTIME_STATE_INVALID', faults=refusal_faults)
        limit = nanoseconds(self.policy.fault_reaction_limit_s)
        gap = None if tick is None else nanoseconds(now) - nanoseconds(tick)
        if gap is None or gap < 0 or gap > limit:
            self._refuse('HEAD_LOCAL_RUNTIME_WATCHDOG_STALLED', faults=refusal_faults)
        if require_armed and not armed:
            raise PermissionError('HEAD_LOCAL_RUNTIME_NOT_ARMED')
        if progress is None or not 0 <= nanoseconds(now) - nanoseconds(progress) < limit:
            self._refuse('HEAD_LOCAL_RUNTIME_EXECUTOR_STALLED', faults=refusal_faults)
        if nanoseconds(now) >= self.local_state.search_deadline_ns:
            self._refuse('HEAD_LOCAL_RUNTIME_SEARCH_EXPIRED', faults=refusal_faults)
        if (observation_deadline is not None
                and nanoseconds(now) >= nanoseconds(observation_deadline)):
            self._refuse('HEAD_LOCAL_RUNTIME_OBSERVATION_EXPIRED', faults=refusal_faults)
        try:
            current = self.observer.current_inputs(now)
        except Exception:
            self._refuse('HEAD_LOCAL_RUNTIME_ORIGINALS_INVALID', faults=refusal_faults)
        now = self.monotonic()
        image_wall = current['image_source_wall_s']
        if (image_wall is None
                or not 0 <= now - image_wall <= self.policy.camera_loss_timeout_s
                or not 0 <= now - current['image']['wall_s'] <= self.policy.camera_source_age_s):
            self._refuse('HEAD_LOCAL_RUNTIME_CAMERA_STALE', faults=refusal_faults)
        try:
            joint_candidates = self.observer.admission_joint_candidates()
            feedback = self.port.feedback_snapshot()
            # Admission must still receive its own original JOINT stream.
            # Fresh raw Stop feedback cannot renew an older routed sample.
            from .ros_execution import _causal_current_original
            admission_joint = _causal_current_original(
                joint_candidates, feedback['decision']['sim_ns'])
            self.port.feedback_policy.check_joint(admission_joint, feedback['decision'])
        except Exception:
            self._refuse('HEAD_LOCAL_RUNTIME_FEEDBACK_STALE', faults=refusal_faults)
        now = self.monotonic()
        # Later reads never renew the absolute budgets checked at entry.
        if nanoseconds(now) >= self.local_state.search_deadline_ns:
            self._refuse('HEAD_LOCAL_RUNTIME_SEARCH_EXPIRED', faults=refusal_faults)
        if (observation_deadline is not None
                and nanoseconds(now) >= nanoseconds(observation_deadline)):
            self._refuse('HEAD_LOCAL_RUNTIME_OBSERVATION_EXPIRED', faults=refusal_faults)
        clock_age_ns = (nanoseconds(feedback['decision']['wall_after_s'])
                        - nanoseconds(current['clock']['wall_s']))
        if not 0 <= clock_age_ns <= math.floor(
                self.port.feedback_policy.clock_interarrival_deadline_s * 1e9):
            self._refuse('HEAD_LOCAL_RUNTIME_CLOCK_STALE', faults=refusal_faults)
        if not 0 <= now - feedback['wall_s'] <= self.policy.feedback_receipt_timeout_s:
            self._refuse('HEAD_LOCAL_RUNTIME_FEEDBACK_STALE', faults=refusal_faults)
        return feedback

    def dispatch_guard(self):
        """Authenticate the last local boundary before a prepared SDK send."""
        self._current(require_armed=True)
        return True

    def own_inventory(self, record, payload):
        """Validate the existing local record/CDR and hand it to the real port once."""
        try:
            self.dispatch_guard()
            if type(record) is not dict or type(payload) is not bytes:
                raise ValueError('HEAD_LOCAL_INVENTORY_INPUT_INVALID')
            gid = record.get('goal_uuid')
            if type(gid) is not str:
                raise ValueError('HEAD_LOCAL_INVENTORY_INPUT_INVALID')
            with self._lock:
                if gid in self._owned:
                    raise PermissionError('HEAD_LOCAL_INVENTORY_DUPLICATE')
            held = self.local_state.inventory.get(gid)
            if held is None or canonical_bytes(held) != canonical_bytes(record):
                raise PermissionError('HEAD_LOCAL_INVENTORY_RECORD_MISMATCH')
            if (self.local_state.prepared_cdr(gid) != payload
                    or hashlib.sha256(payload).hexdigest() != record.get('payload_sha256')):
                raise PermissionError('HEAD_LOCAL_INVENTORY_CDR_MISMATCH')
            if self.port.inventory_prepared(record, payload) is not True:
                raise PermissionError('HEAD_LOCAL_INVENTORY_REFUSED')
            with self._lock:
                self._owned.add(gid)
            if self._sink is not None:
                self.record('INVENTORY_OWNED', dict(goal_uuid=gid,
                                                    payload_sha256=record['payload_sha256']))
            return True
        except Exception:
            self.fault('HEAD_LOCAL_INVENTORY_REFUSED')
            raise

    def dispatch_observation_deadline(self, value):
        """One pending selected-exposure deadline: no extension, no empty clear.

        A pending deadline may be cleared once and a later one armed again, but
        it can never be pushed out, armed over a pending one, or re-armed after
        it has already expired. Any of those is a hard local fault.
        """
        refusal = None
        if (value is not None and (type(value) not in (int, float)
                                   or not math.isfinite(value) or value <= 0)):
            refusal = 'HEAD_LOCAL_SELECTED_EXPOSURE_REFUSED'
        else:
            with self._lock:
                previous = self._observation_deadline_wall_s
                now = self.monotonic()
                if (self._faulted or self._closed
                        or (previous is not None and now >= previous)
                        or (value is not None and (previous is not None or now >= value))
                        or (value is None and previous is None)):
                    refusal = 'HEAD_LOCAL_SELECTED_EXPOSURE_REFUSED'
                else:
                    self._observation_deadline_wall_s = value
        if refusal is not None:
            self.fault(refusal)
            raise PermissionError(refusal)
        return True

    def inference_deadline(self, value):
        """Arm one bounded inference deadline, or discharge it with None.

        A new deadline may never be later than the pending one, and a pending
        deadline is never silently replaced; discharging it (None) is how the
        owning worker completes its job and is retained as a bounded tombstone.
        """
        refusal = None
        if (value is not None and (type(value) not in (int, float)
                                   or not math.isfinite(value) or value <= 0)):
            refusal = 'HEAD_LOCAL_INFERENCE_DEADLINE_INVALID'
        else:
            with self._lock:
                previous = self._inference_deadline_wall_s
                if (self._faulted or self._closed
                        or (value is not None and previous is not None and value > previous)):
                    refusal = 'HEAD_LOCAL_INFERENCE_DEADLINE_EXTENDED'
                else:
                    if value is None and previous is not None and self._sink is not None:
                        self._inference_deadlines.append(previous)
                        del self._inference_deadlines[:-2]
                    self._inference_deadline_wall_s = value
        if refusal == 'HEAD_LOCAL_INFERENCE_DEADLINE_INVALID':
            self.fault(refusal)
            raise ValueError(refusal)
        if refusal is not None:
            self.fault(refusal)
            raise PermissionError(refusal)
        return True

    # ---- first fault and stop ---------------------------------------------

    def record(self, kind, payload, source_stamp_ns=None):
        """Enqueue bounded evidence; a failing sink is a hard local fault."""
        if self._sink is None:
            return None
        try:
            return self._sink(kind, payload, source_stamp_ns)
        except Exception as error:
            self.fault('HEAD_LOCAL_WRITER_ENQUEUE_FAILED', {'error': type(error).__name__})
            raise PermissionError('HEAD_LOCAL_WRITER_ENQUEUE_FAILED') from error

    def _begin_stop(self, kind, *, origin_wall_s=None, clocks=None):
        """Begin the one physical stop from its immutable original origin."""
        with self._lock:
            first = self._stop_origin_wall_s is None
            if first:
                if origin_wall_s is None:
                    origin_wall_s = self.monotonic()
                self._stop_origin_kind = kind
                self._stop_origin_wall_s = float(origin_wall_s)
            elif origin_wall_s is not None and origin_wall_s < self._stop_origin_wall_s:
                self._stop_origin_wall_s = float(origin_wall_s)
            origin = self._stop_origin_wall_s
            self._stop_deadline_wall_s = origin + self.policy.stop_confirmation_timeout_s
        if first:
            if clocks is None:
                clocks = decision_clocks(self.node, self.monotonic)
            if clocks['wall_after_s'] < origin:
                self.fault('HEAD_LOCAL_RUNTIME_CLOCK_DOMAIN_MISMATCH')
                raise PermissionError('HEAD_LOCAL_RUNTIME_CLOCK_DOMAIN_MISMATCH')
            epoch = dict(epoch=self.local_state.scope['epoch'] + '-stop',
                         generation=self.local_state.scope['generation'],
                         request_wall_s=clocks['wall_after_s'], request_sim_s=clocks['sim_s'],
                         fault_wall_s=origin,
                         stop_latency_s=self.policy.stop_confirmation_timeout_s)
            self.port.begin_stop(epoch)
            with self._lock:
                self._stop_request_wall_s = epoch['request_wall_s']
                self._stop_request_sim_s = epoch['request_sim_s']
        else:
            self.port.tighten_stop_fault(origin)

    def fault(self, reason, evidence=None):
        """Latch the first immutable origin, close admission and wake both workers."""
        if type(reason) is not str or not reason:
            raise ValueError('HEAD_LOCAL_FAULT_INVALID')
        # A cancelled startup channel still revokes its local authority; its
        # callback must not replace the operator's immutable stop origin.
        with self._lock:
            startup_cancelled=(reason=='HEAD_MAIN_AUTHORITY_FAILED' and self._arm_in_progress
                and self._startup_cancel_event is not None and self._startup_cancel_event.is_set()
                and not self._faulted)
        if startup_cancelled:
            return self.stop('sigterm',dict(startup_cancelled=True,channel_error=reason))
        token = self.local_state.latch_fault(reason)
        occurred_ns = self.local_state.fault_occurrence_ns
        with self._lock:
            if not self._faulted:
                self._faulted = True
                self._fault_reason = reason
                self._fault_occurred_ns = occurred_ns
            self._admission_open = False
            self._refused_reason = 'HEAD_LOCAL_RUNTIME_FAULTED'
            first_reason, first_ns = self._fault_reason, self._fault_occurred_ns
            existing_origin = self._stop_origin_wall_s
            report_fault = not self._fault_report_claimed
            self._fault_report_claimed = True
        origin = None if occurred_ns is None else occurred_ns * 1e-9
        if existing_origin is not None and (origin is None or existing_origin < origin):
            origin = existing_origin
        self._begin_stop('fault', origin_wall_s=origin)
        self._stop_event.set()
        if token is not None:
            document = {'reason': reason} if evidence is None else dict(evidence, reason=reason)
            try:
                self.local_state.finish_fault(token, document)
            except Exception:
                pass
        if report_fault:
            # Claim before calling the sink. A broken sink may itself call
            # fault(), but can never reenter fault reporting or shift origin.
            try:
                if self._sink is not None:
                    self.record('FAULT', dict(reason=first_reason, occurred_ns=first_ns))
            except Exception:
                pass
        return dict(self.fault_receipt(), first=token is not None)

    def stop(self, origin, evidence=None):
        """Normal success/not-found stop with its own immutable first request origin."""
        if origin not in STOP_ORIGINS:
            raise ValueError('HEAD_LOCAL_STOP_ORIGIN_INVALID')
        with self._lock:
            if self._closed:
                raise PermissionError('HEAD_LOCAL_RUNTIME_CLOSED')
            self._admission_open = False
            first = self._stop_origin_wall_s is None
        clocks = decision_clocks(self.node, self.monotonic) if first else None
        self._begin_stop(origin, origin_wall_s=None if clocks is None else clocks['wall_after_s'],
                         clocks=clocks)
        self._stop_event.set()
        try:
            if self._sink is not None:
                self.record('STOP_REQUEST', dict(origin=origin, evidence=evidence))
        except Exception:
            pass
        return self.stop_receipt()

    def _stop_snapshot(self):
        with self._lock:
            return dict(stop_origin_kind=self._stop_origin_kind,
                        stop_origin_wall_s=self._stop_origin_wall_s,
                        stop_deadline_wall_s=self._stop_deadline_wall_s,
                        request_wall_s=self._stop_request_wall_s,
                        request_sim_s=self._stop_request_sim_s,
                        cancel_stop=dict(self._cancel_stop),
                        native_close=dict(self._native_close))

    def stop_receipt(self):
        receipt = self._stop_snapshot()
        receipt['physical_stop_confirmed'] = receipt['cancel_stop']['raw_stop_confirmed'] is True
        receipt['faulted'] = self._faulted
        return receipt

    def fault_receipt(self):
        with self._lock:
            return dict(reason=self._fault_reason, occurred_ns=self._fault_occurred_ns,
                        faulted=self._faulted, refused_reason=self._refused_reason,
                        stop_origin_wall_s=self._stop_origin_wall_s,
                        native_close=dict(self._native_close),
                        cancel_stop=dict(self._cancel_stop))

    def retirement_snapshot(self):
        with self._lock:
            return dict(faulted=self._faulted, fault_reason=self._fault_reason,
                        fault_occurred_ns=self._fault_occurred_ns,
                        armed=self._armed_identity is not None, started=self._started,
                        closed=self._closed, refused_reason=self._refused_reason,
                        native_close=dict(self._native_close),
                        cancel_stop=dict(self._cancel_stop),
                        stop_origin_kind=self._stop_origin_kind,
                        stop_origin_wall_s=self._stop_origin_wall_s,
                        stop_deadline_wall_s=self._stop_deadline_wall_s,
                        watchdog_gaps=tuple(self._watchdog_gaps))

    # ---- workers -----------------------------------------------------------

    def _await_stop(self):
        """Wait for a stop request; a plain retirement ends the wait unanswered.

        Retirement never cancels a stop that was already requested: after a
        shutdown wake-up the stop flag is re-checked once more.
        """
        period = self.policy.watchdog_period_s
        while not self._stop_event.is_set():
            if self._shutdown.wait(period):
                return self._stop_event.is_set()
        return True

    def _native_close_loop(self):
        if not self._await_stop():
            return
        started = self.monotonic()
        # Publish the request time before the blocking authenticated exchange,
        # so a transport that never returns is still visible as in-progress.
        with self._lock:
            self._native_close = dict(self._native_close, requested_wall_s=started,
                                      finished=False)
        receipt, error_type = None, None
        try:
            with self._lock:
                pinned=None if self._bootstrap_identity is None else dict(self._bootstrap_identity)
            if pinned is None:raise RuntimeError('HEAD_NATIVE_CLOSE_IDENTITY_UNPROVEN')
            candidate=self.revoker.close_scoped_strict(expected_identity=pinned)
            from .head_control_protocol import identity_fields
            if type(candidate) is not dict or candidate.get('ack_validated') is not True or (
                    identity_fields(candidate,pinned['generation'])!=pinned or
                    candidate.get('status') not in ('ARMED_CLOSED','NOT_ARMED_CLOSED') or
                    type(candidate.get('stored_generation')) is not int or
                    candidate['stored_generation']!=(pinned['generation'] if candidate['status']=='ARMED_CLOSED' else 0)):
                raise RuntimeError('HEAD_NATIVE_CLOSE_RECEIPT_INVALID')
            receipt=dict(candidate)
        except Exception as error:
            error_type = type(error).__name__
        with self._lock:
            self._native_close = dict(requested_wall_s=started, finished=True,
                                      ack=receipt is not None, error=error_type,
                                      receipt=None if receipt is None else dict(receipt))
        try:
            if self._sink is not None:
                self.record('NATIVE_CLOSE', dict(ack=receipt is not None, error=error_type,
                                                 requested_wall_s=started,
                                                 receipt=None if receipt is None else dict(receipt)))
        except Exception:
            pass

    def _cancel_stop_loop(self):
        if not self._await_stop():
            return
        started = self.monotonic()
        with self._lock:
            origin = self._stop_origin_wall_s
        deadline = None if origin is None else origin + self.policy.stop_confirmation_timeout_s
        # Publish the worker start, its original-physical-stop deadline and every
        # raw predicate observation while the stop is still in progress.
        with self._lock:
            self._cancel_stop = dict(self._cancel_stop, started_wall_s=started, finished=False,
                                     deadline_wall_s=deadline)
        cancel_error = None
        try:
            self.observer.request_cancel_all()
        except Exception as error:
            cancel_error = type(error).__name__
        # Acceptance delivery may fail before the search tick requests a
        # result. Query inventory UUIDs independently of their goal handles;
        # terminal StatusArray entries alone cannot establish raw Stop.
        result_error = None
        try:
            self.observer.request_results()
        except Exception as error:
            result_error = type(error).__name__
        with self._lock:
            self._cancel_stop = dict(self._cancel_stop, cancel_error=cancel_error,
                                     result_error=result_error)
        observations, confirmed = [], False
        while deadline is not None and self.monotonic() <= deadline:
            if self._shutdown.is_set():
                break
            try:
                observed = self.port.stopped() is True
            except Exception as error:
                observed = False
                observations.append(dict(wall_s=self.monotonic(), stopped=False,
                                         error=type(error).__name__))
            else:
                observations.append(dict(wall_s=self.monotonic(), stopped=observed))
            if observed:
                confirmed = True
            with self._lock:
                self._cancel_stop = dict(self._cancel_stop,
                    raw_stop_observations=tuple(observations[-8:]),
                    raw_stop_confirmed=confirmed,
                    observation_count=len(observations))
            if confirmed:
                break
            self._shutdown.wait(self.policy.watchdog_period_s)
        with self._lock:
            self._cancel_stop = dict(self._cancel_stop, started_wall_s=started, finished=True,
                                     cancel_error=cancel_error, raw_stop_confirmed=confirmed,
                                     result_error=result_error,
                                     raw_stop_observations=tuple(observations[-8:]),
                                     observation_count=len(observations),
                                     deadline_wall_s=deadline,
                                     abandoned_on_retirement=(self._shutdown.is_set()
                                                              and not confirmed))
        try:
            if self._sink is not None:
                self.record('CANCEL_STOP', dict(raw_stop_confirmed=confirmed,
                                                cancel_error=cancel_error,
                                                result_error=result_error,
                                                observation_count=len(observations)))
        except Exception:
            pass

    def _watchdog_loop(self):
        period = self.policy.watchdog_period_s
        limit = self.policy.fault_reaction_limit_s
        while not self._shutdown.is_set():
            if self._shutdown.wait(period):
                return
            try:
                self._watchdog_tick(limit)
            except Exception:
                # A dead watchdog is not supervision: an unexpected local
                # failure must close admission instead of ending the thread.
                try:
                    self.fault('HEAD_LOCAL_RUNTIME_WATCHDOG_FAILED')
                except Exception:
                    return

    def _watchdog_tick(self, limit):
        now = self.monotonic()
        with self._lock:
            previous = self._watchdog_wall
            self._watchdog_wall = now
            started = self._started
            faulted = self._faulted
            inference = self._inference_deadline_wall_s
            progress = self._executor_wall
            armed = self._armed_identity is not None
            gaps = self._watchdog_gaps
        if previous is not None and self._sink is not None:
            gaps.append(now - previous)
            del gaps[:-_WATCHDOG_GAP_HISTORY]
        if not started:
            return
        # A dispatcher may latch HeadLocalState directly while its own
        # diagnostics are blocked; detect it and start the real stop from the
        # original scalar occurrence before anyone calls runtime.fault.
        if not faulted and self.local_state.faulted:
            self._state_fault_detected()
            return
        if faulted:
            return
        if inference is not None and now >= inference:
            self.fault('HEAD_LOCAL_INFERENCE_DEADLINE_EXPIRED')
            return
        # Executor progress is authenticated at the dispatch boundary by
        # _current(); an idle attempt between dispatches is not a fault.
        del armed, progress

    def _state_fault_detected(self):
        occurred_ns = self.local_state.fault_occurrence_ns
        reason = self.local_state.snapshot['fault']['reason']
        with self._lock:
            if not self._faulted:
                self._faulted = True
                self._fault_reason = reason
                self._fault_occurred_ns = occurred_ns
            self._admission_open = False
            self._refused_reason = 'HEAD_LOCAL_STATE_FAULT_DETECTED'
            existing_origin = self._stop_origin_wall_s
        origin = None if occurred_ns is None else occurred_ns * 1e-9
        if existing_origin is not None and (origin is None or existing_origin < origin):
            origin = existing_origin
        try:
            self._begin_stop('fault', origin_wall_s=origin)
        except Exception:
            pass
        self._stop_event.set()
        try:
            if self._sink is not None:
                self.record('STATE_FAULT_DETECTED', dict(reason=reason, occurred_ns=occurred_ns))
        except Exception:
            pass

    # ---- retirement --------------------------------------------------------

    def finish_requested_stop(self):
        """Keep originals live until an existing Stop finishes or its deadline expires."""
        with self._lock:
            deadline = self._stop_deadline_wall_s
            requested = self._stop_event.is_set()
            threads = dict(self._threads)
        if requested and deadline is not None:
            for name in ('native_close', 'cancel_stop'):
                thread = threads.get(name)
                if (thread is not None and thread is not threading.current_thread()
                        and thread.is_alive()):
                    thread.join(max(0., deadline - self.monotonic()))
        return self.stop_receipt()

    def retire_originals(self, *, timeout_s=1.):
        """Called after owned producers exit, while the writer is still open."""
        return dict(head_io=self.port.close_head_io(timeout_s=timeout_s),
                    observer=self.observer.close())

    @property
    def retirement_confirmed(self):
        with self._lock:
            return self._closed and self._workers_retired

    def close(self, *, timeout_s=1., retire_originals=True):
        """Bounded retirement; a live worker is reported, never silently dropped."""
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or timeout_s < 0):
            raise ValueError('HEAD_LOCAL_RUNTIME_CLOSE_DEADLINE_INVALID')
        with self._lock:
            self._closed = True
            self._workers_retired = False
            self._admission_open = False
            threads = dict(self._threads)
            stop_requested = self._stop_event.is_set()
        # Retirement alone is not a stop and must not invent one; a stop that
        # was already requested keeps owning both workers until they finish.
        self._shutdown.set()
        deadline = time.monotonic() + timeout_s
        unquiesced = []
        for name in ('cancel_stop', 'native_close', 'watchdog'):
            thread = threads.get(name)
            if thread is None or thread is threading.current_thread():
                continue
            thread.join(max(0., deadline - time.monotonic()))
            if thread.is_alive():
                unquiesced.append(name)
        originals = (self.retire_originals(timeout_s=max(0., deadline - time.monotonic()))
                     if retire_originals else {})
        snapshot = self.retirement_snapshot()
        receipt = dict(retired=not unquiesced, unquiesced=unquiesced,
                    stop_requested=stop_requested,
                    confirmed_stop=snapshot['cancel_stop']['raw_stop_confirmed'] is True,
                    native_close=snapshot['native_close'], cancel_stop=snapshot['cancel_stop'],
                    **originals, stop=self.stop_receipt(),
                    original_retirement=('CLOSED' if retire_originals else 'DEFERRED_TO_PROVIDER'),
                    closed_wall_s=self.monotonic())
        from so101_demo.act.head_execution_documents import retirement_unconfirmed
        with self._lock:
            self._workers_retired = not retirement_unconfirmed(receipt)
        return receipt
