from __future__ import annotations

from pathlib import Path

import hashlib
import json

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
BASE_SHA = "d" * 64


def _manifest(
    *,
    train: int,
    val: int,
    test: int,
    digest: str,
    promotable: bool = True,
    camera: str = "head_camera",
) -> dict:
    """A sealed dataset manifest: counts, a camera domain and the samples the plan verifies."""

    samples = []
    for split, count, base in (
        ("train", train, 100000),
        ("val", val, 200000),
        ("test", test, 300000),
    ):
        for index in range(count):
            seed = base + index
            samples.append(
                {
                    "seed": seed,
                    "split": split,
                    "scenario": "one_cup_distractors",
                    "scene_group_id": f"scene-{seed:09d}",
                    "image": f"images/{split}/{seed:09d}.png",
                    "label": f"labels/{split}/{seed:09d}.txt",
                    "truth": f"truth/{split}/{seed:09d}.json",
                }
            )
    return {
        "dataset_contract": "so101-head-search-yolo-seg-v1",
        "schema_version": 1,
        "camera_name": camera,
        "sample_count": train + val + test,
        "split_counts": {"train": train, "val": val, "test": test},
        "promotable": promotable,
        "dataset_sha256": digest,
        "samples": samples,
    }


def test_mixed_candidate_uses_full_union_and_balanced_batches() -> None:
    plan = build_candidate_plan(
        "C",
        head=_manifest(train=800, val=200, test=200, digest="a" * 64),
        task=_manifest(train=800, val=200, test=200, digest="b" * 64, camera="task_camera"),
        contract=HEAD_CONTRACT,
        base_model_sha256=BASE_SHA,
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
        task=_manifest(train=800, val=200, test=200, digest="b" * 64, camera="task_camera"),
        contract=HEAD_CONTRACT,
        base_model_sha256=BASE_SHA,
    )

    assert plan.train_count == 800
    assert plan.val_count == 400, "B is scored on both validation domains"
    assert plan.domain_counts == {"head": 800}
    assert plan.validation_counts == {"head": 200, "task": 200}
    assert all(batch.task_count == 0 for batch in plan.batches)


def test_b_and_c_use_the_same_two_domain_checkpoint_score() -> None:
    for candidate_id in ("B", "C"):
        plan = build_candidate_plan(
            candidate_id,
            head=_manifest(train=800, val=200, test=200, digest="a" * 64),
            task=_manifest(train=800, val=200, test=200, digest="b" * 64, camera="task_camera"),
            contract=HEAD_CONTRACT,
            base_model_sha256=BASE_SHA,
        )

        assert plan.checkpoint_score == ("0.5*head_val_mask_map50_95+0.5*task_val_mask_map50_95")
        assert plan.validation_domains == ("head", "task")


def test_smoke_candidate_is_balanced_but_never_promotable() -> None:
    plan = build_candidate_plan(
        "C",
        head=_manifest(train=32, val=8, test=8, digest="a" * 64, promotable=False),
        task=_manifest(train=32, val=8, test=8, digest="b" * 64, camera="task_camera"),
        contract=HEAD_SMOKE_CONTRACT,
        base_model_sha256=BASE_SHA,
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
            task=_manifest(train=32, val=8, test=8, digest="b" * 64, camera="task_camera"),
            contract=cpu_contract,
            base_model_sha256=BASE_SHA,
        )

    document["device"] = "cuda"
    document["allow_cpu_fallback"] = True
    fallback_contract = tmp_path / "fallback.yaml"
    fallback_contract.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(CandidatePlanError, match="CANDIDATE_CPU_FALLBACK_FORBIDDEN"):
        build_candidate_plan(
            "B",
            head=_manifest(train=32, val=8, test=8, digest="a" * 64),
            task=_manifest(train=32, val=8, test=8, digest="b" * 64, camera="task_camera"),
            contract=fallback_contract,
            base_model_sha256=BASE_SHA,
        )


def test_candidate_plan_refuses_an_unknown_candidate_or_smoke_head_for_production() -> None:
    head = _manifest(train=32, val=8, test=8, digest="a" * 64, promotable=False)
    task = _manifest(train=32, val=8, test=8, digest="b" * 64, camera="task_camera")
    with pytest.raises(CandidatePlanError, match="CANDIDATE_ID_INVALID"):
        build_candidate_plan(
            "D", head=head, task=task, contract=HEAD_SMOKE_CONTRACT, base_model_sha256=BASE_SHA
        )
    with pytest.raises(CandidatePlanError, match="CANDIDATE_HEAD_NOT_SEALED"):
        build_candidate_plan(
            "C", head=head, task=task, contract=HEAD_CONTRACT, base_model_sha256=BASE_SHA
        )


def test_candidate_plan_binds_the_union_dataset_digest_and_hyperparameters() -> None:
    head = _manifest(train=800, val=200, test=200, digest="a" * 64)
    task = _manifest(train=800, val=200, test=200, digest="b" * 64, camera="task_camera")
    plan = build_candidate_plan(
        "C", head=head, task=task, contract=HEAD_CONTRACT, base_model_sha256=BASE_SHA
    )
    again = build_candidate_plan(
        "C", head=head, task=task, contract=HEAD_CONTRACT, base_model_sha256=BASE_SHA
    )

    assert plan.sha256 == again.sha256 and len(plan.sha256) == 64
    assert set(plan.dataset_digests) == {"head", "task"}
    assert all(len(value) == 64 for value in plan.dataset_digests.values())
    assert plan.dataset_digests["head"] != plan.dataset_digests["task"], (
        "the plan digests the datasets it verified, not a caller-supplied string"
    )
    baseline = build_candidate_plan(
        "B", head=head, task=task, contract=HEAD_CONTRACT, base_model_sha256=BASE_SHA
    )
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


def _sealed_manifest(root: Path, *, camera: str, train: int, val: int) -> dict:
    """A sealed manifest whose counts and camera domain the plan can verify, with real files written."""

    samples = []
    for split, count, base in (("train", train, 100000), ("val", val, 200000)):
        for index in range(count):
            seed = base + index
            samples.append(
                {
                    "seed": seed,
                    "split": split,
                    "scenario": "one_cup_distractors",
                    "scene_group_id": f"scene-{seed:09d}",
                    "image": f"images/{split}/{seed:09d}.png",
                    "label": f"labels/{split}/{seed:09d}.txt",
                    "truth": f"truth/{split}/{seed:09d}.json",
                }
            )
    return {
        "dataset_contract": "so101-head-search-yolo-seg-v1",
        "schema_version": 1,
        "camera_name": camera,
        "sample_count": train + val,
        "split_counts": {"train": train, "val": val, "test": 0},
        "promotable": True,
        "samples": samples,
    }


def _write_domain(root: Path, manifest: dict) -> Path:
    import numpy as np
    from so101_demo.runtime.point_cloud_preview import write_png_rgb8

    for sample in manifest["samples"]:
        image = root / sample["image"]
        image.parent.mkdir(parents=True, exist_ok=True)
        write_png_rgb8(np.zeros((8, 10, 3), dtype=np.uint8), image)
        label = root / sample["label"]
        label.parent.mkdir(parents=True, exist_ok=True)
        label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
        truth = root / sample["truth"]
        truth.parent.mkdir(parents=True, exist_ok=True)
        truth.write_text("{}\n", encoding="utf-8")
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


def test_prepare_candidate_run_refuses_aliases_and_traversal(tmp_path: Path) -> None:
    from so101_demo.adapters.perception.yolo_training import prepare_candidate_run

    head_manifest = _sealed_manifest(tmp_path, camera="head_camera", train=32, val=8)
    task_manifest = _sealed_manifest(tmp_path, camera="task_camera", train=32, val=8)
    head_root = tmp_path / "head"
    task_root = tmp_path / "task"
    head_manifest_path = _write_domain(head_root, head_manifest)
    task_manifest_path = _write_domain(task_root, task_manifest)
    base_model = tmp_path / "yolo11n-seg.pt"
    base_model.write_bytes(b"weights")
    plan = build_candidate_plan(
        "C",
        head=head_manifest,
        task=task_manifest,
        contract=HEAD_SMOKE_CONTRACT,
        base_model_sha256=hashlib.sha256(base_model.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="CANDIDATE_DOMAIN_ROOT_ALIAS"):
        prepare_candidate_run(
            plan=plan,
            contract_path=HEAD_SMOKE_CONTRACT,
            head_dataset_root=head_root,
            task_dataset_root=head_root,
            head_manifest_path=head_manifest_path,
            task_manifest_path=task_manifest_path,
            base_model_path=base_model,
            output_root=tmp_path / "aliased",
        )
    with pytest.raises(ValueError, match="CANDIDATE_RUN_NAME_INVALID"):
        prepare_candidate_run(
            plan=plan,
            contract_path=HEAD_SMOKE_CONTRACT,
            head_dataset_root=head_root,
            task_dataset_root=task_root,
            head_manifest_path=head_manifest_path,
            task_manifest_path=task_manifest_path,
            base_model_path=base_model,
            output_root=tmp_path / "traversal",
            run_name="..",
        )
    # a label that leaves its own dataset root is refused, and the failed run leaves nothing behind
    outside = tmp_path / "outside.txt"
    outside.write_text("99 -1 -1 -1 -1 -1 -1\n", encoding="utf-8")
    victim = head_root / head_manifest["samples"][0]["label"]
    victim.unlink()
    victim.symlink_to(outside)
    with pytest.raises(ValueError, match="CANDIDATE_SOURCE_ESCAPE"):
        prepare_candidate_run(
            plan=plan,
            contract_path=HEAD_SMOKE_CONTRACT,
            head_dataset_root=head_root,
            task_dataset_root=task_root,
            head_manifest_path=head_manifest_path,
            task_manifest_path=task_manifest_path,
            base_model_path=base_model,
            output_root=tmp_path / "escaped",
        )
    assert not (tmp_path / "escaped").exists(), "a failed preparation leaves no output root"


def test_candidate_cli_refuses_conflicting_overrides(tmp_path: Path) -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "so101_demo.cli.train_yolo_seg",
            "--candidate",
            "C",
            "--training-contract",
            str(HEAD_SMOKE_CONTRACT),
            "--head-manifest",
            str(tmp_path / "head.json"),
            "--task-manifest",
            str(tmp_path / "task.json"),
            "--head-dataset-root",
            str(tmp_path),
            "--task-dataset-root",
            str(tmp_path),
            "--base-model",
            str(tmp_path / "weights.pt"),
            "--output",
            str(tmp_path / "out"),
            "--epochs",
            "9",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stderr
    assert "epochs" in result.stderr and "candidate" in result.stderr


# ----------------------------------------------------------------------------------------------------------------------
# The candidate trainer's own rules: 1:1 batches, the two-domain score and the earlier-epoch tie.
# ----------------------------------------------------------------------------------------------------------------------


def test_balanced_epoch_order_keeps_every_batch_one_to_one_and_is_deterministic() -> None:
    from so101_demo.adapters.perception.candidate_trainer import (
        balanced_epoch_order,
        domain_positions,
    )

    head, task = domain_positions(
        [f"head-{index:03d}.png" for index in range(64)]
        + [f"task-{index:03d}.png" for index in range(64)]
    )
    assert len(head) == 64 and len(task) == 64
    order = balanced_epoch_order(head, task, 32, seed=17, epoch=0)
    assert sorted(order) == list(range(128)), "every union member is seen exactly once"
    for offset in range(0, len(order), 32):
        batch = order[offset : offset + 32]
        assert sum(position < 64 for position in batch) == 16
        assert sum(position >= 64 for position in batch) == 16
    assert order == balanced_epoch_order(head, task, 32, seed=17, epoch=0)
    assert order != balanced_epoch_order(head, task, 32, seed=17, epoch=1)
    with pytest.raises(ValueError, match="CANDIDATE_BATCH_INVALID"):
        balanced_epoch_order(head, task, 31, seed=17, epoch=0)
    with pytest.raises(ValueError, match="CANDIDATE_UNION_UNLABELLED"):
        domain_positions(["mystery-001.png"])


def test_head_only_candidate_trains_from_the_head_domain_alone() -> None:
    from so101_demo.adapters.perception.candidate_trainer import balanced_epoch_order

    head = list(range(32))
    order = balanced_epoch_order(head, [], 32, seed=5, epoch=2)
    assert sorted(order) == sorted(head), "head-only training sees head images and nothing else"
    assert balanced_epoch_order(head, [], 8, seed=5, epoch=2) != []


def test_two_domain_score_requires_both_cells_and_keeps_the_earlier_checkpoint() -> None:
    from so101_demo.adapters.perception.candidate_trainer import (
        select_checkpoint,
        two_domain_fitness,
    )

    assert two_domain_fitness(0.4, 0.6) == pytest.approx(0.5)
    for bad in (None, float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="CANDIDATE_SCORE_INCOMPLETE"):
            two_domain_fitness(0.4, bad)
    assert select_checkpoint([], candidate_epoch=0, candidate_score=0.5)
    assert not select_checkpoint([(3, 0.5)], candidate_epoch=4, candidate_score=0.5), (
        "an equal score keeps the earlier checkpoint"
    )
    assert select_checkpoint([(3, 0.5)], candidate_epoch=2, candidate_score=0.5)
    assert select_checkpoint([(3, 0.5)], candidate_epoch=4, candidate_score=0.6)
    assert not select_checkpoint([(3, 0.6)], candidate_epoch=4, candidate_score=0.5)
    assert not select_checkpoint([(3, 0.5)], candidate_epoch=4, candidate_score=float("nan"))


def test_prepared_runtime_config_carries_only_trainer_arguments(tmp_path: Path) -> None:
    from so101_demo.adapters.perception.candidate_trainer import _unused
    from so101_demo.adapters.perception.yolo_training import TRAINER_ARG_KEYS, prepare_candidate_run

    del _unused
    head_manifest = _sealed_manifest(tmp_path, camera="head_camera", train=32, val=8)
    task_manifest = _sealed_manifest(tmp_path, camera="task_camera", train=32, val=8)
    head_root = tmp_path / "head"
    task_root = tmp_path / "task"
    head_manifest_path = _write_domain(head_root, head_manifest)
    task_manifest_path = _write_domain(task_root, task_manifest)
    base_model = tmp_path / "yolo11n-seg.pt"
    base_model.write_bytes(b"weights")
    plan = build_candidate_plan(
        "C",
        head=head_manifest,
        task=task_manifest,
        contract=HEAD_SMOKE_CONTRACT,
        base_model_sha256=hashlib.sha256(base_model.read_bytes()).hexdigest(),
    )
    prepared = prepare_candidate_run(
        plan=plan,
        contract_path=HEAD_SMOKE_CONTRACT,
        head_dataset_root=head_root,
        task_dataset_root=task_root,
        head_manifest_path=head_manifest_path,
        task_manifest_path=task_manifest_path,
        base_model_path=base_model,
        output_root=tmp_path / "candidate-c",
    )
    runtime = yaml.safe_load(prepared.training_config.read_text(encoding="utf-8"))
    assert set(runtime) <= set(TRAINER_ARG_KEYS), (
        "project metadata must not be forwarded to Ultralytics: "
        f"{sorted(set(runtime) - set(TRAINER_ARG_KEYS))}"
    )
    assert runtime["device"] == "cuda" and runtime["epochs"] == 1
    assert (prepared.output_root / "val-head.txt").is_file()
    assert (prepared.output_root / "val-task.txt").is_file()
    for name in ("train.txt", "val.txt", "val-head.txt", "val-task.txt"):
        for line in (prepared.output_root / name).read_text().split():
            recorded = Path(line)
            assert recorded.is_absolute(), f"{name} must record the published path: {line}"
            assert recorded.is_relative_to(prepared.output_root), (
                f"{name} must not point at a staging directory: {line}"
            )
            assert recorded.is_file(), f"{name} points at a missing {line}"
    assert prepared.trainer_script.is_file()
    manifest = json.loads(prepared.run_manifest.read_text(encoding="utf-8"))
    assert manifest["checkpoint_score"] == ("0.5*head_val_mask_map50_95+0.5*task_val_mask_map50_95")
    assert not (prepared.output_root / "candidate-manifest.json").exists(), (
        "the candidate seal is written only after a successful training run"
    )
    # a mutated source image changes the recorded content digest
    victim = head_root / head_manifest["samples"][0]["image"]
    before = manifest["files"][f"dataset/images/train/head-{victim.name}"]
    import numpy as np
    from so101_demo.runtime.point_cloud_preview import write_png_rgb8

    write_png_rgb8(np.full((8, 10, 3), 255, dtype=np.uint8), victim)
    after = hashlib.sha256(victim.read_bytes()).hexdigest()
    assert after != before, "the run manifest digests file contents, not just names"


def test_prepared_runtime_config_is_accepted_by_the_installed_ultralytics(tmp_path: Path) -> None:
    """The reviewers' finding: a project-metadata key makes Ultralytics refuse the whole run."""

    from so101_demo.adapters.perception.yolo_training import prepare_candidate_run

    ultralytics_cfg = pytest.importorskip("ultralytics.cfg")
    head_manifest = _sealed_manifest(tmp_path, camera="head_camera", train=32, val=8)
    task_manifest = _sealed_manifest(tmp_path, camera="task_camera", train=32, val=8)
    head_root = tmp_path / "head"
    task_root = tmp_path / "task"
    head_manifest_path = _write_domain(head_root, head_manifest)
    task_manifest_path = _write_domain(task_root, task_manifest)
    base_model = tmp_path / "yolo11n-seg.pt"
    base_model.write_bytes(b"weights")
    plan = build_candidate_plan(
        "C",
        head=head_manifest,
        task=task_manifest,
        contract=HEAD_SMOKE_CONTRACT,
        base_model_sha256=hashlib.sha256(base_model.read_bytes()).hexdigest(),
    )
    prepared = prepare_candidate_run(
        plan=plan,
        contract_path=HEAD_SMOKE_CONTRACT,
        head_dataset_root=head_root,
        task_dataset_root=task_root,
        head_manifest_path=head_manifest_path,
        task_manifest_path=task_manifest_path,
        base_model_path=base_model,
        output_root=tmp_path / "candidate-cfg",
    )
    runtime = yaml.safe_load(prepared.training_config.read_text(encoding="utf-8"))
    cfg = ultralytics_cfg.get_cfg(overrides=runtime)
    assert cfg.device == "cuda" and cfg.epochs == 1


def test_prepare_candidate_run_refuses_an_unpaired_training_sample(tmp_path: Path) -> None:
    """The deciding reviewer's residual finding: a merged loop only checked the validation split."""

    from so101_demo.adapters.perception.yolo_training import prepare_candidate_run

    head_manifest = _sealed_manifest(tmp_path, camera="head_camera", train=32, val=8)
    task_manifest = _sealed_manifest(tmp_path, camera="task_camera", train=32, val=8)
    head_root = tmp_path / "head"
    task_root = tmp_path / "task"
    head_manifest_path = _write_domain(head_root, head_manifest)
    task_manifest_path = _write_domain(task_root, task_manifest)
    # the first training sample's manifest entry points at another image's label
    broken = json.loads(json.dumps(head_manifest))
    victim = broken["samples"][0]
    victim["label"] = f"labels/train/{victim['seed'] + 1:09d}.txt"
    head_manifest_path.write_text(
        json.dumps(broken, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    base_model = tmp_path / "yolo11n-seg.pt"
    base_model.write_bytes(b"weights")
    plan = build_candidate_plan(
        "B",
        head=broken,
        task=task_manifest,
        contract=HEAD_SMOKE_CONTRACT,
        base_model_sha256=hashlib.sha256(base_model.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="CANDIDATE_SOURCE_UNPAIRED"):
        prepare_candidate_run(
            plan=plan,
            contract_path=HEAD_SMOKE_CONTRACT,
            head_dataset_root=head_root,
            task_dataset_root=task_root,
            head_manifest_path=head_manifest_path,
            task_manifest_path=task_manifest_path,
            base_model_path=base_model,
            output_root=tmp_path / "unpaired",
        )
    assert not (tmp_path / "unpaired").exists()
