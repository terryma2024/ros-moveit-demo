"""Local typed inventory guards native reservation and prepared SDK send."""

import hashlib
import json
import math
import threading
import time
from pathlib import Path
import uuid
from dataclasses import replace

import pytest

from test_act_head_search_restarts import RestartRefused, socket_root, reservation_authority
from test_act_head_feedback_freshness import setup_ports, sample
from test_act_head_paused_admission import paused_head, command
from test_act_head_trajectory_guard import guard
from so101_demo.act.head_local_state import HeadLocalState
from so101_demo.act.head_evidence_identity import canonical_bytes
from so101_demo.adapters.act.head_inventory_dispatch import HeadInventoryDispatcher
from so101_demo.adapters.act.head_trajectory_guard import HeadTrajectoryGuard
from so101_demo.adapters.act.pick_place_neck_sweep import MujocoNeckSweepChecker
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.scene_state import SceneStateObserver


@pytest.fixture
def composed(socket_root, monkeypatch, request):
    initial_neck = float(getattr(request, "param", .2))
    authority, servers = reservation_authority(socket_root)
    identity = authority.identity('neck')
    _, _, port, wall, sim, calls, _ = setup_ports(monkeypatch, feedback_policy=dict(
        joint_max_receipt_age_s=.25, joint_max_source_age_s=.05,
        camera_interarrival_deadline_s=.11, camera_max_source_age_s=.11,
        clock_interarrival_deadline_s=.25, watchdog_period_s=.002,
        watchdog_reaction_limit_s=.010, revoker_connection_deadline_s=.002))
    wall[0] = time.monotonic()
    port._test_wall = wall
    feedback = sample()
    feedback.position[0] = initial_neck
    port._feedback(feedback)
    events = []; owned = []; faults = []
    port._head_fault_callback = lambda reason: faults.append(reason)
    exchange = authority._exchange
    def native(role, frame, *, expect):
        if frame[4:8] == b'SOGB': events.append('NATIVE_RESERVE')
        return exchange(role, frame, expect=expect)
    authority._exchange = native
    sdk = port.client.send_goal_async
    def send(*args, **kwargs):
        events.append('SDK_SEND')
        return sdk(*args, **kwargs)
    port.client.send_goal_async = send
    def own(record, payload):
        events.append('OWN_INVENTORY'); owned.append((record, payload))
        return port.inventory_prepared(record, payload)
    scope = dict(epoch='attempt-' + uuid.uuid4().hex, generation=11, session_id='head-search-restarts',
        policy_sha256='a' * 64, controller_identity=identity)
    state = HeadLocalState(scope=scope, search_deadline_ns=time.monotonic_ns() + 30_000_000_000)
    model_path = Path(__file__).resolve().parents[1] / 'assets/mujoco/act/head_search_scene.xml'
    geometry_path = Path('/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m/head-camera-probe11-20260930T101722Z/head-camera-geometry.json')
    import mujoco
    model = mujoco.MjModel.from_xml_path(str(model_path))
    semantic_sha = model_sha256(model)
    checker = MujocoNeckSweepChecker(model_path, expected_model_sha256=semantic_sha,
        protected_roots=('base',), allowed_pairs=(), path_step_s=.002,
        path_clearance_m=.001, max_samples=50000)
    observer = SceneStateObserver(model_sha256=semantic_sha, nq=model.nq, nv=model.nv,
        max_age_s=.25, monotonic=lambda: wall[0])
    observer.reset('mujoco-test-session', 1, source_floor_s=sim[0])
    data = mujoco.MjData(model)
    for name, value in zip(('1', '2', '3', '4', '5', '6'),
                           (-.25, 0., .6, .8, 0., .8), strict=True):
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[model.jnt_qposadr[joint]] = value
    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'neck_yaw_joint')
    data.qpos[model.jnt_qposadr[joint]] = initial_neck
    mujoco.mj_fwdPosition(model, data)
    now_ns = round(wall[0] * 1e9)
    frame = dict(simulation_session_id='mujoco-test-session', reset_epoch=1,
        simulation_step=4, paused=False, simulation_time_s=sim[0],
        model_sha256=semantic_sha, qpos=data.qpos.tolist(), qvel=data.qvel.tolist(),
        clock_interval_begin_monotonic_ns=now_ns-1_000_000,
        clock_interval_end_monotonic_ns=now_ns)
    assert observer.accept(frame)
    guard = HeadTrajectoryGuard(checker=checker, feedback_port=port,
        scene_observer=observer, node=port.node, model_xml_path=model_path,
        geometry_path=geometry_path, geometry_sha256=hashlib.sha256(
            geometry_path.read_bytes()).hexdigest(),
        simulation_session_id='mujoco-test-session', reset_epoch=1,
        monotonic=lambda: wall[0])
    config = dict(port=port, authority=authority, local_state=state, guard=guard,
        own_inventory=own, fault_callback=lambda reason: faults.append(reason))
    try:
        yield config, events, owned, faults, servers, calls
    finally:
        port.close_head_io(timeout_s=1.)
        for server in servers.values(): server.stop()


def target():
    return dict(joint_names=('neck_yaw_joint',), header_stamp_s=1.004,
        time_from_start_s=(0., .05), positions=((.2,), (.3,)))


def send_target(sender, config):
    return sender.send_prepared_head(config['guard'].prepare(.3))


def test_local_inventory_precedes_native_reserve_and_sdk_without_monitor_ack(composed):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config); gid = send_target(sender, config)
    assert events == ['OWN_INVENTORY', 'NATIVE_RESERVE', 'SDK_SEND']
    assert not faults and len(owned) == 1 and len(servers['neck'].socket_state.reserved) == 1
    record, payload = owned[0]
    assert gid == record['goal_uuid']
    assert record['operation_sequence'] == 1
    assert record['deadline_ns'] - record['claim_monotonic_ns'] == 400_000_000
    assert record['payload_sha256'] == hashlib.sha256(payload).hexdigest()
    assert {key: value for key, value in sender.inventory[gid].items()
            if not key.endswith('_ns') or key in ('claim_monotonic_ns', 'deadline_ns')} == record
    assert sender.inventory[gid]['reserve_attempt_ns'] <= sender.inventory[gid]['reserved_ns']
    assert sender.inventory[gid]['sdk_attempt_ns'] >= sender.inventory[gid]['reserved_ns']
    trace = sender.dispatch_traces[0]
    assert trace['inventory_record'] == record
    assert trace['original_cdr_sha256'] == record['payload_sha256']
    assert trace['original_cdr'] == payload == sender.local_state.prepared_cdr(gid)
    from rclpy.serialization import deserialize_message
    from control_msgs.action import FollowJointTrajectory
    wire = deserialize_message(payload, FollowJointTrajectory.Goal).trajectory
    assert tuple(wire.points[0].positions) == pytest.approx((.2,))
    assert tuple(wire.points[0].velocities) == (0.,)
    assert tuple(wire.points[0].accelerations) == (0.,)
    assert tuple(wire.points[1].positions) == pytest.approx((.3,))
    assert tuple(wire.points[1].velocities) == (0.,)
    assert tuple(wire.points[1].accelerations) == (0.,)
    assert wire.points[0].time_from_start.sec == 0
    assert wire.points[0].time_from_start.nanosec == 600_000_000
    assert wire.points[-1].time_from_start.nanosec != 0


def test_position_only_dispatch_api_is_closed_before_inventory_or_reserve(composed):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    with pytest.raises(PermissionError, match='HEAD_POSITION_ONLY_BYPASS_REFUSED'):
        sender.send(target())
    assert not events and not owned and not sender.inventory
    assert not faults and not servers['neck'].socket_state.reserved


def test_original_cdr_inventory_survives_ros_reencoding_padding(composed, monkeypatch):
    from rclpy import serialization
    config, events, owned, faults, servers, calls = composed
    monkeypatch.setattr(serialization, 'serialize_message', lambda message: b'other CDR padding')
    sender = HeadInventoryDispatcher(**config); gid = send_target(sender, config)
    record = config['port']._goals[gid]
    assert record['primary_inventory'] and record['prepared_typed_goal_bytes']
    assert record['sdk_claimed'] is True and not faults
    assert events == ['OWN_INVENTORY', 'NATIVE_RESERVE', 'SDK_SEND']


def test_primary_callback_cannot_fake_inventory_receipt_or_allow_native_reserve(composed):
    config, events, owned, faults, servers, calls = composed
    config['own_inventory'] = lambda record, payload: True
    sender = HeadInventoryDispatcher(**config)
    with pytest.raises(RestartRefused) as refused:
        send_target(sender, config)
    assert isinstance(refused.value.__cause__, PermissionError)
    assert str(refused.value.__cause__) == 'HEAD_PRIMARY_INVENTORY_RECEIPT_MISSING'
    assert 'NATIVE_RESERVE' not in events and 'SDK_SEND' not in events
    assert sender.revoked and sender.inventory and faults


def test_false_primary_inventory_callback_stops_before_native_reserve(composed):
    config, events, owned, faults, servers, calls = composed
    config['own_inventory'] = lambda record, payload: False
    sender = HeadInventoryDispatcher(**config)
    with pytest.raises(RestartRefused) as refused:
        send_target(sender, config)
    assert isinstance(refused.value.__cause__, PermissionError)
    assert str(refused.value.__cause__) == 'HEAD_PRIMARY_INVENTORY_REFUSED'
    assert events == [] and sender.revoked and sender.inventory and faults


@pytest.mark.parametrize('field,value', [
    ('goal_uuid', b'X' * 16), ('goal_cdr', b'wrong CDR'), ('generation', 12),
    ('role', 'wrist'), ('controller_incarnation', 'other-controller'),
    ('controller_boot_incarnation', 'other-boot'), ('session_id', 'other-session'),
])
def test_mismatched_native_reservation_binding_stops_before_reserve_or_sdk(composed, field, value):
    config, events, owned, faults, servers, calls = composed
    original = config['authority'].reserve
    def changed(role, *, goal, goal_uuid, before_reserve=None):
        def bind(binding):
            return before_reserve(replace(binding, **{field: value}))
        return original(role, goal=goal, goal_uuid=goal_uuid, before_reserve=bind)
    config['authority'].reserve = changed
    sender = HeadInventoryDispatcher(**config)
    with pytest.raises(RestartRefused): send_target(sender, config)
    assert 'NATIVE_RESERVE' not in events and 'SDK_SEND' not in events
    assert sender.revoked and faults


def test_unknown_native_reservation_keeps_inventory_and_never_sends(composed):
    config, events, owned, faults, servers, calls = composed
    original = config['authority'].reserve
    def unknown(*args, **kwargs):
        original(*args, **kwargs)
        return False
    config['authority'].reserve = unknown
    sender = HeadInventoryDispatcher(**config)
    with pytest.raises(PermissionError, match='NATIVE_RESERVATION_REFUSED'):
        send_target(sender, config)
    assert 'NATIVE_RESERVE' in events and 'SDK_SEND' not in events
    row = next(iter(sender.inventory.values()))
    assert 'reserve_attempt_ns' in row and 'sdk_attempt_ns' not in row


def test_final_local_guard_failure_prevents_sdk_and_keeps_possible_send_uuid(composed):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    original = sender._trajectory_guard.revalidate
    checks = iter((True, True, False))
    def final_failure(prepared):
        if next(checks) is False:
            raise PermissionError('prepared proof invalidated before SDK')
        return original(prepared)
    sender._trajectory_guard.revalidate = final_failure
    with pytest.raises(PermissionError): send_target(sender, config)
    assert 'NATIVE_RESERVE' in events and 'SDK_SEND' not in events
    row = next(iter(sender.inventory.values()))
    assert 'sdk_attempt_ns' in row
    assert sender.revoked and faults


def test_authority_identity_change_is_refused_before_local_registration(composed):
    config, events, owned, faults, servers, calls = composed
    config['authority']._identities['neck'] = dict(generation=11, incarnation='other', boot='boot')
    with pytest.raises(PermissionError, match='SCOPE_INVALID'):
        HeadInventoryDispatcher(**config)
    assert not owned and not events


def test_local_scope_snapshot_is_detached_from_dispatcher(composed):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    snapshot = sender.local_state.snapshot
    snapshot['scope']['controller_identity']['incarnation'] = 'changed'
    assert sender.local_state.scope['controller_identity']['incarnation'] != 'changed'


def test_state_diagnostic_failure_cannot_skip_local_stop_callback(composed):
    config, events, owned, faults, servers, calls = composed
    state = config['local_state']
    state.clock_ns = lambda: (_ for _ in ()).throw(RuntimeError('clock diagnostic unavailable'))
    sender = HeadInventoryDispatcher(**config)
    prepared = config['guard'].prepare(.3)
    sender._trajectory_guard.stop()

    with pytest.raises(PermissionError):
        sender.send_prepared_head(prepared)
    assert sender.revoked and config['port']._head_policy_binding_failed
    assert faults == ['HEAD_INVENTORY_DISPATCH_FAILED']
    assert 'SDK_SEND' not in events


def test_dispatcher_fault_callback_observes_origin_before_blocking(composed):
    config, events, owned, faults, servers, calls = composed
    state = config['local_state']
    sender = HeadInventoryDispatcher(**config)
    goal_uuid = sender.send_prepared_head(config['guard'].prepare(.3))
    original_cdr = state.prepared_cdr(goal_uuid)
    before_fault_inventory = sender.inventory
    before_fault_events = tuple(events)
    entered = threading.Event()
    release = threading.Event()
    observed = []
    callback_errors = []

    def callback(reason):
        observed.append((reason, getattr(state, 'fault_occurrence_ns', None)))
        entered.set()
        if not release.wait(timeout=2.):
            callback_errors.append('callback release timeout')

    sender._fault_callback = callback
    before_ns = time.monotonic_ns()
    worker = threading.Thread(target=lambda: sender._fault('HEAD_INVENTORY_DISPATCH_FAILED'))
    worker.start()
    try:
        assert entered.wait(timeout=1.)
        callback_entry_ns = time.monotonic_ns()
        observed_origin_ns = observed[0][1]
        assert observed == [('HEAD_INVENTORY_DISPATCH_FAILED', observed_origin_ns)]
        assert observed_origin_ns is not None
        assert before_ns <= observed_origin_ns <= callback_entry_ns
        assert state.snapshot['fault']['occurred_ns'] == observed_origin_ns
    finally:
        release.set()
        worker.join(timeout=2.)
    assert not worker.is_alive()
    assert callback_errors == []
    assert observed[0][1] == state.snapshot['fault']['occurred_ns']
    assert sender.revoked
    assert set(state.inventory) == {goal_uuid}
    assert state.prepared_cdr(goal_uuid) == original_cdr
    assert sender.inventory == before_fault_inventory
    assert tuple(events) == before_fault_events
    assert len(owned) == 1 and servers['neck'].socket_state.reserved


def test_fine_target_outside_coarse_domain_reaches_original_typed_sdk_path(composed):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    prepared = config['guard'].prepare(.3)
    proof = prepared.proof
    assert not proof['search_domain_rad'][0] <= .3 <= proof['search_domain_rad'][1]
    assert proof['safe_interval_rad'][0] <= .3 <= proof['safe_interval_rad'][1]
    original = bytes(prepared.original_cdr)
    gid = sender.send_prepared_head(prepared)
    from control_msgs.action import FollowJointTrajectory
    from rclpy.serialization import deserialize_message
    wire = deserialize_message(original, FollowJointTrajectory.Goal)
    trajectory = wire.trajectory
    assert gid == owned[0][0]['goal_uuid']
    assert owned[0][1] == original
    assert config['port']._goals[gid]['prepared_cdr_sha256'] == hashlib.sha256(
        original).hexdigest()
    assert config['port']._goals[gid]['primary_inventory']
    assert sender.dispatch_traces[0]['original_cdr'] == original
    assert trajectory.header.stamp.sec == 1
    assert trajectory.header.stamp.nanosec == 4_000_000
    assert [_point_ns for _point_ns in (
        p.time_from_start.sec * 1_000_000_000 + p.time_from_start.nanosec
        for p in trajectory.points)] == [600_000_000,
            proof['last_point_offset_ns']]
    assert [p.positions[0] for p in trajectory.points] == pytest.approx([.2, .3])
    assert [p.velocities[0] for p in trajectory.points] == [0., 0.]
    assert [p.accelerations[0] for p in trajectory.points] == [0., 0.]
    assert events == ['OWN_INVENTORY', 'NATIVE_RESERVE', 'SDK_SEND']
    assert not faults and servers['neck'].socket_state.reserved


def test_search_deadline_covers_replay_elapsed_header_lead_and_full_endpoint(
        composed, monkeypatch):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    guard = config['guard']
    state = config['local_state']
    snapshot, _, _ = guard._capture()
    wall = config['port']._test_wall
    start_wall_ns = round(wall[0] * 1e9)
    target_rad = .05
    duration_ns = guard._duration_ns(target_rad - snapshot.neck_position)
    # The full endpoint fits before replay with 100 ms left, but not after a
    # deterministic 200 ms replay delay. Keep the original deadline immutable.
    state._search_deadline_ns = start_wall_ns + 600_000_000 + duration_ns + 4_000_000 + 100_000_000
    replay = guard._check_physical_path
    def delayed_replay(*args, **kwargs):
        result = replay(*args, **kwargs)
        wall[0] += .2
        return result
    monkeypatch.setattr(guard, '_check_physical_path', delayed_replay)
    with pytest.raises(PermissionError, match='HEAD_TRAJECTORY_SEARCH_DEADLINE_TOO_SHORT'):
        guard.prepare(target_rad)
    assert not events and not owned and not config['port']._goals
    assert not servers['neck'].socket_state.reserved


def test_boundary_revalidation_uses_issued_guard_owned_original_without_heavy_redecode(
        composed, monkeypatch):
    import types
    import so101_demo.adapters.act.head_trajectory_guard as guard_module
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    prepared = config['guard'].prepare(.05)
    def forbidden(*args, **kwargs):
        raise AssertionError('expensive source decode/re-encode inside claim boundary')
    monkeypatch.setattr(guard_module, 'deserialize_message', forbidden)
    monkeypatch.setattr(guard_module, 'serialize_message', forbidden)
    monkeypatch.setattr(guard_module, 'message_to_ordereddict', forbidden)
    monkeypatch.setattr(guard_module, 'quintic_extrema', forbidden)
    monkeypatch.setattr(guard_module, 'json', types.SimpleNamespace(
        loads=forbidden, dumps=forbidden))
    proof = config['guard'].revalidate(prepared)
    assert proof['requested_target_rad'] == .05
    assert not events and not owned


def test_boundary_revalidation_uses_scope_bytes_without_redecoding_local_scope(
        composed, monkeypatch):
    import so101_demo.act.head_local_state as state_module
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    prepared = config['guard'].prepare(.05)
    def forbidden(*args, **kwargs):
        raise AssertionError('local scope JSON decode inside prepared claim boundary')
    monkeypatch.setattr(state_module.json, 'loads', forbidden)
    proof = config['guard'].revalidate(prepared)
    assert proof['requested_target_rad'] == .05
    assert not events and not owned


def test_foreign_and_mutated_issued_preparations_refuse_before_reserve_or_sdk(
        composed, record_property):
    from dataclasses import replace
    from so101_demo.act.head_feedback import nanoseconds

    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    prepared = config['guard'].prepare(.05)
    original_proof = prepared.proof
    original_search_deadline_ns = config['local_state'].search_deadline_ns
    original_prepared_timing = {
        key: original_proof[key]
        for key in ('header_stamp_ns', 'first_point_offset_ns',
                    'last_point_offset_ns', 'search_deadline_ns')}
    assert original_prepared_timing['search_deadline_ns'] == original_search_deadline_ns
    foreign = replace(prepared, _owner=object())
    with pytest.raises(PermissionError, match='HEAD_TRAJECTORY_PREPARED_OWNER_INVALID'):
        config['guard'].revalidate(foreign)
    assert not events and not owned and not sender.inventory

    object.__setattr__(prepared, 'original_cdr', b'forged original CDR')
    with pytest.raises(PermissionError):
        config['guard'].revalidate(prepared)
    assert 'NATIVE_RESERVE' not in events and 'SDK_SEND' not in events
    assert not servers['neck'].socket_state.reserved

    import mujoco
    model_path = Path(__file__).resolve().parents[1] / 'assets/mujoco/act/head_search_scene.xml'
    semantic = model_sha256(mujoco.MjModel.from_xml_path(str(model_path)))
    other_checker = MujocoNeckSweepChecker(model_path, expected_model_sha256=semantic,
        protected_roots=('base',), allowed_pairs=(), path_step_s=.002,
        path_clearance_m=.001, max_samples=50000)
    fixture_clock = config['guard'].monotonic
    other_guard = HeadTrajectoryGuard(checker=other_checker,
        feedback_port=config['port'], scene_observer=config['guard'].scene_observer,
        node=config['port'].node, model_xml_path=model_path,
        geometry_path=Path('/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m/head-camera-probe11-20260930T101722Z/head-camera-geometry.json'),
        geometry_sha256=config['guard'].geometry_sha256,
        simulation_session_id=config['guard'].simulation_session_id,
        reset_epoch=config['guard'].reset_epoch,
        monotonic=fixture_clock)
    assert other_guard.monotonic is fixture_clock
    other_config = dict(config, guard=other_guard)
    other_sender = HeadInventoryDispatcher(**other_config)
    calls_before = tuple(calls)
    inventories_before = (sender.inventory, other_sender.inventory,
                          config['local_state'].inventory)
    reservations_before = {
        role: list(server.socket_state.reserved)
        for role, server in servers.items()}
    port_goals_before = dict(config['port']._goals)
    before_scene = config['guard'].scene_observer.snapshot()
    before_feedback = config['port'].feedback_snapshot()
    fresh = _advance_fixture_sources_without_moving(config)
    fresh_scene = fresh['scene']
    fresh_feedback = fresh['feedback']
    observer = config['guard'].scene_observer
    wall = config['port']._test_wall
    clock_readback = {
        'original_guard_s': config['guard'].monotonic(),
        'other_guard_s': other_guard.monotonic(),
        'feedback_port_s': config['port'].monotonic(),
        'scene_observer_s': observer.monotonic(),
        'fixture_wall_s': wall[0],
    }
    assert len(set(clock_readback.values())) == 1
    assert fresh_scene['simulation_step'] == before_scene['simulation_step'] + 1
    assert fresh_scene['simulation_time_s'] > before_scene['simulation_time_s']
    assert fresh_scene['qpos'] == before_scene['qpos']
    assert fresh_scene['qvel'] == before_scene['qvel']
    assert fresh_scene['simulation_session_id'] == before_scene['simulation_session_id']
    assert fresh_scene['reset_epoch'] == before_scene['reset_epoch']
    assert fresh_scene['model_sha256'] == before_scene['model_sha256']
    assert fresh_feedback['source_ns'] > before_feedback['source_ns']
    assert fresh_feedback['positions'] == before_feedback['positions']
    assert fresh_feedback['valid'] is True
    decision = fresh_feedback['decision']
    now_wall_ns = nanoseconds(clock_readback['fixture_wall_s'])
    scene_received_ns = nanoseconds(fresh['scene_received_s'])
    scene_source_ns = nanoseconds(fresh_scene['simulation_time_s'])
    scene_begin_ns = fresh_scene['clock_interval_begin_monotonic_ns']
    scene_end_ns = fresh_scene['clock_interval_end_monotonic_ns']
    feedback_received_ns = nanoseconds(fresh_feedback['wall_s'])
    assert 0 < scene_begin_ns <= scene_end_ns <= now_wall_ns
    assert 0 <= now_wall_ns - scene_received_ns <= 250_000_000
    assert 0 <= now_wall_ns - scene_end_ns <= 250_000_000
    assert 0 <= decision['sim_ns'] - scene_source_ns <= 250_000_000
    assert 0 <= nanoseconds(decision['wall_after_s']) - feedback_received_ns <= 250_000_000
    assert 0 <= decision['sim_ns'] - fresh_feedback['source_ns'] <= 50_000_000
    assert fresh_feedback['source_ns'] > before_feedback['source_ns']
    assert config['local_state'].search_deadline_ns == original_search_deadline_ns
    assert prepared.proof == original_proof

    issued_by_other_guard = other_guard.prepare(.05)
    other_proof = other_guard.revalidate(issued_by_other_guard)
    assert other_proof['requested_target_rad'] == .05
    assert other_proof['search_deadline_ns'] == original_search_deadline_ns
    assert other_proof['header_stamp_ns'] == issued_by_other_guard.proof['header_stamp_ns']
    assert other_proof['header_stamp_ns'] - decision['sim_ns'] == 4_000_000
    assert other_guard._deadline_fits(
        original_search_deadline_ns, other_proof['header_stamp_ns'],
        other_proof['last_point_offset_ns'], decision['sim_ns'],
        nanoseconds(other_guard.monotonic()))
    assert other_proof['scene_qpos'] == tuple(fresh_scene['qpos'])
    assert other_proof['scene_qvel'] == tuple(fresh_scene['qvel'])
    assert other_proof['scene_source_time_ns'] == scene_source_ns
    assert other_proof['scene_receipt_wall_ns'] == scene_received_ns
    assert other_proof['feedback_source_ns'] == fresh_feedback['source_ns']
    assert other_proof['feedback_receipt_wall_ns'] == feedback_received_ns
    assert other_proof['feedback_decision_sim_ns'] == decision['sim_ns']

    with pytest.raises(PermissionError, match='HEAD_TRAJECTORY_PREPARED_OWNER_INVALID'):
        sender.send_prepared_head(issued_by_other_guard)
    assert config['local_state'].search_deadline_ns == original_search_deadline_ns
    assert {key: prepared.proof[key] for key in original_prepared_timing} == original_prepared_timing
    assert (sender.inventory, other_sender.inventory,
            config['local_state'].inventory) == inventories_before
    assert {role: list(server.socket_state.reserved)
            for role, server in servers.items()} == reservations_before
    assert config['port']._goals == port_goals_before
    assert tuple(calls) == calls_before
    assert not events and not owned

    record_property('foreign_guard_clock_receipt_json', json.dumps({
        'clock_readback_s': clock_readback,
        'scene': {
            'simulation_step': fresh_scene['simulation_step'],
            'simulation_time_s': fresh_scene['simulation_time_s'],
            'clock_interval_begin_monotonic_ns': scene_begin_ns,
            'clock_interval_end_monotonic_ns': scene_end_ns,
            'receipt_wall_ns': scene_received_ns,
            'session_id': fresh_scene['simulation_session_id'],
            'reset_epoch': fresh_scene['reset_epoch'],
            'model_sha256': fresh_scene['model_sha256'],
            'qpos': fresh_scene['qpos'],
            'qvel': fresh_scene['qvel'],
        },
        'feedback': {
            'source_ns': fresh_feedback['source_ns'],
            'receipt_wall_ns': feedback_received_ns,
            'decision_sim_ns': decision['sim_ns'],
            'decision_wall_before_s': decision['wall_before_s'],
            'decision_wall_after_s': decision['wall_after_s'],
        },
        'original_prepared_timing': original_prepared_timing,
        'current_other_guard_timing': {
            key: other_proof[key] for key in (
                'header_stamp_ns', 'first_point_offset_ns',
                'last_point_offset_ns', 'search_deadline_ns')},
        'foreign_guard_current_revalidation': 'accepted',
        'original_sender_rejection': 'HEAD_TRAJECTORY_PREPARED_OWNER_INVALID',
        'side_effects': {
            'original_inventory': sender.inventory,
            'other_inventory': other_sender.inventory,
            'local_state_inventory': config['local_state'].inventory,
            'native_reservations': {
                role: server.socket_state.reserved
                for role, server in servers.items()},
            'port_goals': config['port']._goals,
            'events': events,
            'owned': len(owned),
            'faults': faults,
            'local_state_faulted': config['local_state'].faulted,
            'sdk_call_count': len(calls),
            'sdk_call_kinds': [call[0] for call in calls],
        },
    }, sort_keys=True))


def _advance_fixture_sources_without_moving(config):
    from types import SimpleNamespace
    wall = config['port']._test_wall
    wall[0] += .001
    simulation_time_s = 1.001
    config['port'].node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(
        nanoseconds=round(simulation_time_s * 1e9)))
    config['port']._feedback(sample(source=simulation_time_s))
    observer = config['guard'].scene_observer
    frame = observer.snapshot()
    frame['simulation_step'] += 1
    frame['simulation_time_s'] = simulation_time_s
    now_ns = round(wall[0] * 1e9)
    frame['clock_interval_begin_monotonic_ns'] = now_ns - 1_000_000
    frame['clock_interval_end_monotonic_ns'] = now_ns
    assert observer.accept(frame)
    current_scene, received_s = observer.snapshot_with_receipt()
    current_feedback = config['port'].feedback_snapshot()
    return {'scene': current_scene, 'scene_received_s': received_s,
            'feedback': current_feedback}


def _mutate_prepared_source(config, field):
    observer = config['guard'].scene_observer
    if field == 'session':
        observer.last['simulation_session_id'] = 'changed-scene-session'
    elif field == 'reset':
        observer.last['reset_epoch'] = 2
    elif field == 'model':
        observer.last['model_sha256'] = '0' * 64
    elif field in ('arm', 'freebody', 'qvel'):
        key = 'qvel' if field == 'qvel' else 'qpos'
        index = 0 if field == 'arm' else 7 if field == 'freebody' else 0
        observer.last[key][index] += .001
    elif field == 'scope':
        scope = config['local_state'].scope
        scope['epoch'] = 'changed-attempt'
        config['local_state']._scope_json = canonical_bytes(scope)
    elif field == 'source_stale':
        config['port']._feedback(sample(source=.8))
    elif field == 'source_future':
        config['port']._head_samples.clear()
        config['port']._feedback(sample(source=1.001))
    elif field == 'receipt_stale':
        config['port']._head_feedback['wall_s'] -= .3
    else:
        raise AssertionError(field)


_SOURCE_MUTATIONS = (
    'session', 'reset', 'model', 'arm', 'freebody', 'qvel', 'scope',
    'source_stale', 'source_future', 'receipt_stale',
)


@pytest.mark.parametrize('field', _SOURCE_MUTATIONS)
def test_changed_source_refuses_before_reservation_and_sdk(composed, field):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    prepared = config['guard'].prepare(.3)
    _mutate_prepared_source(config, field)
    with pytest.raises((PermissionError, ValueError)):
        sender.send_prepared_head(prepared)
    assert 'NATIVE_RESERVE' not in events and 'SDK_SEND' not in events
    assert not servers['neck'].socket_state.reserved


@pytest.mark.parametrize('field', _SOURCE_MUTATIONS)
def test_changed_source_refuses_at_final_sdk_revalidation(composed, field):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    guard = config['guard']
    original = guard.revalidate
    calls_seen = 0
    def mutate_at_final(prepared):
        nonlocal calls_seen
        calls_seen += 1
        if calls_seen == 3:
            _mutate_prepared_source(config, field)
        return original(prepared)
    guard.revalidate = mutate_at_final
    with pytest.raises((PermissionError, ValueError)):
        send_target(sender, config)
    assert calls_seen == 3
    assert 'NATIVE_RESERVE' in events and 'SDK_SEND' not in events
    assert sender.inventory and len(servers['neck'].socket_state.reserved) == 1
    assert 'sdk_attempt_ns' in next(iter(sender.inventory.values()))
    assert sender.revoked and faults


def test_issued_proof_bytes_mutation_refuses_before_reservation(composed):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    prepared = config['guard'].prepare(.3)
    object.__setattr__(prepared, 'proof_bytes', b'forged proof bytes')
    with pytest.raises(PermissionError, match='HEAD_TRAJECTORY_PREPARED_MUTATED'):
        sender.send_prepared_head(prepared)
    assert not events and not owned and not sender.inventory


def test_actual_prepare_records_rounded_duration_and_exact_original_point_nanoseconds(composed):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    prepared = config['guard'].prepare(.3)
    proof = prepared.proof
    distance = abs(.3 - proof['measured_neck_position_rad'])
    expected_ns = max(100_000_000,
        math.ceil(1.875 * distance / .5 * 1e9),
        math.ceil((5.773502691896258 * distance / .5) ** .5 * 1e9))
    assert proof['main_duration_ns'] == expected_ns
    assert proof['last_point_offset_ns'] == 600_000_000 + expected_ns
    from control_msgs.action import FollowJointTrajectory
    from rclpy.serialization import deserialize_message
    wire = deserialize_message(prepared.original_cdr, FollowJointTrajectory.Goal)
    assert wire.trajectory.points[0].time_from_start.sec * 1_000_000_000 + \
        wire.trajectory.points[0].time_from_start.nanosec == 600_000_000
    assert wire.trajectory.points[1].time_from_start.sec * 1_000_000_000 + \
        wire.trajectory.points[1].time_from_start.nanosec == expected_ns + 600_000_000


def test_boundary_revalidation_accepts_new_scene_step_with_unchanged_full_state(composed):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    prepared = config['guard'].prepare(.3)
    observer = config['guard'].scene_observer
    frame = observer.snapshot()
    frame['simulation_step'] += 1
    frame['clock_interval_begin_monotonic_ns'] -= 1_000
    frame['clock_interval_end_monotonic_ns'] -= 1_000
    assert observer.accept(frame)
    proof = config['guard'].revalidate(prepared)
    assert proof['requested_target_rad'] == .3
    assert not events and not owned and not sender.inventory


@pytest.mark.parametrize('velocity,accepted', [
    (.04136050464213824, True), (.04136050564213824, False),
])
def test_actual_guard_uses_measured_quiet_velocity_threshold(composed, velocity, accepted):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    config['port']._head_feedback['velocities'] = (velocity,)
    if accepted:
        prepared = config['guard'].prepare(.3)
        assert prepared.proof['measured_neck_velocity_rad_s'] == velocity
    else:
        with pytest.raises(PermissionError, match='HEAD_TRAJECTORY_MEASURED_ANCHOR_INVALID'):
            config['guard'].prepare(.3)
    assert not events and not owned


def test_original_400ms_claim_does_not_renew_after_slow_reservation(composed, monkeypatch):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    reserve = config['authority'].reserve
    def slow_reserve(*args, **kwargs):
        result = reserve(*args, **kwargs)
        time.sleep(.41)
        return result
    monkeypatch.setattr(config['authority'], 'reserve', slow_reserve)
    with pytest.raises(PermissionError, match='HEAD_INVENTORY_CLAIM_EXPIRED'):
        send_target(sender, config)
    assert 'NATIVE_RESERVE' in events and 'SDK_SEND' not in events
    record = next(iter(sender.inventory.values()))
    assert record['deadline_ns'] - record['claim_monotonic_ns'] == 400_000_000
    assert 'reserve_attempt_ns' in record and 'reserved_ns' in record
    assert 'sdk_attempt_ns' not in record


def test_original_search_deadline_is_rechecked_at_final_sdk_without_refresh(composed):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    guard = config['guard']
    wall = config['port']._test_wall
    start_ns = round(wall[0] * 1e9)
    snapshot, _, _ = guard._capture()
    duration_ns = guard._duration_ns(.3 - snapshot.neck_position)
    last_offset_ns = 600_000_000 + duration_ns
    config['local_state']._search_deadline_ns = start_ns + 4_000_000 + last_offset_ns + 150_000_000
    original = guard.revalidate
    calls_seen = 0
    prepared_headers = []
    def delayed_final(prepared):
        nonlocal calls_seen
        calls_seen += 1
        proof = prepared.proof
        prepared_headers.append((proof['header_stamp_ns'], proof['last_point_offset_ns']))
        if calls_seen == 3:
            wall[0] += .2
        return original(prepared)
    guard.revalidate = delayed_final
    with pytest.raises(PermissionError, match='HEAD_TRAJECTORY_PREPARED_HEADER_EXPIRED'):
        send_target(sender, config)
    assert calls_seen == 3 and len(set(prepared_headers)) == 1
    original_header_ns, endpoint_ns = prepared_headers[0]
    current_ros_ns = guard.node.get_clock().now().nanoseconds
    now_wall_ns = round(wall[0] * 1e9)
    original_deadline_ns = config['local_state'].search_deadline_ns
    assert original_header_ns > current_ros_ns
    assert original_deadline_ns > now_wall_ns
    assert not guard._deadline_fits(original_deadline_ns, original_header_ns,
                                    endpoint_ns, current_ros_ns, now_wall_ns)
    assert 'NATIVE_RESERVE' in events and 'SDK_SEND' not in events
    record = next(iter(sender.inventory.values()))
    assert 'sdk_attempt_ns' in record
    assert sender.revoked and faults


@pytest.mark.parametrize('composed', [.1], indirect=True)
def test_actual_initial_pose_prepares_coarse_edge_with_full_prefix_and_sdk_receipt(composed,
                                                                                   record_property):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    prepared = config['guard'].prepare(-.17559216195018026)
    proof = prepared.proof
    gid = sender.send_prepared_head(prepared)
    record_property('initial_full_qpos', proof['scene_qpos'])
    record_property('initial_full_qvel', proof['scene_qvel'])
    record_property('initial_cup_xyz_quaternion', proof['scene_qpos'][7:14])
    record_property('coarse_edge_collision_proof', proof['collision'])
    assert proof['measured_neck_position_rad'] == pytest.approx(.1)
    assert proof['requested_target_rad'] == pytest.approx(-.17559216195018026)
    assert proof['collision']['prefix_envelope_samples'] >= 2
    assert proof['collision']['main_samples'] >= 2
    assert proof['collision']['prefix_sample_spacing_rad'] <= .001
    assert gid == owned[0][0]['goal_uuid']
    assert events == ['OWN_INVENTORY', 'NATIVE_RESERVE', 'SDK_SEND']
    assert not faults and servers['neck'].socket_state.reserved


def _bound_neck_port(config, sender, *, timeout=.08, handoff=None):
    from so101_demo.adapters.act.ros_neck import RosNeckSearchPort
    neck = RosNeckSearchPort(config['port'].node, session_id='s', attempt_id='a',
        goal_duration_s=.5, submit_lead_s=.004, stop_timeout_s=timeout,
        stop_velocity_rad_s=.002, max_age_s=.15,
        command_guard=lambda *args: True, monotonic=time.monotonic,
        controller_port=sender, feedback_policy=config['port'].feedback_policy,
        head_trajectory_guard=config['guard'], progress=lambda: time.sleep(.001))
    neck._head_stop_handoff = handoff
    return neck


def test_file_head_command_refuses_without_owned_pause_binding(composed):
    config, events, owned, faults, servers, calls = composed
    sender = HeadInventoryDispatcher(**config)
    neck = _bound_neck_port(config, sender)
    with pytest.raises(PermissionError, match='NECK_HEAD_PAUSED_ADMISSION_UNBOUND'):
        neck.command_neck(.3, session_id='s', attempt_id='a', observation_time_s=1.)
    assert 'SDK_SEND' not in events
    assert not owned and not sender.inventory


@pytest.mark.parametrize('boundary', ['reserve', 'sdk'])
def test_stop_handoff_and_unknown_uuid_cancel_start_before_blocked_dispatch_release(
        paused_head, monkeypatch, boundary):
    case = paused_head
    sender, neck = case.dispatcher, case.neck
    entered, release, cancel = threading.Event(), threading.Event(), threading.Event()
    handoff_started = threading.Event()
    handoff_records, stop_results, command_errors = [], [], []
    actual_handoff = neck._head_stop_handoff
    def handoff(occurred_ns, deadline_ns):
        handoff_records.append((occurred_ns, deadline_ns))
        handoff_started.set()
        return actual_handoff(occurred_ns, deadline_ns)
    neck._head_stop_handoff = handoff
    actual_cancel = case.row.port.cancel
    def cancel_goal(gid):
        cancel.set()
        return actual_cancel(gid)
    monkeypatch.setattr(case.row.port, 'cancel', cancel_goal)

    if boundary == 'reserve':
        reserve = case.row.authority.reserve
        def blocked_reserve(role, *, goal, goal_uuid, before_reserve):
            def bind_then_block(binding):
                result = before_reserve(binding)
                entered.set()
                if not release.wait(timeout=2.):
                    raise TimeoutError('test reserve release timed out')
                return result
            return reserve(role, goal=goal, goal_uuid=goal_uuid,
                           before_reserve=bind_then_block)
        monkeypatch.setattr(case.row.authority, 'reserve', blocked_reserve)
    else:
        send = case.row.action_client.send_goal_async
        def blocked_send(*args, **kwargs):
            entered.set()
            if not release.wait(timeout=2.):
                raise TimeoutError('test SDK release timed out')
            return send(*args, **kwargs)
        monkeypatch.setattr(case.row.action_client, 'send_goal_async', blocked_send)

    command_thread = threading.Thread(target=lambda: _capture_error(command_errors,
        lambda: command(case)))
    command_thread.start()
    stop_thread = None
    try:
        assert entered.wait(timeout=1.)
        stop_thread = threading.Thread(target=lambda: _capture_error(stop_results,
                                                                    neck.stop_and_confirm))
        stop_thread.start()
        saw_handoff = handoff_started.wait(timeout=.04)
        saw_cancel = cancel.wait(timeout=.04)
        inventory_before_release = sender.inventory
        original_deadline = case.row.runtime.stop_receipt()['stop_deadline_wall_s']
        release.set()
        stop_thread.join(timeout=1.5)
        command_thread.join(timeout=1.)
        assert not stop_thread.is_alive() and not command_thread.is_alive()
        assert saw_handoff and saw_cancel
        assert len(handoff_records) == 1
        assert handoff_records[0][1] > handoff_records[0][0]
        assert len(inventory_before_release) == 1
        assert stop_results and isinstance(stop_results[0], RuntimeError)
        assert case.row.runtime.stop_receipt()['stop_deadline_wall_s'] == original_deadline
        assert case.row.runtime.stop_receipt()['physical_stop_confirmed'] is False
        assert case.state['paused'] is False
        if boundary == 'reserve':
            assert not any(event[0] == 'SDK_SEND' for event in case.events)
    finally:
        release.set()
        command_thread.join(timeout=1.)
        if stop_thread is not None: stop_thread.join(timeout=1.5)


def _capture_error(errors, callback):
    try:
        callback()
    except Exception as error:
        errors.append(error)
