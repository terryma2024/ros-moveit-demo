"""Phase 6 of the formal head search calibration: the five search parameters and their evidence.

The phase turns the measurements the earlier phases and the run left behind into the search parameters
design section 7.1 fixes, each with the evidence block section 7.1 requires - value, unit, selection
formula, the input evidence with its SHA256, the observed distribution, the safety margin, the production
owner and the startup readback that proves the running system uses the value - in the exact shape phase 8
consumes (`head_search_calibration_bundle.PARAMETER_EVIDENCE_KEYS`):

* ``search_timeout_s`` from the maximum number of stable stop points of the bounded sweep, the p99 settle
  and frame time per step, the fine-correction bound and one complete control period per fine correction;
  a sweep with no stable stop, a missing p99 or no correction bound refuses with `CAL_TIMEOUT_UNBOUNDED`
  rather than inventing a timeout;
* ``center_deadband_px`` starts at the measured centre jitter expressed in pixels through the camera's
  angular resolution and takes the smallest declared candidate at or above that start whose recorded
  trial locks for three consecutive frames with no left-right reversal; when the searched range holds no
  such candidate the phase refuses with `CAL_DEADBAND_OSCILLATES`;
* ``vertical_bounds_px`` is the legal pick workspace projected into the head camera and intersected with
  the image safety margin. It is **never** back-filled from detection extremes: this module has no code
  path that turns detections into bounds, and a caller that offers detection extremes is refused with
  `CAL_VERTICAL_BOUNDS_UNPROJECTED` even when a projection is available;
* ``max_fine_corrections`` is the largest count a successful held-out validation episode needed plus one
  recovery allowance, and ``max_fine_total_rad`` is the largest cumulative fine correction of those
  episodes plus the largest single correction observed in them. Both have to stay inside the legal neck
  interval: a budget that could leave it refuses with `CAL_SWEEP_UNSTABLE`;
* the fine-correction numbers are bounded by held-out or validation episodes only. An episode of the
  calibration split - or of any split the caller did not declare as held out - is refused with phase 3's
  own `CAL_SPLIT_LEAK`, reusing that phase's split-isolation convention rather than inventing a code
  (plan section 4 item 7 names the same misuse `CAL_HELDOUT_MISUSE`).

Nothing here commands motion, starts ROS, MuJoCo, CUDA or a detector, reads a file or writes one unless
the caller passes an explicit `output_path`; the phase document is the only file this module ever
creates, and its `motion_commanded` field says so. The parameters are computed from measurement
documents the caller passes; this phase measures nothing itself (plan section 0: it does not move the
neck on its own).

Phase 6 also owns ``coarse_step_rad``. Its final value needs the selected model's val sweep and lock
evidence (plan section 2 row 6), which is measured by ``head_search_coarse_step_measurement``; when the run
declares that raw sweep, this phase checks it against the sealed geometry and the selected model's weights,
takes the value it chose, and requires it to be the very candidate step phase 2 receipted - a step the
receipts do not vouch for would leave every neck target unproven, which refuses with `CAL_SWEEP_UNSTABLE`.
Without a declared sweep the phase records the gap explicitly instead of inventing the sixth value.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search.calibration_bundle import (
    CAL_EFFECTIVE_VALUE_MISMATCH,
    PARAMETER_EVIDENCE_KEYS,
)
from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search.measured_readback import OBSERVED_OBSERVATIONS
from so101_demo.act.head_search.coarse_step_measurement.contracts import (
    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
    CAL_SWEEP_EVIDENCE_MISSING,
    CAL_SWEEP_EVIDENCE_PARTIAL,
    CalibrationCoarseStepRefused,
)
from so101_demo.act.head_search.coarse_step_measurement.verdicts import (
    validate_head_search_coarse_step_measurement,
)
from so101_demo.act.head_search.coarse_step_measurement.contracts import (
    PARAMETER as COARSE_STEP_PARAMETER,
)
from so101_demo.act.head_search.coarse_step_measurement.contracts import UNIT as COARSE_STEP_UNIT
from so101_demo.act.head_search.operating_point import CAL_SPLIT_LEAK

SCHEMA_VERSION = 1
KIND = "head_search_calibration_search_parameters"
PHASE = "search_parameters"

#: this phase's own refusals, plus the codes it reuses: phase 3's split leak for a calibration frame
#: offered to the held-out fine-correction numbers, phase 8's effective-value code for a startup readback
#: that disagrees with the value this phase computed, and the raw val sweep's own three codes - phase 6
#: owns `coarse_step_rad`, so it owns the refusals that measurement can raise, re-raised under this
#: phase's class with the same code rather than leaking another module's exception type
CAL_TIMEOUT_UNBOUNDED = "CAL_TIMEOUT_UNBOUNDED"
CAL_DEADBAND_OSCILLATES = "CAL_DEADBAND_OSCILLATES"
CAL_SWEEP_UNSTABLE = "CAL_SWEEP_UNSTABLE"
CAL_VERTICAL_BOUNDS_UNPROJECTED = "CAL_VERTICAL_BOUNDS_UNPROJECTED"
REFUSAL_CODES = (
    CAL_TIMEOUT_UNBOUNDED,
    CAL_DEADBAND_OSCILLATES,
    CAL_SWEEP_UNSTABLE,
    CAL_VERTICAL_BOUNDS_UNPROJECTED,
    CAL_SWEEP_EVIDENCE_MISSING,
    CAL_SWEEP_EVIDENCE_PARTIAL,
    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
    CAL_SPLIT_LEAK,
    CAL_EFFECTIVE_VALUE_MISMATCH,
)

#: the five parameters this module computes, in the order design section 7.1 lists them
PARAMETERS = (
    "search_timeout_s",
    "center_deadband_px",
    "vertical_bounds_px",
    "max_fine_corrections",
    "max_fine_total_rad",
)

UNITS = {
    "search_timeout_s": "s",
    "center_deadband_px": "px",
    "vertical_bounds_px": "px",
    "max_fine_corrections": "count",
    "max_fine_total_rad": "rad",
}

#: the production component that reads each value and acts on it; every one of them is a
#: `HeadSearchController` configuration key, so a value that never reaches the controller fails the run
PRODUCTION_OWNERS = {
    "search_timeout_s": "so101_demo.act.search.HeadSearchController (search_timeout_s)",
    "center_deadband_px": "so101_demo.act.search.HeadSearchController (center_deadband_px)",
    "vertical_bounds_px": "so101_demo.act.search.HeadSearchController (vertical_bounds_px)",
    "max_fine_corrections": "so101_demo.act.search.HeadSearchController (max_fine_corrections)",
    "max_fine_total_rad": "so101_demo.act.search.HeadSearchController (max_fine_total_rad)",
}

#: the three-consecutive-frame lock rule the controller applies before it reports a lock (search.py)
LOCK_FRAMES = 3

#: one recovery allowance on top of the largest observed fine-correction count
RECOVERY_ALLOWANCE = 1

TIMEOUT_FORMULA = (
    "max_stable_stop_points * (p99_settle_s + p99_frame_s) + max_fine_corrections * "
    "control_period_s: every stable stop of the bounded sweep costs one p99 settle time and one p99 "
    "frame time, and each fine correction is guarded by one complete control period"
)
DEADBAND_FORMULA = (
    "ceil(centre_jitter_rad / rad_per_px) with rad_per_px = horizontal_fov_rad / image_width_px, then "
    "the smallest declared deadband at or above that start whose recorded trial locks for three "
    "consecutive frames with zero left-right direction reversals"
)
VERTICAL_FORMULA = (
    "[max(workspace_projection.top_px, safety_margin_px), min(workspace_projection.bottom_px, "
    "image_height_px - safety_margin_px)]: the legal pick workspace projected into the head camera, "
    "intersected with the image safety margin, never back-filled from detection extremes"
)
CORRECTIONS_FORMULA = (
    "max(fine_corrections of the successful held-out validation episodes) + one recovery allowance, "
    "kept inside the legal neck interval because max_fine_corrections * the largest observed single "
    "correction must not exceed the distance from every sweep stop to the interval bound"
)
TOTAL_FORMULA = (
    "max(cumulative fine correction of the successful held-out validation episodes) + the largest "
    "single correction observed in those episodes, never crossing the safe neck interval"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

#: the phase-6 parameter design section 7.1 assigns here whose final value needs the selected model's val
#: sweep and lock evidence (plan section 2 row 6). Phase 6 owns the value, but the measurement belongs to
#: `head_search_coarse_step_measurement`: a caller that declares no sweep records the gap here rather than
#: inventing a number
UNCOMPUTED_PARAMETER = {
    "name": COARSE_STEP_PARAMETER,
    "computed_here": False,
    "detail": (
        "phase 6 also owns coarse_step_rad; its final value needs the selected model's val sweep and "
        "lock evidence, so without a declared sweep phase 6 records it outside `parameters` rather than "
        "inventing it"
    ),
}


class CalibrationSearchParamsRefused(CalibrationInputsRefused):
    """A phase-6 refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _refuse(code: str, detail: str) -> CalibrationSearchParamsRefused:
    return CalibrationSearchParamsRefused(code, detail)


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


def _optional_number(document, key: str) -> float | None:
    """One measured number when it is there and finite, else None - never an exception."""

    if not isinstance(document, Mapping):
        return None
    value = document.get(key)
    return float(value) if _finite(value) else None


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


def _declared_splits(held_out_splits) -> tuple[str, ...]:
    """The splits declared for validation, exactly as phase 3 declares its own split sets."""

    if isinstance(held_out_splits, (str, bytes)) or not isinstance(held_out_splits, Sequence):
        raise ValueError("held_out_splits must be a non-empty sequence of split names")
    splits: list[str] = []
    for split in held_out_splits:
        if type(split) is not str or not split:
            raise ValueError("held_out_splits must name every split")
        if split in splits:
            raise ValueError(f"held_out_splits declares {split!r} twice")
        splits.append(split)
    if not splits:
        raise ValueError("held_out_splits must declare at least one held-out split")
    return tuple(splits)


def _records(name: str, value) -> list[Mapping]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence of records")
    records = []
    for record in value:
        if not isinstance(record, Mapping):
            raise ValueError(f"every {name} record must be a mapping")
        records.append(record)
    return records


def _coverage_proof(bounded_sweep) -> Mapping:
    """The coverage proof of the bounded sweep, whether the phase-2 document or the proof itself."""

    if not isinstance(bounded_sweep, Mapping):
        return {}
    proof = bounded_sweep.get("coverage_proof")
    return proof if isinstance(proof, Mapping) else bounded_sweep


def _stop_counts_by_anchor(bounded_sweep) -> dict[str, int]:
    """How many stable stops the bounded sweep plans per anchor."""

    proof = _coverage_proof(bounded_sweep)
    anchors = proof.get("anchors")
    if isinstance(anchors, (str, bytes)) or not isinstance(anchors, Sequence):
        return {}
    counts: dict[str, int] = {}
    for index, anchor in enumerate(anchors):
        if not isinstance(anchor, Mapping):
            continue
        name = anchor.get("anchor")
        name = name if type(name) is str and name else f"anchor-{index}"
        count = anchor.get("stop_count")
        if type(count) is int and not isinstance(count, bool) and count >= 0:
            counts[name] = count
            continue
        targets = anchor.get("targets_rad")
        if isinstance(targets, Sequence) and not isinstance(targets, (str, bytes)):
            counts[name] = len(targets)
    return counts


def max_stable_stop_points(bounded_sweep) -> int:
    """The largest number of stable stop points any anchor of the bounded sweep commands."""

    counts = _stop_counts_by_anchor(bounded_sweep)
    return max(counts.values()) if counts else 0


def sweep_references(bounded_sweep) -> list[dict]:
    """The sealed geometry the sweep was planned from, as the evidence block cites it."""

    if not isinstance(bounded_sweep, Mapping):
        return []
    sealed = bounded_sweep.get("sealed_geometry")
    if sealed is None:
        return []
    return [_reference("the sealed geometry", sealed)]


def _sweep_geometry(bounded_sweep) -> tuple[list[float], tuple[float, float] | None]:
    """The stops the bounded sweep commands and the safe interval it planned them inside."""

    proof = _coverage_proof(bounded_sweep)
    stops: list[float] = []
    anchors = proof.get("anchors")
    if isinstance(anchors, Sequence) and not isinstance(anchors, (str, bytes)):
        for anchor in anchors:
            if not isinstance(anchor, Mapping):
                continue
            targets = anchor.get("targets_rad")
            if isinstance(targets, Sequence) and not isinstance(targets, (str, bytes)):
                stops.extend(float(target) for target in targets if _finite(target))
    declared: list = [proof.get("safe_interval_rad")]
    if isinstance(bounded_sweep, Mapping):
        geometry = bounded_sweep.get("geometry")
        if isinstance(geometry, Mapping):
            declared.append(geometry.get("lock_valid_neck_rad"))
    for value in declared:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
            continue
        if not all(_finite(bound) for bound in value):
            continue
        low, high = (float(bound) for bound in value)
        if low < high:
            return stops, (low, high)
    return stops, None


def _safe_allowance(stops: Sequence[float], safe: tuple[float, float] | None) -> float | None:
    """How far a stop may still travel before it leaves the safe interval, or None when unknowable."""

    if safe is None or not stops:
        return None
    low, high = safe
    return min(min(stop - low, high - stop) for stop in stops)


def _successful_episodes(frames: Sequence[Mapping], held_out: Sequence[str]) -> list[Mapping]:
    """The successful held-out validation episodes, or the refusal that stops the phase."""

    for frame in frames:
        split = frame.get("split")
        if type(split) is not str or not split:
            raise _refuse(
                CAL_SPLIT_LEAK,
                "a fine-correction episode declares no split, so it cannot be shown to belong to a "
                "held-out validation split",
            )
        if split not in held_out:
            raise _refuse(
                CAL_SPLIT_LEAK,
                f"a {split!r} episode was offered to the fine-correction numbers, which only the "
                f"held-out validation splits {list(held_out)} may bound; the fine-correction path is "
                f"never calibrated on the frames it is validated on",
            )
    successful = [frame for frame in frames if frame.get("succeeded") is True]
    if not successful:
        raise _refuse(
            CAL_SWEEP_UNSTABLE,
            f"none of the {len(frames)} held-out validation episodes succeeded, so no fine-correction "
            f"budget can be bounded inside the safe neck interval",
        )
    return successful


def _episode_numbers(frame: Mapping) -> tuple[str, int, float, float]:
    """One successful episode's id, correction count, cumulative correction and largest correction."""

    episode_id = frame.get("episode_id")
    if type(episode_id) is not str or not episode_id:
        raise ValueError("every fine-correction episode must be named")
    count = frame.get("fine_corrections")
    if type(count) is not int or isinstance(count, bool) or count < 1:
        raise _refuse(
            CAL_SWEEP_UNSTABLE,
            f"the successful episode {episode_id!r} records no positive fine-correction count",
        )
    magnitudes = frame.get("fine_corrections_rad")
    if (
        isinstance(magnitudes, (str, bytes))
        or not isinstance(magnitudes, Sequence)
        or len(magnitudes) != count
        or not all(_finite(magnitude) and float(magnitude) > 0.0 for magnitude in magnitudes)
    ):
        raise _refuse(
            CAL_SWEEP_UNSTABLE,
            f"the successful episode {episode_id!r} records {count} fine corrections but not one "
            f"positive finite magnitude per correction, so their travel cannot be bounded",
        )
    values = [float(magnitude) for magnitude in magnitudes]
    return episode_id, count, sum(values), max(values)


def _fine_correction_numbers(
    *, episodes, held_out_splits, bounded_sweep
) -> tuple[list[tuple[str, int, float, float]], float, tuple[float, float]]:
    """The per-episode numbers and the safe allowance every fine-correction budget is checked against."""

    held_out = _declared_splits(held_out_splits)
    frames = _records("fine_correction_episodes", episodes)
    numbers = [_episode_numbers(frame) for frame in _successful_episodes(frames, held_out)]
    stops, safe = _sweep_geometry(bounded_sweep)
    allowance = _safe_allowance(stops, safe)
    if allowance is None:
        raise _refuse(
            CAL_SWEEP_UNSTABLE,
            "the bounded sweep records no safe neck interval and no stop to measure it against, so no "
            "fine correction can be shown to stay inside the legal interval",
        )
    return numbers, allowance, safe


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
            "observation": "declared_by_phase_6",
            "verified": False,
            "detail": (
                "phase 6 computes the value; the run records the startup readback that proves the "
                "production component uses it"
            ),
        }
    if not isinstance(startup_readback, Mapping) or "observed_value" not in startup_readback:
        raise ValueError(f"the startup readback of {name} records no observed value")
    observed = startup_readback["observed_value"]
    if observed != value:
        raise CalibrationSearchParamsRefused(
            CAL_EFFECTIVE_VALUE_MISMATCH,
            f"{name}: the startup readback observed {observed!r} but phase 6 computed {value!r}; the "
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


def compute_search_timeout_s(
    *, bounded_sweep, timing, max_fine_corrections, startup_readback=None
) -> dict:
    """Bound the search: every stable stop plus every guarded fine correction, or refuse unbounded."""

    stops = max_stable_stop_points(bounded_sweep)
    if stops < 1:
        raise _refuse(
            CAL_TIMEOUT_UNBOUNDED,
            "the bounded sweep has no stable stop point, so no timeout can bound a search that never "
            "stops at a known place",
        )
    p99_settle_s = _optional_number(timing, "p99_settle_s")
    p99_frame_s = _optional_number(timing, "p99_frame_s")
    control_period_s = _optional_number(timing, "control_period_s")
    missing = [
        key
        for key, value in (
            ("p99_settle_s", p99_settle_s),
            ("p99_frame_s", p99_frame_s),
            ("control_period_s", control_period_s),
        )
        if value is None or value <= 0.0
    ]
    if missing:
        raise _refuse(
            CAL_TIMEOUT_UNBOUNDED,
            f"the timing measurements do not bound the search timeout: {missing} is missing or not "
            f"positive",
        )
    if (
        type(max_fine_corrections) is not int
        or isinstance(max_fine_corrections, bool)
        or max_fine_corrections < 1
    ):
        raise _refuse(
            CAL_TIMEOUT_UNBOUNDED,
            f"the fine-correction bound {max_fine_corrections!r} does not bound the search timeout, so "
            f"the guard of one complete control period per correction cannot be computed",
        )
    value = stops * (p99_settle_s + p99_frame_s) + max_fine_corrections * control_period_s
    distribution = {
        "max_stable_stop_points": stops,
        "stops_per_anchor": _stop_counts_by_anchor(bounded_sweep),
        "p99_settle_s": p99_settle_s,
        "p99_frame_s": p99_frame_s,
        "control_period_s": control_period_s,
        "max_fine_corrections": max_fine_corrections,
    }
    margin = {
        "per_stop_s": p99_settle_s + p99_frame_s,
        "guard_control_periods": max_fine_corrections,
        "guard_s": max_fine_corrections * control_period_s,
    }
    return _block(
        name="search_timeout_s",
        value=value,
        formula=TIMEOUT_FORMULA,
        references=sweep_references(bounded_sweep)
        + [_reference("the timing measurements", timing)],
        distribution=distribution,
        margin=margin,
        readback=startup_readback,
    )


def _deadband_records(candidates) -> list[dict]:
    records = _records("deadband_candidates", candidates)
    declared: set[float] = set()
    checked = []
    for record in records:
        value = record.get("center_deadband_px")
        run = record.get("longest_locked_run_frames")
        reversals = record.get("direction_reversals")
        if not _finite(value) or float(value) < 0.0:
            raise ValueError("every deadband candidate declares a non-negative center_deadband_px")
        if type(run) is not int or isinstance(run, bool) or run < 0:
            raise ValueError("every deadband candidate declares its longest locked run in frames")
        if type(reversals) is not int or isinstance(reversals, bool) or reversals < 0:
            raise ValueError("every deadband candidate declares its direction reversal count")
        deadband = float(value)
        if deadband in declared:
            raise ValueError(f"the deadband candidate {deadband} is declared twice")
        declared.add(deadband)
        checked.append(
            {
                "center_deadband_px": deadband,
                "longest_locked_run_frames": run,
                "direction_reversals": reversals,
            }
        )
    return checked


def compute_center_deadband_px(*, camera, candidates, startup_readback=None) -> dict:
    """Start at the jitter in pixels, then take the smallest candidate that locks without oscillating."""

    fov = _number(camera, "the camera measurements", "horizontal_fov_rad", positive=True)
    width = _number(camera, "the camera measurements", "image_width_px", positive=True)
    jitter = _number(camera, "the camera measurements", "centre_jitter_rad", nonnegative=True)
    rad_per_px = fov / width
    jitter_px = jitter / rad_per_px
    start_px = float(math.ceil(jitter_px))
    records = _deadband_records(candidates)
    verdicts: dict[str, dict] = {}
    chosen: float | None = None
    for record in records:
        deadband = record["center_deadband_px"]
        locked = record["longest_locked_run_frames"] >= LOCK_FRAMES
        oscillated = record["direction_reversals"] > 0
        in_range = deadband >= start_px
        stable = in_range and locked and not oscillated
        verdicts[str(deadband)] = {
            "longest_locked_run_frames": record["longest_locked_run_frames"],
            "direction_reversals": record["direction_reversals"],
            "locked_three_consecutive_frames": locked,
            "oscillated": oscillated,
            "in_searched_range": in_range,
            "stable": stable,
            "chosen": False,
        }
        if stable and (chosen is None or deadband < chosen):
            chosen = deadband
    if chosen is None:
        raise _refuse(
            CAL_DEADBAND_OSCILLATES,
            f"no declared deadband at or above the computed start {start_px} px locks for "
            f"{LOCK_FRAMES} consecutive frames without a left-right reversal: "
            f"{json.dumps(verdicts, sort_keys=True)}",
        )
    verdicts[str(chosen)]["chosen"] = True
    distribution = {
        "centre_jitter_rad": jitter,
        "centre_jitter_px": jitter_px,
        "rad_per_px": rad_per_px,
        "start_deadband_px": start_px,
        "candidates": verdicts,
    }
    margin = {
        "start_deadband_px": start_px,
        "chosen_minus_start_px": chosen - start_px,
        "lock_frames_required": LOCK_FRAMES,
    }
    return _block(
        name="center_deadband_px",
        value=float(chosen),
        formula=DEADBAND_FORMULA,
        references=[_reference("the camera measurements", camera)],
        distribution=distribution,
        margin=margin,
        readback=startup_readback,
    )


def compute_vertical_bounds_px(
    *, workspace_projection, camera, detection_extremes=None, startup_readback=None
) -> dict:
    """Project the legal pick workspace into the head camera and intersect the image safety margin.

    Detection extremes are not evidence for this value. There is deliberately no code path that turns
    them into bounds: passing them refuses the phase, whatever else the caller offered.
    """

    if detection_extremes is not None:
        raise _refuse(
            CAL_VERTICAL_BOUNDS_UNPROJECTED,
            "the vertical bounds are the legal pick workspace projected into the head camera; they are "
            "never back-filled from detection extremes, so this phase refuses the detection extremes "
            "instead of using them",
        )
    if not isinstance(workspace_projection, Mapping):
        raise _refuse(
            CAL_VERTICAL_BOUNDS_UNPROJECTED,
            "no workspace projection was measured, and detection extremes are never a substitute for "
            "one, so the vertical bounds cannot be derived",
        )
    top_px = _number(workspace_projection, "the workspace projection", "top_px")
    bottom_px = _number(workspace_projection, "the workspace projection", "bottom_px")
    if top_px >= bottom_px:
        raise ValueError("the workspace projection must record top_px below bottom_px")
    image_height_px = _number(camera, "the camera measurements", "image_height_px", positive=True)
    safety_margin_px = _number(
        camera, "the camera measurements", "safety_margin_px", nonnegative=True
    )
    low = max(top_px, safety_margin_px)
    high = min(bottom_px, image_height_px - safety_margin_px)
    if not 0.0 <= low < high <= image_height_px:
        raise _refuse(
            CAL_VERTICAL_BOUNDS_UNPROJECTED,
            f"the workspace projection [{top_px}, {bottom_px}] does not reach inside the image safety "
            f"margin [{safety_margin_px}, {image_height_px - safety_margin_px}] of a "
            f"{image_height_px} px image, so no vertical bounds can be projected",
        )
    distribution = {
        "workspace_projection_px": [top_px, bottom_px],
        "image_height_px": image_height_px,
        "image_safety_margin_px": safety_margin_px,
        "intersection_px": [low, high],
    }
    margin = {
        "safety_margin_px": safety_margin_px,
        "top_clip_px": low - top_px,
        "bottom_clip_px": bottom_px - high,
        "detections_used": False,
    }
    return _block(
        name="vertical_bounds_px",
        value=[low, high],
        formula=VERTICAL_FORMULA,
        references=[
            _reference("the workspace projection", workspace_projection),
            _reference("the camera measurements", camera),
        ],
        distribution=distribution,
        margin=margin,
        readback=startup_readback,
    )


def compute_max_fine_corrections(
    *, episodes, held_out_splits, bounded_sweep, startup_readback=None
) -> dict:
    """The largest count a successful validation episode needed, plus one recovery allowance."""

    numbers, allowance, safe = _fine_correction_numbers(
        episodes=episodes, held_out_splits=held_out_splits, bounded_sweep=bounded_sweep
    )
    max_needed = max(count for _, count, _, _ in numbers)
    largest_single = max(single for _, _, _, single in numbers)
    value = max_needed + RECOVERY_ALLOWANCE
    budget = value * largest_single
    if budget > allowance:
        raise _refuse(
            CAL_SWEEP_UNSTABLE,
            f"max_fine_corrections {value} could command {budget} rad of fine corrections from a sweep "
            f"stop, which leaves the safe neck interval {list(safe)} whose stops allow only "
            f"{allowance} rad",
        )
    distribution = {
        "successful_episodes": [episode_id for episode_id, _, _, _ in numbers],
        "fine_corrections_by_episode": {episode_id: count for episode_id, count, _, _ in numbers},
        "max_needed_fine_corrections": max_needed,
        "largest_single_correction_rad": largest_single,
        "safe_interval_rad": list(safe),
    }
    margin = {
        "recovery_allowance": RECOVERY_ALLOWANCE,
        "safe_allowance_rad": allowance,
        "budget_rad": budget,
        "headroom_rad": allowance - budget,
    }
    return _block(
        name="max_fine_corrections",
        value=value,
        formula=CORRECTIONS_FORMULA,
        references=[_reference("the sealed geometry", _geometry_of(bounded_sweep))],
        distribution=distribution,
        margin=margin,
        readback=startup_readback,
    )


def compute_max_fine_total_rad(
    *, episodes, held_out_splits, bounded_sweep, startup_readback=None
) -> dict:
    """The largest cumulative correction of the successful episodes plus one largest single margin."""

    numbers, allowance, safe = _fine_correction_numbers(
        episodes=episodes, held_out_splits=held_out_splits, bounded_sweep=bounded_sweep
    )
    cumulative = {episode_id: total for episode_id, _, total, _ in numbers}
    largest_cumulative = max(cumulative.values())
    largest_single = max(single for _, _, _, single in numbers)
    value = largest_cumulative + largest_single
    if value > allowance:
        raise _refuse(
            CAL_SWEEP_UNSTABLE,
            f"max_fine_total_rad {value} rad crosses the safe neck interval {list(safe)}, whose stops "
            f"allow only {allowance} rad of cumulative fine correction",
        )
    distribution = {
        "successful_episodes": list(cumulative),
        "cumulative_fine_correction_rad": cumulative,
        "largest_cumulative_fine_correction_rad": largest_cumulative,
        "largest_single_correction_rad": largest_single,
        "safe_interval_rad": list(safe),
    }
    margin = {
        "observed_largest_single_correction_rad": largest_single,
        "safe_allowance_rad": allowance,
        "headroom_rad": allowance - value,
    }
    return _block(
        name="max_fine_total_rad",
        value=value,
        formula=TOTAL_FORMULA,
        references=[_reference("the sealed geometry", _geometry_of(bounded_sweep))],
        distribution=distribution,
        margin=margin,
        readback=startup_readback,
    )


def _geometry_of(bounded_sweep) -> Mapping:
    """The sealed geometry document the sweep cites; a sweep that cites none is a caller error."""

    sealed = bounded_sweep.get("sealed_geometry") if isinstance(bounded_sweep, Mapping) else None
    if not isinstance(sealed, Mapping):
        raise ValueError(
            "the bounded sweep cites no sealed geometry, so its fine-correction budget has no input "
            "evidence"
        )
    return sealed


def _coarse_step_parameter(
    *, bounded_sweep, observations, selected_weights_sha256=None, startup_readback=None
) -> tuple[dict, dict]:
    """The sixth parameter this phase owns: the step the declared val sweep supports and its evidence.

    The measurement and its rules live in `head_search_coarse_step_measurement`, which validates the raw
    sweep against the sealed geometry, matches the detections itself and refuses missing, partial or
    contradictory evidence. What this phase adds is the ownership check the runtime contract implies: the
    bounded sweep phase 2 receipted is the sweep every neck target of this run binds to, so a val sweep
    that supports a *different* step leaves those receipts vouching for a step the run does not use - that
    is refused with this phase's own `CAL_SWEEP_UNSTABLE` rather than shipped.
    """

    geometry = bounded_sweep.get("geometry") if isinstance(bounded_sweep, Mapping) else None
    if not isinstance(geometry, Mapping):
        raise _refuse(
            CAL_SWEEP_UNSTABLE,
            "the bounded sweep records no sealed geometry, so the val sweep cannot be checked against the "
            "one the run sealed",
        )
    try:
        measurement = validate_head_search_coarse_step_measurement(
            geometry=geometry,
            observations=observations,
            selected_weights_sha256=selected_weights_sha256,
            startup_readback=startup_readback,
        )
    except CalibrationCoarseStepRefused as error:
        # the parameter is this phase's, so the refusal is too: same code, this phase's class
        raise _refuse(error.code, error.detail) from error
    block = measurement["parameter_evidence"][COARSE_STEP_PARAMETER]
    if tuple(block) != PARAMETER_EVIDENCE_KEYS:
        raise ValueError(
            f"the val sweep's evidence block is not the one phase 8 requires: {list(block)}"
        )
    if block["unit"] != COARSE_STEP_UNIT:
        raise ValueError(
            f"the val sweep records the unit {block['unit']!r}, not {COARSE_STEP_UNIT!r}"
        )
    if not _finite(block["value"]) or float(block["value"]) <= 0.0:
        raise ValueError("the val sweep chose no positive finite coarse step")
    receipted = (
        bounded_sweep.get("chosen_candidate_rad") if isinstance(bounded_sweep, Mapping) else None
    )
    if not _finite(receipted):
        raise _refuse(
            CAL_SWEEP_UNSTABLE,
            "the val sweep supports a coarse step, but the bounded sweep records no receipted candidate "
            "step for it to match: every neck target's sweep-check receipt binds the step the run uses",
        )
    if abs(float(receipted) - float(block["value"])) > 1e-12:
        raise _refuse(
            CAL_SWEEP_UNSTABLE,
            f"the val sweep supports the coarse step {block['value']!r} but phase 2 receipted "
            f"{float(receipted)!r}: the sweep-check receipts would vouch for a step this run does not use",
        )
    return dict(block), measurement


def validate_head_search_calibration_search_parameters(
    *,
    bounded_sweep,
    timing,
    camera,
    deadband_candidates,
    workspace_projection,
    fine_correction_episodes,
    held_out_splits,
    coarse_step_observations=None,
    selected_weights_sha256=None,
    startup_readbacks=None,
    detection_extremes=None,
    output_path=None,
) -> dict:
    """Produce phase 6's document: the parameters it owns, each with the evidence phase 8 consumes.

    The fine-correction numbers are computed first because the timeout is guarded by them, and their
    split isolation is checked before any of the five is built, so a calibration frame offered to the
    held-out numbers refuses the phase with phase 3's own `CAL_SPLIT_LEAK`. Every refusal stops the
    phase before a value is produced. When the run declares the raw val sweep, its chosen
    ``coarse_step_rad`` joins them with its own evidence block and the ownership check above; without one
    the phase records the deliberately uncomputed parameter instead. When `output_path` is given the phase
    document is written there and nowhere else; without it the phase writes nothing at all.
    """

    if startup_readbacks is not None and not isinstance(startup_readbacks, Mapping):
        raise ValueError("startup_readbacks must map each parameter to its observed readback")

    def readback(name: str):
        return None if startup_readbacks is None else startup_readbacks.get(name)

    max_fine_corrections = compute_max_fine_corrections(
        episodes=fine_correction_episodes,
        held_out_splits=held_out_splits,
        bounded_sweep=bounded_sweep,
        startup_readback=readback("max_fine_corrections"),
    )
    max_fine_total_rad = compute_max_fine_total_rad(
        episodes=fine_correction_episodes,
        held_out_splits=held_out_splits,
        bounded_sweep=bounded_sweep,
        startup_readback=readback("max_fine_total_rad"),
    )
    parameters = {
        "search_timeout_s": compute_search_timeout_s(
            bounded_sweep=bounded_sweep,
            timing=timing,
            max_fine_corrections=max_fine_corrections["value"],
            startup_readback=readback("search_timeout_s"),
        ),
        "center_deadband_px": compute_center_deadband_px(
            camera=camera,
            candidates=deadband_candidates,
            startup_readback=readback("center_deadband_px"),
        ),
        "vertical_bounds_px": compute_vertical_bounds_px(
            workspace_projection=workspace_projection,
            camera=camera,
            detection_extremes=detection_extremes,
            startup_readback=readback("vertical_bounds_px"),
        ),
        "max_fine_corrections": max_fine_corrections,
        "max_fine_total_rad": max_fine_total_rad,
    }
    measurement = None
    names = list(PARAMETERS)
    if coarse_step_observations is not None:
        block, measurement = _coarse_step_parameter(
            bounded_sweep=bounded_sweep,
            observations=coarse_step_observations,
            selected_weights_sha256=selected_weights_sha256,
            startup_readback=readback(COARSE_STEP_PARAMETER),
        )
        parameters[COARSE_STEP_PARAMETER] = block
        names = [COARSE_STEP_PARAMETER, *PARAMETERS]
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "parameter_names": names,
        "parameters": {name: parameters[name] for name in names},
        "parameters_complete": True,
        "uncomputed_parameter": None if measurement is not None else dict(UNCOMPUTED_PARAMETER),
        "coarse_step_measurement": measurement,
        "motion_commanded": False,
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document
