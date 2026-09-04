"""Prepare deterministic Grounding DINO cup-training inventories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.training.grounding_dino_dataset import (
    GroundingDinoDatasetError,
    convert_dataset,
)


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prepare_grounding_dino_dataset",
        description="Convert sealed synthetic YOLO-Seg data into DINO box inventories",
    )
    parser.add_argument("--source-root", required=True, type=_absolute_path)
    parser.add_argument("--output-root", required=True, type=_absolute_path)
    parser.add_argument("--source-archive-sha256", required=True)
    parser.add_argument("--converter-commit", required=True)
    parsed = parser.parse_args(arguments)
    try:
        hashes = convert_dataset(
            parsed.source_root,
            parsed.output_root,
            source_archive_sha256=parsed.source_archive_sha256,
            converter_commit=parsed.converter_commit,
        )
    except (GroundingDinoDatasetError, OSError) as error:
        print(json.dumps({"failure": str(error), "status": "ERROR"}, sort_keys=True))
        return 1
    print(json.dumps({"status": "OK", **hashes}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
