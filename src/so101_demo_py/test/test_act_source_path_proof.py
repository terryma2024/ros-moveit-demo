"""A relative path keeps the broker's original source and prefix clocks."""

from dataclasses import replace

import pytest

from so101_demo.act.execution import prefix_sha256
from so101_demo.act.prefix_source import PrefixSourceReceipt, SOURCE_KEYS
from so101_demo.act.path_proof import RelativePathRequest
from so101_demo.act.path_proof import PathProver

from test_act_physics import checker, inputs, scene


def _prefix():
    return {
        'session_id': 'session', 'attempt_id': 'attempt', 'sequence': 0,
        'observation_time_s': 4.0, 'target_times_s': (4.1,),
        'positions': ((.001,) * 6,),
    }


def _receipt(prefix):
    return PrefixSourceReceipt(
        source_kind='EXPERT_ROUTE', source_artifact_sha256='b' * 64,
        contact_policy_fingerprint='c' * 64,
        observation_sha256='a' * 64,
        source_received_wall_s=tuple((key, 9.8 + index * .01)
                                     for index, key in enumerate(SOURCE_KEYS)),
        source_phase='SEARCH', physics_step=21, reset_epoch=3,
        owner_ticket=(7, 'lease', 'act', 'session', 'attempt'),
        prefix_sha256=prefix_sha256(prefix), sequence=0,
        prefix_issued_wall_s=9.95,
    )


def test_source_path_request_keeps_original_clocks_and_identity():
    prefix = _prefix()
    receipt = _receipt(prefix)
    request = RelativePathRequest.from_source_receipt(
        prefix, receipt=receipt, bridge_time_s=4.0, start_time_s=4.05,
    )
    assert request.source_receipt is receipt
    assert request.prefix_issued_wall_s == 9.95
    assert request.oldest_source_wall_s == 9.8
    request.require_source_freshness(
        now_wall_s=10.1, max_observation_age_s=.4,
        max_prefix_age_s=.2, jitter_s=.01,
    )
    materialized = request.materialize(start_time_s=6.05, bridge_time_s=6.0)
    assert materialized['prefix_issued_wall_s'] == 9.95
    assert materialized['source_received_wall_s'] == receipt.source_received_wall_s
    assert 'policy_received_wall_s' not in materialized


def test_source_path_request_rejects_changed_receipt_and_stale_original_time():
    prefix = _prefix()
    receipt = _receipt(prefix)
    with pytest.raises(ValueError, match='PATH_SOURCE_RECEIPT_INVALID'):
        RelativePathRequest.from_source_receipt(
            prefix, receipt=replace(receipt, prefix_sha256='f' * 64),
            bridge_time_s=4.0, start_time_s=4.05,
        )
    request = RelativePathRequest.from_source_receipt(
        prefix, receipt=receipt, bridge_time_s=4.0, start_time_s=4.05,
    )
    with pytest.raises(ValueError, match='PREFIX_OBSERVATION_STALE'):
        request.require_source_freshness(
            now_wall_s=10.1, max_observation_age_s=.3,
            max_prefix_age_s=.2, jitter_s=.01,
        )
    with pytest.raises(ValueError, match='PREFIX_SOURCE_STALE'):
        request.require_source_freshness(
            now_wall_s=10.14, max_observation_age_s=.5,
            max_prefix_age_s=.2, jitter_s=.02,
        )


@pytest.mark.parametrize('change', ('generation', 'epoch', 'contact_policy'))
def test_path_prover_rejects_source_receipt_scope_change(scene, change):
    path = checker(scene)
    prefix, physical = inputs(path)
    physical['controller_bridge']['time_s'] = .9
    physical['controller_start_time_s'] = 1.05
    physical['model_qvel'] = (0.,) * path.model.nv
    receipt = replace(
        _receipt(_prefix()),
        owner_ticket=(7, 'lease', 'act', 's', 'a'),
        prefix_sha256=prefix_sha256(prefix),
    )
    request = RelativePathRequest.from_source_receipt(
        prefix, receipt=receipt, bridge_time_s=.9, start_time_s=1.05,
    )
    ticket = receipt.owner_ticket
    epoch = 3
    policy = 'c' * 64
    if change == 'generation':
        ticket = (8, *ticket[1:])
    elif change == 'epoch':
        epoch = 4
    else:
        policy = 'd' * 64
    with pytest.raises(ValueError, match='PATH_PROOF_SOURCE_INVALID'):
        PathProver(path, monotonic=lambda: 10.).prove(
            request, physical, ticket=ticket, reset_epoch=epoch,
            policy_fingerprint=policy, profile_sha256='e' * 64,
            contact_scope_sha256='f' * 64, checker_sha256='1' * 64,
            expected_samples=701,
        )
