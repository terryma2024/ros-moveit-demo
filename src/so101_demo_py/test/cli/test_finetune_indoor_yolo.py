"""The indoor YOLO fine-tune CLI: the frozen training arguments (the training itself needs ultralytics and a GPU)."""

from __future__ import annotations

import pytest

from so101_demo.cli import finetune_indoor_yolo as cli


def test_the_training_arguments_are_fixed_by_the_command_line_and_deterministic(tmp_path):
    parsed = cli.parse(["--base-model", "/m/best.pt", "--dataset", "/d/dataset.yaml", "--output", str(tmp_path / "run"), "--epochs", "12"])
    arguments = cli.train_arguments(parsed)
    assert arguments["data"] == "/d/dataset.yaml" and arguments["epochs"] == 12 and arguments["seed"] == 0
    assert arguments["deterministic"] is True and arguments["imgsz"] == 640 and arguments["task"] == "segment"
    assert arguments["project"] == str(tmp_path) and arguments["name"] == "run" and arguments["exist_ok"] is False
    assert arguments["lr0"] < 0.01 and arguments["freeze"] == 0


def test_relative_paths_and_an_existing_output_are_refused(tmp_path):
    with pytest.raises(SystemExit):
        cli.parse(["--base-model", "best.pt", "--dataset", "/d/dataset.yaml", "--output", str(tmp_path / "run")])
    (tmp_path / "run").mkdir()
    with pytest.raises(SystemExit):
        cli.parse(["--base-model", "/m/best.pt", "--dataset", "/d/dataset.yaml", "--output", str(tmp_path / "run")])


def test_dataset_yaml_path_is_anchored_to_the_dataset_directory(tmp_path):
    yaml = tmp_path / "dataset.yaml"
    yaml.write_text("path: .\ntrain: images/train\nnames:\n  0: plastic_cup\n")
    text = cli.anchored_dataset_yaml(yaml)
    assert text.splitlines()[0] == f"path: {tmp_path}" and "train: images/train" in text
