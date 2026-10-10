"""Design 2026-10-10 section 3.3 / D8: the dataset side of the LeRobot adapter (decode, view, statistics). No torch needed."""
import importlib.util
import json
import shutil

import pytest

_HAVE = all(importlib.util.find_spec(name) is not None for name in ("numpy", "PIL"))
pytestmark = pytest.mark.skipif(not _HAVE, reason="the decode path needs numpy and pillow")
if _HAVE:
    import numpy as np

from act_training_fixture import smooth_png, synthetic_dataset  # noqa: E402

SPLITS = {"act-1": "train", "act-2": "train", "act-3": "validation"}


def _view(tmp_path, monkeypatch, **kwargs):
    from so101_demo.act.training import load_training_samples, materialize_training_view
    dataset = synthetic_dataset(tmp_path, monkeypatch, splits=SPLITS, **kwargs)
    samples = load_training_samples(dataset)
    return dataset, materialize_training_view(dataset, tmp_path / "bundle.training-view", samples)


def test_decode_png_returns_uint8_hxwx3_rgb(tmp_path):
    from so101_demo.adapters.act.lerobot import decode_png
    path = tmp_path / "frame.png"
    path.write_bytes(smooth_png(7, 5, 3))
    image = decode_png(path)
    assert image.dtype == np.uint8 and image.shape == (5, 7, 3)
    assert image[0, 0, 0] == (0 * 6 + 0 * 2 + 0 * 61 + 21) % 256 and image[2, 3, 1] == (3 * 6 + 2 * 2 + 61 + 21) % 256


def test_decode_png_refuses_anything_but_8_bit_rgb(tmp_path):
    from PIL import Image

    from so101_demo.adapters.act.lerobot import decode_png
    for mode in ("L", "RGBA"):
        path = tmp_path / f"{mode}.png"
        Image.new(mode, (4, 3)).save(path)
        with pytest.raises(ValueError, match="OBSERVATION_IMAGE_INVALID"):
            decode_png(path)
    garbage = tmp_path / "garbage.png"
    garbage.write_bytes(b"not a png")
    with pytest.raises(ValueError, match="OBSERVATION_IMAGE_INVALID"):
        decode_png(garbage)
    with pytest.raises(ValueError, match="OBSERVATION_IMAGE_INVALID"):
        decode_png(tmp_path / "absent.png")


def test_the_d8_table_turns_a_stored_observation_into_the_runtime_observation(tmp_path, monkeypatch):
    from so101_demo.adapters.act.lerobot import decode_observation, load_training_view
    dataset, view = _view(tmp_path, monkeypatch, size=(9, 6))
    samples, root = load_training_view(view)
    observation = samples[0]["rows"][3]["observation"]
    assert set(observation) == {"sim_time_s", "state", "head_png", "wrist_png"}
    runtime = decode_observation(observation, root)
    assert set(runtime) == {"sim_time_s", "state", "head", "wrist"}               # the runtime keys, not the recorder keys
    assert runtime["head"].dtype == np.uint8 and runtime["head"].shape == (6, 9, 3)
    assert runtime["wrist"].dtype == np.uint8 and runtime["wrist"].shape == (6, 9, 3)
    assert len(runtime["state"]) == 8 and runtime["sim_time_s"] == observation["sim_time_s"]
    assert (runtime["head"] == np.asarray(__import__("PIL.Image", fromlist=["Image"]).open(root / observation["head_png"]))).all()
    assert not (runtime["head"] == runtime["wrist"]).all()                        # head_png -> head and wrist_png -> wrist, not swapped


def test_a_frame_path_that_leaves_the_dataset_is_refused(tmp_path, monkeypatch):
    from so101_demo.adapters.act.lerobot import decode_observation
    observation = {"sim_time_s": 0.0, "state": [0.0] * 8, "head_png": "../x.png", "wrist_png": "episodes/a/frames/000000-wrist.png"}
    with pytest.raises(ValueError, match="OBSERVATION_IMAGE_INVALID"):
        decode_observation(observation, tmp_path)
    observation["head_png"] = "/etc/passwd"
    with pytest.raises(ValueError, match="OBSERVATION_IMAGE_INVALID"):
        decode_observation(observation, tmp_path)


def test_the_view_loads_against_the_dataset_and_re_verifies_the_frame_digests(tmp_path, monkeypatch):
    from so101_demo.adapters.act.lerobot import load_training_view
    dataset, view = _view(tmp_path, monkeypatch)
    samples, root = load_training_view(view)
    assert root == dataset.resolve() and [item["scene_id"] for item in samples] == ["act-1", "act-2", "act-3"]
    assert [item["split"] for item in samples] == ["train", "train", "validation"]
    frame = dataset / "episodes" / "act-2" / "frames" / "000004-head.png"
    frame.write_bytes(frame.read_bytes()[:-1] + b"\x00")
    with pytest.raises(ValueError, match="TRAINING_EPISODE_FRAME_DIGEST_MISMATCH"):
        load_training_view(view)


def test_a_view_whose_manifest_or_samples_do_not_belong_to_the_dataset_is_refused(tmp_path, monkeypatch):
    from so101_demo.adapters.act.lerobot import load_training_view
    dataset, view = _view(tmp_path, monkeypatch)
    document = json.loads((view / "training-samples.json").read_text())
    document["samples"][0]["rows"] = document["samples"][0]["rows"][:-1]
    (view / "training-samples.json").write_text(json.dumps(document))
    with pytest.raises(ValueError, match="TRAINING_VIEW_SAMPLES_MISMATCH"):
        load_training_view(view)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other, other_view = _view(other_dir, monkeypatch, rows=9)
    shutil.copy(other_view / "export-manifest.json", view / "export-manifest.json")
    with pytest.raises(ValueError, match="TRAINING_VIEW_DATASET_MISMATCH"):
        load_training_view(view)
    (view / "training-samples.json").unlink()
    with pytest.raises(ValueError, match="TRAINING_VIEW_INVALID"):
        load_training_view(view)


def _sample(split, states, actions=None):
    rows = [{"observation": {"sim_time_s": 0.0, "state": list(state), "head_png": "h", "wrist_png": "w"},
             "action": list(actions[index] if actions else state[:6])} for index, state in enumerate(states)]
    return {"scene_id": f"s-{split}-{len(states)}", "split": split, "rows": rows}


def test_normalisation_statistics_use_the_train_split_only_and_floor_the_degenerate_dimensions():
    from so101_demo.adapters.act.lerobot import compute_statistics
    train = _sample("train", [[0.0, 2.0, 5, 5, 5, 5, 0.0, 1.0], [2.0, 4.0, 5, 5, 5, 5, 0.0, 1.0]])
    other = [_sample("validation", [[100.0] * 8]), _sample("offline_test", [[-100.0] * 8]), _sample(None, [[7.0] * 8])]
    stats = compute_statistics([train, *other], std_floor=0.01)
    assert stats["split"] == "train" and stats["sample_count"] == 2 and stats["episode_count"] == 1
    assert stats["state_mean"][:2] == [1.0, 3.0] and stats["state_std"][:2] == [1.0, 1.0]
    assert stats["state_std"][2:] == [0.01] * 6 and stats["floored_dims"]["state"] == [2, 3, 4, 5, 6, 7]
    assert stats["state_mean"][6:] == [0.0, 1.0]
    assert stats["action_mean"] == stats["state_mean"][:6] and stats["floored_dims"]["action"] == [2, 3, 4, 5]
    assert stats["std_floor"] == 0.01
    assert all(np.isfinite(stats[key]).all() for key in ("state_mean", "state_std", "action_mean", "action_std"))


def test_statistics_need_a_train_split():
    from so101_demo.adapters.act.lerobot import compute_statistics
    with pytest.raises(ValueError, match="TRAINING_NO_TRAIN_SPLIT"):
        compute_statistics([_sample("validation", [[1.0] * 8])], std_floor=0.01)
