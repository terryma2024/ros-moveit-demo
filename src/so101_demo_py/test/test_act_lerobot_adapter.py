"""The LeRobot-backed adapter: the loader `load_policy` injects and the trainer `train_act` injects.

The loader must resolve the policy inside the bundle, refuse a hash mismatch, and expose exactly the
interface the runner requires (`infer(observation)`, `reset()`), where an observation carries the four keys
the runner builds and an action chunk comes back as tuples of floats. The trainer must leave a bundle that
carries the frozen action semantics and a train-only normalization.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.bundle import BUNDLE_KEYS, load_policy, require_policy_interface


def _policy_bytes() -> bytes:
    return b"fake-lerobot-policy-weights"


def _bundle(root: Path) -> dict:
    policy = root / "policy.safetensors"
    policy.write_bytes(_policy_bytes())
    return {"schema_version": 1, "kind": "act_bundle",
            "model_source": {"name": "lerobot-act", "sha256": "e" * 64},
            "dataset_sha256": "a" * 64, "config_sha256": "b" * 64,
            "policy_path": "policy.safetensors",
            "policy_sha256": hashlib.sha256(_policy_bytes()).hexdigest(),
            "normalization": {"split": "train", "state_mean": [0.0] * 6, "state_std": [1.0] * 6},
            "action": {"chunk_size": 16, "execution_prefix": 8, "temporal_ensembling": False,
                       "tail_padding_mask": True}}


class _FakePolicy:
    def __init__(self):
        self.batches = []
        self.resets = 0

    def predict_action_chunk(self, batch):
        self.batches.append(batch)
        return [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6]] * 16

    def reset(self):
        self.resets += 1


def _observation():
    return {"sim_time_s": 1.5, "state": [0.0] * 6,
            "head": [[[10, 20, 30]] * 2] * 2, "wrist": [[[40, 50, 60]] * 2] * 2}


def test_loader_verifies_the_policy_hash_and_refuses_a_mismatch(tmp_path):
    from so101_demo.adapters.act.lerobot import policy_loader

    bundle = _bundle(tmp_path)
    policy = _FakePolicy()
    loader = policy_loader(tmp_path, factory=lambda path: policy)
    model = require_policy_interface(loader(bundle))            # the loader load_policy would inject
    assert callable(model.infer) and callable(model.reset)

    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle))
    model = load_policy(bundle_path, loader=policy_loader(tmp_path, factory=lambda path: policy))
    assert callable(model.infer)

    broken = {**bundle, "policy_sha256": "c" * 64}
    with pytest.raises(ValueError, match="POLICY_HASH_MISMATCH"):
        policy_loader(tmp_path, factory=lambda path: policy)(broken)


def test_infer_maps_the_runner_observation_and_returns_action_tuples(tmp_path):
    # the batch conversion is a torch path, so it is exercised in the training interpreter and skipped here
    pytest.importorskip("torch", reason="the training interpreter owns the tensor path")
    from so101_demo.adapters.act.lerobot import policy_loader

    policy = _FakePolicy()
    model = policy_loader(tmp_path, factory=lambda path: policy)(_bundle(tmp_path))
    chunk = model.infer(_observation())
    assert isinstance(chunk, tuple) and len(chunk) == 16
    assert all(isinstance(action, tuple) and len(action) == 6 for action in chunk)
    batch = policy.batches[-1]
    assert set(batch) == {"observation.state", "observation.images.head", "observation.images.wrist"}
    assert batch["observation.state"].shape[-1] == 6
    assert batch["observation.images.head"].shape[-3:] == (3, 2, 2)
    model.reset()
    assert policy.resets == 1


def test_trainer_leaves_a_bundle_with_frozen_action_semantics(tmp_path):
    from so101_demo.adapters.act.lerobot import train_with_lerobot

    captured = {}

    def fake_train(config, dataset, target):
        captured["config"] = config
        captured["dataset"] = dataset
        (Path(target) / "policy.safetensors").write_bytes(_policy_bytes())
        return None

    target = tmp_path / "bundle"
    target.mkdir()
    document = train_with_lerobot({"chunk_size": 16, "execution_prefix": 8, "temporal_ensembling": False,
                                   "tail_padding_mask": True},
                                  tmp_path / "dataset", target, requirement_sha256="d" * 64,
                                  train=fake_train)
    assert set(document) == set(BUNDLE_KEYS)
    assert document["action"] == {"chunk_size": 16, "execution_prefix": 8, "temporal_ensembling": False,
                                  "tail_padding_mask": True}
    assert document["normalization"]["split"] == "train"
    assert document["policy_path"] == "policy.safetensors"
    assert document["policy_sha256"] == hashlib.sha256(_policy_bytes()).hexdigest()
    assert captured["dataset"] == tmp_path / "dataset"


def test_trainer_refuses_a_missing_training_entry_point(tmp_path):
    from so101_demo.adapters.act.lerobot import train_with_lerobot

    with pytest.raises(ValueError, match="LEROBOT_TRAIN_REQUIRED"):
        train_with_lerobot({"chunk_size": 16, "execution_prefix": 8, "temporal_ensembling": False,
                            "tail_padding_mask": True}, tmp_path / "dataset", tmp_path,
                           requirement_sha256="d" * 64, train=None)
