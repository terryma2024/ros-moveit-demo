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
    runtime_training = yaml.safe_load(prepared.training_config.read_text(encoding="utf-8"))
    assert runtime_dataset["path"] == str(dataset_yaml.parent.resolve())
    assert runtime_dataset["names"] == {0: "plastic_cup"}
    assert "class_names" not in runtime_training
    assert runtime_training["model"] == str(base_model.resolve())
    assert runtime_training["data"] == str(prepared.dataset_yaml.resolve())
    assert runtime_training["project"] == str(output_root.resolve())
    assert runtime_training["name"] == "smoke"
    assert runtime_training["epochs"] == 1
    assert runtime_training["fraction"] == 0.05
    assert yaml.safe_load(contract.read_text(encoding="utf-8"))["class_names"] == ["plastic_cup"]


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


# ----------------------------------------------------------------------------------------------------------------------
# Head Search candidates: B learns from the head domain only, C from the union of both camera domains with a frozen
# 1:1 batch composition, and both are scored and trained exactly like candidate A.
# ----------------------------------------------------------------------------------------------------------------------

from so101_demo.act.head_search_training import (  # noqa: E402
    CandidatePlanError,
    build_candidate_plan,
    load_training_contract,
)

HEAD_CONTRACT = Path(__file__).parents[1] / "config/perception/head_search_yolo_training.yaml"
HEAD_SMOKE_CONTRACT = (
    Path(__file__).parents[1] / "config/perception/head_search_yolo_training_smoke.yaml"
)
PACKAGE = Path(__file__).parents[1]


def _manifest(*, train: int, val: int, test: int, digest: str, promotable: bool = True) -> dict:
    return {
        "dataset_contract": "so101-head-search-yolo-seg-v1",
        "sample_count": train + val + test,
        "split_counts": {"train": train, "val": val, "test": test},
        "promotable": promotable,
        "dataset_sha256": digest,
        "samples": [],
    }


def test_mixed_candidate_uses_full_union_and_balanced_batches() -> None:
    plan = build_candidate_plan(
        "C",
        head=_manifest(train=800, val=200, test=200, digest="a" * 64),
        task=_manifest(train=800, val=200, test=200, digest="b" * 64),
        contract=HEAD_CONTRACT,
    )

    assert plan.train_count == 1600
    assert plan.val_count == 400
    assert plan.domain_counts == {"head": 800, "task": 800}
    assert plan.validation_counts == {"head": 200, "task": 200}
    assert all(batch.head_count == batch.task_count for batch in plan.batches)
    assert all(batch.head_count + batch.task_count == plan.batch_size for batch in plan.batches)
    assert plan.device == "cuda" and plan.allow_cpu_fallback is False
    assert plan.promotable is True


def test_head_only_candidate_uses_only_the_head_domain() -> None:
    plan = build_candidate_plan(
        "B",
        head=_manifest(train=800, val=200, test=200, digest="a" * 64),
        task=_manifest(train=800, val=200, test=200, digest="b" * 64),
        contract=HEAD_CONTRACT,
    )

    assert plan.train_count == 800
    assert plan.val_count == 200
    assert plan.domain_counts == {"head": 800}
    assert plan.validation_counts == {"head": 200, "task": 200}
    assert all(batch.task_count == 0 for batch in plan.batches)


def test_b_and_c_use_the_same_two_domain_checkpoint_score() -> None:
    for candidate_id in ("B", "C"):
        plan = build_candidate_plan(
            candidate_id,
            head=_manifest(train=800, val=200, test=200, digest="a" * 64),
            task=_manifest(train=800, val=200, test=200, digest="b" * 64),
            contract=HEAD_CONTRACT,
        )

        assert plan.checkpoint_score == ("0.5*head_val_mask_map50_95+0.5*task_val_mask_map50_95")
        assert plan.validation_domains == ("head", "task")


def test_smoke_candidate_is_balanced_but_never_promotable() -> None:
    plan = build_candidate_plan(
        "C",
        head=_manifest(train=32, val=8, test=8, digest="a" * 64, promotable=False),
        task=_manifest(train=32, val=8, test=8, digest="b" * 64),
        contract=HEAD_SMOKE_CONTRACT,
    )

    assert plan.domain_counts == {"head": 32, "task": 32}
    assert plan.validation_counts == {"head": 8, "task": 8}
    assert plan.promotable is False
    assert plan.epochs == 1


def test_candidate_plan_refuses_a_non_cuda_or_fallback_contract(tmp_path: Path) -> None:
    document = yaml.safe_load(HEAD_CONTRACT.read_text(encoding="utf-8"))
    document["device"] = "cpu"
    cpu_contract = tmp_path / "cpu.yaml"
    cpu_contract.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(CandidatePlanError, match="CANDIDATE_DEVICE_INVALID"):
        build_candidate_plan(
            "C",
            head=_manifest(train=32, val=8, test=8, digest="a" * 64),
            task=_manifest(train=32, val=8, test=8, digest="b" * 64),
            contract=cpu_contract,
        )

    document["device"] = "cuda"
    document["allow_cpu_fallback"] = True
    fallback_contract = tmp_path / "fallback.yaml"
    fallback_contract.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(CandidatePlanError, match="CANDIDATE_CPU_FALLBACK_FORBIDDEN"):
        build_candidate_plan(
            "B",
            head=_manifest(train=32, val=8, test=8, digest="a" * 64),
            task=_manifest(train=32, val=8, test=8, digest="b" * 64),
            contract=fallback_contract,
        )


def test_candidate_plan_refuses_an_unknown_candidate_or_smoke_head_for_production() -> None:
    head = _manifest(train=32, val=8, test=8, digest="a" * 64, promotable=False)
    task = _manifest(train=32, val=8, test=8, digest="b" * 64)
    with pytest.raises(CandidatePlanError, match="CANDIDATE_ID_INVALID"):
        build_candidate_plan("D", head=head, task=task, contract=HEAD_SMOKE_CONTRACT)
    with pytest.raises(CandidatePlanError, match="CANDIDATE_HEAD_NOT_SEALED"):
        build_candidate_plan("C", head=head, task=task, contract=HEAD_CONTRACT)


def test_candidate_plan_binds_the_union_dataset_digest_and_hyperparameters() -> None:
    head = _manifest(train=800, val=200, test=200, digest="a" * 64)
    task = _manifest(train=800, val=200, test=200, digest="b" * 64)
    plan = build_candidate_plan("C", head=head, task=task, contract=HEAD_CONTRACT)
    again = build_candidate_plan("C", head=head, task=task, contract=HEAD_CONTRACT)

    assert plan.sha256 == again.sha256 and len(plan.sha256) == 64
    assert plan.dataset_digests == {"head": "a" * 64, "task": "b" * 64}
    baseline = build_candidate_plan("B", head=head, task=task, contract=HEAD_CONTRACT)
    assert plan.hyperparameters == baseline.hyperparameters


def test_the_tracked_training_contracts_freeze_both_profiles() -> None:
    production = load_training_contract(HEAD_CONTRACT)
    smoke = load_training_contract(HEAD_SMOKE_CONTRACT)

    assert production.device == "cuda" and production.allow_cpu_fallback is False
    assert production.checkpoint_score == ("0.5*head_val_mask_map50_95+0.5*task_val_mask_map50_95")
    assert production.batch_size % 2 == 0
    assert production.epochs >= 2
    assert smoke.promotable is False and smoke.epochs == 1
    assert {**production.hyperparameters} == {**smoke.hyperparameters}


def _tiny_domain(root: Path, *, domain: str, train: int, val: int) -> None:
    import numpy as np
    from so101_demo.runtime.point_cloud_preview import write_png_rgb8

    for split, count in (("train", train), ("val", val)):
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)
        for index in range(count):
            stem = f"{domain}-{split}-{index:04d}"
            write_png_rgb8(
                np.zeros((8, 10, 3), dtype=np.uint8), root / "images" / split / f"{stem}.png"
            )
            (root / "labels" / split / f"{stem}.txt").write_text(
                "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
            )


def test_prepared_candidate_run_materialises_the_frozen_union(tmp_path: Path) -> None:
    from so101_demo.adapters.perception.yolo_training import prepare_candidate_run

    head_root = tmp_path / "head"
    task_root = tmp_path / "task"
    _tiny_domain(head_root, domain="head", train=4, val=2)
    _tiny_domain(task_root, domain="task", train=4, val=2)
    plan = build_candidate_plan(
        "C",
        head=_manifest(train=4, val=2, test=2, digest="a" * 64),
        task=_manifest(train=4, val=2, test=2, digest="b" * 64),
        contract=HEAD_SMOKE_CONTRACT,
    )
    base_model = tmp_path / "yolo11n-seg.pt"
    base_model.write_bytes(b"weights")

    prepared = prepare_candidate_run(
        plan=plan,
        contract_path=HEAD_SMOKE_CONTRACT,
        head_dataset_root=head_root,
        task_dataset_root=task_root,
        base_model_path=base_model,
        output_root=tmp_path / "candidate-c",
    )

    run = yaml.safe_load(prepared.run_manifest.read_text(encoding="utf-8"))
    assert run["plan_sha256"] == plan.sha256
    assert run["train_count"] == 8 and run["val_count"] == 4
    train_order = [
        Path(line).name for line in prepared.output_root.joinpath("train.txt").read_text().split()
    ]
    index = 0
    for batch in plan.batches:
        size = batch.head_count + batch.task_count
        block = train_order[index : index + size]
        index += size
        assert sum(name.startswith("head-") for name in block) == batch.head_count
        assert sum(name.startswith("task-") for name in block) == batch.task_count
        assert batch.head_count == batch.task_count, "every block is 1:1 by camera domain"
    assert index == len(train_order)
    assert all(
        (prepared.output_root / "dataset/labels/train" / name.replace(".png", ".txt")).is_file()
        for name in train_order
    )
    runtime = yaml.safe_load(prepared.training_config.read_text(encoding="utf-8"))
    assert runtime["device"] == "cuda" and runtime["epochs"] == 1
    assert runtime["shuffle"] is False and runtime["seed"] == plan.hyperparameters["seed"]

    with pytest.raises(FileExistsError, match="already exists"):
        prepare_candidate_run(
            plan=plan,
            contract_path=HEAD_SMOKE_CONTRACT,
            head_dataset_root=head_root,
            task_dataset_root=task_root,
            base_model_path=base_model,
            output_root=tmp_path / "candidate-c",
        )
