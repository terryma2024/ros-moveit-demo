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


# --- a pool of planners: chunks run at the same time, the verdicts and their order do not change --------------------------

def pool_calls(count, predicate, concurrency, wait=None):
    """``count`` fake planners that record which thread ran them and how many chunks they held at once."""

    import threading

    live = {"now": 0, "peak": 0}
    lock = threading.Lock()
    held = [0] * count
    overlap = [0] * count

    def member(index):
        base = fake_call(predicate)

        def call(document):
            with lock:
                live["now"] += 1
                live["peak"] = max(live["peak"], live["now"])
                held[index] += 1
                overlap[index] = max(overlap[index], held[index])
            try:
                if wait is not None:
                    wait()
                return base(document)
            finally:
                with lock:
                    live["now"] -= 1
                    held[index] -= 1

        return call

    return [member(i) for i in range(count)], live, overlap


def positions(count):
    return [(round(-0.1 + 0.001 * i, 6), -0.3) for i in range(count)]


def test_a_pool_gives_the_same_verdicts_ids_and_order_as_one_planner():
    import time

    serial = fp.FivePoseReachability(fake_call(lambda x, y: x < -0.05), batch_poses=7)
    serial.evaluate(positions(60))
    calls, live, overlap = pool_calls(3, lambda x, y: x < -0.05, 3, wait=lambda: time.sleep(0.05))
    pooled = fp.FivePoseReachability(calls[0], batch_poses=7, pool=calls)
    pooled.evaluate(positions(60))
    assert pooled.pose_log == serial.pose_log
    assert pooled._cache == serial._cache
    assert pooled.calls == serial.calls
    assert live["peak"] >= 2                      # chunks really ran together
    assert max(overlap) == 1                      # and no planner was handed two chunks at once


def test_a_pool_member_that_cannot_answer_aborts_the_evaluation():
    good = fake_call(lambda x, y: True)
    bad = fake_call(lambda x, y: True, unknown_first=False)

    def unknown(document):
        return {p["id"]: ("UNKNOWN", "PLANNER_UNAVAILABLE") for p in document["points"]}

    reach = fp.FivePoseReachability(good, batch_poses=5, pool=[good, unknown])
    with pytest.raises(fp.ReachabilityUnknownError):
        reach.evaluate(positions(30))
    assert bad is not None


def test_evaluate_true_asks_for_true_poses_only_and_never_twice():
    log = []
    reach = fp.FivePoseReachability(fake_call(lambda x, y: True, log), batch_poses=4)
    reach.evaluate_true(positions(10))
    assert sum(len(chunk) for chunk in log) == 10 and reach.calls == 3
    reach.evaluate_true(positions(10) + [(0.2, -0.3)])
    assert sum(len(chunk) for chunk in log) == 11
    # the offsets of a surviving position are still missing, so it is not reachable yet; evaluate then adds exactly four poses
    with pytest.raises(fp.PoseNotEvaluatedError):
        reach.is_reachable(*positions(10)[0])
    reach.evaluate([positions(10)[0]])
    assert reach.is_reachable(*positions(10)[0]) and sum(len(chunk) for chunk in log) == 15


def test_a_small_batch_is_split_over_the_pool_instead_of_going_to_one_planner():
    log = []
    members = [fake_call(lambda x, y: True, log) for _ in range(4)]
    reach = fp.FivePoseReachability(members[0], batch_poses=80, pool=members)
    reach.evaluate(positions(8))
    sizes = sorted(len(chunk) for chunk in log)
    assert sizes[:4] == [2, 2, 2, 2] and sum(sizes[:4]) == 8           # the true poses: four planners, two each
    assert sum(sizes) == 8 + 32 and max(sizes) == 8                    # then 32 offsets in chunks of eight
    serial = fp.FivePoseReachability(fake_call(lambda x, y: True), batch_poses=80)
    serial.evaluate(positions(8))
    assert reach.pose_log == serial.pose_log                            # same ids, same order: the split is invisible


def test_a_large_batch_still_uses_the_batch_size_with_a_pool():
    log = []
    members = [fake_call(lambda x, y: True, log) for _ in range(2)]
    fp.FivePoseReachability(members[0], batch_poses=5, pool=members).evaluate_true(positions(30))
    assert sorted(len(chunk) for chunk in log) == [5] * 6
