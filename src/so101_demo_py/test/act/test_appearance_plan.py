"""The appearance plan of an indoor collection (indoor P3, T1): a pure draw of (seed, scene id) over the closed `indoor` whitelist.

Pins: the 25 % nominal share, layout A only, the held-out assets (layouts B and C, two textures, four cup colour families, dark tints) never
drawn, the physics fingerprint of every draw equal to the nominal one, the YOLO split policy and the pools in step, the Teacher source rule."""

from __future__ import annotations

import copy
import json
from collections import Counter

import numpy as np
import pytest
from PIL import Image

from paths import PACKAGE_ROOT
from so101_demo.act import appearance_plan as ap
from so101_demo.act import indoor_yolo_dataset as iyd
from so101_demo.act import scene_variant, scene_variant_run

NOMINAL_DIR = PACKAGE_ROOT / "assets/mujoco/act"
TEXTURES = PACKAGE_ROOT / "assets/mujoco/textures/indoor"


@pytest.fixture(scope="module")
def inventory():
    return ap.scene_inventory(NOMINAL_DIR)


@pytest.fixture(scope="module")
def plan(inventory):
    return ap.make_plan(seed=710025, nominal_share=0.25, nominal_scene_sha256=inventory["scene_sha256"])


def ids(count, prefix="p3"):
    return [f"{prefix}-{index:03d}" for index in range(count)]


def test_a_draw_is_a_pure_function_of_the_plan_and_the_scene_id(plan, inventory):
    first = [ap.derive(plan, scene, inventory) for scene in ids(40)]
    assert first == [ap.derive(plan, scene, inventory) for scene in ids(40)]
    assert first == [ap.derive(plan, scene, inventory) for scene in reversed(ids(40))][::-1]
    other = ap.make_plan(seed=710026, nominal_share=0.25, nominal_scene_sha256=inventory["scene_sha256"])
    assert [item["variant_sha256"] for item in first] != [ap.derive(other, scene, inventory)["variant_sha256"] for scene in ids(40)]
    assert len({item["draw_sha256"] for item in first}) == 40


def test_the_nominal_share_is_about_a_quarter_and_every_nominal_episode_has_no_variant(plan, inventory):
    draws = [ap.derive(plan, scene, inventory) for scene in ids(2000)]
    share = sum(1 for item in draws if item["kind"] == ap.KIND_NOMINAL) / len(draws)
    assert 0.22 < share < 0.28
    for item in draws:
        assert (item["variant"] is None) == (item["kind"] == ap.KIND_NOMINAL)
        assert (item["variant_sha256"] is None) == (item["variant"] is None)
        assert (item["cup_family"] is None) == (item["variant"] is None)
    none = ap.make_plan(seed=1, nominal_share=0.0, nominal_scene_sha256=inventory["scene_sha256"])
    assert all(ap.derive(none, scene, inventory)["kind"] == ap.KIND_RANDOMISED for scene in ids(50))
    every = ap.make_plan(seed=1, nominal_share=1.0, nominal_scene_sha256=inventory["scene_sha256"])
    assert all(ap.derive(every, scene, inventory)["kind"] == ap.KIND_NOMINAL for scene in ids(50))


def test_a_randomised_draw_is_a_valid_indoor_variant_over_layout_a(plan, inventory):
    drawn = [ap.derive(plan, scene, inventory) for scene in ids(200)]
    randomised = [item for item in drawn if item["variant"] is not None]
    assert randomised and all(item["layout"] == "A" for item in drawn)
    for item in randomised:
        variant = item["variant"]
        assert variant["base"] == "indoor"
        document = {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": variant["name"], "base": "indoor", "set": variant["set"]}
        assert scene_variant.normalize_variant(document) == variant
        assert scene_variant.variant_sha256(variant) == item["variant_sha256"]
        fields = variant["set"]
        assert {"wall.texture", "floor.texture", "table.texture", "cup_material.rgba", "headlight.ambient"} <= set(fields)
        assert all(f"light.{name}.diffuse" in fields for name in inventory["lights"])
        assert {f"prop.{name}.visible" for name in inventory["props"]} <= set(fields)


def test_nothing_held_out_is_ever_drawn(plan, inventory):
    drawn = [ap.derive(plan, scene, inventory) for scene in ids(1500)]
    textures = Counter()
    for item in drawn:
        if item["variant"] is None:
            continue
        fields = item["variant"]["set"]
        for surface in ("wall", "floor", "table"):
            textures[fields[f"{surface}.texture"]] += 1
            assert min(fields[f"{surface}.rgba"][:3]) >= ap.TINT_BAND[0] and max(fields[f"{surface}.rgba"][:3]) <= ap.TINT_BAND[1]
        assert item["cup_family"] in ap.POOLS["cups"] and item["cup_family"] not in ap.HELD_OUT["cups"]
    assert not set(textures) & set(ap.HELD_OUT["textures"])
    assert set(textures) == set(ap.POOLS["wall"]) | set(ap.POOLS["floor"]) | set(ap.POOLS["table"])      # every collected texture is drawn
    assert Counter(item["cup_family"] for item in drawn if item["variant"]).keys() == set(ap.POOLS["cups"])
    assert {item["layout"] for item in drawn} == {"A"}


def test_the_held_out_set_is_explicit_and_agrees_with_the_yolo_validation_and_test_assets():
    policy = iyd.SPLIT_POLICY
    held_textures = set()
    for split in ("val", "test"):
        for surface in ("wall", "floor", "table"):
            held_textures |= set(policy[split][surface])
    assert held_textures == set(ap.HELD_OUT["textures"])
    assert set(policy["val"]["cups"]) | set(policy["test"]["cups"]) == set(ap.HELD_OUT["cups"])
    assert {layout for split in ("val", "test") for layout in policy[split]["layouts"]} - set(policy["train"]["layouts"]) == {"C"}
    assert set(ap.HELD_OUT["layouts"]) == {"B", "C"} and ap.LAYOUT == "A"
    # the collected pools are the YOLO training pools (layout A only)
    for surface in ("wall", "floor", "table"):
        assert set(ap.POOLS[surface]) == set(policy["train"][surface])
    assert set(ap.POOLS["cups"]) == set(policy["train"]["cups"])
    assert ap.TINT_BAND == policy["train"]["tint"] and ap.HELD_OUT["tint_below"] == ap.TINT_BAND[0]
    assert max(policy[split]["tint"][1] for split in ("val", "test")) < ap.TINT_BAND[0]
    ap.check_pools()


def test_a_variant_naming_a_held_out_asset_is_refused(plan, inventory):
    base = next(item for item in (ap.derive(plan, scene, inventory) for scene in ids(50)) if item["variant"] is not None)["variant"]
    for key, value in (("wall.texture", "wall_beige"), ("floor.texture", "floor_parquet"), ("table.texture", "floor_parquet"),
                       ("wall.rgba", [0.6, 0.9, 0.9, 1.0]), ("cup_material.rgba", [0.15, 0.3, 0.85, 1.0]),
                       ("cup_material.rgba", [0.5, 0.2, 0.7, 1.0]), ("cup_material.rgba", [0.2, 0.7, 0.25, 1.0]),
                       ("cup_material.rgba", [0.1, 0.65, 0.65, 1.0])):
        variant = copy.deepcopy(base)
        variant["set"][key] = value
        with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_HELD_OUT"):
            ap.check_not_held_out(variant)
    ap.check_not_held_out(base)


def test_a_collected_texture_outside_the_pools_is_refused_too(plan, inventory):
    base = next(item for item in (ap.derive(plan, scene, inventory) for scene in ids(50)) if item["variant"] is not None)["variant"]
    variant = copy.deepcopy(base)
    variant["set"]["floor.texture"] = "floor_carpet" if variant["set"]["floor.texture"] != "floor_carpet" else "floor_tile_grey"
    ap.check_not_held_out(variant)
    variant["set"]["wall.texture"] = "wall_white"
    ap.check_not_held_out(variant)
    variant["set"]["table.texture"] = "wall_white"
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_HELD_OUT_TEXTURE"):
        ap.check_not_held_out(variant)


def test_the_cup_never_blends_into_the_table_or_the_wall(plan, inventory):
    for scene in ids(600):
        item = ap.derive(plan, scene, inventory)
        if item["variant"] is None:
            continue
        fields = item["variant"]["set"]
        cup = fields["cup_material.rgba"][:3]
        for surface in ("table", "wall"):
            colour = ap._surface_colour(fields[f"{surface}.texture"], fields[f"{surface}.rgba"])
            assert ap._distance(cup, colour) >= ap.BLEND_MIN_DISTANCE


def test_a_cup_that_always_blends_is_an_error_not_a_silent_choice(monkeypatch):
    monkeypatch.setattr(ap, "BLEND_MIN_DISTANCE", 10.0)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_CUP_ALWAYS_BLENDS"):
        ap._cup(1, "x", {"table": (0.5, 0.5, 0.5)})


def test_the_texture_mean_constants_are_the_files():
    for name, mean in ap.TEXTURE_MEAN_RGB.items():
        pixels = np.asarray(Image.open(TEXTURES / f"{name}.png").convert("RGB"), dtype=float) / 255.0
        assert np.allclose(pixels.reshape(-1, 3).mean(0), mean, atol=1e-3), name


def test_every_draw_keeps_the_stripped_physics_fingerprint_of_the_nominal_scene(plan, inventory, tmp_path):
    drawn = [item for item in (ap.derive(plan, scene, inventory) for scene in ids(12)) if item["variant"] is not None]
    assert len(drawn) >= 6
    for item in drawn:
        record = scene_variant_run.realize_into(tmp_path / item["variant"]["name"], PACKAGE_ROOT, item["variant"])
        assert record["physics_fingerprint"] == record["nominal_physics_fingerprint"] and record["fingerprint_version"] == 2
        assert record["variant_sha256"] == item["variant_sha256"]


def test_the_realized_hash_differs_between_two_appearances_and_repeats_for_one(plan, inventory, tmp_path):
    drawn = [item for item in (ap.derive(plan, scene, inventory) for scene in ids(12)) if item["variant"] is not None][:3]
    first = [scene_variant_run.realize_into(tmp_path / f"a{i}", PACKAGE_ROOT, item["variant"])["realized_sha256"] for i, item in enumerate(drawn)]
    again = [scene_variant_run.realize_into(tmp_path / f"b{i}", PACKAGE_ROOT, item["variant"])["realized_sha256"] for i, item in enumerate(drawn)]
    assert first == again and len(set(first)) == 3


def test_the_teacher_source_follows_the_kind_and_the_privileged_pose_is_indoor_randomised_only(plan, inventory):
    assert ap.teacher_source_for(ap.KIND_NOMINAL) == ap.TEACHER_SOURCE_CAMERA
    assert ap.teacher_source_for(ap.KIND_RANDOMISED) == ap.TEACHER_SOURCE_PRIVILEGED
    with pytest.raises(ap.AppearanceInvalid):
        ap.teacher_source_for("other")
    privileged, camera = ap.TEACHER_SOURCE_PRIVILEGED, ap.TEACHER_SOURCE_CAMERA
    assert ap.teacher_source_allowed("side-wrist-indoor", privileged, ap.KIND_RANDOMISED)
    assert not ap.teacher_source_allowed("side-wrist-indoor", privileged, ap.KIND_NOMINAL)
    for rig in ("side-wrist", "head-wrist", None):
        assert not ap.teacher_source_allowed(rig, privileged, ap.KIND_RANDOMISED)
    assert ap.teacher_source_allowed("side-wrist-indoor", camera, ap.KIND_NOMINAL)
    assert not ap.teacher_source_allowed("side-wrist-indoor", camera, ap.KIND_RANDOMISED)
    assert not ap.teacher_source_allowed("side-wrist-indoor", "other", ap.KIND_NOMINAL)


def test_annotated_rows_are_verified_and_any_edit_is_refused(plan, inventory):
    rows = [{"scene_id": scene, "seed": index, "split": "formal", "cup_position_world_m": [0.0, -0.2, 0.165]} for index, scene in enumerate(ids(30))]
    annotated = ap.annotate_rows(plan, rows, inventory)
    assert [row["scene_id"] for row in annotated] == [row["scene_id"] for row in rows]
    assert {row["teacher_source"] for row in annotated} == {ap.TEACHER_SOURCE_CAMERA, ap.TEACHER_SOURCE_PRIVILEGED}
    for row in annotated:
        assert ap.verify_row(plan, row, inventory) == row["appearance"]
    randomised = next(row for row in annotated if row["appearance"]["variant"] is not None)
    tampered = copy.deepcopy(randomised)
    tampered["appearance"]["variant"]["set"]["wall.texture"] = "wall_grey" if randomised["appearance"]["variant"]["set"]["wall.texture"] != "wall_grey" else "wall_white"
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_ROW_NOT_DERIVED"):
        ap.verify_row(plan, tampered, inventory)
    swapped = copy.deepcopy(randomised)
    swapped["teacher_source"] = ap.TEACHER_SOURCE_CAMERA
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_TEACHER_SOURCE_MISMATCH"):
        ap.verify_row(plan, swapped, inventory)
    other_scene = copy.deepcopy(randomised)
    other_scene["scene_id"] = "p3-zzz"
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_ROW_NOT_DERIVED"):
        ap.verify_row(plan, other_scene, inventory)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_ROW_MISSING"):
        ap.verify_row(plan, rows[0], inventory)


def test_the_plan_is_closed_hashed_and_bound_to_the_installed_indoor_scene(plan, inventory):
    assert ap.validate_plan(json.loads(json.dumps(plan))) == plan
    for key, value in (("seed", 1), ("nominal_share", 0.5), ("layout", "B"), ("rig", "side-wrist")):
        bad = {**plan, key: value}
        with pytest.raises(ap.AppearanceInvalid):
            ap.validate_plan(bad)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PLAN_SHAPE_INVALID"):
        ap.validate_plan({**plan, "extra": 1})
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PLAN_LAYOUT_INVALID"):
        ap.validate_plan({**plan, "layout": "C"})
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PLAN_SHARE_INVALID"):
        ap.make_plan(seed=1, nominal_share=1.5, nominal_scene_sha256=inventory["scene_sha256"])
    other = ap.make_plan(seed=710025, nominal_share=0.25, nominal_scene_sha256="0" * 64)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_NOMINAL_SCENE_MISMATCH"):
        ap.derive(other, "p3-000", inventory)


def test_the_inventory_names_the_lights_and_props_the_whitelist_can_edit(inventory):
    assert {"key_light", "ind_main", "ind_fill0", "ind_dirfill0"} <= set(inventory["lights"])
    assert "ind_poster" in inventory["props"] and not any(name.startswith(scene_variant._STRUCTURE_PREFIXES) for name in inventory["props"])
    assert len(inventory["headlight"]["ambient"]) == 3
