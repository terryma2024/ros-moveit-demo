"""Score a Teacher YOLO-Seg weights file on the sets of an indoor dataset (goal 11): detection, ambiguity, mask IoU, centre error, cup xy.

    python -m so101_demo.cli.evaluate_indoor_yolo --weights W.pt --dataset-root D --sets val test eval_dark_nominal --output R.json

Runs the model the way production does (RGB frame, BGR to Ultralytics, `conf` = the Teacher's 0.50 confidence threshold, image size 640);
only the masks come back at full resolution (`retina_masks`). Needs ultralytics and torch (the `so101-yolo11n-seg-train` image).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from so101_demo.act import indoor_yolo_eval as ev

THRESHOLD = 0.50
IMGSZ = 640


def load_frames(root: Path, directory: str) -> list:
    frames = []
    for image in sorted((root / "images" / directory).glob("*.png")):
        truth = json.loads((root / "truth" / directory / f"{image.stem}.json").read_text())
        stored = np.load(root / "depth" / directory / f"{image.stem}.npz")
        camera = truth["camera"]
        mask = np.unpackbits(stored["mask_packed"])[:camera["height"] * camera["width"]].reshape(camera["height"], camera["width"]).astype(bool)
        frames.append({"sample_id": image.stem, "rgb": ev.read_png_rgb8(image), "truth": mask,
                       "depth": stored["depth_mm"].astype(np.float32) / 1000.0, "camera": camera, "cup_xy": truth["cup_xy"],
                       "cup_hidden": bool(truth.get("cup_hidden", False))})
    return frames


def load_detector(*, weights: Path, device: str, imgsz: int = IMGSZ, threshold: float = THRESHOLD):
    from ultralytics import YOLO

    model = YOLO(str(weights))

    def predict(rgb):
        result = model.predict(source=np.ascontiguousarray(rgb[:, :, ::-1]), imgsz=imgsz, device=device, conf=threshold,
                               retina_masks=True, verbose=False)[0]
        if result.masks is None:
            return []
        return [(float(confidence), mask.cpu().numpy() > 0.5) for confidence, mask in zip(result.boxes.conf.cpu().numpy(), result.masks.data)]

    return predict


def evaluate(root: Path, sets: list, detector, *, threshold: float) -> dict:
    report = {"threshold": threshold, "sets": {}}
    for name in sets:
        frames = load_frames(root, name)
        rows = ev.score_frames(frames, detector, threshold=threshold)
        for frame, row in zip(frames, rows):
            row["sample_id"] = frame["sample_id"]
        groups = {}
        for row in rows:
            groups.setdefault(row["sample_id"].rsplit("-", 1)[0], []).append(row)
        report["sets"][name] = {"summary": ev.summarise(rows), "groups": {key: ev.summarise(value) for key, value in sorted(groups.items())},
                                "rows": rows}
    return report


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluate_indoor_yolo", description=__doc__.split("\n")[0])
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--sets", nargs="+", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    parsed = parser.parse_args(arguments)
    if parsed.output.exists():
        parser.error(f"output exists: {parsed.output}")
    detector = load_detector(weights=parsed.weights, device=parsed.device, threshold=parsed.threshold)
    report = evaluate(parsed.dataset_root, parsed.sets, detector, threshold=parsed.threshold)
    report["weights"] = str(parsed.weights)
    parsed.output.parent.mkdir(parents=True, exist_ok=True)
    parsed.output.write_text(json.dumps(report, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({name: value["summary"] for name, value in report["sets"].items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
