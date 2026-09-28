"""Task 12A CLI: evaluate a frozen bundle on the Offline Test split, read-only.

This runs in the training interpreter, never in the ROS environment, and it drives no controller. The
policy loader is injected; the production path deliberately fails closed until the LeRobot adapter that
constructs it exists, rather than reaching for a model by import path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.act.offline_evaluation import evaluate_offline


def _policy_loader(bundle: dict):
    """Load the trained model in the training interpreter, where the pinned dependencies live."""

    try:
        import torch  # noqa: F401  (the training interpreter is the only one that has it)
    except ImportError as error:
        raise ValueError("OFFLINE_EVALUATION_TRAINING_INTERPRETER_REQUIRED") from error
    try:
        from so101_demo.adapters.act.lerobot import build_policy_from_bundle
    except ImportError as error:
        raise ValueError("OFFLINE_EVALUATION_LOADER_UNAVAILABLE") from error
    return build_policy_from_bundle(bundle)


def main(argv: list[str] | None = None, *, policy_loader=None) -> int:
    parser = argparse.ArgumentParser(prog="act_offline_evaluate", description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    document = evaluate_offline(args.manifest, args.bundle, args.freeze, args.output,
                                policy_loader=policy_loader or _policy_loader)
    print(json.dumps({"episode_count": document["episode_count"],
                      "valid_targets": document["valid_targets"],
                      "mean_mae_rad": document["mean_mae_rad"],
                      "byte_weighted": document["byte_weighted"],
                      "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
