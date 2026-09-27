"""An expert approach cannot send its first goal after unseen native ingress."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from so101_demo.adapters.act.visible_approach_commit_ingress import (
    verify_visible_approach_commit_ingress,
)
from so101_demo.adapters.act.pick_place_search_native_ingress import native_ingress_digest
from so101_demo.adapters.act.visible_approach_expert_route import _digest

from test_act_visible_approach_expert_route import (
    TICKET, proven_prefix, proved_search, route,
)


def _case(route, proven_prefix):
    original_prepared, proof, snapshot, _ = proven_prefix
    prepared = deepcopy(original_prepared)
    observed, source = proved_search(route)
    assert source == prepared["selected_source"]
    native = observed.native_controller_ingress_proof
    native["native_ingress_window_sha256"] = native_ingress_digest(
        native["native_snapshots"])
    prepared["native_ingress_window_sha256"] = native["native_ingress_window_sha256"]
    prepared["preparation_sha256"] = _digest({
        key: value for key, value in prepared.items() if key != "preparation_sha256"})
    qualification = route.qualify(prepared, proof, current_snapshot=snapshot)
    queried = []

    def query(ticket, role):
        assert ticket == TICKET
        queried.append(role)
        original = native["native_snapshots"][role]
        return {**original, "observed_monotonic_ns": 10_120_000_000,
                "received_monotonic_ns": 10_121_000_000}

    broker = SimpleNamespace(
        ownership=SimpleNamespace(require_ticket=lambda ticket:
                                  None if ticket == TICKET else (_ for _ in ()).throw(
                                      PermissionError("WRONG_TICKET"))),
        reservation_port=SimpleNamespace(snapshot_generation=query),
        _armed_generation=TICKET[0],
        driver=SimpleNamespace(stopped=lambda: True),
    )
    return prepared, proof, native, qualification, broker, queried


def _verify(case):
    prepared, proof, native, qualification, broker, _ = case
    return verify_visible_approach_commit_ingress(
        broker, TICKET, prepared, qualification, proof, native,
        monotonic=lambda: 10.122, max_age_s=.2,
    )


def test_first_commit_rechecks_three_native_cursors_without_command(route, proven_prefix):
    case = _case(route, proven_prefix)
    result = _verify(case)
    assert case[-1] == ["arm", "gripper", "neck"]
    assert result["selected_source_sha256"] == case[0]["selected_source"]["observation_sha256"]
    assert result["owner_generation"] == TICKET[0]
    assert result["ingress_sequence_by_controller"] == {"arm": 1, "gripper": 2, "neck": 3}
    assert result["command_authority"] is False
    assert result["eligible_for_collection"] is False
    assert len(result["commit_ingress_window_sha256"]) == 64


@pytest.mark.parametrize("change", [
    "sequence", "last_callback", "post_stop", "wrong_generation", "wrong_role",
    "query_before_baseline", "stale_query", "missing_query_field", "query_failure",
    "changed_source", "changed_preparation", "changed_qualification",
    "wrong_proof", "unarmed", "moving", "port_replaced", "ticket_changed",
    "baseline_tamper",
])
def test_first_commit_refuses_changed_or_stale_ingress(route, proven_prefix, change):
    case = list(_case(route, proven_prefix))
    prepared, proof, native, qualification, broker, _ = case
    original = broker.reservation_port.snapshot_generation

    def change_query(ticket, role):
        result = original(ticket, role)
        if role == "gripper":
            result = dict(result)
            if change == "sequence":
                result["ingress_sequence"] += 1
            elif change == "last_callback":
                result["last_ingress_monotonic_ns"] += 1
            elif change == "post_stop":
                result["last_ingress_monotonic_ns"] = 10_115_000_000
            elif change == "wrong_generation":
                result["owner_generation"] += 1
            elif change == "wrong_role":
                result["role"] = "arm"
            elif change == "query_before_baseline":
                result["observed_monotonic_ns"] = 10_005_000_000
            elif change == "stale_query":
                result["received_monotonic_ns"] = 9_000_000_000
            elif change == "missing_query_field":
                del result["ingress_sequence"]
            elif change == "port_replaced":
                broker.reservation_port = SimpleNamespace(snapshot_generation=original)
            elif change == "ticket_changed":
                broker.ownership.require_ticket = lambda _: (_ for _ in ()).throw(
                    PermissionError("OWNER_CHANGED"))
        return result

    broker.reservation_port.snapshot_generation = change_query
    if change == "query_failure":
        broker.reservation_port.snapshot_generation = lambda *_: (_ for _ in ()).throw(
            TimeoutError("SOCKET_TIMEOUT"))
    elif change == "changed_source":
        case[0] = {**prepared, "selected_source": {
            **prepared["selected_source"], "physics_step": 999}}
    elif change == "changed_preparation":
        case[0] = {**prepared, "native_ingress_window_sha256": "0" * 64}
    elif change == "changed_qualification":
        case[3] = {**qualification, "path_proof_sha256": "0" * 64}
    elif change == "baseline_tamper":
        native["native_snapshots"]["gripper"]["ingress_sequence"] += 1
        native["ingress_sequence_by_controller"]["gripper"] += 1
    elif change == "wrong_proof":
        case[1] = deepcopy(proof)
        case[1] = __import__("dataclasses").replace(case[1], sample_count=700)
    elif change == "unarmed":
        broker._armed_generation += 1
    elif change == "moving":
        broker.driver.stopped = lambda: False
    with pytest.raises(ValueError, match="VISIBLE_APPROACH_COMMIT_INGRESS_INVALID"):
        _verify(case)
