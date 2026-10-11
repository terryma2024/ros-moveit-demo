"""Generate the deterministic V5-T004 YOLO segmentation dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate_yolo_seg_dataset",
        description="Render deterministic RGB and MuJoCo object-ID YOLO-Seg labels",
    )
    parser.add_argument("--config", required=True, type=_absolute_path)
    parser.add_argument("--output-root", required=True, type=_absolute_path)
    parser.add_argument("--generator-commit", required=True)
    parser.add_argument(
        "--geometry-seal",
        type=_absolute_path,
        help="the production-camera seal this dataset must be rendered under (required by the "
        "head-camera profiles)",
    )
    parser.add_argument("--sample-limit", type=_positive_integer)
    parsed = parser.parse_args(arguments)

    from so101_demo.adapters.perception.mujoco_dataset.config import load_dataset_config
    from so101_demo.adapters.perception.mujoco_dataset.generate import generate_dataset

    try:
        geometry_seal = None
        if parsed.geometry_seal is not None:
            geometry_seal = json.loads(parsed.geometry_seal.read_text(encoding="utf-8"))
        config = load_dataset_config(
            parsed.config,
            generator_commit=parsed.generator_commit,
            sample_limit=parsed.sample_limit,
        )
        manifest = generate_dataset(config, parsed.output_root, geometry_seal=geometry_seal)
    except (FileExistsError, OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "failure": str(error)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": "OK",
                "sample_count": manifest["sample_count"],
                "manifest": str(parsed.output_root / "dataset-manifest.json"),
                "promotable": manifest.get("promotable", True),
                "geometry_seal_sha256": manifest.get("geometry_seal_sha256"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
