"""Process-local Head admission, watchdog and independent stop workers.

The runtime owns local admission/readiness for the file-protocol Head attempt.
It keeps one shared ``HeadLocalState``, one shared ROS node/controller port and
one `HeadLocalObserver`, and it never allocates a motion client, controller
stack, model or monitor process.

Three threads are started explicitly by :meth:`start` and never by a
constructor: a genuine watchdog and two independent stop workers (the fault
latch of the neck dead-man, and cancel/raw-stop/stop-window with the planned
dead-man close). Constructors do not arm or grant motion; :meth:`arm` performs
the real pre-arm checks and binds the neck owner's controller identity against
the local scope.

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
#: the case ended on its own terms: the dead-man closes as planned after the stop proof
PLANNED_ORIGINS = ('success', 'not_found')
_OWNER_API = ('readback', 'deadman_armed', 'graph_proof', 'startup_stop_window', 'identity',
              'begin_end_window', 'end_stop_window', 'close_planned', 'close_fault', 'start_monitor',
              'bind_liveness', 'bind_fault')
_WATCHDOG_GAP_HISTORY = 64
#: time for the planned dead-man close (helper exit) after the stop window
_CLOSE_ALLOWANCE_S = 0.25


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

    def __init__(self, *, node, port, local_state, owner, observer, policy,
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
        if any(not callable(getattr(owner, name, None)) for name in _OWNER_API):
            raise ValueError('HEAD_LOCAL_RUNTIME_OWNER_INVALID')
        if (getattr(owner, 'generation', None) != local_state.scope['generation']
                or getattr(owner, 'session_id', None) != local_state.scope['session_id']):
            raise ValueError('HEAD_LOCAL_RUNTIME_OWNER_SCOPE_INVALID')
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
        self.owner = owner
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
        self._deadman_close = dict(requested_wall_s=None, finished=False, ack=False, planned=False,
                                   error=None, receipt=None)
        self._cancel_stop = dict(started_wall_s=None, finished=False, cancel_error=None,
                                 raw_stop_confirmed=False, raw_stop_observations=(),
                                 deadline_wall_s=None, abandoned_on_retirement=False,
                                 end_window=None, window_error=None)
        if observer._fault_callback is None:
            observer.bind_fault_callback(self.fault)
        elif observer._fault_callback != self.fault:
            raise PermissionError('HEAD_LOCAL_RUNTIME_OBSERVER_FAULT_OWNER_EXISTS')
        port._head_fault_callback = self.fault
        owner.bind_fault(self.fault)
        if sink is not None:
            port.bind_head_action_sink(self.record)

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
                'deadman_latch': threading.Thread(target=self._deadman_latch_loop, daemon=True,
                                                  name='head-local-deadman-latch'),
                'cancel_stop': threading.Thread(target=self._cancel_stop_loop, daemon=True,
                                                name='head-local-cancel-stop'),
            }
            self._threads = dict(threads)
        # the owner keeps ticking the dead-man helper only while this watchdog keeps ticking
        self.owner.bind_liveness(self._watchdog_age)
        for thread in threads.values():
            thread.start()
        return dict(watchdog_started=threads['watchdog'].is_alive(),
                    workers=['deadman_latch', 'cancel_stop'],
                    threads={name: thread.ident for name, thread in threads.items()})

    def _watchdog_age(self):
        with self._lock:
            tick = self._watchdog_wall
        return None if tick is None else max(0., self.monotonic() - tick)

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
        if not state_open:
            self._refuse('HEAD_LOCAL_RUNTIME_PREARM_STATE_INVALID', faults=False)
        feedback = self._current(require_armed=False, refusal_faults=False)
        if any(abs(value) > self._port_stop_velocity() for value in feedback['velocities']):
            self._refuse('HEAD_LOCAL_RUNTIME_PREARM_NOT_QUIET', faults=False)
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
        deadline = self.clock_ns() + 2_000_000_000
        with self._lock:
            if self._closed:raise PermissionError('HEAD_LOCAL_RUNTIME_CLOSED')
            if self._armed_identity is not None:raise PermissionError('HEAD_LOCAL_RUNTIME_ALREADY_ARMED')
            if self._faulted or not self._admission_open:
                raise PermissionError('HEAD_LOCAL_RUNTIME_STATE_INVALID')
        # A local precondition refusal remains correctable before the owner is consulted.
        self.prearm_guard()
        expected = self.local_state.scope['controller_identity']

        def check(*, window_wait=False):
            self._startup_check(cancel_event, deadline, ready_wait=window_wait)
            self.prearm_guard()
            self._startup_check(cancel_event, deadline, ready_wait=window_wait)

        def owner_deadline():
            return self.monotonic() + max(0., (deadline - self.clock_ns()) * 1e-9)
        try:
            check()
            readback = self.owner.readback(deadline=owner_deadline())
            if self._sink is not None:self.record('CONTROLLER_READBACK', dict(readback))
            check()
            armed = self.owner.deadman_armed()
            if self._sink is not None:self.record('DEADMAN_ARMED', dict(armed))
            check()
            graph = self.owner.graph_proof()
            if self._sink is not None:self.record('GRAPH_PROOF', dict(graph))
            check(window_wait=True)
            try:
                window = self.owner.startup_stop_window(deadline=owner_deadline(), cancel_event=cancel_event)
            except TimeoutError:
                if cancel_event.is_set():raise HeadStartupCancelled('HEAD_STARTUP_CANCELLED') from None
                raise
            if self._sink is not None:self.record('STARTUP_STOP_WINDOW', dict(window))
            check()
            identity = _identity_triple(self.owner.identity())
            if expected is not None and identity != expected:
                raise PermissionError('HEAD_LOCAL_RUNTIME_OWNER_IDENTITY_MISMATCH')
            if self._sink is not None:self.record('ARMED', dict(identity=dict(identity)))
            with self._lock:
                self._startup_check(cancel_event, deadline)
                if self._closed or self._faulted or not self._admission_open:
                    raise PermissionError('HEAD_LOCAL_RUNTIME_STATE_INVALID')
                if expected is None:self.local_state.bind_controller_identity(identity, identity)
                if self.local_state.faulted:raise PermissionError('HEAD_LOCAL_STATE_FAULTED')
                self._startup_check(cancel_event, deadline)
                self._armed_identity = dict(identity)
            self.owner.start_monitor()
        except HeadStartupCancelled:
            self.stop('sigterm',dict(startup_cancelled=True))
            raise
        except Exception as error:
            if cancel_event.is_set():
                self.stop('sigterm',dict(startup_cancelled=True,error_type=type(error).__name__,
                                        reason=str(error)[:256]))
                raise HeadStartupCancelled('HEAD_STARTUP_CANCELLED') from error
            self.fault('HEAD_LOCAL_RUNTIME_STARTUP_FAILED',
                       {'error_type':type(error).__name__,'reason':str(error)[:256]})
            raise
        return dict(identity)

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
                        deadman_close=dict(self._deadman_close))

    @staticmethod
    def _physical_stop_confirmed(cancel_stop):
        """All three: the raw stop, the post-stop controller_state window (the terminal result is in the raw stop)."""
        return cancel_stop['raw_stop_confirmed'] is True and cancel_stop.get('end_window') is not None

    def stop_receipt(self):
        receipt = self._stop_snapshot()
        receipt['physical_stop_confirmed'] = self._physical_stop_confirmed(receipt['cancel_stop'])
        receipt['faulted'] = self._faulted
        return receipt

    def fault_receipt(self):
        with self._lock:
            return dict(reason=self._fault_reason, occurred_ns=self._fault_occurred_ns,
                        faulted=self._faulted, refused_reason=self._refused_reason,
                        stop_origin_wall_s=self._stop_origin_wall_s,
                        deadman_close=dict(self._deadman_close),
                        cancel_stop=dict(self._cancel_stop))

    def retirement_snapshot(self):
        with self._lock:
            return dict(faulted=self._faulted, fault_reason=self._fault_reason,
                        fault_occurred_ns=self._fault_occurred_ns,
                        armed=self._armed_identity is not None, started=self._started,
                        closed=self._closed, refused_reason=self._refused_reason,
                        deadman_close=dict(self._deadman_close),
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

    def _deadman_latch_loop(self):
        """A stop that is not the case ending on its own latches the controller at once.

        Aborting the active goal and holding is the controller's own reaction to the closed dead-man, so it
        does not wait for the cancel service or the raw-stop proof. A planned end (success / not found) is
        closed by the cancel worker after the stop proof instead.
        """
        if not self._await_stop():
            return
        with self._lock:
            origin = self._stop_origin_kind
        if origin in PLANNED_ORIGINS:
            return
        self._close_deadman(planned=False, reason=origin or 'fault')

    def _close_deadman(self, *, planned, reason=None):
        started = self.monotonic()
        with self._lock:
            if self._deadman_close['finished'] or self._deadman_close['requested_wall_s'] is not None:
                return
            self._deadman_close = dict(requested_wall_s=started, finished=False, ack=False,
                                       planned=planned, error=None, receipt=None)
        receipt, error_type = None, None
        try:
            if planned:
                if self._sink is not None:
                    self.record('DEADMAN_CLOSED_PLANNED', dict(activation_id=self._armed_activation_id()))
                receipt = self.owner.close_planned()
            else:
                receipt = self.owner.close_fault(reason)
        except Exception as error:
            error_type = type(error).__name__
        acknowledged = receipt is not None and receipt.get('helper_closed') is True
        with self._lock:
            self._deadman_close = dict(requested_wall_s=started, finished=True, ack=acknowledged,
                                       planned=planned, error=error_type,
                                       receipt=None if receipt is None else dict(receipt))
        try:
            if self._sink is not None and not planned:
                self.record('DEADMAN_CLOSED_FAULT', dict(reason=reason, ack=acknowledged, error=error_type,
                                                         requested_wall_s=started, receipt=receipt))
        except Exception:
            pass

    def _armed_activation_id(self):
        try:
            return self.owner.deadman_armed()['activation_id']
        except Exception:
            return None

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
        confirmation = None
        if confirmed:
            try:
                confirmation = self.port.raw_stop_confirmation()
            except Exception:
                confirmation = None
        try:
            if self._sink is not None:
                self.record('CANCEL_STOP', dict(raw_stop_confirmed=confirmed,
                                                cancel_error=cancel_error,
                                                result_error=result_error,
                                                observation_count=len(observations),
                                                raw_stop_confirmed_sim_ns=(
                                                    None if confirmation is None else confirmation['sim_ns']),
                                                raw_stop_last_sample_source_ns=(
                                                    None if confirmation is None
                                                    else confirmation['last_sample_source_ns'])))
        except Exception:
            pass
        self._finish_closure(confirmed, confirmation)

    def _finish_closure(self, confirmed, confirmation):
        """After the raw stop: the controller_state window, then the stop proof, then the dead-man close.

        The window counts only samples stamped after the raw-stop confirmation. The stop proof needs the
        terminal result, the raw stop and the window; only a proven stop of a case that ended on its own
        terms closes the dead-man as planned. Anything else latches the controller.
        """
        window, window_error = None, None
        if confirmed and confirmation is not None and not self._shutdown.is_set():
            try:
                self.owner.begin_end_window(raw_stop_sim_ns=confirmation['sim_ns'])
                window = self.owner.end_stop_window(timeout_s=self.policy.head_stop_window_deadline_s)
            except Exception as error:
                window_error = type(error).__name__ + ': ' + str(error)[:120]
        with self._lock:
            self._cancel_stop = dict(self._cancel_stop, end_window=window, window_error=window_error)
            faulted, origin = self._faulted, self._stop_origin_kind
        proven = confirmed and window is not None
        planned = proven and not faulted and origin in PLANNED_ORIGINS
        if proven and self._sink is not None:
            try:
                self.record('STOCK_STOP_PROOF', dict(
                    terminal=confirmation['terminal'], raw_stop_samples=confirmation['samples'],
                    raw_stop_confirmed_sim_ns=confirmation['sim_ns'], window=dict(window),
                    deadman_closed_planned=planned))
            except Exception:
                pass
        if planned:
            self._close_deadman(planned=True)
        elif origin in PLANNED_ORIGINS:
            # a case that ended on its own terms but whose proof failed, or that faulted meanwhile: latch it.
            # (Every other origin was latched at once by the fault-latch worker.)
            self._close_deadman(planned=False, reason='STOP_PROOF_UNCONFIRMED' if not proven else 'fault')

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
            # the raw-stop budget, then the controller_state window and the planned close that follow it
            closure_deadline = deadline + self.policy.head_stop_window_deadline_s + _CLOSE_ALLOWANCE_S
            for name in ('deadman_latch', 'cancel_stop'):
                thread = threads.get(name)
                if (thread is not None and thread is not threading.current_thread()
                        and thread.is_alive()):
                    thread.join(max(0., closure_deadline - self.monotonic()))
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
        for name in ('cancel_stop', 'deadman_latch', 'watchdog'):
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
                    confirmed_stop=self._physical_stop_confirmed(snapshot['cancel_stop']),
                    deadman_close=snapshot['deadman_close'], cancel_stop=snapshot['cancel_stop'],
                    **originals, stop=self.stop_receipt(),
                    original_retirement=('CLOSED' if retire_originals else 'DEFERRED_TO_PROVIDER'),
                    closed_wall_s=self.monotonic())
        from so101_demo.act.head_execution_documents import retirement_unconfirmed
        with self._lock:
            self._workers_retired = not retirement_unconfirmed(receipt)
        return receipt
