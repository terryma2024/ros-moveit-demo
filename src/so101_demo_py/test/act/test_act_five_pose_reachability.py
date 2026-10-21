"""The five-pose filter: two phases, cached verdicts, UNKNOWN handling and the command-backed planner call."""

import json
import subprocess

import pytest

from so101_demo.act import five_pose_reachability as fp


def fake_call(predicate, log=None, unknown_first=False):
    state = {"calls": 0}

    def call(document):
        state["calls"] += 1
        if log is not None:
            log.append([tuple(p["cup_position_world_m"][:2]) for p in document["points"]])
        if unknown_first and state["calls"] == 1:
            return {p["id"]: ("UNKNOWN", "PLANNER_UNAVAILABLE") for p in document["points"]}
        return {
            p["id"]: ("REACHABLE", None) if predicate(*p["cup_position_world_m"][:2]) else ("UNREACHABLE", "MOVEIT_PLAN_FAILED")
            for p in document["points"]
        }

    return call


def test_a_position_is_reachable_only_when_all_five_poses_are():
    reach = fp.FivePoseReachability(fake_call(lambda x, y: x <= 0.105))
    reach.evaluate([(0.10, -0.3), (0.10, -0.3), (0.10 + 0.0, -0.31)])
    # x + 0.01 = 0.11 fails for both positions
    assert not reach.is_reachable(0.10, -0.3)
    verdict = reach.verdict(0.10, -0.3)
    assert verdict["true"][0] == "REACHABLE" and verdict["x+"][0] == "UNREACHABLE" and verdict["y-"][0] == "REACHABLE"
    reach.evaluate([(0.05, -0.3)])
    assert reach.is_reachable(0.05, -0.3)


def test_offsets_are_only_planned_for_positions_whose_true_pose_is_reachable():
    log = []
    reach = fp.FivePoseReachability(fake_call(lambda x, y: x < 0.2, log))
    reach.evaluate([(0.0, -0.3), (0.3, -0.3)])
    assert log[0] == [(0.0, -0.3), (0.3, -0.3)]
    assert sorted(log[1]) == [(-0.01, -0.3), (0.0, -0.31), (0.0, -0.29), (0.01, -0.3)]
    verdict = reach.verdict(0.3, -0.3)
    assert verdict["true"][0] == "UNREACHABLE" and verdict["x+"] == (fp.NOT_EVALUATED, None)
    assert not reach.is_reachable(0.3, -0.3)


def test_cached_poses_are_not_asked_twice_and_calls_are_batched():
    log = []
    reach = fp.FivePoseReachability(fake_call(lambda x, y: True, log), batch_poses=3)
    reach.evaluate([(0.0, -0.3), (0.0, -0.3)])
    assert reach.calls == 1 + 2  # one true batch, then four offsets in batches of three
    reach.evaluate([(0.0, -0.3)])
    assert reach.calls == 3


def test_an_unknown_position_raises_and_the_optimistic_probe_records_it():
    reach = fp.FivePoseReachability(fake_call(lambda x, y: True))
    with pytest.raises(fp.PoseNotEvaluatedError):
        reach.is_reachable(0.0, -0.3)
    reachable, missing = reach.optimistic()
    assert reachable(0.0, -0.3) is True and missing == {(0.0, -0.3)}
    reach.evaluate(missing)
    reachable, missing = reach.optimistic()
    assert reachable(0.0, -0.3) is True and missing == set()


def test_an_unknown_verdict_aborts_instead_of_counting_as_a_rejection():
    reach = fp.FivePoseReachability(fake_call(lambda x, y: True, unknown_first=True))
    with pytest.raises(fp.ReachabilityUnknownError, match="REACH_CALL_UNKNOWN"):
        reach.evaluate([(0.0, -0.3)])


def _runner(tmp_path, predicate, statuses=None):
    """A stand-in for the command prefix: writes the evidence file the way task_reachability does."""

    runs = []

    def run(argv, check):
        points, evidence = argv[-3], argv[-2]
        runs.append(argv)
        document = json.loads(open(points).read())
        status = (statuses or {}).get(len(runs))
        reports = [
            {"point_id": p["id"], "status": status or ("REACHABLE" if predicate(*p["cup_position_world_m"][:2]) else "UNREACHABLE"),
             "first_failure_code": None}
            for p in document["points"]
        ]
        with open(evidence, "w") as stream:
            json.dump({"reports": reports}, stream)
        return subprocess.CompletedProcess(argv, 0)

    return runs, run


def test_the_command_call_appends_points_evidence_and_session_and_reads_the_reports(tmp_path):
    runs, run = _runner(tmp_path, lambda x, y: x < 0.5)
    call = fp.CommandReachabilityCall(["zsh", "reach_call.zsh", "OUT", "box"], tmp_path / "calls", run=run)
    verdicts = call({"schema_version": 1, "points": [{"id": "p00000", "label": "reach-filter", "cup_position_world_m": [0.1, -0.3, 0.165]}]})
    assert verdicts == {"p00000": ("REACHABLE", None)}
    assert runs[0][:4] == ["zsh", "reach_call.zsh", "OUT", "box"] and runs[0][-1].startswith("boundary-c0001-a1")
    assert (tmp_path / "calls" / "boundary-c0001-a1.points.json").is_file()


def test_the_command_call_retries_once_on_unknown_and_then_aborts(tmp_path):
    runs, run = _runner(tmp_path, lambda x, y: True, statuses={1: "UNKNOWN"})
    call = fp.CommandReachabilityCall(["x"], tmp_path / "calls", run=run)
    document = {"schema_version": 1, "points": [{"id": "p00000", "label": "l", "cup_position_world_m": [0.1, -0.3, 0.165]}]}
    assert call(document) == {"p00000": ("REACHABLE", None)}
    assert len(runs) == 2
    _runs, always_unknown = _runner(tmp_path, lambda x, y: True, statuses={1: "UNKNOWN", 2: "UNKNOWN"})
    with pytest.raises(fp.ReachabilityUnknownError):
        fp.CommandReachabilityCall(["x"], tmp_path / "calls2", run=always_unknown)(document)


def test_the_exit_code_file_of_the_prefix_wins_over_the_process_code(tmp_path):
    def run(argv, check):
        evidence = argv[-2]
        with open(evidence, "w") as stream:
            json.dump({"reports": []}, stream)
        with open(evidence + ".rc", "w") as stream:
            stream.write("1")
        return subprocess.CompletedProcess(argv, 0)

    call = fp.CommandReachabilityCall(["x"], tmp_path / "calls", run=run)
    with pytest.raises(fp.ReachabilityUnknownError):
        call({"schema_version": 1, "points": [{"id": "p00000", "label": "l", "cup_position_world_m": [0.1, -0.3, 0.165]}]})
