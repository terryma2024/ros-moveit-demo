"""Tier 1 sequencing (plan 2026-10-20 item 18a): `teacher_safety.load_frozen_safety` is a telemetry-only block of about 3 s that used to run
after the cup pose was accepted. The early load of a schema 4 policy was reverted (fallback A): every schema loads it after the pose is
accepted. It is marked as phase events so a run can show where the time goes."""

import json

import pytest

from so101_demo.ros import dynamic_runtime

from test_teacher_runtime import teacher_run


def marks(captured_err):
    lines = [line for line in captured_err.splitlines() if line.startswith(dynamic_runtime._PHASE_TIMING_PREFIX)]
    assert len(lines) == 1
    document = json.loads(lines[0][len(dynamic_runtime._PHASE_TIMING_PREFIX):])
    return [name for name, _ in document["phases"]]


def test_a_schema_3_freeze_loads_the_safety_inputs_after_the_pose_exactly_where_it_always_did(tmp_path, monkeypatch, capsys):
    code, execution, watches, events = teacher_run(tmp_path, monkeypatch, schema=3)
    assert code == 0 and events.count("safety.load") == 1
    assert events.index("sample.acquire") < events.index("safety.load")
    phases = marks(capsys.readouterr().err)
    assert phases.index("execution.construct.end") < phases.index("load_frozen_safety.begin") < phases.index(
        "load_frozen_safety.end") < phases.index("build_actions.begin")


def test_a_schema_4_freeze_loads_the_safety_inputs_after_the_pose_like_schema_3(tmp_path, monkeypatch, capsys):
    # Fallback A (plan amendment 4): the early load put the paused world inside the Teacher's observer ring, so it is reverted.
    code, execution, watches, events = teacher_run(tmp_path, monkeypatch, schema=4)
    assert code == 0 and events.count("safety.load") == 1
    assert events.index("sample.acquire") < events.index("safety.load")
    phases = marks(capsys.readouterr().err)
    assert phases.index("ready") < phases.index("get_one.begin") < phases.index("get_one.end") < phases.index(
        "load_frozen_safety.begin") < phases.index("load_frozen_safety.end") < phases.index("build_actions.begin")
    assert phases.count("load_frozen_safety.begin") == 1 and phases.count("load_frozen_safety.end") == 1


@pytest.mark.parametrize("schema", [3, 4])
def test_the_watches_limits_and_summary_are_the_same_for_both_sequences(tmp_path, monkeypatch, schema):
    code, execution, watches, _events = teacher_run(tmp_path, monkeypatch, schema=schema)
    assert code == 0 and set(watches) == {"collision", "hazard"}
    assert watches["collision"]._record_only and watches["hazard"]._record_only
    assert execution._safety_limits is execution._process_summary.limits
    assert execution._collision_watch is watches["collision"] and execution._physics_hazard_watch is watches["hazard"]
    assert not hasattr(execution, "_safety_limits_error")


@pytest.mark.parametrize("schema", [3, 4])
def test_a_safety_load_failure_is_the_same_non_gating_record_for_both_sequences(tmp_path, monkeypatch, schema):
    code, execution, watches, events = teacher_run(tmp_path, monkeypatch, safety_fails=True, schema=schema)
    assert code == 0 and set(watches) == {"hazard"} and events.count("safety.load") == 1
    assert execution._safety_limits_error.startswith("SAFETY_LOAD_FAILED")
    assert "COLLISION_GEOMETRY_UNAVAILABLE" in execution._process_summary.build()["incomplete_reasons"]


def test_a_run_without_frozen_inputs_never_loads_the_safety_inputs(tmp_path, monkeypatch, capsys):
    code, _execution, _watches, events = teacher_run(tmp_path, monkeypatch, frozen_inputs=False, simulator_x=-0.03)
    assert code == 0 and "safety.load" not in events
    assert "load_frozen_safety.begin" not in marks(capsys.readouterr().err)


# ---- the Teacher loads the policy file the freeze bound ----------------------------------------------------------------------

FAST_FILE = "teacher_execution_policy_side_wrist_fast.yaml"


def test_the_policy_file_is_the_snapshot_file_whose_bytes_the_freeze_bound():
    default, fast = "a" * 64, "b" * 64
    snapshot = {"files": {"config/act/teacher_execution_policy.yaml": {"sha256": default},
                          "config/act/" + FAST_FILE: {"sha256": fast}}}
    name = dynamic_runtime._frozen_policy_file
    assert name({"teacher_execution_policy": {"file_sha256": default}}, snapshot) == "teacher_execution_policy.yaml"
    assert name({"teacher_execution_policy": {"file_sha256": fast}}, snapshot) == FAST_FILE
    assert name({"teacher_execution_policy": {"file_sha256": "c" * 64}}, snapshot) == "teacher_execution_policy.yaml"
    assert name({}, {"scene_path": "x"}) == "teacher_execution_policy.yaml"                   # a freeze double without files


def test_the_execution_loads_the_variant_file_a_freeze_names(tmp_path):
    from test_teacher_moveit_execution import TEACHER_POLICY, make_adapter

    value = make_adapter(tmp_path)
    config = tmp_path / "config/act"
    config.mkdir(parents=True)
    fast = TEACHER_POLICY.with_name(FAST_FILE)
    (config / FAST_FILE).write_bytes(fast.read_bytes())
    value._teacher_config_dir = config
    value._teacher_policy_files = {"execution": {}}
    value._document = {}
    value._select_execution_policy(FAST_FILE)
    assert value._execution_policy["schema_version"] == 4 and value._execution_policy["prepare_open_gripper_duration_s"] == 1.0
    assert value._teacher_policy_files["execution"]["path"].endswith(FAST_FILE)


def test_the_scene_age_comes_from_the_policy_file_the_freeze_bound(tmp_path):
    from test_teacher_moveit_execution import TEACHER_POLICY

    config = tmp_path / "config/act"
    config.mkdir(parents=True)
    (config / FAST_FILE).write_bytes(TEACHER_POLICY.with_name(FAST_FILE).read_bytes())
    assert dynamic_runtime._execution_state_max_age_s(tmp_path, teacher_run=True, file_name=FAST_FILE) == 0.5
    assert dynamic_runtime._execution_state_max_age_s(tmp_path, teacher_run=True) is None     # the default file is not in this share
