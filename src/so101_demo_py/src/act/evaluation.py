"""Task 16: summarise runs without letting a search failure disappear from the denominator.

The end-to-end rate counts every attempted run, including the ones whose search never locked — a rate that
quietly excluded them would improve as the search got worse. The locked rate answers the narrower question,
and reports nothing rather than a perfect score when no run ever locked.
"""

from __future__ import annotations

import math

RUN_KEYS = frozenset({"search_locked", "done", "interventions", "elapsed_wall_s"})
WALL_BUDGET_S = 120.0


def _run(row) -> dict:
    if not isinstance(row, dict) or set(row) != RUN_KEYS:
        raise ValueError("RUN_RESULT_INVALID")
    for field in ("search_locked", "done"):
        if type(row[field]) is not bool:
            raise ValueError("RUN_RESULT_INVALID")
    if type(row["interventions"]) is not int or row["interventions"] < 0:
        raise ValueError("RUN_RESULT_INVALID")
    elapsed = row["elapsed_wall_s"]
    malformed = (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
                 or not math.isfinite(elapsed) or elapsed < 0)
    if malformed:
        raise ValueError("RUN_RESULT_INVALID")
    return {"search_locked": row["search_locked"], "done": row["done"],
            "interventions": row["interventions"], "elapsed_wall_s": float(elapsed)}


def summarize(results: list) -> dict:
    """Per-route summary: end-to-end success, locked success, interventions and the wall budget."""

    if not isinstance(results, (list, tuple)) or not results:
        raise ValueError("EVALUATION_EMPTY")
    runs = [_run(row) for row in results]
    total = len(runs)
    successes = [run for run in runs if run["done"]]
    locked = [run for run in runs if run["search_locked"]]
    locked_successes = [run for run in locked if run["done"]]
    elapsed = sorted(run["elapsed_wall_s"] for run in runs)
    return {"runs": total,
            "end_to_end": len(successes) / total,
            "end_to_end_success": len(successes),
            "locked_denominator": len(locked),
            # a rate over no locked runs is undefined, and reporting 1.0 there would flatter the route
            "locked_success": (len(locked_successes) / len(locked)) if locked else None,
            "interventions_total": sum(run["interventions"] for run in runs),
            "interventions_runs": sum(1 for run in runs if run["interventions"] > 0),
            "elapsed_wall_s": {"min": elapsed[0], "median": elapsed[len(elapsed) // 2],
                               "max": elapsed[-1]},
            "budget_violations": sum(1 for run in runs if run["elapsed_wall_s"] > WALL_BUDGET_S),
            "wall_budget_s": WALL_BUDGET_S}
