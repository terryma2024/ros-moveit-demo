"""Whole-robot contact evidence is audit input, never a policy observation."""

import math
import time
import threading
from collections import deque
from so101_demo.act.contracts import finite,identifier,integer,fields

CONTACT_KEYS=frozenset(('geom_a','geom_b','signed_distance_m','normal_force_n','truncated','evidence_loss'))
FRAME_KEYS=CONTACT_KEYS|frozenset(('simulation_session_id','reset_epoch','physics_step','simulation_time_s'))


def contact_hazard(frame,allowed_pairs):
    try:
        if not isinstance(frame,dict) or set(frame) not in (CONTACT_KEYS,FRAME_KEYS):return True
        if type(frame['truncated']) is not bool or type(frame['evidence_loss']) is not bool:return True
        if frame['truncated'] or frame['evidence_loss']:return True
        arrays=[frame[key] for key in ('geom_a','geom_b','signed_distance_m','normal_force_n')]
        if any(not isinstance(value,(list,tuple)) for value in arrays):return True
        if len({len(value) for value in arrays})!=1:return True
        if not isinstance(allowed_pairs,(set,frozenset)):return True
        for pair in allowed_pairs:
            if not isinstance(pair,tuple) or len(pair)!=2 or tuple(sorted(pair))!=pair:return True
            for name in pair:identifier(name)
        for a,b,distance,force in zip(*arrays,strict=True):
            identifier(a);identifier(b);finite(distance);finite(force,nonnegative=True)
            if tuple(sorted((a,b))) not in allowed_pairs:return True
        return False
    except (KeyError,TypeError,ValueError):return True


class RobotContactObserver:
    def __init__(self,*,known_geoms,allowed_pairs,max_age_s,max_sim_gap_s,monotonic=time.monotonic):
        self._lock=threading.RLock()
        self.known=frozenset(known_geoms);self.allowed=frozenset(allowed_pairs)
        if not self.known:raise ValueError('CONTACT_CONFIG_INVALID')
        for name in self.known:identifier(name)
        for pair in self.allowed:
            if len(pair)!=2 or tuple(sorted(pair))!=pair or not set(pair)<=self.known:raise ValueError('CONTACT_CONFIG_INVALID')
        self.max_age=finite(max_age_s);self.max_gap=finite(max_sim_gap_s)
        if self.max_age<=0 or self.max_gap<=0:raise ValueError('CONTACT_CONFIG_INVALID')
        self.monotonic=monotonic;self.session=None;self.epoch=None;self.last=None;self.received=None;self.hazard=None

    def reset(self,session_id,reset_epoch,*,source_floor_s):
        with self._lock:
            identifier(session_id);integer(reset_epoch);floor=finite(source_floor_s,nonnegative=True)
            if self.session==session_id and self.epoch is not None and reset_epoch<=self.epoch:
                raise ValueError('CONTACT_RESET_EPOCH_INVALID')
            self.session,self.epoch,self.floor=session_id,reset_epoch,floor
            self.last=self.received=self.hazard=None

    def accept(self,frame):
        with self._lock:
            try:
                fields(frame,FRAME_KEYS)
                if (frame['simulation_session_id'],frame['reset_epoch'])!=(self.session,self.epoch):raise ValueError('CONTACT_IDENTITY_INVALID')
                integer(frame['reset_epoch']);integer(frame['physics_step'],minimum=1)
                stamp=finite(frame['simulation_time_s'],nonnegative=True)
                if stamp<=self.floor:raise ValueError('CONTACT_TIME_INVALID')
                expected=1 if self.last is None else self.last['physics_step']+1
                if frame['physics_step']!=expected:raise ValueError('CONTACT_STEP_GAP')
                previous=self.floor if self.last is None else self.last['simulation_time_s']
                if not 0<stamp-previous<=self.max_gap+1e-12:raise ValueError('CONTACT_TIME_GAP')
                if any(name not in self.known for key in ('geom_a','geom_b') for name in frame[key]):raise ValueError('CONTACT_UNKNOWN_GEOM')
                if contact_hazard(frame,self.allowed):self.hazard=self.hazard or 'ROBOT_CONTACT_HAZARD'
                self.last={key:list(value) if isinstance(value,(list,tuple)) else value for key,value in frame.items()}
                self.received=finite(self.monotonic(),nonnegative=True)
            except (KeyError,TypeError,ValueError) as error:self.hazard=self.hazard or str(error)

    def latch(self, reason):
        identifier(reason)
        with self._lock:self.hazard=self.hazard or reason

    def safe(self):
        with self._lock:
            if self.hazard or self.last is None or self.received is None:return False
            now=finite(self.monotonic(),nonnegative=True)
            return 0<=now-self.received<=self.max_age


class RosRobotContactAdapter:
    def __init__(self,node,observer,*,on_hazard,pending_capacity=5000,record_port=None):
        from so101_mujoco_support.msg import RobotContactEvidence
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        integer(pending_capacity,minimum=1)
        if not callable(on_hazard):raise ValueError('CONTACT_HAZARD_PORT_INVALID')
        self.observer,self.on_hazard,self.record_port=observer,on_hazard,record_port
        self._lock=threading.RLock();self._pending=deque(maxlen=pending_capacity)
        self._lost_epochs=set();self._record_failed_epochs=set()
        self._armed=False;self._stopped=False;self.rejections=deque(maxlen=32)
        self.subscription=node.create_subscription(RobotContactEvidence,'/so101/simulation/robot_contacts',
            self.accept_message,QoSProfile(depth=10000,reliability=ReliabilityPolicy.RELIABLE))

    def arm(self,reset_snapshot):
        if reset_snapshot.paused is not True or reset_snapshot.simulation_step!=0:
            raise ValueError('CONTACT_RESET_SNAPSHOT_INVALID')
        with self._lock:
            self.observer.reset(reset_snapshot.simulation_session_id,reset_snapshot.reset_epoch,
                source_floor_s=reset_snapshot.simulation_time_s)
            self._armed=True;self._stopped=False
            identity=(self.observer.session,self.observer.epoch)
            if identity in self._record_failed_epochs:self.observer.latch('CONTACT_RECORD_FAILED')
            if identity in self._lost_epochs:self.observer.latch('CONTACT_RECEIVER_OVERFLOW')
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
