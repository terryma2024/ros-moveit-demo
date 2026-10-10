"""Head v2 feedback decisions keep camera age, source age and stop epochs distinct."""

from types import SimpleNamespace

import pytest
from sensor_msgs.msg import JointState

from so101_demo.adapters.act import ros_neck
from so101_demo.adapters.act.ros_execution import RosControllerPort


def policy():
    # Explicit test quantities only; these do not approve or promote a runtime.
    return dict(joint_max_receipt_age_s=.02, joint_max_source_age_s=.02,
                camera_interarrival_deadline_s=.11, camera_max_source_age_s=.11,
                clock_interarrival_deadline_s=.02, watchdog_period_s=.002,
                watchdog_reaction_limit_s=.010, revoker_connection_deadline_s=.002)


def setup_ports(monkeypatch, **options):
    wall, sim, calls, subscriptions = [10.], [1.], [], []
    node = SimpleNamespace(
        create_subscription=lambda *args: subscriptions.append(args),
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(
            nanoseconds=round(sim[0]*1e9))))
    class Client:
        def __init__(self, *args):
            calls.append(('client', args))
        def server_is_ready(self):
            return True
        def send_goal_async(self, message, **options):
            from concurrent.futures import Future
            calls.append(('send', message, options))
            return Future()
    monkeypatch.setattr(ros_neck, 'ActionClient', Client)
    client = Client(node, None, '/neck_controller/follow_joint_trajectory')
    port = RosControllerPort(node, client, ('neck_yaw_joint',),
        max_age_s=.01, stop_velocity_rad_s=.002, monotonic=lambda: wall[0],
        **{'feedback_policy':policy(),**options})
    return node, client, port, wall, sim, calls, subscriptions


def sample(source=1., velocity=0.):
    message = JointState(name=['neck_yaw_joint'], position=[.2], velocity=[velocity])
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(round(source*1e9), 10**9)
    return message


def neck(node, wall, **options):
    return ros_neck.RosNeckSearchPort(node, session_id='s', attempt_id='a',
        goal_duration_s=.05, submit_lead_s=.004, stop_timeout_s=.07,
        stop_velocity_rad_s=.002, max_age_s=.01, command_guard=lambda *args: True,
        monotonic=lambda: wall[0], feedback_policy=policy(), **options)


def test_injected_head_port_keeps_one_action_client_and_feedback_subscription(monkeypatch):
    node, client, port, wall, _, calls, subscriptions = setup_ports(monkeypatch)
    head = neck(node, wall, controller_port=port)
    assert head.port is port
    assert head.client is client
    assert len([call for call in calls if call[0] == 'client']) == 1
    assert len(subscriptions) == 1


def test_joint_receipt_bound_does_not_borrow_camera_age(monkeypatch):
    node, _, _, wall, sim, calls, _ = setup_ports(monkeypatch)
    head = neck(node, wall)
    head._joint(sample())
    wall[0], sim[0] = 10.015, 1.01
    head.command_neck(.3, session_id='s', attempt_id='a', observation_time_s=1.)
    assert len([call for call in calls if call[0] == 'send']) == 1


@pytest.mark.parametrize('clock_domain', ['source', 'receipt', 'future_source', 'future_receipt'])
def test_head_stop_refuses_invalid_age_in_each_original_clock(monkeypatch, clock_domain):
    _, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port._feedback(sample())
    if clock_domain == 'source':
        sim[0] = 1.1
    elif clock_domain == 'receipt':
        wall[0] = 10.1
    elif clock_domain == 'future_source':
        sim[0] = .99
    else:
        wall[0] = 9.99
    assert port.stopped() is False


def test_one_quiet_sample_after_stop_cannot_be_three_confirmations(monkeypatch):
    _, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port.begin_stop(dict(epoch='stop-1', generation=5, request_wall_s=10.,
                         request_sim_s=1., fault_wall_s=10., stop_latency_s=.07))
    wall[0], sim[0] = 10.01, 1.01
    port._feedback(sample(1.01))
    assert port.stopped() is False
    assert port.stopped() is False


def test_distinct_post_stop_samples_and_terminal_inventory_establish_stop(monkeypatch):
    _, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port._goals['finished'] = dict(accepted=True, result=SimpleNamespace(status=4))
    port.begin_stop(dict(epoch='stop-1', generation=5, request_wall_s=10.,
                         request_sim_s=1., fault_wall_s=10., stop_latency_s=.07))
    for index in range(1, 4):
        wall[0], sim[0] = 10.+index*.01, 1.+index*.01
        port._feedback(sample(sim[0]))
    assert port.stopped() is True
    port._goals['pending'] = dict(accepted=None)
    assert port.stopped() is False


def test_stop_decision_does_not_materialize_consumed_feedback_history(monkeypatch):
    from collections import deque
    from collections.abc import Mapping

    _, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    for index in range(4096):
        port._feedback(sample(.5 + index * .0001))
    physical_history = tuple(port._head_samples)
    materialized = []

    class ArchivedOriginal(Mapping):
        def __init__(self, original):
            self.original = original

        def __getitem__(self, key):
            return self.original[key]

        def __len__(self):
            return len(self.original)

        def __iter__(self):
            # Account for expensive archived metadata copies in the original
            # decision clock. The current three callbacks retain their clocks.
            materialized.append(self.original['sequence'])
            wall[0] += .0001
            return iter(self.original)

    port._head_samples = deque((ArchivedOriginal(row) for row in physical_history), maxlen=4096)
    port.begin_stop(dict(epoch='stop-1', generation=5, request_wall_s=10.,
                         request_sim_s=1., fault_wall_s=10., stop_latency_s=.07))
    for index in range(1, 4):
        wall[0], sim[0] = 10. + index * .01, 1. + index * .01
        port._feedback(sample(sim[0]))
    originals_before = tuple(port._head_samples)
    assert port.stopped() is True
    assert port.stop_predicate_observations[-1]['quiet_count'] == 3
    assert tuple(port._head_samples) == originals_before
    assert materialized == []
    assert port.stopped() is True
    assert port.stop_predicate_observations[-1]['quiet_count'] == 3
    assert materialized == []


@pytest.mark.parametrize('damage', ['moving', 'nonadvancing', 'invalid'])
def test_unconsumed_bad_original_breaks_stop_run_between_polls(monkeypatch, damage):
    _, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port._feedback(sample())
    port.begin_stop(dict(epoch='stop-1', generation=5, request_wall_s=10.,
                         request_sim_s=1., fault_wall_s=10., stop_latency_s=.07))
    wall[0], sim[0] = 10.001, 1.001
    port._feedback(sample(sim[0]))
    assert port.stopped() is False
    wall[0], sim[0] = 10.002, 1.002
    bad = sample(1.001 if damage == 'nonadvancing' else sim[0],
                 .01 if damage == 'moving' else 0.)
    if damage == 'invalid':
        bad.velocity = []
    port._feedback(bad)
    invalid_original = port._head_samples[-1]
    for index in (3, 4):
        wall[0], sim[0] = 10. + index * .001, 1. + index * .001
        port._feedback(sample(sim[0]))
    assert port.stopped() is False
    assert port.stop_predicate_observations[-1]['quiet_count'] == 2
    assert invalid_original in port._head_samples
    assert port.stopped() is False
    assert port.stop_predicate_observations[-1]['quiet_count'] == 2
    wall[0], sim[0] = 10.005, 1.005
    port._feedback(sample(sim[0]))
    assert port.stopped() is True


@pytest.mark.parametrize('damage', ['duplicate', 'regression', 'moving', 'pre_stop', 'deadline'])
def test_stop_run_is_ordered_and_cannot_refresh_a_bad_sample(monkeypatch, damage):
    _, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port.begin_stop(dict(epoch='stop-1', generation=5, request_wall_s=10.,
                         request_sim_s=1., fault_wall_s=10., stop_latency_s=.07))
    sources = [1.01, 1.02, 1.03]
    if damage == 'duplicate':
        sources[-1] = 1.02
    elif damage == 'regression':
        sources[-1] = 1.015
    elif damage == 'pre_stop':
        sources = [.99, 1., 1.01]
    for index, source in enumerate(sources, 1):
        wall[0], sim[0] = 10.+index*.01, max(1.+index*.01, source)
        port._feedback(sample(source, .01 if damage == 'moving' and index == 2 else 0.))
    if damage == 'deadline':
        wall[0] = 10.08
        port._feedback(sample(sim[0]))
    assert port.stopped() is False


@pytest.mark.parametrize('damage', ['zero_source', 'missing_position', 'missing_velocity',
                                  'nonfinite_position', 'nonfinite_velocity', 'duplicate_name'])
def test_invalid_feedback_retains_original_payload_and_callback_clocks(monkeypatch, damage):
    _, _, port, wall, _, _, _ = setup_ports(monkeypatch)
    message = sample(0. if damage == 'zero_source' else 1.)
    if damage == 'missing_position':
        message.position = []
    elif damage == 'missing_velocity':
        message.velocity = []
    elif damage == 'nonfinite_position':
        message.position = [float('nan')]
    elif damage == 'nonfinite_velocity':
        message.velocity = [float('inf')]
    elif damage == 'duplicate_name':
        message.name = ['neck_yaw_joint', 'neck_yaw_joint']
    port._feedback(message)
    original = port._head_samples[-1]
    assert original['valid'] is False
    assert original['wall_s'] == wall[0]
    assert original['callback_sim_ns'] == 1_000_000_000
    assert original['raw_names'] == tuple(message.name)
    assert len(original['raw_positions']) == len(message.position)
    assert len(original['raw_velocities']) == len(message.velocity)
    assert original['source_ns'] == round((0. if damage == 'zero_source' else 1.)*1e9)
    with pytest.raises(ValueError):
        port.feedback_snapshot()


def test_feedback_snapshot_copies_original_before_reading_decision_clocks(monkeypatch):
    node, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port._feedback(sample())
    original_sequence = port._head_sequence
    injected = [False]
    original_clock = node.get_clock
    def clock_after_copy():
        if not injected[0]:
            injected[0] = True
            wall[0], sim[0] = 10.01, 1.01
            port._feedback(sample(1.01))
        return original_clock()
    node.get_clock = clock_after_copy
    snapshot = port.feedback_snapshot()
    assert snapshot['sequence'] == original_sequence
    assert snapshot['source_ns'] == 1_000_000_000
    assert snapshot['decision']['sim_ns'] == 1_010_000_000
    assert snapshot['receipt_age_s'] == .01


def test_current_feedback_waits_for_original_clock_without_rewriting_future_raw_joint(monkeypatch):
    _,_,port,wall,sim,_,_=setup_ports(monkeypatch)
    port._feedback(sample(1.));previous=dict(port._head_feedback)
    wall[0]=10.008;sim[0]=1.008;port._feedback(sample(1.01));pending=dict(port._head_feedback)
    snapshot=port.feedback_snapshot()
    assert snapshot['source_ns']==previous['source_ns'] and snapshot['sequence']==previous['sequence']
    assert snapshot['source_age_s']==pytest.approx(.008)
    assert port._head_feedback==pending and list(port._head_samples)==[previous,pending]
    assert pending['callback_sim_ns']==1_008_000_000 and pending['source_ns']==1_010_000_000
    sim[0]=1.01;wall[0]=10.009
    consumed=port.feedback_snapshot()
    assert consumed['source_ns']==pending['source_ns'] and consumed['wall_s']==10.008
    assert consumed['sequence']==pending['sequence'] and consumed['source_age_s']==0.


@pytest.mark.parametrize('damage',['no_causal','stale','receipt_future','latest_invalid'])
def test_causal_current_feedback_cannot_hide_missing_or_bad_originals(monkeypatch,damage):
    _,_,port,wall,sim,_,_=setup_ports(monkeypatch)
    port._feedback(sample(1.))
    wall[0]=10.008;sim[0]=1.008
    msg=sample(1.01)
    if damage=='latest_invalid':msg.velocity=[]
    port._feedback(msg)
    if damage=='no_causal':sim[0]=.99
    elif damage=='stale':wall[0]=10.03
    elif damage=='receipt_future':wall[0]=9.99
    raw=dict(port._head_feedback)
    with pytest.raises((ValueError,PermissionError)):port.feedback_snapshot()
    assert port._head_feedback==raw and len(port._head_samples)==2


def test_stale_latest_feedback_keeps_actual_negative_stop_predicate(monkeypatch):
    _, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port.begin_stop(dict(epoch='stop-1', generation=5, request_wall_s=10.,
                         request_sim_s=1., fault_wall_s=10., stop_latency_s=.07))
    wall[0], sim[0] = 10.01, 1.01
    port._feedback(sample(1.01))
    wall[0], sim[0] = 10.06, 1.06
    assert port.stopped() is False
    observation = port.stop_predicate_observations[-1]
    assert observation['stopped'] is False
    assert observation['error'] == 'HEAD_FEEDBACK_RECEIPT_STALE'
    assert observation['latest_sample']['sequence'] == port._head_sequence
    assert observation['decision']['sim_ns'] == 1_060_000_000


@pytest.mark.parametrize('source', [1., .995])
def test_nonadvancing_source_cannot_authorize_neck_motion(monkeypatch, source):
    node, _, port, wall, sim, calls, _ = setup_ports(monkeypatch)
    head = neck(node, wall, controller_port=port)
    port._feedback(sample())
    wall[0], sim[0] = 10.005, 1.005
    port._feedback(sample(source))
    with pytest.raises(ValueError, match='HEAD_FEEDBACK_INVALID'):
        head.command_neck(.3, session_id='s', attempt_id='a', observation_time_s=.99)
    assert not [call for call in calls if call[0] == 'send']


@pytest.mark.parametrize('change', ['moving_feedback', 'pending_goal'])
def test_stop_revalidates_feedback_and_inventory_after_decision_clocks(monkeypatch, change):
    node, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port.begin_stop(dict(epoch='stop-1', generation=5, request_wall_s=10.,
                         request_sim_s=1., fault_wall_s=10., stop_latency_s=.07))
    for index in range(1, 4):
        wall[0], sim[0] = 10.+index*.01, 1.+index*.01
        port._feedback(sample(sim[0]))
        assert port.stopped() is (index == 3)
    original_clock, injected = node.get_clock, [False]
    def clock_after_copy():
        if not injected[0]:
            injected[0] = True
            if change == 'moving_feedback':
                wall[0], sim[0] = 10.031, 1.031
                port._feedback(sample(1.031, .01))
            else:
                port._goals['pending'] = dict(accepted=None)
        return original_clock()
    node.get_clock = clock_after_copy
    assert port.stopped() is False
    assert port.stop_predicate_observations[-1]['error'] == 'HEAD_STOP_SNAPSHOT_CHANGED'


def test_timely_stop_confirmation_and_current_hold_are_separate(monkeypatch):
    _, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port.begin_stop(dict(epoch='stop-1', generation=5, request_wall_s=10.,
                         request_sim_s=1., fault_wall_s=10., stop_latency_s=.07))
    for index in range(1, 4):
        wall[0], sim[0] = 10.+index*.01, 1.+index*.01
        port._feedback(sample(sim[0]))
    assert port.stopped() is True
    for index in range(4, 11):
        wall[0], sim[0] = 10.+index*.01, 1.+index*.01
        port._feedback(sample(sim[0]))
        assert port.stopped() is True
    proof = port.stop_predicate_observations[-1]
    assert proof['confirmed_at']['wall_after_s'] == 10.03
    assert proof['confirmed_at']['sim_ns'] == 1_030_000_000
    wall[0], sim[0] = 10.11, 1.11
    port._feedback(sample(sim[0], .01))
    assert port.stopped() is False


def test_late_quiet_feedback_cannot_repair_missed_stop_deadline(monkeypatch):
    _, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port.begin_stop(dict(epoch='stop-1', generation=5, request_wall_s=10.,
                         request_sim_s=1., fault_wall_s=10., stop_latency_s=.07))
    for index in range(8, 11):
        wall[0], sim[0] = 10.+index*.01, 1.+index*.01
        port._feedback(sample(sim[0]))
        assert port.stopped() is False
    assert port.stop_predicate_observations[-1]['confirmed_at'] is None


def test_new_inventory_does_not_inherit_an_earlier_timely_stop(monkeypatch):
    _, _, port, wall, sim, _, _ = setup_ports(monkeypatch)
    port.begin_stop(dict(epoch='stop-1', generation=5, request_wall_s=10.,
                         request_sim_s=1., fault_wall_s=10., stop_latency_s=.07))
    for index in range(1, 4):
        wall[0], sim[0] = 10.+index*.01, 1.+index*.01
        port._feedback(sample(sim[0]))
        port.stopped()
    assert port.stopped() is True
    port._goals['new-unknown'] = dict(accepted=None)
    wall[0], sim[0] = 10.08, 1.08
    port._feedback(sample(sim[0]))
    assert port.stopped() is False
    port._goals['new-unknown'].update(accepted=True, result=SimpleNamespace(status=5))
    for index in range(9, 12):
        wall[0], sim[0] = 10.+index*.01, 1.+index*.01
        port._feedback(sample(sim[0]))
        assert port.stopped() is False


def test_stopped_bootstrap_keeps_originals_without_any_joint_policy_default(monkeypatch):
    _, _, port, _, _, _, subscriptions = setup_ports(monkeypatch,
        feedback_policy=None,head_bootstrap=True)
    port._feedback(sample())
    assert port._head_samples[-1]['source_ns']==1_000_000_000
    assert port._head_samples[-1]['callback_sim_ns']==1_000_000_000
    assert len(subscriptions)==1 and port.feedback_policy is None


def test_stopped_bootstrap_cannot_send_before_measured_policy_binding(monkeypatch):
    _, _, port, _, _, calls, _ = setup_ports(monkeypatch,
        feedback_policy=None,head_bootstrap=True)
    port._feedback(sample())
    goal=dict(joint_names=('neck_yaw_joint',),header_stamp_s=1.004,
        time_from_start_s=(0.,.05),positions=((.2,),(.3,)))
    with pytest.raises(PermissionError,match='HEAD_FEEDBACK_POLICY_REQUIRED'):
        port.send(goal)
    assert not [call for call in calls if call[0]=='send']


def test_stopped_bootstrap_freezes_policy_on_the_original_subscriber(monkeypatch):
    _, _, port, _, _, _, subscriptions = setup_ports(monkeypatch,
        feedback_policy=None,head_bootstrap=True)
    port._feedback(sample())
    port.bind_head_policy(policy())
    assert port.feedback_snapshot()['source_ns']==1_000_000_000
    assert len(subscriptions)==1
    with pytest.raises(PermissionError,match='HEAD_FEEDBACK_POLICY_BINDING_REFUSED'):
        port.bind_head_policy(dict(policy(),joint_max_receipt_age_s=.03))


def test_invalid_bootstrap_policy_is_an_irreversible_binding_failure(monkeypatch):
    _, _, port, _, _, calls, _ = setup_ports(monkeypatch,
        feedback_policy=None,head_bootstrap=True)
    with pytest.raises(ValueError):port.bind_head_policy({})
    with pytest.raises(PermissionError):port.bind_head_policy(policy())
    assert port.stopped() is False
    assert port.feedback_policy is None and not [call for call in calls if call[0]=='send']


@pytest.mark.parametrize('boundary',['snapshot','send'])
def test_failed_rebind_cannot_race_snapshot_or_dispatch(monkeypatch,boundary):
    node, _, port, _, _, calls, _ = setup_ports(monkeypatch,
        feedback_policy=None,head_bootstrap=True)
    port._feedback(sample());port.bind_head_policy(policy())
    def invalidate():
        with pytest.raises(ValueError):port.bind_head_policy({})
    if boundary=='snapshot':
        original=node.get_clock
        def clock():invalidate();return original()
        node.get_clock=clock
        with pytest.raises(PermissionError):port.feedback_snapshot()
    else:
        from so101_demo.adapters.act import ros_execution
        original=ros_execution.trajectory_message
        def wire(goal):invalidate();return original(goal)
        monkeypatch.setattr(ros_execution,'trajectory_message',wire)
        goal=dict(joint_names=('neck_yaw_joint',),header_stamp_s=1.004,
            time_from_start_s=(0.,.05),positions=((.2,),(.3,)))
        with pytest.raises(PermissionError):port.send(goal)
    assert not [call for call in calls if call[0]=='send']


def test_bootstrap_policy_has_no_public_rebinding_bypass(monkeypatch):
    _, _, port, _, _, _, _ = setup_ports(monkeypatch,
        feedback_policy=None,head_bootstrap=True)
    with pytest.raises(AttributeError):port.feedback_policy=policy()


def test_stopped_bootstrap_refuses_a_prebound_policy_constructor(monkeypatch):
    with pytest.raises(ValueError,match='HEAD_BOOTSTRAP_CONFIG_INVALID'):
        setup_ports(monkeypatch,head_bootstrap=True)


def test_failed_rebind_keeps_original_policy_for_actual_safe_stop(monkeypatch):
    _, _, port, wall, sim, calls, _ = setup_ports(monkeypatch,
        feedback_policy=None,head_bootstrap=True)
    port._feedback(sample());port.bind_head_policy(policy())
    with pytest.raises(ValueError):port.bind_head_policy({})
    assert port.original_feedback_snapshot()['sample']['source_ns']==1_000_000_000
    with pytest.raises(PermissionError):port.feedback_snapshot()
    port.begin_stop(dict(epoch='stop-1',generation=5,request_wall_s=10.,
        request_sim_s=1.,fault_wall_s=10.,stop_latency_s=.07))
    for index in range(1,4):
        wall[0],sim[0]=10.+index*.01,1.+index*.01
        port._feedback(sample(sim[0]))
        assert port.stopped() is (index==3)
    assert not [call for call in calls if call[0]=='send']
