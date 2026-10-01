"""The formal head search calibration CLI: run, measure-coarse-step, measure-mujoco, measure-search-timing, measure-deadband-candidates, measure-camera, verify-promoted-config, qualify.

The CLI parses arguments, validates the inputs a run declares and orchestrates nothing itself: `run`
hands the phases to `so101_demo.act.head_search_calibration_run`, where the order, the entry binding, the
trajectory precondition and the run status live (plan rule 4). Every subcommand refuses a run root that
already exists, so there is no way to resume or continue a stage. `measure-coarse-step`,
`measure-mujoco`, `measure-search-timing`, `measure-deadband-candidates` and `measure-camera` are the
measurement flights the run cannot take itself - the run declares documents, it does not render, read a
sealed model, step a simulator or close a control loop - so they are their own installed entries, validated
here and produced by `so101_demo.act.head_search_coarse_step_measurement`,
`so101_demo.act.head_search_mujoco_measurements`,
`so101_demo.act.head_search_timing_measurement`,
`so101_demo.act.head_search_deadband_measurement` and
`so101_demo.act.head_search_camera_measurement`.
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

#: a measurement flight whose inputs are missing or unreadable is refused before it renders anything
HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE = "HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE"

#: the measurement documents phases 6 and 7 consume (plan section 2 rows 6 and 7), each with the flag it
#: is declared under and its shape: `document` is one JSON object the phase cites by path and sha256,
#: `records` is the JSON list of measured records the phase itself builds its evidence from. The raw
#: coarse-step val sweep is the fifteenth: the run never measures it, it declares the sweep the installed
#: `measure-coarse-step` entry produced with the selected model. The run reads these files and never
#: invents a measurement; a run that omits one is refused at this entry.
RUN_PHASE_SIX_MEASUREMENTS = (
    ("search_timing", "--search-timing", "document"),
    ("camera_measurements", "--camera-measurements", "document"),
    ("deadband_candidates", "--deadband-candidates", "records"),
    ("workspace_projection", "--workspace-projection", "document"),
    ("fine_correction_episodes", "--fine-correction-episodes", "records"),
    ("coarse_step_observations", "--coarse-step-observations", "document"),
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

#: the `measure-coarse-step` entry: the sealed geometry, the sealed head dataset and its profile, the
#: selected model's weights and frozen candidate, and the brand-new directory the measurement owns
MEASUREMENT_REQUIRED_FLAGS = (
    ("geometry_seal", "--geometry-seal"),
    ("head_dataset", "--head-dataset"),
    ("dataset_config", "--dataset-config"),
    ("weights", "--weights"),
    ("frozen_candidate", "--frozen-candidate"),
    ("output_dir", "--output-dir"),
)

#: the `measure-mujoco` entry: the sealed scene, at least one sealed document that pins its bytes, and
#: the brand-new directory the document owns. `--mujoco-readback` is optional: it loads the scene in
#: MuJoCo and records `model.opt.timestep` next to the declaration
MUJOCO_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("output_dir", "--output-dir"),
)
MUJOCO_IDENTITY_FLAGS = (
    ("geometry_seal", "--geometry-seal"),
    ("dataset_manifest", "--dataset-manifest"),
    ("geometry_contract", "--geometry-contract"),
)

#: the `measure-search-timing` entry: the sealed scene the sweep steps the neck in, the sealed geometry
#: the controller plan and the sweep's thresholds come from, the production search configuration, the
#: sealed controller period and the brand-new directory the documents own. `--weights` is optional: with
#: it the sweep times its frames with the sealed detector, without it no frame age is invented
TIMING_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("production_search_config", "--production-search-config"),
    ("controller_config", "--controller-config"),
    ("output_dir", "--output-dir"),
)
TIMING_OPTIONAL_FILE_FLAGS = (("weights", "--weights"),)


#: the `measure-deadband-candidates` entry: the sealed scene the lock trials step the neck in, the sealed
#: geometry the controller plan, the motion corridor and the anchor cup placements come from, the
#: production search configuration, the sealed controller period, the selected candidate's frozen
#: document, the selected model's weights and the brand-new directory the documents own. At least one
#: `--candidate` has to be declared: the trials measure the candidates the run declares, never a default
DEADBAND_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("production_search_config", "--production-search-config"),
    ("controller_config", "--controller-config"),
    ("frozen_candidate", "--frozen-candidate"),
    ("weights", "--weights"),
    ("output_dir", "--output-dir"),
)
DEADBAND_CANDIDATE_FLAG = ("candidate", "--candidate")


#: the `measure-camera` entry: the sealed scene the frames are rendered in, the sealed geometry whose
#: field of view and image size are the declared camera, the production search configuration, the sealed
#: controller period, the selected candidate's frozen document, the selected model's weights and the
#: brand-new directory the documents own. `--safety-margin-declaration` is optional: it names the artefact
#: that declares `image_safety_margin_fraction` (the approved production form, the fraction of the shorter
#: production image edge this producer derives into pixels with `ceil`) or `safety_margin_px` directly, and
#: without it that field is written as null and refused rather than defaulted
CAMERA_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("production_search_config", "--production-search-config"),
    ("controller_config", "--controller-config"),
    ("frozen_candidate", "--frozen-candidate"),
    ("weights", "--weights"),
    ("output_dir", "--output-dir"),
)
CAMERA_OPTIONAL_FILE_FLAGS = (("safety_margin_declaration", "--safety-margin-declaration"),)

#: the `measure-controller-stop-config` entry: the controller's own installed declaration, the tree it was
#: built from (which has to declare the same bytes), the sealed controller configuration whose period the
#: declaration's window step is cross-checked against, and the brand-new output directory
STOP_CONFIG_REQUIRED_FLAGS = (
    ("controller_declaration", "--controller-declaration"),
    ("source_declaration", "--source-declaration"),
    ("controller_config", "--controller-config"),
    ("output_dir", "--output-dir"),
)

#: the `measure-feedback` entry: the sealed controller configuration that declares both rates, and the
#: optional artefact that declares the quantisation resolution. Without that artefact the resolution is
#: written as null and refused, exactly like the camera measurement's undeclared safety margin; the
#: retained declaration `config/act/feedback-quantisation-declaration-v1.json` states this platform's
#: explicit zero with its basis (HS-305)
FEEDBACK_REQUIRED_FLAGS = (
    ("controller_config", "--controller-config"),
    ("output_dir", "--output-dir"),
)
FEEDBACK_OPTIONAL_FILE_FLAGS = (("quantisation_declaration", "--quantisation-declaration"),)

#: the three stop flights: the sealed scene they step, the sealed geometry that pins it, the production
#: search configuration whose declared values they read, the sealed controller period, and the output
#: directory. None of them loads a detector or touches a GPU
STOP_FLIGHT_REQUIRED_FLAGS = (
    ("scene", "--scene"),
    ("geometry_seal", "--geometry-seal"),
    ("production_search_config", "--production-search-config"),
    ("controller_config", "--controller-config"),
    ("output_dir", "--output-dir"),
)


def _measurement_parser() -> argparse.ArgumentParser:
    """The `measure-coarse-step` entry: it declares inputs and calls one library function.

    This is the measurement flight the run cannot take itself (the run declares documents, it does not
    render): the installed program rebuilds the sealed head val scenes, walks the bounded stops of every
    generated candidate step with the selected model, and writes the raw observations, the decision and
    the receipt. Nothing is computed here beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-coarse-step",
        description=(
            "Measure the coarse-step val sweep once, into a brand-new output directory, and choose "
            "coarse_step_rad from the head val split"
        ),
    )
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--head-dataset", type=Path, help="the sealed head dataset manifest")
    parser.add_argument("--dataset-config", type=Path, help="the dataset profile it was rendered from")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the sweep owns")
    parser.add_argument("--scene-limit", type=int, help="measure only the first N val scenes")
    parser.add_argument("--passes", type=int, default=1, help="independent passes over every stop")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--split", default="val")
    parser.add_argument("--domain", default="head")
    return parser


def _measure_coarse_step(arguments: list[str]) -> int:
    """Validate the declared measurement inputs, then hand the flight to the library module."""

    parsed = _measurement_parser().parse_args(arguments)
    missing = [
        flag for name, flag in MEASUREMENT_REQUIRED_FLAGS if getattr(parsed, name) is None
    ]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in MEASUREMENT_REQUIRED_FLAGS
        if name != "output_dir" and not Path(getattr(parsed, name)).is_file()
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

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_coarse_step_measurement import measure_coarse_step_val_sweep

    try:
        result = measure_coarse_step_val_sweep(
            geometry_seal_path=parsed.geometry_seal,
            dataset_manifest_path=parsed.head_dataset,
            dataset_config_path=parsed.dataset_config,
            weights_path=parsed.weights,
            frozen_candidate_path=parsed.frozen_candidate,
            output_dir=parsed.output_dir,
            split=parsed.split,
            domain=parsed.domain,
            scene_limit=parsed.scene_limit,
            passes=parsed.passes,
            device=parsed.device,
            command=_command_line(arguments, subcommand="measure-coarse-step"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"COARSE_STEP_MEASURED {receipt['chosen_coarse_step_rad']} "
        f"scenes={receipt['scene_count']} candidates={receipt['candidate_count']} "
        f"passes={receipt['passes']} output_dir={parsed.output_dir}"
    )
    return 0


def _mujoco_parser() -> argparse.ArgumentParser:
    """The `measure-mujoco` entry: it declares the sealed scene and calls one library function.

    The document phase 7 declares under `--mujoco-measurements` carries one number, the sealed MuJoCo
    model's simulation timestep, which is a declaration of the sealed scene rather than a measurement
    flight. Nothing is computed here beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-mujoco",
        description=(
            "Read the sealed MuJoCo scene's simulation timestep once, into a brand-new output directory, "
            "and write the document the run declares under --mujoco-measurements"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the runtime steps")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--dataset-manifest", type=Path, help="the sealed head dataset manifest")
    parser.add_argument("--geometry-contract", type=Path, help="the sealed geometry contract")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the document owns")
    parser.add_argument(
        "--mujoco-readback",
        action="store_true",
        help="load the scene in MuJoCo and record model.opt.timestep next to the declaration",
    )
    return parser


def _measure_mujoco(arguments: list[str]) -> int:
    """Validate the declared scene and its sealed identities, then hand the flight to the library."""

    parsed = _mujoco_parser().parse_args(arguments)
    missing = [flag for name, flag in MUJOCO_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if not missing and all(getattr(parsed, name) is None for name, _flag in MUJOCO_IDENTITY_FLAGS):
        missing = [flag for _name, flag in MUJOCO_IDENTITY_FLAGS]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    declared = MUJOCO_REQUIRED_FLAGS + MUJOCO_IDENTITY_FLAGS
    absent = [
        str(getattr(parsed, name))
        for name, _flag in declared
        if name != "output_dir" and getattr(parsed, name) is not None
        and not Path(getattr(parsed, name)).is_file()
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

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_mujoco_measurements import write_mujoco_measurements

    try:
        result = write_mujoco_measurements(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            dataset_manifest_path=parsed.dataset_manifest,
            geometry_contract_path=parsed.geometry_contract,
            output_dir=parsed.output_dir,
            mujoco_readback=parsed.mujoco_readback,
            command=_command_line(arguments, subcommand="measure-mujoco"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"MUJOCO_TIMESTEP_PRODUCED {receipt['simulation_timestep_s']} "
        f"scene={receipt['scene_path']} readback={receipt['mujoco_readback']} "
        f"output_dir={parsed.output_dir}"
    )
    return 0


def _deadband_parser() -> argparse.ArgumentParser:
    """The `measure-deadband-candidates` entry: it declares the sealed inputs and the candidates.

    This is the closed-loop flight the run cannot take itself: the installed program walks the production
    controller's own bounded plan in the sealed MuJoCo scene, renders the head camera, detects the cup with
    the selected model and feeds the measured centre error back as the next correction, once per declared
    deadband candidate. Nothing is computed here beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-deadband-candidates",
        description=(
            "Run one closed-loop lock trial per declared deadband candidate in the sealed MuJoCo scene, "
            "into a brand-new output directory, and write the deadband candidates document phase 6 reads"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the trials step")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument(
        "--candidate",
        type=float,
        action="append",
        help="a declared deadband candidate in pixels; repeat once per candidate",
    )
    parser.add_argument("--anchor", action="append", help="trial only these sealed anchors")
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-stop settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    parser.add_argument("--max-frames", type=int, default=None, help="the per-trial frame budget")
    return parser


def _measure_deadband_candidates(arguments: list[str]) -> int:
    """Validate the declared inputs and candidates, then hand the lock trials to the library."""

    parsed = _deadband_parser().parse_args(arguments)
    missing = [flag for name, flag in DEADBAND_REQUIRED_FLAGS if getattr(parsed, name) is None]
    name, flag = DEADBAND_CANDIDATE_FLAG
    if not getattr(parsed, name):
        missing.append(flag)
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in DEADBAND_REQUIRED_FLAGS
        if name != "output_dir" and not Path(getattr(parsed, name)).is_file()
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

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_deadband_measurement import (
        DEFAULT_MAX_FRAMES,
        SETTLE_CONSECUTIVE_STEPS,
        write_head_search_deadband_measurement,
    )

    optional = {"max_frames": DEFAULT_MAX_FRAMES, "settle_consecutive_steps": SETTLE_CONSECUTIVE_STEPS}
    for key in ("max_settle_s", "settle_consecutive_steps", "max_frames"):
        if getattr(parsed, key) is not None:
            optional[key] = getattr(parsed, key)
    try:
        result = write_head_search_deadband_measurement(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            frozen_candidate_path=parsed.frozen_candidate,
            weights_path=parsed.weights,
            output_dir=parsed.output_dir,
            candidates=parsed.candidate,
            anchors=parsed.anchor,
            device=parsed.device,
            command=_command_line(arguments, subcommand="measure-deadband-candidates"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    locking = [
        record
        for record in receipt["records"]
        if record["longest_locked_run_frames"] >= receipt["lock_frames_required"]
        and record["direction_reversals"] == 0
    ]
    print(
        f"DEADBAND_CANDIDATES_MEASURED candidates={receipt['candidate_count']} "
        f"anchors={','.join(receipt['anchor_names'])} trials={receipt['trial_count']} "
        f"locking={len(locking)} output_dir={parsed.output_dir}"
    )
    return 0


def _camera_parser() -> argparse.ArgumentParser:
    """The `measure-camera` entry: it declares the sealed inputs and the frame budget.

    This is the flight the run cannot take itself: the installed program holds the production controller's
    own settled poses in the sealed MuJoCo scene, renders the head camera once per frame period, detects
    the cup with the selected model and measures the spread of the detected centre, which is the
    `centre_jitter_rad` phase 6 starts `center_deadband_px` from. It measures that field and only that
    field: the image safety margin is a declaration, so it is read from `--safety-margin-declaration` or
    refused, never defaulted.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-camera",
        description=(
            "Hold every sealed anchor's settled poses in the sealed MuJoCo scene, measure the detected "
            "cup centre's spread frame by frame, and write the camera measurements document phase 6 reads"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the frames are rendered in")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument(
        "--safety-margin-declaration",
        type=Path,
        help=(
            "the artefact that declares image_safety_margin_fraction (derived with ceil against the sealed "
            "image dimensions) or safety_margin_px directly; without one the field is refused, not defaulted"
        ),
    )
    parser.add_argument("--anchor", action="append", help="measure only these sealed anchors")
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--frames-per-pose", type=int, default=None, help="how many repeated frames each pose is held for"
    )
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-pose settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    return parser


def _measure_camera(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the pose holds to the library.

    The measurement itself is complete when the jitter has been measured; a field no artefact declares is
    a refusal this entry reports with the library's own code and exit status 2, even though the document
    carrying the measured jitter is on disk - a caller must never read a defaulted margin out of it.
    """

    parsed = _camera_parser().parse_args(arguments)
    missing = [flag for name, flag in CAMERA_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in CAMERA_REQUIRED_FLAGS + CAMERA_OPTIONAL_FILE_FLAGS
        if getattr(parsed, name) is not None
        and name != "output_dir"
        and not Path(getattr(parsed, name)).is_file()
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

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_camera_measurement import (
        DEFAULT_FRAMES_PER_POSE,
        SETTLE_CONSECUTIVE_STEPS,
        write_head_search_camera_measurement,
    )

    optional = {
        "frames_per_pose": DEFAULT_FRAMES_PER_POSE,
        "settle_consecutive_steps": SETTLE_CONSECUTIVE_STEPS,
    }
    for key in ("frames_per_pose", "max_settle_s", "settle_consecutive_steps"):
        if getattr(parsed, key) is not None:
            optional[key] = getattr(parsed, key)
    try:
        result = write_head_search_camera_measurement(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            frozen_candidate_path=parsed.frozen_candidate,
            weights_path=parsed.weights,
            output_dir=parsed.output_dir,
            safety_margin_declaration_path=parsed.safety_margin_declaration,
            anchors=parsed.anchor,
            device=parsed.device,
            command=_command_line(arguments, subcommand="measure-camera"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"CAMERA_MEASUREMENTS_MEASURED centre_jitter_px={receipt['centre_jitter_px']!r} "
        f"centre_jitter_rad={receipt['centre_jitter_rad']!r} "
        f"poses={receipt['pose_count']} frames={receipt['frame_count']} "
        f"rad_per_px={receipt['rad_per_px']!r} "
        f"safety_margin_px={receipt['safety_margin_px']!r} output_dir={parsed.output_dir}"
    )
    for refusal in receipt["refusals"]:
        print(f"{refusal['code']}: {refusal['detail']}", file=sys.stderr)
    return 2 if receipt["refusals"] else 0


def _refuse_measurement_inputs(parsed, required, optional_file_flags=()) -> str | None:
    """The shared input check of a measurement entry: a missing or absent declaration is refused here."""

    missing = [flag for name, flag in required if getattr(parsed, name) is None]
    if missing:
        return f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}"
    absent = [
        str(getattr(parsed, name))
        for name, _flag in tuple(required) + tuple(optional_file_flags)
        if getattr(parsed, name) is not None
        and name != "output_dir"
        and not Path(getattr(parsed, name)).is_file()
    ]
    if absent:
        return f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}"
    if parsed.output_dir.exists():
        return (
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a measurement is never "
            f"resumed, continued or overwritten"
        )
    return None


def _stop_config_parser() -> argparse.ArgumentParser:
    """The `measure-controller-stop-config` entry: it reads the controller's own declaration.

    This is not a flight: the controller's stopped tolerance is a constant the running controller declares,
    so the entry cites it from the installed header, checks the source tree declares the same bytes, and
    cross-checks the declaration's window step against the sealed controller period. A header that declares
    no tolerance is refused rather than defaulted.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-controller-stop-config",
        description=(
            "Cite the controller's own declared stopped tolerance (the installed ControllerStopWitness "
            "constant) as the document phase 7 reads its third envelope term from"
        ),
    )
    parser.add_argument(
        "--controller-declaration", type=Path, help="the installed controller header that declares it"
    )
    parser.add_argument(
        "--source-declaration", type=Path, help="the same declaration in the tree it was built from"
    )
    parser.add_argument("--controller-config", type=Path, help="the sealed controller configuration")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    return parser


def _measure_controller_stop_config(arguments: list[str]) -> int:
    parsed = _stop_config_parser().parse_args(arguments)
    refusal = _refuse_measurement_inputs(parsed, STOP_CONFIG_REQUIRED_FLAGS)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_stop_measurement import write_controller_stop_config

    try:
        result = write_controller_stop_config(
            installed_declaration=parsed.controller_declaration,
            source_declaration=parsed.source_declaration,
            controller_config_path=parsed.controller_config,
            output_dir=parsed.output_dir,
            command=_command_line(arguments, subcommand="measure-controller-stop-config"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"CONTROLLER_STOP_CONFIG_DECLARED "
        f"stopped_tolerance_rad_s={receipt['stopped_tolerance_rad_s']!r} "
        f"window_samples={receipt['window']['samples']} "
        f"window_step_s={receipt['window']['step_s']!r} "
        f"controller_cycle_period_s={receipt['controller_cycle_period_s']!r} "
        f"measured_here=False output_dir={parsed.output_dir}"
    )
    return 0


def _feedback_parser() -> argparse.ArgumentParser:
    """The `measure-feedback` entry: the declared period, and the quantisation or its refusal."""

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-feedback",
        description=(
            "Read the declared feedback period the stop path consumes and the declared feedback quantisation "
            "resolution; without a declaration of the resolution the field is refused, never defaulted, and "
            "an explicitly zero resolution has to state its basis"
        ),
    )
    parser.add_argument("--controller-config", type=Path, help="the sealed controller configuration")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument(
        "--quantisation-declaration",
        type=Path,
        help=(
            "the artefact that declares quantisation_rad (explicitly zero needs the basis of the zero), or "
            "counts_per_revolution with joint_travel_rad; without one the field is written as null and refused"
        ),
    )
    return parser


def _measure_feedback(arguments: list[str]) -> int:
    parsed = _feedback_parser().parse_args(arguments)
    refusal = _refuse_measurement_inputs(
        parsed, FEEDBACK_REQUIRED_FLAGS, FEEDBACK_OPTIONAL_FILE_FLAGS
    )
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_stop_measurement import write_feedback_measurements

    try:
        result = write_feedback_measurements(
            controller_config_path=parsed.controller_config,
            output_dir=parsed.output_dir,
            quantisation_declaration_path=parsed.quantisation_declaration,
            command=_command_line(arguments, subcommand="measure-feedback"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"FEEDBACK_MEASUREMENTS_MEASURED period_s={receipt['period_s']!r} "
        f"feedback_rate_hz={receipt['feedback_rate_hz']!r} "
        f"controller_cycle_period_s={receipt['controller_cycle_period_s']!r} "
        f"quantisation_rad={receipt['quantisation_rad']!r} output_dir={parsed.output_dir}"
    )
    for record in receipt["refusals"]:
        print(f"{record['code']}: {record['detail']}", file=sys.stderr)
    return 2 if receipt["refusals"] else 0


def _stop_flight_parser(subcommand: str, description: str) -> argparse.ArgumentParser:
    """One of the three stop flights: the sealed scene, the sealed inputs and the brand-new directory."""

    parser = argparse.ArgumentParser(
        prog=f"so101_head_search_calibration {subcommand}", description=description
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the neck is stepped in")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument("--anchor", action="append", help="measure only these sealed anchors")
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-pose settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    parser.add_argument(
        "--no-realtime",
        dest="realtime",
        action="store_false",
        default=True,
        help="step the plant as fast as the machine allows instead of pacing it to the monotonic clock",
    )
    return parser


def _measure_stationary(arguments: list[str]) -> int:
    parser = _stop_flight_parser(
        "measure-stationary",
        "Hold the production controller's own settled poses in the sealed MuJoCo scene and sample the "
        "monitored joints' velocities at the declared feedback period",
    )
    parser.add_argument(
        "--samples-per-pose", type=int, default=None, help="how many feedback periods each pose is held for"
    )
    parsed = parser.parse_args(arguments)
    refusal = _refuse_measurement_inputs(parsed, STOP_FLIGHT_REQUIRED_FLAGS)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_stop_measurement import (
        DEFAULT_SAMPLES_PER_POSE,
        SETTLE_CONSECUTIVE_STEPS,
        write_stationary_measurements,
    )

    optional = {"samples_per_pose": DEFAULT_SAMPLES_PER_POSE}
    for key, default in (
        ("samples_per_pose", DEFAULT_SAMPLES_PER_POSE),
        ("max_settle_s", None),
        ("settle_consecutive_steps", SETTLE_CONSECUTIVE_STEPS),
    ):
        value = getattr(parsed, key)
        optional[key] = default if value is None else value
    if optional["max_settle_s"] is None:
        optional.pop("max_settle_s")
    try:
        result = write_stationary_measurements(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            output_dir=parsed.output_dir,
            anchors=parsed.anchor,
            realtime=parsed.realtime,
            command=_command_line(arguments, subcommand="measure-stationary"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"STATIONARY_MEASUREMENTS_MEASURED "
        f"p99_9_velocity_rad_s={receipt['p99_9_velocity_rad_s']!r} "
        f"max_velocity_rad_s={receipt['max_velocity_rad_s']!r} poses={receipt['pose_count']} "
        f"samples={receipt['sample_count']} samples_per_pose={receipt['samples_per_pose']} "
        f"feedback_period_s={receipt['feedback_period_s']!r} output_dir={parsed.output_dir}"
    )
    return 0


def _measure_controller_submissions(arguments: list[str]) -> int:
    parser = _stop_flight_parser(
        "measure-controller-submissions",
        "Submit the installed production controller's own targets through the admission port and record the "
        "simulation-time goal-admission lead of every submission",
    )
    parsed = parser.parse_args(arguments)
    refusal = _refuse_measurement_inputs(parsed, STOP_FLIGHT_REQUIRED_FLAGS)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_stop_measurement import (
        SETTLE_CONSECUTIVE_STEPS,
        write_controller_submissions,
    )

    optional = {}
    if parsed.max_settle_s is not None:
        optional["max_settle_s"] = parsed.max_settle_s
    optional["settle_consecutive_steps"] = (
        SETTLE_CONSECUTIVE_STEPS
        if parsed.settle_consecutive_steps is None
        else parsed.settle_consecutive_steps
    )
    try:
        result = write_controller_submissions(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            output_dir=parsed.output_dir,
            anchors=parsed.anchor,
            realtime=parsed.realtime,
            command=_command_line(arguments, subcommand="measure-controller-submissions"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"CONTROLLER_SUBMISSIONS_MEASURED minimum_lead_s={receipt['minimum_lead_s']!r} "
        f"maximum_lead_s={receipt['maximum_lead_s']!r} lead_spread_s={receipt['lead_spread_s']!r} "
        f"submissions={receipt['submission_count']} control_period_s={receipt['control_period_s']!r} "
        f"time_base={receipt['time_base']} output_dir={parsed.output_dir}"
    )
    return 0


def _measure_stop_proofs(arguments: list[str]) -> int:
    parser = _stop_flight_parser(
        "measure-stop-proofs",
        "Revoke real neck motions at the declared offsets and prove every stop with the installed stop "
        "criterion at the third consecutive qualifying feedback receipt",
    )
    parser.add_argument(
        "--revoke-offset-s",
        type=float,
        action="append",
        default=None,
        help="how long after the motion starts the revoke is requested, in simulation seconds",
    )
    parser.add_argument(
        "--stop-budget-s",
        type=float,
        default=None,
        help="how long a stop proof may look for three consecutive qualifying receipts",
    )
    parsed = parser.parse_args(arguments)
    refusal = _refuse_measurement_inputs(parsed, STOP_FLIGHT_REQUIRED_FLAGS)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_stop_measurement import (
        DEFAULT_STOP_BUDGET_S,
        SETTLE_CONSECUTIVE_STEPS,
        write_stop_proofs,
    )

    optional = {
        "stop_budget_s": DEFAULT_STOP_BUDGET_S if parsed.stop_budget_s is None else parsed.stop_budget_s,
        "settle_consecutive_steps": (
            SETTLE_CONSECUTIVE_STEPS
            if parsed.settle_consecutive_steps is None
            else parsed.settle_consecutive_steps
        ),
    }
    if parsed.max_settle_s is not None:
        optional["max_settle_s"] = parsed.max_settle_s
    if parsed.revoke_offset_s:
        optional["revoke_offsets_s"] = parsed.revoke_offset_s
    try:
        result = write_stop_proofs(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            output_dir=parsed.output_dir,
            anchors=parsed.anchor,
            realtime=parsed.realtime,
            command=_command_line(arguments, subcommand="measure-stop-proofs"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"STOP_PROOFS_MEASURED p99_9_latency_s={receipt['p99_9_latency_s']!r} "
        f"slowest_latency_s={receipt['slowest_latency_s']!r} proofs={receipt['proof_count']} "
        f"feedback_period_s={receipt['feedback_period_s']!r} "
        f"declared_production_latency_s={receipt['declared_production_latency_s']!r} "
        f"exceedances={receipt['exceedance_count']} output_dir={parsed.output_dir}"
    )
    return 0


def _timing_parser() -> argparse.ArgumentParser:
    """The `measure-search-timing` entry: it declares the sealed inputs and calls one library function.

    This is the measurement flight the run cannot take itself: the installed program walks the production
    controller's own bounded stop points in the sealed MuJoCo scene, commanding the scene's neck joint at
    the sealed controller period, applies the declared settle rule to every stop, and - when a detector is
    declared - times one frame per declared frame period of simulation time. Nothing is computed here
    beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-search-timing",
        description=(
            "Walk the bounded stop-point sweep of the production head search controller in the sealed "
            "MuJoCo scene once, into a brand-new output directory, and write the search timing document "
            "phase 6 reads and - with a detector - the frame age document phase 7 reads"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the sweep steps")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--weights", type=Path, help="the sealed detector weights, when frames are timed")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument("--anchor", action="append", help="measure only these sealed anchors")
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-stop settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    return parser


def _measure_search_timing(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the sweep to the library module."""

    parsed = _timing_parser().parse_args(arguments)
    missing = [flag for name, flag in TIMING_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    declared = TIMING_REQUIRED_FLAGS
    absent = [
        str(getattr(parsed, name))
        for name, _flag in declared
        if name != "output_dir" and not Path(getattr(parsed, name)).is_file()
    ] + [
        str(getattr(parsed, name))
        for name, _flag in TIMING_OPTIONAL_FILE_FLAGS
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

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_timing_measurement import (
        DEFAULT_MAX_SETTLE_S,
        SETTLE_CONSECUTIVE_STEPS,
        write_head_search_timing_measurement,
    )

    optional = {
        name: getattr(parsed, name)
        for name, _flag in (
            ("max_settle_s", "--max-settle-s"),
            ("settle_consecutive_steps", "--settle-consecutive-steps"),
        )
        if getattr(parsed, name) is not None
    }
    if "max_settle_s" not in optional:
        optional["max_settle_s"] = DEFAULT_MAX_SETTLE_S
    if "settle_consecutive_steps" not in optional:
        optional["settle_consecutive_steps"] = SETTLE_CONSECUTIVE_STEPS
    try:
        result = write_head_search_timing_measurement(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            weights_path=parsed.weights,
            output_dir=parsed.output_dir,
            anchors=parsed.anchor,
            device=parsed.device,
            command=_command_line(arguments, subcommand="measure-search-timing"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"SEARCH_TIMING_MEASURED p99_settle_s={receipt['p99_settle_s']} "
        f"p99_frame_s={receipt['p99_frame_s']} stops={receipt['stable_stop_count']} "
        f"frames={receipt['frame_count']} anchors={','.join(receipt['anchors'])} "
        f"output_dir={parsed.output_dir}"
    )
    return 0


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


def _command_line(arguments: Sequence[str], *, subcommand: str = "run") -> str:
    return (
        f"ros2 run so101_demo_py so101_head_search_calibration {subcommand} "
        + " ".join(shlex.quote(str(item)) for item in arguments)
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
    # the one measurement the run cannot take itself is its own installed entry, never a script
    if arguments[:1] == ["measure-coarse-step"]:
        return _measure_coarse_step(arguments[1:])
    # the sealed scene's own declaration is the other document the run declares but does not read itself
    if arguments[:1] == ["measure-mujoco"]:
        return _measure_mujoco(arguments[1:])
    # the bounded stop-point sweep's settle and frame timing is the third flight the run cannot take
    if arguments[:1] == ["measure-search-timing"]:
        return _measure_search_timing(arguments[1:])
    # the closed-loop deadband lock trials are the fourth flight the run cannot take
    if arguments[:1] == ["measure-deadband-candidates"]:
        return _measure_deadband_candidates(arguments[1:])
    # the camera's centre jitter is the fifth flight the run cannot take; its safety margin is a
    # declaration this entry reads or refuses, never a number it makes up
    if arguments[:1] == ["measure-camera"]:
        return _measure_camera(arguments[1:])
    # the controller's stopped tolerance is a declaration of the running controller: this entry cites it
    if arguments[:1] == ["measure-controller-stop-config"]:
        return _measure_controller_stop_config(arguments[1:])
    # the feedback period is declared; the feedback resolution is declared or refused, never defaulted
    if arguments[:1] == ["measure-feedback"]:
        return _measure_feedback(arguments[1:])
    # the stationary velocity noise, the goal-admission lead and the stop proofs are the last three flights
    if arguments[:1] == ["measure-stationary"]:
        return _measure_stationary(arguments[1:])
    if arguments[:1] == ["measure-controller-submissions"]:
        return _measure_controller_submissions(arguments[1:])
    if arguments[:1] == ["measure-stop-proofs"]:
        return _measure_stop_proofs(arguments[1:])
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
