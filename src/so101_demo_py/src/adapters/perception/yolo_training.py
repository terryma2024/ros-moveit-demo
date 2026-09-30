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
from typing import TYPE_CHECKING, Any, Mapping, Sequence

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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _link(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(Path(source).resolve(), target)


PROJECT_ONLY_KEYS = (
    "allow_cpu_fallback",
    "checkpoint_score",
    "validation_domains",
    "dataset_domains",
    "promotable",
    "domain_train",
    "domain_val",
    "class_names",
    "classes",
)
TRAINER_ARG_KEYS = (
    "task",
    "model",
    "data",
    "imgsz",
    "epochs",
    "batch",
    "workers",
    "seed",
    "deterministic",
    "device",
    "amp",
    "optimizer",
    "patience",
    "project",
    "name",
    "save",
    "plots",
    "verbose",
    "val",
)


@dataclass(frozen=True, slots=True)
class PreparedCandidateRun:
    """One materialized candidate run: the union dataset, its config and its file manifest."""

    output_root: Path
    dataset_yaml: Path
    training_config: Path
    candidate_plan: Path
    run_manifest: Path
    trainer_script: Path
    plan_sha256: str


def _require_regular_file(name: str, path: Path, *, inside: Path | None = None) -> Path:
    resolved = Path(path)
    if resolved.is_symlink():
        resolved = resolved.resolve()
    if not resolved.is_file():
        raise ValueError(f"CANDIDATE_SOURCE_MISSING: {name} is not a file: {path}")
    if inside is not None:
        try:
            resolved.resolve().relative_to(Path(inside).resolve())
        except ValueError as error:
            raise ValueError(
                f"CANDIDATE_SOURCE_ESCAPE: {name} resolves outside its dataset root: {path}"
            ) from error
    return resolved


def _domain_files(
    root: Path, manifest: Mapping[str, Any], split: str, seeds: Sequence[int]
) -> list[tuple[Path, Path]]:
    """The (image, label) pairs of one domain split, refusing escapes and unpaired files."""

    by_seed = {
        int(sample["seed"]): sample for sample in manifest["samples"] if sample["split"] == split
    }
    pairs = []
    for seed in seeds:
        sample = by_seed.get(int(seed))
        if sample is None:
            raise ValueError(f"CANDIDATE_SOURCE_MISSING: no {split} sample for seed {seed}")
        image = _require_regular_file("image", root / str(sample["image"]), inside=root)
        label = _require_regular_file("label", root / str(sample["label"]), inside=root)
        pairs.append((image, label))
    return pairs


def prepare_candidate_run(
    *,
    plan: "CandidatePlan",
    contract_path: Path,
    head_dataset_root: Path,
    task_dataset_root: Path,
    head_manifest_path: Path | None = None,
    task_manifest_path: Path | None = None,
    base_model_path: Path,
    output_root: Path,
    run_name: str = "train",
) -> PreparedCandidateRun:
    """Materialize one candidate's union dataset and the exact run the trainer will perform.

    Everything is checked before anything is written, the batch is staged in a sibling directory and
    published with one rename, so a failure leaves no output root behind and a published root is never
    half written.
    """

    import json
    import shutil

    from so101_demo.act.head_search_training import CandidatePlan
    from so101_demo.perception_benchmark.contracts import canonical_sha256
    from so101_demo.runtime.task_artifacts import atomic_json

    if not isinstance(plan, CandidatePlan):
        raise ValueError("candidate plan must be a CandidatePlan")
    contract_path = Path(contract_path).resolve(strict=True)
    head_root = Path(head_dataset_root).resolve(strict=True)
    task_root = Path(task_dataset_root).resolve(strict=True)
    if head_root == task_root:
        raise ValueError(
            "CANDIDATE_DOMAIN_ROOT_ALIAS: the head and task domains cannot share one dataset root"
        )
    if run_name in {"", ".", ".."} or Path(run_name).name != run_name or "/" in run_name:
        raise ValueError(
            f"CANDIDATE_RUN_NAME_INVALID: run name must be one ordinary path component, not {run_name!r}"
        )
    base_model = _require_regular_file("base model", base_model_path)
    base_sha = _sha256_file(base_model)
    if base_sha != plan.base_model_sha256:
        raise ValueError(
            "CANDIDATE_BASE_MODEL_DRIFT: the base weights are not the ones the plan froze "
            f"({base_sha[:12]} vs {plan.base_model_sha256[:12]})"
        )
    output_root = Path(output_root)
    if output_root.exists():
        raise FileExistsError(f"training output root already exists: {output_root}")
    contract = _mapping(contract_path)
    if canonical_sha256(contract) != canonical_sha256(dict(plan.recipe)):
        raise ValueError(
            "CANDIDATE_CONTRACT_DRIFT: the contract on disk is not the recipe the plan froze"
        )
    manifests = {}
    for domain, root, manifest_path in (
        ("head", head_root, head_manifest_path),
        ("task", task_root, task_manifest_path),
    ):
        if manifest_path is None:
            raise ValueError(f"CANDIDATE_MANIFEST_MISSING: {domain} needs its sealed manifest")
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if canonical_sha256(manifest) != plan.dataset_digests[domain]:
            raise ValueError(
                f"CANDIDATE_MANIFEST_DRIFT: the {domain} manifest on disk is not the one the plan froze"
            )
        manifests[domain] = manifest

    train_pairs = {
        "head": _domain_files(head_root, manifests["head"], "train", plan.head_train_seeds)
    }
    val_pairs = {"head": _domain_files(head_root, manifests["head"], "val", plan.head_val_seeds)}
    if plan.candidate_id == "C":
        train_pairs["task"] = _domain_files(task_root, manifests["task"], "train", plan.task_subset)
    val_pairs["task"] = _domain_files(task_root, manifests["task"], "val", plan.task_val_seeds)
    if sum(len(pairs) for pairs in train_pairs.values()) != plan.train_count:
        raise ValueError("CANDIDATE_UNION_MISMATCH: the training union is not the plan's")
    if sum(len(pairs) for pairs in val_pairs.values()) != plan.val_count:
        raise ValueError("CANDIDATE_UNION_MISMATCH: the validation union is not the plan's")
    # both splits are checked: merging the two mappings would silently drop the training pairs
    for split, pairs_by_domain in (("train", train_pairs), ("val", val_pairs)):
        for domain, pairs in pairs_by_domain.items():
            for image, label in pairs:
                if image.parent.parent.name != "images" or label.parent.parent.name != "labels":
                    raise ValueError(
                        "CANDIDATE_SOURCE_LAYOUT_INVALID: images and labels must live under the "
                        f"dataset's images/ and labels/ directories ({split} {domain})"
                    )
                if image.stem != label.stem:
                    raise ValueError(
                        f"CANDIDATE_SOURCE_UNPAIRED: {image.name} and {label.name} do not belong "
                        f"together ({split} {domain})"
                    )

    staging = output_root.parent / f".{output_root.name}.staging-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        union = staging / "dataset"
        files: dict[str, str] = {}
        domain_files: dict[str, dict[str, list[Path]]] = {"train": {}, "val": {}}
        for split, pairs_by_domain in (("train", train_pairs), ("val", val_pairs)):
            for domain in sorted(pairs_by_domain):
                linked = []
                for image, label in pairs_by_domain[domain]:
                    name = f"{domain}-{image.name}"
                    target_image = union / "images" / split / name
                    published_image = output_root / "dataset/images" / split / name
                    target_label = union / "labels" / split / f"{domain}-{label.name}"
                    _link(image, target_image)
                    _link(label, target_label)
                    files[target_image.relative_to(staging).as_posix()] = _sha256_file(image)
                    files[target_label.relative_to(staging).as_posix()] = _sha256_file(label)
                    linked.append(published_image)
                domain_files[split][domain] = linked

        def _interleave(split: str) -> list[Path]:
            head_list = domain_files[split].get("head", [])
            task_list = domain_files[split].get("task", [])
            if not task_list:
                return list(head_list)
            order: list[Path] = []
            half = plan.batch_size // 2
            head_index = task_index = 0
            while head_index < len(head_list) or task_index < len(task_list):
                order.extend(head_list[head_index : head_index + half])
                head_index += half
                order.extend(task_list[task_index : task_index + half])
                task_index += half
            return order

        dataset_yaml = staging / "dataset.yaml"
        train_list = staging / "train.txt"
        val_list = staging / "val.txt"
        train_list.write_text(
            "".join(f"{path}\n" for path in _interleave("train")), encoding="utf-8"
        )
        val_list.write_text("".join(f"{path}\n" for path in _interleave("val")), encoding="utf-8")
        class_names = _class_names(contract.get("class_names"))
        _write_yaml(
            dataset_yaml,
            {
                "path": str(output_root),
                "train": str(output_root / "train.txt"),
                "val": str(output_root / "val.txt"),
                "names": {index: name for index, name in enumerate(class_names)},
            },
        )
        runtime = {
            key: value
            for key, value in contract.items()
            if key in TRAINER_ARG_KEYS and key not in {"model", "data", "project", "name"}
        }
        runtime["model"] = str(base_model)
        runtime["data"] = str(output_root / "dataset.yaml")
        runtime["project"] = str(output_root)
        runtime["name"] = run_name
        runtime["epochs"] = plan.epochs
        runtime["device"] = plan.device
        training_config = staging / "training-config.yaml"
        _write_yaml(training_config, runtime)
        candidate_plan_path = staging / "candidate-plan.json"
        atomic_json(candidate_plan_path, plan.to_document())
        for path in (dataset_yaml, training_config, candidate_plan_path, train_list, val_list):
            files[path.relative_to(staging).as_posix()] = _sha256_file(path)
        for domain in ("head", "task"):
            domain_list = staging / f"val-{domain}.txt"
            domain_list.write_text(
                "".join(f"{path}\n" for path in domain_files["val"].get(domain, [])),
                encoding="utf-8",
            )
            files[domain_list.relative_to(staging).as_posix()] = _sha256_file(domain_list)
        trainer_script = staging / "train-candidate.py"
        trainer_script.write_text(
            "#!/usr/bin/env python3\n"
            '"""Run one Head Search candidate with its frozen balanced composition and score."""\n\n'
            "import sys\n\n"
            "from so101_demo.adapters.perception.candidate_trainer import main\n\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main(sys.argv[1:]))\n",
            encoding="utf-8",
        )
        trainer_script.chmod(0o755)
        files["train-candidate.py"] = _sha256_file(trainer_script)
        run_manifest = staging / "run-manifest.json"
        atomic_json(
            run_manifest,
            {
                "schema_version": 1,
                "candidate_id": plan.candidate_id,
                "plan_sha256": plan.sha256,
                "base_model_sha256": base_sha,
                "train_count": plan.train_count,
                "val_count": plan.val_count,
                "domain_counts": dict(plan.domain_counts),
                "validation_counts": dict(plan.validation_counts),
                "batch_size": plan.batch_size,
                "batches": len(plan.batches),
                "device": plan.device,
                "allow_cpu_fallback": plan.allow_cpu_fallback,
                "checkpoint_score": plan.checkpoint_score,
                "promotable": plan.promotable,
                "trainer_script": "train-candidate.py",
                "files": files,
            },
        )
        os.replace(staging, output_root)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return PreparedCandidateRun(
        output_root=output_root,
        dataset_yaml=output_root / "dataset.yaml",
        training_config=output_root / "training-config.yaml",
        candidate_plan=output_root / "candidate-plan.json",
        run_manifest=output_root / "run-manifest.json",
        trainer_script=output_root / "train-candidate.py",
        plan_sha256=plan.sha256,
    )
