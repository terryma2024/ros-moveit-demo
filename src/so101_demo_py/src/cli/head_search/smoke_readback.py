"""The production smoke and qualification readback subcommands."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import sys

from so101_demo.act.head_search import ownership as ownership
from so101_demo.act.head_search.ownership import process_ancestry
from so101_demo.cli.head_search.common import _command_line
from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
    PRODUCTION_SMOKE_ENTRY,
    PRODUCTION_SMOKE_REQUIRED_FLAGS,
    QUALIFICATION_READBACK_ENTRY,
    QUALIFICATION_READBACK_REQUIRED_FLAGS,
)


def _production_smoke_parser() -> argparse.ArgumentParser:
    """The `measure-production-smoke` entry: one owned stack, one bounded search, one sealed journal."""

    from so101_demo.act.head_search.production_smoke.journal import ANCHORS as SMOKE_ANCHORS
    from so101_demo.act.head_search.production_smoke.journal import CONDITION_CLASS

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-production-smoke",
        description=(
            "Run the production smoke: take the exclusive-ownership receipt, start the one "
            "production composition, place the anchor's cup where the seal declares it, run the bounded "
            "search through the real adapter and controller, prove the lock, the 10 Hz cadence, the "
            "bounded commands and the three-sample stop, then stop the stack and prove it is gone. The "
            "success condition is the sealed journal the aggregate phase consumes, not the planning "
            "coverage proof, which is written beside it"
        ),
    )
    parser.add_argument("--run-root", type=Path, help="the brand-new phase root the journal owns")
    parser.add_argument(
        "--ownership-receipt",
        type=Path,
        help="Step 1's exclusive-ownership receipt for this run root",
    )
    parser.add_argument("--final-run", type=Path, help="the frozen runtime of record")
    parser.add_argument(
        "--production-config", type=Path, help="the promoted production search config"
    )
    parser.add_argument("--approved-bundle", type=Path, help="the approved calibration bundle")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the stack steps")
    parser.add_argument(
        "--urdf", type=Path, help="the ACT URDF the stack's robot description is built from"
    )
    parser.add_argument(
        "--plugin-config", type=Path, help="the production MuJoCo plugin configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration"
    )
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument(
        "--frozen-candidate", type=Path, help="the selected frozen candidate document"
    )
    parser.add_argument("--workdir", type=Path, help="the scratch directory the phase writes into")
    parser.add_argument(
        "--anchor",
        default=SMOKE_ANCHORS[0],
        help=f"the seal anchor to search, one of {','.join(SMOKE_ANCHORS)}",
    )
    parser.add_argument(
        "--scenario",
        dest="condition_class",
        default=CONDITION_CLASS,
        help=(
            "the declared condition class the terminal is judged against (the flag the coverage smoke "
            "accepted and never read); the production smoke is the legal single cup, `nominal`"
        ),
    )
    parser.add_argument(
        "--device", default="cuda", help="the detector device (never a CPU fallback)"
    )
    parser.add_argument(
        "--expected-source-commit",
        help="the frozen runtime's source commit the identity must match",
    )
    parser.add_argument(
        "--expected-production-config-sha256",
        help="the promoted config digest the identity must match",
    )
    parser.add_argument(
        "--expected-values-sha256", help="the 17 values' digest the identity must match"
    )
    parser.add_argument(
        "--expected-weights-sha256", help="the detector weights digest the identity must match"
    )
    parser.add_argument(
        "--expected-package-prefix",
        help="the `ros2 pkg prefix so101_demo_py` the gate must observe",
    )
    return parser


def _measure_production_smoke(arguments: list[str], *, entry: str = PRODUCTION_SMOKE_ENTRY) -> int:
    """Validate the declared inputs, then hand the one smoke flight to the library.

    The CLI is thin on purpose: the library owns the order (class, runtime, receipt, seal, root, flight,
    seal the journal, aggregate it) and this entry owns the flag surface and the exit code.
    """

    parsed = _production_smoke_parser().parse_args(arguments)
    missing = [
        flag for name, flag in PRODUCTION_SMOKE_REQUIRED_FLAGS if getattr(parsed, name) is None
    ]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a production smoke declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in PRODUCTION_SMOKE_REQUIRED_FLAGS
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

    from functools import partial

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.production_smoke.aggregate import (
        read_runtime_of_record,
        run_smoke_flight,
        write_head_search_production_smoke,
    )

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
    command = _command_line(arguments, subcommand="measure-production-smoke")
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
                    "SMOKE_RUNTIME_UNVERIFIED",
                    f"{key}: the run declares {wanted!r} and the frozen runtime reads "
                    f"{runtime.get(key)!r}",
                )
        result = write_head_search_production_smoke(
            run_root=parsed.run_root,
            ownership_receipt=parsed.ownership_receipt,
            runtime=runtime,
            seal=seal,
            workdir=parsed.workdir,
            anchor=parsed.anchor,
            condition_class=parsed.condition_class,
            values=values,
            approved_bundle_sha256=hashlib.sha256(parsed.approved_bundle.read_bytes()).hexdigest(),
            producer={
                "entry": entry,
                "argv_sha256": hashlib.sha256(" ".join(command.split()).encode()).hexdigest(),
                "command": command,
                "pid": os.getpid(),
            },
            run_flight=partial(
                run_smoke_flight,
                urdf_path=parsed.urdf,
                scene_path=parsed.scene,
                plugin_config_path=parsed.plugin_config,
                controller_config_path=parsed.controller_config,
                production_config_path=parsed.production_config,
                weights_path=parsed.weights,
                frozen_candidate_path=parsed.frozen_candidate,
                production=production,
                device=parsed.device,
                excluded_pids=process_ancestry(),
            ),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    document = result["document"]
    print(
        f"production_smoke: anchor={document['anchor']} scenario={document['condition_class']} "
        f"terminal_status={document['terminal_status']} status={document['status']} "
        f"gates={json.dumps(document['gates'], sort_keys=True)} "
        f"elapsed_s={document.get('elapsed_s')} journal={result['journal']}"
    )
    for refusal in result["refusals"]:
        print(f"{refusal['code']}: {refusal['detail']}", file=sys.stderr)
    print(
        f"SMOKE_MEASURED status={document['status']} run_root={result['run_root']} "
        f"sealed_journal={result['sealed_journal']} frames={document['frame_cadence']['frame_count']} "
        f"rate_hz={document['frame_cadence']['achieved_rate_hz']}"
    )
    return 0 if document["status"] == "PASS" else 2


def _qualification_readback_parser() -> argparse.ArgumentParser:
    """The `measure-qualification-readback` entry: one owned stack, seventeen values, four measurements."""

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-qualification-readback",
        description=(
            "Run the during-qualification approved-values readback: take the exclusive-ownership "
            "receipt that guards the qualification run root, start the one production composition, read "
            "each of the seventeen approved values off the production component that consumes it while "
            "the stack runs, read the four camera measurements off the running camera and TF, load the "
            "one CUDA detector from the frozen weights, then stop the stack and prove it is gone. The "
            "document the aggregate's `approved_values_readback` gate consumes is written under the "
            "evidence root, and the qualification run root it declares stays unclaimed for the aggregator"
        ),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        help="the qualification run root this readback is taken for; it must not exist yet",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        help="the readback's own evidence root (the campaign's qualification-readback-<UTC>)",
    )
    parser.add_argument(
        "--ownership-receipt",
        type=Path,
        help="Step 1's exclusive-ownership receipt, whose planned root is the run root above",
    )
    parser.add_argument("--final-run", type=Path, help="the frozen runtime of record")
    parser.add_argument(
        "--production-config", type=Path, help="the promoted production search config whose values are read"
    )
    parser.add_argument("--approved-bundle", type=Path, help="the approved calibration bundle")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the stack steps")
    parser.add_argument("--urdf", type=Path, help="the ACT URDF the stack's robot description is built from")
    parser.add_argument("--plugin-config", type=Path, help="the production MuJoCo plugin configuration")
    parser.add_argument("--controller-config", type=Path, help="the sealed controller configuration")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument("--workdir", type=Path, help="the scratch directory the phase writes into")
    parser.add_argument(
        "--anchor",
        default="default",
        help="the seal anchor whose controller configuration the running controller is built with",
    )
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--camera-reference",
        type=Path,
        help="an optional document carrying approved values for the four camera measurements",
    )
    parser.add_argument(
        "--expected-source-commit", help="the frozen runtime's source commit the identity must match"
    )
    parser.add_argument(
        "--expected-production-config-sha256",
        help="the promoted config digest the identity must match",
    )
    parser.add_argument(
        "--expected-values-sha256", help="the 17 values' digest the identity must match"
    )
    parser.add_argument(
        "--expected-weights-sha256", help="the detector weights digest the identity must match"
    )
    return parser


def _measure_qualification_readback(
    arguments: list[str], *, entry: str = QUALIFICATION_READBACK_ENTRY
) -> int:
    """Validate the declared inputs, then hand the one readback to the library.

    The CLI is thin on purpose: the library owns the order (recorded values against the approval, the
    receipt, the run root, one stack, the observations, the teardown proof) and this entry owns the flag
    surface and the exit code.
    """

    parsed = _qualification_readback_parser().parse_args(arguments)
    missing = [
        flag for name, flag in QUALIFICATION_READBACK_REQUIRED_FLAGS if getattr(parsed, name) is None
    ]
    if parsed.run_root is None:
        missing.insert(0, "--run-root")
    if parsed.evidence_root is None:
        missing.insert(0, "--evidence-root")
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a qualification readback declares "
            f"{' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in QUALIFICATION_READBACK_REQUIRED_FLAGS
        if not Path(getattr(parsed, name)).exists()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.run_root.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.run_root} exists; the readback is "
            f"taken for a qualification run root the aggregate has not claimed yet, and no qualification "
            f"phase is ever resumed",
            file=sys.stderr,
        )
        return 2
    if parsed.evidence_root.exists() and any(parsed.evidence_root.iterdir()):
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.evidence_root} exists and is not "
            f"empty; a readback is never resumed or overwritten",
            file=sys.stderr,
        )
        return 2

    from functools import partial

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.qualification_readback.readback_run import (
        run_readback_observation,
        write_head_search_qualification_readback,
    )

    production = json.loads(parsed.production_config.read_text(encoding="utf-8"))
    seal = json.loads(parsed.geometry_seal.read_text(encoding="utf-8"))
    approved_bundle = json.loads(parsed.approved_bundle.read_text(encoding="utf-8"))
    camera_reference = (
        json.loads(parsed.camera_reference.read_text(encoding="utf-8"))
        if parsed.camera_reference is not None
        else None
    )
    command = _command_line(arguments, subcommand="measure-qualification-readback")
    try:
        runtime = ownership.read_runtime_identity(parsed.final_run, production_config=parsed.production_config)
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
                    "READBACK_RUNTIME_UNVERIFIED",
                    f"{key}: the run declares {wanted!r} and the frozen runtime reads "
                    f"{runtime.get(key)!r}",
                )
        result = write_head_search_qualification_readback(
            run_root=parsed.run_root,
            evidence_root=parsed.evidence_root,
            ownership_receipt=parsed.ownership_receipt,
            runtime=runtime,
            approved_bundle=approved_bundle,
            production_config=production,
            observe=partial(
                run_readback_observation,
                workdir=parsed.workdir,
                production=production,
                seal=seal,
                anchor=parsed.anchor,
                production_config_path=parsed.production_config,
                urdf_path=parsed.urdf,
                scene_path=parsed.scene,
                plugin_config_path=parsed.plugin_config,
                controller_config_path=parsed.controller_config,
                weights_path=parsed.weights,
                device=parsed.device,
                excluded_pids=process_ancestry(),
            ),
            approved_bundle_path=parsed.approved_bundle,
            production_config_path=parsed.production_config,
            camera_reference=camera_reference,
            command=f"{entry} {command}",
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    document = result["document"]
    observed = [
        f"{name}={row.get('observed_value')}"
        for name, row in sorted(document["values"].items())
    ]
    for row in observed:
        print(f"observed {row}")
    print(
        f"camera_measurements="
        f"{json.dumps({name: row.get('observed_value') for name, row in document['camera_measurements'].items()}, sort_keys=True)}"
    )
    print(
        f"READBACK_MEASURED status={document['status']} run_root={result['run_root']} "
        f"evidence_root={result['evidence_root']} values={document['values_count']} "
        f"values_sha256={document['values_sha256']} elapsed_s={result['elapsed_s']:.1f} "
        f"document={result['document_path']} teardown={result['teardown_proof']}"
    )
    return 0 if document["status"] == "PASS" else 2
