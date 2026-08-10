#!/usr/bin/env python3
"""Print the deterministic URDF/MJCF parity report as one JSON document."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from so101_mujoco_demo_py.model_parity import check_model_parity  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = check_model_parity(args.config)
        code = 0 if not report["validation_errors"] else 1
    except Exception as error:
        report = {"validation_errors": [f"parity failed: {type(error).__name__}: {error}"]}
        code = 1
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
