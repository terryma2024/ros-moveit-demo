"""The appearance plan of an indoor collection (indoor P3, T1): a pure draw of (seed, scene id) over the closed `indoor` whitelist.

Pins: the 25 % nominal share, layout A only, the held-out assets (layouts B and C, two textures, four cup colour families, dark tints) never
drawn, the physics fingerprint of every draw equal to the nominal one, the YOLO split policy and the pools in step, the Teacher source rule."""

from __future__ import annotations

import colorsys
import copy
import hashlib
import json
import shutil
from collections import Counter

import numpy as np
import pytest
from PIL import Image

from paths import PACKAGE_ROOT
from so101_demo.act import appearance_plan as ap
from so101_demo.act import indoor_assets
from so101_demo.act import indoor_yolo_dataset as iyd
from so101_demo.act import scene_variant, scene_variant_run

NOMINAL_DIR = PACKAGE_ROOT / "assets/mujoco/act"
TEXTURES = PACKAGE_ROOT / "assets/mujoco/textures/indoor"


@pytest.fixture(scope="module")
def inventory():
    return ap.scene_inventory(NOMINAL_DIR)


@pytest.fixture(scope="module")
def plan(inventory):
    return ap.make_plan(seed=710025, nominal_share=0.25, nominal_scene_sha256=inventory["scene_sha256"], pool_identity=inventory["pool_identity"])


def ids(count, prefix="p3"):
    return [f"{prefix}-{index:03d}" for index in range(count)]


def test_a_draw_is_a_pure_function_of_the_plan_and_the_scene_id(plan, inventory):
    first = [ap.derive(plan, scene, inventory) for scene in ids(40)]
    assert first == [ap.derive(plan, scene, inventory) for scene in ids(40)]
    assert first == [ap.derive(plan, scene, inventory) for scene in reversed(ids(40))][::-1]
    other = ap.make_plan(seed=710026, nominal_share=0.25, nominal_scene_sha256=inventory["scene_sha256"], pool_identity=inventory["pool_identity"])
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
    none = ap.make_plan(seed=1, nominal_share=0.0, nominal_scene_sha256=inventory["scene_sha256"], pool_identity=inventory["pool_identity"])
    assert all(ap.derive(none, scene, inventory)["kind"] == ap.KIND_RANDOMISED for scene in ids(50))
    every = ap.make_plan(seed=1, nominal_share=1.0, nominal_scene_sha256=inventory["scene_sha256"], pool_identity=inventory["pool_identity"])
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
    pools = inventory["pools"]
    owned = {split: {texture for ids_ in pools[split].values() for texture in ids_} for split in ("train", "val", "test")}
    train_bands, held_bands = set(indoor_assets.hue_bands("train")), set(ap.HELD_OUT["cup_hue_bands"])
    drawn = [ap.derive(plan, scene, inventory) for scene in ids(1500)]
    textures, bands = Counter(), Counter()
    for item in drawn:
        if item["variant"] is None:
            continue
        fields = item["variant"]["set"]
        for surface in ("wall", "floor", "table"):
            textures[fields[f"{surface}.texture"]] += 1
            assert fields[f"{surface}.texture"] in pools["train"][surface]
            assert min(fields[f"{surface}.rgba"][:3]) >= ap.TINT_BAND[0] and max(fields[f"{surface}.rgba"][:3]) <= ap.TINT_BAND[1]
        band = indoor_assets.hue_band_of(fields["cup_material.rgba"])
        assert item["cup_family"] == f"hue-band-{band:02d}" and band in train_bands and band not in held_bands
        bands[band] += 1
    assert not set(textures) & set(ap.HELD_OUT["textures"])
    assert not set(textures) & (owned["val"] | owned["test"])               # no val or test texture, and no held-out one
    assert any(name.startswith("proc/") for name in textures) and any(name.startswith("cc0/") for name in textures)
    assert any(not name.startswith(("proc/", "cc0/")) for name in textures)         # the legacy train textures are drawn too
    # nothing but train bands; the red ones are rare by design (the landing-ring contrast rule), so a couple may be missing from this sample
    assert set(bands) <= train_bands and len(set(bands)) >= len(train_bands) - 2
    assert {item["layout"] for item in drawn} == {"A"}


#: the validation and test assets of the indoor YOLO fine-tune, as it was trained (CP-3785): the literal list the appearance plan must keep out of
#: its pools. (The sampler of `indoor_yolo_dataset` now draws the three splits from the identity pools of `indoor_assets`, so it no longer names them.)
YOLO_FINETUNE_HELD_OUT = {"textures": {"wall_beige", "floor_parquet"}, "cups": {"blue", "purple", "green", "teal"}, "layouts": {"B", "C"},
                          "tints_below": 0.82}


def test_the_held_out_set_is_explicit_and_agrees_with_the_yolo_validation_and_test_assets(inventory):
    assert set(ap.HELD_OUT["textures"]) == YOLO_FINETUNE_HELD_OUT["textures"]
    assert set(ap.HELD_OUT["cups"]) == YOLO_FINETUNE_HELD_OUT["cups"]
    assert set(ap.HELD_OUT["layouts"]) == YOLO_FINETUNE_HELD_OUT["layouts"] and ap.LAYOUT == "A"
    assert ap.HELD_OUT["tint_below"] == YOLO_FINETUNE_HELD_OUT["tints_below"] == ap.TINT_BAND[0]
    policy = iyd.SPLIT_POLICY
    assert set(policy["train"]["layouts"]) == {"A"}
    assert {layout for split in ("val", "test") for layout in policy[split]["layouts"]} == YOLO_FINETUNE_HELD_OUT["layouts"] | {"A"}
    assert ap.TINT_BAND == policy["train"]["tint"]
    assert max(policy[split]["tint"][1] for split in ("val", "test")) < ap.TINT_BAND[0]
    # no held-out legacy texture and no held-out cup colour box reaches a train pool, whatever the pools of the install
    train = {texture for ids_ in inventory["pools"]["train"].values() for texture in ids_}
    assert not train & YOLO_FINETUNE_HELD_OUT["textures"]
    assert {"wall_beige", "floor_parquet"} <= {texture for ids_ in inventory["pools"]["val"].values() for texture in ids_}
    train_bands = set(indoor_assets.hue_bands("train"))
    assert not train_bands & set(ap.HELD_OUT["cup_hue_bands"])
    assert set(ap.HELD_OUT["cup_hue_bands"]) == {11, 12, 13, 14, 16, 17, 18, 19, 21, 22, 23, 26, 27, 28, 29}
    for family in YOLO_FINETUNE_HELD_OUT["cups"]:
        base = np.asarray(ap.CUP_FAMILIES[family])
        for offset in np.ndindex(3, 3, 3):
            colour = np.clip(base + (np.asarray(offset) - 1) * ap.CUP_JITTER, 0, 1)      # the corners and the middle of the family's colour box
            assert indoor_assets.hue_band_of(colour) not in train_bands, (family, offset)
    ap.check_pools(inventory)
    ap.check_pools()


def test_the_train_pools_keep_the_split_sizes_and_the_held_out_moves_are_documented(inventory):
    pools = inventory["pools"]
    assert [len(pools[split]["wall"]) for split in ("train", "val", "test")] == [401, 89, 88]
    assert [len(pools[split]["floor"]) for split in ("train", "val", "test")] == [477, 106, 105]
    assert [len(pools[split]["table"]) for split in ("train", "val", "test")] == [409, 91, 90]
    # the hue bands: antzb's seeded split gave 26/5/5; the 11 train bands of the held-out cup families (green, teal, blue, purple) moved to val and test
    assert [len(indoor_assets.hue_bands(split)) for split in ("train", "val", "test")] == [15, 11, 10]
    assert indoor_assets.hue_bands("train") == [1, 2, 3, 4, 6, 7, 9, 10, 20, 30, 31, 32, 33, 34, 35]
    assert set(indoor_assets.hue_bands("val")) | set(indoor_assets.hue_bands("test")) >= set(ap.HELD_OUT["cup_hue_bands"])


def test_a_variant_naming_a_held_out_asset_is_refused(plan, inventory):
    base = next(item for item in (ap.derive(plan, scene, inventory) for scene in ids(50)) if item["variant"] is not None)["variant"]
    for key, value in (("wall.texture", "wall_beige"), ("floor.texture", "floor_parquet"), ("table.texture", "floor_parquet"),
                       ("wall.rgba", [0.6, 0.9, 0.9, 1.0]), ("cup_material.rgba", [0.15, 0.3, 0.85, 1.0]),
                       ("cup_material.rgba", [0.5, 0.2, 0.7, 1.0]), ("cup_material.rgba", [0.2, 0.7, 0.25, 1.0]),
                       ("cup_material.rgba", [0.1, 0.65, 0.65, 1.0]),
                       # val and test pool assets are refused as well, not only the held-out ones of the YOLO fine-tune
                       ("wall.texture", inventory["pools"]["val"]["wall"][5]), ("floor.texture", inventory["pools"]["test"]["floor"][5]),
                       ("table.texture", inventory["pools"]["val"]["table"][-1]),
                       ("cup_material.rgba", [round(c, 4) for c in colorsys.hsv_to_rgb(255 / 360, 0.9, 0.9)] + [1.0])):   # hue band 25: a val band, not a family of the fine-tune
        variant = copy.deepcopy(base)
        variant["set"][key] = value
        with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_HELD_OUT"):
            ap.check_not_held_out(variant, inventory)
    ap.check_not_held_out(base, inventory)


def test_a_collected_texture_outside_the_pools_is_refused_too(plan, inventory):
    base = next(item for item in (ap.derive(plan, scene, inventory) for scene in ids(50)) if item["variant"] is not None)["variant"]
    variant = copy.deepcopy(base)
    variant["set"]["floor.texture"] = "floor_carpet" if variant["set"]["floor.texture"] != "floor_carpet" else "floor_tile_grey"
    ap.check_not_held_out(variant, inventory)
    variant["set"]["wall.texture"] = "wall_white"
    ap.check_not_held_out(variant, inventory)
    variant["set"]["table.texture"] = "wall_white"
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_HELD_OUT_TEXTURE"):
        ap.check_not_held_out(variant, inventory)


def test_the_cup_is_clearly_different_from_the_wall_floor_table_and_the_ring_and_its_hue_is_spread_over_the_train_bands(plan, inventory):
    bands = Counter()
    for scene in ids(1200):
        item = ap.derive(plan, scene, inventory)
        if item["variant"] is None:
            continue
        fields = item["variant"]["set"]
        cup = fields["cup_material.rgba"][:3]
        colours = {surface: ap._surface_colour(fields[f"{surface}.texture"], fields[f"{surface}.rgba"], inventory["means"])
                   for surface in indoor_assets.SURFACES}
        assert indoor_assets.cup_distinct(cup, colours)
        bands[indoor_assets.hue_band_of(cup)] += 1
    total = sum(bands.values())
    # the red-green-cups flag of the goal 13 contact sheet: the cup is not one colour. The hue histogram over 900 draws covers most train bands
    # and no band takes more than a fifth of the draws
    assert len(bands) >= 12 and max(bands.values()) < 0.2 * total, dict(sorted(bands.items()))


def test_a_cup_that_always_blends_is_an_error_not_a_silent_choice(monkeypatch):
    monkeypatch.setattr(indoor_assets, "MIN_DELTA_E", {"wall": 10.0, "floor": 10.0, "table": 10.0, "ring": 10.0})
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_CUP_ALWAYS_BLENDS"):
        ap._cup(1, "x", {"table": (0.5, 0.5, 0.5)})


def test_the_texture_mean_constants_are_the_files():
    for name, mean in ap.TEXTURE_MEAN_RGB.items():
        pixels = np.asarray(Image.open(TEXTURES / f"{name}.png").convert("RGB"), dtype=float) / 255.0
        assert np.allclose(pixels.reshape(-1, 3).mean(0), mean, atol=1e-3), name


def test_every_draw_keeps_the_stripped_physics_fingerprint_of_the_nominal_scene(plan, inventory, tmp_path, indoor_pool_share):
    drawn = [item for item in (ap.derive(plan, scene, inventory) for scene in ids(40)) if item["variant"] is not None]
    assert len(drawn) >= 20
    for item in drawn:
        record = scene_variant_run.realize_into(tmp_path / item["variant"]["name"], indoor_pool_share, item["variant"])
        assert record["physics_fingerprint"] == record["nominal_physics_fingerprint"] and record["fingerprint_version"] == 2
        assert record["variant_sha256"] == item["variant_sha256"]


def test_the_realized_hash_differs_between_two_appearances_and_repeats_for_one(plan, inventory, tmp_path, indoor_pool_share):
    drawn = [item for item in (ap.derive(plan, scene, inventory) for scene in ids(12)) if item["variant"] is not None][:3]
    first = [scene_variant_run.realize_into(tmp_path / f"a{i}", indoor_pool_share, item["variant"])["realized_sha256"] for i, item in enumerate(drawn)]
    again = [scene_variant_run.realize_into(tmp_path / f"b{i}", indoor_pool_share, item["variant"])["realized_sha256"] for i, item in enumerate(drawn)]
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
        ap.make_plan(seed=1, nominal_share=1.5, nominal_scene_sha256=inventory["scene_sha256"], pool_identity=inventory["pool_identity"])
    other = ap.make_plan(seed=710025, nominal_share=0.25, nominal_scene_sha256="0" * 64, pool_identity=inventory["pool_identity"])
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_NOMINAL_SCENE_MISMATCH"):
        ap.derive(other, "p3-000", inventory)


def test_the_plan_hash_includes_the_pool_identity_and_a_plan_for_other_pools_is_refused(plan, inventory):
    identity = plan["pool_identity"]
    assert identity == inventory["pool_identity"] and set(identity) == ap.POOL_IDENTITY_FIELDS
    assert identity["proc_manifest_sha256"] == hashlib.sha256((TEXTURES / "proc-manifest.json").read_bytes()).hexdigest()
    assert identity["cc0_pack_sha256"] == json.loads((TEXTURES / "cc0-manifest.json").read_text())["pack_sha256"]
    assert identity["split_seed"] == indoor_assets.MASTER_SEED
    for key in ("proc_manifest_sha256", "cc0_pack_sha256", "split_assignment_sha256", "cup_rule_sha256"):
        other = ap.make_plan(seed=710025, nominal_share=0.25, nominal_scene_sha256=inventory["scene_sha256"],
                             pool_identity={**identity, key: "1" * 64})
        assert other["plan_sha256"] != plan["plan_sha256"], key         # every part of the identity is in the hash
        with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_POOL_IDENTITY_MISMATCH"):
            ap.derive(other, "p3-000", inventory)
    other = ap.make_plan(seed=710025, nominal_share=0.25, nominal_scene_sha256=inventory["scene_sha256"], pool_identity={**identity, "split_seed": 7})
    assert other["plan_sha256"] != plan["plan_sha256"]
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_POOL_IDENTITY_MISMATCH"):
        ap.derive(other, "p3-000", inventory)
    for bad in ({k: v for k, v in identity.items() if k != "cup_rule_sha256"}, {**identity, "extra": 1}, {**identity, "split_seed": -1},
                {**identity, "split_assignment_sha256": "xyz"}, None):
        with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PLAN_POOL_IDENTITY_INVALID"):
            ap.make_plan(seed=1, nominal_share=0.25, nominal_scene_sha256=inventory["scene_sha256"], pool_identity=bad)
    stripped = {key: value for key, value in plan.items() if key != "pool_identity"}
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PLAN_SHAPE_INVALID"):
        ap.validate_plan(stripped)                                      # a plan of before the pools (no identity) is refused
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PLAN_SHAPE_INVALID"):
        ap.validate_plan({**stripped, "schema_version": 1})


def _pool_install(tmp_path, source, *, cc0=True):
    """`<share>/assets/mujoco/act` with the manifests of the repository and the PNGs of `source` (a pool tree's act directory)."""
    root = tmp_path / "assets/mujoco"
    shutil.copytree(NOMINAL_DIR, root / "act")
    textures = root / "textures/indoor"
    shutil.copytree(source.parent / "textures/indoor", textures, symlinks=False)
    if not cc0:
        shutil.rmtree(textures / "cc0")
        (textures / "cc0-manifest.json").unlink()
    return root / "act"


def test_the_installed_pool_files_are_verified_and_a_missing_or_changed_cc0_pack_is_refused(tmp_path, indoor_pool_act):
    act = _pool_install(tmp_path, indoor_pool_act)
    inventory = ap.scene_inventory(act, verify_files=True)
    plan = ap.make_plan(seed=5, nominal_share=0.25, nominal_scene_sha256=inventory["scene_sha256"], pool_identity=inventory["pool_identity"])
    ap.derive(plan, "p3-000", inventory)
    cc0 = act.parent / "textures/indoor/cc0"
    victim = sorted(cc0.glob("*.png"))[3]
    original = victim.read_bytes()
    victim.write_bytes(original + b"\0")
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_CC0_PACK_MISMATCH"):
        ap.scene_inventory(act, verify_files=True)
    ap.scene_inventory(act)                                             # an offline draw does not read the files
    victim.unlink()
    with pytest.raises(ap.AppearanceInvalid, match=f"APPEARANCE_CC0_PACK_MISSING: cc0/{victim.stem}"):
        ap.scene_inventory(act, verify_files=True)
    victim.write_bytes(original)
    ap.scene_inventory(act, verify_files=True)
    shutil.rmtree(cc0)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_CC0_PACK_MISSING"):
        ap.scene_inventory(act, verify_files=True)


def test_a_procedural_texture_that_is_missing_or_not_reproduced_is_refused(tmp_path, indoor_pool_act):
    act = _pool_install(tmp_path, indoor_pool_act)
    victim = act.parent / "textures/indoor/proc/wood_050.png"
    original = victim.read_bytes()
    victim.write_bytes(original[:-9])                                   # only the PNG trailer differs: the decoded pixels are the manifest's, accepted
    ap.scene_inventory(act, verify_files=True)
    middle = len(original) // 2
    victim.write_bytes(original[:middle] + bytes([original[middle] ^ 0xFF]) + original[middle + 1:])
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PROC_TEXTURE_MISMATCH"):
        ap.scene_inventory(act, verify_files=True)
    victim.unlink()
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_PROC_TEXTURE_MISSING: proc/wood_050"):
        ap.scene_inventory(act, verify_files=True)


def test_a_plan_that_references_cc0_textures_is_refused_on_an_install_without_the_pack(tmp_path, plan, indoor_pool_act):
    without = _pool_install(tmp_path, indoor_pool_act, cc0=False)
    inventory = ap.scene_inventory(without, verify_files=True)            # a tree without a CC0 manifest is a consistent tree of its own ...
    assert inventory["pool_identity"]["cc0_pack_sha256"] is None and not any(
        name.startswith("cc0/") for ids_ in inventory["pools"]["train"].values() for name in ids_)
    with pytest.raises(ap.AppearanceInvalid, match="APPEARANCE_POOL_IDENTITY_MISMATCH.*cc0_pack_sha256"):
        ap.derive(plan, "p3-000", inventory)                              # ... and the plan made with the pack is not drawn on it
    alone = ap.make_plan(seed=5, nominal_share=0.0, nominal_scene_sha256=inventory["scene_sha256"], pool_identity=inventory["pool_identity"])
    assert all(not name.startswith("cc0/") for scene in ids(40)
               for name in (ap.derive(alone, scene, inventory)["variant"]["set"][f"{s}.texture"] for s in indoor_assets.SURFACES))


def test_the_inventory_names_the_lights_and_props_the_whitelist_can_edit(inventory):
    assert {"key_light", "ind_main", "ind_fill0", "ind_dirfill0"} <= set(inventory["lights"])
    assert "ind_poster" in inventory["props"] and not any(name.startswith(scene_variant._STRUCTURE_PREFIXES) for name in inventory["props"])
    assert len(inventory["headlight"]["ambient"]) == 3
