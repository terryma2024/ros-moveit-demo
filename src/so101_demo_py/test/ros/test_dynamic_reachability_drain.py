"""Reachability planning and the Teacher's progress spin hold no data drain (A4c; the physics backlog is the Recorder's).

What actual59 added here - draining the raw physics backlog on every reachability tick and on every `_progress` call - is
REPLACED_BY the Recorder's own source pass (`OfflineRosSources.pump`): the Teacher only spins its own callbacks."""

import json
import threading
import time
from types import SimpleNamespace

from so101_demo.ros.dynamic_runtime import run_dynamic_execute
from test_dynamic_scene_sync import _runtime, _options, _observation, RecordingTaskScenePort


def _wired_runtime(events, *, binding):
    runtime = _runtime(events, observations=(
        _observation(simulator_x=-.03, moveit_x=.02),
        _observation(simulator_x=-.03), _observation(simulator_x=-.03)), scene=RecordingTaskScenePort())
    runtime.rclpy.spin_once = lambda _node, timeout_sec: events.append("spin")
    runtime.bind_scene_source = lambda *args, **kwargs: binding
    return runtime


def _drain_binding(events, drained, *, error=None):
    def drain_sources():
        events.append("drain")
        drained.append(threading.get_ident())
        if error is not None:
            raise error
        return 7
    return SimpleNamespace(observer=object(), drain_sources=drain_sources,
                           close=lambda: events.append("scene_source.close"))


def test_the_teacher_reachability_check_runs_the_planners_own_spin_and_drains_nothing(tmp_path):
    events, drained = [], []
    runtime = _wired_runtime(events, binding=_drain_binding(events, drained))
    original = runtime.reachability_preflight
    calls = []

    def preflight(*args, **kwargs):
        calls.append((len(args), dict(kwargs)))
        return original(*args)

    runtime.reachability_preflight = preflight
    assert run_dynamic_execute(_options(tmp_path), _runtime=runtime) == 0
    assert calls == [(4, {})], "no progress hook: the planner's default spin is the whole of it"
    assert "drain" not in events and drained == []


def test_real_reachability_preflight_threads_progress_to_the_planner(monkeypatch):
    from so101_demo.application import task_reachability as application
    from so101_demo.ros import dynamic_runtime, task_reachability as ros_reachability

    seen = {}

    class Planner:
        def __init__(self, node, template, **kwargs):
            seen["planner_kwargs"] = kwargs
        def close(self):
            seen["planner_closed"] = True

    class Reader:
        def __init__(self, node, names):
            pass
        def read(self, timeout_s):
            return "start"
        def close(self):
            seen["reader_closed"] = True

    monkeypatch.setattr(ros_reachability, "RosMoveGroupReachabilityPlanner", Planner)
    monkeypatch.setattr(ros_reachability, "RosJointStateReader", Reader)
    monkeypatch.setattr(application, "check_task_reachability", lambda *args, **kwargs: "report")
    runtime = dynamic_runtime._dynamic_execute_runtime()
    template = SimpleNamespace(arm_joint_names=("a",), planning_timeout_s=1.0)
    sample = SimpleNamespace(pose_world=SimpleNamespace(values=(0.0, 0.0, 0.0)))
    progress = lambda: None
    assert runtime.reachability_preflight(object(), sample, template, 3, progress=progress) == "report"
    assert seen["planner_kwargs"] == {"progress": progress}
    assert runtime.reachability_preflight(object(), sample, template, 3) == "report"
    assert seen["planner_kwargs"] == {}


def _slow_execution(monkeypatch, *, spin_s):
    import rclpy
    from so101_demo.ros.dynamic_mujoco_execution import RosDynamicMujocoExecution

    monkeypatch.setattr(rclpy, "spin_once", lambda node, timeout_sec: time.sleep(spin_s))
    execution = RosDynamicMujocoExecution.__new__(RosDynamicMujocoExecution)
    execution._node = object()
    execution._document = {}
    return execution


def _slow_lines(capsys):
    return [line for line in capsys.readouterr().err.splitlines() if line.startswith("DYNAMIC_PROGRESS_SLOW ")]


def test_slow_progress_call_emits_one_bounded_fact_line_with_its_only_substep(monkeypatch, capsys):
    execution = _slow_execution(monkeypatch, spin_s=0.07)
    execution._progress()
    lines = _slow_lines(capsys)
    assert len(lines) == 1
    document = json.loads(lines[0].split(" ", 1)[1])
    assert document["total_ms"] >= 50
    assert set(document["substeps_ms"]) == {"spin_once"} and document["substeps_ms"]["spin_once"] >= 50
    assert "drained_records" not in document, "the Teacher drains no data source"
    assert len(lines[0].encode()) <= 2048


def test_fast_progress_calls_emit_no_fact_line(monkeypatch, capsys):
    execution = _slow_execution(monkeypatch, spin_s=0.0)
    for _ in range(5):
        execution._progress()
    assert _slow_lines(capsys) == []


def test_slow_progress_fact_lines_are_capped_per_execution(monkeypatch, capsys):
    execution = _slow_execution(monkeypatch, spin_s=0.055)
    for _ in range(25):
        execution._progress()
    assert len(_slow_lines(capsys)) == 20


def test_fact_line_failure_never_changes_progress(monkeypatch, capsys):
    import json

    execution = _slow_execution(monkeypatch, spin_s=0.06)
    monkeypatch.setattr(json, "dumps", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    execution._progress()
    assert _slow_lines(capsys) == []
