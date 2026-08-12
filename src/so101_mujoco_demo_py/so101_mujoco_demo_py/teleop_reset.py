"""CLI owner for Teleop-triggered qualified MuJoCo reset transactions."""

from __future__ import annotations

import argparse
import json
import sys

from .teleop_runtime import transactional_reset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teleop_reset")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--keyframe", default="task_start")
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    try:
        receipt = transactional_reset(options.session_id, keyframe=options.keyframe)
    except Exception as error:
        print(f"failure=TRANSACTIONAL_RESET_FAILED\nfailure_message={error}")
        return 1
    print(
        json.dumps(
            {
                "status": "SUCCEEDED",
                "simulation_session_id": receipt.simulation_session_id,
                "preserve_session": True,
                "old_epoch": receipt.old_epoch,
                "new_epoch": receipt.new_epoch,
                "simulation_step": receipt.simulation_step,
                "keyframe": receipt.keyframe,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
