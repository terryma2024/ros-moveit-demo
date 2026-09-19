"""All broker submissions share scope, generation fencing and physical stop."""
import threading
import pytest
from so101_demo.act.ownership import Ownership
from so101_demo.adapters.act.command_broker import CommandBroker, endpoint_bytes

class Driver:
    def __init__(self):self.sent=[];self.cancels=[];self.stops=[];self.stationary=True
    def validate(self,kind,goal):
        if kind not in ('arm','gripper','execute_trajectory') or goal!={'trajectory':{}}:
            raise ValueError('GOAL_INVALID')
        return goal
    def submit(self,kind,goal):self.sent.append((kind,goal));return f'g{len(self.sent)}'
    def cancel(self,gid):self.cancels.append(gid)
    def stop_all(self,reason):self.stops.append(reason)
    def stopped(self):return self.stationary
    def goal_state(self,gid):return dict(accepted=True,status=5,result={'error_code':-4})


def request(op='acquire',owner='teacher',token='',**extra):
    return dict(protocol_version=1,request_id='r',owner=owner,session_id='s',attempt_id='a',
                lease_token=token,operation=op,**extra)


def test_cross_client_attempts_never_reach_bottom_driver():
    driver=Driver();broker=CommandBroker(driver,ownership=Ownership())
    token=broker.handle(request(owner='act'),'connection-act')['lease_token']
    for kind in ('arm','gripper','execute_trajectory'):
        out=broker.handle(request('submit',token=token,action_kind=kind,goal={'trajectory':{}}),'teacher')
        assert not out['accepted'] and out['error']=='LEASE_INVALID'
    assert driver.sent==[]
    out=broker.handle(request('submit',owner='act',token=token,action_kind='arm',goal={'trajectory':{}}),'connection-act')
    assert not out['accepted'] and out['error']=='ACT_PREFIX_REQUIRED'
    assert driver.sent==[]


def test_disconnect_expiry_and_stop_barrier():
    now=[0.];driver=Driver();ownership=Ownership(monotonic=lambda:now[0],lease_timeout_s=1.)
    broker=CommandBroker(driver,ownership=ownership)
    token=broker.handle(request(),'c')['lease_token'];driver.stationary=False
    broker.disconnect('c');assert driver.stops and ownership.state=='STOPPING'
    assert not broker.handle(request(owner='recovery'),'r')['accepted']
    driver.stationary=True;broker.tick();assert ownership.state=='IDLE'
    token=broker.handle(request(),'new')['lease_token'];now[0]=1.
    broker.tick();assert driver.stops[-1]=='LEASE_EXPIRED'
    assert not broker.handle(request('submit',token=token,action_kind='arm',goal={'trajectory':{}}),'new')['accepted']


def test_old_queued_generation_is_fenced_and_release_checks_driver():
    driver=Driver();ownership=Ownership();broker=CommandBroker(driver,ownership=ownership)
    token=broker.handle(request(),'c')['lease_token'];ticket=ownership.ticket(token,'teacher','s','a')
    driver.stationary=False
    assert not broker.handle(request('release',token=token),'c')['accepted']
    broker.handle(request('revoke',token=token),'c');driver.stationary=True;broker.tick()
    broker.handle(request(owner='teleop'),'other')
    with pytest.raises(PermissionError):broker.dispatch(ticket,'arm',{'trajectory':{}})
    assert driver.sent==[]


def test_atomic_submit_revoke_and_protocol_is_closed():
    driver=Driver();broker=CommandBroker(driver,ownership=Ownership())
    token=broker.handle(request(),'c')['lease_token']
    broker.handle(request('revoke',token=token),'c')
    assert not broker.handle(request('submit',token=token,action_kind='arm',goal={'trajectory':{}}),'c')['accepted']
    for bad in (dict(request(),protocol_version=2),dict(request(),unknown=True),dict(request(),owner=True)):
        assert not broker.handle(bad,'c')['accepted']
    assert driver.sent==[]


def test_socket_maximum_checks_utf8_bytes_before_start():
    assert endpoint_bytes('/'+'a'*106)==107
    with pytest.raises(ValueError):endpoint_bytes('/'+'a'*107)
    with pytest.raises(ValueError):endpoint_bytes('/'+'中'*36)


def test_factory_requires_explicit_act_context_and_preserves_legacy(monkeypatch):
    from so101_demo.adapters.act.leased_action_client import make_action_client
    monkeypatch.setenv('SO101_ACT_PROFILE','1')
    with pytest.raises(PermissionError,match='CONTROL_CONTEXT_REQUIRED'):
        make_action_client(None,None,'/execute_trajectory')
    monkeypatch.delenv('SO101_ACT_PROFILE')
    import rclpy.action
    monkeypatch.setattr(rclpy.action,'ActionClient',lambda *args:'legacy-direct-client')
    assert make_action_client(None,None,'/execute_trajectory')=='legacy-direct-client'


def test_unix_exclusivity_result_status_and_disconnect_real_factory(tmp_path):
    import time,uuid
    from pathlib import Path
    from control_msgs.action import FollowJointTrajectory
    from so101_demo.adapters.act.command_broker import UnixBrokerServer
    from so101_demo.adapters.act.leased_action_client import BrokerConnection,make_action_client
    # Unix path budget is checked for the complete endpoint. NVMe scratch paths
    # are intentionally long; use the registered root's short runtime directory.
    root=Path('/data/work/so101-evidence/act-data/0917a/r')/uuid.uuid4().hex[:8]
    endpoint=str(root/'a');driver=Driver()
    driver.validate=lambda kind,goal:goal
    driver.ready=lambda kind:True
    broker=CommandBroker(driver,ownership=Ownership(lease_timeout_s=2.))
    server=UnixBrokerServer(broker,endpoint).start()
    conn=None
    try:
        with pytest.raises((RuntimeError,BlockingIOError)):UnixBrokerServer(broker,endpoint).start()
        conn=BrokerConnection(endpoint,rpc_lock_path=str(root/'rpc.lock'))
        context=conn.acquire('teacher','s','a')
        client=make_action_client(None,FollowJointTrajectory,
                 '/arm_controller/follow_joint_trajectory',control_context=context)
        assert client.wait_for_server(.1)
        handle=client.send_goal_async(FollowJointTrajectory.Goal()).result(timeout=2)
        assert handle.accepted
        actual=handle.get_result_async().result(timeout=2)
        assert actual.status==5 and actual.result.error_code==-4
        driver.stationary=False;conn.close();conn=None
        until=time.monotonic()+2
        while broker.ownership.state!='STOPPING' and time.monotonic()<until:time.sleep(.01)
        assert broker.ownership.state=='STOPPING' and driver.stops==['CLIENT_DISCONNECTED']
        driver.stationary=True;broker.tick();assert broker.ownership.state=='IDLE'
    finally:
        if conn is not None:conn.close()
        server.close()


def test_actual_ros_goal_whitelist_limits_and_no_multi_dof():
    from control_msgs.action import FollowJointTrajectory
    from trajectory_msgs.msg import JointTrajectoryPoint
    from so101_demo.adapters.act.leased_action_client import message_dict
    from so101_demo.adapters.act.ros_broker import validated_goal
    goal=FollowJointTrajectory.Goal();goal.trajectory.joint_names=['6']
    point=JointTrajectoryPoint(positions=[.1]);point.time_from_start.sec=1
    goal.trajectory.points=[point]
    wire=message_dict(goal)
    import copy
    before=copy.deepcopy(wire)
    assert validated_goal('gripper',wire).trajectory.points[0].positions[0]==.1
    assert wire==before
    for bad in (dict(wire,unknown=True),dict(wire,trajectory=dict(wire['trajectory'],joint_names=['neck_yaw_joint'])),
                dict(wire,trajectory=dict(wire['trajectory'],points=[dict(wire['trajectory']['points'][0],positions=[100.])]))):
        with pytest.raises(ValueError):validated_goal('gripper',bad)


def test_teacher_factory_cannot_impersonate_act_owner(monkeypatch):
    from so101_demo.adapters.act.leased_action_client import make_action_client
    monkeypatch.setenv('SO101_ACT_PROFILE','1')
    with pytest.raises(PermissionError,match='LEASE_OWNER_INVALID'):
        make_action_client(None,None,'/execute_trajectory',control_context=dict(
            broker_socket='/tmp/no-connection-must-be-created',owner='act',session_id='s',
            attempt_id='a',lease_token='x'))


def test_reset_is_authorized_and_requires_physical_stop():
    driver=Driver();writes=[]
    from concurrent.futures import Future
    driver.validate_write=lambda operation,values:values
    def write(operation,value):
        future=Future();writes.append(value);future.set_result({'success':True});return future
    driver.begin_write=write;driver.await_write=lambda future:future.result()
    broker=CommandBroker(driver,ownership=Ownership())
    token=broker.handle(request(owner='recovery'),'r')['lease_token']
    assert broker.handle(request('prepare_reset',owner='recovery',token=token),'r')['accepted']
    out=broker.handle(request('reset_world',owner='recovery',token=token,reset_request={'keyframe':'task_start'}),'r')
    assert out['accepted'] and out['reset_result']['success'] and len(writes)==1
    driver.stationary=False
    out=broker.handle(request('reset_world',owner='recovery',token=token,reset_request={'keyframe':'task_start'}),'r')
    assert not out['accepted'] and out['error']=='RESET_ALREADY_APPLIED' and len(writes)==1
    out=broker.handle(request('reset_world',owner='teacher',token=token,reset_request={'keyframe':'task_start'}),'other')
    assert not out['accepted'] and len(writes)==1


def test_competing_acquire_cannot_revoke_a_running_owner():
    driver=Driver();ownership=Ownership();broker=CommandBroker(driver,ownership=ownership)
    token=broker.handle(request(),'teacher')['lease_token'];driver.stationary=False
    competitor=broker.handle(request(owner='teleop'),'competitor')
    assert competitor['error']=='CONTROL_BUSY'
    ownership.require(token,'teacher','s','a')
    assert driver.stops==[]


def test_ros_stop_requires_real_negative_baseline_when_no_status_events():
    from concurrent.futures import Future
    from types import SimpleNamespace
    from so101_demo.adapters.act.ros_broker import RosBrokerDriver,ACTION_TYPES
    driver=object.__new__(RosBrokerDriver)
    driver.monotonic=lambda:10.;driver.max_age=1.5;driver.stop_velocity=.002
    driver._lock=threading.RLock();driver._records={};driver._pending_writes=[]
    driver._received=10.;driver._velocity=(0.,)*6;driver._statuses={};driver._status_received={}
    driver._cancel_all=[];driver._stop_confirmed_at=None
    driver.clients={k:SimpleNamespace(server_is_ready=lambda:True) for k in ACTION_TYPES}
    assert not driver.stopped()
    driver._stop_confirmed_at=10.
    assert driver.stopped()
    driver._stop_confirmed_at=8.
    assert not driver.stopped()
    driver._stop_confirmed_at=10.;driver._statuses={'arm':{'unknown':2}}
    assert not driver.stopped()
    driver._statuses={};driver._velocity=(.003,0.,0.,0.,0.,0.)
    assert not driver.stopped()


def test_act_raw_goal_requires_paired_supervised_prefix():
    driver=Driver();broker=CommandBroker(driver,ownership=Ownership())
    token=broker.handle(request(owner='act'),'act')['lease_token']
    for kind in ('arm','gripper','execute_trajectory'):
        out=broker.handle(request('submit',owner='act',token=token,
                                 action_kind=kind,goal={'trajectory':{}}),'act')
        assert not out['accepted'] and out['error']=='ACT_PREFIX_REQUIRED'
    assert driver.sent==[]


def test_paired_prefix_uses_trusted_executor_and_fences_old_lease():
    class Pair:
        def __init__(self):self.calls=[]
        def approve(self,ticket,prefix):self.calls.append(('approve',ticket,prefix));return {'permit':'trusted'}
        def submit(self,ticket,prefix,permit):self.calls.append(('submit',ticket,prefix,permit));return 'pair-goal'
        def invalidate(self,reason):self.calls.append(('invalidate',reason))
    pair=Pair();driver=Driver();owner=Ownership();broker=CommandBroker(driver,ownership=owner,prefix_executor=pair)
    token=broker.handle(request(owner='act'),'act')['lease_token']
    approved=broker.handle(request('approve_prefix',owner='act',token=token,prefix={'data':'p'}),'act')
    assert approved['accepted'] and approved['permit']=={'permit':'trusted'}
    out=broker.handle(request('submit_prefix',owner='act',token=token,prefix={'data':'p'},permit=approved['permit']),'act')
    assert out['accepted'] and out['goal_id']=='pair-goal'
    broker.handle(request('revoke',owner='act',token=token),'act')
    out=broker.handle(request('submit_prefix',owner='act',token=token,prefix={'data':'p'},permit=approved['permit']),'act')
    assert not out['accepted'] and len([c for c in pair.calls if c[0]=='submit'])==1


def test_running_approval_epoch_uses_atomic_live_evidence_not_paused_snapshot():
    from types import SimpleNamespace
    from so101_mujoco_support.msg import SimulationEvidence
    from so101_demo.adapters.act.ros_broker import RosBrokerDriver
    driver=object.__new__(RosBrokerDriver);driver._lock=threading.RLock()
    driver.monotonic=lambda:10.;driver.max_age=1.5;driver._received=10.
    driver._positions=(0.,)*6;driver._velocity=(0.,)*6;driver._epoch=None
    driver.current_reference=lambda when:(0.,)*6
    driver.node=SimpleNamespace(get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=2000000000)))
    message=SimulationEvidence(simulation_session_id='s',reset_epoch=3,paused=False)
    message.header.stamp.sec=2
    driver._live_epoch(message)
    snapshot=driver.approval_snapshot((2,'token','act','s','a'))
    assert snapshot['reset_epoch']==3 and snapshot['sim_time_s']==2.


def test_reset_transaction_fences_controller_writes_and_stop_can_interrupt_wait():
    from concurrent.futures import Future
    import time
    driver=Driver();writes=[];pending=Future()
    driver.validate_write=lambda operation,values:values
    driver.begin_write=lambda operation,values:(writes.append((operation,values)),pending)[1]
    driver.await_write=lambda future:future.result(timeout=1.)
    broker=CommandBroker(driver,ownership=Ownership())
    token=broker.handle(request(owner='recovery'),'r')['lease_token']
    assert broker.handle(request('prepare_reset',owner='recovery',token=token),'r')['accepted']
    denied=broker.handle(request('submit',owner='recovery',token=token,action_kind='arm',goal={'trajectory':{}}),'r')
    assert denied['error']=='RESET_IN_PROGRESS' and driver.sent==[]
    responses=[]
    worker=threading.Thread(target=lambda:responses.append(broker.handle(
        request('switch_controllers',owner='recovery',token=token,activate=[],deactivate=['arm_controller']),'r')))
    worker.start()
    until=time.monotonic()+1.
    while not writes and time.monotonic()<until:time.sleep(.001)
    assert writes
    assert broker.handle(request('revoke',owner='recovery',token=token),'stop')['accepted']
    pending.set_result({'ok':True});worker.join(timeout=1.)
    assert not worker.is_alive() and responses[0]['error']=='LEASE_GENERATION_INVALID'
    assert driver.stops


def test_act_cannot_pause_or_switch_controllers_and_reset_requires_preparation():
    driver=Driver();writes=[]
    driver.validate_write=lambda op,value:value
    driver.begin_write=lambda op,value:writes.append((op,value))
    broker=CommandBroker(driver,ownership=Ownership())
    token=broker.handle(request(owner='act'),'a')['lease_token']
    for req in (request('pause',owner='act',token=token,paused=True),
                request('switch_controllers',owner='act',token=token,activate=[],deactivate=['arm_controller'])):
        assert broker.handle(req,'a')['error']=='RESET_OWNER_INVALID'
    broker.handle(request('release',owner='act',token=token),'a')
    token=broker.handle(request(owner='teacher'),'t')['lease_token']
    out=broker.handle(request('reset_world',token=token,reset_request={}), 't')
    assert out['error']=='RESET_PREPARATION_REQUIRED' and writes==[]


def test_ros_reset_writes_validate_roles_and_require_acknowledged_deactivation():
    from mujoco_ros2_control_msgs.srv import SetPause,ResetWorld
    from so101_demo.adapters.act.ros_broker import RosBrokerDriver
    driver=object.__new__(RosBrokerDriver);driver._lock=threading.RLock()
    driver._pending_writes=[];driver._disabled_ack=False;driver._paused_ack=False
    driver._world_reset_ack=False;driver._activated_ack=False
    assert driver.validate_write('pause',{'paused':True}).paused is True
    for values in ({'paused':1},{'paused':False,'extra':1}):
        with pytest.raises(ValueError):driver.validate_write('pause',values)
    for activate,deactivate in ((['arm_controller'],[]),([],['unknown']),(['arm_controller'],['arm_controller'])):
        with pytest.raises(ValueError):driver.validate_write('switch_controllers',{'activate':activate,'deactivate':deactivate})
    with pytest.raises(PermissionError,match='RESET_CONTROLLERS_NOT_ACKNOWLEDGED'):
        driver.begin_write('reset_world',ResetWorld.Request())


def test_prepare_reset_refreshes_real_stop_proof_before_mutations():
    class RefreshDriver(Driver):
        def __init__(self):super().__init__();self.refreshes=0;self.prepared=False
        def refresh_idle(self):
            self.refreshes+=1
            if self.refreshes>=2:self.stationary=True
        def prepare_reset(self):assert self.stationary;self.prepared=True
    driver=RefreshDriver();broker=CommandBroker(driver,ownership=Ownership())
    token=broker.handle(request(),'owner')['lease_token'];driver.stationary=False
    result=broker.handle(request('prepare_reset',token=token),'owner')
    assert result['accepted'] and driver.prepared and driver.refreshes>=2
    assert not driver.sent and broker._reset_ticket is not None


def test_prepare_stop_proof_wait_is_generation_fenced_and_preemptible():
    reached=threading.Event();proceed=threading.Event()
    class RefreshDriver(Driver):
        def refresh_idle(self):reached.set()
        def prepare_reset(self):raise AssertionError('revoked reset must not prepare')
    driver=RefreshDriver();broker=CommandBroker(driver,ownership=Ownership())
    token=broker.handle(request(),'owner')['lease_token'];reached.clear();driver.stationary=False;out=[]
    worker=threading.Thread(target=lambda:out.append(broker.handle(request('prepare_reset',token=token),'owner')))
    worker.start()
    try:
        assert reached.wait(.5)
        revoked=broker.handle(request('revoke',token=token),'stop-independent')
        assert revoked['accepted'] and driver.stops
        worker.join(1)
        assert not worker.is_alive() and not out[0]['accepted']
        assert broker._reset_ticket is None and not driver.sent
    finally:
        driver.stationary=True;worker.join(6)


def test_execute_trajectory_uses_actual_installed_message_fields():
    from moveit_msgs.action import ExecuteTrajectory
    from trajectory_msgs.msg import JointTrajectoryPoint
    from so101_demo.adapters.act.leased_action_client import message_dict
    from so101_demo.adapters.act.ros_broker import validated_goal
    goal=ExecuteTrajectory.Goal()
    goal.trajectory.joint_trajectory.joint_names=['1','2','3','4','5']
    point=JointTrajectoryPoint(positions=[0.]*5);point.time_from_start.sec=1
    goal.trajectory.joint_trajectory.points=[point]
    result=validated_goal('execute_trajectory',message_dict(goal))
    assert list(result.trajectory.joint_trajectory.joint_names)==['1','2','3','4','5']
    if not hasattr(goal,'controllers'):
        with pytest.raises(ValueError,match='GOAL_FIELDS_INVALID'):
            validated_goal('execute_trajectory',dict(message_dict(goal),controllers=['arm_controller']))


def test_latched_driver_hazard_fences_acquire_even_after_actual_stop():
    driver=Driver();driver.hazard_reason='UNKNOWN_ACTIVE_GOAL';broker=CommandBroker(driver,ownership=Ownership())
    for _ in range(3):
        result=broker.handle(request(),'new-owner')
        assert not result['accepted'] and result['error']=='UNKNOWN_ACTIVE_GOAL'
        assert driver.stops and not driver.sent
    driver.hazard_reason=None
    assert not broker.handle(request(),'new-owner')['accepted']


def test_pair_invalidation_failure_still_calls_real_all_goal_stop():
    class BrokenPair:
        def invalidate(self,*args):raise RuntimeError('PAIR_CANCEL_LOST')
    driver=Driver();broker=CommandBroker(driver,ownership=Ownership(),prefix_executor=BrokenPair())
    token=broker.handle(request(owner='act'),'act')['lease_token']
    broker.handle(request('revoke',owner='act',token=token),'stop')
    assert driver.stops and not driver.sent


def test_moveit_downstream_status_is_recorded_and_pending_goal_is_rechecked():
    from types import SimpleNamespace
    from concurrent.futures import Future
    from action_msgs.msg import GoalStatusArray,GoalStatus
    from so101_demo.adapters.act.ros_broker import RosBrokerDriver
    driver=object.__new__(RosBrokerDriver);driver._lock=threading.RLock();driver.monotonic=lambda:10.
    driver._statuses={};driver._status_received={};driver.unknown_goal_seen=False;driver.hazard_reason=None
    execute=dict(kind='execute_trajectory',accepted=True,result=None)
    driver._records={'execute':execute}
    status=GoalStatus(status=2);status.goal_info.goal_id.uuid=[3]*16
    message=GoalStatusArray(status_list=[status]);driver._status('arm',message)
    assert not driver.unknown_goal_seen
    assert ('03'*16) in execute['downstream_goal_ids']['arm']
    execute['result']=SimpleNamespace(status=4);driver._status('arm',message)
    assert not driver.unknown_goal_seen
    pending=dict(kind='gripper',accepted=None,result=None,cancel_requested=False)
    driver._records['pending']=pending;driver._status('gripper',message)
    assert not driver.unknown_goal_seen
    response=Future();response.set_result(SimpleNamespace(accepted=False))
    driver._accepted('pending',response)
    assert driver.unknown_goal_seen and driver.hazard_reason=='UNKNOWN_ACTIVE_GOAL'


def test_initial_pair_binding_after_prelease_stop_requires_fresh_stop_confirmation():
    from so101_demo.adapters.act.broker_execution import BrokerPairedExecution
    driver=Driver();ownership=Ownership();broker=CommandBroker(driver,ownership=ownership)
    paired=BrokerPairedExecution(broker,snapshot_port=lambda ticket:None,
        check_port=lambda p,s:True,reference_port=lambda t:(0.,)*6,sim_clock=lambda:1.,
        submit_lead_s=.04,accept_timeout_s=.03,stop_timeout_s=1.,permit_ttl_s=.1)
    broker.prefix_executor=paired
    # A negative-baseline refresh can invalidate the adapter before its first
    # owner has ever bound. No controller goals have been sent.
    driver.stationary=False
    assert broker.handle(request(owner='act'),'c')['error']=='CONTROL_NOT_STOPPED'
    assert paired.adapter.state=='STOPPING' and paired._ticket is None
    driver.stationary=True;broker.tick()
    token=broker.handle(request(owner='act'),'c')['lease_token']
    ticket=ownership.ticket(token,'act','s','a')
    paired._bind(ticket)
    assert paired.adapter.state=='READY' and paired._ticket==ticket
    assert driver.sent==[]


def test_initial_pair_binding_cannot_clear_unconfirmed_prelease_stop():
    from so101_demo.adapters.act.broker_execution import BrokerPairedExecution
    driver=Driver();ownership=Ownership();broker=CommandBroker(driver,ownership=ownership)
    paired=BrokerPairedExecution(broker,snapshot_port=lambda ticket:None,
        check_port=lambda p,s:True,reference_port=lambda t:(0.,)*6,sim_clock=lambda:1.,
        submit_lead_s=.04,accept_timeout_s=.03,stop_timeout_s=1.,permit_ttl_s=.1)
    token=broker.handle(request(owner='act'),'c')['lease_token']
    paired.invalidate('PRELEASE_STOP');driver.stationary=False
    with pytest.raises(RuntimeError,match='CONTROL_NOT_STOPPED'):
        paired._bind(ownership.ticket(token,'act','s','a'))
    assert paired._ticket is None and driver.sent==[]


def test_inherited_rpc_reads_large_response_in_bounded_chunks_without_stealing_next_reply(monkeypatch):
    import json,socket
    from so101_demo.adapters.act.leased_action_client import BrokerConnection
    import so101_demo.adapters.act.leased_action_client as module
    client,server=socket.socketpair();ids=iter(('first','second'))
    monkeypatch.setattr(module.uuid,'uuid4',lambda:next(ids))
    payload={'request_id':'first','accepted':True,'audit':'é'*10000}
    second={'request_id':'second','accepted':True,'audit':'next-client'}
    # Deliberately queue two replies on the shared FD. Each process's read
    # must end exactly at its own newline, without retaining the other's bytes.
    server.sendall((json.dumps(payload)+'\n'+json.dumps(second)+'\n').encode())
    connection=BrokerConnection('/data/work/so101-evidence/act-data/0917a/r/read-probe',connection_fd=client.fileno())
    class CountedSocket:
        def __init__(self,wrapped):self.wrapped=wrapped;self.reads=0
        def recv(self,*args):self.reads+=1;return self.wrapped.recv(*args)
        def __getattr__(self,name):return getattr(self.wrapped,name)
    counted=CountedSocket(connection.socket);connection.socket=counted
    ctx=dict(owner='act',session_id='s',attempt_id='a',lease_token='x')
    try:
        assert connection.request('status',ctx)==payload
        assert connection.request('status',ctx)==second
        assert counted.reads<=8,'Byte-by-byte syscalls defeat the 0.1-second control grid'
    finally:connection.close();client.close();server.close()
