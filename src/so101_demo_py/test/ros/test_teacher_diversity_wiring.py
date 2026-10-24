"""R3-a at the Teacher runtime entry: a schema 6 freeze derives the per-episode values from (campaign seed, scene id = the lease point id),
resolves the targets, runs the reachability preflight and builds the execution on them, and records them on the Teacher document.
A schema 3, 4 or 5 freeze does exactly what it always did (the calls carry no extra argument, the execution holds no values)."""

import pytest

from so101_demo.act import teacher_diversity as td
from so101_demo.act.teacher_endpoint import load_teacher_execution_policy
from so101_demo.core.dynamic_pick import resolve_motion_targets
from paths import PACKAGE_ROOT

from test_dynamic_scene_sync import RecordingTaskScenePort, _observation, _options, _runtime
from test_teacher_runtime import TeacherExecution

SCHEMA6 = PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_diversity.yaml"
SCHEMA5 = PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml"


class Execution(TeacherExecution):
    def __init__(self, events, faults):
        super().__init__(events, faults)
        self._document = {}
        self.diversity_recorded = []

    def _record_episode_diversity(self, values):
        self._episode_diversity = values
        self.diversity_recorded.append(values)


def diversity_run(tmp_path, monkeypatch, policy_path, *, point_id="act-0001"):
    from so101_demo.act import frozen_runtime_inputs
    from so101_demo.ros import teacher_safety
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events, built, calls = [], {}, {}
    runtime = _runtime(events, observations=tuple(_observation(simulator_x=-0.03, moveit_x=-0.03) for _ in range(3)),
                       scene=RecordingTaskScenePort())
    template = runtime.load_policy(None, backend="mujoco").template

    def execution(node, run_template, targets, **kwargs):
        built["execution"] = Execution(events, frozenset())
        calls["execution"] = (run_template, targets)
        return built["execution"]

    def resolve(sample, run_template, **kwargs):
        calls["resolve"] = (run_template, kwargs)
        return resolve_motion_targets(sample, run_template, **kwargs)

    def preflight(node, sample, run_template, scene_revision, **kwargs):
        calls["preflight"] = (run_template, kwargs)
        return type("Report", (), {"status": type("Status", (), {"value": "REACHABLE"})(), "segments": (), "point_id": "p",
                                   "first_failure_code": None, "scene_revision": scene_revision})()

    runtime.execution, runtime.resolve_motion_targets, runtime.reachability_preflight = execution, resolve, preflight
    runtime.build_actions = lambda exec_, targets, **kwargs: object()
    runtime.bind_scene_source = lambda *a, **k: None
    policy = load_teacher_execution_policy(policy_path)
    frozen = {"runtime_policy": {"sha256": "x", "kind": "k"},
              "teacher_execution_policy": {"values": {key: value for key, value in policy.items() if key != "policy_sha256"}}}
    monkeypatch.setattr(frozen_runtime_inputs, "load_teacher_frozen_inputs",
                        lambda path: (frozen, {"scene_path": "assets/mujoco/act/scene.xml"}, PACKAGE_ROOT))
    monkeypatch.setattr(teacher_safety, "load_frozen_safety", lambda path: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(teacher_safety.PhysicsHazardWatch, "attach", lambda self, node: None)
    options = _options(tmp_path)
    options.frozen_inputs_manifest = tmp_path / "inputs-manifest.json"
    if point_id is not None:
        options.ready_receipt = tmp_path / "consumer-ready.json"
        for name, value in (("batch_id", "b"), ("coordinator_epoch", 1), ("worker_id", "w0"), ("worker_generation", 1),
                            ("point_id", point_id), ("attempt_id", point_id + "-lease-1"), ("lease_generation", 1)):
            setattr(options, name, value)
    code = run_dynamic_execute(options, _runtime=runtime)
    return code, built.get("execution"), calls, template, policy, events


def test_a_schema_6_freeze_resolves_preflights_and_builds_on_the_episode_targets(tmp_path, monkeypatch):
    code, execution, calls, template, policy, events = diversity_run(tmp_path, monkeypatch, SCHEMA6)
    values = td.values_for_policy(policy, "act-0001")
    shifted = td.episode_template(template, values)
    offset = tuple(values["carry_via_offset_m"])
    assert code == 0 and "runner.run" in events
    assert calls["resolve"] == (shifted, {"carry_via_offset_m": offset})
    assert calls["preflight"] == (shifted, {"descend_final_distance_m": policy["descend_final_distance_m"], "carry_via_offset_m": offset})
    assert calls["execution"][0] == shifted and calls["execution"][1].carry_via is not None
    assert execution._episode_diversity == values
    assert execution.diversity_recorded == [values]


def test_the_values_follow_the_lease_point_id(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = diversity_run(tmp_path / "a", monkeypatch, SCHEMA6, point_id="act-0001")
    second = diversity_run(tmp_path / "b", monkeypatch, SCHEMA6, point_id="act-0002")
    assert first[1]._episode_diversity != second[1]._episode_diversity
    assert first[1]._episode_diversity["scene_id"] == "act-0001" and second[1]._episode_diversity["scene_id"] == "act-0002"


def test_a_schema_5_freeze_calls_everything_exactly_as_before(tmp_path, monkeypatch):
    code, execution, calls, template, _policy, events = diversity_run(tmp_path, monkeypatch, SCHEMA5)
    assert code == 0 and "runner.run" in events
    assert calls["resolve"] == (template, {}) and calls["preflight"][0] == template
    assert calls["preflight"][1] == {"descend_final_distance_m": 0.02}      # the schema 5 argument, and nothing from schema 6
    assert calls["execution"][0] == template and calls["execution"][1].carry_via is None
    assert not hasattr(execution, "_episode_diversity") and execution.diversity_recorded == []


def test_a_schema_6_freeze_without_a_scene_id_is_refused_before_any_motion(tmp_path, monkeypatch, capsys):
    code, execution, calls, _template, _policy, events = diversity_run(tmp_path, monkeypatch, SCHEMA6, point_id=None)
    assert code == 1 and execution is None and "runner.run" not in events and "resolve" not in calls
    assert "TEACHER_DIVERSITY_SCENE_ID_REQUIRED" in capsys.readouterr().out
