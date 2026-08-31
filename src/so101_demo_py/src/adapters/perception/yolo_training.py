"""Prepare reproducible Ultralytics segmentation training inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class PreparedTrainingRun:
    """Materialized, runtime-compatible configuration for one training run."""

    output_root: Path
    dataset_yaml: Path
    training_config: Path


def _mapping(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"YAML document must be a mapping: {path}")
    return dict(document)


def _class_names(value: object) -> list[str]:
    if isinstance(value, list):
        names = value
    elif isinstance(value, Mapping):
        try:
            names = [value[index] for index in range(len(value))]
        except (KeyError, TypeError) as error:
            raise ValueError("dataset class names must use contiguous integer keys") from error
    else:
        raise ValueError("dataset class names must be a list or integer-keyed mapping")
    if not names or not all(isinstance(name, str) and name for name in names):
        raise ValueError("dataset class names must be non-empty strings")
    return list(names)


def _write_yaml(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(dict(document), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def prepare_training_run(
    *,
    contract_path: Path,
    dataset_yaml_path: Path,
    base_model_path: Path,
    output_root: Path,
    run_name: str,
    epochs_override: int | None = None,
    fraction: float | None = None,
) -> PreparedTrainingRun:
    """Freeze project metadata into configs accepted by Ultralytics.

    ``class_names`` remains part of the repository contract, but Ultralytics
    rejects it as an unknown training argument.  The runtime dataset config
    carries the authoritative names and an absolute dataset root instead.
    """

    contract_path = contract_path.resolve(strict=True)
    dataset_yaml_path = dataset_yaml_path.resolve(strict=True)
    if base_model_path.is_symlink():
        raise ValueError("base model must not be a symlink")
    base_model_path = base_model_path.resolve(strict=True)
    if not base_model_path.is_file():
        raise ValueError("base model must be a regular file")
    if not run_name or Path(run_name).name != run_name:
        raise ValueError("run name must be one non-empty path component")
    if output_root.exists():
        raise FileExistsError(f"training output root already exists: {output_root}")

    contract = _mapping(contract_path)
    dataset = _mapping(dataset_yaml_path)
    contract_names = _class_names(contract.get("class_names"))
    dataset_names = _class_names(dataset.get("names"))
    if contract_names != dataset_names:
        raise ValueError(
            f"training contract class names {contract_names!r} do not match "
            f"dataset class names {dataset_names!r}"
        )
    if epochs_override is not None and epochs_override <= 0:
        raise ValueError("epochs override must be positive")
    if fraction is not None and not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be in (0, 1]")

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    runtime_dataset_path = output_root / "dataset.yaml"
    runtime_training_path = output_root / "training-config.yaml"

    runtime_dataset = dict(dataset)
    runtime_dataset["path"] = str(dataset_yaml_path.parent)
    _write_yaml(runtime_dataset_path, runtime_dataset)

    runtime_training = dict(contract)
    runtime_training.pop("class_names")
    runtime_training["model"] = str(base_model_path)
    runtime_training["data"] = str(runtime_dataset_path)
    runtime_training["project"] = str(output_root)
    runtime_training["name"] = run_name
    if epochs_override is not None:
        runtime_training["epochs"] = epochs_override
    if fraction is not None:
        runtime_training["fraction"] = fraction
    _write_yaml(runtime_training_path, runtime_training)

    return PreparedTrainingRun(
        output_root=output_root,
        dataset_yaml=runtime_dataset_path,
        training_config=runtime_training_path,
    )
