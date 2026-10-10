"""Production Head admission with typed originals and controlled native/SDK peers.

The MuJoCo model and full collision replay are real; service and action peers
are fixtures. These tests cannot establish installed or physical acceptance.
"""

import time
import threading
from concurrent.futures import Future
from contextlib import contextmanager
from types import SimpleNamespace

import mujoco
import pytest

from test_act_head_local_runtime import armed_runtime, prime_current_inputs, runtime_setup
from test_act_head_trajectory_guard import guard, MODEL, GEOMETRY, GEOMETRY_SHA256
from head_admission_peer_support import admission_peer_cpu_slot, release_guard_buffers


@pytest.fixture
def paused_head(monkeypatch, tmp_path_factory, request):
    with admission_peer_cpu_slot(tmp_path_factory):
        guard = request.getfixturevalue('guard')
        from so101_demo.adapters.act.head_execution_reset import OwnedHeadScene
        from so101_demo.adapters.act.head_execution_scene import HeadSceneSafety, scene_coordinates
        from so101_demo.adapters.act.head_inventory_dispatch import HeadInventoryDispatcher
        from so101_demo.adapters.act.head_trajectory_guard import HeadTrajectoryGuard
        from so101_demo.adapters.act.ros_neck import RosNeckSearchPort
        from so101_mujoco_support.msg import SceneStateEvidence

        row = runtime_setup(monkeypatch)
        joints, bodies = scene_coordinates(guard.checker.model)
        safety = HeadSceneSafety(guard.checker, joints, bodies, 'a' * 64)
        inputs = SimpleNamespace(run=dict(row.state.scope), document={
            'development_pose': dict(arm_rad=[-.25, 0., .6, .8, 0., .8],
                                    neck_rad=.2, cup_xyz=[.02, -.28, .165])})
        simulation_session_id = row.state.scope['session_id']
        data = mujoco.MjData(guard.checker.model)
        events, deadlines, behavior = [], [], {}
        peer_lock = threading.RLock()
        state = dict(epoch=1, step=1, paused=False, pause_count=0)

        def publish():
            message = SceneStateEvidence()
            message.simulation_session_id = simulation_session_id
            message.reset_epoch = state['epoch']
            message.simulation_step = state['step']
            message.paused = state['paused']
            message.header.stamp.sec, message.header.stamp.nanosec = divmod(
                round(row.clock.sim * 1e9), 10**9)
            message.model_sha256 = guard.model_semantic_sha256
            message.qpos, message.qvel = data.qpos.tolist(), data.qvel.tolist()
            message.clock_interval_begin_monotonic_ns = time.monotonic_ns()
            message.clock_interval_end_monotonic_ns = time.monotonic_ns()
            for args in row.subscriptions:
                if args[1] == '/so101/simulation/scene_state':
                    args[2](message)

        class Services:
            def pause(self, paused, *, deadline):
                with peer_lock:
                    events.append(('pause', paused))
                    deadlines.append((paused, deadline))
                    if not paused and (behavior.get('resume_refuse')
                                       or behavior.pop('resume_refuse_once', False)):
                        return False
                    state['paused'] = paused
                    if paused:
                        state['pause_count'] += 1
                    if not paused and state['step'] == 0:
                        state['step'] = 1
                    if not (paused and behavior.get('no_pause_frame')
                            or not paused and behavior.get('no_resume_frame')):
                        publish()
                    if paused and behavior.get('pause_timeout'):
                        raise TimeoutError('controlled uncertain pause')
                    return True

            def active(self, names, **kwargs): return True
            def switch(self, **kwargs): return True

            def reset_pose(self, pose, **kwargs):
                mujoco.mj_resetData(guard.checker.model, data)
                for name, value in zip(('1', '2', '3', '4', '5', '6', 'neck_yaw_joint'),
                                       (*pose['arm_rad'], pose['neck_rad']), strict=True):
                    data.qpos[joints[name]['qpos']] = value
                address = bodies['plastic_cup']['qpos']
                data.qpos[address:address + 7] = (*pose['cup_xyz'], 1., 0., 0., 0.)
                state.update(epoch=state['epoch'] + 1, step=0)
                publish()
                return True

            def close(self): return {'closed': True}

        scene = OwnedHeadScene(node=row.node, inputs=inputs, safety=safety,
            max_age_s=.25, services=Services(),
            emit=lambda kind, record: events.append((kind, record)))
        publish()
        scene.reset(timeout_s=.1)
        scene.resume()
        armed_runtime(row)
        bound_guard = HeadTrajectoryGuard(checker=guard.checker, feedback_port=row.port,
            scene_observer=scene.observer, node=row.node, model_xml_path=MODEL,
            geometry_path=GEOMETRY, geometry_sha256=GEOMETRY_SHA256,
            simulation_session_id=inputs.run['session_id'], reset_epoch=scene.receipt['reset_epoch'])

        def reserve(role, *, goal, goal_uuid, before_reserve):
            assert state['paused'] is True
            claim = time.monotonic_ns()
            identity = row.authority.identity(role)
            binding = SimpleNamespace(role=role, generation=row.authority.generation,
                session_id=row.authority.session_id, goal_cdr=goal, goal_uuid=goal_uuid,
                controller_incarnation=identity['incarnation'],
                controller_boot_incarnation=identity['boot'],
                claim_monotonic_ns=claim, deadline_ns=claim + 400_000_000)
            assert before_reserve(binding) is True
            events.append(('NATIVE_RESERVE', bytes(goal)))
            return True

        row.authority.reserve = reserve
        dispatcher = None
        if getattr(request, 'param', None) != 'unbound':
            dispatcher = HeadInventoryDispatcher(row.port, row.authority, row.state,
                guard=bound_guard, own_inventory=row.runtime.own_inventory,
                fault_callback=row.runtime.fault)
            scene.bind_admission(runtime=row.runtime, guard=bound_guard)
        neck = RosNeckSearchPort(row.node, session_id=row.state.scope['session_id'],
            attempt_id=row.state.scope['epoch'], goal_duration_s=.5, submit_lead_s=.004,
            stop_timeout_s=row.policy.stop_confirmation_timeout_s,
            stop_velocity_rad_s=.002, max_age_s=.15, command_guard=lambda *args: True,
            controller_port=row.port, feedback_policy=row.port.feedback_policy)
        if dispatcher is not None:
            neck.bind_prepared_head(dispatcher, guard=bound_guard,
                stop_handoff=lambda occurred_ns, deadline_ns: row.runtime.stop('signal', {}))

        def sdk(message, **kwargs):
            assert state['paused'] is True
            events.append(('SDK_SEND', kwargs['goal_uuid']))
            return Future()

        row.action_client.send_goal_async = sdk
        # Assembly loads a full model; the live product receives originals during
        # it. Deliver genuinely newer fixture originals before exercising admission.
        prime_current_inputs(row)
        publish()
        events.clear()
        deadlines.clear()
        result = SimpleNamespace(row=row, scene=scene, guard=bound_guard, neck=neck,
            dispatcher=dispatcher, data=data, state=state, events=events,
            behavior=behavior, deadlines=deadlines, publish=publish, peer_lock=peer_lock)
        try:
            yield result
        finally:
            try:
                row.runtime.close(timeout_s=1.)
            finally:
                try:
                    scene.close()
                finally:
                    # Closed Services callbacks share the data cell. Clear it
                    # as well as the inspection handle after retirement.
                    data = result.data = None
                    release_guard_buffers(bound_guard)


@contextmanager
def next_original_pair(case, *, enabled=True):
    """Original peer stays live before the first pause, then retires permanently."""
    retired = threading.Event()
    delivered = threading.Event()
    pause_floor = case.state['pause_count']

    def deliver():
        while not retired.wait(.01):
            # Serialize only this controlled peer and service fixture. A pause
            # cannot overtake a frame that this fixture already started, and
            # resuming never restarts the peer or manufactures Stop freshness.
            with case.peer_lock:
                if case.state['pause_count'] > pause_floor:
                    return
                if not case.state['paused']:
                    prime_current_inputs(case.row)
                    case.publish()
                    delivered.set()

    producer = threading.Thread(target=deliver) if enabled else None
    if producer is not None:
        producer.start()
    try:
        if producer is not None and not delivered.wait(case.row.policy.fault_reaction_limit_s):
            raise TimeoutError('fixture original peer did not deliver within its fixed budget')
        yield
    finally:
        retired.set()
        if producer is not None:
            producer.join(timeout=.2)
            assert not producer.is_alive()


def command(case, *, produce_original=True):
    # Replay a real nonzero displacement for ownership/SDK ordering. Fixed
    # sampling and freshness budgets remain unchanged; numeric guard tests
    # exercise larger trajectories independently of this peer fixture.
    with next_original_pair(case, enabled=produce_original):
        return case.neck.command_neck(.21, session_id=case.row.state.scope['session_id'],
            attempt_id=case.row.state.scope['epoch'], observation_time_s=case.row.clock.sim)


def test_pause_waits_for_next_complete_original_pair_before_capturing_lease(paused_head):
    case = paused_head
    previous = case.row.observer.current_inputs(time.monotonic())['image']['source_ns']
    time.sleep(.13)
    pause = case.scene.services.pause
    seen = []

    def verify_original(paused, *, deadline):
        if paused:
            current = case.row.observer.current_inputs(time.monotonic())
            assert current['image']['source_ns'] > previous
            assert current['info']['source_ns'] == current['image']['source_ns']
            seen.append(dict(current['image']))
        return pause(paused, deadline=deadline)

    case.scene.services.pause = verify_original

    with next_original_pair(case):
        with case.scene.paused_admission(case.guard):
            lease = case.scene._require_lease(case.guard, check_scene=True)
            assert case.state['paused'] is True
            assert lease['thread'] == threading.get_ident()
    assert seen
    assert not case.state['paused'] and not case.row.runtime.faulted
    ready = next(record for kind, record in case.events if kind == 'HEAD_ADMISSION_INPUT_READY')
    assert ready['source_floor_ns'] >= previous
    assert seen[0]['source_ns'] > ready['source_floor_ns']
    assert ready['source_ns'] == seen[0]['source_ns']
    assert lease['deadline_ns'] == ready['deadline_ns']
    assert ready['deadline_ns'] <= round(seen[0]['wall_s'] * 1e9) + 200_000_000


def test_original_peer_keeps_advancing_when_submitter_is_delayed(paused_head):
    case = paused_head
    with next_original_pair(case):
        time.sleep(.03)
        with case.scene.paused_admission(case.guard):
            lease = case.scene._require_lease(case.guard, check_scene=True)
            assert case.state['paused'] is True
    ready = next(record for kind, record in case.events if kind == 'HEAD_ADMISSION_INPUT_READY')
    assert ready['source_ns'] > ready['source_floor_ns']
    assert lease['deadline_ns'] == ready['deadline_ns']
    assert not case.row.runtime.faulted and not case.state['paused']


def test_selected_stopped_observation_uses_complete_pair_without_waiting_for_another(
        paused_head):
    case = paused_head
    original = case.row.observer.current_inputs(time.monotonic())
    selected_deadline_s = time.monotonic() + .15
    case.row.runtime.dispatch_observation_deadline(selected_deadline_s)
    with case.scene.paused_admission(case.guard):
        lease = case.scene._require_lease(case.guard, check_scene=True)
        assert case.state['paused'] is True
    ready = next(record for kind, record in case.events if kind == 'HEAD_ADMISSION_INPUT_READY')
    assert ready['source_ns'] == original['image']['source_ns']
    assert ready['source_ns'] == original['info']['source_ns']
    assert ready['image_receipt_wall_s'] == original['image']['wall_s']
    assert ready['info_receipt_wall_s'] == original['info']['wall_s']
    assert ready['deadline_ns'] <= round(selected_deadline_s * 1e9)
    assert lease['deadline_ns'] == ready['deadline_ns']
    assert not case.row.runtime.faulted and not case.state['paused']
    assert case.row.runtime._observation_deadline_wall_s == selected_deadline_s
    case.row.runtime.dispatch_observation_deadline(None)


def test_expired_selected_observation_never_pauses_or_dispatches(paused_head):
    case = paused_head
    case.row.runtime.dispatch_observation_deadline(time.monotonic() + .005)
    time.sleep(.01)
    with pytest.raises(PermissionError):
        command(case, produce_original=False)
    assert not any(kind in ('pause', 'SDK_SEND', 'HEAD_ADMISSION_INPUT_READY')
                   for kind, _ in case.events)
    assert not case.dispatcher.inventory
    assert case.row.runtime.faulted


def test_missing_next_pair_never_pauses_or_renews_original_wait_budget(paused_head):
    case = paused_head
    image = dict(case.row.observer.current_inputs(time.monotonic())['image'])
    with pytest.raises(PermissionError, match='ORIGINAL_PAIR_TIMEOUT|CAMERA_STALE|ORIGINALS_INVALID'):
        command(case, produce_original=False)
    assert not any(kind in ('pause', 'SDK_SEND', 'HEAD_ADMISSION_INPUT_READY')
                   for kind, _ in case.events)
    assert case.scene._admission_lease is None
    stop = case.row.runtime.stop_receipt()
    assert stop['stop_origin_wall_s'] >= image['wall_s'] + .2 - 1e-9
    assert stop['stop_deadline_wall_s'] == stop['stop_origin_wall_s'] + 1.
    assert stop['physical_stop_confirmed'] is False


def test_stop_remains_independent_while_waiting_for_next_original_pair(paused_head, monkeypatch):
    case = paused_head
    waiting = threading.Event()
    current_inputs = type(case.row.observer).current_inputs
    errors = []

    def observe(owner, now):
        result = current_inputs(owner, now)
        if owner is case.row.observer and case.scene._admission_gate.locked():
            waiting.set()
        return result

    monkeypatch.setattr(type(case.row.observer), 'current_inputs', observe)

    def submit():
        try:
            command(case, produce_original=False)
        except PermissionError as error:
            errors.append(str(error))

    worker = threading.Thread(target=submit)
    worker.start()
    try:
        assert waiting.wait(timeout=.5)
        case.row.runtime.stop('signal', {})
        deadline = case.row.runtime.stop_receipt()['stop_deadline_wall_s']
        worker.join(timeout=.5)
        assert not worker.is_alive() and errors
        assert not any(kind in ('pause', 'SDK_SEND') for kind, _ in case.events)
        assert case.row.runtime.stop_receipt()['stop_deadline_wall_s'] == deadline
    finally:
        worker.join(timeout=1.)


def test_complete_prepared_send_is_paused_and_resumes_before_return(paused_head):
    case = paused_head
    original = case.guard._check_collision_pose
    samples = []

    def replay(qpos, position):
        samples.append(case.state['paused'])
        return original(qpos, position)

    case.guard._check_collision_pose = replay
    gid = command(case)
    assert samples and all(samples)
    kinds = [event[0] for event in case.events]
    assert kinds.index('NATIVE_RESERVE') < kinds.index('SDK_SEND')
    assert next(event for event in case.events if event[0] == 'pause') == ('pause', True)
    assert ('pause', False) in case.events
    assert case.state['paused'] is False
    assert case.neck._goals == [gid]
    assert len(case.dispatcher.inventory) == 1
    trace = case.dispatcher.dispatch_traces[0]
    assert trace['goal_uuid'] == gid
    from rclpy.serialization import deserialize_message
    from control_msgs.action import FollowJointTrajectory
    wire = deserialize_message(trace['original_cdr'], FollowJointTrajectory.Goal)
    assert wire.trajectory.points[0].time_from_start.nanosec == 50_000_000
    assert not case.row.runtime.faulted


@pytest.mark.parametrize('coordinate', ['qpos', 'qvel'])
def test_changed_full_state_during_pause_still_refuses_and_resumes(paused_head, coordinate):
    case = paused_head
    original = case.guard._check_collision_pose
    changed = []

    def replay(qpos, position):
        if not changed:
            changed.append(True)
            getattr(case.data, coordinate)[-1] += 1e-8
            case.publish()
        return original(qpos, position)

    case.guard._check_collision_pose = replay
    with pytest.raises(PermissionError, match='STATE_CHANGED_DURING_CHECK'):
        command(case)
    assert case.row.runtime.faulted
    assert ('pause', False) in case.events and not case.state['paused']
    assert not any(event[0] == 'SDK_SEND' for event in case.events)
    assert case.deadlines[-1][1] == case.row.runtime.stop_receipt()['stop_deadline_wall_s']


def test_original_receipt_lease_expires_inside_collision_replay(paused_head):
    case = paused_head
    original = case.guard._check_collision_pose
    expired = []

    def replay(qpos, position):
        if not expired:
            expired.append(True)
            time.sleep(.21)
        return original(qpos, position)

    case.guard._check_collision_pose = replay
    with pytest.raises(PermissionError, match='HEAD_ADMISSION_LEASE_EXPIRED'):
        command(case)
    assert case.row.runtime.faulted and not case.state['paused']
    assert not any(event[0] == 'NATIVE_RESERVE' for event in case.events)


@pytest.mark.parametrize('failure', ['pause_timeout', 'no_pause_frame', 'resume_refuse_once'])
def test_uncertain_service_never_reports_success_and_uses_original_stop_budget(paused_head, failure):
    case = paused_head
    case.behavior[failure] = True
    with pytest.raises((PermissionError, TimeoutError)):
        command(case)
    assert case.row.runtime.faulted
    assert ('pause', False) in case.events
    assert case.deadlines[-1][1] == case.row.runtime.stop_receipt()['stop_deadline_wall_s']
    assert case.row.runtime.stop_receipt()['physical_stop_confirmed'] is False


def test_stop_racing_sdk_retains_actual_uuid_before_resume(paused_head):
    case = paused_head
    original = case.row.action_client.send_goal_async

    def sdk(message, **kwargs):
        future = original(message, **kwargs)
        case.row.runtime.stop('signal', {})
        return future

    case.row.action_client.send_goal_async = sdk
    with pytest.raises(PermissionError, match='HEAD_ADMISSION_REVOKED'):
        command(case)
    assert len(case.neck._goals) == 1
    assert case.neck._goals[0] in case.dispatcher.inventory
    assert not case.state['paused']
    assert case.deadlines[-1][1] == case.row.runtime.stop_receipt()['stop_deadline_wall_s']


def test_bound_guard_refuses_prepare_outside_its_paused_transaction(paused_head):
    case = paused_head
    with pytest.raises(PermissionError, match='HEAD_ADMISSION_LEASE_REQUIRED'):
        case.guard.prepare(.3)
    assert not any(event[0] == 'pause' for event in case.events)


def test_duplicate_original_remains_immediate_fault_while_paused(paused_head):
    case = paused_head
    original = case.guard._check_collision_pose
    submitted = []

    def replay(qpos, position):
        if not submitted:
            submitted.append(True)
            image = case.row.observer.current_inputs(time.monotonic())['image']
            case.row.observer.observe_original('IMAGE', dict(image))
            assert case.row.observer.failed
        return original(qpos, position)

    case.guard._check_collision_pose = replay
    with pytest.raises(PermissionError, match='HEAD_ADMISSION_REVOKED'):
        command(case)
    assert case.row.runtime.faulted and not case.state['paused']
    assert not any(event[0] == 'SDK_SEND' for event in case.events)


def test_stop_racing_authoritative_resume_never_returns_success(paused_head):
    case = paused_head
    original = case.scene.services.pause

    def pause(paused, *, deadline):
        result = original(paused, deadline=deadline)
        if not paused:
            case.row.runtime.stop('signal', {})
        return result

    case.scene.services.pause = pause
    with pytest.raises(PermissionError, match='HEAD_ADMISSION_REVOKED'):
        command(case)
    assert len(case.neck._goals) == 1
    assert case.neck._goals[0] in case.dispatcher.inventory
    assert not case.state['paused']


@pytest.mark.parametrize('identity', ['session_id', 'generation', 'epoch'])
def test_foreign_owned_run_identity_refuses_binding_before_pause(paused_head, identity):
    case = paused_head
    case.scene.inputs.run[identity] = (
        'foreign' if identity != 'generation' else case.row.state.scope['generation'] + 1)
    # Native scene originals must retain their identity when client inputs are damaged.
    case.publish()
    assert case.scene.observer.hazard is None
    assert case.scene.observer.snapshot()['simulation_session_id'] == case.row.state.scope['session_id']
    with pytest.raises(PermissionError, match='HEAD_ADMISSION_BINDING_INVALID'):
        command(case)
    assert not any(event[0] == 'pause' for event in case.events)
    assert not any(event[0] in ('NATIVE_RESERVE', 'SDK_SEND') for event in case.events)


def test_prepared_cdr_from_retired_lease_cannot_enter_another_transaction(paused_head):
    case = paused_head
    with next_original_pair(case), case.scene.paused_admission(case.guard):
        prepared = case.guard.prepare(.21)
    prime_current_inputs(case.row)
    case.publish()
    with pytest.raises(PermissionError, match='HEAD_ADMISSION_PREPARED_LEASE_INVALID'):
        with next_original_pair(case), case.scene.paused_admission(case.guard):
            case.dispatcher.send_prepared_head(prepared)
    assert not any(event[0] == 'SDK_SEND' for event in case.events)


def test_actual_prepared_bytes_and_uuid_are_retained_for_full_run_readback(paused_head):
    import hashlib
    case = paused_head
    gid = command(case)
    records = [record for kind, record in case.events if kind == 'HEAD_PREPARED_DISPATCH_TRACE']
    assert len(records) == 1
    record = records[0]
    assert record['goal_uuid'] == gid
    payload = bytes.fromhex(record['original_cdr_hex'])
    assert payload == case.row.state.prepared_cdr(gid)
    assert hashlib.sha256(payload).hexdigest() == record['original_cdr_sha256']
    assert record['prepared_proof']['original_cdr_sha256'] == record['original_cdr_sha256']
    assert record['inventory_record']['goal_uuid'] == gid
    assert record['phases'][-1]['phase'] == 'complete'


@pytest.mark.parametrize('failure', ['resume_refuse', 'no_resume_frame'])
def test_resume_ack_or_refusal_without_authoritative_running_proof_stays_failed(paused_head, failure):
    case = paused_head
    case.behavior[failure] = True
    with pytest.raises((PermissionError, TimeoutError)):
        command(case)
    assert case.row.runtime.faulted
    assert not any(kind == 'HEAD_ADMISSION_RESUMED' for kind, _ in case.events)
    assert any(kind == 'HEAD_ADMISSION_RESUME_UNCONFIRMED' for kind, _ in case.events)
    assert case.row.runtime.stop_receipt()['physical_stop_confirmed'] is False
    assert case.deadlines[-1][1] == case.row.runtime.stop_receipt()['stop_deadline_wall_s']
    assert len(case.neck._goals) == 1


def test_rejected_mutated_cdr_log_hash_names_actual_bytes(paused_head):
    import hashlib
    case = paused_head
    prepare = case.guard.prepare
    def damaged(target):
        prepared = prepare(target)
        object.__setattr__(prepared, 'original_cdr', b'rejected changed bytes')
        return prepared
    case.guard.prepare = damaged
    with pytest.raises(PermissionError, match='HEAD_TRAJECTORY_PREPARED_MUTATED'):
        command(case)
    records = [record for kind, record in case.events if kind == 'HEAD_PREPARED_DISPATCH_TRACE']
    assert len(records) == 1
    record = records[0]
    payload = bytes.fromhex(record['original_cdr_hex'])
    assert payload == b'rejected changed bytes'
    assert hashlib.sha256(payload).hexdigest() == record['original_cdr_sha256']
    assert record['prepared_proof']['original_cdr_sha256'] != record['original_cdr_sha256']
    assert record['error_type'] == 'PermissionError'
    assert not any(kind == 'SDK_SEND' for kind, _ in case.events)
