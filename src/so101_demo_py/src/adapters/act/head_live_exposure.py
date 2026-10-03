"""Original-frame inference on the once-loaded, owned Head composition.

No node, subscription, model, SDK or worker is constructed here. The caller owns
the single inference thread and must retire it before closing producer journals.
"""
from copy import deepcopy
import hashlib
import json
import math
import threading

import numpy as np
from rclpy.time import Time

from so101_demo.act.head_feedback import nanoseconds
from so101_demo.act.head_monitor import digest
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
        self._activation_wall=None

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

    def infer(self):
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
            epoch=self.primary.epoch
            claim=dict(epoch=epoch.epoch,generation=epoch.generation,session_id=epoch.session_id,
                policy_sha256=epoch.policy_hash,sequence=sequence,image_source_ns=source,
                info_source_ns=info['source_ns'],joint_source_ns=causal['source_ns'],tf_source_ns=tf_source,
                image_frame_id=self.frame,payload_sha256=image['payload_sha256'],
                image_received_wall_s=image['wall_s'],info_received_wall_s=info['wall_s'],deadline_ns=deadline)
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
                tf_rotation=rotation,admission_ack=ack,admission_rpc_started_wall_s=started,
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

    def records_snapshot(self):
        with self._lock:records=list(self.results)
        return _wire(records)

    def next_completed_exposure(self,after_sequence):
        if type(after_sequence) is not int or after_sequence<0:
            raise ValueError('HEAD_COMPLETED_EXPOSURE_SEQUENCE_INVALID')
        with self._lock:
            record=next((row for row in self.results if row['sequence']>after_sequence),None)
        return None if record is None else _wire(record)

    def close(self):
        with self._lock:
            if self._busy:raise PermissionError('HEAD_LIVE_INFERENCE_RETIRE_UNCONFIRMED')
            self._closed=True;pending=self._pending;self._pending=None
        if pending is not None:self.emit('LIVE_EXPOSURE_UNADMITTED_AT_RETIRE',original=pending[0])
        return dict(retired=True,inference_calls=self._inference_calls,
            completed_exposures=len(self.results),sequence=self._sequence,source_floor_ns=self._source_floor,
            original_attempts=_wire(self._original_attempts),
            inference_thread='owned caller; no child workers')
