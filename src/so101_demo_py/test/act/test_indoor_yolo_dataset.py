"""The indoor YOLO dataset plan: deterministic draws from the indoor whitelist, split by asset identity, labels from masks."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from paths import PACKAGE_ROOT
from so101_demo.act import indoor_assets
from so101_demo.act import indoor_yolo_dataset as iyd
from so101_demo.act import scene_variant

ACT_ASSETS = PACKAGE_ROOT / "assets/mujoco/act"
COUNTS = {"train": 60, "val": 20, "test": 20}


@pytest.fixture(scope="module")
def inventories():
    return iyd.layout_inventories(ACT_ASSETS)


@pytest.fixture(scope="module")
def plan(inventories):
    return iyd.build_plan(COUNTS, iyd.MASTER_SEED, inventories)


def test_the_plan_is_a_pure_function_of_the_seed(inventories, plan):
    assert iyd.build_plan(COUNTS, iyd.MASTER_SEED, inventories) == plan
    assert iyd.build_plan(COUNTS, iyd.MASTER_SEED + 1, inventories) != plan
    assert [len([item for item in plan if item["split"] == split]) for split in COUNTS] == list(COUNTS.values())
    assert len({item["sample_id"] for item in plan}) == len(plan)


def test_every_variant_is_accepted_by_the_scene_variant_whitelist(plan):
    drawn = [item for item in plan if item["variant"] is not None]
    assert drawn
    for item in drawn:
        normalized = scene_variant.normalize_variant(item["variant"])
        assert normalized["base"] == "indoor"


def test_the_splits_share_no_texture_hue_band_or_tint_range(plan):
    iyd.check_split_disjoint()
    used = {split: {"textures": set(), "bands": set(), "tints": []} for split in COUNTS}
    for item in plan:
        if item["variant"] is None:
            continue
        fields = item["variant"]["set"]
        entry = used[item["split"]]
        entry["textures"] |= {value for key, value in fields.items() if key.endswith(".texture")}
        entry["bands"].add(item["cup"]["band"])
        entry["tints"] += [value for key, value in fields.items() if key.endswith(".rgba") and not key.startswith("cup")]
    for first, second in (("train", "val"), ("train", "test"), ("val", "test")):
        assert not used[first]["textures"] & used[second]["textures"], (first, second)
        assert not used[first]["bands"] & used[second]["bands"], (first, second)
    for split, entry in used.items():
        assert entry["bands"] <= set(indoor_assets.hue_bands(split))
    train_low = min(channel for tint in used["train"]["tints"] for channel in tint[:3])
    held_out_high = max(channel for split in ("val", "test") for tint in used[split]["tints"] for channel in tint[:3])
    assert held_out_high < train_low


def test_every_surface_texture_comes_from_the_pool_of_its_split_and_suits_the_surface(plan):
    pools = iyd.asset_pools()["pools"]
    for item in plan:
        if item["variant"] is None:
            continue
        for surface in indoor_assets.SURFACES:
            texture = item["variant"]["set"][f"{surface}.texture"]
            assert texture in pools[item["split"]][surface] and indoor_assets.texture_allowed(surface, texture)


def test_the_cup_colour_is_continuous_and_clearly_different_from_the_drawn_surfaces_and_the_ring(inventories):
    big = iyd.build_plan({"train": 150, "val": 60, "test": 60}, 5, inventories)
    drawn = [item for item in big if item["variant"] is not None]
    colours = {tuple(item["variant"]["set"]["cup_material.rgba"]) for item in drawn}
    assert len(colours) == len(drawn) > 200
    assert sum(item["cup"]["satisfied"] for item in drawn) >= 0.99 * len(drawn)
    means = iyd.asset_pools()["means"]
    for item in drawn:
        if not item["cup"]["satisfied"]:
            continue
        fields = item["variant"]["set"]
        surfaces = {surface: indoor_assets.surface_colour(fields[f"{surface}.rgba"], means.get(fields[f"{surface}.texture"], (0.5, 0.5, 0.5)))
                    for surface in indoor_assets.SURFACES}
        assert indoor_assets.cup_distinct(fields["cup_material.rgba"][:3], surfaces)


def test_layouts_b_and_c_are_never_in_train_and_c_only_in_test(plan):
    layouts = {split: {item["layout"] for item in plan if item["split"] == split} for split in COUNTS}
    assert layouts["train"] == {"A"} and layouts["val"] <= {"A", "B"} and layouts["test"] == {"A", "B", "C"}


def test_cup_positions_cover_the_teacher_boundary_polygon_and_stay_inside_it(inventories):
    big = iyd.build_plan({"train": 400}, 7, inventories)
    points = np.array([item["cup_xy"] for item in big])
    assert all(iyd.point_in_polygon(x, y, iyd.REGION_XY) for x, y in points)
    assert points[:, 0].max() - points[:, 0].min() > 0.10 and points[:, 1].max() - points[:, 1].min() > 0.15


def test_the_inventory_lists_only_lights_and_props_the_whitelist_accepts(inventories):
    for layout, inventory in inventories.items():
        assert "ind_main" in inventory["lights"] and "key_light" in inventory["lights"]
        assert inventory["props"] and not [name for name in inventory["props"] if name.startswith(scene_variant._STRUCTURE_PREFIXES)]
    assert "ind_shelf_box_0" in inventories["B"]["props"] and "ind_sofa_seat" in inventories["C"]["props"]


@pytest.mark.parametrize("layout", ["A", "B", "C"])
def test_a_layout_is_materialised_so_that_the_variant_module_can_realize_it(tmp_path, indoor_pool_act, layout):
    drawn = iyd.build_plan({"train": 10, "val": 10, "test": 10}, iyd.MASTER_SEED, iyd.layout_inventories(ACT_ASSETS), iyd.asset_pools(indoor_pool_act))
    nominal_dir = iyd.materialize_layout(indoor_pool_act, layout, tmp_path / layout)
    item = next(item for item in drawn if item["layout"] == layout and item["variant"] is not None)
    realized = scene_variant.realize(nominal_dir, item["variant"])
    assert realized.realized_sha256 and "<mujoco" in realized.xml_text
    assert (nominal_dir.parent / "textures/indoor/wall_white.png").is_file()


def test_the_label_is_a_normalised_yolo_seg_polygon_of_the_mask():
    mask = np.zeros((480, 640), dtype=bool)
    mask[100:140, 200:260] = True
    line = iyd.label_line(mask)
    fields = line.split()
    assert fields[0] == "0" and len(fields) >= 7 and len(fields) % 2 == 1
    values = np.array(fields[1:], dtype=float)
    assert values.min() >= 0.0 and values.max() <= 1.0
    xs, ys = values[0::2], values[1::2]
    assert xs.min() == pytest.approx(200 / 639) and xs.max() == pytest.approx(259 / 639)
    assert ys.min() == pytest.approx(100 / 479) and ys.max() == pytest.approx(139 / 479)
    assert iyd.label_line(np.zeros((480, 640), dtype=bool)) == ""


def test_the_dataset_yaml_names_the_splits_and_the_class():
    text = iyd.dataset_yaml(("train", "val", "test", "eval_dark_nominal"))
    assert "train: images/train" in text and "val: images/val" in text and "test: images/test" in text
    assert "0: plastic_cup" in text and "eval_dark_nominal" not in text.split("names:")[0].split("test:")[0]


def test_the_plan_document_is_canonical_json(plan):
    document = iyd.plan_document(plan, COUNTS, iyd.MASTER_SEED)
    assert json.loads(json.dumps(document)) == document
    assert document["plan_sha256"] == iyd.plan_document(plan, COUNTS, iyd.MASTER_SEED)["plan_sha256"]


def test_hard_positive_sets_put_the_cup_in_the_ambiguity_zone_with_the_split_assets(inventories):
    plan = iyd.build_plan({"train_ring": 30, "val_ring": 10, "test_ring": 10}, 3, inventories)
    x0, x1, y0, y1 = iyd.AMBIGUITY_ZONE
    assert all(x0 <= x <= x1 and y0 <= y <= y1 and iyd.point_in_polygon(x, y, iyd.REGION_XY) for x, y in (item["cup_xy"] for item in plan))
    assert {item["directory"] for item in plan} == {"train", "val", "test"} and not any(item["cup_hidden"] for item in plan)
    assert {item["split"] for item in plan if item["sample_id"].startswith("val_ring")} == {"val"}
    assert all(item["variant"] is not None for item in plan)           # drawn from the whitelist of its own split, not the nominal


def test_negative_sets_hide_the_cup_so_only_the_ring_and_the_room_remain(inventories):
    plan = iyd.build_plan({"train_negative": 12, "test_negative": 6}, 3, inventories)
    assert all(item["cup_hidden"] for item in plan)
    assert {item["layout"] for item in plan if item["split"] == "test"} <= {"A", "B", "C"}
    assert {item["layout"] for item in plan if item["split"] == "train"} <= {"A"}
    iyd.check_split_disjoint()
    train_textures = {value for item in plan if item["split"] == "train" for key, value in item["variant"]["set"].items() if key.endswith(".texture")}
    test_textures = {value for item in plan if item["split"] == "test" for key, value in item["variant"]["set"].items() if key.endswith(".texture")}
    assert not train_textures & test_textures


def test_ring_and_negative_frames_do_not_change_the_plain_plan(inventories):
    base = iyd.build_plan(COUNTS, iyd.MASTER_SEED, inventories)
    extended = iyd.build_plan({**COUNTS, "train_ring": 5, "train_negative": 5}, iyd.MASTER_SEED, inventories)
    assert extended[:len(base)] == base


def test_ringnear_sets_put_the_cup_in_the_polygon_closest_to_the_landing_ring(inventories):
    plan = iyd.build_plan({"train_ringnear": 30, "test_ringnear": 10}, 3, inventories)
    x0, x1, y0, y1 = iyd.RING_NEAR_ZONE
    assert all(x0 <= x <= x1 and y0 <= y <= y1 and iyd.point_in_polygon(x, y, iyd.REGION_XY) for x, y in (item["cup_xy"] for item in plan))
    ring_x, ring_y = iyd.LANDING_RING_XY
    assert max(abs(item["cup_xy"][0] - ring_x) for item in plan) < 0.12 and not any(item["cup_hidden"] for item in plan)
    assert {item["directory"] for item in plan} == {"train", "test"}


@pytest.mark.parametrize("split", ["train", "val", "test"])
def test_the_cup_hue_is_spread_over_the_bands_of_the_split_and_is_not_one_colour(inventories, split):
    """The goal 13 contact sheet showed a green cup in all four draws. The sampler does not do that: over 1200 draws per split the hue covers the
    split's bands, no band takes a third of the draws, and the train bands never include a held-out cup family (blue, purple, green, teal)."""
    import colorsys
    from collections import Counter

    assets = iyd.asset_pools(ACT_ASSETS)
    bands, hues = Counter(), set()
    for index in range(1200):
        item = iyd.draw_sample(1, split, index, inventories, assets=assets)
        if item["variant"] is None:
            continue
        rgb = item["variant"]["set"]["cup_material.rgba"][:3]
        bands[indoor_assets.hue_band_of(rgb)] += 1
        hues.add(round(colorsys.rgb_to_hsv(*rgb)[0], 2))
        assert item["cup"]["satisfied"]
    owned = set(indoor_assets.hue_bands(split))
    total = sum(bands.values())
    assert total >= 1000
    assert set(bands) <= owned and len(bands) >= min(len(owned) - 3, 4) and max(bands.values()) < total / 3, dict(sorted(bands.items()))
    assert len(hues) > 20
    if split == "train":
        assert not set(bands) & set(indoor_assets.held_out_hue_bands())
