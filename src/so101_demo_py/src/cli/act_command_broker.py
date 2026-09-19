"""Run the sole ROS command authority; calibration mode is explicitly excluded from data."""

import argparse
import json
import os
from pathlib import Path
import signal
import threading
import time

from so101_demo.act.calibration import require_qualified
from so101_demo.act.ownership import Ownership
from so101_demo.adapters.act.command_broker import CommandBroker, UnixBrokerServer, endpoint_bytes


def main(arguments=None):
    parser=argparse.ArgumentParser(prog='act_command_broker')
    parser.add_argument('--socket',required=True)
    parser.add_argument('--session-id',required=True)
    parser.add_argument('--parent-pid',type=int,required=True)
    parser.add_argument('--lease-timeout-s',type=float,required=True)
    parser.add_argument('--calibration-report',type=Path)
    parser.add_argument('--calibration-mode',action='store_true')
    parser.add_argument('--motion-calibration-manifest',type=Path)
    parser.add_argument('--stop-velocity-rad-s',type=float)
    parser.add_argument('--max-age-s',type=float)
    for flag in ('submit-lead-s','accept-timeout-s','stop-timeout-s','permit-ttl-s'):
        parser.add_argument('--'+flag,type=float)
    from rclpy.utilities import remove_ros_args
    options=parser.parse_args(arguments if arguments is not None else remove_ros_args()[1:])
    endpoint_bytes(options.socket)
    if options.parent_pid<=0:raise ValueError('PARENT_PID_INVALID')
    os.kill(options.parent_pid,0)
    if options.calibration_mode:
        if options.calibration_report or options.stop_velocity_rad_s is None or options.max_age_s is None:
            raise ValueError('EXPLICIT_CALIBRATION_PARAMETERS_REQUIRED')
        speed,age=options.stop_velocity_rad_s,options.max_age_s
    else:
        if not options.calibration_report:raise ValueError('CALIBRATION_REQUIRED')
        report=json.loads(options.calibration_report.read_text());require_qualified(report)
        speed=report['measurements']['stop_velocity_rad_s']['value']
        age=report['measurements']['max_age_s']['value']
    from math import isfinite
    if not isfinite(speed) or speed < 0 or not isfinite(age) or age <= 0:
        raise ValueError('STOP_CONFIG_INVALID')
    timing=(options.submit_lead_s,options.accept_timeout_s,options.stop_timeout_s,options.permit_ttl_s)
    if any(value is not None for value in timing):
        if not all(value is not None for value in timing):raise ValueError('PAIRED_TIMING_PARAMETERS_REQUIRED')
        if not options.calibration_mode:raise ValueError('FULL_SUPERVISOR_REQUIRED')
        if not all(isfinite(value) and value > 0 for value in timing) or not timing[1] < timing[0]:
            raise ValueError('EXECUTION_TIMING_INVALID')
    motion_manifest=None
    if options.motion_calibration_manifest:
        from so101_demo.adapters.act.calibration_motion import require_motion_manifest
        if not options.calibration_mode or not all(value is not None for value in timing):raise ValueError('MOTION_CALIBRATION_MODE_REQUIRED')
        motion_manifest=require_motion_manifest(json.loads(options.motion_calibration_manifest.read_text()))
        if (motion_manifest['session_id']!=options.session_id or motion_manifest['submit_lead_s']!=options.submit_lead_s
                or motion_manifest['stop_velocity_rad_s']!=speed):raise ValueError('MOTION_CALIBRATION_CONFIG_MISMATCH')
    from so101_demo.adapters.act.domain_authority import DomainAuthority
    authority=DomainAuthority(int(os.environ.get('ROS_DOMAIN_ID','0'))).acquire()
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.parameter import Parameter
    from so101_demo.adapters.act.ros_broker import RosBrokerDriver
    rclpy.init();node=rclpy.create_node('act_command_broker',parameter_overrides=[Parameter('use_sim_time',value=True)])
    executor=SingleThreadedExecutor();executor.add_node(node)
    thread=threading.Thread(target=executor.spin,daemon=True);thread.start()
    driver=RosBrokerDriver(node,stop_velocity_rad_s=speed,max_age_s=age)
    broker=CommandBroker(driver,ownership=Ownership(lease_timeout_s=options.lease_timeout_s),
                         simulation_session_id=options.session_id)
    motion_guard=None
    if motion_manifest is not None:
        from so101_demo.adapters.act.calibration_motion import RosCalibrationMotionGuard
        motion_guard=RosCalibrationMotionGuard(node,driver,broker,motion_manifest,evidence_root=Path(options.socket).parent)
    timing=(options.submit_lead_s,options.accept_timeout_s,options.stop_timeout_s,options.permit_ttl_s)
    if any(value is not None for value in timing):
        if not all(value is not None for value in timing):raise ValueError('PAIRED_TIMING_PARAMETERS_REQUIRED')
        if not options.calibration_mode:raise ValueError('FULL_SUPERVISOR_REQUIRED')
        from so101_demo.adapters.act.broker_execution import BrokerPairedExecution
        def static_calibration_only(prefix,snapshot):
            # This opt-in calibration authority approves zero-motion holds only.
            # It cannot grant formal collection or general trajectory safety.
            return (all(abs(value)<=speed for value in snapshot['velocities'])
                    and all(all(abs(value-held)<=1e-12 for value,held in zip(row,snapshot['reference'],strict=True))
                            for row in prefix['positions']))
        broker.prefix_executor=BrokerPairedExecution(broker,
            snapshot_port=driver.approval_snapshot,check_port=motion_guard.check_prefix if motion_guard is not None else static_calibration_only,
            reference_port=driver.current_reference,
            sim_clock=lambda:node.get_clock().now().nanoseconds*1e-9,
            submit_lead_s=options.submit_lead_s,accept_timeout_s=options.accept_timeout_s,
            stop_timeout_s=options.stop_timeout_s,permit_ttl_s=options.permit_ttl_s,
            path_port=motion_guard.check_exact_goals if motion_guard is not None else None)
    server=UnixBrokerServer(broker,options.socket,parent_pid=options.parent_pid)
    shutdown=threading.Event()
    for signum in (signal.SIGINT,signal.SIGTERM):signal.signal(signum,lambda *_:shutdown.set())
    report_path=Path(options.socket).with_name('broker-runtime.json')
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(dict(pid=os.getpid(),parent_pid=options.parent_pid,
        socket=options.socket,session_id=options.session_id,calibration_only=options.calibration_mode,
        control_guard_kernel_name=authority.kernel_name,ros_domain_id=authority.domain,
        eligible_for_collection=False,stop_velocity_rad_s=speed,max_age_s=age,
        paired_calibration_timing=timing if broker.prefix_executor is not None else None,
        motion_calibration_manifest=str(options.motion_calibration_manifest) if motion_guard is not None else None,
        motion_calibration_model_sha256=motion_manifest['model_sha256'] if motion_guard is not None else None,
        action_map={'arm':'/arm_controller/follow_joint_trajectory','gripper':'/gripper_controller/follow_joint_trajectory',
                    'execute_trajectory':'/execute_trajectory'}),indent=2)+'\n')
    try:
        server.start()
        while not shutdown.wait(.1) and not server._stop.is_set():broker.tick()
    finally:
        server.close()
        # No new process may inherit authority merely because the old lease was
        # revoked. Keep the driver alive for the bounded real-stop observation.
        deadline=time.monotonic()+5.
        while broker.ownership.state=='STOPPING' and time.monotonic()<deadline:
            broker.tick();time.sleep(.01)
        stop=dict(state=broker.ownership.state,unknown_goal_seen=driver.unknown_goal_seen,
                  audit=broker.audit,stop_confirmed=driver.stopped(),driver=driver.diagnostics(),
                  motion_calibration_audit=list(motion_guard.audit) if motion_guard is not None else [])
        report_path.with_name('broker-stop.json').write_text(json.dumps(stop,indent=2)+'\n')
        executor.shutdown();thread.join(3)
        if motion_guard is not None:motion_guard.close()
        node.destroy_node();rclpy.shutdown();authority.close()
    return 0 if stop['stop_confirmed'] else 2


if __name__=='__main__':raise SystemExit(main())
