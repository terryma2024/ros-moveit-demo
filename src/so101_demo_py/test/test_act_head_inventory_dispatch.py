"""Actual goal codecs and epoch ACKs order Head's primary dispatch boundary.

Native replies and SDK calls are controlled peers; no runtime qualification.
"""
import base64

import pytest

from test_act_head_search_restarts import socket_root, reservation_authority
from test_act_head_feedback_freshness import setup_ports, sample, policy
from so101_demo.act.head_monitor import HeadMonitorEpoch
from so101_demo.act.head_search_restarts import RestartRefused
from so101_demo.adapters.act.head_monitor_goal_binding import validate_goal_inventory
from so101_demo.adapters.act.head_inventory_dispatch import HeadInventoryDispatcher


class Monitor:
    identity=dict(uid=1000,pid=202,start_ticks=303)
    def __init__(self,identity,events,damage=None):
        self.events=events;self.damage=damage
        self.epoch=HeadMonitorEpoch(epoch='attempt',generation=11,session_id='head-search-restarts')
        self.epoch.bind_policy(policy(),'a'*64);self.epoch.armed_ready(identity,identity)
    def request_runtime(self,request):
        operation=request['operation'];self.events.append(operation)
        if operation=='REGISTER':
            inventory=request['inventory']
            record=validate_goal_inventory(inventory['record'],base64.b64decode(inventory['goal_cdr_base64']))
            reply=self.epoch.register(record)
        else:
            assert operation=='DISPATCH'
            binding=request['binding'];self.epoch.require_dispatch(binding['goal_uuid'],binding['inventory_sha256'])
            reply=dict(epoch='attempt',**binding)
        reply=dict(reply,request=operation,stage='ARMED_READY',generation=11,
            session_id='head-search-restarts',purpose='calibration',motion_authority=False,
            monitor_peer=dict(self.identity))
        if self.damage is not None and operation=='REGISTER':
            key,value=self.damage;reply[key]=value
        return reply


@pytest.fixture
def composed(socket_root,monkeypatch):
    authority,servers=reservation_authority(socket_root);identity=authority.identity('neck')
    _,_,port,_,_,calls,_=setup_ports(monkeypatch);port._feedback(sample())
    events=[];owned=[];faults=[];monitor=Monitor(identity,events)
    exchange=authority._exchange
    def native(role,frame,*,expect):
        if frame[4:8]==b'SOGB':events.append('NATIVE_RESERVE')
        return exchange(role,frame,expect=expect)
    authority._exchange=native
    sdk=port.client.send_goal_async
    def send(*args,**kw):events.append('SDK_SEND');return sdk(*args,**kw)
    port.client.send_goal_async=send
    def own(record,payload):events.append('OWN_INVENTORY');owned.append((record,payload));return True
    config=dict(port=port,authority=authority,monitor=monitor,epoch='attempt',generation=11,
        session_id='head-search-restarts',controller_identity=identity,guard=lambda:True,
        own_inventory=own,fault_callback=lambda reason:faults.append(reason))
    try:yield config,events,owned,faults,servers,calls
    finally:
        port.close_head_io(timeout_s=1.)
        for server in servers.values():server.stop()


def target():
    return dict(joint_names=('neck_yaw_joint',),header_stamp_s=1.004,
        time_from_start_s=(0.,.05),positions=((.2,),(.3,)))


def test_exact_inventory_and_two_dispatch_acks_precede_native_and_sdk(composed):
    config,events,owned,faults,servers,calls=composed
    sender=HeadInventoryDispatcher(**config);gid=sender.send(target())
    assert events==['OWN_INVENTORY','REGISTER','DISPATCH','NATIVE_RESERVE','DISPATCH','SDK_SEND']
    assert not faults and len(owned)==1 and len(servers['neck'].socket_state.reserved)==1
    record,payload=owned[0]
    assert gid==record['goal_uuid']
    assert record['operation_sequence']==1
    assert record['deadline_ns']-record['claim_monotonic_ns']==400_000_000
    assert record['payload_sha256']==__import__('hashlib').sha256(payload).hexdigest()
    assert sender.inventory[gid]==record


@pytest.mark.parametrize('damage',[
    ('epoch','foreign'),('generation',12),('session_id','foreign'),('operation_sequence',2),
    ('inventory_sha256','f'*64),('goal_uuid','foreign'),('stage','POLICY_READY'),
    ('monitor_peer',dict(uid=1000,pid=203,start_ticks=303)),('purpose','qualified'),('motion_authority',True)])
def test_mixed_inventory_ack_never_reserves_or_sends_and_consumes_sender(composed,damage):
    config,events,owned,faults,servers,calls=composed;config['monitor'].damage=damage
    sender=HeadInventoryDispatcher(**config)
    with pytest.raises((PermissionError,ValueError)):sender.send(target())
    assert sender.revoked and faults
    assert 'NATIVE_RESERVE' not in events and 'SDK_SEND' not in events
    assert len(owned)==1 and len(sender.inventory)==1
    config['monitor'].damage=None
    with pytest.raises(PermissionError):sender.send(target())
    assert len(owned)==1


def test_failed_primary_inventory_prevents_remote_registration_and_native(composed):
    config,events,owned,faults,servers,calls=composed
    config['own_inventory']=lambda record,payload:False
    sender=HeadInventoryDispatcher(**config)
    with pytest.raises(RestartRefused) as refused:sender.send(target())
    assert isinstance(refused.value.__cause__,PermissionError)
    assert str(refused.value.__cause__)=='HEAD_PRIMARY_INVENTORY_REFUSED'
    assert events==[] and sender.revoked and faults
    assert len(sender.inventory)==1


def test_current_monitor_revocation_after_native_ack_prevents_sdk(composed):
    config,events,owned,faults,servers,calls=composed;monitor=config['monitor']
    exchange=config['authority']._exchange
    def native(role,frame,*,expect):
        reply=exchange(role,frame,expect=expect)
        if frame[4:8]==b'SOGB':monitor.epoch.revoke('actual monitor fault',fault_wall_s=0.)
        return reply
    config['authority']._exchange=native
    sender=HeadInventoryDispatcher(**config)
    with pytest.raises(PermissionError):sender.send(target())
    assert 'NATIVE_RESERVE' in events and 'SDK_SEND' not in events
    assert sender.revoked and faults


def test_peer_identity_cannot_change_after_primary_binding(composed):
    config,events,owned,faults,servers,calls=composed
    sender=HeadInventoryDispatcher(**config)
    config['monitor'].identity=dict(uid=1000,pid=204,start_ticks=304)
    with pytest.raises((PermissionError,RestartRefused)):sender.send(target())
    assert 'NATIVE_RESERVE' not in events and 'SDK_SEND' not in events
    assert sender.revoked and faults


def test_inventory_exception_is_not_formatted_before_fault_closure(composed):
    config,events,owned,faults,servers,calls=composed
    rendered=[]
    class DiagnosticError(Exception):
        def __repr__(self):
            rendered.append(tuple(faults));return 'untrusted diagnostic'
    def own(record,payload):raise DiagnosticError()
    config['own_inventory']=own
    sender=HeadInventoryDispatcher(**config)
    with pytest.raises(RestartRefused):sender.send(target())
    assert not rendered and faults and sender.revoked
    assert 'NATIVE_RESERVE' not in events and 'SDK_SEND' not in events


def test_failed_current_guard_never_constructs_inventory_or_sends(composed):
    config,events,owned,faults,servers,calls=composed
    config['guard']=lambda:False
    sender=HeadInventoryDispatcher(**config)
    with pytest.raises(PermissionError):sender.send(target())
    assert not events and not owned and not sender.inventory and sender.revoked and faults
