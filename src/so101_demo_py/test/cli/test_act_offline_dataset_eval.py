"""Design follow-up 3: `act_offline_evaluate` reads the offline_test split of an exported dataset.

The frames go through the same verified-dataset / D8 decode path as training (digests re-verified, runtime observation keys), and the
metrics are the masked per-joint MAE / RMSE the evaluation already defines."""
import hashlib
import importlib.util
import json

import pytest

_HAVE = all(importlib.util.find_spec(name) is not None for name in ("numpy", "PIL"))
pytestmark = pytest.mark.skipif(not _HAVE, reason="the decode path needs numpy and pillow")
if _HAVE:
    import numpy as np

from act_training_fixture import synthetic_dataset, write_freeze  # noqa: E402


class _Zero:
    def __init__(self):
        self.resets, self.observations = 0, []

    def reset(self):
        self.resets += 1

    def infer(self, observation):
        self.observations.append(observation)
        return ((0.0,) * 6,) * 10


def _setup(tmp_path, monkeypatch, *, offline=10, rows=5):
    splits = {"t-0": "train", "t-1": "train", **{f"o-{index}": "offline_test" for index in range(offline)}}
    dataset = synthetic_dataset(tmp_path, monkeypatch, splits=splits, rows=rows, size=(8, 6))
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({"schema_version": 1, "kind": "act_bundle", "model_source": {"name": "m", "sha256": "a" * 64},
                                  "dataset_sha256": hashlib.sha256((dataset / "export-manifest.json").read_bytes()).hexdigest(),
                                  "config_sha256": "c" * 64, "policy_path": "policy.bin",
                                  "policy_sha256": hashlib.sha256(b"m").hexdigest(),
                                  "normalization": {"split": "train"},
                                  "action": {"chunk_size": 10, "execution_prefix": 1, "temporal_ensembling": False,
                                             "tail_padding_mask": True}}))
    (tmp_path / "policy.bin").write_bytes(b"m")
    freeze = write_freeze(tmp_path / "freeze", bundle, dataset / "export-manifest.json")
    return dataset, bundle, freeze


def test_the_evaluation_runs_end_to_end_on_the_offline_test_split_of_an_export(tmp_path, monkeypatch, capsys):
    from so101_demo.act.training import load_training_samples
    from so101_demo.cli.act_offline_evaluate import main
    dataset, bundle, freeze = _setup(tmp_path, monkeypatch)
    policy = _Zero()
    report = tmp_path / "report.json"
    assert main(["--manifest", str(dataset / "export-manifest.json"), "--bundle", str(bundle), "--freeze", str(freeze),
                 "--output", str(report)], policy_loader=lambda _bundle: policy) == 0
    document = json.loads(report.read_text())
    offline = [s for s in load_training_samples(dataset) if s["split"] == "offline_test"]
    assert document["episode_count"] == 10 and document["valid_targets"] == 50 and document["byte_weighted"] is False
    assert [item["episode_id"] for item in document["per_episode"]] == [s["scene_id"] for s in offline]
    actions = np.asarray([row["action"] for s in offline for row in s["rows"]])
    assert np.allclose(document["mean_mae_rad"], np.abs(actions).mean(axis=0), atol=1e-9)    # a zero policy: |action| per joint
    assert policy.resets == 10 and len(policy.observations) == 50                             # one reset per episode, one infer per row
    observation = policy.observations[0]
    assert set(observation) == {"sim_time_s", "state", "head", "wrist"}                       # the runtime keys, not head_png / wrist_png
    assert observation["head"].dtype == np.uint8 and observation["head"].shape == (6, 8, 3)
    assert len(observation["state"]) == 8
    assert json.loads(capsys.readouterr().out)["episode_count"] == 10


def test_a_tampered_frame_refuses_the_evaluation_before_any_inference(tmp_path, monkeypatch):
    from so101_demo.cli.act_offline_evaluate import main
    dataset, bundle, freeze = _setup(tmp_path, monkeypatch)
    frame = dataset / "episodes" / "o-3" / "frames" / "000002-head.png"
    frame.write_bytes(frame.read_bytes()[:-1] + b"\x00")
    policy = _Zero()
    with pytest.raises(ValueError, match="TRAINING_EPISODE_FRAME_DIGEST_MISMATCH"):
        main(["--manifest", str(dataset / "export-manifest.json"), "--bundle", str(bundle), "--freeze", str(freeze),
              "--output", str(tmp_path / "report.json")], policy_loader=lambda _bundle: policy)
    assert policy.observations == [] and not (tmp_path / "report.json").exists()


def test_too_few_offline_test_episodes_in_an_export_still_refuses(tmp_path, monkeypatch):
    from so101_demo.cli.act_offline_evaluate import main
    dataset, bundle, freeze = _setup(tmp_path, monkeypatch, offline=9)
    with pytest.raises(ValueError, match="OFFLINE_TEST_EPISODES_INSUFFICIENT"):
        main(["--manifest", str(dataset / "export-manifest.json"), "--bundle", str(bundle), "--freeze", str(freeze),
              "--output", str(tmp_path / "report.json")], policy_loader=lambda _bundle: _Zero())
