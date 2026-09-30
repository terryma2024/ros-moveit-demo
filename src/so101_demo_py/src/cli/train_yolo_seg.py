"""Run one reproducible Ultralytics segmentation fine-tuning job."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from ..adapters.perception.yolo_training import prepare_training_run


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _fraction(value: str) -> float:
    parsed = float(value)
    if not 0.0 < parsed <= 1.0:
        raise argparse.ArgumentTypeError("must be in (0, 1]")
    return parsed


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="train_yolo_seg",
        description="Prepare immutable YOLO-Seg runtime YAML and start fine-tuning",
    )
    parser.add_argument("--contract", type=_path)
    parser.add_argument("--dataset", type=_path)
    parser.add_argument("--base-model", required=True, type=_path)
    parser.add_argument("--output", required=True, type=_path)
    parser.add_argument("--run-name", default="train")
    parser.add_argument("--epochs", type=_positive_integer)
    parser.add_argument("--fraction", type=_fraction)
    # Head Search candidates: one candidate id, the sealed head manifest and the task manifest, plus the
    # roots those manifests describe. The plan the candidate implies is written into the output root.
    parser.add_argument("--candidate", choices=("B", "C"))
    parser.add_argument("--training-contract", type=_path)
    parser.add_argument("--head-manifest", type=_path)
    parser.add_argument("--task-manifest", type=_path)
    parser.add_argument("--head-dataset-root", type=_path)
    parser.add_argument("--task-dataset-root", type=_path)
    parsed = parser.parse_args(arguments)

    if parsed.candidate is not None:
        if parsed.epochs is not None or parsed.fraction is not None:
            print(
                "training input error: --epochs and --fraction cannot be combined with --candidate; "
                "the candidate's epoch count and data union are frozen in its contract and plan",
                file=sys.stderr,
            )
            return 2
        missing = [
            name
            for name, value in (
                ("--training-contract", parsed.training_contract),
                ("--head-manifest", parsed.head_manifest),
                ("--task-manifest", parsed.task_manifest),
                ("--head-dataset-root", parsed.head_dataset_root),
                ("--task-dataset-root", parsed.task_dataset_root),
            )
            if value is None
        ]
        if missing:
            print(f"training input error: --candidate needs {', '.join(missing)}", file=sys.stderr)
            return 2
        try:
            import hashlib
            import json

            from so101_demo.act.head_search_training import build_candidate_plan
            from so101_demo.adapters.perception.yolo_training import prepare_candidate_run

            plan = build_candidate_plan(
                parsed.candidate,
                head=json.loads(parsed.head_manifest.read_text(encoding="utf-8")),
                task=json.loads(parsed.task_manifest.read_text(encoding="utf-8")),
                contract=parsed.training_contract,
                # the candidate plan must bind the very weights it starts from
                base_model_sha256=hashlib.sha256(parsed.base_model.read_bytes()).hexdigest(),
            )
            prepared = prepare_candidate_run(
                plan=plan,
                contract_path=parsed.training_contract,
                # the run re-reads each manifest from disk and compares it with the frozen digest
                head_manifest_path=parsed.head_manifest,
                task_manifest_path=parsed.task_manifest,
                head_dataset_root=parsed.head_dataset_root,
                task_dataset_root=parsed.task_dataset_root,
                base_model_path=parsed.base_model,
                output_root=parsed.output,
                run_name=parsed.run_name,
            )
        except (FileExistsError, OSError, ValueError) as error:
            print(f"training input error: {error}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {"plan_sha256": plan.sha256, "run_manifest": str(prepared.run_manifest)},
                sort_keys=True,
            )
        )
        environment = os.environ.copy()
        environment["YOLO_OFFLINE"] = "true"
        result = subprocess.run(
            [
                sys.executable,
                str(prepared.trainer_script),
                "--run-root",
                str(prepared.output_root),
                "--training-config",
                str(prepared.training_config),
            ],
            check=False,
            env=environment,
        )
        if result.returncode != 0:
            print(
                f"candidate training failed with exit code {result.returncode}; no candidate manifest "
                "was written",
                file=sys.stderr,
            )
        return result.returncode

    if parsed.contract is None or parsed.dataset is None:
        print(
            "training input error: --contract and --dataset are required without --candidate",
            file=sys.stderr,
        )
        return 2
    try:
        prepared = prepare_training_run(
            contract_path=parsed.contract,
            dataset_yaml_path=parsed.dataset,
            base_model_path=parsed.base_model,
            output_root=parsed.output,
            run_name=parsed.run_name,
            epochs_override=parsed.epochs,
            fraction=parsed.fraction,
        )
    except (FileExistsError, OSError, ValueError) as error:
        print(f"training input error: {error}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["YOLO_OFFLINE"] = "true"
    result = subprocess.run(
        ["yolo", "segment", "train", f"cfg={prepared.training_config}"],
        check=False,
        env=environment,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
