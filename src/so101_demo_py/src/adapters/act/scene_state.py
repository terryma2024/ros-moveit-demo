"""Content-bound actual scene coordinates are audit input, never policy features."""
import copy
import threading
import time
from collections import deque
from so101_demo.act.contracts import fields,finite,identifier,integer,sha256,vector

SCENE_KEYS=frozenset(('simulation_session_id','reset_epoch','simulation_step','paused',
    'simulation_time_s','model_sha256','qpos','qvel',
    'clock_interval_begin_monotonic_ns','clock_interval_end_monotonic_ns'))


class SceneStateObserver:
    def __init__(self,*,model_sha256,nq,nv,max_age_s,monotonic=time.monotonic,history_capacity=256,producer_now_ns=None):
        sha256(model_sha256);integer(nq,minimum=1);integer(nv,minimum=1)
        self.model_sha256,self.nq,self.nv=model_sha256,nq,nv
        self.max_age=finite(max_age_s)
        if self.max_age<=0:raise ValueError('SCENE_STATE_CONFIG_INVALID')
        self.monotonic=monotonic;self._lock=threading.RLock()
        # With a producer clock (ns, same clock as `clock_interval_end_monotonic_ns`) frames age on producer time
        # instead of consumer receipt, so a consumer backlog shows up as age.
        if producer_now_ns is not None and not callable(producer_now_ns):raise ValueError('SCENE_STATE_CONFIG_INVALID')
        self.producer_now_ns=producer_now_ns
        self.session=self.epoch=self.last=self.received=self.hazard=None
        if type(history_capacity) is not int or not 1<=history_capacity<=4096:raise ValueError('SCENE_STATE_CONFIG_INVALID')
        self._history=deque(maxlen=history_capacity)
        self._geometry_version=0;self._geometry_key=None
        self._history_version=0  # bumps whenever the retained frames change (lets readers cache derived verdicts)

    def reset(self,session_id,reset_epoch,*,source_floor_s):
        identifier(session_id);integer(reset_epoch,minimum=1);floor=finite(source_floor_s,nonnegative=True)
        with self._lock:
            if self.session==session_id and self.epoch is not None and (reset_epoch<=self.epoch or floor<self.floor):
                raise ValueError('SCENE_STATE_RESET_INVALID')
            self.session,self.epoch,self.floor=session_id,reset_epoch,floor
            self.last=self.received=self.hazard=None
            self._history.clear();self._history_version+=1
            self._geometry_version=0;self._geometry_key=None

    def accept(self,frame):
        with self._lock:
            if self.hazard:return False
            try:
                stamp=self.validate(frame)
                if self.session is None:return False
                if (self.last is None and frame['simulation_session_id']==self.session
                        and frame['reset_epoch']<self.epoch and stamp<=self.floor):return False
                if (frame['simulation_session_id'],frame['reset_epoch'])!=(self.session,self.epoch):
                    raise ValueError('SCENE_STATE_IDENTITY_INVALID')
                if stamp<self.floor:raise ValueError('SCENE_STATE_TIME_INVALID')
                if self.last is not None and (stamp<self.last['simulation_time_s']
                        or frame['simulation_step']<self.last['simulation_step']):
                    raise ValueError('SCENE_STATE_REORDERED')
                geometry=(tuple(frame['qpos']),tuple(frame['qvel']),frame['paused'])
                if geometry!=self._geometry_key:
                    self._geometry_version+=1;self._geometry_key=geometry
                self.last=copy.deepcopy(frame);self.received=finite(self.monotonic(),nonnegative=True)
                self._history.append((copy.deepcopy(self.last),self.received));self._history_version+=1
                return True
            except (KeyError,TypeError,ValueError) as error:
                self.hazard=str(error);return False

    def validate(self,frame):
        fields(frame,SCENE_KEYS)
        identifier(frame['simulation_session_id']);integer(frame['reset_epoch'])
        integer(frame['simulation_step']);stamp=finite(frame['simulation_time_s'],nonnegative=True)
        begin=frame['clock_interval_begin_monotonic_ns']
        end=frame['clock_interval_end_monotonic_ns']
        if (type(begin) is not int or type(end) is not int
                or not 0<begin<=end<=round(finite(self.monotonic(),nonnegative=True)*1e9)):
            raise ValueError('SCENE_SOURCE_CLOCK_INVALID')
        sha256(frame['model_sha256'])
        if frame['model_sha256']!=self.model_sha256:raise ValueError('SCENE_STATE_MODEL_INVALID')
        if type(frame['paused']) is not bool:raise ValueError('SCENE_STATE_INVALID')
        vector(frame['qpos'],self.nq);vector(frame['qvel'],self.nv)
        return stamp

    def snapshot(self):
        return self.snapshot_with_receipt()[0]

    def snapshot_with_receipt(self):
        """Read one fresh scene frame and its receipt clock atomically."""
        with self._lock:
            if self.hazard:raise ValueError(self.hazard)
            if self.last is None:raise ValueError('SCENE_STATE_UNAVAILABLE')
            if not self._fresh(self.last,self.received,self.monotonic(),log=True):raise ValueError('SCENE_STATE_STALE')
            return copy.deepcopy(self.last),self.received

    def recent_frames(self):
        """Return fresh bounded frames without exposing mutable history."""
        return tuple(frame for frame, _ in self.recent_frames_with_receipts())

    def original_frames_with_receipts(self,min_simulation_step=None):
        """Copy retained originals for audit; expired frames never become fresh sources.

        `min_simulation_step` filters before copying so a caller that needs only recent frames does not pay for
        the whole history. The default returns everything.
        """
        if min_simulation_step is not None and (type(min_simulation_step) is not int or min_simulation_step<0):
            raise ValueError('SCENE_STATE_QUERY_INVALID')
        with self._lock:
            if self.hazard:raise ValueError(self.hazard)
            return tuple((copy.deepcopy(frame),received) for frame,received in self._history
                         if min_simulation_step is None or frame['simulation_step']>=min_simulation_step)

    def recent_frames_with_receipts(self):
        """Return fresh scene steps with the receipt of each exact frame."""
        return tuple((copy.deepcopy(frame),received) for frame,received in self._fresh_history())

    def recent_steps(self):
        """Return the simulation steps of the fresh frames without copying any frame."""
        return tuple(frame['simulation_step'] for frame,_ in self._fresh_history())

    def ready_steps(self):
        """Fresh simulation steps for the readiness gate: stale or missing frames are an empty answer, not an error."""
        with self._lock:
            if self.hazard:raise ValueError(self.hazard)
            if self.last is None:return ()
            now=finite(self.monotonic(),nonnegative=True)
            return tuple(frame['simulation_step'] for frame,received in self._history
                         if self._fresh(frame,received,now))

    def _fresh_history(self):
        """Shared checks and freshness filter; entries are the retained originals, never copies."""
        with self._lock:
            if self.hazard:raise ValueError(self.hazard)
            if self.last is None:raise ValueError('SCENE_STATE_UNAVAILABLE')
            now=finite(self.monotonic(),nonnegative=True)
            if not self._fresh(self.last,self.received,now,log=True):raise ValueError('SCENE_STATE_STALE')
            return tuple((frame,received) for frame,received in self._history
                         if self._fresh(frame,received,now))

    def _fresh(self,frame,received,now,log=False):
        """Receipt-aged by default; producer-aged (source end of the frame) when a producer clock is bound."""
        if self.producer_now_ns is None:
            return 0<=now-received<=self.max_age
        age_ns=self.producer_now_ns()-frame['clock_interval_end_monotonic_ns']
        ok=0<=age_ns<=round(self.max_age*1e9)
        if not ok and log:self._log_refusal(age_ns)
        return ok

    def _log_refusal(self,age_ns):
        try:
            import json,sys
            print('TEACHER_DATA_AGE_REFUSAL '+json.dumps({'check':'scene_producer_age','age_ms':round(age_ns/1e6,3),
                'bound_ms':round(self.max_age*1e3,3),'reference':'scene_clock_interval_end'},sort_keys=True),
                file=sys.stderr,flush=True)
        except Exception:pass


class RosSceneStateAdapter:
    def __init__(self,node,observer,*,on_hazard,record_port=None,pending_reset_port=None,on_state=None,
                 subscription_depth=1):
        from so101_mujoco_support.msg import SceneStateEvidence
        from so101_demo.backends.mujoco.observer import ATOMIC_EVIDENCE_QOS
        from rclpy.qos import QoSProfile, HistoryPolicy, ReliabilityPolicy, DurabilityPolicy
        if type(subscription_depth) is not int or not 1<=subscription_depth<=256:
            raise ValueError('SCENE_SUBSCRIPTION_DEPTH_INVALID')
        qos=ATOMIC_EVIDENCE_QOS if subscription_depth==1 else QoSProfile(
            history=HistoryPolicy.KEEP_LAST,depth=subscription_depth,
            reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.observer,self.on_hazard,self.record_port=observer,on_hazard,record_port
        self.pending_reset_port=pending_reset_port;self.on_state=on_state;self._lock=threading.RLock()
        self._pending=None;self._stopped=False
        self.subscription=node.create_subscription(SceneStateEvidence,'/so101/simulation/scene_state',
            self.accept_message,qos)

    def _stop_if_hazard(self):
        if self.observer.hazard and not self._stopped:
            self._stopped=True;self.on_hazard(self.observer.hazard)

    def arm(self,snapshot):
        if snapshot.paused is not True or snapshot.simulation_step!=0:
            raise ValueError('SCENE_RESET_SNAPSHOT_INVALID')
        with self._lock:
            pending=self._pending;self._pending=None
            self.observer.reset(snapshot.simulation_session_id,snapshot.reset_epoch,
                source_floor_s=snapshot.simulation_time_s)
            self._stopped=False
            if pending is not None:
                first,latest=pending
                if ((first['simulation_session_id'],first['reset_epoch'])!=
                        (snapshot.simulation_session_id,snapshot.reset_epoch)
                        or abs(first['simulation_time_s']-snapshot.simulation_time_s)>1e-9):
                    self.observer.hazard='SCENE_RESET_FLOOR_INVALID'
                else:self.observer.accept(latest)
            self._stop_if_hazard()

    def accept_message(self,message):
        frame={key:list(getattr(message,key)) if key in ('qpos','qvel') else getattr(message,key)
            for key in SCENE_KEYS if key!='simulation_time_s'}
        frame['simulation_time_s']=message.header.stamp.sec+message.header.stamp.nanosec*1e-9
        with self._lock:
            try:
                if self.record_port is not None:self.record_port(copy.deepcopy(frame))
            except Exception:
                with self.observer._lock:self.observer.hazard='SCENE_STATE_RECORD_FAILED'
            try:
                accepted=False
                self.observer.validate(frame)
                identity=(frame['simulation_session_id'],frame['reset_epoch'])
                if self.observer.hazard:pass
                elif self._pending is not None and identity==(
                        self._pending[0]['simulation_session_id'],self._pending[0]['reset_epoch']):
                    first,latest=self._pending
                    if (frame['simulation_time_s']<latest['simulation_time_s']
                            or frame['simulation_step']<latest['simulation_step']):
                        raise ValueError('SCENE_STATE_REORDERED')
                    # Exactly two frames: immutable reset proof and latest
                    # complete state. Neither is usable before scalar reset arm.
                    self._pending=(first,copy.deepcopy(frame))
                elif (self.observer.epoch is None and frame['paused']
                        and frame['simulation_step']==0 and self.pending_reset_port is not None
                        and self.pending_reset_port(frame) is True):
                    self._pending=(copy.deepcopy(frame),copy.deepcopy(frame))
                elif (self.observer.epoch is not None
                        and identity==(self.observer.session,self.observer.epoch+1)
                        and frame['paused'] and frame['simulation_step']==0
                        and self.pending_reset_port is not None
                        and self.pending_reset_port(frame) is True):
                    self._pending=(copy.deepcopy(frame),copy.deepcopy(frame))
                elif (self.observer.epoch is not None
                        and identity==(self.observer.session,self.observer.epoch)
                        and frame['paused'] and frame['simulation_step']==0
                        and self.pending_reset_port is not None):
                    if self.pending_reset_port(frame) is not True:
                        raise ValueError('SCENE_RESET_PROOF_INVALID')
                    accepted=self.observer.accept(frame)
                else:accepted=self.observer.accept(frame)
                if accepted and self.observer.hazard is None and self.on_state is not None:
                    self.on_state(copy.deepcopy(frame))
            except (KeyError,TypeError,ValueError,RuntimeError) as error:
                self.observer.hazard=self.observer.hazard or str(error)
            self._stop_if_hazard()
