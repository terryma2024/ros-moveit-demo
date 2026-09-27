"""A reserved ACT pair needs broker-owned source proof before approval."""

from types import SimpleNamespace

import pytest

from so101_demo.adapters.act.broker_execution import BrokerPairedExecution
from test_act_physics import scene
from test_act_path_proof_permits import proof_authority
from test_controller_reservation_transaction import acquire_request, prepared_broker


def _paired(broker, **proof_ports):
    return BrokerPairedExecution(
        broker,
        snapshot_port=lambda ticket: dict(
            session_id=ticket[3], attempt_id=ticket[4], reset_epoch=1,
            sim_time_s=1., positions=(0.,) * 6, velocities=(0.,) * 6,
        ),
        check_port=lambda *_: (_ for _ in ()).throw(
            AssertionError("legacy checker must not approve a reserved pair")),
        reference_port=lambda _: (0.,) * 6,
        sim_clock=lambda: 1., submit_lead_s=.15,
        accept_timeout_s=.08, stop_timeout_s=.03, permit_ttl_s=.2,
        **proof_ports,
    )


def test_reserved_pair_refuses_legacy_approval_before_path_check():
    broker, driver, controller, ticket = prepared_broker()
    broker.prefix_executor = _paired(broker)
    prefix = dict(session_id="session", attempt_id="attempt", sequence=0,
                  observation_time_s=1., target_times_s=(1.1,),
                  positions=((0.,) * 6,))

    response = broker.handle(dict(acquire_request(ticket[1]),
                                  operation="approve_prefix", prefix=prefix),
                             "connection")

    assert not response["accepted"]
    assert response["error"] == "PATH_PROOF_SOURCE_UNWIRED"
    assert driver.events == []
    assert controller.closes == []


def test_broker_pair_approves_one_complete_proof_from_trusted_source(scene):
    authority, prefix, current, checks = proof_authority(
        scene, source_backed=True)
    receipt = authority.test_source_receipt
    ticket = receipt.owner_ticket

    class Owner:
        generation = ticket[0]

        @staticmethod
        def require_ticket(candidate):
            if candidate != ticket:
                raise PermissionError("OWNER_CHANGED")

    broker = SimpleNamespace(
        ownership=Owner(), driver=SimpleNamespace(stopped=lambda: True),
        reservation_port=object(),
    )
    pair = _paired(
        broker,
        proof_source_port=authority.proof_source_port,
        proof_state_port=authority.proof_state_port,
        proof_reference_port=lambda start: dict(
            requested_sim_time_s=start,
            positions=current["snapshot"]["controller_start_positions"],
            velocities=current["snapshot"]["controller_start_velocities"]),
        proof_clock_port=lambda: dict(
            wall_s=10.06, sim_s=4.85, error_s=.001, continuous=True),
        proof_goal_port=lambda *_: True,
        proof_timing=dict(max_observation_age_s=.4, max_prefix_age_s=.2,
                          max_state_age_s=.1, observation_jitter_s=.01,
                          start_jitter_s=.02, first_target_jitter_s=.02),
        max_observation_age_s=.4, max_prefix_age_s=.2,
    )
    pair.permits.snapshot_port = authority.snapshot_port
    pair.permits.monotonic = lambda: 10.

    permit = pair.approve_with_source(ticket, prefix, receipt)
    proof = pair.permits.require(permit, prefix)

    assert proof.status == "SAFE"
    assert proof.sample_count == 701
    assert proof.relative_request.source_receipt is receipt
    assert checks == [1]
    assert pair.adapter.proof_timing["max_observation_age_s"] == .4
