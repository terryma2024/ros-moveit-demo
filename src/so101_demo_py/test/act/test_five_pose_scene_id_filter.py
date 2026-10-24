"""R3-a: the per-episode diversity values derive from the final scene id, never from the sampling-time pose id (`p00012`).

The five-pose sampling filter therefore refuses a Teacher execution policy; a separate re-filter, keyed by the final scene ids, checks the
assigned scenes against their own per-episode targets."""

import json

import pytest

from so101_demo.act.five_pose_reachability import (
    CommandReachabilityCall, ReachabilityUnknownError, refilter_scenes)

ROWS = [{"scene_id": "act-0001", "cup_position_world_m": [0.02, -0.28, 0.165]},
        {"scene_id": "act-0002", "cup_position_world_m": [0.05, -0.30, 0.165]},
        {"scene_id": "act-0003", "cup_position_world_m": [0.08, -0.33, 0.165]}]


def test_the_re_filter_asks_with_the_final_scene_ids_as_point_ids():
    asked = []

    def call(document):
        asked.append(document)
        return {point["id"]: ("REACHABLE", None) for point in document["points"]}

    kept, rejected = refilter_scenes(ROWS, call)
    assert [point["id"] for point in asked[0]["points"]] == [row["scene_id"] for row in ROWS]
    assert [point["cup_position_world_m"] for point in asked[0]["points"]] == [row["cup_position_world_m"] for row in ROWS]
    assert kept == ROWS and rejected == []


def test_a_scene_that_is_unreachable_under_its_own_values_is_rejected_by_id():
    def call(document):
        return {point["id"]: (("UNREACHABLE", "DYNAMIC_IK_HORIZON_FAILED") if point["id"] == "act-0002" else ("REACHABLE", None))
                for point in document["points"]}

    kept, rejected = refilter_scenes(ROWS, call)
    assert [row["scene_id"] for row in kept] == ["act-0001", "act-0003"]
    assert rejected == [{"scene_id": "act-0002", "status": "UNREACHABLE", "first_failure_code": "DYNAMIC_IK_HORIZON_FAILED"}]


def test_an_unknown_verdict_or_a_missing_report_is_never_a_rejection():
    with pytest.raises(ReachabilityUnknownError):
        refilter_scenes(ROWS, lambda document: {point["id"]: ("UNKNOWN", None) for point in document["points"]})
    with pytest.raises(ReachabilityUnknownError):
        refilter_scenes(ROWS, lambda document: {"act-0001": ("REACHABLE", None)})


def test_duplicate_scene_ids_are_refused():
    with pytest.raises(ValueError, match="SCENE_ID_DUPLICATE"):
        refilter_scenes([ROWS[0], ROWS[0]], lambda document: {})


def test_the_five_pose_command_call_refuses_a_teacher_policy(tmp_path, monkeypatch):
    document = {"schema_version": 1, "points": [{"id": "p00000", "label": "x", "cup_position_world_m": [0, 0, 0.165]}]}
    calls = []
    call = CommandReachabilityCall(["x", "--teacher-execution-policy", "t.yaml"], tmp_path, run=lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError, match="TEACHER_POLICY_NOT_ALLOWED_IN_FIVE_POSE_FILTER"):
        call(document)
    monkeypatch.setenv("REACH_TEACHER_POLICY", "/act/t.yaml")
    with pytest.raises(ValueError, match="TEACHER_POLICY_NOT_ALLOWED_IN_FIVE_POSE_FILTER"):
        CommandReachabilityCall(["x"], tmp_path, run=lambda *a, **k: calls.append(a))(document)
    assert calls == []


def test_the_re_filter_command_call_may_carry_the_policy(tmp_path, monkeypatch):
    monkeypatch.delenv("REACH_TEACHER_POLICY", raising=False)
    document = {"schema_version": 1, "points": [{"id": "act-0001", "label": "x", "cup_position_world_m": [0, 0, 0.165]}]}

    def run(command, check):
        evidence = command[-2]
        open(evidence, "w").write(json.dumps({"reports": [{"point_id": "act-0001", "status": "REACHABLE", "first_failure_code": None}]}))
        open(evidence + ".rc", "w").write("0")

        class Done:
            returncode = 0
        return Done()

    call = CommandReachabilityCall(["x", "--teacher-execution-policy", "t.yaml"], tmp_path, run=run, per_scene_ids=True)
    assert call(document) == {"act-0001": ("REACHABLE", None)}
