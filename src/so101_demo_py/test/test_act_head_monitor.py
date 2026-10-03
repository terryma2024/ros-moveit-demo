"""Monitor readiness and immutable ACK must precede native reserve/action send."""

import copy
import uuid

import pytest

from so101_demo.act.head_monitor import HeadMonitorEpoch, digest


IDENTITY=dict(generation=5,incarnation='native-inc',boot='native-boot')


def policy():
    return dict(joint_max_receipt_age_s=.02,joint_max_source_age_s=.02,
        camera_interarrival_deadline_s=.11,camera_max_source_age_s=.11,
        clock_interarrival_deadline_s=.02,watchdog_period_s=.002,
        watchdog_reaction_limit_s=.010,revoker_connection_deadline_s=.002)


def monitor():
    return HeadMonitorEpoch(epoch='attempt-epoch',generation=5,session_id='head-session',
        clock_ns=lambda:10_050_000_000)


def test_explicit_simulation_epoch_binds_exact_feedback_without_arming():
    from dataclasses import asdict
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    simulation=HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document())
    epoch=HeadMonitorEpoch(epoch='attempt-epoch',generation=5,session_id='head-session',
        clock_ns=lambda:10_050_000_000,simulation_policy=simulation.readback())
    epoch.bind_policy(simulation.feedback_values(),'a'*64)
    assert asdict(epoch.policy)==simulation.feedback_values()
    assert epoch.stage=='POLICY_READY' and epoch.identity is None and epoch.inventory=={}
    with pytest.raises(PermissionError):epoch.register(inventory())
    assert epoch.stage=='REVOKED'


def test_simulation_epoch_refuses_different_mapping_and_cannot_rebind_after_fault():
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    simulation=HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document())
    epoch=HeadMonitorEpoch(epoch='attempt-epoch',generation=5,session_id='head-session',
        clock_ns=lambda:10_050_000_000,simulation_policy=simulation)
    with pytest.raises(ValueError):epoch.bind_policy(policy(),'a'*64)
    assert epoch.stage=='REVOKED'
    with pytest.raises(PermissionError):epoch.bind_policy(simulation.feedback_values(),'b'*64)


def test_legacy_epoch_cannot_implicitly_adopt_typed_simulation_feedback():
    from so101_demo.act.head_feedback import FeedbackPolicy
    from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
    simulation=HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document())
    bound=FeedbackPolicy.parse(simulation.feedback_values(),simulation_policy=simulation)
    epoch=monitor()
    with pytest.raises(ValueError):epoch.bind_policy(bound,'a'*64)
    assert epoch.stage=='REVOKED'


def ready():
    port=monitor();port.bind_policy(policy(),'a'*64)
    port.armed_ready(IDENTITY,IDENTITY)
    return port


def inventory(sequence=1):
    return dict(goal_uuid=str(uuid.uuid4()),typed_goal={'trajectory':{'joint_names':['neck_yaw_joint']}},
        payload_sha256='b'*64,generation=5,controller_identity=dict(IDENTITY),
        attempt_epoch='attempt-epoch',session_id='head-session',role='neck',
        operation_sequence=sequence,claim_monotonic_ns=10_000_000_000,
        deadline_ns=10_400_000_000)


def test_matching_staged_identity_and_inventory_have_exact_ack():
    port=ready();record=inventory();ack=port.register(record)
    assert ack==dict(epoch='attempt-epoch',operation_sequence=1,
        goal_uuid=record['goal_uuid'],inventory_sha256=digest(record))
    assert port.require_dispatch(record['goal_uuid'],ack['inventory_sha256']) is True
    record['typed_goal']['trajectory']['joint_names'][0]='arm_joint'
    assert port.inventory[record['goal_uuid']]['typed_goal']['trajectory']['joint_names']==['neck_yaw_joint']


@pytest.mark.parametrize('stage',['PRESENT','POLICY_READY','REVOKED'])
def test_inventory_before_exact_armed_ready_is_refused(stage):
    port=monitor()
    if stage!='PRESENT':port.bind_policy(policy(),'a'*64)
    if stage=='REVOKED':port.revoke('fault',fault_wall_s=10.)
    with pytest.raises(PermissionError):port.register(inventory())
    assert port.inventory=={}


@pytest.mark.parametrize('field',['generation','incarnation','boot'])
def test_monitor_does_not_accept_primary_identity_disagreement(field):
    port=monitor();port.bind_policy(policy(),'a'*64)
    changed=dict(IDENTITY);changed[field]=6 if field=='generation' else 'foreign'
    with pytest.raises(PermissionError):port.armed_ready(changed,IDENTITY)
    assert port.stage=='REVOKED'


@pytest.mark.parametrize('field',['attempt_epoch','generation','session_id','role','controller_identity',
                                  'operation_sequence','payload_sha256','goal_uuid','claim_monotonic_ns',
                                  'deadline_ns','extra'])
def test_mixed_or_malformed_inventory_is_never_acknowledged(field):
    port=ready();record=inventory()
    changes=dict(attempt_epoch='foreign',generation=6,session_id='foreign',role='arm',
        controller_identity=dict(IDENTITY,boot='foreign'),operation_sequence=2,
        payload_sha256='not-a-digest',goal_uuid='not-a-uuid',claim_monotonic_ns=10_500_000_000,
        deadline_ns=10_500_000_000,extra='undeclared')
    record[field]=changes[field]
    with pytest.raises((PermissionError,ValueError)):port.register(record)
    assert port.inventory=={} and port.stage=='REVOKED'


def test_duplicate_uuid_and_changed_inventory_cannot_replace_acked_goal():
    port=ready();record=inventory();port.register(record)
    changed=copy.deepcopy(record);changed['operation_sequence']=2
    changed['typed_goal']['trajectory']['points']=[dict(positions=[.3])]
    with pytest.raises(PermissionError):port.register(changed)
    assert port.inventory[record['goal_uuid']]==record


@pytest.mark.parametrize('operation',['policy','armed_ready','register','dispatch'])
def test_revoked_epoch_cannot_recover_or_ack_queued_operations(operation):
    port=ready();record=inventory();ack=port.register(record)
    port.revoke('watchdog stalled',fault_wall_s=10.)
    with pytest.raises(PermissionError):
        if operation=='policy':port.bind_policy(policy(),'a'*64)
        elif operation=='armed_ready':port.armed_ready(IDENTITY,IDENTITY)
        elif operation=='register':port.register(inventory(2))
        else:port.require_dispatch(record['goal_uuid'],ack['inventory_sha256'])
    assert port.stage=='REVOKED' and port.fault['fault_wall_s']==10.


@pytest.mark.parametrize('damage',['unknown_uuid','wrong_ack','unregistered'])
def test_dispatch_requires_this_exact_uuid_ack(damage):
    port=ready();record=inventory();ack=port.register(record)
    goal_uuid,sha=record['goal_uuid'],ack['inventory_sha256']
    if damage=='unknown_uuid':goal_uuid=str(uuid.uuid4())
    elif damage=='wrong_ack':sha='c'*64
    else:port=ready()
    with pytest.raises(PermissionError):port.require_dispatch(goal_uuid,sha)


def test_repeated_fault_keeps_the_earliest_observed_crossing():
    port=ready();port.revoke('first',fault_wall_s=10.)
    port.revoke('later',fault_wall_s=10.02)
    assert port.fault==dict(reason='first',fault_wall_s=10.)


def test_invalid_policy_latches_refusal_before_ready_or_after_arm():
    for port in (monitor(),ready()):
        with pytest.raises((ValueError,PermissionError)):
            port.bind_policy({},'a'*64)
        assert port.stage=='REVOKED'
        with pytest.raises(PermissionError):port.bind_policy(policy(),'a'*64)


def test_claim_expiry_while_reacquiring_state_lock_refuses_dispatch():
    now=[10_050_000_000]
    port=HeadMonitorEpoch(epoch='attempt-epoch',generation=5,session_id='head-session',
        clock_ns=lambda:now[0])
    port.bind_policy(policy(),'a'*64);port.armed_ready(IDENTITY,IDENTITY)
    record=inventory();ack=port.register(record)
    original=port._lock
    class ContendedLock:
        entries=0
        def __enter__(self):
            original.acquire();self.entries+=1
            if self.entries==2:now[0]=10_500_000_000
        def __exit__(self,*args):original.release()
    port._lock=ContendedLock()
    with pytest.raises(PermissionError,match='HEAD_MONITOR_CLAIM_EXPIRED'):
        port.require_dispatch(record['goal_uuid'],ack['inventory_sha256'])


@pytest.mark.parametrize('field',['epoch','generation','session_id','stage','identity',
                                  'fault','policy','policy_hash','sequence'])
def test_caller_cannot_rebind_attempt_scope_or_native_identity(field):
    port=ready()
    with pytest.raises(AttributeError):setattr(port,field,'replacement')
    identity=port.identity;identity['boot']='replacement'
    assert port.identity==IDENTITY
    port.revoke('first',fault_wall_s=10.)
    fault=port.fault;fault['fault_wall_s']=20.
    assert port.fault['fault_wall_s']==10.
