"""Fine-tune the Teacher YOLO11n-Seg weights on an indoor dataset (goal 11). Report only: the result is never installed as the Teacher's weights.

    python -m so101_demo.cli.finetune_indoor_yolo --base-model best.pt --dataset D/dataset.yaml --output /abs/run [--epochs 40]

Run it in the `so101-yolo11n-seg-train` image (ultralytics 8.4.115, torch 2.13 cu130) on the GPU; the arguments are fixed here so that the run is
reproducible: seed 0, deterministic, AdamW with a small learning rate, every layer trainable, ultralytics' default augmentation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _absolute(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def parse(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="finetune_indoor_yolo", description=__doc__.split("\n")[0])
    parser.add_argument("--base-model", required=True, type=_absolute)
    parser.add_argument("--dataset", required=True, type=_absolute)
    parser.add_argument("--output", required=True, type=_absolute)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--lr0", type=float, default=0.0005)
    parser.add_argument("--device", default="0")
    parsed = parser.parse_args(arguments)
    if parsed.output.exists():
        parser.error(f"output exists: {parsed.output}")
    return parsed


def train_arguments(parsed: argparse.Namespace) -> dict:
    return {"task": "segment", "data": str(parsed.dataset), "epochs": parsed.epochs, "imgsz": 640, "batch": parsed.batch, "seed": 0,
            "deterministic": True, "optimizer": "AdamW", "lr0": parsed.lr0, "lrf": 0.1, "freeze": 0, "patience": 15, "close_mosaic": 5,
            "workers": 4, "device": parsed.device, "project": str(parsed.output.parent), "name": parsed.output.name, "exist_ok": False,
            "plots": False, "verbose": True}


def anchored_dataset_yaml(dataset: Path) -> str:
    """The dataset yaml with `path: .` anchored to the dataset's own directory (ultralytics resolves `.` against the cwd)."""
    lines = dataset.read_text().splitlines()
    return "\n".join(f"path: {dataset.parent}" if line.strip() == "path: ." else line for line in lines) + "\n"


def main(arguments: list[str] | None = None) -> int:
    parsed = parse(arguments)
    from ultralytics import YOLO

    anchored = parsed.output.parent / f"{parsed.output.name}.dataset.yaml"
    anchored.write_text(anchored_dataset_yaml(parsed.dataset))
    model = YOLO(str(parsed.base_model))
    model.train(**{**train_arguments(parsed), "data": str(anchored)})
    print(json.dumps({"status": "OK", "best": str(parsed.output / "weights" / "best.pt")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
