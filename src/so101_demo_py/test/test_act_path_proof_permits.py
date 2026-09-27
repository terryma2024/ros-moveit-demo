"""A broker permit consumes one full path proof after fresh state checks."""

import copy

import pytest

from so101_demo.act.path_proof import PathProver, RelativePathRequest
from so101_demo.act.permits import PermitAuthority

from test_act_physics import checker, inputs, scene


def proof_authority(scene):
    path = checker(scene, {'CONTACT': {('arm', 'obstacle')}})
    prefix, physical = inputs(path)
    held = physical['controller_start_positions']
    prefix.update(
        first_target_delay_s=.1, target_interval_s=.002,
        target_times_s=tuple(1.1 + .002 * (index + 1) for index in range(600)),
        positions=tuple(held for _ in range(600)),
    )
    physical.update(phase='CONTACT', sim_time_s=1.,
                    controller_start_time_s=1.05,
                    model_qvel=(0.,) * path.model.nv)
    physical['controller_bridge']['time_s'] = .9
    request = RelativePathRequest.from_prefix(
        prefix, bridge_time_s=.9, start_time_s=1.05,
        policy_received_wall_s=10.,
    )
    ticket = (7, 'lease', 'act', 's', 'a')
    fingerprints = dict(
        policy_fingerprint='1' * 64, profile_sha256='2' * 64,
        contact_scope_sha256='3' * 64, checker_sha256='4' * 64,
    )
    current = dict(snapshot=physical, reset_epoch=3, **fingerprints)
    approval = dict(session_id='s', attempt_id='a', reset_epoch=3,
                    sim_time_s=1., positions=held, velocities=(0.,) * 6)
    checks = [0]
    original_check = path.check_path

    def counted_check(candidate, snapshot):
        checks[0] += 1
        return original_check(candidate, snapshot)

    path.check_path = counted_check

    def prove(candidate, _approval, generation):
        assert generation == ticket[0]
        assert candidate == prefix
        return PathProver(path, monotonic=lambda: 10.).prove(
            request, physical, ticket=ticket, reset_epoch=3,
            expected_samples=701, **fingerprints,
        )

    authority = PermitAuthority(
        snapshot_port=lambda: copy.deepcopy(approval),
        check_port=lambda *_: (_ for _ in ()).throw(
            AssertionError('full checker called twice')),
        proof_port=prove,
        proof_state_port=lambda: copy.deepcopy(current),
        proof_ticket_port=lambda: ticket,
        generation_port=lambda: ticket[0],
        monotonic=lambda: 10., ttl_s=.2,
    )
    return authority, prefix, current, checks


def test_one_full_checker_run_serves_approve_and_single_use_consume(scene):
    authority, prefix, current, checks = proof_authority(scene)
    permit = authority.approve(prefix)
    proof = authority.require(permit, prefix)
    assert proof.status == 'SAFE' and proof.sample_count == 701
    assert checks == [1]
    with pytest.raises(PermissionError, match='PERMIT_INVALID'):
        authority.require(permit, prefix)


@pytest.mark.parametrize('change', (
    'qpos', 'qvel', 'phase', 'holding', 'bridge_reference',
    'epoch', 'policy', 'profile', 'contact', 'checker',
))
def test_proof_permit_rejects_changed_physical_or_source_state(scene, change):
    authority, prefix, current, checks = proof_authority(scene)
    permit = authority.approve(prefix)
    if change == 'qpos':
        current['snapshot']['model_qpos'] = tuple(
            value + (0.001 if index == 0 else 0.)
            for index, value in enumerate(current['snapshot']['model_qpos']))
    elif change == 'qvel':
        current['snapshot']['model_qvel'] = (0.001,) + tuple(
            current['snapshot']['model_qvel'][1:])
    elif change == 'phase':
        current['snapshot']['phase'] = 'APPROACH'
    elif change == 'holding':
        current['snapshot']['holding_state'] = 'held'
    elif change == 'bridge_reference':
        current['snapshot']['controller_bridge']['point']['positions'] = (
            0.001,) + tuple(
                current['snapshot']['controller_bridge']['point']['positions'][1:])
    elif change == 'epoch':
        current['reset_epoch'] += 1
    else:
        field = {
            'policy': 'policy_fingerprint', 'profile': 'profile_sha256',
            'contact': 'contact_scope_sha256', 'checker': 'checker_sha256',
        }[change]
        current[field] = 'f' * 64
    with pytest.raises(PermissionError, match='PERMIT_INVALID'):
        authority.require(permit, prefix)
    assert checks == [1]


def test_proof_permit_rejects_same_generation_with_different_lease(scene):
    authority, prefix, _, checks = proof_authority(scene)
    permit = authority.approve(prefix)
    authority.proof_ticket_port = lambda: (7, 'other-lease', 'act', 's', 'a')
    with pytest.raises(PermissionError, match='PERMIT_INVALID'):
        authority.require(permit, prefix)
    assert checks == [1]
