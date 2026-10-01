"""Phase 8 of the formal head search calibration: the bundle, its manifest and the run status.

The phase assembles what the earlier phases measured and records it as the run's final artefacts:

* the seventeen parameters of design section 7.1, each with the evidence block section 7.1 requires -
  value, unit, selection formula, input evidence with its SHA256, observed distribution, safety margin,
  production owner and the startup readback that proves the running system uses the value;
* the five items section 7.1 also requires recorded though they are not among the seventeen:
  `settle_velocity_rad_s`, `goal_tolerance_rad`, the three-consecutive-frame lock rule, the tracker
  algorithm and the 10 Hz frame contract (plan section 2b, ledger HS-282);
* the runtime identity of section 2b and the controlled dependencies with their digests;
* `manifest.json` and `run-status.json`. The status is `SUCCEEDED` or `FAILED`, and a failed run records
  the first failing phase, its code, command, exit code and the evidence already produced - and never a
  bundle, because a failed run is not promotable (design section 8.2).

Phase 8 records **no approval state of any kind**. The approval is bound to the bundle digest later, by
the promotion step (plan section 2a), so no `approved`, `approval`, `approved_bundle_sha256` or
equivalent field appears in any produced document; a phase input that smuggles one in is refused.

Nothing here measures anything, starts ROS, MuJoCo or a detector, or reads a file: the phase consumes
the documents the other phases produced. Nothing is written unless the caller passes an explicit
`output_dir`, and the three documents below are the only files this module ever creates.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import (
    SEALED_INPUT_NAMES,
    CalibrationInputsRefused,
)

SCHEMA_VERSION = 1
KIND = "head_search_calibration_bundle"
MANIFEST_KIND = "head_search_calibration_manifest"
RUN_STATUS_KIND = "head_search_calibration_run_status"
PHASE = "bundle_generation"

#: this phase owns `CAL_BUNDLE_INCOMPLETE`; `CAL_EFFECTIVE_VALUE_MISMATCH` is the plan's own code for a
#: value whose startup readback does not prove the running system uses it (plan section 2b)
CAL_BUNDLE_INCOMPLETE = "CAL_BUNDLE_INCOMPLETE"
CAL_EFFECTIVE_VALUE_MISMATCH = "CAL_EFFECTIVE_VALUE_MISMATCH"
REFUSAL_CODES = (CAL_BUNDLE_INCOMPLETE, CAL_EFFECTIVE_VALUE_MISMATCH)

#: the authoritative seventeen, in the order ledger HS-278 lists them (design section 7.1)
PARAMETERS = (
    "horizontal_fov_rad",
    "lock_valid_neck_rad",
    "coarse_step_rad",
    "search_timeout_s",
    "min_confidence",
    "tracking_iou",
    "min_bbox_aspect",
    "min_area_px2",
    "center_deadband_px",
    "vertical_bounds_px",
    "max_fine_corrections",
    "max_fine_total_rad",
    "max_age_s",
    "max_skew_s",
    "submit_lead_s",
    "stop_velocity_rad_s",
    "stop_latency_s",
)

#: which phase hands over which parameter, exactly as plan section 3 maps them
PHASE_PARAMETERS = {
    "geometry_coverage": ("horizontal_fov_rad", "lock_valid_neck_rad"),
    "perception_operating_point": (
        "min_confidence",
        "tracking_iou",
        "min_bbox_aspect",
        "min_area_px2",
    ),
    "search_parameters": (
        "coarse_step_rad",
        "search_timeout_s",
        "center_deadband_px",
        "vertical_bounds_px",
        "max_fine_corrections",
        "max_fine_total_rad",
    ),
    "timing_stop_parameters": (
        "max_age_s",
        "max_skew_s",
        "submit_lead_s",
        "stop_velocity_rad_s",
        "stop_latency_s",
    ),
}

#: the evidence block design section 7.1 requires of every one of the seventeen
PARAMETER_EVIDENCE_KEYS = (
    "value",
    "unit",
    "selection_formula",
    "input_evidence",
    "observed_distribution",
    "safety_margin",
    "production_owner",
    "startup_readback",
)

#: one input-evidence reference: the path that was read and the digest it had
EVIDENCE_REFERENCE_KEYS = ("path", "sha256")

#: the five items recorded though outside the seventeen (design section 7.1, final paragraph)
ALSO_RECORDED_ITEMS = (
    "settle_velocity_rad_s",
    "goal_tolerance_rad",
    "three_consecutive_frame_lock_rule",
    "tracker_algorithm",
    "frame_contract_10_hz",
)
ALSO_RECORDED_KEYS = ("value_or_definition", "input_evidence", "startup_readback")

#: the runtime identity of plan section 2b, field for field
RUNTIME_IDENTITY_FIELDS = (
    "package_prefix",
    "console_script_path",
    "detector_weights_sha256",
    "torch_version",
    "ultralytics_version",
    "cuda_version",
    "driver_version",
    "mujoco_version",
    "camera_id",
    "camera_intrinsics_sha256",
    "tracker_id",
    "web_bundle_id",
)

#: one controlled dependency: where it was read from and the digest it had
DEPENDENCY_KEYS = ("path", "sha256")

#: the three documents this phase writes, named as design section 8.3 names them
BUNDLE_NAME = "head-search-calibration-bundle.json"
MANIFEST_NAME = "manifest.json"
RUN_STATUS_NAME = "run-status.json"
ARTIFACT_NAMES = (BUNDLE_NAME, MANIFEST_NAME, RUN_STATUS_NAME)

#: what a failed run has to record: the first failing phase, its code, command, exit code and the
#: evidence already produced (design section 8.2)
FAILURE_KEYS = ("phase", "code", "command", "exit_code", "evidence_produced")

RUN_STATUSES = ("SUCCEEDED", "FAILED")

#: an approval state is not phase 8's to record; these are the names it must never carry
APPROVAL_TOKENS = ("approval", "approved", "approve", "signoff", "sign_off")

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CalibrationBundleRefused(CalibrationInputsRefused):
    """A phase-8 refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _valid_value(value) -> bool:
    """One finite number, or one ordered pair of finite numbers, is a value phase 8 can record."""

    if _finite(value):
        return True
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(_finite(bound) for bound in value)
        and value[0] < value[1]
    )


def _refuse(detail: str) -> CalibrationBundleRefused:
    return CalibrationBundleRefused(CAL_BUNDLE_INCOMPLETE, detail)


def _evidence_references(name: str, references) -> None:
    if (
        isinstance(references, (str, bytes))
        or not isinstance(references, Sequence)
        or not references
    ):
        raise _refuse(f"{name}: input evidence is a non-empty list of path and sha256 references")
    for reference in references:
        if not isinstance(reference, Mapping) or set(reference) != set(EVIDENCE_REFERENCE_KEYS):
            raise _refuse(
                f"{name}: an input evidence reference is exactly "
                f"{list(EVIDENCE_REFERENCE_KEYS)}, not {reference!r}"
            )
        if type(reference["path"]) is not str or not reference["path"]:
            raise _refuse(f"{name}: an input evidence reference names no path")
        if type(reference["sha256"]) is not str or _SHA256.fullmatch(reference["sha256"]) is None:
            raise _refuse(f"{name}: the input evidence {reference['path']!r} has no sha256 digest")


def _parameter_block(name: str, record) -> dict:
    """Check one parameter's evidence block and return it, verbatim, for the bundle."""

    if not isinstance(record, Mapping):
        raise _refuse(f"{name}: a value is declared without its evidence block")
    missing = [key for key in PARAMETER_EVIDENCE_KEYS if key not in record]
    if missing:
        raise _refuse(f"{name}: the evidence block omits {missing}")
    value = record["value"]
    if not _valid_value(value):
        raise _refuse(f"{name}: {value!r} is not one finite value or one ordered pair")
    for key in ("unit", "selection_formula", "production_owner"):
        if type(record[key]) is not str or not record[key]:
            raise _refuse(f"{name}: {key} is not a non-empty string")
    for key in ("observed_distribution", "safety_margin"):
        if not isinstance(record[key], Mapping) or not record[key]:
            raise _refuse(f"{name}: {key} is not a recorded distribution or margin")
    _evidence_references(name, record["input_evidence"])
    readback = record["startup_readback"]
    if not isinstance(readback, Mapping) or "observed_value" not in readback:
        raise _refuse(f"{name}: the startup readback records no observed value")
    if readback["observed_value"] != value:
        raise CalibrationBundleRefused(
            CAL_EFFECTIVE_VALUE_MISMATCH,
            f"{name}: the startup readback observed {readback['observed_value']!r} but the bundle "
            f"records {value!r}; the running system has to use the recorded value",
        )
    return dict(record)


def _collect_parameters(phase_inputs) -> dict:
    """Collect the seventeen blocks from the four phases that own them, or refuse the bundle."""

    if not isinstance(phase_inputs, Mapping):
        raise _refuse("the phase inputs are not a document of phase documents")
    collected: dict[str, dict] = {}
    for phase, owned in PHASE_PARAMETERS.items():
        document = phase_inputs.get(phase)
        if document is None:
            continue
        if not isinstance(document, Mapping):
            raise _refuse(f"{phase}: the phase document is not a mapping")
        declared = document.get("parameters")
        if declared is None:
            continue
        if not isinstance(declared, Mapping):
            raise _refuse(f"{phase}: the declared parameters are not a mapping of evidence blocks")
        for name, record in declared.items():
            if name not in PARAMETERS:
                raise _refuse(f"{name!r} is not one of the seventeen parameters")
            if name not in owned:
                raise _refuse(f"{name}: phase {phase!r} does not own this parameter")
            if name in collected:
                raise _refuse(f"{name}: the parameter is declared by more than one phase")
            collected[name] = _parameter_block(name, record)
    missing = [name for name in PARAMETERS if name not in collected]
    if missing:
        raise _refuse(f"the bundle is missing {missing}")
    return {name: collected[name] for name in PARAMETERS}


def _check_dependencies(controlled_dependencies) -> dict:
    """Check the six controlled dependencies of plan section 2b, each with the digest it was read at."""

    if not isinstance(controlled_dependencies, Mapping):
        raise _refuse("the controlled dependencies are not a document of dependencies")
    declared = set(controlled_dependencies)
    required = set(SEALED_INPUT_NAMES)
    if declared != required:
        missing = sorted(required - declared)
        unknown = sorted(declared - required)
        detail = []
        if missing:
            detail.append(f"the bundle omits the controlled dependencies {missing}")
        if unknown:
            detail.append(f"the bundle declares dependencies outside the sealed six: {unknown}")
        raise _refuse("; ".join(detail))
    checked: dict[str, dict] = {}
    for name in SEALED_INPUT_NAMES:
        dependency = controlled_dependencies[name]
        if not isinstance(dependency, Mapping) or any(
            key not in dependency for key in DEPENDENCY_KEYS
        ):
            raise _refuse(f"{name}: a controlled dependency records its path and sha256")
        if type(dependency["path"]) is not str or not dependency["path"]:
            raise _refuse(f"{name}: the controlled dependency names no path")
        if type(dependency["sha256"]) is not str or _SHA256.fullmatch(dependency["sha256"]) is None:
            raise _refuse(f"{name}: the controlled dependency has no sha256 digest")
        checked[name] = {"path": dependency["path"], "sha256": dependency["sha256"]}
    return checked


def _check_runtime_identity(runtime_identity) -> dict:
    """Check the runtime identity of plan section 2b, field for field."""

    if not isinstance(runtime_identity, Mapping):
        raise _refuse("the runtime identity is not a document")
    missing = [field for field in RUNTIME_IDENTITY_FIELDS if field not in runtime_identity]
    if missing:
        raise _refuse(f"the runtime identity omits {missing}")
    for field in RUNTIME_IDENTITY_FIELDS:
        value = runtime_identity[field]
        if value is None or (type(value) is str and not value):
            raise _refuse(f"the runtime identity records no {field}")
    for field in ("detector_weights_sha256", "camera_intrinsics_sha256"):
        value = runtime_identity[field]
        if type(value) is not str or _SHA256.fullmatch(value) is None:
            raise _refuse(f"the runtime identity records no sha256 digest for {field}")
    return {field: runtime_identity[field] for field in RUNTIME_IDENTITY_FIELDS}


def _check_also_recorded(also_recorded) -> dict:
    """Check the five items the design requires recorded though outside the seventeen."""

    if not isinstance(also_recorded, Mapping):
        raise _refuse("the also-recorded items are not a document")
    declared = set(also_recorded)
    required = set(ALSO_RECORDED_ITEMS)
    if declared != required:
        missing = sorted(required - declared)
        unknown = sorted(declared - required)
        detail = []
        if missing:
            detail.append(f"the bundle does not record {missing}")
        if unknown:
            detail.append(f"the bundle records items outside the five: {unknown}")
        raise _refuse("; ".join(detail))
    checked: dict[str, dict] = {}
    for item in ALSO_RECORDED_ITEMS:
        record = also_recorded[item]
        if not isinstance(record, Mapping):
            raise _refuse(f"{item}: a definition is declared without its evidence")
        missing = [key for key in ALSO_RECORDED_KEYS if key not in record]
        if missing:
            raise _refuse(f"{item}: the record omits {missing}")
        _evidence_references(item, record["input_evidence"])
        if not isinstance(record["startup_readback"], Mapping) or not record["startup_readback"]:
            raise _refuse(f"{item}: the record carries no startup readback")
        if not _valid_value(record["value_or_definition"]) and (
            type(record["value_or_definition"]) is not str or not record["value_or_definition"]
        ):
            raise _refuse(f"{item}: the record carries no value or definition")
        checked[item] = dict(record)
    return checked


def _assert_no_approval_state(document, *, where: str) -> None:
    """Refuse a document that would record an approval state; approval is bound later, to the digest."""

    if isinstance(document, Mapping):
        for key, item in document.items():
            if any(token in key.lower() for token in APPROVAL_TOKENS):
                raise _refuse(
                    f"{where} would record the approval state {key!r}; phase 8 records no approval, "
                    f"the approval is bound to the bundle digest by the promotion step"
                )
            _assert_no_approval_state(item, where=f"{where}.{key}")
    elif isinstance(document, (list, tuple)):
        for index, item in enumerate(document):
            _assert_no_approval_state(item, where=f"{where}[{index}]")


def build_run_status(
    *, status: str, command=None, exit_code=None, failure=None, evidence_produced=()
) -> dict:
    """Render `run-status.json`: `SUCCEEDED` or `FAILED`, audit only and never a checkpoint.

    A successful run records the run's own command, exit code and the evidence it produced. A failed run
    records the first failing phase, its failure code, command and exit code and the evidence already
    produced, exactly as design section 8.2 requires; a failed status without that record, or with a
    command that belongs to the entry rather than to the failure, is a caller bug and raises a plain
    `ValueError` rather than a refusal code.
    """

    if status not in RUN_STATUSES:
        raise ValueError(f"a run status is one of {RUN_STATUSES}, not {status!r}")
    if status == "SUCCEEDED":
        if type(command) is not str or not command:
            raise ValueError("a succeeded run records the command it ran")
        if type(exit_code) is not int or isinstance(exit_code, bool):
            raise ValueError("a succeeded run records its exit code")
        if failure is not None:
            raise ValueError("a succeeded run records no failure")
        first_failing_phase = failure_code = failure_command = failure_exit_code = None
    else:
        if command is not None or exit_code is not None:
            raise ValueError("a failed run records the failing command, not the entry command")
        if not isinstance(failure, Mapping) or set(failure) != set(FAILURE_KEYS):
            raise ValueError(f"a failed run records exactly {list(FAILURE_KEYS)}")
        if type(failure["phase"]) is not str or not failure["phase"]:
            raise ValueError("a failed run records the first failing phase")
        if type(failure["code"]) is not str or not failure["code"]:
            raise ValueError("a failed run records the failure code")
        if type(failure["command"]) is not str or not failure["command"]:
            raise ValueError("a failed run records the failing command")
        if type(failure["exit_code"]) is not int or isinstance(failure["exit_code"], bool):
            raise ValueError("a failed run records the failing exit code")
        first_failing_phase = failure["phase"]
        failure_code = failure["code"]
        failure_command = failure["command"]
        failure_exit_code = failure["exit_code"]
        evidence_produced = failure["evidence_produced"]
    if isinstance(evidence_produced, (str, bytes)) or not isinstance(evidence_produced, Sequence):
        raise ValueError("the evidence already produced is a list of artifact names")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RUN_STATUS_KIND,
        "phase": PHASE,
        "status": status,
        "audit_only": True,
        "checkpoint": False,
        "resume_supported": False,
        "command": command if status == "SUCCEEDED" else failure_command,
        "exit_code": exit_code if status == "SUCCEEDED" else failure_exit_code,
        "first_failing_phase": first_failing_phase,
        "failure_code": failure_code,
        "failure_command": failure_command,
        "failure_exit_code": failure_exit_code,
        "evidence_produced": [str(item) for item in evidence_produced],
    }


def _write(directory: Path, name: str, document) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def assemble_calibration_bundle(
    *,
    status: str = "SUCCEEDED",
    command=None,
    exit_code=None,
    failure=None,
    phase_inputs=None,
    controlled_dependencies=None,
    runtime_identity=None,
    also_recorded=None,
    output_dir=None,
) -> dict:
    """Assemble the run's final documents from the phase inputs, or refuse an incomplete bundle.

    A successful run is assembled from the four phases that own the seventeen parameters, the runtime
    identity and the controlled dependencies; every one of the seventeen has to be there with its
    evidence block, and every dependency with its digest, or the bundle is refused with
    `CAL_BUNDLE_INCOMPLETE` before anything is written. A failed run produces only `run-status.json`:
    it records the first failing phase and the evidence already produced, and never a bundle, because a
    failed run cannot be promoted (design section 8.2).

    Nothing is written unless `output_dir` is given, and then only the three documents of design
    section 8.3 are created there.
    """

    if status == "FAILED":
        run_status = build_run_status(status=status, failure=failure)
        _assert_no_approval_state(run_status, where="run-status.json")
        if output_dir is not None:
            _write(Path(output_dir), RUN_STATUS_NAME, run_status)
        return {"run_status": run_status}
    if status != "SUCCEEDED":
        raise ValueError(f"a run status is one of {RUN_STATUSES}, not {status!r}")
    if failure is not None:
        raise ValueError("a succeeded run records no failure")

    parameters = _collect_parameters(phase_inputs)
    dependencies = _check_dependencies(controlled_dependencies)
    identity = _check_runtime_identity(runtime_identity)
    recorded = _check_also_recorded(also_recorded)

    names = list(PARAMETERS)
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "parameter_names": names,
        "parameters": parameters,
        "also_recorded": recorded,
        "runtime_identity": identity,
        "controlled_dependencies": dependencies,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "phase": PHASE,
        "command": command,
        "artifacts": list(ARTIFACT_NAMES),
        "controlled_dependencies": dependencies,
        "runtime_identity": identity,
        "parameter_names": names,
        "also_recorded": recorded,
    }
    run_status = build_run_status(
        status="SUCCEEDED",
        command=command,
        exit_code=exit_code,
        evidence_produced=ARTIFACT_NAMES,
    )
    _assert_no_approval_state(bundle, where="head-search-calibration-bundle.json")
    _assert_no_approval_state(manifest, where=MANIFEST_NAME)
    _assert_no_approval_state(run_status, where=RUN_STATUS_NAME)
    if output_dir is not None:
        directory = Path(output_dir)
        _write(directory, BUNDLE_NAME, bundle)
        _write(directory, MANIFEST_NAME, manifest)
        _write(directory, RUN_STATUS_NAME, run_status)
    return {"bundle": bundle, "manifest": manifest, "run_status": run_status}
