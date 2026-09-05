"""Renderer context isolation prevents categorical color-ID blending."""
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from so101_demo.adapters.perception.mujoco_dataset import MuJoCoDatasetRenderer


def backend(monkeypatch, *, fail_second=False, ignore_zero=False):
    model = SimpleNamespace(vis=SimpleNamespace(quality=SimpleNamespace(offsamples=4)),
                            cam_pos=np.zeros((1, 3)), cam_mat0=np.eye(3).reshape(1, 9))
    contexts = []

    class Context:
        def __init__(self, model, *, height, width):
            assert (height, width) == (2, 3)
            if contexts and fail_second:
                raise RuntimeError("context creation failed")
            self._mjr_context = SimpleNamespace(offSamples=4 if ignore_zero else model.vis.quality.offsamples)
            self.closed = False
            self.segmentation = False
            self.fail_render = False
            contexts.append(self)

        def enable_segmentation_rendering(self):
            self.segmentation = True

        def disable_segmentation_rendering(self):
            self.segmentation = False

        def update_scene(self, data, *, camera):
            assert camera == "task_camera"

        def render(self):
            if self.fail_render:
                raise RuntimeError("readback failed")
            assert self.segmentation
            output = np.zeros((2, 3, 2), dtype=np.int32)
            output[:, :, 0] = 3 if self._mjr_context.offSamples == 0 else 91
            output[:, :, 1] = 5
            return output

        def close(self):
            self.closed = True

    api = SimpleNamespace(MjModel=SimpleNamespace(from_xml_path=lambda path: model),
                          MjData=lambda model: object(), Renderer=Context,
                          mj_name2id=lambda *args: 0,
                          mjtObj=SimpleNamespace(mjOBJ_CAMERA=7, mjOBJ_GEOM=5))
    monkeypatch.setitem(sys.modules, "mujoco", api)
    config = SimpleNamespace(mjcf_path="scene.xml", image_height=2, image_width=3, camera_name="task_camera")
    return model, contexts, config


def test_segmentation_uses_zero_sample_context_without_changing_rgb_context(monkeypatch):
    model, contexts, config = backend(monkeypatch)
    renderer = MuJoCoDatasetRenderer(config)
    assert np.array_equal(renderer._segmentation(), np.full((2, 3), 3))
    assert [c._mjr_context.offSamples for c in contexts] == [4, 0]
    assert model.vis.quality.offsamples == 4
    assert contexts[0].segmentation is False
    renderer.close()
    assert all(c.closed for c in contexts)


def test_categorical_context_creation_failure_restores_model_and_closes_rgb(monkeypatch):
    model, contexts, config = backend(monkeypatch, fail_second=True)
    with pytest.raises(RuntimeError, match="context creation failed"):
        MuJoCoDatasetRenderer(config)
    assert model.vis.quality.offsamples == 4
    assert contexts[0].closed


def test_backend_ignoring_zero_samples_is_rejected_and_both_contexts_closed(monkeypatch):
    model, contexts, config = backend(monkeypatch, ignore_zero=True)
    with pytest.raises(RuntimeError, match="CATEGORICAL_MULTISAMPLING_FORBIDDEN"):
        MuJoCoDatasetRenderer(config)
    assert model.vis.quality.offsamples == 4
    assert len(contexts) == 2 and all(c.closed for c in contexts)


def test_segmentation_readback_failure_restores_categorical_mode(monkeypatch):
    _, contexts, config = backend(monkeypatch)
    renderer = MuJoCoDatasetRenderer(config)
    assert len(contexts) == 2
    contexts[1].fail_render = True
    with pytest.raises(RuntimeError, match="readback failed"):
        renderer._segmentation()
    assert contexts[1].segmentation is False
    assert contexts[0].segmentation is False
    renderer.close()
