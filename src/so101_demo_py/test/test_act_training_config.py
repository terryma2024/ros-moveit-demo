"""Task 12: the training configuration is frozen, and drift is refused rather than absorbed."""

from pathlib import Path

import pytest
import yaml

from so101_demo.act.training_config import load_training_config

PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE / "config/act/training.yaml"


def _load(tmp_path, **overrides):
    document = yaml.safe_load(CONFIG.read_text())
    for dotted, value in overrides.items():
        head, _, leaf = dotted.partition(".")
        document[head][leaf] = value
    path = tmp_path / "training.yaml"
    path.write_text(yaml.safe_dump(document))
    return load_training_config(path)


def test_the_frozen_smoke_configuration_is_accepted(tmp_path):
    document = load_training_config(CONFIG)
    assert document["action"]["chunk_size"] == 10
    assert document["action"]["execution_prefix"] == 1
    assert document["action"]["temporal_ensembling"] is False
    assert document["action"]["tail_padding_mask"] is True
    assert tuple(document["observation"]["cameras"]) == ("head", "wrist")
    assert document["normalization"]["split"] == "train"


def test_drift_from_the_frozen_contract_is_refused(tmp_path):
    for overrides, code in (({"action.chunk_size": 20}, "TRAINING_CHUNK_SIZE_DRIFT"),
                            ({"action.execution_prefix": 10}, "TRAINING_EXECUTION_PREFIX_DRIFT"),
                            ({"action.temporal_ensembling": True},
                             "TRAINING_TEMPORAL_ENSEMBLING_FORBIDDEN"),
                            ({"action.tail_padding_mask": False}, "TRAINING_PADDING_MASK_REQUIRED"),
                            ({"observation.cameras": ["head"]}, "TRAINING_CAMERAS_INVALID"),
                            ({"observation.cameras": ["head", "wrist", "side"]},
                             "TRAINING_CAMERAS_INVALID"),
                            ({"observation.state_dim": 7}, "TRAINING_DIMENSIONS_INVALID"),
                            ({"observation.action_dim": 7}, "TRAINING_DIMENSIONS_INVALID"),
                            ({"normalization.split": "validation"},
                             "TRAINING_NORMALIZATION_NOT_TRAIN_ONLY"),
                            ({"frozen.preprocessing_sha256": "short"}, "TRAINING_CONFIG_INVALID"),
                            ({"frozen.seed": "0"}, "TRAINING_CONFIG_INVALID")):
        with pytest.raises(ValueError, match=code):
            _load(tmp_path, **overrides)
    with pytest.raises(ValueError, match="TRAINING_CONFIG_MISSING"):
        load_training_config(tmp_path / "absent.yaml")
    broken = tmp_path / "broken.yaml"
    broken.write_text("{not yaml")
    with pytest.raises(ValueError, match="TRAINING_CONFIG_INVALID"):
        load_training_config(broken)


def test_an_extra_key_is_refused_rather_than_ignored(tmp_path):
    document = yaml.safe_load(CONFIG.read_text())
    document["extra"] = 1
    path = tmp_path / "extra.yaml"
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError, match="TRAINING_CONFIG_INVALID"):
        load_training_config(path)
