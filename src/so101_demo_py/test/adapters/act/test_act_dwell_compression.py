"""``sample_selection.compress_dwell``: the dwell rows leave the episode timeline (observations and action targets alike)."""
import importlib.util
import json

import pytest

# the end-to-end test needs torch and LeRobot; the pure-row tests only need numpy
needs_training = pytest.mark.skipif(
    any(importlib.util.find_spec(name) is None for name in ("torch", "lerobot", "PIL", "numpy")),
    reason="the training interpreter owns torch and LeRobot")
pytest.importorskip("numpy")

COMPRESS = {"trim_leading_idle": False, "idle_threshold_rad": 0.005, "lead_in_rows": 0, "compress_dwell": True, "keep_tail_rows": 2}


def _walk(positions):
    """Rows of a robot commanded to, and reaching, ``positions[i]`` (joint 0) one row later: action[t] = state[t+1]."""
    rows = []
    for index, position in enumerate(positions):
        target = positions[min(index + 1, len(positions) - 1)]
        rows.append({"observation": {"state": [position, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
                     "action": [target, 0.0, 0.0, 0.0, 0.0, 0.0]})
    return rows


def test_plateaus_and_leading_idle_are_removed_and_only_the_tail_is_kept():
    from so101_demo.adapters.act.lerobot import dwell_compressed_rows
    # rows 0..2 dwell at 0 (leading idle), 3..5 move, 6..9 dwell at 0.3, 10..12 move, 13..16 dwell at 0.6 (the last two are the tail)
    positions = [0, 0, 0, 0, 0.1, 0.2, 0.3, 0.3, 0.3, 0.3, 0.3, 0.4, 0.5, 0.6, 0.6, 0.6, 0.6]
    rows = _walk(positions)
    assert dwell_compressed_rows(rows, 0.005, 2) == [3, 4, 5, 10, 11, 12, 15, 16]
    assert dwell_compressed_rows(rows, 0.005, 0) == [3, 4, 5, 10, 11, 12]
    assert dwell_compressed_rows([], 0.005, 2) == []
    assert dwell_compressed_rows(rows, 0.005, 100) == list(range(17))      # a tail longer than the episode keeps everything


def test_the_threshold_is_strict_and_both_the_command_and_the_motion_count():
    from so101_demo.adapters.act.lerobot import dwell_compressed_rows
    still = {"observation": {"state": [0.0] * 8}, "action": [0.0] * 6}
    commanded = {"observation": {"state": [0.0] * 8}, "action": [0.005, 0, 0, 0, 0, 0]}          # |a - s| == thr: not below, so moving
    moved_on = {"observation": {"state": [0.005, 0, 0, 0, 0, 0, 0, 0]}, "action": [0.005, 0, 0, 0, 0, 0]}
    assert dwell_compressed_rows([still, still, still], 0.005, 0) == []
    assert dwell_compressed_rows([commanded, still, still], 0.005, 0) == [0]
    assert dwell_compressed_rows([still, moved_on, moved_on], 0.005, 0) == [0]                   # s[1] - s[0] == thr: row 0 moves
    assert dwell_compressed_rows([still, still], 0.005, 0) == []                                 # the last row has no successor
    gripper = {"observation": {"state": [0.0] * 8}, "action": [0, 0, 0, 0, 0, 0.5]}
    assert dwell_compressed_rows([gripper], 0.005, 0) == [0]                                     # joint 5 is one of the six arm joints
    state_only = {"observation": {"state": [0, 0, 0, 0, 0, 0, 0.9, 0.9]}, "action": [0.0] * 6}
    assert dwell_compressed_rows([state_only], 0.005, 0) == []                                   # entries beyond the six are ignored


def test_a_chunk_spanning_a_removed_plateau_is_one_continuous_motion():
    import numpy as np
    from so101_demo.adapters.act.lerobot import _action_window, _chunk_samples, compress_dwell_samples
    episode = {"scene_id": "m", "split": "train", "rows": _walk([0, 0, 0.1, 0.2, 0.2, 0.2, 0.2, 0.3, 0.4, 0.4, 0.4])}
    [compressed] = compress_dwell_samples([episode], COMPRESS)
    assert len(compressed["rows"]) < len(episode["rows"])
    actions = np.asarray([row["action"] for row in compressed["rows"]])
    window, pad = _action_window(actions, 0, 4)
    assert not pad.any() and (np.diff(window[:, 0]) > 0).all()                                   # no repeated plateau value in the chunk
    assert _chunk_samples([compressed], COMPRESS, 4) == [(0, row) for row in range(len(compressed["rows"]))]
    assert list(actions[-2:, 0]) == [0.4, 0.4]                                                   # the tail: the policy still learns to hold


def test_off_by_default_and_the_same_rule_for_every_split():
    from so101_demo.adapters.act.lerobot import compress_dwell_samples
    episode = {"scene_id": "m", "split": "validation", "rows": _walk([0, 0, 0, 0.1, 0.2, 0.2, 0.2])}
    assert compress_dwell_samples([episode], None) is not None and compress_dwell_samples([episode], None) == [episode]
    assert compress_dwell_samples([episode], {**COMPRESS, "compress_dwell": False}) == [episode]
    [out] = compress_dwell_samples([episode], COMPRESS)
    assert out["split"] == "validation" and out["scene_id"] == "m"
    assert [row["observation"]["state"][0] for row in out["rows"]] == [0.0, 0.1, 0.2, 0.2]


@needs_training
def test_a_training_run_with_compress_dwell_trains_on_the_compressed_timeline(tmp_path, monkeypatch):
    from test_act_lerobot_training import _train
    selection = {"trim_leading_idle": False, "idle_threshold_rad": 0.005, "lead_in_rows": 0, "compress_dwell": True, "keep_tail_rows": 2}
    _, outcome, root = _train(tmp_path, monkeypatch, sample_selection=selection)
    assert outcome["status"] == "COMPLETED"
    log = json.loads((root / "training-log.json").read_text())
    train = log["sample_selection"]["train"]
    assert train["compress_dwell"] is True and train["samples_before"] - train["samples_after"] == train["dwell_rows_removed"]
    assert log["train_samples"] == train["samples_after"]
    assert log["sample_selection"]["validation"]["compress_dwell"] is True
