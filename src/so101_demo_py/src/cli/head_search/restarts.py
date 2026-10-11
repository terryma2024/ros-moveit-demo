"""The restart measurement and the ownership check subcommands."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import sys

from so101_demo.act import head_search_ownership as ownership
from so101_demo.act.head_search_ownership import process_ancestry
from so101_demo.cli.head_search.common import _command_line
from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
    RESTART_REQUIRED_FLAGS,
)


def _restart_parser() -> argparse.ArgumentParser:
    """The `measure-restarts` entry: one restart per declared anchor, each with its own teardown proof."""

    from so101_demo.act.head_search_restarts.contracts import ANCHORS as RESTART_ANCHORS

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-restarts",
        description=(
            "Run exactly one independent FULL_RESTART per anchor (default, left, forward): take the Step 1 "
            "ownership receipt, start the one production composition, prove its graph, camera rate, "
            "simulation clock and one CUDA detector, run one bounded anchor search through the production "
            "transport, prove the stop, then stop the stack and prove it is gone before the next anchor"
        ),
    )
    parser.add_argument("--run-root", type=Path, help="the brand-new run root the three receipts own")
    parser.add_argument(
        "--ownership-receipt", type=Path, help="Step 1's exclusive-ownership receipt for this run root"
    )
    parser.add_argument("--final-run", type=Path, help="the frozen runtime of record")
    parser.add_argument("--production-config", type=Path, help="the promoted production search config")
    parser.add_argument("--approved-bundle", type=Path, help="the approved calibration bundle")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the stack steps")
    parser.add_argument("--urdf", type=Path, help="the ACT URDF the stack's robot description is built from")
    parser.add_argument("--plugin-config", type=Path, help="the production MuJoCo plugin configuration")
    parser.add_argument("--controller-config", type=Path, help="the sealed controller configuration")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--workdir", type=Path, help="the scratch directory the phase writes into")
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--anchors",
        default=",".join(RESTART_ANCHORS),
        help="the anchors to run, in order; the plan fixes default,left,forward",
    )
    parser.add_argument(
        "--max-settle-s", type=float, default=None, help="the per-stop settle budget of the cadence check"
    )
    parser.add_argument(
        "--expected-source-commit", help="the frozen runtime's source commit the identity must match"
    )
    parser.add_argument(
        "--expected-production-config-sha256", help="the promoted config digest the identity must match"
    )
    parser.add_argument("--expected-values-sha256", help="the 17 values' digest the identity must match")
    parser.add_argument(
        "--expected-weights-sha256", help="the detector weights digest the identity must match"
    )
    parser.add_argument(
        "--expected-package-prefix", help="the `ros2 pkg prefix so101_demo_py` the gate must observe"
    )
    return parser


def _measure_restarts(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the three anchor restarts to the library."""

    parsed = _restart_parser().parse_args(arguments)
    missing = [flag for name, flag in RESTART_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a restart declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    # the run root is the one declared input that must NOT exist, and the scratch directory is created by
    # the phase itself: everything else is a sealed input the caller has to present
    absent = [
        str(getattr(parsed, name))
        for name, _flag in RESTART_REQUIRED_FLAGS
        if name not in ("run_root", "workdir") and not Path(getattr(parsed, name)).exists()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.run_root.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.run_root} exists; a qualification run "
            f"is never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2
    anchors = [name for name in str(parsed.anchors).split(",") if name]

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_restarts.observation import read_runtime_of_record
    from so101_demo.act.head_search_restarts.restart_run import run_anchor_restart
    from so101_demo.act.head_search_restarts.writer import write_head_search_restarts

    production = json.loads(parsed.production_config.read_text(encoding="utf-8"))
    values = production.get("values") if isinstance(production.get("values"), Mapping) else {}
    if not values:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.production_config} declares no values "
            f"block",
            file=sys.stderr,
        )
        return 2
    seal = json.loads(parsed.geometry_seal.read_text(encoding="utf-8"))
    try:
        runtime = read_runtime_of_record(parsed.final_run, parsed.production_config)
        expected: dict = {}
        for key, attribute in (
            ("source_commit", "expected_source_commit"),
            ("production_config_sha256", "expected_production_config_sha256"),
            ("values_sha256", "expected_values_sha256"),
            ("weight_sha256_declared", "expected_weights_sha256"),
        ):
            value = getattr(parsed, attribute)
            if value:
                expected[key] = value
        for key, wanted in sorted(expected.items()):
            if runtime.get(key) != wanted:
                raise CalibrationInputsRefused(
                    "RESTART_RUNTIME_UNVERIFIED",
                    f"{key}: the run declares {wanted!r} and the frozen runtime reads "
                    f"{runtime.get(key)!r}",
                )
        result = write_head_search_restarts(
            run_root=parsed.run_root,
            ownership_receipt=parsed.ownership_receipt,
            runtime=runtime,
            approved_bundle_sha256=hashlib.sha256(parsed.approved_bundle.read_bytes()).hexdigest(),
            seal=seal,
            workdir=parsed.workdir,
            values=values,
            anchors=anchors,
            producer={
                "entry": "so101_head_search_calibration measure-restarts",
                "argv_sha256": hashlib.sha256(
                    " ".join(_command_line(arguments, subcommand="measure-restarts").split()).encode()
                ).hexdigest(),
                "command": _command_line(arguments, subcommand="measure-restarts"),
            },
            run_anchor=lambda **kwargs: run_anchor_restart(
                urdf_path=parsed.urdf,
                scene_path=parsed.scene,
                plugin_config_path=parsed.plugin_config,
                controller_config_path=parsed.controller_config,
                production_config_path=parsed.production_config,
                weights_path=parsed.weights,
                frozen_candidate_path=parsed.frozen_candidate,
                values=values,
                seal=seal,
                production=production,
                device=parsed.device,
                excluded_pids=process_ancestry(),
                **kwargs,
            ),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    for anchor in result["aggregate"]["anchors"]:
        document = result["documents"][anchor]
        print(
            f"restart_{anchor}: status={document['status']} gates={json.dumps(document['gates'], sort_keys=True)} "
            f"elapsed_s={document.get('elapsed_s')} receipt={result['receipts'][anchor]}"
        )
    print(
        f"HEAD_SEARCH_RESTARTS_MEASURED anchors={','.join(result['aggregate']['anchors'])} "
        f"status={result['aggregate']['status']} run_root={result['run_root']}"
    )
    return 0 if result["aggregate"]["status"] == "PASS" else 2


def _ownership_parser() -> argparse.ArgumentParser:
    """Step 1's entry: the gate root, the campaign root, and the frozen runtime it must match."""

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration check-ownership",
        description=(
            "Read the fresh process table, ROS graph, GPU processes, tmux ownership and evidence root, "
            "refuse any second owner, and bind the frozen runtime of record before a qualifier starts"
        ),
    )
    parser.add_argument("--run-root", type=Path, required=True, help="a brand-new gate root")
    parser.add_argument("--evidence-root", type=Path, required=True, help="the registered campaign root")
    parser.add_argument("--planned-run-root", type=Path, help="the qualifier root that must not exist")
    parser.add_argument("--final-run", type=Path, help="the frozen qualification runtime root of record")
    parser.add_argument(
        "--production-config", type=Path, help="a promoted config; defaults to the frozen install copy"
    )
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--expected-production-config-sha256")
    parser.add_argument("--expected-values-sha256")
    parser.add_argument("--expected-weights-sha256")
    parser.add_argument("--expected-package-prefix")
    return parser


def _check_ownership(arguments: list[str]) -> int:
    """Run the stack-free ownership gate, write its receipt, and fail closed on any refusal."""

    parsed = _ownership_parser().parse_args(arguments)
    if parsed.production_config is not None and parsed.final_run is None:
        print(
            "RUNTIME_IDENTITY_UNREADABLE: --production-config is read relative to --final-run",
            file=sys.stderr,
        )
        return 2
    expected: dict[str, str] = {}
    if parsed.expected_source_commit:
        expected["source_commit"] = parsed.expected_source_commit
    if parsed.expected_production_config_sha256:
        expected["production_config_sha256"] = parsed.expected_production_config_sha256
    if parsed.expected_values_sha256:
        expected["values_sha256"] = parsed.expected_values_sha256
    if parsed.expected_weights_sha256:
        expected["weight_sha256_declared"] = parsed.expected_weights_sha256
    runtime = None
    if parsed.final_run is not None:
        # the identity is read before the run root is claimed: a bad runtime must leave nothing behind
        try:
            runtime = ownership.read_runtime_identity(
                parsed.final_run, production_config=parsed.production_config
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
    try:
        document = ownership.check_exclusive_ownership(
            run_root=parsed.run_root,
            evidence_root=parsed.evidence_root,
            planned_run_root=parsed.planned_run_root,
            runtime=runtime,
            expected_runtime=expected or None,
            expected_package_prefix=parsed.expected_package_prefix,
        )
    except ValueError as error:
        if "RUN_ROOT_ALREADY_EXISTS" not in str(error):
            raise
        print(str(error), file=sys.stderr)
        return 2
    if document["status"] == ownership.EXCLUSIVE_OWNERSHIP_OK:
        print(f"{document['status']} {document['run_root']}")
        return 0
    codes = ",".join(str(item["code"]) for item in document["refusals"])
    print(f"{document['status']} {codes}", file=sys.stderr)
    return 2
