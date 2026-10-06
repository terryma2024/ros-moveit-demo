"""The real neck port switches once from denied admission to prepared dispatch."""

from types import SimpleNamespace

import pytest

from test_act_head_inventory_dispatch import composed, socket_root
from test_act_head_paused_admission import paused_head, command
from test_act_head_trajectory_guard import guard
from so101_demo.adapters.act.head_inventory_dispatch import HeadInventoryDispatcher
from so101_demo.adapters.act.ros_neck import RosNeckSearchPort


def neck_for(config):
    return RosNeckSearchPort(config['port'].node,
        session_id=config['local_state'].scope['session_id'],
        attempt_id=config['local_state'].scope['epoch'], goal_duration_s=1.,
        submit_lead_s=.004, stop_timeout_s=1., stop_velocity_rad_s=.04136050464213824,
        max_age_s=.25, command_guard=lambda *a: False,
        controller_port=config['port'], feedback_policy=config['port'].feedback_policy)


def test_owned_neck_prepared_binding_sends_through_same_inventory_and_client(paused_head):
    case = paused_head
    neck, dispatcher = case.neck, case.dispatcher
    client = neck.client
    assert client is case.row.port.client
    try:
        gid = command(case)
    except PermissionError:
        pytest.fail(repr(dict(fault=case.row.runtime.fault_reason,
            refusal=case.row.runtime.dispatch_guard_refused_reason,
            records=case.row.sink.rows)))
    assert neck.client is client and neck.port is dispatcher
    assert gid in dispatcher.inventory
    trace = dispatcher.dispatch_traces[0]
    assert trace['goal_uuid'] == gid
    assert all(dispatcher.inventory[gid][key] == value
               for key, value in trace['inventory_record'].items())
    inventory = dispatcher.inventory[gid]
    assert inventory['reserve_attempt_ns'] <= inventory['reserved_ns'] <= inventory['sdk_attempt_ns']
    assert len(dispatcher.inventory) == 1
    assert len([event for event in case.events if event[0] == 'SDK_SEND']) == 1
    assert len([call for call in case.row.calls if call[0] == 'action_client']) == 1
    assert not case.row.runtime.faulted
    assert case.state['paused'] is False
    with pytest.raises(PermissionError, match='ALREADY_BOUND'):
        neck.bind_prepared_head(dispatcher, guard=case.guard, stop_handoff=lambda *a: None)


@pytest.mark.parametrize('paused_head', ['unbound'], indirect=True)
def test_runner_post_arm_binder_uses_bound_runtime_authority_and_stop_origin(paused_head, monkeypatch):
    from so101_demo.cli.head_execution_runner import _bind_prepared_transport
    case = paused_head
    runtime, neck = case.row.runtime, case.neck
    emitted, stops = [], []
    original_stop = type(runtime).stop

    def stop(owner, origin, evidence):
        stops.append((origin, evidence))
        return original_stop(owner, origin, evidence)

    monkeypatch.setattr(type(runtime), 'stop', stop)
    composition = SimpleNamespace(emit=lambda *args: emitted.append(args))
    client = neck.client
    dispatcher = _bind_prepared_transport(composition,
        dict(neck=neck, scene=case.scene), runtime, case.guard)
    assert dispatcher.authority is runtime._authority and neck.port is dispatcher
    assert neck.client is client is runtime.port.client
    assert case.scene._admission_binding == (runtime, case.guard)
    assert emitted[0][0] == 'EXECUTION_PREPARED_TRANSPORT_BOUND'
    gid = command(case)
    assert gid in dispatcher.inventory and not case.state['paused']
    neck._head_stop_handoff(100, 200)
    from so101_demo.adapters.act.head_local_runtime import STOP_ORIGINS
    assert stops[0][0] in STOP_ORIGINS
    assert stops[0][1] == dict(occurred_ns=100, deadline_ns=200)
    assert runtime.stop_requested


@pytest.mark.parametrize('damage', ['session', 'epoch', 'client', 'guard', 'handoff', 'stopped'])
def test_prepared_neck_binding_refuses_wrong_scope_or_retired_port(composed, damage):
    config, events, owned, faults, servers, calls = composed
    neck = neck_for(config)
    dispatcher = HeadInventoryDispatcher(**config)
    guard, handoff = config['guard'], lambda *a: None
    if damage == 'session': neck.identity = ('foreign', neck.identity[1])
    elif damage == 'epoch': neck.identity = (neck.identity[0], 'foreign')
    elif damage == 'client': neck.client = object()
    elif damage == 'guard': guard = SimpleNamespace()
    elif damage == 'handoff': handoff = None
    else: neck._stopped = True
    with pytest.raises((ValueError, PermissionError)):
        neck.bind_prepared_head(dispatcher, guard=guard, stop_handoff=handoff)
    assert neck.port is config['port'] and neck._head_trajectory_guard is None
    assert owned == [] and not [c for c in calls if c[0] == 'send']
