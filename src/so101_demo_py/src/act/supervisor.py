"""Attempt-scoped physical evidence gates; never generates a recovery trajectory."""

import threading
import time
from .contracts import fields,finite,identifier,integer,vector,sha256,validate_action_prefix
from .deadline import Deadline
from .execution import bounded_positions
from .trajectory import controller_point

EVIDENCE_SOURCES=frozenset(('joints','cup','contacts','head','wrist'))
BOOL_FIELDS=frozenset(('target_visible','bilateral_contact','micro_lift_confirmed','cup_off_table',
    'cup_supported','robot_contacts_safe','released','placement_stable','retreat_stable','planning_attached'))
SNAPSHOT_KEYS=frozenset(('session_id','attempt_id','reset_epoch','release_epoch','sim_time_s',
    'source_times_s','received_wall_s','arm_positions','arm_velocities','neck_yaw_rad','holding_state','phase',
    'controller_start_time_s','controller_start_positions','controller_start_velocities','controller_bridge','model_sha256','model_qpos','cup_in_gripper_transform'))|BOOL_FIELDS
PHASES=frozenset(('APPROACH','CONTACT','LIFT','TRANSPORT','RELEASE','RETREAT','FINAL'))


def release_allowed(holding,opening,supported,fresh):
    if any(type(value) is not bool for value in (holding,opening,supported,fresh)):
        raise ValueError('RELEASE_STATE_INVALID')
    return not (holding and opening) or (supported and fresh)


def validate_snapshot(snapshot):
    fields(snapshot,SNAPSHOT_KEYS)
    for key in ('session_id','attempt_id'):identifier(snapshot[key])
    for key in ('reset_epoch','release_epoch'):integer(snapshot[key])
    finite(snapshot['sim_time_s'],nonnegative=True);finite(snapshot['neck_yaw_rad'])
    bounded_positions(snapshot['arm_positions']);vector(snapshot['arm_velocities'],6)
    bounded_positions(snapshot['controller_start_positions'])
    vector(snapshot['controller_start_velocities'],6);sha256(snapshot['model_sha256'])
    finite(snapshot['controller_start_time_s'],nonnegative=True)
    fields(snapshot['controller_bridge'],('time_s','point'))
    before=finite(snapshot['controller_bridge']['time_s'],nonnegative=True)
    bridge=controller_point(snapshot['controller_bridge']['point'])
    bounded_positions(bridge['positions'])
    if not before<=snapshot['sim_time_s'] or not before<snapshot['controller_start_time_s']:
        raise ValueError('SNAPSHOT_BRIDGE_INVALID')
    fields(snapshot['source_times_s'],EVIDENCE_SOURCES);fields(snapshot['received_wall_s'],EVIDENCE_SOURCES)
    for key in EVIDENCE_SOURCES:
        finite(snapshot['source_times_s'][key],nonnegative=True)
        finite(snapshot['received_wall_s'][key],nonnegative=True)
    if any(type(snapshot[key]) is not bool for key in BOOL_FIELDS):raise ValueError('SNAPSHOT_BOOL_INVALID')
    if snapshot['holding_state'] not in ('EMPTY','HOLDING','UNKNOWN') or snapshot['phase'] not in PHASES:
        raise ValueError('SNAPSHOT_STATE_INVALID')
    if not isinstance(snapshot['model_qpos'],(list,tuple)):raise ValueError('SNAPSHOT_QPOS_INVALID')
    for value in snapshot['model_qpos']:finite(value)
    attachment=snapshot['cup_in_gripper_transform']
    if attachment is not None:
        if not isinstance(attachment,(list,tuple)) or len(attachment)!=4:raise ValueError('SNAPSHOT_ATTACHMENT_INVALID')
        for row in attachment:vector(row,4)
    return snapshot


class ActSupervisor:
    def __init__(self,execution,physics,*,deadline,initial_snapshot,max_age_s,max_skew_s,
                 max_neck_drift_rad,visibility_occlusion_s,opening_delta_rad,permit_port,
                 monotonic=time.monotonic):
        validate_snapshot(initial_snapshot)
        if not isinstance(deadline,Deadline) or not callable(permit_port):raise ValueError('SUPERVISOR_CONFIG_INVALID')
        values=tuple(finite(v) for v in (max_age_s,max_skew_s,max_neck_drift_rad,visibility_occlusion_s,opening_delta_rad))
        if min(values)<=0:raise ValueError('SUPERVISOR_CONFIG_INVALID')
        self.max_age,self.max_skew,self.max_drift,self.occlusion,self.open_delta=values
        self.execution,self.physics,self.deadline,self.permit_port=execution,physics,deadline,permit_port
        self.monotonic=monotonic;self._lock=threading.RLock()
        self.identity=(initial_snapshot['session_id'],initial_snapshot['attempt_id'],initial_snapshot['reset_epoch'])
        self.neck=initial_snapshot['neck_yaw_rad'];self.initial_release=initial_snapshot['release_epoch']
        self.release_epoch=None;self.release_time=None;self.last_sim=initial_snapshot['sim_time_s']
        self.last_visible_wall=deadline.started_wall_s if initial_snapshot['target_visible'] else None
        self.state='EMPTY';self.reason=None;self.ever_held=False

    def _fail(self,reason):
        if self.reason is None:
            self.reason=reason;self.state='STOPPING';self.execution.invalidate(reason)
        if self.execution.poll_stop()=='STOPPED':self.state='STOPPED'
        return self.state

    def _verify(self,snapshot,now):
        try:validate_snapshot(snapshot)
        except (KeyError,TypeError,ValueError):return 'SUPERVISOR_SNAPSHOT_INVALID'
        if (snapshot['session_id'],snapshot['attempt_id'],snapshot['reset_epoch'])!=self.identity:
            return 'SUPERVISOR_SCOPE_INVALID'
        stamp=snapshot['sim_time_s']
        if self.release_epoch is not None and snapshot['release_epoch']!=self.release_epoch:
            return 'RELEASE_EPOCH_INVALID'
        if stamp<self.last_sim:return 'EVIDENCE_STALE'
        if any(not 0<=now-value<=self.max_age for value in snapshot['received_wall_s'].values()):return 'EVIDENCE_STALE'
        if any(not 0<=stamp-value<=self.max_skew for value in snapshot['source_times_s'].values()):return 'EVIDENCE_STALE'
        if snapshot['robot_contacts_safe'] is not True:return 'ROBOT_CONTACT_HAZARD'
        if abs(snapshot['neck_yaw_rad']-self.neck)>self.max_drift:return 'NECK_DRIFT'
        if snapshot['holding_state']=='UNKNOWN':return 'HOLDING_UNKNOWN'
        if snapshot['target_visible']:
            self.last_visible_wall=now
        elif not (snapshot['phase']=='CONTACT' and self.last_visible_wall is not None
                  and 0<=now-self.last_visible_wall<=self.occlusion):return 'TARGET_LOST'
        if self.release_epoch is None:
            if snapshot['release_epoch']!=self.initial_release:
                if (snapshot['release_epoch']!=self.initial_release+1 or not self.ever_held
                        or not snapshot['released'] or snapshot['planning_attached'] or not snapshot['cup_supported']
                        or stamp<=self.last_sim
                        or any(snapshot['source_times_s'][key]<=self.last_sim for key in ('cup','contacts','joints'))):
                    return 'RELEASE_EPOCH_INVALID'
            elif snapshot['released']:return 'RELEASE_EPOCH_INVALID'
        elif (snapshot['release_epoch']!=self.release_epoch or stamp<self.release_time
              or any(value<self.release_time for key,value in snapshot['source_times_s'].items()
                     if key in ('cup','contacts','joints'))):return 'RELEASE_EPOCH_INVALID'
        if snapshot['holding_state']=='HOLDING':
            required=('bilateral_contact',) if self.ever_held else ('bilateral_contact','micro_lift_confirmed','cup_off_table')
            if not all(snapshot[key] for key in required):return 'HOLD_NOT_CONFIRMED'
        return None

    def tick(self,snapshot,now_wall_s):
        with self._lock:
            if self.reason is not None:return self._fail(self.reason)
            try:
                now=finite(now_wall_s,nonnegative=True)
                if self.deadline.expired(now):return self._fail('ACT_TIMEOUT')
            except ValueError:return self._fail('SUPERVISOR_CLOCK_INVALID')
            reason=self._verify(snapshot,now)
            if reason:return self._fail(reason)
            self.last_sim=snapshot['sim_time_s']
            if self.release_epoch is None and snapshot['release_epoch']==self.initial_release+1:
                self.release_epoch=snapshot['release_epoch'];self.release_time=snapshot['sim_time_s']
                self.state='RELEASE_CONFIRMED';return self.state
            if self.release_epoch is not None:
                if snapshot['holding_state']!='EMPTY' or not snapshot['released']:
                    return self._fail('RELEASE_NOT_CONFIRMED')
                if snapshot['phase'] not in ('RELEASE','RETREAT','FINAL'):return self._fail('RELEASE_EPOCH_INVALID')
                if snapshot['phase'] in ('RETREAT','FINAL'):
                    self.state='ACT_RETREAT'
                    if snapshot['retreat_stable']:
                        self.state='VALIDATE_FINAL_PLACEMENT'
                        if snapshot['placement_stable'] and snapshot['cup_supported']:self.state='DONE'
                return self.state
            self.state=snapshot['holding_state']
            if self.state=='HOLDING':self.ever_held=True
            elif self.ever_held:return self._fail('HOLD_LOST')
            return self.state

    def check(self,prefix,snapshot):
        checked=validate_action_prefix(prefix)
        for row in checked['positions']:bounded_positions(row)
        with self._lock:
            state=self.tick(snapshot,self.monotonic())
            if state in ('STOPPING','STOPPED','DONE'):raise PermissionError(self.reason or 'SUBMISSION_DISABLED')
            if (checked['session_id'],checked['attempt_id'])!=self.identity[:2]:raise PermissionError('SUPERVISOR_SCOPE_INVALID')
            if not 0<=snapshot['sim_time_s']-checked['observation_time_s']<=self.max_skew:
                raise PermissionError('PREFIX_STALE')
            # The actual model opens as joint 6 decreases. Approving one tick at
            # a potential release boundary keeps future opening out of a queue.
            opening=any(row[5]<snapshot['arm_positions'][5]-self.open_delta for row in checked['positions'])
            if state=='HOLDING' and opening:
                if not release_allowed(True,True,snapshot['cup_supported'],True):raise PermissionError('UNSUPPORTED_RELEASE')
                if snapshot['planning_attached']:raise PermissionError('DETACH_REQUIRED')
                if len(checked['positions'])!=1:raise PermissionError('RELEASE_PREFIX_BOUNDARY')
        # Slow independent reconstruction must not serialize watchdog/Stop.
        safe=self.physics.check_path(checked,snapshot)
        with self._lock:
            state=self.tick(snapshot,self.monotonic())
            if state in ('STOPPING','STOPPED','DONE'):raise PermissionError(self.reason or 'SUBMISSION_DISABLED')
            if safe is not True:raise PermissionError('PATH_REJECTED')
        permit=self.permit_port(checked,snapshot)
        with self._lock:
            state=self.tick(snapshot,self.monotonic())
            if state in ('STOPPING','STOPPED','DONE'):raise PermissionError(self.reason or 'SUBMISSION_DISABLED')
            return permit
