"""The qualification items and scenarios, expected terminals and the frame cadence check."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from so101_demo.act.head_search.fine_correction_episodes.episode import (
    cup_count_for_condition_class,
)
from so101_demo.act.head_search.scenarios.contracts import (
    _CADENCE_TOLERANCE_S,
    CAL_SCENARIO_SPLIT_LEAK,
    EXPECTED_TERMINALS,
    INTERRUPTION_CLASSES,
    QUALIFICATION_SPLIT,
    _partitions_document,
    _refuse,
)
from so101_demo.act.head_search.timing_measurement.contracts import (
    CAL_TIMING_EVIDENCE_MISSING,
    FRAME_RATE_HZ,
    _finite,
)


def qualification_items(partitions) -> list[dict]:
    """Every declared qualification item, in declaration order, or the refusal that stops the producer."""

    document = _partitions_document(partitions)
    declared = document.get(QUALIFICATION_SPLIT)
    if (
        isinstance(declared, (str, bytes))
        or not isinstance(declared, Sequence)
        or not declared
    ):
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the scenario partitions declare no {QUALIFICATION_SPLIT!r} list, so the forty qualification "
            f"scenarios are not declared anywhere",
        )
    items: list[dict] = []
    seen: set[int] = set()
    for position, item in enumerate(declared):
        if not isinstance(item, Mapping):
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"qualification item {position} is not a document, so its seed, condition class and anchor "
                f"are not declared",
            )
        seed = item.get("seed")
        if type(seed) is not int or isinstance(seed, bool):
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"qualification item {position} declares the seed {seed!r}, which is not a whole number",
            )
        if seed in seen:
            raise ValueError(f"the qualification seed {seed} is declared twice")
        seen.add(seed)
        condition_class = item.get("condition_class")
        anchor = item.get("anchor")
        if type(condition_class) is not str or not condition_class:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"qualification item {position} (seed {seed}) declares no condition class",
            )
        if type(anchor) is not str or not anchor:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"qualification item {position} (seed {seed}) declares no anchor",
            )
        items.append(
            {
                "seed": seed,
                "scene_group_id": str(item.get("scene_group_id", "")),
                "condition_class": condition_class,
                "anchor": anchor,
            }
        )
    return items


def qualification_scenarios(partitions, *, seeds=None) -> list[dict]:
    """The declared qualification items, restricted to a declared subset, or the refusal that stops it.

    The partitions are the single tracked source of the head-search seed partitions, so a seed of another
    split - a calibration seed in particular - is refused rather than qualified: the qualification scenes
    are never the scenes the seventeen values were calibrated on.
    """

    document = _partitions_document(partitions)
    declared = qualification_items(document)
    if seeds is None:
        return declared
    by_seed = {item["seed"]: item for item in declared}
    other = {
        str(name): {int(seed) for seed in value if type(seed) is int and not isinstance(seed, bool)}
        for name, value in document.items()
        if name != QUALIFICATION_SPLIT
        and isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and value
        and all(type(seed) is int and not isinstance(seed, bool) for seed in value)
    }
    chosen: list[dict] = []
    offered: set[int] = set()
    for seed in seeds:
        if type(seed) is not int or isinstance(seed, bool):
            raise ValueError(f"every declared seed must be a whole number: {seed!r}")
        if seed in offered:
            raise ValueError(f"the seed {seed} is declared twice")
        offered.add(seed)
        if seed in by_seed:
            chosen.append(by_seed[seed])
            continue
        for name, members in other.items():
            if seed in members:
                raise _refuse(
                    CAL_SCENARIO_SPLIT_LEAK,
                    f"the seed {seed} belongs to the {name!r} split, which may never be qualified: only "
                    f"the declared {QUALIFICATION_SPLIT!r} items may, because the qualification scenes are "
                    f"never the scenes the seventeen values were calibrated on",
                )
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the seed {seed} belongs to no split of the scenario partitions, so the scene it would "
            f"prepare is not a declared one",
        )
    if not chosen:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "no declared qualification item was offered, so this producer would carry no scenario at all",
        )
    return chosen


def expected_terminals(condition_class: str) -> tuple[str, ...]:
    """The terminal statuses the plan declares for one condition class, and nothing this module chose.

    The plan's scenario rule: "Legal single cup ends ``TARGET_LOCKED``; two cups end ``TARGET_AMBIGUOUS``; no
    cup ends ``TARGET_NOT_FOUND`` only with complete coverage". A class the plan does not name refuses,
    because a scenario whose expected outcome is undeclared cannot be judged.
    """

    if type(condition_class) is not str or condition_class not in EXPECTED_TERMINALS:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the condition class {condition_class!r} declares no expected terminal status in the plan's "
            f"scenario rule, so a scenario of that class cannot be judged; the declared classes are "
            f"{sorted(EXPECTED_TERMINALS)}",
        )
    return tuple(EXPECTED_TERMINALS[condition_class])


def requires_interruption(condition_class: str) -> bool:
    """Whether the plan declares this class as interrupted input that has to reacquire."""

    return condition_class in INTERRUPTION_CLASSES


def declared_cup_count(condition_class: str) -> int:
    """How many cups the recorder's own convention places in one class's scene."""

    return cup_count_for_condition_class(condition_class)


def check_frame_cadence(
    frames, *, frame_period_s: float, max_settle_s: float, tolerance_s: float = _CADENCE_TOLERANCE_S
) -> dict:
    """One attempt's frames against the declared frame contract, or the numbers that say why not.

    The contract is the design's 10 Hz: a frame is produced at most once per declared frame period of
    simulation time and never before the commanded target has settled, so the achieved interval is that
    settle time plus the remainder that carries the loop to the next frame boundary. The check therefore
    refuses a **duplicate** stamp (no interval at all), a **backward** stamp (a frame older than its
    predecessor), a frame faster than the declared period (``too_fast``), and a gap larger than the
    settle budget plus one frame period, which no declared settle can produce (``undeclared_gap``).
    """

    if not _finite(frame_period_s) or float(frame_period_s) <= 0.0:
        raise ValueError("the frame cadence needs a positive finite frame period")
    if not _finite(max_settle_s) or float(max_settle_s) <= 0.0:
        raise ValueError("the frame cadence needs a positive finite settle budget")
    period = float(frame_period_s)
    if not math.isclose(FRAME_RATE_HZ, 1.0 / period, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(
            f"the frame cadence is checked against {1.0 / period} Hz, but the design fixes the "
            f"{FRAME_RATE_HZ} Hz frame contract"
        )
    if isinstance(frames, (str, bytes)) or not isinstance(frames, Sequence):
        raise ValueError("the frames of one attempt must be a sequence")

    intervals: list[float | None] = []
    duplicate = backward = too_fast = undeclared_gap = gap = 0
    previous = None
    for index, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            raise ValueError("every recorded frame must be a mapping")
        stamp = frame.get("frame_sim_s")
        if not _finite(stamp):
            raise ValueError(f"frame {index} records no finite frame_sim_s")
        stamp = float(stamp)
        if previous is None:
            intervals.append(None)
            previous = stamp
            continue
        interval = stamp - previous
        intervals.append(interval)
        if interval < -tolerance_s:
            backward += 1
        elif abs(interval) <= tolerance_s:
            duplicate += 1
        elif interval < period - tolerance_s:
            too_fast += 1
        elif interval > max_settle_s + period + tolerance_s:
            undeclared_gap += 1
        elif interval > period + tolerance_s:
            gap += 1
        previous = stamp

    measured = [value for value in intervals if value is not None]
    span = None if len(frames) < 2 else float(frames[-1]["frame_sim_s"]) - float(frames[0]["frame_sim_s"])
    achieved = None if not span or span <= 0.0 else len(measured) / span
    continuous = not (duplicate or backward or too_fast or undeclared_gap)
    return {
        "frame_rate_hz": FRAME_RATE_HZ,
        "frame_period_s": period,
        "max_settle_s": float(max_settle_s),
        "tolerance_s": float(tolerance_s),
        "frame_count": len(frames),
        "interval_count": len(measured),
        "intervals_s": measured,
        "min_interval_s": min(measured) if measured else None,
        "max_interval_s": max(measured) if measured else None,
        "span_s": span,
        "achieved_rate_hz": achieved,
        "duplicate_count": duplicate,
        "backward_count": backward,
        "too_fast_count": too_fast,
        "gap_count": gap,
        "undeclared_gap_count": undeclared_gap,
        "continuous": continuous,
        "definition": (
            "a frame is produced at most once per declared frame period of simulation time and never "
            "before the commanded target has settled, so the achieved interval between two frames is that "
            "settle time plus the remainder that carries the loop to the next frame boundary; a duplicate, "
            "a backward stamp, an interval shorter than the frame period or one longer than the settle "
            "budget plus one frame period all violate the contract"
        ),
    }


#: how many held samples the stop proof may spend before it must have three consecutive qualifying ones
STOP_PROOF_WINDOW = 6


SETTLE_PROOF_DEFINITION = (
    "a commanded stop is settled when the neck reached its target inside goal_tolerance_rad and held a "
    "velocity at or below the controller's declared settle_velocity_rad_s for settle_consecutive_steps "
    "consecutive control steps, which is the rule the plant's own settle tracker applies and the rule the "
    "timing measurement's classify_stop refuses an unsettled stop on"
)
