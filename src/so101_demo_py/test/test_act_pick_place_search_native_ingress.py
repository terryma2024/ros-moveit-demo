"""A stopped SEARCH source needs three native controller ingress cursors."""

from types import SimpleNamespace

import pytest

from test_act_pick_place_search_owner import _case_with_events, _verify

from so101_demo.adapters.act.pick_place_search_native_ingress import (
    verify_search_native_controller_ingress,
)


def _case():
    case = _case_with_events()
    sources, observed, physical, references, broker, ticket, _ = case
    owner = _verify(case)
    snapshots = {
        kind: {
            "role": kind, "owner_generation": ticket[0],
            "ingress_sequence": index + 1,
            "last_ingress_monotonic_ns": 9_985_000_000,
            "observed_monotonic_ns": 10_105_000_000,
            "received_monotonic_ns": 10_106_000_000,
            "command_authority": False,
        }
        for index, kind in enumerate(("arm", "gripper", "neck"))
    }
    called = []

    def query(query_ticket, kind):
        assert query_ticket == ticket
        called.append(kind)
        return snapshots[kind]

    broker.reservation_port = SimpleNamespace(snapshot_generation=query)
    return sources, observed, physical, references, owner, broker, ticket, snapshots, called


def _verify_native(case):
    sources, observed, physical, references, owner, broker, ticket, _, _ = case
    return verify_search_native_controller_ingress(
        broker, ticket, sources, observed, physical, references, owner,
        stopped_wall_s=9.99,
    )


def test_three_native_cursors_bind_selected_search_and_remain_neutral():
    case = _case()
    proof = _verify_native(case)
    assert case[-1] == ["arm", "gripper", "neck"]
    assert proof["owner_generation"] == case[6][0]
    assert proof["selected_source_sha256"] == case[4]["selected_source_sha256"]
    assert proof["control_event_window_sha256"] == case[4]["control_event_window_sha256"]
    assert proof["ingress_sequence_by_controller"] == {"arm": 1, "gripper": 2, "neck": 3}
    assert len(proof["native_ingress_window_sha256"]) == 64
    assert proof["commit_window_ingress_recheck_required"] is True
    assert proof["command_authority"] is False
    assert proof["eligible_for_collection"] is False
    assert _verify_native(_case())["native_ingress_window_sha256"] == proof["native_ingress_window_sha256"]


@pytest.mark.parametrize("change", [
    "post_stop_callback", "snapshot_before_selected_receipt", "wrong_role",
    "wrong_generation", "changed_owner_proof", "stale_reply", "future_reply",
    "missing_field", "clock_order", "query_failure", "changed_scope",
    "unarmed_generation", "driver_moving",
])
def test_native_ingress_join_refuses_broken_fence(change):
    case = list(_case())
    sources, _, _, _, owner, broker, ticket, snapshots, _ = case
    if change == "post_stop_callback":
        snapshots["gripper"]["last_ingress_monotonic_ns"] = 9_995_000_000
    elif change == "snapshot_before_selected_receipt":
        snapshots["neck"]["observed_monotonic_ns"] = 10_050_000_000
    elif change == "wrong_role":
        snapshots["arm"]["role"] = "neck"
    elif change == "wrong_generation":
        snapshots["arm"]["owner_generation"] += 1
    elif change == "changed_owner_proof":
        case[4] = {**owner, "selected_source_sha256": "other"}
    elif change == "stale_reply":
        snapshots["arm"]["received_monotonic_ns"] = 9_800_000_000
    elif change == "future_reply":
        snapshots["arm"]["observed_monotonic_ns"] = 10_200_000_000
    elif change == "missing_field":
        del snapshots["gripper"]["ingress_sequence"]
    elif change == "clock_order":
        snapshots["neck"]["last_ingress_monotonic_ns"] = 10_110_000_000
    elif change == "query_failure":
        broker.reservation_port.snapshot_generation = lambda *_: (_ for _ in ()).throw(
            RuntimeError("SOCKET_TIMEOUT"))
    elif change == "changed_scope":
        query = broker.reservation_port.snapshot_generation

        def change_after_query(query_ticket, kind):
            result = query(query_ticket, kind)
            if kind == "neck":
                sources.phase = "APPROACH"
            return result

        broker.reservation_port.snapshot_generation = change_after_query
    elif change == "unarmed_generation":
        broker._armed_generation = ticket[0] + 1
    elif change == "driver_moving":
        broker.driver.stopped = lambda: False
    with pytest.raises(ValueError, match="SEARCH_NATIVE_CONTROLLER_INGRESS_INVALID"):
        _verify_native(case)
