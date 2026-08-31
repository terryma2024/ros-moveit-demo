from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from so101_demo.adapters.perception.yolo_training import prepare_training_run


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    contract = tmp_path / "training.yaml"
    contract.write_text(
        yaml.safe_dump(
            {
                "task": "segment",
                "model": "yolo11n-seg.pt",
                "data": "dataset.yaml",
                "class_names": ["plastic_cup"],
                "classes": [0],
                "imgsz": 640,
                "epochs": 100,
                "device": "cuda",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    dataset_yaml = dataset_root / "dataset.yaml"
    dataset_yaml.write_text(
        "path: .\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        "  0: plastic_cup\n",
        encoding="utf-8",
    )
    base_model = tmp_path / "yolo11n-seg.pt"
    base_model.write_bytes(b"locked-local-model")
    return contract, dataset_yaml, base_model


def test_prepare_training_run_materializes_ultralytics_compatible_configs(
    tmp_path: Path,
) -> None:
    contract, dataset_yaml, base_model = _write_inputs(tmp_path)
    output_root = tmp_path / "run"

    prepared = prepare_training_run(
        contract_path=contract,
        dataset_yaml_path=dataset_yaml,
        base_model_path=base_model,
        output_root=output_root,
        run_name="smoke",
        epochs_override=1,
        fraction=0.05,
    )

    runtime_dataset = yaml.safe_load(prepared.dataset_yaml.read_text(encoding="utf-8"))
    runtime_training = yaml.safe_load(
        prepared.training_config.read_text(encoding="utf-8")
    )
    assert runtime_dataset["path"] == str(dataset_yaml.parent.resolve())
    assert runtime_dataset["names"] == {0: "plastic_cup"}
    assert "class_names" not in runtime_training
    assert runtime_training["model"] == str(base_model.resolve())
    assert runtime_training["data"] == str(prepared.dataset_yaml.resolve())
    assert runtime_training["project"] == str(output_root.resolve())
    assert runtime_training["name"] == "smoke"
    assert runtime_training["epochs"] == 1
    assert runtime_training["fraction"] == 0.05
    assert yaml.safe_load(contract.read_text(encoding="utf-8"))["class_names"] == [
        "plastic_cup"
    ]


def test_prepare_training_run_rejects_contract_dataset_class_mismatch(
    tmp_path: Path,
) -> None:
    contract, dataset_yaml, base_model = _write_inputs(tmp_path)
    dataset_yaml.write_text(
        dataset_yaml.read_text(encoding="utf-8").replace("plastic_cup", "bottle"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="class names"):
        prepare_training_run(
            contract_path=contract,
            dataset_yaml_path=dataset_yaml,
            base_model_path=base_model,
            output_root=tmp_path / "run",
            run_name="smoke",
        )


def test_prepare_training_run_refuses_existing_output_root(tmp_path: Path) -> None:
    contract, dataset_yaml, base_model = _write_inputs(tmp_path)
    output_root = tmp_path / "run"
    output_root.mkdir()

    with pytest.raises(FileExistsError, match="output root"):
        prepare_training_run(
            contract_path=contract,
            dataset_yaml_path=dataset_yaml,
            base_model_path=base_model,
            output_root=output_root,
            run_name="smoke",
        )
