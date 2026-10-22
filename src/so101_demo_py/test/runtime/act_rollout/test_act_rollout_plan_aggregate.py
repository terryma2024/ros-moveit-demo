"""The work queue and the results view of a parallel rollout (pure, no process)."""

import pytest

from so101_demo.runtime.act_rollout import aggregate
from so101_demo.runtime.act_rollout.plan import Unit, build_units, checked

SCENES = {"groups": {"rollout_standard": [{"scene_id": "task_start"}, {"scene_id": "forward_5cm"}, {"scene_id": "left_5cm"}],
                     "rollout_test": [{"scene_id": "t1"}]}}


def test_the_queue_is_trial_major_with_the_first_attempt_of_every_point():
    units = build_units(SCENES, group="rollout_standard", scene_ids=None, trials=2)
    assert [unit.unit_id for unit in units] == ["task_start-t1-a1", "forward_5cm-t1-a1", "left_5cm-t1-a1",
                                                "task_start-t2-a1", "forward_5cm-t2-a1", "left_5cm-t2-a1"]
    assert {unit.group for unit in units} == {"rollout_standard"} and units[0].key == ("task_start", 1)


def test_scene_selection_and_limit_follow_the_native_commands_rules():
    units = build_units(SCENES, group="rollout_standard", scene_ids=["left_5cm", "task_start"], trials=1)
    assert [unit.point_id for unit in units] == ["left_5cm", "task_start"]
    assert [unit.point_id for unit in build_units(SCENES, group="rollout_standard", scene_ids=None, trials=1, limit=2)] == [
        "task_start", "forward_5cm"]
    with pytest.raises(ValueError, match="ROLLOUT_SCENE_UNKNOWN"):
        build_units(SCENES, group="rollout_standard", scene_ids=["nowhere"], trials=1)
    with pytest.raises(ValueError, match="ROLLOUT_GROUP_UNKNOWN"):
        build_units(SCENES, group="rollout_validation", scene_ids=None, trials=1)
    with pytest.raises(ValueError, match="ROLLOUT_TRIALS_INVALID"):
        build_units(SCENES, group="rollout_standard", scene_ids=None, trials=0)


def test_a_retry_is_the_same_point_and_trial_with_the_next_attempt():
    unit = Unit("forward_5cm", "rollout_standard", 3)
    again = unit.retry()
    assert again.unit_id == "forward_5cm-t3-a2" and again.key == unit.key and again.attempt_number == 2


def test_an_identifier_the_instance_would_refuse_is_refused_before_anything_starts():
    with pytest.raises(ValueError, match="ROLLOUT_UNIT_ID_INVALID"):
        checked(Unit("x" * 70, "rollout_standard", 1))
    long_scenes = {"groups": {"rollout_standard": [{"scene_id": "p" * 58}]}}       # fits as a1 (64 characters), not as a21
    with pytest.raises(ValueError, match="ROLLOUT_UNIT_ID_INVALID"):
        build_units(long_scenes, group="rollout_standard", scene_ids=None, trials=1, max_invalid_retries=20)
    with pytest.raises(ValueError, match="ROLLOUT_UNIT_ID_INVALID"):
        checked(Unit("bad id", "rollout_standard", 1))


def attempt(number, verdict, reason=None, **fields):
    return dict(attempt_number=number, verdict=verdict, reason=reason, **fields)


def summary(attempts, points=("task_start", "forward_5cm"), trials=2):
    return aggregate.build_summary(run_id="run-1", group="rollout_standard", points=points, trials=trials, attempts=attempts,
                                   header={"runtime": {"shards": 4}})


def test_the_last_attempt_decides_the_cell_and_invalid_attempts_are_counted_apart():
    attempts = {("task_start", 1): [attempt(1, "INVALID", "CONTROLLER_PAIR_FAILED"), attempt(2, "DONE", elapsed_wall_s=200.5)],
                ("task_start", 2): [attempt(1, "FAILED", "FINAL_XY_OUT_OF_TOLERANCE", max_arm_displacement_rad=1.25)],
                ("forward_5cm", 1): [attempt(1, "INVALID", "A"), attempt(2, "INVALID", "B")],
                ("forward_5cm", 2): [attempt(1, "NO_MOTION", "NO_MOTION", max_arm_displacement_rad=0.0)]}
    result = summary(attempts)
    assert result["per_point"]["task_start"] == {"done": 1, "valid": 2, "invalid_attempts": 1, "trials": 2,
                                                 "verdicts": ["DONE", "FAILED"]}
    assert result["per_point"]["forward_5cm"] == {"done": 0, "valid": 1, "invalid_attempts": 2, "trials": 2,
                                                  "verdicts": ["INVALID", "NO_MOTION"]}
    assert result["totals"] == {"done": 1, "valid": 3, "invalid_attempts": 3, "invalid_exhausted": 1, "not_run": 0, "units": 4}
    assert result["kind"] == "ACT_ROLLOUT_PARALLEL_SUMMARY" and result["runtime"] == {"shards": 4}
    assert [unit["final_verdict"] for unit in result["units"]] == ["DONE", "INVALID", "FAILED", "NO_MOTION"]   # trial-major


def test_a_cell_that_was_never_run_is_not_run_and_not_a_result():
    result = summary({("task_start", 1): [attempt(1, "DONE")]})
    assert result["per_point"]["task_start"]["verdicts"] == ["DONE", "NOT_RUN"]
    assert result["totals"]["not_run"] == 3 and result["totals"]["valid"] == 1


def test_the_table_has_the_trial6_matrix_then_failures_done_episodes_and_invalid_attempts():
    attempts = {("task_start", 1): [attempt(1, "INVALID", "goal response timeout"), attempt(2, "DONE", elapsed_wall_s=181.25)],
                ("task_start", 2): [attempt(1, "FAILED", "FINAL_XY_OUT_OF_TOLERANCE", max_arm_displacement_rad=1.2345)],
                ("forward_5cm", 1): [attempt(1, "DONE", elapsed_wall_s=190.0)],
                ("forward_5cm", 2): [attempt(1, "NO_MOTION", "NO_MOTION", max_arm_displacement_rad=None)]}
    lines = aggregate.render_table(summary(attempts)).splitlines()
    assert lines[0] == "| point | DONE / valid (INVALID attempts) | t1 | t2 |"
    assert lines[1] == "|---|---|---|---|"
    assert lines[2] == "| task_start | 1 / 2 (1) | DONE | FAILED |"
    assert lines[3] == "| forward_5cm | 1 / 2 (0) | DONE | NO_MOTION |"
    text = "\n".join(lines)
    assert "Totals: 2 DONE of 4 valid attempts over 4 (point, trial) cells; 1 INVALID attempts, 0 cells never gave a result" in text
    assert "- t2 task_start (attempt 1): FINAL_XY_OUT_OF_TOLERANCE | max arm displacement 1.234 rad" in text
    assert "- t2 forward_5cm (attempt 1): NO_MOTION | max arm displacement - rad" in text
    assert "- t1 task_start: attempt 2, wall 181.25 s" in text and "- t1 forward_5cm: attempt 1, wall 190.0 s" in text
    assert "- t1 task_start (attempt 1): goal response timeout" in text


def test_a_table_without_failures_or_invalid_attempts_has_only_the_matrix_and_the_totals():
    result = summary({("task_start", 1): [attempt(1, "DONE", elapsed_wall_s=1.0)]}, points=("task_start",), trials=1)
    text = aggregate.render_table(result)
    assert "Failures" not in text and "INVALID attempts (" not in text and text.endswith("\n")
