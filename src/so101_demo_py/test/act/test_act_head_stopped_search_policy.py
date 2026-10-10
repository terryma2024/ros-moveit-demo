"""Explicit simulation controller contracts; pure geometry, no runtime proof."""
from copy import deepcopy
import pytest

from test_act_search import config,evidence
from so101_demo.act.search import HeadSearchController
from so101_demo.act.head_simulation_policy import HeadSimulationPolicy


def bounded_config(**changes):
    values = dict(max_age_s=1., required_search_domain_rad=[-.2,.2],
                  lock_valid_neck_rad=[-.3,.3])
    values.update(changes)
    return config(**values)


def simulation():return HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document())


def test_simulation_controller_only_reports_clean_negative_after_all_bounded_stops():
    search=HeadSearchController(bounded_config(),simulation_policy=simulation())
    yaw=0.;targets=[]
    for wall in (1.,1.1,1.2):
        result=search.tick(*evidence(wall,q=yaw),wall)
        if 'found' in result:break
        yaw=result['neck_target_rad'];targets.append(yaw)
    assert targets==[.2,-.2]
    assert result['found'] is False and result['status']=='TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL'
    assert search.started_wall_s==1. and search.plan_index==2 and search.lock_count==0


@pytest.mark.parametrize('damage',['no_domain','no_safe','old_age','old_timeout','alias_only','unsafe_anchor','boolean_bound'])
def test_simulation_controller_refuses_unbounded_or_different_effective_config_before_ticks(damage):
    values=bounded_config()
    if damage=='no_domain':values.pop('required_search_domain_rad')
    elif damage=='no_safe':values.pop('lock_valid_neck_rad')
    elif damage=='old_age':values['max_age_s']=.014736005
    elif damage=='old_timeout':values['search_timeout_s']=.70892135
    elif damage=='alias_only':values['required_domain_rad']=values.pop('required_search_domain_rad')
    elif damage=='unsafe_anchor':values['search_start_rad']=.4
    else:values['lock_valid_neck_rad']=[False,.3]
    with pytest.raises(ValueError):HeadSearchController(values,simulation_policy=simulation())


def test_simulation_controller_never_qualifies_an_incomplete_degenerate_stop_plan():
    search=HeadSearchController(config(max_age_s=1., required_search_domain_rad=[0.,0.],lock_valid_neck_rad=[0.,0.]),
        simulation_policy=simulation())
    result=search.tick(*evidence(1.),1.)
    assert result['status']=='SEARCH_COVERAGE_INCOMPLETE' and result['found'] is False


def test_simulation_controller_reset_keeps_frozen_mode_and_refuses_legacy_revolution():
    search=HeadSearchController(bounded_config(),simulation_policy=simulation())
    with pytest.raises(ValueError):search.reset(config())


def test_simulation_controller_rejects_foreign_feedback_policy_even_when_values_are_fresh():
    from test_act_head_feedback_freshness import policy
    search=HeadSearchController(bounded_config(),simulation_policy=simulation())
    frame,joint=evidence(1.)
    context=dict(session_id='s',attempt_id='a',policy=policy(),
        sample=dict(valid=True,source_ns=1_000_000_000,wall_s=1.,positions=[0.],velocities=[0.]),
        decision=dict(wall_before_s=1.,wall_after_s=1.,sim_ns=1_000_000_000,sim_s=1.))
    with pytest.raises(ValueError):search.tick(frame,joint,1.,joint_context=context)
    assert search.lock_count==0 and search.plan_index==0


def test_simulation_controller_accepts_exact_typed_policy_without_resetting_original_search_clock():
    from so101_demo.act.head_feedback import FeedbackPolicy
    bound=simulation();search=HeadSearchController(bounded_config(),simulation_policy=bound)
    assert search.advance_deadline(1.) is None
    frame,joint=evidence(1.1)
    context=dict(session_id='s',attempt_id='a',policy=FeedbackPolicy.parse(bound.feedback_values(),simulation_policy=bound),
        sample=dict(valid=True,source_ns=1_100_000_000,wall_s=1.1,positions=[0.],velocities=[0.]),
        decision=dict(wall_before_s=1.1,wall_after_s=1.1,sim_ns=1_100_000_000,sim_s=1.1))
    assert search.tick(frame,joint,1.1,joint_context=context)['neck_target_rad']==.2
    result=search.advance_deadline(31.)
    assert result['status']=='SEARCH_TIMEOUT' and search.started_wall_s==1.
