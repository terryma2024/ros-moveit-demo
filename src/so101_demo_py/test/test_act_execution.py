"""Paired control uses common simulation times and fails closed on either side."""
import copy
import pytest
from so101_demo.act.execution import ActExecutionAdapter, prefix_sha256, split_positions

class Clock:
    sim=1.; wall=10.
    def progress(self): self.sim+=.005; self.wall+=.005

class Port:
    def __init__(self,accepted=True):
        self.accept=accepted; self.goals=[]; self.cancels=[]; self.stationary=True
    def send(self,goal): self.goals.append(goal); return str(len(self.goals))
    def accepted(self,goal_id): return self.accept
    def cancel(self,goal_id): self.cancels.append(goal_id)
    def stopped(self): return bool(self.cancels) and self.stationary

class Permits:
    def __init__(self): self.calls=[]; self.revoked=False
    def require(self,permit,prefix):
        if self.revoked or permit.get('prefix_sha256')!=prefix_sha256(prefix): raise PermissionError('PERMIT_INVALID')
        self.calls.append(prefix)
    def revoke(self,reason): self.revoked=True


def prefix(sequence=0):
    return dict(session_id='s',attempt_id='a',sequence=sequence,observation_time_s=1.,
                target_times_s=(1.1,1.2),positions=((.01,)*6,(.02,)*6))

def setup(arm=None,grip=None):
    clock=Clock(); arm=arm or Port(); grip=grip or Port(); permits=Permits()
    adapter=ActExecutionAdapter(arm,grip,permit_port=permits,sim_clock=lambda:clock.sim,
        monotonic=lambda:clock.wall,progress=clock.progress,submit_lead_s=.03,
        accept_timeout_s=.02,stop_timeout_s=.03,reference_port=lambda t:(0.,)*6)
    adapter.begin_attempt('s','a')
    return adapter,clock,arm,grip,permits

def submit(adapter,p=None):
    p=p or prefix(); return adapter.submit(p,dict(prefix_sha256=prefix_sha256(p)))


def test_same_rows_reach_arm_and_gripper():
    assert split_positions(((1.,2.,3.,4.,5.,6.),))==(((1.,2.,3.,4.,5.),),((6.,),))
    with pytest.raises(ValueError): split_positions(((0.,)*5,))


def test_same_header_and_absolute_grid_with_held_reference():
    adapter,clock,arm,grip,_=setup(); submit(adapter)
    a,g=arm.goals[0],grip.goals[0]
    assert a['header_stamp_s']==g['header_stamp_s']==pytest.approx(1.03)
    assert a['time_from_start_s']==g['time_from_start_s']==pytest.approx((0.,.07,.17))
    assert a['positions']==((0.,)*5,(.01,)*5,(.02,)*5)
    assert g['positions']==((0.,),(.01,),(.02,))
    assert adapter.current_goal_ids==('1','1')


@pytest.mark.parametrize('accepted',(False,None))
def test_partial_acceptance_or_timeout_cancels_both_and_latches(accepted):
    adapter,clock,arm,grip,_=setup(grip=Port(accepted))
    with pytest.raises(RuntimeError,match='CONTROLLER_PAIR_FAILED'): submit(adapter)
    assert arm.cancels==grip.cancels==['1']
    assert adapter.state=='STOPPED'
    with pytest.raises(RuntimeError): submit(adapter,prefix(1))
    assert len(arm.goals)==len(grip.goals)==1


def test_cancel_ack_without_physical_stop_keeps_stopping():
    adapter,clock,arm,grip,_=setup(); submit(adapter); arm.stationary=False
    assert adapter.stop('hazard')=='STOPPING'
    assert arm.cancels==grip.cancels==['1']
    with pytest.raises(RuntimeError): adapter.begin_attempt('s','b')
    with pytest.raises(RuntimeError): submit(adapter,prefix(1))
    arm.stationary=True
    assert adapter.poll_stop()=='STOPPED'


def test_late_attempt_sequence_reused_permit_and_content_mutation_rejected():
    adapter,clock,arm,grip,permits=setup(); submit(adapter)
    for p in (prefix(),dict(prefix(1),attempt_id='old')):
        with pytest.raises((RuntimeError,ValueError)): submit(adapter,p)
    p=prefix(1); stale=dict(prefix_sha256=prefix_sha256(p)); p['positions']=((.03,)*6,(.04,)*6)
    with pytest.raises(PermissionError): adapter.submit(p,stale)
    assert len(arm.goals)==1
    adapter.stop('timeout')
    with pytest.raises(RuntimeError): submit(adapter,prefix(2))


def test_replacement_uses_controller_reference_at_common_future_start():
    adapter,clock,arm,grip,_=setup(); submit(adapter)
    adapter.reference_port=lambda t:(.015,)*6
    submit(adapter,prefix(1))
    assert arm.cancels==grip.cancels==['1']
    assert arm.goals[-1]['positions'][0]==(.015,)*5
    assert grip.goals[-1]['positions'][0]==(.015,)


def test_late_acceptance_and_invalid_reference_cannot_start_unapproved_motion():
    adapter,clock,arm,grip,_=setup(); clock.sim=1.08
    with pytest.raises(ValueError,match='PREFIX_LATE'): submit(adapter)
    assert arm.goals==grip.goals==[]
    adapter.reference_port=lambda t:(float('nan'),)*6
    clock.sim=1.
    with pytest.raises(ValueError): submit(adapter)
    assert arm.goals==[]


def test_ros_wire_has_common_sim_stamp_and_no_wall_time():
    from so101_demo.adapters.act.ros_execution import trajectory_message
    goal=dict(joint_names=('1','2'),header_stamp_s=4.25,
              time_from_start_s=(0.,.1),positions=((.1,.2),(.2,.3)))
    wire=trajectory_message(goal)
    assert (wire.header.stamp.sec,wire.header.stamp.nanosec)==(4,250000000)
    assert wire.joint_names==['1','2']
    assert [(p.time_from_start.sec,p.time_from_start.nanosec) for p in wire.points]==[(0,0),(0,100000000)]
    assert list(wire.points[0].velocities)==[]  # frozen JTC position-only linear interpolation


def test_pending_ros_goal_accepted_after_cancel_is_cancelled_and_waits_terminal_velocity():
    from types import SimpleNamespace
    from concurrent.futures import Future
    from sensor_msgs.msg import JointState
    from so101_demo.adapters.act.ros_execution import RosControllerPort
    class Node:
        def create_subscription(self,*args):return None
    response=Future(); result=Future(); cancelled=Future(); calls=[]
    handle=SimpleNamespace(accepted=True,get_result_async=lambda:result,
        cancel_goal_async=lambda:(calls.append('cancel'),cancelled)[1])
    client=SimpleNamespace(send_goal_async=lambda message:response)
    port=RosControllerPort(Node(),client,('6',),stop_velocity_rad_s=.001,max_age_s=.2,
                           monotonic=lambda:10.)
    gid=port.send(dict(joint_names=('6',),header_stamp_s=1.1,time_from_start_s=(0.,.1),
                       positions=((.1,),(.2,))))
    port.cancel(gid);assert port.accepted(gid) is None and not port.stopped()
    response.set_result(handle);assert calls==['cancel']
    port._feedback(JointState(name=['6'],velocity=[0.]))
    cancelled.set_result(SimpleNamespace(return_code=0));assert not port.stopped()
    result.set_result(SimpleNamespace(status=5,result=SimpleNamespace(error_code=-4)))
    assert port.stopped() and port.result(gid).result.error_code==-4
    port._feedback(JointState(name=['6'],velocity=[.1]));assert not port.stopped()


@pytest.mark.parametrize('lost_at',('send','response'))
def test_unknown_goal_send_or_response_never_establishes_rejection_or_stop(lost_at):
    from types import SimpleNamespace
    from concurrent.futures import Future
    from sensor_msgs.msg import JointState
    from so101_demo.adapters.act.ros_execution import RosControllerPort
    response=Future()
    class Client:
        def send_goal_async(self,goal):
            if lost_at=='send':raise OSError('uncertain send')
            return response
    node=SimpleNamespace(create_subscription=lambda *args:None)
    port=RosControllerPort(node,Client(),('6',),stop_velocity_rad_s=.002,max_age_s=.15,monotonic=lambda:10.)
    goal=dict(joint_names=('6',),header_stamp_s=1.1,time_from_start_s=(0.,.1),positions=((.1,),(.2,)))
    if lost_at=='send':
        with pytest.raises(OSError):port.send(goal)
    else:
        port.send(goal);response.set_exception(OSError('unknown response'))
    port._feedback(JointState(name=['6'],velocity=[0.]))
    assert list(port._goals.values())[0]['accepted'] is None
    assert not port.stopped()


@pytest.mark.parametrize('boundary',('permit','reference','path'))
def test_stop_preempts_blocked_preparation_before_any_goal_is_forwarded(boundary):
    import threading
    adapter,clock,arm,grip,_=setup();entered=threading.Event();release=threading.Event();stopped=threading.Event();errors=[]
    def delayed(*args):entered.set();release.wait(1.);return True if boundary=='path' else (0.,)*6
    if boundary=='permit':adapter.permit_port.require=delayed
    elif boundary=='reference':adapter.reference_port=delayed
    else:adapter.path_port=delayed
    def run():
        try:submit(adapter)
        except RuntimeError as error:errors.append(str(error))
    worker=threading.Thread(target=run);worker.start();assert entered.wait(.2)
    stopper=threading.Thread(target=lambda:(adapter.invalidate('robot_contact'),stopped.set()));stopper.start()
    try:assert stopped.wait(.05),'Stop blocked behind prefix preparation'
    finally:release.set();worker.join(.2);stopper.join(.2)
    assert not worker.is_alive() and errors and arm.goals==grip.goals==[]


def test_exact_goals_are_path_checked_before_any_send():
    adapter,clock,arm,grip,_=setup();checked=[]
    def reject(goals,p):
        checked.append((goals,p));return False
    adapter.path_port=reject
    with pytest.raises(PermissionError,match='PATH_REJECTED'):submit(adapter)
    assert arm.goals==grip.goals==[] and len(checked)==1
    goals,p=checked[0]
    assert goals[0]['header_stamp_s']==goals[1]['header_stamp_s']==1.03
    assert goals[0]['positions'][0]+goals[1]['positions'][0]==(0.,)*6
    assert p==prefix()
