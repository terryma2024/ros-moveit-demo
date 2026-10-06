"""Original-frame inference on the once-loaded, owned Head composition.

No node, subscription, model, SDK or worker is constructed here. The caller owns
the single inference thread and must retire it before closing producer journals.
"""
from copy import deepcopy
import hashlib
import json
import math
import threading
import time

import numpy as np
from rclpy.time import Time

from so101_demo.act.head_feedback import nanoseconds
from so101_demo.act.head_evidence_identity import canonical_bytes,digest
from so101_demo.act.head_simulation_policy import HeadSimulationPolicy,validate_stopped_observation_request
from .ros_search import rotation_matrix


def _wire(value):return json.loads(json.dumps(value,allow_nan=False))


class HeadLiveExposures:
    def __init__(self,*,port,buffer,detector,primary,monitor,camera_skew_s,emit):
        if monitor is not None:
            raise ValueError('HEAD_LIVE_LOCAL_MONITOR_REFUSED')
        if (primary.port is not port or port.feedback_policy is None or not callable(emit)
                or type(camera_skew_s) not in (int,float) or not 0<camera_skew_s<=.05):
            raise ValueError('HEAD_LIVE_EXPOSURE_CONFIG_INVALID')
        self.port=port;self.buffer=buffer;self.detector=detector
        self.primary=primary;self.monitor=monitor;self.skew_ns=math.floor(camera_skew_s*1e9)
        self.emit=emit;self.monotonic=port.monotonic;self.frame=primary.observer.camera_frame
        self.age_ns=math.floor(primary.observer.camera_age*1e9)
        self._lock=threading.Lock();self._pending=None;self._infos={};self._closed=False
        self._sequence=0;self._source_floor=0;self._image_source=0;self._info_source=0
        self._inference_calls=0;self._busy=False;self.results=[]
        self._inference_owner=threading.get_ident()
        # Only the existing inference owner mutates these small original records.
        # Formatting and readback happen at retirement, outside the live path.
        self._original_attempts=[];self._pending_trace=None
        self._activation_wall=None;self._retirement=None
        self._simulation_policy=primary._simulation_policy
        if self._simulation_policy is not None:
            expected=canonical_bytes(self._simulation_policy.readback())
            if (type(self._simulation_policy) is not HeadSimulationPolicy
                    or canonical_bytes(port.feedback_policy._bound_simulation_policy.readback())!=expected
                    or canonical_bytes(primary.observer._simulation_policy.readback())!=expected
                    or self.age_ns!=nanoseconds(self._simulation_policy.perception_max_age_s)):
                raise ValueError('HEAD_LIVE_SIMULATION_BINDING_INVALID')
        self._stopped_request=None;self._last_stopped_request=None;self._observation_sequence=0
        self._stopped_candidate=None

    def _discard_before_activation(self):
        with self._lock:
            if self._closed or self._busy:return
            pending=self._pending;wall=self._activation_wall
            if pending is None or wall is None:return
            info=self._infos.get(pending[0]['source_ns'])
            if (pending[0]['wall_s']>=wall
                    and (info is None or info['wall_s']>=wall)):return
            self._pending=None
        self.emit('LIVE_EXPOSURE_BEFORE_ACTIVATION',original=pending[0],
            original_info=info,activation_wall_s=wall,reason='original received before activation')

    def activate(self):
        refused=False
        with self._lock:
            if (self._closed or self._busy or self._activation_wall is not None
                    or not self.primary.ready):refused=True
            else:self._activation_wall=self.monotonic()
        if refused:
            self.primary.fault('HEAD_LIVE_ACTIVATION_REFUSED')
            raise PermissionError('HEAD_LIVE_ACTIVATION_REFUSED')
        self._discard_before_activation()

    def observe(self,kind,record,*,payload=None):
        if kind=='CLOCK':return  # The existing primary observer owns Clock admission.
        try:
            if kind not in ('IMAGE','INFO') or record.get('valid') is not True:
                raise ValueError('HEAD_LIVE_ORIGINAL_INVALID')
            source=record['source_ns']
            if (type(source) is not int or source<=0 or record['frame_id']!=self.frame
                    or type(record['wall_s']) not in (int,float)
                    or not math.isfinite(record['wall_s']) or record['wall_s']<0):
                raise ValueError('HEAD_LIVE_ORIGINAL_INVALID')
            if kind=='IMAGE' and (type(payload) is not bytes or len(payload)!=640*480*3
                    or record['payload_sha256']!=hashlib.sha256(payload).hexdigest()
                    or any(record[key]!=value for key,value in dict(width=640,height=480,
                        step=1920,encoding='rgb8',is_bigendian=0,payload_bytes=640*480*3).items())):
                raise ValueError('HEAD_LIVE_PAYLOAD_INVALID')
            owned=deepcopy(record);dropped=None
            with self._lock:
                if self._closed:return
                if source<=(self._image_source if kind=='IMAGE' else self._info_source):
                    raise ValueError('HEAD_LIVE_ORIGINAL_NONADVANCING')
                if kind=='IMAGE':
                    self._image_source=source;dropped=self._pending;self._pending=(owned,payload)
                else:
                    self._info_source=source;self._infos[source]=owned
                    while len(self._infos)>32:self._infos.pop(next(iter(self._infos)))
            if dropped is not None:
                self.emit('LIVE_EXPOSURE_DROPPED_BEFORE_ADMISSION',original=dropped[0],
                    replacing_source_ns=source)
        except Exception:
            self.primary.fault('HEAD_LIVE_ORIGINAL_REFUSED');raise

    def _guard(self,deadline):
        now=self.monotonic()
        if nanoseconds(now)>=deadline:
            self.primary.fault('HEAD_LIVE_EXPOSURE_DEADLINE', dict(deadline_ns=deadline))
            raise PermissionError('HEAD_LIVE_EXPOSURE_DEADLINE')
        self.primary.dispatch_guard()
        if self._closed or not self.primary.ready:
            raise PermissionError('HEAD_LIVE_CONTEXT_REVOKED')

    def infer(self, *, observation_request=None):
        """Infer only a stopped observation under the bound local policy."""
        if self._simulation_policy is None:
            self.primary.fault('HEAD_LIVE_LOCAL_POLICY_REQUIRED')
            raise PermissionError('HEAD_LIVE_LOCAL_POLICY_REQUIRED')
        return self._infer_stopped_local(observation_request)

    def _stopped_root_proof(self,request,image,current):
        """No unfinished owned SDK goal or moving current sample may enter YOLO."""
        with self.port._lock:
            goals=dict(self.port._goals);samples=tuple(self.port._head_samples)
        if set(goals)!=set(self.primary.epoch.inventory):
            raise PermissionError('HEAD_LIVE_STOPPED_INVENTORY_MISMATCH')
        for goal in goals.values():
            result=goal.get('result')
            if goal.get('accepted') is False or goal.get('error') is not None:
                raise PermissionError('HEAD_LIVE_STOPPED_GOAL_FAILED')
            if result is None or goal.get('accepted') is not True:return None
            if result.status!=4 or result.result.error_code!=0:
                raise PermissionError('HEAD_LIVE_STOPPED_GOAL_FAILED')
        limit=self.port.stop_velocity
        def quiet(row):
            return (row.get('valid') is True and len(row.get('positions',()))==1
                and len(row.get('velocities',()))==1 and all(type(v) in (int,float)
                    and math.isfinite(v) for v in (*row['positions'],*row['velocities']))
                and abs(row['velocities'][0])<=limit)
        if not quiet(current['sample']):return None
        proof=[];previous=None
        for row in samples:
            if (type(row.get('source_ns')) is not int or type(row.get('wall_s')) not in (int,float)
                    or not math.isfinite(row['wall_s']) or row['source_ns']<=request['settled_source_floor_ns']
                    or nanoseconds(row['wall_s'])<=nanoseconds(request['settled_wall_s'])
                    or row['source_ns']>=image['source_ns']
                    or nanoseconds(row['wall_s'])>nanoseconds(image['wall_s'])):continue
            if (not quiet(row) or previous is not None and (row['source_ns']<=previous['source_ns']
                    or nanoseconds(row['wall_s'])<=nanoseconds(previous['wall_s']))):
                proof=[];previous=row;continue
            proof.append(dict(row));previous=row
            if len(proof)==3:return proof
        return None


    def _save_stopped_observation(self,row,outcome,*,detections=()):
        if outcome not in ('VALID','EXPIRED','SHORT_DROP'):
            raise PermissionError('HEAD_LIVE_STOPPED_OUTCOME_INVALID')
        request=self._stopped_request
        if request is None:raise PermissionError('HEAD_LIVE_STOPPED_REQUEST_MISSING')
        self._guard(request['search_deadline_ns'])
        validation=self.port.original_feedback_snapshot();self.port.feedback_policy.check_joint(
            validation['sample'],validation['decision'])
        def expired(decision):
            age=decision['sim_ns']-row['source_ns']
            if age<0:raise PermissionError('HEAD_LIVE_STOPPED_FUTURE_SOURCE')
            return (nanoseconds(decision['wall_after_s'])>=row['deadline_ns']
                or age>nanoseconds(self._simulation_policy.camera_source_age_s))
        if outcome=='VALID' and expired(validation['decision']):
            outcome='EXPIRED'
        saved=_wire(dict(row,observation_request=request,observation_request_sha256=digest(request),
            observation_sequence=request['observation_sequence'],motion_epoch=request['motion_epoch'],
            simulation_policy_sha256=digest(self._simulation_policy.readback()),
            observation_outcome=outcome,detections=list(detections) if outcome=='VALID' else [],
            discarded_detections=list(detections) if outcome!='VALID' else [],
            validation_decision=validation['decision'],
            record_saved_wall_s=self.monotonic()))
        self.emit('LIVE_STOPPED_OBSERVATION_FINISHED',record=saved)
        self._guard(request['search_deadline_ns'])
        # Journal latency cannot turn an already expired image into authority.
        handoff=self.port.original_feedback_snapshot();self.port.feedback_policy.check_joint(handoff['sample'],handoff['decision'])
        saved['handoff_decision']=handoff['decision']
        if saved['observation_outcome']=='VALID' and expired(handoff['decision']):
            saved['observation_outcome']='EXPIRED';saved['discarded_detections']=saved['detections'];saved['detections']=[]
            self.emit('LIVE_STOPPED_OBSERVATION_EXPIRED_AT_HANDOFF',record=saved)
        self.emit('LIVE_STOPPED_OBSERVATION_HANDOFF',record=saved)
        with self._lock:self.results.append(_wire(saved))
        trace=self._stopped_candidate['trace']
        trace['outcome']='COMPLETED' if saved['observation_outcome']=='VALID' else 'DISCARDED'
        trace['phases']['record_saved']=saved['record_saved_wall_s']
        trace['observation_outcome']=saved['observation_outcome']
        self._observation_sequence=request['observation_sequence'];self._last_stopped_request=dict(request)
        self._stopped_request=None;self._stopped_candidate=None
        return saved



    def _local_frame_verdict(self,image,claim):
        """Local replacement for the CPU EXPOSURE_INPUTS verdict, without an RPC."""
        snapshot=self.port.original_feedback_snapshot()
        decision=snapshot['decision']
        age=decision['sim_ns']-image['source_ns']
        if age<0:raise PermissionError('HEAD_LIVE_STOPPED_FUTURE_SOURCE')
        deadline=claim['deadline_ns']
        if (nanoseconds(decision['wall_after_s'])>=deadline
                or age>nanoseconds(self._simulation_policy.camera_source_age_s)):
            return dict(discarded=True,outcome='EXPIRED',decision=decision,deadline_ns=deadline)
        return dict(discarded=False,outcome=None,decision=decision,deadline_ns=deadline)

    def _infer_stopped_local(self,observation_request):
        """The same stopped observation on this process's own originals.

        It freezes the schema-1 request, proves post-settle root settlement on
        the shared port originals, admits one exact local Image/CameraInfo pair
        with its causal joint and TF, runs the single owned detector once inside
        the job deadline and records the outcome. There is no monitor RPC, no
        ACK exchange and no second capture owner.
        """
        entered=False;trace=None
        try:
            if (threading.get_ident()!=self._inference_owner or self._activation_wall is None
                    or self._closed or self._busy or observation_request is None):
                raise PermissionError('HEAD_LIVE_STOPPED_OWNER_INVALID')
            epoch=self.primary.epoch;policy=self._simulation_policy
            request=validate_stopped_observation_request(observation_request,policy=policy,
                expected_scope=dict(epoch=epoch.epoch,generation=epoch.generation,
                    session_id=epoch.session_id,policy_sha256=epoch.policy_hash),now_wall_s=self.monotonic())
            if (request['motion_epoch']!=len(epoch.inventory)
                    or request['observation_sequence']!=self._observation_sequence+1):
                raise PermissionError('HEAD_LIVE_STOPPED_REQUEST_REUSED')
            if self._stopped_request is None:
                last=self._last_stopped_request
                if last is not None and (request['search_deadline_ns']!=last['search_deadline_ns']
                        or nanoseconds(request['requested_wall_s'])<=nanoseconds(last['requested_wall_s'])
                        or request['motion_epoch']<last['motion_epoch']
                        or request['motion_epoch']==last['motion_epoch'] and any(request[k]!=last[k]
                            for k in ('settled_source_floor_ns','settled_wall_s'))):
                    raise PermissionError('HEAD_LIVE_STOPPED_REQUEST_REUSED')
                self._stopped_request=request
            elif canonical_bytes(request)!=canonical_bytes(self._stopped_request):
                raise PermissionError('HEAD_LIVE_STOPPED_REQUEST_CHANGED')
            self._guard(request['search_deadline_ns'])
            self._discard_before_activation()
            with self._lock:
                pending=self._pending
                if pending is None:return None
                image,data=pending;info=self._infos.get(image['source_ns'])
                info=None if info is None else dict(info)
            source=image['source_ns']
            if (source<=request['settled_source_floor_ns']
                    or nanoseconds(image['wall_s'])<=nanoseconds(request['requested_wall_s'])
                    or info is None or nanoseconds(info['wall_s'])<=nanoseconds(request['requested_wall_s'])):return None
            current=self.port.original_feedback_snapshot()
            self.port.feedback_policy.check_joint(current['sample'],current['decision'])
            proof=self._stopped_root_proof(request,image,current)
            if proof is None:return None
            if source>current['decision']['sim_ns']:return None
            with self.port._lock:
                causal=next((dict(row) for row in reversed(self.port._head_samples) if row['source_ns']<=source),None)
            target=Time(nanoseconds=source)
            if not self.buffer.can_transform('base',self.frame,target):return None
            transform=self.buffer.lookup_transform('base',self.frame,target)
            tf_source=transform.header.stamp.sec*10**9+transform.header.stamp.nanosec
            rotation_matrix(transform.transform.rotation)
            translation=[getattr(transform.transform.translation,key) for key in ('x','y','z')]
            rotation=[getattr(transform.transform.rotation,key) for key in ('x','y','z','w')]
            if (causal is None or causal.get('valid') is not True or info.get('valid') is not True
                    or info['source_ns']!=source or info['frame_id']!=self.frame
                    or not 0<=source-causal['source_ns']<=self.skew_ns
                    or not 0<tf_source<=source or source-tf_source>self.skew_ns
                    or any(type(v) not in (int,float) or not math.isfinite(v) for v in translation)
                    or nanoseconds(causal['wall_s'])>nanoseconds(self.monotonic())):
                raise PermissionError('HEAD_LIVE_SOURCE_MISMATCH')
            candidate=self._stopped_candidate
            if candidate is None or candidate['pending'] is not pending:
                if candidate is not None and candidate['trace']['outcome']=='WAITING':
                    candidate['trace']['outcome']='SUPERSEDED_BEFORE_ADMISSION'
                started=self.monotonic();deadline=min(nanoseconds(image['wall_s']),nanoseconds(info['wall_s']))+self.age_ns
                claim=dict(schema_version=2,epoch=epoch.epoch,generation=epoch.generation,session_id=epoch.session_id,
                    policy_sha256=epoch.policy_hash,sequence=self._sequence+1,image_source_ns=source,
                    info_source_ns=source,joint_source_ns=causal['source_ns'],tf_source_ns=tf_source,
                    image_frame_id=self.frame,payload_sha256=image['payload_sha256'],image_received_wall_s=image['wall_s'],
                    info_received_wall_s=info['wall_s'],deadline_ns=deadline,observation_request=dict(request),
                    job_started_wall_s=started,job_deadline_ns=min(nanoseconds(started)
                        +nanoseconds(policy.perception_job_timeout_s),request['search_deadline_ns']))
                trace=dict(source_ns=source,observation_sequence=request['observation_sequence'],
                    observation_request=dict(request),image_received_wall_s=image['wall_s'],
                    info_received_wall_s=info['wall_s'],root_deadline_ns=deadline,
                    job_started_wall_s=started,job_deadline_ns=claim['job_deadline_ns'],
                    phases=dict(pair_selected=started),outcome='WAITING',error_type=None)
                self._original_attempts.append(trace)
                candidate=dict(pending=pending,claim=claim,trace=trace);self._stopped_candidate=candidate
            trace=candidate['trace']
            claim=candidate['claim'];job=claim['job_deadline_ns'];deadline=claim['deadline_ns']
            base=dict(epoch=epoch.epoch,generation=epoch.generation,session_id=epoch.session_id,policy_sha256=epoch.policy_hash,
                sequence=None,source_ns=source,info_source_ns=source,joint_source_ns=causal['source_ns'],tf_source_ns=tf_source,
                inference_performed=False,cuda_started_wall_s=None,completion_wall_s=None,
                causal_joint=causal,payload_sha256=image['payload_sha256'],image_received_wall_s=image['wall_s'],
                info_received_wall_s=info['wall_s'],original_info=info,deadline_ns=deadline,job_started_wall_s=claim['job_started_wall_s'],
                job_deadline_ns=job,tf_translation=translation,tf_rotation=rotation,root_settled_samples=proof,
                exposure_pipeline_owner=dict(name=threading.current_thread().name,ident=threading.get_ident(),
                    native_id=threading.get_native_id()))
            self._guard(job)
            with self._lock:
                replaced = self._pending is not pending
            if replaced:
                base['deadline_ns']=deadline
                return self._save_stopped_observation(base,'SHORT_DROP')
            verdict=self._local_frame_verdict(image,claim)
            trace['local_verdict']=dict(verdict,decision=dict(verdict['decision']))
            if verdict['discarded']:
                base['deadline_ns']=verdict['deadline_ns']
                return self._save_stopped_observation(base,verdict['outcome'])
            if self._stopped_root_proof(request,image,self.port.original_feedback_snapshot()) is None:return None
            with self._lock:
                if self._pending is not pending:return None
                if self._closed or self._busy or source<=self._source_floor:
                    raise PermissionError('HEAD_LIVE_SOURCE_REUSED')
                self._busy=True;entered=True
            snapshot=dict(image=dict(image),info=dict(info),joint=dict(causal))
            admitted=dict(root_claim=claim,original_snapshot=snapshot,deadline_ns=deadline,job_deadline_ns=job)
            expected=min(deadline,nanoseconds(image['wall_s'])+self.age_ns,nanoseconds(info['wall_s'])+self.age_ns)
            if (snapshot['image']['source_ns']!=source or snapshot['info']['source_ns']!=source
                    or snapshot['joint']['source_ns']!=causal['source_ns']
                    or snapshot['image']['payload_sha256']!=image['payload_sha256']
                    or expected!=min(deadline,nanoseconds(image['wall_s'])+self.age_ns,
                        nanoseconds(info['wall_s'])+self.age_ns)):
                raise PermissionError('HEAD_LIVE_LOCAL_ADMISSION_INVALID')
            trace['local_admission']=dict(admitted_sha256=digest(dict(admitted,deadline_ns=expected)),
                image_source_ns=source,info_source_ns=source,joint_source_ns=causal['source_ns'])
            with self._lock:
                if self._pending is pending:self._pending=None
                self._sequence=claim['sequence'];self._source_floor=source
            base.update(sequence=self._sequence,deadline_ns=expected)
            self.primary.inference_deadline(job*1e-9);self._guard(job)
            trace['outcome']='ADMITTED';trace['sequence']=self._sequence
            current=self.port.original_feedback_snapshot()
            self.port.feedback_policy.check_joint(current['sample'],current['decision'])
            if self._stopped_root_proof(request,image,current) is None:
                raise PermissionError('HEAD_LIVE_STOPPED_MOVED_AFTER_ADMISSION')
            source_age=current['decision']['sim_ns']-source
            if source_age<0:raise PermissionError('HEAD_LIVE_STOPPED_FUTURE_SOURCE')
            detections=[]
            if (nanoseconds(current['decision']['wall_after_s'])<expected
                    and source_age<=nanoseconds(policy.camera_source_age_s)):
                cuda_started=self.monotonic();base['cuda_started_wall_s']=cuda_started
                trace['phases']['cuda_started']=cuda_started
                base['inference_performed']=True;self._inference_calls+=1
                detections=_wire(self.detector.detect(np.frombuffer(data,dtype=np.uint8).reshape(480,640,3),
                    session_id=epoch.session_id,attempt_id=epoch.epoch,source_stamp_ns=source,source_frame_id=self.frame))
            completion=self.monotonic();base['completion_wall_s']=completion;self._guard(job)
            trace['phases']['model_returned_or_skipped']=completion
            base['result_sha256']=digest(detections)
            self._guard(job);self.primary.inference_deadline(None)
            return self._save_stopped_observation(base,'VALID',detections=detections)
        except Exception as error:
            if trace is not None:
                trace['outcome']='REFUSED';trace['error_type']=type(error).__name__
                trace['phases']['refused']=self.monotonic()
            self.primary.fault('HEAD_LIVE_STOPPED_EXPOSURE_REFUSED');raise
        finally:
            if entered:
                with self._lock:self._busy=False

    def records_snapshot(self):
        with self._lock:records=list(self.results)
        return _wire(records)

    def next_completed_exposure(self,after_sequence):
        if type(after_sequence) is not int or after_sequence<0:
            raise ValueError('HEAD_COMPLETED_EXPOSURE_SEQUENCE_INVALID')
        with self._lock:
            record=next((row for row in self.results if row['sequence'] is not None and row['sequence']>after_sequence),None)
        return None if record is None else _wire(record)

    def next_completed_observation(self,after_sequence):
        if self._simulation_policy is None or type(after_sequence) is not int or after_sequence<0:
            raise ValueError('HEAD_COMPLETED_OBSERVATION_SEQUENCE_INVALID')
        with self._lock:record=next((row for row in self.results if row['observation_sequence']>after_sequence),None)
        return None if record is None else _wire(record)

    def freeze_retirement(self):
        # The CUDA owner exits without encoding the growing attempt/result
        # history. Reactive native/Stop/FAULT workers still have deadlines.
        if threading.get_ident()!=self._inference_owner:
            raise PermissionError('HEAD_LIVE_INFERENCE_RETIRE_OWNER_INVALID')
        with self._lock:
            if self._busy:raise PermissionError('HEAD_LIVE_INFERENCE_RETIRE_UNCONFIRMED')
            if self._retirement is not None:return dict(self._retirement)
            self._closed=True;pending=self._pending;self._pending=None
            self._retirement=dict(retired=True,inference_calls=self._inference_calls,
                completed_exposures=len(self.results),sequence=self._sequence,source_floor_ns=self._source_floor,
                inference_thread='owned caller; no child workers')
        if pending is not None:self.emit('LIVE_EXPOSURE_UNADMITTED_AT_RETIRE',original=pending[0])
        return dict(self._retirement)

    def _retirement_record(self):
        with self._lock:
            if self._busy or not self._closed or self._retirement is None:
                raise PermissionError('HEAD_LIVE_INFERENCE_RETIRE_UNCONFIRMED')
            receipt=dict(self._retirement)
        return dict(receipt,original_attempts=_wire(self._original_attempts))

    def retirement_snapshot(self):
        if getattr(self.primary,'retirement_confirmed',False) is not True:
            raise PermissionError('HEAD_LIVE_PRIMARY_RETIRE_UNCONFIRMED')
        return self._retirement_record()

    def close(self):
        # Direct callers own this complete synchronous lifecycle. The entry's
        # HeadInferenceOwner uses freeze, joins, then guarded readback instead.
        self.freeze_retirement()
        return self._retirement_record()
