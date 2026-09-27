"""A stopped SEARCH interval needs continuous local ownership and no goal."""

from types import SimpleNamespace

import pytest

from so101_demo.act.control_event_timeline import ControlEventTimeline
from so101_demo.act.ownership import Ownership
from test_act_pick_place_search_reference import _case, _verify_references
from test_act_task8_search_boundary import _boundary, _request


def _case_with_events(*, capacity=4096, late_bind=False, baseline=True):
    sources, observed, physical, _ = _case()
    references = _verify_references(sources, observed, physical)
    tick = [9_000_000_000]
    timeline = ControlEventTimeline(capacity=capacity, monotonic_ns=lambda: tick[0])
    ownership = Ownership()
    if not late_bind:
        ownership.bind_control_events(timeline)
    token = ownership.acquire("act", sources.session_id,
                              observed.search_result["attempt_id"])
    ticket = ownership.ticket(token, "act", sources.session_id,
                              observed.search_result["attempt_id"])
    if late_bind:
        ownership.bind_control_events(timeline)
    if baseline:
        tick[0] = 9_980_000_000
        timeline.record("stop_baseline_confirmed")
    tick[0] = 10_050_000_000
    timeline.record("action_status", detail="arm|")
    broker = SimpleNamespace(
        control_events=timeline, ownership=ownership,
        reservation_port=object(), _armed_generation=ticket[0],
        driver=SimpleNamespace(stopped=lambda: True),
    )
    return sources, observed, physical, references, broker, ticket, tick


def _verify(case):
    from so101_demo.adapters.act.pick_place_search_owner import (
        verify_search_owner_goal_interval,
    )

    sources, observed, physical, references, broker, ticket, _ = case
    return verify_search_owner_goal_interval(
        broker, ticket, sources, observed, physical, references,
        stopped_wall_s=9.99,
    )


def test_selected_search_has_local_owner_and_no_goal_interval():
    proof = _verify(_case_with_events())
    assert proof["owner_generation"] == 1
    assert proof["selected_source_sha256"]
    assert len(proof["control_event_window_sha256"]) == 64
    assert proof["controller_native_ingress_proof_required"] is True
    assert proof["command_authority"] is False
    assert proof["eligible_for_collection"] is False


def test_empty_moveit_action_status_does_not_close_search():
    case = _case_with_events()
    timeline, tick = case[4].control_events, case[6]
    tick[0] = 10_060_000_000
    timeline.record("action_status", detail="execute_trajectory|")
    assert _verify(case)["command_authority"] is False


@pytest.mark.parametrize("change", [
    "gap", "late_bind", "missing_baseline", "baseline_after_stop",
    "goal_send", "goal_submit", "unknown_goal", "nonempty_status",
    "owner_revoked", "wrong_generation", "unarmed_native_gate",
    "not_stopped", "changed_reference_proof", "clock_regression",
    "future_event", "stale_source",
])
def test_selected_search_refuses_broken_local_owner_goal_fence(change):
    case = _case_with_events(capacity=2 if change == "gap" else 4096,
                             late_bind=change == "late_bind",
                             baseline=change not in ("missing_baseline", "baseline_after_stop"))
    sources, observed, physical, references, broker, ticket, tick = case
    if change == "baseline_after_stop":
        tick[0] = 10_060_000_000
        broker.control_events.record("stop_baseline_confirmed")
    elif change == "goal_send":
        tick[0] = 10_060_000_000
        broker.control_events.record("goal_send_enqueued", goal_id="g")
    elif change == "goal_submit":
        tick[0] = 10_060_000_000
        broker.control_events.record("submit_begin", generation=ticket[0])
    elif change == "unknown_goal":
        tick[0] = 10_060_000_000
        broker.control_events.record("unknown_goal", ros_goal_id="r")
    elif change == "nonempty_status":
        tick[0] = 10_060_000_000
        broker.control_events.record("action_status", detail="arm|r:2")
    elif change == "owner_revoked":
        broker.ownership.revoke("HAZARD")
    elif change == "wrong_generation":
        broker._armed_generation += 1
    elif change == "unarmed_native_gate":
        broker.reservation_port = None
    elif change == "not_stopped":
        broker.driver.stopped = lambda: False
    elif change == "changed_reference_proof":
        references = {**references, "selected_source_sha256": "other"}
        case = (sources, observed, physical, references, broker, ticket, tick)
    elif change == "clock_regression":
        tick[0] = 8_000_000_000
        broker.control_events.record("action_status", detail="arm|")
    elif change == "future_event":
        tick[0] = 10_200_000_000
        broker.control_events.record("action_status", detail="arm|")
    elif change == "stale_source":
        sources.readback.monotonic = lambda: 10.4
    with pytest.raises(ValueError, match="SEARCH_OWNER_GOAL_INTERVAL_INVALID"):
        _verify(case)


def test_production_search_boundary_supplies_real_local_owner_verifier():
    case = _case_with_events()
    sources, observed, physical, references, broker, ticket, _ = case
    boundary, _, reset, _, _, _ = _boundary()
    reset.sources = sources
    reset.broker = broker
    reset.act_context = {"lease_token": ticket[1]}
    verified = []

    def segment_factory(_sources_arg, _adapter, _scene, _geometry, **kwargs):
        verified.append(kwargs["owner_verifier"](
            observed, physical, references, 9.99))
        return SimpleNamespace(run=lambda _request_arg, *, reset_epoch: observed)

    boundary.segment_factory = segment_factory
    request = dict(_request(), session_id=sources.session_id,
                   attempt_id=observed.search_result["attempt_id"])
    boundary.begin(request)
    assert boundary.search(request) is observed
    assert len(verified) == 1
    assert verified[0]["owner_generation"] == ticket[0]
    assert verified[0]["command_authority"] is False
