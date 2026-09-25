"""Search owns only the neck controller and requires scoped fresh measured feedback."""
from types import SimpleNamespace
from concurrent.futures import Future
import pytest
from sensor_msgs.msg import JointState
from so101_demo.adapters.act.ros_neck import RosNeckSearchPort


def make(monkeypatch,guard=lambda *args:True,ready=True):
    from so101_demo.adapters.act import ros_neck
    calls=[];response=Future();result=Future()
    class Client:
        def __init__(self,node,kind,name):calls.append(('endpoint',name))
        def server_is_ready(self):return ready
        def send_goal_async(self,msg):calls.append(('goal',msg));return response
    monkeypatch.setattr(ros_neck,'ActionClient',Client)
    node=SimpleNamespace(create_subscription=lambda *args:None,
        get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=1000000000)))
    now=[10.]
    port=RosNeckSearchPort(node,session_id='s',attempt_id='a',goal_duration_s=.5,submit_lead_s=.04,
        stop_timeout_s=.1,stop_velocity_rad_s=.002,max_age_s=.15,command_guard=guard,monotonic=lambda:now[0])
    joint=JointState(name=['neck_yaw_joint'],position=[.2],velocity=[0.]);joint.header.stamp.sec=1
    port._joint(joint)
    return port,calls,response,result,now


def test_neck_goal_has_only_neck_future_header_and_absolute_target(monkeypatch):
    port,calls,*_=make(monkeypatch)
    port.command_neck(.7,session_id='s',attempt_id='a',observation_time_s=1.)
    assert calls[0]==('endpoint','/neck_controller/follow_joint_trajectory')
    goal=calls[1][1].trajectory
    assert list(goal.joint_names)==['neck_yaw_joint'] and goal.header.stamp.nanosec==40000000
    assert [list(p.positions) for p in goal.points]==[[.2],[.7]]
    assert goal.points[1].time_from_start.nanosec==500000000


def test_neck_search_can_use_only_the_existing_broker_client(monkeypatch):
    from so101_demo.adapters.act import ros_neck
    monkeypatch.setattr(ros_neck,'ActionClient',lambda *args:pytest.fail('second neck client'))
    sent=[];cancelled=[]
    client=SimpleNamespace(server_is_ready=lambda:True)
    driver=SimpleNamespace(clients={'neck':client},cancel=lambda gid:cancelled.append(gid),
                           stopped=lambda:True,refresh_stop=lambda:None)
    broker=SimpleNamespace(driver=driver,dispatch=lambda ticket,kind,goal:
                           (sent.append((ticket,kind,goal)) or 'neck-goal'))
    node=SimpleNamespace(create_subscription=lambda *args:None,
        get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(nanoseconds=1000000000)))
    ticket=[(1,'lease','act','s','a')]
    port=RosNeckSearchPort(node,session_id='s',attempt_id='a',goal_duration_s=.5,
        submit_lead_s=.04,stop_timeout_s=.1,stop_velocity_rad_s=.002,max_age_s=.15,
        command_guard=lambda *args:True,monotonic=lambda:10.,
        broker=broker,ticket_port=lambda:ticket[0])
    joint=JointState(name=['neck_yaw_joint'],position=[.2],velocity=[0.])
    joint.header.stamp.sec=1
    port._joint(joint)
    assert port.command_neck(.7,session_id='s',attempt_id='a',observation_time_s=1.)=='neck-goal'
    assert sent[0][0]==(1,'lease','act','s','a') and sent[0][1]=='neck'
    assert list(sent[0][2].trajectory.joint_names)==['neck_yaw_joint']
    ticket[0]=(1,'lease','act','other','a')
    with pytest.raises(PermissionError,match='NECK_SCOPE_INVALID'):
        port.command_neck(.6,session_id='s',attempt_id='a',observation_time_s=1.)
    assert len(sent)==1
    assert port.stop_and_confirm() is True and cancelled==['neck-goal']


@pytest.mark.parametrize('kwargs',({'session_id':'old','attempt_id':'a','observation_time_s':1.},
    {'session_id':'s','attempt_id':'old','observation_time_s':1.},
    {'session_id':'s','attempt_id':'a','observation_time_s':1.1}))
def test_old_scope_or_future_observation_never_sends_goal(monkeypatch,kwargs):
    port,calls,*_=make(monkeypatch)
    with pytest.raises((PermissionError,ValueError)):port.command_neck(.7,**kwargs)
    assert len(calls)==1


def test_missing_stale_unsafe_neck_command_is_rejected(monkeypatch):
    port,calls,*tail=make(monkeypatch,guard=lambda *args:False)
    with pytest.raises(PermissionError,match='SEARCH_UNSAFE_MOTION'):
        port.command_neck(.7,session_id='s',attempt_id='a',observation_time_s=1.)
    tail[-1][0]=10.2
    with pytest.raises(PermissionError,match='NECK_FEEDBACK_STALE'):
        port.command_neck(.7,session_id='s',attempt_id='a',observation_time_s=1.)
    assert len(calls)==1


def test_neck_command_refuses_undiscovered_action_server(monkeypatch):
    port,calls,*_=make(monkeypatch,ready=False)
    with pytest.raises(RuntimeError,match='NECK_ACTION_SERVER_UNAVAILABLE'):
        port.command_neck(.7,session_id='s',attempt_id='a',observation_time_s=1.)
    assert calls==[('endpoint','/neck_controller/follow_joint_trajectory')]
