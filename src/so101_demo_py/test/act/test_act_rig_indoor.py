"""Rig `side-wrist-indoor` (rig v3) and its assets (indoor scene design 2026-10-24, P1).

The rig is the side+wrist rig in a scene of its own: the robot MJCF, URDF, plugins, controllers, cameras, state and action are those of
`side-wrist`, and the `side-wrist` rig and its files are untouched. The textures are procedural PNGs with a manifest; the scenes
refer to them by package-relative paths and the package installs every asset directory.
"""

import hashlib
import json
import re
import subprocess
import sys

import mujoco
import pytest
import yaml
from paths import PACKAGE_ROOT, REPOSITORY

from so101_demo.act import contact_collector
from so101_demo.act.rig_files import KNOWN_SCENES, RIG_MODEL_FILES, foreign_files, rig_for_scene, rig_model_files
from so101_demo.act.rig_profile import (
    HEAD_WRIST_RIG, KNOWN_RIGS, SIDE_WRIST_INDOOR_RIG, SIDE_WRIST_RIG, known_rig, load_rig_profile, rig_from_observation,
    rig_from_profile_sha256, source_keys_for)

SIDE = rig_model_files(SIDE_WRIST_RIG)
INDOOR = rig_model_files(SIDE_WRIST_INDOOR_RIG)
ACT = PACKAGE_ROOT / "assets/mujoco/act"
TEXTURES = PACKAGE_ROOT / "assets/mujoco/textures/indoor"
CANDIDATES = sorted((ACT / "indoor").glob("*.xml"))


# ---- the rig -----------------------------------------------------------------------------------------------------------------


def test_the_indoor_rig_is_known_by_name_and_digest_and_is_the_side_wrist_rig_but_for_its_name():
    assert known_rig("side-wrist-indoor") is SIDE_WRIST_INDOOR_RIG and "side-wrist-indoor" in KNOWN_RIGS
    assert rig_from_profile_sha256(SIDE_WRIST_INDOOR_RIG.profile_sha256) is SIDE_WRIST_INDOOR_RIG
    assert SIDE_WRIST_INDOOR_RIG.profile_sha256 not in (SIDE_WRIST_RIG.profile_sha256, HEAD_WRIST_RIG.profile_sha256)
    assert {**SIDE_WRIST_INDOOR_RIG.document, "rig": "side-wrist"} == SIDE_WRIST_RIG.document
    assert SIDE_WRIST_INDOOR_RIG.camera_topics == SIDE_WRIST_RIG.camera_topics and SIDE_WRIST_INDOOR_RIG.state_dim == 6
    assert source_keys_for(SIDE_WRIST_INDOOR_RIG) == source_keys_for(SIDE_WRIST_RIG)
    assert load_rig_profile(PACKAGE_ROOT / "config/act/rig-v3.yaml").document == SIDE_WRIST_INDOOR_RIG.document


def test_a_lookup_by_cameras_alone_still_resolves_to_the_side_wrist_rig():
    """The observation (cameras and state width) is the same in both scenes; only the name says which scene a record belongs to."""
    assert rig_from_observation(["side", "wrist"], 6) is SIDE_WRIST_RIG
    assert tuple(KNOWN_RIGS) == ("head-wrist", "side-wrist", "side-wrist-indoor")


def test_the_indoor_rig_has_a_scene_of_its_own_and_every_other_file_of_the_side_wrist_rig():
    assert INDOOR.rig == "side-wrist-indoor" and INDOOR.scene == "assets/mujoco/act/scene_side_wrist_indoor.xml"
    assert INDOOR.scene != SIDE.scene
    for field in ("robot_mjcf", "urdf", "plugins", "controllers"):
        assert getattr(INDOOR, field) == getattr(SIDE, field), field
    assert INDOOR.profile == "config/act/rig-v3.yaml" and (PACKAGE_ROOT / INDOOR.profile).is_file()
    assert set(RIG_MODEL_FILES) == set(KNOWN_RIGS)
    assert INDOOR.scene in KNOWN_SCENES and rig_for_scene(INDOOR.scene) is INDOOR and rig_for_scene(SIDE.scene) is SIDE
    # a candidate layout is not the scene of any rig
    for path in CANDIDATES:
        with pytest.raises(ValueError, match="RIG_SCENE_UNKNOWN"):
            rig_for_scene(str(path.relative_to(PACKAGE_ROOT)))


def test_every_file_of_the_indoor_rig_exists_and_the_candidates_are_the_rigs_variants():
    for relative in INDOOR.exclusive:
        assert (PACKAGE_ROOT / relative).is_file(), relative
    assert {PACKAGE_ROOT / relative for relative in INDOOR.variants} == set(CANDIDATES) and len(CANDIDATES) == 2


def test_the_side_wrist_and_head_wrist_rigs_did_not_change():
    """Their files are the ones sealed data verifies against: the pinned side+wrist scene is still the scene of the rig."""
    assert SIDE.scene == "assets/mujoco/act/scene_side_wrist.xml" and SIDE.variants == ()
    assert hashlib.sha256((PACKAGE_ROOT / SIDE.scene).read_bytes()).hexdigest() == contact_collector.RIG_IDENTITIES["side-wrist"][0]
    assert INDOOR.exclusive & SIDE.exclusive == {SIDE.robot_mjcf, SIDE.urdf, SIDE.plugins, SIDE.controllers}
    assert not foreign_files(SIDE_WRIST_INDOOR_RIG) & INDOOR.exclusive
    # the contact calibration of the indoor rig is a separate, confirmed step: no scene or model pin exists for it yet
    assert "side-wrist-indoor" not in contact_collector.RIG_IDENTITIES
    with pytest.raises(ValueError, match="RIG_PROFILE_UNKNOWN"):
        contact_collector.rig_identity(SIDE_WRIST_INDOOR_RIG)


def test_the_indoor_scene_is_the_side_wrist_model_with_its_cameras_and_the_cup_keyframes():
    side = mujoco.MjModel.from_xml_path(str(PACKAGE_ROOT / SIDE.scene))
    indoor = mujoco.MjModel.from_xml_path(str(PACKAGE_ROOT / INDOOR.scene))
    assert (indoor.nq, indoor.nv, indoor.nu, indoor.nkey, indoor.ncam) == (side.nq, side.nv, side.nu, side.nkey, side.ncam) == (13, 12, 6, 4, 3)
    for kind in (mujoco.mjtObj.mjOBJ_CAMERA, mujoco.mjtObj.mjOBJ_JOINT, mujoco.mjtObj.mjOBJ_ACTUATOR, mujoco.mjtObj.mjOBJ_KEY):
        count = {mujoco.mjtObj.mjOBJ_CAMERA: side.ncam, mujoco.mjtObj.mjOBJ_JOINT: side.njnt,
                 mujoco.mjtObj.mjOBJ_ACTUATOR: side.nu, mujoco.mjtObj.mjOBJ_KEY: side.nkey}[kind]
        assert [mujoco.mj_id2name(indoor, kind, i) for i in range(count)] == [mujoco.mj_id2name(side, kind, i) for i in range(count)]
    assert (indoor.cam_pos == side.cam_pos).all() and (indoor.cam_quat == side.cam_quat).all() and (indoor.cam_fovy == side.cam_fovy).all()
    assert (indoor.key_qpos == side.key_qpos).all() and indoor.opt.timestep == side.opt.timestep
    assert indoor.nlight == 7 and side.nlight == 1


# ---- the scenes ----------------------------------------------------------------------------------------------------------------


def _scene_files():
    return [PACKAGE_ROOT / INDOOR.scene, *CANDIDATES]


@pytest.mark.parametrize("path", _scene_files(), ids=lambda path: path.name)
def test_every_added_element_is_visual_only_static_and_massless(path):
    model = mujoco.MjModel.from_xml_path(str(path))
    base = mujoco.MjModel.from_xml_path(str(PACKAGE_ROOT / SIDE.scene))
    names = {mujoco.mj_id2name(base, mujoco.mjtObj.mjOBJ_GEOM, i) for i in range(base.ngeom)}
    added = [i for i in range(model.ngeom) if mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) not in names]
    assert added and all(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i).startswith("ind_") for i in added)
    for i in added:
        assert model.geom_contype[i] == 0 and model.geom_conaffinity[i] == 0
        body = model.geom_bodyid[i]
        assert model.body_mass[body] == 0.0 and model.body_dofnum[body] == 0 and model.body_weldid[body] == 0
    # nothing was added to the dynamic part: same degrees of freedom, same bodies with mass
    assert (model.nq, model.nv, model.nu, model.njnt) == (base.nq, base.nv, base.nu, base.njnt)
    assert sorted(model.body_mass[model.body_mass > 0]) == sorted(base.body_mass[base.body_mass > 0])


@pytest.mark.parametrize("path", _scene_files(), ids=lambda path: path.name)
def test_the_cameras_have_a_clear_view_and_the_props_are_outside_the_arm_envelope(path):
    """Walls at 1.5 to 2.5 m from the base, props beyond the 0.70 m reach margin, nothing between a camera and the workspace."""
    model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    import numpy as np

    base_pos = np.array([0.0, 0.0, 0.19])
    for name, axis in (("ind_wall_xneg", 0), ("ind_wall_xpos", 0), ("ind_wall_yneg", 1), ("ind_wall_ypos", 1)):
        geom = model.geom(name).id
        distance = abs(float(data.geom_xpos[geom][axis] - base_pos[axis])) - float(model.geom_size[geom][axis])
        assert 1.5 <= distance <= 2.5, (name, distance)
    for geom in range(model.ngeom):
        name = model.geom(geom).name
        if not name.startswith("ind_") or name.startswith(("ind_desk", "ind_floor", "ind_wall", "ind_ceiling", "ind_rug")):
            continue
        centre, rotation, size = data.geom_xpos[geom], data.geom_xmat[geom].reshape(3, 3), model.geom_size[geom]
        extent = np.array([size[0], size[0], size[1]]) if model.geom_type[geom] == mujoco.mjtGeom.mjGEOM_CYLINDER else np.abs(rotation) @ size
        gap = np.linalg.norm(np.maximum(np.maximum(centre - extent - base_pos, 0), base_pos - (centre + extent)))
        assert gap > 0.70, (name, gap)
    points = [np.array([x, y, 0.125]) for x in np.linspace(-0.2, 0.2, 5) for y in np.linspace(-0.45, 0.05, 5)]
    for camera in range(model.ncam):
        origin = data.cam_xpos[camera]
        for point in points:
            ray = point - origin
            distance = np.linalg.norm(ray)
            hit = np.zeros(1, np.int32)
            reach = mujoco.mj_ray(model, data, origin, ray / distance, None, 1, -1, hit)
            if hit[0] >= 0 and reach < distance - 1e-3:
                assert not model.geom(hit[0]).name.startswith("ind_"), (model.camera(camera).name, model.geom(hit[0]).name)


def test_the_scene_files_hold_no_absolute_path_and_every_texture_they_name_is_in_the_manifest():
    manifest = json.loads((TEXTURES / "manifest.json").read_text())
    listed = {entry["file"] for entry in manifest["textures"]}
    for path in _scene_files():
        text = path.read_text()
        assert "/home/" not in text and "/data/" not in text and "/opt/" not in text, path.name
        for reference in re.findall(r'<texture [^>]*file="([^"]+)"', text):
            target = (path.parent / reference).resolve()
            assert target.parent == TEXTURES.resolve() and target.name in listed, (path.name, reference)
            assert target.is_file()
    used = {name for path in _scene_files() for name in re.findall(r'textures/indoor/([a-z_]+\.png)', path.read_text())}
    assert used <= listed


# ---- the textures --------------------------------------------------------------------------------------------------------------


def test_the_texture_manifest_lists_every_png_with_its_sha256_size_and_the_generator_command():
    manifest = json.loads((TEXTURES / "manifest.json").read_text())
    assert manifest["kind"] == "SO101_INDOOR_TEXTURE_MANIFEST" and manifest["schema_version"] == 1
    assert manifest["generator"] == "scripts/assets/gen_indoor_textures.py" and (REPOSITORY / manifest["generator"]).is_file()
    assert manifest["command"].startswith("python scripts/assets/gen_indoor_textures.py")
    files = {path.name for path in TEXTURES.glob("*.png")}
    assert files == {entry["file"] for entry in manifest["textures"]} and len(files) == len(manifest["textures"]) >= 16
    for entry in manifest["textures"]:
        data = (TEXTURES / entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"] and len(data) == entry["bytes"], entry["file"]
        assert (entry["width"], entry["height"]) == (512, 512) and isinstance(entry["seed"], int)
    assert len({entry["seed"] for entry in manifest["textures"]}) == len(manifest["textures"])


def test_the_generator_is_deterministic_and_reproduces_the_manifest_layout(tmp_path):
    out = tmp_path / "textures"
    command = [sys.executable, "-I", str(REPOSITORY / "scripts/assets/gen_indoor_textures.py"), "--out", str(out)]
    subprocess.run(command, check=True, capture_output=True, timeout=300)
    first = json.loads((out / "manifest.json").read_text())
    committed = json.loads((TEXTURES / "manifest.json").read_text())
    assert [(e["file"], e["seed"], e["generator"], e["width"], e["height"]) for e in first["textures"]] == [
        (e["file"], e["seed"], e["generator"], e["width"], e["height"]) for e in committed["textures"]]
    again = tmp_path / "again"
    subprocess.run([*command[:-1], str(again)], check=True, capture_output=True, timeout=300)
    assert {p.name: p.read_bytes() for p in out.iterdir()} == {p.name: p.read_bytes() for p in again.iterdir()}


# ---- installation --------------------------------------------------------------------------------------------------------------


def test_the_package_installs_the_indoor_scenes_textures_and_manifest_like_every_other_asset():
    setup = PACKAGE_ROOT / "setup.py"
    namespace = {"__name__": "setup_probe"}
    source = setup.read_text().split("setup(\n    name=package_name")[0]
    source = source.replace("Path(__file__).resolve().parent", f"Path({str(PACKAGE_ROOT.resolve())!r})")
    exec(compile(source, str(setup), "exec"), namespace)    # noqa: S102 - the module's own resource table, nothing is installed
    installed = {entry for _directory, files in namespace["installed_resources"]() for entry in files}
    wanted = {str(path.relative_to(PACKAGE_ROOT)) for path in (*TEXTURES.iterdir(), *CANDIDATES, ACT / "scene_side_wrist_indoor.xml")}
    wanted.add("config/act/rig-v3.yaml")
    assert wanted <= installed and len(wanted) == 16 + 1 + 2 + 1 + 1
    targets = {directory for directory, files in namespace["installed_resources"]() if any(f in wanted for f in files)}
    assert "share/so101_demo_py/assets/mujoco/textures/indoor" in targets and "share/so101_demo_py/assets/mujoco/act/indoor" in targets


def test_the_yaml_profile_names_a_valid_rig():
    document = yaml.safe_load((PACKAGE_ROOT / "config/act/rig-v3.yaml").read_text())
    assert document["rig"] == "side-wrist-indoor" and document["state"]["state_dim"] == 6
