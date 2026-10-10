"""Design 2026-10-10 D8: one decode table maps the recorder's PNG keys to the runtime keys, and its digest is frozen in the config."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config/act/training.yaml"


def test_the_decode_table_maps_the_recorder_png_keys_to_the_runtime_keys():
    from so101_demo.adapters.act.lerobot import OBSERVATION_DECODE_TABLE
    assert dict(OBSERVATION_DECODE_TABLE) == {"head_png": "head", "wrist_png": "wrist"}
    assert [key for key, _ in OBSERVATION_DECODE_TABLE] == ["head_png", "wrist_png"]


def test_preprocessing_sha256_is_the_digest_of_the_declared_preprocessing_and_is_frozen_in_the_config():
    from so101_demo.adapters.act.lerobot import PREPROCESSING, preprocessing_sha256
    expected = hashlib.sha256(json.dumps(PREPROCESSING, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                         allow_nan=False).encode()).hexdigest()
    assert preprocessing_sha256() == expected
    assert PREPROCESSING["observation_decode"] == {"head_png": "head", "wrist_png": "wrist"}
    assert PREPROCESSING["image"]["decode"] == "PNG -> uint8 HxWx3 RGB"
    frozen = yaml.safe_load(CONFIG.read_text())["frozen"]["preprocessing_sha256"]
    assert frozen == expected and frozen != "0" * 64


def test_the_trainer_refuses_a_config_whose_preprocessing_hash_drifted(tmp_path):
    # the check precedes the torch import, so it is exercised in the ordinary interpreter
    from so101_demo.act.training_config import load_training_config
    from so101_demo.adapters.act.lerobot import train_act_bundle
    config = load_training_config(CONFIG)
    config["frozen"]["preprocessing_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="TRAINING_PREPROCESSING_DRIFT"):
        train_act_bundle(config, tmp_path / "view", tmp_path / "out", requirements_sha256="a" * 64)
    assert not (tmp_path / "out").exists()


def test_the_trainer_refuses_a_schema_v1_config_and_a_missing_requirements_digest(tmp_path):
    from so101_demo.act.training_config import load_training_config
    from so101_demo.adapters.act.lerobot import preprocessing_sha256, train_act_bundle
    config = load_training_config(CONFIG)
    config["frozen"]["preprocessing_sha256"] = preprocessing_sha256()
    with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_SHA256_INVALID"):
        train_act_bundle(config, tmp_path / "view", tmp_path / "out", requirements_sha256="short")
    v1 = {**config, "schema_version": 1}
    with pytest.raises(ValueError, match="TRAINING_CONFIG_V2_REQUIRED"):
        train_act_bundle(v1, tmp_path / "view", tmp_path / "out", requirements_sha256="a" * 64)


def _ready_config(**backbone):
    from so101_demo.act.training_config import load_training_config
    from so101_demo.adapters.act.lerobot import preprocessing_sha256
    config = load_training_config(CONFIG)
    config["frozen"]["preprocessing_sha256"] = preprocessing_sha256()
    return config


def test_the_backbone_weights_are_required_present_and_hash_verified_before_any_training(tmp_path):
    from so101_demo.adapters.act.lerobot import train_act_bundle
    config = _ready_config()
    assert config["training"]["pretrained_backbone"] is not None
    with pytest.raises(ValueError, match="TRAINING_BACKBONE_PATH_REQUIRED"):
        train_act_bundle(config, tmp_path / "view", tmp_path / "out", requirements_sha256="a" * 64)
    with pytest.raises(ValueError, match="TRAINING_BACKBONE_MISSING"):
        train_act_bundle(config, tmp_path / "view", tmp_path / "out", requirements_sha256="a" * 64,
                         backbone_weights=tmp_path / "absent.pth")
    weights = tmp_path / "resnet18.pth"
    weights.write_bytes(b"not the pinned weights")
    with pytest.raises(ValueError, match="TRAINING_BACKBONE_HASH_MISMATCH"):
        train_act_bundle(config, tmp_path / "view", tmp_path / "out", requirements_sha256="a" * 64, backbone_weights=weights)
    assert not (tmp_path / "out").exists()


def test_weights_are_refused_when_the_config_names_no_backbone(tmp_path):
    from so101_demo.adapters.act.lerobot import train_act_bundle
    config = _ready_config()
    config["training"]["pretrained_backbone"] = None
    weights = tmp_path / "w.pth"
    weights.write_bytes(b"x")
    with pytest.raises(ValueError, match="TRAINING_BACKBONE_NOT_CONFIGURED"):
        train_act_bundle(config, tmp_path / "view", tmp_path / "out", requirements_sha256="a" * 64, backbone_weights=weights)
