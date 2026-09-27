"""Relative proof time must preserve the real MuJoCo swept-path decision."""

import pytest

from so101_demo.act.path_proof import RelativePathRequest

from so101_demo.adapters.act.physics import MujocoPathProcess

from test_act_physics import checker, inputs, scene


def test_time_translation_preserves_all_701_safe_samples(scene):
    port = checker(scene, {'CONTACT': {('arm', 'obstacle')}})
    prefix, snapshot = inputs(port)
    held = snapshot['controller_start_positions']
    prefix.update(
        first_target_delay_s=.1, target_interval_s=.002,
        target_times_s=tuple(1.1 + .002 * (index + 1) for index in range(600)),
        positions=tuple(held for _ in range(600)),
    )
    snapshot.update(phase='CONTACT', sim_time_s=1.,
                    controller_start_time_s=1.05)
    snapshot['controller_bridge']['time_s'] = .9

    assert port.check_path(prefix, snapshot) is True
    assert port.last_check['samples'] == 701

    request = RelativePathRequest.from_prefix(
        prefix, bridge_time_s=.9, start_time_s=1.05,
        policy_received_wall_s=10.,
    )
    shifted_prefix, shifted_snapshot = request.checker_inputs(snapshot)
    assert port.check_path(shifted_prefix, shifted_snapshot) is True
    assert port.last_check['samples'] == 701
    assert shifted_snapshot['controller_start_time_s'] - shifted_snapshot['controller_bridge']['time_s'] == pytest.approx(.15)


def test_time_translation_preserves_first_forbidden_contact(scene):
    port = checker(scene)
    prefix, snapshot = inputs(port)
    start = snapshot['controller_start_positions']
    prefix.update(
        first_target_delay_s=.1, target_interval_s=.002,
        target_times_s=tuple(1.1 + .002 * (index + 1) for index in range(600)),
        positions=tuple((-1. + 2. * (index + 1) / 600, *start[1:])
                        for index in range(600)),
    )
    snapshot.update(sim_time_s=1., controller_start_time_s=1.05)
    snapshot['controller_bridge']['time_s'] = .9

    assert port.check_path(prefix, snapshot) is False
    original = dict(port.last_check)
    assert original['reason'] == 'ROBOT_PATH_CONTACT'
    assert original['contact_pair'] == ('arm', 'obstacle')
    assert 0 < original['sample_index'] < 701

    request = RelativePathRequest.from_prefix(
        prefix, bridge_time_s=.9, start_time_s=1.05,
        policy_received_wall_s=10.,
    )
    shifted_prefix, shifted_snapshot = request.checker_inputs(snapshot)
    assert port.check_path(shifted_prefix, shifted_snapshot) is False
    shifted = dict(port.last_check)
    assert shifted['reason'] == original['reason']
    assert shifted['contact_pair'] == original['contact_pair']
    assert shifted['sample_index'] == original['sample_index']
    assert shifted['signed_distance_m'] == pytest.approx(original['signed_distance_m'])
    assert shifted['sample_time_s'] - shifted_snapshot['controller_bridge']['time_s'] == pytest.approx(
        original['sample_time_s'] - snapshot['controller_bridge']['time_s'], abs=1e-9)


def test_full_proof_binds_qvel_and_checks_all_701_once(scene, monkeypatch):
    from so101_demo.act.path_proof import PathProver

    port = checker(scene, {'CONTACT': {('arm', 'obstacle')}})
    prefix, snapshot = inputs(port)
    held = snapshot['controller_start_positions']
    prefix.update(
        first_target_delay_s=.1, target_interval_s=.002,
        target_times_s=tuple(1.1 + .002 * (index + 1) for index in range(600)),
        positions=tuple(held for _ in range(600)),
    )
    snapshot.update(phase='CONTACT', sim_time_s=1.,
                    controller_start_time_s=1.05,
                    model_qvel=(0.,) * port.model.nv)
    snapshot['controller_bridge']['time_s'] = .9
    request = RelativePathRequest.from_prefix(
        prefix, bridge_time_s=.9, start_time_s=1.05,
        policy_received_wall_s=10.,
    )
    checks = [0]
    clock = [10.]
    original_inputs = RelativePathRequest.checker_inputs

    def counted_preparation(candidate, physical):
        clock[0] += .05
        return original_inputs(candidate, physical)

    monkeypatch.setattr(RelativePathRequest, 'checker_inputs',
                        counted_preparation)
    original_check = port.check_path

    def count_real_check(candidate, physical):
        checks[0] += 1
        result = original_check(candidate, physical)
        clock[0] += .09
        return result

    port.check_path = count_real_check
    proof = PathProver(port, monotonic=lambda: clock[0]).prove(
        request, snapshot, ticket=(7, 'lease', 'act', 's', 'a'),
        reset_epoch=3, policy_fingerprint='1' * 64,
        profile_sha256='2' * 64, contact_scope_sha256='3' * 64,
        checker_sha256='4' * 64, expected_samples=701,
    )
    assert proof.status == 'SAFE'
    assert proof.sample_count == 701
    assert proof.proof_compute_latency_s == pytest.approx(.14)
    assert checks == [1]
    assert proof.matches_state(snapshot)
    changed = dict(snapshot, model_qvel=(.001,) + snapshot['model_qvel'][1:])
    assert not proof.matches_state(changed)


def test_first_unsafe_sample_is_a_read_only_result(scene):
    from so101_demo.act.path_proof import PathProver

    port = checker(scene)
    prefix, snapshot = inputs(port)
    start = snapshot['controller_start_positions']
    prefix.update(
        first_target_delay_s=.1, target_interval_s=.002,
        target_times_s=tuple(1.1 + .002 * (index + 1) for index in range(600)),
        positions=tuple((-1. + 2. * (index + 1) / 600, *start[1:])
                        for index in range(600)),
    )
    snapshot.update(sim_time_s=1., controller_start_time_s=1.05,
                    model_qvel=(0.,) * port.model.nv)
    snapshot['controller_bridge']['time_s'] = .9
    request = RelativePathRequest.from_prefix(
        prefix, bridge_time_s=.9, start_time_s=1.05,
        policy_received_wall_s=10.,
    )
    proof = PathProver(port, monotonic=lambda: 10.).prove(
        request, snapshot, ticket=(7, 'lease', 'act', 's', 'a'),
        reset_epoch=3, policy_fingerprint='1' * 64,
        profile_sha256='2' * 64, contact_scope_sha256='3' * 64,
        checker_sha256='4' * 64, expected_samples=701,
    )
    assert proof.status == 'VIOLATION'
    assert proof.first_violation['sample_index'] + 1 == proof.sample_count
    assert proof.first_violation['contact_pair'] == ('arm', 'obstacle')
    with pytest.raises(TypeError):
        proof.first_violation['sample_index'] = 0


def test_production_worker_can_return_a_full_relative_proof(scene):
    from so101_demo.act.path_proof import PathProver

    process = MujocoPathProcess(
        check_timeout_s=1., start_timeout_s=2., model_path=scene,
        protected_roots=('base',), cup_joint='cup_free_joint',
        gripper_body='gripper', path_step_s=.002, path_clearance_m=.002,
        velocity_limit_rad_s=(100.,) * 6,
        acceleration_limit_rad_s2=(1e6,) * 6,
        allowed_pairs_by_phase={'CONTACT': {('arm', 'obstacle')}},
    )
    try:
        prefix, snapshot = inputs(process)
        held = snapshot['controller_start_positions']
        prefix.update(
            first_target_delay_s=.1, target_interval_s=.002,
            target_times_s=tuple(1.1 + .002 * (index + 1)
                                 for index in range(600)),
            positions=tuple(held for _ in range(600)),
        )
        snapshot.update(phase='CONTACT', sim_time_s=1.,
                        controller_start_time_s=1.05,
                        model_qvel=(0.,) * process.model.nv)
        snapshot['controller_bridge']['time_s'] = .9
        request = RelativePathRequest.from_prefix(
            prefix, bridge_time_s=.9, start_time_s=1.05,
            policy_received_wall_s=10.,
        )
        proof = PathProver(process).prove(
            request, snapshot, ticket=(7, 'lease', 'act', 's', 'a'),
            reset_epoch=3, policy_fingerprint='1' * 64,
            profile_sha256='2' * 64, contact_scope_sha256='3' * 64,
            checker_sha256='4' * 64, expected_samples=701,
        )
        assert proof.status == 'SAFE' and proof.sample_count == 701
    finally:
        process.close()
