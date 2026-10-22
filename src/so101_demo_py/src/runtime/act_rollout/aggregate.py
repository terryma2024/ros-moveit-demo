"""The run's results: `summary.json` and `table.md`, the point x trial x verdict view of the TRAIN-006 rollout table.

A (point, trial) has one or more attempts: the first, and one more for each INVALID attempt that was run again. The last attempt
decides the cell; every INVALID attempt is counted apart from the policy's results (`valid` counts DONE, FAILED and NO_MOTION only),
as in the native command's `invalid-runs.jsonl`. A cell whose attempts are all INVALID, or that was never run, is not a result.
"""

from __future__ import annotations

from so101_demo.runtime.act_rollout.plan import FINAL_VERDICTS

NOT_RUN = "NOT_RUN"


def cell_verdict(attempts) -> str:
    """The verdict of a (point, trial): its last attempt, INVALID when none gave a result, NOT_RUN when none was made."""
    if not attempts:
        return NOT_RUN
    return attempts[-1]["verdict"]


def point_counts(trials) -> dict:
    """`{done, valid, invalid_attempts, trials, cells}` of one point over its trials (a list of attempt lists)."""
    done = valid = invalid = 0
    for attempts in trials:
        invalid += sum(1 for attempt in attempts if attempt["verdict"] == "INVALID")
        final = cell_verdict(attempts)
        if final in FINAL_VERDICTS:
            valid += 1
            done += 1 if final == "DONE" else 0
    return {"done": done, "valid": valid, "invalid_attempts": invalid, "trials": len(trials)}


def build_summary(*, run_id, group, points, trials, attempts, header) -> dict:
    """`attempts` maps `(point, trial)` to its attempts in order; `header` carries the run's identity and runtime values."""
    per_point = {}
    for point in points:
        cells = [list(attempts.get((point, trial), ())) for trial in range(1, trials + 1)]
        per_point[point] = dict(point_counts(cells), verdicts=[cell_verdict(cell) for cell in cells])
    units = [dict(point_id=point, trial=trial, final_verdict=cell_verdict(attempts.get((point, trial), ())),
                  attempts=list(attempts.get((point, trial), ())))
             for trial in range(1, trials + 1) for point in points]
    totals = dict(done=sum(item["done"] for item in per_point.values()), valid=sum(item["valid"] for item in per_point.values()),
                  invalid_attempts=sum(item["invalid_attempts"] for item in per_point.values()),
                  invalid_exhausted=sum(1 for unit in units if unit["final_verdict"] == "INVALID"),
                  not_run=sum(1 for unit in units if unit["final_verdict"] == NOT_RUN), units=len(units))
    return dict(header, schema_version=1, kind="ACT_ROLLOUT_PARALLEL_SUMMARY", run_id=run_id, group=group, points=list(points),
                trials=trials, per_point=per_point, totals=totals, units=units)


def render_table(summary: dict) -> str:
    """The markdown view: the point x trial grid, the per-point counts, then the failures and the INVALID attempts."""
    points, trials = summary["points"], summary["trials"]
    columns = " | ".join(f"t{trial}" for trial in range(1, trials + 1))
    lines = [f"| point | DONE / valid (INVALID attempts) | {columns} |", "|---|---|" + "---|" * trials]
    for point in points:
        item = summary["per_point"][point]
        cells = " | ".join(item["verdicts"])
        lines.append(f"| {point} | {item['done']} / {item['valid']} ({item['invalid_attempts']}) | {cells} |")
    totals = summary["totals"]
    lines += ["", f"Totals: {totals['done']} DONE of {totals['valid']} valid attempts over {totals['units']} (point, trial) cells; "
                  f"{totals['invalid_attempts']} INVALID attempts, {totals['invalid_exhausted']} cells never gave a result, "
                  f"{totals['not_run']} never run.", ""]
    failures, invalid = [], []
    for unit in summary["units"]:
        for attempt in unit["attempts"]:
            label = f"t{unit['trial']} {unit['point_id']} (attempt {attempt['attempt_number']})"
            if attempt["verdict"] == "INVALID":
                invalid.append(f"- {label}: {attempt.get('reason')}")
            elif attempt["verdict"] in ("FAILED", "NO_MOTION"):
                motion = attempt.get("max_arm_displacement_rad")
                failures.append(f"- {label}: {attempt.get('reason')} | max arm displacement "
                                f"{'-' if motion is None else format(motion, '.3f')} rad")
    if failures:
        lines += ["Failures (trial, point: reason | max arm displacement):", *failures, ""]
    done = [f"- t{unit['trial']} {unit['point_id']}: attempt {attempt['attempt_number']}, wall {attempt.get('elapsed_wall_s')} s"
            for unit in summary["units"] for attempt in unit["attempts"] if attempt["verdict"] == "DONE"]
    if done:
        lines += ["DONE episodes:", *done, ""]
    if invalid:
        lines += ["INVALID attempts (infrastructure faults, not policy results):", *invalid, ""]
    return "\n".join(lines).rstrip() + "\n"
