"""The phases' stop, feedback, submission and stop-proof measurements: declared or measured, never invented.

Phase 7 consumes five measurement documents this module produces. Two of them are **declarations** the
running controller already carries and this module only reads:

* ``controller_stop_config`` cites the Head neck's own stopped-velocity tolerance - the constant the stop
  window applies to every ``controller_state`` sample, read out of the *installed* ``head_neck_limits``
  module (the one Python home of the stop-window constants) and cross-checked against the same declaration
  in the source tree and against the sealed controller period. Nothing here measures it; the document says ``measured_here: false`` and carries the declaring
  path, digest and source line. A system whose limits module declares no such constant is refused
  (``CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED``); a source tree and an installed limits module that disagree, or a
  window whose step is not the controller's own period, are refused as contradictory.
* ``feedback_measurements`` carries the declared feedback period - the rate `/joint_states` arrives at, which
  is the feedback the stop path's own criterion consumes - and the feedback path's quantisation resolution.
  The period is a declaration read from the sealed controller configuration (both declared rates are
  recorded, and the one the stop path uses is the broadcaster's). The quantisation is **not** declared
  anywhere in this repository: the producer accepts an explicit ``quantisation`` declaration, derives the
  resolution from a declared encoder count and joint travel, and otherwise writes ``null`` with the refusal
  ``CAL_FEEDBACK_QUANTISATION_UNDECLARED`` rather than inventing, defaulting or substituting a number that
  measures something else.

The other three are **measurements** taken in the sealed MuJoCo scene, in simulation time, with no ROS node,
no detector, no CUDA and no hardware:

* ``stationary_measurements`` holds each declared settled pose and samples the monitored joints' velocities
  at the declared feedback period, which is the stationary velocity noise phase 7 turns into
  ``stop_velocity_rad_s``. A pose the declared settle rule never reaches refuses the measurement.
* ``controller_submissions`` submits the targets the *installed* production controller selected (its own
  bounded plan's stops and the anchor's declared search start) through an admission port that writes the
  command interface once per sealed control cycle, exactly as the controller's ``update()`` does, and records
  the simulation instant of the submission snapshot and of the first physics step that consumed the admitted
  target. Every lead is proved to be the simulation clock's: on the sealed timestep grid, inside one control
  period plus one timestep, and equal to the instant the plant itself reported. Nothing is wall-clock, so
  ``CAL_SUBMIT_LEAD_UNVERIFIED`` cannot fire on these records.
* ``stop_proofs`` revokes the neck at declared offsets of a real motion and then decides every feedback
  sample with the **installed** stop criterion - ``RosControllerPort.stopped()``, fed the same
  ``sensor_msgs/JointState`` messages rclpy would deliver - counting the receipts until three *consecutive*
  samples qualify. The interval from the request to the third confirming receipt is the latency phase 7
  bounds, every sample of every window is recorded so one slow sample can be checked, and a window without
  three consecutive qualifying receipts is refused rather than trimmed.

The plant is paced to the monotonic clock (``realtime``, the production loop's own behaviour), so the
monotonic stop latency is a real-time quantity and not an artefact of a fast in-process loop; the achieved
real-time factor and the largest pacing lag are recorded beside it. What this flight cannot measure is a DDS
transport: the submission port is in process, the goal is not encoded into a ROS action message, and the
documents say so (``transport_measured: false``) instead of implying a flight over the wire.

Nothing here starts a ROS node, addresses hardware or renders a frame; the MuJoCo plant is the only heavy
import and it is made inside the call.
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_camera_measurement.frames import (
    _anchor_pose_requests,
    _corridor_check,
)
from so101_demo.act.head_search_deadband_measurement.lock_trial import motion_corridor_rad
from so101_demo.act.head_search_deadband_measurement.plant import (
    _plant_request,
    MujocoClosedLoopPlant,
)
from so101_demo.act.head_search_timing_measurement.contracts import (
    _digest,
    _finite,
    _number,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    DEFAULT_MAX_SETTLE_S,
    DIGEST_CONVENTION,
    SETTLE_CONSECUTIVE_STEPS,
    SIMULATION_TIME_BASE,
)
from so101_demo.act.head_search_timing_measurement.control import (
    planned_stops,
    read_control_period,
    SettleTracker,
)
from so101_demo.act.head_search_timing_params import P99_9, p99_9
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1

STOP_CONFIG_KIND = "head_search_calibration_controller_stop_config"
STOP_CONFIG_PHASE = "controller_stop_config"
STOP_CONFIG_ARTIFACT = "controller-stop-config.json"

FEEDBACK_KIND = "head_search_calibration_feedback_measurements"
FEEDBACK_PHASE = "feedback_measurements"
FEEDBACK_ARTIFACT = "feedback-measurements.json"

STATIONARY_KIND = "head_search_calibration_stationary_measurements"
STATIONARY_PHASE = "stationary_measurements"
STATIONARY_ARTIFACT = "stationary-measurements.json"

SUBMISSIONS_KIND = "head_search_calibration_controller_submissions"
SUBMISSIONS_PHASE = "controller_submissions"
SUBMISSIONS_ARTIFACT = "controller-submissions.json"

STOP_PROOFS_KIND = "head_search_calibration_stop_proofs"
STOP_PROOFS_PHASE = "stop_proofs"
STOP_PROOFS_ARTIFACT = "stop-proofs.json"

RECEIPT_KIND = "head_search_calibration_stop_measurement_receipt"
RECEIPT_ARTIFACT = "measurement-receipt.json"

#: the refusals this module owns; everything else it raises is the timing module's, because the settle
#: rule, the time-base proof and the sealed-input refusals are that module's and are reused here
CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED = "CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED"
CAL_CONTROLLER_STOP_TOLERANCE_CONTRADICTORY = "CAL_CONTROLLER_STOP_TOLERANCE_CONTRADICTORY"
CAL_FEEDBACK_PERIOD_UNDECLARED = "CAL_FEEDBACK_PERIOD_UNDECLARED"
CAL_FEEDBACK_QUANTISATION_UNDECLARED = "CAL_FEEDBACK_QUANTISATION_UNDECLARED"
CAL_STATIONARY_UNSETTLED = "CAL_STATIONARY_UNSETTLED"
CAL_STOP_PROOF_UNCONFIRMED = "CAL_STOP_PROOF_UNCONFIRMED"
REFUSAL_CODES = (
    CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
    CAL_CONTROLLER_STOP_TOLERANCE_CONTRADICTORY,
    CAL_FEEDBACK_PERIOD_UNDECLARED,
    CAL_FEEDBACK_QUANTISATION_UNDECLARED,
    CAL_STATIONARY_UNSETTLED,
    CAL_STOP_PROOF_UNCONFIRMED,
)

#: the joints every stop-path sample covers: the six arm joints and the neck, which is the scope the Task-8
#: measurement protocol fixes for `stop_velocity_rad_s` and the scope the cadence-correct history verifier
#: requires (`robot_dof_indices` of length seven)
MONITORED_JOINTS = ("1", "2", "3", "4", "5", "6", "neck_yaw_joint")
JOINT_SCOPE_RULE = (
    "every stationary, submission and stop-proof sample carries the velocity of all six arm joints and the "
    "neck, in this order: the Task-8 measurement protocol computes max(abs(v)) over the six arm joints and "
    "the neck, and the production cadence-correct history verifier requires exactly seven robot dof indices"
)

#: the controller's own stop declaration, as the installed limits module spells the constants
STOP_TOLERANCE_CONSTANT = "STOP_WINDOW_MAX_VELOCITY_RAD_S"
WINDOW_SAMPLES_CONSTANT = "STOP_WINDOW_SAMPLES"
WINDOW_STEP_CONSTANT = "STOP_WINDOW_STEP_NS"
WINDOW_MAX_AGE_CONSTANT = "STOP_WINDOW_MAX_AGE_NS"
DECLARED_CONSTANTS = (
    WINDOW_SAMPLES_CONSTANT,
    WINDOW_STEP_CONSTANT,
    WINDOW_MAX_AGE_CONSTANT,
    STOP_TOLERANCE_CONSTANT,
)
STOP_DECLARATION_RULE = (
    "the Head neck's own stopped-velocity tolerance, read from the installed "
    "`head_neck_limits.STOP_WINDOW_MAX_VELOCITY_RAD_S` constant: a `controller_state` sample whose measured or "
    "reference velocity exceeds it is not a stopped sample, and the stop proof requires a whole window of "
    "them. It is a declaration of the running controller, so the document records `measured_here: false` and "
    "cites the installed limits module's path, digest and source line, plus the identical source declaration"
)
_CONSTANT = re.compile(
    r"^(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*"
    r"(?P<value>[0-9][0-9_]*(?:\.[0-9_]*)?(?:[eE][-+]?[0-9]+)?)\s*(?:#.*)?$"
)

#: the declared feedback period is the rate the stop path's own criterion consumes receipts at
FEEDBACK_PERIOD_RULE = (
    "the feedback period is the rate `/joint_states` arrives at, declared by "
    "`joint_state_broadcaster.ros__parameters.update_rate`: that is the feedback the stop path's own "
    "criterion (`RosControllerPort.stopped()`) evaluates, and the period over which a quantised position "
    "difference is observed as a velocity. The controller manager's own update rate is recorded beside it, "
    "because the controller's stop window steps at that rate"
)
QUANTISATION_RULE = (
    "the feedback path's position resolution in radians, expressed as a velocity over one feedback period. It "
    "is a declaration of the plant or the encoder, never a measurement of the simulation: from a declared "
    "`counts_per_revolution` and `joint_travel_rad` it is `joint_travel_rad / counts_per_revolution`, and a "
    "declaration may carry `quantisation_rad` directly. On this platform the MuJoCo feedback path exposes "
    "joint velocities with no encoder quantisation, so the retained declaration "
    "`config/act/feedback-quantisation-declaration.json` states an explicit zero together with its basis; "
    "a declaration that states no resolution at all still leaves the field `null` with its refusal, because a "
    "missing resolution alone never justifies a zero"
)

#: the statement an explicitly zero resolution has to carry: a bare zero would be the invented value the
#: amendment refuses, so this platform records the zero as a declaration together with its basis
QUANTISATION_BASIS_KEY = "basis"
ZERO_BASIS_REQUIRED = (
    "an explicitly zero quantisation_rad is a declaration, not a default: the document has to state the "
    "basis of the zero - the feedback path that exposes velocities without quantisation - because a missing "
    "resolution alone never justifies one"
)
QUANTISATION_SEARCH = {
    "searched": [
        "the installed share tree's config and asset trees (URDF, MJCF, controller and plugin configuration)",
        "the sealed head camera geometry and calibration contract",
        "the installed Head neck limits module (it declares the stop window's velocity tolerance only)",
    ],
    "keys": ["quantisation_rad", "encoder_resolution", "counts_per_revolution", "resolution_rad"],
    "result": (
        "no retained artefact declares a joint or encoder resolution; the geometry and calibration contracts "
        "declare pixel counts and angles, the URDF and MJCF declare joint limits, and the controller's "
        "declaration is a velocity tolerance. This platform's MuJoCo feedback exposes joint velocities, so "
        "the resolution is declared as an explicit zero by "
        "`config/act/feedback-quantisation-declaration.json` and never derived from a count"
    ),
}

#: what a submission is, and what the port in front of the plant does with it
LEAD_DEFINITION = (
    "`first_target_sim_s - submit_snapshot_sim_s`: the simulation instant at which the target was snapshotted "
    "for submission, and the simulation instant right after the first physics step that ran with the admitted "
    "target as the actuator command. The target of every submission is one the installed production "
    "controller selected - its bounded plan's stops and the anchor's declared search start - and the port "
    "writes the command interface once per sealed control cycle, which is where the controller's `update()` "
    "writes it too"
)
ADMISSION_RULE = (
    "the submission port holds the goal in a mailbox and drains it at the next control-cycle boundary, so a "
    "target can never reach the plant sooner than one timestep after its snapshot. The bound proved on every "
    "record is one control period plus one timestep: no submission of this flight can take longer than the "
    "cycle it waits for plus the step that consumes it"
)
TRANSPORT_RULE = (
    "the submission port is in process: it carries the installed controller's target into the sealed scene "
    "without a DDS action and without encoding a `FollowJointTrajectory` goal, because the sealed production "
    "configuration declares no goal duration for the neck trajectory. The measured lead is therefore the "
    "admission quantisation of the sealed controller period, and a wall-clock transport latency is not "
    "measured by this flight"
)

#: what counts as a qualifying feedback sample, straight from the installed stop criterion
QUALIFICATION_RULE = (
    "a feedback receipt qualifies when the installed stop criterion `RosControllerPort.stopped()` is True on "
    "it: the receipt is fresh (`0 <= now - received <= max_age_s`) and every monitored joint's measured "
    "velocity is within the production configuration's declared `stop_velocity_rad_s`. The proof is complete "
    "at the **third consecutive** qualifying receipt, exactly as the Task-8 measurement protocol fixes it, "
    "and every sample of the window is recorded whether it qualified or not"
)
CONSECUTIVE_RULE = (
    "the three confirming receipts are consecutive feedback periods of the same window: no qualifying receipt "
    "is skipped, and a lane of two quiet samples between two loud ones is not a proof"
)
STATIONARY_RULE = (
    "each declared pose is commanded through the admission port and the declared settle rule has to hold "
    "before a single sample is taken; the pose is then held (no re-command between samples) and the monitored "
    "joints' velocities are sampled once per declared feedback period. Sampling a pose the rule never settled "
    "is refused (`CAL_STATIONARY_UNSETTLED`), and so is an unsettled pose that is still moving"
)
SINGLE_EXCEEDANCE_RULE = (
    "every stop proof records its whole window, so one latency beyond the bound phase 7 computes fails the "
    "run: the phase checks every measured sample against `nearest_rank_p99_9 + one feedback period` and never "
    "raises the threshold to accommodate a slow one"
)

MEASUREMENT_ATTEMPT_ID = "head-search-stop-measurement"
MEASUREMENT_SESSION_ID = "head-search-stop-measurement"

DEFAULT_SAMPLES_PER_POSE = 200
DEFAULT_REVOKE_OFFSETS_S = (0.01, 0.03, 0.06, 0.10, 0.15, 0.50)
DEFAULT_STOP_BUDGET_S = 1.0
DEFAULT_REALTIME = True
_GRID_TOLERANCE_S = 1e-9
#: how far a proof window's realised real-time factor may sit from one and still be a real-time
#: measurement: the monotonic interval only bounds the stop path when the plant kept the clock
PACING_TOLERANCE = 0.1
PACING_FAITHFUL_RULE = (
    "the window's realised real-time factor `sim_latency_s / latency_s`: the plant is paced to the "
    "monotonic clock, so a window that advanced its simulation clock at the monotonic clock's rate "
    "is a real-time stop proof, and one that caught up after falling behind is recorded with its own "
    "factor rather than presented as if the two clocks agreed"
)


class CalibrationStopMeasurementRefused(CalibrationInputsRefused):
    """A refusal of these measurements, carrying the exact code the run records and stops on."""


def _refuse(code: str, detail: str) -> CalibrationStopMeasurementRefused:
    return CalibrationStopMeasurementRefused(code, detail)


def _positive_number(name: str, value, *, allow_zero: bool = False) -> float:
    if not _finite(value):
        raise ValueError(f"{name} is not a finite number")
    number = float(value)
    if number < 0.0 or (number == 0.0 and not allow_zero):
        raise ValueError(f"{name} is not positive")
    return number


def _nonnegative_number(name: str, value) -> float:
    """A declared number that may be an explicit zero, but never negative or non-finite."""

    return _positive_number(name, value, allow_zero=True)


def _positive_int(name: str, value, *, minimum: int = 1) -> int:
    if type(value) is not int or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} is not a whole number of at least {minimum}")
    return value


def _mapping(name: str, value) -> Mapping:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} is not a document")
    return value


# --- the controller's declared stopped tolerance ------------------------------------------------------


def read_controller_stop_declaration(path) -> dict:
    """The constants the Head neck's stop window declares, read out of the installed limits module.

    The module is parsed rather than imported: every declared constant of the stop window has to be present
    with a literal value. A module that declares none of them, or only some of them,
    is refused as undeclared - a missing tolerance is not a zero tolerance.
    """

    header = Path(path)
    if not header.is_file():
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
            f"the controller's stop declaration {header} does not exist, so no stopped tolerance is declared",
        )
    text = header.read_text(encoding="utf-8")
    constants: dict[str, float] = {}
    source_lines: dict[str, str] = {}
    for line in text.splitlines():
        match = _CONSTANT.match(line.strip())
        if match is None:
            continue
        constants[match.group("name")] = float(match.group("value").replace("_", ""))
        source_lines[match.group("name")] = line.strip()
    missing = [name for name in DECLARED_CONSTANTS if name not in constants]
    if missing:
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
            f"the controller's stop declaration {header} declares no {missing}: a controller whose stop "
            f"window declares no stopped tolerance has no tolerance to cite, and a default would be an "
            f"invented number",
        )
    tolerance = constants[STOP_TOLERANCE_CONSTANT]
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
            f"the controller's stop declaration {header} declares a non-positive "
            f"{STOP_TOLERANCE_CONSTANT} of {tolerance!r}",
        )
    samples = constants[WINDOW_SAMPLES_CONSTANT]
    if samples < 3:
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
            f"the controller's stop declaration {header} requires only {samples} samples, which cannot even "
            f"carry the three consecutive samples the stop protocol fixes",
        )
    return {
        "path": str(header),
        "sha256": _digest(header),
        "constants": dict(sorted(constants.items())),
        "source_lines": source_lines,
        "stopped_tolerance_rad_s": tolerance,
        "window_samples": int(samples),
        "window_step_s": constants[WINDOW_STEP_CONSTANT] / 1e9,
        "window_max_age_s": constants[WINDOW_MAX_AGE_CONSTANT] / 1e9,
    }


def declared_controller_stop_tolerance(
    *, installed_declaration, source_declaration, controller_config_path
) -> dict:
    """The tolerance the running controller was built with, or a refusal that says why it cannot be cited.

    The installed header is the artefact that declares it; the source declaration has to be the same bytes,
    because otherwise the running controller and the tree it was built from disagree about when a sample is
    stopped. The window's own step has to be the sealed controller's period, because a window that steps at
    another rate is a declaration of another controller.
    """

    installed = read_controller_stop_declaration(installed_declaration)
    source = read_controller_stop_declaration(source_declaration)
    if installed["sha256"] != source["sha256"]:
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_CONTRADICTORY,
            f"the installed controller declaration {installed['path']} digests to {installed['sha256']} but "
            f"the source declaration {source['path']} digests to {source['sha256']}: the running controller "
            f"and its source disagree, so neither tolerance can be cited as the running one",
        )
    period = read_control_period(controller_config_path)
    step = installed["window_step_s"]
    if not math.isclose(step, period, rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_CONTROLLER_STOP_TOLERANCE_CONTRADICTORY,
            f"the controller's stop window steps every {step} s but the sealed controller configuration "
            f"declares a period of {period} s: the declaration describes another controller",
        )
    return {
        "stopped_tolerance_rad_s": installed["stopped_tolerance_rad_s"],
        "unit": "rad/s",
        "measured_here": False,
        "declared_by": {
            "path": installed["path"],
            "sha256": installed["sha256"],
            "constant": STOP_TOLERANCE_CONSTANT,
            "source_line": installed["source_lines"][STOP_TOLERANCE_CONSTANT],
            "constant_path": f"head_neck_limits.{STOP_TOLERANCE_CONSTANT}",
        },
        "window_samples": installed["window_samples"],
        "window_step_s": step,
        "window_max_age_s": installed["window_max_age_s"],
        "controller_cycle_period_s": period,
        "source_declaration": {"path": source["path"], "sha256": source["sha256"]},
        "cross_checks": {
            "installed_equals_source": True,
            "window_step_matches_controller_period": True,
            "window_span_s": installed["window_samples"] * step,
        },
    }


# --- the declared feedback period and the declared quantisation ---------------------------------------


def read_feedback_declarations(controller_config_path) -> dict:
    """The two declared rates: the feedback period the stop path consumes, and the controller's own cycle."""

    import yaml

    path = Path(controller_config_path)
    if not path.is_file():
        raise _refuse(
            CAL_FEEDBACK_PERIOD_UNDECLARED, f"the controller configuration {path} does not exist"
        )
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        manager = document["controller_manager"]["ros__parameters"]["update_rate"]
        broadcaster = document["joint_state_broadcaster"]["ros__parameters"]["update_rate"]
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as error:
        raise _refuse(
            CAL_FEEDBACK_PERIOD_UNDECLARED,
            f"the controller configuration {path} declares no controller_manager and "
            f"joint_state_broadcaster update_rate pair: {error}",
        ) from error
    for name, rate in (("controller_manager", manager), ("joint_state_broadcaster", broadcaster)):
        if not _finite(rate) or float(rate) <= 0.0:
            raise _refuse(
                CAL_FEEDBACK_PERIOD_UNDECLARED,
                f"the controller configuration {path} declares the non-positive {name} update_rate {rate!r}",
            )
    return {
        "path": str(path),
        "sha256": _digest(path),
        "period_s": 1.0 / float(broadcaster),
        "feedback_rate_hz": float(broadcaster),
        "controller_cycle_period_s": 1.0 / float(manager),
        "controller_cycle_rate_hz": float(manager),
        "declared_by": {
            "period_s": {
                "keys": {"joint_state_broadcaster": "ros__parameters.update_rate"},
                "rule": FEEDBACK_PERIOD_RULE,
            },
            "controller_cycle_period_s": {
                "keys": {"controller_manager": "ros__parameters.update_rate"},
                "rule": (
                    "the controller manager's own update rate: the rate the controller's stop window steps "
                    "at, recorded beside the feedback period because both are declared"
                ),
            },
        },
    }


def undeclared_quantisation(detail: str | None = None) -> dict:
    """The quantisation block when no artefact declares one: `null`, with the refusal that says so."""

    return {
        "declared": False,
        "measured_here": False,
        "quantisation_rad": None,
        "path": None,
        "sha256": None,
        "declared_by": None,
        "rule": QUANTISATION_RULE,
        "declaration_search": dict(QUANTISATION_SEARCH),
        "detail": detail
        or (
            "no retained artefact declares a joint or encoder resolution: the field is written `null` with "
            "the refusal CAL_FEEDBACK_QUANTISATION_UNDECLARED instead of being defaulted, and phase 7 refuses "
            "any document whose quantisation_rad is missing or not a finite non-negative number"
        ),
    }


def declared_quantisation(path) -> dict:
    """The quantisation a caller's declaration states, or the refusal block when there is no declaration.

    A declaration carries either `quantisation_rad` itself, or the two declarations the resolution is derived
    from: `counts_per_revolution` and `joint_travel_rad`. Anything else is a caller error (a plain
    `ValueError`), because a document that names neither is not a declaration of a resolution.

    An explicitly **zero** `quantisation_rad` is a valid declaration on this platform - the MuJoCo feedback
    path exposes joint velocities with no encoder quantisation, so the second term of the stop envelope is
    identically zero - but only when the document also states the basis of the zero. A bare zero, and a
    document that declares no resolution at all, are refused: the zero is declared here, never defaulted for
    a missing value.
    """

    if path is None:
        return undeclared_quantisation()
    declaration_path = Path(path)
    if not declaration_path.is_file():
        return undeclared_quantisation(
            f"the declared quantisation artefact {declaration_path} does not exist, so no resolution is "
            f"declared and none is invented"
        )
    document = json.loads(declaration_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"the quantisation declaration {declaration_path} is not a document")
    digest = _digest(declaration_path)
    basis = None
    if "quantisation_rad" in document:
        value = _nonnegative_number("the declared quantisation_rad", document["quantisation_rad"])
        keys = {"quantisation_rad": "quantisation_rad"}
        derivation = "declared directly"
        if value == 0.0:
            basis = document.get(QUANTISATION_BASIS_KEY)
            if type(basis) is not str or not basis.strip():
                raise ValueError(
                    f"the quantisation declaration {declaration_path} declares quantisation_rad = 0.0 "
                    f"without a {QUANTISATION_BASIS_KEY}: {ZERO_BASIS_REQUIRED}"
                )
            basis = basis.strip()
            derivation = "declared directly as an explicit zero, with its basis"
    elif "counts_per_revolution" in document and "joint_travel_rad" in document:
        counts = _positive_number(
            "the declared counts_per_revolution", document["counts_per_revolution"]
        )
        travel = _positive_number("the declared joint_travel_rad", document["joint_travel_rad"])
        value = travel / counts
        keys = {
            "counts_per_revolution": "counts_per_revolution",
            "joint_travel_rad": "joint_travel_rad",
        }
        derivation = "joint_travel_rad / counts_per_revolution"
    else:
        raise ValueError(
            f"the quantisation declaration {declaration_path} declares neither quantisation_rad nor the "
            f"counts_per_revolution and joint_travel_rad pair the resolution is derived from"
        )
    declared_by = {
        "path": str(declaration_path),
        "sha256": digest,
        "keys": keys,
        "rule": QUANTISATION_RULE,
        "derivation": derivation,
    }
    block = {
        "declared": True,
        "measured_here": False,
        "quantisation_rad": value,
        "path": str(declaration_path),
        "sha256": digest,
        "declared_by": declared_by,
        "rule": QUANTISATION_RULE,
        "declaration_search": dict(QUANTISATION_SEARCH),
        "detail": (
            "the resolution is a declaration of the plant or the encoder, read from the artefact named here "
            "and not measured by this producer"
        ),
    }
    if basis is not None:
        declared_by[QUANTISATION_BASIS_KEY] = basis
        block[QUANTISATION_BASIS_KEY] = basis
        block["detail"] = (
            "the resolution is declared as an explicit zero, with the basis of the zero recorded here: the "
            "feedback path of this platform exposes velocities without an encoder quantisation"
        )
    return block


# --- the documents ------------------------------------------------------------------------------------


def _document(path, body: Mapping) -> dict:
    """One document, with its own path and the canonical digest of everything but that digest."""

    document = {**body, "path": str(path)}
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def _declaration_runtime() -> dict:
    """What a declaration-only producer ran as: an interpreter and nothing else started."""

    import so101_demo

    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "so101_demo_module_path": str(Path(so101_demo.__file__).resolve()),
        "muJoCo_imported": False,
        "cuda_used": False,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": False,
        "hardware_motion_commanded": False,
    }


def build_controller_stop_config(
    *, path, tolerance: Mapping, controller_config_path, command=None
) -> dict:
    """The controller stop configuration document phase 7 reads its tolerance out of."""

    config_path = Path(controller_config_path)
    period = _positive_number("the controller cycle period", tolerance["controller_cycle_period_s"])
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": STOP_CONFIG_KIND,
        "phase": STOP_CONFIG_PHASE,
        "measured_here": False,
        "stopped_tolerance_rad_s": float(tolerance["stopped_tolerance_rad_s"]),
        "unit": "rad/s",
        "quantity": (
            "the controller's own stopped-velocity tolerance: a feedback sample whose measured or reference "
            "velocity exceeds it is not a stopped sample"
        ),
        "declaration_rule": STOP_DECLARATION_RULE,
        "declared_by": dict(tolerance["declared_by"]),
        "source_declaration": dict(tolerance["source_declaration"]),
        "window": {
            "samples": int(tolerance["window_samples"]),
            "step_s": float(tolerance["window_step_s"]),
            "max_age_s": float(tolerance["window_max_age_s"]),
            "span_s": float(tolerance["window_samples"]) * float(tolerance["window_step_s"]),
            "rule": (
                "the controller's stop proof requires this many consecutive samples of its own window, each "
                "stepped by `step_s` and no older than `max_age_s`"
            ),
        },
        "controller_cycle_period_s": period,
        "controller_cycle_rate_hz": 1.0 / period,
        "controller_config": {"path": str(config_path), "sha256": _digest(config_path)},
        "cross_checks": dict(tolerance["cross_checks"]),
        "production_owner": (
            "so101_demo.act.head_neck_limits.STOP_WINDOW_MAX_VELOCITY_RAD_S "
            "(so101_mujoco_support/HeadNeckTrajectoryController)"
        ),
        "consumed_by": (
            "so101_demo.act.head_search_timing_params.compute_stop_velocity_rad_s(controller=...): the "
            "tolerance is the third term of the conservative envelope"
        ),
        "command": command,
        "refusals": [],
        "runtime": _declaration_runtime(),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": False,
        "hardware_motion_commanded": False,
        "cuda_used": False,
        "digest_convention": DIGEST_CONVENTION,
    }
    return _document(path, body)


def build_feedback_measurements(*, path, declaration: Mapping, quantisation: Mapping, command=None) -> dict:
    """The feedback measurements document phase 7 reads the period and the quantisation out of."""

    period = _positive_number("the declared feedback period", declaration["period_s"])
    cycle = _positive_number(
        "the declared controller cycle period", declaration["controller_cycle_period_s"]
    )
    declared = bool(quantisation["declared"])
    refusals = []
    if not declared:
        refusals.append(
            {
                "field": "quantisation_rad",
                "code": CAL_FEEDBACK_QUANTISATION_UNDECLARED,
                "detail": quantisation["detail"],
                "searched": quantisation["declaration_search"],
            }
        )
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": FEEDBACK_KIND,
        "phase": FEEDBACK_PHASE,
        "measured_here": False,
        "period_s": period,
        "unit": "s",
        "period_rule": FEEDBACK_PERIOD_RULE,
        "feedback_rate_hz": float(declaration["feedback_rate_hz"]),
        "controller_cycle_period_s": cycle,
        "controller_cycle_rate_hz": float(declaration["controller_cycle_rate_hz"]),
        "declared_by": dict(declaration["declared_by"]),
        "controller_config": {"path": declaration["path"], "sha256": declaration["sha256"]},
        "quantisation_rad": quantisation["quantisation_rad"],
        "quantisation_unit": "rad",
        "quantisation": dict(quantisation),
        "consumed_by": (
            "so101_demo.act.head_search_timing_params.compute_stop_velocity_rad_s(feedback=...): "
            "quantisation_rad / period_s is the second term of the envelope, and "
            "compute_stop_latency_s(feedback=...) adds one period to the p99.9 stop latency"
        ),
        "command": command,
        "refusals": refusals,
        "runtime": _declaration_runtime(),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": False,
        "hardware_motion_commanded": False,
        "cuda_used": False,
        "digest_convention": DIGEST_CONVENTION,
    }
    return _document(path, body)


# --- the simulation-time base proof -------------------------------------------------------------------


def verify_submission_time_base(samples, *, simulation_timestep_s, control_period_s) -> dict:
    """Prove every submission's lead is the simulation clock's, or refuse rather than record it.

    Phase 7 refuses a submission record it cannot verify in simulation time. The proof here is stronger than
    a declaration: every stamp has to be a whole number of the sealed timestep, the lead has to be the
    difference the record states, the plant's own consumption stamp has to agree with it, and no lead may
    exceed the admission bound of one control period plus one timestep.
    """

    timestep = _positive_number("the sealed simulation timestep", simulation_timestep_s)
    period = _positive_number("the sealed control period", control_period_s)
    if isinstance(samples, (str, bytes)) or not isinstance(samples, Sequence) or not samples:
        raise _refuse(
            CAL_TIMING_TIME_BASE_UNVERIFIED,
            "the submission measurement records no submission, so no lead can be verified in simulation time",
        )
    bound = period + timestep
    leads: list[float] = []
    previous_snapshot = None
    for index, sample in enumerate(samples):
        record = _mapping("a controller submission", sample)
        if record.get("time_base") != SIMULATION_TIME_BASE:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"submission {index} declares the time base {record.get('time_base')!r} instead of "
                f"{SIMULATION_TIME_BASE!r}: a wall-clock submission is not verified in simulation time",
            )
        snapshot = _number(record, f"submission {index}", "submit_snapshot_sim_s", nonnegative=True)
        first = _number(record, f"submission {index}", "first_target_sim_s", nonnegative=True)
        consumed = _number(record, f"submission {index}", "plant_consumed_sim_s", nonnegative=True)
        lead = _number(record, f"submission {index}", "lead_s", positive=True)
        for name, value in (("submit_snapshot_sim_s", snapshot), ("first_target_sim_s", first)):
            steps = value / timestep
            if not math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=_GRID_TOLERANCE_S):
                raise _refuse(
                    CAL_TIMING_TIME_BASE_UNVERIFIED,
                    f"submission {index} is stamped {value} s, which is not a whole number of the sealed "
                    f"{timestep} s timesteps: the stamp is not the simulation clock's",
                )
        if not math.isclose(first - snapshot, lead, rel_tol=0.0, abs_tol=_GRID_TOLERANCE_S):
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"submission {index} records a lead of {lead} s but its stamps differ by "
                f"{first - snapshot} s",
            )
        if not math.isclose(consumed, first, rel_tol=0.0, abs_tol=_GRID_TOLERANCE_S):
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"submission {index} puts the plant's own consumption at {consumed} s but the record claims "
                f"{first} s, so the lead was not read back out of the stepped plant",
            )
        if lead > bound + _GRID_TOLERANCE_S:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"submission {index} records a lead of {lead} s, beyond the admission bound of one "
                f"{period} s control period plus one {timestep} s timestep ({bound} s): a submission cannot "
                f"wait longer than the cycle it is drained at plus the step that consumes it",
            )
        if previous_snapshot is not None and snapshot <= previous_snapshot:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"submission {index} is snapshotted at {snapshot} s, not after submission {index - 1} at "
                f"{previous_snapshot} s: the submissions are not the simulation clock's own order",
            )
        previous_snapshot = snapshot
        leads.append(lead)
    return {
        "time_base": SIMULATION_TIME_BASE,
        "sample_count": len(leads),
        "submission_count": len(leads),
        "simulation_timestep_s": timestep,
        "control_period_s": period,
        "admission_bound_s": bound,
        "minimum_lead_s": min(leads),
        "maximum_lead_s": max(leads),
        "lead_spread_s": max(leads) - min(leads),
        "all_leads_within_admission_bound": True,
        "plant_consumption_matches": True,
        "stamps_on_timestep_grid": True,
        "submissions_verified_in_simulation_time": True,
    }


# --- the documents the three flights write ------------------------------------------------------------


def build_stationary_measurements(
    *, path, records, samples_per_pose, flight: Mapping, command=None
) -> dict:
    """The stationary measurements document phase 7 reads the velocity noise out of."""

    samples: list[dict] = []
    poses: list[dict] = []
    for record in records:
        for sample in record["samples"]:
            samples.append(
                {
                    **sample,
                    "index": len(samples),
                    "pose_index": record["pose_index"],
                    "anchor": record["anchor"],
                    "pose_rad": record["pose_rad"],
                    "pose_kind": record["pose_kind"],
                }
            )
        magnitudes = [max(abs(value) for value in sample["velocity_rad_s"]) for sample in record["samples"]]
        poses.append(
            {
                "pose_index": record["pose_index"],
                "anchor": record["anchor"],
                "pose_rad": record["pose_rad"],
                "pose_kind": record["pose_kind"],
                "settle": record["settle"],
                "sample_count": len(record["samples"]),
                "p99_9_velocity_rad_s": p99_9(magnitudes),
                "max_velocity_rad_s": max(magnitudes),
            }
        )
    magnitudes = [max(abs(value) for value in sample["velocity_rad_s"]) for sample in samples]
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": STATIONARY_KIND,
        "phase": STATIONARY_PHASE,
        "measured_here": True,
        "time_base": SIMULATION_TIME_BASE,
        "monitored_joints": list(MONITORED_JOINTS),
        "joint_scope_rule": JOINT_SCOPE_RULE,
        "measurement_rule": STATIONARY_RULE,
        "feedback_period_s": float(flight["feedback_period_s"]),
        "controller_cycle_period_s": float(flight["control_period_s"]),
        "simulation_timestep_s": float(flight["simulation_timestep_s"]),
        "samples_per_pose": int(samples_per_pose),
        "pose_count": len(poses),
        "sample_count": len(samples),
        "settle_velocity_rad_s": float(flight["settle_velocity_rad_s"]),
        "goal_tolerance_rad": float(flight["goal_tolerance_rad"]),
        "settle_consecutive_steps": int(flight["settle_consecutive_steps"]),
        "poses": poses,
        "samples": samples,
        "p99_9_velocity_rad_s": p99_9(magnitudes),
        "max_velocity_rad_s": max(magnitudes),
        "percentile": {
            "quantile": P99_9,
            "convention": "nearest_rank_ceil(quantile * n)",
            "sample_count": len(magnitudes),
            "rank": max(1, math.ceil(P99_9 * len(magnitudes))),
        },
        "magnitude_rule": (
            "each sample's magnitude is max(abs(velocity_rad_s)) over the monitored joints, which is the "
            "magnitude the Task-8 stop protocol and phase 7 both take"
        ),
        "real_time_factor": flight["real_time_factor"],
        "pacing": dict(flight["pacing"]),
        "scene_path": flight["scene_path"],
        "scene_sha256": flight["scene_sha256"],
        "geometry_seal": dict(flight["geometry_seal"]),
        "production_search_config": dict(flight["production_search_config"]),
        "controller_config": dict(flight["controller_config"]),
        "runtime_identity": dict(flight["runtime_identity"]),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "cuda_used": False,
        "detector_loaded": False,
        "command": command,
        "refusals": [],
        "digest_convention": DIGEST_CONVENTION,
    }
    return _document(path, body)


def build_controller_submissions(*, path, records, flight: Mapping, command=None) -> dict:
    """The controller submissions document phase 7 reads the goal-admission lead out of."""

    samples = [
        {
            "index": index,
            "purpose": record["purpose"],
            "submitted_by": record["submitted_by"],
            "target_rad": float(record["target_rad"]),
            "reference_before_rad": float(record["reference_before_rad"]),
            "motion_rad": float(record["target_rad"]) - float(record["reference_before_rad"]),
            "submit_snapshot_sim_s": float(record["submit_snapshot_sim_s"]),
            "first_target_sim_s": float(record["first_target_sim_s"]),
            "plant_consumed_sim_s": float(record["plant_consumed_sim_s"]),
            "lead_s": float(record["lead_s"]),
            "time_base": SIMULATION_TIME_BASE,
            "control_cycles": int(record["control_cycles"]),
            "steps": int(record["steps"]),
            "settled": bool(record["settled"]),
            "reached": bool(record["reached"]),
            "final_velocity_rad_s": float(record["final_velocity_rad_s"]),
            "final_position_error_rad": float(record["final_position_error_rad"]),
        }
        for index, record in enumerate(records)
    ]
    proof = verify_submission_time_base(
        samples,
        simulation_timestep_s=flight["simulation_timestep_s"],
        control_period_s=flight["control_period_s"],
    )
    leads = [sample["lead_s"] for sample in samples]
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": SUBMISSIONS_KIND,
        "phase": SUBMISSIONS_PHASE,
        "measured_here": True,
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(flight["simulation_timestep_s"]),
        "control_period_s": float(flight["control_period_s"]),
        "controller_cycle_rate_hz": 1.0 / float(flight["control_period_s"]),
        "monitored_joints": list(MONITORED_JOINTS),
        "lead_definition": LEAD_DEFINITION,
        "admission_rule": ADMISSION_RULE,
        "transport_rule": TRANSPORT_RULE,
        "transport": {
            "in_process": True,
            "dds_transport_measured": False,
            "wire_goal_encoded": False,
            "detail": TRANSPORT_RULE,
        },
        "samples": samples,
        "submission_count": len(samples),
        "minimum_lead_s": min(leads),
        "maximum_lead_s": max(leads),
        "lead_spread_s": max(leads) - min(leads),
        "time_base_proof": proof,
        "real_time_factor": flight["real_time_factor"],
        "pacing": dict(flight["pacing"]),
        "scene_path": flight["scene_path"],
        "scene_sha256": flight["scene_sha256"],
        "geometry_seal": dict(flight["geometry_seal"]),
        "production_search_config": dict(flight["production_search_config"]),
        "controller_config": dict(flight["controller_config"]),
        "runtime_identity": dict(flight["runtime_identity"]),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "cuda_used": False,
        "detector_loaded": False,
        "command": command,
        "refusals": [],
        "digest_convention": DIGEST_CONVENTION,
    }
    return _document(path, body)


def build_stop_proofs(*, path, records, flight: Mapping, command=None) -> dict:
    """The stop/revoke proofs document phase 7 reads the stop latency out of."""

    samples = [
        {
            "index": index,
            "reason": record["reason"],
            "anchor": record["anchor"],
            "pose_rad": float(record["pose_rad"]),
            "pose_kind": record["pose_kind"],
            "revoke_offset_s": float(record["revoke_offset_s"]),
            "motion_target_rad": float(record["motion_target_rad"]),
            "hold_rad": float(record["hold_rad"]),
            "stop_request_monotonic_s": float(record["stop_request_monotonic_s"]),
            "stop_request_sim_s": float(record["stop_request_sim_s"]),
            "third_confirming_receive_monotonic_s": float(
                record["third_confirming_receive_monotonic_s"]
            ),
            "third_confirming_receive_sim_s": float(record["third_confirming_receive_sim_s"]),
            "latency_s": float(record["latency_s"]),
            "sim_latency_s": float(record["sim_latency_s"]),
            "window_real_time_factor": record["window_real_time_factor"],
            "pacing_faithful": bool(record["pacing_faithful"]),
            "confirming_sample_indices": list(record["confirming_sample_indices"]),
            "third_confirming_sample_index": int(record["third_confirming_sample_index"]),
            "sample_count": len(record["feedback_samples"]),
            "feedback_samples": list(record["feedback_samples"]),
            "exceeds_declared_production_latency_s": record[
                "exceeds_declared_production_latency_s"
            ],
        }
        for index, record in enumerate(records)
    ]
    latencies = [sample["latency_s"] for sample in samples]
    exceedances = [
        sample
        for sample in samples
        if sample["exceeds_declared_production_latency_s"] is True
    ]
    body = {
        "schema_version": SCHEMA_VERSION,
        "kind": STOP_PROOFS_KIND,
        "phase": STOP_PROOFS_PHASE,
        "measured_here": True,
        "feedback_period_s": float(flight["feedback_period_s"]),
        "controller_cycle_period_s": float(flight["control_period_s"]),
        "simulation_timestep_s": float(flight["simulation_timestep_s"]),
        "monitored_joints": list(MONITORED_JOINTS),
        "joint_scope_rule": JOINT_SCOPE_RULE,
        "stop_velocity_rad_s": float(flight["stop_velocity_rad_s"]),
        "max_age_s": float(flight["max_age_s"]),
        "qualification_rule": QUALIFICATION_RULE,
        "consecutive_rule": CONSECUTIVE_RULE,
        "qualification_source": (
            "so101_demo.adapters.act.ros_execution.RosControllerPort.stopped(): the installed stop criterion "
            "is called on every receipt this flight delivers, so the qualification is the running system's"
        ),
        "samples": samples,
        "proof_count": len(samples),
        "p99_9_latency_s": p99_9(latencies),
        "slowest_latency_s": max(latencies),
        "percentile": {
            "quantile": P99_9,
            "convention": "nearest_rank_ceil(quantile * n)",
            "sample_count": len(latencies),
            "rank": max(1, math.ceil(P99_9 * len(latencies))),
        },
        "single_exceedance_rule": SINGLE_EXCEEDANCE_RULE,
        "pacing_faithful_rule": PACING_FAITHFUL_RULE,
        "pacing_faithful_tolerance": PACING_TOLERANCE,
        "pacing_faithful_proof_count": sum(1 for sample in samples if sample["pacing_faithful"]),
        "off_schedule_sample_indices": [
            sample["index"] for sample in samples if not sample["pacing_faithful"]
        ],
        "declared_production_latency_s": flight["declared_production_latency_s"],
        "exceedance_count": len(exceedances),
        "exceeding_sample_indices": [sample["index"] for sample in exceedances],
        "stop_budget_s": float(flight["stop_budget_s"]),
        "revoke_offsets_s": [float(value) for value in flight["revoke_offsets_s"]],
        "real_time_factor": flight["real_time_factor"],
        "pacing": dict(flight["pacing"]),
        "scene_path": flight["scene_path"],
        "scene_sha256": flight["scene_sha256"],
        "geometry_seal": dict(flight["geometry_seal"]),
        "production_search_config": dict(flight["production_search_config"]),
        "controller_config": dict(flight["controller_config"]),
        "runtime_identity": dict(flight["runtime_identity"]),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "cuda_used": False,
        "detector_loaded": False,
        "command": command,
        "refusals": [],
        "digest_convention": DIGEST_CONVENTION,
    }
    return _document(path, body)


# --- the installed stop criterion's transport ---------------------------------------------------------


class MeasurementClock:
    """The monotonic clock the flight hands to the installed stop criterion.

    The criterion stamps every receipt with the clock it is given, so the flight gives it a clock it can read
    afterwards: the receipt's own stamp is then the criterion's own reading and not an estimate taken beside
    it, and no private state of the installed port has to be touched.
    """

    def __init__(self, monotonic=time.monotonic) -> None:
        self._monotonic = monotonic
        self.last: float | None = None
        self.reads = 0

    def __call__(self) -> float:
        self.last = float(self._monotonic())
        self.reads += 1
        return self.last


class ControllerFeedbackTransport:
    """The subscription the installed stop criterion registers, with an explicit delivery call.

    `RosControllerPort` registers its feedback callback on the node it is built with. This stand-in keeps that
    callback and delivers `sensor_msgs/JointState` messages to it exactly as rclpy would, so the criterion is
    the installed one and only the transport is the harness's.
    """

    def __init__(self) -> None:
        self.topic: str | None = None
        self.message_type = None
        self.callback = None
        self.delivered = 0

    def create_subscription(self, topic, message_type, callback, qos_profile):
        self.topic = topic
        self.message_type = message_type
        self.callback = callback
        return None

    def deliver(self, message) -> None:
        if self.callback is None:
            raise ValueError("nothing registered a feedback callback on this transport")
        self.callback(message)
        self.delivered += 1


def joint_state_message(*, joint_names, positions, velocities, stamp_s):
    """One `sensor_msgs/JointState` carrying the sampled feedback, as the plant reports it."""

    from sensor_msgs.msg import JointState

    names = [str(name) for name in joint_names]
    message = JointState()
    message.name = names
    message.position = [float(value) for value in positions]
    message.velocity = [float(value) for value in velocities]
    nanoseconds = int(round(float(stamp_s) * 1e9))
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(nanoseconds, 1000000000)
    message.header.frame_id = ""
    return message


def controller_stop_criterion(*, stop_velocity_rad_s, max_age_s, clock=None):
    """The installed stop criterion over the monitored joints, with its transport and clock."""

    from so101_demo.adapters.act.ros_execution import RosControllerPort

    running = MeasurementClock() if clock is None else clock
    transport = ControllerFeedbackTransport()
    port = RosControllerPort(
        transport,
        None,
        MONITORED_JOINTS,
        stop_velocity_rad_s=stop_velocity_rad_s,
        max_age_s=max_age_s,
        monotonic=running,
    )
    return port, transport, running


def confirm_stop(
    *,
    plant,
    port,
    transport,
    clock,
    hold_rad,
    stop_budget_s,
    index,
    reason,
    period_s,
    motion=None,
    revoke_offset_s=None,
    anchor=None,
    pose_rad=None,
    pose_kind=None,
    declared_production_latency_s=None,
) -> dict:
    """Revoke the motion and count the receipts until three consecutive samples qualify.

    This is the stop proof the Task-8 measurement protocol fixes: the request is stamped when the revoke is
    handed to the plant, every feedback period then delivers one receipt to the installed stop criterion, and
    the proof is complete at the third consecutive qualifying receipt. A window that never carries three
    consecutive qualifying receipts inside its declared budget refuses the whole measurement; every receipt's
    own values are kept, so a single slow one can be checked against the bound phase 7 computes later.
    """

    plant.hold_command(float(hold_rad))
    request_monotonic = clock()
    request_sim = float(plant.time_s)
    samples: list[dict] = []
    consecutive = 0
    qualifying_indices: list[int] = []
    confirming: dict | None = None
    cycles_per_sample = max(1, int(round(period_s / float(plant.control_period_s))))
    while float(plant.time_s) - request_sim <= float(stop_budget_s):
        for _ in range(cycles_per_sample):
            plant.step_control_cycle()
        sample = dict(plant.feedback_sample())
        transport.deliver(
            joint_state_message(
                joint_names=MONITORED_JOINTS,
                positions=sample["joint_positions"],
                velocities=sample["joint_velocities"],
                stamp_s=sample["sim_s"],
            )
        )
        received = clock.last
        stopped = bool(port.stopped())
        if stopped:
            consecutive += 1
            qualifying_indices.append(len(samples))
        else:
            consecutive = 0
            qualifying_indices = []
        samples.append(
            {
                "index": len(samples),
                "receive_monotonic_s": received,
                "receive_sim_s": float(sample["sim_s"]),
                "velocity_rad_s": [float(value) for value in sample["velocity_rad_s"]],
                "yaw_rad": float(sample["yaw_rad"]),
                "reference_rad": float(sample["reference_rad"]),
                "position_error_rad": float(sample["position_error_rad"]),
                "qualifying": stopped,
                "consecutive_qualifying": consecutive,
            }
        )
        if consecutive >= 3:
            confirming = samples[-1]
            break
    if confirming is None:
        raise _refuse(
            CAL_STOP_PROOF_UNCONFIRMED,
            f"stop proof {index} ({reason}) found no three consecutive qualifying feedback receipts inside "
            f"its {stop_budget_s} s budget: the widest window recorded was "
            f"{max((sample['consecutive_qualifying'] for sample in samples), default=0)} consecutive "
            f"qualifying samples out of {len(samples)}, and a proof that never confirmed is not written",
        )
    latency = float(confirming["receive_monotonic_s"]) - float(request_monotonic)
    sim_latency = float(confirming["receive_sim_s"]) - request_sim
    factor = None if latency <= 0.0 else sim_latency / latency
    return {
        "index": index,
        "reason": reason,
        "anchor": anchor,
        "pose_rad": pose_rad,
        "pose_kind": pose_kind,
        "revoke_offset_s": revoke_offset_s,
        "motion_target_rad": None if motion is None else float(motion["target_rad"]),
        "hold_rad": float(hold_rad),
        "stop_request_monotonic_s": float(request_monotonic),
        "stop_request_sim_s": request_sim,
        "third_confirming_receive_monotonic_s": float(confirming["receive_monotonic_s"]),
        "third_confirming_receive_sim_s": float(confirming["receive_sim_s"]),
        "latency_s": latency,
        "sim_latency_s": sim_latency,
        "window_real_time_factor": factor,
        "pacing_faithful": factor is not None and abs(factor - 1.0) <= PACING_TOLERANCE,
        "confirming_sample_indices": list(qualifying_indices[-3:]),
        "third_confirming_sample_index": int(confirming["index"]),
        "feedback_samples": samples,
        "exceeds_declared_production_latency_s": (
            None
            if declared_production_latency_s is None
            else latency > float(declared_production_latency_s)
        ),
    }


# --- the flights --------------------------------------------------------------------------------------


def _pose_records(poses) -> list[dict]:
    records = []
    for index, pose in enumerate(poses):
        record = _mapping("a declared pose", pose)
        records.append(
            {
                "pose_index": index,
                "anchor": record.get("anchor"),
                "pose_rad": _number(record, "a declared pose", "pose_rad"),
                "pose_kind": record.get("pose_kind"),
            }
        )
    return records


def _plant_of(request: Mapping, factory):
    """The plant of one flight, built from the declared plant request (or the request itself in a test)."""

    return factory(request.get("plant_request") or request)


def _declared_settle(request: Mapping) -> dict:
    """The declared settle rule of one flight, as the floor plan request carries it."""

    source = request.get("plant_request") if isinstance(request.get("plant_request"), Mapping) else request
    return {
        "settle_velocity_rad_s": source.get("settle_velocity_rad_s"),
        "goal_tolerance_rad": source.get("goal_tolerance_rad"),
        "settle_consecutive_steps": source.get("settle_consecutive_steps", SETTLE_CONSECUTIVE_STEPS),
    }


def run_stationary_flight(*, request: Mapping, plant_factory=None) -> dict:
    """Hold every declared pose and sample the monitored joints at the declared feedback period."""

    factory = MujocoStopFlight if plant_factory is None else plant_factory
    poses = _pose_records(request["poses"])
    feedback_period = _positive_number("the declared feedback period", request["feedback_period_s"])
    control_period = _positive_number("the sealed control period", request["control_period_s"])
    samples_per_pose = _positive_int(
        "the declared samples per pose", request.get("samples_per_pose", DEFAULT_SAMPLES_PER_POSE)
    )
    cycles_per_sample = max(1, int(round(feedback_period / control_period)))
    declared_settle = _declared_settle(request)
    plant = _plant_of(request, factory)
    records: list[dict] = []
    try:
        for pose in poses:
            settle = plant.command_through_admission(
                pose["pose_rad"],
                purpose="anchor_positioning" if pose["pose_kind"] == "anchor" else "plan_stop",
            )
            if not settle["settled"]:
                raise _refuse(
                    CAL_STATIONARY_UNSETTLED,
                    f"the pose {pose['pose_rad']} rad of the anchor {pose['anchor']!r} never settled under "
                    f"the declared rule (final velocity {settle['final_velocity_rad_s']} rad/s, final position "
                    f"error {settle['final_position_error_rad']} rad), so its velocity noise is not the "
                    f"stationary state's and is not sampled",
                )
            samples = []
            for _ in range(samples_per_pose):
                for _ in range(cycles_per_sample):
                    plant.step_control_cycle()
                sample = plant.feedback_sample()
                samples.append(
                    {
                        "sim_s": float(sample["sim_s"]),
                        "velocity_rad_s": [float(value) for value in sample["velocity_rad_s"]],
                        "joint_velocities": [float(value) for value in sample["joint_velocities"]],
                        "joint_positions": [float(value) for value in sample["joint_positions"]],
                        "yaw_rad": float(sample["yaw_rad"]),
                        "reference_rad": float(sample["reference_rad"]),
                        "position_error_rad": float(sample["position_error_rad"]),
                        "time_base": SIMULATION_TIME_BASE,
                    }
                )
            magnitudes = [
                max(abs(value) for value in sample["velocity_rad_s"]) for sample in samples
            ]
            records.append(
                {
                    **pose,
                    "settle": dict(settle),
                    "samples": samples,
                    "p99_9_velocity_rad_s": p99_9(magnitudes),
                    "max_velocity_rad_s": max(magnitudes),
                }
            )
    finally:
        close = getattr(plant, "close", None)
        if callable(close):
            close()
    magnitudes = [
        max(abs(value) for value in sample["velocity_rad_s"])
        for record in records
        for sample in record["samples"]
    ]
    return {
        "records": records,
        "flight": {
            "feedback_period_s": feedback_period,
            "control_period_s": control_period,
            "simulation_timestep_s": float(plant.simulation_timestep_s),
            "samples_per_pose": samples_per_pose,
            "sample_count": len(magnitudes),
            "pose_count": len(records),
            "stationary_p99_9_velocity_rad_s": p99_9(magnitudes),
            "max_velocity_rad_s": max(magnitudes),
            "settle_velocity_rad_s": declared_settle["settle_velocity_rad_s"],
            "goal_tolerance_rad": declared_settle["goal_tolerance_rad"],
            "settle_consecutive_steps": int(declared_settle["settle_consecutive_steps"]),
            "real_time_factor": _real_time_factor(plant),
            "pacing": _pacing(plant),
            "ros_nodes_started": False,
        },
    }


def run_submission_flight(*, request: Mapping, plant_factory=None) -> dict:
    """Submit the installed controller's own targets through the admission port and time every lead."""

    factory = MujocoStopFlight if plant_factory is None else plant_factory
    submissions = _mapping_sequence("a declared submission", request["submissions"])
    if not submissions:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "no submission was declared: the installed controller's plan selects no target for this anchor",
        )
    plant = _plant_of(request, factory)
    records: list[dict] = []
    try:
        for index, submission in enumerate(submissions):
            record = plant.command_through_admission(
                _number(submission, "a declared submission", "target_rad"),
                purpose=submission["purpose"],
            )
            records.append(
                {
                    "index": index,
                    "purpose": submission["purpose"],
                    "submitted_by": submission["submitted_by"],
                    "time_base": SIMULATION_TIME_BASE,
                    **{key: value for key, value in record.items()},
                }
            )
    finally:
        close = getattr(plant, "close", None)
        if callable(close):
            close()
    return {
        "records": records,
        "flight": {
            "control_period_s": float(request["control_period_s"]),
            "simulation_timestep_s": float(plant.simulation_timestep_s),
            "submission_count": len(records),
            "minimum_lead_s": min(record["lead_s"] for record in records),
            "maximum_lead_s": max(record["lead_s"] for record in records),
            "real_time_factor": _real_time_factor(plant),
            "pacing": _pacing(plant),
            "ros_nodes_started": False,
        },
    }


def run_stop_proof_flight(*, request: Mapping, plant_factory=None) -> dict:
    """Revoke real motions at the declared offsets and prove every stop with the installed criterion."""

    factory = MujocoStopFlight if plant_factory is None else plant_factory
    poses = _pose_records(request["poses"])
    offsets = [_positive_number("a declared revoke offset", value, allow_zero=True)
               for value in request.get("revoke_offsets_s", DEFAULT_REVOKE_OFFSETS_S)]
    if not offsets:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, "no revoke offset was declared, so no stop is requested")
    control_period = _positive_number("the sealed control period", request["control_period_s"])
    feedback_period = _positive_number("the declared feedback period", request["feedback_period_s"])
    stop_budget = _positive_number("the declared stop budget", request.get("stop_budget_s", DEFAULT_STOP_BUDGET_S))
    plant = _plant_of(request, factory)
    port, transport, clock = controller_stop_criterion(
        stop_velocity_rad_s=request["stop_velocity_rad_s"],
        max_age_s=request["max_age_s"],
    )
    records: list[dict] = []
    try:
        for pose in poses:
            for offset in offsets:
                cycles = max(1, int(round(offset / control_period)))
                motion = plant.command_through_admission(
                    pose["pose_rad"], purpose="plan_stop", max_cycles=cycles
                )
                records.append(
                    confirm_stop(
                        plant=plant,
                        port=port,
                        transport=transport,
                        clock=clock,
                        hold_rad=plant.yaw_rad,
                        stop_budget_s=stop_budget,
                        index=len(records),
                        reason="plan_stop_revoke",
                        period_s=feedback_period,
                        motion=motion,
                        revoke_offset_s=offset,
                        anchor=pose["anchor"],
                        pose_rad=pose["pose_rad"],
                        pose_kind=pose["pose_kind"],
                        declared_production_latency_s=request.get("declared_production_latency_s"),
                    )
                )
    finally:
        close = getattr(plant, "close", None)
        if callable(close):
            close()
    latencies = [record["latency_s"] for record in records]
    return {
        "records": records,
        "flight": {
            "feedback_period_s": feedback_period,
            "control_period_s": control_period,
            "simulation_timestep_s": float(plant.simulation_timestep_s),
            "stop_velocity_rad_s": float(request["stop_velocity_rad_s"]),
            "max_age_s": float(request["max_age_s"]),
            "stop_budget_s": stop_budget,
            "revoke_offsets_s": offsets,
            "declared_production_latency_s": request.get("declared_production_latency_s"),
            "proof_count": len(records),
            "p99_9_latency_s": p99_9(latencies),
            "slowest_latency_s": max(latencies),
            "real_time_factor": _real_time_factor(plant),
            "pacing": _pacing(plant),
            "ros_nodes_started": False,
        },
    }


def _mapping_sequence(name: str, value) -> list[Mapping]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"{name} sequence is empty or not a sequence")
    for item in value:
        _mapping(name, item)
    return list(value)


def _real_time_factor(plant) -> float | None:
    factor = getattr(plant, "real_time_factor", None)
    return None if not callable(factor) else factor()


def _pacing(plant) -> dict:
    return {
        "realtime": bool(getattr(plant, "realtime", False)),
        "max_lag_s": getattr(plant, "max_lag_s", None),
        "rule": (
            "the plant is paced to the monotonic clock (as the production MuJoCo loop is), so the monotonic "
            "stop latency is a real-time quantity and not an artefact of a fast in-process loop; the achieved "
            "real-time factor and the largest lag are recorded beside every measurement"
        ),
    }


class MujocoStopFlight(MujocoClosedLoopPlant):
    """The sealed scene's neck, driven through an admission port and sampled as the stop path sees it.

    This is the only place in this module that imports MuJoCo, and it does so inside the call. It holds the
    six arm joints where the sealed model starts them, commands the neck's own position actuator once per
    sealed control cycle, samples the velocities of the monitored joints, and paces the loop to the monotonic
    clock. It commands the simulated neck only: no ROS node starts, no detector runs, no hardware is
    addressed.
    """

    def __init__(self, request: Mapping) -> None:
        super().__init__(request)
        self.control_period_s = float(request["control_period_s"])
        self.feedback_period_s = float(request["feedback_period_s"])
        self.realtime = bool(request.get("realtime", DEFAULT_REALTIME))
        self.max_lag_s = 0.0
        self.stop_velocity_rad_s = float(request["stop_velocity_rad_s"])
        self.max_age_s = float(request["max_age_s"])
        self.monitored_joints = tuple(request.get("monitored_joints") or MONITORED_JOINTS)
        self._dof_addresses: list[int] = []
        self._qpos_addresses: list[int] = []
        for name in self.monitored_joints:
            joint = self._mujoco.mj_name2id(self._model, self._mujoco.mjtObj.mjOBJ_JOINT, name)
            if joint < 0:
                raise _refuse(
                    CAL_TIMING_EVIDENCE_CONTRADICTORY,
                    f"the sealed scene {request['scene_path']} has no {name!r} joint, so its velocity cannot "
                    f"be sampled",
                )
            self._dof_addresses.append(int(self._model.jnt_dofadr[joint]))
            self._qpos_addresses.append(int(self._model.jnt_qposadr[joint]))
            actuator = self._mujoco.mj_name2id(
                self._model, self._mujoco.mjtObj.mjOBJ_ACTUATOR, name
            )
            if actuator >= 0:
                # hold every monitored joint where the sealed model starts it: the arm must not be pulled to
                # a command this flight never declared
                self._data.ctrl[actuator] = float(self._data.qpos[self._qpos_addresses[-1]])
        self._reference_rad = self.yaw_rad
        self._goal_pending: float | None = None
        self._start_monotonic = time.monotonic()
        self._start_sim_s = self.time_s

    def joint_velocity_vector(self) -> tuple[float, ...]:
        return tuple(float(self._data.qvel[address]) for address in self._dof_addresses)

    def joint_position_vector(self) -> tuple[float, ...]:
        return tuple(float(self._data.qpos[address]) for address in self._qpos_addresses)

    def hold_command(self, rad: float) -> None:
        self._data.ctrl[self._actuator] = float(rad)
        self._reference_rad = float(rad)

    def step_control_cycle(self) -> None:
        for _ in range(self._steps_per_control):
            self._mujoco.mj_step(self._model, self._data)
        self._pace()

    def _pace(self) -> None:
        if not self.realtime:
            return
        target = self._start_monotonic + (self.time_s - self._start_sim_s)
        lag = target - time.monotonic()
        if lag > 0.0:
            time.sleep(lag)
        self.max_lag_s = max(self.max_lag_s, time.monotonic() - target)

    def real_time_factor(self) -> float | None:
        wall = time.monotonic() - self._start_monotonic
        return None if wall <= 0.0 else (self.time_s - self._start_sim_s) / wall

    def feedback_sample(self) -> dict:
        return {
            "sim_s": self.time_s,
            "yaw_rad": self.yaw_rad,
            "reference_rad": self._reference_rad,
            "position_error_rad": self._reference_rad - self.yaw_rad,
            "joint_velocities": list(self.joint_velocity_vector()),
            "joint_positions": list(self.joint_position_vector()),
            "velocity_rad_s": list(self.joint_velocity_vector()),
        }

    def command_through_admission(self, target_rad: float, *, purpose: str, max_cycles=None) -> dict:
        """Snapshot one goal, drain it at the next control cycle, and settle on it (or stop early)."""

        target = float(target_rad)
        snapshot_sim = self.time_s
        reference_before = self._reference_rad
        tracker = SettleTracker(
            settle_velocity_rad_s=self._settle_velocity_rad_s,
            goal_tolerance_rad=self._goal_tolerance_rad,
            consecutive_steps=self._settle_consecutive_steps,
        )
        budget = max(1, int(math.ceil(self.max_settle_s / self.control_period_s)) + 1)
        limit = budget if max_cycles is None else min(budget, int(max_cycles))
        self._goal_pending = target
        cycles = 0
        consumed_sim = None
        settled = reached = False
        while cycles < limit:
            if self._goal_pending is not None:
                self.hold_command(self._goal_pending)
                self._goal_pending = None
            self.step_control_cycle()
            cycles += 1
            if consumed_sim is None:
                consumed_sim = self.time_s
            error = target - self.yaw_rad
            if abs(error) <= self._goal_tolerance_rad:
                reached = True
            if tracker.observe(self.velocity_rad_s, error):
                settled = True
                break
        if consumed_sim is None:  # pragma: no cover - limit is at least one cycle
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                "the admission port drained no goal: no target of this submission reached the plant",
            )
        return {
            "purpose": purpose,
            "target_rad": target,
            "reference_before_rad": reference_before,
            "submit_snapshot_sim_s": snapshot_sim,
            "first_target_sim_s": consumed_sim,
            "plant_consumed_sim_s": consumed_sim,
            "lead_s": consumed_sim - snapshot_sim,
            "control_cycles": cycles,
            "steps": cycles * self._steps_per_control,
            "settled": settled,
            "reached": reached,
            "final_velocity_rad_s": self.velocity_rad_s,
            "final_position_error_rad": target - self.yaw_rad,
            "quiet_steps": tracker.quiet_steps,
        }


# --- the producers ------------------------------------------------------------------------------------


def _write(output: Path, document: Mapping, receipt: Mapping) -> None:
    (output / RECEIPT_ARTIFACT).write_text(
        json.dumps(dict(receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifact = Path(document["path"])
    artifact.write_text(json.dumps(dict(document), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _receipt(*, kind_phase, output, document_path, command, fields) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": kind_phase,
        "command": command,
        "output_dir": str(output),
        "document_path": str(document_path),
        "document_sha256": fields.pop("document_sha256"),
        "status": fields.pop("status"),
        "refusals": fields.pop("refusals"),
        "fields_refused": fields.pop("fields_refused"),
        **fields,
    }


def write_controller_stop_config(
    *,
    installed_declaration,
    source_declaration,
    controller_config_path,
    output_dir,
    command=None,
) -> dict:
    """Read the controller's declared stopped tolerance and write the document phase 7 consumes."""

    output = Path(output_dir)
    output.mkdir(parents=True)
    tolerance = declared_controller_stop_tolerance(
        installed_declaration=installed_declaration,
        source_declaration=source_declaration,
        controller_config_path=controller_config_path,
    )
    document_path = output / STOP_CONFIG_ARTIFACT
    document = build_controller_stop_config(
        path=document_path,
        tolerance=tolerance,
        controller_config_path=controller_config_path,
        command=command,
    )
    receipt = _receipt(
        kind_phase=STOP_CONFIG_PHASE,
        output=output,
        document_path=document_path,
        command=command,
        fields={
            "document_sha256": document["sha256"],
            "status": "DECLARED",
            "refusals": [],
            "fields_refused": [],
            "stopped_tolerance_rad_s": document["stopped_tolerance_rad_s"],
            "declared_by": document["declared_by"],
            "source_declaration": document["source_declaration"],
            "window": document["window"],
            "controller_cycle_period_s": document["controller_cycle_period_s"],
            "measured_here": False,
            "ros_nodes_started": False,
            "mujoco_neck_commanded": False,
            "hardware_motion_commanded": False,
            "cuda_used": False,
        },
    )
    _write(output, document, receipt)
    return {"document": document, "receipt": receipt, "document_path": document_path,
            "output_dir": output, "refusals": []}


def write_feedback_measurements(
    *, controller_config_path, output_dir, quantisation_declaration_path=None, command=None
) -> dict:
    """Read the declared feedback period and resolution, write the document, refuse the undeclared field."""

    output = Path(output_dir)
    output.mkdir(parents=True)
    declaration = read_feedback_declarations(controller_config_path)
    quantisation = declared_quantisation(quantisation_declaration_path)
    document_path = output / FEEDBACK_ARTIFACT
    document = build_feedback_measurements(
        path=document_path,
        declaration=declaration,
        quantisation=quantisation,
        command=command,
    )
    refusals = list(document["refusals"])
    receipt = _receipt(
        kind_phase=FEEDBACK_PHASE,
        output=output,
        document_path=document_path,
        command=command,
        fields={
            "document_sha256": document["sha256"],
            "status": "MEASURED_WITH_REFUSED_FIELD" if refusals else "DECLARED",
            "refusals": refusals,
            "fields_refused": [record["field"] for record in refusals],
            "period_s": document["period_s"],
            "feedback_rate_hz": document["feedback_rate_hz"],
            "controller_cycle_period_s": document["controller_cycle_period_s"],
            "quantisation_rad": document["quantisation_rad"],
            "quantisation": document["quantisation"],
            "measured_here": False,
            "ros_nodes_started": False,
            "mujoco_neck_commanded": False,
            "hardware_motion_commanded": False,
            "cuda_used": False,
        },
    )
    _write(output, document, receipt)
    return {"document": document, "receipt": receipt, "document_path": document_path,
            "output_dir": output, "refusals": refusals}


def _flight_inputs(
    *, scene_path, geometry_seal_path, production_search_config_path, controller_config_path,
    anchors=None,
) -> dict:
    """Every sealed input of a flight, cross-checked before a single step is taken."""

    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    for path in (scene, seal_path, production_path, controller_path):
        if not path.is_file():
            raise FileNotFoundError(f"the stop measurement needs {path}")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    from so101_demo.act.head_search_mujoco_measurements import read_mujoco_timestep

    declaration = read_mujoco_timestep(scene)
    scene_sha256 = declaration["scene_sha256"]
    sealed_scene = (seal.get("source_digests") or {}).get("scene_sha256")
    if sealed_scene != scene_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry pins the scene {sealed_scene}, but the scene this flight would step "
            f"digests to {scene_sha256}",
        )
    control_period = read_control_period(controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s steps, so the plant could not be driven at the production period",
        )
    requests = _anchor_pose_requests(
        seal=seal,
        production=production,
        anchors=anchors,
        attempt_id=MEASUREMENT_ATTEMPT_ID,
        session_id=MEASUREMENT_SESSION_ID,
    )
    feedback = read_feedback_declarations(controller_path)
    motion = production.get("motion") if isinstance(production.get("motion"), Mapping) else {}
    values = production.get("values") if isinstance(production.get("values"), Mapping) else {}
    return {
        "scene": scene,
        "scene_sha256": scene_sha256,
        "seal": seal,
        "seal_path": seal_path,
        "production": production,
        "production_path": production_path,
        "controller_path": controller_path,
        "controller_period_s": control_period,
        "feedback_period_s": feedback["period_s"],
        "simulation_timestep_s": timestep,
        "requests": requests,
        "corridor": motion_corridor_rad(geometry_seal=seal),
        "camera": seal.get("camera") if isinstance(seal.get("camera"), Mapping) else {},
        "settle_velocity_rad_s": _number(
            motion, "the production motion thresholds", "settle_velocity_rad_s", positive=True
        ),
        "goal_tolerance_rad": _number(
            motion, "the production motion thresholds", "goal_tolerance_rad", positive=True
        ),
        "stop_velocity_rad_s": _number(
            values, "the production search values", "stop_velocity_rad_s", positive=True
        ),
        "max_age_s": _number(values, "the production search values", "max_age_s", positive=True),
        "declared_production_latency_s": _number(
            values, "the production search values", "stop_latency_s", positive=True
        ),
    }


def _plant_request_for(*, inputs, request, realtime, settle_consecutive_steps, max_settle_s) -> dict:
    plant_request = _plant_request(
        request=request,
        scene=inputs["scene"],
        seal=inputs["seal"],
        camera=inputs["camera"],
        control_period_s=inputs["controller_period_s"],
        max_settle_s=max_settle_s,
        settle_consecutive_steps=settle_consecutive_steps,
    )
    plant_request.update(
        {
            "feedback_period_s": inputs["feedback_period_s"],
            "realtime": bool(realtime),
            "stop_velocity_rad_s": inputs["stop_velocity_rad_s"],
            "max_age_s": inputs["max_age_s"],
            "monitored_joints": list(MONITORED_JOINTS),
        }
    )
    return plant_request


def _flight_evidence(*, inputs, flight: Mapping, timestep: float) -> dict:
    from so101_demo.act.head_search_timing_measurement.documents import runtime_identity

    return {
        **flight,
        "simulation_timestep_s": timestep,
        "scene_path": str(inputs["scene"]),
        "scene_sha256": inputs["scene_sha256"],
        "geometry_seal": {"path": str(inputs["seal_path"]), "sha256": _digest(inputs["seal_path"])},
        "production_search_config": {
            "path": str(inputs["production_path"]),
            "sha256": _digest(inputs["production_path"]),
        },
        "controller_config": {
            "path": str(inputs["controller_path"]),
            "sha256": _digest(inputs["controller_path"]),
        },
        "runtime_identity": runtime_identity(detector_loaded=False),
    }


def _check_poses(*, requests, corridor) -> None:
    for request in requests:
        for pose in request["poses"]:
            _corridor_check(
                angle_rad=pose["pose_rad"],
                corridor_rad=corridor,
                what=f"planned pose of the anchor {request['anchor']!r}",
            )


def write_stationary_measurements(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    output_dir,
    anchors=None,
    samples_per_pose=DEFAULT_SAMPLES_PER_POSE,
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    realtime=DEFAULT_REALTIME,
    command=None,
) -> dict:
    """Hold every sealed anchor's planned poses and write the stationary velocity document."""

    started = time.time()
    output = Path(output_dir)
    output.mkdir(parents=True)
    inputs = _flight_inputs(
        scene_path=scene_path,
        geometry_seal_path=geometry_seal_path,
        production_search_config_path=production_search_config_path,
        controller_config_path=controller_config_path,
        anchors=anchors,
    )
    _check_poses(requests=inputs["requests"], corridor=inputs["corridor"])
    results = []
    for request in inputs["requests"]:
        plant_request = _plant_request_for(
            inputs=inputs,
            request=request,
            realtime=realtime,
            settle_consecutive_steps=settle_consecutive_steps,
            max_settle_s=max_settle_s,
        )
        result = run_stationary_flight(
            request={
                "poses": [
                    {**pose, "anchor": request["anchor"]} for pose in request["poses"]
                ],
                "plant_request": plant_request,
                "samples_per_pose": samples_per_pose,
                "feedback_period_s": inputs["feedback_period_s"],
                "control_period_s": inputs["controller_period_s"],
            }
        )
        results.append((request, result))
    records = [record for _request, result in results for record in result["records"]]
    flight = _flight_evidence(
        inputs=inputs, flight=results[0][1]["flight"], timestep=inputs["simulation_timestep_s"]
    )
    document_path = output / STATIONARY_ARTIFACT
    document = build_stationary_measurements(
        path=document_path,
        records=records,
        samples_per_pose=samples_per_pose,
        flight=flight,
        command=command,
    )
    receipt = _receipt(
        kind_phase=STATIONARY_PHASE,
        output=output,
        document_path=document_path,
        command=command,
        fields={
            "document_sha256": document["sha256"],
            "status": "MEASURED",
            "refusals": [],
            "fields_refused": [],
            "pose_count": document["pose_count"],
            "sample_count": document["sample_count"],
            "samples_per_pose": document["samples_per_pose"],
            "p99_9_velocity_rad_s": document["p99_9_velocity_rad_s"],
            "max_velocity_rad_s": document["max_velocity_rad_s"],
            "anchor_names": [request["anchor"] for request in inputs["requests"]],
            "poses_measured": [
                {
                    "anchor": record["anchor"],
                    "pose_rad": record["pose_rad"],
                    "pose_kind": record["pose_kind"],
                    "p99_9_velocity_rad_s": record["p99_9_velocity_rad_s"],
                }
                for record in document["poses"]
            ],
            "feedback_period_s": document["feedback_period_s"],
            "controller_cycle_period_s": document["controller_cycle_period_s"],
            "simulation_timestep_s": document["simulation_timestep_s"],
            "real_time_factor": document["real_time_factor"],
            "pacing": document["pacing"],
            "scene_path": str(inputs["scene"]),
            "scene_sha256": inputs["scene_sha256"],
            "elapsed_s": time.time() - started,
            "runtime_identity": document["runtime_identity"],
            "ros_nodes_started": False,
            "mujoco_neck_commanded": True,
            "hardware_motion_commanded": False,
            "cuda_used": False,
            "detector_loaded": False,
            "transport_measured": False,
        },
    )
    _write(output, document, receipt)
    return {"document": document, "receipt": receipt, "document_path": document_path,
            "output_dir": output, "refusals": []}


def write_controller_submissions(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    output_dir,
    anchors=None,
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    realtime=DEFAULT_REALTIME,
    command=None,
) -> dict:
    """Submit the installed controller's own targets and write the goal-admission lead document."""

    started = time.time()
    output = Path(output_dir)
    output.mkdir(parents=True)
    inputs = _flight_inputs(
        scene_path=scene_path,
        geometry_seal_path=geometry_seal_path,
        production_search_config_path=production_search_config_path,
        controller_config_path=controller_config_path,
        anchors=anchors,
    )
    _check_poses(requests=inputs["requests"], corridor=inputs["corridor"])
    records = []
    flights = []
    for request in inputs["requests"]:
        plan = planned_stops(request["controller_config"])
        submissions = [
            {
                "purpose": "anchor_positioning",
                "submitted_by": (
                    "the sealed anchor's own search start (so101_demo.act.search.HeadSearchController "
                    "search_start_rad)"
                ),
                "target_rad": float(request["search_start_rad"]),
            },
            *[
                {
                    "purpose": "plan_stop",
                    "submitted_by": (
                        "so101_demo.act.search.HeadSearchController.next_target(): the installed controller's "
                        "own bounded plan stop"
                    ),
                    "target_rad": float(target),
                }
                for target in plan
            ],
        ]
        result = run_submission_flight(
            request={
                "submissions": submissions,
                "plant_request": _plant_request_for(
                    inputs=inputs,
                    request=request,
                    realtime=realtime,
                    settle_consecutive_steps=settle_consecutive_steps,
                    max_settle_s=max_settle_s,
                ),
                "control_period_s": inputs["controller_period_s"],
            }
        )
        records.extend(result["records"])
        flights.append((request, result))
    flight = _flight_evidence(
        inputs=inputs, flight=flights[0][1]["flight"], timestep=inputs["simulation_timestep_s"]
    )
    document_path = output / SUBMISSIONS_ARTIFACT
    document = build_controller_submissions(
        path=document_path, records=records, flight=flight, command=command
    )
    receipt = _receipt(
        kind_phase=SUBMISSIONS_PHASE,
        output=output,
        document_path=document_path,
        command=command,
        fields={
            "document_sha256": document["sha256"],
            "status": "MEASURED",
            "refusals": [],
            "fields_refused": [],
            "submission_count": document["submission_count"],
            "minimum_lead_s": document["minimum_lead_s"],
            "maximum_lead_s": document["maximum_lead_s"],
            "lead_spread_s": document["lead_spread_s"],
            "control_period_s": document["control_period_s"],
            "simulation_timestep_s": document["simulation_timestep_s"],
            "time_base": document["time_base"],
            "time_base_proof": document["time_base_proof"],
            "anchor_names": [request["anchor"] for request in inputs["requests"]],
            "submissions": [
                {
                    "purpose": sample["purpose"],
                    "target_rad": sample["target_rad"],
                    "submit_snapshot_sim_s": sample["submit_snapshot_sim_s"],
                    "first_target_sim_s": sample["first_target_sim_s"],
                    "lead_s": sample["lead_s"],
                }
                for sample in document["samples"]
            ],
            "real_time_factor": document["real_time_factor"],
            "pacing": document["pacing"],
            "scene_path": str(inputs["scene"]),
            "scene_sha256": inputs["scene_sha256"],
            "elapsed_s": time.time() - started,
            "runtime_identity": document["runtime_identity"],
            "ros_nodes_started": False,
            "mujoco_neck_commanded": True,
            "hardware_motion_commanded": False,
            "cuda_used": False,
            "detector_loaded": False,
            "transport_measured": False,
        },
    )
    _write(output, document, receipt)
    return {"document": document, "receipt": receipt, "document_path": document_path,
            "output_dir": output, "refusals": []}


def write_stop_proofs(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    output_dir,
    anchors=None,
    revoke_offsets_s=None,
    stop_budget_s=DEFAULT_STOP_BUDGET_S,
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    realtime=DEFAULT_REALTIME,
    command=None,
) -> dict:
    """Revoke declared motions and write the stop/revoke proof document phase 7 bounds the latency with."""

    started = time.time()
    output = Path(output_dir)
    output.mkdir(parents=True)
    inputs = _flight_inputs(
        scene_path=scene_path,
        geometry_seal_path=geometry_seal_path,
        production_search_config_path=production_search_config_path,
        controller_config_path=controller_config_path,
        anchors=anchors,
    )
    _check_poses(requests=inputs["requests"], corridor=inputs["corridor"])
    records = []
    flights = []
    for request in inputs["requests"]:
        poses = [pose for pose in request["poses"] if pose["pose_kind"] == "plan"]
        if not poses:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"the anchor {request['anchor']!r} has no plan stop, so there is no motion to revoke",
            )
        result = run_stop_proof_flight(
            request={
                "poses": [{**pose, "anchor": request["anchor"]} for pose in poses],
                "plant_request": _plant_request_for(
                    inputs=inputs,
                    request=request,
                    realtime=realtime,
                    settle_consecutive_steps=settle_consecutive_steps,
                    max_settle_s=max_settle_s,
                ),
                "revoke_offsets_s": (
                    DEFAULT_REVOKE_OFFSETS_S if revoke_offsets_s is None else tuple(revoke_offsets_s)
                ),
                "stop_budget_s": stop_budget_s,
                "feedback_period_s": inputs["feedback_period_s"],
                "control_period_s": inputs["controller_period_s"],
                "stop_velocity_rad_s": inputs["stop_velocity_rad_s"],
                "max_age_s": inputs["max_age_s"],
                "declared_production_latency_s": inputs["declared_production_latency_s"],
            }
        )
        records.extend(result["records"])
        flights.append((request, result))
    flight = _flight_evidence(
        inputs=inputs, flight=flights[0][1]["flight"], timestep=inputs["simulation_timestep_s"]
    )
    document_path = output / STOP_PROOFS_ARTIFACT
    document = build_stop_proofs(path=document_path, records=records, flight=flight, command=command)
    receipt = _receipt(
        kind_phase=STOP_PROOFS_PHASE,
        output=output,
        document_path=document_path,
        command=command,
        fields={
            "document_sha256": document["sha256"],
            "status": "MEASURED",
            "refusals": [],
            "fields_refused": [],
            "proof_count": document["proof_count"],
            "p99_9_latency_s": document["p99_9_latency_s"],
            "slowest_latency_s": document["slowest_latency_s"],
            "feedback_period_s": document["feedback_period_s"],
            "stop_velocity_rad_s": document["stop_velocity_rad_s"],
            "max_age_s": document["max_age_s"],
            "stop_budget_s": document["stop_budget_s"],
            "revoke_offsets_s": document["revoke_offsets_s"],
            "declared_production_latency_s": document["declared_production_latency_s"],
            "exceedance_count": document["exceedance_count"],
            "pacing_faithful_proof_count": document["pacing_faithful_proof_count"],
            "off_schedule_sample_indices": document["off_schedule_sample_indices"],
            "exceeding_sample_indices": document["exceeding_sample_indices"],
            "anchor_names": [request["anchor"] for request in inputs["requests"]],
            "proofs": [
                {
                    "index": sample["index"],
                    "pose_rad": sample["pose_rad"],
                    "revoke_offset_s": sample["revoke_offset_s"],
                    "stop_request_monotonic_s": sample["stop_request_monotonic_s"],
                    "third_confirming_receive_monotonic_s": sample[
                        "third_confirming_receive_monotonic_s"
                    ],
                    "latency_s": sample["latency_s"],
                    "sim_latency_s": sample["sim_latency_s"],
                    "sample_count": sample["sample_count"],
                }
                for sample in document["samples"]
            ],
            "real_time_factor": document["real_time_factor"],
            "pacing": document["pacing"],
            "scene_path": str(inputs["scene"]),
            "scene_sha256": inputs["scene_sha256"],
            "elapsed_s": time.time() - started,
            "runtime_identity": document["runtime_identity"],
            "ros_nodes_started": False,
            "mujoco_neck_commanded": True,
            "hardware_motion_commanded": False,
            "cuda_used": False,
            "detector_loaded": False,
            "transport_measured": False,
        },
    )
    _write(output, document, receipt)
    return {"document": document, "receipt": receipt, "document_path": document_path,
            "output_dir": output, "refusals": []}
