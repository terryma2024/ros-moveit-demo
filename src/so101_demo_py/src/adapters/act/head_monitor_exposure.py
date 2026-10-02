"""Single-use inference admission from the existing CPU monitor's originals.

This object owns no ROS, CUDA, motion capability or worker. The monitor's existing
watchdog expires its immutable original-receipt deadline independently of the
primary heartbeat. A completion received after that deadline cannot release it.
"""
import json
import math
import re
import threading
import time

from so101_demo.act.head_feedback import nanoseconds
from so101_demo.act.head_monitor import digest

_SHA=re.compile(r'[0-9a-f]{64}\Z')
_CLAIM={'epoch','generation','session_id','policy_sha256','sequence',
    'image_source_ns','info_source_ns','joint_source_ns','tf_source_ns','image_frame_id',
    'payload_sha256','image_received_wall_s','info_received_wall_s','deadline_ns'}
_COMPLETION={'exposure_sha256','sequence','image_source_ns','completion_wall_s','result_sha256'}


def _integer(value):return type(value) is int and 0<value<2**64
def _wall(value):return type(value) in (int,float) and math.isfinite(value) and value>=0
def _sha(value):return type(value) is str and _SHA.fullmatch(value) is not None
def _wire(value):return json.loads(json.dumps(value,allow_nan=False))


class _Expired(PermissionError):
    def __init__(self,deadline):
        super().__init__('HEAD_MONITOR_EXPOSURE_DEADLINE');self.deadline=deadline


class HeadMonitorExposures:
    def __init__(self,runtime):
        self.runtime=runtime;self._lock=threading.Lock()
        self._active=None;self._sequence=0;self._source_floor=0;self._expiry_reported=False

    def summary(self):
        with self._lock:
            return _wire(dict(sequence=self._sequence,source_floor_ns=self._source_floor,
                active=self._active,expiry_reported=self._expiry_reported))

    def poll(self,wall):
        with self._lock:
            active=self._active
            expired=active is not None and nanoseconds(wall)>=active['deadline_ns']
            report=expired and not self._expiry_reported
            if report:self._expiry_reported=True
        if expired:
            self.runtime.fault('HEAD_MONITOR_EXPOSURE_DEADLINE',active['deadline_ns']*1e-9)
            if report:
                try:self.runtime._emit('EXPOSURE_EXPIRED',exposure=active,observed_wall_s=wall)
                except Exception:self.runtime.fault('HEAD_MONITOR_EXPOSURE_JOURNAL_FAILED',wall)

    def _current(self):
        runtime=self.runtime;observer=runtime._observer
        if (not runtime.configured or runtime._finished or runtime._policy is None
                or runtime.revoked or runtime.epoch.stage!='ARMED_READY'
                or observer is None or not observer._active or observer.failed):
            raise PermissionError('HEAD_MONITOR_EXPOSURE_STAGE_INVALID')
        watchdog=runtime._watchdog_wall;now=observer.monotonic()
        self.poll(now)
        if runtime.revoked:raise PermissionError('HEAD_MONITOR_EXPOSURE_REVOKED')
        if watchdog is None:raise PermissionError('HEAD_MONITOR_EXPOSURE_WATCHDOG_STALE')
        limit=math.floor(observer._policy.watchdog_reaction_limit_s*1e9)
        gap=nanoseconds(now)-nanoseconds(watchdog)
        if not 0<=gap<=limit:
            runtime.fault('HEAD_MONITOR_EXPOSURE_WATCHDOG_STALE',
                (nanoseconds(watchdog)+limit)*1e-9 if gap>limit else now)
            raise PermissionError('HEAD_MONITOR_EXPOSURE_WATCHDOG_STALE')
        observer.poll(watchdog=False)
        original=observer.port.original_feedback_snapshot()
        observer._policy.check_joint(original['sample'],original['decision'])
        with observer._lock:clock=None if observer._clock is None else dict(observer._clock)
        decision=original['decision']
        if (clock is None or not clock['valid'] or not 0<clock['source_ns']<=decision['sim_ns']
                or not 0<=nanoseconds(decision['wall_after_s'])-nanoseconds(clock['wall_s'])
                    <=math.floor(observer._policy.clock_interarrival_deadline_s*1e9)
                or runtime.revoked or observer.failed):
            raise PermissionError('HEAD_MONITOR_EXPOSURE_CURRENT_INPUTS_INVALID')
        return original,clock,watchdog

    def admit(self,record):
        runtime=self.runtime;observer=runtime._observer
        try:
            original,clock,watchdog=self._current()
            now=original['decision']['wall_after_s'];now_ns=nanoseconds(now)
            if (type(record) is not dict or set(record)!=_CLAIM
                    or any(not _integer(record[key]) for key in ('generation','sequence',
                        'image_source_ns','info_source_ns','joint_source_ns','tf_source_ns','deadline_ns'))
                    or record['epoch']!=runtime.epoch.epoch
                    or record['generation']!=runtime.epoch.generation
                    or record['session_id']!=runtime.epoch.session_id
                    or record['policy_sha256']!=runtime.epoch.policy_hash
                    or record['image_frame_id']!=observer.camera_frame
                    or not _sha(record['payload_sha256'])
                    or any(not _wall(record[key]) or nanoseconds(record[key])>now_ns
                        for key in ('image_received_wall_s','info_received_wall_s'))):
                raise PermissionError('HEAD_MONITOR_EXPOSURE_CLAIM_INVALID')
            source=record['image_source_ns']
            with observer._lock:
                image=observer._images.get(source)
                if image is None and observer._camera is not None and observer._camera['source_ns']==source:
                    image=observer._camera
                image=None if image is None else dict(image)
                info=observer._infos.get(source)
                info=None if info is None else dict(info)
            with observer.port._lock:
                samples=tuple(dict(value) for value in observer.port._head_samples)
            causal=None
            for value in samples:
                if value['source_ns']<=source:causal=value
            age=math.floor(observer.camera_age*1e9)
            skew=observer.camera_skew
            if (not _wall(skew) or not 0<skew<=.05 or image is None or info is None
                    or not image['valid'] or not info['valid'] or record['info_source_ns']!=source
                    or image['payload_sha256']!=record['payload_sha256']
                    or image['frame_id']!=record['image_frame_id'] or info['frame_id']!=image['frame_id']
                    or any(not 0<=now_ns-nanoseconds(value['wall_s'])<age for value in (image,info))
                    or not 0<=original['decision']['sim_ns']-source
                        <=math.floor(observer._policy.camera_max_source_age_s*1e9)
                    or causal is None or not causal['valid'] or nanoseconds(causal['wall_s'])>now_ns
                    or record['joint_source_ns']!=causal['source_ns']
                    or not 0<=source-causal['source_ns']<=math.floor(skew*1e9)
                    or not 0<=source-record['tf_source_ns']<=math.floor(skew*1e9)):
                raise PermissionError('HEAD_MONITOR_EXPOSURE_ORIGINAL_MISMATCH')
            root_deadline=min(nanoseconds(record['image_received_wall_s']),
                nanoseconds(record['info_received_wall_s']))+age
            if record['deadline_ns']!=root_deadline:
                raise PermissionError('HEAD_MONITOR_EXPOSURE_DEADLINE_CHANGED')
            deadline=min(root_deadline,nanoseconds(image['wall_s'])+age,nanoseconds(info['wall_s'])+age)
            snapshot=_wire(dict(image=image,info=info,joint=causal,current_joint=original['sample'],
                decision=original['decision'],clock=clock,watchdog_wall_s=watchdog))
            claim=_wire(record)
            token=digest(dict(root_claim=claim,original_snapshot=snapshot,deadline_ns=deadline))
            active=dict(exposure_sha256=token,sequence=record['sequence'],image_source_ns=source,
                deadline_ns=deadline,ack_wall_s=observer.monotonic(),
                root_claim=claim,original_snapshot=snapshot)
            if nanoseconds(active['ack_wall_s'])>=deadline:
                runtime.fault('HEAD_MONITOR_EXPOSURE_DEADLINE',deadline*1e-9)
                raise PermissionError('HEAD_MONITOR_EXPOSURE_DEADLINE')
            with self._lock:
                committed_wall=observer.monotonic()
                expired=nanoseconds(committed_wall)>=deadline
                if (self._active is not None or record['sequence']!=self._sequence+1
                        or source<=self._source_floor or runtime.revoked or observer.failed or expired):
                    # Fault reporting belongs outside this short state lock.
                    # Preserve the original deadline if it crossed before commit.
                    if expired:raise _Expired(deadline)
                    raise PermissionError('HEAD_MONITOR_EXPOSURE_REUSED_OR_REVOKED')
                self._active=active;self._sequence=record['sequence'];self._source_floor=source
                self._expiry_reported=False
            self.poll(observer.monotonic())
            if runtime.revoked:raise PermissionError('HEAD_MONITOR_EXPOSURE_REVOKED')
            ack=dict(active,stage='ARMED_READY',exposure_admitted=True,motion_authority=False)
            runtime._emit('EXPOSURE_ADMITTED',ack=ack)
            return _wire(ack)
        except Exception as error:
            if isinstance(error,_Expired):runtime.fault('HEAD_MONITOR_EXPOSURE_DEADLINE',error.deadline*1e-9)
            runtime.fault('HEAD_MONITOR_EXPOSURE_ADMISSION_REFUSED',
                observer.monotonic() if observer is not None else time.monotonic())
            raise PermissionError('HEAD_MONITOR_EXPOSURE_ADMISSION_REFUSED') from error

    def finish(self,record):
        runtime=self.runtime;observer=runtime._observer
        try:
            original,clock,watchdog=self._current()
            with self._lock:active=self._active
            if (type(record) is not dict or set(record)!=_COMPLETION or active is None
                    or not _sha(record['exposure_sha256']) or not _sha(record['result_sha256'])
                    or any(not _integer(record[key]) for key in ('sequence','image_source_ns'))
                    or any(record[key]!=active[key] for key in ('exposure_sha256','sequence','image_source_ns'))
                    or not _wall(record['completion_wall_s'])
                    or not nanoseconds(active['ack_wall_s'])<=nanoseconds(record['completion_wall_s'])
                        <=nanoseconds(original['decision']['wall_after_s'])
                    or nanoseconds(record['completion_wall_s'])>=active['deadline_ns']):
                raise PermissionError('HEAD_MONITOR_EXPOSURE_COMPLETION_INVALID')
            now=observer.monotonic();self.poll(now)
            with self._lock:
                now=observer.monotonic()
                if nanoseconds(now)>=active['deadline_ns']:
                    raise _Expired(active['deadline_ns'])
                if runtime.revoked or observer.failed or self._active is not active:
                    raise PermissionError('HEAD_MONITOR_EXPOSURE_COMPLETION_REVOKED')
                self._active=None
            ack=dict(record,stage='ARMED_READY',exposure_finished=True,ack_wall_s=now,
                deadline_ns=active['deadline_ns'],motion_authority=False,
                original_snapshot=_wire(dict(current_joint=original['sample'],decision=original['decision'],
                    clock=clock,watchdog_wall_s=watchdog)))
            runtime._emit('EXPOSURE_FINISHED',ack=ack)
            return ack
        except Exception as error:
            if isinstance(error,_Expired):runtime.fault('HEAD_MONITOR_EXPOSURE_DEADLINE',error.deadline*1e-9)
            runtime.fault('HEAD_MONITOR_EXPOSURE_COMPLETION_REFUSED',
                observer.monotonic() if observer is not None else time.monotonic())
            raise PermissionError('HEAD_MONITOR_EXPOSURE_COMPLETION_REFUSED') from error
