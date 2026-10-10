"""Directed tests for the shared-original local ROS observer."""

import importlib
import importlib.util
import itertools
import threading
import time
import uuid
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from so101_demo.act.head_evidence_identity import digest
from so101_demo.act.head_feedback import FeedbackPolicy
from so101_demo.act.head_local_state import HeadLocalState
from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
from so101_demo.adapters.act.ros_execution import RosControllerPort
from so101_demo.adapters.act import ros_neck


CAMERA_FRAME = 'head_camera_optical_frame'
_SEQUENCE = itertools.count(1)


def observer_module():
    return importlib.import_module('so101_demo.adapters.act.head_local_observer')


def simulation_policy(**overrides):
    document = HeadSimulationPolicy.default_document()
    document.update(overrides)
    return HeadSimulationPolicy.parse(document)


def local_state(policy, **scope_overrides):
    sequence = next(_SEQUENCE)
    scope = dict(epoch='epoch-%d' % sequence, generation=7,
                 session_id='session-%d' % sequence,
                 policy_sha256=digest(policy.readback()),
                 controller_identity=dict(generation=7, incarnation='inc-1', boot='boot-1'))
    scope.update(scope_overrides)
    return HeadLocalState(scope, 10**18)


class FakeTime:
    def __init__(self, wall=100.0, sim=10.0):
        self.wall, self.sim = wall, sim

    def monotonic(self):
        return self.wall

    def now_ns(self):
        return round(self.sim * 1e9)


class ServiceClient:
    def __init__(self, kind, calls):
        self.kind, self.calls = kind, calls
        self.statuses = []
        self.block = None
        self.dead = False

    def service_is_ready(self):
        return True

    def call_async(self, request):
        self.calls.append((self.kind, request))
        if self.block is not None:
            self.block.wait(5.)
        future = Future()
        future.set_result(self.response(request))
        return future

    def response(self, request):
        from action_msgs.srv import CancelGoal
        return CancelGoal.Response(return_code=CancelGoal.Response.ERROR_NONE,
                                   goals_canceling=[])


class ResultClient(ServiceClient):
    def response(self, request):
        status = self.statuses.pop(0) if self.statuses else 0
        return SimpleNamespace(status=status, result=SimpleNamespace(error_code=0,
                                                                    error_string=''))


def observer_setup(monkeypatch, *, policy=None, clock=None, camera_frame=CAMERA_FRAME,
                   fault_calls=None, bind_faults=True, bind_port_sink=True, unbound=False):
    policy = simulation_policy() if policy is None else policy
    clock = FakeTime() if clock is None else clock
    calls, subscriptions, destroyed = [], [], []
    clients = {}

    class ActionClient:
        def __init__(self, *args):
            calls.append(('action_client', args))

        def server_is_ready(self):
            return True

        def send_goal_async(self, message, **options):
            calls.append(('send', message, options))
            raise AssertionError('the local observer must never send a goal')

    def create_client(kind, name):
        short = name.split('/')[-1]
        client = (ResultClient if 'get_result' in name else ServiceClient)(short, calls)
        clients[short] = client
        calls.append(('client', kind, name))
        return client

    node = SimpleNamespace(
        get_fully_qualified_name=lambda: '/head_test_owned',
        create_subscription=lambda *args: subscriptions.append(args),
        create_client=create_client,
        destroy_client=lambda client: destroyed.append(('client', client.kind)) or True,
        destroy_subscription=lambda subscription: destroyed.append(('subscription',)) or True,
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(
            nanoseconds=round(clock.sim * 1e9))))
    monkeypatch.setattr(ros_neck, 'ActionClient', ActionClient)
    action_client = ActionClient(node, None, '/neck_controller/follow_joint_trajectory')
    port = RosControllerPort(node, action_client, ('neck_yaw_joint',),
        max_age_s=.01, stop_velocity_rad_s=.002, monotonic=clock.monotonic,
        feedback_policy=FeedbackPolicy.parse(policy.feedback_values(), simulation_policy=policy))
    state = local_state(policy, **({'controller_identity': None} if unbound else {}))
    faults = fault_calls if fault_calls is not None else []
    module = observer_module()
    observer = module.HeadLocalObserver(node, port, state, policy=policy,
        fault_callback=(faults.append if bind_faults else None), camera_frame=camera_frame,
        monotonic=clock.monotonic, bind_port_sink=bind_port_sink)
    return SimpleNamespace(node=node, port=port, state=state, policy=policy, clock=clock,
                           observer=observer, calls=calls, subscriptions=subscriptions,
                           clients=clients, faults=faults, destroyed=destroyed,
                           action_client=action_client)


def wait_for(predicate, timeout_s=2.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.002)
    return predicate()


def clock_record(clock, source, *, valid=True):
    return dict(wall_s=clock.wall, source_ns=round(source * 1e9), valid=valid)


def image_record(clock, source, *, frame_id=CAMERA_FRAME, valid=True):
    record = dict(wall_s=clock.wall, source_ns=round(source * 1e9), frame_id=frame_id,
                  valid=valid, width=640, height=480)
    record['payload_sha256'] = ('a' * 64) if valid else None
    return record


def info_record(clock, source, *, frame_id=CAMERA_FRAME, valid=True):
    return dict(wall_s=clock.wall, source_ns=round(source * 1e9), frame_id=frame_id,
                valid=valid, width=640, height=480)


def joint_record(clock, source, *, sequence=1, valid=True):
    return dict(wall_s=clock.wall, callback_sim_ns=round(clock.sim * 1e9), valid=valid,
                source_ns=round(source * 1e9), positions=(.2,), velocities=(0.,),
                raw_names=('neck_yaw_joint',), raw_positions=(.2,), raw_velocities=(0.,),
                sequence=sequence)


def inventory(port, gid, **overrides):
    record = dict(accepted=None, handle=None, result=None, cancel_requested=False,
                  cancel_ack=False, error=None, goal={})
    record.update(overrides)
    with port._lock:
        port._goals[gid] = record
    return record


def test_local_observer_is_a_real_component_api():
    spec = importlib.util.find_spec("so101_demo.adapters.act.head_local_observer")
    assert spec is not None, "HeadLocalObserver component module must exist"
    module = __import__("so101_demo.adapters.act.head_local_observer", fromlist=["HeadLocalObserver"])
    assert callable(getattr(module, "HeadLocalObserver", None))


def test_observer_exports_original_and_action_response_boundaries():
    spec = importlib.util.find_spec("so101_demo.adapters.act.head_local_observer")
    assert spec is not None, "HeadLocalObserver component module must exist"
    module = __import__("so101_demo.adapters.act.head_local_observer", fromlist=["HeadLocalObserver"])
    observer = module.HeadLocalObserver
    for name in ("observe_original", "request_results", "request_cancel_all", "close"):
        assert callable(getattr(observer, name, None)), name


def test_observer_shares_the_existing_node_and_never_creates_a_send_goal_client(monkeypatch):
    setup_row = observer_setup(monkeypatch)
    created = [row for row in setup_row.calls if row[0] == 'client']
    assert [row[0] for row in setup_row.calls if row[0] == 'action_client'] == ['action_client']
    assert sorted(row[2] for row in created) == [
        '/neck_controller/follow_joint_trajectory/_action/cancel_goal',
        '/neck_controller/follow_joint_trajectory/_action/get_result']
    assert [row[1] for row in setup_row.subscriptions] == [
        '/joint_states', '/neck_controller/follow_joint_trajectory/_action/status']
    assert setup_row.port._head_original_sink is not None
    assert setup_row.port._goals == {}


def test_observer_refuses_a_foreign_node_port_or_unbound_policy(monkeypatch):
    module = observer_module()
    setup_row = observer_setup(monkeypatch)
    policy = setup_row.policy
    state = local_state(policy)
    with pytest.raises((TypeError, ValueError)):
        module.HeadLocalObserver(setup_row.node, object(), state, policy=policy,
                                 camera_frame=CAMERA_FRAME, fault_callback=lambda reason: None)
    with pytest.raises((TypeError, ValueError, PermissionError)):
        module.HeadLocalObserver(SimpleNamespace(), setup_row.port, state, policy=policy,
                                 camera_frame=CAMERA_FRAME, fault_callback=lambda reason: None)
    with pytest.raises((TypeError, ValueError, PermissionError)):
        module.HeadLocalObserver(setup_row.node, setup_row.port, state,
                                 policy=simulation_policy(search_timeout_s=29.),
                                 camera_frame=CAMERA_FRAME, fault_callback=lambda reason: None)


def test_advancing_originals_are_retained_without_new_clocks(monkeypatch):
    setup_row = observer_setup(monkeypatch)
    for source in (1., 1.01, 1.02):
        setup_row.clock.sim = source
        setup_row.observer.observe_original('CLOCK', clock_record(setup_row.clock, source))
    setup_row.clock.sim = 1.02
    setup_row.observer.observe_original('IMAGE', image_record(setup_row.clock, 1.02))
    setup_row.observer.observe_original('INFO', info_record(setup_row.clock, 1.02))
    setup_row.observer.observe_original('JOINT', joint_record(setup_row.clock, 1.02, sequence=4))
    snapshot = setup_row.observer.snapshot()
    assert snapshot['clock']['source_ns'] == round(1.02e9)
    assert snapshot['image']['source_ns'] == round(1.02e9)
    assert snapshot['info']['source_ns'] == round(1.02e9)
    assert snapshot['joint']['sequence'] == 4
    assert snapshot['clock']['wall_s'] == setup_row.clock.wall
    assert setup_row.faults == [] and setup_row.state.faulted is False
    pair = setup_row.observer.camera_pair()
    assert pair['frame_id'] == CAMERA_FRAME and pair['source_ns'] == round(1.02e9)


@pytest.mark.parametrize('damage', ['nonadvancing', 'zero_source', 'wrong_frame', 'invalid'])
def test_invalid_or_nonadvancing_camera_original_latches_before_retention(monkeypatch, damage):
    setup_row = observer_setup(monkeypatch)
    setup_row.clock.sim = 1.02
    setup_row.observer.observe_original('IMAGE', image_record(setup_row.clock, 1.02))
    setup_row.clock.sim = 1.03
    source = 1.02 if damage == 'nonadvancing' else (0. if damage == 'zero_source' else 1.03)
    frame = 'other_frame' if damage == 'wrong_frame' else CAMERA_FRAME
    setup_row.observer.observe_original('IMAGE',
        image_record(setup_row.clock, source, frame_id=frame, valid=damage != 'invalid'))
    snapshot = setup_row.observer.snapshot()
    assert snapshot['image']['valid'] is False
    assert snapshot['image']['source_ns'] == round(source * 1e9)
    assert setup_row.state.faulted is True
    assert setup_row.faults and setup_row.faults[-1] == 'HEAD_LOCAL_OBSERVER_CAMERA_INVALID'
    assert setup_row.state.fault_occurrence_ns is not None
    assert snapshot['image_source_ns'] == round(1.02e9)


def test_nonadvancing_clock_original_hard_faults_without_replacing_the_watermark(monkeypatch):
    setup_row = observer_setup(monkeypatch)
    setup_row.observer.observe_original('CLOCK', clock_record(setup_row.clock, 1.0))
    setup_row.observer.observe_original('CLOCK', clock_record(setup_row.clock, 1.0))
    assert setup_row.state.faulted is True
    assert setup_row.faults == ['HEAD_LOCAL_OBSERVER_CLOCK_NONADVANCING']
    snapshot = setup_row.observer.snapshot()
    assert snapshot['clock']['source_ns'] == round(1.0e9)
    assert snapshot['clock']['valid'] is False
    assert snapshot['clock_source_ns'] == round(1.0e9)


@pytest.mark.parametrize('kind', ['IMAGE', 'INFO'])
def test_invalid_camera_fragment_closes_admission_before_unlocked_diagnostics(monkeypatch, kind):
    row = observer_setup(monkeypatch)
    observer = row.observer
    observer.observe_original('CLOCK', clock_record(row.clock, 1.02))
    observer.observe_original('JOINT', joint_record(row.clock, 1.02))
    observer.observe_original('IMAGE', image_record(row.clock, 1.02))
    observer.observe_original('INFO', info_record(row.clock, 1.02))
    reached, release = threading.Event(), threading.Event()
    invalidate = observer._invalidate
    errors = []

    def paused_invalidate(reason, **kwargs):
        reached.set()
        assert release.wait(2.)
        return invalidate(reason, **kwargs)

    monkeypatch.setattr(observer, '_invalidate', paused_invalidate)

    def deliver():
        try:
            record = (image_record if kind == 'IMAGE' else info_record)(
                row.clock, 1.03, valid=False)
            assert observer.observe_original(kind, record) is False
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=deliver)
    worker.start()
    try:
        assert reached.wait(2.)
        assert row.state.faulted is True
        origin = row.state.fault_occurrence_ns
        assert observer.failed is True
        with pytest.raises(PermissionError, match='CURRENT_INVALID'):
            observer.camera_pair()
        with pytest.raises(PermissionError, match='CURRENT_INVALID'):
            observer.current_inputs(row.clock.wall)
        assert observer._lock.acquire(blocking=False)
        observer._lock.release()
    finally:
        release.set()
        worker.join(2.)
    assert not worker.is_alive() and not errors
    assert row.state.fault_occurrence_ns == origin
    assert row.faults == ['HEAD_LOCAL_OBSERVER_CAMERA_INVALID']


def test_invalid_joint_original_is_retained_and_latches_before_recovery(monkeypatch):
    setup_row = observer_setup(monkeypatch)
    setup_row.observer.observe_original('JOINT',
        joint_record(setup_row.clock, 1.0, sequence=1, valid=False))
    assert setup_row.state.faulted is True
    assert setup_row.observer.snapshot()['joint']['valid'] is False
    assert setup_row.faults == ['HEAD_LOCAL_OBSERVER_JOINT_INVALID']
    setup_row.observer.observe_original('JOINT', joint_record(setup_row.clock, 1.01, sequence=2))
    snapshot = setup_row.observer.snapshot()
    assert snapshot['joint']['sequence'] == 2
    assert snapshot['joint_count'] == 2
    assert setup_row.state.faulted is True
    assert setup_row.faults == ['HEAD_LOCAL_OBSERVER_JOINT_INVALID']
    with pytest.raises((TypeError, ValueError, PermissionError)):
        setup_row.observer.observe_original('JOINT', dict(wall_s='bad', source_ns=1, valid=True))
    assert setup_row.state.faulted is True


def test_unknown_inventory_uuid_is_cancelled_without_a_goal_handle(monkeypatch):
    setup_row = observer_setup(monkeypatch)
    gid = str(uuid.uuid4())
    inventory(setup_row.port, gid)
    setup_row.observer.request_cancel_all()
    assert wait_for(lambda: any(row[0] == 'cancel_goal' for row in setup_row.calls))
    cancel_requests = [row[1] for row in setup_row.calls if row[0] == 'cancel_goal']
    assert len(cancel_requests) == 1
    assert bytes(cancel_requests[0].goal_info.goal_id.uuid) == uuid.UUID(gid).bytes
    assert setup_row.port._goals[gid]['cancel_requested'] is True
    assert not [row for row in setup_row.calls if row[0] == 'get_result']
    setup_row.port.close_head_io(timeout_s=1.)


def test_terminal_inventory_is_not_cancelled_or_re_requested(monkeypatch):
    setup_row = observer_setup(monkeypatch)
    gid = str(uuid.uuid4())
    inventory(setup_row.port, gid, accepted=True, result=SimpleNamespace(status=4))
    setup_row.observer.request_cancel_all()
    setup_row.observer.request_results()
    time.sleep(.05)
    assert not [row for row in setup_row.calls if row[0] in ('cancel_goal', 'get_result')]
    setup_row.port.close_head_io(timeout_s=1.)


def test_status_zero_stays_unknown_and_terminal_retains_original_clocks(monkeypatch):
    setup_row = observer_setup(monkeypatch)
    gid = str(uuid.uuid4())
    inventory(setup_row.port, gid)
    setup_row.clients['get_result'].statuses = [0]
    setup_row.observer.request_results()
    assert wait_for(lambda: any(row[0] == 'get_result' for row in setup_row.calls))
    time.sleep(.02)
    assert setup_row.port._goals[gid]['accepted'] is None
    assert setup_row.port._goals[gid]['result'] is None
    setup_row.calls.clear()
    setup_row.clock.wall, setup_row.clock.sim = 100.25, 10.25
    setup_row.clients['get_result'].statuses = [4]
    setup_row.observer.request_results()
    assert wait_for(lambda: setup_row.port._goals[gid]['result'] is not None)
    record = setup_row.port._goals[gid]
    assert record['accepted'] is True
    assert record['terminal_wall_s'] == 100.25
    assert record['terminal_source_floor_ns'] == round(10.25e9)
    setup_row.port.close_head_io(timeout_s=1.)


def test_contradicting_terminal_responses_hard_fault_the_observer(monkeypatch):
    setup_row = observer_setup(monkeypatch)
    gid = str(uuid.uuid4())
    inventory(setup_row.port, gid)
    setup_row.clients['get_result'].statuses = [4, 5]
    setup_row.observer.request_result(gid)
    assert wait_for(lambda: setup_row.port._goals[gid]['result'] is not None)
    setup_row.observer.request_result(gid)
    assert wait_for(lambda: setup_row.state.faulted is True)
    assert setup_row.faults and setup_row.faults[-1] == 'HEAD_LOCAL_OBSERVER_TERMINAL_CONTRADICTION'
    setup_row.port.close_head_io(timeout_s=1.)


def test_status_array_proves_acceptance_but_a_terminal_status_is_not_a_result(monkeypatch):
    setup_row = observer_setup(monkeypatch)
    gid = str(uuid.uuid4())
    inventory(setup_row.port, gid)
    from action_msgs.msg import GoalStatus, GoalStatusArray
    from unique_identifier_msgs.msg import UUID
    message = GoalStatusArray()
    status = GoalStatus()
    status.goal_info.goal_id = UUID(uuid=list(uuid.UUID(gid).bytes))
    status.status = 4
    message.status_list = [status]
    setup_row.observer._status(message)
    record = setup_row.port._goals[gid]
    assert record['accepted'] is True
    assert record['result'] is None
    assert setup_row.observer.snapshot()['action_status'][gid] == 4


def test_observer_close_retires_its_clients_and_refuses_further_observation(monkeypatch):
    setup_row = observer_setup(monkeypatch)
    setup_row.observer.observe_original('CLOCK', clock_record(setup_row.clock, 1.0))
    receipt = setup_row.observer.close()
    assert receipt['subscriptions_retired'] is True
    assert receipt['clients_retired'] is True
    with pytest.raises(PermissionError):
        setup_row.observer.observe_original('CLOCK', clock_record(setup_row.clock, 1.01))
    assert setup_row.observer.closed is True
    assert [row[0] for row in setup_row.destroyed].count('client') == 2
    assert [row[0] for row in setup_row.destroyed].count('subscription') == 1


def test_read_between_camera_callbacks_keeps_newest_complete_original_pair(monkeypatch):
    row=observer_setup(monkeypatch)
    row.clock.sim=1.02
    row.observer.observe_original('CLOCK',clock_record(row.clock,1.02))
    row.observer.observe_original('JOINT',joint_record(row.clock,1.02,sequence=1))
    first_image=image_record(row.clock,1.02)
    first_info=info_record(row.clock,1.02)
    row.observer.observe_original('IMAGE',first_image)
    row.observer.observe_original('INFO',first_info)
    row.clock.sim=1.12
    row.clock.wall+=.1
    second_image=image_record(row.clock,1.12)
    row.observer.observe_original('IMAGE',second_image)
    current=row.observer.current_inputs(row.clock.wall)
    assert current['camera_pair']['source_ns']==1_020_000_000
    assert current['image']==first_image and current['info']==first_info
    assert current['image_source_wall_s']==first_image['wall_s']
    assert row.observer.snapshot()['image']['source_ns']==1_120_000_000
    second_info=info_record(row.clock,1.12)
    row.observer.observe_original('INFO',second_info)
    current=row.observer.current_inputs(row.clock.wall)
    assert current['camera_pair']['source_ns']==1_120_000_000
    assert current['image']==second_image and current['info']==second_info


@pytest.mark.parametrize('damage',['invalid','nonadvancing','wrong_frame'])
def test_invalid_current_fragment_cannot_be_hidden_by_older_complete_pair(monkeypatch,damage):
    row=observer_setup(monkeypatch)
    row.clock.sim=1.02
    row.observer.observe_original('IMAGE',image_record(row.clock,1.02))
    row.observer.observe_original('INFO',info_record(row.clock,1.02))
    source=1.02 if damage=='nonadvancing' else 1.12
    row.observer.observe_original('IMAGE',image_record(row.clock,source,
        valid=damage!='invalid',frame_id='foreign_frame' if damage=='wrong_frame' else CAMERA_FRAME))
    assert row.state.faulted and row.observer.failed
    with pytest.raises(PermissionError):row.observer.camera_pair()
