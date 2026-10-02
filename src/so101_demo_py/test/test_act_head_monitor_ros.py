"""CPU monitor cancellation inventories unknown UUIDs without motion clients."""
from concurrent.futures import Future
from types import SimpleNamespace
import threading
import uuid

import pytest
from action_msgs.msg import GoalStatus, GoalStatusArray
from action_msgs.srv import CancelGoal
from control_msgs.action import FollowJointTrajectory
from unique_identifier_msgs.msg import UUID

from test_act_head_feedback_freshness import policy, sample
from so101_demo.adapters.act.head_monitor_ros import HeadROSMonitor


class SubscriptionSpec(tuple):
    @property
    def topic_name(self):return self[1]


class Node:
    def __init__(self):
        self.wall=10.;self.sim=1.;self.calls=[];self.subscriptions=[]
        def update(message):self.sim=message.clock.sec+message.clock.nanosec*1e-9
        self._time_source=SimpleNamespace(ros_time_is_active=True,clock_callback=update)
        from rosgraph_msgs.msg import Clock
        from rclpy.qos import QoSProfile
        # This fixture records application-created subscriptions; TimeSource preexists.
        self._time_source._clock_sub=SimpleNamespace(callback=update,qos_profile=QoSProfile(depth=1),topic_name='/clock')
    def get_clock(self):return SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=round(self.sim*1e9)))
    def create_subscription(self,*args):
        self.subscriptions.append(SubscriptionSpec(args))
        return SimpleNamespace(callback=args[2],qos_profile=args[3],topic_name=args[1])
    def create_client(self,kind,name):
        node=self
        class Client:
            def call_async(self,request):
                future=Future();node.calls.append((kind,name,request,future));return future
        return Client()


def observer():
    node=Node();events=[];faults=[]
    monitor=HeadROSMonitor(node,epoch='attempt',generation=5,
        stop_velocity_rad_s=.002,stop_latency_s=.07,camera_max_age_s=.05,
        camera_frame_id='head_camera_optical_frame',emit=lambda *args,**kw:events.append((args,kw)),
        fault_callback=lambda reason,wall:faults.append((reason,wall)),monotonic=lambda:node.wall)
    monitor.bind_policy(policy())
    return node,monitor,events,faults


def inventory(monitor):
    goal_uuid=str(uuid.uuid4());monitor.inventory(goal_uuid)
    return goal_uuid


def test_monitor_has_only_scoped_result_and_cancel_service_clients():
    node,monitor,_,_=observer()
    try:
        assert set(monitor.service_names)=={
            '/neck_controller/follow_joint_trajectory/_action/get_result',
            '/neck_controller/follow_joint_trajectory/_action/cancel_goal'}
        assert len([row for row in node.subscriptions if row[1]=='/joint_states'])==1
        with pytest.raises(PermissionError,match='MONITOR_MOTION_FORBIDDEN'):monitor.port.send({})
    finally:monitor.close(timeout_s=1.)


def test_unknown_inventory_is_cancelled_by_exact_uuid_without_acceptance():
    node,monitor,_,_=observer();goal_uuid=inventory(monitor)
    try:
        monitor.request_cancel_all()
        assert monitor.wait_for_operations(timeout_s=.2)
        cancels=[row for row in node.calls if row[0] is CancelGoal]
        assert len(cancels)==1
        assert bytes(cancels[0][2].goal_info.goal_id.uuid)==uuid.UUID(goal_uuid).bytes
        assert cancels[0][2].goal_info.stamp.sec==cancels[0][2].goal_info.stamp.nanosec==0
        response=CancelGoal.Response(return_code=2)
        cancels[0][3].set_result(response)
        assert monitor.port.accepted(goal_uuid) is None
        assert monitor.port.result(goal_uuid) is None
        assert monitor.port.stopped() is False
    finally:monitor.close(timeout_s=1.)


def test_unknown_result_is_not_rejection_or_terminal_proof():
    node,monitor,_,_=observer();goal_uuid=inventory(monitor)
    try:
        monitor.request_results()
        assert monitor.wait_for_operations(timeout_s=.2)
        node.calls[-1][3].set_result(FollowJointTrajectory.Impl.GetResultService.Response(status=0))
        assert monitor.port.accepted(goal_uuid) is None
        assert monitor.port.result(goal_uuid) is None
        assert monitor.port.stopped() is False
    finally:monitor.close(timeout_s=1.)


def test_late_accepted_uuid_is_cancelled_again_and_requires_actual_terminal():
    node,monitor,_,_=observer();goal_uuid=inventory(monitor)
    try:
        monitor.request_cancel_all();assert monitor.wait_for_operations(timeout_s=.2)
        node.calls[-1][3].set_result(CancelGoal.Response(return_code=2))
        message=GoalStatusArray(status_list=[GoalStatus(status=2)])
        message.status_list[0].goal_info.goal_id=UUID(uuid=list(uuid.UUID(goal_uuid).bytes))
        monitor._status(message)
        assert monitor.port.accepted(goal_uuid) is True
        monitor.request_cancel_all();assert monitor.wait_for_operations(timeout_s=.2)
        assert len([row for row in node.calls if row[0] is CancelGoal])==2
        assert monitor.port.result(goal_uuid) is None
        monitor.request_results();assert monitor.wait_for_operations(timeout_s=.2)
        node.calls[-1][3].set_result(FollowJointTrajectory.Impl.GetResultService.Response(status=5))
        assert monitor.port.result(goal_uuid).status==5
    finally:monitor.close(timeout_s=1.)


def test_quiet_feedback_and_cancel_ack_do_not_settle_unknown_inventory():
    node,monitor,_,_=observer();goal_uuid=inventory(monitor)
    try:
        monitor.begin_stop(fault_wall_s=node.wall)
        monitor.request_cancel_all();assert monitor.wait_for_operations(timeout_s=.2)
        node.calls[-1][3].set_result(CancelGoal.Response(return_code=0))
        for index in range(1,4):
            node.wall=10.+index*.01;node.sim=1.+index*.01
            monitor.port._feedback(sample(node.sim))
        assert monitor.port.stopped() is False
        assert monitor.port.accepted(goal_uuid) is None
    finally:monitor.close(timeout_s=1.)


def test_terminal_result_and_three_post_request_originals_prove_actual_predicate():
    node,monitor,_,_=observer();goal_uuid=inventory(monitor)
    try:
        monitor.begin_stop(fault_wall_s=node.wall)
        monitor.request_results();assert monitor.wait_for_operations(timeout_s=.2)
        node.calls[-1][3].set_result(FollowJointTrajectory.Impl.GetResultService.Response(status=5))
        for index in range(1,4):
            node.wall=10.+index*.01;node.sim=1.+index*.01
            monitor.port._feedback(sample(node.sim))
            assert monitor.port.stopped() is (index==3)
        assert monitor.port.stop_predicate_observations[-1]['confirmed_at']['wall_after_s']==10.03
    finally:monitor.close(timeout_s=1.)


def test_foreign_status_cannot_settle_owned_unknown_goal():
    node,monitor,_,_=observer();goal_uuid=inventory(monitor)
    try:
        message=GoalStatusArray(status_list=[GoalStatus(status=5)])
        message.status_list[0].goal_info.goal_id=UUID(uuid=list(uuid.uuid4().bytes))
        monitor._status(message)
        assert monitor.port.accepted(goal_uuid) is None
    finally:monitor.close(timeout_s=1.)


def test_async_result_failure_consumes_attempt_and_cannot_reopen():
    node,monitor,_,faults=observer();goal_uuid=inventory(monitor)
    try:
        monitor.request_results();assert monitor.wait_for_operations(timeout_s=.2)
        node.calls[-1][3].set_exception(RuntimeError('real Future failure'))
        assert faults and monitor.failed
        assert monitor.port.accepted(goal_uuid) is None
        with pytest.raises(PermissionError):monitor.inventory(str(uuid.uuid4()))
        with pytest.raises(PermissionError):monitor.bind_policy(policy())
    finally:monitor.close(timeout_s=1.)


def test_journal_sink_failure_still_requests_independent_fault_closure():
    _,monitor,_,faults=observer()
    try:
        def bad_sink(*args,**kwargs):raise OSError('disk worker unavailable')
        monitor.emit=bad_sink
        monitor._event('CONTROL')
        assert monitor.failed
        assert faults==[('HEAD_MONITOR_JOURNAL_FAILED',10.)]
    finally:monitor.close(timeout_s=1.)


@pytest.mark.parametrize('boundary',['duplicate_inventory','primary_rejection','heartbeat'])
def test_fault_reporting_never_holds_observation_or_watchdog_locks(boundary):
    node,monitor,_,_=observer();gid=inventory(monitor);available=[]
    def reporter(reason,wall):
        def check():
            locks=(monitor._lock,monitor.port._lock)
            acquired=[]
            for lock in locks:
                found=lock.acquire(timeout=.01);acquired.append(found)
                if found:lock.release()
            available.append(all(acquired))
        other=threading.Thread(target=check);other.start();other.join(.1)
    monitor.fault_callback=reporter
    try:
        if boundary=='duplicate_inventory':
            with pytest.raises(PermissionError):monitor.inventory(gid)
        elif boundary=='primary_rejection':
            with monitor.port._lock:monitor.port._goals[gid]['accepted']=True
            monitor.primary_rejection(gid)
        else:
            with pytest.raises(ValueError):monitor.heartbeat(dict(wall_s=11.,executor_wall_s=10.,inference_deadline_wall_s=None))
        assert available==[True]
    finally:monitor.close(timeout_s=1.)


def ready_monitor():
    from builtin_interfaces.msg import Time
    from std_msgs.msg import Header
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import CameraInfo,Image
    node,monitor,events,faults=observer()
    monitor.port._feedback(sample())
    monitor._on_clock(Clock(clock=Time(sec=1)))
    header=Header(frame_id='head_camera_optical_frame',stamp=Time(sec=1))
    monitor._on_info(CameraInfo(header=header,width=640,height=480,k=[200.,0.,320.,0.,200.,240.,0.,0.,1.]))
    monitor._on_image(Image(header=header,width=640,height=480,encoding='rgb8',step=1920,data=bytes(640*480*3)))
    monitor.executor_progress();monitor.heartbeat(dict(wall_s=10.,executor_wall_s=10.,inference_deadline_wall_s=None))
    monitor.activate()
    return node,monitor,events,faults


def test_backward_camera_original_is_refused_before_source_order_can_be_sorted():
    from builtin_interfaces.msg import Time
    from std_msgs.msg import Header
    from sensor_msgs.msg import Image
    node,monitor,events,faults=ready_monitor()
    try:
        message=Image(header=Header(frame_id=monitor.camera_frame,stamp=Time(nanosec=990000000)),
            width=640,height=480,encoding='rgb8',step=1920,data=bytes(640*480*3))
        monitor._on_image(message)
        assert monitor.failed and faults
        assert monitor._camera_watermark==1_000_000_000
        assert any(row[0][0]=='IMAGE_ORIGINAL' and row[1].get('valid') is False for row in events)
    finally:monitor.close(timeout_s=1.)


def test_watchdog_gap_cannot_be_hidden_by_fresh_intervening_callbacks():
    from builtin_interfaces.msg import Time
    from rosgraph_msgs.msg import Clock
    node,monitor,_,faults=ready_monitor()
    try:
        node.wall=10.012;node.sim=1.01
        monitor.port._feedback(sample(node.sim));monitor._on_clock(Clock(clock=Time(sec=1,nanosec=10000000)))
        monitor.executor_progress();monitor.heartbeat(dict(wall_s=node.wall,executor_wall_s=node.wall,inference_deadline_wall_s=None))
        monitor.poll()
        assert monitor.failed
        assert faults[0][1]==pytest.approx(10.010,abs=1e-12)
    finally:monitor.close(timeout_s=1.)


@pytest.mark.parametrize('expired',['heartbeat','inference','clock'])
def test_known_expiry_fault_retains_threshold_crossing_time(expired):
    node,monitor,_,faults=ready_monitor()
    try:
        if expired=='heartbeat':node.wall=10.012;expected=10.010
        elif expired=='inference':
            node.wall=10.006;expected=10.005
            monitor.heartbeat(dict(wall_s=node.wall,executor_wall_s=node.wall,inference_deadline_wall_s=expected))
            monitor.executor_progress()
        else:
            node.wall=10.021;node.sim=1.01;expected=10.020
            monitor.watchdog_polls.append(10.020)
            monitor.port._feedback(sample(node.sim));monitor.executor_progress()
            monitor.heartbeat(dict(wall_s=node.wall,executor_wall_s=node.wall,inference_deadline_wall_s=None))
        monitor.poll()
        assert monitor.failed
        assert faults[0][1]==pytest.approx(expected,abs=1e-12)
    finally:monitor.close(timeout_s=1.)


@pytest.mark.parametrize('deadlines,completed,observed',[
    ([10_005_000_000],10.005,10.005),
    ([10_005_000_000],10.004,10.005),
    ([10_005_000_000],10.004,10.003),
    ([True],10.,10.),([],10.,10.),
    ([10_005_000_000,10_005_000_000],10.,10.),
])
def test_deadline_discharge_refuses_late_future_or_invalid_completion(deadlines,completed,observed):
    node,monitor,_,_=ready_monitor()
    try:
        node.wall=observed
        with pytest.raises((ValueError,PermissionError)):
            monitor.discharge_inference_deadlines(deadlines,completion_wall_s=completed)
    finally:monitor.close(timeout_s=1.)


def test_conflicting_terminal_response_consumes_attempt_without_replacing_proof():
    node,monitor,_,faults=observer();gid=inventory(monitor)
    try:
        first=Future();first.set_result(FollowJointTrajectory.Impl.GetResultService.Response(status=5))
        second=Future();second.set_result(FollowJointTrajectory.Impl.GetResultService.Response(status=6))
        monitor._response(gid,'result',first);monitor._response(gid,'result',second)
        assert monitor.failed and faults
        assert monitor.port.result(gid).status==5
    finally:monitor.close(timeout_s=1.)


def test_replaced_pending_exposure_is_logged_as_dropped_before_admission():
    from builtin_interfaces.msg import Time
    from std_msgs.msg import Header
    from sensor_msgs.msg import Image
    _,monitor,events,_=ready_monitor()
    try:
        for stamp in (100000000,200000000):
            monitor._on_image(Image(header=Header(frame_id=monitor.camera_frame,stamp=Time(sec=1,nanosec=stamp)),
                width=640,height=480,encoding='rgb8',step=1920,data=bytes(640*480*3)))
        assert len(monitor._images)==1
        drops=[row for row in events if row[0][0]=='DROPPED_EXPOSURE']
        assert len(drops)==1 and drops[0][1]['source_ns']==1_100_000_000
    finally:monitor.close(timeout_s=1.)


def test_dispatch_checks_cannot_hide_stalled_owned_watchdog():
    import hashlib
    import os
    from so101_demo.adapters.act.head_monitor_runtime import HeadMonitorRuntime,_peer
    node,monitor,_,faults=ready_monitor()
    runtime=HeadMonitorRuntime(epoch='attempt',generation=5,session_id='monitor-control',primary=_peer(os.getppid()))
    runtime._observer=monitor
    runtime.epoch.clock_ns=lambda:round(node.wall*1e9)
    runtime.epoch.bind_policy(policy(),'a'*64)
    identity=dict(generation=5,incarnation='controller',boot='boot')
    runtime.epoch.armed_ready(identity,identity)
    gid=inventory(monitor)
    record=dict(goal_uuid=gid,typed_goal={'trajectory':{'joint_names':['neck_yaw_joint']}},
        payload_sha256='b'*64,generation=5,controller_identity=identity,attempt_epoch='attempt',
        session_id='monitor-control',role='neck',operation_sequence=1,claim_monotonic_ns=10_000_000_000,
        deadline_ns=10_400_000_000)
    ack=runtime.epoch.register(record)
    try:
        node.wall=10.008;monitor.executor_progress()
        monitor.heartbeat(dict(wall_s=node.wall,executor_wall_s=node.wall,inference_deadline_wall_s=None))
        runtime.dispatch(dict(goal_uuid=gid,inventory_sha256=ack['inventory_sha256']))
        node.wall=10.015;monitor.executor_progress()
        monitor.heartbeat(dict(wall_s=node.wall,executor_wall_s=node.wall,inference_deadline_wall_s=None))
        monitor.poll()
        assert monitor.failed, 'dispatch polling refreshed the stalled watchdog'
        assert faults[0][1]==pytest.approx(10.010,abs=1e-12)
    finally:monitor.close(timeout_s=1.)


@pytest.mark.parametrize('valid',[True,False])
def test_actual_camera_info_callback_emits_json_boolean_with_original_identity(valid):
    import json
    from sensor_msgs.msg import CameraInfo
    node,monitor,_,faults=observer();records=[]
    try:
        monitor.emit=lambda event,**fields:records.append(json.loads(json.dumps(
            dict(event=event,**fields),allow_nan=False)))
        info=CameraInfo();info.header.stamp.sec=1;info.header.frame_id=monitor.camera_frame
        info.width=640;info.height=480;info.k=[415.,0.,320.,0.,415.,240.,0.,0.,1.]
        if not valid:info.k[0]=0.
        monitor._on_info(info)
        assert not faults
        assert len(records)==1
        assert records[0]['event']=='INFO_ORIGINAL'
        assert records[0]['valid'] is valid
        assert records[0]['source_ns']==1_000_000_000
        assert records[0]['wall_s']==node.wall
        assert records[0]['frame_id']==monitor.camera_frame
    finally:monitor.close(timeout_s=1.)


def test_later_report_of_earlier_fault_reaches_owned_fault_closer():
    node,monitor,_,faults=observer()
    try:
        monitor.fault('first observed',fault_wall_s=10.)
        monitor.fault('earlier origin',fault_wall_s=9.95)
        monitor.fault('later origin',fault_wall_s=10.01)
        assert faults==[('first observed',10.),('earlier origin',9.95)]
        assert monitor._fault_wall==9.95 and monitor.failed
    finally:monitor.close(timeout_s=1.)


@pytest.mark.parametrize('earliest,valid',[(9.95,False),(9.99,True)])
def test_original_stop_request_is_preserved_when_deadline_tightens(earliest,valid):
    node,monitor,_,_=observer()
    try:
        monitor.begin_stop(fault_wall_s=10.)
        for index in range(1,4):
            node.wall=10.+index*.01;node.sim=1.+index*.01
            monitor.port._feedback(sample(node.sim))
            monitor.port.stopped()
        assert monitor.port.stopped()
        sequence=monitor.port._head_stop_proof.last_sequence
        monitor.begin_stop(fault_wall_s=earliest)
        assert monitor.port._stop_epoch['request_wall_s']==10.
        assert monitor.port._stop_epoch['request_sim_s']==1.
        assert monitor.port._head_stop_proof.last_sequence==sequence
        assert monitor.port._stop_epoch['fault_wall_s']==earliest
        assert monitor.port.stopped() is valid
        # A later origin cannot extend the original deadline or repair failure.
        monitor.begin_stop(fault_wall_s=10.)
        assert monitor.port._stop_epoch['fault_wall_s']==earliest
        for index in range(4,11):
            node.wall=10.+index*.01;node.sim=1.+index*.01
            monitor.port._feedback(sample(node.sim))
            assert monitor.port.stopped() is valid
    finally:monitor.close(timeout_s=1.)


def test_owned_runtime_receives_earliest_fault_after_stop_worker_completed():
    import os
    from so101_demo.adapters.act.head_monitor_runtime import HeadMonitorRuntime,_peer
    node,monitor,_,_=observer()
    runtime=HeadMonitorRuntime(epoch='attempt',generation=5,session_id='session',primary=_peer(os.getppid()))
    runtime._observer=monitor;monitor.fault_callback=runtime.fault
    try:
        monitor.fault('first observed',fault_wall_s=10.)
        monitor.begin_stop(fault_wall_s=10.)
        for index in range(1,4):
            node.wall=10.+index*.01;node.sim=1.+index*.01
            monitor.port._feedback(sample(node.sim));monitor.port.stopped()
        assert monitor.port.stopped()
        runtime._stop_done.set()  # independent worker has already completed
        monitor.fault('earlier origin',fault_wall_s=9.95)
        assert runtime._fault_event.is_set() and runtime.revoked
        assert runtime._fault['fault_wall_s']==runtime.epoch.fault['fault_wall_s']==9.95
        assert monitor.port._stop_epoch['fault_wall_s']==9.95
        assert monitor.port.stopped() is False
    finally:monitor.close(timeout_s=1.)
