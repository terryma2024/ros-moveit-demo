import copy

import pytest

from b2_collection_fixtures import collection_materials
from test_act_scene_association import frozen_scene
from paths import PACKAGE_ROOT


def materials(frozen_scene):
    """The complete V2 originals (reset_complete, goal phase_begin, normal_stop, terminal, summary, continuity)."""
    events, identity, window, boundaries, sources, samples, _teacher = collection_materials(frozen_scene)
    return events, identity, window, boundaries, sources, samples


# REPLACED_BY test_teacher_collection.py: the dispatch-receipt / stop-evidence fault matrix of the broker contract
# (`test_current_native_qc_recomputes_complete_original_boundary_causality`, the previous-terminal-before-next-enqueue
# test) is gone with that contract; the V2 matrix is there.


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
