"""The deadband, fine correction, scenario and camera measurement subcommands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from so101_demo.cli.head_search.common import _command_line
from so101_demo.cli.head_search.flags import (
    CAMERA_OPTIONAL_FILE_FLAGS,
    CAMERA_REQUIRED_FLAGS,
    DEADBAND_CANDIDATE_FLAG,
    DEADBAND_REQUIRED_FLAGS,
    FINE_CORRECTION_REQUIRED_FLAGS,
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
    SCENARIO_REQUIRED_FLAGS,
)


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
    from so101_demo.act.head_search_deadband_measurement.contracts import DEFAULT_MAX_FRAMES
    from so101_demo.act.head_search_deadband_measurement.writer import (
        write_head_search_deadband_measurement,
    )
    from so101_demo.act.head_search_timing_measurement.contracts import SETTLE_CONSECUTIVE_STEPS

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


def _fine_correction_parser() -> argparse.ArgumentParser:
    """The `measure-fine-correction-episodes` entry: the sealed inputs, the split and the budget.

    This is the closed-loop flight the run cannot take itself: one episode per held-out seed of the
    declared split, in that seed's own prepared scene, driven by the production controller's bounded sweep
    and its own fine corrections, with the head camera and the selected model closing the loop. Nothing is
    computed here beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-fine-correction-episodes",
        description=(
            "Run one closed-loop episode per held-out seed of the declared scenario split, in the scene "
            "that seed prepares, and write the fine-correction episodes document phase 6 reads"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the episodes step")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the sealed production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument(
        "--dataset-config", type=Path, help="the head dataset profile every seed's scene is prepared from"
    )
    parser.add_argument(
        "--scenario-partitions", type=Path, help="the tracked source of the head-search seed partitions"
    )
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the documents own")
    parser.add_argument(
        "--split",
        default="held_out_evaluation",
        help="the declared split whose seeds are measured (never the calibration split)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        action="append",
        help="measure only these seeds of the declared split; repeat once per seed",
    )
    parser.add_argument(
        "--anchor",
        action="append",
        help=(
            "the sealed anchor every episode starts from (default `left`, the anchor whose start lies "
            "inside the HS-302 corridor and whose sweep sees the held-out scenes' cup)"
        ),
    )
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--generator-commit",
        default="unrecorded",
        help="the commit the dataset profile is used at (the renderer records it, it changes no scene)",
    )
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-stop settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    parser.add_argument("--max-frames", type=int, default=None, help="the per-episode frame budget")
    parser.add_argument(
        "--max-fine-corrections",
        type=int,
        default=None,
        help=(
            "the harness's own measurement budget for one episode; an episode that reaches it refuses the "
            "document rather than understating the maximum (default 8, never the calibrated value)"
        ),
    )
    parser.add_argument(
        "--max-fine-total-rad",
        type=float,
        default=None,
        help="the harness's own cumulative measurement budget for one episode, in radians (default 2.0)",
    )
    return parser


def _measure_fine_correction_episodes(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the closed-loop episodes to the library."""

    parsed = _fine_correction_parser().parse_args(arguments)
    missing = [flag for name, flag in FINE_CORRECTION_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    absent = [
        str(getattr(parsed, name))
        for name, _flag in FINE_CORRECTION_REQUIRED_FLAGS
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
    from so101_demo.act.head_search_fine_correction_episodes.contracts import (
        DEFAULT_MAX_FRAMES,
        DEFAULT_MEASUREMENT_BUDGET,
    )
    from so101_demo.act.head_search_fine_correction_episodes.writer import (
        write_head_search_fine_correction_episodes,
    )
    from so101_demo.act.head_search_timing_measurement.contracts import SETTLE_CONSECUTIVE_STEPS

    optional = {"max_frames": DEFAULT_MAX_FRAMES, "settle_consecutive_steps": SETTLE_CONSECUTIVE_STEPS}
    for key in ("max_settle_s", "settle_consecutive_steps", "max_frames"):
        if getattr(parsed, key) is not None:
            optional[key] = getattr(parsed, key)
    budget = dict(DEFAULT_MEASUREMENT_BUDGET)
    if parsed.max_fine_corrections is not None:
        budget["max_fine_corrections"] = parsed.max_fine_corrections
    if parsed.max_fine_total_rad is not None:
        budget["max_fine_total_rad"] = parsed.max_fine_total_rad
    try:
        result = write_head_search_fine_correction_episodes(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            frozen_candidate_path=parsed.frozen_candidate,
            weights_path=parsed.weights,
            dataset_config_path=parsed.dataset_config,
            scenario_partitions_path=parsed.scenario_partitions,
            output_dir=parsed.output_dir,
            seeds=parsed.seed,
            split=parsed.split,
            anchors=parsed.anchor or ["left"],
            device=parsed.device,
            generator_commit=parsed.generator_commit,
            measurement_budget=budget,
            command=_command_line(arguments, subcommand="measure-fine-correction-episodes"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    for refused in receipt["refused_episodes"]:
        print(
            f"{refused['failure_code']}: the episode {refused['episode_id']} did not lock "
            f"({refused['failure_detail']})",
            file=sys.stderr,
        )
    succeeded = [
        record for record in receipt["records"] if record["succeeded"] is True
    ]
    print(
        f"FINE_CORRECTION_EPISODES_MEASURED episodes={receipt['episode_count']} "
        f"succeeded={receipt['succeeded_count']} refused={receipt['refused_count']} "
        f"split={receipt['split']} anchor={','.join(receipt['anchor_names'])} "
        f"max_fine_corrections_observed="
        f"{max((record['fine_corrections'] for record in succeeded), default=0)} "
        f"max_cumulative_fine_correction_rad="
        f"{max((sum(record['fine_corrections_rad']) for record in succeeded), default=0.0)!r} "
        f"output_dir={parsed.output_dir}"
    )
    return 0


def _scenario_parser() -> argparse.ArgumentParser:
    """The `measure-scenarios` entry: the sealed inputs, the campaign root and the declared subset.

    This is the scenario flight: the forty declared qualification scenarios, one at a time, each in its
    own prepared scene, from its own declared anchor, with the production controller's bounded sweep and
    its own fine corrections, and with the selected model closing the loop. Nothing is computed here
    beyond parsing and validating what the caller declared.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-scenarios",
        description=(
            "Run the declared qualification scenarios one at a time in the closed loop, journal every "
            "outcome honestly and write the scenarios document, its journal and its receipt"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the scenarios step")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument(
        "--production-search-config", type=Path, help="the promoted production search configuration"
    )
    parser.add_argument(
        "--controller-config", type=Path, help="the sealed controller configuration (the control period)"
    )
    parser.add_argument("--frozen-candidate", type=Path, help="the selected frozen candidate document")
    parser.add_argument("--weights", type=Path, help="the selected model's weights file")
    parser.add_argument(
        "--dataset-config", type=Path, help="the head dataset profile every scenario is prepared from"
    )
    parser.add_argument(
        "--scenario-partitions", type=Path, help="the tracked source of the head-search seed partitions"
    )
    parser.add_argument("--output-dir", type=Path, help="the brand-new run root the documents own")
    parser.add_argument(
        "--evidence-root", type=Path, help="the registered campaign root the ownership gate checks"
    )
    parser.add_argument(
        "--final-run", type=Path, help="the frozen runtime of record whose identity the run must hold"
    )
    parser.add_argument(
        "--seed",
        type=int,
        action="append",
        help="run only these declared qualification seeds; repeat once per seed",
    )
    parser.add_argument("--device", default="cuda", help="the detector device (never a CPU fallback)")
    parser.add_argument(
        "--generator-commit",
        default="unrecorded",
        help="the commit the dataset profile is used at (it changes no scene)",
    )
    parser.add_argument("--max-settle-s", type=float, default=None, help="the per-stop settle budget")
    parser.add_argument(
        "--settle-consecutive-steps", type=int, default=None, help="the consecutive quiet control steps"
    )
    parser.add_argument("--max-frames", type=int, default=None, help="the per-attempt frame budget")
    parser.add_argument(
        "--interruption-frame",
        type=int,
        default=None,
        help="the frame index at which the declared interrupted classes are stopped fail-closed",
    )
    parser.add_argument(
        "--expected-source-commit", help="the frozen runtime's source commit the identity must match"
    )
    parser.add_argument(
        "--expected-production-config-sha256",
        help="the promoted config digest the identity must match",
    )
    parser.add_argument("--expected-values-sha256", help="the 17 values' digest the identity must match")
    parser.add_argument(
        "--expected-weights-sha256", help="the detector weights digest the identity must match"
    )
    parser.add_argument(
        "--expected-package-prefix", help="the `ros2 pkg prefix so101_demo_py` the gate must observe"
    )
    return parser


def _measure_scenarios(arguments: list[str]) -> int:
    """Validate the declared inputs, then hand the closed-loop scenarios to the library."""

    parsed = _scenario_parser().parse_args(arguments)
    missing = [flag for name, flag in SCENARIO_REQUIRED_FLAGS if getattr(parsed, name) is None]
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    # the campaign root the gate checks is a directory; every other declared input is a file
    absent = [
        str(getattr(parsed, name))
        for name, _flag in SCENARIO_REQUIRED_FLAGS
        if name != "output_dir"
        and not (
            Path(getattr(parsed, name)).is_dir()
            if name == "evidence_root"
            else Path(getattr(parsed, name)).is_file()
        )
    ]
    if absent:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: no such input {', '.join(sorted(absent))}",
            file=sys.stderr,
        )
        return 2
    if parsed.output_dir.exists():
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: {parsed.output_dir} exists; a qualification run "
            f"is never resumed, continued or overwritten",
            file=sys.stderr,
        )
        return 2

    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_scenarios.contracts import DEFAULT_MAX_FRAMES
    from so101_demo.act.head_search_scenarios.writer import write_head_search_scenarios
    from so101_demo.act.head_search_timing_measurement.contracts import SETTLE_CONSECUTIVE_STEPS

    optional: dict = {"max_frames": DEFAULT_MAX_FRAMES, "settle_consecutive_steps": SETTLE_CONSECUTIVE_STEPS}
    for key in ("max_settle_s", "settle_consecutive_steps", "max_frames", "interruption_frame"):
        if getattr(parsed, key) is not None:
            optional[key] = getattr(parsed, key)
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
    try:
        result = write_head_search_scenarios(
            scene_path=parsed.scene,
            geometry_seal_path=parsed.geometry_seal,
            production_search_config_path=parsed.production_search_config,
            controller_config_path=parsed.controller_config,
            frozen_candidate_path=parsed.frozen_candidate,
            weights_path=parsed.weights,
            dataset_config_path=parsed.dataset_config,
            scenario_partitions_path=parsed.scenario_partitions,
            output_dir=parsed.output_dir,
            evidence_root=parsed.evidence_root,
            final_run=parsed.final_run,
            seeds=parsed.seed,
            device=parsed.device,
            generator_commit=parsed.generator_commit,
            expected_runtime=expected or None,
            expected_package_prefix=parsed.expected_package_prefix,
            command=_command_line(arguments, subcommand="measure-scenarios"),
            **optional,
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    receipt = result["receipt"]
    for record in receipt["records"]:
        if record["outcome"] == "PASSED":
            continue
        print(
            f"{record['outcome_code']}: the scenario {record['seed']} "
            f"({record['condition_class']}, anchor {record['anchor']}) {record['outcome'].lower()} "
            f"({record.get('outcome_detail')})",
            file=sys.stderr,
        )
    print(
        f"HEAD_SEARCH_SCENARIOS_MEASURED scenarios={receipt['scenario_count']} "
        f"passed={receipt['passed_count']} failed={receipt['failed_count']} "
        f"refused={receipt['refused_count']} "
        f"anchors={json.dumps(receipt['anchor_split'], sort_keys=True)} "
        f"zero_wrong_locks={receipt['zero_wrong_locks']} "
        f"cadence_all_continuous={receipt['cadence_all_continuous']} "
        f"stop_proofs_all_proven={receipt['stop_proofs_all_proven']} "
        f"output_dir={result['output_dir']}"
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
    from so101_demo.act.head_search_camera_measurement.declarations import DEFAULT_FRAMES_PER_POSE
    from so101_demo.act.head_search_camera_measurement.writer import (
        write_head_search_camera_measurement,
    )
    from so101_demo.act.head_search_timing_measurement.contracts import SETTLE_CONSECUTIVE_STEPS

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
