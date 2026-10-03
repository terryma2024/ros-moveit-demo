"""Once-bound original Head inputs for a stopped calibration workload.

The controller port owns the only joint subscription. Camera, info and joint
snapshots share its short cache lock; clocks are read after copying originals.
No method here arms a controller, sends a goal or grants motion authority.
"""
from collections import deque
from copy import deepcopy
import hashlib
import math
import threading
import time

from sensor_msgs.msg import Image, CameraInfo

from so101_demo.act.head_feedback import decision_clocks, nanoseconds
from so101_demo.act.head_feedback_measurement import evaluate_feedback_window, _quantile
from .ros_search import RGB_QOS, rotation_matrix
from .head_clock_binding import bind_head_clock
from .ros_execution import _copy_current_original_candidates,_causal_current_original


def _source(message):
    return message.header.stamp.sec*1_000_000_000+message.header.stamp.nanosec


def stopped_window_boundary(receipts,*,now_ns,processing_margin_s=0.):
    """Choose a future phase before declaring the immutable full20s window."""
    gaps=sorted(right-left for left,right in zip(receipts,receipts[1:]))
    period=gaps[len(gaps)//2]
    if (type(processing_margin_s) not in (int,float) or not math.isfinite(processing_margin_s)
            or not 0<=processing_margin_s<period):
        raise ValueError('HEAD_STOPPED_WINDOW_PHASE_INVALID')
    midpoint=nanoseconds(receipts[-1])+nanoseconds(max(period/2,processing_margin_s))
    return midpoint if midpoint>now_ns else None


class StoppedHeadCapture:
    def __init__(self,node,port,*,frame_id,monotonic=time.monotonic,strict=True,emit=None):
        self.node,self.port,self.frame_id,self.monotonic=node,port,frame_id,monotonic
        self.strict=strict;self.emit=emit;self._started=False;self._failure=None
        self.camera_messages=deque(maxlen=40000);self.info_messages=deque(maxlen=40000)
        self.clock_messages=deque(maxlen=40000);self.events=deque(maxlen=40000)
        self._pending=None;self._last={};self._last_camera=None
        self._original_sink=None;self._window=None;self._window_finished=False
        self._live_sink=None;self._live_floor=None
        self._measurement_monitor=None;self._measurement_scope=None
        self._measurement_attempts=[]
        self._measurement_pending=None;self._measurement_handoff=None
        self._measurement_consumed=threading.Event()
        self.subscriptions=[
            node.create_subscription(Image,'/head_camera/color',self._image,RGB_QOS),
            node.create_subscription(CameraInfo,'/head_camera/camera_info',self._info,RGB_QOS),
            bind_head_clock(node,self._clock,monotonic=self.monotonic)]

    def begin_capture(self):
        """Declare the first workload boundary once, after CUDA/discovery warmup."""
        with self.port._lock:
            if self._started:raise PermissionError('HEAD_STOPPED_CAPTURE_REUSED')
            self.check();self._started=True
            self.strict=True;self._pending=None
            # CameraInfo may precede its Image across this boundary. Retain
            # its bounded original Header/receipt/K/D, never latest geometry.
            info_carry_in=tuple(self.info_messages)[-32:]
            # Startup is diagnostic only. From this boundary every original is
            # retained; overflow refuses instead of silently dropping history.
            for rows in (self.camera_messages,self.info_messages,self.clock_messages,self.events):rows.clear()
            self.info_messages.extend(info_carry_in)

    def bind_original_sink(self,sink):
        if not callable(sink):raise ValueError('HEAD_STOPPED_ORIGINAL_SINK_INVALID')
        with self.port._lock:
            if self._original_sink is not None or self._failure is not None:
                raise PermissionError('HEAD_STOPPED_ORIGINAL_SINK_REBOUND')
            self._original_sink=sink

    def bind_measurement_monitor(self,monitor,*,epoch,generation,session_id):
        if (not callable(getattr(monitor,'request_runtime',None))
                or type(epoch) is not str or not epoch or type(session_id) is not str or not session_id
                or type(generation) is not int or not 0<generation<2**64):
            raise ValueError('HEAD_STOPPED_MEASUREMENT_BINDING_INVALID')
        with self.port._lock:
            if self._measurement_monitor is not None or self._started or self._failure is not None:
                raise PermissionError('HEAD_STOPPED_MEASUREMENT_REBOUND')
            self._measurement_monitor=monitor
            self._measurement_scope=dict(epoch=epoch,generation=generation,session_id=session_id,
                monitor_peer=dict(monitor.identity))

    def _measurement_request(self,operation,value):
        attempt=None
        try:
            self.check()
            if len(self._measurement_attempts)>=40000:
                raise PermissionError('HEAD_STOPPED_MEASUREMENT_HISTORY_OVERFLOW')
            claim=value if operation=='CALIBRATION_FRAME_INPUTS' else value['claim']
            attempt=dict(operation=operation,root_claim=deepcopy(claim),channel_trace={},
                outcome='PENDING',error_type=None,ack_wall_s=None,inputs_ready=None)
            attempt['started_wall_s']=self.monotonic()
            reply=self._read_measurement_request(operation,value,
                started=attempt['started_wall_s'],trace=attempt['channel_trace'])
            attempt.update(outcome='ACK',ack_wall_s=reply['ack_wall_s'],inputs_ready=reply['inputs_ready'],
                ended_wall_s=self.monotonic())
            self._measurement_attempts.append(attempt)
            return reply
        except Exception as error:
            self._failure='HEAD_STOPPED_MEASUREMENT_REFUSED'
            self.port._head_policy_binding_failed=True
            if attempt is not None:
                attempt.update(outcome='REFUSED',error_type=type(error).__name__,ended_wall_s=self.monotonic())
                self._measurement_attempts.append(attempt)
            callback=getattr(self.port,'_head_fault_callback',None)
            if callable(callback):callback(self._failure)
            raise

    def _read_measurement_request(self,operation,value,*,started,trace):
        field='exposure' if operation=='CALIBRATION_FRAME_INPUTS' else 'completion'
        claim=value if field=='exposure' else value['claim']
        reply=deepcopy(self._measurement_monitor.request_runtime(
            dict(operation=operation,**{field:value}),trace=trace))
        received=self.monotonic()
        if (type(reply) is not dict or reply.get('request')!=operation or reply.get('stage')!='CONFIGURED'
                or reply.get('purpose')!='calibration' or reply.get('calibration_measurement') is not True
                or reply.get('motion_authority') is not False or reply.get('root_claim')!=claim
                or type(reply.get('inputs_ready')) is not bool
                or type(reply.get('generation')) is not int
                or any(reply.get(key)!=val for key,val in self._measurement_scope.items())
                or not 0<=received-started<=.010
                or type(reply.get('ack_wall_s')) not in (int,float)
                or not math.isfinite(reply['ack_wall_s']) or not started<=reply['ack_wall_s']<=received):
            raise PermissionError('HEAD_STOPPED_MEASUREMENT_ACK_INVALID')
        snapshot=reply['original_snapshot'];decision=snapshot['decision']
        if (not started<=decision['wall_before_s']<=decision['wall_after_s']<=reply['ack_wall_s']
                or type(decision['sim_ns']) is not int or decision['sim_ns']<claim['image_source_ns']):
            raise PermissionError('HEAD_STOPPED_MEASUREMENT_CLOCK_INVALID')
        if reply['inputs_ready']:
            for kind in ('image','info'):
                row=snapshot[kind]
                if (type(row) is not dict or row.get('valid') is not True
                        or row['source_ns']!=claim['image_source_ns']
                        or row['frame_id']!=claim['image_frame_id']
                        or type(row['wall_s']) not in (int,float) or not math.isfinite(row['wall_s'])
                        or not 0<=row['wall_s']<=decision['wall_before_s']
                        or kind=='image' and row['payload_sha256']!=claim['payload_sha256']):
                    raise PermissionError('HEAD_STOPPED_MEASUREMENT_ORIGINAL_INVALID')
        if field=='completion' and (reply.get('measurement_complete') is not True
                or reply.get('completion')!=value or reply['inputs_ready'] is not True):
            raise PermissionError('HEAD_STOPPED_MEASUREMENT_COMPLETION_INVALID')
        return reply

    def bind_live_sink(self,sink):
        """Delegate future originals once; the finished calibration stays sealed.

        This changes retention and delivery only. It cannot reopen stopped
        inference, clear invalidity, create a subscription or grant authority.
        """
        if not callable(sink):raise ValueError('HEAD_STOPPED_LIVE_SINK_INVALID')
        with self.port._lock:
            self.check()
            if (not self._started or not self._window_finished or self._pending is not None
                    or self._original_sink is None or self._live_sink is not None):
                raise PermissionError('HEAD_STOPPED_LIVE_HANDOFF_REFUSED')
            # A callback already copied before this boundary is not a new live
            # exposure even if its outside-lock delivery completes afterwards.
            self._live_floor=dict(self._last)
            self._live_sink=sink

    def _forward_live(self,kind,record,*,payload=None):
        sink=self._live_sink
        if sink is None:return
        if self._failure is None and record['source_ns']>self._live_floor.get(kind.lower(),0):
            try:sink(kind,deepcopy(record),payload=payload)
            except Exception:self._failure='HEAD_STOPPED_LIVE_SINK_FAILED'
        if self._failure is not None:
            self.port._head_policy_binding_failed=True
            callback=getattr(self.port,'_head_fault_callback',None)
            if callback is not None:
                try:callback(self._failure)
                except Exception:pass

    def _forward_original(self,kind,record):
        sink=self._original_sink
        if sink is None:return
        try:sink(kind,deepcopy(record))
        except Exception:
            self._failure='HEAD_STOPPED_ORIGINAL_SINK_FAILED'
            self.port._head_policy_binding_failed=True
            callback=getattr(self.port,'_head_fault_callback',None)
            if callback is not None:
                try:callback(self._failure)
                except Exception:pass

    def declare_window(self,*,start_ns,end_ns):
        if (type(start_ns) is not int or type(end_ns) is not int
                or end_ns-start_ns!=20_000_000_000 or start_ns<=nanoseconds(self.monotonic())):
            raise ValueError('HEAD_STOPPED_WINDOW_DECLARATION_INVALID')
        with self.port._lock:
            self.check()
            if not self._started or self._window is not None:
                raise PermissionError('HEAD_STOPPED_WINDOW_REDECLARED')
            self._window=(start_ns,end_ns)

    def finish_window(self):
        with self.port._lock:
            self.check()
            if (self._window is None or self._window_finished
                    or nanoseconds(self.monotonic())<self._window[1]):
                raise PermissionError('HEAD_STOPPED_WINDOW_FINISH_INVALID')
            if self._pending is not None:
                self._failure='HEAD_STOPPED_IN_WINDOW_UNCONSUMED'
                self.check()
            self._window_finished=True

    def _record(self,rows,record):
        if self._live_sink is not None:return
        if self.strict and len(rows)==rows.maxlen:self._failure='HEAD_STOPPED_HISTORY_OVERFLOW'
        rows.append(record)

    def _validate_source(self,kind,record):
        if record['source_ns']<=0 or record['source_ns']<=self._last.get(kind,0):
            record.update(valid=False,error='HEAD_STOPPED_SOURCE_NONADVANCING')
        else:self._last[kind]=record['source_ns']
        if self.strict and not record['valid']:self._failure=record['error']

    def _image(self,message):
        received=self.monotonic();data=bytes(message.data)
        valid=(message.header.frame_id==self.frame_id and message.width==640 and message.height==480
            and message.encoding=='rgb8' and message.step==1920 and len(data)==640*480*3
            and message.is_bigendian==0)
        record=dict(source_ns=_source(message),wall_s=received,valid=valid,
            frame_id=message.header.frame_id,width=message.width,height=message.height,
            step=message.step,encoding=message.encoding,is_bigendian=message.is_bigendian,
            payload_sha256=hashlib.sha256(data).hexdigest(),payload_bytes=len(data))
        if not valid:record['error']='HEAD_STOPPED_IMAGE_INVALID'
        with self.port._lock:
            self._validate_source('image',record);self._record(self.camera_messages,record)
            if self._live_sink is None:
                unadmitted=self._window is not None and nanoseconds(received)>self._window[1]
                if unadmitted:
                    self._record(self.events,dict(event='IMAGE_UNADMITTED_PRESENCE',
                        source_ns=record['source_ns'],wall_s=received))
                elif self._pending is not None:
                    self._record(self.events,dict(event='IMAGE_DROPPED',source_ns=self._pending[0]['source_ns'],
                                                  replacing_source_ns=record['source_ns'],wall_s=received))
                    if self.strict:self._failure='HEAD_STOPPED_IMAGE_DROPPED'
                if not unadmitted:self._pending=(record,data)
            self._last_camera=record
        self._forward_original('IMAGE',record)
        if self.emit is not None and self._started:
            try:self.emit('IMAGE',record=record,payload=data)
            except Exception:self._failure='HEAD_STOPPED_EVIDENCE_FAILED'
        self._forward_live('IMAGE',record,payload=data)

    def _info(self,message):
        received=self.monotonic()
        valid=bool(message.header.frame_id==self.frame_id and message.width==640 and message.height==480
            and len(message.k)==9 and all(math.isfinite(value) for value in message.k)
            and message.k[0]>0 and message.k[4]>0 and message.k[8]==1.)
        record=dict(source_ns=_source(message),wall_s=received,valid=valid,
            frame_id=message.header.frame_id,width=message.width,height=message.height,
            k=list(message.k),d=list(message.d),r=list(message.r),p=list(message.p),
            distortion_model=message.distortion_model)
        if not valid:record['error']='HEAD_STOPPED_INFO_INVALID'
        with self.port._lock:
            self._validate_source('info',record);self._record(self.info_messages,record)
        self._forward_original('INFO',record)
        self._forward_live('INFO',record)

    def _clock(self,message,*,received_wall_s=None):
        record=dict(source_ns=message.clock.sec*1_000_000_000+message.clock.nanosec,
                    wall_s=self.monotonic() if received_wall_s is None else received_wall_s,valid=True)
        with self.port._lock:
            self._validate_source('clock',record);self._record(self.clock_messages,record)
        self._forward_original('CLOCK',record)
        self._forward_live('CLOCK',record)

    def check(self):
        if self._failure is not None:raise ValueError(self._failure)

    def snapshot(self,*,consume_measurement=False):
        self.check()
        with self.port._lock:
            joint_candidates=_copy_current_original_candidates(self.port._head_feedback,self.port._head_samples)
            camera_candidates=_copy_current_original_candidates(self._last_camera,self.camera_messages)
            pending=self._measurement_pending if consume_measurement else None
            completed=None if pending is None else deepcopy(pending)
        clocks=decision_clocks(self.node,self.monotonic)
        joint=_causal_current_original(joint_candidates,clocks['sim_ns'])
        camera=_causal_current_original(camera_candidates,clocks['sim_ns'])
        if joint is None or camera is None:raise ValueError('HEAD_STOPPED_INPUT_MISSING')
        snapshot=dict(joint=joint,camera=camera,clocks=clocks,
            current_original_selection=dict(
                joint_candidate_sources_ns=[row['source_ns'] for row in joint_candidates],
                camera_candidate_sources_ns=[row['source_ns'] for row in camera_candidates]))
        if completed is not None:
            snapshot.update(calibration_consumed_source_ns=completed['root_claim']['image_source_ns'],
                calibration_completion_ack_wall_s=completed['ack_wall_s'],
                consumer_thread_native_id=threading.get_native_id())
            with self.port._lock:
                self.check()
                if self._measurement_pending is not pending:
                    raise PermissionError('HEAD_STOPPED_MAIN_HANDOFF_CHANGED')
                self._measurement_handoff=snapshot;self._measurement_pending=None
                self._measurement_consumed.set()
        return snapshot

    def _main_measurement_handoff(self,completion):
        if not self._started:return self.snapshot()
        with self.port._lock:
            self.check()
            if self._measurement_pending is not None:
                raise PermissionError('HEAD_STOPPED_MAIN_HANDOFF_BUSY')
            self._measurement_handoff=None;self._measurement_consumed.clear()
            started=self.monotonic()
            self._measurement_pending=completion
        # The existing 5ms decision worker consumes the fixed original. The
        # unchanged 10ms progress limit bounds waiting; no cache lock is held.
        consumed=self._measurement_consumed.wait(.010)
        if (not consumed or self._measurement_handoff is None
                or not 0<=self._measurement_handoff['clocks']['wall_after_s']-started<=.010):
            self._failure='HEAD_STOPPED_MAIN_PROGRESS_DEADLINE'
            self.port._head_policy_binding_failed=True
            callback=getattr(self.port,'_head_fault_callback',None)
            if callable(callback):callback(self._failure)
            self.check()
        self.check()
        return self._measurement_handoff

    def take_image(self):
        with self.port._lock:
            pending=self._pending;self._pending=None
        return pending

    def infer(self,detector,tf_buffer,*,session_id,attempt_id,stop_velocity_rad_s):
        """Consume an advancing exposure once; all SDK/CUDA work is outside cache."""
        self.check()
        with self.port._lock:
            if self._window_finished:return None
            pending=self._pending
            if pending is None:return None
            record,data=pending
            matches=[row for row in self.info_messages if row['source_ns']==record['source_ns']]
            if not matches:return None
            info=dict(matches[-1])
            causal=next((row for row in reversed(self.port._head_samples)
                         if row['source_ns']<=record['source_ns']),None)
            joint=None if causal is None else dict(causal)
        if (joint is None or not joint['valid'] or not info['valid'] or not record['valid']
                or any(abs(value)>stop_velocity_rad_s for value in joint['velocities'])):
            raise ValueError('HEAD_STOPPED_INFERENCE_INPUT_INVALID')
        from rclpy.time import Time
        import numpy as np
        target_time=Time(nanoseconds=record['source_ns'])
        # TF delivery is an admission prerequisite. Waiting keeps the one
        # original exposure/receipt intact; it never reruns an admitted job or
        # substitutes latest TF. A replacement still consumes this attempt.
        if not tf_buffer.can_transform('base',self.frame_id,target_time):return None
        transform=tf_buffer.lookup_transform('base',self.frame_id,target_time)
        tf_source=_source(transform)
        rotation_matrix(transform.transform.rotation)
        translation=transform.transform.translation
        if (tf_source<=0 or tf_source>record['source_ns']
                or any(not math.isfinite(getattr(translation,key)) for key in ('x','y','z'))):
            raise ValueError('HEAD_STOPPED_TF_INVALID')
        cpu_inputs=claim=None
        if self._measurement_monitor is not None:
            if session_id!=self._measurement_scope['session_id']:
                raise PermissionError('HEAD_STOPPED_MEASUREMENT_SESSION_CHANGED')
            claim={key:self._measurement_scope[key] for key in ('epoch','generation','session_id')}
            claim.update(image_source_ns=record['source_ns'],info_source_ns=info['source_ns'],
                joint_source_ns=joint['source_ns'],tf_source_ns=tf_source,image_frame_id=self.frame_id,
                payload_sha256=record['payload_sha256'],image_received_wall_s=record['wall_s'],
                info_received_wall_s=info['wall_s'])
            cpu_inputs=self._measurement_request('CALIBRATION_FRAME_INPUTS',claim)
            if not cpu_inputs['inputs_ready']:return None
        with self.port._lock:
            self.check()
            if self._pending is not pending:raise ValueError('HEAD_STOPPED_IMAGE_DROPPED')
            self._pending=None
        admission=self.monotonic()
        if joint['wall_s']>admission:raise ValueError('HEAD_STOPPED_JOINT_FUTURE')
        result=detector.detect(np.frombuffer(data,dtype=np.uint8).reshape(480,640,3),
            session_id=session_id,attempt_id=attempt_id,source_stamp_ns=record['source_ns'],
            source_frame_id=self.frame_id)
        completion=self.monotonic()
        sources=(record['source_ns'],info['source_ns'],joint['source_ns'],tf_source)
        row=dict(source_ns=record['source_ns'],info_source_ns=info['source_ns'],
            joint_source_ns=joint['source_ns'],tf_source_ns=tf_source,
            image_received_wall_s=record['wall_s'],info_received_wall_s=info['wall_s'],
            admission_wall_s=admission,completion_wall_s=completion,
            source_skew_s=(max(sources)-min(sources))*1e-9,detections=result,
            tf_translation=[getattr(translation,key) for key in ('x','y','z')],
            tf_rotation=[getattr(transform.transform.rotation,key) for key in ('x','y','z','w')])
        if cpu_inputs is not None:
            from so101_demo.act.head_monitor import digest
            cpu_completion=self._measurement_request('CALIBRATION_FRAME_COMPLETION',dict(
                claim=claim,completion_wall_s=completion,result_sha256=digest(result)))
            if any(cpu_completion['original_snapshot'][key]!=cpu_inputs['original_snapshot'][key]
                    for key in ('image','info')):
                raise PermissionError('HEAD_STOPPED_MEASUREMENT_ORIGINAL_CHANGED')
            # Consume the copied CPU completion before reading Main clocks.
            handoff=self._main_measurement_handoff(cpu_completion)
            row.update(cpu_measurement_inputs=cpu_inputs,cpu_measurement_completion=cpu_completion,
                root_handoff=handoff,matched_consumer_measurement=dict(motion_authority=False,
                    image_source_ns=record['source_ns'],
                    cpu_image_received_wall_s=cpu_inputs['original_snapshot']['image']['wall_s'],
                    cpu_info_received_wall_s=cpu_inputs['original_snapshot']['info']['wall_s'],
                    cpu_inputs_decision_wall_s=cpu_inputs['original_snapshot']['decision']['wall_after_s'],
                    cpu_completion_decision_wall_s=cpu_completion['original_snapshot']['decision']['wall_after_s'],
                    root_handoff_decision_wall_s=handoff['clocks']['wall_after_s']))
        return row

    def window(self,*,start_ns,end_ns,decisions,polls,inferences):
        """Build one declared cohort; keep pre-window originals as carry-in only."""
        self.check()
        def inside(wall):return start_ns<=nanoseconds(wall)<=end_ns
        def series(rows):
            before=[dict(row) for row in rows if nanoseconds(row['wall_s'])<start_ns]
            if not before:raise ValueError('HEAD_STOPPED_CARRY_IN_MISSING')
            return [dict(row) for row in rows if inside(row['wall_s'])],before[-1]
        with self.port._lock:
            joint,carry_joint=series(self.port._head_samples)
            camera,carry_camera=series(self.camera_messages)
            info,carry_info=series(self.info_messages)
            clock,carry_clock=series(self.clock_messages)
        window=dict(start_wall_s=start_ns*1e-9,end_wall_s=end_ns*1e-9,
            joint_messages=joint,camera_messages=camera,info_messages=info,clock_messages=clock,
            carry_in=dict(joint=carry_joint,camera=carry_camera,info=carry_info,clock=carry_clock),
            decisions=[row for row in decisions if inside(row['clocks']['wall_before_s'])],
            watchdog_polls=[wall for wall in polls if inside(wall)],
            inferences=[row for row in inferences if inside(row['image_received_wall_s'])],
            clock_resolution_s=min((right['source_ns']-left['source_ns'])*1e-9
                for left,right in zip(clock,clock[1:])))
        if self._measurement_monitor is not None:
            window['consumer_measurement']='MATCHED_CPU_CUDA_MAIN'
            window['root_handoff_schedule']='EXISTING_5MS_DECISION_WORKER'
        return window


def measure_stopped_workload(capture,detector,tf_buffer,*,session_id,stop_velocity_rad_s,
                             stop_latency_s,progress=lambda **fields:None,before_stable=lambda:None):
    """Warm once, then stable 10 s and one complete 20 s original CUDA window."""
    capture.check();discovery_deadline=time.monotonic()+10.
    while True:
        result=capture.infer(detector,tf_buffer,session_id=session_id,attempt_id='bootstrap_warmup',
                             stop_velocity_rad_s=stop_velocity_rad_s)
        if result is not None:break
        if time.monotonic()>=discovery_deadline:raise TimeoutError('HEAD_STOPPED_DISCOVERY_TIMEOUT')
        time.sleep(.001)
    detector.reset();before_stable();capture.begin_capture()
    decisions,polls,inferences=[],[],[];errors=[];stop=threading.Event()
    capture.workload=dict(decisions=decisions,watchdog_polls=polls,inferences=inferences)
    def worker(period,consume):
        try:
            due=time.monotonic()
            while not stop.is_set():
                consume();due+=period
                # Do not fabricate catch-up decisions after a scheduling stall.
                delay=due-time.monotonic()
                if delay<0:due=time.monotonic();delay=0
                stop.wait(delay)
        except BaseException as error:errors.append(error);stop.set()
    def decision():decisions.append(capture.snapshot(consume_measurement=True))
    def watchdog():capture.check();polls.append(time.monotonic())
    threads=[threading.Thread(target=worker,args=(.005,decision),name='head-bootstrap-decisions'),
             threading.Thread(target=worker,args=(.002,watchdog),name='head-bootstrap-watchdog')]
    # First advancing originals must exist before the first decision. This is
    # discovery after warmup; stable duration starts afterwards, never retried.
    while not capture.camera_messages or not capture.info_messages or not capture.clock_messages:
        if time.monotonic()>=discovery_deadline:raise TimeoutError('HEAD_STOPPED_DISCOVERY_TIMEOUT')
        time.sleep(.001)
    for thread in threads:thread.start()
    stable_start=time.monotonic();start_ns=end_ns=None
    progress(stage='stable',stable_start_wall_s=stable_start)
    try:
        while end_ns is None or time.monotonic_ns()<end_ns:
            if errors:raise errors[0]
            capture.check()
            if start_ns is None and time.monotonic()-stable_start>=10.:
                with capture.port._lock:
                    receipts=[row['wall_s'] for row in capture.camera_messages]
                    stable_joints=[dict(row) for row in capture.port._head_samples if row['wall_s']>=stable_start]
                if (len(stable_joints)<900 or len(receipts)<90
                        or any(not row['valid'] or any(abs(value)>stop_velocity_rad_s for value in row['velocities'])
                               for row in stable_joints)
                        or any(abs((right['source_ns']-left['source_ns'])*1e-9-.01)>1e-6
                               for left,right in zip(stable_joints,stable_joints[1:]))):
                    raise ValueError('HEAD_STOPPED_STABLE_STREAM_INVALID')
                # Choose the phase from the preceding stable cohort before the
                # first declaration. Both budgets use original monotonic wall
                # durations; no source-clock or real-time-factor conversion.
                stable_inferences=[row for row in inferences if row['image_received_wall_s']>=stable_start]
                latencies=[row.get('matched_consumer_measurement',{}).get(
                    'root_handoff_decision_wall_s',row['completion_wall_s'])-row['image_received_wall_s']
                    for row in stable_inferences]
                receipt_gaps=[right['wall_s']-left['wall_s'] for left,right in zip(stable_joints,stable_joints[1:])]
                if (len(latencies)<90 or not receipt_gaps
                        or any(not math.isfinite(value) or value<0 for value in latencies+receipt_gaps)):
                    raise ValueError('HEAD_STOPPED_WINDOW_PHASE_INVALID')
                processing_p99=_quantile(latencies,.99);joint_receipt_p99=_quantile(receipt_gaps,.99)
                phase_budget=dict(stable_inferences=len(latencies),stable_joint_receipt_gaps=len(receipt_gaps),
                    processing_wall_p99_s=processing_p99,joint_receipt_gap_wall_p99_s=joint_receipt_p99,
                    processing_margin_s=processing_p99+joint_receipt_p99,quantile='linear (n-1)*p',
                    clock='original monotonic wall durations')
                midpoint=stopped_window_boundary(receipts,now_ns=time.monotonic_ns(),
                    processing_margin_s=phase_budget['processing_margin_s'])
                if midpoint is not None:
                    start_ns=midpoint;end_ns=start_ns+20_000_000_000
                    capture.declare_window(start_ns=start_ns,end_ns=end_ns)
                    capture.workload.update(start_ns=start_ns,end_ns=end_ns,boundary_processing_budget=phase_budget)
                    progress(stage='window',start_ns=start_ns,end_ns=end_ns,boundary_processing_budget=phase_budget)
                elif time.monotonic()-stable_start>10.2:
                    # The fixed 10 Hz source gets at most two source periods
                    # to present the next original. Keep consuming stable
                    # exposures while waiting; never retry a declared window.
                    raise ValueError('HEAD_STOPPED_WINDOW_DECLARATION_LATE')
            result=capture.infer(detector,tf_buffer,session_id=session_id,attempt_id='bootstrap_workload',
                                 stop_velocity_rad_s=stop_velocity_rad_s)
            if result is not None:inferences.append(result)
            time.sleep(.001)
    finally:
        stop.set()
        for thread in threads:thread.join(timeout=1.)
        if any(thread.is_alive() for thread in threads):raise RuntimeError('HEAD_STOPPED_WORKER_TEARDOWN_FAILED')
    if errors:raise errors[0]
    capture.finish_window()
    window=capture.window(start_ns=start_ns,end_ns=end_ns,decisions=decisions,polls=polls,inferences=inferences)
    progress(stage='collected',window=window)
    measured=evaluate_feedback_window(window,stop_latency_s=stop_latency_s)
    return window,measured
