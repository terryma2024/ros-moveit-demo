"""One CPU exec monitor's owned ROS runtime and staged private protocol.

Construction and provisioning run before CUDA and before motion. Configuration
is asynchronous so discovery/import/fsync work never extends the private IPC
exchange deadline. This entry currently accepts calibration-only policy files;
it cannot supply production qualification authority.
"""
import base64
from concurrent.futures import Future
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import stat
import threading
import time

from so101_demo.act.head_monitor import HeadMonitorEpoch, digest
from so101_demo.act.head_feedback_measurement import evaluate_feedback_window
from so101_demo.act.head_feedback import nanoseconds
from .controller_reservation_provision import (
    _private_parent,_process_start_ticks,write_head_revocation_provision)
from .head_monitor_goal_binding import validate_goal_inventory,warm_goal_binding
from .head_monitor_ros import HeadROSMonitor
from .head_revocation import NativeRevocationClient

_SHA=re.compile(r'[0-9a-f]{64}\Z')
_C2A='2afd550694abfbe6d1c37922c9ea0b4a0f8567bef94cf4c4ec85d4b50c0cc82a'


def _peer(pid):return dict(uid=os.geteuid(),pid=pid,start_ticks=_process_start_ticks(pid))


def _read(path,limit):
    path=Path(path)
    if not path.is_absolute() or path!=Path(os.path.normpath(path)):
        raise PermissionError('HEAD_MONITOR_INPUT_PATH_INVALID')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise PermissionError('HEAD_MONITOR_INPUT_FILE_INVALID')
        body=handle.read(limit+1)
    if len(body)>limit:raise ValueError('HEAD_MONITOR_INPUT_TOO_LARGE')
    return body


def _sha_file(path,expected,limit=128*1024*1024):
    if type(expected) is not str or not _SHA.fullmatch(expected):
        raise ValueError('HEAD_MONITOR_INPUT_HASH_INVALID')
    body=_read(path,limit)
    if hashlib.sha256(body).hexdigest()!=expected:raise PermissionError('HEAD_MONITOR_INPUT_HASH_MISMATCH')
    return body


def _provision(path,*,authority,actor,native_owner,session_id):
    path=Path(path);_private_parent(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as handle:
        info=os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=actor['uid']
                or stat.S_IMODE(info.st_mode)!=0o600):
            raise PermissionError('HEAD_MONITOR_PROVISION_FILE_INVALID')
        body=handle.read(512)
    if len(body)<56 or body[:4]!=b'SOPR':raise PermissionError('HEAD_MONITOR_PROVISION_INVALID')
    version=1 if authority=='main' else 2;code=3 if authority in ('main','monitor') else 4
    session=session_id.encode('ascii');stem={'main':'neck','monitor':'neck-revoke','primary':'neck-primary-revoke'}[authority]
    endpoint=path.parent/(stem+'.sock')
    if (path.name!=stem+'.provision' or body[4]!=version or body[5]!=code
            or body[6]!=len(session) or int.from_bytes(body[8:12],'big')!=actor['uid']
            or int.from_bytes(body[12:16],'big')!=actor['pid']
            or int.from_bytes(body[16:24],'big')!=actor['start_ticks'] or not any(body[24:56])):
        raise PermissionError('HEAD_MONITOR_PROVISION_SCOPE_INVALID')
    if version==1:
        if body[7]!=0 or body[56:]!=session:
            raise PermissionError('HEAD_MONITOR_PROVISION_SCOPE_INVALID')
    else:
        peer_bytes=(native_owner['uid'].to_bytes(4,'big')+native_owner['pid'].to_bytes(4,'big')+
                    native_owner['start_ticks'].to_bytes(8,'big'))
        socket_bytes=os.fsencode(endpoint)
        if (body[7]!=len(socket_bytes) or body[56:72]!=peer_bytes
                or body[72:]!=session+socket_bytes):
            raise PermissionError('HEAD_MONITOR_PROVISION_NATIVE_INVALID')
    return dict(path=str(path),socket_path=str(endpoint),sha256=hashlib.sha256(body).hexdigest()),body[24:56]


class HeadMonitorRuntime:
    """Only the authenticated exec server constructs and calls this object."""
    def __init__(self,*,epoch,generation,session_id,primary):
        if primary!=_peer(os.getppid()):raise PermissionError('HEAD_MONITOR_RUNTIME_PRIMARY_INVALID')
        self.primary=dict(primary);self.identity=_peer(os.getpid())
        self.epoch=HeadMonitorEpoch(epoch=epoch,generation=generation,session_id=session_id)
        self._configure_future=None;self._configure_thread=None;self._configured=False
        self._observer=None;self._context=None;self._node=None;self._executor=None;self._spinner=None
        self._journal_handle=None;self._journal_path=None;self._journal_thread=None
        self._records=queue.Queue(maxsize=20000);self._journal_error=None;self._journal_count=0
        self._finished=False;self._shutdown=threading.Event();self._fault_event=threading.Event()
        self._stop_done=threading.Event();self._close_done=threading.Event()
        self._watchdog_wall=None;self._fault=None;self._native_close=None;self._native_close_error=None
        self._policy=None;self._dependencies=None;self._provisions=None;self._revoker=None
        self._prearm_guarded=False;self._goal_codec_warmup=None
        self._guard_lock=threading.Lock();self._threads=[]

    @property
    def configured(self):return self._configured

    @property
    def revoked(self):return self._fault is not None or self.epoch.stage=='REVOKED'

    def _emit(self,event,**fields):
        if self._journal_error is not None:raise PermissionError('HEAD_MONITOR_JOURNAL_FAILED')
        self._records.put_nowait(dict(event=event,**fields))

    def _write_journal(self):
        try:
            while True:
                record=self._records.get()
                try:
                    if record is None:break
                    self._journal_handle.write(json.dumps(record,sort_keys=True,allow_nan=False)+'\n')
                    self._journal_count+=1
                finally:self._records.task_done()
            self._journal_handle.flush();os.fsync(self._journal_handle.fileno())
        except Exception as error:
            self._journal_error=type(error).__name__
            self.fault('HEAD_MONITOR_JOURNAL_FAILED',time.monotonic())

    def configure(self,record):
        if self._configure_future is not None or self.revoked:
            self.fault('HEAD_MONITOR_CONFIGURE_REUSED',time.monotonic())
            raise PermissionError('HEAD_MONITOR_CONFIGURE_REUSED')
        # Own a bounded JSON snapshot before handing configuration to another
        # thread; the authenticated codec has already bounded its wire cost.
        owned=json.loads(json.dumps(record,allow_nan=False))
        self._configure_future=Future()
        def run():
            try:self._configure(owned);self._configure_future.set_result(True)
            except BaseException as error:
                self.fault('HEAD_MONITOR_CONFIGURE_FAILED',time.monotonic())
                self._configure_future.set_exception(error)
        self._configure_thread=threading.Thread(target=run,name='head-monitor-configure',daemon=True)
        self._configure_thread.start()
        return dict(stage='CONFIGURE_PENDING',motion_authority=False)

    def configuration(self):
        if self._configure_future is None:raise PermissionError('HEAD_MONITOR_CONFIGURE_REQUIRED')
        if not self._configure_future.done():return dict(stage='CONFIGURE_PENDING',motion_authority=False)
        self._configure_future.result()
        if self.revoked:raise PermissionError('HEAD_MONITOR_RUNTIME_REVOKED')
        return dict(stage='CONFIGURED',motion_authority=False,monitor_peer=dict(self.identity),
            provisions=self._provisions,dependencies=self._dependencies,node_name=self._node.get_name(),
            executor='SingleThreadedExecutor',joint_qos=dict(depth=5,reliability='BEST_EFFORT'),
            camera_qos=dict(depth=32,reliability='RELIABLE'),goal_codec_warmup=self._goal_codec_warmup,
            native_transport=getattr(self._revoker,'transport_origin',None),
            clock_qos=dict(depth=self._node._time_source._clock_sub.qos_profile.depth,
                reliability=self._node._time_source._clock_sub.qos_profile.reliability.name),
            clock_subscription_count=sum(sub.topic_name=='/clock' for sub in self._node.subscriptions))

    def _configure(self,record):
        fields={'native_owner','reservation_directory','journal_path','dependencies','observer','purpose'}
        if type(record) is not dict or set(record)!=fields or record['purpose']!='calibration':
            raise PermissionError('HEAD_MONITOR_CONFIGURATION_INVALID')
        native=record['native_owner']
        if (type(native) is not dict or set(native)!={'uid','pid','start_ticks'}
                or native!=_peer(native['pid']) or native in (self.primary,self.identity)):
            raise PermissionError('HEAD_MONITOR_NATIVE_OWNER_INVALID')
        directory=Path(record['reservation_directory'])
        primary,primary_cap=_provision(directory/'neck.provision',authority='main',actor=self.primary,
            native_owner=native,session_id=self.epoch.session_id)
        fault,fault_cap=_provision(directory/'neck-primary-revoke.provision',authority='primary',
            actor=self.primary,native_owner=native,session_id=self.epoch.session_id)
        dependencies=record['dependencies']
        if type(dependencies) is not dict or set(dependencies)!={'weights','geometry','candidate','runtime_manifest'}:
            raise ValueError('HEAD_MONITOR_DEPENDENCIES_INVALID')
        for name,value in dependencies.items():
            if type(value) is not dict or set(value)!={'path','sha256'}:
                raise ValueError('HEAD_MONITOR_DEPENDENCY_INVALID')
            if name=='weights' and value['sha256']!=_C2A:raise PermissionError('HEAD_MONITOR_C2A_MISMATCH')
            _sha_file(value['path'],value['sha256'])
        journal=Path(record['journal_path'])
        if not journal.is_absolute() or journal!=Path(os.path.normpath(journal)):
            raise ValueError('HEAD_MONITOR_JOURNAL_PATH_INVALID')
        # One new evidence file in the owner's registered run; never overwrite.
        self._journal_handle=journal.open('x',encoding='ascii');self._journal_path=journal
        self._journal_thread=threading.Thread(target=self._write_journal,name='head-monitor-journal',daemon=True)
        self._journal_thread.start()
        observer=record['observer']
        if type(observer) is not dict or set(observer)!={'stop_velocity_rad_s','stop_latency_s','camera_max_age_s','camera_frame_id'}:
            raise ValueError('HEAD_MONITOR_OBSERVER_CONFIG_INVALID')
        capability=write_head_revocation_provision(directory/'neck-revoke.provision',
            session_id=self.epoch.session_id,native_owner=native,socket_path=directory/'neck-revoke.sock')
        monitor,actual_cap=_provision(directory/'neck-revoke.provision',authority='monitor',actor=self.identity,
            native_owner=native,session_id=self.epoch.session_id)
        if actual_cap!=capability or len({primary_cap,fault_cap,capability})!=3:
            raise PermissionError('HEAD_MONITOR_PROVISION_CAPABILITY_COLLISION')
        self._provisions=dict(main=primary,primary_fault=fault,monitor_fault=monitor)
        self._dependencies=dependencies
        # This client cannot arm, reserve or use the primary's exact-peer endpoint.
        self._revoker=NativeRevocationClient(directory/'neck-revoke.sock',capability=capability,
            native_owner=native,generation=self.epoch.generation,timeout_s=.002)
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.node import Node
        from rclpy.parameter import Parameter
        self._context=Context();rclpy.init(context=self._context)
        self._node=Node('head_monitor_'+self.epoch.epoch.replace('-','_'),context=self._context,
                         parameter_overrides=[Parameter('use_sim_time',value=True)])
        self._goal_codec_warmup=warm_goal_binding()
        self._observer=HeadROSMonitor(self._node,epoch=self.epoch.epoch,generation=self.epoch.generation,
            **observer,emit=self._emit,fault_callback=self.fault)
        self._node.create_timer(.002,self._observer.executor_progress,
            clock=rclpy.clock.Clock(clock_type=rclpy.clock.ClockType.STEADY_TIME))
        self._executor=SingleThreadedExecutor(context=self._context);self._executor.add_node(self._node)
        def spin():
            try:self._executor.spin()
            except BaseException:self.fault('HEAD_MONITOR_EXECUTOR_FAILED',time.monotonic())
        self._spinner=threading.Thread(target=spin,name='head-monitor-ros-executor',daemon=True)
        self._spinner.start()
        for target,name in ((self._watchdog,'head-monitor-watchdog'),
                            (self._close_native,'head-monitor-native-close'),
                            (self._cancel_and_stop,'head-monitor-cancel-stop')):
            thread=threading.Thread(target=target,name=name,daemon=True);thread.start();self._threads.append(thread)
        self._emit('CONFIGURED',epoch=self.epoch.epoch,generation=self.epoch.generation,
            monitor_peer=self.identity,primary_peer=self.primary,native_owner=native,
            dependencies=dependencies,provisions=self._provisions,observer=observer,
            cpu_only=True,motion_authority=False,goal_codec_warmup=self._goal_codec_warmup,
            native_transport=dict(self._revoker.transport_origin))
        self._configured=True

    def bind_policy(self,record):
        if not self._configured or self.revoked or self._policy is not None:
            raise PermissionError('HEAD_MONITOR_POLICY_STAGE_INVALID')
        if type(record) is not dict or set(record)!={'path','sha256'}:
            raise ValueError('HEAD_MONITOR_POLICY_REFERENCE_INVALID')
        body=_sha_file(record['path'],record['sha256'],1024*1024)
        policy=json.loads(body)
        required={'purpose','motion_authority','epoch','generation','session_id','dependencies',
                  'measurement','values','camera_seed_values','sha256'}
        if (type(policy) is not dict or set(policy)!=required or policy['purpose']!='calibration'
                or policy['motion_authority'] is not False or policy['epoch']!=self.epoch.epoch
                or policy['generation']!=self.epoch.generation or policy['session_id']!=self.epoch.session_id
                or policy['dependencies']!=self._dependencies
                or policy['sha256']!=digest({k:v for k,v in policy.items() if k!='sha256'})):
            raise PermissionError('HEAD_MONITOR_POLICY_BINDING_INVALID')
        measurement=policy['measurement']
        if type(measurement) is not dict or set(measurement)!={'path','sha256'}:
            raise ValueError('HEAD_MONITOR_POLICY_MEASUREMENT_INVALID')
        measured=json.loads(_sha_file(measurement['path'],measurement['sha256'],64*1024*1024))
        if (type(measured) is not dict or set(measured)!={'epoch','generation','session_id','dependencies','window','sha256'}
                or measured['epoch']!=self.epoch.epoch or measured['generation']!=self.epoch.generation
                or measured['session_id']!=self.epoch.session_id or measured['dependencies']!=self._dependencies
                or measured['sha256']!=digest({k:v for k,v in measured.items() if k!='sha256'})):
            raise PermissionError('HEAD_MONITOR_MEASUREMENT_BINDING_INVALID')
        independently_computed=evaluate_feedback_window(measured['window'],stop_latency_s=self._observer.stop_latency)
        if (independently_computed['values']!=policy['values'] or
                independently_computed['camera_seed_values']!=policy['camera_seed_values']):
            raise PermissionError('HEAD_MONITOR_POLICY_FORMULA_MISMATCH')
        camera=policy['camera_seed_values']
        if (type(camera) is not dict or set(camera)!={'max_age_s','max_skew_s'}
                or type(camera['max_age_s']) not in (int,float) or not 0<camera['max_age_s']<=.15
                or type(camera['max_skew_s']) not in (int,float) or not 0<camera['max_skew_s']<=.05):
            raise ValueError('HEAD_MONITOR_CAMERA_POLICY_INVALID')
        ack=self.epoch.bind_policy(policy['values'],record['sha256'])
        self._observer.bind_policy(policy['values']);self._observer.camera_age=camera['max_age_s']
        self._policy=record
        self._emit('POLICY_READY',ack=ack,policy_reference=record,purpose='calibration',motion_authority=False)
        return dict(ack,stage='POLICY_READY',motion_authority=False)

    def prearm_inputs(self,record):
        """Passive own-input receipt before activation; never a watchdog tick."""
        if (type(record) is not dict or set(record)!={'policy_sha256'}
                or not self._configured or self._finished or self._policy is None
                or self.epoch.stage!='POLICY_READY' or self.revoked or self._prearm_guarded
                or record['policy_sha256']!=self.epoch.policy_hash):
            raise PermissionError('HEAD_MONITOR_PREARM_INPUTS_STAGE_INVALID')
        observer=self._observer;watchdog=self._watchdog_wall
        with observer._lock:
            images={key:dict(value) for key,value in observer._images.items()}
            infos={key:dict(value) for key,value in observer._infos.items()}
            clock=None if observer._clock is None else dict(observer._clock)
            primary=None if observer._primary is None else dict(observer._primary)
            executor=observer._executor_wall
        original=observer.port.original_feedback_snapshot();decision=original['decision']
        now=decision['wall_after_s'];sim=decision['sim_ns'];policy=observer._policy
        def fresh(wall,limit):
            return wall is not None and 0<=nanoseconds(now)-nanoseconds(wall)<=int(limit*1e9)
        ready=False;reason=None;pair=None
        try:
            policy.check_joint(original['sample'],decision)
            if any(abs(value)>observer.port.stop_velocity for value in original['sample']['velocities']):
                raise ValueError('HEAD_MONITOR_PREARM_INPUTS_NOT_QUIET')
            if (not fresh(watchdog,policy.watchdog_reaction_limit_s)
                    or not fresh(executor,policy.watchdog_reaction_limit_s)
                    or primary is None
                    or any(not fresh(primary[key],policy.watchdog_reaction_limit_s)
                           for key in ('wall_s','executor_wall_s'))):
                raise ValueError('HEAD_MONITOR_PREARM_INPUTS_PROGRESS_STALE')
            inference_deadline=primary['inference_deadline_wall_s']
            if inference_deadline is not None and now>=inference_deadline:
                raise ValueError('HEAD_MONITOR_PREARM_INPUTS_INFERENCE_EXPIRED')
            if (clock is None or not clock['valid'] or clock['source_ns']>sim
                    or not fresh(clock['wall_s'],policy.clock_interarrival_deadline_s)):
                raise ValueError('HEAD_MONITOR_PREARM_INPUTS_CLOCK_STALE')
            for source,image in images.items():
                info=infos.get(source)
                if (info is not None and image['valid'] and info['valid']
                        and fresh(image['wall_s'],observer.camera_age)
                        and fresh(info['wall_s'],observer.camera_age)
                        and 0<=sim-source<=int(policy.camera_max_source_age_s*1e9)):
                    pair=dict(image=image,info=info);break
            if pair is None:raise ValueError('HEAD_MONITOR_PREARM_INPUTS_CAMERA_PENDING')
            ready=not observer.failed
        except (KeyError,TypeError,ValueError) as error:reason=str(error)
        # The immutable JSON wire snapshot preserves every original value;
        # in-memory joint tuples are not types accepted by the strict codec.
        snapshot=json.loads(json.dumps(dict(decision=decision,joint=original['sample'],camera_pair=pair,
            clock=clock,primary=primary,executor_wall_s=executor),allow_nan=False))
        ack=dict(stage='POLICY_READY',inputs_ready=ready,policy_sha256=self.epoch.policy_hash,
            ack_wall_s=observer.monotonic(),watchdog_wall_s=watchdog,motion_authority=False,
            original_snapshot=snapshot,pending_reason=reason)
        self._emit('PREARM_INPUTS',ack=ack)
        return ack

    def prearm_ready(self,record):
        """Check current own inputs before main ARM; grant no motion authority."""
        watchdog_wall=self._watchdog_wall
        now=time.monotonic() if self._observer is None else self._observer.monotonic()
        fault_wall=now
        try:
            if (type(record) is not dict or set(record)!={'policy_sha256'}
                    or not self._configured or self._finished or self._policy is None
                    or self.epoch.stage!='POLICY_READY' or self.revoked
                    or record['policy_sha256']!=self.epoch.policy_hash):
                raise PermissionError('HEAD_MONITOR_PREARM_STAGE_INVALID')
            if watchdog_wall is None:
                raise PermissionError('HEAD_MONITOR_PREARM_WATCHDOG_STALE')
            gap=nanoseconds(now)-nanoseconds(watchdog_wall)
            limit=int(self._observer._policy.watchdog_reaction_limit_s*1e9)
            if gap>limit:
                fault_wall=(nanoseconds(watchdog_wall)+limit)*1e-9
            if not 0<=gap<=limit:
                raise PermissionError('HEAD_MONITOR_PREARM_WATCHDOG_STALE')
            # This RPC cannot manufacture an independent watchdog tick. Once
            # active, the owned2ms worker keeps checking while main ARM runs.
            self._observer.activate(watchdog=False)
            feedback=self._observer.port.feedback_snapshot()
            if (self.revoked or self._observer.failed
                    or any(abs(value)>self._observer.port.stop_velocity for value in feedback['velocities'])):
                raise PermissionError('HEAD_MONITOR_PREARM_CURRENT_INPUTS_REFUSED')
            self._prearm_guarded=True
            ack=dict(stage='POLICY_READY',state='POLICY_READY',current_inputs_guarded=True,
                policy_sha256=self.epoch.policy_hash,ack_wall_s=self._observer.monotonic(),
                watchdog_wall_s=watchdog_wall,motion_authority=False)
            self._emit('PREARM_READY',ack=ack)
            return ack
        except Exception as error:
            self.fault('HEAD_MONITOR_PREARM_REFUSED',fault_wall)
            raise PermissionError('HEAD_MONITOR_PREARM_REFUSED') from error

    def armed_ready(self,record):
        if (type(record) is not dict or set(record)!={'main','primary_fault'}
                or self.epoch.stage!='POLICY_READY' or self.revoked or not self._prearm_guarded):
            raise PermissionError('HEAD_MONITOR_READY_STAGE_INVALID')
        identities=[]
        for key in ('main','primary_fault'):
            value=record[key]
            required={'identity','native_owner','provision_sha256'}
            if (type(value) is not dict or set(value)!=required
                    or value['native_owner']!=self._revoker.native_owner
                    or value['provision_sha256']!=self._provisions[key]['sha256']):
                raise PermissionError('HEAD_MONITOR_PRIMARY_IDENTITY_REPORT_INVALID')
            identities.append(value['identity'])
        if identities[0]!=identities[1]:raise PermissionError('HEAD_MONITOR_PRIMARY_IDENTITY_MISMATCH')
        actual=self._revoker.identity()
        monitor_identity={key:actual[key] for key in ('generation','incarnation','boot')}
        ack=self.epoch.armed_ready(identities[0],monitor_identity)
        self._observer.activate(watchdog=False)
        ack=dict(ack,stage='ARMED_READY',policy_sha256=self.epoch.policy_hash,
                 provisions=self._provisions,dependencies=self._dependencies,motion_authority=False)
        self._emit('ARMED_READY',ack=ack,monitor_identity_receipt=actual)
        return ack

    def register(self,record):
        if type(record) is not dict or set(record)!={'record','goal_cdr_base64'}:
            raise ValueError('HEAD_MONITOR_REGISTER_INVALID')
        if self.revoked:raise PermissionError('HEAD_MONITOR_RUNTIME_REVOKED')
        payload=base64.b64decode(record['goal_cdr_base64'],validate=True)
        owned=validate_goal_inventory(record['record'],payload,
            deadline=min(time.monotonic()+.010,record['record']['deadline_ns']*1e-9))
        self._observer.poll(watchdog=False)
        if self.revoked or self._observer.failed:raise PermissionError('HEAD_MONITOR_RUNTIME_REVOKED')
        ack=self.epoch.register(owned)
        self._observer.inventory(owned['goal_uuid'])
        self._emit('INVENTORY_ACK',inventory=owned,ack=ack,wall_s=time.monotonic())
        return dict(ack,stage='ARMED_READY',motion_authority=False)

    def dispatch(self,record):
        if type(record) is not dict or set(record)!={'goal_uuid','inventory_sha256'}:
            raise ValueError('HEAD_MONITOR_DISPATCH_INVALID')
        self._observer.poll(watchdog=False)
        if self.revoked or self._observer.failed:raise PermissionError('HEAD_MONITOR_RUNTIME_REVOKED')
        self.epoch.require_dispatch(record['goal_uuid'],record['inventory_sha256'])
        self._emit('DISPATCH_ACK',**record,wall_s=time.monotonic())
        return dict(stage='ARMED_READY',epoch=self.epoch.epoch,goal_uuid=record['goal_uuid'],
                    inventory_sha256=record['inventory_sha256'],motion_authority=False)

    def heartbeat(self,record):
        if not self._configured or self.revoked:raise PermissionError('HEAD_MONITOR_RUNTIME_REVOKED')
        self._observer.heartbeat(record)
        now=time.monotonic()
        return dict(stage=self.epoch.stage,epoch=self.epoch.epoch,watchdog_wall_s=self._watchdog_wall,
            executor_wall_s=self._observer._executor_wall,ack_wall_s=now,motion_authority=False)

    def _watchdog(self):
        next_poll=time.monotonic()
        while not self._shutdown.is_set():
            now=time.monotonic();self._watchdog_wall=now
            try:
                if _peer(self.primary['pid'])!=self.primary:
                    self.fault('HEAD_MONITOR_PRIMARY_LOST',now)
                self._observer.poll()
            except BaseException:self.fault('HEAD_MONITOR_WATCHDOG_FAILED',now)
            next_poll+=.002
            self._shutdown.wait(max(0.,next_poll-time.monotonic()))

    def fault(self,reason,wall):
        # No state lock, I/O or logger precedes the local admission latch.
        if self._fault is None:self._fault=dict(reason=reason,fault_wall_s=wall)
        elif wall<self._fault['fault_wall_s']:self._fault=dict(reason=reason,fault_wall_s=wall)
        self._fault_event.set()
        if self._observer is not None:
            self._observer.failed=True;self._observer.port._head_policy_binding_failed=True
        self.epoch.revoke(reason,fault_wall_s=wall)
        # Wake the independent native closer before touching the observer's
        # short stop-state lock; later reports may reveal an earlier origin.
        if self._observer is not None and self._observer._stop_started:
            self._observer.begin_stop(fault_wall_s=self._fault['fault_wall_s'])

    def notice_fault(self,record):
        if not self._configured or self._finished:
            raise PermissionError('HEAD_MONITOR_FAULT_NOTICE_STAGE_INVALID')
        now=time.monotonic()
        if (type(record) is not dict or set(record)!={'reason','fault_wall_s'}
                or type(record['reason']) is not str or not record['reason']
                or type(record['fault_wall_s']) not in (int,float)
                or not math.isfinite(record['fault_wall_s'])
                or not 0<=record['fault_wall_s']<=now):
            self.fault('HEAD_MONITOR_FAULT_NOTICE_INVALID',now)
            raise ValueError('HEAD_MONITOR_FAULT_NOTICE_INVALID')
        self.fault(record['reason'],record['fault_wall_s'])
        ack=dict(stage='REVOKED',fault=dict(self._fault),ack_wall_s=time.monotonic(),motion_authority=False)
        self._emit('PRIMARY_FAULT_NOTICE',reported_fault=dict(record),ack=ack)
        return ack

    def _close_native(self):
        self._fault_event.wait()
        if self._shutdown.is_set():return
        try:
            self._native_close=self._revoker.close_strict()
            self._emit('NATIVE_FAULT_CLOSE_ACK',fault=self._fault,receipt=self._native_close,
                transport_trace=getattr(self._revoker,'exchange_trace',None))
        except BaseException as error:
            self._native_close_error=type(error).__name__
            try:self._emit('NATIVE_FAULT_CLOSE_UNCONFIRMED',fault=self._fault,error=self._native_close_error,
                transport_trace=getattr(self._revoker,'exchange_trace',None))
            except Exception:pass
        finally:self._close_done.set()

    def _cancel_and_stop(self):
        self._fault_event.wait()
        if self._shutdown.is_set():return
        try:
            self._observer.begin_stop(fault_wall_s=self._fault['fault_wall_s'])
            self._observer.request_cancel_all()
            self._emit('CANCEL_INITIATED',fault=self._fault,wall_s=time.monotonic())
            while time.monotonic()-self._fault['fault_wall_s']<=self._observer.stop_latency:
                self._observer.begin_stop(fault_wall_s=self._fault['fault_wall_s'])
                self._observer.request_cancel_all();self._observer.request_results()
                stopped=self._observer.port.stopped()
                self._emit('STOP_PREDICATE',observation=self._observer.port.stop_predicate_observations[-1])
                if stopped:
                    self._emit('STOP_CONFIRMED',wall_s=time.monotonic());break
                self._shutdown.wait(.002)
            else:self._emit('STOP_UNCONFIRMED',wall_s=time.monotonic())
        except BaseException as error:
            try:self._emit('STOP_UNCONFIRMED',error=type(error).__name__,wall_s=time.monotonic())
            except Exception:pass
        finally:self._stop_done.set()

    def rejection(self,record):
        if type(record) is not dict or set(record)!={'goal_uuid','accepted','response_wall_s'} or record['accepted'] is not False:
            raise ValueError('HEAD_MONITOR_REJECTION_REPORT_INVALID')
        self._observer.primary_rejection(record['goal_uuid'])

    def close(self):
        """Owned CPU teardown and sealed raw stream, never a robot stop claim."""
        if self._finished:return dict(stage='RETIRED',motion_authority=False)
        if self._configure_thread is not None and self._configure_thread.is_alive():
            # Setup can still assign owned ROS resources. Stop and join it
            # before retiring those resources or publishing a receipt.
            self._shutdown.set();self._configure_thread.join(.2)
            if self._configure_thread.is_alive():
                raise PermissionError('HEAD_MONITOR_CONFIGURE_RETIRE_UNCONFIRMED')
        if self._configured and self.epoch.stage=='ARMED_READY' and not self.revoked:
            self.fault('HEAD_MONITOR_OWNED_SHUTDOWN',time.monotonic())
        if self.revoked and self._observer is not None:
            self._stop_done.wait(self._observer.stop_latency+.010)
            self._close_done.wait(.010)
        self._shutdown.set();self._fault_event.set()
        for thread in self._threads:thread.join(.2)
        if any(thread.is_alive() for thread in self._threads):
            raise PermissionError('HEAD_MONITOR_WORKER_RETIRE_UNCONFIRMED')
        if self._observer is not None:
            retired=self._observer.close(timeout_s=.010)
            if (type(retired) is not dict or set(retired)!={'result','cancel'}
                    or any(value.get('retired') is not True for value in retired.values())):
                raise PermissionError('HEAD_MONITOR_ACTION_IO_RETIRE_UNCONFIRMED')
        if self._executor is not None and self._executor.shutdown(timeout_sec=.2) is not True:
            raise PermissionError('HEAD_MONITOR_EXECUTOR_RETIRE_UNCONFIRMED')
        if self._spinner is not None:
            self._spinner.join(.2)
            if self._spinner.is_alive():raise PermissionError('HEAD_MONITOR_SPINNER_RETIRE_UNCONFIRMED')
        if self._node is not None:self._node.destroy_node()
        if self._context is not None and self._context.ok():self._context.shutdown()
        if self._journal_handle is not None:
            self._records.put_nowait(None);self._journal_thread.join(.5)
            if self._journal_thread.is_alive():raise PermissionError('HEAD_MONITOR_JOURNAL_RETIRE_UNCONFIRMED')
            self._journal_handle.close()
            result=dict(stage='RETIRED',motion_authority=False,epoch=self.epoch.epoch,
                journal_path=str(self._journal_path),journal_sha256=hashlib.sha256(_read(self._journal_path,128*1024*1024)).hexdigest(),
                records=self._journal_count,journal_error=self._journal_error,fault=self._fault,
                native_close=self._native_close,native_close_error=self._native_close_error)
            seal=self._journal_path.with_name(self._journal_path.name+'.seal.json')
            with seal.open('x') as handle:json.dump(result,handle,sort_keys=True);handle.write('\n');handle.flush();os.fsync(handle.fileno())
        else:result=dict(stage='RETIRED',motion_authority=False,fault=self._fault)
        self._finished=True
        return result
