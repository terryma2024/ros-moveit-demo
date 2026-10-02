"""Installed CUDA bootstrap with explicit calibration-only native/SDK diagnostics."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import secrets
import sys
import threading
import time
import uuid

from so101_demo.act.head_monitor import digest


def _reference(path):
    path=Path(path).resolve(strict=True)
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _owned_runtime_environment(peer):
    """Read only the two public runtime selectors from this exact owned process."""
    from so101_demo.adapters.act.head_monitor_runtime import _peer
    if _peer(peer['pid'])!=peer:raise PermissionError('HEAD_BOOTSTRAP_ENVIRONMENT_PEER_CHANGED')
    entries=Path('/proc/'+str(peer['pid'])+'/environ').read_bytes().split(b'\0')
    selected={name:None for name in ('ROS_DOMAIN_ID','GZ_PARTITION')}
    for entry in entries:
        key,separator,value=entry.partition(b'=')
        if separator and key in (b'ROS_DOMAIN_ID',b'GZ_PARTITION'):
            selected[key.decode('ascii')]=value.decode('utf-8')
    if _peer(peer['pid'])!=peer:raise PermissionError('HEAD_BOOTSTRAP_ENVIRONMENT_PEER_CHANGED')
    return dict(peer=dict(peer),values=selected,read_wall_s=time.monotonic(),source='original /proc/pid/environ')


def _write(path,record):
    with Path(path).open('x',encoding='ascii') as handle:
        json.dump(record,handle,sort_keys=True,allow_nan=False);handle.write('\n')
        handle.flush();os.fsync(handle.fileno())
    return _reference(path)


def _bind_native_diagnostic(primary,authority,result):
    # A later identity/RPC failure cannot erase an already acknowledged ARM.
    # Without a complete reply the physical outcome remains unknown, never zero.
    result['native_arm_count']=None
    try:return primary.arm(authority)
    finally:
        result['main_exchange_receipts']=list(authority.exchange_receipts)
        if 'neck' in authority._armed:result['native_arm_count']=1


def _record_refusal(result,error):
    result['status']='REFUSED'
    result['error']=dict(type=type(error).__name__,message=str(error))


def _require_monitor_closure(root,result,*,stop_velocity_rad_s):
    """Read the owned CPU seal after reap; primary stop cannot stand in for it."""
    from so101_demo.act.head_feedback import FeedbackPolicy,OrderedStopConfirmation,nanoseconds
    try:
        def require(condition):
            if not condition:raise ValueError('missing or contradictory CPU closure evidence')
        root=Path(root)
        reap=result['monitor_teardown']
        require(reap['shutdown_ack'] is True and reap['exit_code']==0)
        seal=json.loads((root/'monitor.jsonl.seal.json').read_text())
        require(seal['stage']=='RETIRED' and seal['epoch']==result['epoch']
            and seal['motion_authority'] is False and seal['journal_error'] is None
            and seal['journal_path']==str(root/'monitor.jsonl'))
        payload=(root/'monitor.jsonl').read_bytes()
        require(hashlib.sha256(payload).hexdigest()==seal['journal_sha256'])
        rows=[json.loads(line) for line in payload.splitlines()]
        require(len(rows)==seal['records'])
        close=seal['native_close'];primary=result['primary_teardown']
        require(seal['native_close_error'] is None and close['ack_validated'] is True
            and close['generation']==result['generation']
            and close['native_owner']==primary['native_close']['native_owner'])
        started=nanoseconds(close['request_wall_s']);ended=nanoseconds(close['ack_wall_s'])
        origin=min(nanoseconds(seal['fault']['fault_wall_s']),nanoseconds(primary['fault']['fault_wall_s']))
        require(0<=ended-started<=2_000_000 and 0<=ended-origin<=10_000_000)
        require(any(row['event']=='NATIVE_FAULT_CLOSE_ACK' and row['receipt']==close for row in rows))
        require(not any(row['event'] in ('NATIVE_FAULT_CLOSE_UNCONFIRMED','STOP_UNCONFIRMED') for row in rows))
        policy=FeedbackPolicy.parse(result['measured']['values'])
        originals={row['sample']['sequence']:row['sample'] for row in rows if row['event']=='JOINT_ORIGINAL'}
        inventory={row['inventory']['goal_uuid'] for row in rows if row['event']=='INVENTORY_ACK'}
        proven=False
        for row in rows:
            if row['event']!='STOP_PREDICATE':continue
            observed=row['observation']
            if observed['stopped'] is not True:continue
            epoch=observed['epoch'];samples=observed['confirming_samples'];states=observed['confirmation_inventory']
            require(epoch['generation']==result['generation'] and len(samples)==3 and set(states)==inventory)
            require(all(state['accepted'] is False or (state['accepted'] is True
                and state['terminal_status'] in (4,5,6)) for state in states.values()))
            proof=OrderedStopConfirmation(epoch)
            for sample in samples:
                original={key:value for key,value in sample.items() if key!='decision'}
                require(originals.get(sample['sequence'])==original)
                proof.observe(original,sample['decision'],policy,stop_velocity_rad_s)
            require(proof.count>=3 and proof.within_deadline(observed['decision']))
            require(0<=nanoseconds(observed['decision']['wall_after_s'])-origin
                <=math.floor(epoch['stop_latency_s']*1e9))
            proven=True
        require(proven and any(row['event']=='STOP_CONFIRMED' for row in rows))
        return dict(proven=True,seal=_reference(root/'monitor.jsonl.seal.json'),
            native_close=close,stop_proven=True)
    except (OSError,KeyError,TypeError,ValueError) as error:
        raise PermissionError('HEAD_BOOTSTRAP_MONITOR_CLOSURE_UNPROVEN') from error


def _bound_goal_settlement(samples,state,*,target_rad,position_tolerance_rad,
        velocity_tolerance_rad_s,source_floor_ns,dispatch_wall_s,terminal_wall_s):
    """Terminal success plus three advancing, original post-terminal samples."""
    response=state.get('result')
    if (state.get('accepted') is not True or getattr(response,'status',None)!=4
            or getattr(getattr(response,'result',None),'error_code',None)!=0):return None
    quiet=[];previous=None
    for original in samples:
        row=dict(original)
        if (any(type(row[key]) is not int or row[key]<=0 for key in ('sequence','source_ns'))
                or any(type(value) not in (int,float) or not math.isfinite(value)
                    for value in (row['wall_s'],row['positions'][0],row['velocities'][0]))):return None
        if (row.get('valid') is not True or row['source_ns']<=source_floor_ns
                or row['wall_s']<=max(dispatch_wall_s,terminal_wall_s)):
            quiet=[];previous=None;continue
        if previous is not None and any(row[key]<=previous[key]
                for key in ('sequence','source_ns','wall_s')):return None
        previous=row
        if (abs(row['positions'][0]-target_rad)>position_tolerance_rad
                or abs(row['velocities'][0])>velocity_tolerance_rad_s):
            quiet=[];continue
        quiet.append(row)
        if len(quiet)==3:return quiet
    return None


def _prepare_bound_goal_dispatch():
    # Resolve cold trajectory modules and full codecs before primary activation,
    # while the one SDK remains send-disabled and native admission is closed.
    started=time.monotonic()
    from so101_demo.act import head_search_calibration_admission_document,head_search_calibration_run
    from so101_demo.adapters.act import head_inventory_dispatch,ros_neck,head_live_exposure,head_owned_search
    from so101_demo.adapters.act.head_monitor_goal_binding import warm_goal_binding
    return dict(goal_codec=warm_goal_binding(),elapsed_s=time.monotonic()-started,
        modules={module.__name__:module.__file__ for module in (
            head_search_calibration_admission_document,head_search_calibration_run,head_inventory_dispatch,ros_neck,head_live_exposure,head_owned_search)})


def _prepare_bound_goal_plan(*,port,production,geometry,result):
    if (type(result.get('native_arm_count')) is not int or result['native_arm_count']!=0
            or type(result.get('goal_send_count')) is not int or result['goal_send_count']!=0):
        raise PermissionError('HEAD_BOOTSTRAP_TRAJECTORY_AFTER_ARM_OR_SEND')
    from so101_demo.act.head_search_calibration_admission_document import derive_measurement_plan
    from so101_demo.act.head_search_calibration_run import check_trajectory_contract
    initial=port.feedback_snapshot()
    config=derive_measurement_plan(production_config=production,geometry_document=geometry,
        generation=result['epoch'],search_start_rad=initial['positions'][0])
    config.update(session_id=result['session_id'],attempt_id=result['epoch'])
    trajectory=check_trajectory_contract(production_search_config=config)
    return dict(initial=initial,config=config,trajectory_contract=trajectory,
        prepared_wall_s=time.monotonic(),native_arm_count=result['native_arm_count'],
        sdk_send_count=result['goal_send_count'])


def _bind_search_transport(*,node,port,primary,authority,monitor,production,result,emit,trajectory):
    from so101_demo.act.head_search_restarts import _neck_goal_duration
    from so101_demo.adapters.act.head_inventory_dispatch import HeadInventoryDispatcher
    from so101_demo.adapters.act.ros_neck import RosNeckSearchPort
    low,high=trajectory['safe_interval_rad'];values=production['values']
    dispatcher=HeadInventoryDispatcher(port,authority,monitor,epoch=result['epoch'],
        generation=result['generation'],session_id=result['session_id'],
        controller_identity=result['native_identity'],guard=primary.dispatch_guard,
        own_inventory=primary.own_inventory,fault_callback=primary.fault,emit=emit)
    neck=RosNeckSearchPort(node,session_id=result['session_id'],attempt_id=result['epoch'],
        goal_duration_s=_neck_goal_duration(values),submit_lead_s=values['submit_lead_s'],
        stop_timeout_s=values['stop_latency_s'],stop_velocity_rad_s=values['stop_velocity_rad_s'],
        max_age_s=values['max_age_s'],command_guard=lambda current,end:low<=current<=high and low<=end<=high,
        controller_port=dispatcher,feedback_policy=port.feedback_policy)
    return dispatcher,neck


def _run_owned_search_diagnostic(*,driver,dispatcher,result,emit):
    evidence=result['search_controller_diagnostic']
    next_tick=time.monotonic()
    try:
        while True:
            terminal=driver.tick()
            if terminal is not None:
                evidence['terminal']=terminal
                if terminal['status']!='TARGET_LOCKED':
                    raise PermissionError('HEAD_SEARCH_DIAGNOSTIC_'+terminal['status'])
                return evidence
            next_tick+=.005;delay=next_tick-time.monotonic()
            if delay<0:
                emit('SEARCH_CONTROL_TICK_LATE',scheduled_wall_s=next_tick,observed_wall_s=time.monotonic())
                next_tick=time.monotonic();delay=0.
            time.sleep(delay)
    finally:
        evidence.update(terminal=driver.result,commands=driver.commands,
            observations=driver.observations,inventory=dispatcher.inventory,
            main_exchange_receipts=list(dispatcher.authority.exchange_receipts),
            dispatch_traces=dispatcher.dispatch_traces,
            finished_wall_s=time.monotonic())


def _bind_live_exposures(*,capture,port,buffer,detector,primary,monitor,camera_skew_s,emit):
    from so101_demo.adapters.act.head_live_exposure import HeadLiveExposures
    detector.reset()
    reader=HeadLiveExposures(port=port,buffer=buffer,detector=detector,primary=primary,
        monitor=monitor,camera_skew_s=camera_skew_s,emit=emit)
    capture.bind_live_sink(reader.observe)
    return reader


def _start_owned_detector(*,factory,fault_callback):
    from so101_demo.adapters.act.head_inference_owner import HeadInferenceOwner
    return HeadInferenceOwner(factory=factory,fault_callback=fault_callback)


def _run_bound_goal_diagnostic(*,node,port,primary,authority,monitor,production,geometry,result,emit,live=None,
                             owned_inference=False,prepared=None):
    """One real sealed-domain endpoint goal, through the existing bound SDK."""
    # All actual resources and the measured policy already exist before this
    # precondition; the formal entry must eventually share this composition.
    prepared=prepared or _prepare_bound_goal_plan(port=port,production=production,geometry=geometry,result=result)
    initial=prepared['initial'];trajectory=prepared['trajectory_contract']
    domain=trajectory['required_search_domain_rad']
    target=max(domain,key=lambda value:abs(value-initial['positions'][0]))
    if abs(target-initial['positions'][0])<=production['motion']['goal_tolerance_rad']:
        raise PermissionError('HEAD_DIAGNOSTIC_NONMOVING_ENDPOINT')
    values=production['values']
    dispatcher,neck=_bind_search_transport(node=node,port=port,primary=primary,authority=authority,
        monitor=monitor,production=production,result=result,emit=emit,trajectory=trajectory)
    evidence=dict(diagnostic_only=True,trajectory_contract=trajectory,initial=initial,target_rad=target,
        target_rule='farthest endpoint of the sealed required search domain; diagnostic motion, not a search terminal',
        duration_s=neck.duration,position_tolerance_rad=production['motion']['goal_tolerance_rad'],
        velocity_tolerance_rad_s=min(production['motion']['settle_velocity_rad_s'],values['stop_velocity_rad_s']),
        dispatch_wall_s=time.monotonic(),settled=False)
    result['bound_goal_diagnostic']=evidence
    emit('BOUND_GOAL_DECLARATION',**evidence)
    try:
        gid=neck.command_neck(target,session_id=result['session_id'],attempt_id=result['epoch'],
            observation_time_s=initial['source_ns']*1e-9)
        evidence['goal_uuid']=gid;evidence['inventory']=dispatcher.inventory
        evidence['main_exchange_receipts']=list(authority.exchange_receipts)
        deadline=evidence['dispatch_wall_s']+values['search_timeout_s']
        next_tick=time.monotonic()
        if owned_inference:evidence['control_period_s']=.005
        terminal_wall=None;floor=None
        while True:
            if live is not None:live.infer()
            primary.dispatch_guard();current=port.feedback_snapshot()
            if owned_inference:
                emit('BOUND_GOAL_CONTROL_DECISION',goal_uuid=gid,decision=current['decision'],
                    original_joint={key:value for key,value in current.items() if key!='decision'},
                    controller_thread_native_id=threading.get_native_id())
            with port._lock:
                state=dict(port._goals[gid])
                samples=tuple(dict(row) for row in port._head_samples
                    if terminal_wall is not None and row['wall_s']>terminal_wall)
            response=state.get('result')
            evidence['accepted']=state['accepted'];evidence['terminal_status']=getattr(response,'status',None)
            evidence['result_error_code']=getattr(getattr(response,'result',None),'error_code',None)
            if state['accepted'] is False:raise PermissionError('HEAD_DIAGNOSTIC_GOAL_REJECTED')
            if response is not None:
                if response.status!=4 or response.result.error_code!=0:
                    raise PermissionError('HEAD_DIAGNOSTIC_GOAL_RESULT_FAILED')
                if terminal_wall is None:
                    terminal_wall=time.monotonic();floor=current['decision']['sim_ns']
                    evidence['terminal_observed_wall_s']=terminal_wall;evidence['terminal_source_floor_ns']=floor
                proof=_bound_goal_settlement(samples,state,target_rad=target,
                    position_tolerance_rad=evidence['position_tolerance_rad'],
                    velocity_tolerance_rad_s=evidence['velocity_tolerance_rad_s'],source_floor_ns=floor,
                    dispatch_wall_s=evidence['dispatch_wall_s'],terminal_wall_s=terminal_wall)
                if proof is not None:
                    if live is not None and not any(any(abs(value)>values['stop_velocity_rad_s']
                            for value in row['causal_joint']['velocities']) for row in live.results):
                        raise PermissionError('HEAD_DIAGNOSTIC_MOVING_CUDA_EXPOSURE_MISSING')
                    evidence['confirming_samples']=proof;evidence['settled_source_floor_ns']=proof[-1]['source_ns']
                    evidence['settled']=True;evidence['settled_wall_s']=time.monotonic()
                    emit('BOUND_GOAL_SETTLED',**evidence);return evidence
            if time.monotonic()>=deadline:raise TimeoutError('HEAD_DIAGNOSTIC_GOAL_SETTLEMENT_TIMEOUT')
            if owned_inference:
                next_tick+=.005;delay=next_tick-time.monotonic()
                if delay<0:
                    emit('BOUND_GOAL_CONTROL_TICK_LATE',scheduled_wall_s=next_tick,
                        observed_wall_s=time.monotonic())
                    next_tick=time.monotonic();delay=0.
                time.sleep(delay)
            else:time.sleep(.001)
    except Exception:
        primary.fault('HEAD_BOUND_GOAL_DIAGNOSTIC_FAILED')
        raise
    finally:
        evidence['inventory']=dispatcher.inventory
        evidence['main_exchange_receipts']=list(authority.exchange_receipts)


class _ImageWriter:
    """Bounded owned worker: callbacks never write pixels to disk."""
    def __init__(self,root):
        self.root=root;self.records=queue.Queue(maxsize=64);self.error=None;self.count=0
        self.thread=threading.Thread(target=self._run,name='head-bootstrap-pixels');self.thread.start()

    def emit(self,event,*,record,payload):
        if self.error is not None:raise RuntimeError('HEAD_BOOTSTRAP_PIXEL_WRITER_FAILED')
        self.records.put_nowait((dict(record),payload))

    def _run(self):
        try:
            with (self.root/'images.jsonl').open('x',encoding='ascii') as journal:
                while True:
                    item=self.records.get()
                    try:
                        if item is None:break
                        record,data=item;name=f'image-{self.count:06d}-{record["source_ns"]}.rgb'
                        with (self.root/name).open('xb') as handle:
                            handle.write(data);handle.flush();os.fsync(handle.fileno())
                        journal.write(json.dumps(dict(record,payload_file=name),sort_keys=True)+'\n')
                        self.count+=1
                    finally:self.records.task_done()
                journal.flush();os.fsync(journal.fileno())
        except BaseException as error:self.error=error

    def close(self):
        if self.thread.is_alive():self.records.put(None,timeout=2.)
        self.thread.join(timeout=10.)
        if self.thread.is_alive() or self.error is not None:
            raise RuntimeError('HEAD_BOOTSTRAP_PIXEL_SEAL_FAILED')
        return dict(count=self.count,journal=_reference(self.root/'images.jsonl'))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('run-root','reservation-root','runtime-manifest','production-config','geometry-seal',
                 'frozen-candidate','urdf','scene','plugin-config','controller-config'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--device',choices=['cuda'],default='cuda')
    parser.add_argument('--native-binding-diagnostic',action='store_true',
        help='after the full stopped measurement, bind all three native identities and prove owned fault stop; SDK sends remain forbidden')
    parser.add_argument('--bound-goal-diagnostic',action='store_true',
        help='after stopped measurement and three-party native binding, dispatch one sealed-domain endpoint goal; diagnostic only')
    parser.add_argument('--moving-exposure-diagnostic',action='store_true',
        help='during the one bound endpoint goal, admit original frames on the CPU monitor and infer on the same C2a; diagnostic only')
    parser.add_argument('--owned-inference-diagnostic',action='store_true',
        help='build and infer on one owned thread while main advances original5ms control decisions; requires moving exposure diagnostic')
    parser.add_argument('--search-controller-diagnostic',action='store_true',
        help='drive the real HeadSearchController on once-owned completed frames and SDK transport; calibration diagnostic only')
    args=parser.parse_args(argv)
    if args.moving_exposure_diagnostic and not args.bound_goal_diagnostic:
        parser.error('--moving-exposure-diagnostic requires --bound-goal-diagnostic')
    if args.owned_inference_diagnostic and not args.moving_exposure_diagnostic:
        parser.error('--owned-inference-diagnostic requires --moving-exposure-diagnostic')
    if args.search_controller_diagnostic and not args.owned_inference_diagnostic:
        parser.error('--search-controller-diagnostic requires --owned-inference-diagnostic')
    # Import CPU resources first. No torch/model import precedes monitor exec.
    from so101_demo.act.head_search_restarts import (
        RestartStack,TimedHeadDetector,_operating_point,publish_provisions,stack_environment,
        probe_owners,_require_empty,measure_gpu_compute_apps,classify_nodes)
    from so101_demo.adapters.act.controller_reservation_provision import (
        _process_start_ticks,write_head_primary_fault_provision)
    from so101_demo.adapters.act.head_monitor_process import start_monitor
    from so101_demo.adapters.act.head_stopped_capture import StoppedHeadCapture,measure_stopped_workload
    from so101_demo.adapters.act.head_original_journal import HeadOriginalJournal
    from so101_demo.adapters.act.head_original_router import HeadOriginalRouter
    from so101_demo.adapters.act.head_primary_supervisor import HeadPrimarySupervisor
    from so101_demo.adapters.act.head_revocation import NativeRevocationClient
    from so101_demo.adapters.act.head_reservation_authority import HeadReservationAuthority
    from so101_demo.adapters.act.head_monitor_runtime import _provision,_peer
    from so101_demo.adapters.act.ros_execution import RosControllerPort
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from rclpy.action import ActionClient
    from control_msgs.action import FollowJointTrajectory
    from tf2_ros import Buffer,TransformListener
    root=args.run_root
    if not root.is_absolute() or root.exists():raise FileExistsError('HEAD_BOOTSTRAP_FRESH_ROOT_REQUIRED')
    production=json.loads(args.production_config.read_text());values=production['values']
    dependencies={name:_reference(path) for name,path in dict(weights=production['weight_path'],
        geometry=args.geometry_seal,candidate=args.frozen_candidate,runtime_manifest=args.runtime_manifest).items()}
    if dependencies['weights']['sha256']!=production['weight_sha256']:
        raise PermissionError('HEAD_BOOTSTRAP_WEIGHTS_MISMATCH')
    candidate=json.loads(args.frozen_candidate.read_text())
    if candidate['weight_sha256']!=dependencies['weights']['sha256']:
        raise PermissionError('HEAD_BOOTSTRAP_CANDIDATE_MISMATCH')
    before=probe_owners(excluded_pids=(os.getpid(),),excluded_nodes=())
    before['gpu_compute_apps']=measure_gpu_compute_apps()
    _require_empty(before,anchor='stopped_bootstrap',stage='pre-start')
    root.mkdir();session='hs_boot_'+uuid.uuid4().hex[:16];epoch=uuid.uuid4().hex
    generation=int.from_bytes(secrets.token_bytes(7),'big') or 1
    result=dict(purpose='calibration',motion_authority=False,qualification=False,diagnostic_only=True,
        status='REFUSED',epoch=epoch,generation=generation,session_id=session,dependencies=dependencies,
        before=before,seed_config=_reference(args.production_config),entry=_reference(__file__),
        runtime_environment={'root':_owned_runtime_environment(_peer(os.getpid()))},
        python=sys.executable,started_wall_s=time.monotonic(),native_arm_count=0,goal_send_count=0)
    _write(root/'attempt-declaration.json',dict(result,window_rule='stable10s then first future boundary at latest original camera receipt + max(stable p50 receipt gap / 2, stable linear p99 original CUDA receipt-to-completion wall duration + stable linear p99 original Joint receipt gap); phase must remain shorter than one receipt period; at most two fixed 100ms source periods waiting before the single declaration; end=start+20s; no retry',
        startup_retention='bounded diagnostic metadata, no pixels before CUDA warmup; all stable/window originals and RGB retained',
        controlled_inputs={name:_reference(getattr(args,name)) for name in ('urdf','scene','plugin_config','controller_config')}))
    monitor=stack=context=node=executor=spinner=port=writer=capture=client=listener=original_writer=original_router=None
    primary=primary_writer=live=inference_owner=None
    try:
        provisions=publish_provisions(args.reservation_root,session)
        directory=provisions.directory
        if len(os.fsencode(directory/'neck-primary-revoke.sock'))>107:
            raise ValueError('HEAD_BOOTSTRAP_RESERVATION_PATH_TOO_LONG')
        monitor_directory=directory/'m';monitor_directory.mkdir(mode=0o700)
        monitor=start_monitor(python_executable=sys.executable,ipc_directory=monitor_directory,
            log_path=root/'monitor-process.log',epoch=epoch,generation=generation,session_id=session,
            startup_timeout_s=5.)
        result['monitor_exec']=monitor.receipt
        result['runtime_environment']['monitor']=_owned_runtime_environment(monitor.identity)
        environment=stack_environment(directory,session)
        environment['SO101_HEAD_SEARCH_V2_MONITOR_REQUIRED']='1';environment['MUJOCO_GL']='egl'
        stack=RestartStack(urdf_path=args.urdf,scene_path=args.scene,plugin_config_path=args.plugin_config,
            controller_config_path=args.controller_config,workspace=root/'stack',session_id=session,
            environment=environment,logger=lambda message:print(message,flush=True))
        stack.workspace.mkdir();stack.start()
        result['runtime_environment']['stack']=[_owned_runtime_environment(_peer(process.pid))
            for process in stack.processes]
        native=dict(uid=os.geteuid(),pid=stack.processes[0].pid,
                    start_ticks=_process_start_ticks(stack.processes[0].pid))
        write_head_primary_fault_provision(directory/'neck-primary-revoke.provision',session_id=session,
            native_owner=native,socket_path=directory/'neck-primary-revoke.sock')
        monitor.request_runtime(dict(operation='CONFIGURE',configuration=dict(purpose='calibration',
            native_owner=native,reservation_directory=str(directory),journal_path=str(root/'monitor.jsonl'),
            dependencies=dependencies,observer=dict(stop_velocity_rad_s=values['stop_velocity_rad_s'],
                stop_latency_s=values['stop_latency_s'],camera_max_age_s=values['max_age_s'],
                camera_frame_id=production['camera']['frame_id']))))
        result['monitor_configured']=monitor.await_runtime(phase='configuration',timeout_s=10.)
        context=Context();rclpy.init(context=context)
        node=Node('head_bootstrap_'+epoch,context=context,parameter_overrides=[Parameter('use_sim_time',value=True)])
        client=ActionClient(node,FollowJointTrajectory,'/neck_controller/follow_joint_trajectory')
        def forbid_send(*positional,**named):
            result['goal_send_count']+=1
            raise PermissionError('HEAD_BOOTSTRAP_MOTION_FORBIDDEN')
        # The default/native-only diagnostic never sends. Only the explicit
        # bound-goal branch below temporarily adopts this same SDK after ARM.
        sdk_send=client.send_goal_async
        client.send_goal_async=forbid_send
        port=RosControllerPort(node,client,('neck_yaw_joint',),stop_velocity_rad_s=values['stop_velocity_rad_s'],
                               max_age_s=values['max_age_s'],head_bootstrap=True)
        writer=_ImageWriter(root)
        capture=StoppedHeadCapture(node,port,frame_id=production['camera']['frame_id'],strict=False,emit=writer.emit)
        result['clock_binding']=dict(owner='rclpy.TimeSource',
            depth=node._time_source._clock_sub.qos_profile.depth,
            reliability=node._time_source._clock_sub.qos_profile.reliability.name,
            subscription_count=sum(sub.topic_name=='/clock' for sub in node.subscriptions))
        def original_failure(reason):
            # An owned writer failure invalidates this attempt before any
            # diagnostic formatting, policy binding or future ARM decision.
            capture._failure=reason;port._head_policy_binding_failed=True
            if port._head_fault_callback is not None:port._head_fault_callback(reason)
        original_writer=HeadOriginalJournal(root/'primary-originals.jsonl',fault_callback=original_failure)
        original_router=HeadOriginalRouter(port,original_writer)
        port.bind_head_original_sink(original_router)
        capture.bind_original_sink(original_router)
        buffer=Buffer();listener=TransformListener(buffer,node)
        if args.bound_goal_diagnostic:
            result['primary_goal_dispatch_preparation']=_prepare_bound_goal_dispatch()
            _write(root/'goal-dispatch-preparation.json',result['primary_goal_dispatch_preparation'])
        executor=SingleThreadedExecutor(context=context);executor.add_node(node)
        spinner=threading.Thread(target=executor.spin,name='head-bootstrap-ros');spinner.start()
        deadline=time.monotonic()+90.
        own_nodes=('/'+node.get_name(),'/'+result['monitor_configured']['node_name'])
        while True:
            observation=probe_owners(excluded_pids=(os.getpid(),),excluded_nodes=own_nodes)
            graph=classify_nodes(observation['nodes'])
            if graph['foreign']:raise PermissionError('HEAD_BOOTSTRAP_FOREIGN_NODE')
            if not graph['missing'] and not graph['transient'] and all(p.poll() is not None for p in stack.processes[2:]):break
            if time.monotonic()>=deadline:raise TimeoutError('HEAD_BOOTSTRAP_STACK_DISCOVERY_FAILED')
            time.sleep(.25)
        result['graph']=observation
        result['ros_endpoints']={topic:[dict(node_name=e.node_name,node_namespace=e.node_namespace,
            reliability=str(e.qos_profile.reliability),depth=e.qos_profile.depth)
            for e in node.get_publishers_info_by_topic(topic)]
            for topic in ('/joint_states','/head_camera/color','/head_camera/camera_info','/clock')}
        if any(not rows for rows in result['ros_endpoints'].values()):
            raise PermissionError('HEAD_BOOTSTRAP_PUBLISHER_MISSING')
        # Discovery can outlive the first sensor callbacks. A presence
        # receipt from before discovery cannot hide a subsequent monitor fault.
        result['monitor_pre_cuda_health']=monitor.request_runtime({'operation':'CONFIGURATION'})
        result['cuda_load_started_wall_s']=time.monotonic()
        import torch
        import ultralytics
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        result['detector_runtime']=dict(torch_version=torch.__version__,ultralytics_version=ultralytics.__version__,
            cuda_version=torch.version.cuda,torch_threads=torch.get_num_threads(),
            torch_interop_threads=torch.get_num_interop_threads(),allow_cpu_fallback=False,requested_device=args.device)
        inference_owner=_start_owned_detector(factory=lambda:TimedHeadDetector.build(
            weights_path=dependencies['weights']['path'],model_id=production['runtime_id'],
            device=args.device,values=values,operating_point=_operating_point(args.frozen_candidate)),
            fault_callback=original_failure)
        built=inference_owner.configuration(timeout_s=90.)
        result['inference_owner']=built['inference_owner']
        if built['runtime_device']!=args.device:raise PermissionError('HEAD_BOOTSTRAP_CUDA_REQUIRED')
        result['cuda_loaded_wall_s']=time.monotonic();result['detector_count']=1
        result['cuda_compute_apps']=measure_gpu_compute_apps()
        if not any(int(row['pid'])==os.getpid() for row in result['cuda_compute_apps']):
            raise PermissionError('HEAD_BOOTSTRAP_CUDA_PID_UNPROVEN')
        measurement_reference=None
        def progress(**fields):
            nonlocal measurement_reference
            if fields['stage']=='collected':
                raw=dict(epoch=epoch,generation=generation,session_id=session,dependencies=dependencies,window=fields['window'])
                raw['sha256']=digest(raw);measurement_reference=_write(root/'measurement.json',raw)
            else:
                print(json.dumps(fields),flush=True)
                _write(root/(fields['stage']+'-declaration.json'),fields)
        window,measured=measure_stopped_workload(capture,built['runtime'],buffer,session_id=session,
            stop_velocity_rad_s=values['stop_velocity_rad_s'],stop_latency_s=values['stop_latency_s'],progress=progress)
        result['measured']=measured
        policy=dict(purpose='calibration',motion_authority=False,epoch=epoch,generation=generation,
            session_id=session,dependencies=dependencies,measurement=measurement_reference,
            values=measured['values'],camera_seed_values=measured['camera_seed_values'])
        policy['sha256']=digest(policy);reference=_write(root/'provisional-policy.json',policy)
        monitor.request_runtime(dict(operation='POLICY',policy=reference))
        result['policy_ack']=monitor.await_runtime(phase='policy',timeout_s=10.)
        capture.check()
        port.bind_head_policy(measured['values'])
        result['status']='STOPPED_BOOTSTRAP_MEASURED'
        if args.native_binding_diagnostic or args.bound_goal_diagnostic:
            primary_writer=HeadOriginalJournal(root/'primary-events.jsonl',fault_callback=original_failure)
            own=_peer(os.getpid())
            provision,fault_cap=_provision(directory/'neck-primary-revoke.provision',authority='primary',
                actor=own,native_owner=native,session_id=session)
            if provision!=result['monitor_configured']['provisions']['primary_fault']:
                raise PermissionError('HEAD_BOOTSTRAP_PRIMARY_PROVISION_CHANGED')
            revoker=NativeRevocationClient(directory/'neck-primary-revoke.sock',capability=fault_cap,
                native_owner=native,generation=generation,timeout_s=.002)
            result['primary_native_transport']=dict(revoker.transport_origin)
            primary=HeadPrimarySupervisor(node=node,port=port,router=original_router,monitor=monitor,
                revoker=revoker,epoch=epoch,generation=generation,session_id=session,policy_reference=reference,
                policy_ack=result['policy_ack'],configuration_ack=result['monitor_configured'],
                stop_latency_s=values['stop_latency_s'],camera_max_age_s=measured['camera_seed_values']['max_age_s'],
                camera_frame_id=production['camera']['frame_id'],
                emit=lambda event,**fields:primary_writer('EVENT',dict(event=event,diagnostic_only=True,**fields)))
            if args.moving_exposure_diagnostic:
                def bind_live(detector):
                    return _bind_live_exposures(capture=capture,port=port,buffer=buffer,detector=detector,
                        primary=primary,monitor=monitor,camera_skew_s=measured['camera_seed_values']['max_skew_s'],
                        emit=lambda event,**fields:primary_writer('EVENT',dict(event=event,**fields)))
                if args.owned_inference_diagnostic:
                    result['live_binding']=inference_owner.bind_live(bind_live,timeout_s=1.)
                    live=inference_owner
                else:live=bind_live(built['runtime'])
                result['live_exposure_diagnostic']=dict(diagnostic_only=True,qualification=False,
                    detector_count=1,inference_thread='owned worker' if args.owned_inference_diagnostic else 'owned main',
                    records=live.results)
            primary.start()
            prepared=None;search_driver=None
            if args.bound_goal_diagnostic:
                prepared=_prepare_bound_goal_plan(port=port,production=production,
                    geometry=json.loads(args.geometry_seal.read_text()),result=result)
                if prepared['native_arm_count']!=0 or prepared['sdk_send_count']!=0:
                    raise PermissionError('HEAD_BOOTSTRAP_TRAJECTORY_AFTER_ARM_OR_SEND')
                result['prearm_trajectory']=prepared
            if args.search_controller_diagnostic:
                from so101_demo.adapters.act.head_owned_search import OwnedHeadSearch
                search_config=dict(prepared['config'],**measured['camera_seed_values'])
                search_driver=OwnedHeadSearch(config=search_config,primary=primary,port=port,owner=live,
                    settlement=_bound_goal_settlement,stop_velocity_rad_s=values['stop_velocity_rad_s'],
                    emit=lambda event,**fields:primary_writer('EVENT',dict(event=event,**fields)))
                result['search_controller_diagnostic']=dict(diagnostic_only=True,qualification=False,
                    config=search_config,trajectory_contract=prepared['trajectory_contract'],
                    control_period_s=.005,prepared_before_arm=True,
                    camera_parameters='unapproved measured calibration seed; all other thresholds unchanged')
            # Before the first activation, wait only for newly received matching
            # originals. No cached bootstrap sample is seeded into the primary.
            deadline=time.monotonic()+.2
            while True:
                if primary.failed:raise PermissionError('HEAD_BOOTSTRAP_PRIMARY_PREARM_FAILED')
                with port._lock:
                    images=dict(primary.observer._images);infos=dict(primary.observer._infos)
                    hb=primary.observer._primary
                now=time.monotonic();sim_ns=node.get_clock().now().nanoseconds
                if hb is not None and any(source in infos and 0<=now-row['wall_s']<=primary.observer.camera_age
                        and 0<=now-infos[source]['wall_s']<=primary.observer.camera_age
                        and 0<=sim_ns-source<=int(port.feedback_policy.camera_max_source_age_s*1e9)
                        for source,row in images.items()):break
                if now>=deadline:raise TimeoutError('HEAD_BOOTSTRAP_NEW_ORIGINAL_PAIR_MISSING')
                time.sleep(.001)
            result['cpu_inputs_before_prearm']=primary.wait_cpu_inputs(timeout_s=.2)
            authority=HeadReservationAuthority(directory=directory,capability=provisions.capabilities['neck'],
                native_owner=native,generation=generation,session_id=session,
                arm_guard=primary.prearm_guard,fault_callback=primary.fault)
            result['native_identity']=_bind_native_diagnostic(primary,authority,result)
            result['primary_ready']=primary.ready
            if args.owned_inference_diagnostic:inference_owner.activate_live()
            if args.bound_goal_diagnostic:
                def counted_send(*positional,**named):
                    primary.dispatch_guard()
                    result['goal_send_count']+=1
                    return sdk_send(*positional,**named)
                client.send_goal_async=counted_send
                try:
                    emit=lambda event,**fields:primary_writer('EVENT',dict(event=event,**fields))
                    if search_driver is not None:
                        dispatcher,neck=_bind_search_transport(node=node,port=port,primary=primary,
                            authority=authority,monitor=monitor,production=production,result=result,
                            emit=emit,trajectory=prepared['trajectory_contract'])
                        search_driver.bind_transport(neck)
                        _run_owned_search_diagnostic(driver=search_driver,dispatcher=dispatcher,result=result,emit=emit)
                    else:
                        _run_bound_goal_diagnostic(node=node,port=port,primary=primary,authority=authority,
                            monitor=monitor,production=production,geometry=json.loads(args.geometry_seal.read_text()),
                            result=result,emit=emit,live=live,owned_inference=args.owned_inference_diagnostic,
                            prepared=prepared)
                    if live is not None:result['live_exposure_diagnostic']['records']=live.results
                finally:client.send_goal_async=forbid_send
            primary.fault('HEAD_BOOTSTRAP_CONTROLLED_OWNED_FAULT',time.monotonic())
            result['primary_teardown']=primary.close()
            receipt=result['primary_teardown']
            expected_sends=1 if args.bound_goal_diagnostic else 0
            if args.search_controller_diagnostic:
                search=result['search_controller_diagnostic'];expected_sends=len(search['commands'])
                if (search['terminal']['status']!='TARGET_LOCKED'
                        or {command['goal_uuid'] for command in search['commands']}!=set(search['inventory'])
                        or any(len(command.get('confirming_samples',[]))!=3 for command in search['commands'])):
                    raise PermissionError('HEAD_BOOTSTRAP_SEARCH_INVENTORY_UNPROVEN')
            if (receipt['native_close'] is None or receipt['native_close'].get('ack_validated') is not True
                    or not any(row['stopped'] for row in receipt['stop_observations'])
                    or result['native_arm_count']!=1 or result['goal_send_count']!=expected_sends):
                raise PermissionError('HEAD_BOOTSTRAP_NATIVE_BOUNDARY_UNPROVEN')
            result['status']='BOUND_GOAL_STOPPED_DIAGNOSTIC' if args.bound_goal_diagnostic else 'NATIVE_BINDING_STOPPED_DIAGNOSTIC'
            if args.search_controller_diagnostic:result['status']='SEARCH_CONTROLLER_STOPPED_DIAGNOSTIC'
    except Exception as error:
        result['status']='REFUSED'
        if primary is not None:primary.fault('HEAD_BOOTSTRAP_ATTEMPT_FAILED')
        _record_refusal(result,error)
        print('STOPPED_BOOTSTRAP_REFUSED '+str(error),file=sys.stderr,flush=True)
    finally:
        inference_retired=True
        if inference_owner is not None:
            try:
                result['inference_owner_teardown']=inference_owner.close()
                if result['inference_owner_teardown']['error'] is not None:result['status']='REFUSED'
                if live is inference_owner:
                    result['live_exposure_teardown']=result['inference_owner_teardown']['live']
                    result['live_exposure_diagnostic']['records']=live.results
            except Exception as error:
                inference_retired=False;result['inference_owner_teardown_error']=str(error)
                result['producer_seals_withheld']=True;result['status']='REFUSED'
        if live is not None and live is not inference_owner:
            try:result['live_exposure_teardown']=live.close()
            except Exception as error:result['live_exposure_teardown_error']=str(error);result['status']='REFUSED'
        if primary is not None:
            try:result['primary_teardown']=primary.close()
            except Exception as error:result['primary_teardown_error']=str(error);result['status']='REFUSED'
        if capture is not None:
            with port._lock:
                raw=dict(joint_messages=list(port._head_samples),camera_messages=list(capture.camera_messages),
                    info_messages=list(capture.info_messages),clock_messages=list(capture.clock_messages),
                    events=list(capture.events),workload=getattr(capture,'workload',None))
            result['raw_observations_pending']=raw
        if executor is not None:
            try:
                result['executor_shutdown']=executor.shutdown(timeout_sec=1.)
                spinner.join(timeout=1.);result['executor_thread_exited']=not spinner.is_alive()
                if not result['executor_shutdown'] or spinner.is_alive():result['status']='REFUSED'
            except Exception as error:result['executor_teardown_error']=str(error);result['status']='REFUSED'
        if port is not None:
            try:result['port_io_teardown']=port.close_head_io(timeout_s=.010)
            except Exception as error:result['port_io_teardown_error']=str(error);result['status']='REFUSED'
        # rclpy Node.destroy_node destroys services/subscriptions, but leaves
        # ActionClient waitables owned until their explicit destroy().
        if client is not None:
            try:client.destroy();result['action_client_destroyed']=True
            except Exception as error:result['action_client_teardown_error']=str(error);result['status']='REFUSED'
        if listener is not None:
            try:listener.unregister();result['tf_listener_unregistered']=True
            except Exception as error:result['tf_listener_teardown_error']=str(error);result['status']='REFUSED'
        if node is not None:
            try:node.destroy_node()
            except Exception as error:result['node_teardown_error']=str(error);result['status']='REFUSED'
        if context is not None:
            try:context.try_shutdown()
            except Exception as error:result['context_teardown_error']=str(error);result['status']='REFUSED'
        if writer is not None and inference_retired:
            try:result['images']=writer.close()
            except Exception as error:result['image_seal_error']=str(error);result['status']='REFUSED'
        if original_router is not None:original_router.retire()
        if original_writer is not None and inference_retired:
            try:result['primary_original_journal']=original_writer.close(timeout_s=10.)
            except Exception as error:result['primary_original_seal_error']=str(error);result['status']='REFUSED'
        if primary_writer is not None and inference_retired:
            try:result['primary_events_journal']=primary_writer.close(timeout_s=10.)
            except Exception as error:result['primary_event_seal_error']=str(error);result['status']='REFUSED'
        if monitor is not None:
            try:result['monitor_teardown']=monitor.close()
            except Exception as error:result['monitor_teardown_error']=str(error);result['status']='REFUSED'
        if result['status'] in ('NATIVE_BINDING_STOPPED_DIAGNOSTIC','BOUND_GOAL_STOPPED_DIAGNOSTIC','SEARCH_CONTROLLER_STOPPED_DIAGNOSTIC'):
            try:result['monitor_closure']=_require_monitor_closure(root,result,
                stop_velocity_rad_s=values['stop_velocity_rad_s'])
            except Exception as error:_record_refusal(result,error)
        if stack is not None:
            children=list(stack.processes)
            try:stack.stop();result['stack_children']=[dict(pid=p.pid,exit_code=p.returncode) for p in children]
            except Exception as error:result['stack_teardown_error']=str(error);result['status']='REFUSED'
        # Provisions, markers and scratch remain retained deletion candidates.
        after=probe_owners(excluded_pids=(os.getpid(),),excluded_nodes=())
        teardown_deadline=time.monotonic()+10.;teardown_probes=[after]
        while (after['processes'] or after['nodes']) and time.monotonic()<teardown_deadline:
            time.sleep(.25)
            after=probe_owners(excluded_pids=(os.getpid(),),excluded_nodes=());teardown_probes.append(after)
        result['teardown_probes']=teardown_probes
        result['after']=after;result['gpu_after_in_process']=measure_gpu_compute_apps()
        result['gpu_release_requires_parent_readback']=True
        if after['processes'] or after['nodes']:result['status']='REFUSED';result['teardown_unproven']=True
        # Seal ownership readback before serializing raw sensor values: an
        # evidence encoder failure must still leave an auditable owned reap.
        _write(root/'teardown.json',{key:value for key,value in result.items()
                                   if key!='raw_observations_pending'})
        if 'raw_observations_pending' in result:
            result['raw_observations']=_write(root/'raw-observations.json',result.pop('raw_observations_pending'))
        result['ended_wall_s']=time.monotonic();_write(root/'result.json',result)
    print(result['status']+' run_root='+str(root),flush=True)
    return 0 if result['status'] in ('STOPPED_BOOTSTRAP_MEASURED','NATIVE_BINDING_STOPPED_DIAGNOSTIC','BOUND_GOAL_STOPPED_DIAGNOSTIC') else 2
