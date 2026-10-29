"""Rendering of the indoor YOLO dataset frames: MuJoCo RGB, segmentation mask of the cup geoms and depth (software GL; skipped without MuJoCo)."""

from __future__ import annotations

import math
import os

import numpy as np
import pytest

os.environ.setdefault("MUJOCO_GL", "osmesa")      # before MuJoCo is imported: it picks the GL backend then
mujoco = pytest.importorskip("mujoco")

from paths import PACKAGE_ROOT  # noqa: E402
from so101_demo.act import indoor_yolo_dataset as iyd  # noqa: E402
from so101_demo.act import indoor_yolo_eval as ev  # noqa: E402
from so101_demo.act import indoor_yolo_render as render  # noqa: E402

ACT_ASSETS = PACKAGE_ROOT / "assets/mujoco/act"


@pytest.fixture(scope="module")
def renderer(tmp_path_factory, indoor_pool_act):
    try:
        instance = render.IndoorFrameRenderer(indoor_pool_act, tmp_path_factory.mktemp("indoor-render"))
        instance.render(iyd.draw_sample(1, "eval_dark_nominal", 0, iyd.layout_inventories(indoor_pool_act)))
    except Exception as error:      # noqa: BLE001 - no usable GL context on this host
        pytest.skip(f"no offscreen GL: {error}")
    yield instance
    instance.close()


@pytest.fixture(scope="module")
def inventories(indoor_pool_act):
    return iyd.layout_inventories(indoor_pool_act)


@pytest.fixture(scope="module")
def pools(indoor_pool_act):
    return iyd.asset_pools(indoor_pool_act)


def test_a_frame_has_image_mask_depth_and_the_true_cup_position(renderer, inventories):
    entry = iyd.draw_sample(5, "eval_indoor_nominal", 0, inventories)
    frame = renderer.render(entry)
    assert frame.rgb.shape == (480, 640, 3) and frame.rgb.dtype == np.uint8
    assert frame.mask.shape == (480, 640) and 300 < frame.mask.sum() < 20000
    assert frame.depth.shape == (480, 640) and frame.depth[frame.mask].min() > 0.3
    assert 80 < frame.rgb.mean() < 160                                   # the bright indoor nominal (design target 80 to 130)
    assert frame.cup_xy == pytest.approx(entry["cup_xy"], abs=1e-6)


def test_the_dark_nominal_is_dark_and_the_indoor_nominal_is_bright(renderer, inventories):
    dark = renderer.render(iyd.draw_sample(5, "eval_dark_nominal", 0, inventories))
    bright = renderer.render(iyd.draw_sample(5, "eval_indoor_nominal", 0, inventories))
    assert dark.rgb.mean() < 40 < 80 < bright.rgb.mean()


def test_the_rgbd_circle_fit_of_the_true_mask_recovers_the_cup_xy_within_a_few_millimetres(renderer, inventories):
    for index in range(3):
        entry = iyd.draw_sample(9, "eval_indoor_nominal", index, inventories)
        frame = renderer.render(entry)
        estimate = ev.cup_xy_from_mask_depth(frame.mask, frame.depth, frame.camera)
        assert estimate is not None and math.dist(estimate["xy"], entry["cup_xy"]) < 0.006


@pytest.mark.parametrize("layout", ["A", "B", "C"])
def test_every_layout_renders_with_a_variant_and_the_cup_stays_visible(renderer, inventories, pools, layout):
    entry = next(item for item in (iyd.draw_sample(3, "test", index, inventories, assets=pools) for index in range(60)) if item["layout"] == layout)
    frame = renderer.render(entry)
    assert frame.mask.sum() > 300 and frame.realized_sha256 and len(frame.realized_sha256) == 64
    assert frame.cup_rgba == pytest.approx(entry["variant"]["set"]["cup_material.rgba"])


def test_rendering_is_deterministic(renderer, inventories, pools):
    entry = iyd.draw_sample(11, "val", 4, inventories, assets=pools)
    first, second = renderer.render(entry), renderer.render(entry)
    # software GL (osmesa) is bit-exact; the gate renders with EGL on the GPU, where a few pixels differ by one level between two renders of the same frame
    difference = np.abs(first.rgb.astype(int) - second.rgb.astype(int))
    assert difference.max() <= 1 and (difference > 0).sum() <= 100
    assert np.array_equal(first.mask, second.mask) and first.realized_sha256 == second.realized_sha256


def test_the_cup_mask_covers_the_visible_cup_geoms_only(renderer, inventories):
    frame = renderer.render(iyd.draw_sample(5, "eval_indoor_nominal", 1, inventories))
    colour = frame.rgb[frame.mask].astype(float).mean(axis=0)
    assert colour[0] > colour[2]                                         # the nominal cup is orange: more red than blue under the mask


def test_a_negative_frame_hides_the_cup_and_keeps_the_ring_and_the_room(renderer, inventories, pools):
    entry = iyd.draw_sample(5, "test_negative", 0, inventories, assets=pools)
    frame = renderer.render(entry)
    assert frame.mask.sum() == 0 and frame.rgb.mean() > 40
    positive = renderer.render({**entry, "cup_hidden": False})
    assert positive.mask.sum() > 300 and not np.array_equal(frame.rgb, positive.rgb)
