"""Chunk size 50 is a supported, explicit contract next to 10; any other size stays refused (TRAIN-007). Fixture-only."""

import pytest
import yaml

from so101_demo.act.rollout_execution import ChunkEnsembler, resolve_execution
from so101_demo.act.training_config import ALLOWED_CHUNK_SIZES, load_training_config
from paths import PACKAGE_ROOT

CONFIG_DIR = PACKAGE_ROOT / "config/act"
BASE = CONFIG_DIR / "training-side-wrist-005-bf16.yaml"


def _with_chunk(tmp_path, chunk):
    document = yaml.safe_load(BASE.read_text())
    document["action"]["chunk_size"] = chunk
    path = tmp_path / f"training-{chunk}.yaml"
    path.write_text(yaml.safe_dump(document))
    return path


def test_the_allowed_set_is_closed():
    assert ALLOWED_CHUNK_SIZES == (10, 50)


@pytest.mark.parametrize("chunk", [10, 50])
def test_allowed_chunk_sizes_load(tmp_path, chunk):
    assert load_training_config(_with_chunk(tmp_path, chunk))["action"]["chunk_size"] == chunk


@pytest.mark.parametrize("chunk", [20, 0, 100, True, 50.0, "50"])
def test_other_chunk_sizes_are_refused(tmp_path, chunk):
    with pytest.raises(ValueError, match="TRAINING_CHUNK_SIZE_DRIFT"):
        load_training_config(_with_chunk(tmp_path, chunk))


@pytest.mark.parametrize("name,lr", [("a", 1.0e-4), ("b", 1.0e-5)])
def test_the_train007_configs_differ_from_train005_only_where_approved(name, lr):
    base = load_training_config(BASE)
    config = load_training_config(CONFIG_DIR / f"training-side-wrist-007{name}-bf16.yaml")
    assert config["action"]["chunk_size"] == 50 and config["action"]["execution_prefix"] == 1
    assert config["training"]["learning_rate"] == lr and config["training"]["learning_rate_backbone"] == 1.0e-5
    assert config["training"]["sample_selection"]["idle_threshold_rad"] == 0.001
    assert config["training"]["sample_selection"]["keep_tail_rows"] == 20 < config["action"]["chunk_size"]
    for document in (base, config):
        document["action"].pop("chunk_size")
        document["training"].pop("learning_rate")
        document["training"]["sample_selection"].pop("idle_threshold_rad")
    assert base == config


def test_the_action_window_and_mask_at_chunk_50_near_the_episode_end():
    import numpy as np

    from so101_demo.adapters.act.lerobot import _action_window
    actions = np.arange(100, dtype=np.float32)[:, None].repeat(6, axis=1)
    chunk, pad = _action_window(actions, 10, 50)
    assert chunk.shape == (50, 6) and not pad.any() and chunk[0, 0] == 10 and chunk[-1, 0] == 59
    chunk, pad = _action_window(actions, 80, 50)         # 20 real rows, 30 padded
    assert chunk.shape == (50, 6) and pad.tolist() == [False] * 20 + [True] * 30
    assert (chunk[20:] == 99).all() and chunk[19, 0] == 99
    chunk, pad = _action_window(actions, 99, 50)         # the very last row: one real, 49 padded
    assert pad.sum() == 49 and not pad[0]
    # every one of the last keep_tail_rows (20) start rows still has real rows at the front of its masked window
    for start in range(80, 100):
        assert not _action_window(actions, start, 50)[1][0]


def test_the_rollout_prefix_bound_is_the_bundle_chunk():
    action = {"chunk_size": 50, "execution_prefix": 1, "temporal_ensembling": False, "tail_padding_mask": True}
    assert resolve_execution(action, prefix=50).execution_prefix == 50
    assert resolve_execution(action, prefix=25).document()["chunk_size"] == 50
    with pytest.raises(ValueError, match="EXECUTION_PREFIX_EXCEEDS_CHUNK"):
        resolve_execution(action, prefix=51)
    with pytest.raises(ValueError, match="EXECUTION_PREFIX_EXCEEDS_CHUNK"):
        resolve_execution(dict(action, chunk_size=10), prefix=11)


def test_ensembling_at_chunk_50_uses_the_whole_chunk():
    action = {"chunk_size": 50, "execution_prefix": 1, "temporal_ensembling": False, "tail_padding_mask": True}
    mode = resolve_execution(action, ensembling=0.01)
    assert mode.scheme == "ensemble" and mode.chunk_size == 50
    ensembler = ChunkEnsembler(mode.ensemble_m, mode.chunk_size)
    ensembler.add(0.0, [(1.0,) * 6] * 50)
    ensembler.add(0.1, [(3.0,) * 6] * 50)
    value, contributors = ensembler.action_at(0.5)
    assert len(contributors) == 2 and 1.0 < value[0] < 3.0
    value, contributors = ensembler.action_at(4.5)       # index 44 of the older chunk, 43 of the newer
    assert sorted(item["index"] for item in contributors) == [43, 44]
    value, contributors = ensembler.action_at(5.1)       # past the end of the older chunk (50 targets): only the newer one is left
    assert [item["index"] for item in contributors] == [49] and value[0] == 3.0
