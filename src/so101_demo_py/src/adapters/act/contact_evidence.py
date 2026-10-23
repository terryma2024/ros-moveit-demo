"""Whole-robot contact evidence is audit input, never a policy observation."""

import copy
import math
import time
import threading
from collections import deque
from so101_demo.act.contracts import finite,identifier,integer,fields

CONTACT_KEYS=frozenset(('geom_a','geom_b','signed_distance_m','normal_force_n','truncated','evidence_loss'))
FRAME_KEYS=CONTACT_KEYS|frozenset(('simulation_session_id','reset_epoch','physics_step','simulation_time_s'))


def _pair_hazards(frame,allowed_pairs,process_pairs):
    """Return (hazard, process_violations) for a frame.

    A pair outside the phase allowlist is a hazard unless it is one of the ``process_pairs``:
    those are cup process expectations (cup support, finger contact by phase), never a
    robot-environment or self collision. With no process pairs this is the strict check.
    """
    violations=[]
    try:
        if not isinstance(frame,dict) or set(frame) not in (CONTACT_KEYS,FRAME_KEYS):return True,violations
        if type(frame['truncated']) is not bool or type(frame['evidence_loss']) is not bool:return True,violations
        if frame['truncated'] or frame['evidence_loss']:return True,violations
        arrays=[frame[key] for key in ('geom_a','geom_b','signed_distance_m','normal_force_n')]
        if any(not isinstance(value,(list,tuple)) for value in arrays):return True,violations
        if len({len(value) for value in arrays})!=1:return True,violations
        if not isinstance(allowed_pairs,(set,frozenset)):return True,violations
        for pair in allowed_pairs:
            if not isinstance(pair,tuple) or len(pair)!=2 or tuple(sorted(pair))!=pair:return True,violations
            for name in pair:identifier(name)
        for a,b,distance,force in zip(*arrays,strict=True):
            identifier(a);identifier(b);finite(distance);finite(force,nonnegative=True)
            pair=tuple(sorted((a,b)))
            if pair in allowed_pairs:continue
            if pair in process_pairs:
                if pair not in violations:violations.append(pair)
                continue
            return True,violations
        return False,violations
    except (KeyError,TypeError,ValueError):return True,violations


def contact_hazard(frame,allowed_pairs,process_pairs=frozenset()):
    return _pair_hazards(frame,allowed_pairs,process_pairs)[0]


class RobotContactObserver:
    """Whole-robot contact observer.

    ``process_pairs`` (default none) names cup process-expectation pairs: a contact of one of
    these outside the phase allowlist is reported to ``audit`` and is not a hazard, while every
    other pair stays a collision hazard. ``audit_integrity`` (default off) makes forward step and
    time gaps data completeness: they are reported to ``audit`` and the observer resynchronises.
    Out-of-order evidence, identity faults, unknown geometry and truncated or lossy frames remain
    hazards in every mode. Both options are opt-in for the Teacher's own broker source.
    """

    def __init__(self,*,known_geoms,allowed_pairs,max_age_s,max_sim_gap_s,monotonic=time.monotonic,
                 process_pairs=frozenset(),audit_integrity=False,audit=None,history_capacity=512):
        self._lock=threading.RLock()
        self.known=frozenset(known_geoms);self.allowed=frozenset(allowed_pairs)
        if not self.known:raise ValueError('CONTACT_CONFIG_INVALID')
        for name in self.known:identifier(name)
        for pair in self.allowed:
            if len(pair)!=2 or tuple(sorted(pair))!=pair or not set(pair)<=self.known:raise ValueError('CONTACT_CONFIG_INVALID')
        if not isinstance(process_pairs,(set,frozenset)):raise ValueError('CONTACT_CONFIG_INVALID')
        self.process_pairs=frozenset(process_pairs)
        for pair in self.process_pairs:
            if (not isinstance(pair,tuple) or len(pair)!=2 or tuple(sorted(pair))!=pair
                    or not set(pair)<=self.known):raise ValueError('CONTACT_CONFIG_INVALID')
        if type(audit_integrity) is not bool or (audit is not None and not callable(audit)):
            raise ValueError('CONTACT_CONFIG_INVALID')
        self.audit_integrity=audit_integrity;self.audit=audit
        self.max_age=finite(max_age_s);self.max_gap=finite(max_sim_gap_s)
        if self.max_age<=0 or self.max_gap<=0:raise ValueError('CONTACT_CONFIG_INVALID')
        self.monotonic=monotonic;self.session=None;self.epoch=None;self.last=None;self.received=None;self.hazard=None
        integer(history_capacity,minimum=1)  # retention sizing only; fresh windows age at max_age_s regardless
        self._history=deque(maxlen=history_capacity)
        self._receipts=deque(maxlen=4096)  # monotonic receipt time of each accepted frame (receive-rate facts)
        # Producer-time ageing (plan D8a): contact frames carry no producer clock, so each step is mapped to the
        # producer clock of the raw physics sample with the same step. An unmapped step is never fresh.
        self.producer_end_ns=None;self.producer_now_ns=None;self.producer_range=None

    def bind_producer_clock(self,end_ns_of_step,now_ns,step_range=None):
        """`step_range()` returns the (oldest, newest) retained raw step or None; it separates a step that is merely
        newer than the raw stream (pending mapping) from one older than it (lost)."""
        if (not callable(end_ns_of_step) or not callable(now_ns)
                or (step_range is not None and not callable(step_range))):raise ValueError('CONTACT_CONFIG_INVALID')
        with self._lock:self.producer_end_ns,self.producer_now_ns,self.producer_range=end_ns_of_step,now_ns,step_range

    def replace_allowed_pairs(self, pairs):
        """Atomically replace the active phase policy and recheck the last frame.

        A contact rejected under either policy stays hazardous until a new reset
        epoch; broadening the next phase cannot retroactively accept it.
        """
        if not isinstance(pairs,(set,frozenset)):
            raise ValueError('CONTACT_CONFIG_INVALID')
        checked=frozenset(pairs)
        for pair in checked:
            if (not isinstance(pair,tuple) or len(pair)!=2
                    or any(not isinstance(name,str) or name not in self.known for name in pair)
                    or tuple(sorted(pair))!=pair):
                raise ValueError('CONTACT_CONFIG_INVALID')
        with self._lock:
            self.allowed=checked
            if self.last is not None and contact_hazard(self.last,checked,self.process_pairs):
                self.hazard=self.hazard or 'ROBOT_CONTACT_HAZARD'

    def reset(self,session_id,reset_epoch,*,source_floor_s):
        with self._lock:
            identifier(session_id);integer(reset_epoch);floor=finite(source_floor_s,nonnegative=True)
            if self.session==session_id and self.epoch is not None and reset_epoch<=self.epoch:
                raise ValueError('CONTACT_RESET_EPOCH_INVALID')
            self.session,self.epoch,self.floor=session_id,reset_epoch,floor
            self.last=self.received=self.hazard=None
            self._history.clear();self._receipts.clear()

    def accept(self,frame):
        with self._lock:
            try:
                fields(frame,FRAME_KEYS)
                if (frame['simulation_session_id'],frame['reset_epoch'])!=(self.session,self.epoch):raise ValueError('CONTACT_IDENTITY_INVALID')
                integer(frame['reset_epoch']);integer(frame['physics_step'],minimum=1)
                stamp=finite(frame['simulation_time_s'],nonnegative=True)
                if stamp<=self.floor:raise ValueError('CONTACT_TIME_INVALID')
                expected=1 if self.last is None else self.last['physics_step']+1
                observed=[]
                if frame['physics_step']!=expected:
                    if not self.audit_integrity or frame['physics_step']<expected:raise ValueError('CONTACT_STEP_GAP')
                    observed.append(('CONTACT_STEP_GAP',dict(expected_step=expected,physics_step=frame['physics_step'])))
                previous=self.floor if self.last is None else self.last['simulation_time_s']
                delta=stamp-previous
                if not 0<delta:raise ValueError('CONTACT_TIME_GAP')
                if delta>self.max_gap+1e-12:
                    if not self.audit_integrity:raise ValueError('CONTACT_TIME_GAP')
                    observed.append(('CONTACT_TIME_GAP',dict(gap_s=delta,physics_step=frame['physics_step'])))
                if any(name not in self.known for key in ('geom_a','geom_b') for name in frame[key]):raise ValueError('CONTACT_UNKNOWN_GEOM')
                hazard,violations=_pair_hazards(frame,self.allowed,self.process_pairs)
                if hazard:self.hazard=self.hazard or 'ROBOT_CONTACT_HAZARD'
                elif violations:
                    observed.append(('CONTACT_PROCESS_EXPECTATION',dict(pairs=violations,physics_step=frame['physics_step'])))
                self._note(observed)
                self.last={key:list(value) if isinstance(value,(list,tuple)) else value for key,value in frame.items()}
                self.received=finite(self.monotonic(),nonnegative=True)
                # `self.last` is a fresh dict of fresh lists built above and never mutated afterwards (every reader
                # copies it or only reads), so history can share it instead of keeping a second deep copy.
                self._history.append((self.last,self.received));self._receipts.append(self.received)
            except (KeyError,TypeError,ValueError) as error:self.hazard=self.hazard or str(error)

    def _note(self,observed):
        """Report completeness and process observations; never raises, never latches."""
        if self.audit is None:return
        for code,facts in observed:
            try:self.audit(code,**facts)
            except Exception:pass

    def latch(self, reason):
        identifier(reason)
        with self._lock:self.hazard=self.hazard or reason

    def safe(self):
        with self._lock:
            if self.hazard or self.last is None or self.received is None:return False
            now=finite(self.monotonic(),nonnegative=True)
            return 0<=now-self.received<=self.max_age

    def snapshot(self):
        """Return one immutable-in-effect frame from the current safe epoch."""
        with self._lock:
            if self.hazard:raise ValueError(self.hazard)
            if self.last is None or self.received is None:raise ValueError('CONTACT_UNAVAILABLE')
            now=finite(self.monotonic(),nonnegative=True)
            if not 0<=now-self.received<=self.max_age:raise ValueError('CONTACT_STALE')
            return copy.deepcopy(self.last)

    def recent_frames(self):
        """Return fresh contiguous accepted steps from the current safe epoch."""
        return tuple(frame for frame, _ in self.recent_frames_with_receipts())

    def recent_frames_with_receipts(self):
        """Return each fresh frame with its original monotonic callback receipt."""
        return tuple((copy.deepcopy(frame),received) for frame,received in self._fresh_history())

    def recent_steps(self):
        """Return the physics steps of the fresh frames without copying any frame."""
        return tuple(frame['physics_step'] for frame,_ in self._fresh_history())

    def _fresh_history(self):
        """Shared checks and freshness filter; entries are the retained originals, never copies."""
        with self._lock:
            if self.hazard:raise ValueError(self.hazard)
            if self.last is None or self.received is None:raise ValueError('CONTACT_UNAVAILABLE')
            if self.producer_end_ns is not None:return self._fresh_producer_history()
            now=finite(self.monotonic(),nonnegative=True)
            if not 0<=now-self.received<=self.max_age:raise ValueError('CONTACT_STALE')
            return tuple((frame,received) for frame,received in self._history
                         if 0<=now-received<=self.max_age)

    def ready_steps(self):
        """Fresh steps for the readiness gate: lag, pending, lost and stale frames are an empty answer, never an error.

        Only a latched hazard (including identity/scope faults) raises. Point-of-use readbacks keep CONTACT_STALE.
        """
        with self._lock:
            if self.hazard:raise ValueError(self.hazard)
            if self.last is None or self.received is None:return ()
            if self.producer_end_ns is not None:
                return tuple(frame['physics_step'] for frame,_ in self._classify_producer()[0])
            now=finite(self.monotonic(),nonnegative=True)
            return tuple(frame['physics_step'] for frame,received in self._history if 0<=now-received<=self.max_age)

    def readiness_counts(self):
        """(fresh, pending, lost) retained frame counts on producer time; (None,None,None) without a producer clock."""
        with self._lock:
            if self.producer_end_ns is None or self.last is None:return None,None,None
            fresh,pending,_=self._classify_producer()
            return len(fresh),pending,len(self._history)-len(fresh)-pending

    def receive_rate_hz(self,window_s=1.0):
        """Accepted contact messages per second over the last `window_s` (by receipt time)."""
        with self._lock:
            now=finite(self.monotonic(),nonnegative=True)
            return round(sum(1 for t in self._receipts if 0<=now-t<=window_s)/window_s,1)

    def _classify_producer(self):
        """(fresh, pending, newest_mapped_age_ns) for the retained frames on producer time.

        A step with a retained raw sample is aged against that sample's producer clock. A step NEWER than the newest
        retained raw step (or any step while no raw chunk has arrived yet) is "pending mapping": neither fresh nor
        stale, because contacts arrive every step while raw arrives in chunks. A step older than the retained raw
        range, or missing inside it, is lost and never fresh.
        """
        now_ns=self.producer_now_ns();bound_ns=round(self.max_age*1e9)
        limits=self.producer_range() if self.producer_range is not None else None
        fresh=[];pending=0;newest=None
        # Newest first: producer ages never increase with the step, so the walk ends at the first mapped frame older
        # than the bound (everything before it is older still, lost or unmapped, never fresh). A long retained
        # history (plan A19) therefore costs only the fresh window per call, not the whole ring.
        for frame,received in reversed(self._history):
            step=frame['physics_step']
            end=self.producer_end_ns(step)
            if end is None:
                if self.producer_range is not None and (limits is None or step>limits[1]):pending+=1
                continue  # lost or (without a range) unmappable: never fresh
            age=now_ns-end
            newest=age if newest is None or age<newest else newest
            if 0<=age<=bound_ns:fresh.append((frame,received))
            elif age>bound_ns:break
        fresh.reverse()
        return fresh,pending,newest

    def pending_count(self):
        """Frames waiting for their raw producer clock (observation and the point-of-use wait)."""
        with self._lock:
            if self.producer_end_ns is None or self.hazard or self.last is None:return 0
            return self._classify_producer()[1]

    def _fresh_producer_history(self):
        """Fresh frames aged on producer time.

        Pending frames never raise: with no fresh mapped frame the answer is an empty window (not ready yet).
        CONTACT_STALE is raised only when nothing is pending and no mapped frame is within the bound, i.e. the
        mapped producer age exceeds the bound or the steps are older than the retained raw range.
        """
        fresh,pending,newest=self._classify_producer()
        if not fresh and not pending:
            try:
                import json,sys
                print('TEACHER_DATA_AGE_REFUSAL '+json.dumps({'check':'contacts_producer_age',
                    'age_ms':None if newest is None else round(newest/1e6,3),'bound_ms':round(self.max_age*1e3,3),
                    'reference':'raw_chunk_clock_of_the_same_physics_step'},sort_keys=True),file=sys.stderr,flush=True)
            except Exception:pass
            raise ValueError('CONTACT_STALE')
        return tuple(fresh)


class RosRobotContactAdapter:
    def __init__(self,node,observer,*,on_hazard,pending_capacity=5000,record_port=None,callback_group=None):
        from so101_mujoco_support.msg import RobotContactEvidence
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        integer(pending_capacity,minimum=1)
        if not callable(on_hazard):raise ValueError('CONTACT_HAZARD_PORT_INVALID')
        self.observer,self.on_hazard,self.record_port=observer,on_hazard,record_port
        self._lock=threading.RLock();self._pending=deque(maxlen=pending_capacity)
        self._lost_epochs=set();self._record_failed_epochs=set()
        self._armed=False;self._stopped=False;self.rejections=deque(maxlen=32)
        options={} if callback_group is None else {'callback_group':callback_group}
        self._message_type=RobotContactEvidence;self.drained=0
        # The subscription callback consumes the delivered message and then drains what is already queued (plan A22).
        self.subscription=node.create_subscription(RobotContactEvidence,'/so101/simulation/robot_contacts',
            self._on_message,QoSProfile(depth=10000,reliability=ReliabilityPolicy.RELIABLE),**options)

    def replace_allowed_pairs(self, pairs):
        with self._lock:
            self.observer.replace_allowed_pairs(pairs)
            self._stop_if_hazard()

    def arm(self,reset_snapshot):
        if reset_snapshot.paused is not True or reset_snapshot.simulation_step!=0:
            raise ValueError('CONTACT_RESET_SNAPSHOT_INVALID')
        with self._lock:
            self.observer.reset(reset_snapshot.simulation_session_id,reset_snapshot.reset_epoch,
                source_floor_s=reset_snapshot.simulation_time_s)
            self._armed=True;self._stopped=False
            identity=(self.observer.session,self.observer.epoch)
            if identity in self._record_failed_epochs:self.observer.latch('CONTACT_RECORD_FAILED')
            if identity in self._lost_epochs:
                if self.observer.audit_integrity:
                    self.observer._note([('CONTACT_RECEIVER_OVERFLOW',dict(reset_epoch=identity[1]))])
                else:self.observer.latch('CONTACT_RECEIVER_OVERFLOW')
            for frame in self._pending:self._consume(frame)
            self._pending.clear();self._lost_epochs.clear();self._record_failed_epochs.clear()
            self._stop_if_hazard()

    def _stop_if_hazard(self):
        if self.observer.hazard and not self._stopped:
            self._stopped=True;self.on_hazard(self.observer.hazard)

    def _consume(self,frame):
        if (self.observer.last is None and frame['simulation_session_id']==self.observer.session
                and frame['reset_epoch']<self.observer.epoch):
            self.rejections.append(dict(reason='PRE_RESET_FRAME',epoch=frame['reset_epoch'],step=frame['physics_step']))
            return
        self.observer.accept(frame);self._stop_if_hazard()

    _DRAIN_LIMIT=256

    def _on_message(self,message):
        """Subscription callback: the delivered message, then up to `_DRAIN_LIMIT` already queued ones, in order.

        One executor cycle costs several GIL hand-offs; under a busy Python thread each is a full switch interval, so a
        500 Hz stream taken one message per cycle starves (measured: 46 msg/s at the default 5 ms interval while the
        callback itself costs ~25 us). Taking the queued messages inside the same mutually exclusive callback keeps
        the order (the executor took the first one before calling us, and the group admits no concurrent callback) and
        amortises the hand-offs. A subscription without a native handle (test doubles) just handles the one message.
        """
        self.accept_message(message)
        subscription=self.subscription
        handle=getattr(subscription,'handle',None);take=getattr(handle,'take_message',None)
        if take is None:return
        for _ in range(self._DRAIN_LIMIT):
            try:taken=take(self._message_type,False)
            except Exception:return  # the executor's own take reports a real subscription fault
            if taken is None:return
            queued=taken[0] if isinstance(taken,tuple) else taken
            if queued is None:return
            self.drained+=1
            self.accept_message(queued)

    def accept_message(self,message):
        frame={key:list(getattr(message,key)) if key in ('geom_a','geom_b','signed_distance_m','normal_force_n')
               else getattr(message,key) for key in FRAME_KEYS}
        with self._lock:
            if self.record_port is not None:
                try:self.record_port({key:list(value) if isinstance(value,list) else value for key,value in frame.items()})
                except Exception as error:
                    self._record_failed_epochs.add((frame['simulation_session_id'],frame['reset_epoch']))
                    self.rejections.append(dict(reason='CONTACT_RECORD_FAILED',error=repr(error)))
                    self.observer.latch('CONTACT_RECORD_FAILED');self._stop_if_hazard()
            if not self._armed:
                if len(self._pending)==self._pending.maxlen:
                    old=self._pending[0];self._lost_epochs.add((old['simulation_session_id'],old['reset_epoch']))
                self._pending.append(frame)
            else:self._consume(frame)
