"""Runtime observability must expose real renderer attempt boundaries safely."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def scene():
    import mujoco

    path = Path(__file__).parents[1] / "assets/mujoco/v5_multi_object_scene.xml"
    model = mujoco.MjModel.from_xml_path(str(path))
    return mujoco, path, model, mujoco.MjData(model)


def _position(mujoco, model, data, joint_name, xyz):
    identifier = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
    address = int(model.jnt_qposadr[identifier])
    data.qpos[address : address + 7] = (*xyz, 1.0, 0.0, 0.0, 0.0)


class _RgbBackendSpy:
    def __init__(self, calls):
        self._calls = calls

    def disable_segmentation_rendering(self):
        return None

    def update_scene(self, data, *, camera):
        self._calls.append(("rgb_update", camera))

    def render(self):
        self._calls.append(("rgb_render",))
        return np.zeros((4, 4, 3), dtype=np.uint8)


class _SegmentationBackendSpy:
    def __init__(self, calls, geom_type):
        self._calls = calls
        self._geom_type = geom_type
        self._mjr_context = SimpleNamespace(offSamples=0)

    def enable_segmentation_rendering(self):
        return None

    def disable_segmentation_rendering(self):
        return None

    def update_scene(self, data, *, camera):
        self._calls.append(("segmentation_update", camera))

    def render(self):
        self._calls.append(("segmentation_render",))
        result = np.full((4, 4, 2), -1, dtype=np.int32)
        result[:, :, 0] = self._geom_type
        return result


def _instrumented_renderer(scene, *, maximum_attempts=2):
    from so101_demo.adapters.perception.mujoco_dataset import (
        MuJoCoDatasetRenderer,
        SceneGeometry,
    )

    mujoco, _, model, data = scene
    calls = []
    renderer = MuJoCoDatasetRenderer.__new__(MuJoCoDatasetRenderer)
    renderer._mujoco = mujoco
    renderer._model = model
    renderer._data = data
    renderer._config = SimpleNamespace(
        camera_name="task_camera",
        geometry=SceneGeometry(maximum_deterministic_attempts=maximum_attempts),
        require_nonpenetrating_scene=True,
    )
    renderer._renderer = _RgbBackendSpy(calls)
    renderer._segmentation_renderer = _SegmentationBackendSpy(
        calls, int(mujoco.mjtObj.mjOBJ_GEOM)
    )
    return renderer, calls


def _prepare_one_cup_state(scene, *, penetrating):
    mujoco, _, model, data = scene
    mujoco.mj_resetData(model, data)
    _position(mujoco, model, data, "cup_free_joint", (0.02, -0.28, 0.165))
    _position(mujoco, model, data, "cup_b_free_joint", (2.0, 2.0, 2.0))
    bottle = (0.07, -0.28, 0.19) if penetrating else (0.11, -0.22, 0.19)
    _position(mujoco, model, data, "bottle_free_joint", bottle)
    mujoco.mj_forward(model, data)


def test_native_penetration_error_carries_exact_immutable_receipt_and_context(scene):
    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetScenario,
    )
    from so101_demo.adapters.perception.mujoco_scene_geometry import (
        ScenePenetrationError,
    )

    renderer, calls = _instrumented_renderer(scene)
    renderer._prepare = lambda random, scenario: _prepare_one_cup_state(
        scene, penetrating=True
    )
    with pytest.raises(ScenePenetrationError) as caught:
        renderer._render_attempt(
            np.random.default_rng(1),
            DatasetScenario.ONE_CUP_DISTRACTORS,
            seed=410000127,
            attempt_index=0,
        )

    error = caught.value
    assert str(error) == "intersecting task visual solids"
    assert error.seed == 410000127
    assert error.scenario == DatasetScenario.ONE_CUP_DISTRACTORS
    assert error.attempt_index == 0
    assert error.receipt.accepted is False
    error.receipt.validate_scope(1)
    assert any(pair.signed_distance_m < -0.001 for pair in error.receipt.pairs)
    with pytest.raises(FrozenInstanceError):
        error.receipt.state_sha256 = "0" * 64
    assert calls == []


def test_message_only_penetration_error_remains_compatible_but_has_no_evidence():
    from so101_demo.adapters.perception.mujoco_scene_geometry import ScenePenetrationError

    error = ScenePenetrationError("legacy penetration")
    assert str(error) == "legacy penetration"
    assert error.receipt is None
    assert error.seed is None
    assert error.scenario is None
    assert error.attempt_index is None


def test_actual_boundaries_emit_ordered_immutable_reject_then_accept_events(scene):
    from so101_demo.adapters.perception.mujoco_dataset import DatasetScenario

    renderer, calls = _instrumented_renderer(scene)
    preparations = 0

    def prepare(random, scenario):
        nonlocal preparations
        _prepare_one_cup_state(scene, penetrating=preparations == 0)
        preparations += 1

    renderer._prepare = prepare
    events = []

    def sink(event):
        events.append(event)
        if event.receipt is not None:
            with pytest.raises(FrozenInstanceError):
                event.receipt.state_sha256 = "0" * 64
        with pytest.raises(FrozenInstanceError):
            event.attempt_index = 99
        return "ignored"

    render = renderer.render(
        410000127,
        DatasetScenario.ONE_CUP_DISTRACTORS,
        event_sink=sink,
    )

    assert [event.kind for event in events] == [
        "geometry_measured",
        "penetration_rejected",
        "geometry_measured",
        "rgb_render_started",
        "rgb_render_finished",
        "segmentation_render_started",
        "segmentation_render_finished",
        "accepted",
    ]
    assert [(event.seed, event.scenario, event.attempt_index) for event in events] == [
        (410000127, DatasetScenario.ONE_CUP_DISTRACTORS, 0),
        (410000127, DatasetScenario.ONE_CUP_DISTRACTORS, 0),
        (410000127, DatasetScenario.ONE_CUP_DISTRACTORS, 1),
        (410000127, DatasetScenario.ONE_CUP_DISTRACTORS, 1),
        (410000127, DatasetScenario.ONE_CUP_DISTRACTORS, 1),
        (410000127, DatasetScenario.ONE_CUP_DISTRACTORS, 1),
        (410000127, DatasetScenario.ONE_CUP_DISTRACTORS, 1),
        (410000127, DatasetScenario.ONE_CUP_DISTRACTORS, 1),
    ]
    assert events[0].receipt is events[1].receipt
    assert events[0].receipt.accepted is False
    assert all(event.receipt is events[2].receipt for event in events[2:])
    assert events[2].receipt.accepted is True
    assert calls == [
        ("rgb_update", "task_camera"),
        ("rgb_render",),
        ("segmentation_update", "task_camera"),
        ("segmentation_render",),
    ]
    assert render.geometry_receipt is events[2].receipt


def test_all_penetrating_attempts_emit_exact_bound_and_make_no_image_calls(scene):
    from so101_demo.adapters.perception.mujoco_dataset import DatasetScenario

    renderer, calls = _instrumented_renderer(scene, maximum_attempts=3)
    renderer._prepare = lambda random, scenario: _prepare_one_cup_state(
        scene, penetrating=True
    )
    events = []

    with pytest.raises(RuntimeError, match="failed 3 deterministic attempts"):
        renderer.render(
            410000127,
            DatasetScenario.ONE_CUP_DISTRACTORS,
            event_sink=events.append,
        )

    assert [event.kind for event in events] == [
        "geometry_measured",
        "penetration_rejected",
    ] * 3
    assert [event.attempt_index for event in events] == [0, 0, 1, 1, 2, 2]
    assert all(event.receipt is not None and not event.receipt.accepted for event in events)
    assert calls == []


def test_event_sink_failure_aborts_before_image_or_next_attempt(scene):
    from so101_demo.adapters.perception.mujoco_dataset import DatasetScenario

    renderer, calls = _instrumented_renderer(scene)
    preparations = 0

    def prepare(random, scenario):
        nonlocal preparations
        preparations += 1
        _prepare_one_cup_state(scene, penetrating=True)

    renderer._prepare = prepare

    def fail_sink(event):
        raise OSError("evidence write failed")

    with pytest.raises(OSError, match="evidence write failed"):
        renderer.render(
            410000127,
            DatasetScenario.ONE_CUP_DISTRACTORS,
            event_sink=fail_sink,
        )
    assert preparations == 1
    assert calls == []


@pytest.mark.parametrize("malformation", ["missing", "accepted", "wrong_scope", "nonfinite"])
def test_observed_retry_rejects_malformed_penetration_evidence(scene, malformation):
    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetScenario,
        SceneGeometry,
        select_bounded_render,
    )
    from so101_demo.adapters.perception.mujoco_scene_geometry import (
        ScenePenetrationError,
        measure_task_scene_geometry,
    )

    mujoco, _, model, data = scene
    _prepare_one_cup_state(scene, penetrating=malformation != "accepted")
    active_cup_count = 0 if malformation == "wrong_scope" else 1
    receipt = measure_task_scene_geometry(
        model,
        data,
        active_cup_count=active_cup_count,
    )
    if malformation == "missing":
        receipt = None
    elif malformation == "nonfinite":
        object.__setattr__(receipt.pairs[0], "signed_distance_m", float("nan"))

    attempts = 0

    def attempt(random):
        nonlocal attempts
        attempts += 1
        raise ScenePenetrationError(
            "penetration",
            receipt=receipt,
            seed=410000127,
            scenario=DatasetScenario.ONE_CUP_DISTRACTORS,
            attempt_index=0,
        )

    with pytest.raises(ValueError, match="receipt|scope|finite"):
        select_bounded_render(
            410000127,
            DatasetScenario.ONE_CUP_DISTRACTORS,
            attempt,
            SceneGeometry(maximum_deterministic_attempts=3),
            require_nonpenetrating_scene=True,
            event_sink=lambda event: None,
        )
    assert attempts == 1


def test_split_free_renderer_settings_are_exact_and_construct_the_real_renderer(scene, monkeypatch):
    import mujoco
    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetConfig,
        MuJoCoDatasetRenderer,
        RendererSettings,
        SceneGeometry,
    )

    _, path, _, _ = scene
    config = DatasetConfig(
        mjcf_path=path,
        split_counts={"train": 1, "val": 1, "test": 1},
        generator_commit="a" * 40,
        geometry=SceneGeometry(maximum_deterministic_attempts=2),
        require_nonpenetrating_scene=True,
    )
    settings = config.renderer_settings()
    assert settings == RendererSettings(
        mjcf_path=path,
        camera_name="task_camera",
        image_width=640,
        image_height=480,
        geometry=config.geometry,
        require_nonpenetrating_scene=True,
    )
    assert not any(
        hasattr(settings, name)
        for name in ("split_counts", "seed_starts", "scenario_quotas", "generator_commit")
    )

    constructed = []

    class Backend:
        def __init__(self, model, *, height, width):
            constructed.append((model, height, width))
            self._mjr_context = SimpleNamespace(offSamples=0)

        def close(self):
            return None

    monkeypatch.setattr(mujoco, "Renderer", Backend)
    renderer = MuJoCoDatasetRenderer(settings)
    try:
        assert renderer._config is settings
        assert [(height, width) for _, height, width in constructed] == [(480, 640), (480, 640)]
    finally:
        renderer.close()
