"""The compress_dwell selection keys and the TRAIN-005 configurations."""
import pytest
from paths import PACKAGE_ROOT
from test_act_training_config import CONFIG, _load

from so101_demo.act.training_config import load_training_config

PACKAGE = PACKAGE_ROOT


def test_the_compress_dwell_selection_keys_come_together_and_exclude_the_other_rules(tmp_path):
    base = {"trim_leading_idle": False, "idle_threshold_rad": 0.005, "lead_in_rows": 0}
    selection = {**base, "compress_dwell": True, "keep_tail_rows": 20}
    assert _load(tmp_path, **{"training.sample_selection": selection})["training"]["sample_selection"] == selection
    off = {**selection, "compress_dwell": False}
    assert _load(tmp_path, **{"training.sample_selection": off})["training"]["sample_selection"] == off
    for bad in ({**base, "compress_dwell": True},                                          # one key without the other
                {**base, "keep_tail_rows": 20},
                {**selection, "compress_dwell": 1},
                {**selection, "keep_tail_rows": -1}, {**selection, "keep_tail_rows": True},
                {**selection, "trim_interior_idle": True},                                 # with the interior trim: refused
                {**selection, "trim_leading_idle": True}):                                 # leading idle is a dwell: no second rule
        with pytest.raises(ValueError, match="TRAINING_SAMPLE_SELECTION_INVALID"):
            _load(tmp_path, **{"training.sample_selection": bad})


def test_an_absent_compress_dwell_keeps_the_config_as_it_was():
    selection = load_training_config(CONFIG)["training"].get("sample_selection", {})
    assert "compress_dwell" not in selection
    old = load_training_config(PACKAGE / "config/act/training-side-wrist-004.yaml")["training"]["sample_selection"]
    assert "compress_dwell" not in old


def test_the_train_005_configurations_are_train_004_with_compress_dwell_and_optionally_bf16():
    new = load_training_config(PACKAGE / "config/act/training-side-wrist-005.yaml")
    bf16 = load_training_config(PACKAGE / "config/act/training-side-wrist-005-bf16.yaml")
    old = load_training_config(PACKAGE / "config/act/training-side-wrist-004.yaml")
    rest = lambda cfg: {k: v for k, v in cfg.items() if k != "training"}          # noqa: E731
    assert rest(new) == rest(old) == rest(bf16)
    assert {k: v for k, v in new["training"].items() if k != "sample_selection"} \
        == {k: v for k, v in old["training"].items() if k != "sample_selection"}
    assert new["training"]["sample_selection"] == {"trim_leading_idle": False, "idle_threshold_rad": 0.005, "lead_in_rows": 0,
                                                    "compress_dwell": True, "keep_tail_rows": 20}
    assert "precision" not in new["training"]
    assert bf16["training"] == {**new["training"], "precision": "bf16"}
