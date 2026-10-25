"""The indoor YOLO dataset plan: deterministic draws from the indoor whitelist, split by asset identity, labels from masks."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from paths import PACKAGE_ROOT
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


def test_the_train_split_shares_no_texture_cup_family_or_tint_range_with_val_and_test(plan):
    iyd.check_split_disjoint()
    used = {split: {"textures": set(), "cups": set(), "tints": []} for split in COUNTS}
    for item in plan:
        if item["variant"] is None:
            continue
        fields = item["variant"]["set"]
        entry = used[item["split"]]
        entry["textures"] |= {value for key, value in fields.items() if key.endswith(".texture")}
        entry["cups"].add(item["cup_family"])
        entry["tints"] += [value for key, value in fields.items() if key.endswith(".rgba") and not key.startswith("cup")]
    for held_out in ("val", "test"):
        assert not used["train"]["textures"] & used[held_out]["textures"]
        assert not used["train"]["cups"] & used[held_out]["cups"]
    assert not used["val"]["cups"] & used["test"]["cups"]
    train_low = min(channel for tint in used["train"]["tints"] for channel in tint[:3])
    held_out_high = max(channel for split in ("val", "test") for tint in used[split]["tints"] for channel in tint[:3])
    assert held_out_high < train_low


def test_layout_c_appears_only_in_the_test_split(plan):
    layouts = {split: {item["layout"] for item in plan if item["split"] == split} for split in COUNTS}
    assert "C" not in layouts["train"] and "C" not in layouts["val"] and layouts["train"] <= {"A", "B"}
    assert layouts["test"] == {"A", "B", "C"}


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
def test_a_layout_is_materialised_so_that_the_variant_module_can_realize_it(tmp_path, plan, layout):
    nominal_dir = iyd.materialize_layout(ACT_ASSETS, layout, tmp_path / layout)
    item = next(item for item in plan if item["layout"] == layout and item["variant"] is not None)
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
    assert {item["layout"] for item in plan if item["split"] == "train"} <= {"A", "B"}
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
