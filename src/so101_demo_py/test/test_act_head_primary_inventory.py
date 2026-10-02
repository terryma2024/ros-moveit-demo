"""Pre-native UUIDs remain in the original port through every SDK/fault stage."""
import hashlib
import json
import time
import uuid

import pytest
from rosidl_runtime_py.convert import message_to_ordereddict
from test_act_head_feedback_freshness import setup_ports,sample
from test_act_head_prepared_sdk import prepared


def inventory(message,goal_uuid,cdr):
    claim=time.monotonic_ns()-1_000_000
    return dict(goal_uuid=str(uuid.UUID(bytes=bytes(goal_uuid.uuid))),typed_goal=json.loads(json.dumps(message_to_ordereddict(message))),
        payload_sha256=hashlib.sha256(cdr).hexdigest(),generation=5,
        controller_identity=dict(generation=5,incarnation='inc',boot='boot'),attempt_epoch='attempt',
        session_id='session',role='neck',operation_sequence=1,claim_monotonic_ns=claim,deadline_ns=claim+400_000_000)


def test_pre_native_inventory_is_adopted_without_replacing_unknown_record(monkeypatch):
    _,_,port,_,_,calls,subscriptions=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();record=inventory(message,goal_uuid,cdr)
    faults=[];port._head_fault_callback=faults.append
    try:
        assert port.inventory_prepared(record,cdr) is True
        gid=record['goal_uuid'];original=port._goals[gid]
        assert port.accepted(gid) is None and port.result(gid) is None
        assert port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=lambda:True)==gid
        assert port._goals[gid] is original and len(subscriptions)==1 and not faults
        assert len([row for row in calls if row[0]=='send'])==1
        with pytest.raises(PermissionError):port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=lambda:True)
        assert port._goals[gid] is original
    finally:port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('damage',['cdr','typed_goal','extra','claim_window','expiry','role','uuid','sequence'])
def test_invalid_inventory_consumes_primary_without_inventing_send_or_rejection(monkeypatch,damage):
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();record=inventory(message,goal_uuid,cdr);faults=[]
    port._head_fault_callback=faults.append
    if damage=='cdr':cdr=cdr[:-1]+bytes([cdr[-1]^1])
    elif damage=='typed_goal':record['typed_goal']['goal_time_tolerance']['nanosec']+=1
    elif damage=='extra':record['extra']=True
    elif damage=='claim_window':record['deadline_ns']+=1
    elif damage=='expiry':record['claim_monotonic_ns']-=500_000_000;record['deadline_ns']-=500_000_000
    elif damage=='role':record['role']='arm'
    elif damage=='uuid':record['goal_uuid']='invalid'
    else:record['operation_sequence']=2
    try:
        with pytest.raises((PermissionError,ValueError)):port.inventory_prepared(record,cdr)
        assert faults and port._head_policy_binding_failed
        assert not [row for row in calls if row[0]=='send']
    finally:port.close_head_io(timeout_s=1.)


def test_reused_inventory_cannot_overwrite_original_unknown_uuid(monkeypatch):
    _,_,port,_,_,_,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();record=inventory(message,goal_uuid,cdr);port._head_fault_callback=lambda reason:None
    try:
        port.inventory_prepared(record,cdr);original=port._goals[record['goal_uuid']]
        with pytest.raises(PermissionError):port.inventory_prepared(record,cdr)
        assert port._goals[record['goal_uuid']] is original and port.accepted(record['goal_uuid']) is None
    finally:port.close_head_io(timeout_s=1.)


def test_native_inventory_failure_cannot_erase_pre_sdk_uuid_from_stop_proof(monkeypatch):
    _,_,port,wall,sim,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();record=inventory(message,goal_uuid,cdr);port._head_fault_callback=lambda reason:None
    try:
        port.inventory_prepared(record,cdr)
        guards=[]
        with pytest.raises(PermissionError):port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,
            dispatch_guard=lambda:(guards.append(record['goal_uuid']) or False))
        port.begin_stop(dict(epoch='stop',generation=5,request_wall_s=10.,request_sim_s=1.,fault_wall_s=10.,stop_latency_s=.07))
        for index in range(1,4):
            wall[0]=10.+index*.01;sim[0]=1.+index*.01;port._feedback(sample(sim[0]))
        assert guards==[record['goal_uuid']]
        assert port.stopped() is False
        proof=port.stop_predicate_observations[-1]
        assert proof['goal_states'][record['goal_uuid']]['accepted'] is None
        assert proof['goal_states'][record['goal_uuid']]['terminal_status'] is None
        assert not [row for row in calls if row[0]=='send']
    finally:port.close_head_io(timeout_s=1.)


def test_sdk_adoption_never_serializes_inventory_under_feedback_cache(monkeypatch):
    from so101_demo.act import head_monitor
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();record=inventory(message,goal_uuid,cdr);port._head_fault_callback=lambda reason:None
    try:
        port.inventory_prepared(record,cdr)
        original=head_monitor.canonical_bytes
        def without_cache(value):
            assert not port._lock._is_owned(),'inventory serialization held original feedback cache'
            return original(value)
        monkeypatch.setattr(head_monitor,'canonical_bytes',without_cache)
        port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=lambda:True)
        assert len([row for row in calls if row[0]=='send'])==1
    finally:port.close_head_io(timeout_s=1.)


def test_inventory_claim_expiring_after_monitor_guard_prevents_sdk(monkeypatch):
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();record=inventory(message,goal_uuid,cdr);port._head_fault_callback=lambda reason:None
    try:
        port.inventory_prepared(record,cdr)
        def guard():
            monkeypatch.setattr(time,'monotonic_ns',lambda:record['deadline_ns']+1)
            return True
        with pytest.raises(PermissionError):port.send_prepared(message,goal_uuid=goal_uuid,expected_cdr=cdr,dispatch_guard=guard)
        assert not [row for row in calls if row[0]=='send']
        assert port.accepted(record['goal_uuid']) is None and port.result(record['goal_uuid']) is None
    finally:port.close_head_io(timeout_s=1.)


@pytest.mark.parametrize('field',['attempt_epoch','session_id','generation'])
def test_second_inventory_cannot_rebind_primary_scope(monkeypatch,field):
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();record=inventory(message,goal_uuid,cdr);port._head_fault_callback=lambda reason:None
    try:
        port.inventory_prepared(record,cdr)
        second_message,second_uuid,second_cdr=prepared();second=inventory(second_message,second_uuid,second_cdr)
        second['operation_sequence']=2
        if field=='generation':second['generation']=6;second['controller_identity']['generation']=6
        else:second[field]='foreign'
        with pytest.raises(PermissionError):port.inventory_prepared(second,second_cdr)
        assert len(port._goals)==1 and port.accepted(record['goal_uuid']) is None
        assert not [row for row in calls if row[0]=='send']
    finally:port.close_head_io(timeout_s=1.)


def test_changed_complete_goal_cannot_adopt_original_uuid_even_with_matching_new_cdr(monkeypatch):
    from rclpy.serialization import serialize_message
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    message,goal_uuid,cdr=prepared();record=inventory(message,goal_uuid,cdr);port._head_fault_callback=lambda reason:None
    try:
        port.inventory_prepared(record,cdr);original=port._goals[record['goal_uuid']]
        message.goal_tolerance[0].position+=.1
        with pytest.raises(PermissionError):port.send_prepared(message,goal_uuid=goal_uuid,
            expected_cdr=serialize_message(message),dispatch_guard=lambda:True)
        assert port._goals[record['goal_uuid']] is original and port.accepted(record['goal_uuid']) is None
        assert not [row for row in calls if row[0]=='send']
    finally:port.close_head_io(timeout_s=1.)
