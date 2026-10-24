"""The selection rule, operating point, admission, bundle inputs and episode records subcommands."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from so101_demo.cli.head_search.common import _command_line, _digest, _gpu_device, _has_file
from so101_demo.cli.head_search.flags import (
    ADMISSION_OPTIONAL_FILE_FLAGS,
    ADMISSION_REQUIRED_FILE_FLAGS,
    ADMISSION_REQUIRED_FLAGS,
    BUNDLE_INPUTS_OPTIONAL_FILE_FLAGS,
    BUNDLE_INPUTS_REQUIRED_FILE_FLAGS,
    BUNDLE_INPUTS_REQUIRED_FLAGS,
    EPISODE_RECORDS_REQUIRED_FILE_FLAGS,
    EPISODE_RECORDS_REQUIRED_FLAGS,
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
    OPERATING_POINT_REQUIRED_DIRECTORY_FLAGS,
    OPERATING_POINT_REQUIRED_FILE_FLAGS,
    SELECTION_RULE_REQUIRED_FLAGS,
)
from so101_demo.cli.head_search.run import _sealed_inputs


def _selection_rule_parser() -> argparse.ArgumentParser:
    """The `measure-selection-rule` entry: the sealed config, the future measurement and the output.

    The rule of record has to exist before its measurement, so this entry takes the directory the
    measurement will own and refuses to write anything when that directory already exists; it never
    measures, renders or detects, and `so101_demo.act.head_search.operating_point_measurement` is the
    only library it calls.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-selection-rule",
        description=(
            "Record the phase-3 selection rule (the declared grid, the splits it selects on and the "
            "tie-break chain) into a brand-new output directory, before any measurement exists"
        ),
    )
    parser.add_argument(
        "--production-search-config",
        type=Path,
        help="the sealed production search configuration the grid and its two fixed values come from",
    )
    parser.add_argument(
        "--measurements-output-dir",
        type=Path,
        help="the directory the operating-point measurement will own; it must not exist yet",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="the brand-new directory the rule records own"
    )
    parser.add_argument(
        "--generation", help="the generation the rule binds to, when one is declared"
    )
    parser.add_argument(
        "--measurement-plan-sha256",
        help="the digest of the measurement plan the rule binds to, when one is declared",
    )
    return parser


def _measure_selection_rule(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the rule record to the library module."""

    parsed = _selection_rule_parser().parse_args(arguments)
    missing = [
        flag for name, flag in SELECTION_RULE_REQUIRED_FLAGS if getattr(parsed, name) is None
    ]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in SELECTION_RULE_REQUIRED_FLAGS
        # the measurement directory is the one path that must NOT exist yet: it is what proves the rule
        # was written before its measurement
        if name not in ("output_dir", "measurements_output_dir")
        and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.operating_point_measurement.documents import (
        record_selection_rule_documents,
    )

    config_path = Path(parsed.production_search_config)
    try:
        result = record_selection_rule_documents(
            production_config=json.loads(config_path.read_text(encoding="utf-8")),
            measurements_output_dir=parsed.measurements_output_dir,
            output_dir=parsed.output_dir,
            generation=parsed.generation,
            measurement_plan_sha256=parsed.measurement_plan_sha256,
            provenance={
                "production_search_config_path": str(config_path),
                "production_search_config_sha256": _digest(config_path),
                "command": _command_line(arguments, subcommand="measure-selection-rule"),
            },
            command=_command_line(arguments, subcommand="measure-selection-rule"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"SELECTION_RULE_RECORDED points={receipt['point_count']} "
        f"splits={','.join(receipt['selection_splits'])} "
        f"domains={','.join(receipt['domains'])} "
        f"rule_sha256={receipt['rule_sha256']['head']} output_dir={parsed.output_dir}"
    )
    return 0


def _operating_point_parser() -> argparse.ArgumentParser:
    """The `measure-operating-point` entry: every sealed input, the rules and the three candidates.

    Nothing is computed here beyond parsing and validating what the caller declared: the measurement is
    one library call, and the point it selects is the installed phase 3's own choice, not this entry's.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-operating-point",
        description=(
            "Measure the phase-3 operating-point frames (both domains' val images and calibration "
            "episodes) for the three frozen candidates, into a brand-new output directory, and let the "
            "installed phase 3 select each candidate's point"
        ),
    )
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--head-dataset", type=Path, help="the sealed head dataset manifest")
    parser.add_argument("--task-dataset", type=Path, help="the sealed task dataset manifest")
    parser.add_argument(
        "--dataset-config", type=Path, help="the dataset profile the scenes are rendered from"
    )
    parser.add_argument(
        "--production-search-config",
        type=Path,
        help="the sealed production search configuration the grid and its two fixed values come from",
    )
    parser.add_argument("--episode-partitions", type=Path, help="the sealed scenario partitions")
    parser.add_argument(
        "--selection-rule", type=Path, help="the head-domain rule record, written first"
    )
    parser.add_argument(
        "--task-selection-rule", type=Path, help="the task-domain rule record, written first"
    )
    parser.add_argument(
        "--frozen-candidate",
        type=Path,
        action="append",
        help="one frozen candidate document; the measurement covers exactly A, B and C",
    )
    parser.add_argument("--weights-dir", type=Path, help="the directory holding <candidate>.pt")
    parser.add_argument(
        "--output-dir", type=Path, help="the brand-new directory the measurement owns"
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument(
        "--seed-limit",
        type=int,
        help="measure only the first N calibration seeds (a declared subset, never a silent one)",
    )
    return parser


def _measure_operating_point(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the whole measurement to the library module."""

    parsed = _operating_point_parser().parse_args(arguments)
    declared = OPERATING_POINT_REQUIRED_FILE_FLAGS + OPERATING_POINT_REQUIRED_DIRECTORY_FLAGS
    missing = [flag for name, flag in declared if getattr(parsed, name) is None]
    if parsed.frozen_candidate is None:
        missing.append("--frozen-candidate")
    if parsed.output_dir is None:
        missing.append("--output-dir")
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in OPERATING_POINT_REQUIRED_FILE_FLAGS
        if not _has_file(getattr(parsed, name))
    ] + [
        str(getattr(parsed, name))
        for name, _flag in OPERATING_POINT_REQUIRED_DIRECTORY_FLAGS
        if not Path(getattr(parsed, name)).is_dir()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.operating_point_measurement.measurement import (
        measure_operating_point_measurements,
    )

    try:
        result = measure_operating_point_measurements(
            geometry_seal_path=parsed.geometry_seal,
            head_dataset_manifest_path=parsed.head_dataset,
            task_dataset_manifest_path=parsed.task_dataset,
            dataset_config_path=parsed.dataset_config,
            production_config_path=parsed.production_search_config,
            episode_partitions_path=parsed.episode_partitions,
            selection_rule_path=parsed.selection_rule,
            task_selection_rule_path=parsed.task_selection_rule,
            weights_dir=parsed.weights_dir,
            frozen_candidate_paths=list(parsed.frozen_candidate),
            output_dir=parsed.output_dir,
            device=parsed.device,
            seed_limit=parsed.seed_limit,
            command=_command_line(arguments, subcommand="measure-operating-point"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    chosen = ",".join(
        f"{domain}:{candidate}:{point['min_confidence']}/{point['tracking_iou']}"
        for domain in sorted(receipt["chosen"])
        for candidate, point in sorted(receipt["chosen"][domain].items())
    )
    print(
        f"OPERATING_POINTS_MEASURED frames={receipt['frame_count']} "
        f"candidates={receipt['candidate_count']} points={receipt['grid_point_count']} "
        f"chosen={chosen} output_dir={parsed.output_dir}"
    )
    return 0


def _admission_document_parser() -> argparse.ArgumentParser:
    """The `measure-admission` entry: the six sealed inputs, the new run root and the output directory.

    Nothing is decided here: the six sealed inputs are digested by the same helper the run uses, the
    generation is the brand-new run root's name, and the plan, the admission and the receipt are one
    library call. The entry refuses a missing or absent input before the library runs, and the library
    refuses an existing run root or output directory, a document that cannot yield a plan, and a plan the
    installed controller will not accept.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-admission",
        description=(
            "Produce the run's --admission: the flat measurement plan the installed controller is "
            "constructed with, the six-field CalibrationMeasurementAdmission for role=calibration, and "
            "the receipt that records the refusals and the single resource binding"
        ),
    )
    parser.add_argument("--dataset", type=Path, help="dataset manifest (sealed input)")
    parser.add_argument("--candidate", type=Path, help="model manifest (sealed input)")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--episode-partitions", type=Path, help="scenario partitions (sealed input)")
    parser.add_argument("--production-config", type=Path, help="the sealed production configuration")
    parser.add_argument("--camera-config", type=Path, help="the production camera configuration")
    parser.add_argument("--seal", type=Path, help="declared digests of the six sealed inputs")
    parser.add_argument(
        "--run-root", type=Path, help="the brand-new run root the run will claim; it must not exist"
    )
    parser.add_argument(
        "--output-dir", type=Path, help="the brand-new directory the plan, admission and receipt own"
    )
    parser.add_argument("--operation", default="neck_target", help="the admitted operation")
    parser.add_argument("--cpu-cores", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--gpu-device", default="0")
    parser.add_argument(
        "--search-start-rad",
        type=float,
        default=0.0,
        help="the neck angle the bounded plan starts from; it must lie in the sealed interval",
    )
    return parser


def _measure_admission(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the admission document to the library module."""

    parsed = _admission_document_parser().parse_args(arguments)
    missing = [flag for name, flag in ADMISSION_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name in ADMISSION_REQUIRED_FILE_FLAGS
        if not Path(getattr(parsed, name)).is_file()
    ] + [
        str(getattr(parsed, name))
        for name, _flag in ADMISSION_OPTIONAL_FILE_FLAGS
        if getattr(parsed, name) is not None and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search.calibration_admission_document import (
        record_admission_document,
    )
    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused

    try:
        result = record_admission_document(
            sealed_inputs=_sealed_inputs(parsed),
            run_root=parsed.run_root,
            output_dir=parsed.output_dir,
            operation=parsed.operation,
            cpu_cores=parsed.cpu_cores,
            gpu_device=_gpu_device(parsed.gpu_device),
            search_start_rad=parsed.search_start_rad,
            command=_command_line(arguments, subcommand="measure-admission"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    admission = result["admission"]
    print(
        f"ADMISSION_RECORDED generation={admission['generation']} "
        f"plan_sha256={admission['measurement_plan_sha256']} "
        f"safe_interval_rad={admission['safe_interval_rad']} output_dir={parsed.output_dir}"
    )
    return 0


def _bundle_inputs_parser() -> argparse.ArgumentParser:
    """The `measure-bundle-inputs` entry: the declared documents, the device and the output directory.

    Nothing is computed and nothing is constructed here: the entry validates the declared inputs and hands
    them to `so101_demo.act.head_search.calibration_bundle_inputs`, which constructs the installed
    controller and the production detector with the recorded values and records what it observes. The
    output directory must be brand new, exactly as every other runner's is.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-bundle-inputs",
        description=(
            "Produce the run's --bundle-inputs: the geometry and perception evidence blocks, each with the "
            "evidence phase 8 requires and the startup readback observed on the production components"
        ),
    )
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--operating-point", type=Path, help="the installed phase 3's selection document"
    )
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument(
        "--operating-point-measurements",
        type=Path,
        help="the phase-3 frame measurements the selection was made on, cited as input evidence",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="the brand-new directory the document and receipt own"
    )
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--readback-identity",
        default=None,
        help="the identity the readback's controller is constructed under",
    )
    parser.add_argument(
        "--web-bundle-root",
        type=Path,
        help="the installed teleop web bundle whose digest the runtime identity records",
    )
    return parser


def _measure_bundle_inputs(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the declaration to the library module."""

    parsed = _bundle_inputs_parser().parse_args(arguments)
    missing = [flag for name, flag in BUNDLE_INPUTS_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name in BUNDLE_INPUTS_REQUIRED_FILE_FLAGS
        if not Path(getattr(parsed, name)).is_file()
    ] + [
        str(getattr(parsed, name))
        for name, _flag in BUNDLE_INPUTS_OPTIONAL_FILE_FLAGS
        if getattr(parsed, name) is not None and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search.calibration_bundle_inputs import (
        DECLARED_PARAMETERS,
        record_bundle_inputs,
    )
    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused

    request = {
        "geometry_seal": parsed.geometry_seal,
        "production_config": parsed.production_config,
        "operating_point": parsed.operating_point,
        "frozen_candidate": parsed.frozen_candidate,
        "weights": parsed.weights,
        "output_dir": parsed.output_dir,
        "operating_point_measurements": parsed.operating_point_measurements,
        "device": parsed.device,
        "web_bundle_root": parsed.web_bundle_root,
        "command": _command_line(arguments, subcommand="measure-bundle-inputs"),
    }
    if parsed.readback_identity is not None:
        request["readback_identity"] = parsed.readback_identity
    try:
        result = record_bundle_inputs(**request)
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    unverified = sorted(result["receipt"]["unverified"])
    print(
        f"BUNDLE_INPUTS_RECORDED parameters={len(DECLARED_PARAMETERS)} "
        f"unverified={','.join(unverified) if unverified else 'none'} "
        f"detector_device={parsed.device} output_dir={parsed.output_dir}"
    )
    return 0


def _episode_records_parser() -> argparse.ArgumentParser:
    """The `measure-episode-records` entry: the measurement document, the partitions and the output.

    The entry measures nothing: phase 4's gate reads one document per declared seed, and the installed
    phase-3 flight's measurement document already holds those frames. The library re-shapes them verbatim
    and refuses a seed, a candidate's measurement or a domain that is missing.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-episode-records",
        description=(
            "Write the gate's --episode-records from the installed phase-3 measurement document: one "
            "document per declared seed, every measured frame verbatim"
        ),
    )
    parser.add_argument(
        "--operating-point-measurements", type=Path, help="the installed phase-3 measurement document"
    )
    parser.add_argument(
        "--episode-partitions", type=Path, help="the sealed scenario partitions the seeds come from"
    )
    parser.add_argument("--split", default="calibration", help="the partition the episodes belong to")
    parser.add_argument(
        "--output-dir", type=Path, help="the brand-new directory the per-seed documents own"
    )
    return parser


def _measure_episode_records(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the re-shaping to the library module."""

    parsed = _episode_records_parser().parse_args(arguments)
    missing = [flag for name, flag in EPISODE_RECORDS_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name in EPISODE_RECORDS_REQUIRED_FILE_FLAGS
        if not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is "
            f"never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.episode_records import record_episode_records

    try:
        result = record_episode_records(
            measurements=parsed.operating_point_measurements,
            partitions=parsed.episode_partitions,
            output_dir=parsed.output_dir,
            split=parsed.split,
            command=_command_line(arguments, subcommand="measure-episode-records"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"EPISODE_RECORDS_RECORDED split={receipt['split']} seeds={receipt['seed_count']} "
        f"frames={receipt['frame_count']} output_dir={parsed.output_dir}"
    )
    return 0
