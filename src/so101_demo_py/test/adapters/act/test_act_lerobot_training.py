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


def _config(steps=3, batch_size=2, **training):
    from so101_demo.act.training_config import load_training_config
    config = load_training_config(CONFIG)
    # the CPU tests load in-process (num_workers 0) unless a test asks for workers
    config["training"] = {**config["training"], "steps": steps, "batch_size": batch_size, "pretrained_backbone": None,
                          "num_workers": 0, **training}
    return config


def _train(tmp_path, monkeypatch, *, steps=3, neck=(0.0, 1.0), name="bundle", **training):
    from so101_demo.act.training import train_act
    from so101_demo.adapters.act.lerobot import train_act_bundle
    dataset = synthetic_dataset(tmp_path, monkeypatch, splits=SPLITS, neck=neck)
    config = _config(steps=steps, **training)

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
    # the bundle declares the cameras and state width it was trained with (read back by the policy loader and the rollout executor)
    assert normalization["observation"] == {"cameras": ["head", "wrist"], "state_dim": 8}
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
        seen.setdefault("calls", []).append([item["scene_id"] for item in samples])
        return real(samples, *args, **kwargs)
    monkeypatch.setattr(lerobot, "_chunk_samples", spy)
    _train(tmp_path, monkeypatch)
    # the training index is the first call and holds the train episodes only; the validation episodes are indexed separately for evaluation
    assert seen["calls"][0] == ["act-1", "act-2"] and seen["calls"][1:] == [["act-3"]]


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


def _metrics(root):
    return [json.loads(line) for line in (root / "metrics.jsonl").read_text().splitlines()]


def test_the_loop_writes_progress_and_validation_records_at_the_configured_intervals(tmp_path, monkeypatch, capsys):
    from so101_demo.act.bundle import load_bundle
    _, _, root = _train(tmp_path, monkeypatch, steps=5, log_interval_steps=2, validation_interval_steps=4, validation_samples=3)
    records = _metrics(root)
    train = [row for row in records if row["kind"] == "train"]
    assert [row["step"] for row in train] == [2, 4, 5]               # every 2 steps and the last, a partial window included
    assert [row["window_steps"] for row in train] == [2, 2, 1]
    for row in train:
        for key in ("loss", "l1_loss", "kld_loss", "learning_rate", "samples_per_s", "elapsed_s", "eta_s",
                    "wait_s_per_step", "compute_s_per_step", "wait_share"):
            assert row[key] == row[key] and row[key] >= 0.0, key
        assert 0.0 <= row["wait_share"] <= 1.0
    assert train[-1]["eta_s"] == 0.0 and train[0]["learning_rate"] == 1.0e-5
    log = json.loads((root / "training-log.json").read_text())
    window_mean = sum(entry["loss"] for entry in log["steps"][:2]) / 2
    assert train[0]["loss"] == pytest.approx(window_mean)
    validation = [row for row in records if row["kind"] == "validation"]
    assert [row["step"] for row in validation] == [4, 5]             # the interval and the last step
    assert all(row["samples"] == 3 and row["loss"] == row["loss"] for row in validation)
    assert log["validations"] == validation and log["last_validation"] == validation[-1]
    assert log["metrics_file"] == "metrics.jsonl" and log["num_workers"] == 0 and len(log["steps"]) == 5
    assert load_bundle(root / "bundle.json")["normalization"]["last_validation"] == validation[-1]
    out = capsys.readouterr().out
    assert "step=2/5" in out and "step=5/5" in out and "validation step=4" in out


def test_validation_does_not_change_what_is_trained(tmp_path, monkeypatch):
    """The training losses are identical with validation running every step and with it effectively never running."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _, _, frequent = _train(tmp_path / "a", monkeypatch, steps=4, validation_interval_steps=1, validation_samples=4, name="b")
    _, _, rare = _train(tmp_path / "b", monkeypatch, steps=4, validation_interval_steps=10 ** 6, validation_samples=4, name="b")
    first = [entry["loss"] for entry in json.loads((frequent / "training-log.json").read_text())["steps"]]
    second = [entry["loss"] for entry in json.loads((rare / "training-log.json").read_text())["steps"]]
    assert first == second


def test_the_validation_subset_is_fixed_and_drawn_only_from_validation_episodes(tmp_path, monkeypatch):
    _, _, root = _train(tmp_path, monkeypatch, steps=2, validation_interval_steps=1, validation_samples=2)
    validation = [row for row in _metrics(root) if row["kind"] == "validation"]
    assert [row["step"] for row in validation] == [1, 2] and all(row["samples"] == 2 for row in validation)


def test_num_workers_comes_from_the_config_and_an_argument_wins(tmp_path, monkeypatch):
    from so101_demo.act.training import train_act
    from so101_demo.adapters.act.lerobot import train_act_bundle
    dataset = synthetic_dataset(tmp_path, monkeypatch, splits=SPLITS)
    seen = []
    real = torch.utils.data.DataLoader

    def spy(*args, **kwargs):
        seen.append(kwargs["num_workers"])
        return real(*args, **kwargs)
    monkeypatch.setattr(torch.utils.data, "DataLoader", spy)
    for name, config_workers, argument, expected in (("a", 1, None, 1), ("b", 1, 0, 0)):
        outcome = train_act(config=_config(steps=1, num_workers=config_workers), requirements={"status": "RESOLVED"}, dataset=dataset,
                            owner={"device": "cuda", "run_root": str(tmp_path)}, output=tmp_path / name,
                            trainer=lambda cfg, view, out, argument=argument: train_act_bundle(
                                cfg, view, out, requirements_sha256="a" * 64, device="cpu", num_workers=argument))
        assert outcome["status"] == "COMPLETED"
        log = json.loads((tmp_path / name / "training-log.json").read_text())
        assert log["num_workers"] == expected
    assert seen[0] == 1 and seen[2] == 0                              # training loaders; the validation loaders follow each


# ---- O7: leading-idle sample selection and the separate backbone learning rate ---------------------------------------------------------

def _rows(gaps):
    """Rows whose arm action sits ``gaps[i]`` (a six-vector or a scalar for joint 0) away from a zero state."""
    rows = []
    for gap in gaps:
        action = list(gap) if isinstance(gap, (list, tuple)) else [gap, 0.0, 0.0, 0.0, 0.0, 0.0]
        rows.append({"observation": {"state": [0.0] * 8}, "action": action})
    return rows


SELECTION = {"trim_leading_idle": True, "idle_threshold_rad": 0.005, "lead_in_rows": 2}


def test_first_motion_is_found_in_raw_units_over_the_six_arm_joints_only():
    from so101_demo.adapters.act.lerobot import first_motion_row
    rows = _rows([0.0, 0.005, 0.004, 0.0051, 1.0])
    assert first_motion_row(rows, 0.005) == 3                       # strictly greater than the threshold
    rows = _rows([0.0, 0.0, [0.0, 0.0, 0.0, 0.0, 0.0, -0.02]])      # the gripper (joint 5) counts, the sign does not
    assert first_motion_row(rows, 0.005) == 2
    rows = _rows([0.0, 0.0])
    rows[1]["observation"]["state"][6] = 5.0                        # the neck sin/cos dimensions are not arm joints
    assert first_motion_row(rows, 0.005) is None
    rows = _rows([0.0, 0.0])
    rows[1]["observation"]["state"][0] = -0.01                      # a state offset counts as action - state
    assert first_motion_row(rows, 0.005) == 1


def test_the_selection_drops_start_rows_before_the_lead_in_and_keeps_never_moving_episodes_whole():
    from so101_demo.adapters.act.lerobot import _chunk_samples, selection_summary
    moving = {"scene_id": "m", "split": "train", "rows": _rows([0, 0, 0, 0, 0, 0.1, 0.2, 0.3])}       # r* = 5, first start 3
    early = {"scene_id": "e", "split": "train", "rows": _rows([0, 0.1, 0.2])}                          # r* = 1, lead-in reaches row 0
    still = {"scene_id": "s", "split": "train", "rows": _rows([0, 0, 0, 0])}                           # never moves
    items = _chunk_samples([moving, early, still], SELECTION)
    assert items == ([(0, row) for row in range(3, 8)] + [(1, row) for row in range(3)] + [(2, row) for row in range(4)])
    summary = selection_summary([moving, early, still], SELECTION)
    assert (summary["samples_before"], summary["samples_after"], summary["never_moving_episodes"]) == (15, 12, 1)
    assert (summary["first_motion_row_min"], summary["first_motion_row_median"], summary["first_motion_row_max"]) == (1, 3.0, 5)
    assert [entry["first_motion_row"] for entry in summary["per_episode"]] == [5, 1, None]
    assert [entry["trimmed"] for entry in summary["per_episode"]] == [3, 0, 0]


def test_sampling_is_identical_when_the_selection_is_absent_or_disabled():
    from so101_demo.adapters.act.lerobot import _chunk_samples
    samples = [{"scene_id": "m", "split": "train", "rows": _rows([0, 0, 0.1, 0.2])}]
    plain = _chunk_samples(samples)
    assert plain == [(0, 0), (0, 1), (0, 2), (0, 3)]
    assert _chunk_samples(samples, None) == plain
    assert _chunk_samples(samples, {**SELECTION, "trim_leading_idle": False}) == plain


def test_the_trainer_applies_the_selection_to_train_and_validation_and_records_it(tmp_path, monkeypatch):
    from so101_demo.adapters.act import lerobot
    monkeypatch.setattr(lerobot, "first_motion_row", lambda rows, threshold: 3)         # every fixture episode first moves at row 3
    _, _, root = _train(tmp_path, monkeypatch, steps=2, validation_interval_steps=1, validation_samples=100,
                        sample_selection={"trim_leading_idle": True, "idle_threshold_rad": 0.005, "lead_in_rows": 1})
    log = json.loads((root / "training-log.json").read_text())
    assert log["train_samples"] == 2 * (12 - 2)                                          # starts from row 2 on, 12 rows each
    train, validation = log["sample_selection"]["train"], log["sample_selection"]["validation"]
    assert (train["samples_before"], train["samples_after"], train["first_motion_row_median"]) == (24, 20, 3)
    assert (validation["samples_before"], validation["samples_after"]) == (12, 10)
    assert [entry["first_start_row"] for entry in train["per_episode"]] == [2, 2]
    assert all(row["samples"] == 10 for row in _metrics(root) if row["kind"] == "validation")      # the subset follows the selection
    selection_records = [row for row in _metrics(root) if row["kind"] == "sample_selection"]
    assert [row["split"] for row in selection_records] == ["train", "validation"]


def test_without_a_selection_the_log_records_it_disabled_and_the_sample_count_is_unchanged(tmp_path, monkeypatch):
    _, _, root = _train(tmp_path, monkeypatch, steps=1)
    log = json.loads((root / "training-log.json").read_text())
    assert log["train_samples"] == 24 and log["sample_selection"]["train"] == {"enabled": False, "samples_before": 24, "samples_after": 24}
    assert log["learning_rate_backbone"] == log["learning_rate"]
    assert not [row for row in _metrics(root) if row["kind"] == "sample_selection"]


def test_the_backbone_learning_rate_defaults_to_the_learning_rate_and_can_differ():
    from so101_demo.adapters.act.lerobot import _act_config
    shape = (3, 48, 64)
    assert _act_config(10, 1, shape, "cpu", learning_rate=1e-4).optimizer_lr_backbone == 1e-4
    config = _act_config(10, 1, shape, "cpu", learning_rate=1e-4, head_learning_rate=1e-5)
    assert (config.optimizer_lr, config.optimizer_lr_backbone) == (1e-4, 1e-5)


def test_a_training_run_records_the_backbone_rate(tmp_path, monkeypatch):
    _, _, root = _train(tmp_path, monkeypatch, steps=1, learning_rate=1e-3, learning_rate_backbone=1e-4)
    log = json.loads((root / "training-log.json").read_text())
    assert (log["learning_rate"], log["learning_rate_backbone"]) == (1e-3, 1e-4)


def _side_wrist_dataset(tmp_path, *, rows=12, size=(64, 48)):
    """An exported dataset of the side+wrist rig (6-wide state, `side_png` / `wrist_png`), written as the exporter writes it."""
    import math

    from act_training_fixture import smooth_png
    root = tmp_path / "side-wrist-dataset"
    episodes, counter = [], 0
    for index, (scene, split) in enumerate(SPLITS.items()):
        frames, content_rows = {}, []
        for row in range(rows):
            observation = {"sim_time_s": round(row * 0.1, 6),
                           "state": [0.4 * math.sin(0.35 * row + 0.7 * index + joint) for joint in range(6)]}
            for camera in ("side", "wrist"):
                counter += 1
                relative = f"episodes/{scene}/frames/{row:06d}-{camera}.png"
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                payload = smooth_png(size[0], size[1], counter)
                (root / relative).write_bytes(payload)
                frames[relative] = hashlib.sha256(payload).hexdigest()
                observation[f"{camera}_png"] = relative
            content_rows.append({"observation": observation, "action": [value + 0.05 for value in observation["state"]]})
        payload = (json.dumps({"frames": rows, "rows": content_rows}, sort_keys=True, indent=2) + "\n").encode()
        (root / "episodes" / f"{scene}.json").write_bytes(payload)
        episodes.append({"scene_id": scene, "split": split, "content_sha256": hashlib.sha256(payload).hexdigest(),
                         "frames": dict(sorted(frames.items()))})
    (root / "export-manifest.json").write_text(json.dumps(
        {"schema_version": 1, "kind": "act_dataset_export", "scene_count": len(episodes), "source_manifest_sha256": "a" * 64,
         "campaign_index_sha256": "b" * 64, "episodes": episodes}, sort_keys=True, indent=2) + "\n")
    return root


def test_a_side_wrist_dataset_trains_a_bundle_that_declares_its_cameras_and_six_wide_state(tmp_path):
    """The trainer reads the cameras, the frame keys, the state width and the preprocessing hash from the config's rig."""
    import numpy as np

    from so101_demo.act.bundle import load_bundle
    from so101_demo.act.rig_profile import SIDE_WRIST_RIG
    from so101_demo.act.training import load_training_samples, train_act
    from so101_demo.adapters.act.lerobot import (
        build_policy_from_bundle, decode_observation, preprocessing_sha256, train_act_bundle)
    dataset = _side_wrist_dataset(tmp_path)
    config = _config(steps=2)
    config["observation"] = {"cameras": ["side", "wrist"], "state_dim": 6, "action_dim": 6}
    with pytest.raises(ValueError, match="TRAINING_PREPROCESSING_DRIFT"):          # the config still freezes the head+wrist hash
        train_act_bundle(config, dataset, tmp_path / "refused", requirements_sha256="a" * 64, device="cpu")
    config["frozen"]["preprocessing_sha256"] = preprocessing_sha256(SIDE_WRIST_RIG)

    def trainer(cfg, view, output):
        return train_act_bundle(cfg, view, output, requirements_sha256="a" * 64, device="cpu")
    outcome = train_act(config=config, requirements={"status": "RESOLVED"}, dataset=dataset,
                        owner={"device": "cuda", "run_root": str(tmp_path)}, output=tmp_path / "bundle", trainer=trainer)
    assert outcome["status"] == "COMPLETED"
    bundle = load_bundle(tmp_path / "bundle" / "bundle.json")
    normalization = bundle["normalization"]
    assert normalization["observation"] == {"cameras": ["side", "wrist"], "state_dim": 6}
    assert len(normalization["state_mean"]) == 6 and normalization["floored_dims"]["state"] == []
    policy = build_policy_from_bundle(tmp_path / "bundle", device="cpu")
    policy.reset()
    observation = decode_observation(load_training_samples(dataset)[0]["rows"][2]["observation"], dataset)
    assert set(observation) == {"sim_time_s", "state", "side", "wrist"} and len(observation["state"]) == 6
    chunk = policy.infer(observation)
    assert len(chunk) == 10 and all(len(action) == 6 for action in chunk) and np.isfinite(np.asarray(chunk)).all()


def test_prefetched_yields_every_batch_in_order():
    from so101_demo.adapters.act.lerobot import _prefetched
    assert list(_prefetched(iter(range(50)), depth=2)) == list(range(50))
    assert list(_prefetched(iter([]), depth=2)) == []


def test_prefetched_reads_ahead_of_the_consumer():
    import time
    from so101_demo.adapters.act.lerobot import _prefetched
    pulled = []

    def source():
        for value in range(10):
            pulled.append(value)
            yield value

    batches = _prefetched(source(), depth=2)
    assert next(batches) == 0
    deadline = time.monotonic() + 5
    while len(pulled) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(pulled) >= 3                         # the batch handed out plus the ones waiting in the buffer
    batches.close()


def test_prefetched_reraises_the_loader_error_after_the_batches_before_it():
    from so101_demo.adapters.act.lerobot import _prefetched

    def source():
        yield 1
        yield 2
        raise RuntimeError("DATALOADER_TIMEOUT")

    batches = _prefetched(source(), depth=2)
    assert [next(batches), next(batches)] == [1, 2]
    with pytest.raises(RuntimeError, match="DATALOADER_TIMEOUT"):
        next(batches)


def test_prefetched_stops_its_thread_when_the_consumer_leaves_early():
    import threading
    import time
    from so101_demo.adapters.act.lerobot import _prefetched
    before = threading.active_count()

    def endless():
        while True:
            yield 0

    batches = _prefetched(endless(), depth=2)
    next(batches)
    batches.close()
    deadline = time.monotonic() + 5
    while threading.active_count() > before and time.monotonic() < deadline:
        time.sleep(0.05)
    assert threading.active_count() == before


def _record_module_compile(monkeypatch):
    calls = []

    def compile_stub(self, *args, **kwargs):
        calls.append(type(self).__name__)

    monkeypatch.setattr(torch.nn.Module, "compile", compile_stub)
    return calls


def test_torch_compile_is_off_unless_the_config_asks_for_it(tmp_path, monkeypatch):
    calls = _record_module_compile(monkeypatch)
    _train(tmp_path, monkeypatch)
    assert calls == []


def test_torch_compile_compiles_the_act_model_in_place_and_the_bundle_still_loads(tmp_path, monkeypatch):
    from so101_demo.act.bundle import load_bundle
    calls = _record_module_compile(monkeypatch)
    _, outcome, root = _train(tmp_path, monkeypatch, compile=True)
    assert calls == ["ACT"]                                  # the inner model, once; not the policy wrapper
    assert outcome["status"] == "COMPLETED"
    assert load_bundle(root / "bundle.json") == outcome["bundle"]
    from safetensors import safe_open
    with safe_open(str(root / "policy.safetensors"), "pt") as stream:
        assert not [key for key in stream.keys() if "_orig_mod" in key]     # in-place compile leaves the state_dict keys alone


# ---- interior idle trim, cudnn.benchmark and channels_last ---------------------------------------------------------------------------

INTERIOR = {"trim_leading_idle": True, "idle_threshold_rad": 0.005, "lead_in_rows": 2, "trim_interior_idle": True, "keep_tail_rows": 2}


def test_the_interior_trim_drops_start_rows_with_a_static_next_chunk_but_keeps_the_tail():
    from so101_demo.adapters.act.lerobot import _chunk_samples, selection_summary
    # r* = 5 so the leading trim starts at row 3; rows 7..13 have a static chunk; the last two rows (12, 13) are the kept tail
    episode = {"scene_id": "m", "split": "train", "rows": _rows([0, 0, 0, 0, 0, 0.1, 0.1, 0, 0, 0, 0, 0, 0, 0])}
    assert _chunk_samples([episode], INTERIOR, 3) == [(0, row) for row in (3, 4, 5, 6, 12, 13)]
    summary = selection_summary([episode], INTERIOR, 3)
    assert (summary["samples_before"], summary["leading_trimmed_rows"], summary["interior_trimmed_rows"], summary["samples_after"]) == (14, 3, 5, 6)
    assert [(entry["trimmed"], entry["interior_trimmed"]) for entry in summary["per_episode"]] == [(3, 5)]
    assert summary["keep_tail_rows"] == 2 and summary["trim_interior_idle"] is True


def test_the_interior_trim_threshold_is_strict_and_looks_at_every_action_of_the_chunk_and_all_six_joints():
    from so101_demo.adapters.act.lerobot import _chunk_samples
    selection = {**INTERIOR, "lead_in_rows": 0, "keep_tail_rows": 0}
    # moves at row 0 (0.1); then a deviation of exactly the threshold (kept: not below it) and one just under it (dropped)
    at_threshold = {"scene_id": "a", "split": "train", "rows": _rows([0.1, 0, 0, 0, 0.005, 0, 0, 0, 0])}
    assert _chunk_samples([at_threshold], selection, 2) == [(0, row) for row in (0, 3, 4)]       # row 3 reaches 0.005 at k=1; row 4 starts on it
    just_under = {"scene_id": "b", "split": "train", "rows": _rows([0.1, 0, 0, 0, 0.0049, 0, 0, 0, 0])}
    assert _chunk_samples([just_under], selection, 2) == [(0, 0)]
    other_joint = {"scene_id": "c", "split": "train", "rows": _rows([0.1, 0, 0, [0, 0, 0, 0, 0, -0.02], 0, 0, 0])}
    assert _chunk_samples([other_joint], selection, 2) == [(0, row) for row in (0, 2, 3)]        # the gripper counts, the sign does not


def test_the_interior_trim_uses_the_shorter_chunk_at_the_end_of_the_episode():
    from so101_demo.adapters.act.lerobot import _chunk_samples
    selection = {**INTERIOR, "lead_in_rows": 0, "keep_tail_rows": 0}
    episode = {"scene_id": "e", "split": "train", "rows": _rows([0.1, 0, 0, 0, 0, 0.1])}
    # chunk 3: row 3 sees rows 3..5 (the last action moves) so it is kept; row 4 sees 4..5 and row 5 sees 5; row 2 sees 2..4 (static)
    assert _chunk_samples([episode], selection, 3) == [(0, row) for row in (0, 3, 4, 5)]
    short = {"scene_id": "s", "split": "train", "rows": _rows([0.1, 0, 0])}
    assert _chunk_samples([short], {**selection, "keep_tail_rows": 50}, 3) == [(0, 0), (0, 1), (0, 2)]      # a tail longer than the episode keeps it whole


def test_the_interior_trim_needs_the_chunk_size_and_keeps_a_never_moving_episode_whole():
    from so101_demo.adapters.act.lerobot import _chunk_samples
    still = {"scene_id": "s", "split": "train", "rows": _rows([0, 0, 0, 0])}
    assert _chunk_samples([still], INTERIOR, 3) == [(0, row) for row in range(4)]
    moving = {"scene_id": "m", "split": "train", "rows": _rows([0, 0.1, 0, 0])}
    with pytest.raises(ValueError, match="SAMPLE_SELECTION_CHUNK_SIZE_MISSING"):
        _chunk_samples([moving], INTERIOR)


def test_the_leading_only_selection_is_unchanged_by_the_interior_code():
    from so101_demo.adapters.act.lerobot import _chunk_samples, selection_summary
    episode = {"scene_id": "m", "split": "train", "rows": _rows([0, 0, 0, 0, 0, 0.1, 0.2, 0.3])}
    assert _chunk_samples([episode], SELECTION) == _chunk_samples([episode], SELECTION, 10) == [(0, row) for row in range(3, 8)]
    summary = selection_summary([episode], SELECTION)
    assert "trim_interior_idle" not in summary and "interior_trimmed" not in summary["per_episode"][0]


def test_the_trainer_applies_the_interior_trim_to_train_and_validation(tmp_path, monkeypatch):
    from so101_demo.adapters.act import lerobot
    monkeypatch.setattr(lerobot, "first_motion_row", lambda rows, threshold: 3)
    seen = []

    def all_static(rows, first, chunk_size, threshold):
        seen.append(chunk_size)
        return [True] * (len(rows) - first)
    monkeypatch.setattr(lerobot, "_static_chunk_rows", all_static)
    _, _, root = _train(tmp_path, monkeypatch, steps=2, validation_interval_steps=1, validation_samples=100,
                        sample_selection={**INTERIOR, "lead_in_rows": 1, "keep_tail_rows": 4})
    log = json.loads((root / "training-log.json").read_text())
    assert set(seen) == {10}                                                              # the config's chunk size
    assert log["train_samples"] == 2 * 4                                                  # 12 rows each; only the 4 tail rows stay
    train, validation = log["sample_selection"]["train"], log["sample_selection"]["validation"]
    assert (train["leading_trimmed_rows"], train["interior_trimmed_rows"], train["samples_after"]) == (4, 12, 8)
    assert (validation["samples_before"], validation["interior_trimmed_rows"], validation["samples_after"]) == (12, 6, 4)
    assert [entry["interior_trimmed"] for entry in train["per_episode"]] == [6, 6]
    assert all(row["samples"] == 4 for row in _metrics(root) if row["kind"] == "validation")


def test_cudnn_benchmark_is_set_only_when_the_config_asks_for_it(tmp_path, monkeypatch):
    monkeypatch.setattr(torch.backends.cudnn, "benchmark", False)
    (tmp_path / "off").mkdir()
    (tmp_path / "on").mkdir()
    _train(tmp_path / "off", monkeypatch, steps=1)
    assert torch.backends.cudnn.benchmark is False
    _train(tmp_path / "on", monkeypatch, steps=1, cudnn_benchmark=True)
    assert torch.backends.cudnn.benchmark is True


def test_channels_last_converts_only_the_backbone_and_only_when_asked(tmp_path, monkeypatch):
    calls = []
    real = torch.nn.Module.to

    def spy(self, *args, **kwargs):
        if kwargs.get("memory_format") is not None:
            calls.append((type(self).__name__, kwargs["memory_format"]))
        return real(self, *args, **kwargs)
    monkeypatch.setattr(torch.nn.Module, "to", spy)
    (tmp_path / "off").mkdir()
    (tmp_path / "on").mkdir()
    _train(tmp_path / "off", monkeypatch, steps=1)
    assert calls == []
    _, outcome, _ = _train(tmp_path / "on", monkeypatch, steps=1, channels_last=True)
    assert outcome["status"] == "COMPLETED"
    assert len(calls) == 1 and calls[0][1] == torch.channels_last and calls[0][0] != "ACTPolicy"

def _record_autocast(monkeypatch):
    from lerobot.policies.act.modeling_act import ACTPolicy
    seen = []
    forward = ACTPolicy.forward

    def recording(self, batch):
        seen.append((self.training, torch.is_autocast_enabled("cpu")))
        return forward(self, batch)

    monkeypatch.setattr(ACTPolicy, "forward", recording)
    return seen


def test_precision_defaults_to_fp32_without_autocast(tmp_path, monkeypatch):
    seen = _record_autocast(monkeypatch)
    _train(tmp_path, monkeypatch)
    assert seen and not any(autocast for _, autocast in seen)


def test_bf16_precision_autocasts_the_training_forward_only_and_keeps_fp32_weights(tmp_path, monkeypatch):
    from safetensors import safe_open
    seen = _record_autocast(monkeypatch)
    _, outcome, root = _train(tmp_path, monkeypatch, precision="bf16")
    assert outcome["status"] == "COMPLETED"
    assert [autocast for training, autocast in seen if training] == [True] * 3          # the three training steps
    assert not any(autocast for training, autocast in seen if not training)           # validation stays fp32
    with safe_open(str(root / "policy.safetensors"), "pt") as stream:
        assert {stream.get_tensor(key).dtype for key in stream.keys()} == {torch.float32}      # master weights are fp32
