"""Run one reproducible Ultralytics segmentation fine-tuning job."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from ..adapters.perception.yolo_training import prepare_training_run


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _fraction(value: str) -> float:
    parsed = float(value)
    if not 0.0 < parsed <= 1.0:
        raise argparse.ArgumentTypeError("must be in (0, 1]")
    return parsed


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="train_yolo_seg",
        description="Prepare immutable YOLO-Seg runtime YAML and start fine-tuning",
    )
    parser.add_argument("--contract", required=True, type=_path)
    parser.add_argument("--dataset", required=True, type=_path)
    parser.add_argument("--base-model", required=True, type=_path)
    parser.add_argument("--output", required=True, type=_path)
    parser.add_argument("--run-name", default="train")
    parser.add_argument("--epochs", type=_positive_integer)
    parser.add_argument("--fraction", type=_fraction)
    parsed = parser.parse_args(arguments)

    try:
        prepared = prepare_training_run(
            contract_path=parsed.contract,
            dataset_yaml_path=parsed.dataset,
            base_model_path=parsed.base_model,
            output_root=parsed.output,
            run_name=parsed.run_name,
            epochs_override=parsed.epochs,
            fraction=parsed.fraction,
        )
    except (FileExistsError, OSError, ValueError) as error:
        print(f"training input error: {error}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["YOLO_OFFLINE"] = "true"
    result = subprocess.run(
        ["yolo", "segment", "train", f"cfg={prepared.training_config}"],
        check=False,
        env=environment,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
