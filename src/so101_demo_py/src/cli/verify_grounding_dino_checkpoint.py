"""Reload a complete Grounding DINO checkpoint in a fresh CUDA process."""

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
    parser = argparse.ArgumentParser(prog="verify_grounding_dino_checkpoint")
    parser.add_argument("--contract", required=True, type=_absolute_path)
    parser.add_argument("--checkpoint", required=True, type=_absolute_path)
    parser.add_argument("--image", required=True, type=_absolute_path)
    parser.add_argument("--output", required=True, type=_absolute_path)
    parsed = parser.parse_args(arguments)

    from so101_demo.training.grounding_dino_runtime import (
        verify_checkpoint_in_fresh_process,
    )

    try:
        result = verify_checkpoint_in_fresh_process(
            contract_path=parsed.contract,
            checkpoint=parsed.checkpoint,
            image=parsed.image,
            output=parsed.output,
        )
    except (FileExistsError, OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"failure": str(error), "status": "ERROR"}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
