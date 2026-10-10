"""Head main channel is authenticated and whole-exchange bounded, without motion."""
import os
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
    body=b'SOGR'+bytes((1,3))+gate._capabilities['neck']+int(5).to_bytes(8,'big')+bytes(16)
    assert bytes.fromhex(process.stdout.readline())==len(body).to_bytes(4,'big')+body


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
    slow=revocation.SERVER.replace('            connection.sendall(bytes.fromhex(sys.argv[2]))',
        "            reply=bytes.fromhex(sys.argv[2])\n            for index in range(0,len(reply),4):\n                time.sleep(.02)\n                connection.sendall(reply[index:index+4])")
    assert slow!=revocation.SERVER
    monkeypatch.setattr(revocation,'SERVER',slow)
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    faults=[];gate=authority(path,owner,faults=faults)
    start=time.monotonic()
    with pytest.raises(Exception):gate.arm('neck')
    assert time.monotonic()-start<.15
    assert gate._registration_failed and faults and not gate.transport_retries
    assert process.stdout.readline()=='RECEIVED\n'
    trace=gate._channel.exchange_trace
    assert trace['phase']=='receive' and 'reply_received' not in trace['phases']
    assert abs(trace['deadline_wall_s']-trace['request_wall_s']-.05)<1e-9


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


def test_main_transport_does_not_load_or_inherit_close_only_abi(native_server,monkeypatch):
    def missing():raise RuntimeError('fault transport unavailable')
    monkeypatch.setattr(revocation.head_revocation,'_load_transport',missing)
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    gate=authority(path,owner)
    assert not isinstance(gate._channel,revocation.NativeRevocationClient)
    assert gate.arm('neck')==5


@pytest.mark.parametrize('damage',['capability','path','owner'])
def test_main_channel_scope_changes_refuse_before_capability_send(native_server,damage):
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    faults=[];gate=authority(path,owner,faults=faults)
    if damage=='capability':gate._channel.capability+=b'additional bytes'
    elif damage=='path':gate._channel.path=path.parent/'foreign.sock'
    else:gate._channel.native_owner['start_ticks']+=1
    with pytest.raises((PermissionError,RestartRefused)):gate.arm('neck')
    assert gate._registration_failed and faults and not gate._armed


def test_complete_goal_frame_reaches_main_peer_after_inventory_ack(native_server):
    from so101_demo.act.head_search_restarts import encode_bound_reservation_frame,goal_digest
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    gate=authority(path,owner);gate._armed.add('neck')
    gate._identities['neck']=dict(generation=5,incarnation='inc',boot='boot')
    message=FollowJointTrajectory.Goal(trajectory=trajectory_message(dict(
        joint_names=['neck_yaw_joint'],header_stamp_s=1.004,
        time_from_start_s=[0.,.05],positions=[[.2],[.3]])))
    goal=serialize_message(message);goal_uuid=uuid.uuid4().bytes;inventory=[]
    def register(binding):inventory.append(binding);return True
    assert gate.reserve('neck',goal=goal,goal_uuid=goal_uuid,before_reserve=register) is True
    assert len(inventory)==1 and inventory[0].goal_cdr==goal
    binding=inventory[0]
    expected=encode_bound_reservation_frame(generation=binding.generation,
        goal_uuid=goal_uuid,role=3,permit_uuid=binding.permit_uuid,target_digest=goal_digest(goal),
        claim_monotonic_ns=binding.claim_monotonic_ns,deadline_ns=binding.deadline_ns,
        session_id=binding.session_id,broker_incarnation=binding.broker_incarnation,
        controller_incarnation=binding.controller_incarnation,
        controller_boot_incarnation=binding.controller_boot_incarnation,
        goal_cdr=goal,capability=gate._capabilities['neck'])
    assert process.stdout.readline()=='RECEIVED\n'
    assert bytes.fromhex(process.stdout.readline())==expected


@pytest.mark.parametrize('damage',['parent_mode','socket_mode','endpoint_symlink','ancestor_symlink','regular_file'])
def test_main_path_authentication_refuses_before_connect(native_server,damage):
    from so101_demo.adapters.act.head_reservation_authority import _MainChannel
    path,owner,_=native_server(ack());destination=path
    if damage=='parent_mode':path.parent.chmod(0o755)
    elif damage=='socket_mode':path.chmod(0o666)
    elif damage=='endpoint_symlink':
        destination=path.parent/'link.sock';destination.symlink_to(path)
    elif damage=='ancestor_symlink':
        alias=path.parent.parent/('hm-link-'+uuid.uuid4().hex[:8]);alias.symlink_to(path.parent)
        destination=alias/path.name
    else:destination=path.parent/'regular';destination.write_text('not a socket')
    channel=_MainChannel(destination,capability=secrets.token_bytes(32),native_owner=owner,
        generation=5,timeout_s=.05)
    try:
        with pytest.raises(PermissionError):channel._exchange(b'SOGR')
        assert channel.exchange_trace['phase']=='path'
        assert 'connected' not in channel.exchange_trace['phases']
    finally:
        if damage=='parent_mode':path.parent.chmod(0o700)


@pytest.mark.parametrize('reply',[b'FAIL'+ack()[4:],ack(6),ack()[:6]+b'\x01\x00'+ack()[8:],
    ack()[:4]+b'\x02'+ack()[5:],ack()[:5]+b'\x02'+ack()[6:],
    ack()[:5]+b'\x01'+ack()[6:]])
def test_main_bad_or_refused_ack_consumes_authority(native_server,reply):
    path,owner,_=native_server(reply);path.rename(path.parent/'neck.sock')
    faults=[];gate=authority(path,owner,faults=faults)
    with pytest.raises(RestartRefused):gate.arm('neck')
    assert gate._registration_failed and faults and not gate._armed


def test_main_identity_frame_uses_exact_capability_and_role(native_server):
    body=b'SOID'+bytes((1,1,3))+int(5).to_bytes(8,'big')+b'\x03inc\x04boot'
    path,owner,process=native_server(len(body).to_bytes(4,'big')+body);path.rename(path.parent/'neck.sock')
    gate=authority(path,owner);gate._armed.add('neck')
    assert gate.identity('neck')==dict(generation=5,incarnation='inc',boot='boot')
    request=b'SOIA'+bytes((1,1))+gate._capabilities['neck']+bytes((3,))
    assert process.stdout.readline()=='RECEIVED\n'
    assert bytes.fromhex(process.stdout.readline())==len(request).to_bytes(4,'big')+request


@pytest.mark.parametrize('size',[16,146])
def test_main_identity_length_is_bounded(native_server,size):
    path,owner,_=native_server(size.to_bytes(4,'big')+b'x'*size);path.rename(path.parent/'neck.sock')
    faults=[];gate=authority(path,owner,faults=faults);gate._armed.add('neck')
    with pytest.raises(RestartRefused):gate.identity('neck')
    assert gate._registration_failed and faults


def test_main_peer_is_authenticated_again_after_reply(native_server,monkeypatch):
    from so101_demo.adapters.act import head_reservation_authority as module
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    gate=authority(path,owner);calls=[];original=module._process_start_ticks
    def changed(pid):
        calls.append(pid)
        return original(pid)+(1 if len(calls)==2 else 0)
    monkeypatch.setattr(module,'_process_start_ticks',changed)
    with pytest.raises(RestartRefused):gate.arm('neck')
    assert len(calls)==2 and gate._registration_failed and not gate._armed
    assert process.stdout.readline()=='RECEIVED\n'
    assert gate._channel.exchange_trace['phase']=='reply_peer'


def test_main_delayed_post_reply_authentication_cannot_restart_deadline(native_server,monkeypatch):
    path,owner,process=native_server(ack());path.rename(path.parent/'neck.sock')
    gate=authority(path,owner);original=gate._channel._verify_peer;calls=[]
    def delayed(connection):
        calls.append(True);original(connection)
        if len(calls)==2:time.sleep(.06)
    monkeypatch.setattr(gate._channel,'_verify_peer',delayed)
    with pytest.raises(RestartRefused):gate.arm('neck')
    assert len(calls)==2 and gate._registration_failed and not gate._armed
    assert gate._channel.exchange_trace['phase']=='final_deadline'


def startup_proof(*, passed=True, evaluation_id=47):
    import struct
    now=time.monotonic_ns()
    fields=(evaluation_id,0 if passed else 6,0 if passed else 2,1 if passed else 9,
        5 if passed else 1,51 if passed else 0,-1,-1,-1,0,7,0,
        1 if passed else 0,51 if passed else 0,
        2000000 if passed else 0,102000000 if passed else 0,
        now-100000000 if passed else 0,now if passed else 0,now+1)
    body=struct.pack('>QBBBBHbbbBIHQQqqqqq',*fields)
    assert len(body)==80
    return body


def prearm_reply(*,passed=True,generation=5,stored=0):
    return (b'SOPR'+bytes((1,0 if passed else 1,3,0))+generation.to_bytes(8,'big')
        +stored.to_bytes(8,'big')+bytes(2)+b'\x03inc\x04boot'+startup_proof(passed=passed))


def diagnostic_reply(*,passed=True,phase=0,gate_reason=0):
    return (b'SOAR'+bytes((1,0 if passed else 1,3,phase))+int(5).to_bytes(8,'big')
        +gate_reason.to_bytes(2,'big')+bytes(6)+startup_proof(passed=passed or phase==2))


def test_main_prearm_requires_exact_peer_identity_and_record(native_server):
    body=prearm_reply();path,owner,process=native_server(len(body).to_bytes(4,'big')+body)
    path.rename(path.parent/'neck.sock');gate=authority(path,owner)
    reply=gate.prearm_status('neck',expected_identity=dict(role=3,generation=5,incarnation='inc',boot='boot'),overall_deadline_ns=time.monotonic_ns()+2_000_000_000)
    assert reply['status']=='READY' and reply['generation']==5 and reply['stored_generation']==0
    assert (reply['role'],reply['incarnation'],reply['boot'])==(3,'inc','boot')
    assert reply['proof']['evaluation_id']==47 and reply['proof']['flags']==5
    assert reply['proof']['sample_count']==51 and reply['proof']['cumulative_observation_lock_losses']==7
    assert reply['proof']['first_sequence']==1 and reply['proof']['last_sequence']==51
    assert reply['proof']['first_sim_time_ns']==2_000_000 and reply['proof']['last_sim_time_ns']==102_000_000
    assert reply['proof']['failing_sample_index']==-1 and reply['proof']['failing_joint_index']==-1
    assert not gate._armed
    assert process.stdout.readline()=='RECEIVED\n'
    frame=bytes.fromhex(process.stdout.readline());assert frame[9]==5 and len(frame)==66


def test_prearm_not_ready_keeps_exact_reset_distinct_from_rejection(native_server):
    body=prearm_reply(passed=False);path,owner,_=native_server(len(body).to_bytes(4,'big')+body)
    path.rename(path.parent/'neck.sock');gate=authority(path,owner)
    reply=gate.prearm_status('neck',expected_identity=dict(role=3,generation=5,incarnation='inc',boot='boot'),overall_deadline_ns=time.monotonic_ns()+2_000_000_000)
    assert reply['status']=='NOT_READY' and not gate._armed and not gate._registration_failed
    assert reply['proof']['witness_rejection']==2 and reply['proof']['last_reset_reason']==9


@pytest.mark.parametrize('offset',[4,5,6,7,15,25,-72,-71,-70,-69,-63,-58,-57])
def test_prearm_malformed_fields_consume_authority(native_server,offset):
    body=bytearray(prearm_reply());body[offset]=255
    path,owner,_=native_server(len(body).to_bytes(4,'big')+body);path.rename(path.parent/'neck.sock')
    gate=authority(path,owner)
    with pytest.raises(Exception):gate.prearm_status('neck',expected_identity=dict(role=3,generation=5,incarnation='inc',boot='boot'),overall_deadline_ns=time.monotonic_ns()+2_000_000_000)
    assert gate._registration_failed and not gate._armed


@pytest.mark.parametrize('phase,reason',[(1,0),(2,3),(3,0)])
def test_main_one_arm_reject_preserves_phase_and_unknown_timeout(native_server,phase,reason):
    path,owner,process=native_server(diagnostic_reply(passed=False,phase=phase,gate_reason=reason))
    path.rename(path.parent/'neck.sock');gate=authority(path,owner)
    with pytest.raises(Exception) as error:gate.arm_with_diagnostics('neck',overall_deadline_ns=time.monotonic_ns()+2_000_000_000)
    assert error.value.phase=={1:'STOP_BEFORE',2:'GATE_ARM',3:'STOP_AFTER'}[phase]
    assert error.value.proof['evaluation_id']==47
    assert not gate._armed and gate._registration_failed
    with pytest.raises(Exception):gate.arm_with_diagnostics('neck',overall_deadline_ns=time.monotonic_ns()+2_000_000_000)
    assert process.stdout.readline()=='RECEIVED\n'
    assert bytes.fromhex(process.stdout.readline())[9]==6
    assert not gate.transport_retries


def test_diagnostic_arm_ack_opens_only_after_full_104_byte_validation(native_server):
    path,owner,process=native_server(diagnostic_reply());path.rename(path.parent/'neck.sock');gate=authority(path,owner)
    receipt=gate.arm_with_diagnostics('neck',overall_deadline_ns=time.monotonic_ns()+2_000_000_000)
    assert receipt['phase']=='NONE' and receipt['proof']['evaluation_id']==47 and gate._armed=={'neck'}
    assert receipt['generation']==5


def test_diagnostic_arm_timeout_preserves_unknown_outcome(native_server):
    path,owner,_=native_server(diagnostic_reply(),delay=.03);path.rename(path.parent/'neck.sock');gate=authority(path,owner)
    with pytest.raises(Exception) as error:gate.arm_with_diagnostics('neck',overall_deadline_ns=time.monotonic_ns()+5_000_000)
    assert error.value.code=='ARM_OUTCOME_UNKNOWN'
    assert not gate._armed and not gate.transport_retries


def test_main_identity_uses_remaining_startup_budget(native_server):
    body=b'SOID'+bytes((1,1,3))+int(5).to_bytes(8,'big')+b'\x03inc\x04boot'
    path,owner,_=native_server(len(body).to_bytes(4,'big')+body,delay=.02)
    path.rename(path.parent/'neck.sock');gate=authority(path,owner);gate._armed.add('neck')
    with pytest.raises(Exception):gate.identity('neck',overall_deadline_ns=time.monotonic_ns()+5_000_000)
    assert gate._registration_failed
    trace=gate._channel.exchange_trace
    assert 0<trace['deadline_wall_s']-trace['request_wall_s']<=.0051


def test_main_deadline_is_smaller_of_50ms_and_overall(native_server):
    body=prearm_reply();path,owner,_=native_server(len(body).to_bytes(4,'big')+body,delay=.02)
    path.rename(path.parent/'neck.sock');gate=authority(path,owner)
    with pytest.raises(TimeoutError):gate.prearm_status('neck',expected_identity=dict(role=3,generation=5,incarnation='inc',boot='boot'),overall_deadline_ns=time.monotonic_ns()+5_000_000)
    assert gate._channel.exchange_trace['deadline_wall_s']-gate._channel.exchange_trace['request_wall_s']<=.0051


def test_main_prearm_rejects_authenticated_replacement_identity(native_server):
    body=prearm_reply();path,owner,_=native_server(len(body).to_bytes(4,'big')+body)
    path.rename(path.parent/'neck.sock');gate=authority(path,owner)
    with pytest.raises(PermissionError,match='IDENTITY_MISMATCH'):
        gate.prearm_status('neck',expected_identity=dict(role=3,generation=5,incarnation='other',boot='boot'),
            overall_deadline_ns=time.monotonic_ns()+2_000_000_000)
    assert not gate._armed


def test_main_startup_arm_keeps_generation_and_diagnostic_record(native_server):
    path,owner,_=native_server(diagnostic_reply());path.rename(path.parent/'neck.sock');gate=authority(path,owner)
    assert gate.arm('neck',overall_deadline_ns=time.monotonic_ns()+2_000_000_000)==5
    assert gate.last_arm_result['proof']['evaluation_id']==47

def unavailable_record():
    import struct
    return struct.pack('>QBBBBHbbbBIHQQqqqqq', 81,8,0,0,0,0,-1,-1,-1,0,0,0,0,0,0,0,0,0,0)


def test_wrapper_eight_requires_canonical_fields_and_refusal_phase():
    from so101_demo.adapters.act.head_control_protocol import (
        parse_proof_record, parse_prearm, parse_diagnostic_arm)
    import struct
    record=unavailable_record()
    parsed=parse_proof_record(record)
    assert parsed['evaluation_id']==81 and parsed['wrapper_reason']==8 and parsed['flags']==0
    fields=list(struct.unpack('>QBBBBHbbbBIHQQqqqqq',record))
    for index in (0,2,3,4,5,6,7,8,10,12,13,14,15,16,17,18):
        forged=fields[:];forged[index]=0 if index in (0,6,7,8) else 1
        with pytest.raises(RuntimeError):
            parse_proof_record(struct.pack('>QBBBBHbbbBIHQQqqqqq',*forged))
    body=prearm_reply(passed=False)[:-80]+record
    assert parse_prearm(body,generation=5)['status']=='NOT_READY'
    forged=bytearray(body);forged[5]=0
    with pytest.raises(RuntimeError):parse_prearm(bytes(forged),generation=5)
    for phase in (1,3):
        body=diagnostic_reply(passed=False,phase=phase)[:-80]+record
        assert parse_diagnostic_arm(body,generation=5)['proof']['wrapper_reason']==8
    for passed,phase,reason in ((True,0,0),(False,2,3)):
        body=diagnostic_reply(passed=passed,phase=phase,gate_reason=reason)[:-80]+record
        with pytest.raises(RuntimeError):parse_diagnostic_arm(body,generation=5)


@pytest.mark.parametrize('count',[0xFFFFFF,0xFFFFFFFF])
def test_python_loss_count_saturation_and_legacy_u32_layout(count):
    from so101_demo.adapters.act.head_control_protocol import parse_proof_record
    import struct
    fields=list(struct.unpack('>QBBBBHbbbBIHQQqqqqq',startup_proof(passed=False)))
    fields[2]=1;fields[3]=4;fields[4]=3;fields[10]=count
    parsed=parse_proof_record(struct.pack('>QBBBBHbbbBIHQQqqqqq',*fields))
    assert parsed['witness_rejection']==1 and parsed['cumulative_observation_lock_losses']==count


def test_reply_51ms_after_evaluation_exceeds_main_exchange(native_server):
    body=prearm_reply()
    path,owner,_=native_server(len(body).to_bytes(4,'big')+body,delay=.051)
    path.rename(path.parent/'neck.sock');gate=authority(path,owner)
    with pytest.raises(TimeoutError):
        gate.prearm_status('neck',expected_identity=dict(role=3,generation=5,incarnation='inc',boot='boot'),
            overall_deadline_ns=time.monotonic_ns()+2_000_000_000)
    assert not gate._armed and gate._registration_failed
