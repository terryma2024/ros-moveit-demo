"""Scene variants over the indoor nominal (indoor scene design 2026-10-24, P1): the `indoor` whitelist and the v2 physics invariance.

A variant with `"base": "indoor"` may set the wall, floor and table material (a library texture and a tint), the diffuse, direction
and active flag of each light, the headlight, the visibility of a prop and the cup colour. Every physics field stays refused, and a
realized variant must keep the v2 physics fingerprint of the nominal scene (enforced when the variant is realized into a run).
"""

import copy
import json
import re
import shutil
from pathlib import Path
from xml.etree import ElementTree

import mujoco
import numpy as np
import pytest

from paths import PACKAGE_ROOT
from so101_demo.act import scene_variant as sv
from so101_demo.act import scene_variant_run as run
from so101_demo.act.physics_fingerprint import physics_fingerprint_v2_of_file, physics_fingerprint_v2_of_string

SHARE = PACKAGE_ROOT
NOMINAL_DIR = PACKAGE_ROOT / "assets/mujoco/act"
INDOOR_SCENE = NOMINAL_DIR / "scene_side_wrist_indoor.xml"
TEXTURES = PACKAGE_ROOT / "assets/mujoco/textures/indoor"


def _variant(name="indoor_v", **fields):
    return {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": name, "base": "indoor", "set": fields}


#: one variant for every whitelisted indoor field
WHITELISTED = {
    "wall_texture": _variant(**{"wall.texture": "wall_beige"}),
    "wall_tint": _variant(**{"wall.rgba": [0.9, 0.95, 1.0, 1.0]}),
    "floor_texture": _variant(**{"floor.texture": "floor_carpet", "floor.rgba": [1.0, 0.95, 0.9, 1.0]}),
    "table_texture": _variant(**{"table.texture": "cabinet_wood"}),
    "table_tint": _variant(**{"table.rgba": [0.8, 0.8, 0.9, 1.0]}),
    "main_light": _variant(**{"light.ind_main.diffuse": [0.3, 0.3, 0.28], "light.ind_main.dir": [0.1, 0.0, -1.0]}),
    "fill_light_off": _variant(**{"light.ind_fill0.active": 0}),
    "key_light": _variant(**{"light.key_light.diffuse": [0.05, 0.05, 0.05]}),
    "dir_light": _variant(**{"light.ind_dirfill1.diffuse": [0.05, 0.05, 0.05], "light.ind_dirfill1.dir": [0.5, 0.2, -0.5]}),
    "headlight": _variant(**{"headlight.ambient": [0.2, 0.2, 0.2], "headlight.diffuse": [0.1, 0.1, 0.1], "headlight.active": 1}),
    "prop_hidden": _variant(**{"prop.ind_poster.visible": 0, "prop.ind_cabinet_low.visible": 0}),
    "prop_shown": _variant(**{"prop.ind_poster.visible": 1}),
    "cup_colour": _variant(**{"cup_material.rgba": [0.1, 0.4, 0.9, 1.0]}),
    "everything": _variant(**{"wall.texture": "wall_grey", "floor.texture": "floor_tile_grey", "table.texture": "floor_parquet",
                              "light.ind_main.diffuse": [0.4, 0.3, 0.3], "headlight.ambient": [0.25, 0.25, 0.25],
                              "prop.ind_board.visible": 0, "cup_material.rgba": [0.2, 0.7, 0.3, 1.0]}),
}


@pytest.fixture(scope="module")
def nominal_v2():
    return physics_fingerprint_v2_of_file(INDOOR_SCENE)


def _write(tmp_path, realized, name="scene_variant.xml"):
    directory = tmp_path / "owned"
    directory.mkdir(exist_ok=True)
    path = directory / name
    path.write_text(realized.xml_text)
    return path


# ---- the whitelist -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["geom.friction", "cup.mass", "option.timestep", "table_collision.size", "joint.damping",
                                 "actuator.kp", "wrist_camera.fovy", "task_camera.pos", "side_camera.fovy", "side_camera.pos_delta_m",
                                 "light.ind_main.cutoff", "light.ind_main.pos", "light.ind_main.castshadow", "headlight.specular",
                                 "wall.size", "wall.pos", "floor.friction", "prop.ind_poster.pos", "prop.ind_poster.size",
                                 "prop.ind_poster.contype", "table.collision", "key_light.diffuse", "table_material.rgba"])
def test_a_physics_or_unlisted_field_is_refused_over_the_indoor_base(key):
    with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_FIELD_REFUSED"):
        sv.normalize_variant(_variant(**{key: [1.0]}))


@pytest.mark.parametrize("fields", [
    {"wall.texture": "no_such_texture"}, {"wall.texture": "floor_carpet"}, {"floor.texture": "wall_white"}, {"table.texture": "poster"},
    {"wall.texture": "../wall_white"}, {"wall.texture": ["wall_white"]}, {"wall.rgba": [1.0, 1.0, 1.0]}, {"wall.rgba": [2.0, 1.0, 1.0, 1.0]},
    {"table.rgba": [float("nan")] * 4}, {"light.ind_main.diffuse": [9.0, 0.0, 0.0]}, {"light.ind_main.diffuse": [1.0, 1.0]},
    {"light.ind_main.dir": [0.0, 0.0, 0.0]}, {"light.ind_main.active": 2}, {"light.ind_main.active": True},
    {"headlight.active": 2}, {"headlight.ambient": [1.5, 0, 0]}, {"prop.ind_poster.visible": 2}, {"prop.ind_poster.visible": False},
    {"prop.visible": 1}, {"light.diffuse": [0.1, 0.1, 0.1]}, {"light.Ind Main.diffuse": [0.1, 0.1, 0.1]}, {"cup_material.rgba": [1.0, 1.0, 1.0]},
])
def test_a_value_outside_its_range_is_refused_over_the_indoor_base(fields):
    with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_(VALUE_INVALID|FIELD_REFUSED)"):
        sv.normalize_variant(_variant(**fields))


@pytest.mark.parametrize("document", [
    {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": "v", "base": "head-wrist", "set": {"headlight.active": 0}},
    {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": "v", "base": 3, "set": {"headlight.active": 0}},
    {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": "v", "base": "indoor", "extra": 1, "set": {"headlight.active": 0}},
])
def test_an_unknown_base_or_an_extra_key_is_refused(document):
    with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_(SHAPE_INVALID|BASE_INVALID)"):
        sv.normalize_variant(document)


def test_a_variant_without_a_base_is_the_side_wrist_variant_it_always_was():
    plain = {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": "v", "set": {"key_light.diffuse": [0.3, 0.3, 0.3]}}
    normalized = sv.normalize_variant(plain)
    assert normalized == {"name": "v", "set": {"key_light.diffuse": [0.3, 0.3, 0.3]}} and "base" not in normalized
    with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_FIELD_REFUSED"):
        sv.normalize_variant({**plain, "set": {"wall.texture": "wall_white"}})
    indoor = sv.normalize_variant(_variant(**{"headlight.active": 0}))
    assert indoor["base"] == "indoor" and sv.variant_sha256(indoor) != sv.variant_sha256(sv.normalize_variant(
        {**plain, "set": {"headlight.active": 0}}))


def test_the_texture_library_is_the_manifest_of_the_installed_textures():
    listed = {entry["file"][:-4] for entry in json.loads((TEXTURES / "manifest.json").read_text())["textures"]}
    for category in (sv.WALL_TEXTURES, sv.FLOOR_TEXTURES, sv.TABLE_TEXTURES):
        assert category and set(category) <= listed
    assert not set(sv.WALL_TEXTURES) & set(sv.FLOOR_TEXTURES)


# ---- realizing a variant -----------------------------------------------------------------------------------------------------------


def _root(realized):
    return ElementTree.fromstring(realized.xml_tokenized)


def test_realize_applies_each_field_to_the_element_it_names():
    def applied(name):
        return sv.realize(NOMINAL_DIR, WHITELISTED[name])

    root = _root(applied("wall_texture"))
    texture = next(item for item in root.iter("texture") if item.get("name") == "t_wall")
    assert texture.get("file") == "@NOMINAL_DIR@/../textures/indoor/wall_beige.png"
    root = _root(applied("wall_tint"))
    assert next(item for item in root.iter("material") if item.get("name") == "m_wall").get("rgba") == "0.9 0.95 1 1"
    root = _root(applied("floor_texture"))
    assert next(item for item in root.iter("texture") if item.get("name") == "t_floor").get("file").endswith("floor_carpet.png")
    assert next(item for item in root.iter("material") if item.get("name") == "m_floor").get("rgba") == "1 0.95 0.9 1"
    root = _root(applied("table_texture"))
    assert next(item for item in root.iter("texture") if item.get("name") == "t_table").get("file").endswith("cabinet_wood.png")
    light = next(item for item in _root(applied("main_light")).iter("light") if item.get("name") == "ind_main")
    assert light.get("diffuse") == "0.3 0.3 0.28" and light.get("dir") == "0.1 0 -1"
    light = next(item for item in _root(applied("fill_light_off")).iter("light") if item.get("name") == "ind_fill0")
    assert light.get("active") == "false"
    headlight = next(_root(applied("headlight")).iter("headlight"))
    assert headlight.get("ambient") == "0.2 0.2 0.2" and headlight.get("diffuse") == "0.1 0.1 0.1" and headlight.get("active") == "1"
    for name in ("ind_poster", "ind_cabinet_low"):
        geom = next(item for item in _root(applied("prop_hidden")).iter("geom") if item.get("name") == name)
        assert geom.get("rgba") == "0 0 0 0" and geom.get("group") == "4"
    geom = next(item for item in _root(applied("prop_shown")).iter("geom") if item.get("name") == "ind_poster")
    assert geom.get("rgba") is None and geom.get("group") == "0"
    material = next(item for item in _root(applied("cup_colour")).iter("material") if item.get("name") == "cup_orange")
    assert material.get("rgba") == "0.1 0.4 0.9 1"


def test_the_realized_record_names_the_nominal_and_the_applied_value_of_every_field():
    realized = sv.realize(NOMINAL_DIR, WHITELISTED["everything"])
    assert set(realized.applied) == set(WHITELISTED["everything"]["set"])
    assert realized.applied["wall.texture"] == {"nominal": "wall_white", "value": "wall_grey"}
    assert realized.applied["prop.ind_board.visible"] == {"nominal": 1, "value": 0}
    assert realized.applied["light.ind_main.diffuse"]["nominal"] == pytest.approx([0.149, 0.149, 0.14])
    assert realized.applied["headlight.ambient"]["nominal"] == pytest.approx([0.132] * 3)


def test_a_light_or_prop_the_nominal_scene_does_not_have_is_refused():
    for fields in ({"light.ind_main2.diffuse": [0.1] * 3}, {"prop.ind_nothing.visible": 0}, {"prop.ind_wall_xneg.visible": 0},
                   {"prop.ind_floor.visible": 0}, {"prop.ind_ceiling.visible": 0}, {"prop.ind_desk_top.visible": 0},
                   {"prop.table_visual.visible": 0}, {"prop.wall_near_visual.visible": 0}, {"light.task_light.active": 0}):
        with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_(FIELD_REFUSED|NOMINAL_DRIFT)"):
            sv.realize(NOMINAL_DIR, _variant(**fields))


@pytest.mark.parametrize("name", sorted(WHITELISTED))
def test_every_whitelisted_indoor_variant_keeps_the_v2_physics_fingerprint(name, tmp_path, nominal_v2):
    realized = sv.realize(NOMINAL_DIR, WHITELISTED[name])
    path = _write(tmp_path, realized)
    assert physics_fingerprint_v2_of_file(path) == nominal_v2
    mujoco.MjModel.from_xml_path(str(path))      # and it compiles
    assert physics_fingerprint_v2_of_string(path.read_text()) == nominal_v2


def test_the_realized_hash_is_pure_and_does_not_depend_on_where_the_nominal_directory_is(tmp_path):
    realized = sv.realize(NOMINAL_DIR, WHITELISTED["everything"])
    again = sv.realize(NOMINAL_DIR, copy.deepcopy(WHITELISTED["everything"]))
    assert again.realized_sha256 == realized.realized_sha256 and again.xml_text == realized.xml_text
    root = tmp_path / "share/assets/mujoco"
    shutil.copytree(NOMINAL_DIR, root / "act", ignore=shutil.ignore_patterns("indoor"))
    shutil.copytree(TEXTURES, root / "textures/indoor")
    elsewhere = sv.realize(root / "act", WHITELISTED["everything"])
    assert elsewhere.realized_sha256 == realized.realized_sha256
    assert str(root / "act") in elsewhere.xml_text and str(NOMINAL_DIR) not in elsewhere.xml_text


def test_the_realized_hash_covers_the_bytes_of_the_texture_the_variant_names(tmp_path):
    root = tmp_path / "share/assets/mujoco"
    shutil.copytree(NOMINAL_DIR, root / "act", ignore=shutil.ignore_patterns("indoor"))
    shutil.copytree(TEXTURES, root / "textures/indoor")
    before = sv.realize(root / "act", WHITELISTED["wall_texture"]).realized_sha256
    (root / "textures/indoor/wall_beige.png").write_bytes((TEXTURES / "wall_grey.png").read_bytes())
    assert sv.realize(root / "act", WHITELISTED["wall_texture"]).realized_sha256 != before
    # a variant that names no texture does not care about the texture files
    quiet = sv.realize(root / "act", WHITELISTED["cup_colour"]).realized_sha256
    (root / "textures/indoor/wall_grey.png").write_bytes(b"x")
    assert sv.realize(root / "act", WHITELISTED["cup_colour"]).realized_sha256 == quiet


def test_every_texture_path_in_a_realized_scene_is_absolute_and_exists(tmp_path):
    path = _write(tmp_path, sv.realize(NOMINAL_DIR, WHITELISTED["everything"]))
    files = re.findall(r'<texture [^>]*file="([^"]+)"', path.read_text())
    assert len(files) >= 7 and all(item.startswith("/") for item in files)
    assert all(Path(item).resolve().is_file() for item in files)


def test_the_side_wrist_variants_are_untouched_by_the_indoor_base():
    plain = {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": "v", "set": {"headlight.active": 0}}
    realized = sv.realize(NOMINAL_DIR, plain)
    assert "scene_side_wrist_indoor" not in realized.xml_tokenized and "textures" not in realized.xml_tokenized
    assert "base" not in realized.variant


# ---- the run: the physics fingerprint is enforced -----------------------------------------------------------------------------------


def test_a_run_realizes_an_indoor_variant_with_the_v2_fingerprint_of_the_nominal_scene(tmp_path, nominal_v2):
    variant = run.read_variant_file(_write_json(tmp_path, WHITELISTED["everything"]))
    record = run.realize_into(tmp_path / "scene-variant", SHARE, variant)
    assert record["fingerprint_version"] == 2 and record["physics_fingerprint"] == record["nominal_physics_fingerprint"] == nominal_v2
    assert record["variant"]["base"] == "indoor"
    assert (tmp_path / "scene-variant/scene_variant.xml").is_file()
    again = run.realize_into(tmp_path / "again", SHARE, variant)
    assert again["realized_sha256"] == record["realized_sha256"]


def test_a_run_refuses_an_indoor_variant_whose_physics_differs_and_leaves_no_scene(tmp_path, monkeypatch):
    variant = run.read_variant_file(_write_json(tmp_path, WHITELISTED["wall_texture"]))
    real = run.physics_fingerprint_v2_of_file

    def altered(path):
        return "0" * 64 if str(path).endswith("scene_variant.xml") else real(path)

    monkeypatch.setattr(run, "physics_fingerprint_v2_of_file", altered)
    with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_PHYSICS_MISMATCH"):
        run.realize_into(tmp_path / "scene-variant", SHARE, variant)
    assert not (tmp_path / "scene-variant/scene_variant.xml").exists()


def test_a_variant_that_changed_a_collision_geom_would_be_caught_by_the_v2_comparison(tmp_path, nominal_v2):
    """The whitelist cannot express it, so build the scene a hostile edit would produce and compare as `realize_into` does."""
    path = _write(tmp_path, sv.realize(NOMINAL_DIR, WHITELISTED["wall_texture"]))
    text = path.read_text().replace('name="table_collision" type="box" size="0.25 0.30 0.02"',
                                    'name="table_collision" type="box" size="0.25 0.30 0.021"')
    assert text != path.read_text()
    assert physics_fingerprint_v2_of_string(text) != nominal_v2


def test_a_host_record_and_a_shard_agree_on_an_indoor_variant(tmp_path):
    path = _write_json(tmp_path, WHITELISTED["main_light"])
    host = run.host_record(path, SHARE)
    assert host["fingerprint_version"] == 2 and "scene_path" not in host
    spec = {"scene_variant": run.spec_entry(host), "owned_root": str(tmp_path / "shard")}
    (tmp_path / "shard").mkdir()
    scene, record = run.prepare_shard_scene(spec, SHARE)
    assert scene.is_file() and record["realized_sha256"] == host["realized_sha256"]
    assert record["physics_fingerprint"] == host["physics_fingerprint"]


def _write_json(tmp_path, document):
    path = tmp_path / "variant.json"
    path.write_text(json.dumps(document))
    return path


# ---- the renderer sees the edits ------------------------------------------------------------------------------------------------------


def _render(path, camera="side_camera"):
    try:
        model = mujoco.MjModel.from_xml_path(str(path))
        data = mujoco.MjData(model)
        mujoco.mj_resetDataKeyframe(model, data, 0)
        mujoco.mj_forward(model, data)
        renderer = mujoco.Renderer(model, 240, 320)
    except Exception as error:   # noqa: BLE001 - no GL context on this host
        pytest.skip("no offscreen renderer: " + type(error).__name__)
    try:
        renderer.update_scene(data, camera=camera)
        return renderer.render().astype(np.float32)
    finally:
        renderer.close()


def test_the_edits_are_visible_to_the_camera(tmp_path):
    nominal = _render(INDOOR_SCENE)
    assert 60 < nominal.mean() < 160       # the indoor scene is bright (the old scene renders at about 17)

    def look(name):
        return _render(_write(tmp_path, sv.realize(NOMINAL_DIR, WHITELISTED[name]), f"{name}.xml"))

    assert abs(look("wall_texture") - nominal).mean() > 0.5
    board = _variant(**{"prop.ind_board.visible": 0, "prop.ind_board_frame.visible": 0})
    hidden = _render(_write(tmp_path, sv.realize(NOMINAL_DIR, board), "board.xml"))
    assert abs(hidden - nominal).mean() > 0.5       # the whiteboard on the wall behind the table is in the side camera's view
    assert abs(look("cup_colour") - nominal).mean() > 0.01
    dark = _variant(**{"light.ind_main.diffuse": [0.0, 0.0, 0.0], "light.ind_fill0.active": 0, "light.ind_fill1.active": 0,
                       "light.ind_fill2.active": 0, "light.ind_dirfill0.active": 0, "light.ind_dirfill1.active": 0,
                       "light.key_light.active": 0, "headlight.ambient": [0.02, 0.02, 0.02], "headlight.diffuse": [0.0, 0.0, 0.0]})
    assert _render(_write(tmp_path, sv.realize(NOMINAL_DIR, dark), "dark.xml")).mean() < nominal.mean() * 0.6
