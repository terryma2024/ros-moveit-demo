"""Head main channel is authenticated and whole-exchange bounded, without motion."""
import secrets
import time
import uuid
from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import serialize_message
from so101_demo.adapters.act.ros_execution import trajectory_message
from so101_demo.act.head_search_restarts import RestartRefused

import pytest
import test_act_head_revocation as revocation
from test_act_head_revocation import native_server,ack
from so101_demo.adapters.act.head_reservation_authority import HeadReservationAuthority


def authority(path,owner,*,guard=lambda:True,faults=None):
    return HeadReservationAuthority(directory=path.parent,capability=secrets.token_bytes(32),
        native_owner=owner,generation=5,session_id='session',arm_guard=guard,
        fault_callback=lambda reason:(faults if faults is not None else []).append(reason))


def test_explicit_arm_from_exact_native_peer_is_one_50ms_exchange(native_server):
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    gate=authority(path,owner);assert gate.arm('neck')==5
    assert gate.timeout_s==.05 and gate.transport_attempts==1
    assert not gate.transport_retries
    assert process.stdout.readline()=='RECEIVED\n'


@pytest.mark.parametrize('damage',['pid','uid','start_ticks'])
def test_foreign_native_peer_never_receives_main_capability(native_server,damage):
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    changed=dict(owner);changed[damage]+=1;faults=[];gate=authority(path,changed,faults=faults)
    with pytest.raises(Exception):gate.arm('neck')
    assert process.stdout.readline()=='EMPTY\n'
    assert gate._registration_failed and faults


def test_identity_cannot_implicitly_arm_before_stopped_policy(native_server):
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    faults=[];gate=authority(path,owner,faults=faults)
    with pytest.raises((PermissionError,RestartRefused)):gate.identity('neck')
    assert gate._registration_failed and faults and not gate._armed


def test_failed_arm_precondition_latches_without_native_exchange(native_server):
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    faults=[];gate=authority(path,owner,guard=lambda:False,faults=faults)
    with pytest.raises(PermissionError):gate.arm('neck')
    assert gate._registration_failed and faults and not gate._armed
    gate.arm_guard=lambda:True
    with pytest.raises(PermissionError):gate.arm('neck')


def test_reserve_without_inventory_hook_never_calls_native(native_server):
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    faults=[];gate=authority(path,owner,faults=faults)
    gate._armed.add('neck');gate._identities['neck']=dict(generation=5,incarnation='inc',boot='boot')
    message=FollowJointTrajectory.Goal(trajectory=trajectory_message(dict(joint_names=['neck_yaw_joint'],header_stamp_s=1.004,time_from_start_s=[0.,.05],positions=[[.2],[.3]])))
    with pytest.raises(PermissionError):gate.reserve('neck',goal=serialize_message(message),goal_uuid=uuid.uuid4().bytes)
    assert gate._registration_failed and faults


def test_trickled_ack_cannot_restart_main_50ms_budget(native_server,monkeypatch):
    # Actual child/socket; per-read deadlines would accept this incomplete ACK.
    slow=revocation.SERVER.replace('if data: connection.sendall(bytes.fromhex(sys.argv[2]))',
        "if data:\n            import time\n            reply=bytes.fromhex(sys.argv[2])\n            for index in range(0,len(reply),4):\n                time.sleep(.02)\n                connection.sendall(reply[index:index+4])")
    monkeypatch.setattr(revocation,'SERVER',slow)
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    faults=[];gate=authority(path,owner,faults=faults)
    start=time.monotonic()
    with pytest.raises(Exception):gate.arm('neck')
    assert time.monotonic()-start<.15
    assert gate._registration_failed and faults and not gate.transport_retries


def test_session_cannot_change_after_native_channel_is_frozen(native_server):
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    faults=[];gate=authority(path,owner,faults=faults);gate.session_id='foreign'
    with pytest.raises(PermissionError):gate.arm('neck')
    assert gate._registration_failed and faults and not gate._armed


def test_identity_reply_generation_must_equal_frozen_primary_generation(native_server):
    body=b'SOID'+bytes((1,1,3))+int(6).to_bytes(8,'big')+b'\x03inc\x04boot'
    path,owner,process=native_server(len(body).to_bytes(4,'big')+body);path.rename(path.parent/'neck.sock')
    faults=[];gate=authority(path,owner,faults=faults);gate._armed.add('neck')
    with pytest.raises(PermissionError):gate.identity('neck')
    assert gate._registration_failed and faults


def test_normal_close_has_validated_ack_and_never_rearms_same_authority(native_server):
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    gate=authority(path,owner);gate._armed.add('neck')
    receipt=gate.close()
    assert receipt['ack_validated'] and receipt['native_owner']==owner
    assert receipt['ack_wall_s']-receipt['request_wall_s']<=.05
    assert not gate._armed
    with pytest.raises(PermissionError):gate.arm('neck')


def test_fault_callback_failure_never_recovers_native_authority(native_server):
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    gate=authority(path,owner,guard=lambda:False)
    def fail(reason):raise RuntimeError('owned fault reporter unavailable')
    gate.fault_callback=fail
    with pytest.raises(PermissionError):gate.arm('neck')
    assert gate._registration_failed and gate._fault_callback_error=='RuntimeError'
    gate.arm_guard=lambda:True
    with pytest.raises(PermissionError):gate.arm('neck')


def test_fault_channel_keeps_hard_two_ms_bound(native_server):
    path,owner,process=native_server(ack())
    with pytest.raises(ValueError):revocation.NativeRevocationClient(path,capability=secrets.token_bytes(32),
        native_owner=owner,generation=5,timeout_s=.003)
