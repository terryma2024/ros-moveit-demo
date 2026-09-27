"""Only a validated SEARCH observation may register an expert source."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from so101_demo.act.ownership import Ownership
from so101_demo.act.prefix_source import PrefixSourceAuthority
from so101_demo.adapters.act.command_broker import CommandBroker
from so101_demo.adapters.act.pick_place_search_native_ingress import native_ingress_digest
from so101_demo.adapters.act.pick_place_search_port import PickPlaceSearchPhasePort
from so101_demo.adapters.act.trusted_visible_approach_source import (
    TrustedVisibleApproachSourcePort,
)

from test_act_visible_approach_expert_route import POLICY, proved_search, route


def _case(route):
    route._test_clock[0] = 10.12
    observed, source = proved_search(route)
    ownership = Ownership(monotonic=lambda: route._test_clock[0])
    source_port = TrustedVisibleApproachSourcePort()
    authority = PrefixSourceAuthority(
        ticket_guard=ownership.require_ticket,
        max_observation_age_s=.2, max_prefix_age_s=.2,
        monotonic=lambda: route._test_clock[0],
    )
    driver = SimpleNamespace(
        current_epoch=lambda: {"session_id": source["session_id"],
                               "reset_epoch": source["reset_epoch"]},
        stopped=lambda: True, stop_all=lambda _: None,
        refresh_stop=lambda: None,
        prepare_goal=lambda *_: None, send_prepared=lambda *_: None,
        discard_prepared=lambda *_: None,
    )
    reservation = SimpleNamespace(
        arm_generation=lambda *_: True, reserve=lambda *_: True,
        close_generation=lambda *_: True,
    )
    broker = CommandBroker(
        driver, ownership=ownership, simulation_session_id=source["session_id"],
        prefix_source_authority=authority, prefix_source_port=source_port,
        reservation_port=reservation,
    )
    token = ownership.acquire("act", source["session_id"], source["attempt_id"])
    ticket = ownership.ticket(token, "act", source["session_id"], source["attempt_id"])
    broker._armed_generation = ticket[0]
    observed = deepcopy(observed)
    observed.local_owner_goal_proof["owner_generation"] = ticket[0]
    native = observed.native_controller_ingress_proof
    native["owner_generation"] = ticket[0]
    for snapshot in native["native_snapshots"].values():
        snapshot["owner_generation"] = ticket[0]
    native["native_ingress_window_sha256"] = native_ingress_digest(
        native["native_snapshots"])
    search_port = object.__new__(PickPlaceSearchPhasePort)
    search_port._validated_search_observation = observed
    search_port._searched = True
    return source_port, search_port, broker, ticket, authority, source


def test_validated_search_registers_one_private_expert_source(route):
    source_port, search_port, broker, ticket, authority, source = _case(route)
    prepared = source_port.register(
        broker, search_port, route, ticket, active_policy_fingerprint=POLICY)
    receipt = authority._pending

    assert prepared["selected_source"] == source
    assert receipt.source_kind == "EXPERT_ROUTE"
    assert receipt.owner_ticket == ticket
    assert receipt.source_artifact_sha256 == prepared["source_artifact_sha256"]
    assert source_port(ticket) == source
    assert source_port(ticket) is not source_port(ticket)
    assert authority.consume(ticket=ticket, prefix=prepared["prefix"],
                             source=source_port(ticket)) is receipt
    assert prepared["command_authority"] is False
    assert prepared["eligible_for_collection"] is False
    assert broker._goal_tickets == {}


@pytest.mark.parametrize("change", ["selected_physics", "native_cursor", "owner_revoke"])
def test_private_source_lookup_refuses_changed_search(route, change):
    source_port, search_port, broker, ticket, authority, _ = _case(route)
    source_port.register(broker, search_port, route, ticket,
                         active_policy_fingerprint=POLICY)
    if change == "selected_physics":
        search_port._validated_search_observation.physical_readback[
            "scene"]["simulation_step"] += 1
    elif change == "native_cursor":
        search_port._validated_search_observation.native_controller_ingress_proof[
            "native_snapshots"]["gripper"]["ingress_sequence"] += 1
    else:
        broker.ownership.revoke("OTHER_OWNER")
    with pytest.raises(PermissionError, match="VISIBLE_APPROACH_SOURCE_UNAVAILABLE"):
        source_port(ticket)
    assert broker.ownership.state != "RUNNING"
    assert authority._pending is None


@pytest.mark.parametrize("change", [
    "unsearched", "wrong_epoch", "changed_native_digest", "wrong_policy",
    "moving", "unarmed", "source_port_replaced", "stale_source",
    "wrong_ticket", "replay",
])
def test_registration_failure_closes_owner_without_a_goal(route, change):
    source_port, search_port, broker, ticket, authority, _ = _case(route)
    if change == "unsearched":
        search_port._searched = False
    elif change == "wrong_epoch":
        broker.driver.current_epoch = lambda: {
            "session_id": ticket[3], "reset_epoch": 99}
    elif change == "changed_native_digest":
        search_port._validated_search_observation.native_controller_ingress_proof[
            "native_snapshots"]["neck"]["ingress_sequence"] += 1
    elif change == "wrong_policy":
        policy = "0" * 64
    elif change == "moving":
        broker.driver.stopped = lambda: False
    elif change == "unarmed":
        broker._armed_generation += 1
    elif change == "source_port_replaced":
        broker._prefix_source_port = lambda _: None
    elif change == "stale_source":
        route._test_clock[0] = 10.4
    elif change == "wrong_ticket":
        ticket = (ticket[0] + 1, *ticket[1:])
    elif change == "replay":
        source_port.register(broker, search_port, route, ticket,
                             active_policy_fingerprint=POLICY)
    if change != "wrong_policy":
        policy = POLICY
    with pytest.raises(ValueError, match="TRUSTED_VISIBLE_APPROACH_SOURCE_INVALID"):
        source_port.register(broker, search_port, route, ticket,
                             active_policy_fingerprint=policy)
    assert broker.ownership.state != "RUNNING"
    assert broker._goal_tickets == {}
    assert authority._pending is None
