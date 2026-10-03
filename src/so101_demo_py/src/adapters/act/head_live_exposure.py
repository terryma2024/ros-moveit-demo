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
from so101_demo.act.head_monitor import canonical_bytes,digest
from so101_demo.act.head_simulation_policy import HeadSimulationPolicy,validate_stopped_observation_request
from .ros_search import rotation_matrix


def _wire(value):return json.loads(json.dumps(value,allow_nan=False))


class HeadLiveExposures:
    def __init__(self,*,port,buffer,detector,primary,monitor,camera_skew_s,emit):
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
            self.primary.fault('HEAD_LIVE_EXPOSURE_DEADLINE',deadline*1e-9)
            raise PermissionError('HEAD_LIVE_EXPOSURE_DEADLINE')
        self.primary.dispatch_guard()
        if self._closed or not self.primary.ready:
            raise PermissionError('HEAD_LIVE_CONTEXT_REVOKED')

    def infer(self,*,observation_request=None):
        if self._simulation_policy is not None:return self._infer_stopped(observation_request)
        if observation_request is not None:
            self.primary.fault('HEAD_LIVE_LEGACY_STOPPED_REQUEST_REFUSED')
            raise PermissionError('HEAD_LIVE_LEGACY_STOPPED_REQUEST_REFUSED')
        entered=False;trace=None
        try:
            if threading.get_ident()!=self._inference_owner:
                raise PermissionError('HEAD_LIVE_INFERENCE_OWNER_INVALID')
            self._discard_before_activation()
            with self._lock:
                if self._closed or self._busy:raise PermissionError('HEAD_LIVE_REUSED_OR_RETIRED')
                pending=self._pending
                if pending is None:return None
                image,data=pending;info=self._infos.get(image['source_ns'])
                info=None if info is None else dict(info)
            deadline=nanoseconds(image['wall_s'])+self.age_ns
            source=image['source_ns']
            trace=self._pending_trace
            if trace is None or trace['source_ns']!=source:
                if trace is not None and trace['outcome']=='WAITING':
                    trace['outcome']='SUPERSEDED_BEFORE_ADMISSION'
                trace=dict(source_ns=source,image_received_wall_s=image['wall_s'],
                    root_deadline_ns=deadline,phases={'first_pending':self.monotonic()},
                    outcome='WAITING',error_type=None)
                self._original_attempts.append(trace);self._pending_trace=trace
            def mark(phase,wall=None):
                if phase not in trace['phases']:
                    trace['phases'][phase]=self.monotonic() if wall is None else wall
            self._guard(deadline)
            if info is None:return None
            deadline=min(deadline,nanoseconds(info['wall_s'])+self.age_ns)
            trace['info_received_wall_s']=info['wall_s'];trace['root_deadline_ns']=deadline
            mark('info_ready')
            self._guard(deadline)
            current=self.port.original_feedback_snapshot()
            self.port.feedback_policy.check_joint(current['sample'],current['decision'])
            if source>current['decision']['sim_ns']:return None
            mark('clock_ready')
            if current['decision']['sim_ns']-source>math.floor(self.port.feedback_policy.camera_max_source_age_s*1e9):
                raise PermissionError('HEAD_LIVE_ORIGINAL_SOURCE_STALE')
            with self.port._lock:
                causal=next((dict(row) for row in reversed(self.port._head_samples)
                    if row['source_ns']<=image['source_ns']),None)
            target=Time(nanoseconds=source)
            mark('tf_probe_started')
            if not self.buffer.can_transform('base',self.frame,target):return None
            transform=self.buffer.lookup_transform('base',self.frame,target)
            mark('tf_ready')
            tf_source=transform.header.stamp.sec*10**9+transform.header.stamp.nanosec
            rotation_matrix(transform.transform.rotation)
            translation=[getattr(transform.transform.translation,key) for key in ('x','y','z')]
            rotation=[getattr(transform.transform.rotation,key) for key in ('x','y','z','w')]
            if (causal is None or not causal['valid'] or not info['valid']
                    or info['source_ns']!=source or info['frame_id']!=self.frame
                    or not 0<=source-causal['source_ns']<=self.skew_ns
                    or not 0<tf_source<=source or source-tf_source>self.skew_ns
                    or any(not math.isfinite(value) for value in translation)
                    or nanoseconds(causal['wall_s'])>nanoseconds(self.monotonic())):
                raise PermissionError('HEAD_LIVE_SOURCE_MISMATCH')
            epoch=self.primary.epoch
            claim=dict(epoch=epoch.epoch,generation=epoch.generation,session_id=epoch.session_id,
                policy_sha256=epoch.policy_hash,sequence=self._sequence+1,image_source_ns=source,
                info_source_ns=info['source_ns'],joint_source_ns=causal['source_ns'],tf_source_ns=tf_source,
                image_frame_id=self.frame,payload_sha256=image['payload_sha256'],
                image_received_wall_s=image['wall_s'],info_received_wall_s=info['wall_s'],deadline_ns=deadline)
            self._guard(deadline)
            mark('inputs_request_started')
            trace['inputs_queries']=trace.get('inputs_queries',0)+1
            inputs_started=self.monotonic()
            inputs=self.monitor.request_runtime(dict(operation='EXPOSURE_INPUTS',exposure=claim))
            inputs_received=self.monotonic()
            self.primary._ack(inputs,'EXPOSURE_INPUTS','ARMED_READY',root_claim=claim)
            if (type(inputs.get('inputs_ready')) is not bool
                    or type(inputs.get('deadline_ns')) is not int
                    or not nanoseconds(inputs_started)<=nanoseconds(inputs['observed_wall_s'])
                        <=nanoseconds(inputs_received)<inputs['deadline_ns']<=deadline):
                raise PermissionError('HEAD_LIVE_CPU_INPUTS_INVALID')
            self._guard(deadline)
            if not inputs['inputs_ready']:
                if 'inputs_wait_ack' not in trace:trace['inputs_wait_ack']=inputs
                mark('inputs_wait_started');return None
            mark('inputs_ready',inputs_received)
            trace['inputs_ack']=inputs
            with self._lock:
                if self._pending is not pending:return None
                if self._closed or self._busy or source<=self._source_floor:
                    raise PermissionError('HEAD_LIVE_SOURCE_REUSED')
                self._pending=None;self._busy=True;self._sequence+=1;self._source_floor=source
                entered=True
                sequence=self._sequence
            trace['sequence']=sequence;trace['outcome']='ADMITTED'
            mark('admission_committed')
            self.primary.inference_deadline(deadline*1e-9)
            self._guard(deadline)
            started=self.monotonic()
            mark('admission_request_started',started)
            ack=self.monitor.request_runtime(dict(operation='EXPOSURE_ADMIT',exposure=claim))
            received=self.monotonic()
            mark('admission_reply_received',received)
            self.primary._ack(ack,'EXPOSURE_ADMIT','ARMED_READY',exposure_admitted=True,
                sequence=sequence,image_source_ns=source,root_claim=claim)
            snapshot=ack['original_snapshot'];cpu_image=snapshot['image'];cpu_info=snapshot['info']
            expected=min(deadline,nanoseconds(cpu_image['wall_s'])+self.age_ns,
                nanoseconds(cpu_info['wall_s'])+self.age_ns)
            if (type(ack['deadline_ns']) is not int or ack['deadline_ns']!=expected
                    or ack['exposure_sha256']!=digest(dict(root_claim=claim,
                        original_snapshot=snapshot,deadline_ns=expected))
                    or cpu_image['source_ns']!=source or cpu_info['source_ns']!=source
                    or cpu_image['payload_sha256']!=image['payload_sha256']
                    or snapshot['joint']['source_ns']!=causal['source_ns']):
                raise PermissionError('HEAD_LIVE_CPU_ADMISSION_INVALID')
            deadline=expected;self.primary.inference_deadline(deadline*1e-9)
            trace['cpu_deadline_ns']=deadline
            trace['cpu_image_received_wall_s']=cpu_image['wall_s']
            trace['cpu_info_received_wall_s']=cpu_info['wall_s']
            mark('admission_validated')
            self._guard(deadline)
            cuda_started=self.monotonic();self._inference_calls+=1
            mark('cuda_started',cuda_started)
            try:
                detections=self.detector.detect(np.frombuffer(data,dtype=np.uint8).reshape(480,640,3),
                    session_id=epoch.session_id,attempt_id=epoch.epoch,source_stamp_ns=source,
                    source_frame_id=self.frame)
            except BaseException:
                mark('cuda_raised');raise
            completion=self.monotonic()
            mark('cuda_returned',completion)
            self._guard(deadline)
            detections=_wire(detections);result_sha=digest(detections)
            done=dict(exposure_sha256=ack['exposure_sha256'],sequence=sequence,image_source_ns=source,
                completion_wall_s=completion,result_sha256=result_sha)
            finish_started=self.monotonic()
            mark('completion_request_started',finish_started)
            finish=self.monitor.request_runtime(dict(operation='EXPOSURE_FINISH',completion=done))
            finish_received=self.monotonic()
            mark('completion_reply_received',finish_received)
            self.primary._ack(finish,'EXPOSURE_FINISH','ARMED_READY',exposure_finished=True,
                **done,deadline_ns=deadline)
            self._guard(deadline)
            row=_wire(dict(epoch=epoch.epoch,generation=epoch.generation,session_id=epoch.session_id,
                exposure_pipeline_owner=dict(name=threading.current_thread().name,
                    ident=threading.get_ident(),native_id=threading.get_native_id()),
                sequence=sequence,source_ns=source,info_source_ns=info['source_ns'],
                joint_source_ns=causal['source_ns'],tf_source_ns=tf_source,causal_joint=causal,
                payload_sha256=image['payload_sha256'],image_received_wall_s=image['wall_s'],
                info_received_wall_s=info['wall_s'],original_info=info,deadline_ns=deadline,tf_translation=translation,
                tf_rotation=rotation,inputs_ack=inputs,inputs_rpc_started_wall_s=inputs_started,
                inputs_rpc_received_wall_s=inputs_received,admission_ack=ack,admission_rpc_started_wall_s=started,
                admission_rpc_received_wall_s=received,cuda_started_wall_s=cuda_started,
                completion_wall_s=completion,completion_ack=finish,completion_rpc_started_wall_s=finish_started,
                completion_rpc_received_wall_s=finish_received,detections=detections,result_sha256=result_sha))
            self.emit('LIVE_EXPOSURE_FINISHED',record=row)
            self._guard(deadline)
            saved=_wire(row)
            with self._lock:self.results.append(saved)
            mark('record_saved')
            self.primary.inference_deadline(None)
            mark('deadlines_discharged');trace['outcome']='COMPLETED'
            return row
        except Exception as error:
            if trace is not None:
                trace['error_type']=type(error).__name__;trace['outcome']='REFUSED'
                trace['phases']['refused']=self.monotonic()
            self.primary.fault('HEAD_LIVE_EXPOSURE_REFUSED');raise
        finally:
            if entered:
                with self._lock:self._busy=False

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

    def _stopped_rpc(self,value,deadline_ns):
        """One sent frame can finish; unsent waits share the original finite cap."""
        started=self.monotonic();wait_cap=min(deadline_ns,nanoseconds(started)
            +nanoseconds(self._simulation_policy.supervision_stale_s))
        attempts=[]
        while True:
            self._guard(wait_cap)
            trace={};attempts.append(trace)
            try:reply=self.monitor.request_runtime(value,trace=trace)
            except TimeoutError:
                if self.monitor.runtime_pending:
                    cap=min(wait_cap,nanoseconds(self.monitor.pending_runtime_deadline_wall_s))
                    reply=self.monitor.complete_pending_runtime(cap*1e-9)
                else:
                    # No snapshot/bytes were sent. The heartbeat owner alone
                    # completes its own frame; never borrow or reset its cap.
                    self._guard(wait_cap)
                    time.sleep(min(self._simulation_policy.watchdog_period_s,
                        max(0.,wait_cap*1e-9-self.monotonic())))
                    continue
            return reply,dict(started_wall_s=started,received_wall_s=self.monotonic(),attempts=attempts)

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

    def _stopped_input_clock(self,reply,claim,trace,*,admission=False):
        discard=reply.get('observation_discarded') is True
        key='observed_wall_s' if discard or not admission else 'ack_wall_s'
        decision_key='observed_decision' if discard or not admission else 'admission_decision'
        wall=reply.get(key);decision=reply.get(decision_key);deadline=reply.get('deadline_ns')
        if (type(wall) not in (int,float) or not math.isfinite(wall)
                or not nanoseconds(trace['started_wall_s'])<=nanoseconds(wall)<=nanoseconds(trace['received_wall_s'])
                or type(decision) is not dict or nanoseconds(decision['wall_after_s'])!=nanoseconds(wall)
                or type(deadline) is not int or not 0<deadline<=claim['deadline_ns']
                or (not admission or discard) and type(reply.get('inputs_ready')) is not bool
                or discard and (reply['inputs_ready'] is not False
                    or reply.get('observation_outcome') not in ('EXPIRED','SHORT_DROP'))):
            raise PermissionError('HEAD_LIVE_CPU_INPUTS_INVALID')

    def _infer_stopped(self,observation_request):
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
            trace['inputs_queries']=trace.get('inputs_queries',0)+1
            inputs,inputs_trace=self._stopped_rpc(dict(operation='EXPOSURE_INPUTS',exposure=claim),job)
            trace['inputs_rpc']=inputs_trace;trace['inputs_ack']=inputs
            self.primary._ack(inputs,'EXPOSURE_INPUTS','ARMED_READY',root_claim=claim,job_deadline_ns=job)
            self._stopped_input_clock(inputs,claim,inputs_trace)
            base.update(inputs_ack=inputs,inputs_rpc=inputs_trace)
            if inputs.get('observation_discarded') is True:
                base['deadline_ns']=inputs['deadline_ns']
                return self._save_stopped_observation(base,inputs['observation_outcome'])
            if not inputs['inputs_ready']:return None
            self._guard(job)
            if self._stopped_root_proof(request,image,self.port.original_feedback_snapshot()) is None:return None
            with self._lock:
                if self._pending is not pending:return None
                if self._closed or self._busy or source<=self._source_floor:
                    raise PermissionError('HEAD_LIVE_SOURCE_REUSED')
                self._busy=True;entered=True
            ack,admission_trace=self._stopped_rpc(dict(operation='EXPOSURE_ADMIT',exposure=claim),job)
            trace['admission_rpc']=admission_trace;trace['admission_ack']=ack
            self.primary._ack(ack,'EXPOSURE_ADMIT','ARMED_READY',root_claim=claim,job_deadline_ns=job)
            self._stopped_input_clock(ack,claim,admission_trace,admission=True)
            base.update(admission_ack=ack,admission_rpc=admission_trace)
            if ack.get('observation_discarded') is True:
                if ack.get('exposure_admitted') is not False:raise PermissionError('HEAD_LIVE_CPU_ADMISSION_INVALID')
                base['deadline_ns']=ack['deadline_ns']
                return self._save_stopped_observation(base,ack['observation_outcome'])
            snapshot=ack['original_snapshot'];cpu_image=snapshot['image'];cpu_info=snapshot['info']
            expected=min(deadline,nanoseconds(cpu_image['wall_s'])+self.age_ns,nanoseconds(cpu_info['wall_s'])+self.age_ns)
            self.primary._ack(ack,'EXPOSURE_ADMIT','ARMED_READY',exposure_admitted=True,
                sequence=claim['sequence'],image_source_ns=source,root_claim=claim,deadline_ns=expected,job_deadline_ns=job)
            if (ack['exposure_sha256']!=digest(dict(root_claim=claim,original_snapshot=snapshot,deadline_ns=expected,job_deadline_ns=job))
                    or cpu_image['source_ns']!=source or cpu_info['source_ns']!=source
                    or cpu_image['payload_sha256']!=image['payload_sha256'] or snapshot['joint']['source_ns']!=causal['source_ns']):
                raise PermissionError('HEAD_LIVE_CPU_ADMISSION_INVALID')
            with self._lock:
                if self._pending is pending:self._pending=None
                self._sequence=claim['sequence'];self._source_floor=source
            base.update(sequence=self._sequence,deadline_ns=expected,cpu_image_received_wall_s=cpu_image['wall_s'],
                cpu_info_received_wall_s=cpu_info['wall_s'])
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
            done=dict(schema_version=2,exposure_sha256=ack['exposure_sha256'],sequence=self._sequence,image_source_ns=source,
                completion_wall_s=completion,result_sha256=digest(detections),observation_request_sha256=digest(request))
            finish,finish_trace=self._stopped_rpc(dict(operation='EXPOSURE_FINISH',completion=done),job)
            trace['completion_rpc']=finish_trace;trace['completion_ack']=finish
            self.primary._ack(finish,'EXPOSURE_FINISH','ARMED_READY',exposure_finished=True,**done,deadline_ns=expected,job_deadline_ns=job)
            base.update(completion_ack=finish,completion_rpc=finish_trace,result_sha256=done['result_sha256'])
            self._guard(job);self.primary.inference_deadline(None)
            return self._save_stopped_observation(base,finish['observation_outcome'],detections=detections)
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
        if getattr(self.primary,'_finished',False) is not True:
            raise PermissionError('HEAD_LIVE_PRIMARY_RETIRE_UNCONFIRMED')
        return self._retirement_record()

    def close(self):
        # Direct callers own this complete synchronous lifecycle. The entry's
        # HeadInferenceOwner uses freeze, joins, then guarded readback instead.
        self.freeze_retirement()
        return self._retirement_record()
