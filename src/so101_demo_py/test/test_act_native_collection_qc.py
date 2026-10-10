import copy

import pytest

from b2_collection_fixtures import materials_v2
from test_act_scene_association import frozen_scene
from paths import PACKAGE_ROOT


def materials(frozen_scene):
    """The complete V2 originals (reset_complete, goal phase_begin, normal_stop, terminal, summary, continuity)."""
    events, identity, window, boundaries, sources, samples, _teacher = materials_v2(frozen_scene)
    return events, identity, window, boundaries, sources, samples


# REPLACED_BY test_b2_collection_v2.py: the dispatch-receipt / stop-evidence fault matrix of the broker contract
# (`test_current_native_qc_recomputes_complete_original_boundary_causality`, the previous-terminal-before-next-enqueue
# test) is gone with that contract; the V2 matrix is there.


@pytest.mark.parametrize('fault', [None, 'target', 'policy', 'missing_proofs'])
def test_native_endpoint_reader_uses_first_sources_and_authenticated_frozen_targets(frozen_scene, fault):
    from so101_demo.act import episode_qc
    from so101_demo.act.endpoint_pose_acceptance import load_endpoint_policy
    from so101_demo.act.execution_snapshot import verify_execution_snapshot
    from so101_demo.act.scene_association import digest
    verify = getattr(episode_qc, 'native_endpoint_records', None)
    assert callable(verify), 'actual endpoint readback still uses physics stream extrema'
    events, identity, window, _, sources, _ = materials(frozen_scene)
    policy = load_endpoint_policy(PACKAGE_ROOT/'config/act/endpoint_pose_acceptance_v1.yaml')
    inputs = copy.deepcopy(frozen_scene[1])
    inputs['endpoint_policy'] = dict(rule_version=policy['rule_version'], thresholds=policy['thresholds'], sha256=digest(policy))
    inputs['inputs_sha256'] = digest({**inputs['roles'], **{key: value for key, value in inputs.items() if key not in ('roles', 'inputs_sha256')}})
    targets = verify_execution_snapshot(frozen_scene[0])['targets']
    endpoint_inputs = dict(endpoint_policy=inputs['endpoint_policy'], initial_target=targets['initial_target'],
        final_target=targets['final_target'], endpoint_targets=targets)
    if fault == 'target': endpoint_inputs['initial_target'] = [9.,9.,9.,0.,0.,0.,1.]
    if fault == 'policy': endpoint_inputs['endpoint_policy'] = dict(inputs['endpoint_policy'], sha256='a'*64)
    if fault == 'missing_proofs': events = [row for row in events if row['kind'] != 'collection_boundary_v1']
    if fault is None:
        result = verify(events, identity=identity, window=window, inputs=inputs, endpoint_inputs=endpoint_inputs)
        assert result['initial_sequence'] == 8 and result['final_sequence'] == 10
        assert result['initial_pose'] == [*sources[1]['physics']['object_state']['position_world'],
            *sources[1]['physics']['object_state']['orientation_xyzw']]
        assert result['initial_target'] == targets['initial_target']
        # The controlled elevated cup is intentionally away from both frozen targets.
        assert result['status'] == 'FAIL' and not all(result['passed'].values())
    else:
        with pytest.raises(ValueError): verify(events, identity=identity, window=window, inputs=inputs, endpoint_inputs=endpoint_inputs)


def test_the_raw_step_index_matches_the_scan_it_replaces_and_follows_the_list_it_is_given():
    """The QC verifies thousands of world sources against one list of raw samples; the per-source scan made that quadratic. The
    memoised index must return exactly what the scan returned, including duplicates, and must never serve a stale list: the seal
    passes a fresh one-element list per source, so temporaries (whose ids get reused) are scanned, never cached."""
    from so101_demo.act.native_endpoints import _raw_steps_at

    big = [{"physics_step": step % 200} for step in range(1000)]
    for step in (0, 5, 199, 200, 999):
        assert _raw_steps_at(big, step) == [sample for sample in big if sample["physics_step"] == step]
    other = [{"physics_step": (step * 7) % 150} for step in range(1000)]            # same length, another list
    for step in (0, 5, 149, 199):
        assert _raw_steps_at(other, step) == [sample for sample in other if sample["physics_step"] == step]
    for round_ in range(50):                                                         # temporaries with reused addresses
        sample = {"physics_step": round_}
        assert _raw_steps_at([sample], round_) == [sample] and _raw_steps_at([sample], round_ + 1) == []
    assert _raw_steps_at([], 1) == []


def test_the_physics_count_of_a_schema_3_report_counts_the_raw_chunks_the_episode_retained():
    """A passing QC report needs every count above zero; the count read `physics.jsonl`, which nothing writes since the Recorder was
    decoupled, so the pilot episode's QC computed PASS and then failed to validate its own report ('verdict')."""
    from so101_demo.act.episode_qc import physics_chunk_count

    events = [{"kind": "physics_chunk_v1"}, {"kind": "world_source_v1"}, {"kind": "physics_chunk_v1"}, "not an event"]
    assert physics_chunk_count(events) == 2 and physics_chunk_count([]) == 0
