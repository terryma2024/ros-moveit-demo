"""The macOS MPS two-worker campaign entry point.

The Linux container batch (a broker image, a CUDA device and `proc_fd_unix`) was retired with the perception
broker (migration M5). This macOS entry point exists because the v4 contract had no
executable entry point at all — the schema, the broker, the IPC, the supervisor, the registry and
the recovery were each tested but never driven together outside a test.

What it does, in the design's order:

1. read-only inventory, so a duplicate claim, endpoint or campaign directory stops the run before
   anything is spawned;
2. the real start guard, in its own process, because the accelerator probe imports torch;
3. the supervisor claim and the private campaign root;
4. one broker bootstrap that loads the real model set on MPS through the detector factory, on a
   single execution lane, and publishes a ready receipt;
5. two workers spawned by the supervisor, each writing a registered ACK before it runs;
6. the composed campaign's one-time admission for every response;
7. exact cleanup, with the durable receipt cleared only when cleanup is proven complete.

The command emits one JSON document on stdout so the ledger can quote it directly, and it exits
non-zero when the run is not a pass.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from so101_demo.cli.macos_campaign.drive import run, run_routed
from so101_demo.cli.macos_campaign.guard import RefusedRun, route_spec
from so101_demo.parallel_batch.contracts.common import ContractError
from so101_demo.parallel_batch.single_worker_composition import (
    SINGLE_WORKER_RETRY_BATCH_KIND,
)


def build_single_worker_parser(execution_profile: str) -> argparse.ArgumentParser:
    """The single-worker parser. One entry point per profile: there is no `--batch-kind` switch."""

    spec = route_spec(execution_profile)
    retry = spec.batch_kind == SINGLE_WORKER_RETRY_BATCH_KIND
    parser = argparse.ArgumentParser(
        prog="so101_macos_single_worker_retry" if retry else "so101_macos_single_worker_first_pass",
        description=f"Run one macOS MPS W1 campaign ({spec.execution_profile}) with one Worker.")
    parser.add_argument("--config", type=Path, required=True,
                        help=f"the schema-v{5 if retry else 6} macOS MPS W1 document")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--point-id", action="append", default=[],
                        help="repeatable; exact W1 keeps one slot regardless")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=None,
                        help="the immutable point catalog the selection is frozen from")
    parser.add_argument("--catalog-sha256", default=None)
    parser.add_argument("--retry-root", type=Path, default=None,
                        help="v5 only: the prior campaign root holding the committed business "
                             "FAILED point this retry is bound to")
    parser.add_argument("--original-selection-sha256", default=None,
                        help="v5 only: the original first-pass selection digest the retry "
                             "references (required without --retry-root)")
    parser.add_argument("--original-result-sha256", default=None,
                        help="v5 only: the digest of the original committed business FAILED "
                             "point result (required without --retry-root)")
    parser.add_argument("--original-catalog-sha256", default=None,
                        help="v5 only: the catalog digest the original selection was frozen from; "
                             "the resolved catalog is used when this is omitted")
    parser.add_argument("--original-result", type=Path, default=None,
                        help="v5 only: the original committed result document; when given, its "
                             "bytes must match --original-result-sha256 and it decides the outcome")
    parser.add_argument("--original-batch-id", default=None,
                        help="v5 only: the original batch the failed point came from; it must "
                             "differ from --batch-id")
    parser.add_argument("--yolo-weights", type=Path, required=True)
    parser.add_argument("--grounded-root", type=Path, required=True)
    parser.add_argument("--duplicate-probe", action="store_true")
    parser.add_argument("--cancel-second-worker-after-served", type=int, default=0)
    parser.add_argument("--tamper-snapshot-sha", action="store_true")
    parser.add_argument("--stall-serve-after", type=int, default=0)
    parser.add_argument("--worker-deadline-s", type=float, default=240.0)
    parser.add_argument("--crash-broker-after-served", type=int, default=0)
    parser.add_argument("--skip-models", action="store_true",
                        help="compose and pre-flight only; never a pass")
    return parser


def run_single_worker(argv: list[str] | None = None, *, execution_profile: str) -> int:
    """The single-worker entry point for one named profile. A different profile's document is refused."""

    spec = route_spec(execution_profile)
    if spec.worker_count != 1:
        raise ContractError(f"NOT_A_SINGLE_WORKER_PROFILE: {execution_profile}")
    arguments = build_single_worker_parser(execution_profile).parse_args(argv)
    arguments_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        return run_routed(argv=arguments_argv, arguments=arguments,
                          execution_profile=execution_profile)
    except RefusedRun as refusal:
        print(json.dumps({"status": "REFUSED", "stage": refusal.stage, "detail": refusal.detail},
                         indent=2, sort_keys=True))
        return refusal.exit_code


def main(argv: list[str] | None = None) -> int:
    # The launcher's first job is the fallback pin and the process handover, and it happens before
    # anything that could import torch. The accelerator probe needs torch.mps, while the broker
    # bootstrap requires torch to still be unimported when it reads the pin, so the two must not
    # share an interpreter. Pinning and re-executing here is what keeps that true; the guard phase
    # re-executes once more to hand the admission over.
    arguments = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") != "0":
        environment = dict(os.environ)
        environment["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
        os.execve(sys.executable, [sys.executable, "-m",
                                   "so101_demo.cli.macos_two_worker_campaign", *arguments], environment)
    try:
        return run(arguments)
    except Exception as error:  # noqa: BLE001 - a refusal is reported, never a traceback alone
        print(json.dumps({"status": "ERROR", "error": f"{type(error).__name__}: {error}"},
                         indent=2, sort_keys=True))
        return 1


def main_single_worker(execution_profile: str, argv: list[str] | None = None) -> int:
    """The single-worker launcher: same fallback pin, then the profile's own entry point."""

    spec = route_spec(execution_profile)
    arguments = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") != "0":
        environment = dict(os.environ)
        environment["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"
        os.execve(sys.executable, [sys.executable, "-m", spec.module, *arguments], environment)
    try:
        return run_single_worker(arguments, execution_profile=execution_profile)
    except Exception as error:  # noqa: BLE001 - a refusal is reported, never a traceback alone
        print(json.dumps({"status": "ERROR", "error": f"{type(error).__name__}: {error}"},
                         indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
