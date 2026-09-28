"""Task 16: a search failure stays in the denominator, and no locked runs means no locked rate."""

import pytest

from so101_demo.act.evaluation import WALL_BUDGET_S, summarize


def test_search_failure_remains_in_denominator():
    runs = [{"search_locked": False, "done": False, "interventions": 0, "elapsed_wall_s": 1.},
            {"search_locked": True, "done": True, "interventions": 0, "elapsed_wall_s": 119.}]
    report = summarize(runs)
    assert report["end_to_end"] == .5
    assert report["locked_denominator"] == 1
    assert report["locked_success"] == 1.


def test_interventions_and_the_wall_budget_are_reported_per_route():
    report = summarize([
        {"search_locked": True, "done": True, "interventions": 2, "elapsed_wall_s": 121.},
        {"search_locked": True, "done": False, "interventions": 0, "elapsed_wall_s": 10.},
        {"search_locked": False, "done": False, "interventions": 1, "elapsed_wall_s": 30.}])
    assert report["runs"] == 3
    assert report["end_to_end"] == pytest.approx(1 / 3)
    assert report["interventions_total"] == 3 and report["interventions_runs"] == 2
    assert report["budget_violations"] == 1 and report["wall_budget_s"] == WALL_BUDGET_S
    assert report["elapsed_wall_s"] == {"min": 10.0, "median": 30.0, "max": 121.0}


def test_a_route_that_never_locked_reports_no_rate_rather_than_a_perfect_one():
    report = summarize([{"search_locked": False, "done": False, "interventions": 0,
                         "elapsed_wall_s": 5.}])
    assert report["locked_denominator"] == 0 and report["locked_success"] is None
    assert report["end_to_end"] == 0.0


def test_empty_or_malformed_runs_are_refused_rather_than_summarised():
    with pytest.raises(ValueError, match="EVALUATION_EMPTY"):
        summarize([])
    for bad in ({"search_locked": True}, "run", 1,
                {"search_locked": "yes", "done": True, "interventions": 0, "elapsed_wall_s": 1.},
                {"search_locked": True, "done": True, "interventions": -1, "elapsed_wall_s": 1.},
                {"search_locked": True, "done": True, "interventions": 0, "elapsed_wall_s": float("nan")},
                {"search_locked": True, "done": True, "interventions": 0, "elapsed_wall_s": True}):
        with pytest.raises(ValueError, match="RUN_RESULT_INVALID"):
            summarize([bad])
