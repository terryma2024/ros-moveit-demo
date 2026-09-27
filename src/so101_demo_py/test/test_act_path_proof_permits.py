"""A broker permit consumes one full path proof after fresh state checks."""

import copy
from dataclasses import replace

import pytest

from so101_demo.act.path_proof import PathProver, RelativePathRequest
from so101_demo.act.permits import PermitAuthority
from so101_demo.act.prefix_source import PrefixSourceReceipt, SOURCE_KEYS
from so101_demo.act.execution import prefix_sha256

from test_act_physics import checker, inputs, scene


def proof_authority(scene, *, source_backed=False):
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
    ticket = (7, 'lease', 'act', 's', 'a')
    receipt = None
    if source_backed:
        receipt = PrefixSourceReceipt(
            source_kind='EXPERT_ROUTE', source_artifact_sha256='5' * 64,
            contact_policy_fingerprint='1' * 64,
            observation_sha256='6' * 64,
            source_received_wall_s=tuple((key, 9.8 + index * .01)
                                         for index, key in enumerate(SOURCE_KEYS)),
            source_phase='SEARCH', physics_step=21, reset_epoch=3,
            owner_ticket=ticket, prefix_sha256=prefix_sha256(prefix),
            sequence=prefix['sequence'], prefix_issued_wall_s=9.95,
        )
        request = RelativePathRequest.from_source_receipt(
            prefix, receipt=receipt, bridge_time_s=.9, start_time_s=1.05,
        )
    else:
        request = RelativePathRequest.from_prefix(
            prefix, bridge_time_s=.9, start_time_s=1.05,
            prefix_issued_wall_s=10.,
        )
    fingerprints = dict(
        policy_fingerprint='1' * 64, profile_sha256='2' * 64,
        contact_scope_sha256='3' * 64, checker_sha256='4' * 64,
    )
    current = dict(snapshot=physical, reset_epoch=3, **fingerprints)
    if source_backed:
        current.update(
            source_available=True,
            source_artifact_sha256=receipt.source_artifact_sha256,
            observation_sha256=receipt.observation_sha256,
            source_received_wall_s=receipt.source_received_wall_s,
            source_phase=receipt.source_phase,
            source_physics_step=receipt.physics_step,
        )
    approval = dict(session_id='s', attempt_id='a', reset_epoch=3,
                    sim_time_s=1., positions=held, velocities=(0.,) * 6,
                    prefix_issued_wall_s=10.)
    checks = [0]
    original_check = path.check_path

    def counted_check(candidate, snapshot):
        checks[0] += 1
        return original_check(candidate, snapshot)

    path.check_path = counted_check

    def prove(candidate, _approval, generation, source_receipt=None):
        assert generation == ticket[0]
        assert candidate == prefix
        if source_backed:
            assert source_receipt is receipt
        return PathProver(path, monotonic=lambda: 10.).prove(
            request, physical, ticket=ticket, reset_epoch=3,
            expected_samples=701, **fingerprints,
        )

    authority = PermitAuthority(
        snapshot_port=lambda: copy.deepcopy(approval),
        check_port=lambda *_: (_ for _ in ()).throw(
            AssertionError('full checker called twice')),
        proof_port=None if source_backed else prove,
        proof_source_port=prove if source_backed else None,
        proof_state_port=lambda: copy.deepcopy(current),
        proof_ticket_port=lambda: ticket,
        max_observation_age_s=.4 if source_backed else None,
        max_prefix_age_s=.2 if source_backed else None,
        generation_port=lambda: ticket[0],
        monotonic=lambda: 10., ttl_s=.2,
    )
    authority.test_source_receipt = receipt
    return authority, prefix, current, checks


def test_source_backed_proof_requires_private_receipt_and_checks_once(scene):
    authority, prefix, _, checks = proof_authority(scene, source_backed=True)
    receipt = authority.test_source_receipt
    with pytest.raises(PermissionError, match='PATH_SOURCE_RECEIPT_REQUIRED'):
        authority.approve(prefix)
    with pytest.raises(PermissionError, match='PATH_SOURCE_RECEIPT_INVALID'):
        authority.approve_with_source(prefix, replace(receipt, prefix_sha256='f' * 64))
    permit = authority.approve_with_source(prefix, receipt)
    proof = authority.require(permit, prefix)
    assert proof.relative_request.source_receipt is receipt
    assert checks == [1]
    with pytest.raises(PermissionError, match='PERMIT_INVALID'):
        authority.require(permit, prefix)


def test_source_backed_commit_keeps_observation_and_prefix_ages(scene):
    from so101_demo.act.path_proof import require_commit_window

    authority, prefix, _, checks = proof_authority(scene, source_backed=True)
    proof = authority.require(
        authority.approve_with_source(prefix, authority.test_source_receipt),
        prefix,
    )
    proof = replace(proof, started_wall_s=10., completed_wall_s=10.09,
                    proof_compute_latency_s=.09)
    parameters = dict(
        state_received_wall_s=10.10, accepted_wall_s=10.14,
        accepted_sim_s=4.9, start_sim_s=5.,
        max_observation_age_s=.4, max_prefix_age_s=.25,
        max_state_age_s=.1, observation_jitter_s=.01,
        start_jitter_s=.02, first_target_jitter_s=.02,
        clock_error_s=.001, clock_continuous=True,
    )
    result = require_commit_window(proof, **parameters)
    assert result['observation_age_s'] == pytest.approx(.34)
    assert result['prefix_age_s'] == pytest.approx(.19)
    for changed in (
            dict(max_observation_age_s=.3), dict(max_prefix_age_s=.2),
            dict(max_observation_age_s=None), dict(max_prefix_age_s=None)):
        with pytest.raises(ValueError, match='COMMIT_WINDOW_INVALID'):
            require_commit_window(proof, **dict(parameters, **changed))
    assert checks == [1]


@pytest.mark.parametrize('changed', (
    'source_available', 'source_artifact_sha256', 'observation_sha256',
    'source_received_wall_s', 'source_phase', 'source_physics_step',
))
def test_source_proof_closes_if_selected_source_changes(scene, changed):
    authority, prefix, current, checks = proof_authority(scene, source_backed=True)
    permit = authority.approve_with_source(prefix, authority.test_source_receipt)
    current[changed] = (False if changed == 'source_available'
                        else 'different')
    with pytest.raises(PermissionError, match='PERMIT_INVALID'):
        authority.require(permit, prefix)
    assert checks == [1]


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


def test_proof_permit_requires_complete_701_sample_result(scene):
    authority, prefix, _, checks = proof_authority(scene)
    original = authority.proof_port
    authority.proof_port = lambda *args: replace(
        original(*args), sample_count=700)
    with pytest.raises(PermissionError, match='PATH_REJECTED'):
        authority.approve(prefix)
    assert checks == [1]


@pytest.mark.parametrize('change', (
    'positions', 'target_offset', 'observation', 'sequence',
    'bridge_offset', 'policy_receipt',
))
def test_proof_request_must_match_approved_prefix_fields(scene, change):
    authority, prefix, _, checks = proof_authority(scene)
    original = authority.proof_port

    def altered_proof(*args):
        proof = original(*args)
        request = proof.relative_request
        if change == 'positions':
            rows = ((request.positions[0][0] + .001,
                     *request.positions[0][1:]), *request.positions[1:])
            request = replace(request, positions=rows)
        elif change == 'target_offset':
            request = replace(request, target_offsets_ns=(
                request.target_offsets_ns[0] + 1_000_000,
                *request.target_offsets_ns[1:]))
        elif change == 'observation':
            request = replace(request, source_observation_time_s=2.)
        elif change == 'sequence':
            request = replace(request, sequence=request.sequence + 1)
        elif change == 'policy_receipt':
            request = replace(request, prefix_issued_wall_s=10.01)
        else:
            request = replace(request, bridge_offset_ns=
                              request.bridge_offset_ns + 1_000_000)
        return replace(proof, relative_request=request)

    authority.proof_port = altered_proof
    with pytest.raises(PermissionError, match='PATH_REJECTED'):
        authority.approve(prefix)
    assert checks == [1]


def test_consumed_proof_fresh_readback_closes_on_state_change_or_revoke(scene):
    authority, prefix, current, checks = proof_authority(scene)
    permit = authority.approve(prefix)
    proof = authority.require(permit, prefix)
    readback = authority.current_proof_state(proof)
    assert readback['reset_epoch'] == proof.reset_epoch
    assert readback['snapshot']['model_qvel'] == current['snapshot']['model_qvel']
    current['snapshot']['model_qvel'] = (0.001,) + tuple(
        current['snapshot']['model_qvel'][1:])
    with pytest.raises(PermissionError, match='PATH_PROOF_CURRENT_INVALID'):
        authority.current_proof_state(proof)
    authority.revoke('hazard')
    with pytest.raises(PermissionError, match='PATH_PROOF_CURRENT_INVALID'):
        authority.current_proof_state(proof)
    assert checks == [1]


def test_unconsumed_or_closed_proof_cannot_get_commit_readback(scene):
    authority, prefix, _, checks = proof_authority(scene)
    captured = []
    original = authority.proof_port

    def capture(*args):
        proof = original(*args)
        captured.append(proof)
        return proof

    authority.proof_port = capture
    permit = authority.approve(prefix)
    proof = captured[0]
    with pytest.raises(PermissionError, match='PATH_PROOF_CURRENT_INVALID'):
        authority.current_proof_state(proof)
    consumed = authority.require(permit, prefix)
    authority.close_proof(consumed)
    with pytest.raises(PermissionError, match='PATH_PROOF_CURRENT_INVALID'):
        authority.current_proof_state(consumed)
    assert checks == [1]


def test_consumed_proof_expiry_and_revoke_fence_a_delayed_readback(scene):
    import threading

    authority, prefix, _, checks = proof_authority(scene)
    proof = authority.require(authority.approve(prefix), prefix)
    original = authority.proof_state_port
    entered, release = threading.Event(), threading.Event()
    outcomes = []

    def delayed():
        entered.set()
        release.wait(1.)
        return original()

    authority.proof_state_port = delayed

    def readback():
        try:
            authority.current_proof_state(proof)
        except PermissionError as error:
            outcomes.append(str(error))

    worker = threading.Thread(target=readback)
    worker.start()
    assert entered.wait(.2)
    authority.revoke('hazard')
    release.set()
    worker.join(.2)
    assert not worker.is_alive() and outcomes == ['PATH_PROOF_CURRENT_INVALID']
    assert checks == [1]

    new_authority, new_prefix, _, new_checks = proof_authority(scene)
    new_proof = new_authority.require(
        new_authority.approve(new_prefix), new_prefix)
    new_authority.monotonic = lambda: 10.2
    with pytest.raises(PermissionError, match='PATH_PROOF_CURRENT_INVALID'):
        new_authority.current_proof_state(new_proof)
    assert new_checks == [1]


@pytest.mark.parametrize('change', (
    'arm_joint_order', 'gripper_joint_order', 'row', 'offset', 'stamp',
    'prefix_hash', 'extra_field',
))
def test_exact_goal_pair_is_bound_to_proof(scene, change):
    from so101_demo.act.path_proof import goal_pair_from_proof, require_proven_goals

    authority, prefix, _, checks = proof_authority(scene)
    proof = authority.require(authority.approve(prefix), prefix)
    goals = goal_pair_from_proof(
        proof, start_time_s=5., bridge_time_s=4.85,
        reference_positions=proof.controller_start_positions,
    )
    assert goals[0]['header_stamp_s'] == goals[1]['header_stamp_s'] == 5.
    assert goals[0]['time_from_start_s'][:3] == (0., .052, .054)
    assert len(goals[0]['positions']) == len(goals[1]['positions']) == 601
    require_proven_goals(
        proof, goals, bridge_time_s=4.85,
        reference_positions=proof.controller_start_positions,
    )
    changed = copy.deepcopy(goals)
    if change == 'arm_joint_order':
        changed[0]['joint_names'] = tuple(reversed(changed[0]['joint_names']))
    elif change == 'gripper_joint_order':
        changed[1]['joint_names'] = ('wrong_gripper',)
    elif change == 'row':
        changed[0]['positions'] = changed[0]['positions'][:-1] + ((.001,) * 5,)
    elif change == 'offset':
        offsets = changed[0]['time_from_start_s']
        changed[0]['time_from_start_s'] = offsets[:-1] + (offsets[-1] + .002,)
    elif change == 'stamp':
        changed[1]['header_stamp_s'] += .002
    elif change == 'prefix_hash':
        changed[0]['prefix_sha256'] = '0' * 64
    else:
        changed[1]['unapproved'] = True
    with pytest.raises(ValueError, match='PATH_GOALS_MISMATCH'):
        require_proven_goals(
            proof, tuple(changed), bridge_time_s=4.85,
            reference_positions=proof.controller_start_positions,
        )
    assert checks == [1]


def test_goal_materialization_rejects_changed_bridge_or_reference(scene):
    from so101_demo.act.path_proof import goal_pair_from_proof

    authority, prefix, _, checks = proof_authority(scene)
    proof = authority.require(authority.approve(prefix), prefix)
    with pytest.raises(ValueError, match='BRIDGE_INTERVAL_CHANGED'):
        goal_pair_from_proof(
            proof, start_time_s=5., bridge_time_s=4.851,
            reference_positions=proof.controller_start_positions,
        )
    changed = (proof.controller_start_positions[0] + .001,
               *proof.controller_start_positions[1:])
    with pytest.raises(ValueError, match='PATH_REFERENCE_CHANGED'):
        goal_pair_from_proof(
            proof, start_time_s=5., bridge_time_s=4.85,
            reference_positions=changed,
        )
    assert checks == [1]


@pytest.mark.parametrize('change', (
    'state_age', 'policy_age', 'start_deadline', 'first_deadline',
    'clock_discontinuity', 'missing_clock_error', 'state_before_proof',
))
def test_commit_window_rejects_stale_or_late_acceptance(scene, change):
    from so101_demo.act.path_proof import require_commit_window

    authority, prefix, _, checks = proof_authority(scene)
    proof = authority.require(authority.approve(prefix), prefix)
    proof = replace(proof, started_wall_s=10., completed_wall_s=10.09,
                    proof_compute_latency_s=.09)
    parameters = dict(
        state_received_wall_s=10.10, accepted_wall_s=10.14,
        accepted_sim_s=4.9, start_sim_s=5.,
        max_prefix_age_s=.2, max_state_age_s=.1,
        observation_jitter_s=.01, start_jitter_s=.02,
        first_target_jitter_s=.02, clock_error_s=.001,
        clock_continuous=True,
    )
    result = require_commit_window(proof, **parameters)
    assert result['prefix_age_s'] == pytest.approx(.14)
    assert result['state_age_s'] == pytest.approx(.04)
    if change == 'state_age':
        parameters.update(accepted_wall_s=10.20, max_prefix_age_s=.5)
    elif change == 'policy_age':
        parameters['accepted_wall_s'] = 10.20
    elif change == 'start_deadline':
        parameters['accepted_sim_s'] = 5.
    elif change == 'first_deadline':
        parameters.update(accepted_sim_s=4.95,
                          first_target_jitter_s=.11)
    elif change == 'clock_discontinuity':
        parameters['clock_continuous'] = False
    elif change == 'missing_clock_error':
        parameters['clock_error_s'] = None
    else:
        parameters['state_received_wall_s'] = 10.08
    with pytest.raises(ValueError, match='COMMIT_WINDOW_INVALID'):
        require_commit_window(proof, **parameters)
    assert checks == [1]
