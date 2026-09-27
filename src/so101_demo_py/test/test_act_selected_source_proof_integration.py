"""One selected physical source reaches one complete offline path proof."""

import copy

import pytest

from so101_demo.act.path_proof import PathProver, RelativePathRequest
from so101_demo.act.ownership import Ownership
from so101_demo.act.prefix_source import PrefixSourceAuthority
from so101_demo.adapters.act.command_broker import CommandBroker
from so101_demo.adapters.act.selected_search_source import freeze_selected_search_source

from test_act_physics import checker, inputs, scene
from test_act_task8_search_port import observation


def _fixture(scene):
    path = checker(scene, {'CONTACT': {('arm', 'obstacle')}})
    _, physical = inputs(path)
    physical.update(
        phase='CONTACT', model_qvel=(0.,) * path.model.nv,
        sim_time_s=1.2, controller_start_time_s=1.25,
    )
    physical['controller_bridge']['time_s'] = 1.1
    held = physical['controller_start_positions']
    selected = observation()
    selected.physical_readback['scene'].update(
        model_sha256=path.model_sha256,
        qpos=physical['model_qpos'], qvel=physical['model_qvel'],
    )
    source = freeze_selected_search_source(selected, max_skew_s=.02)
    prefix = dict(
        session_id=source['session_id'], attempt_id=source['attempt_id'],
        sequence=0, observation_time_s=source['simulation_time_s'],
        first_target_delay_s=.1, target_interval_s=.002,
        target_times_s=tuple(1.2 + .1 + .002 * (index + 1)
                             for index in range(600)),
        positions=tuple(held for _ in range(600)),
    )
    clock = [10.1]
    ownership = Ownership(monotonic=lambda: clock[0])
    token = ownership.acquire('act', source['session_id'], source['attempt_id'])
    ticket = ownership.ticket(token, 'act', source['session_id'], source['attempt_id'])
    authority = PrefixSourceAuthority(
        ticket_guard=ownership.require_ticket,
        monotonic=lambda: clock[0], max_observation_age_s=.5,
        max_prefix_age_s=.3,
    )

    class StoppedDriver:
        def stopped(self):
            return True

    broker = CommandBroker(
        StoppedDriver(), ownership=ownership,
        simulation_session_id=source['session_id'],
        prefix_source_authority=authority,
        prefix_source_port=lambda current_ticket: source,
    )
    receipt = broker.issue_prefix_source(
        ticket=ticket, prefix=prefix, source=source,
        source_kind='EXPERT_ROUTE', source_artifact_sha256='b' * 64,
        contact_policy_fingerprint='c' * 64,
    )
    return path, physical, selected, source, prefix, ticket, authority, receipt


def test_one_selected_source_yields_one_complete_no_command_proof(scene):
    path, physical, _, source, prefix, ticket, authority, receipt = _fixture(scene)
    assert authority.consume(ticket=ticket, prefix=prefix, source=source) is receipt
    request = RelativePathRequest.from_source_receipt(
        prefix, receipt=receipt, bridge_time_s=1.1, start_time_s=1.25,
    )
    checks = [0]
    original_check = path.check_path

    def counted_check(candidate, snapshot):
        checks[0] += 1
        return original_check(candidate, snapshot)

    path.check_path = counted_check
    proof = PathProver(path, monotonic=lambda: 10.1).prove(
        request, physical, ticket=ticket, reset_epoch=source['reset_epoch'],
        policy_fingerprint='c' * 64, profile_sha256='d' * 64,
        contact_scope_sha256='e' * 64, checker_sha256='f' * 64,
        expected_samples=701,
    )
    assert proof.status == 'SAFE'
    assert proof.sample_count == 701
    assert proof.relative_request.source_receipt is receipt
    assert checks == [1]
    assert receipt.command_authority is False
    with pytest.raises(PermissionError, match='PREFIX_SOURCE_UNAVAILABLE'):
        authority.consume(ticket=ticket, prefix=prefix, source=source)


def test_selected_image_change_closes_receipt_before_proof(scene):
    _, _, selected, _, prefix, ticket, authority, _ = _fixture(scene)
    changed = copy.deepcopy(selected)
    changed.physical_readback['observation']['wrist'][0, 0, 0] = 1
    different = freeze_selected_search_source(changed, max_skew_s=.02)
    with pytest.raises(PermissionError, match='PREFIX_SOURCE_CHANGED'):
        authority.consume(ticket=ticket, prefix=prefix, source=different)
