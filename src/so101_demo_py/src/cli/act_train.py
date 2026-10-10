"""Task 12 CLI: export a verified dataset and run one owned training job.

The order is deliberate. The dependency lock must be resolved and the config valid before anything is
written; the dataset is exported from the campaign index (never by scanning episode directories) into a
sibling of `--output`; the owner lease is bound to the dataset and config hashes; and only then does the
trainer run. The production trainer fails closed until the training interpreter and LeRobot adapter exist.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import subprocess
from pathlib import Path

from so101_demo.act.bundle import export_dataset, resolve_committed_episodes
from so101_demo.act.training import attach_episode_content, train_act
from so101_demo.act.training_config import load_training_config
from so101_demo.act.training_requirements import require_resolved_requirements

_SOURCE_ROOT = Path(__file__).resolve().parents[2]          # src/so101_demo_py in the source tree (config/ is its sibling of src/)
_LOCK_RELATIVE = Path("config") / "act" / "requirements.lock"


def default_requirements_lock() -> Path:
    """The lock beside the source tree, else the installed share directory (the pattern the other CLIs use)."""

    source = _SOURCE_ROOT / _LOCK_RELATIVE
    if source.is_file():
        return source
    try:
        from ament_index_python.packages import get_package_share_directory
        installed = Path(get_package_share_directory("so101_demo_py")) / _LOCK_RELATIVE
    except Exception:                      # no ament index in the training interpreter: the source path is the answer
        return source
    return installed if installed.is_file() else source


REQUIREMENTS_LOCK = default_requirements_lock()


def _trainer(_config, _dataset, _output, *, requirements_sha256=None, backbone_weights=None):
    """Train in the training interpreter, where the pinned dependencies live.

    ``requirements_sha256`` is the digest of the resolved lock this run validated; it is the provenance of the weights."""

    try:
        import torch  # noqa: F401
    except ImportError as error:
        raise ValueError("TRAINING_INTERPRETER_REQUIRED") from error
    try:
        from so101_demo.adapters.act.lerobot import train_act_bundle
    except ImportError as error:
        raise ValueError("TRAINING_ADAPTER_UNAVAILABLE") from error
    return train_act_bundle(_config, _dataset, _output, requirements_sha256=requirements_sha256,
                            backbone_weights=backbone_weights)


class ProcessTableArbiter:
    """IDLE only when no process holds a CUDA compute context (`nvidia-smi --query-compute-apps`); anything else is BUSY.

    This is the arbiter the CLI uses for a local training run: it answers from the GPU's own process table and fails closed when that
    table cannot be read. ``runner()`` returns the query's stdout."""

    def __init__(self, runner=None) -> None:
        self.runner = runner or self._nvidia_smi

    @staticmethod
    def _nvidia_smi() -> str:
        return subprocess.run(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], check=True,
                              capture_output=True, text=True, timeout=15).stdout

    def state(self) -> str:
        try:
            listing = self.runner()
        except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
            raise ValueError("TRAINING_ARBITER_UNAVAILABLE") from error
        return "BUSY" if str(listing).strip() else "IDLE"


def _process_identity() -> dict:
    """This process as `TrainingRunOwner` pins it: pid and the start time in clock ticks (field 22 of /proc/self/stat)."""

    import os

    stat = Path("/proc/self/stat").read_text()
    fields = stat[stat.rindex(")") + 2:].split()          # fields after the command name, which may contain spaces
    return {"pid": os.getpid(), "started_ticks": int(fields[19])}


def local_owner_factory(gpu_binding: Path, run_root: Path, *, arbiter=None, identity=None):
    """The CUDA owner-lease factory `act_train` uses: ``factory(dataset_sha256=, config_sha256=) -> owner``.

    The owner is `TrainingRunOwner.acquire` over ``run_root`` with the GPU binding document (`--gpu-binding`: device, binding_id,
    leases) as the lease, so a binding that lists collection, broker or training leases, a busy GPU, or a run root already owned
    by another identity refuses before any training starts."""

    from so101_demo.act.training_owner import TrainingRunOwner

    def factory(*, dataset_sha256: str, config_sha256: str) -> dict:
        try:
            lease = json.loads(Path(gpu_binding).read_bytes())
        except (OSError, ValueError) as error:
            raise ValueError("TRAINING_GPU_LEASE_INVALID") from error
        root = Path(run_root)
        root.mkdir(parents=True, exist_ok=True)
        owner = TrainingRunOwner(arbiter=arbiter or ProcessTableArbiter(), identity=identity or _process_identity)
        return owner.acquire(run_root=root.resolve(), dataset_sha256=dataset_sha256, config_sha256=config_sha256, gpu_lease=lease)

    return factory


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
    parser.add_argument("--backbone-weights", type=Path, default=None,
                        help="local pretrained backbone file; its sha256 must equal training.pretrained_backbone.sha256")
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
    if owner_factory is None:
        owner_factory = local_owner_factory(args.gpu_binding, args.output.with_name(args.output.name + ".run"))
    owner = _owner(args, dataset_sha256, config_sha256, args.gpu_binding, owner_factory)
    if trainer is None:
        lock_sha256 = hashlib.sha256(Path(requirements_path or REQUIREMENTS_LOCK).read_bytes()).hexdigest()
        trainer = functools.partial(_trainer, requirements_sha256=lock_sha256, backbone_weights=args.backbone_weights)
    outcome = train_act(config=config, requirements=requirements, dataset=dataset, owner=owner,
                        output=args.output, trainer=trainer)
    print(json.dumps({"status": outcome["status"], "episode_count": outcome["episode_count"],
                      "dataset": str(dataset), "bundle": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
