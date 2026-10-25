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

SCHEMA6 = PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast_carry_b_diversity.yaml"
SCHEMA5 = PACKAGE_ROOT / "config/act/teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml"


class Execution(TeacherExecution):
    def __init__(self, events, faults):
        super().__init__(events, faults)
        self._document = {}
        self.diversity_recorded = []
        self.source_recorded = []

    def _record_episode_diversity(self, values):
        self._episode_diversity = values
        self.diversity_recorded.append(values)

    def _record_teacher_source(self, entry, *, published_truth_gap_m):
        self.source_recorded.append((entry, published_truth_gap_m))


def diversity_run(tmp_path, monkeypatch, policy_path, *, point_id="act-0001", start_draw=2, simulator_x=-0.03, source_entry=None):
    from so101_demo.act import frozen_runtime_inputs
    from so101_demo.ros import teacher_safety
    from so101_demo.ros.dynamic_runtime import run_dynamic_execute

    events, built, calls = [], {}, {}
    runtime = _runtime(events, observations=tuple(_observation(simulator_x=simulator_x, moveit_x=-0.03) for _ in range(3)),
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
    if source_entry is not None:
        from so101_demo.ros import dynamic_runtime
        monkeypatch.setattr(dynamic_runtime, "_frozen_teacher_source", lambda *args: source_entry)
    options = _options(tmp_path)
    options.frozen_inputs_manifest = tmp_path / "inputs-manifest.json"
    if point_id is not None:
        options.ready_receipt = tmp_path / "consumer-ready.json"
        options.start_pose_draw = start_draw
        for name, value in (("batch_id", "b"), ("coordinator_epoch", 1), ("worker_id", "w0"), ("worker_generation", 1),
                            ("point_id", point_id), ("attempt_id", point_id + "-lease-1"), ("lease_generation", 1)):
            setattr(options, name, value)
    code = run_dynamic_execute(options, _runtime=runtime)
    return code, built.get("execution"), calls, template, policy, events


def test_a_schema_6_freeze_resolves_preflights_and_builds_on_the_episode_targets(tmp_path, monkeypatch):
    code, execution, calls, template, policy, events = diversity_run(tmp_path, monkeypatch, SCHEMA6)
    values = td.values_for_policy(policy, "act-0001", 2)             # the draw the reset applied rides in on --start-pose-draw
    assert values["start_pose"]["draw_index"] == 2
    shifted = td.episode_template(template, values)
    offset = tuple(values["carry_via_offset_m"])
    assert code == 0 and "runner.run" in events
    assert calls["resolve"] == (shifted, {"carry_via_offset_m": offset})
    # carry_b + diversity has no DESCEND group: the preflight gets no distance (six interpolated segments), only the via offset
    assert "descend_final_distance_m" not in policy
    assert calls["preflight"] == (shifted, {"carry_via_offset_m": offset})
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


def test_a_schema_6_freeze_without_the_applied_start_draw_is_refused_before_any_motion(tmp_path, monkeypatch, capsys):
    code, execution, calls, _template, _policy, events = diversity_run(tmp_path, monkeypatch, SCHEMA6, start_draw=None)
    assert code == 1 and execution is None and "runner.run" not in events and "resolve" not in calls
    assert "TEACHER_DIVERSITY_START_DRAW_REQUIRED" in capsys.readouterr().out


def test_a_schema_6_freeze_without_a_scene_id_is_refused_before_any_motion(tmp_path, monkeypatch, capsys):
    code, execution, calls, _template, _policy, events = diversity_run(tmp_path, monkeypatch, SCHEMA6, point_id=None)
    assert code == 1 and execution is None and "runner.run" not in events and "resolve" not in calls
    assert "TEACHER_DIVERSITY_SCENE_ID_REQUIRED" in capsys.readouterr().out


# --- indoor P3: the Teacher source of the scene (a scene list with an appearance plan) -----------------------------------------------
def source_entry(source):
    kind = "randomised" if source == "privileged_pose" else "nominal"
    return {"teacher_source": source, "appearance": {"kind": kind, "plan_sha256": "a" * 64, "draw_sha256": "b" * 64,
                                                       "variant_sha256": "c" * 64 if kind == "randomised" else None}}


def bind_proof(monkeypatch, proof=True):
    from so101_demo.act import model_equivalence

    value = {"sha256": "ab" * 32, "declared": "cd" * 32, "loaded": "ef" * 32, "proof": {}} if proof else None
    monkeypatch.setattr(model_equivalence, "bound", lambda environ=None: value)


def test_a_privileged_episode_whose_pose_is_the_simulators_runs_and_records_its_source(tmp_path, monkeypatch):
    entry = source_entry("privileged_pose")
    bind_proof(monkeypatch)
    code, execution, _calls, _template, _policy, events = diversity_run(tmp_path, monkeypatch, SCHEMA6, source_entry=entry)
    assert code == 0 and "runner.run" in events
    assert len(execution.source_recorded) == 1 and execution.source_recorded[0][0] is entry
    assert execution.source_recorded[0][1] == pytest.approx(0.0, abs=1e-9)


def test_a_privileged_episode_whose_pose_is_not_the_simulators_is_refused_before_any_motion(tmp_path, monkeypatch, capsys):
    bind_proof(monkeypatch)
    code, execution, calls, _template, _policy, events = diversity_run(
        tmp_path, monkeypatch, SCHEMA6, simulator_x=-0.02, source_entry=source_entry("privileged_pose"))
    assert code == 1 and execution is None and "runner.run" not in events and "resolve" not in calls
    assert "TEACHER_SOURCE_PRIVILEGED_POSE_MISMATCH" in capsys.readouterr().out


def test_a_randomised_episode_without_the_bound_proof_is_refused_before_any_motion(tmp_path, monkeypatch, capsys):
    bind_proof(monkeypatch, False)
    code, execution, calls, _template, _policy, events = diversity_run(tmp_path, monkeypatch, SCHEMA6, source_entry=source_entry("privileged_pose"))
    assert code == 1 and execution is None and "runner.run" not in events and "resolve" not in calls
    assert "TEACHER_SOURCE_MODEL_EQUIVALENCE_MISSING" in capsys.readouterr().out


def test_a_camera_episode_records_how_far_its_pose_is_from_the_simulators_and_is_never_refused_for_it(tmp_path, monkeypatch):
    bind_proof(monkeypatch, False)
    code, execution, _calls, _template, _policy, events = diversity_run(
        tmp_path, monkeypatch, SCHEMA6, simulator_x=-0.02, source_entry=source_entry("camera_rgbd"))
    assert code == 0 and "runner.run" in events
    assert execution.source_recorded[0][1] == pytest.approx(0.01)


def test_a_freeze_without_a_scene_list_plan_records_no_source(tmp_path, monkeypatch):
    code, execution, *_ = diversity_run(tmp_path, monkeypatch, SCHEMA6)
    assert code == 0 and execution.source_recorded == []


def test_a_scene_list_that_is_not_the_plans_is_refused_before_any_motion(tmp_path, monkeypatch, capsys):
    from so101_demo.ros import dynamic_runtime
    from so101_demo.act import appearance_plan as ap

    def refuse(*args):
        raise ap.AppearanceInvalid("APPEARANCE_ROW_NOT_DERIVED: act-0001")

    monkeypatch.setattr(dynamic_runtime, "_frozen_teacher_source", refuse)
    code, execution, calls, *_ = diversity_run(tmp_path, monkeypatch, SCHEMA6, source_entry=None)
    assert code == 1 and execution is None and "resolve" not in calls
    assert "APPEARANCE_ROW_NOT_DERIVED" in capsys.readouterr().out
