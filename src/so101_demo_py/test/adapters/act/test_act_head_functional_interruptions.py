"""Real signal delivery and original-message relay boundaries."""
import os
import signal
from types import SimpleNamespace

import pytest


def test_camera_relay_cuts_only_after_actual_goal_uuid_and_preserves_originals():
    from so101_demo.adapters.act.head_campaign_camera_relay import HeadCampaignCameraRelay
    receipts, delivered = [], []
    relay = HeadCampaignCameraRelay(emit=lambda kind, **record: receipts.append((kind, record)))
    original = object()
    relay.deliver(original, delivered.append)
    assert delivered == [original]
    with pytest.raises(ValueError):
        relay.cut_after_sdk_return({'status': 'SUBMITTED', 'goal_uuid': 'not-an-sdk-uuid'})
    assert relay.open
    relay.cut_after_sdk_return({'status': 'SUBMITTED', 'goal_uuid': '12345678-1234-4234-8234-123456789abc'})
    relay.deliver(object(), delivered.append)
    assert delivered == [original]
    assert receipts[0][0] == 'CAMPAIGN_CAMERA_DELIVERY_CUT'
    assert receipts[0][1]['goal_uuid'] == '12345678-1234-4234-8234-123456789abc'


@pytest.mark.parametrize('terminal', ['TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL', 'TARGET_AMBIGUOUS'])
def test_normal_negative_search_uses_stop_without_latching_a_fault(terminal):
    from so101_demo.cli.head_execution_runner import _drive
    calls = []
    runtime = SimpleNamespace(start=lambda: None, arm=lambda **kwargs: None, faulted=False,
        stop_requested=False, stop=lambda origin, evidence: calls.append(('stop', origin)),
        fault=lambda reason: calls.append(('fault', reason)))
    search = SimpleNamespace(tick=lambda: {'status': terminal})
    owner = SimpleNamespace(activate_live=lambda: None)
    capture = SimpleNamespace(bind_live_sink=lambda callback: None)
    assert _drive(SimpleNamespace(event_log_enabled=False), search, runtime, owner,
                  capture, SimpleNamespace(observe=lambda: None), 3) == 1
    assert calls == [('stop', 'not_found')]


def test_sigterm_uses_owned_stop_and_restores_original_handler():
    from so101_demo.cli.head_execution_runner import _drive
    events, calls = [], []
    runtime = SimpleNamespace(start=lambda: None, arm=lambda **kwargs: None, faulted=False,
        stop=lambda origin, evidence: calls.append((origin, evidence)),
        fault=lambda reason: calls.append(('fault', reason)))
    search = SimpleNamespace(tick=lambda: pytest.fail('search must not continue after SIGTERM'))
    original = signal.getsignal(signal.SIGTERM)
    composition = SimpleNamespace(event_log_enabled=True,
        emit=lambda kind, record: events.append((kind, record)))
    def send_after_arm():
        assert signal.getsignal(signal.SIGTERM) != original
        os.kill(os.getpid(), signal.SIGTERM)
    rc = _drive(composition, search, runtime, SimpleNamespace(activate_live=lambda: None),
        SimpleNamespace(bind_live_sink=lambda callback: None),
        SimpleNamespace(observe=lambda: None), 3,
        after_arm=send_after_arm)
    assert rc == 1 and calls[0][0] == 'sigterm'
    assert ('EXECUTION_OPERATOR_TERMINAL', {'status': 'INTERRUPTED', 'signal': signal.SIGTERM}) in events
    assert signal.getsignal(signal.SIGTERM) == original


@pytest.mark.parametrize('terminal', ['TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL', 'TARGET_AMBIGUOUS'])
def test_owned_search_preserves_normal_negative_without_fault(terminal):
    from test_act_head_owned_search import driver
    current = driver()
    original = dict(status=terminal, found=False)
    assert current.search._terminal(original) == original
    assert current.faults == []


def test_owned_bounded_controller_receives_frozen_simulation_policy():
    from so101_demo.adapters.act.head_owned_search import OwnedHeadSearch
    from test_act_head_stopped_search_policy import bounded_config,simulation
    from test_act_search import evidence
    bound=simulation()
    search=OwnedHeadSearch(config=bounded_config(),policy=bound,
        primary=SimpleNamespace(),port=SimpleNamespace(),owner=SimpleNamespace(),
        settlement=lambda *args:None,stop_velocity_rad_s=.01,emit=None)
    yaw=0.;targets=[]
    for wall in (1.,1.1,1.2):
        result=search.controller.tick(*evidence(wall,q=yaw),wall)
        if 'found' in result:
            break
        yaw=result['neck_target_rad'];targets.append(yaw)
    assert targets==[.2,-.2]
    assert result['status']=='TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL'
    assert search.controller.plan.coverage_complete is True
    assert search.controller._simulation_policy.readback()==bound.readback()
