"""The rollout-side execution override: mode resolution, the temporal-ensembling math, and its use in the episode loop."""

import math

import pytest

from so101_demo.act.policy import ActPolicyRunner
from so101_demo.act.rollout_episode import run_episode
from so101_demo.act.rollout_execution import ChunkEnsembler, resolve_execution

from test_act_rollout_episode import Model, Ports, SETTINGS, SCENE, Sink, SNAPSHOT_TARGETS, _endpoint_policy

BUNDLE_ACTION = {"chunk_size": 10, "execution_prefix": 1, "temporal_ensembling": False, "tail_padding_mask": True}


def _mode(**kwargs):
    return resolve_execution(BUNDLE_ACTION, **kwargs)


# ---- resolution and refusals ----------------------------------------------------------------------------------------------


def test_no_override_is_the_bundle_default():
    mode = _mode()
    assert mode.source == "bundle" and mode.scheme == "prefix" and mode.execution_prefix == 1
    assert mode.runner_prefix is None and not mode.open_loop and not mode.ensembling
    assert mode.document() == {"source": "bundle", "scheme": "prefix", "execution_prefix": 1, "chunk_size": 10,
                               "temporal_ensembling_m": None, "open_loop": False}


def test_a_prefix_override_is_open_loop_and_recorded():
    mode = _mode(prefix=5)
    assert (mode.source, mode.scheme, mode.execution_prefix, mode.runner_prefix) == ("cli", "prefix", 5, 5)
    assert mode.open_loop and mode.document()["execution_prefix"] == 5


def test_a_prefix_override_equal_to_the_bundle_is_still_an_override_for_identity_purposes():
    mode = _mode(prefix=1)
    assert mode.source == "cli" and not mode.open_loop


def test_ensembling_is_one_step_per_inference_with_the_weight_decay_recorded():
    mode = _mode(ensembling=0.01)
    assert mode.ensembling and mode.runner_prefix == 1 and mode.execution_prefix == 1
    assert mode.document()["temporal_ensembling_m"] == 0.01 and mode.document()["scheme"] == "ensemble"


@pytest.mark.parametrize("kwargs, code", [
    ({"prefix": 0}, "EXECUTION_PREFIX_INVALID"), ({"prefix": -3}, "EXECUTION_PREFIX_INVALID"),
    ({"prefix": True}, "EXECUTION_PREFIX_INVALID"), ({"prefix": 2.0}, "EXECUTION_PREFIX_INVALID"),
    ({"prefix": 11}, "EXECUTION_PREFIX_EXCEEDS_CHUNK"),
    ({"prefix": 5, "ensembling": 0.01}, "EXECUTION_MODE_CONFLICT"),
    ({"ensembling": -0.1}, "EXECUTION_ENSEMBLING_INVALID"), ({"ensembling": float("nan")}, "EXECUTION_ENSEMBLING_INVALID"),
    ({"ensembling": float("inf")}, "EXECUTION_ENSEMBLING_INVALID"), ({"ensembling": True}, "EXECUTION_ENSEMBLING_INVALID"),
    ({"ensembling": "0.01"}, "EXECUTION_ENSEMBLING_INVALID")])
def test_invalid_combinations_are_refused(kwargs, code):
    with pytest.raises(ValueError, match=code):
        _mode(**kwargs)


def test_ensembling_needs_a_chunk_longer_than_one_step():
    with pytest.raises(ValueError, match="EXECUTION_ENSEMBLING_CHUNK_TOO_SHORT"):
        resolve_execution(dict(BUNDLE_ACTION, chunk_size=1), ensembling=0.01)


def test_the_runner_takes_a_prefix_override_and_refuses_one_beyond_the_chunk():
    runner = ActPolicyRunner({"action": BUNDLE_ACTION}, Model(), execution_prefix=4)
    assert runner.execution_prefix == 4
    with pytest.raises(ValueError, match="POLICY_BUNDLE_INVALID"):
        ActPolicyRunner({"action": BUNDLE_ACTION}, Model(), execution_prefix=11)
    with pytest.raises(ValueError, match="POLICY_BUNDLE_INVALID"):
        ActPolicyRunner({"action": BUNDLE_ACTION}, Model(), execution_prefix=0)


# ---- the ensembling math --------------------------------------------------------------------------------------------------


def _chunk(value):
    return [[value + 0.01 * k] * 6 for k in range(10)]


def test_the_first_chunk_alone_gives_its_first_action():
    ensembler = ChunkEnsembler(0.01, 10)
    ensembler.add(1.0, _chunk(0.0))
    action, who = ensembler.action_at(1.1)
    assert action == pytest.approx([0.0] * 6) and [item["index"] for item in who] == [0]


def test_weights_are_exp_minus_m_times_rank_with_the_oldest_chunk_first():
    m = 0.5
    ensembler = ChunkEnsembler(m, 10)
    for step, base in enumerate((1.0, 2.0, 4.0)):                  # chunks observed at 1.0, 1.1, 1.2
        ensembler.add(round(1.0 + 0.1 * step, 6), _chunk(base))
    action, who = ensembler.action_at(1.3)                         # k = 2 of the oldest, 1 of the middle, 0 of the newest
    assert [item["index"] for item in who] == [2, 1, 0]
    values = (1.0 + 0.02, 2.0 + 0.01, 4.0)
    weights = [math.exp(-m * rank) for rank in range(3)]
    expected = sum(w * v for w, v in zip(weights, values)) / sum(weights)
    assert action == pytest.approx([expected] * 6)
    assert [item["weight"] for item in who] == pytest.approx(weights)


def test_a_skipped_observation_leaves_a_gap_and_the_index_follows_the_time():
    ensembler = ChunkEnsembler(0.0, 10)
    ensembler.add(1.0, _chunk(0.0))
    ensembler.add(1.3, _chunk(1.0))                                 # observations at 1.1 and 1.2 were skipped
    action, who = ensembler.action_at(1.4)
    assert [item["index"] for item in who] == [3, 0]
    assert action == pytest.approx([(0.03 + 1.0) / 2] * 6)


def test_a_chunk_that_no_longer_covers_the_target_drops_out():
    ensembler = ChunkEnsembler(0.01, 10)
    ensembler.add(1.0, _chunk(0.0))                                 # covers 1.1 .. 2.0
    ensembler.add(2.0, _chunk(5.0))
    action, who = ensembler.action_at(2.1)
    assert [item["index"] for item in who] == [0] and action == pytest.approx([5.0] * 6)


def test_a_target_off_the_chunk_grid_does_not_borrow_a_neighbouring_step():
    ensembler = ChunkEnsembler(0.0, 10)
    ensembler.add(1.0, _chunk(0.0))
    ensembler.add(1.15, _chunk(1.0))                                # 50 ms off the grid of the first chunk
    action, who = ensembler.action_at(1.25)
    assert [item["index"] for item in who] == [0]
    assert action == pytest.approx([1.0] * 6)


def test_an_uncovered_target_and_malformed_chunks_are_refused():
    ensembler = ChunkEnsembler(0.01, 10)
    with pytest.raises(ValueError, match="ENSEMBLE_EMPTY"):
        ensembler.action_at(1.1)
    for bad in ([[0.0] * 5], [[float("nan")] * 6], "x", [[True] * 6]):
        with pytest.raises(ValueError, match="ENSEMBLE_CHUNK_INVALID"):
            ensembler.add(1.0, bad)


# ---- the episode loop -----------------------------------------------------------------------------------------------------


def _ports(prefix=1, **kwargs):
    ports = Ports(**kwargs)
    ports.runner = ActPolicyRunner({"action": dict(BUNDLE_ACTION)}, Model(), execution_prefix=prefix)
    return ports


def _run(ports, mode, sink=None):
    return run_episode(scene=SCENE, attempt_id="attempt-1", ports=ports, settings=SETTINGS,
                       snapshot_targets=SNAPSHOT_TARGETS, endpoint_policy=_endpoint_policy(), sink=sink, execution=mode)


def test_without_an_execution_argument_the_loop_is_unchanged_and_records_the_bundle_default():
    ports = Ports()
    result = run_episode(scene=SCENE, attempt_id="a", ports=ports, settings=SETTINGS, snapshot_targets=SNAPSHOT_TARGETS,
                         endpoint_policy=_endpoint_policy())
    assert result["execution"]["source"] == "bundle" and result["execution"]["execution_prefix"] == 1
    assert result["counts"].get("prefix_wait_observations", 0) == 0
    assert all(len(prefix["positions"]) == 1 for prefix in ports.session.prefixes)


def test_a_multi_step_prefix_is_executed_open_loop_and_inference_waits_for_it():
    ports, sink = _ports(prefix=5), Sink()
    result = _run(ports, _mode(prefix=5), sink)
    prefixes = ports.session.prefixes
    assert result["execution"]["execution_prefix"] == 5 and result["execution"]["open_loop"] is True
    assert prefixes and all(len(prefix["positions"]) == 5 for prefix in prefixes)
    for prefix in prefixes:
        assert prefix["target_times_s"] == pytest.approx(
            tuple(prefix["observation_time_s"] + 0.1 * step for step in range(1, 6)))
    for previous, following in zip(prefixes, prefixes[1:]):
        # the next observation is taken only once the previous prefix has been consumed (within the 10 ms tolerance)
        assert following["observation_time_s"] >= previous["target_times_s"][-1] - 0.011
    waits = [row for row in sink.steps if row.get("reason") == "PREFIX_IN_PROGRESS"]
    assert waits and result["counts"]["prefix_wait_observations"] == len(waits)
    assert len(prefixes) < result["counts"]["observations"] / 4                  # far fewer inferences than observations


def test_a_late_multi_step_prefix_is_held_whole_and_inference_does_not_wait():
    ports, sink = _ports(prefix=5, session_kwargs={"submit_error": ValueError("PREFIX_LATE")}), Sink()
    result = _run(ports, _mode(prefix=5), sink)
    assert result["counts"]["prefix_late"] > 3 and result["counts"]["applied"] == 0
    assert result["counts"]["prefix_wait_observations"] == 0                      # nothing was applied, so nothing is waited for


def test_a_late_reply_during_open_loop_sends_nothing_and_inference_resumes_at_once():
    ports, sink = _ports(prefix=5), Sink()
    ports.inference.script = ["ok", "timeout", "ok"]
    result = _run(ports, _mode(prefix=5), sink)
    late = [row for row in sink.steps if row.get("late")]
    assert result["counts"]["late_replies"] == 1 and len(late) == 1 and late[0]["applied"] is False
    applied = [row for row in sink.steps if row.get("applied")]
    assert applied[0]["sequence"] == 0 and any(row["sequence"] > late[0]["sequence"] for row in applied)
    # the late reply applied nothing, so the observation after it started an inference without a prefix wait in between
    after = [row for row in sink.steps if row.get("sequence") == late[0]["sequence"] + 1]
    assert after and after[0]["observation_sim_s"] - late[0]["observation_sim_s"] < 0.5


def test_temporal_ensembling_infers_every_step_and_applies_one_ensembled_action():
    ports, sink = _ports(prefix=1), Sink()
    result = _run(ports, _mode(ensembling=0.01), sink)
    prefixes = ports.session.prefixes
    assert result["execution"]["scheme"] == "ensemble" and result["execution"]["temporal_ensembling_m"] == 0.01
    assert prefixes and all(len(prefix["positions"]) == 1 for prefix in prefixes)
    applied = [row for row in sink.steps if row.get("applied")]
    counts = [len(row["ensemble"]["contributors"]) for row in applied]
    assert counts[0] == 1 and max(counts) > 1 and max(counts) <= 10
    row = applied[-1]
    # the applied action is the weighted mean of the contributors' chunk entries
    chunks = {r["observation_sim_s"]: r["chunk"] for r in sink.steps if r.get("chunk")}
    num = [0.0] * 6
    den = 0.0
    for who in row["ensemble"]["contributors"]:
        action = chunks[who["observed_s"]][who["index"]]
        num = [a + who["weight"] * b for a, b in zip(num, action)]
        den += who["weight"]
    assert row["prefix"]["positions"][0] == pytest.approx([a / den for a in num])
    assert result["counts"]["prefix_wait_observations"] == 0


def test_a_late_chunk_still_feeds_the_ensemble_but_is_not_applied():
    ports, sink = _ports(prefix=1, session_kwargs={"submit_error": ValueError("PREFIX_LATE")}), Sink()
    result = _run(ports, _mode(ensembling=0.01), sink)
    assert result["counts"]["prefix_late"] > 0 and result["counts"]["applied"] == 0
    held = [row for row in sink.steps if row.get("reason") == "PREFIX_LATE"]
    assert held and max(len(row["ensemble"]["contributors"]) for row in held) > 1


def test_a_runner_that_does_not_match_the_mode_is_refused_before_anything_runs():
    ports = _ports(prefix=1)
    with pytest.raises(ValueError, match="EXECUTION_RUNNER_MISMATCH"):
        _run(ports, _mode(prefix=5))
    assert "reset" not in ports.calls
    with pytest.raises(ValueError, match="EXECUTION_RUNNER_MISMATCH"):
        _run(_ports(prefix=5), _mode(ensembling=0.01))
