"""Refusal codes, approved values, the observed qualification values and the readback document."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import time

from so101_demo.act.head_search.binding import _CAMERA_MEASURED, _MEASURED
from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search.measured_readback import (
    CONSTRUCTED_OBSERVATION,
    MEASURED_PARAMETERS,
    NOT_OBSERVABLE,
    observe_measured_readbacks,
)
from so101_demo.act.head_search.ownership import APPROVED_VALUE_COUNT
from so101_demo.act.head_search.restarts.contracts import (
    CAMERA_INFO_TOPIC,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1


#: refuses any other kind by name, so the two constants are deliberately spelled identically
KIND = "head_search_qualification_runtime_readback"


PHASE = "qualification_readback"


OPERATION = "QUALIFICATION_RUN"


ARTIFACT = "qualification-runtime-readback.json"


TEARDOWN_ARTIFACT = "teardown-proof.json"


STDOUT_LOG = "stdout.log"


STDERR_LOG = "stderr.log"


#: this phase's own session identity: the simulation session, the runner node and the detector's identity
SESSION_ID = "head-search-qualification-readback"


#: the live run found this: ``Node("/head_search_qualification_readback")`` is refused by rclpy itself
RUNNER_NODE = "head_search_qualification_readback"


RUNNER_GRAPH_NODE = f"/{RUNNER_NODE}"


BASE_FRAME = "base"


CAMERA_FRAME = "head_camera_frame"


IMAGE_TOPIC = "/head_camera/color"


#: the four observations this module records, beside the measured readback's own vocabulary
RUNNING_STACK_OBSERVATION = "running_stack"


LOADED_DETECTOR_OBSERVATION = "loaded_detector"


READBACK_INPUTS_INCOMPLETE = "READBACK_INPUTS_INCOMPLETE"


READBACK_RUN_ROOT_EXISTS = "READBACK_RUN_ROOT_EXISTS"


READBACK_OWNERSHIP_REFUSED = "READBACK_OWNERSHIP_REFUSED"


READBACK_OWNERSHIP_MISMATCH = "READBACK_OWNERSHIP_MISMATCH"


READBACK_RUNTIME_UNVERIFIED = "READBACK_RUNTIME_UNVERIFIED"


READBACK_VALUES_INCOMPLETE = "READBACK_VALUES_INCOMPLETE"


READBACK_BUNDLE_MISMATCH = "READBACK_BUNDLE_MISMATCH"


READBACK_VALUE_MISMATCH = "READBACK_VALUE_MISMATCH"


READBACK_CAMERA_NOT_OBSERVED = "READBACK_CAMERA_NOT_OBSERVED"


READBACK_PROBE_FAILED = "READBACK_PROBE_FAILED"


READBACK_FOREIGN_OWNER_ACTIVE = "READBACK_FOREIGN_OWNER_ACTIVE"


READBACK_STACK_START_FAILED = "READBACK_STACK_START_FAILED"


READBACK_COMPONENT_UNBUILDABLE = "READBACK_COMPONENT_UNBUILDABLE"


READBACK_DETECTOR_FAILED = "READBACK_DETECTOR_FAILED"


READBACK_TEARDOWN_UNPROVEN = "READBACK_TEARDOWN_UNPROVEN"


READBACK_GPU_NOT_RELEASED = "READBACK_GPU_NOT_RELEASED"


REFUSAL_CODES = (
    READBACK_INPUTS_INCOMPLETE,
    READBACK_RUN_ROOT_EXISTS,
    READBACK_OWNERSHIP_REFUSED,
    READBACK_OWNERSHIP_MISMATCH,
    READBACK_RUNTIME_UNVERIFIED,
    READBACK_VALUES_INCOMPLETE,
    READBACK_BUNDLE_MISMATCH,
    READBACK_VALUE_MISMATCH,
    READBACK_CAMERA_NOT_OBSERVED,
    READBACK_PROBE_FAILED,
    READBACK_FOREIGN_OWNER_ACTIVE,
    READBACK_STACK_START_FAILED,
    READBACK_COMPONENT_UNBUILDABLE,
    READBACK_DETECTOR_FAILED,
    READBACK_TEARDOWN_UNPROVEN,
    READBACK_GPU_NOT_RELEASED,
)


#: the four teardown facts that must all be true, and the GPU hold beside them
TEARDOWN_FACTS = (
    "previous_stack_stopped",
    "controller_owner_stopped",
    "children_exited",
    "graph_clear",
)


#: the camera measurements and the live source each one is taken from, as the pick-place calibration contract names them
CAMERA_SOURCES = {
    "head_intrinsics_px": f"{CAMERA_INFO_TOPIC} K, the running camera plugin's own calibration",
    "head_translation_m": f"{BASE_FRAME} -> {CAMERA_FRAME} translation, the running description's TF",
    "head_rpy_rad": f"{BASE_FRAME} -> {CAMERA_FRAME} rotation, ZYX decomposition",
    "yaw_zero_bearing_rad": (
        f"{BASE_FRAME} -> {CAMERA_FRAME} rotation: wrap_pi(atan2(a_y, a_x)) of the optical forward axis "
        f"a = R * [0, 0, 1]"
    ),
}


#: ``PASS`` only when every one of the seventeen was read back and matched; anything else refuses
PASS = "PASS"


class QualificationReadbackRefused(CalibrationInputsRefused):
    """A readback refusal, carrying the exact code the run records and stops on."""


def _refuse(code: str, detail: str) -> QualificationReadbackRefused:
    return QualificationReadbackRefused(code, detail)


def _digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _utc_now(now=time.gmtime) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", now())


def _write(root: Path, name: str, document: Mapping) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    pending = root / f".{name}.pending"
    pending.write_text(
        json.dumps(dict(document), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(pending, target)
    return target


def _same_number(left, right) -> bool:
    """Exact equality of two recorded values: the same JSON number, not merely the same quantity.

    The same rule ``head_search_calibration_readback`` applies to the selected perception values, and for
    the same reason: a component that holds ``0.1 + 0.2`` where the approval recorded ``0.3`` is running
    another value, and the canonical encodings are what tell the two apart.
    """

    if type(left) not in (int, float) or type(right) not in (int, float):
        return False
    try:
        return json.dumps(left, allow_nan=False) == json.dumps(right, allow_nan=False)
    except ValueError:
        return False


def _same_value(left, right) -> bool:
    """Exact equality for a scalar or a vector of scalars; anything else is never the same value."""

    if isinstance(left, Sequence) and not isinstance(left, (str, bytes)):
        if not isinstance(right, Sequence) or isinstance(right, (str, bytes)):
            return False
        return len(left) == len(right) and all(
            _same_number(one, other) for one, other in zip(left, right)
        )
    return _same_number(left, right)


def bare(value):
    """`{name: {value: v}}` and `{name: v}` are the same declaration; this is the bare value."""

    if isinstance(value, Mapping) and "value" in value:
        return value["value"]
    return value


def approved_values(*, production_config: Mapping, approved_bundle: Mapping) -> dict:
    """The seventeen approved values, and the digest the frozen config and the bundle both carry.

    The promoted config is the promotion of record: its ``values`` block is what the running components
    are constructed with. The approved bundle is the declaration the promotion came from, and it must
    agree with it value by value - a bundle whose parameters digest to something else is
    ``READBACK_BUNDLE_MISMATCH``, because a readback that verified a promotion nobody approved has proven
    nothing about the approved values.
    """

    config = production_config if isinstance(production_config, Mapping) else {}
    declared = config.get("values")
    if not isinstance(declared, Mapping):
        raise _refuse(
            READBACK_VALUES_INCOMPLETE,
            "the promoted production config declares no values block, so there is nothing to read back",
        )
    absent = [name for name in _MEASURED if name not in declared]
    if absent or len(declared) != APPROVED_VALUE_COUNT:
        raise _refuse(
            READBACK_VALUES_INCOMPLETE,
            f"the promoted production config carries {len(declared)} values for "
            f"{APPROVED_VALUE_COUNT} approved names; not declared: {absent}",
        )
    values = {name: declared[name] for name in _MEASURED}
    parameters = approved_bundle.get("parameters") if isinstance(approved_bundle, Mapping) else None
    if not isinstance(parameters, Mapping):
        raise _refuse(
            READBACK_BUNDLE_MISMATCH,
            "the approved calibration bundle declares no parameters block, so the promotion cannot be "
            "checked against the approval it claims",
        )
    approved = {name: bare(parameters[name]) for name in _MEASURED if name in parameters}
    if len(approved) != APPROVED_VALUE_COUNT:
        raise _refuse(
            READBACK_BUNDLE_MISMATCH,
            f"the approved bundle carries {len(approved)} of {APPROVED_VALUE_COUNT} approved values",
        )
    if canonical_sha256(approved) != canonical_sha256(values):
        differing = sorted(
            name for name in _MEASURED if not _same_value(approved[name], values[name])
        )
        raise _refuse(
            READBACK_BUNDLE_MISMATCH,
            f"the approved bundle's values digest to {canonical_sha256(approved)} but the promoted "
            f"config's digest to {canonical_sha256(values)}; they differ in {differing}",
        )
    return {"values": values, "values_sha256": canonical_sha256(values), "approved": approved}


def _controller_observations(*, configuration: Mapping, controller_factory=None) -> dict:
    """The twelve values the installed search controller's own code reads, off the constructed controller.

    ``horizontal_fov_rad`` and ``lock_valid_neck_rad`` are read off the bounded stop plan the controller
    builds with them, because that plan is the object the search actually walks; the other ten are the
    configuration keys the controller validates and ``tick`` applies. A controller that cannot be
    constructed with the recorded values is ``READBACK_COMPONENT_UNBUILDABLE``: a value no component could
    be asked about is not an observation.
    """

    from so101_demo.act.search import HeadSearchController

    factory = controller_factory or HeadSearchController
    try:
        controller = factory(dict(configuration))
    except Exception as error:  # noqa: BLE001 - an unbuildable component is a refusal, never a record
        raise _refuse(
            READBACK_COMPONENT_UNBUILDABLE,
            f"the installed search controller {factory!r} could not be constructed with the promoted "
            f"configuration: {type(error).__name__}: {error}",
        ) from error
    component = "so101_demo.act.search.HeadSearchController"
    observations = {
        name: {
            "component": component,
            "source": f"HeadSearchController(...).config[{name!r}]",
            "value": controller.config[name],
        }
        for name in (
            "coarse_step_rad",
            "search_timeout_s",
            "center_deadband_px",
            "vertical_bounds_px",
            "max_fine_corrections",
            "max_fine_total_rad",
            "max_age_s",
            "max_skew_s",
            "min_confidence",
            "min_area_px2",
        )
    }
    plan = getattr(controller, "plan", None)
    if plan is None:
        raise _refuse(
            READBACK_COMPONENT_UNBUILDABLE,
            "the constructed search controller built no bounded stop plan, so the field of view and the "
            "safe neck interval it walks have no consumer to be read off",
        )
    observations["horizontal_fov_rad"] = {
        "component": component,
        "source": "HeadSearchController(...).plan.horizontal_fov_rad",
        "value": float(plan.horizontal_fov_rad),
    }
    observations["lock_valid_neck_rad"] = {
        "component": component,
        "source": "HeadSearchController(...).plan.safe_interval_rad",
        "value": [float(bound) for bound in plan.safe_interval_rad],
    }
    return observations


def _detector_observations(*, detector) -> dict:
    """The two perception values the loaded detector's own ``detect`` applies.

    The detector is the one this readback builds from the frozen weights (or the stand-in a test puts in
    its place); a detector that holds no such attribute cannot be the production detector, and that is a
    refusal rather than a record with a missing source.
    """

    component = f"{type(detector).__module__}.{type(detector).__qualname__}"
    observations = {}
    for name, attribute in (
        ("tracking_iou", "tracking_iou"),
        ("min_bbox_aspect", "min_bbox_aspect"),
    ):
        if not hasattr(detector, attribute):
            raise _refuse(
                READBACK_DETECTOR_FAILED,
                f"the loaded detector {component} holds no {attribute}, so {name} has no consumer the "
                f"readback can query",
            )
        observations[name] = {
            "component": component,
            "source": f"HeadRgbDetector(...).{attribute}",
            "value": float(getattr(detector, attribute)),
        }
    return observations


def observe_qualification_values(
    *,
    values: Mapping,
    configuration: Mapping,
    detector,
    controller_factory=None,
    neck_port_factory=None,
    stop_criterion_factory=None,
) -> dict:
    """Observe all seventeen approved values off the production components that consume them.

    The eleven measured values go through ``head_search_measured_readback.observe_measured_readbacks`` -
    the capability wired into the calibration run - because those are exactly the values the
    neck port, the stop criterion and the eight controller keys were read back for; the six declared ones
    are read off the same constructed controller's plan and configuration, and the two the detector applies
    off the loaded detector. The result is one record per value, in the order ``head_search_binding._MEASURED``
    fixes, each carrying the observed value, its component, its source, the configuration it was built with
    and whether it matches the approved value.
    """

    if not isinstance(values, Mapping) or not values:
        raise _refuse(READBACK_VALUES_INCOMPLETE, "no approved values were presented to read back")
    measured = {name: values[name] for name in MEASURED_PARAMETERS if name in values}
    readbacks = observe_measured_readbacks(
        values=measured,
        configuration=configuration,
        controller_factory=controller_factory,
        neck_port_factory=neck_port_factory,
        stop_criterion_factory=stop_criterion_factory,
    )
    controller = _controller_observations(
        configuration=configuration, controller_factory=controller_factory
    )
    detected = _detector_observations(detector=detector)

    records: dict[str, dict] = {}
    for name in _MEASURED:
        if name not in values:
            continue
        approved = values[name]
        if name in readbacks:
            readback = readbacks[name]
            observed = readback.get("observed_value")
            record = {
                "observed_value": observed,
                "observation": readback.get("observation"),
                "component": readback.get("component"),
                "source": readback.get("source"),
                "configuration": readback.get("configuration"),
                "configuration_sha256": readback.get("configuration_sha256"),
                "verified": readback.get("verified"),
            }
            for extra in ("also_observed", "behavioural", "harness", "reason"):
                if readback.get(extra) is not None:
                    record[extra] = readback[extra]
            if readback.get("observation") == NOT_OBSERVABLE:
                raise _refuse(
                    READBACK_COMPONENT_UNBUILDABLE,
                    f"{name} could not be read back off the production component that consumes it: "
                    f"{readback.get('reason')}",
                )
        elif name in controller:
            observation = controller[name]
            record = {
                "observed_value": observation["value"],
                "observation": CONSTRUCTED_OBSERVATION,
                "component": observation["component"],
                "source": observation["source"],
                "configuration": dict(configuration),
                "configuration_sha256": canonical_sha256(configuration),
                "verified": None,
            }
        elif name in detected:
            observation = detected[name]
            record = {
                "observed_value": observation["value"],
                "observation": LOADED_DETECTOR_OBSERVATION,
                "component": observation["component"],
                "source": observation["source"],
                "configuration": dict(configuration),
                "configuration_sha256": canonical_sha256(configuration),
                "verified": None,
            }
        else:
            raise _refuse(
                READBACK_COMPONENT_UNBUILDABLE,
                f"{name} has no production component this readback can query, so it was not observed",
            )
        record["value"] = approved
        record["approved_value"] = approved
        record["matches_approved"] = _same_value(record["observed_value"], approved)
        records[name] = record
    absent = [name for name in _MEASURED if name not in records]
    if absent:  # pragma: no cover - every branch above either records or refuses
        raise _refuse(
            READBACK_VALUES_INCOMPLETE,
            f"{len(absent)} of {APPROVED_VALUE_COUNT} approved values were not observed: {absent}",
        )
    return records


def camera_measurement_records(*, live: Mapping, reference: Mapping | None = None) -> dict:
    """The four camera measurements, as the running stack published them, or honestly not observed.

    ``live`` is the observation taken from the running stack, one entry per measurement with the value the
    live source reported and the numbers it was derived from. A measurement the stack did not publish is
    recorded as ``not_observable`` with the reason, and its ``value`` stays null: the approved number is
    never restated as if it had been seen. When ``reference`` carries an approved value for a measurement
    the live observation is compared with it, exactly like a value; without one the comparison is recorded
    as null with the reason, because there is nothing under this run root to compare against.
    """

    records: dict[str, dict] = {}
    for name in _CAMERA_MEASURED:
        entry = live.get(name) if isinstance(live, Mapping) else None
        entry = entry if isinstance(entry, Mapping) else {}
        observed = entry.get("value")
        approved = (
            bare(reference[name]) if isinstance(reference, Mapping) and name in reference else None
        )
        record = {
            "observation": entry.get("observation") or NOT_OBSERVABLE,
            "component": entry.get("component"),
            "source": entry.get("source") or CAMERA_SOURCES[name],
            "observed_value": observed,
            "value": observed,
            "derivation": entry.get("derivation"),
            "raw": entry.get("raw"),
            "reference_value": approved,
            "reference": entry.get("reference"),
        }
        if observed is None:
            record["matches_approved"] = None
            record["verified"] = False
            record["reason"] = entry.get("reason") or (
                f"the running stack published no {name} this readback could observe"
            )
        elif approved is None:
            record["matches_approved"] = None
            record["verified"] = None
            record["reason"] = (
                "no approved reference for this camera measurement was presented, so the live "
                "observation is recorded as measured rather than compared"
            )
        else:
            record["matches_approved"] = _same_value(observed, approved)
            record["verified"] = bool(record["matches_approved"])
            if not record["matches_approved"]:
                record["reason"] = (
                    f"the running stack reported {observed!r} where the approved measurement is "
                    f"{approved!r}"
                )
        records[name] = record
    return records


def readback_document(
    *,
    run_root,
    evidence_root,
    runtime: Mapping,
    approved: Mapping,
    observations: Mapping,
    camera_measurements: Mapping,
    detector: Mapping,
    ownership: Mapping,
    approved_bundle_path,
    production_config_path,
    elapsed_s: float,
    taken_at_utc: str,
    command: str = "",
) -> dict:
    """Assemble the document the aggregate gate consumes, and refuse the run when it may not be published.

    Every rule the gate applies is applied here first, and one more: an observed value that differs from
    the approved one is ``READBACK_VALUE_MISMATCH`` - a hard failure, not a warning - and the record keeps
    the observed value so the refusal names both numbers. The document is only assembled for a readback
    whose every value was observed and matched.
    """

    records = dict(observations)
    absent = [name for name in _MEASURED if name not in records]
    if absent:
        raise _refuse(
            READBACK_VALUES_INCOMPLETE,
            f"{len(absent)} of {APPROVED_VALUE_COUNT} approved values were not read back: {absent}",
        )
    mismatched = sorted(name for name in _MEASURED if not records[name].get("matches_approved"))
    if mismatched:
        detail = "; ".join(
            f"{name}: observed {records[name].get('observed_value')!r}, approved "
            f"{records[name].get('approved_value')!r}"
            for name in mismatched
        )
        raise _refuse(
            READBACK_VALUE_MISMATCH,
            f"{len(mismatched)} of {APPROVED_VALUE_COUNT} values differ from the approved ones, so this "
            f"system is not the approved one: {detail}",
        )
    read_back = {name: bare(records[name]) for name in _MEASURED}
    digest = canonical_sha256(read_back)
    declared = runtime.get("values_sha256") if isinstance(runtime, Mapping) else None
    if digest != declared:
        raise _refuse(
            READBACK_VALUE_MISMATCH,
            f"the read-back values digest to {digest}, but the frozen promoted config carries {declared}",
        )
    if not isinstance(camera_measurements, Mapping) or any(
        name not in camera_measurements for name in _CAMERA_MEASURED
    ):
        raise _refuse(
            READBACK_CAMERA_NOT_OBSERVED,
            f"the readback carries no record for the four camera measurements {list(_CAMERA_MEASURED)}",
        )
    if not isinstance(detector, Mapping) or int(detector.get("count", 0)) != 1:
        raise _refuse(
            READBACK_DETECTOR_FAILED,
            f"the readback must show exactly one detector instance, saw "
            f"{detector.get('count') if isinstance(detector, Mapping) else detector!r}",
        )
    if str(detector.get("device")) != "cuda" or detector.get("allow_cpu_fallback") is not False:
        raise _refuse(
            READBACK_DETECTOR_FAILED,
            f"the readback detector is {detector.get('device')!r} with "
            f"allow_cpu_fallback={detector.get('allow_cpu_fallback')!r}; this gate is CUDA-only",
        )
    declared_weight = (
        runtime.get("weight_sha256_declared") if isinstance(runtime, Mapping) else None
    )
    observed_weight = detector.get("weights_sha256")
    if observed_weight != declared_weight:
        raise _refuse(
            READBACK_DETECTOR_FAILED,
            f"the loaded detector's weights digest to {observed_weight!r}, the frozen config declares "
            f"{declared_weight!r}",
        )

    provenance = {
        "run_root": str(run_root),
        "evidence_root": str(evidence_root),
        "final_run": str(runtime.get("final_run", "")),
        "source_commit": str(runtime.get("source_commit", "")),
        "production_config": str(production_config_path),
        "production_config_sha256": runtime.get("production_config_sha256"),
        "values_sha256": digest,
        "weight_path": runtime.get("weight_path"),
        "weight_sha256": declared_weight,
        "elapsed_s": elapsed_s,
        "taken_at_utc": taken_at_utc,
        "ownership_receipt": ownership.get("path"),
        "ownership_receipt_sha256": ownership.get("sha256"),
        "approved_bundle": str(approved_bundle_path),
    }
    for name, record in records.items():
        record["provenance"] = dict(provenance)
    for name, record in camera_measurements.items():
        record.setdefault("provenance", dict(provenance))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "operation": OPERATION,
        "status": PASS,
        "command": command,
        "taken_at_utc": taken_at_utc,
        "elapsed_s": elapsed_s,
        "run_root": str(run_root),
        "evidence_root": str(evidence_root),
        "final_run": str(runtime.get("final_run", "")),
        "source_commit": str(runtime.get("source_commit", "")),
        "production_config": str(production_config_path),
        "production_config_sha256": runtime.get("production_config_sha256"),
        "approved_bundle": str(approved_bundle_path),
        "approved_bundle_sha256": _digest(approved_bundle_path)
        if Path(approved_bundle_path).is_file()
        else None,
        "approved_values_sha256": approved.get("values_sha256"),
        "values_count": len(read_back),
        "values_sha256": digest,
        "values": {name: records[name] for name in _MEASURED},
        "camera_measurements": {name: camera_measurements[name] for name in _CAMERA_MEASURED},
        "detector": dict(detector),
        "device": detector.get("device"),
        "cuda_device": detector.get("cuda_device"),
        "cuda_used": True,
        "allow_cpu_fallback": False,
        "weight_path": runtime.get("weight_path"),
        "weight_sha256_declared": declared_weight,
        "weight_sha256_observed": detector.get("weights_sha256"),
        "provenance": provenance,
        "observation_definitions": {
            "constructed_production_component": (
                "the installed production component that consumes the value was constructed with the "
                "promoted configuration while the qualification stack ran, and the attribute its own code "
                "reads was recorded"
            ),
            LOADED_DETECTOR_OBSERVATION: (
                "the value was read off the production detector this readback loaded from the frozen "
                "weights - the only CUDA detector instance in play"
            ),
            RUNNING_STACK_OBSERVATION: (
                "the value was read off a topic the running qualification stack itself publishes"
            ),
            NOT_OBSERVABLE: (
                "the running stack did not publish what this measurement needs; the reason is recorded "
                "and no value is claimed"
            ),
        },
    }
