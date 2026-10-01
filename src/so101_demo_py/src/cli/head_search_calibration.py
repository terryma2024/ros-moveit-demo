"""The formal head search calibration CLI: run, verify-promoted-config, qualify, serve-teleop.

The CLI parses arguments, validates the inputs a run declares and orchestrates nothing itself: `run`
hands the phases to `so101_demo.act.head_search_calibration_run`, where the order, the entry binding, the
trajectory precondition and the run status live (plan rule 4). Every subcommand refuses a run root that
already exists, so there is no way to resume or continue a stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from so101_demo.act.head_search_qualification import (
    qualification_parser,
    qualify_head_search,
    serve_teleop,
)

if TYPE_CHECKING:  # pragma: no cover - the run module is imported where it is used
    from so101_demo.act.head_search_calibration_run import CalibrationPhaseInputs

#: a run whose declared inputs are missing or unreadable is refused before any phase, by name
HEAD_SEARCH_RUN_INPUTS_INCOMPLETE = "HEAD_SEARCH_RUN_INPUTS_INCOMPLETE"

#: the measurement documents phases 6 and 7 consume (plan section 2 rows 6 and 7), each with the flag it
#: is declared under and its shape: `document` is one JSON object the phase cites by path and sha256,
#: `records` is the JSON list of measured records the phase itself builds its evidence from. The run
#: reads these files and never invents a measurement; a run that omits one is refused at this entry.
RUN_PHASE_SIX_MEASUREMENTS = (
    ("search_timing", "--search-timing", "document"),
    ("camera_measurements", "--camera-measurements", "document"),
    ("deadband_candidates", "--deadband-candidates", "records"),
    ("workspace_projection", "--workspace-projection", "document"),
    ("fine_correction_episodes", "--fine-correction-episodes", "records"),
)
RUN_PHASE_SEVEN_MEASUREMENTS = (
    ("frame_age_measurements", "--frame-age-measurements", "document"),
    ("skew_measurements", "--skew-measurements", "document"),
    ("frame_contract", "--frame-contract", "document"),
    ("controller_submissions", "--controller-submissions", "document"),
    ("mujoco_measurements", "--mujoco-measurements", "document"),
    ("stationary_measurements", "--stationary-measurements", "document"),
    ("feedback_measurements", "--feedback-measurements", "document"),
    ("controller_stop_config", "--controller-stop-config", "document"),
    ("stop_proofs", "--stop-proofs", "document"),
)
RUN_PHASE_MEASUREMENTS = RUN_PHASE_SIX_MEASUREMENTS + RUN_PHASE_SEVEN_MEASUREMENTS

#: the six sealed controlled dependencies of plan section 2b, and the flag each is declared with
RUN_SEALED_INPUT_FLAGS = (
    ("dataset_manifest", "dataset", "--dataset"),
    ("model_manifest", "candidate", "--candidate"),
    ("geometry_seal", "geometry_seal", "--geometry-seal"),
    ("scenario_partitions", "episode_partitions", "--episode-partitions"),
    ("production_config", "production_config", "--production-config"),
    ("camera_config", "camera_config", "--camera-config"),
)

#: the flags a run cannot start without; each is validated before the run root is claimed
RUN_REQUIRED_FLAGS = (
    ("run_root", "--run-root"),
    ("dataset", "--dataset"),
    ("candidate", "--candidate"),
    ("geometry_seal", "--geometry-seal"),
    ("episode_partitions", "--episode-partitions"),
    ("production_config", "--production-config"),
    ("camera_config", "--camera-config"),
    ("production_search_config", "--production-search-config"),
    ("admission", "--admission"),
    ("selection_rule", "--selection-rule"),
    ("operating_point_measurements", "--operating-point-measurements"),
    ("candidate_id", "--candidate-id"),
    ("frozen_candidate", "--frozen-candidate"),
    ("task_dataset", "--task-dataset"),
    ("bundle_inputs", "--bundle-inputs"),
) + tuple((name, flag) for name, flag, _shape in RUN_PHASE_MEASUREMENTS)

#: the required flags that name a file that must already exist; `--run-root` must not, and a candidate
#: id is a name rather than a path
RUN_REQUIRED_FILE_FLAGS = (
    "dataset",
    "candidate",
    "geometry_seal",
    "episode_partitions",
    "production_config",
    "camera_config",
    "production_search_config",
    "admission",
    "selection_rule",
    "operating_point_measurements",
    "frozen_candidate",
    "task_dataset",
    "bundle_inputs",
) + tuple(name for name, _flag, _shape in RUN_PHASE_MEASUREMENTS)

#: the optional flags that name a file, and the ones that name an existing directory
RUN_OPTIONAL_FILE_FLAGS = ("seal", "held_out_measurements", "episode_records")
RUN_OPTIONAL_DIRECTORY_FLAGS = (
    "evidence_root",
    "weights_dir",
    "head_dataset_root",
    "task_dataset_root",
)


def _run_parser() -> argparse.ArgumentParser:
    """The `run` entry: the six sealed inputs, the phase inputs and the gate's own arguments.

    Nothing is fabricated here. The search configuration is the one the installed controller is
    constructed with, the admission is the repository's own `CalibrationMeasurementAdmission`, the rule
    and the measurements come from the phase-3 producers, and the argument list of the frozen-candidate
    gate is assembled from the declared documents rather than rebuilt.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration run",
        description="Run the eight fixed calibration phases once, into a brand-new run root",
    )
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
    """Validate the declared inputs, then hand the phases to the orchestration library."""

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
    from so101_demo.act.task8_calibration_admission import CalibrationMeasurementAdmission

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


def _evaluation_arguments(parsed) -> list[str]:
    """The frozen-candidate gate's own argument list, assembled from the declared documents."""

    arguments = ["compare"]
    for path in parsed.frozen_candidate:
        arguments += ["--candidate", str(path)]
    arguments += [
        "--head-dataset",
        str(parsed.dataset),
        "--task-dataset",
        str(parsed.task_dataset),
        "--episode-partitions",
        str(parsed.episode_partitions),
        "--episode-split",
        parsed.episode_split,
        "--bootstrap-repetitions",
        str(parsed.bootstrap_repetitions),
        "--device",
        parsed.device,
    ]
    for flag, value in (
        ("--episode-records", parsed.episode_records),
        ("--weights-dir", parsed.weights_dir),
        ("--head-dataset-root", parsed.head_dataset_root),
        ("--task-dataset-root", parsed.task_dataset_root),
    ):
        if value is not None:
            arguments += [flag, str(value)]
    return arguments


def _declared_paths(parsed) -> list[Path]:
    """Every file a run declares: the required ones, the repeated ones and the optional ones."""

    values: list[Path] = []
    for name in RUN_REQUIRED_FILE_FLAGS:
        value = getattr(parsed, name)
        if value is None:
            continue
        values.extend(value if isinstance(value, list) else [value])
    for name in RUN_OPTIONAL_FILE_FLAGS:
        value = getattr(parsed, name)
        if value is not None:
            values.append(value)
    return [Path(value) for value in values]


def _declared_directories(parsed) -> list[Path]:
    return [
        Path(getattr(parsed, name))
        for name in RUN_OPTIONAL_DIRECTORY_FLAGS
        if getattr(parsed, name) is not None
    ]


def _json_document(path) -> Mapping:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"{path} is not a JSON object")
    return document


def _records(path) -> list:
    """A phase's declared list of measured records, or a document that carries them under `records`."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(document, Mapping):
        document = document.get("records")
    if isinstance(document, (str, bytes)) or not isinstance(document, Sequence):
        raise ValueError(f"{path} declares no list of measured records")
    return list(document)


def _frames(path) -> list:
    """A phase-3 measurement document: a list of frames, or a document that carries them."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(document, Mapping):
        document = document.get("frames")
    if isinstance(document, (str, bytes)) or not isinstance(document, Sequence):
        raise ValueError(f"{path} declares no list of measurement frames")
    return list(document)


def _gpu_device(value: str):
    return int(value) if value.isdigit() else value


def _command_line(arguments: Sequence[str]) -> str:
    return "ros2 run so101_demo_py so101_head_search_calibration run " + " ".join(
        shlex.quote(str(item)) for item in arguments
    )


def _verify_promoted_config(
    run_root: Path, approved: str | None, promoted_config: Path | None
) -> int:
    """Hash the promoted bundle's bytes and record the approval once, immutably.

    The bundle is hashed as bytes, so a formatting-only difference is caught rather than normalised away,
    and the receipt is created exclusively: a second verification cannot overwrite what was approved. The
    receipt belongs to a run root that does not exist yet, so verification obeys the same no-resume rule as
    every other runner.
    """

    from so101_demo.act.head_search_qualification import _require_new_root, write_exclusive

    if not approved:
        print("HEAD_SEARCH_APPROVAL_REQUIRED: pass --approved-bundle-sha256", file=sys.stderr)
        return 2
    if promoted_config is None:
        print("HEAD_SEARCH_BUNDLE_REQUIRED: pass --promoted-config", file=sys.stderr)
        return 2
    promoted = Path(promoted_config)
    if not promoted.is_file():
        print(f"HEAD_SEARCH_BUNDLE_MISSING: {promoted} is absent", file=sys.stderr)
        return 2
    measured = hashlib.sha256(promoted.read_bytes()).hexdigest()
    if measured != approved:
        print(
            f"HEAD_SEARCH_APPROVAL_MISMATCH: promoted {measured} differs from approved {approved}",
            file=sys.stderr,
        )
        return 2
    try:
        root = _require_new_root(run_root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        write_exclusive(
            root,
            "approval-receipt.json",
            {
                "approved_bundle_sha256": approved,
                "promoted_bundle_sha256": measured,
                "promoted_config": str(promoted),
                "hashed": "bytes",
                "verified": True,
            },
        )
    except FileExistsError:
        print("APPROVAL_RECEIPT_EXISTS: an approval is immutable", file=sys.stderr)
        return 2
    print(f"HEAD_SEARCH_APPROVED {measured}")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # `run` declares the inputs of the eight phases, so its entry is the run module's and not a stub
    if arguments[:1] == ["run"]:
        return _run(arguments[1:])
    parsed = qualification_parser().parse_args(arguments)
    run_root = Path(parsed.run_root)
    if parsed.command == "verify-promoted-config":
        return _verify_promoted_config(
            run_root, parsed.approved_bundle_sha256, parsed.promoted_config
        )
    if parsed.command == "qualify":
        evidence_root = (
            Path(parsed.evidence_root) if parsed.evidence_root else run_root / "evidence"
        )
        promoted = (
            Path(parsed.promoted_config)
            if parsed.promoted_config
            else run_root / "head-search-bundle.json"
        )
        evidence = (
            {path.stem: _digest(path) for path in sorted(evidence_root.glob("*.json"))}
            if evidence_root.is_dir()
            else {}
        )
        try:
            report = qualify_head_search(
                {
                    "run_root": run_root,
                    "runtime_id": run_root.name,
                    "bundle_sha256": _digest(promoted),
                    "evidence": evidence,
                },
                run_root,
            )
        except ValueError as error:
            if "RUN_ROOT_ALREADY_EXISTS" not in str(error):
                raise
            print(str(error), file=sys.stderr)
            return 2
        print(f"{report['status']} {report['evidence_sha256_set']}")
        return 0
    if parsed.command == "serve-teleop":
        # the closed report is read from where it was written, never from the root this owner will claim
        if parsed.report is None or not Path(parsed.report).is_file():
            print("HEAD_SEARCH_QUALIFIED_REQUIRED: pass --report", file=sys.stderr)
            return 2
        report = json.loads(Path(parsed.report).read_text(encoding="utf-8"))
        connection = serve_teleop(report, run_root, bridge_socket_root=parsed.bridge_socket_root)
        print(f"TELEOP_ACCEPTANCE {connection['owner']['pid']}")
        return 0
    print(f"HEAD_SEARCH_COMMAND_UNKNOWN: {parsed.command!r}", file=sys.stderr)
    return 2


def _digest(path: Path) -> str:
    if not Path(path).is_file():
        return ""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


if __name__ == "__main__":  # pragma: no cover - console script entry
    raise SystemExit(main())
