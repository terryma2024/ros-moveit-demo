"""The controller stop, feedback, frame contract, skew and search timing measurement subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from so101_demo.cli.head_search.common import (
    _command_line,
    _refuse_measurement_inputs,
    _transport_runtime_identity,
    _validate_flight,
)
from so101_demo.cli.head_search.flags import (
    FEEDBACK_OPTIONAL_FILE_FLAGS,
    FEEDBACK_REQUIRED_FLAGS,
    FRAME_CONTRACT_FLAGS,
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
    SKEW_FLAGS,
    STOP_CONFIG_REQUIRED_FLAGS,
    STOP_FLIGHT_REQUIRED_FLAGS,
    TIMING_OPTIONAL_FILE_FLAGS,
    TIMING_REQUIRED_FLAGS,
)


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

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.stop_measurement.writers import write_controller_stop_config

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

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.stop_measurement.writers import write_feedback_measurements

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

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.stop_measurement.contracts import DEFAULT_SAMPLES_PER_POSE
    from so101_demo.act.head_search.stop_measurement.writers import write_stationary_measurements
    from so101_demo.act.head_search.timing_measurement.contracts import SETTLE_CONSECUTIVE_STEPS

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

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.stop_measurement.writers import write_controller_submissions
    from so101_demo.act.head_search.timing_measurement.contracts import SETTLE_CONSECUTIVE_STEPS

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

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.stop_measurement.contracts import DEFAULT_STOP_BUDGET_S
    from so101_demo.act.head_search.stop_measurement.writers import write_stop_proofs
    from so101_demo.act.head_search.timing_measurement.contracts import SETTLE_CONSECUTIVE_STEPS

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

    from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search.timing_measurement.contracts import (
        DEFAULT_MAX_SETTLE_S,
        SETTLE_CONSECUTIVE_STEPS,
    )
    from so101_demo.act.head_search.timing_measurement.writer import (
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


def _frame_contract_parser() -> argparse.ArgumentParser:
    """The `measure-frame-contract` entry: the production artefact that declares the head camera rate."""

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-frame-contract",
        description=(
            "Declare the 10 Hz head-search frame contract phase 7 expresses every cap in, citing the "
            "production camera plugin configuration that declares the head camera stream and its rate, "
            "into a brand-new output directory"
        ),
    )
    parser.add_argument("--plugin-config", type=Path, help="the production MuJoCo plugin configuration")
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the document owns")
    parser.add_argument(
        "--skew-measurements",
        type=Path,
        default=None,
        help=(
            "a measured skew document whose capture achieved rate is recorded beside the declaration; "
            "the declared rate stays the value and the document says so"
        ),
    )
    return parser


def _measure_frame_contract(arguments: list[str]) -> int:
    """Validate the declared production artefact, then hand the declaration to the library."""

    parsed = _frame_contract_parser().parse_args(arguments)
    missing, absent = _validate_flight(parsed, FRAME_CONTRACT_FLAGS)
    if parsed.skew_measurements is not None and not parsed.skew_measurements.is_file():
        absent.append(str(parsed.skew_measurements))
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
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
    from so101_demo.act.head_search.transport_measurement import write_transport_measurements

    try:
        result = write_transport_measurements(
            mode="frame_contract",
            plugin_config_path=parsed.plugin_config,
            output_dir=parsed.output_dir,
            measured_rate_from=parsed.skew_measurements,
            command=_command_line(arguments, subcommand="measure-frame-contract"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    document, receipt = result["measurement"], result["receipt"]
    print(
        f"FRAME_CONTRACT_DECLARED {document['frame_rate_hz']} Hz "
        f"declared_by={document['declared_by']['source']} "
        f"sha256={document['declared_by']['sha256']} "
        f"measured={document['measured_frame_rate_hz']} value_source={document['value_source']} "
        f"output_dir={parsed.output_dir}"
    )
    return 0 if receipt["status"] == "DECLARED" else 2


def _skew_parser() -> argparse.ArgumentParser:
    """The `measure-skew` entry: the running MuJoCo head-camera transport, sampled for its stamps.

    This flight starts the production MuJoCo simulation with the production camera plugin, the robot state
    publisher and the joint-state broadcaster, subscribes to the image, CameraInfo and joint-state topics
    exactly as `RosSearchAdapter` does, and records the paired stamps. It loads no detector and uses no
    GPU, and it leaves no node behind.
    """

    parser = argparse.ArgumentParser(
        prog="so101_head_search_calibration measure-skew",
        description=(
            "Measure the image/CameraInfo/joint skew of the running head-camera transport, with the clock "
            "resolution the capture itself observed, into a brand-new output directory"
        ),
    )
    parser.add_argument("--scene", type=Path, help="the sealed MuJoCo scene the stack is started with")
    parser.add_argument("--geometry-seal", type=Path, help="the sealed head camera geometry")
    parser.add_argument("--plugin-config", type=Path, help="the production MuJoCo plugin configuration")
    parser.add_argument(
        "--controller-config", type=Path, help="the production ros2_controllers.yaml the stack loads"
    )
    parser.add_argument("--urdf", type=Path, help="the ACT URDF template the stack's robot is built from")
    parser.add_argument(
        "--frame-contract", type=Path, help="the declaration the capture is paced against"
    )
    parser.add_argument("--output-dir", type=Path, help="the brand-new directory the document owns")
    parser.add_argument("--frames", type=int, default=300, help="the frames to pair (default 300)")
    parser.add_argument(
        "--timeout-s", type=float, default=180.0, help="the whole capture's budget (default 180 s)"
    )
    parser.add_argument(
        "--startup-timeout-s",
        type=float,
        default=90.0,
        help="the stack's readiness budget (default 90 s)",
    )
    parser.add_argument(
        "--pair-window-s",
        type=float,
        default=0.15,
        help="the causal pairing window of CameraInfo and joint state (default 0.15 s)",
    )
    return parser


def _measure_skew(arguments: list[str]) -> int:
    """Validate the declared stack inputs, start the running transport, and hand the flight to the library."""

    parsed = _skew_parser().parse_args(arguments)
    missing, absent = _validate_flight(parsed, SKEW_FLAGS)
    if missing:
        print(
            f"{HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE}: a measurement declares {' '.join(missing)}",
            file=sys.stderr,
        )
        return 2
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
    from so101_demo.act.head_search.transport_measurement import (
        MujocoRosTransport,
        RosTopicSkewCapture,
        leave_nothing_running,
        write_transport_measurements,
    )

    transport = MujocoRosTransport(
        urdf_path=parsed.urdf,
        scene_path=parsed.scene,
        plugin_config_path=parsed.plugin_config,
        controller_config_path=parsed.controller_config,
        workspace=parsed.output_dir / "transport",
        startup_timeout_s=parsed.startup_timeout_s,
        logger=lambda message: print(f"transport: {message}", file=sys.stderr),
    )
    capture = RosTopicSkewCapture(
        frames=parsed.frames,
        timeout_s=parsed.timeout_s,
        pair_window_s=parsed.pair_window_s,
        startup_timeout_s=parsed.startup_timeout_s,
    )
    transport.capture = capture.capture
    transport.frames = parsed.frames
    try:
        result = write_transport_measurements(
            mode="skew",
            plugin_config_path=parsed.plugin_config,
            scene_path=parsed.scene,
            controller_config_path=parsed.controller_config,
            frame_contract_path=parsed.frame_contract,
            transport=transport,
            frames=parsed.frames,
            timeout_s=parsed.timeout_s,
            pair_window_s=parsed.pair_window_s,
            output_dir=parsed.output_dir,
            runtime_identity=_transport_runtime_identity(parsed),
            command=_command_line(arguments, subcommand="measure-skew"),
        )
    except CalibrationInputsRefused as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        leftovers = leave_nothing_running()
        if leftovers:
            print(
                "TRANSPORT_LEFT_RUNNING: " + "; ".join(leftovers), file=sys.stderr
            )
    document = result["measurement"]
    print(
        f"SKEW_MEASURED samples={len(document['samples'])} "
        f"max_skew_s={document['observed']['max_skew_s']} "
        f"clock_resolution_s={document['clock_resolution_s']} "
        f"achieved_rate_hz={document['capture'].get('achieved_rate_hz')} "
        f"inside_cap={document['observed']['inside_cap']} "
        f"output_dir={parsed.output_dir}"
    )
    return 0
