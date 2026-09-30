"""Prepare reproducible Ultralytics segmentation training inputs.

Two entry points live here. `prepare_training_run` is the original single-dataset path. 1
`prepare_candidate_run` materializes one Head Search candidate: the union of the sealed head-camera
dataset and the task-camera dataset, undownsampled, in the exact 1:1 batch order the candidate plan
declares, together with the runtime config the trainer consumes and a manifest of every file it wrote.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:  # pragma: no cover - the import is only for the annotation
    from so101_demo.act.head_search_training import CandidatePlan

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


@dataclass(frozen=True, slots=True)
class PreparedCandidateRun:
    """One materialized candidate run: the union dataset, its config and its file manifest."""

    output_root: Path
    dataset_yaml: Path
    training_config: Path
    candidate_plan: Path
    run_manifest: Path
    plan_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(source.resolve(), target)


def _domain_images(root: Path, split: str, domain: str) -> list[Path]:
    images = sorted((root / "images" / split).glob("*.png"))
    if not images:
        raise ValueError(f"candidate dataset {domain} has no {split} images under {root}")
    for image in images:
        label = root / "labels" / split / f"{image.stem}.txt"
        if not label.is_file():
            raise ValueError(f"candidate dataset {domain} is missing the label of {image.name}")
    return images


def prepare_candidate_run(
    *,
    plan: "CandidatePlan",
    contract_path: Path,
    head_dataset_root: Path,
    task_dataset_root: Path,
    base_model_path: Path,
    output_root: Path,
    run_name: str = "train",
) -> PreparedCandidateRun:
    """Materialize one candidate's union dataset and the exact run the trainer will perform."""

    from so101_demo.act.head_search_training import CandidatePlan
    from so101_demo.runtime.task_artifacts import atomic_json

    if not isinstance(plan, CandidatePlan):
        raise ValueError("candidate plan must be a CandidatePlan")
    contract_path = Path(contract_path).resolve(strict=True)
    head_root = Path(head_dataset_root).resolve(strict=True)
    task_root = Path(task_dataset_root).resolve(strict=True)
    if Path(base_model_path).is_symlink():
        raise ValueError("base model must not be a symlink")
    base_model = Path(base_model_path).resolve(strict=True)
    if not base_model.is_file():
        raise ValueError("base model must be a regular file")
    if not run_name or Path(run_name).name != run_name:
        raise ValueError("run name must be one non-empty path component")
    output_root = Path(output_root)
    if output_root.exists():
        raise FileExistsError(f"training output root already exists: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    contract = _mapping(contract_path)
    contract_names = _class_names(contract.get("class_names"))

    union = output_root / "dataset"
    domain_files: dict[str, dict[str, list[Path]]] = {"train": {}, "val": {}}
    for split, expected in (
        ("train", plan.train_count),
        ("val", plan.val_count),
    ):
        head_images = _domain_images(head_root, split, "head")
        task_images = _domain_images(task_root, split, "task")
        if split == "train":
            declared = plan.domain_counts
        else:
            declared = plan.validation_counts
        if len(head_images) != declared.get("head") or (
            "task" in declared and len(task_images) != declared["task"]
        ):
            raise ValueError(
                f"candidate datasets do not hold the plan's {split} counts: head "
                f"{len(head_images)}/{declared.get('head')}, task {len(task_images)}/"
                f"{declared.get('task')}"
            )
        if sum(len(values) for values in (head_images, task_images)) != expected:
            raise ValueError(f"candidate union {split} count does not match the plan")
        for domain, images in (("head", head_images), ("task", task_images)):
            root = head_root if domain == "head" else task_root
            linked = []
            for image in images:
                name = f"{domain}-{image.name}"
                target_image = union / "images" / split / name
                _link(image, target_image)
                _link(
                    root / "labels" / split / f"{image.stem}.txt",
                    union / "labels" / split / f"{domain}-{image.stem}.txt",
                )
                linked.append(target_image)
            domain_files[split][domain] = linked

    # the batch order the plan froze: one head block, one task block, repeating
    def _interleave(split: str) -> list[Path]:
        head_list = domain_files[split].get("head", [])
        task_list = domain_files[split].get("task", [])
        if not task_list:
            return list(head_list)
        ordered_list: list[Path] = []
        half = plan.batch_size // 2
        head_index = task_index = 0
        while head_index < len(head_list) or task_index < len(task_list):
            ordered_list.extend(head_list[head_index : head_index + half])
            head_index += half
            ordered_list.extend(task_list[task_index : task_index + half])
            task_index += half
        return ordered_list

    dataset_yaml = output_root / "dataset.yaml"
    train_list = output_root / "train.txt"
    val_list = output_root / "val.txt"
    train_list.write_text("".join(f"{path}\n" for path in _interleave("train")), encoding="utf-8")
    val_list.write_text("".join(f"{path}\n" for path in _interleave("val")), encoding="utf-8")
    _write_yaml(
        dataset_yaml,
        {
            "path": str(output_root),
            "train": str(train_list),
            "val": str(val_list),
            "names": {index: name for index, name in enumerate(contract_names)},
        },
    )
    runtime = {key: value for key, value in contract.items() if key != "class_names"}
    runtime["model"] = str(base_model)
    runtime["data"] = str(dataset_yaml)
    runtime["project"] = str(output_root)
    runtime["name"] = run_name
    runtime["epochs"] = plan.epochs
    runtime["device"] = plan.device
    training_config = output_root / "training-config.yaml"
    _write_yaml(training_config, runtime)
    candidate_plan_path = output_root / "candidate-plan.json"
    atomic_json(candidate_plan_path, plan.to_document())
    files = {
        path.relative_to(output_root).as_posix(): _sha256_file(path)
        for path in (dataset_yaml, training_config, candidate_plan_path, train_list, val_list)
    }
    run_manifest = output_root / "run-manifest.json"
    atomic_json(
        run_manifest,
        {
            "schema_version": 1,
            "candidate_id": plan.candidate_id,
            "plan_sha256": plan.sha256,
            "train_count": plan.train_count,
            "val_count": plan.val_count,
            "domain_counts": dict(plan.domain_counts),
            "validation_counts": dict(plan.validation_counts),
            "batch_size": plan.batch_size,
            "batches": len(plan.batches),
            "device": plan.device,
            "allow_cpu_fallback": plan.allow_cpu_fallback,
            "promotable": plan.promotable,
            "files": files,
        },
    )
    return PreparedCandidateRun(
        output_root=output_root,
        dataset_yaml=dataset_yaml,
        training_config=training_config,
        candidate_plan=candidate_plan_path,
        run_manifest=run_manifest,
        plan_sha256=plan.sha256,
    )
