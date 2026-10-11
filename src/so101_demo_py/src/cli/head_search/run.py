"""The run subcommand, its parser and the teleop serving."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from so101_demo.cli.head_search.common import (
    _command_line,
    _declared_directories,
    _declared_paths,
    _digest,
    _evaluation_arguments,
    _frames,
    _frozen_run_root,
    _gpu_device,
    _json_document,
    _records,
    _source_web_dir,
)
from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_RUN_INPUTS_INCOMPLETE,
    RUN_PHASE_MEASUREMENTS,
    RUN_REQUIRED_FLAGS,
    RUN_SEALED_INPUT_FLAGS,
)

if TYPE_CHECKING:  # pragma: no cover - the run module is imported where it is used
    from so101_demo.act.head_search_calibration_run import CalibrationPhaseInputs


def _run_parser() -> argparse.ArgumentParser:
    """The `run` entry: the six sealed inputs, the phase inputs and the gate's own arguments.

    Nothing is fabricated here. The search configuration is the one the installed controller is
    constructed with, the admission is the repository's own `CalibrationMeasurementAdmission`, the rule
    and the measurements come from the phase-3 producers, and the argument list of the frozen-candidate
    gate is assembled from the declared documents rather than rebuilt.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration run",
        description="Run a frozen Head execution input or the eight calibration phases into a new run root",
    )
    parser.add_argument('--execution-inputs', type=Path,
                        help='absolute frozen input for one stage-one development execution; excludes calibration phase flags')
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--seal", type=Path, help="declared digests of the six sealed inputs")
    parser.add_argument("--dataset", type=Path, help="dataset manifest")
    parser.add_argument("--candidate", type=Path, help="model manifest")
    parser.add_argument("--geometry-seal", type=Path)
    parser.add_argument("--episode-partitions", type=Path)
    parser.add_argument("--production-config", type=Path)
    parser.add_argument("--camera-config", type=Path)
    parser.add_argument("--production-search-config", type=Path)
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--selection-rule", type=Path)
    parser.add_argument("--operating-point-measurements", type=Path)
    parser.add_argument("--candidate-id")
    parser.add_argument("--held-out-measurements", type=Path)
    parser.add_argument("--frozen-candidate", type=Path, action="append")
    parser.add_argument("--task-dataset", type=Path)
    parser.add_argument("--episode-split", default="calibration")
    parser.add_argument("--episode-records", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    parser.add_argument("--weights-dir", type=Path)
    parser.add_argument("--head-dataset-root", type=Path)
    parser.add_argument("--task-dataset-root", type=Path)
    parser.add_argument("--bundle-inputs", type=Path)
    for name, flag, _shape in RUN_PHASE_MEASUREMENTS:
        parser.add_argument(flag, dest=name, type=Path, help=f"phase measurement: {name}")
    parser.add_argument("--operation", default="neck_target")
    parser.add_argument("--cpu-cores", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--gpu-device", default="0")
    return parser


def _run(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the phases to the orchestration library.

    The formal stage-one file-protocol entry is the same `run` command with
    `--execution-inputs`: it is mutually exclusive with the legacy eight-phase
    flags, and a mixed invocation is refused before anything reads a path.
    """

    if any(argument == "--execution-inputs" or argument.startswith("--execution-inputs=")
           for argument in arguments):
        formal_flags = {'--execution-inputs', '--print-readback', '--help'}
        legacy = [argument for argument in arguments
                  if argument.startswith("--") and argument.split('=',1)[0] not in formal_flags]
        if legacy:
            print(
                f"{HEAD_SEARCH_RUN_INPUTS_INCOMPLETE}: --execution-inputs is the formal stage-one "
                f"entry and cannot be combined with the legacy phase flags {' '.join(sorted(legacy))}",
                file=sys.stderr,
            )
            return 2
        from so101_demo.cli.head_execution_run import main as execution_main

        return execution_main(arguments)

    parsed = _run_parser().parse_args(arguments)
    missing = [flag for name, flag in RUN_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_RUN_INPUTS_INCOMPLETE}: a run declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [str(path) for path in _declared_paths(parsed) if not Path(path).is_file()] + [
        str(path) for path in _declared_directories(parsed) if not Path(path).is_dir()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_RUN_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    try:
        phase_inputs = _phase_inputs(parsed)
    except (KeyError, TypeError, ValueError) as error:
        print(
            f"{HEAD_SEARCH_RUN_INPUTS_INCOMPLETE}: a declared document is not the one it must be: "
            f"{error}",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_run import (
        CalibrationInputsRefused,
        execute_calibration_run,
    )

    try:
        result = execute_calibration_run(
            run_root=parsed.run_root,
            phase_inputs=phase_inputs,
            command=_command_line(arguments),
        )
    except CalibrationInputsRefused as error:
        # the entry's own refusals - the trajectory contract and an existing root - and nothing ran
        print(str(error), file=sys.stderr)
        return 2
    status = result.run_status
    if result.status == "SUCCEEDED":
        print(f"RUN_SUCCEEDED {result.run_root}")
        return 0
    print(
        f"RUN_FAILED first_failing_phase={status['first_failing_phase']} "
        f"code={status['failure_code']} run_root={result.run_root}",
        file=sys.stderr,
    )
    return int(status["failure_exit_code"])


def _phase_inputs(parsed) -> CalibrationPhaseInputs:
    """Build the phase inputs from the declared documents; nothing is computed here."""

    from so101_demo.act.head_search_calibration_run import CalibrationPhaseInputs
    from so101_demo.act.head_search_measured_readback import observe_measured_readbacks
    from so101_demo.act.pick_place_calibration_admission import CalibrationMeasurementAdmission

    admission_document = _json_document(parsed.admission)
    fields = (
        "generation",
        "status",
        "measurement_plan_sha256",
        "safe_interval_rad",
        "controller_generation",
        "broker_generation",
    )
    if set(admission_document) != set(fields):
        raise ValueError(f"a production admission declares exactly {list(fields)}")
    generation = admission_document["generation"]
    if type(generation) is not str or not generation:
        raise ValueError("a production admission names the generation it admits")

    held_out = (
        _frames(parsed.held_out_measurements) if parsed.held_out_measurements is not None else ()
    )
    measurements = {
        name: (
            _records(getattr(parsed, name))
            if shape == "records"
            else _json_document(getattr(parsed, name))
        )
        for name, _flag, shape in RUN_PHASE_MEASUREMENTS
    }
    return CalibrationPhaseInputs(
        production_search_config=_json_document(parsed.production_search_config),
        sealed_inputs=_sealed_inputs(parsed),
        admission=CalibrationMeasurementAdmission(**admission_document),
        generation=generation,
        operation=parsed.operation,
        cpu_cores=parsed.cpu_cores,
        gpu_device=_gpu_device(parsed.gpu_device),
        selection_rule=_json_document(parsed.selection_rule),
        operating_point_measurements=_frames(parsed.operating_point_measurements),
        candidate_id=parsed.candidate_id,
        held_out_measurements=held_out,
        evaluation_arguments=_evaluation_arguments(parsed),
        bundle_inputs=_json_document(parsed.bundle_inputs),
        # phases 6 and 7 prove the eleven values they measure by constructing the production component
        # that consumes each one (plan section 2b): the run observes them at startup rather than
        # restating the number it just computed
        readback_observer=observe_measured_readbacks,
        **measurements,
    )


def _sealed_inputs(parsed) -> dict:
    """The seal of the six dependencies: the declared one, or what the run just read and digested."""

    if parsed.seal is not None:
        declared = _json_document(parsed.seal)
        if not isinstance(declared, Mapping):
            raise ValueError("a seal declares one entry per sealed input")
        return dict(declared)
    sealed = {}
    for name, attribute, _flag in RUN_SEALED_INPUT_FLAGS:
        path = Path(getattr(parsed, attribute))
        sealed[name] = {"path": str(path), "sha256": _digest(path)}
    return sealed


def _serve_teleop(parsed) -> int:
    """The owned acceptance: start, probe, run the case, tear down, then write the receipt.

    Refusing is a result and it is recorded as one: every declared input is read off disk, every probe is
    measured, and the receipt is written only after the teardown has been observed. There is no longer a
    path that writes a descriptor without measuring anything, and no path that reports
    ``teardown: not-attempted``.
    """

    from so101_demo.act.head_search_teleop_acceptance.acceptance import accept_teleop
    from so101_demo.act.head_search_teleop_acceptance.receipts import (
        DEFAULT_FRAME_PROBE,
        DEFAULT_WEB_PORT,
        PROFILE,
        RECEIPT_ARTIFACT,
    )
    from so101_demo.act.head_search_teleop_acceptance.runners import TeleopAcceptanceRefused

    if not parsed.bundle:
        print(
            "TELEOP_ACCEPTANCE_INPUTS_INCOMPLETE: pass --bundle (the approved calibration bundle)",
            file=sys.stderr,
        )
        return 2
    if not parsed.runtime_id:
        print("TELEOP_ACCEPTANCE_INPUTS_INCOMPLETE: pass --runtime-id", file=sys.stderr)
        return 2
    try:
        final_run = _frozen_run_root(parsed.final_run)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    production_config = parsed.production_config or (
        final_run
        / "install/so101_demo_py/share/so101_demo_py/config/mujoco/act/head_search_runtime.json"
    )
    run_root = Path(parsed.run_root)
    ready_file = Path(parsed.ready_file) if parsed.ready_file else run_root / "head-camera-connection.json"
    acceptance_root = Path(parsed.acceptance_root) if parsed.acceptance_root else ready_file.parent
    socket_root = (
        Path(parsed.bridge_socket_root)
        if parsed.bridge_socket_root
        else Path(os.environ.get("SO101_UNIFIED_SOCKET_DIR") or acceptance_root / "bridge")
    )
    expected = {
        key: value
        for key, value in (
            ("source_commit", parsed.expected_source_commit),
            ("production_config_sha256", parsed.expected_production_config_sha256),
            ("values_sha256", parsed.expected_values_sha256),
            ("weight_sha256_declared", parsed.expected_weights_sha256),
        )
        if value is not None
    }
    try:
        receipt = accept_teleop(
            run_root=run_root,
            acceptance_root=acceptance_root,
            socket_root=socket_root,
            ready_file=ready_file,
            final_run=final_run,
            production_config=production_config,
            approved_bundle=parsed.bundle,
            approval_receipt=parsed.approval_receipt,
            qualification_report=parsed.qualification_report,
            runtime_id=parsed.runtime_id,
            profile=parsed.profile or PROFILE,
            device=parsed.device,
            frames=parsed.frames if parsed.frames is not None else DEFAULT_FRAME_PROBE,
            web_port=parsed.web_port if parsed.web_port is not None else DEFAULT_WEB_PORT,
            weights_path=parsed.weights,
            frozen_candidate=parsed.frozen_candidate,
            expected=expected or None,
            web_dir=parsed.web_dir or _source_web_dir(),
            ros_python=os.environ.get("SO101_UNIFIED_ROS_PYTHON") or sys.executable,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
    except TeleopAcceptanceRefused as error:
        print(f"{error.code}: {error.detail}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt_path = acceptance_root / RECEIPT_ARTIFACT
    print(f"TELEOP_ACCEPTANCE {receipt['status']} receipt={receipt_path}")
    for reason in receipt["refusals"]:
        print(f"  refusal {reason['code']}: {reason['detail']}", file=sys.stderr)
    return 0 if receipt["status"] == "PASSED" else 2
