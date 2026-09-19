"""Content-bound actual scene coordinates are audit input, never policy features."""
import copy
import threading
import time
from so101_demo.act.contracts import fields,finite,identifier,integer,sha256,vector

SCENE_KEYS=frozenset(('simulation_session_id','reset_epoch','simulation_step','paused',
    'simulation_time_s','model_sha256','qpos','qvel'))


class SceneStateObserver:
    def __init__(self,*,model_sha256,nq,nv,max_age_s,monotonic=time.monotonic):
        sha256(model_sha256);integer(nq,minimum=1);integer(nv,minimum=1)
        self.model_sha256,self.nq,self.nv=model_sha256,nq,nv
        self.max_age=finite(max_age_s)
        if self.max_age<=0:raise ValueError('SCENE_STATE_CONFIG_INVALID')
        self.monotonic=monotonic;self._lock=threading.RLock()
        self.session=self.epoch=self.last=self.received=self.hazard=None

    def reset(self,session_id,reset_epoch,*,source_floor_s):
        identifier(session_id);integer(reset_epoch,minimum=1);floor=finite(source_floor_s,nonnegative=True)
        with self._lock:
            if self.session==session_id and self.epoch is not None and (reset_epoch<=self.epoch or floor<self.floor):
                raise ValueError('SCENE_STATE_RESET_INVALID')
            self.session,self.epoch,self.floor=session_id,reset_epoch,floor
            self.last=self.received=self.hazard=None

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
                self.last=copy.deepcopy(frame);self.received=finite(self.monotonic(),nonnegative=True)
                return True
            except (KeyError,TypeError,ValueError) as error:
                self.hazard=str(error);return False

    def validate(self,frame):
        fields(frame,SCENE_KEYS)
        identifier(frame['simulation_session_id']);integer(frame['reset_epoch'])
        integer(frame['simulation_step']);stamp=finite(frame['simulation_time_s'],nonnegative=True)
        sha256(frame['model_sha256'])
        if frame['model_sha256']!=self.model_sha256:raise ValueError('SCENE_STATE_MODEL_INVALID')
        if type(frame['paused']) is not bool:raise ValueError('SCENE_STATE_INVALID')
        vector(frame['qpos'],self.nq);vector(frame['qvel'],self.nv)
        return stamp

    def snapshot(self):
        with self._lock:
            if self.hazard:raise ValueError(self.hazard)
            if self.last is None:raise ValueError('SCENE_STATE_UNAVAILABLE')
            if not 0<=self.monotonic()-self.received<=self.max_age:raise ValueError('SCENE_STATE_STALE')
            return copy.deepcopy(self.last)


class RosSceneStateAdapter:
    def __init__(self,node,observer,*,on_hazard,record_port=None,pending_reset_port=None):
        from so101_mujoco_support.msg import SceneStateEvidence
        from so101_demo.backends.mujoco.observer import ATOMIC_EVIDENCE_QOS
        self.observer,self.on_hazard,self.record_port=observer,on_hazard,record_port
        self.pending_reset_port=pending_reset_port;self._lock=threading.RLock()
        self._pending=None;self._stopped=False
        self.subscription=node.create_subscription(SceneStateEvidence,'/so101/simulation/scene_state',
            self.accept_message,ATOMIC_EVIDENCE_QOS)

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
                elif (self.observer.epoch is not None
                        and identity==(self.observer.session,self.observer.epoch+1)
                        and frame['paused'] and frame['simulation_step']==0
                        and self.pending_reset_port is not None
                        and self.pending_reset_port(frame) is True):
                    self._pending=(copy.deepcopy(frame),copy.deepcopy(frame))
                else:self.observer.accept(frame)
            except (KeyError,TypeError,ValueError,RuntimeError) as error:
                self.observer.hazard=self.observer.hazard or str(error)
            self._stop_if_hazard()
