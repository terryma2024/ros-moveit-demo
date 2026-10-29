"""The coarse step, MuJoCo and workspace projection measurement subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from so101_demo.cli.head_search.common import _command_line, _refuse_measurement_inputs
from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
    MEASUREMENT_REQUIRED_FLAGS,
    MUJOCO_IDENTITY_FLAGS,
    MUJOCO_REQUIRED_FLAGS,
    WORKSPACE_PROJECTION_REQUIRED_FLAGS,
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

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.coarse_step_measurement.measurement import (
        measure_coarse_step_val_sweep,
    )

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

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.mujoco_measurements import write_mujoco_measurements

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


def _workspace_projection_parser() -> argparse.ArgumentParser:
    """The `measure-workspace-projection` entry: the sealed scene, the seal and the contract.

    This flight is the one phase 6's `vertical_bounds_px` was missing: the legal pick workspace the
    geometry contract declares, projected into the sealed head camera at the neck poses the bounded search
    actually holds, with the image-space extent per pose and over the pose set. It loads the scene for the
    camera pose alone - no detector, no renderer, no GPU and no controller take part.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-workspace-projection",
        description=(
            "Project the geometry contract's declared legal pick workspace into the sealed head camera at "
            "the bounded plan's in-domain neck poses, into a brand-new output directory, and write the "
            "document the run declares under --workspace-projection"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the camera pose is read from")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--geometry-contract", type=Path, help="the contract that declares the legal pick workspace box"
    )
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the document owns")
    parser.add_argument(
        "--coarse-step-rad",
        type=float,
        default=None,
        help=(
            "the coarse step the run's own bounded plan was receipted at; without it the step is the one "
            "phase 2's selection rule chooses, and a declared step has to be a generated candidate that "
            "covers the required domain"
        ),
    )
    return parser


def _measure_workspace_projection(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the projection to the library."""

    parsed = _workspace_projection_parser().parse_args(arguments)
    refused = _refuse_measurement_inputs(parsed, WORKSPACE_PROJECTION_REQUIRED_FLAGS)
    if refused is not None:
        print(refused, file=sys.stderr)
        return 2

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.workspace_projection.writer import (
        write_head_search_workspace_projection,
    )

    try:
        result = write_head_search_workspace_projection(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            geometry_contract_path=parsed.geometry_contract,
            output_dir=parsed.output_dir,
            coarse_step_rad=parsed.coarse_step_rad,
            command=_command_line(arguments, subcommand="measure-workspace-projection"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    print(
        f"WORKSPACE_PROJECTION_PRODUCED top_px={receipt['top_px']!r} "
        f"bottom_px={receipt['bottom_px']!r} poses={receipt['pose_count']} "
        f"points={receipt['point_count']} union={receipt['union_px']} "
        f"intersection={receipt['intersection_px']} step={receipt['chosen_step_rad']!r} "
        f"({receipt['step_source']}) output_dir={parsed.output_dir}"
    )
    return 0
