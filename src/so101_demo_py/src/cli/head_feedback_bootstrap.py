"""Installed CUDA bootstrap and optional native binding, with SDK send disabled."""
import argparse
import hashlib
import json
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


def _write(path,record):
    with Path(path).open('x',encoding='ascii') as handle:
        json.dump(record,handle,sort_keys=True,allow_nan=False);handle.write('\n')
        handle.flush();os.fsync(handle.fileno())
    return _reference(path)


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
    args=parser.parse_args(argv)
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
    result=dict(purpose='calibration',motion_authority=False,qualification=False,
        status='REFUSED',epoch=epoch,generation=generation,session_id=session,dependencies=dependencies,
        before=before,seed_config=_reference(args.production_config),entry=_reference(__file__),
        python=sys.executable,started_wall_s=time.monotonic(),native_arm_count=0,goal_send_count=0)
    _write(root/'attempt-declaration.json',dict(result,window_rule='stable10s then first future boundary at latest original camera receipt + stable p50 receipt gap / 2; at most two fixed 100ms source periods waiting before the single declaration; end=start+20s; no retry',
        startup_retention='bounded diagnostic metadata, no pixels before CUDA warmup; all stable/window originals and RGB retained',
        controlled_inputs={name:_reference(getattr(args,name)) for name in ('urdf','scene','plugin_config','controller_config')}))
    monitor=stack=context=node=executor=spinner=port=writer=capture=client=listener=original_writer=original_router=None
    primary=primary_writer=None
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
        environment=stack_environment(directory,session)
        environment['SO101_HEAD_SEARCH_V2_MONITOR_REQUIRED']='1';environment['MUJOCO_GL']='egl'
        stack=RestartStack(urdf_path=args.urdf,scene_path=args.scene,plugin_config_path=args.plugin_config,
            controller_config_path=args.controller_config,workspace=root/'stack',session_id=session,
            environment=environment,logger=lambda message:print(message,flush=True))
        stack.workspace.mkdir();stack.start()
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
        # Even binding a provisional policy cannot turn this diagnostic into a
        # dispatcher. The actual SDK client remains permanently send-disabled.
        client.send_goal_async=forbid_send
        port=RosControllerPort(node,client,('neck_yaw_joint',),stop_velocity_rad_s=values['stop_velocity_rad_s'],
                               max_age_s=values['max_age_s'],head_bootstrap=True)
        writer=_ImageWriter(root)
        capture=StoppedHeadCapture(node,port,frame_id=production['camera']['frame_id'],strict=False,emit=writer.emit)
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
        built=TimedHeadDetector.build(weights_path=dependencies['weights']['path'],model_id=production['runtime_id'],
            device=args.device,values=values,operating_point=_operating_point(args.frozen_candidate))
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
        if args.native_binding_diagnostic:
            primary_writer=HeadOriginalJournal(root/'primary-events.jsonl',fault_callback=original_failure)
            own=_peer(os.getpid())
            provision,fault_cap=_provision(directory/'neck-primary-revoke.provision',authority='primary',
                actor=own,native_owner=native,session_id=session)
            if provision!=result['monitor_configured']['provisions']['primary_fault']:
                raise PermissionError('HEAD_BOOTSTRAP_PRIMARY_PROVISION_CHANGED')
            revoker=NativeRevocationClient(directory/'neck-primary-revoke.sock',capability=fault_cap,
                native_owner=native,generation=generation,timeout_s=.002)
            primary=HeadPrimarySupervisor(node=node,port=port,router=original_router,monitor=monitor,
                revoker=revoker,epoch=epoch,generation=generation,session_id=session,policy_reference=reference,
                policy_ack=result['policy_ack'],configuration_ack=result['monitor_configured'],
                stop_latency_s=values['stop_latency_s'],camera_max_age_s=measured['camera_seed_values']['max_age_s'],
                camera_frame_id=production['camera']['frame_id'],
                emit=lambda event,**fields:primary_writer('EVENT',dict(event=event,**fields)))
            primary.start()
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
            authority=HeadReservationAuthority(directory=directory,capability=provisions.capabilities['neck'],
                native_owner=native,generation=generation,session_id=session,
                arm_guard=primary.prearm_guard,fault_callback=primary.fault)
            result['native_identity']=primary.arm(authority)
            result['native_arm_count']=sum(row['operation']=='SOGR' for row in authority.exchange_receipts)
            result['main_exchange_receipts']=authority.exchange_receipts
            result['primary_ready']=primary.ready
            primary.fault('HEAD_BOOTSTRAP_CONTROLLED_OWNED_FAULT',time.monotonic())
            result['primary_teardown']=primary.close()
            receipt=result['primary_teardown']
            if (receipt['native_close'] is None or receipt['native_close'].get('ack_validated') is not True
                    or not any(row['stopped'] for row in receipt['stop_observations'])
                    or result['native_arm_count']!=1 or result['goal_send_count']!=0):
                raise PermissionError('HEAD_BOOTSTRAP_NATIVE_BOUNDARY_UNPROVEN')
            result['status']='NATIVE_BINDING_STOPPED_DIAGNOSTIC'
    except Exception as error:
        result['error']=dict(type=type(error).__name__,message=str(error))
        print('STOPPED_BOOTSTRAP_REFUSED '+str(error),file=sys.stderr,flush=True)
    finally:
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
        if writer is not None:
            try:result['images']=writer.close()
            except Exception as error:result['image_seal_error']=str(error);result['status']='REFUSED'
        if original_router is not None:original_router.retire()
        if original_writer is not None:
            try:result['primary_original_journal']=original_writer.close(timeout_s=10.)
            except Exception as error:result['primary_original_seal_error']=str(error);result['status']='REFUSED'
        if primary_writer is not None:
            try:result['primary_events_journal']=primary_writer.close(timeout_s=10.)
            except Exception as error:result['primary_event_seal_error']=str(error);result['status']='REFUSED'
        if monitor is not None:
            try:result['monitor_teardown']=monitor.close()
            except Exception as error:result['monitor_teardown_error']=str(error);result['status']='REFUSED'
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
    return 0 if result['status'] in ('STOPPED_BOOTSTRAP_MEASURED','NATIVE_BINDING_STOPPED_DIAGNOSTIC') else 2
