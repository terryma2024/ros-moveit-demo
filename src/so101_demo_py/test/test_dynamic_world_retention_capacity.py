"""Actual67 H2/D17: retention capacity sized to the admission window.

(S2b - the in-child admission progress spin - is REPLACED_BY the Recorder's off-loop admission, tested in
`test_act_recorder_scene`.)"""

import json
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from paths import PACKAGE_ROOT


# ---- H2: retention capacity ----

def _evidence(sequence):
    from so101_demo.core.simulation.types import ObjectState, SimulationEvidence
    return SimulationEvidence(simulation_time_s=1. + sequence * .01, frame_id="world", publisher_sequence=sequence,
        simulation_step=sequence, reset_epoch=1, simulation_session_id="session", paused=False,
        object_state=ObjectState(body_id=1, body="plastic_cup", position_world=(0., 0., 0.),
            orientation_xyzw=(0., 0., 0., 1.), linear_velocity_world=(0., 0., 0.), angular_velocity_world=(0., 0., 0.)),
        has_contact=False, minimum_signed_distance_m=0., maximum_normal_force_n=0., truncated=False,
        left_fingertip_contacts=(), right_fingertip_contacts=(), other_object_contacts=())


def _observer(monkeypatch, **kwargs):
    from so101_demo.backends.mujoco import observer as world_module
    monkeypatch.setattr(world_module, "convert_message", lambda value: value)
    node = SimpleNamespace(create_subscription=lambda *args: object())
    return world_module, world_module.MujocoWorldObserver(node, "session", subscription_depth=256,
        monotonic=lambda: 10., **kwargs)


def test_large_history_capacity_keeps_a_contiguous_600_record_window(monkeypatch):
    _, world = _observer(monkeypatch, history_capacity=2048)
    for sequence in range(1, 601):
        world.accept(_evidence(sequence), received_at_s=10.)
    records = world.original_records_after(0)
    assert [record.evidence.publisher_sequence for record in records] == list(range(1, 601))


def test_default_capacity_still_loses_the_prefix_after_600_records(monkeypatch):
    world_module, world = _observer(monkeypatch)
    for sequence in range(1, 601):
        world.accept(_evidence(sequence), received_at_s=10.)
    with pytest.raises(world_module.EvidenceRejected, match="atomic evidence retention prefix lost"):
        world.original_records_after(0)


@pytest.mark.parametrize("invalid", [0, 4097, -1, True, 1.5, "256", None])
def test_history_capacity_validation(monkeypatch, invalid):
    from so101_demo.backends.mujoco import observer as world_module
    node = SimpleNamespace(create_subscription=lambda *args: object())
    with pytest.raises(ValueError, match="history capacity"):
        world_module.MujocoWorldObserver(node, "session", history_capacity=invalid)
    for valid in (1, 4096):
        assert world_module.MujocoWorldObserver(node, "session", history_capacity=valid)._history.maxlen == valid


# ---- scene source retention (same pattern) ----

def _scene_frame(step):
    return dict(simulation_session_id="s", reset_epoch=2, simulation_step=step, paused=False,
        simulation_time_s=1.0 + step * .01, model_sha256="1" * 64, qpos=[.2] * 14, qvel=[.3] * 12,
        clock_interval_begin_monotonic_ns=9_999_800_000, clock_interval_end_monotonic_ns=9_999_900_000)


def test_scene_observer_history_capacity_default_and_override():
    from so101_demo.adapters.act.scene_state import SceneStateObserver
    kwargs = dict(model_sha256="1" * 64, nq=14, nv=12, max_age_s=.15, monotonic=lambda: 10.)
    assert SceneStateObserver(**kwargs)._history.maxlen == 256
    large = SceneStateObserver(**kwargs, history_capacity=2048)
    large.reset("s", 2, source_floor_s=1.)
    for step in range(1, 601):
        assert large.accept(_scene_frame(step))
    frames = large.original_frames_with_receipts()
    assert [frame["simulation_step"] for frame, _ in frames] == list(range(1, 601))
    for invalid in (0, 4097, True, 1.5, None):
        with pytest.raises(ValueError, match="SCENE_STATE_CONFIG_INVALID"):
            SceneStateObserver(**kwargs, history_capacity=invalid)


def test_dynamic_scene_binding_with_episode_recorder_retains_2048_frames():
    import mujoco
    from so101_demo.ros.data_source_binding import bind_data_sources
    from so101_demo.act.synchronizer import RgbObservationSynchronizer

    class Node:
        def create_subscription(self, cls, topic, callback, qos):
            return topic

        def destroy_subscription(self, subscription):
            pass

    episode = SimpleNamespace(synchronizer=RgbObservationSynchronizer(max_age_s=.1, max_skew_s=.1),
        capture=SimpleNamespace(audit=SimpleNamespace(append_raw_physics=lambda record: None,
        inputs={"execution_snapshot": {"physics_chunks": {"max_samples": 50, "max_contacts": 128}}})))
    path = PACKAGE_ROOT / "assets/mujoco/act/scene.xml"
    binding = bind_data_sources(Node(), session_id="live-source", reset_epoch=2, model_path=path,
        episode_recorder=episode)
    try:
        assert binding.observer._history.maxlen == 2048
    finally:
        binding.close()
    plain = bind_data_sources(Node(), session_id="live-source", reset_epoch=2, model_path=path)
    try:
        assert plain.observer._history.maxlen == 256
    finally:
        plain.close()


# ---- D17: retention facts before the unchanged exception ----

def test_prefix_loss_prints_exactly_one_fact_line_and_keeps_exception_text(monkeypatch, capsys):
    world_module, world = _observer(monkeypatch)
    for sequence in range(1, 601):
        world.accept(_evidence(sequence), received_at_s=10.)
    capsys.readouterr()
    with pytest.raises(world_module.EvidenceRejected) as caught:
        world.original_records_after(0)
    assert str(caught.value) == "atomic evidence retention prefix lost"
    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert len(lines) == 1
    prefix = "WORLD_EVIDENCE_RETENTION_LOST "
    assert lines[0].startswith(prefix)
    assert json.loads(lines[0][len(prefix):]) == {"cursor": 0, "first_retained_sequence": 345,
        "last_retained_sequence": 600, "retained": 256, "capacity": 256}
    capsys.readouterr()
    assert world.original_records_after(344)[0].evidence.publisher_sequence == 345
    assert capsys.readouterr().err == ""


# ---- H2b: the world drain copies only scene frames at or after the first pending record ----

def _scene_observer_with_frames(count):
    from so101_demo.adapters.act.scene_state import SceneStateObserver
    observer = SceneStateObserver(model_sha256="1" * 64, nq=14, nv=12, max_age_s=.15, monotonic=lambda: 10.,
        history_capacity=2048)
    observer.reset("s", 2, source_floor_s=1.)
    for step in range(1, count + 1):
        assert observer.accept(_scene_frame(step))
    return observer


def test_original_frames_min_step_filters_before_copy_and_default_returns_all(monkeypatch):
    import copy
    from so101_demo.adapters.act import scene_state
    observer = _scene_observer_with_frames(2048)
    copies = []
    real = copy.deepcopy
    monkeypatch.setattr(scene_state.copy, "deepcopy", lambda value, *a: copies.append(1) or real(value, *a))
    frames = observer.original_frames_with_receipts(min_simulation_step=2040)
    assert [frame["simulation_step"] for frame, _ in frames] == list(range(2040, 2049))
    assert len(copies) == 9
    copies.clear()
    assert len(observer.original_frames_with_receipts()) == 2048 and len(copies) == 2048
    assert len(observer.original_frames_with_receipts(min_simulation_step=None)) == 2048
    assert observer.original_frames_with_receipts(min_simulation_step=0) != ()
    assert observer.original_frames_with_receipts(min_simulation_step=5000) == ()


@pytest.mark.parametrize("invalid", [-1, True, 1.5, "3"])
def test_original_frames_min_step_validation(invalid):
    observer = _scene_observer_with_frames(3)
    with pytest.raises(ValueError, match="SCENE_STATE_QUERY_INVALID"):
        observer.original_frames_with_receipts(min_simulation_step=invalid)


def test_drain_fetches_records_first_and_asks_only_for_scenes_from_the_first_record_step():
    from so101_demo.ros.recorder_data_side import RecorderDataSide
    execution = RecorderDataSide.__new__(RecorderDataSide)
    execution.episode_recorder = object()
    execution._world_record_cursor = 7
    order, queries = [], []
    execution.observer = SimpleNamespace(original_records_after=lambda cursor: order.append("records") or ())
    execution._scene_source_binding = SimpleNamespace(observer=SimpleNamespace(
        original_frames_with_receipts=lambda **kwargs: queries.append(kwargs) or ()))
    assert execution._drain_world_sources() == 0
    assert queries == [] and order == ["records"]
    record = SimpleNamespace(evidence=SimpleNamespace(simulation_session_id="x", reset_epoch=9,
        publisher_sequence=8, simulation_step=2041))
    execution.observer = SimpleNamespace(original_records_after=lambda cursor: order.append("records") or (record,))
    execution._session_id, execution._expected_reset_epoch = "x", 9
    execution._scene_source_binding = SimpleNamespace(observer=SimpleNamespace(
        original_frames_with_receipts=lambda **kwargs: order.append("scenes") or queries.append(kwargs) or ()))
    assert execution._drain_world_sources() == 0
    assert order[-2:] == ["records", "scenes"]
    assert queries == [{"min_simulation_step": 2041}]
