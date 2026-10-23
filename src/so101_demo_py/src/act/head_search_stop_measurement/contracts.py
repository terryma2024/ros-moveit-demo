"""Kinds, refusal codes, rules and small validators of the stop measurement."""

from __future__ import annotations

from collections.abc import Mapping
import re

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_timing_measurement.contracts import (
    _finite,
)

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
