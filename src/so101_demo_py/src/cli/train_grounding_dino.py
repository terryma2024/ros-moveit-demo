"""Run one offline CUDA-only Grounding DINO fine-tuning job."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="train_grounding_dino")
    parser.add_argument("--contract", required=True, type=_absolute_path)
    parser.add_argument("--train-inventory", required=True, type=_absolute_path)
    parser.add_argument("--val-inventory", required=True, type=_absolute_path)
    parser.add_argument("--train-images", required=True, type=_absolute_path)
    parser.add_argument("--val-images", required=True, type=_absolute_path)
    parser.add_argument("--base-model", required=True, type=_absolute_path)
    parser.add_argument("--output", required=True, type=_absolute_path)
    parser.add_argument("--mode", required=True, choices=("smoke", "formal"))
    parser.add_argument("--training-commit", required=True)
    parser.add_argument("--resume-checkpoint", type=_absolute_path)
    parsed = parser.parse_args(arguments)

    from so101_demo.training.grounding_dino_runtime import run_training

    try:
        result = run_training(
            contract_path=parsed.contract,
            train_inventory=parsed.train_inventory,
            val_inventory=parsed.val_inventory,
            train_images=parsed.train_images,
            val_images=parsed.val_images,
            base_model=parsed.base_model,
            output_root=parsed.output,
            mode=parsed.mode,
            training_commit=parsed.training_commit,
            resume_checkpoint=parsed.resume_checkpoint,
        )
    except (FileExistsError, OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"failure": str(error), "status": "ERROR"}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
