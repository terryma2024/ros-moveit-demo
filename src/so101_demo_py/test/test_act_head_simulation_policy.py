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
