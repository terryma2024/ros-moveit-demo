"""Task 12 CLI: export a verified dataset and run one owned training job.

The order is deliberate. The dependency lock must be resolved and the config valid before anything is
written; the dataset is exported from the campaign index (never by scanning episode directories) into a
sibling of `--output`; the owner lease is bound to the dataset and config hashes; and only then does the
trainer run. The production trainer fails closed until the training interpreter and LeRobot adapter exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from so101_demo.act.bundle import export_dataset, resolve_committed_episodes
from so101_demo.act.training import attach_episode_content, train_act
from so101_demo.act.training_config import load_training_config
from so101_demo.act.training_requirements import require_resolved_requirements

_PACKAGE = Path(__file__).resolve().parents[1]
REQUIREMENTS_LOCK = _PACKAGE / "config" / "act" / "requirements.lock"


def _trainer(_config, _dataset, _output):
    """Train in the training interpreter, where the pinned dependencies live."""

    try:
        import torch  # noqa: F401
    except ImportError as error:
        raise ValueError("TRAINING_INTERPRETER_REQUIRED") from error
    try:
        from so101_demo.adapters.act.lerobot import train_act_bundle
    except ImportError as error:
        raise ValueError("TRAINING_ADAPTER_UNAVAILABLE") from error
    return train_act_bundle(_config, _dataset, _output)


def _owner(argv, dataset_sha256, config_sha256, gpu_binding, owner_factory):
    if owner_factory is not None:
        return owner_factory(dataset_sha256=dataset_sha256, config_sha256=config_sha256)
    raise ValueError(f"TRAINING_OWNER_UNAVAILABLE: {gpu_binding}")


def main(argv: list[str] | None = None, *, trainer=None, owner_factory=None,
         requirements_path=None) -> int:
    parser = argparse.ArgumentParser(prog="act_train", description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--campaign-index", type=Path, required=True)
    parser.add_argument("--gpu-binding", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", required=True)
    args = parser.parse_args(argv)

    if args.device != "cuda":
        # the plan's training lease is CUDA-only; there is no CPU path to fall back to
        raise ValueError("TRAINING_DEVICE_INVALID")
    config = load_training_config(args.config)
    # the lock lives beside the installed config, so its path is supplied the way the repo's other
    # loaders supply a package share; the module constant is only the source-tree default
    requirements = require_resolved_requirements(requirements_path or REQUIREMENTS_LOCK)
    manifest = json.loads(args.manifest.read_bytes())
    committed = attach_episode_content(
        resolve_committed_episodes(manifest=manifest, campaign_index=args.campaign_index),
        root=args.campaign_index.parent)
    dataset = args.output.with_name(args.output.name + ".dataset")
    if args.output.exists() or dataset.exists():
        raise ValueError("TRAINING_OUTPUT_EXISTS")
    export_dataset(committed, dataset,
                   source_manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                   campaign_index_sha256=hashlib.sha256(args.campaign_index.read_bytes()).hexdigest())
    dataset_sha256 = hashlib.sha256((dataset / "export-manifest.json").read_bytes()).hexdigest()
    config_sha256 = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    owner = _owner(args, dataset_sha256, config_sha256, args.gpu_binding, owner_factory)
    outcome = train_act(config=config, requirements=requirements, dataset=dataset, owner=owner,
                        output=args.output, trainer=trainer or _trainer)
    print(json.dumps({"status": outcome["status"], "episode_count": outcome["episode_count"],
                      "dataset": str(dataset), "bundle": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
