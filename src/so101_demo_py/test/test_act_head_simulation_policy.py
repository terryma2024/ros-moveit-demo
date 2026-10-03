"""Explicit bounded-simulation policy refuses ambiguous or unbounded consumers."""

from copy import deepcopy
import importlib

import pytest


def policy_type():
    # Import in the test body: missing feature is executed RED, not collection RED.
    return importlib.import_module('so101_demo.act.head_simulation_policy').HeadSimulationPolicy


def document():
    return dict(schema_version=1, mode='mujoco_bounded_stop_search',
        heartbeat_rpc_timeout_s=.25, supervision_stale_s=.5, watchdog_period_s=.02,
        fault_reaction_limit_s=.25, native_close_timeout_s=.05,
        stop_confirmation_timeout_s=1., perception_max_age_s=.15,
        perception_job_timeout_s=1., camera_loss_timeout_s=.5,
        feedback_receipt_timeout_s=.25, joint_source_age_s=.05,
        camera_source_age_s=.2, search_timeout_s=30.,
        max_reobservations_per_stop=3, max_reobservations_total=12)


def test_explicit_policy_maps_original_consumers_without_mixing_clocks():
    parsed = policy_type().parse(document())
    assert parsed.feedback_values() == dict(joint_max_receipt_age_s=.25,
        joint_max_source_age_s=.05, camera_interarrival_deadline_s=.5,
        camera_max_source_age_s=.2, clock_interarrival_deadline_s=.25,
        watchdog_period_s=.02, watchdog_reaction_limit_s=.25,
        revoker_connection_deadline_s=.05)
    # Mutating a readback cannot silently change the bound used by another actor.
    readback = parsed.readback()
    readback['supervision_stale_s'] = 10.
    assert parsed.readback()['supervision_stale_s'] == .5
    parsed.validate_search_values(dict(max_age_s=.15, search_timeout_s=30., stop_latency_s=1.))


@pytest.mark.parametrize('value', [True, False, 0, -1, float('nan'), float('inf'), '0.25', None])
def test_rpc_budget_cannot_be_boolean_nonfinite_or_unbounded(value):
    cls = policy_type()
    doc = document(); doc['heartbeat_rpc_timeout_s'] = value
    with pytest.raises(ValueError): cls.parse(doc)


@pytest.mark.parametrize('change', [
    dict(schema_version=True), dict(schema_version=2), dict(mode='hardware'),
    dict(mode='legacy'), dict(unknown=1),
])
def test_policy_does_not_admit_unknown_mode_version_or_field(change):
    cls = policy_type()
    with pytest.raises(ValueError): cls.parse(dict(document(), **change))


def test_missing_field_cannot_inherit_default_motion_policy():
    cls = policy_type(); doc = document(); del doc['supervision_stale_s']
    with pytest.raises(ValueError): cls.parse(doc)
    with pytest.raises(ValueError): cls.parse(None)


@pytest.mark.parametrize('change', [
    dict(heartbeat_rpc_timeout_s=.5), dict(watchdog_period_s=.25),
    dict(fault_reaction_limit_s=.5, native_close_timeout_s=.25, stop_confirmation_timeout_s=.75),
    dict(camera_loss_timeout_s=.6), dict(feedback_receipt_timeout_s=.6),
    dict(perception_max_age_s=.15, perception_job_timeout_s=.14),
    dict(search_timeout_s=1.), dict(max_reobservations_per_stop=13),
])
def test_related_budgets_cannot_leave_no_supervision_or_stop_window(change):
    cls = policy_type()
    with pytest.raises(ValueError): cls.parse(dict(document(), **change))


@pytest.mark.parametrize('name,value', [
    ('heartbeat_rpc_timeout_s', 1.01), ('supervision_stale_s', 2.01),
    ('watchdog_period_s', .101), ('fault_reaction_limit_s', .501),
    ('native_close_timeout_s', .251), ('stop_confirmation_timeout_s', 3.01),
    ('perception_max_age_s', .151), ('perception_job_timeout_s', 3.01),
    ('camera_loss_timeout_s', 2.01), ('feedback_receipt_timeout_s', 1.01),
    ('joint_source_age_s', .101), ('camera_source_age_s', .301),
    ('search_timeout_s', 120.01), ('max_reobservations_per_stop', 11),
    ('max_reobservations_total', 41), ('max_reobservations_per_stop', True),
    ('max_reobservations_total', 12.0),
])
def test_configured_budget_cannot_exceed_declared_simulation_limit(name, value):
    cls = policy_type()
    with pytest.raises(ValueError): cls.parse(dict(document(), **{name:value}))


@pytest.mark.parametrize('name', ['max_age_s', 'search_timeout_s', 'stop_latency_s'])
def test_bundle_cannot_bind_two_different_effective_values(name):
    parsed = policy_type().parse(document())
    values = dict(max_age_s=.15, search_timeout_s=30., stop_latency_s=1.)
    values[name] = values[name] + .001
    with pytest.raises(ValueError): parsed.validate_search_values(values)
    values[name] = True
    with pytest.raises(ValueError): parsed.validate_search_values(values)


def test_explicit_custom_budget_survives_readback_and_cannot_mutate_after_parse():
    cls = policy_type(); doc = document()
    doc.update(heartbeat_rpc_timeout_s=.3, supervision_stale_s=.75,
        stop_confirmation_timeout_s=1.5, search_timeout_s=40.)
    expected = deepcopy(doc); parsed = cls.parse(doc)
    doc['search_timeout_s'] = 120.
    assert parsed.readback() == expected
    parsed.validate_search_values(dict(max_age_s=.15, search_timeout_s=40., stop_latency_s=1.5))


def test_simulation_feedback_requires_explicit_matching_policy_binding():
    from so101_demo.act.head_feedback import FeedbackPolicy
    sim = policy_type().parse(document())
    values = sim.feedback_values()
    with pytest.raises(ValueError): FeedbackPolicy.parse(values)
    bound = FeedbackPolicy.parse(values, simulation_policy=sim)
    # Source and wall clocks remain independent after accepting the new schedule.
    with pytest.raises(ValueError, match='SOURCE_STALE'):
        bound.check_joint(dict(valid=True, wall_s=10., source_ns=1_000_000_000),
            dict(wall_after_s=10.01, sim_ns=1_100_000_000))
    with pytest.raises(ValueError, match='RECEIPT_STALE'):
        bound.check_joint(dict(valid=True, wall_s=10., source_ns=1_000_000_000),
            dict(wall_after_s=10.3, sim_ns=1_010_000_000))
    assert bound.check_joint(dict(valid=True, wall_s=10., source_ns=1_000_000_000),
        dict(wall_after_s=10.02, sim_ns=1_010_000_000)) == dict(receipt_age_s=.02, source_age_s=.01)


def test_simulation_feedback_cannot_silently_rebind_an_existing_consumer():
    from so101_demo.act.head_feedback import FeedbackPolicy
    sim = policy_type().parse(document())
    bound = FeedbackPolicy.parse(sim.feedback_values(), simulation_policy=sim)
    changed = document(); changed['feedback_receipt_timeout_s'] = .3
    with pytest.raises(ValueError): FeedbackPolicy.parse(bound, simulation_policy=changed)
    damaged = sim.feedback_values(); damaged['joint_max_source_age_s'] = .08
    with pytest.raises(ValueError): FeedbackPolicy.parse(damaged, simulation_policy=sim)


def observation_request():
    from so101_demo.act.head_monitor import digest
    return dict(schema_version=1,epoch='attempt',generation=5,session_id='session',
        policy_sha256='a'*64,simulation_policy_sha256=digest(document()),motion_epoch=0,
        observation_sequence=1,settled_source_floor_ns=1_000_000_000,
        settled_wall_s=10.,requested_wall_s=10.01,search_deadline_ns=40_000_000_000)


def request_validation(request,now=10.02):
    module=importlib.import_module('so101_demo.act.head_simulation_policy')
    return module.validate_stopped_observation_request(request,policy=policy_type().parse(document()),
        expected_scope=dict(epoch='attempt',generation=5,session_id='session',policy_sha256='a'*64),
        now_wall_s=now)


def test_stopped_request_keeps_original_settlement_acquisition_and_whole_search_deadline():
    request=observation_request();bound=request_validation(request)
    request['requested_wall_s']=99.
    assert bound['requested_wall_s']==10.01 and bound['settled_source_floor_ns']==1_000_000_000
    assert bound['search_deadline_ns']==40_000_000_000 and bound['motion_epoch']==0


@pytest.mark.parametrize('field,value',[
    ('schema_version',True),('schema_version',2),('epoch','other'),('generation',True),
    ('generation',6),('session_id','other'),('policy_sha256','b'*64),
    ('simulation_policy_sha256','b'*64),('motion_epoch',True),('motion_epoch',-1),
    ('observation_sequence',0),('observation_sequence',True),('settled_source_floor_ns',0),
    ('settled_source_floor_ns',True),('settled_wall_s',float('nan')),('settled_wall_s',10.02),
    ('requested_wall_s',10.03),('requested_wall_s',True),('search_deadline_ns',10_010_000_000),
    ('search_deadline_ns',40_020_000_001),('extra',1),
])
def test_stopped_request_refuses_changed_scope_clock_or_unbounded_future(field,value):
    request=observation_request();request[field]=value
    with pytest.raises(ValueError):request_validation(request)


def test_stopped_request_expiry_cannot_be_renewed_by_a_later_validation():
    with pytest.raises(ValueError):request_validation(observation_request(),40.)


def budget():
    module=importlib.import_module('so101_demo.act.head_simulation_policy')
    return module.BoundedObservationBudget(policy_type().parse(document()),started_wall_s=10.)


def test_reobservation_per_stop_and_total_caps_preserve_one_original_search_deadline():
    observed=budget()
    assert observed.reobserve(0,'MISS',10.1)
    assert observed.reobserve(0,'EXPIRED',10.2)
    assert observed.reobserve(0,'SHORT_DROP',10.3)
    assert observed.reobserve(0,'MISS',10.4) is False
    for stop in (1,2,3):
        for _ in range(3):assert observed.reobserve(stop,'MISS',11.+stop)
    assert observed.reobserve(4,'MISS',20.) is False
    assert observed.readback()['reobservations_total']==12
    assert observed.readback()['per_stop']=={0:3,1:3,2:3,3:3}
    assert observed.readback()['search_deadline_ns']==40_000_000_000


def test_reobservation_expiry_refuses_without_incrementing_or_restarting_search():
    observed=budget();assert observed.reobserve(0,'MISS',39.999999999)
    assert observed.reobserve(1,'MISS',40.) is False
    assert observed.readback()['reobservations_total']==1
    assert observed.readback()['search_deadline_ns']==40_000_000_000


@pytest.mark.parametrize('stop,reason,wall',[(True,'MISS',10.1),(-1,'MISS',10.1),
    (0,'PEER_DEATH',10.1),(0,'MISS',float('nan')),(0,'MISS',9.)])
def test_reobservation_never_recovers_identity_fault_or_backward_clock(stop,reason,wall):
    observed=budget()
    with pytest.raises(ValueError):observed.reobserve(stop,reason,wall)
    assert observed.readback()['reobservations_total']==0
