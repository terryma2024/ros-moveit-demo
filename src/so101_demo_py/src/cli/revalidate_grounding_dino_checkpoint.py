"""Fresh-reload one immutable Grounding DINO checkpoint on frozen val."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _freeze_tree(root: Path) -> dict[str, object]:
    files = tuple(sorted(path for path in root.rglob("*") if path.is_file()))
    directories = tuple(sorted(path for path in root.rglob("*") if path.is_dir()))
    if root.is_symlink() or any(path.is_symlink() for path in (*files, *directories)):
        raise RuntimeError("EVIDENCE_TREE_INVALID")
    for path in files:
        path.chmod(0o444)
    for path in reversed(directories):
        path.chmod(0o555)
    root.chmod(0o555)
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256_file(path),
            "size": path.stat().st_size,
            "mode": format(stat.S_IMODE(path.stat().st_mode), "04o"),
        }
        for path in files
    ]
    return {
        "file_count": len(files),
        "directory_count": len(directories) + 1,
        "size_bytes": sum(int(entry["size"]) for entry in entries),
        "inventory_sha256": hashlib.sha256(
            (json.dumps(entries, sort_keys=True, separators=(",", ":")) + "\n").encode()
        ).hexdigest(),
        "files_mode": "0444",
        "directories_mode": "0555",
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="revalidate_grounding_dino_checkpoint")
    parser.add_argument("--contract", required=True, type=_absolute_path)
    parser.add_argument("--checkpoint", required=True, type=_absolute_path)
    parser.add_argument("--val-inventory", required=True, type=_absolute_path)
    parser.add_argument("--val-images", required=True, type=_absolute_path)
    parser.add_argument("--output-root", required=True, type=_absolute_path)
    parser.add_argument("--source-commit", required=True)
    parsed = parser.parse_args(arguments)

    from so101_demo.training.saved_checkpoint_revalidation import evaluate_saved_checkpoint

    try:
        report = evaluate_saved_checkpoint(
            contract_path=parsed.contract,
            checkpoint_root=parsed.checkpoint,
            val_inventory=parsed.val_inventory,
            val_images=parsed.val_images,
            output_root=parsed.output_root,
            source_commit=parsed.source_commit,
        )
        tree = _freeze_tree(parsed.output_root)
        result = {
            "status": "VALID",
            "epoch": report["epoch"],
            "selected": report["selected"],
            "elapsed_ms": report["elapsed_ms"],
            "output_root": str(parsed.output_root),
            "tree": tree,
        }
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "failure": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
