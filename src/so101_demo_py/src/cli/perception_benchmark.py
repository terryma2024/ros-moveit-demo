"""Fail-closed command line entry point for the perception benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Sequence

from so101_demo.adapters.perception.model_runtime import ModelSetupError
from so101_demo.cli.benchmark.aggregate import _handle_aggregate, _handle_verify_evidence
from so101_demo.cli.benchmark.assets import (
    _handle_inspect_archive,
    _handle_prepare_dataset,
    _handle_unlock_test,
    _handle_verify_assets,
)
from so101_demo.cli.benchmark.calibrate import _handle_calibrate
from so101_demo.cli.benchmark.collect import _handle_collect
from so101_demo.cli.benchmark.common import _MODELS, BenchmarkError
from so101_demo.cli.benchmark.dry_run import _handle_dry_run
from so101_demo.perception_benchmark.calibration.contracts import CalibrationError
from so101_demo.perception_benchmark.contracts import (
    RunKind,
)
from so101_demo.perception_benchmark.dataset.contracts import DatasetVerificationError


def _add_dataset_anchors(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset-inventory", type=Path, required=True)
    parser.add_argument("--dataset-archive-sha256", required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--test-access-event-sha256")
    parser.add_argument("--sealed-member-inventory-sha256")
    parser.add_argument("--yolo-lock-sha256")
    parser.add_argument("--grounded-sam-lock-sha256")
    parser.add_argument("--test-access-log", type=Path)


def _add_model_assets(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--weights-sha256")
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--manifest-sha256")


def _add_frozen_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="perception_benchmark")
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify-assets")
    _add_frozen_config(verify)
    verify.add_argument("--model", choices=_MODELS, required=True)
    _add_model_assets(verify)
    verify.set_defaults(handler=_handle_verify_assets)

    inspect = commands.add_parser("inspect-archive")
    _add_frozen_config(inspect)
    inspect.add_argument("--archive", type=Path, required=True)
    inspect.add_argument("--expected-sha256", required=True)
    inspect.add_argument("--sealed-member-inventory", type=Path, required=True)
    inspect.set_defaults(handler=_handle_inspect_archive)

    prepare = commands.add_parser("prepare-dataset")
    _add_frozen_config(prepare)
    prepare.add_argument("--archive", type=Path, required=True)
    prepare.add_argument("--expected-sha256", required=True)
    prepare.add_argument("--split", choices=("val",), required=True)
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.set_defaults(handler=_handle_prepare_dataset)

    unlock = commands.add_parser("unlock-test")
    _add_frozen_config(unlock)
    unlock.add_argument("--archive", type=Path, required=True)
    unlock.add_argument("--expected-sha256", required=True)
    unlock.add_argument("--sealed-member-inventory", type=Path, required=True)
    unlock.add_argument("--yolo-threshold-lock", type=Path, required=True)
    unlock.add_argument("--grounded-sam-threshold-lock", type=Path, required=True)
    unlock.add_argument("--access-log", type=Path, required=True)
    unlock.add_argument("--output-root", type=Path, required=True)
    unlock.set_defaults(handler=_handle_unlock_test)

    dry = commands.add_parser("dry-run")
    dry.add_argument("--config", type=Path, required=True)
    dry.add_argument("--output-root", type=Path, required=True)
    dry.add_argument("--adapter-fixture", type=Path)
    dry.add_argument("--platform", choices=("macos", "linux"))
    dry.add_argument("--device", choices=("mps", "cuda"))
    dry.add_argument("--dtype")
    dry.add_argument("--dataset-inventory", type=Path)
    dry.add_argument("--dataset-archive-sha256")
    dry.add_argument("--inventory-sha256")
    dry.add_argument("--weights", type=Path)
    dry.add_argument("--weights-sha256")
    dry.add_argument("--model-root", type=Path)
    dry.add_argument("--manifest-sha256")
    dry.add_argument("--source-commit")
    dry.set_defaults(split="val")
    dry.set_defaults(handler=_handle_dry_run)

    collect = commands.add_parser("collect")
    collect.add_argument("--run-id", required=True)
    collect.add_argument("--platform", choices=("macos", "linux"), required=True)
    collect.add_argument("--model", choices=_MODELS, required=True)
    collect.add_argument("--device", choices=("mps", "cuda"), required=True)
    collect.add_argument("--dtype", required=True)
    collect.add_argument("--split", choices=("val", "test"), required=True)
    collect.add_argument("--run-kind", choices=tuple(item.value for item in RunKind), required=True)
    _add_dataset_anchors(collect)
    _add_model_assets(collect)
    collect.add_argument("--threshold-lock", type=Path)
    collect.add_argument("--config", type=Path, required=True)
    collect.add_argument("--source-commit", required=True)
    collect.add_argument("--output-root", type=Path, required=True)
    collect.add_argument("--allow-oracle-diagnostic", action="store_true")
    collect.set_defaults(handler=_handle_collect)

    calibrate = commands.add_parser("calibrate")
    _add_frozen_config(calibrate)
    calibrate.add_argument("--model", choices=_MODELS, required=True)
    _add_dataset_anchors(calibrate)
    calibrate.set_defaults(split="val")
    calibrate.add_argument("--mac-run-root", type=Path, required=True)
    calibrate.add_argument("--mac-run-expectation", type=Path, required=True)
    calibrate.add_argument("--mac-run-expectation-sha256", required=True)
    calibrate.add_argument("--linux-run-root", type=Path, required=True)
    calibrate.add_argument("--linux-run-expectation", type=Path, required=True)
    calibrate.add_argument("--linux-run-expectation-sha256", required=True)
    calibrate.add_argument("--source-commit", required=True)
    calibrate.add_argument("--output-root", type=Path, required=True)
    calibrate.add_argument("--calibration-workers", type=int, default=1)
    calibrate.set_defaults(handler=_handle_calibrate)

    aggregate = commands.add_parser("aggregate")
    _add_frozen_config(aggregate)
    aggregate.add_argument("--aggregation-plan", type=Path, required=True)
    aggregate.add_argument("--aggregation-plan-sha256", required=True)
    aggregate.add_argument("--bootstrap-seed", type=int, default=20260902)
    aggregate.add_argument("--bootstrap-repetitions", type=int, default=10000)
    aggregate.add_argument("--output-root", type=Path, required=True)
    aggregate.set_defaults(handler=_handle_aggregate)

    verify_evidence = commands.add_parser("verify-evidence")
    verify_evidence.add_argument("--output-root", type=Path, required=True)
    verify_evidence.add_argument("--print-inventory-sha", action="store_true")
    verify_evidence.set_defaults(handler=_handle_verify_evidence)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return arguments.handler(arguments)
    except BenchmarkError as error:
        print(f"{error.code}: {error.detail}", file=sys.stderr)
        return 2
    except ModelSetupError as error:
        print(f"{error.code}: benchmark command rejected", file=sys.stderr)
        return 2
    except (CalibrationError, DatasetVerificationError, ValueError, OSError) as error:
        code = str(error).split(":", 1)[0]
        if not re.fullmatch(r"[A-Z][A-Z0-9_]+", code):
            code = type(error).__name__.upper()
        print(f"{code}: benchmark command rejected", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
