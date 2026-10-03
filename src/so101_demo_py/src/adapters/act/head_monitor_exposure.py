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
_MEASUREMENT_CLAIM=_CLAIM-{'policy_sha256','sequence','deadline_ns'}


def _integer(value):return type(value) is int and 0<value<2**64
def _wall(value):return type(value) in (int,float) and math.isfinite(value) and value>=0
def _sha(value):return type(value) is str and _SHA.fullmatch(value) is not None
def _wire(value):return json.loads(json.dumps(value,allow_nan=False))


def _received_original(value,*,source,frame,decision_ns,payload_sha256=None):
    """Common physical original checks; this never issues an admission."""
    if (type(value) is not dict or value.get('valid') is not True
            or value.get('source_ns')!=source or value.get('frame_id')!=frame
            or not _wall(value.get('wall_s')) or nanoseconds(value['wall_s'])>decision_ns
            or payload_sha256 is not None and value.get('payload_sha256')!=payload_sha256):
        raise PermissionError('HEAD_MONITOR_EXPOSURE_ORIGINAL_MISMATCH')


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

    def measure(self,claim,*,completion=None):
        """Read actual pre-policy CPU consumers, without leases or readiness.

        No unknown camera/J age bound is guessed here. The complete stopped
        cohort measures those bounds; the existing 10ms progress limits and
        original validity, scope, source order and quietness still apply.
        """
        runtime=self.runtime;observer=runtime._observer
        phase='stage';snapshot=None;original_claim=None
        try:
            if (not runtime.configured or runtime._finished or runtime.revoked
                    or runtime.epoch.stage!='PRESENT' or runtime._policy is not None
                    or observer is None or observer._active or observer.failed
                    or observer.port.feedback_policy is not None):
                raise PermissionError('HEAD_MONITOR_MEASUREMENT_STAGE_INVALID')
            phase='claim'
            if (type(claim) is not dict or set(claim)!=_MEASUREMENT_CLAIM
                    or any(not _integer(claim[key]) for key in ('generation','image_source_ns',
                        'info_source_ns','joint_source_ns','tf_source_ns'))
                    or claim['epoch']!=runtime.epoch.epoch or claim['generation']!=runtime.epoch.generation
                    or claim['session_id']!=runtime.epoch.session_id or not _sha(claim['payload_sha256'])
                    or claim['image_frame_id']!=observer.camera_frame):
                raise PermissionError('HEAD_MONITOR_MEASUREMENT_CLAIM_INVALID')
            original_claim=claim;phase='snapshot'
            source=claim['image_source_ns']
            with observer._lock:
                image=observer._images.get(source)
                if image is None and observer._camera is not None and observer._camera['source_ns']==source:
                    image=observer._camera
                image=None if image is None else dict(image)
                info=observer._infos.get(source);info=None if info is None else dict(info)
                watermarks=(observer._image_source,observer._info_source)
                clock=None if observer._clock is None else dict(observer._clock)
                executor=observer._executor_wall
            with observer.port._lock:
                causal=next((dict(row) for row in reversed(observer.port._head_samples)
                    if row['source_ns']<=source),None)
            watchdog=runtime._watchdog_wall
            original=observer.port.original_feedback_snapshot();decision=original['decision']
            now_ns=nanoseconds(decision['wall_after_s']);current=original['sample']
            snapshot=dict(image=image,info=info,joint=causal,current_joint=current,
                decision=decision,clock=clock,watchdog_wall_s=watchdog,executor_wall_s=executor)
            phase='current'
            if (any(not _wall(wall) or not 0<=now_ns-nanoseconds(wall)<=10_000_000
                    for wall in (watchdog,executor))
                    or current is None or current.get('valid') is not True
                    or not _wall(current['wall_s']) or nanoseconds(current['wall_s'])>now_ns
                    or not 0<current['source_ns']<=decision['sim_ns']
                    or any(not math.isfinite(value) or abs(value)>observer.port.stop_velocity
                        for value in current['velocities'])
                    or clock is None or clock.get('valid') is not True
                    or not 0<clock['source_ns']<=decision['sim_ns']
                    or not _wall(clock['wall_s']) or nanoseconds(clock['wall_s'])>now_ns):
                raise PermissionError('HEAD_MONITOR_MEASUREMENT_CURRENT_INVALID')
            phase='original'
            if (claim['info_source_ns']!=source or source>decision['sim_ns']
                    or causal is None or causal.get('valid') is not True
                    or claim['joint_source_ns']!=causal['source_ns']
                    or not 0<claim['tf_source_ns']<=source
                    or not _wall(causal['wall_s']) or nanoseconds(causal['wall_s'])>now_ns
                    or any(not _wall(claim[key]) or nanoseconds(claim[key])>now_ns
                        for key in ('image_received_wall_s','info_received_wall_s'))):
                raise PermissionError('HEAD_MONITOR_MEASUREMENT_ORIGINAL_INVALID')
            phase='received'
            for value,watermark in zip((image,info),watermarks):
                if value is None:
                    if watermark>=source:raise PermissionError('HEAD_MONITOR_MEASUREMENT_RECEIVED_MISSING')
                else:_received_original(value,source=source,frame=claim['image_frame_id'],
                    decision_ns=now_ns,payload_sha256=claim['payload_sha256'] if value is image else None)
            ready=image is not None and info is not None
            phase='completion'
            if completion is not None:
                if (not ready or type(completion) is not dict
                        or set(completion)!={'claim','completion_wall_s','result_sha256'}
                        or completion['claim']!=claim or not _sha(completion['result_sha256'])
                        or not _wall(completion['completion_wall_s'])
                        or not max(nanoseconds(claim['image_received_wall_s']),
                            nanoseconds(claim['info_received_wall_s']))
                            <=nanoseconds(completion['completion_wall_s'])<=now_ns):
                    raise PermissionError('HEAD_MONITOR_MEASUREMENT_COMPLETION_INVALID')
            if runtime.revoked or observer.failed:raise PermissionError('HEAD_MONITOR_MEASUREMENT_REVOKED')
            phase='reply';snapshot=_wire(snapshot)
            reply=dict(stage='CONFIGURED',calibration_measurement=True,motion_authority=False,
                inputs_ready=ready,root_claim=_wire(claim),original_snapshot=snapshot,
                ack_wall_s=observer.monotonic())
            if completion is not None:reply.update(measurement_complete=True,completion=_wire(completion))
            if ready:runtime._emit('CALIBRATION_FRAME_COMPLETION' if completion is not None else
                'CALIBRATION_FRAME_INPUTS',measurement=reply)
            return reply
        except Exception as error:
            runtime.fault('HEAD_MONITOR_MEASUREMENT_REFUSED',
                observer.monotonic() if observer is not None else time.monotonic())
            # Admission/native-fault latches precede all audit encoding. Retain
            # the originals already copied for this decision, never new clocks
            # or a refreshed snapshot after failure. No exception formatter runs.
            try:
                args=BaseException.args.__get__(error)
                code=(args[0] if args and type(args[0]) is str and len(args[0])<=128
                    and args[0].startswith('HEAD_') else None)
                runtime._emit('CALIBRATION_MEASUREMENT_REFUSED',
                    operation='CALIBRATION_FRAME_INPUTS' if completion is None else 'CALIBRATION_FRAME_COMPLETION',
                    phase=phase,error_type=type(error).__name__,error_code=code,
                    root_claim=_wire(original_claim),original_snapshot=_wire(snapshot))
            except Exception:pass
            raise PermissionError('HEAD_MONITOR_MEASUREMENT_REFUSED') from error

    def inputs(self,record):
        """Observe matching CPU originals without creating an inference lease.

        Only an original that has not physically arrived may be pending. A
        received but missing, invalid or mismatched original is a refusal.
        The subsequent admission independently rechecks the complete claim.
        """
        runtime=self.runtime;observer=runtime._observer
        try:
            if (type(record) is not dict or set(record)!=_CLAIM
                    or not _integer(record['image_source_ns'])):
                raise PermissionError('HEAD_MONITOR_EXPOSURE_CLAIM_INVALID')
            source=record['image_source_ns']
            # Copy originals and physical arrival watermarks before the
            # decision clocks. Later callbacks belong to the next query.
            with observer._lock:
                image=observer._images.get(source)
                if image is None and observer._camera is not None and observer._camera['source_ns']==source:
                    image=observer._camera
                image=None if image is None else dict(image)
                info=observer._infos.get(source);info=None if info is None else dict(info)
                image_source=observer._image_source;info_source=observer._info_source
            original,_,_=self._current()
            now_ns=nanoseconds(original['decision']['wall_after_s'])
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
            source=record['image_source_ns'];age=math.floor(observer.camera_age*1e9)
            deadline=min(nanoseconds(record['image_received_wall_s']),
                nanoseconds(record['info_received_wall_s']))+age
            if deadline!=record['deadline_ns']:
                raise PermissionError('HEAD_MONITOR_EXPOSURE_DEADLINE_CHANGED')
            skew=observer.camera_skew
            with observer.port._lock:
                causal=next((dict(row) for row in reversed(observer.port._head_samples)
                    if row['source_ns']<=source),None)
            if (not _wall(skew) or not 0<skew<=.05 or record['info_source_ns']!=source
                    or not 0<=original['decision']['sim_ns']-source
                        <=math.floor(observer._policy.camera_max_source_age_s*1e9)
                    or causal is None or not causal['valid'] or nanoseconds(causal['wall_s'])>now_ns
                    or record['joint_source_ns']!=causal['source_ns']
                    or not 0<=source-causal['source_ns']<=math.floor(skew*1e9)
                    or not 0<=source-record['tf_source_ns']<=math.floor(skew*1e9)):
                raise PermissionError('HEAD_MONITOR_EXPOSURE_ORIGINAL_MISMATCH')
            for value,watermark in ((image,image_source),(info,info_source)):
                if value is None:
                    if watermark>=source:
                        raise PermissionError('HEAD_MONITOR_EXPOSURE_RECEIVED_ORIGINAL_MISSING')
                    continue
                if (not value['valid'] or value['source_ns']!=source
                        or value['frame_id']!=record['image_frame_id']
                        or nanoseconds(value['wall_s'])>now_ns):
                    raise PermissionError('HEAD_MONITOR_EXPOSURE_ORIGINAL_MISMATCH')
                _received_original(value,source=source,frame=record['image_frame_id'],decision_ns=now_ns,
                    payload_sha256=record['payload_sha256'] if value is image else None)
                deadline=min(deadline,nanoseconds(value['wall_s'])+age)
            if image is not None and image['payload_sha256']!=record['payload_sha256']:
                raise PermissionError('HEAD_MONITOR_EXPOSURE_ORIGINAL_MISMATCH')
            with self._lock:
                observed=observer.monotonic()
                if nanoseconds(observed)>=deadline:raise _Expired(deadline)
                if (self._active is not None or record['sequence']!=self._sequence+1
                        or source<=self._source_floor or runtime.revoked or observer.failed):
                    raise PermissionError('HEAD_MONITOR_EXPOSURE_REUSED_OR_REVOKED')
            return _wire(dict(stage='ARMED_READY',inputs_ready=image is not None and info is not None,
                motion_authority=False,root_claim=record,observed_wall_s=observed,deadline_ns=deadline))
        except Exception as error:
            if isinstance(error,_Expired):runtime.fault('HEAD_MONITOR_EXPOSURE_DEADLINE',error.deadline*1e-9)
            runtime.fault('HEAD_MONITOR_EXPOSURE_INPUTS_REFUSED',
                observer.monotonic() if observer is not None else time.monotonic())
            raise PermissionError('HEAD_MONITOR_EXPOSURE_INPUTS_REFUSED') from error

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
                # Preserve the last causal original without cloning the
                # append-only bootstrap history under the feedback cache lock.
                causal=next((dict(value) for value in reversed(observer.port._head_samples)
                    if value['source_ns']<=source),None)
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
            _received_original(image,source=source,frame=record['image_frame_id'],
                decision_ns=now_ns,payload_sha256=record['payload_sha256'])
            _received_original(info,source=source,frame=record['image_frame_id'],decision_ns=now_ns)
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
                discharge=observer.discharge_inference_deadlines(
                    sorted(set([active['deadline_ns'],active['root_claim']['deadline_ns']])),
                    completion_wall_s=record['completion_wall_s'])
                self._active=None
            ack=dict(record,stage='ARMED_READY',exposure_finished=True,
                ack_wall_s=discharge['observed_wall_s'],
                deadline_ns=active['deadline_ns'],motion_authority=False,
                deadline_discharge=discharge,
                original_snapshot=_wire(dict(current_joint=original['sample'],decision=original['decision'],
                    clock=clock,watchdog_wall_s=watchdog)))
            runtime._emit('EXPOSURE_FINISHED',ack=ack)
            return ack
        except Exception as error:
            if isinstance(error,_Expired):runtime.fault('HEAD_MONITOR_EXPOSURE_DEADLINE',error.deadline*1e-9)
            runtime.fault('HEAD_MONITOR_EXPOSURE_COMPLETION_REFUSED',
                observer.monotonic() if observer is not None else time.monotonic())
            raise PermissionError('HEAD_MONITOR_EXPOSURE_COMPLETION_REFUSED') from error
