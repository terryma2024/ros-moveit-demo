"""Collect and calibrate Grounded-SAM on the immutable r3 validation split."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path

from so101_demo.cli.evaluate_grounded_sam_frozen_candidate import _build_runtime
from so101_demo.training.frozen_candidate_evaluation import verify_frozen_candidate_lock
from so101_demo.training.grounded_sam_val_calibration import (
    ValCalibrationError,
    collect_val_raw,
    load_locked_val_dataset,
    load_verified_raw_records,
    select_mask_aware_sam_quality_threshold,
    select_sam_quality_threshold,
    write_calibration_evidence,
    write_mask_aware_calibration_evidence,
)


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _freeze_tree(root: Path) -> dict[str, object]:
    target = Path(root)
    if not target.is_absolute() or target.is_symlink() or not target.is_dir():
        raise ValCalibrationError("EVIDENCE_TREE_INVALID", str(target))
    files = tuple(sorted(path for path in target.rglob("*") if path.is_file()))
    directories = tuple(sorted(path for path in target.rglob("*") if path.is_dir()))
    if any(path.is_symlink() for path in (*files, *directories)):
        raise ValCalibrationError("EVIDENCE_TREE_INVALID", "symlink")
    for path in files:
        path.chmod(0o444)
    for path in reversed(directories):
        path.chmod(0o555)
    target.chmod(0o555)
    entries = [
        {
            "relative_path": path.relative_to(target).as_posix(),
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
            "mode": format(stat.S_IMODE(path.stat().st_mode), "04o"),
        }
        for path in files
    ]
    return {
        "file_count": len(files),
        "directory_count": len(directories) + 1,
        "size_bytes": sum(int(entry["size_bytes"]) for entry in entries),
        "inventory_sha256": hashlib.sha256(
            (json.dumps(entries, sort_keys=True, separators=(",", ":")) + "\n").encode()
        ).hexdigest(),
        "files_mode": "0444",
        "directories_mode": "0555",
    }


def _dataset(arguments: argparse.Namespace):
    return load_locked_val_dataset(
        inventory_path=arguments.val_inventory,
        expected_inventory_sha256=arguments.val_inventory_sha256,
        source_root=arguments.source_root,
        expected_source_manifest_sha256=arguments.source_manifest_sha256,
    )


def _collect(arguments: argparse.Namespace) -> dict[str, object]:
    lock = verify_frozen_candidate_lock(
        arguments.candidate_lock, arguments.candidate_lock_sha256
    )
    dataset = _dataset(arguments)
    model_manifest_sha = str(lock.document["model_bundle"]["manifest_sha256"])
    manifest = collect_val_raw(
        dataset=dataset,
        adapter_factory=lambda root: _build_runtime(lock, root)[0],
        output_root=arguments.output_root,
        run_id=arguments.run_id,
        source_commit=arguments.source_commit,
        model_manifest_sha256=model_manifest_sha,
    )
    frozen = _freeze_tree(arguments.output_root)
    return {
        "status": manifest["status"],
        "output_root": str(arguments.output_root),
        "record_count": manifest["record_count"],
        "record_inventory_sha256": manifest["record_inventory_sha256"],
        "tree": frozen,
    }


def _calibrate(arguments: argparse.Namespace) -> dict[str, object]:
    dataset = _dataset(arguments)
    raw_root = arguments.raw_run_root
    if stat.S_IMODE(raw_root.stat().st_mode) & 0o222:
        raise ValCalibrationError("RAW_RUN_MUTABLE", str(raw_root))
    raw_candidates = load_verified_raw_records(
        raw_root,
        dataset=dataset,
        expected_model_manifest_sha256=arguments.model_manifest_sha256,
        expected_source_commit=arguments.raw_source_commit,
    )
    raw_manifest_sha = _sha256_file(raw_root / "manifest.json")
    selected, points = select_sam_quality_threshold(
        dataset=dataset,
        raw_candidates_by_sample=raw_candidates,
    )
    report = write_calibration_evidence(
        output_root=arguments.output_root,
        dataset=dataset,
        raw_run_root=raw_root,
        raw_manifest_sha256=raw_manifest_sha,
        source_commit=arguments.source_commit,
        selected=selected,
        points=points,
    )
    frozen = _freeze_tree(arguments.output_root)
    return {
        "status": "VALID",
        "output_root": str(arguments.output_root),
        "selected_sam_quality": report["selected_sam_quality"],
        "selected": report["selected"],
        "tree": frozen,
    }


def _calibrate_mask_aware(arguments: argparse.Namespace) -> dict[str, object]:
    dataset = _dataset(arguments)
    raw_root = arguments.raw_run_root
    if stat.S_IMODE(raw_root.stat().st_mode) & 0o222:
        raise ValCalibrationError("RAW_RUN_MUTABLE", str(raw_root))
    raw_candidates = load_verified_raw_records(
        raw_root,
        dataset=dataset,
        expected_model_manifest_sha256=arguments.model_manifest_sha256,
        expected_source_commit=arguments.raw_source_commit,
    )
    raw_manifest_sha = _sha256_file(raw_root / "manifest.json")
    selected, points = select_mask_aware_sam_quality_threshold(
        dataset=dataset,
        raw_candidates_by_sample=raw_candidates,
        raw_evidence_root=raw_root,
    )
    report = write_mask_aware_calibration_evidence(
        output_root=arguments.output_root,
        dataset=dataset,
        raw_run_root=raw_root,
        raw_manifest_sha256=raw_manifest_sha,
        source_commit=arguments.source_commit,
        selected=selected,
        points=points,
    )
    frozen = _freeze_tree(arguments.output_root)
    return {
        "status": "VALID",
        "output_root": str(arguments.output_root),
        "selected_sam_quality": report["selected_sam_quality"],
        "selected": report["selected"],
        "tree": frozen,
    }


def _common_dataset(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--val-inventory", required=True, type=_absolute_path)
    parser.add_argument("--val-inventory-sha256", required=True)
    parser.add_argument("--source-root", required=True, type=_absolute_path)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--output-root", required=True, type=_absolute_path)
    parser.add_argument("--source-commit", required=True)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="grounded_sam_val_calibration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect")
    _common_dataset(collect)
    collect.add_argument("--candidate-lock", required=True, type=_absolute_path)
    collect.add_argument("--candidate-lock-sha256", required=True)
    collect.add_argument("--run-id", required=True)
    calibrate = subparsers.add_parser("calibrate")
    _common_dataset(calibrate)
    calibrate.add_argument("--raw-run-root", required=True, type=_absolute_path)
    calibrate.add_argument("--raw-source-commit", required=True)
    calibrate.add_argument("--model-manifest-sha256", required=True)
    mask_aware = subparsers.add_parser("calibrate-mask-aware")
    _common_dataset(mask_aware)
    mask_aware.add_argument("--raw-run-root", required=True, type=_absolute_path)
    mask_aware.add_argument("--raw-source-commit", required=True)
    mask_aware.add_argument("--model-manifest-sha256", required=True)
    parsed = parser.parse_args(arguments)
    try:
        if parsed.command == "collect":
            result = _collect(parsed)
        elif parsed.command == "calibrate":
            result = _calibrate(parsed)
        else:
            result = _calibrate_mask_aware(parsed)
    except (OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {"status": "ERROR", "failure": str(error)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
