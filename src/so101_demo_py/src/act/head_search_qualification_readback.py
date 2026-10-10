"""The during-qualification readback: the seventeen approved values and the four camera measurements.

Task 14's `approved_values_readback` gate (``head_search_aggregate``) consumes one document - the readback
of a qualification run - and refuses unless all seventeen approved values and the four camera measurements
were read back **under that qualification run root**, unless the readback's own values digest is the digest
the frozen promoted config carries, and unless exactly one CUDA detector was in play. Nothing produced
such a document: the values were proven once, inside the calibration run, by
``head_search_measured_readback`` (ledger HS-312), but the qualification itself never queried a running
system for them. This module is that producer.

What it observes, and from which consumer
-----------------------------------------

Every one of the seventeen values is read off the **production component that consumes it**, while the one
production composition is up, and each record names that component, the expression the value was read from,
the configuration the component was constructed with and the digest of it:

===================================  ==========================================================
value                                the consumer it is read from
===================================  ==========================================================
``horizontal_fov_rad``               ``HeadSearchController(...).plan.horizontal_fov_rad``
``lock_valid_neck_rad``              ``HeadSearchController(...).plan.safe_interval_rad``
``coarse_step_rad``,                  ``HeadSearchController(...).config[...]`` - and the eleven
``search_timeout_s``,                 measured values also through
``center_deadband_px``,               ``head_search_measured_readback.observe_measured_readbacks``,
``vertical_bounds_px``,               which adds the neck port's and the stop criterion's own
``max_fine_corrections``,             attributes plus the three behavioural probes
``max_fine_total_rad``,               (deadline, freshness, skew) at the exact float boundary
``max_age_s``, ``max_skew_s``,        each component applies
``min_confidence``, ``min_area_px2``
``submit_lead_s``, ``stop_latency_s`` ``RosNeckSearchPort`` attributes (via the same readback)
``stop_velocity_rad_s``               ``RosControllerPort`` stop criterion attribute (ditto)
``tracking_iou``,                     the loaded ``HeadRgbDetector`` - the one CUDA instance this
``min_bbox_aspect``                   readback builds from the frozen weights
===================================  ==========================================================

The four camera measurements are observed **live from the running stack**, exactly as the Task 8
measurement contract defines them (``config/act/pick-place-calibration-measurement-contract.json``):
``head_intrinsics_px`` from the ``/head_camera/camera_info`` the running camera plugin publishes,
``head_translation_m`` and ``head_rpy_rad`` from the ``base -> head_camera_frame`` transform the running
description publishes, and ``yaw_zero_bearing_rad`` from the bearing of that rotation's optical forward
axis. A camera measurement that the running stack does not publish is recorded as ``not_observable`` with
the reason that stopped the observation - never with the approved number restated as if it had been seen.

The documents this producer needs
---------------------------------

It is handed the same frozen artefacts the qualifier declares: the promoted production config (whose
``values`` block is the promotion of record), the approved calibration bundle (whose parameters must agree
with it, value by value, or the readback refuses with ``READBACK_BUNDLE_MISMATCH``), the frozen runtime
identity, the sealed geometry, the scene, the URDF, the MuJoCo plugin configuration, the controller
configuration, the selected weights and, through the controller configuration, the dead-man directory. It takes Task 14 Step 1's exclusive-ownership
receipt, refuses unless the receipt guards exactly this run root, and starts **one** stack - the same
``RestartStack`` the production smoke and the anchor restarts own - through the restart module's own
helpers, so the qualification cannot drift into a second definition of "the stack".

The run root
------------

The gate compares the readback's ``run_root`` with the qualification run root it aggregates, character for
character, and refuses a readback taken for another run (``QUAL_AGGREGATE_VALUES_NOT_DURING_QUALIFICATION``).
The aggregate, in turn, claims its run root exclusively and refuses to resume one that exists. The
readback therefore declares the qualification run root it is taken **for** - the root the Step 1 receipt
guards, the root the aggregate claims afterwards - and writes its own evidence (this document, the teardown
proof, stdout and stderr) under the evidence root the run was given. Both roots are recorded, so a reader
can see which qualification the readback belongs to and where it was physically taken.

What refuses, and what is recorded instead
------------------------------------------

Four things are hard failures, never warnings: a stack that does not start (``READBACK_STACK_START_FAILED``),
a production component that cannot be built (``READBACK_COMPONENT_UNBUILDABLE`` /
``READBACK_DETECTOR_FAILED``), an observed value that differs from the approved one
(``READBACK_VALUE_MISMATCH`` - the observed value is recorded beside the approved one, so the refusal names
both), and a teardown that cannot be proven (``READBACK_TEARDOWN_UNPROVEN`` / ``READBACK_GPU_NOT_RELEASED``).
A camera measurement the running stack does not publish is not a failure of the run: it is recorded as
``not_observable`` with the reason, because "could not look" is evidence about this run and inventing the
number would not be.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_binding import _CAMERA_MEASURED, _MEASURED
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_measured_readback import (
    CONSTRUCTED_OBSERVATION,
    MEASURED_PARAMETERS,
    NOT_OBSERVABLE,
    observe_measured_readbacks,
)
from so101_demo.act.head_search_ownership import APPROVED_VALUE_COUNT
from so101_demo.act.head_search_restarts import (
    CAMERA_INFO_TOPIC,
    CAMERA_PROBE_S,
    JOINT_TOPIC,
    RESTART_OWNERSHIP_MISMATCH,
    RESTART_OWNERSHIP_REFUSED,
    RESTART_RUNTIME_UNVERIFIED,
    probe_owners,
    read_ownership_receipt,
    require_runtime_of_record,
    stack_environment,
    teardown_proof,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
#: the aggregate's own declaration of this artefact (``head_search_aggregate.READBACK_KIND``); the gate
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
#: the runtime name rclpy accepts (a node name is not a graph name) and the graph name the probes read;
#: the live run found this: ``Node("/head_search_qualification_readback")`` is refused by rclpy itself
RUNNER_NODE = "head_search_qualification_readback"
RUNNER_GRAPH_NODE = f"/{RUNNER_NODE}"
#: the frame the camera measurements are taken in: the Task 8 contract's ``base -> head_camera_frame``
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

#: the camera measurements and the live source each one is taken from, as the Task 8 contract names them
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
    the capability ledger HS-312 wired into the calibration run - because those are exactly the values the
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


# --- the live observation ------------------------------------------------------------------------------


def _stamp_s(message) -> float:
    return float(message.header.stamp.sec) + float(message.header.stamp.nanosec) * 1e-9


def _zyx_from_quaternion(quaternion) -> list[float]:
    """The Task 8 contract's fixed decomposition: ZYX, in (-pi, pi]."""

    x, y, z, w = (float(value) for value in quaternion)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)
    sinp = 2.0 * (w * y - z * x)
    pitch = math.copysign(math.pi / 2.0, sinp) if abs(sinp) >= 1.0 else math.asin(sinp)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return [roll, pitch, yaw]


def _wrap_pi(angle: float) -> float:
    wrapped = math.fmod(angle + math.pi, 2.0 * math.pi)
    if wrapped <= 0.0:
        wrapped += 2.0 * math.pi
    return wrapped - math.pi


def _camera_measurements_from_live(*, infos, frames, transform, joints) -> dict:
    """The four camera measurements, derived from what the running stack published.

    ``transform`` is the ``base -> head_camera_frame`` sample the running description's TF served, or the
    reason it could not be looked up. Nothing is defaulted: a source that published nothing yields
    ``not_observable`` with that reason and a null value.
    """

    from statistics import median

    live: dict[str, dict] = {}
    if infos:
        rows = [
            [float(row["k"][0]), float(row["k"][4]), float(row["k"][2]), float(row["k"][5])]
            for row in infos
            if isinstance(row.get("k"), (list, tuple)) and len(row["k"]) >= 6
        ]
        if rows:
            value = [float(median([row[index] for row in rows])) for index in range(4)]
            live["head_intrinsics_px"] = {
                "value": value,
                "observation": RUNNING_STACK_OBSERVATION,
                "component": f"the running camera plugin, {CAMERA_INFO_TOPIC}",
                "source": CAMERA_SOURCES["head_intrinsics_px"],
                "derivation": "per-component median of [K00, K11, K02, K12] over the valid frames",
                "raw": {
                    "frames": len(rows),
                    "width": rows and infos[-1].get("width"),
                    "height": rows and infos[-1].get("height"),
                    "samples": rows[:8],
                    "frame_id": infos[-1].get("frame_id"),
                },
            }
        else:
            live["head_intrinsics_px"] = {
                "value": None,
                "observation": NOT_OBSERVABLE,
                "reason": f"{CAMERA_INFO_TOPIC} published no distortion-free K this readback could read",
            }
    else:
        live["head_intrinsics_px"] = {
            "value": None,
            "observation": NOT_OBSERVABLE,
            "reason": f"the running stack published no {CAMERA_INFO_TOPIC} within {CAMERA_PROBE_S} s",
        }

    if frames and not infos:
        live["head_intrinsics_px"]["reason"] = (
            f"the running stack published {len(frames)} {IMAGE_TOPIC} frames but no "
            f"{CAMERA_INFO_TOPIC}, so the intrinsics were not observed"
        )
    neck = [row["position_rad"] for row in joints if row.get("name") == "neck_yaw_joint"]
    context = {
        "camera_frames": len(frames),
        "camera_info_frames": len(infos),
        "neck_yaw_rad": neck[-1] if neck else None,
        "tf_sample": transform,
    }
    if not isinstance(transform, Mapping) or transform.get("error"):
        reason = (
            transform.get("error")
            if isinstance(transform, Mapping)
            else f"no {BASE_FRAME} -> {CAMERA_FRAME} transform was looked up"
        )
        for name in ("head_translation_m", "head_rpy_rad", "yaw_zero_bearing_rad"):
            live[name] = {
                "value": None,
                "observation": NOT_OBSERVABLE,
                "source": CAMERA_SOURCES[name],
                "reason": f"the running description served no {BASE_FRAME} -> {CAMERA_FRAME} transform: "
                f"{reason}",
                "raw": context,
            }
        return live
    translation = [float(value) for value in transform["translation_m"]]
    quaternion = [float(value) for value in transform["quaternion_xyzw"]]
    rpy = _zyx_from_quaternion(quaternion)
    x, y, z, w = quaternion
    forward = [
        2.0 * (x * z + w * y),
        2.0 * (y * z - w * x),
        1.0 - 2.0 * (x * x + y * y),
    ]
    bearing = _wrap_pi(math.atan2(forward[1], forward[0]))
    live["head_translation_m"] = {
        "value": translation,
        "observation": RUNNING_STACK_OBSERVATION,
        "component": f"the running robot description's TF, {BASE_FRAME} -> {CAMERA_FRAME}",
        "source": CAMERA_SOURCES["head_translation_m"],
        "derivation": "the transform's translation, in metres",
        "raw": {**context, "quaternion_xyzw": quaternion},
    }
    live["head_rpy_rad"] = {
        "value": rpy,
        "observation": RUNNING_STACK_OBSERVATION,
        "component": f"the running robot description's TF, {BASE_FRAME} -> {CAMERA_FRAME}",
        "source": CAMERA_SOURCES["head_rpy_rad"],
        "derivation": "ZYX decomposition of the transform's normalised quaternion, wrapped to (-pi, pi]",
        "raw": {**context, "quaternion_xyzw": quaternion},
    }
    live["yaw_zero_bearing_rad"] = {
        "value": bearing,
        "observation": RUNNING_STACK_OBSERVATION,
        "component": f"the running robot description's TF, {BASE_FRAME} -> {CAMERA_FRAME}",
        "source": CAMERA_SOURCES["yaw_zero_bearing_rad"],
        "derivation": "wrap_pi(atan2(a_y, a_x)) with a = R * [0, 0, 1] the optical forward axis",
        "raw": {**context, "forward_axis": forward},
    }
    return live


def prepare_deadman_directory(controller_config_path) -> str:
    """The private dead-man directory the sealed controllers file declares for the neck, created.

    The neck controller refuses to activate without it (design section 1.4), so the readback creates it
    (mode 0700, owned by this process) before the stack starts. An undeclared directory, or one whose
    socket path would exceed the AF_UNIX bound, is a refusal, never a default.
    """

    from so101_demo.adapters.act.head_neck_owner import HeadNeckOwner
    from so101_demo.adapters.act.head_neck_owner_build import deadman_directory_from_controllers

    try:
        directory = HeadNeckOwner.ensure_directory(deadman_directory_from_controllers(controller_config_path))
    except Exception as error:  # noqa: BLE001 - an undeclared directory is a refusal, not a default
        raise _refuse(
            READBACK_PROBE_FAILED,
            f"the controller configuration declares no usable dead-man directory: "
            f"{type(error).__name__}: {error}",
        ) from error
    if len(os.fsencode(os.path.join(directory, "neck-18446744073709551615.sock"))) > 107:
        raise _refuse(
            READBACK_PROBE_FAILED,
            f"the AF_UNIX dead-man sockets under {directory} exceed the 107-byte bound",
        )
    return str(directory)


def run_readback_observation(
    *,
    run_root=None,
    evidence_root,
    workdir,
    production: Mapping,
    seal: Mapping,
    anchor: str,
    production_config_path,
    urdf_path,
    scene_path,
    plugin_config_path,
    controller_config_path,
    weights_path,
    device: str = "cuda",
    runtime: Mapping | None = None,
    values: Mapping | None = None,
    stdout=None,
    stderr=None,
    clock=time.monotonic,
    sleep=time.sleep,
    excluded_pids: Sequence[int] = (),
    stack_factory=None,
    detector_factory=None,
    probe=None,
    camera_probe_s: float = CAMERA_PROBE_S,
) -> dict:
    """Bring up the one production composition, observe everything, tear it down and prove it gone.

    The order is the restarts phase's own and it is not negotiable: the pre-start probe must be empty, the
    dead-man directory exists before the stack starts, one ``RestartStack`` is started and waited for as a
    steady state, the observations are taken while it runs, and the post-teardown probe must be empty
    before this function returns. The observation is returned raw; deciding what it means is the caller's.
    """

    import threading
    from collections import deque

    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.time import Time
    from sensor_msgs.msg import CameraInfo, Image, JointState
    from so101_demo.act.head_search_deadband_measurement import _anchor_requests
    from so101_demo.act.head_search_restarts import (
        _await_graph,
        _kill_stragglers,
        _require_empty,
        _stack_factory,
    )
    from so101_demo.adapters.act.ros_search import RGB_QOS

    def log(message: str) -> None:
        line = f"[{_utc_now()}] readback: {message}\n"
        if stdout is not None:
            stdout.write(line)
            stdout.flush()

    def warn(message: str) -> None:
        line = f"[{_utc_now()}] readback: {message}\n"
        if stderr is not None:
            stderr.write(line)
            stderr.flush()

    observer = probe or (lambda **kwargs: probe_owners(**kwargs))
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    started = clock()
    started_at = _utc_now()
    log("pre-start ownership probe")
    before = observer(excluded_pids=excluded_pids, excluded_nodes=(RUNNER_GRAPH_NODE,))
    try:
        _require_empty(before, anchor=PHASE, stage="pre-start")
    except CalibrationInputsRefused as error:
        raise _refuse(READBACK_FOREIGN_OWNER_ACTIVE, f"{error.code}: {error.detail}") from error
    log(f"pre-start probe clean: {before['owner_processes']}")

    deadman_directory = prepare_deadman_directory(controller_config_path)
    environment = stack_environment(SESSION_ID)

    stack = None
    rclpy_state: dict = {}
    observations: dict = {"deadman_directory": str(deadman_directory)}
    try:
        factory = stack_factory or _stack_factory
        stack = factory(
            urdf_path=urdf_path,
            scene_path=scene_path,
            plugin_config_path=plugin_config_path,
            controller_config_path=controller_config_path,
            workspace=root / "stack",
            session_id=SESSION_ID,
            environment=environment,
            logger=lambda message: log(f"stack: {message}"),
        )
        log("starting the production composition")
        try:
            stack.start()
        except Exception as error:  # noqa: BLE001 - a stack that will not start is a refusal
            raise _refuse(
                READBACK_STACK_START_FAILED,
                f"the production composition did not start: {type(error).__name__}: {error}",
            ) from error
        observations["stack"] = _await_graph(
            observer,
            anchor=PHASE,
            clock=clock,
            sleep=sleep,
            excluded_pids=excluded_pids,
            log=log,
        )
        if not observations["stack"].get("nodes"):
            raise _refuse(
                READBACK_STACK_START_FAILED,
                "the production composition published no node within the graph timeout",
            )
        log(f"stack up: {sorted(observations['stack'].get('nodes') or [])}")

        rclpy.init()
        # the context is recorded before the node exists: a node the runtime refuses still leaves an
        # initialised context behind, and the teardown below must shut it down either way
        rclpy_state["initialized"] = True
        node = Node(RUNNER_NODE)
        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(node)
        spinner = threading.Thread(target=executor.spin, daemon=True, name="readback-spin")
        spinner.start()
        images: deque = deque(maxlen=256)
        infos: deque = deque(maxlen=256)
        joints: deque = deque(maxlen=512)

        def on_image(message):
            images.append({"stamp_s": _stamp_s(message), "frame_id": str(message.header.frame_id)})

        def on_info(message):
            infos.append(
                {
                    "stamp_s": _stamp_s(message),
                    "frame_id": str(message.header.frame_id),
                    "width": int(message.width),
                    "height": int(message.height),
                    "k": [float(value) for value in message.k],
                }
            )

        def on_joints(message):
            names = list(message.name)
            for index, name in enumerate(names):
                if name == "neck_yaw_joint":
                    joints.append({"name": name, "position_rad": float(message.position[index])})

        node.create_subscription(Image, IMAGE_TOPIC, on_image, RGB_QOS)
        node.create_subscription(CameraInfo, CAMERA_INFO_TOPIC, on_info, RGB_QOS)
        node.create_subscription(JointState, JOINT_TOPIC, on_joints, qos_profile_sensor_data)
        transform: dict = {}
        try:
            import tf2_ros

            buffer = tf2_ros.Buffer()
            listener = tf2_ros.TransformListener(buffer, node, spin_thread=False)
            log(f"probing the camera and the TF for {camera_probe_s} s")
            sleep(camera_probe_s)
            try:
                stamped = buffer.lookup_transform(BASE_FRAME, CAMERA_FRAME, Time())
                transform = {
                    "translation_m": [
                        float(stamped.transform.translation.x),
                        float(stamped.transform.translation.y),
                        float(stamped.transform.translation.z),
                    ],
                    "quaternion_xyzw": [
                        float(stamped.transform.rotation.x),
                        float(stamped.transform.rotation.y),
                        float(stamped.transform.rotation.z),
                        float(stamped.transform.rotation.w),
                    ],
                    "stamp_s": float(stamped.header.stamp.sec)
                    + float(stamped.header.stamp.nanosec) * 1e-9,
                    "child_frame_id": str(stamped.child_frame_id),
                }
            except Exception as error:  # noqa: BLE001 - an unavailable TF is recorded, never invented
                transform = {"error": f"{type(error).__name__}: {error}"}
            del listener
        except Exception as error:  # noqa: BLE001 - a missing tf2 is recorded with its reason
            transform = {"error": f"tf2_ros unavailable: {type(error).__name__}: {error}"}
            sleep(camera_probe_s)
        camera_live = _camera_measurements_from_live(
            infos=list(infos), frames=list(images), transform=transform, joints=list(joints)
        )
        observations["camera_measurements"] = camera_live
        observations["clock_probe"] = {
            "camera_frames": len(images),
            "camera_info_frames": len(infos),
        }
        log(
            f"camera: {len(images)} frames, {len(infos)} camera_info; observed "
            f"{sorted(name for name, row in camera_live.items() if row.get('value') is not None)}"
        )

        requests = _anchor_requests(
            seal=seal,
            production=production,
            anchors=[anchor],
            attempt_id=f"{SESSION_ID}-attempt-1",
            session_id=SESSION_ID,
        )
        if len(requests) != 1:
            raise _refuse(
                READBACK_COMPONENT_UNBUILDABLE,
                f"the sealed geometry resolves the anchor {anchor!r} to {len(requests)} declarations",
            )
        configuration = requests[0]["controller_config"]
        observations["configuration_sha256"] = canonical_sha256(configuration)
        observations["search_start_rad"] = configuration["search_start_rad"]

        built = (detector_factory or _default_detector_factory)(
            weights_path=weights_path,
            production=production,
            values=values or {},
            device=device,
            runtime=runtime or {},
            clock=clock,
            log=log,
        )
        detector = built["runtime"]
        observations["detector"] = {
            "loaded": True,
            "count": 1,
            "device": device,
            "runtime_device": built.get("runtime_device"),
            "cuda_device": built.get("cuda_device"),
            "allow_cpu_fallback": False,
            "weights_sha256": built.get("weights_sha256"),
            "model_id": built.get("model_id"),
            "count_definition": (
                "one detector object exists in this process, and it is the only CUDA context this phase "
                "opens; no other process consumes the head camera, because no other process runs"
            ),
        }
        observations["values"] = observe_qualification_values(
            values=values or {},
            configuration=configuration,
            detector=detector,
            controller_factory=None,
            neck_port_factory=None,
            stop_criterion_factory=None,
        )
        rclpy_state.update({"node": node, "executor": executor, "spinner": spinner})
    finally:
        # the runner's own node leaves the graph before the post-teardown probe, whatever happened above:
        # the teardown proof excludes that node by name, and a node left spinning would keep a CUDA-free
        # but real participant in the graph the proof reads
        if rclpy_state:
            if "node" in rclpy_state:
                try:
                    rclpy_state["executor"].remove_node(rclpy_state["node"])
                    rclpy_state["executor"].shutdown()
                    rclpy_state["node"].destroy_node()
                except Exception as error:  # noqa: BLE001 - a derelict runner node is excluded by name
                    warn(f"the runner node teardown raised {error!r}")
            try:
                import rclpy as _rclpy

                _rclpy.shutdown()
            except Exception as error:  # noqa: BLE001 - an already-shut-down context is not a failure
                warn(f"the rclpy shutdown raised {error!r}")
            if "spinner" in rclpy_state:
                rclpy_state["spinner"].join(timeout=10.0)
        if stack is not None:
            log("stopping the stack")
            try:
                stack.stop()
            except Exception as error:  # noqa: BLE001 - a stop failure is verified, not asserted
                warn(f"the stack stop raised {error!r}")
            _kill_stragglers(excluded_pids=excluded_pids, log=log)

    log("post-teardown ownership probe")
    after = observer(excluded_pids=excluded_pids, excluded_nodes=(RUNNER_GRAPH_NODE,))
    proof = teardown_proof(
        processes=after.get("processes") or (),
        nodes=after.get("nodes") or (),
        gpu_compute_apps=after.get("gpu_compute_apps") or (),
        sim_clock_s=after.get("sim_clock_s") or (),
        own_pid=os.getpid(),
        runner_node=RUNNER_GRAPH_NODE,
    )
    proof["before"] = {
        "processes": before.get("processes"),
        "nodes": before.get("nodes"),
        "gpu_compute_apps": before.get("gpu_compute_apps"),
    }
    if not all(proof.get(field) is True for field in TEARDOWN_FACTS):
        raise _refuse(
            READBACK_TEARDOWN_UNPROVEN,
            f"the readback's stack could not be proven gone: {json.dumps(proof, sort_keys=True)}",
        )
    if proof.get("gpu_released") is not True:
        raise _refuse(
            READBACK_GPU_NOT_RELEASED,
            "a compute process still held the GPU after the readback's stack stopped",
        )
    observations["teardown"] = proof
    observations["elapsed_s"] = clock() - started
    observations["started_at_utc"] = started_at
    observations["finished_at_utc"] = _utc_now()
    log(f"readback observation complete in {observations['elapsed_s']:.1f} s; stack proven gone")
    return observations


def _default_detector_factory(
    *, weights_path, production, values, device, runtime, clock, log
) -> dict:
    """The one CUDA detector: the production weights loaded with the promoted operating point.

    It is the same construction the restart phase flies (``TimedHeadDetector.build``): the production
    ``HeadRgbDetector`` over the installed ``YoloSegDetector``, ``allow_cpu_fallback=False``, the weight
    digest checked against the frozen config's own declaration. A detector that will not load is
    ``READBACK_DETECTOR_FAILED`` - the readback never falls back to a CPU model.
    """

    from so101_demo.adapters.act.detector import HeadRgbDetector
    from so101_demo.adapters.perception.yolo_seg import YoloSegDetector

    declared = str(runtime.get("weight_sha256_declared") or "")
    observed = _digest(weights_path)
    if declared and observed != declared:
        raise _refuse(
            READBACK_DETECTOR_FAILED,
            f"the weights at {weights_path} digest to {observed}, the frozen config declares {declared}",
        )
    model_id = str(production.get("runtime_id") or "head-search-runtime")
    try:
        yolo = YoloSegDetector(
            weights_path=Path(weights_path),
            expected_sha256=observed,
            requested_device=device,
            allow_cpu_fallback=False,
            model_id=model_id,
            imgsz=640,
        )
        detector = HeadRgbDetector(
            yolo,
            model_id=model_id,
            weights_sha256=observed,
            tracking_iou=float(values["tracking_iou"]),
            min_bbox_aspect=float(values["min_bbox_aspect"]),
        )
    except Exception as error:  # noqa: BLE001 - a detector that will not load is a refusal
        raise _refuse(
            READBACK_DETECTOR_FAILED,
            f"the production detector could not be loaded on {device}: {type(error).__name__}: {error}",
        ) from error
    log(f"detector {model_id} loaded on {getattr(yolo, 'runtime_device', device)}")
    return {
        "runtime": detector,
        "runtime_device": str(getattr(yolo, "runtime_device", device)),
        "cuda_device": str(runtime.get("cuda_device") or device),
        "weights_sha256": observed,
        "model_id": model_id,
    }


# --- the producer --------------------------------------------------------------------------------------


def write_head_search_qualification_readback(
    *,
    run_root,
    evidence_root,
    ownership_receipt,
    runtime: Mapping,
    approved_bundle: Mapping,
    production_config: Mapping,
    observe: Callable[..., Mapping],
    approved_bundle_path,
    production_config_path,
    camera_reference: Mapping | None = None,
    command: str = "",
    now=time.gmtime,
    clock=time.monotonic,
) -> dict:
    """Take the Step 1 receipt, observe the running composition, and publish the readback it proves.

    The order is fixed: the qualification run root this readback is taken for must not exist yet (the
    aggregate claims it afterwards and never resumes one), the runtime must be the CUDA-only runtime of
    record, the Step 1 receipt must guard exactly that run root, and the promoted values must be the
    approved ones - only then is the stack started through ``observe``. A refused observation is written
    out as evidence before it is raised: a readback that could not be taken is still readable.
    """

    root = Path(run_root)
    if root.exists():
        raise _refuse(
            READBACK_RUN_ROOT_EXISTS,
            f"the qualification run root {root} already exists; this readback is taken for a run root the "
            f"aggregate has not claimed yet, and no qualification phase is ever resumed",
        )
    evidence = Path(evidence_root)
    if evidence.exists() and any(evidence.iterdir()):
        raise _refuse(
            READBACK_RUN_ROOT_EXISTS,
            f"the evidence root {evidence} already exists and is not empty; a readback is never resumed "
            f"or overwritten",
        )
    try:
        runtime = require_runtime_of_record(runtime)
    except CalibrationInputsRefused as error:
        raise _refuse(READBACK_RUNTIME_UNVERIFIED, f"{error.code}: {error.detail}") from error
    try:
        ownership = read_ownership_receipt(ownership_receipt, run_root=root)
    except CalibrationInputsRefused as error:
        code = {
            RESTART_OWNERSHIP_REFUSED: READBACK_OWNERSHIP_REFUSED,
            RESTART_OWNERSHIP_MISMATCH: READBACK_OWNERSHIP_MISMATCH,
            RESTART_RUNTIME_UNVERIFIED: READBACK_RUNTIME_UNVERIFIED,
        }.get(error.code, READBACK_OWNERSHIP_MISMATCH)
        raise _refuse(code, f"{error.code}: {error.detail}") from error
    approved = approved_values(production_config=production_config, approved_bundle=approved_bundle)
    evidence.mkdir(parents=True, exist_ok=True)
    values = approved["values"]
    started = clock()
    taken_at = _utc_now(now)
    stdout = (evidence / STDOUT_LOG).open("a", encoding="utf-8")
    stderr = (evidence / STDERR_LOG).open("a", encoding="utf-8")
    observation: dict = {}
    try:
        observation = dict(
            observe(
                run_root=root,
                evidence_root=evidence,
                runtime=runtime,
                values=values,
                stdout=stdout,
                stderr=stderr,
            )
            or {}
        )
    except CalibrationInputsRefused as error:
        elapsed = clock() - started
        print(f"the readback refused: {error}", file=stderr)
        stderr.flush()
        _write(
            evidence,
            "readback-refusal.json",
            {
                "schema_version": SCHEMA_VERSION,
                "kind": f"{KIND}_refusal",
                "phase": PHASE,
                "run_root": str(root),
                "evidence_root": str(evidence),
                "code": error.code,
                "detail": error.detail,
                "elapsed_s": elapsed,
                "refused_at_utc": _utc_now(now),
                "provenance": {
                    "run_root": str(root),
                    "evidence_root": str(evidence),
                    "source_commit": runtime.get("source_commit"),
                    "production_config_sha256": runtime.get("production_config_sha256"),
                    "values_sha256": approved["values_sha256"],
                    "weight_sha256": runtime.get("weight_sha256_declared"),
                    "elapsed_s": elapsed,
                },
            },
        )
        stdout.close()
        stderr.close()
        raise
    elapsed = clock() - started
    stdout.close()
    stderr.close()

    detector = observation.get("detector") or {}
    live_camera = observation.get("camera_measurements") or {}
    camera_records = camera_measurement_records(live=live_camera, reference=camera_reference)
    document = readback_document(
        run_root=root,
        evidence_root=evidence,
        runtime=runtime,
        approved=approved,
        observations=observation.get("values") or {},
        camera_measurements=camera_records,
        detector=detector,
        ownership=ownership,
        approved_bundle_path=approved_bundle_path,
        production_config_path=production_config_path,
        elapsed_s=elapsed,
        taken_at_utc=taken_at,
        command=command,
    )
    teardown_path = _write(evidence, TEARDOWN_ARTIFACT, observation.get("teardown") or {})
    _write(evidence, ARTIFACT, document)
    document_path = evidence / ARTIFACT
    return {
        "run_root": str(root),
        "evidence_root": str(evidence),
        "document": document,
        "document_path": str(document_path),
        "document_sha256": _digest(document_path),
        "teardown_proof": str(teardown_path),
        "teardown": observation.get("teardown") or {},
        "values": document["values"],
        "camera_measurements": document["camera_measurements"],
        "elapsed_s": elapsed,
        "status": document["status"],
    }
