"""Phase 7 of the formal head search calibration: the five timing and stop parameters and their evidence.

The phase turns the timing measurements the run left behind into the five parameters design section 7.1
fixes, each with the evidence block section 7.1 requires - value, unit, selection formula, the input
evidence with its SHA256, the observed distribution, the safety margin, the production owner and the
startup readback that proves the running system uses the value - in the exact shape phase 8 consumes
(`head_search_calibration_bundle.PARAMETER_EVIDENCE_KEYS`):

* ``max_age_s`` is the nearest-rank p99.9 of the measured end-to-end frame age plus 10 ms. The result
  has to stay within 1.5 frame periods of the declared frame contract; a pipeline that cannot meet it
  refuses with `CAL_FRESHNESS_EXCEEDED`, and the threshold is never raised to accommodate it;
* ``max_skew_s`` is the nearest-rank p99.9 of the measured image/CameraInfo/joint-TF skew plus one
  clock resolution, and has to stay within half a frame period, or the phase refuses with
  `CAL_SKEW_EXCEEDED` - again instead of clamping the value to the cap;
* ``submit_lead_s`` is the minimum measured controller goal-admission lead plus one MuJoCo simulation
  timestep. Every submission used has to be verified in **simulation time**: a record that carries
  wall-clock stamps (or no simulation-time stamps at all) refuses with `CAL_SUBMIT_LEAD_UNVERIFIED`,
  and so does a submission whose lead the computed value does not cover;
* ``stop_velocity_rad_s`` is a conservative envelope of the three stationary contributions: the
  p99.9 of the stationary velocity noise, the feedback quantisation resolution expressed as a velocity
  over one feedback period, and the controller's own stopped tolerance;
* ``stop_latency_s`` is the nearest-rank p99.9 of the measured interval from the stop/revoke request
  to the third consecutive qualifying feedback plus one feedback period. The phase then checks every
  single measurement against that bound: one slow sample fails the run with
  `CAL_STOP_LATENCY_EXCEEDED`, because the threshold is never raised to accommodate it.

The percentile is the nearest-rank order statistic ``ceil(0.999 * n)`` of the measured samples: a safety
bound never interpolates a value that was never measured. The records keep the raw shapes the Task-8
measurement contract already fixes for these five fields, so the same flight's evidence feeds both this
computation and the later per-submission verification.

Phase 7 also records the 10 Hz frame contract itself among the additionally-recorded items phase 8
requires (`frame_contract_10_hz`), because every cap above is expressed in its frame periods. A caller
declaring any other contract is a caller error: the caps are the design's, and another declaration could
only widen them. This phase produces that one item; the other four items phase 8 wants
(`settle_velocity_rad_s`, `goal_tolerance_rad`, the three-consecutive-frame lock rule and the tracker
algorithm) come from their own owners and are merged by the run.

Nothing here commands motion, starts ROS, MuJoCo, CUDA or a detector, reads a file or writes one unless
the caller passes an explicit `output_path`; the phase document is the only file this module ever
creates, and its `motion_commanded` field says so.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_bundle import (
    ALSO_RECORDED_ITEMS,
    CAL_EFFECTIVE_VALUE_MISMATCH,
    PARAMETER_EVIDENCE_KEYS,
)
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_measured_readback import OBSERVED_OBSERVATIONS

SCHEMA_VERSION = 1
KIND = "head_search_calibration_timing_parameters"
PHASE = "timing_stop_parameters"

#: the artefact phase 7 owns in the run root; the run reserves this exact name (design section 8.3)
ARTIFACT_NAME = "timing-calibration.json"

#: this phase's own refusals, plus phase 8's effective-value code for a startup readback that disagrees
#: with the value this phase computed
CAL_FRESHNESS_EXCEEDED = "CAL_FRESHNESS_EXCEEDED"
CAL_SKEW_EXCEEDED = "CAL_SKEW_EXCEEDED"
CAL_SUBMIT_LEAD_UNVERIFIED = "CAL_SUBMIT_LEAD_UNVERIFIED"
CAL_STOP_LATENCY_EXCEEDED = "CAL_STOP_LATENCY_EXCEEDED"
REFUSAL_CODES = (
    CAL_FRESHNESS_EXCEEDED,
    CAL_SKEW_EXCEEDED,
    CAL_SUBMIT_LEAD_UNVERIFIED,
    CAL_STOP_LATENCY_EXCEEDED,
    CAL_EFFECTIVE_VALUE_MISMATCH,
)

#: the five parameters this module computes, in the order design section 7.1 lists them
PARAMETERS = (
    "max_age_s",
    "max_skew_s",
    "submit_lead_s",
    "stop_velocity_rad_s",
    "stop_latency_s",
)

UNITS = {
    "max_age_s": "s",
    "max_skew_s": "s",
    "submit_lead_s": "s",
    "stop_velocity_rad_s": "rad/s",
    "stop_latency_s": "s",
}

#: the production component that reads each value and acts on it. The first two are read by the search
#: controller's freshness gate, the submit lead by the controller submission path, the stop velocity by
#: the cadence-correct history's stop check and the stop latency by the stop-proof verdict
PRODUCTION_OWNERS = {
    "max_age_s": "so101_demo.act.search.HeadSearchController (max_age_s)",
    "max_skew_s": "so101_demo.act.search.HeadSearchController (max_skew_s)",
    "submit_lead_s": "so101_demo.act.execution (submit_lead_s)",
    "stop_velocity_rad_s": (
        "so101_demo.adapters.act.cadence_correct_search_history (stop_velocity_rad_s)"
    ),
    "stop_latency_s": "so101_demo.act.pick_place_calibration_measurement_formulas (stop_latency_s stop proof)",
}

#: the declared frame contract of the design (section 7.1, final paragraph): every cap of this phase is
#: expressed in its frame periods, so the phase accepts no other contract
FRAME_CONTRACT_HZ = 10.0
FRAME_CONTRACT_ITEM = "frame_contract_10_hz"

#: the design's own margins
FRESHNESS_MARGIN_S = 0.010
FRESHNESS_CAP_FRAME_PERIODS = 1.5
SKEW_CAP_FRAME_PERIODS = 0.5

#: the percentile convention: the nearest-rank order statistic, never an interpolated sample
P99_9 = 0.999

#: one controller submission is verified in simulation time or it is refused: the raw record names its
#: stamps in simulation time (`first_target_sim_s`, `submit_snapshot_sim_s`, as the Task-8 measurement
#: contract does) and declares that time base
TIME_BASE_FIELD = "time_base"
SIMULATION_TIME_BASE = "simulation"
SIM_TIME_STAMPS = ("submit_snapshot_sim_s", "first_target_sim_s")

AGE_FORMULA = (
    "nearest_rank_p99_9(decision_monotonic_s - received_monotonic_s) + 10 ms freshness margin; the "
    "value must stay within 1.5 frame periods of the declared 10 Hz frame contract, and a pipeline "
    "that cannot stay there is fixed rather than given a raised threshold"
)
SKEW_FORMULA = (
    "nearest_rank_p99_9(max(stamps) - min(stamps)) + one clock resolution; the value must stay within "
    "half a frame period of the declared 10 Hz frame contract"
)
SUBMIT_FORMULA = (
    "min(first_target_sim_s - submit_snapshot_sim_s) + one MuJoCo simulation timestep; every "
    "submission used has to be verified in simulation time and covered by the computed lead"
)
STOP_VELOCITY_FORMULA = (
    "nearest_rank_p99_9(max(abs(velocity_rad_s)) of the stationary feedback samples) + "
    "feedback_quantisation_rad / feedback_period_s + controller stopped tolerance: a conservative "
    "envelope that covers all three stationary contributions"
)
STOP_LATENCY_FORMULA = (
    "nearest_rank_p99_9(third_confirming_receive_monotonic_s - stop_request_monotonic_s) + one "
    "feedback period; a single stop/revoke measurement beyond that bound fails the run"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

#: every cap above is expressed in frame periods, so the design's contract is the only one this phase
#: may record; the assertion is at import time so a rename cannot silently detach the item
if FRAME_CONTRACT_ITEM not in ALSO_RECORDED_ITEMS:  # pragma: no cover - a bundle-contract guard
    raise RuntimeError(
        f"phase 8 no longer records {FRAME_CONTRACT_ITEM}; phase 7's frame contract has no owner"
    )


class CalibrationTimingParamsRefused(CalibrationInputsRefused):
    """A phase-7 refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _refuse(code: str, detail: str) -> CalibrationTimingParamsRefused:
    return CalibrationTimingParamsRefused(code, detail)


def _number(document, name: str, key: str, *, positive=False, nonnegative=False) -> float:
    """One measured number, or a plain `ValueError` for a caller that passed something else."""

    if not isinstance(document, Mapping):
        raise ValueError(f"{name} must be a measurement document")
    value = document.get(key)
    if not _finite(value):
        raise ValueError(f"{name} declares no finite {key}")
    value = float(value)
    if positive and value <= 0.0:
        raise ValueError(f"{name} declares a non-positive {key}")
    if nonnegative and value < 0.0:
        raise ValueError(f"{name} declares a negative {key}")
    return value


def _samples(name: str, document) -> list[Mapping]:
    """The measured samples of one document; an empty measurement is a caller error, not a refusal."""

    if not isinstance(document, Mapping):
        raise ValueError(f"{name} must be a measurement document")
    samples = document.get("samples")
    if isinstance(samples, (str, bytes)) or not isinstance(samples, Sequence) or not samples:
        raise ValueError(f"{name} records no measured samples")
    for sample in samples:
        if not isinstance(sample, Mapping):
            raise ValueError(f"every {name} sample must be a record")
    return list(samples)


def _reference(name: str, document) -> dict:
    """The path and sha256 of one measured input, as the evidence block cites it."""

    if not isinstance(document, Mapping):
        raise ValueError(f"{name} must be a measurement document")
    path, digest = document.get("path"), document.get("sha256")
    if type(path) is not str or not path:
        raise ValueError(f"{name} names no evidence path")
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        raise ValueError(f"{name} carries no sha256 evidence digest")
    return {"path": path, "sha256": digest}


def nearest_rank_percentile(values, quantile: float = P99_9) -> float:
    """The nearest-rank order statistic of the measured samples: no interpolated value is invented.

    The rank is ``ceil(quantile * n)`` of the sorted samples, so with a thousand samples the p99.9 is
    the second largest one and a single slow outlier does not raise the percentile it has to be
    checked against.
    """

    if isinstance(quantile, bool) or not isinstance(quantile, (int, float)):
        raise ValueError("a percentile takes a quantile in (0, 1]")
    normalized = float(quantile)
    if not math.isfinite(normalized) or not 0.0 < normalized <= 1.0:
        raise ValueError("a percentile takes a quantile in (0, 1]")
    samples: list[float] = []
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("a percentile takes a sequence of measured samples")
    for value in values:
        if not _finite(value):
            raise ValueError(f"{value!r} is not a finite measured sample")
        samples.append(float(value))
    if not samples:
        raise ValueError("a percentile needs at least one measured sample")
    samples.sort()
    rank = max(1, math.ceil(normalized * len(samples)))
    return samples[rank - 1]


def p99_9(values) -> float:
    """The measured p99.9 of one distribution, by the nearest-rank convention."""

    return nearest_rank_percentile(values, P99_9)


def _frame_period(frame_contract) -> tuple[float, float]:
    """The declared frame rate and the frame period every cap is expressed in.

    The design fixes the contract at 10 Hz, so a document declaring another rate is a caller error:
    accepting it would let the caps be widened (or silently changed) by redefining the contract.
    """

    rate = _number(frame_contract, "the frame contract", "frame_rate_hz", positive=True)
    if not math.isclose(rate, FRAME_CONTRACT_HZ, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(
            f"the frame contract declares {rate} Hz, but the design fixes the {FRAME_CONTRACT_HZ} Hz "
            f"frame contract every cap of phase 7 is expressed in"
        )
    period = 1.0 / rate
    declared = frame_contract.get("frame_period_s")
    if declared is not None:
        if not _finite(declared) or not math.isclose(
            float(declared), period, rel_tol=1e-9, abs_tol=1e-12
        ):
            raise ValueError(
                f"the frame contract declares a frame_period_s of {declared!r}, which is not one "
                f"period of its {rate} Hz rate"
            )
    return rate, period


def _readback(name: str, value, startup_readback):
    """The startup readback of one value: a reported one is checked, an absent one stays unverified.

    A readback taken off the running component keeps its own observation and verdict: the caller that
    observed the component already decided whether the observation proves the value, and relabelling it a
    caller's report would hide the difference between proof and restatement. A readback the caller merely
    reports is checked here and marked as reported.
    """

    if startup_readback is None:
        return {
            "observed_value": value,
            "observation": "declared_by_phase_7",
            "verified": False,
            "detail": (
                "phase 7 computes the value; the run records the startup readback that proves the "
                "production component uses it"
            ),
        }
    if not isinstance(startup_readback, Mapping) or "observed_value" not in startup_readback:
        raise ValueError(f"the startup readback of {name} records no observed value")
    observed = startup_readback["observed_value"]
    if observed != value:
        raise CalibrationTimingParamsRefused(
            CAL_EFFECTIVE_VALUE_MISMATCH,
            f"{name}: the startup readback observed {observed!r} but phase 7 computed {value!r}; the "
            f"running system has to use the computed value",
        )
    readback = dict(startup_readback)
    if readback.get("observation") not in OBSERVED_OBSERVATIONS:
        # the caller reported the value rather than observing the component that uses it
        readback["observation"] = "reported_by_caller"
        readback["verified"] = True
    return readback


def _block(*, name: str, value, formula: str, references, distribution, margin, readback) -> dict:
    """One evidence block, with exactly the keys phase 8 requires and nothing else."""

    fields = {
        "value": value,
        "unit": UNITS[name],
        "selection_formula": formula,
        "input_evidence": list(references),
        "observed_distribution": dict(distribution),
        "safety_margin": dict(margin),
        "production_owner": PRODUCTION_OWNERS[name],
        "startup_readback": _readback(name, value, readback),
    }
    return {key: fields[key] for key in PARAMETER_EVIDENCE_KEYS}


def compute_max_age_s(*, frame_age, frame_contract, startup_readback=None) -> dict:
    """The measured p99.9 end-to-end frame age plus 10 ms, inside 1.5 declared frame periods."""

    rate, period = _frame_period(frame_contract)
    samples = _samples("the frame-age measurements", frame_age)
    ages: list[float] = []
    for sample in samples:
        received = _number(sample, "a frame-age sample", "received_monotonic_s")
        decision = _number(sample, "a frame-age sample", "decision_monotonic_s")
        age = decision - received
        if age < 0.0:
            raise ValueError("a frame-age sample records a decision before its receipt")
        ages.append(age)
    p99_9_age = p99_9(ages)
    value = p99_9_age + FRESHNESS_MARGIN_S
    cap = FRESHNESS_CAP_FRAME_PERIODS * period
    if value > cap:
        raise _refuse(
            CAL_FRESHNESS_EXCEEDED,
            f"max_age_s {value} s (p99.9 frame age {p99_9_age} s + {FRESHNESS_MARGIN_S} s margin) "
            f"exceeds the {cap} s cap of {FRESHNESS_CAP_FRAME_PERIODS} frame periods of the declared "
            f"{rate} Hz contract: the frame pipeline must be fixed rather than the freshness threshold "
            f"raised",
        )
    distribution = {
        "p99_9_frame_age_s": p99_9_age,
        "sample_count": len(ages),
        "max_frame_age_s": max(ages),
        "frame_rate_hz": rate,
        "frame_period_s": period,
    }
    margin = {
        "freshness_margin_s": FRESHNESS_MARGIN_S,
        "cap_s": cap,
        "frame_periods": FRESHNESS_CAP_FRAME_PERIODS,
        "headroom_s": cap - value,
    }
    return _block(
        name="max_age_s",
        value=value,
        formula=AGE_FORMULA,
        references=[
            _reference("the frame contract", frame_contract),
            _reference("the frame-age measurements", frame_age),
        ],
        distribution=distribution,
        margin=margin,
        readback=startup_readback,
    )


def compute_max_skew_s(*, skew, frame_contract, startup_readback=None) -> dict:
    """The measured p99.9 image/CameraInfo/joint-TF skew plus one clock resolution, inside half a frame."""

    rate, period = _frame_period(frame_contract)
    samples = _samples("the skew measurements", skew)
    spreads: list[float] = []
    for sample in samples:
        stamps = sample.get("stamps")
        if (
            isinstance(stamps, (str, bytes))
            or not isinstance(stamps, Sequence)
            or len(stamps) < 2
            or not all(_finite(stamp) for stamp in stamps)
        ):
            raise ValueError(
                "a skew sample records the finite stamps of at least two required sources"
            )
        values = [float(stamp) for stamp in stamps]
        spreads.append(max(values) - min(values))
    clock_resolution = _number(skew, "the skew measurements", "clock_resolution_s", positive=True)
    p99_9_skew = p99_9(spreads)
    value = p99_9_skew + clock_resolution
    cap = SKEW_CAP_FRAME_PERIODS * period
    if value > cap:
        raise _refuse(
            CAL_SKEW_EXCEEDED,
            f"max_skew_s {value} s (p99.9 skew {p99_9_skew} s + {clock_resolution} s clock "
            f"resolution) exceeds the {cap} s cap of half a frame period of the declared {rate} Hz "
            f"contract; the value is refused rather than clamped to the cap",
        )
    distribution = {
        "p99_9_skew_s": p99_9_skew,
        "sample_count": len(spreads),
        "max_skew_s": max(spreads),
        "clock_resolution_s": clock_resolution,
        "frame_rate_hz": rate,
        "frame_period_s": period,
    }
    margin = {
        "clock_resolution_s": clock_resolution,
        "cap_s": cap,
        "frame_periods": SKEW_CAP_FRAME_PERIODS,
        "headroom_s": cap - value,
    }
    return _block(
        name="max_skew_s",
        value=value,
        formula=SKEW_FORMULA,
        references=[
            _reference("the frame contract", frame_contract),
            _reference("the skew measurements", skew),
        ],
        distribution=distribution,
        margin=margin,
        readback=startup_readback,
    )


def _simulation_time_lead(sample: Mapping, index: int) -> float:
    """One submission's lead, or the refusal that says it was not verified in simulation time."""

    time_base = sample.get(TIME_BASE_FIELD)
    stamps = {name: sample.get(name) for name in SIM_TIME_STAMPS}
    missing = [name for name, stamp in stamps.items() if not _finite(stamp)]
    if missing:
        clock = f" on the {time_base!r} clock" if isinstance(time_base, str) and time_base else ""
        raise _refuse(
            CAL_SUBMIT_LEAD_UNVERIFIED,
            f"submission {index} carries no simulation-time stamps{clock}: it records {missing} "
            f"instead, and every submission used has to be verified in simulation time - a wall-clock "
            f"submission record cannot bound a lead the controller sees in simulation time",
        )
    if isinstance(time_base, str) and time_base.lower() != SIMULATION_TIME_BASE:
        raise _refuse(
            CAL_SUBMIT_LEAD_UNVERIFIED,
            f"submission {index} declares the {time_base!r} time base, not {SIMULATION_TIME_BASE!r}: "
            f"a wall-clock submission record is not verified in simulation time and is refused",
        )
    lead = float(stamps["first_target_sim_s"]) - float(stamps["submit_snapshot_sim_s"])
    if lead < 0.0:
        raise ValueError("a submission records its first target before its snapshot")
    return lead


def compute_submit_lead_s(*, submissions, mujoco, startup_readback=None) -> dict:
    """The minimum simulation-time goal-admission lead plus one MuJoCo simulation timestep."""

    samples = _samples("the controller submissions", submissions)
    leads = [_simulation_time_lead(sample, index) for index, sample in enumerate(samples)]
    timestep = _number(mujoco, "the MuJoCo measurements", "simulation_timestep_s", positive=True)
    value = min(leads) + timestep
    uncovered = [lead for lead in leads if lead > value]
    if uncovered:
        raise _refuse(
            CAL_SUBMIT_LEAD_UNVERIFIED,
            f"the computed submit_lead_s {value} s (minimum lead {min(leads)} s + one "
            f"{timestep} s MuJoCo timestep) does not cover the measured submission lead "
            f"{max(uncovered)} s: a single lead value can only be certified when every verified "
            f"submission stays inside it",
        )
    distribution = {
        "minimum_lead_s": min(leads),
        "maximum_lead_s": max(leads),
        "sample_count": len(leads),
        "submission_count": len(leads),
        "simulation_timestep_s": timestep,
        "submissions_verified_in_simulation_time": True,
        "leads_s": list(leads),
    }
    margin = {
        "simulation_timestep_s": timestep,
        "lead_spread_s": max(leads) - min(leads),
        "headroom_s": value - max(leads),
    }
    return _block(
        name="submit_lead_s",
        value=value,
        formula=SUBMIT_FORMULA,
        references=[
            _reference("the controller submissions", submissions),
            _reference("the MuJoCo measurements", mujoco),
        ],
        distribution=distribution,
        margin=margin,
        readback=startup_readback,
    )


def compute_stop_velocity_rad_s(*, stationary, feedback, controller, startup_readback=None) -> dict:
    """The conservative envelope of the stationary noise, the feedback quantisation and the tolerance."""

    samples = _samples("the stationary velocity measurements", stationary)
    maxima: list[float] = []
    for sample in samples:
        velocities = sample.get("velocity_rad_s")
        if (
            isinstance(velocities, (str, bytes))
            or not isinstance(velocities, Sequence)
            or not velocities
            or not all(_finite(velocity) for velocity in velocities)
        ):
            raise ValueError("every stationary sample records the finite velocity of each joint")
        maxima.append(max(abs(float(velocity)) for velocity in velocities))
    noise = p99_9(maxima)
    # the second term is the declared feedback resolution over one feedback period. On this platform the
    # resolution is declared as an explicit zero (the MuJoCo feedback exposes joint velocities, with no
    # encoder quantisation), so the term may be zero - but a missing or null resolution is still refused,
    # because a defaulted zero would be the invented value design section 7.1 forbids (HS-305)
    quantisation_rad = _number(
        feedback, "the controller feedback", "quantisation_rad", nonnegative=True
    )
    feedback_period_s = _number(feedback, "the controller feedback", "period_s", positive=True)
    tolerance = _number(
        controller, "the controller stop configuration", "stopped_tolerance_rad_s", nonnegative=True
    )
    quantisation_velocity = quantisation_rad / feedback_period_s
    value = noise + quantisation_velocity + tolerance
    distribution = {
        "p99_9_stationary_velocity_rad_s": noise,
        "stationary_sample_count": len(maxima),
        "max_stationary_velocity_rad_s": max(maxima),
        "quantisation_rad": quantisation_rad,
        "feedback_period_s": feedback_period_s,
        "stopped_tolerance_rad_s": tolerance,
    }
    margin = {
        "stationary_velocity_rad_s": noise,
        "quantisation_velocity_rad_s": quantisation_velocity,
        "stopped_tolerance_rad_s": tolerance,
        "envelope_terms": 3,
    }
    return _block(
        name="stop_velocity_rad_s",
        value=value,
        formula=STOP_VELOCITY_FORMULA,
        references=[
            _reference("the stationary velocity measurements", stationary),
            _reference("the controller feedback", feedback),
            _reference("the controller stop configuration", controller),
        ],
        distribution=distribution,
        margin=margin,
        readback=startup_readback,
    )


def compute_stop_latency_s(*, stop_proofs, feedback, startup_readback=None) -> dict:
    """The p99.9 stop/revoke-to-third-feedback interval plus one feedback period, as a hard bound."""

    samples = _samples("the stop/revoke proofs", stop_proofs)
    latencies: list[float] = []
    for sample in samples:
        request = _number(sample, "a stop proof", "stop_request_monotonic_s")
        third = _number(sample, "a stop proof", "third_confirming_receive_monotonic_s")
        latency = third - request
        if latency < 0.0:
            raise ValueError(
                "a stop proof records its third confirming feedback before the request"
            )
        latencies.append(latency)
    feedback_period_s = _number(feedback, "the controller feedback", "period_s", positive=True)
    p99_9_latency = p99_9(latencies)
    value = p99_9_latency + feedback_period_s
    slow = [latency for latency in latencies if latency > value]
    if slow:
        raise _refuse(
            CAL_STOP_LATENCY_EXCEEDED,
            f"the stop/revoke measurement {max(slow)} s exceeds stop_latency_s {value} s (p99.9 "
            f"{p99_9_latency} s + one {feedback_period_s} s feedback period) in a set of "
            f"{len(latencies)} measurements: the threshold is never raised to accommodate a slow "
            f"sample, the stop path has to be fixed",
        )
    slowest = max(latencies)
    distribution = {
        "p99_9_stop_latency_s": p99_9_latency,
        "sample_count": len(latencies),
        "slowest_sample_s": slowest,
        "feedback_period_s": feedback_period_s,
    }
    margin = {
        "feedback_period_s": feedback_period_s,
        "p99_9_stop_latency_s": p99_9_latency,
        "bound_s": value,
        "slowest_sample_s": slowest,
        "headroom_s": value - slowest,
    }
    return _block(
        name="stop_latency_s",
        value=value,
        formula=STOP_LATENCY_FORMULA,
        references=[
            _reference("the stop/revoke proofs", stop_proofs),
            _reference("the controller feedback", feedback),
        ],
        distribution=distribution,
        margin=margin,
        readback=startup_readback,
    )


def frame_contract_item(*, frame_contract, startup_readback=None) -> dict:
    """The `frame_contract_10_hz` item among the additionally-recorded items phase 8 requires.

    Every cap of this phase is expressed in frame periods, so the contract itself is recorded with its
    value, the evidence it was read from and the readback that proves the running system uses it.
    """

    rate, period = _frame_period(frame_contract)
    definition = (
        f"{rate} Hz frame contract: frame_period_s = {period}; every freshness, skew, submit and stop "
        f"bound of phase 7 is expressed in these frame periods"
    )
    return {
        "value_or_definition": definition,
        "input_evidence": [_reference("the frame contract", frame_contract)],
        "startup_readback": _readback(FRAME_CONTRACT_ITEM, rate, startup_readback),
    }


def validate_head_search_calibration_timing_params(
    *,
    frame_age,
    skew,
    frame_contract,
    submissions,
    mujoco,
    stationary,
    feedback,
    controller,
    stop_proofs,
    startup_readbacks=None,
    output_path=None,
) -> dict:
    """Produce phase 7's document: the five parameters, each with the evidence block phase 8 consumes.

    The five values are computed in the order design section 7.1 lists them, and every refusal stops
    the phase before a value is produced: a frame age beyond 1.5 frame periods or a skew beyond half a
    frame period refuses instead of clamping, a submission that was not verified in simulation time
    refuses, and one stop/revoke measurement beyond the computed bound fails the run. When
    `output_path` is given the phase document is written there and nowhere else; without it the phase
    writes nothing at all.
    """

    if startup_readbacks is not None and not isinstance(startup_readbacks, Mapping):
        raise ValueError("startup_readbacks must map each parameter to its observed readback")

    def readback(name: str):
        return None if startup_readbacks is None else startup_readbacks.get(name)

    parameters = {
        "max_age_s": compute_max_age_s(
            frame_age=frame_age,
            frame_contract=frame_contract,
            startup_readback=readback("max_age_s"),
        ),
        "max_skew_s": compute_max_skew_s(
            skew=skew,
            frame_contract=frame_contract,
            startup_readback=readback("max_skew_s"),
        ),
        "submit_lead_s": compute_submit_lead_s(
            submissions=submissions,
            mujoco=mujoco,
            startup_readback=readback("submit_lead_s"),
        ),
        "stop_velocity_rad_s": compute_stop_velocity_rad_s(
            stationary=stationary,
            feedback=feedback,
            controller=controller,
            startup_readback=readback("stop_velocity_rad_s"),
        ),
        "stop_latency_s": compute_stop_latency_s(
            stop_proofs=stop_proofs,
            feedback=feedback,
            startup_readback=readback("stop_latency_s"),
        ),
    }
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "parameter_names": list(PARAMETERS),
        "parameters": {name: parameters[name] for name in PARAMETERS},
        "parameters_complete": True,
        "also_recorded": {
            FRAME_CONTRACT_ITEM: frame_contract_item(
                frame_contract=frame_contract,
                startup_readback=readback(FRAME_CONTRACT_ITEM),
            )
        },
        "motion_commanded": False,
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document
