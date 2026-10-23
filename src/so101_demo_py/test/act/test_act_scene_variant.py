"""Evaluation-only scene variants (goal 35-R0, D1): the whitelist, the realized hash and the physics fingerprint.

The nominal scene is the shipped side+wrist ACT scene. Physics edits are made on a private copy of its asset tree.
"""

import copy
import math
import shutil

import numpy as np
import pytest

from paths import PACKAGE_ROOT
from so101_demo.act import scene_variant as sv
from so101_demo.act.physics_fingerprint import covered_names, physics_fingerprint, physics_fingerprint_of_file

NOMINAL_DIR = PACKAGE_ROOT / "assets/mujoco/act"
SIDE_QUAT = [0.5969, 0.472, -0.4024, -0.509]


def _variant(name="v", **fields):
    return {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": name, "set": fields}


#: one variant for every whitelisted field
WHITELISTED = {
    "key_light_diffuse": _variant(**{"key_light.diffuse": [0.35, 0.35, 0.35]}),
    "key_light_dir": _variant(**{"key_light.dir": [0.1, 0.5, -1.0]}),
    "headlight_off": _variant(**{"headlight.active": 0}),
    "headlight_ambient": _variant(**{"headlight.ambient": [0.3, 0.3, 0.3], "headlight.diffuse": [0.2, 0.2, 0.2]}),
    "cup_rgba": _variant(**{"cup_material.rgba": [0.1, 0.4, 0.9, 1.0]}),
    "table_rgba": _variant(**{"table_material.rgba": [0.8, 0.8, 0.8, 1.0]}),
    "table_texture": _variant(**{"table_material.texture": {"builtin": "checker", "rgb1": [0.2, 0.2, 0.2],
                                                              "rgb2": [0.7, 0.7, 0.7], "width": 64, "height": 64,
                                                              "texrepeat": [4.0, 4.0]}}),
    "camera_shift": _variant(**{"side_camera.pos_delta_m": [0.005, 0.0, -0.005]}),
    "camera_turn": _variant(**{"side_camera.quat_delta": sv.quaternion_about([1, 0, 0], 1.0)}),
    "camera_fovy": _variant(**{"side_camera.fovy": 63.86}),
}


def _write(tmp_path, realized, name="scene_variant.xml"):
    directory = tmp_path / "owned"
    directory.mkdir(exist_ok=True)
    path = directory / name
    path.write_text(realized.xml_text)
    return path


@pytest.fixture(scope="module")
def nominal_fingerprint():
    return physics_fingerprint_of_file(NOMINAL_DIR / "scene_side_wrist.xml")


# ---- the whitelist --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["geom.friction", "cup.mass", "option.timestep", "table_collision.size", "joint.damping",
                                 "actuator.kp", "wrist_camera.fovy", "task_camera.pos", "light.cutoff", "headlight.specular"])
def test_a_field_outside_the_whitelist_is_refused(key):
    with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_FIELD_REFUSED"):
        sv.normalize_variant(_variant(**{key: [1.0]}))


@pytest.mark.parametrize("fields", [
    {"key_light.diffuse": [1.0, 1.0]}, {"key_light.diffuse": [float("nan")] * 3}, {"key_light.diffuse": [9.0, 0, 0]},
    {"key_light.dir": [0.0, 0.0, 0.0]}, {"headlight.active": 2}, {"headlight.active": True},
    {"cup_material.rgba": [1.0, 1.0, 1.0]}, {"table_material.rgba": [2.0, 0, 0, 1]},
    {"table_material.texture": {"builtin": "file", "rgb1": [0, 0, 0], "rgb2": [1, 1, 1]}},
    {"table_material.texture": {"builtin": "checker", "rgb1": [0, 0, 0]}},
    {"table_material.texture": {"builtin": "checker", "rgb1": [0, 0, 0], "rgb2": [1, 1, 1], "file": "x.png"}},
    {"side_camera.pos_delta_m": [0.2, 0.0, 0.0]}, {"side_camera.quat_delta": [1.0, 0.0, 0.0, 0.2]},
    {"side_camera.quat_delta": sv.quaternion_about([0, 1, 0], 25.0)}, {"side_camera.fovy": 10.0},
])
def test_a_value_outside_its_range_is_refused(fields):
    with pytest.raises(sv.SceneVariantRefused, match="SCENE_VARIANT_VALUE_INVALID"):
        sv.normalize_variant(_variant(**fields))


@pytest.mark.parametrize("document", [
    {}, {"schema_version": 2, "kind": "ACT_SCENE_VARIANT", "name": "v", "set": {"headlight.active": 0}},
    {"schema_version": 1, "kind": "OTHER", "name": "v", "set": {"headlight.active": 0}},
    {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": "v", "set": {"headlight.active": 0}, "extra": 1},
    {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": "bad name", "set": {"headlight.active": 0}},
    {"schema_version": 1, "kind": "ACT_SCENE_VARIANT", "name": "v", "set": {}},
])
def test_a_malformed_document_is_refused(document):
    with pytest.raises(sv.SceneVariantRefused):
        sv.normalize_variant(document)


# ---- the realized scene ---------------------------------------------------------------------------------------------------------


def test_realizing_writes_nothing_and_is_deterministic(tmp_path):
    before = sorted(path.name for path in NOMINAL_DIR.iterdir())
    first = sv.realize(NOMINAL_DIR, WHITELISTED["key_light_diffuse"])
    second = sv.realize(NOMINAL_DIR, copy.deepcopy(WHITELISTED["key_light_diffuse"]))
    assert first == second and first.realized_sha256 == second.realized_sha256
    assert sorted(path.name for path in NOMINAL_DIR.iterdir()) == before


def test_the_realized_hash_follows_the_values_and_not_the_directory(tmp_path):
    shutil.copytree(PACKAGE_ROOT / "assets/mujoco", tmp_path / "copy" / "mujoco")
    here = sv.realize(NOMINAL_DIR, WHITELISTED["camera_fovy"])
    there = sv.realize(tmp_path / "copy" / "mujoco" / "act", WHITELISTED["camera_fovy"])
    assert here.realized_sha256 == there.realized_sha256 and here.xml_text != there.xml_text
    other = sv.realize(NOMINAL_DIR, _variant(**{"side_camera.fovy": 63.0}))
    assert other.realized_sha256 != here.realized_sha256 and other.variant_sha256 != here.variant_sha256
    renamed = sv.realize(NOMINAL_DIR, _variant("other-name", **{"side_camera.fovy": 63.86}))
    assert renamed.variant_sha256 != here.variant_sha256         # the name is part of the variant's identity


def test_includes_and_meshes_resolve_through_absolute_paths_to_the_nominal_directory(tmp_path):
    realized = sv.realize(NOMINAL_DIR, WHITELISTED["key_light_diffuse"])
    assert f'file="{NOMINAL_DIR}/so101_side_wrist.xml"' in realized.xml_text and f'meshdir="{NOMINAL_DIR}"' in realized.xml_text
    assert sv.DIRECTORY_TOKEN not in realized.xml_text and sv.DIRECTORY_TOKEN in realized.xml_tokenized
    path = _write(tmp_path, realized)
    assert path.parent == tmp_path / "owned"
    import mujoco
    model = mujoco.MjModel.from_xml_path(str(path))           # loads from a directory that holds only the variant file
    assert model.ngeom > 0 and model.nmesh > 0


def test_the_applied_values_record_what_took_effect():
    realized = sv.realize(NOMINAL_DIR, _variant(**{
        "side_camera.pos_delta_m": [0.005, 0.0, 0.0], "side_camera.fovy": 60.0, "key_light.diffuse": [0.35] * 3,
        "headlight.active": 0, "cup_material.rgba": [0.1, 0.4, 0.9, 1.0]}))
    applied = realized.applied
    assert applied["side_camera.pos"]["nominal"] == pytest.approx([-0.5, -0.32, 0.42])
    assert applied["side_camera.pos"]["value"] == pytest.approx([-0.495, -0.32, 0.42])
    assert applied["side_camera.fovy"] == {"nominal": 62.0, "value": 60.0}
    assert applied["key_light.diffuse"] == {"nominal": [0.7, 0.7, 0.7], "value": [0.35] * 3}
    assert applied["headlight.active"] == {"nominal": 1, "value": 0}
    assert applied["cup_material.rgba"]["nominal"] == pytest.approx([1.0, 0.55, 0.12, 1.0])


def test_a_camera_rotation_is_applied_in_the_cameras_own_frame():
    base = np.array(SIDE_QUAT) / np.linalg.norm(SIDE_QUAT)
    delta = sv.quaternion_about([0, 1, 0], 1.0)
    realized = sv.realize(NOMINAL_DIR, _variant(**{"side_camera.quat_delta": delta}))
    turned = np.array(realized.applied["side_camera.quat"]["value"])
    assert turned == pytest.approx(np.array(sv.quaternion_multiply(list(base), delta)))
    # the angle between the two orientations is the 1 degree that was asked for
    angle = math.degrees(2.0 * math.acos(min(1.0, abs(float(np.dot(base, turned))))))
    assert angle == pytest.approx(1.0, abs=1e-6)


# ---- the physics fingerprint ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(WHITELISTED))
def test_every_whitelisted_visual_edit_leaves_the_physics_fingerprint_unchanged(name, tmp_path, nominal_fingerprint):
    realized = sv.realize(NOMINAL_DIR, WHITELISTED[name])
    assert physics_fingerprint_of_file(_write(tmp_path, realized)) == nominal_fingerprint


def test_all_whitelisted_edits_together_leave_the_physics_fingerprint_unchanged(tmp_path, nominal_fingerprint):
    merged = {}
    for document in WHITELISTED.values():
        merged.update(document["set"])
    merged.pop("table_material.rgba")
    realized = sv.realize(NOMINAL_DIR, _variant("all", **merged))
    assert physics_fingerprint_of_file(_write(tmp_path, realized)) == nominal_fingerprint
    assert set(realized.variant["set"]) == set(merged)


def test_a_variant_really_differs_from_the_nominal_model_in_its_rendering_arrays(tmp_path):
    import mujoco
    nominal = mujoco.MjModel.from_xml_path(str(NOMINAL_DIR / "scene_side_wrist.xml"))
    realized = sv.realize(NOMINAL_DIR, WHITELISTED["camera_fovy"])
    variant = mujoco.MjModel.from_xml_path(str(_write(tmp_path, realized)))
    camera = mujoco.mj_name2id(nominal, mujoco.mjtObj.mjOBJ_CAMERA, "side_camera")
    assert nominal.cam_fovy[camera] == pytest.approx(62.0) and variant.cam_fovy[camera] == pytest.approx(63.86)
    assert physics_fingerprint(nominal) == physics_fingerprint(variant)


def _tree(tmp_path):
    root = tmp_path / "tree"
    shutil.copytree(PACKAGE_ROOT / "assets/mujoco", root)
    return root / "act"


def _edit(directory, filename, old, new, count=1):
    path = directory / filename
    text = path.read_text()
    assert text.count(old) >= 1, (filename, old)
    path.write_text(text.replace(old, new) if count == 0 else text.replace(old, new, count))


def _first_actuator_line(directory):
    text = (directory / "so101_side_wrist.xml").read_text()
    start = text.index("<actuator>")
    return text[start:start + 400]


PHYSICS_EDITS = {
    "cup_friction": ("scene_side_wrist.xml", 'friction="1.2 0.01 0.001"', 'friction="1.0 0.01 0.001"'),
    "table_friction": ("scene_side_wrist.xml", 'friction="0.8 0.01 0.001"', 'friction="0.9 0.01 0.001"'),
    "cup_mass": ("scene_side_wrist.xml", 'mass="0.020"', 'mass="0.021"'),
    "cup_geom_size": ("scene_side_wrist.xml", 'name="bottom_collision" class="cup_collision" type="cylinder" pos="0 0 -0.044" size="0.040 0.001"',
                      'name="bottom_collision" class="cup_collision" type="cylinder" pos="0 0 -0.044" size="0.041 0.001"'),
    "table_geom_pos": ("scene_side_wrist.xml", '<body name="table" pos="0 -0.20 0.10">', '<body name="table" pos="0 -0.20 0.101">'),
    "cup_joint_damping": ("scene_side_wrist.xml", 'damping="0.01"', 'damping="0.02"'),
    "timestep": ("scene_side_wrist.xml", 'timestep="0.002"', 'timestep="0.001"'),
    "gravity": ("scene_side_wrist.xml", 'gravity="0 0 -9.81"', 'gravity="0 0 -9.8"'),
    "robot_joint_damping": ("so101_side_wrist.xml", '<joint damping="0.60"', '<joint damping="0.61"'),
}


@pytest.mark.parametrize("name", sorted(PHYSICS_EDITS))
def test_any_physics_edit_changes_the_physics_fingerprint(name, tmp_path, nominal_fingerprint):
    directory = _tree(tmp_path)
    filename, old, new = PHYSICS_EDITS[name]
    _edit(directory, filename, old, new)
    assert physics_fingerprint_of_file(directory / "scene_side_wrist.xml") != nominal_fingerprint


def test_an_actuator_gain_edit_changes_the_physics_fingerprint(tmp_path, nominal_fingerprint):
    directory = _tree(tmp_path)
    text = (directory / "so101_side_wrist.xml").read_text()
    assert "<actuator>" in text
    import re
    match = re.search(r'kp="([0-9.eE+-]+)"', text[text.index("<actuator>"):])
    assert match is not None, _first_actuator_line(directory)
    old = match.group(0)
    _edit(directory, "so101_side_wrist.xml", old, f'kp="{float(match.group(1)) * 1.1:.6g}"')
    assert physics_fingerprint_of_file(directory / "scene_side_wrist.xml") != nominal_fingerprint


def test_the_fingerprint_is_the_same_for_the_same_model_compiled_twice(nominal_fingerprint):
    assert physics_fingerprint_of_file(NOMINAL_DIR / "scene_side_wrist.xml") == nominal_fingerprint


def test_the_fingerprint_covers_physics_arrays_and_none_of_the_rendering_ones():
    import mujoco
    model = mujoco.MjModel.from_xml_path(str(NOMINAL_DIR / "scene_side_wrist.xml"))
    names = covered_names(model)
    for physics in ("geom_friction", "geom_size", "body_mass", "dof_damping", "actuator_gainprm", "opt.timestep", "opt.gravity"):
        assert physics in names, physics
    for rendering in ("cam_fovy", "cam_pos", "light_diffuse", "light_dir", "mat_rgba", "geom_rgba", "geom_matid"):
        assert rendering not in names, rendering


# ---- the change is visible --------------------------------------------------------------------------------------------------------


def _render(model, camera="side_camera", size=(240, 320)):
    import mujoco
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, height=size[0], width=size[1])
    try:
        renderer.update_scene(data, camera=camera)
        return renderer.render().copy()
    finally:
        renderer.close()


def _model(tmp_path, document, name):
    import mujoco
    realized = sv.realize(NOMINAL_DIR, document)
    return mujoco.MjModel.from_xml_path(str(_write(tmp_path, realized, name)))


def test_a_lighting_variant_changes_a_fresh_side_camera_image(tmp_path):
    import mujoco
    nominal = mujoco.MjModel.from_xml_path(str(NOMINAL_DIR / "scene_side_wrist.xml"))
    base = _render(nominal)
    assert np.array_equal(base, _render(nominal))                       # rendering is deterministic: a difference is the variant
    dark = _render(_model(tmp_path, _variant(**{"key_light.diffuse": [0.35, 0.35, 0.35]}), "dark.xml"))
    off = _render(_model(tmp_path, _variant(**{"headlight.active": 0}), "off.xml"))
    assert not np.array_equal(base, dark) and not np.array_equal(base, off)
    assert dark.astype(float).mean() < base.astype(float).mean()        # half the light is darker, not just different


def test_a_colour_variant_changes_the_cup_pixels_and_not_the_pose(tmp_path):
    import mujoco
    nominal = mujoco.MjModel.from_xml_path(str(NOMINAL_DIR / "scene_side_wrist.xml"))
    blue = _model(tmp_path, _variant(**{"cup_material.rgba": [0.1, 0.3, 0.9, 1.0]}), "blue.xml")
    assert not np.array_equal(_render(nominal), _render(blue))
    assert physics_fingerprint(nominal) == physics_fingerprint(blue)


GREEN_CUP = {"cup_material.rgba": [0.0, 1.0, 0.0, 1.0]}     # a colour nothing else in the scene has, to find the cup in an image


def _cup_centroid(image):
    red, green, blue = (image[..., index].astype(int) for index in range(3))
    mask = (green > red + 40) & (green > blue + 40)
    assert mask.sum() > 20
    rows, columns = np.nonzero(mask)
    return float(columns.mean()), float(rows.mean())


def _project(model, point, size):
    """Pixel of a world point in `side_camera` by the pinhole model that the camera's fovy defines."""
    import mujoco
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    camera = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "side_camera")
    rotation = data.cam_xmat[camera].reshape(3, 3)
    local = rotation.T @ (np.asarray(point) - data.cam_xpos[camera])          # the camera looks along its -z axis
    focal = (size[0] / 2.0) / math.tan(math.radians(model.cam_fovy[camera]) / 2.0)
    return size[1] / 2.0 + focal * local[0] / -local[2], size[0] / 2.0 - focal * local[1] / -local[2]


@pytest.mark.parametrize("fovy,shift", [(None, None), (59.9, None), (None, [0.005, 0.0, 0.0])])
def test_the_projection_follows_the_variant_camera(fovy, shift, tmp_path):
    """The cup's pixel position in a fresh image is where the variant camera's own intrinsics and pose put the cup."""
    import mujoco
    fields = dict(GREEN_CUP)
    if fovy is not None:
        fields["side_camera.fovy"] = fovy
    if shift is not None:
        fields["side_camera.pos_delta_m"] = shift
    model = _model(tmp_path, _variant("proj", **fields), "proj.xml")
    size = (240, 320)
    seen = _cup_centroid(_render(model, size=size))
    cup_centre = [0.02, -0.28, 0.165 - 0.0]
    predicted = _project(model, cup_centre, size)
    assert math.hypot(seen[0] - predicted[0], seen[1] - predicted[1]) < 6.0, (seen, predicted)


def test_a_fovy_variant_moves_the_cup_in_the_image_as_the_focal_length_says(tmp_path):
    import mujoco
    nominal = _model(tmp_path, _variant("green", **GREEN_CUP), "green.xml")
    wide = _model(tmp_path, _variant("wide", **GREEN_CUP, **{"side_camera.fovy": 63.86}), "wide.xml")
    size = (240, 320)
    a, b = _cup_centroid(_render(nominal, size=size)), _cup_centroid(_render(wide, size=size))
    centre = np.array([size[1] / 2.0, size[0] / 2.0])
    ratio = np.linalg.norm(np.array(b) - centre) / np.linalg.norm(np.array(a) - centre)
    expected = math.tan(math.radians(62.0) / 2.0) / math.tan(math.radians(63.86) / 2.0)
    assert ratio == pytest.approx(expected, abs=0.02)
