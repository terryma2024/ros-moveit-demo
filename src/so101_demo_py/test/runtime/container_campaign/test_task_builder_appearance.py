"""The collection task builder and an appearance plan (indoor P3): the stack runs the scene of the task before anything is built on it, and the
pose source follows the scene's Teacher source. The frozen set here is the synthetic head+wrist fixture of `test_task_builder`, so the plan's rig
(`side-wrist-indoor`) is refused by the rig check: the positive wiring is tested by giving `build_collection_task` an entry and a switch directly."""

from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace

import pytest

from paths import PACKAGE_ROOT
from so101_demo.act import appearance_plan as ap
from so101_demo.act import frozen_appearance
from test_task_builder import TEACHER_SOCKET, FakeInference, builder, make_env, make_task

INVENTORY = ap.scene_inventory(PACKAGE_ROOT / "assets/mujoco/act")
PLAN = ap.make_plan(seed=710025, nominal_share=0.25, nominal_scene_sha256=INVENTORY["scene_sha256"], pool_identity=INVENTORY["pool_identity"])


def planned_env(tmp_path, monkeypatch, scene="scene-a"):
    """The bound-scene fixture whose frozen scene list carries the plan and the derived rows (the same cup positions and ids)."""
    import test_task_builder as module

    annotated = ap.annotate_rows(PLAN, list(module.BOUND_ROWS), INVENTORY)
    real_dumps = json.dumps

    def dumps(value, *args, **kwargs):
        if isinstance(value, dict) and set(value) == {"scenarios"} and value["scenarios"] is annotated:
            value = {**value, frozen_appearance.PLAN_KEY: PLAN}
        return real_dumps(value, *args, **kwargs)

    with monkeypatch.context() as local:
        local.setattr(module, "BOUND_ROWS", annotated)
        local.setattr(module.json, "dumps", dumps)
        return make_env(tmp_path, monkeypatch, bound_scene=scene)


def test_a_scene_list_with_a_plan_and_a_shard_without_a_switch_is_refused(tmp_path, monkeypatch):
    env = planned_env(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="COLLECTION_CASE_SCENE_SWITCH_REQUIRED"):
        builder().load_task_input(make_task(env), env.spec, teacher_socket=TEACHER_SOCKET)


def test_the_plans_rig_must_be_the_rig_of_the_frozen_inputs(tmp_path, monkeypatch):
    env = planned_env(tmp_path, monkeypatch)
    switch = SimpleNamespace(entry=lambda frozen, manifest, scene: frozen_appearance.scene_entry(frozen, manifest, scene, inventory=INVENTORY))
    with pytest.raises(ValueError, match="COLLECTION_CASE_APPEARANCE_RIG_MISMATCH"):
        builder().load_task_input(make_task(env), env.spec, teacher_socket=TEACHER_SOCKET, scene_switch=switch)


def test_a_row_that_is_not_the_plans_is_refused_as_an_invalid_appearance(tmp_path, monkeypatch):
    env = planned_env(tmp_path, monkeypatch)

    def entry(frozen, manifest, scene):
        raise ap.AppearanceInvalid("APPEARANCE_ROW_NOT_DERIVED: " + scene)

    with pytest.raises(ValueError, match="COLLECTION_CASE_APPEARANCE_INVALID: APPEARANCE_ROW_NOT_DERIVED"):
        builder().load_task_input(make_task(env), env.spec, teacher_socket=TEACHER_SOCKET, scene_switch=SimpleNamespace(entry=entry))


def test_a_list_without_a_plan_is_loaded_as_before_with_or_without_a_switch(tmp_path, monkeypatch):
    env = make_env(tmp_path, monkeypatch, bound_scene="scene-a")
    plain = builder().load_task_input(make_task(env), env.spec, teacher_socket=TEACHER_SOCKET)
    assert plain.appearance is None and plain.expected_model_sha256 and plain.start_tolerance_m == 0.010
    switch = SimpleNamespace(entry=lambda frozen, manifest, scene: frozen_appearance.scene_entry(frozen, manifest, scene, inventory=INVENTORY))
    assert builder().load_task_input(make_task(env), env.spec, teacher_socket=TEACHER_SOCKET, scene_switch=switch).appearance is None


class Switch:
    """Records the calls and what already existed when the stack was switched."""

    def __init__(self, order):
        self.order, self.calls, self.records = order, [], []

    def switch(self, appearance, scene_id, *, expected_model_sha256):
        self.order.append("switch")
        self.calls.append((appearance, scene_id, expected_model_sha256))
        return {"switched": True, "scene_id": scene_id}

    def record_task(self, task_id, entry, switched):
        self.order.append("record")
        self.records.append((task_id, entry, switched))


def wired(env, monkeypatch, entry, order, switch):
    real = builder().load_task_input

    def load(*args, **kwargs):
        loaded = real(*args, **{**kwargs, "scene_switch": None})
        return dataclasses.replace(loaded, appearance=entry)

    monkeypatch.setattr(builder(), "load_task_input", load)
    real_ports = builder().ActRosRuntimePorts

    def ports(*args, **kwargs):
        order.append("ports")
        return real_ports(*args, **kwargs)

    monkeypatch.setattr(builder(), "ActRosRuntimePorts", ports)
    return builder().build_collection_task(make_task(env), stack=env.stack, shard_spec=env.spec, output_root=env.output,
                                           teacher_socket=TEACHER_SOCKET, ready_check=env.ready_check, scene_switch=switch,
                                           inference_client_factory=FakeInference,
                                           evidence=lambda session: SimpleNamespace(simulation_session_id=session, reset_epoch=2))


def nominal_entry(scene):
    for index in range(200):
        candidate = f"w-{index}"
        if ap.derive(PLAN, candidate, INVENTORY)["kind"] == ap.KIND_NOMINAL:
            appearance = ap.derive(PLAN, scene, INVENTORY)
            nominal = ap.derive(PLAN, candidate, INVENTORY)
            return {"plan": PLAN, "appearance": nominal, "teacher_source": ap.TEACHER_SOURCE_CAMERA, "row": {}}, appearance
    raise AssertionError


def test_the_stack_gets_the_scene_before_anything_is_built_and_the_pose_source_follows_the_scene_source(tmp_path, monkeypatch):
    env = make_env(tmp_path, monkeypatch, bound_scene="scene-a")
    entry, _ = nominal_entry("scene-a")
    order = []
    switch = Switch(order)
    execution = wired(env, monkeypatch, entry, order, switch)
    assert order[:3] == ["switch", "record", "ports"]
    assert switch.calls[0][0] is entry["appearance"] and switch.calls[0][1] == "scene-a" and len(switch.calls[0][2]) == 64
    assert switch.records[0][0] == "task-1" and switch.records[0][1] is entry
    source = execution.workload.pose_source
    assert source.source == ap.TEACHER_SOURCE_CAMERA and source.kind == ap.KIND_NOMINAL and source.tolerance_m == 0.010
    assert source.record_directory == env.root / "scene-appearance" and source.task_id == "task-1"
    assert source.session_id == execution.resources.session_id


def test_a_privileged_source_on_a_rig_that_is_not_the_indoor_one_is_refused_when_the_task_is_built(tmp_path, monkeypatch):
    env = make_env(tmp_path, monkeypatch, bound_scene="scene-a")
    entry, _ = nominal_entry("scene-a")
    randomised = next(ap.derive(PLAN, f"r-{index}", INVENTORY) for index in range(200)
                      if ap.derive(PLAN, f"r-{index}", INVENTORY)["kind"] == ap.KIND_RANDOMISED)
    bad = {**entry, "appearance": randomised, "teacher_source": ap.TEACHER_SOURCE_PRIVILEGED}
    with pytest.raises(Exception, match="TEACHER_SOURCE_NOT_ALLOWED"):
        wired(env, monkeypatch, bad, [], Switch([]))


def test_a_task_without_an_appearance_builds_no_pose_source_and_never_touches_the_switch(tmp_path, monkeypatch):
    env = make_env(tmp_path, monkeypatch, bound_scene="scene-a")
    order, switch = [], Switch([])
    execution = wired(env, monkeypatch, None, order, switch)
    assert execution.workload.pose_source is None and switch.calls == [] and order == ["ports"]
