"""The training configuration is frozen, and drift is refused rather than absorbed."""


import pytest
import yaml

from so101_demo.act.training_config import load_training_config
from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT
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


# ---- schema 2 (design 2026-10-10 section 3.0 item 3): steps, learning rate, batch size and the std floor ---------------------------


def _write(tmp_path, document):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(document))
    return path


def test_the_shipped_configuration_carries_the_training_hyper_parameters():
    document = load_training_config(CONFIG)
    assert document["schema_version"] == 2
    training = document["training"]
    assert type(training["steps"]) is int and training["steps"] > 0
    assert type(training["batch_size"]) is int and training["batch_size"] > 0
    assert type(training["learning_rate"]) is float and training["learning_rate"] > 0
    assert type(document["normalization"]["std_floor"]) is float and document["normalization"]["std_floor"] > 0


@pytest.mark.parametrize("overrides,code", [
    ({"training.steps": 0}, "TRAINING_STEPS_INVALID"), ({"training.steps": 1.5}, "TRAINING_STEPS_INVALID"),
    ({"training.steps": True}, "TRAINING_STEPS_INVALID"),
    ({"training.batch_size": 0}, "TRAINING_BATCH_SIZE_INVALID"), ({"training.batch_size": "8"}, "TRAINING_BATCH_SIZE_INVALID"),
    ({"training.learning_rate": 0.0}, "TRAINING_LEARNING_RATE_INVALID"),
    ({"training.learning_rate": -1e-5}, "TRAINING_LEARNING_RATE_INVALID"),
    ({"training.learning_rate": float("inf")}, "TRAINING_LEARNING_RATE_INVALID"),
    ({"training.learning_rate": "1e-5"}, "TRAINING_LEARNING_RATE_INVALID"),
    ({"normalization.std_floor": 0.0}, "TRAINING_STD_FLOOR_INVALID"),
    ({"normalization.std_floor": float("nan")}, "TRAINING_STD_FLOOR_INVALID"),
    ({"normalization.std_floor": None}, "TRAINING_STD_FLOOR_INVALID")])
def test_a_configuration_with_a_bad_hyper_parameter_is_refused(tmp_path, overrides, code):
    with pytest.raises(ValueError, match=code):
        _load(tmp_path, **{key.replace("training.", "training.", 1): value for key, value in overrides.items()})


def test_a_configuration_must_carry_the_training_block(tmp_path):
    document = yaml.safe_load(CONFIG.read_text())
    del document["training"]
    with pytest.raises(ValueError, match="TRAINING_CONFIG_INVALID"):
        load_training_config(_write(tmp_path, document))
    document = yaml.safe_load(CONFIG.read_text())
    document["training"]["momentum"] = 0.9
    with pytest.raises(ValueError, match="TRAINING_CONFIG_INVALID"):
        load_training_config(_write(tmp_path, document))
    document = yaml.safe_load(CONFIG.read_text())
    document["schema_version"] = 3
    with pytest.raises(ValueError, match="TRAINING_CONFIG_INVALID"):
        load_training_config(_write(tmp_path, document))


# ---- pretrained backbone (closed v2 field: {name, sha256} or null) ---------------------------------------------------------------------


def test_the_shipped_configuration_names_the_imagenet_resnet18_backbone_by_hash():
    backbone = load_training_config(CONFIG)["training"]["pretrained_backbone"]
    assert backbone == {"name": "ResNet18_Weights.IMAGENET1K_V1",
                        "sha256": "f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec"}


def test_no_pretrained_backbone_is_an_explicit_null(tmp_path):
    assert _load(tmp_path, **{"training.pretrained_backbone": None})["training"]["pretrained_backbone"] is None


@pytest.mark.parametrize("value", [{"name": "x"}, {"name": "x", "sha256": "short"}, {"name": "", "sha256": "a" * 64},
                                   {"name": "x", "sha256": "a" * 64, "path": "/w"}, "ResNet18", {"name": 3, "sha256": "a" * 64}])
def test_a_malformed_backbone_field_is_refused(tmp_path, value):
    with pytest.raises(ValueError, match="TRAINING_BACKBONE_INVALID"):
        _load(tmp_path, **{"training.pretrained_backbone": value})


def test_the_backbone_field_is_part_of_the_training_block_only(tmp_path):
    document = yaml.safe_load(CONFIG.read_text())
    del document["training"]["pretrained_backbone"]
    with pytest.raises(ValueError, match="TRAINING_CONFIG_INVALID"):
        load_training_config(_write(tmp_path, document))


def test_a_configuration_of_another_schema_is_refused(tmp_path):
    document = yaml.safe_load(CONFIG.read_text())
    document["schema_version"] = 1
    del document["training"]
    del document["normalization"]["std_floor"]
    with pytest.raises(ValueError, match="TRAINING_CONFIG_INVALID"):
        load_training_config(_write(tmp_path, document))


def test_the_progress_validation_and_worker_keys_default_and_are_validated(tmp_path):
    document = load_training_config(CONFIG)["training"]
    assert (document["log_interval_steps"], document["validation_interval_steps"], document["validation_samples"],
            document["num_workers"]) == (100, 2000, 512, 4)
    raw = yaml.safe_load(CONFIG.read_text())
    for key in ("log_interval_steps", "validation_interval_steps", "validation_samples", "num_workers"):
        del raw["training"][key]
    path = tmp_path / "old.yaml"
    path.write_text(yaml.safe_dump(raw))
    assert load_training_config(path)["training"]["num_workers"] == 4          # an older file without the keys still loads
    assert _load(tmp_path, **{"training.num_workers": 0})["training"]["num_workers"] == 0
    for key, value, code in (("log_interval_steps", 0, "TRAINING_LOG_INTERVAL_STEPS_INVALID"),
                             ("log_interval_steps", 1.5, "TRAINING_LOG_INTERVAL_STEPS_INVALID"),
                             ("validation_interval_steps", -1, "TRAINING_VALIDATION_INTERVAL_STEPS_INVALID"),
                             ("validation_samples", 0, "TRAINING_VALIDATION_SAMPLES_INVALID"),
                             ("validation_samples", True, "TRAINING_VALIDATION_SAMPLES_INVALID"),
                             ("num_workers", -1, "TRAINING_NUM_WORKERS_INVALID"),
                             ("num_workers", 65, "TRAINING_NUM_WORKERS_INVALID"),
                             ("num_workers", "4", "TRAINING_NUM_WORKERS_INVALID"),
                             ("num_workers", 2.0, "TRAINING_NUM_WORKERS_INVALID")):
        with pytest.raises(ValueError, match=code):
            _load(tmp_path, **{f"training.{key}": value})
    with pytest.raises(ValueError, match="TRAINING_CONFIG_INVALID"):
        _load(tmp_path, **{"training.surprise": 1})


def test_the_o7_keys_are_optional_and_absent_ones_are_not_filled_in(tmp_path):
    training = load_training_config(CONFIG)["training"]
    assert "sample_selection" not in training and "learning_rate_backbone" not in training      # TRAIN-001 config is unchanged
    selection = {"trim_leading_idle": True, "idle_threshold_rad": 0.005, "lead_in_rows": 10}
    loaded = _load(tmp_path, **{"training.sample_selection": selection, "training.learning_rate_backbone": 1.0e-5})["training"]
    assert loaded["sample_selection"] == selection and loaded["learning_rate_backbone"] == 1.0e-5


@pytest.mark.parametrize("key,value", [
    ("learning_rate_backbone", 0.0), ("learning_rate_backbone", -1e-5), ("learning_rate_backbone", "1e-5"),
    ("learning_rate_backbone", float("nan")),
    ("sample_selection", None), ("sample_selection", {"trim_leading_idle": True}),
    ("sample_selection", {"trim_leading_idle": 1, "idle_threshold_rad": 0.005, "lead_in_rows": 10}),
    ("sample_selection", {"trim_leading_idle": True, "idle_threshold_rad": 0, "lead_in_rows": 10}),
    ("sample_selection", {"trim_leading_idle": True, "idle_threshold_rad": 0.005, "lead_in_rows": -1}),
    ("sample_selection", {"trim_leading_idle": True, "idle_threshold_rad": 0.005, "lead_in_rows": 1.5}),
    ("sample_selection", {"trim_leading_idle": True, "idle_threshold_rad": 0.005, "lead_in_rows": 10, "extra": 1}),
])
def test_bad_o7_keys_are_refused(tmp_path, key, value):
    code = "TRAINING_LEARNING_RATE_BACKBONE_INVALID" if key == "learning_rate_backbone" else "TRAINING_SAMPLE_SELECTION_INVALID"
    with pytest.raises(ValueError, match=code):
        _load(tmp_path, **{f"training.{key}": value})


def test_the_training_002_configuration_loads_with_the_o7_values():
    training = load_training_config(PACKAGE / "config/act/training-002.yaml")["training"]
    assert (training["learning_rate"], training["learning_rate_backbone"], training["steps"], training["batch_size"],
            training["num_workers"]) == (1.0e-4, 1.0e-5, 60000, 16, 8)
    assert training["sample_selection"] == {"trim_leading_idle": True, "idle_threshold_rad": 0.005, "lead_in_rows": 10}
    assert (training["log_interval_steps"], training["validation_interval_steps"]) == (100, 2000)
    base = load_training_config(CONFIG)
    other = load_training_config(PACKAGE / "config/act/training-002.yaml")
    assert {key: other[key] for key in other if key != "training"} == {key: base[key] for key in base if key != "training"}
