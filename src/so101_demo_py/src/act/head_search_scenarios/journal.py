"""Scenario journal entries and the aggregate over all scenarios."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from so101_demo.act.head_search_scenarios.contracts import (
    CAL_SCENARIO_UNEXPECTED_LOCK,
    FAILED,
    PASSED,
    QUALIFICATION_FIT_WARNING,
    REFUSED,
)
from so101_demo.act.head_search_timing_measurement.contracts import (
    _finite,
)

#: exactly the keys one journal entry carries, and nothing else
JOURNAL_KEYS = (
    "scenario_index",
    "seed",
    "scene_group_id",
    "condition_class",
    "anchor",
    "cup_count",
    "scenario_name",
    "expected_terminals",
    "outcome",
    "outcome_code",
    "outcome_detail",
    "terminal_status",
    "found",
    "locked",
    "locked_neck_rad",
    "cup_found",
    "detection_frames",
    "frame_count",
    "plan_moves",
    "fine_corrections",
    "fine_corrections_rad",
    "cumulative_fine_correction_rad",
    "largest_single_correction_rad",
    "coverage",
    "stop_proof",
    "frame_cadence",
    "attempt_ids",
    "attempt_summaries",
    "evidence",
)


def scenario_journal_entry(entry: Mapping) -> dict:
    """One scenario's journal row: exactly :data:`JOURNAL_KEYS`, and nothing else.

    The full entry (with its frames and stops) stays in the per-scenario evidence document; the journal is
    the row a reviewer reads one scenario at a time, so it carries the outcome, the numbers and the
    evidence that reproduces it, and never a number the scenario did not measure.
    """

    if not isinstance(entry, Mapping):
        raise ValueError("a scenario entry must be a mapping")
    missing = [key for key in JOURNAL_KEYS if key != "attempt_summaries" and key not in entry]
    if missing:
        raise ValueError(f"the scenario entry carries no {missing}, so it is not a journal entry")
    summaries = []
    for attempt in entry.get("attempts") or ():
        if not isinstance(attempt, Mapping):
            continue
        summaries.append(
            {
                key: attempt.get(key)
                for key in (
                    "index",
                    "attempt_id",
                    "frame_count",
                    "detection_frames",
                    "terminal_status",
                    "found",
                    "stop",
                    "stop_status",
                    "interruption_injected",
                    "interruption_decision_status",
                    "lock_count_before_interruption",
                    "lock_count_after_interruption",
                    "lock_count_cleared_by_interruption",
                    "track_after_interruption",
                    "track_cleared_by_controller",
                    "detector_reset_before_attempt",
                    "fine_corrections",
                    "cumulative_fine_correction_rad",
                    "controller_fine_count",
                    "controller_fine_angle_rad",
                    "corrections_match_controller",
                    "refusal",
                )
            }
        )
    row = {key: entry[key] for key in JOURNAL_KEYS if key != "attempt_summaries"}
    row["attempt_summaries"] = summaries
    return {key: row[key] for key in JOURNAL_KEYS}


def aggregate_scenarios(entries) -> dict:
    """Count every outcome per condition class and per anchor, and never claim the verdict.

    The passed, failed and refused counts are the honest aggregate; the qualification verdict belongs to
    the qualifier's ``aggregate`` phase (``head_search_qualification.RUN_PHASES``), which this round does
    not implement, so this document carries ``qualification_verdict: null`` and names its owner.
    """

    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        raise ValueError("the aggregate needs the sequence of journaled scenarios")
    by_condition_class: dict[str, dict] = {}
    by_anchor: dict[str, dict] = {}
    wrong_locks: list[dict] = []
    corrections: list[int] = []
    cumulative: list[float] = []
    cadence_ok = True
    stops_ok = True
    terminals: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("every journaled scenario must be a mapping")
        condition_class = str(entry.get("condition_class"))
        anchor = str(entry.get("anchor"))
        outcome = str(entry.get("outcome"))
        terminal = entry.get("terminal_status")
        if terminal is not None:
            terminals[str(terminal)] = terminals.get(str(terminal), 0) + 1
        for table, key in ((by_condition_class, condition_class), (by_anchor, anchor)):
            bucket = table.setdefault(
                key,
                {"total": 0, "passed": 0, "failed": 0, "refused": 0, "terminal_statuses": {}},
            )
            bucket["total"] += 1
            bucket[outcome.lower()] = bucket.get(outcome.lower(), 0) + 1
            if terminal is not None:
                bucket["terminal_statuses"][str(terminal)] = (
                    bucket["terminal_statuses"].get(str(terminal), 0) + 1
                )
        if entry.get("outcome_code") == CAL_SCENARIO_UNEXPECTED_LOCK:
            wrong_locks.append(
                {
                    "seed": entry.get("seed"),
                    "condition_class": condition_class,
                    "anchor": anchor,
                }
            )
        value = entry.get("fine_corrections")
        if type(value) is int and not isinstance(value, bool):
            corrections.append(value)
        total = entry.get("cumulative_fine_correction_rad")
        if _finite(total):
            cumulative.append(float(total))
        cadence = entry.get("frame_cadence")
        if not isinstance(cadence, Mapping) or cadence.get("continuous") is not True:
            cadence_ok = False
        proof = entry.get("stop_proof")
        if not isinstance(proof, Mapping) or proof.get("proven") is not True:
            stops_ok = False
    passed = sum(1 for entry in entries if entry.get("outcome") == PASSED)
    failed = sum(1 for entry in entries if entry.get("outcome") == FAILED)
    refused = sum(1 for entry in entries if entry.get("outcome") == REFUSED)
    return {
        "scenario_count": len(entries),
        "passed_count": passed,
        "failed_count": failed,
        "refused_count": refused,
        "by_condition_class": by_condition_class,
        "by_anchor": by_anchor,
        "terminal_statuses": terminals,
        "zero_wrong_locks": not wrong_locks,
        "wrong_locks": wrong_locks,
        "fine_corrections": {
            "min": min(corrections) if corrections else None,
            "max": max(corrections) if corrections else None,
            "observed_on": len(corrections),
        },
        "cumulative_fine_correction_rad": {
            "min": min(cumulative) if cumulative else None,
            "max": max(cumulative) if cumulative else None,
            "observed_on": len(cumulative),
        },
        "cadence_all_continuous": cadence_ok,
        "stop_proofs_all_proven": stops_ok,
        "qualification_verdict": None,
        "qualification_verdict_owner": (
            "so101_demo.act.head_search_qualification (the qualifier's `aggregate` phase), which consumes "
            "the smoke, the forty scenarios and the three anchor restarts together; this document is the "
            "`scenarios` phase's own evidence and publishes no verdict"
        ),
        "fit_warning": QUALIFICATION_FIT_WARNING,
    }
