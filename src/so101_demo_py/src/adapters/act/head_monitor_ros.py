"""CPU-only, neck-scoped ROS observations owned by the exec monitor.

This observer creates GetResult/CancelGoal clients and no SendGoal client. Unknown
UUIDs remain unresolved until authoritative action state is actually observed.
The composition owns its executor, strict native close worker and journal writer.
"""
from collections import deque
import hashlib
import math
import threading
import time
import uuid

from action_msgs.msg import GoalStatusArray
from action_msgs.srv import CancelGoal
from control_msgs.action import FollowJointTrajectory
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from unique_identifier_msgs.msg import UUID

from so101_demo.act.head_feedback import FeedbackPolicy, decision_clocks, nanoseconds
from .ros_execution import RosControllerPort
from .ros_search import RGB_QOS
from .head_clock_binding import bind_head_clock

_ACTION='/neck_controller/follow_joint_trajectory/_action/'


class _NoMotion:
    def send_goal_async(self,*args,**kwargs):raise PermissionError('MONITOR_MOTION_FORBIDDEN')


class _ObservationPort(RosControllerPort):
    def __init__(self,*args,observe,**kwargs):
        self._observe=observe
        super().__init__(*args,**kwargs)

    def _head_feedback_message(self,message):
        super()._head_feedback_message(message)
        with self._lock:original=dict(self._head_feedback)
        self._observe('JOINT_ORIGINAL',sample=original)

    def send(self,*args,**kwargs):raise PermissionError('MONITOR_MOTION_FORBIDDEN')


class HeadROSMonitor:
    def __init__(self,node,*,epoch,generation,stop_velocity_rad_s,stop_latency_s,
                 camera_max_age_s,camera_frame_id,emit,fault_callback,monotonic=time.monotonic,controller_port=None):
        if (type(epoch) is not str or not epoch or type(generation) is not int or generation<=0
                or any(type(value) not in (int,float) or not math.isfinite(value) or value<=0
                       for value in (stop_velocity_rad_s,stop_latency_s,camera_max_age_s))
                or type(camera_frame_id) is not str or not camera_frame_id
                or not callable(emit) or not callable(fault_callback) or not callable(monotonic)):
            raise ValueError('HEAD_MONITOR_ROS_CONFIG_INVALID')
        self.node=node;self.epoch=epoch;self.generation=generation;self.monotonic=monotonic
        self.stop_latency=stop_latency_s;self.camera_age=camera_max_age_s
        self.camera_skew=None
        self.camera_frame=camera_frame_id;self.emit=emit;self.fault_callback=fault_callback
        self.failed=False;self._fault_wall=None;self._fault_reason=None;self._closed=False
        self._lock=threading.RLock();self._stop_lock=threading.Lock();self._policy=None;self._active=False
        self._primary=None;self._executor_wall=None;self._clock=None;self._camera=None
        self._completed_inference_deadlines={}
        self._images={};self._infos={};self._camera_watermark=0
        self._measurement_images={}
        self._image_source=self._info_source=0
        self._outstanding={};self._stop_started=False;self.watchdog_polls=deque(maxlen=20000)
        self._external_inputs=controller_port is not None
        if controller_port is None:
            self.port=_ObservationPort(node,_NoMotion(),('neck_yaw_joint',),
                stop_velocity_rad_s=stop_velocity_rad_s,max_age_s=camera_max_age_s,
                monotonic=monotonic,head_bootstrap=True,
                head_fault_callback=lambda reason:self.fault(reason),observe=self._event)
        else:
            if (not isinstance(controller_port,RosControllerPort) or controller_port.node is not node
                    or controller_port.names!=('neck_yaw_joint',) or controller_port.feedback_policy is None
                    or controller_port._head_policy_binding_failed
                    or controller_port._head_fault_callback is not None
                    or controller_port.stop_velocity!=stop_velocity_rad_s):
                raise ValueError('HEAD_PRIMARY_SHARED_PORT_INVALID')
            self.port=controller_port;self._lock=controller_port._lock
            self._policy=controller_port.feedback_policy
            controller_port._head_fault_callback=lambda reason:self.fault(reason)
        self.service_names=(_ACTION+'get_result',_ACTION+'cancel_goal')
        self._result_client=node.create_client(FollowJointTrajectory.Impl.GetResultService,
                                                self.service_names[0])
        self._cancel_client=node.create_client(CancelGoal,self.service_names[1])
        self.subscriptions=[node.create_subscription(GoalStatusArray,_ACTION+'status',self._status,
                                                     qos_profile_sensor_data)]
        if not self._external_inputs:
            self.subscriptions.extend([
                bind_head_clock(node,self._on_clock,monotonic=self.monotonic),
                node.create_subscription(Image,'/head_camera/color',self._on_image,RGB_QOS),
                node.create_subscription(CameraInfo,'/head_camera/camera_info',self._on_info,RGB_QOS)])

    def _event(self,event,**fields):
        # The supplied sink must enqueue bounded owned records without disk I/O.
        try:self.emit(event,epoch=self.epoch,generation=self.generation,**fields)
        except Exception:
            self.fault('HEAD_MONITOR_JOURNAL_FAILED')

    def fault(self,reason,*,fault_wall_s=None,report=True):
        wall=self.monotonic() if fault_wall_s is None else fault_wall_s
        # Publish admission failure before locks, logger, native or ROS calls.
        self.failed=True;self.port._head_policy_binding_failed=True
        with self._lock:
            first=self._fault_wall is None
            earlier=first or wall<self._fault_wall
            if earlier:
                self._fault_wall=wall;self._fault_reason=reason
        if earlier and report:
            try:self.fault_callback(reason,wall)
            except Exception:
                self._fault_reason='HEAD_MONITOR_FAULT_REPORT_FAILED'
        return first

    def bind_policy(self,values):
        if self.failed or self._closed or self._policy is not None:
            self.fault('HEAD_MONITOR_POLICY_REBOUND')
            raise PermissionError('HEAD_MONITOR_ROS_REVOKED')
        self._policy=FeedbackPolicy.parse(values)
        self.port.bind_head_policy(self._policy)

    def inventory(self,goal_uuid):
        if self.failed or self._closed or self._policy is None:
            raise PermissionError('HEAD_MONITOR_ROS_REVOKED')
        parsed=uuid.UUID(goal_uuid)
        if str(parsed)!=goal_uuid or parsed.version!=4:
            self.fault('HEAD_MONITOR_UUID_INVALID');raise ValueError('HEAD_MONITOR_UUID_INVALID')
        with self.port._lock:
            reused=goal_uuid in self.port._goals
            if not reused and not self.failed:
                self.port._goals[goal_uuid]=dict(accepted=None,handle=None,result=None,
                    cancel_requested=False,cancel_ack=False,error=None)
        if reused:
            self.fault('HEAD_MONITOR_UUID_REUSED');raise PermissionError('HEAD_MONITOR_UUID_REUSED')
        if self.failed:raise PermissionError('HEAD_MONITOR_ROS_REVOKED')
        self._event('UUID_INVENTORIED',goal_uuid=goal_uuid,wall_s=self.monotonic())

    def primary_rejection(self,goal_uuid):
        # Only the composition may call this after an authenticated primary
        # record carrying the actual SendGoal accepted=False response.
        with self.port._lock:
            record=self.port._goals[goal_uuid]
            contradiction=record['accepted'] is True
            if not contradiction:record['accepted']=False
        if contradiction:
            self.fault('HEAD_MONITOR_ACCEPTANCE_CONTRADICTION');return
        self._event('ACTION_REJECTED',goal_uuid=goal_uuid,source='authenticated-primary-response')

    def _status(self,message):
        for status in message.status_list:
            gid=str(uuid.UUID(bytes=bytes(status.goal_info.goal_id.uuid)))
            value=int(status.status)
            with self.port._lock:
                record=self.port._goals.get(gid)
                if record is None:continue
                if not 1<=value<=6:continue
                if record['accepted'] is False:
                    contradiction=True
                else:record['accepted']=True;contradiction=False
            if contradiction:self.fault('HEAD_MONITOR_ACCEPTANCE_CONTRADICTION')
            self._event('ACTION_STATUS',goal_uuid=gid,status=value,wall_s=self.monotonic())
            # Even a terminal status does not invent a GetResult response.

    def _request(self,gid,kind):
        with self._lock:
            if (gid,kind) in self._outstanding:return
            self._outstanding[(gid,kind)]=None
        def operation():
            request=(CancelGoal.Request() if kind=='cancel' else
                     FollowJointTrajectory.Impl.GetResultService.Request())
            goal_id=UUID(uuid=list(uuid.UUID(gid).bytes))
            if kind=='cancel':request.goal_info.goal_id=goal_id
            else:request.goal_id=goal_id
            client=self._cancel_client if kind=='cancel' else self._result_client
            self._event('ACTION_RPC_STARTED',goal_uuid=gid,kind=kind,wall_s=self.monotonic())
            future=client.call_async(request)
            with self._lock:self._outstanding[(gid,kind)]=future
            future.add_done_callback(lambda result:self._response(gid,kind,result))
        self.port._head_dispatch_io(gid,kind,operation)

    def _response(self,gid,kind,future):
        try:
            response=future.result()
            with self.port._lock:
                record=self.port._goals[gid]
                if kind=='cancel':record['cancel_ack']=response.return_code==0
                elif response.status in (1,2,3,4,5,6):
                    if record['accepted'] is False:
                        raise ValueError('HEAD_MONITOR_ACCEPTANCE_CONTRADICTION')
                    terminal=record['result']
                    if terminal is not None and (response.status!=terminal.status or response!=terminal):
                        raise ValueError('HEAD_MONITOR_TERMINAL_CONTRADICTION')
                    record['accepted']=True
                    if response.status in (4,5,6):record['result']=response
                elif response.status!=0:raise ValueError('HEAD_MONITOR_RESULT_STATUS_INVALID')
            self._event('ACTION_RPC_RESPONSE',goal_uuid=gid,kind=kind,wall_s=self.monotonic(),
                status=response.status if kind=='result' else None,
                return_code=response.return_code if kind=='cancel' else None)
        except Exception as error:
            self.port._head_io_failed(gid,error)
        finally:
            with self._lock:self._outstanding.pop((gid,kind),None)

    def request_cancel_all(self):
        with self.port._lock:
            ids=tuple(gid for gid,record in self.port._goals.items()
                if record['accepted'] is not False and
                   getattr(record['result'],'status',None) not in (4,5,6))
            for gid in ids:self.port._goals[gid]['cancel_requested']=True
        # Pending acceptance is included; never call a missing goal handle.
        for gid in ids:self._request(gid,'cancel')

    def request_results(self):
        with self.port._lock:
            ids=tuple(gid for gid,record in self.port._goals.items()
                if record['accepted'] is not False and
                   getattr(record['result'],'status',None) not in (4,5,6))
        for gid in ids:self._request(gid,'result')

    def begin_stop(self,*,fault_wall_s):
        with self._stop_lock:
            with self._lock:
                if self._fault_wall is not None:fault_wall_s=min(fault_wall_s,self._fault_wall)
            if self._stop_started:
                tightened=self.port.tighten_stop_fault(fault_wall_s)
                clocks=None
            else:
                clocks=decision_clocks(self.node,self.monotonic)
                self.port.begin_stop(dict(epoch=self.epoch+'-stop',generation=self.generation,
                    request_wall_s=clocks['wall_after_s'],request_sim_s=clocks['sim_s'],
                    fault_wall_s=fault_wall_s,stop_latency_s=self.stop_latency))
                self._stop_started=True;tightened=False
        if clocks is not None:self._event('STOP_REQUEST',fault_wall_s=fault_wall_s,clocks=clocks)
        elif tightened:self._event('STOP_DEADLINE_TIGHTENED',fault_wall_s=fault_wall_s)

    @staticmethod
    def _stamp(message):
        return message.header.stamp.sec*10**9+message.header.stamp.nanosec

    def _on_clock(self,message,*,received_wall_s=None):
        wall=self.monotonic() if received_wall_s is None else received_wall_s
        source=message.clock.sec*10**9+message.clock.nanosec
        with self._lock:
            previous=self._clock
            valid=source>0 and (previous is None or source>previous['source_ns'])
            self._clock=dict(wall_s=wall,source_ns=source,valid=valid)
        self._event('CLOCK_ORIGINAL',**self._clock)
        if not valid and self._active:self.fault('HEAD_MONITOR_CLOCK_NONADVANCING')

    def _on_image(self,message):
        record=dict(source_ns=self._stamp(message),wall_s=self.monotonic(),
            frame_id=message.header.frame_id,valid=(message.encoding=='rgb8'
            and message.width==640 and message.height==480 and message.step==1920
            and message.is_bigendian==0 and len(message.data)==640*480*3
            and message.header.frame_id==self.camera_frame))
        record['payload_sha256']=hashlib.sha256(message.data).hexdigest() if record['valid'] else None
        self._camera_message(record,image=True)

    def _on_info(self,message):
        record=dict(source_ns=self._stamp(message),wall_s=self.monotonic(),
            frame_id=message.header.frame_id,valid=bool(message.width==640 and message.height==480
            and message.header.frame_id==self.camera_frame and len(message.k)==9
            and all(math.isfinite(v) for v in message.k) and message.k[0]>0 and message.k[4]>0))
        self._camera_message(record,image=False)

    def _camera_message(self,record,*,image):
        dropped=None
        with self._lock:
            originals=self._images if image else self._infos
            source=record['source_ns']
            previous=self._image_source if image else self._info_source
            if source<=previous or not record['valid']:
                invalid=True
                record=dict(record,valid=False,error='HEAD_MONITOR_CAMERA_NONADVANCING_OR_INVALID')
            else:
                if image:
                    self._image_source=source
                    if originals:dropped=next(iter(originals.values()))
                    originals.clear()
                else:self._info_source=source
                originals[source]=record;invalid=False
                while len(originals)>32:originals.pop(next(iter(originals)))
            if image and self._policy is None and not self._active:
                # Read-only pre-policy completion can cross a warmup source
                # period. Keep physical metadata only; the admission cache
                # above remains latest-only and emits its unchanged drop.
                self._measurement_images[source]=record
                while len(self._measurement_images)>32:
                    self._measurement_images.pop(next(iter(self._measurement_images)))
        self._event('IMAGE_ORIGINAL' if image else 'INFO_ORIGINAL',**record)
        if dropped is not None:
            self._event('DROPPED_EXPOSURE',**dropped,reason='replaced-before-admission')
        if invalid and (self._active or self._external_inputs):self.fault('HEAD_MONITOR_CAMERA_INVALID')

    def observe_original(self,kind,record):
        """Primary-only original metadata, delivered after the shared cache lock.

        No new receipt clock, source clock, subscription or readiness is made.
        The independent CPU monitor continues to use its own ROS subscribers.
        """
        if not self._external_inputs:raise PermissionError('HEAD_MONITOR_EXTERNAL_INPUT_FORBIDDEN')
        if (kind not in ('CLOCK','IMAGE','INFO','JOINT') or type(record) is not dict
                or type(record.get('source_ns')) is not int or record['source_ns']<=0
                or type(record.get('wall_s')) not in (int,float)
                or not math.isfinite(record['wall_s']) or record['wall_s']<0
                or record.get('valid') is not True
                or (kind in ('IMAGE','INFO') and record.get('frame_id')!=self.camera_frame)):
            self.fault('HEAD_PRIMARY_ORIGINAL_INVALID');raise ValueError('HEAD_PRIMARY_ORIGINAL_INVALID')
        original=dict(record)
        if kind=='JOINT':
            # The shared port already owns this original. Never replace its
            # cache or receipt clock; this path adds immediate invalidity
            # closure and evidence outside that port's short cache lock.
            self._event('JOINT_ORIGINAL',sample=original)
            return
        if kind=='CLOCK':
            with self._lock:
                previous=self._clock
                invalid=previous is not None and original['source_ns']<=previous['source_ns']
                if invalid:original['valid']=False
                self._clock=original
            if invalid:self.fault('HEAD_MONITOR_CLOCK_NONADVANCING')
            self._event('CLOCK_ORIGINAL',**original)
        else:self._camera_message(original,image=kind=='IMAGE')

    def executor_progress(self):
        self._executor_wall=self.monotonic()

    def heartbeat(self,record):
        required={'wall_s','executor_wall_s','inference_deadline_wall_s'}
        if (type(record) is not dict or set(record)!=required
                or any(type(record[key]) not in (int,float) or not math.isfinite(record[key])
                       or record[key]<0 for key in ('wall_s','executor_wall_s'))
                or (record['inference_deadline_wall_s'] is not None and
                    (type(record['inference_deadline_wall_s']) not in (int,float)
                     or not math.isfinite(record['inference_deadline_wall_s'])))):
            self.fault('HEAD_MONITOR_HEARTBEAT_INVALID');raise ValueError('HEAD_MONITOR_HEARTBEAT_INVALID')
        now=self.monotonic()
        with self._lock:
            regression=(record['wall_s']>now or record['executor_wall_s']>record['wall_s']
                    or (self._primary is not None and record['wall_s']<=self._primary['wall_s']))
            if not regression:self._primary=dict(record)
        if regression:
            self.fault('HEAD_MONITOR_HEARTBEAT_REGRESSION');raise ValueError('HEAD_MONITOR_HEARTBEAT_REGRESSION')
        if self.failed:raise PermissionError('HEAD_MONITOR_ROS_REVOKED')

    def discharge_inference_deadlines(self,deadlines_ns,*,completion_wall_s):
        """Retain exact completion tombstones without rewriting a heartbeat.

        Only the owned Root result publication or an authenticated CPU lease
        completion calls this boundary. An expired deadline cannot be discharged.
        """
        if (type(deadlines_ns) is not list or not 1<=len(deadlines_ns)<=2
                or any(type(value) is not int or value<=0 for value in deadlines_ns)
                or len(set(deadlines_ns))!=len(deadlines_ns)):
            raise ValueError('HEAD_INFERENCE_DISCHARGE_INVALID')
        completed=nanoseconds(completion_wall_s)
        with self._lock:
            observed=self.monotonic()
            if (self.failed or self._closed or completed>nanoseconds(observed)
                    or any(nanoseconds(observed)>=deadline for deadline in deadlines_ns)
                    or any(deadline in self._completed_inference_deadlines for deadline in deadlines_ns)):
                raise PermissionError('HEAD_INFERENCE_DISCHARGE_REFUSED')
            receipt=dict(deadlines_ns=sorted(deadlines_ns),completion_wall_s=completion_wall_s,
                observed_wall_s=observed)
            for deadline in deadlines_ns:
                self._completed_inference_deadlines[deadline]=dict(receipt,deadlines_ns=list(receipt['deadlines_ns']))
            while len(self._completed_inference_deadlines)>32:
                self._completed_inference_deadlines.pop(next(iter(self._completed_inference_deadlines)))
        return receipt

    def activate(self,*,watchdog=True):
        if self.failed or self._policy is None or self._primary is None:
            raise PermissionError('HEAD_MONITOR_ROS_NOT_READY')
        self._active=True
        self.poll(watchdog=watchdog)
        if self.failed:raise PermissionError('HEAD_MONITOR_ROS_REVOKED')

    def poll(self,*,watchdog=True):
        now=self.monotonic()
        previous_poll=self.watchdog_polls[-1] if self.watchdog_polls else None
        if watchdog:self.watchdog_polls.append(now)
        if not self._active or self.failed:return
        with self._lock:
            primary=None if self._primary is None else dict(self._primary)
            clock=None if self._clock is None else dict(self._clock)
            camera=None if self._camera is None else dict(self._camera)
            images,infos=dict(self._images),dict(self._infos)
            executor=self._executor_wall
        original=self.port.original_feedback_snapshot()
        clocks=original['decision'];sim=clocks['sim_ns'];after=clocks['wall_after_s']
        violations=[]
        def expired(reason,original,bound):
            if original is None:
                violations.append((clocks['wall_before_s'],reason))
            else:
                elapsed=nanoseconds(after)-nanoseconds(original)
                bound_ns=math.floor(bound*1e9)
                if elapsed<0:violations.append((clocks['wall_before_s'],reason))
                elif elapsed>bound_ns:
                    violations.append(((nanoseconds(original)+bound_ns)*1e-9,reason))
        if previous_poll is not None:
            expired('HEAD_MONITOR_WATCHDOG_GAP',previous_poll,self._policy.watchdog_reaction_limit_s)
        try:
            self._policy.check_joint(original['sample'],clocks)
        except (KeyError,TypeError,ValueError) as error:
            receipt=None if original['sample'] is None else original['sample']['wall_s']
            if str(error)=='HEAD_FEEDBACK_RECEIPT_STALE':
                expired(str(error),receipt,self._policy.joint_max_receipt_age_s)
            else:violations.append((clocks['wall_before_s'],str(error)))
        try:
            for value in (primary['wall_s'],primary['executor_wall_s'],executor):
                expired('HEAD_MONITOR_HEARTBEAT_STALE',value,self._policy.watchdog_reaction_limit_s)
            if primary['inference_deadline_wall_s'] is not None and after>=primary['inference_deadline_wall_s']:
                # Recheck after reading decision clocks: a completed lease may
                # have committed since this poll copied the original heartbeat.
                with self._lock:
                    completed=nanoseconds(primary['inference_deadline_wall_s']) in self._completed_inference_deadlines
                if not completed:
                    violations.append((primary['inference_deadline_wall_s'],'HEAD_MONITOR_INFERENCE_DEADLINE'))
            if clock is None or not clock['valid']:raise ValueError('HEAD_MONITOR_CLOCK_STALE')
            expired('HEAD_MONITOR_CLOCK_STALE',clock['wall_s'],self._policy.clock_interarrival_deadline_s)
            # Images retain reception order and capacity one. No sorting can
            # turn backward originals into a manufactured advancing stream.
            for source,image in images.items():
                if source not in infos:continue
                if source<=self._camera_watermark:continue
                info=infos[source]
                if source>sim:continue
                if (not 0<=after-image['wall_s']<=self.camera_age
                        or not 0<=after-info['wall_s']<=self.camera_age
                        or not 0<=sim-source<=math.floor(self._policy.camera_max_source_age_s*1e9)):
                    raise ValueError('HEAD_MONITOR_CAMERA_STALE')
                camera=image
                self._camera_watermark=source
                with self._lock:
                    self._camera=dict(image)
                    self._images.pop(source,None)
            if camera is None:raise ValueError('HEAD_MONITOR_CAMERA_GAP')
            expired('HEAD_MONITOR_CAMERA_GAP',camera['wall_s'],self._policy.camera_interarrival_deadline_s)
            if not 0<=sim-camera['source_ns']<=math.floor(self._policy.camera_max_source_age_s*1e9):
                raise ValueError('HEAD_MONITOR_CAMERA_SOURCE_STALE')
        except (KeyError,TypeError,ValueError) as error:
            violations.append((clocks['wall_before_s'],str(error)))
        reason=None
        if violations:
            crossing,reason=min(violations)
            self.fault(reason,fault_wall_s=crossing)
        self._event('WATCHDOG_POLL',wall_s=after,decision=clocks,reason=reason)

    def wait_for_operations(self,*,timeout_s):
        """Diagnostic waiting for SDK request initiation, never a stop predicate."""
        deadline=time.monotonic()+timeout_s
        while time.monotonic()<deadline:
            if all(worker._queue.unfinished_tasks==0 for worker in self.port._head_io.values()):return True
            time.sleep(.001)
        return False

    def close(self,*,timeout_s):
        self._closed=True;self.failed=True
        return self.port.close_head_io(timeout_s=timeout_s)
