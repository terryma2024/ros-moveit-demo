"""Prepare the fixed immutable Grounded DINO + SAM2 model bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.adapters.perception.model_bundle import build_model_bundle


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _snapshot_download(**kwargs: str) -> str:
    from huggingface_hub import snapshot_download

    return str(snapshot_download(**kwargs))


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prepare_grounded_sam_bundle",
        description="Build the fixed immutable Grounded DINO + SAM2 model bundle",
    )
    parser.add_argument("--config", required=True, type=_absolute_path)
    parser.add_argument("--output", required=True, type=_absolute_path)
    parsed = parser.parse_args(arguments)
    try:
        digest = build_model_bundle(parsed.config, parsed.output, _snapshot_download)
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "failure": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"manifest_sha256": digest, "status": "OK"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
