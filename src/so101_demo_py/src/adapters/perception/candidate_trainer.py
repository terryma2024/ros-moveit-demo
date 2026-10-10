"""Train one Head Search candidate with its frozen composition and two-domain score.

The plan for a candidate freezes three things this module implements: every training batch holds the same
number of head-camera and task-camera images, the checkpoint score is the average of the two camera
domains' validation mask mAP, and two epochs that score the same keep the earlier checkpoint. The pure
functions below carry those rules and are tested directly; `main` wires them into Ultralytics.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path

#: two epochs whose scores differ by less than this are the same score
CHECKPOINT_TOLERANCE = 1e-9
HEAD_PREFIX = "head-"
TASK_PREFIX = "task-"


def domain_positions(im_files: Sequence[str]) -> tuple[list[int], list[int]]:
    """Split a materialized union's image list into its head and task positions.

    `prepare_candidate_run` writes each member as `<domain>-<original name>`, so the domain of a position
    is read from the file name rather than guessed from the directory it happens to sit in.
    """

    head: list[int] = []
    task: list[int] = []
    for position, path in enumerate(im_files):
        name = Path(path).name
        if name.startswith(HEAD_PREFIX):
            head.append(position)
        elif name.startswith(TASK_PREFIX):
            task.append(position)
        else:
            raise ValueError(
                f"CANDIDATE_UNION_UNLABELLED: {name} does not declare its camera domain"
            )
    return head, task


def balanced_epoch_order(
    head_positions: Sequence[int],
    task_positions: Sequence[int],
    batch_size: int,
    *,
    seed: int,
    epoch: int,
) -> list[int]:
    """One epoch's positions: 1:1 by camera domain in every batch, deterministic in (seed, epoch).

    Shuffling happens *inside* each domain before the two are interleaved, so the composition is exact
    rather than statistical. A candidate that trains on the head domain alone returns its own order.
    """

    if batch_size <= 0 or batch_size % 2 != 0:
        raise ValueError(
            "CANDIDATE_BATCH_INVALID: a candidate batch must be a positive even number"
        )
    if len(head_positions) != len(task_positions) and task_positions:
        raise ValueError(
            "CANDIDATE_DOMAINS_UNBALANCED: the two camera domains must contribute equally"
        )
    generator = _Random(seed, epoch)
    head_order = list(head_positions)
    task_order = list(task_positions)
    generator.shuffle(head_order)
    generator.shuffle(task_order)
    if not task_order:
        return head_order
    half = batch_size // 2
    order: list[int] = []
    for offset in range(0, len(head_order), half):
        order.extend(head_order[offset : offset + half])
        order.extend(task_order[offset : offset + half])
    return order


class _Random:
    """A tiny deterministic shuffle: reproducible across Python versions and processes."""

    def __init__(self, seed: int, epoch: int) -> None:
        state = (int(seed) * 1_000_003 + int(epoch) * 7919) % (2**32) or 1
        self._state = state

    def _next(self) -> int:
        self._state = (1103515245 * self._state + 12345) % (2**31)
        return self._state

    def shuffle(self, values: list[int]) -> None:
        for index in range(len(values) - 1, 0, -1):
            other = self._next() % (index + 1)
            values[index], values[other] = values[other], values[index]


def two_domain_fitness(head_mask_map: object, task_mask_map: object) -> float:
    """The frozen checkpoint score: half the head cell, half the task cell, both required finite."""

    cells = []
    for name, value in (("head", head_mask_map), ("task", task_mask_map)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError(
                f"CANDIDATE_SCORE_INCOMPLETE: the {name} validation cell is not a finite number"
            )
        cells.append(float(value))
    return 0.5 * cells[0] + 0.5 * cells[1]


def select_checkpoint(
    history: Sequence[tuple[int, float]],
    *,
    candidate_epoch: int,
    candidate_score: float,
) -> bool:
    """Whether `candidate_epoch` should become the saved checkpoint.

    Strictly better wins; an equal score keeps the earlier epoch, which is what the stock trainer does not
    do because it rewrites the best checkpoint whenever the score does not improve.
    """

    if not math.isfinite(float(candidate_score)):
        return False
    for epoch, score in history:
        if abs(float(score) - float(candidate_score)) <= CHECKPOINT_TOLERANCE:
            return int(candidate_epoch) < int(epoch)
    return not history or float(candidate_score) > max(float(score) for _, score in history)


def _mask_map(metrics: object) -> float:
    """The mask mAP50-95 of one validation cell, from an Ultralytics segmentation metrics object."""

    results = getattr(metrics, "results_dict", None)
    if not isinstance(results, Mapping):
        raise ValueError("CANDIDATE_SCORE_INCOMPLETE: the validator returned no results")
    for key in ("metrics/mAP50-95(M)", "metrics/mAP50-95(B)"):
        value = results.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    raise ValueError("CANDIDATE_SCORE_INCOMPLETE: the validator returned no mask mAP")


def _balanced_sampler_class() -> type:
    class _BalancedBatchSampler:
        """Yield the frozen 1:1 batches, reshuffled deterministically once per epoch."""

        def __init__(self, head_positions, task_positions, batch_size, seed, epochs) -> None:
            self.head = list(head_positions)
            self.task = list(task_positions)
            self.batch_size = int(batch_size)
            self.seed = int(seed)
            self.epochs = int(epochs) if epochs and epochs > 0 else 1
            self._epoch = 0

        def __iter__(self) -> Iterator[list[int]]:
            order = balanced_epoch_order(
                self.head,
                self.task,
                self.batch_size,
                seed=self.seed,
                epoch=self._epoch,
            )
            self._epoch += 1
            for offset in range(0, len(order), self.batch_size):
                yield order[offset : offset + self.batch_size]

        def __len__(self) -> int:
            total = len(self.head) + len(self.task)
            return max(1, math.ceil(total / self.batch_size))

    return _BalancedBatchSampler


def main(argv: Sequence[str] | None = None) -> int:
    """Train one candidate and seal the weight it selected."""

    parser = argparse.ArgumentParser(prog="train-candidate")
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parsed = parser.parse_args(argv)

    import yaml
    from ultralytics.models.yolo.segment import SegmentationTrainer

    run_root = parsed.run_root.resolve(strict=True)
    overrides = yaml.safe_load(parsed.training_config.read_text(encoding="utf-8"))
    if not isinstance(overrides, Mapping):
        raise SystemExit("training config must be a mapping")
    if str(overrides.get("device")) != "cuda":
        raise SystemExit("CANDIDATE_DEVICE_INVALID: candidates train on cuda only")
    run_manifest = json.loads((run_root / "run-manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((run_root / "candidate-plan.json").read_text(encoding="utf-8"))
    seed = int(overrides.get("seed", plan["hyperparameters"]["seed"]))
    epochs = int(overrides.get("epochs", plan["epochs"]))

    class CandidateTrainer(SegmentationTrainer):
        def get_dataloader(self, dataset_path, batch_size=16, rank=0, mode="train"):
            if mode != "train":
                return super().get_dataloader(dataset_path, batch_size, rank, mode)
            import torch
            from ultralytics.data.build import InfiniteDataLoader, seed_worker
            from ultralytics.utils import RANK

            dataset = self.build_dataset(dataset_path, mode, batch_size)
            head_positions, task_positions = domain_positions(dataset.im_files)
            sampler_class = _balanced_sampler_class()
            sampler = sampler_class(head_positions, task_positions, batch_size, seed, epochs)
            generator = torch.Generator()
            generator.manual_seed(6148914691236517205 + RANK)
            workers = min(
                os.cpu_count() // max(torch.cuda.device_count(), 1), int(self.args.workers)
            )
            loader = InfiniteDataLoader(
                dataset=dataset,
                batch_sampler=sampler,
                num_workers=workers,
                pin_memory=True,
                collate_fn=getattr(dataset, "collate_fn", None),
                worker_init_fn=seed_worker,
                generator=generator,
            )
            # Ultralytics' training pipeline reads batch_size and len(sampler) off the loader, which a
            # batch-sampler loader leaves unset
            object.__setattr__(loader, "batch_size", batch_size)
            object.__setattr__(loader, "sampler", sampler)
            return loader

        def validate(self):
            from copy import deepcopy

            from ultralytics.models.yolo.segment import SegmentationValidator

            cells = {}
            for domain, val_list in (("head", self._head_val), ("task", self._task_val)):
                args = deepcopy(self.args)
                args.data = str(val_list)
                validator = SegmentationValidator(args=args)
                # validate a copy: the validator mutates the module it is handed (eval/half), which
                # would desynchronise the trainer's EMA for the next epoch
                import copy

                source = self.ema.ema if self.ema else self.model
                validator(model=copy.deepcopy(source))
                cells[domain] = _mask_map(validator.metrics)
            self.fitness = two_domain_fitness(cells["head"], cells["task"])
            self.metrics = dict(cells)
            return self.metrics, self.fitness

        def save_model(self):
            """Keep the checkpoint the frozen rule selects, not the one a pretrained baseline ranks.

            A candidate starts from A's weights, whose recorded `best_fitness` is higher than any early
            candidate epoch, so the stock comparison would never promote an epoch. The selection is made
            here and the selected weights are promoted explicitly.
            """

            import shutil

            epoch = int(self.epoch)
            score = float(self.fitness)
            keep = select_checkpoint(
                list(self._history), candidate_epoch=epoch, candidate_score=score
            )
            if keep:
                self._history.append((epoch, score))
            super().save_model()
            if keep:
                last, best = self.wdir / "last.pt", self.wdir / "best.pt"
                if last.is_file():
                    shutil.copyfile(last, best)
                    self.best_fitness = score

    # the two validation lists the frozen plan declares
    # each validation domain is its own dataset yaml: the score needs both cells measured separately
    head_val = run_root / "val-head.txt"
    task_val = run_root / "val-task.txt"
    if not head_val.is_file() or not task_val.is_file():
        raise SystemExit("CANDIDATE_VALIDATION_MISSING: the run root lacks its validation lists")
    names = overrides.get("names") or {
        index: name
        for index, name in enumerate(plan["recipe"].get("class_names") or ["plastic_cup"])
    }
    domain_yaml = {}
    for domain, val_list in (("head", head_val), ("task", task_val)):
        path = run_root / f"val-{domain}.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "path": str(val_list.parent),
                    "train": str(val_list),
                    "val": str(val_list),
                    "names": names,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        domain_yaml[domain] = path
    trainer = CandidateTrainer(overrides=dict(overrides))
    trainer._head_val = domain_yaml["head"]
    trainer._task_val = domain_yaml["task"]
    trainer._history = []
    trainer.train()
    best = run_root / str(overrides.get("name", "train")) / "weights" / "best.pt"
    if not best.is_file():
        raise SystemExit("CANDIDATE_TRAINING_FAILED: no best checkpoint was written")
    import hashlib

    digest = hashlib.sha256(best.read_bytes()).hexdigest()
    payload = {
        "schema_version": 1,
        "candidate_id": run_manifest["candidate_id"],
        "plan_sha256": run_manifest["plan_sha256"],
        "base_model_sha256": run_manifest["base_model_sha256"],
        "best_weight": str(best.relative_to(run_root)),
        "best_weight_sha256": digest,
        "checkpoint_score": run_manifest["checkpoint_score"],
        "history": [{"epoch": epoch, "score": score} for epoch, score in trainer._history],
        "device": overrides.get("device"),
    }
    temporary = run_root / "candidate-manifest.json.tmp"
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, run_root / "candidate-manifest.json")
    return 0


def _unused(_: Iterable[object]) -> None:  # pragma: no cover - keeps Iterable imported for typing
    return None
