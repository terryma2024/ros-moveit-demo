"""The installed producer of the run's `--admission`: one generation, one measurement plan, one binding.

The run takes a single `role=calibration` measurement flight through the repository's own
`CalibrationMeasurementAdmission`, and this module produces the document that carries it - exactly the
six fields the run's entry reads - from documents the run also declares, so nothing about the admission
is hand-written:

* **one generation**: the brand-new run root the run will claim. Its name is the generation, and a run
  root that already exists is refused, so a generation is never reused and never resumed;
* **one measurement plan**: the *flat* configuration the installed `HeadSearchController` is constructed
  with - the declared production search values with the sealed geometry's field of view, safe interval
  and required search domain. The run's own trajectory precondition decides whether it is admissible, and
  the digest recorded in the admission is the canonical digest of that document, so phase 2's sweep-check
  receipts bind the very plan the admission granted;
* **one safe interval**: the sealed geometry's `lock_valid_neck_rad`, which is also the interval phase 2
  re-checks the admission against;
* **release and recorder refused, once**: every refusal the runtime contract fixes is *executed* against
  the produced admission and recorded, including the second flight and the second resource binding, so
  the receipt shows the flight is single-use rather than asserting that it is.

`controller_generation` and `broker_generation` are recorded as absent with their reason: no phase of
this calibration sends a neck target and no broker session takes part, so there is no controller
incarnation or broker generation to cite. Writing a token there would invent one; the receipt records
the absence instead (HS-311).

Nothing here commands motion, starts ROS, a simulator or a detector, and nothing is written unless the
caller passes an explicit `output_dir`; the three documents named below are the only files this module
creates.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path

from so101_demo.act.head_search_calibration_geometry import (
    load_sealed_geometry,
    read_geometry_document,
)
from so101_demo.act.head_search_calibration_inputs import (
    CALIBRATION_ROLE,
    CAL_ADMISSION_REFUSED,
    CAL_BINDING_REBOUND,
    CalibrationInputsRefused,
    CalibrationResourceBinder,
    validate_head_search_calibration_inputs,
    validate_sealed_inputs,
)
from so101_demo.act.head_search_operating_point_measurement import toolchain_identity
from so101_demo.act.task8_calibration_admission import CalibrationMeasurementAdmission
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_calibration_admission_receipt"
PHASE = "input_validation"

#: the three documents this producer owns
PLAN_NAME = "measurement-plan.json"
ADMISSION_NAME = "admission.json"
RECEIPT_NAME = "admission-receipt.json"
ARTIFACT_NAMES = (PLAN_NAME, ADMISSION_NAME, RECEIPT_NAME)

#: the admission document the run reads: exactly these six fields, no more and no fewer
ADMISSION_FIELDS = (
    "generation",
    "status",
    "measurement_plan_sha256",
    "safe_interval_rad",
    "controller_generation",
    "broker_generation",
)

#: the only status that admits one calibration flight
ADMISSIBLE_STATUS = "CALIBRATION_REQUIRED"

#: this producer refuses a declaration it cannot turn into an admission; the plan's own precondition
#: keeps its own code, so a controller that refuses the plan is refused by the run's name for it
CAL_ADMISSION_INCOMPLETE = "CAL_ADMISSION_INCOMPLETE"
CAL_TRAJECTORY_CONTRACT_UNSATISFIED = "CAL_TRAJECTORY_CONTRACT_UNSATISFIED"
REFUSAL_CODES = (CAL_ADMISSION_INCOMPLETE, CAL_TRAJECTORY_CONTRACT_UNSATISFIED)

#: the controller configuration keys the plan carries besides the eleven search values of the sealed
#: production configuration: the motion tolerances, the camera frames and the run's own identity
PLAN_IDENTITY_KEYS = ("attempt_id", "session_id", "search_start_rad")
PLAN_MOTION_KEYS = ("settle_velocity_rad_s", "goal_tolerance_rad")
PLAN_CAMERA_KEYS = ("frame_id", "ray_origin_frame_id")
PLAN_GEOMETRY_KEYS = ("horizontal_fov_rad", "lock_valid_neck_rad", "required_search_domain_rad")
PLAN_VALUE_KEYS = (
    "horizontal_fov_rad",
    "coarse_step_rad",
    "search_timeout_s",
    "max_age_s",
    "max_skew_s",
    "center_deadband_px",
    "vertical_bounds_px",
    "min_area_px2",
    "min_confidence",
    "max_fine_corrections",
    "max_fine_total_rad",
)

#: how far the sealed field of view may sit from the one its own camera intrinsics derive: the seal
#: states one number and carries the intrinsics it was computed from, and the two have to agree
FOV_TOLERANCE_RAD = 1e-9

_CONTROLLER_INCARNATION_REASON = (
    "this calibration flight declares no controller incarnation and no broker generation: no phase of "
    "this run sends a neck target (phase 2 issues computed sweep-check receipts with "
    "motion_commanded=false) and no command broker session takes part, so no such identity exists to "
    "cite and none is invented (HS-311)"
)

#: the zero position the bounded two-way plan starts from when the caller declares no other start; it is
#: recorded in the receipt together with the sealed anchors it coincides with
DEFAULT_SEARCH_START_RAD = 0.0


class CalibrationAdmissionDocumentRefused(CalibrationInputsRefused):
    """A producer refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _refuse(detail: str) -> CalibrationAdmissionDocumentRefused:
    return CalibrationAdmissionDocumentRefused(CAL_ADMISSION_INCOMPLETE, detail)


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mapping(name: str, value) -> Mapping:
    if not isinstance(value, Mapping):
        raise _refuse(f"the declared {name} is not a document of values")
    return value


def _declared(where: str, block: Mapping, name: str):
    if name not in block:
        raise _refuse(f"{where} declares no {name}")
    return block[name]


def _ordered_interval(name: str, value) -> tuple[float, float]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(type(item) not in (int, float) or not math.isfinite(item) for item in value)
        or not value[0] < value[1]
    ):
        raise _refuse(f"the sealed geometry declares no ordered {name}")
    return float(value[0]), float(value[1])


def _derived_horizontal_fov(camera: Mapping) -> float:
    """The field of view the sealed camera intrinsics derive, or a refusal naming what is missing."""

    fovy = _declared("the sealed camera", camera, "fovy_rad")
    width = _declared("the sealed camera", camera, "width")
    height = _declared("the sealed camera", camera, "height")
    if any(type(item) not in (int, float) or not math.isfinite(item) for item in (fovy, width, height)):
        raise _refuse("the sealed camera intrinsics are not finite numbers")
    if not 0.0 < float(fovy) < math.pi or float(width) <= 0 or float(height) <= 0:
        raise _refuse("the sealed camera intrinsics are not a usable camera")
    return 2.0 * math.atan(math.tan(float(fovy) / 2.0) * float(width) / float(height))


def derive_measurement_plan(
    *,
    production_config,
    geometry_document,
    generation: str,
    search_start_rad: float = DEFAULT_SEARCH_START_RAD,
) -> dict:
    """The flat configuration the installed controller is constructed with, for one generation.

    The declared production search configuration supplies the eleven search values and the motion
    tolerances, its camera block supplies the two frame identifiers, and the **sealed** geometry supplies
    the field of view, the safe interval and the required search domain - never the configuration's own
    copy of them, which a drifted config could have moved without the seal knowing. The sealed field of
    view is cross-checked against the one the sealed camera intrinsics derive, so a seal whose number and
    intrinsics disagree is refused here rather than vouchsafed by a receipt.
    """

    if type(generation) is not str or not generation:
        raise _refuse("the generation must be a non-empty name")
    config = _mapping("production search configuration", production_config)
    values = _mapping("production search values", _declared("the production search configuration", config, "values"))
    motion = _mapping("production motion block", _declared("the production search configuration", config, "motion"))
    camera = _mapping("production camera block", _declared("the production search configuration", config, "camera"))
    # phase 2's own reader: the sealed document's own digest has to cover its body, and the values the
    # plan carries are the ones that reader validated rather than this module's second opinion
    sealed = read_geometry_document(geometry_document)

    plan: dict = {}
    for name in PLAN_VALUE_KEYS:
        if name in PLAN_GEOMETRY_KEYS:
            continue
        plan[name] = _declared("the production search values", values, name)
    plan["horizontal_fov_rad"] = _declared("the sealed geometry", sealed, "horizontal_fov_rad")
    plan["lock_valid_neck_rad"] = list(
        _ordered_interval("lock_valid_neck_rad", _declared("the sealed geometry", sealed, "lock_valid_neck_rad"))
    )
    plan["required_search_domain_rad"] = list(
        _ordered_interval(
            "required_search_domain_rad",
            _declared("the sealed geometry", sealed, "required_search_domain_rad"),
        )
    )
    for name in PLAN_MOTION_KEYS:
        plan[name] = _declared("the production motion block", motion, name)
    for name in PLAN_CAMERA_KEYS:
        plan[name] = _declared("the production camera block", camera, name)
    plan["session_id"] = generation
    plan["attempt_id"] = generation
    plan["search_start_rad"] = search_start_rad
    if type(search_start_rad) not in (int, float) or not math.isfinite(search_start_rad):
        raise _refuse("the search start must be one finite angle")
    low, high = plan["lock_valid_neck_rad"]
    if not low <= float(search_start_rad) <= high:
        raise _refuse(
            f"the declared search start {search_start_rad} is outside the sealed safe interval "
            f"{plan['lock_valid_neck_rad']}, so the plan would start where the seal allowed no target"
        )

    sealed_camera = (
        geometry_document.get("camera") if isinstance(geometry_document, Mapping) else None
    )
    if not isinstance(sealed_camera, Mapping):
        raise _refuse(
            "the sealed geometry carries no camera intrinsics, so its field of view cannot be derived "
            "independently of the number it states"
        )
    derived = _derived_horizontal_fov(sealed_camera)
    if abs(derived - float(plan["horizontal_fov_rad"])) > FOV_TOLERANCE_RAD:
        raise _refuse(
            f"the sealed field of view {plan['horizontal_fov_rad']!r} is not the one the sealed camera "
            f"intrinsics derive ({derived!r})"
        )
    return plan


def _controller_refusal(detail: str) -> CalibrationAdmissionDocumentRefused:
    return CalibrationAdmissionDocumentRefused(CAL_TRAJECTORY_CONTRACT_UNSATISFIED, detail)


def _trajectory_contract(plan: Mapping) -> dict:
    """The run's own precondition, applied here so the plan is admissible before it is recorded."""

    from so101_demo.act.head_search_calibration_run import (
        CAL_TRAJECTORY_CONTRACT_UNSATISFIED as run_code,
        CalibrationRunRefused,
        check_trajectory_contract,
    )

    if run_code != CAL_TRAJECTORY_CONTRACT_UNSATISFIED:  # pragma: no cover - a drift guard
        raise _refuse("the run's trajectory-contract code is not the one this producer records")
    try:
        return check_trajectory_contract(production_search_config=plan)
    except CalibrationRunRefused as error:
        raise _controller_refusal(
            f"the installed controller refuses the derived measurement plan: {error.detail}"
        ) from error
    except (KeyError, TypeError, ValueError) as error:
        raise _controller_refusal(
            f"the installed controller refuses the derived measurement plan: {error}"
        ) from error


def _require_refused(*, what: str, expected_code: str, call) -> dict:
    """Execute one refusal the runtime contract fixes, and refuse to record a flight that is not refused.

    A refusal the installed code failed to raise is not a detail to note: it is the contract not holding,
    so the producer stops and writes no admission rather than vouchsafing a flight the contract forbids.
    """

    try:
        call()
    except CalibrationInputsRefused as error:
        if error.code != expected_code:
            raise _refuse(
                f"{what} was refused as {error.code} rather than {expected_code}: {error.detail}"
            ) from error
        return {"refused": True, "code": error.code, "detail": str(error)}
    raise _refuse(f"the installed phase 1 admitted {what}, which the runtime contract refuses")


def _probe_refusals(*, admission, admission_document, generation: str, operation: str, binder) -> dict:
    """Every refusal the runtime contract fixes, executed against the produced admission itself."""

    from so101_demo.act.head_search_calibration_inputs import decide_calibration_admission

    refusals = {}
    for refused_operation in ("release", "recorder"):
        refusals[refused_operation] = _require_refused(
            what=f"{refused_operation!r}",
            expected_code=CAL_ADMISSION_REFUSED,
            call=lambda name=refused_operation: decide_calibration_admission(
                admission=admission, generation=generation, operation=name, role=CALIBRATION_ROLE
            ),
        )
    refusals["foreign_role"] = _require_refused(
        what="a foreign role",
        expected_code=CAL_ADMISSION_REFUSED,
        call=lambda: decide_calibration_admission(
            admission=admission, generation=generation, operation=operation, role="act"
        ),
    )
    refusals["foreign_role"]["role"] = "act"
    # the flight the installed phase 1 already took: the same admission may not take a second one
    refusals["second_flight"] = _require_refused(
        what="a second flight",
        expected_code=CAL_ADMISSION_REFUSED,
        call=lambda: decide_calibration_admission(
            admission=admission, generation=generation, operation=operation, role=CALIBRATION_ROLE
        ),
    )
    interval = admission_document["safe_interval_rad"]
    refusals["second_resource_binding"] = _require_refused(
        what="a second resource binding",
        expected_code=CAL_BINDING_REBOUND,
        call=lambda: binder.bind(
            generation=generation,
            measurement_plan_sha256=admission_document["measurement_plan_sha256"],
            safe_interval_rad=interval,
            cpu_cores=1,
            gpu_device=0,
        ),
    )
    return refusals


def record_admission_document(
    *,
    sealed_inputs,
    run_root,
    output_dir,
    operation: str = "neck_target",
    role: str = CALIBRATION_ROLE,
    cpu_cores: int = 1,
    gpu_device=0,
    search_start_rad: float = DEFAULT_SEARCH_START_RAD,
    command=None,
) -> dict:
    """Produce `measurement-plan.json`, `admission.json` and the receipt that proves both.

    Everything is validated before the output directory is created: the six sealed inputs by digest, the
    geometry through phase 2's own loader, the plan through the run's own trajectory precondition, the
    admission through the installed phase 1 - which admits the single `role=calibration` flight - and
    every refusal the contract fixes, executed against that same admission. A refusal therefore leaves no
    directory, no plan and no admission behind.
    """

    root = Path(run_root)
    if root.exists():
        raise _refuse(
            f"the run root {root} already exists, so the generation {root.name!r} it names is not "
            "brand new: one generation is one run, and no reuse"
        )
    generation = root.name
    if not generation:
        raise _refuse(f"the run root {root} names no generation")
    output = Path(output_dir)
    if output.exists():
        raise _refuse(f"{output} exists; the producer's documents are never resumed or overwritten")

    production_config_path = Path(sealed_inputs["production_config"]["path"])
    manifest = validate_sealed_inputs(sealed_inputs)
    loaded = load_sealed_geometry(sealed_inputs)
    production_config = json.loads(production_config_path.read_text(encoding="utf-8"))
    geometry_document = json.loads(
        Path(loaded["sealed_geometry"]["path"]).read_text(encoding="utf-8")
    )
    plan = derive_measurement_plan(
        production_config=production_config,
        geometry_document=geometry_document,
        generation=generation,
        search_start_rad=search_start_rad,
    )
    contract = _trajectory_contract(plan)
    plan_sha256 = canonical_sha256(plan)
    admission_document = {
        "generation": generation,
        "status": ADMISSIBLE_STATUS,
        "measurement_plan_sha256": plan_sha256,
        "safe_interval_rad": [float(value) for value in loaded["geometry"]["lock_valid_neck_rad"]],
        "controller_generation": None,
        "broker_generation": None,
    }
    if tuple(admission_document) != ADMISSION_FIELDS:  # pragma: no cover - a shape guard
        raise _refuse(f"the admission declares exactly {list(ADMISSION_FIELDS)}")
    admission = CalibrationMeasurementAdmission(**admission_document)
    binder = CalibrationResourceBinder()
    phase_one = validate_head_search_calibration_inputs(
        sealed_inputs=sealed_inputs,
        admission=admission,
        generation=generation,
        operation=operation,
        cpu_cores=cpu_cores,
        gpu_device=gpu_device,
        role=role,
        binder=binder,
    )
    refusals = _probe_refusals(
        admission=admission,
        admission_document=admission_document,
        generation=generation,
        operation=operation,
        binder=binder,
    )

    output.mkdir(parents=True)
    plan_path = output / PLAN_NAME
    admission_path = output / ADMISSION_NAME
    receipt_path = output / RECEIPT_NAME
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    admission_path.write_text(
        json.dumps(admission_document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sealed_manifest = {
        name: {"path": record["path"], "sha256": record["sha256"]}
        for name, record in manifest["inputs"].items()
    }
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "status": "ADMITTED",
        "generation": generation,
        "generation_origin": "run_root_name",
        "run_root": str(root),
        "run_root_existed": False,
        "measurement_plan": {
            "path": str(plan_path),
            "sha256": _digest(plan_path),
            "canonical_sha256": plan_sha256,
        },
        "admission": {
            "path": str(admission_path),
            "sha256": _digest(admission_path),
            **admission_document,
        },
        "trajectory_contract": contract,
        "phase_one": phase_one,
        "refusals": refusals,
        "controller_incarnation": {
            "declared": False,
            "controller_generation": None,
            "broker_generation": None,
            "reason": _CONTROLLER_INCARNATION_REASON,
        },
        "motion_commanded": False,
        "provenance": {
            "command": command,
            "sealed_inputs": sealed_manifest,
            "geometry_seal_path": loaded["sealed_geometry"]["path"],
            "geometry_seal_sha256": loaded["sealed_geometry"]["sha256"],
            "production_config_path": str(production_config_path),
            "production_config_sha256": _digest(production_config_path),
            "search_start_rad": float(search_start_rad),
            "sealed_anchors_rad": dict(loaded["geometry"]["anchors_rad"]),
            "search_start_matches_anchors": sorted(
                name
                for name, angle in loaded["geometry"]["anchors_rad"].items()
                if float(angle) == float(search_start_rad)
            ),
            "toolchain": toolchain_identity(__file__),
        },
    }
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "admission": admission_document,
        "measurement_plan": plan,
        "receipt": receipt,
        "admission_path": admission_path,
        "measurement_plan_path": plan_path,
        "receipt_path": receipt_path,
    }
