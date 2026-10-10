"""Frozen native-bound Head goals reach the SDK only under current guards."""
import uuid
from types import SimpleNamespace

import pytest
from control_msgs.action import FollowJointTrajectory
from control_msgs.msg import JointTolerance
from rclpy.serialization import serialize_message
from unique_identifier_msgs.msg import UUID

from test_act_head_feedback_freshness import setup_ports, sample
from so101_demo.adapters.act.ros_execution import trajectory_message


def prepared():
    goal=dict(joint_names=('neck_yaw_joint',),header_stamp_s=1.004,
              time_from_start_s=(0.,.05),positions=((.2,),(.3,)))
    message=FollowJointTrajectory.Goal(trajectory=trajectory_message(goal))
    message.path_tolerance=[JointTolerance(name='neck_yaw_joint',position=.01,velocity=.02)]
    message.goal_tolerance=[JointTolerance(name='neck_yaw_joint',position=.03,velocity=.04)]
    message.goal_time_tolerance.nanosec=12_000_000
    goal_uuid=UUID(uuid=list(uuid.uuid4().bytes))
    return message,goal_uuid,serialize_message(message)


def test_complete_original_message_and_uuid_reach_sdk_without_reconstruction(monkeypatch):
    _,_,port,_,_,calls,subscriptions=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();guards=[]
    def guard():guards.append('checked');return True
    try:
        gid=port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=guard)
        sent=[row for row in calls if row[0]=='send']
        assert guards==['checked'] and len(sent)==1
        assert sent[0][1] is message and serialize_message(sent[0][1])==cdr
        assert bytes(sent[0][2]['goal_uuid'].uuid)==bytes(goal_uuid.uuid)
        assert gid==str(uuid.UUID(bytes=bytes(goal_uuid.uuid)))
        assert port.accepted(gid) is None and len(subscriptions)==1
    finally:port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('outcome',['false','none','exception'])
def test_last_guard_failure_prevents_sdk_and_consumes_local_admission(monkeypatch,outcome):
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared()
    def guard():
        if outcome=='exception':raise PermissionError('monitor irrevocably revoked')
        return False if outcome=='false' else None
    try:
        with pytest.raises((PermissionError,ValueError)):
            port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=guard)
        assert not [row for row in calls if row[0]=='send']
        assert port._head_policy_binding_failed
        with pytest.raises(PermissionError):port.send({})
    finally:port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('damage',['target','header','tolerance','raw_digest'])
def test_changed_field_or_raw_bytes_never_reach_sdk(monkeypatch,damage):
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared()
    if damage=='target':message.trajectory.points[1].positions=[9.]
    elif damage=='header':message.trajectory.header.stamp.nanosec+=1
    elif damage=='tolerance':message.goal_tolerance[0].velocity+=.01
    else:cdr=cdr[:-1]+bytes((cdr[-1]^1,))
    try:
        with pytest.raises((PermissionError,ValueError)):
            port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=lambda:True)
        assert not [row for row in calls if row[0]=='send'] and port._head_policy_binding_failed
    finally:port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('clock',['receipt','source'])
def test_feedback_that_expires_during_last_guard_prevents_sdk(monkeypatch,clock):
    _,_,port,wall,sim,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared()
    def guard():
        if clock=='receipt':wall[0]+=.021
        else:sim[0]+=.021
        return True
    try:
        with pytest.raises((PermissionError,ValueError)):
            port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=guard)
        assert not [row for row in calls if row[0]=='send']
    finally:port.close_head_io(timeout_s=1.)


def test_guard_runs_outside_feedback_cache_lock(monkeypatch):
    _,_,port,_,_,_,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared()
    def guard():
        assert not port._lock._is_owned()
        return True
    try:port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=guard)
    finally:port.close_head_io(timeout_s=1.)


def test_same_action_uuid_cannot_replace_pending_sdk_operation(monkeypatch):
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared()
    try:
        gid=port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=lambda:True)
        original=port._goals[gid]
        with pytest.raises((PermissionError,ValueError)):
            port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=lambda:True)
        assert port._goals[gid] is original and port.accepted(gid) is None
        assert len([row for row in calls if row[0]=='send'])==1
    finally:port.close_head_io(timeout_s=1.)


def test_sdk_exception_preserves_unknown_uuid_and_closes_admission(monkeypatch):
    _,client,port,_,_,_,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();gid=str(uuid.UUID(bytes=bytes(goal_uuid.uuid)))
    def stalled_sdk(*args,**kwargs):raise RuntimeError('SDK dispatch outcome is unknown')
    client.send_goal_async=stalled_sdk
    try:
        with pytest.raises(RuntimeError):
            port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=lambda:True)
        assert port.accepted(gid) is None and port._goals[gid]['error']
        assert port._head_policy_binding_failed
    finally:port.close_head_io(timeout_s=1.)


def test_caller_uuid_mutation_during_guard_cannot_change_frozen_sdk_uuid(monkeypatch):
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();original=bytes(goal_uuid.uuid)
    def guard():goal_uuid.uuid=list(uuid.uuid4().bytes);return True
    try:
        gid=port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=guard)
        sent=[row for row in calls if row[0]=='send']
        assert bytes(sent[0][2]['goal_uuid'].uuid)==original
        assert gid==str(uuid.UUID(bytes=original))
    finally:port.close_head_io(timeout_s=1.)


def test_message_mutation_during_guard_is_refused_before_sdk(monkeypatch):
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared()
    def guard():message.goal_time_tolerance.nanosec+=1;return True
    try:
        with pytest.raises(ValueError):
            port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=guard)
        assert not [row for row in calls if row[0]=='send']
    finally:port.close_head_io(timeout_s=1.)


def test_failed_fault_reporter_cannot_reopen_admission_or_hold_cache(monkeypatch):
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();observed=[]
    def reporter(reason):
        observed.append((reason,port._head_policy_binding_failed,port._lock._is_owned()))
        raise OSError('reporter unavailable')
    port._head_fault_callback=reporter
    try:
        with pytest.raises(PermissionError):
            port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=lambda:False)
        assert observed==[('HEAD_PREPARED_DISPATCH_FAILED',True,False)]
        assert port._head_fault_handler_error and not [row for row in calls if row[0]=='send']
    finally:port.close_head_io(timeout_s=1.)


def test_fault_report_precedes_any_exception_formatting(monkeypatch):
    _,_,port,_,_,_,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();reported=[]
    class DiagnosticError(PermissionError):
        def __repr__(self):
            assert reported, 'exception formatting preceded independent fault request'
            assert not port._lock._is_owned()
            return 'diagnostic failure'
    port._head_fault_callback=lambda reason:reported.append(reason)
    def guard():raise DiagnosticError('guard failed')
    try:
        with pytest.raises(DiagnosticError):
            port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=guard)
        assert reported==['HEAD_PREPARED_DISPATCH_FAILED'] and port._head_policy_binding_failed
    finally:port.close_head_io(timeout_s=1.)
