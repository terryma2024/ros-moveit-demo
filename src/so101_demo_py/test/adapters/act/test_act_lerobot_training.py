"""Design 2026-10-10 section 3.3: the LeRobot 0.6.1 ACT trainer and the bundle loader. Torch-gated: runs in the training gate."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from paths import PACKAGE_ROOT

# A module-level `importorskip` would end the whole directory collection in the ordinary interpreter, so the gate is a marker.
pytestmark = pytest.mark.skipif(
    any(importlib.util.find_spec(name) is None for name in ("torch", "lerobot", "PIL", "numpy")),
    reason="the training interpreter owns torch and LeRobot")

if importlib.util.find_spec("torch") is not None:
    import torch

from act_training_fixture import synthetic_dataset  # noqa: E402

CONFIG = PACKAGE_ROOT / "config/act/training.yaml"
SPLITS = {"act-1": "train", "act-2": "train", "act-3": "validation"}


def _config(steps=3, batch_size=2):
    from so101_demo.act.training_config import load_training_config
    config = load_training_config(CONFIG)
    config["training"] = {**config["training"], "steps": steps, "batch_size": batch_size, "pretrained_backbone": None}
    return config


def _train(tmp_path, monkeypatch, *, steps=3, neck=(0.0, 1.0), name="bundle"):
    from so101_demo.act.training import train_act
    from so101_demo.adapters.act.lerobot import train_act_bundle
    dataset = synthetic_dataset(tmp_path, monkeypatch, splits=SPLITS, neck=neck)
    config = _config(steps=steps)

    def trainer(cfg, view, output):
        return train_act_bundle(cfg, view, output, requirements_sha256="a" * 64, device="cpu")
    outcome = train_act(config=config, requirements={"status": "RESOLVED"}, dataset=dataset,
                        owner={"device": "cuda", "run_root": str(tmp_path)}, output=tmp_path / name, trainer=trainer)
    return dataset, outcome, tmp_path / name


def test_a_tiny_cpu_training_run_leaves_a_loadable_hash_verified_bundle(tmp_path, monkeypatch):
    from so101_demo.act.bundle import load_bundle
    dataset, outcome, root = _train(tmp_path, monkeypatch)
    assert outcome["status"] == "COMPLETED"
    bundle = load_bundle(root / "bundle.json")                   # the closed document, policy path and digest verified
    assert bundle == outcome["bundle"]
    assert bundle["policy_path"] == "policy.safetensors"
    assert bundle["policy_sha256"] == hashlib.sha256((root / "policy.safetensors").read_bytes()).hexdigest()
    assert bundle["dataset_sha256"] == hashlib.sha256((dataset / "export-manifest.json").read_bytes()).hexdigest()
    assert bundle["model_source"] == {"name": "lerobot-act", "sha256": "a" * 64}
    assert bundle["action"] == {"chunk_size": 10, "execution_prefix": 1, "temporal_ensembling": False, "tail_padding_mask": True}
    normalization = bundle["normalization"]
    assert normalization["split"] == "train" and normalization["episode_count"] == 2          # validation is not in the statistics
    assert normalization["image_shape"] == [3, 48, 64]
    log = json.loads((root / "training-log.json").read_text())
    assert len(log["steps"]) == 3 and all(entry["loss"] == entry["loss"] for entry in log["steps"])


def test_build_policy_from_bundle_predicts_finite_six_wide_chunks(tmp_path, monkeypatch):
    import numpy as np

    from so101_demo.adapters.act.lerobot import build_policy_from_bundle, decode_observation, load_training_view
    from so101_demo.act.training import load_training_samples
    dataset, _, root = _train(tmp_path, monkeypatch)
    policy = build_policy_from_bundle(root, device="cpu")
    policy.reset()
    row = load_training_samples(dataset)[0]["rows"][2]
    observation = decode_observation(row["observation"], dataset)
    chunk = policy.infer(observation)
    assert len(chunk) == 10 and all(len(action) == 6 for action in chunk)
    assert np.isfinite(np.asarray(chunk)).all()
    assert all(isinstance(value, float) for action in chunk for value in action)


def test_build_policy_from_bundle_verifies_the_hashes(tmp_path, monkeypatch):
    from so101_demo.adapters.act.lerobot import build_policy_from_bundle
    _, _, root = _train(tmp_path, monkeypatch)
    weights = root / "policy.safetensors"
    weights.write_bytes(weights.read_bytes() + b"\x00")
    with pytest.raises(ValueError, match="BUNDLE_POLICY_DIGEST_MISMATCH"):
        build_policy_from_bundle(root, device="cpu")


def test_a_degenerate_std_dimension_stays_finite_end_to_end(tmp_path, monkeypatch):
    import numpy as np

    from so101_demo.adapters.act.lerobot import build_policy_from_bundle, decode_observation
    from so101_demo.act.bundle import load_bundle
    from so101_demo.act.training import load_training_samples
    dataset, _, root = _train(tmp_path, monkeypatch, neck=(0.0, 1.0))
    normalization = load_bundle(root / "bundle.json")["normalization"]
    assert normalization["floored_dims"]["state"] == [6, 7]                  # the fixed neck has zero spread
    assert normalization["state_std"][6] == normalization["state_std"][7] == normalization["std_floor"]
    assert np.isfinite(np.asarray(normalization["state_std"])).all() and min(normalization["state_std"]) > 0
    policy = build_policy_from_bundle(root, device="cpu")
    observation = decode_observation(load_training_samples(dataset)[0]["rows"][0]["observation"], dataset)
    observation["state"] = [*observation["state"][:6], 0.02, 0.9998]         # the neck moved slightly at run time
    chunk = policy.infer(observation)
    assert np.isfinite(np.asarray(chunk)).all()


def test_the_trainer_cycles_only_the_train_split(tmp_path, monkeypatch):
    from so101_demo.adapters.act import lerobot
    seen = {}
    real = lerobot._chunk_samples

    def spy(samples, *args, **kwargs):
        seen["scenes"] = [item["scene_id"] for item in samples]
        return real(samples, *args, **kwargs)
    monkeypatch.setattr(lerobot, "_chunk_samples", spy)
    _train(tmp_path, monkeypatch)
    assert seen["scenes"] == ["act-1", "act-2"]


def test_tail_padding_is_masked_and_never_borrows_another_episode():
    import numpy as np

    from so101_demo.adapters.act.lerobot import _action_window, _chunk_samples
    rows = [{"observation": {"state": [float(index)] * 8}, "action": [10.0 * index] * 6} for index in range(4)]
    other = [{"observation": {"state": [99.0] * 8}, "action": [990.0] * 6} for _ in range(4)]
    items = _chunk_samples([{"scene_id": "a", "split": "train", "rows": rows}, {"scene_id": "b", "split": "train", "rows": other}])
    assert items == [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3)]
    actions = np.asarray([row["action"] for row in rows], dtype=np.float32)
    chunk, pad = _action_window(actions, 2, 3)               # rows 2, 3, then one padded slot
    assert pad.tolist() == [False, False, True]
    assert np.allclose(chunk[:2, 0], [20.0, 30.0]) and np.allclose(chunk[2], chunk[1])     # the pad repeats this episode's last action
    chunk, pad = _action_window(actions, 0, 3)
    assert pad.tolist() == [False, False, False] and np.allclose(chunk[:, 0], [0.0, 10.0, 20.0])


def test_loader_workers_do_not_need_a_short_temp_directory(tmp_path, monkeypatch):
    """The scratch rule puts TMPDIR deep under the evidence root. The default tensor sharing passes file descriptors over an AF_UNIX
    socket in a `pymp-*` directory there, whose path limit (107) is then exceeded and the DataLoader hangs; workers must not need it."""
    import multiprocessing.process
    import tempfile

    from so101_demo.act.training import train_act
    from so101_demo.adapters.act import lerobot
    from so101_demo.adapters.act.lerobot import train_act_bundle

    deep = tmp_path / ("d" * 60) / ("e" * 60) / "tmp"
    deep.mkdir(parents=True)
    monkeypatch.setenv("TMPDIR", str(deep))
    monkeypatch.setattr(tempfile, "tempdir", None)
    monkeypatch.delitem(multiprocessing.process.current_process()._config, "tempdir", raising=False)
    monkeypatch.setattr(lerobot, "_LOADER_TIMEOUT_S", 40)          # a dead worker raises instead of hanging the run
    assert len(str(deep)) + len("/pymp-00000000/listener-00000000") > 107
    dataset = synthetic_dataset(tmp_path, monkeypatch, splits=SPLITS)
    outcome = train_act(config=_config(steps=3), requirements={"status": "RESOLVED"}, dataset=dataset,
                        owner={"device": "cuda", "run_root": str(tmp_path)}, output=tmp_path / "bundle",
                        trainer=lambda cfg, view, out: train_act_bundle(cfg, view, out, requirements_sha256="a" * 64, device="cpu",
                                                                        num_workers=2))
    assert outcome["status"] == "COMPLETED"


def _fake_resnet18_weights(path, seed=0):
    """A real-shaped torchvision ResNet18 state dict (fc included, like the ImageNet file), randomly initialised, saved offline."""
    import torchvision
    torch.manual_seed(seed)
    torch.save(torchvision.models.resnet18().state_dict(), path)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _backbone_config(digest, steps=2):
    config = _config(steps=steps)
    config["training"]["pretrained_backbone"] = {"name": "ResNet18_Weights.IMAGENET1K_V1", "sha256": digest}
    return config


def test_the_pretrained_backbone_loads_offline_into_the_policy_and_the_bundle_records_it(tmp_path, monkeypatch):
    import socket
    import urllib.request

    from so101_demo.act.training import train_act
    from so101_demo.act.bundle import load_bundle
    from so101_demo.adapters.act import lerobot
    from so101_demo.adapters.act.lerobot import build_policy_from_bundle, train_act_bundle

    weights = tmp_path / "resnet18.pth"
    digest = _fake_resnet18_weights(weights)

    def no_network(*args, **kwargs):
        raise AssertionError("the loading path must be offline")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(torch.hub, "load_state_dict_from_url", no_network)
    loaded = {}
    real = lerobot._load_backbone

    def spy(policy, path, expected_sha256):
        real(policy, path, expected_sha256)
        loaded["conv1"] = policy.model.backbone.conv1.weight.detach().clone()
    monkeypatch.setattr(lerobot, "_load_backbone", spy)
    dataset = synthetic_dataset(tmp_path, monkeypatch, splits=SPLITS)
    train_act(config=_backbone_config(digest), requirements={"status": "RESOLVED"}, dataset=dataset,
              owner={"device": "cuda", "run_root": str(tmp_path)}, output=tmp_path / "bundle",
              trainer=lambda cfg, view, out: train_act_bundle(cfg, view, out, requirements_sha256="a" * 64, device="cpu",
                                                              backbone_weights=weights))
    expected = torch.load(weights, weights_only=True)["conv1.weight"]
    assert torch.equal(loaded["conv1"], expected)                        # the file's tensors, not a random init
    bundle = load_bundle(tmp_path / "bundle" / "bundle.json")
    assert bundle["normalization"]["pretrained_backbone"] == {"name": "ResNet18_Weights.IMAGENET1K_V1", "sha256": digest}
    # inference needs neither the weights file nor the network: the backbone lives inside policy.safetensors
    weights.unlink()
    assert build_policy_from_bundle(tmp_path / "bundle", device="cpu") is not None


def test_a_backbone_whose_bytes_do_not_match_the_pinned_hash_is_refused_at_load(tmp_path):
    from so101_demo.adapters.act.lerobot import _act_config, _load_backbone
    from lerobot.policies.act.modeling_act import ACTPolicy

    weights = tmp_path / "resnet18.pth"
    digest = _fake_resnet18_weights(weights)
    policy = ACTPolicy(_act_config(10, 1, [3, 32, 32], "cpu"))
    with pytest.raises(ValueError, match="TRAINING_BACKBONE_HASH_MISMATCH"):
        _load_backbone(policy, weights, "0" * 64)
    _load_backbone(policy, weights, digest)
    assert _act_config(10, 1, [3, 32, 32], "cpu").pretrained_backbone_weights is None       # LeRobot never downloads
