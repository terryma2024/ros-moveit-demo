"""The indoor appearance pools (`act/indoor_assets.py`): parametric textures, three-way splits by identity, continuous cup colour."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")

from paths import PACKAGE_ROOT  # noqa: E402
from so101_demo.act import indoor_assets as ia  # noqa: E402

TEXTURES = PACKAGE_ROOT / "assets/mujoco/textures/indoor"
SCENE = PACKAGE_ROOT / "assets/mujoco/act/scene_side_wrist_indoor.xml"


# ---- names -------------------------------------------------------------------------------------------------------------------------


def test_the_procedural_pool_has_eight_families_of_at_least_one_hundred():
    ids = ia.all_proc_ids()
    assert len(ia.PROC_FAMILIES) == 8 and ia.PER_FAMILY >= 100 and len(ids) == len(set(ids)) == 8 * ia.PER_FAMILY
    assert {re.fullmatch(r"proc/([a-z]+)_\d{3}", item).group(1) for item in ids} == set(ia.PROC_FAMILIES)


def test_a_texture_name_decides_the_surfaces_it_may_cover():
    assert ia.texture_allowed("wall", "proc/plaster_000") and not ia.texture_allowed("floor", "proc/plaster_000")
    assert ia.texture_allowed("floor", "proc/wood_103") and ia.texture_allowed("table", "proc/wood_103")
    assert not ia.texture_allowed("wall", "proc/wood_103")
    assert ia.texture_allowed("wall", "cc0/wall_polyhaven_beige_plaster") and not ia.texture_allowed("floor", "cc0/wall_polyhaven_x")
    assert ia.texture_allowed("table", "cc0/table_ambientcg_wood051")
    for surface, names in ia.LEGACY.items():
        assert all(ia.texture_allowed(surface, name) for name in names)
    assert not ia.texture_allowed("wall", "floor_parquet") and ia.texture_allowed("table", "floor_parquet")


@pytest.mark.parametrize("name", ["proc/wood_104", "proc/wood_1", "proc/marble_000", "proc/../wall_white", "cc0/ceiling_x", "cc0/wall_",
                                  "cc0/wall_UPPER", "../wall_white", "wall_white.png", "", "proc/wood_000/x", "/etc/passwd"])
def test_a_name_outside_the_pools_covers_nothing(name):
    assert ia.texture_surfaces(name) == ()
    with pytest.raises(ValueError, match="INDOOR_TEXTURE_UNKNOWN"):
        ia.texture_file(name)


# ---- parameters and pixels ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("family", ia.PROC_FAMILIES)
def test_the_parameters_are_a_pure_function_of_family_and_index(family):
    assert ia.proc_params(family, 3) == ia.proc_params(family, 3)
    assert ia.proc_params(family, 3) != ia.proc_params(family, 4)
    params = ia.proc_params(family, 0)
    assert params["family"] == family and all(0.0 <= value <= 255.0 for value in params["base"]) and params["orientation"] in (0, 1, 2, 3)
    json.dumps(params)                                      # the manifest stores it as is


@pytest.mark.parametrize("family", ia.PROC_FAMILIES)
def test_a_texture_renders_deterministically_to_a_full_size_rgb_image(family):
    entry, pixels = ia.texture_entry(family, 5)
    again, pixels_again = ia.texture_entry(family, 5)
    assert pixels.shape == (ia.SIZE, ia.SIZE, 3) and pixels.dtype == np.uint8
    assert entry == again and np.array_equal(pixels, pixels_again)
    assert pixels.std() > 1.0                                # not a flat fill
    other, _ = ia.texture_entry(family, 6)
    assert other["pixel_sha256"] != entry["pixel_sha256"]


def test_every_family_actually_varies_with_its_parameters():
    for family in ia.PROC_FAMILIES:
        hashes = {ia.texture_entry(family, index)[0]["pixel_sha256"] for index in range(6)}
        means = {tuple(ia.texture_entry(family, index)[0]["mean_rgb"]) for index in range(6)}
        assert len(hashes) == 6 and len(means) >= 4, family


def test_the_png_bytes_are_deterministic_and_decode_to_the_pixels(tmp_path):
    from PIL import Image

    _entry, pixels = ia.texture_entry("tile", 2)
    data = ia.png_bytes(pixels)
    assert data == ia.png_bytes(pixels) and data[:8] == b"\x89PNG\r\n\x1a\n"
    path = tmp_path / "x.png"
    path.write_bytes(data)
    with Image.open(path) as image:
        assert np.array_equal(np.asarray(image.convert("RGB")), pixels)
        assert set(image.info) <= {"gamma", "dpi"} or not image.info                      # no metadata that depends on the run


# ---- manifest, materialize, verify -------------------------------------------------------------------------------------------------


def test_materialize_writes_what_the_manifest_says_and_verify_confirms_it(tmp_path):
    ids = ["proc/wood_001", "proc/plaster_002", "proc/wallpaper_003"]
    manifest = ia.build_proc_manifest(ids)
    assert [entry["id"] for entry in manifest["textures"]] == ["proc/wood_001", "proc/plaster_002", "proc/wallpaper_003"]
    assert ia.materialize(manifest, tmp_path) == ids
    assert ia.verify_directory(manifest, tmp_path) == {"missing": [], "png_differs": [], "pixels_differ": [], "checked": 3}
    # a second materialization is byte-identical
    first = {path.name: path.read_bytes() for path in (tmp_path / "proc").iterdir()}
    again = tmp_path / "again"
    ia.materialize(manifest, again)
    assert first == {path.name: path.read_bytes() for path in (again / "proc").iterdir()}


def test_materialize_refuses_a_manifest_whose_pixels_cannot_be_reproduced(tmp_path):
    manifest = ia.build_proc_manifest(["proc/tile_000"])
    manifest["textures"][0]["pixel_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="INDOOR_TEXTURE_NOT_REPRODUCED: proc/tile_000"):
        ia.materialize(manifest, tmp_path)


def test_verify_reports_a_missing_a_changed_and_a_different_png(tmp_path):
    from PIL import Image

    manifest = ia.build_proc_manifest(["proc/wood_001", "proc/tile_001", "proc/fabric_001"])
    ia.materialize(manifest, tmp_path)
    (tmp_path / "proc/wood_001.png").unlink()
    Image.fromarray(np.zeros((ia.SIZE, ia.SIZE, 3), np.uint8)).save(tmp_path / "proc/tile_001.png")            # other pixels
    ok = ia.png_bytes(ia.texture_entry("fabric", 1)[1])
    (tmp_path / "proc/fabric_001.png").write_bytes(ok)
    result = ia.verify_directory(manifest, tmp_path)
    assert result["missing"] == ["proc/wood_001"] and result["pixels_differ"] == ["proc/tile_001"] and "proc/fabric_001" not in result["png_differs"]


def test_the_committed_manifest_lists_the_whole_pool_with_the_parameters_the_code_derives():
    manifest = ia.load_manifest(TEXTURES / ia.PROC_MANIFEST)
    assert manifest["kind"] == "SO101_INDOOR_PROC_TEXTURE_MANIFEST" and manifest["master_seed"] == ia.MASTER_SEED
    assert [entry["id"] for entry in manifest["textures"]] == ia.all_proc_ids()
    for entry in manifest["textures"]:
        assert entry["params"] == ia.proc_params(entry["family"], entry["index"]) and entry["seed"] == entry["params"]["seed"]
        assert re.fullmatch(r"[0-9a-f]{64}", entry["pixel_sha256"]) and re.fullmatch(r"[0-9a-f]{64}", entry["png_sha256"])
    assert len({entry["pixel_sha256"] for entry in manifest["textures"]}) == len(manifest["textures"])       # no duplicate texture


@pytest.mark.parametrize("index", [0, 37, 103])
@pytest.mark.parametrize("family", ia.PROC_FAMILIES)
def test_spot_textures_reproduce_the_committed_manifest(family, index):
    manifest = ia.load_manifest(TEXTURES / ia.PROC_MANIFEST)
    entry = next(item for item in manifest["textures"] if item["id"] == ia.proc_id(family, index))
    fresh, _pixels = ia.texture_entry(family, index)
    assert fresh["pixel_sha256"] == entry["pixel_sha256"] and fresh["mean_rgb"] == entry["mean_rgb"]


def test_no_generated_png_is_committed():
    ignored = (Path(__file__).resolve().parents[4] / ".gitignore").read_text()
    assert "textures/indoor/proc/" in ignored


# ---- splits by identity ------------------------------------------------------------------------------------------------------------


def _all_ids(pools):
    return [texture for split in pools.values() for ids in split.values() for texture in ids]


def test_every_texture_is_in_exactly_one_split_and_the_splits_are_disjoint():
    pools = ia.texture_pools()
    per_split = {split: {texture for ids in pools[split].values() for texture in ids} for split in ia.SPLITS}
    assert not per_split["train"] & per_split["val"] and not per_split["train"] & per_split["test"] and not per_split["val"] & per_split["test"]
    assert set().union(*per_split.values()) == set(ia.all_proc_ids()) | set(ia.LEGACY_SPLIT)
    for split, surfaces in pools.items():
        for surface, ids in surfaces.items():
            assert ids == sorted(ids) and all(ia.texture_allowed(surface, texture) for texture in ids), (split, surface)


def test_a_texture_covering_two_surfaces_keeps_one_split():
    pools = ia.texture_pools()
    for texture in ("proc/concrete_010", "proc/tile_020", "floor_parquet", "floor_wood_light"):
        owners = {split for split in ia.SPLITS for ids in pools[split].values() if texture in ids}
        assert len(owners) == 1


def test_each_family_has_a_train_val_and_test_share_in_the_stated_proportion():
    assignment = ia.split_assignment(ia.split_groups())
    for family in ia.PROC_FAMILIES:
        counts = {split: sum(1 for texture, owner in assignment.items() if texture.startswith(f"proc/{family}_") and owner == split)
                  for split in ia.SPLITS}
        assert sum(counts.values()) == ia.PER_FAMILY
        assert counts["val"] == counts["test"] == round(ia.PER_FAMILY * 0.15) and counts["train"] > 4 * counts["val"], (family, counts)


def test_the_split_is_deterministic_and_depends_on_the_seed():
    assert ia.split_assignment(ia.split_groups()) == ia.split_assignment(ia.split_groups())
    assert ia.split_assignment(ia.split_groups()) != ia.split_assignment(ia.split_groups(), seed=ia.MASTER_SEED + 1)


def test_a_small_group_still_gets_a_val_and_a_test_texture_when_it_has_three():
    cc0 = {"textures": [{"id": f"cc0/wall_t{index}", "surface": "wall"} for index in range(3)]}
    assignment = ia.split_assignment({"cc0/wall": [entry["id"] for entry in cc0["textures"]]})
    assert sorted(assignment.values()) == ["test", "train", "val"]


def test_cc0_textures_join_the_pools_by_their_surface_prefix():
    cc0 = {"textures": [{"id": f"cc0/floor_t{index:02d}", "surface": "floor"} for index in range(20)]
           + [{"id": f"cc0/table_t{index:02d}", "surface": "table"} for index in range(20)]}
    pools = ia.texture_pools(cc0_manifest=cc0)
    for split in ia.SPLITS:
        assert any(texture.startswith("cc0/floor_") for texture in pools[split]["floor"])
        assert any(texture.startswith("cc0/table_") for texture in pools[split]["table"])
        assert not any(texture.startswith("cc0/floor_") for texture in pools[split]["wall"] + pools[split]["table"])
    assert ia.split_of("cc0/floor_t03", cc0_manifest=cc0) in ia.SPLITS


def test_the_legacy_textures_keep_the_held_out_ones_out_of_train():
    pools = ia.texture_pools()
    assert "wall_beige" in pools["val"]["wall"] and "wall_beige" not in pools["train"]["wall"]
    assert "floor_parquet" in pools["val"]["floor"] and "floor_parquet" not in pools["train"]["floor"]
    assert {"wall_white", "wall_grey"} <= set(pools["train"]["wall"])


# ---- continuous cup colour ---------------------------------------------------------------------------------------------------------


def test_the_hue_bands_are_partitioned_among_the_splits_by_identity():
    owners = {split: ia.hue_bands(split) for split in ia.SPLITS}
    assert sorted(band for bands in owners.values() for band in bands) == list(range(ia.HUE_BAND_COUNT))
    assert all(owners[split] for split in ia.SPLITS) and len(owners["train"]) > len(owners["val"]) >= 4
    assert ia.hue_bands("val") == ia.hue_bands("val") and ia.hue_bands("val", seed=1) != ia.hue_bands("val", seed=2)
    assert ia.hue_band_split(owners["test"][0]) == "test"


def _surfaces(rng):
    return {name: tuple(rng.uniform(0.15, 0.95) for _ in range(3)) for name in ("wall", "floor", "table")}


@pytest.mark.parametrize("split", ia.SPLITS)
def test_a_cup_colour_has_its_hue_in_a_band_of_its_split(split):
    rng = random.Random(7)
    bands = set(ia.hue_bands(split))
    for _ in range(150):
        draw = ia.draw_cup_rgba(rng, split, _surfaces(rng))
        assert draw["band"] in bands and int(draw["hue"] * ia.HUE_BAND_COUNT / 360.0) in bands
        assert len(draw["rgba"]) == 4 and draw["rgba"][3] == 1.0 and all(0.0 <= value <= 1.0 for value in draw["rgba"])


def test_the_colour_is_continuous_not_one_of_a_few_families():
    rng = random.Random(11)
    colours = {tuple(ia.draw_cup_rgba(rng, "train", _surfaces(rng))["rgba"]) for _ in range(300)}
    assert len(colours) > 290
    hues = sorted({round(ia.draw_cup_rgba(rng, "train", _surfaces(rng))["hue"] // 5) for _ in range(400)})
    assert len(hues) > 20


def test_a_satisfied_draw_is_clearly_different_from_every_drawn_surface_and_from_the_landing_ring():
    rng = random.Random(3)
    satisfied = 0
    for _ in range(300):
        surfaces = _surfaces(rng)
        draw = ia.draw_cup_rgba(rng, rng.choice(ia.SPLITS), surfaces)
        if draw["satisfied"]:
            satisfied += 1
            contrast = ia.cup_contrast(draw["rgba"][:3], surfaces)
            assert all(contrast[name] >= ia.MIN_DELTA_E[name] for name in contrast) and contrast["ring"] >= ia.MIN_DELTA_E["ring"]
    assert satisfied >= 285


def test_a_cup_the_colour_of_the_table_or_of_the_ring_is_not_distinct():
    surfaces = {"wall": (0.9, 0.9, 0.9), "floor": (0.3, 0.2, 0.1), "table": (0.8, 0.7, 0.4)}
    assert not ia.cup_distinct((0.8, 0.7, 0.4), surfaces)
    assert not ia.cup_distinct((0.82, 0.68, 0.38), surfaces)                       # a near match of the table
    assert not ia.cup_distinct(ia.LANDING_RING_RGB, surfaces) and not ia.cup_distinct((0.85, 0.12, 0.1), surfaces)
    assert not ia.cup_distinct((0.9, 0.9, 0.88), surfaces)                         # the wall
    assert ia.cup_distinct((0.1, 0.3, 0.85), surfaces)


def test_the_draw_avoids_a_surface_that_matches_the_only_hue_a_split_offers():
    rng = random.Random(5)
    surfaces = {"wall": (0.8, 0.8, 0.8), "floor": (0.5, 0.5, 0.5), "table": (0.1, 0.3, 0.8)}
    for _ in range(40):
        draw = ia.draw_cup_rgba(rng, "train", surfaces)
        if draw["satisfied"]:
            assert ia.delta_e(draw["rgba"][:3], surfaces["table"]) >= ia.MIN_DELTA_E["table"]


def test_the_draw_is_deterministic_for_a_seed():
    surfaces = {"wall": (0.9, 0.9, 0.9), "floor": (0.5, 0.4, 0.3), "table": (0.8, 0.7, 0.6)}
    assert ia.draw_cup_rgba(random.Random(1), "val", surfaces) == ia.draw_cup_rgba(random.Random(1), "val", surfaces)


def test_the_colour_distance_is_a_metric_and_the_conversions_round_trip():
    a, b = (0.2, 0.4, 0.6), (0.7, 0.2, 0.1)
    assert ia.delta_e(a, a) == pytest.approx(0.0, abs=1e-9) and ia.delta_e(a, b) == pytest.approx(ia.delta_e(b, a))
    for colour in (a, b, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)):
        assert ia.oklab_to_srgb(ia.srgb_to_oklab(colour)) == pytest.approx(colour, abs=1e-6)
    assert ia.delta_e((0, 0, 0), (1, 1, 1)) == pytest.approx(1.0, abs=1e-3)


def test_the_ring_colour_is_the_colour_of_the_ring_in_the_indoor_scene():
    from xml.etree import ElementTree

    root = ElementTree.fromstring(SCENE.read_text())
    ring = next(item for item in root.iter("geom") if (item.get("name") or "") == "target_landing_tolerance_ring")
    material = next((item for item in root.iter("material") if item.get("name") == ring.get("material")), None)
    rgba = [float(value) for value in (ring.get("rgba") or material.get("rgba")).split()]
    assert ia.delta_e(rgba[:3], ia.LANDING_RING_RGB) < 0.12


def test_surface_colour_is_the_texture_mean_times_the_tint():
    assert ia.surface_colour((0.5, 0.5, 0.5, 1.0), (0.8, 0.4, 1.0)) == pytest.approx((0.4, 0.2, 0.5))


# ---- the CC0 pool --------------------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cc0():
    return ia.load_manifest(TEXTURES / ia.CC0_MANIFEST)


def test_the_cc0_manifest_describes_a_pack_of_cc0_albedo_maps_with_source_and_hashes(cc0):
    entries = cc0["textures"]
    assert 150 <= len(entries) <= 200 and cc0["licence"] == "CC0-1.0" and cc0["size"] == ia.SIZE
    assert {surface: sum(1 for entry in entries if entry["surface"] == surface) for surface in ia.SURFACES} == {"wall": 55, "floor": 60, "table": 65}
    assert len({entry["id"] for entry in entries}) == len(entries)
    for entry in entries:
        assert entry["licence"] == "CC0-1.0" and entry["source"] == "polyhaven" and entry["source_url"] == f"https://polyhaven.com/a/{entry['asset_id']}"
        assert entry["download_url"].startswith("https://dl.polyhaven.org/") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["download_date"])
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256_original"]) and re.fullmatch(r"[0-9a-f]{64}", entry["sha256_resized"])
        assert ia.texture_surfaces(entry["id"]) == (entry["surface"],) and entry["id"].startswith(f"cc0/{entry['surface']}_")
        assert len(entry["original_size"]) == 2 and len(entry["mean_rgb"]) == 3 and entry["map"].startswith("diffuse")
    assert cc0["pack_sha256"] == ia.cc0_pack_sha256(cc0)


def test_every_cc0_texture_has_a_line_in_the_licence_file(cc0):
    text = (TEXTURES / "CC0-LICENSES.md").read_text()
    assert "CC0 1.0" in text and "polyhaven.com/license" in text
    assert all(entry["id"] in text and entry["source_url"] in text for entry in cc0["textures"])


def test_cc0_textures_are_in_every_split_of_every_surface_and_split_by_identity(cc0):
    pools = ia.texture_pools(cc0_manifest=cc0)
    for surface in ia.SURFACES:
        counts = {split: sum(1 for texture in pools[split][surface] if texture.startswith("cc0/")) for split in ia.SPLITS}
        assert all(counts.values()) and counts["train"] > counts["val"] and counts["train"] > counts["test"], (surface, counts)
    owners = {}
    for split in ia.SPLITS:
        for ids in pools[split].values():
            for texture in ids:
                assert owners.setdefault(texture, split) == split


def test_the_real_cc0_pack_matches_the_manifest_when_it_is_available(cc0):
    import hashlib
    import os

    pack = os.environ.get("INDOOR_CC0_PACK")
    if not pack or not Path(pack).is_dir():
        pytest.skip("no CC0 pack (INDOOR_CC0_PACK)")
    for entry in cc0["textures"]:
        assert hashlib.sha256((Path(pack) / (entry["id"].split("/", 1)[1] + ".png")).read_bytes()).hexdigest() == entry["sha256_resized"], entry["id"]


def _script():
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[4] / "scripts/assets/gen_indoor_textures.py"
    spec = importlib.util.spec_from_file_location("gen_indoor_textures_for_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_cc0_pack_is_copied_only_when_every_file_matches_its_manifest(tmp_path):
    import hashlib

    script = _script()
    pixels = np.full((ia.SIZE, ia.SIZE, 3), 120, np.uint8)
    data = ia.png_bytes(pixels)
    manifest = {"textures": [{"id": "cc0/wall_polyhaven_a", "sha256_resized": hashlib.sha256(data).hexdigest()},
                             {"id": "cc0/floor_polyhaven_b", "sha256_resized": hashlib.sha256(data).hexdigest()}]}
    out = tmp_path / "out"
    out.mkdir()
    ia.write_manifest(out / ia.CC0_MANIFEST, manifest)
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "wall_polyhaven_a.png").write_bytes(data)
    assert script.cc0_pack(pack, out) == 1                                  # one file is missing
    (pack / "floor_polyhaven_b.png").write_bytes(data + b"x")
    assert script.cc0_pack(pack, out) == 1                                  # one file differs
    (pack / "floor_polyhaven_b.png").write_bytes(data)
    assert script.cc0_pack(pack, out) == 0 and sorted(path.name for path in (out / "cc0").iterdir()) == ["floor_polyhaven_b.png", "wall_polyhaven_a.png"]


def test_the_texture_means_come_from_the_manifests_and_the_legacy_pngs(tmp_path):
    proc = ia.build_proc_manifest(["proc/wood_000"])
    cc0 = {"textures": [{"id": "cc0/wall_polyhaven_a", "mean_rgb": [0.1, 0.2, 0.3]}]}
    means = ia.texture_means(TEXTURES, proc, cc0)
    assert means["proc/wood_000"] == proc["textures"][0]["mean_rgb"] and means["cc0/wall_polyhaven_a"] == [0.1, 0.2, 0.3]
    assert set(ia.LEGACY_SPLIT) <= set(means) and all(0.0 <= value <= 1.0 for name in ia.LEGACY_SPLIT for value in means[name])
