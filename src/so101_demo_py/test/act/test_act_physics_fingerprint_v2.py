"""Physics fingerprint version 2 (indoor scene design 2026-10-24, P1): visual-only furniture leaves it unchanged, physics moves it.

Version 1 hashes the compiled model as it is, so a scene that only ADDS visual geoms has another version 1 value. Version 2 strips the
geoms that can never collide, the bodies that only carried them and the asset-path bookkeeping, and refuses a strip that would
change a mass or an inertia.
"""

import hashlib

import mujoco
import numpy as np
import pytest

from paths import PACKAGE_ROOT
from so101_demo.act import physics_fingerprint as pf

ACT = PACKAGE_ROOT / "assets/mujoco/act"
NOMINAL = ACT / "scene_side_wrist.xml"
INDOOR = ACT / "scene_side_wrist_indoor.xml"
LAB = ACT / "indoor/scene_side_wrist_indoor_lab.xml"
HOME = ACT / "indoor/scene_side_wrist_indoor_home.xml"
SCENES = {"indoor_A": INDOOR, "indoor_B_lab": LAB, "indoor_C_home": HOME}
BOX = mujoco.mjtGeom.mjGEOM_BOX


def _spec(path=INDOOR):
    return mujoco.MjSpec.from_file(str(path))


@pytest.fixture(scope="module")
def nominal_v2():
    return pf.physics_fingerprint_v2_of_file(NOMINAL)


# ---- the indoor scenes are the nominal physics -------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCENES))
def test_every_indoor_layout_has_the_v2_fingerprint_of_the_nominal_side_wrist_scene(name, nominal_v2):
    assert pf.physics_fingerprint_v2_of_file(SCENES[name]) == nominal_v2


@pytest.mark.parametrize("name", sorted(SCENES))
def test_the_v1_fingerprint_of_an_indoor_layout_differs_from_the_nominal_one(name):
    assert pf.physics_fingerprint_of_file(SCENES[name]) != pf.physics_fingerprint_of_file(NOMINAL)


def test_v1_is_the_hash_of_the_compiled_arrays_as_it_always_was():
    """Existing records carry v1: its algorithm (no domain prefix, no strip, `npaths` included) must not move."""
    model = mujoco.MjModel.from_xml_path(str(NOMINAL))
    digest = hashlib.sha256()
    for name, value in sorted(pf._arrays(model).items()):
        data = np.ascontiguousarray(value)
        digest.update(f"{name}|{data.dtype.str}|{data.shape}|".encode())
        digest.update(data.tobytes())
    assert pf.physics_fingerprint(model) == digest.hexdigest() == pf.physics_fingerprint_of_file(NOMINAL)
    assert "npaths" in pf.covered_names(model)
    assert pf.physics_fingerprint_of_file_version(NOMINAL, 1) == digest.hexdigest()


def test_v2_is_versioned_domain_separated_and_reports_what_it_stripped(nominal_v2):
    record = pf.physics_fingerprint_v2_record_of_file(INDOOR)
    assert record["fingerprint_version"] == pf.FINGERPRINT_VERSION == 2 and pf.FINGERPRINT_VERSIONS == (1, 2)
    assert record["sha256"] == nominal_v2 and pf.physics_fingerprint_of_file_version(INDOOR, 2) == nominal_v2
    assert set(record["stripped"]) == {"geoms", "bodies", "meshes"}
    assert record["stripped"]["geoms"] > pf.physics_fingerprint_v2_record_of_file(NOMINAL)["stripped"]["geoms"] > 0
    # v2 of a scene is never its v1 (the digest is domain separated), whichever scene it is
    assert nominal_v2 != pf.physics_fingerprint_of_file(NOMINAL)
    with pytest.raises(ValueError, match="PHYSICS_FINGERPRINT_VERSION_UNKNOWN"):
        pf.physics_fingerprint_of_file_version(NOMINAL, 3)


def test_v2_leaves_out_the_asset_path_counts_and_nothing_else_that_is_physics():
    stripped = pf._strip_visual_only(_spec(NOMINAL))[1]
    names = set(pf.covered_names_v2(stripped))
    assert not names & {"npaths", "paths", "mesh_pathadr", "hfield_pathadr"}
    assert {"npaths", "mesh_pathadr"} <= set(pf.covered_names(stripped))
    assert {"geom_friction", "body_mass", "dof_damping", "opt.timestep", "geom_size", "actuator_gainprm"} <= names


def test_a_text_and_a_file_agree():
    assert pf.physics_fingerprint_v2_of_string(INDOOR.read_text().replace(
        'file="../', f'file="{INDOOR.parent.parent}/').replace('<include file="so101_side_wrist.xml" />',
        f'<include file="{INDOOR.parent / "so101_side_wrist.xml"}" />').replace(
        'file="../textures', f'file="{INDOOR.parent.parent}/textures')) == pf.physics_fingerprint_v2_of_file(INDOOR)


# ---- visual additions and edits do not move v2 -----------------------------------------------------------------------------------


def _v2(edit, path=INDOOR):
    spec = _spec(path)
    edit(spec)
    return pf.physics_fingerprint_v2(spec)


def test_a_visual_box_a_light_a_camera_and_a_colour_edit_leave_v2_unchanged(nominal_v2):
    def edit(spec):
        spec.worldbody.add_geom(name="extra_visual", type=BOX, size=[.1, .1, .1], pos=[1.5, 1.5, 0], contype=0, conaffinity=0)
        body = spec.worldbody.add_body(name="extra_prop", pos=[-1.5, 1.5, 0])
        body.add_geom(name="extra_prop_geom", type=BOX, size=[.1, .1, .1], contype=0, conaffinity=0, rgba=[1, 0, 0, 1])
        spec.worldbody.add_light(name="extra_light", pos=[0, 0, 1.9])
        spec.geom("table_visual").rgba = [0.1, 0.2, 0.3, 1.0]
        spec.visual.headlight.ambient = [0.5, 0.5, 0.5]

    assert _v2(edit) == nominal_v2


def test_a_visual_only_mesh_asset_leaves_v2_unchanged(nominal_v2):
    def edit(spec):
        mesh = spec.add_mesh(name="extra_visual_mesh")
        mesh.uservert = [0, 0, 0, 0.1, 0, 0, 0, 0.1, 0, 0, 0, 0.1]
        mesh.userface = [0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3]
        spec.worldbody.add_geom(name="extra_mesh_geom", type=mujoco.mjtGeom.mjGEOM_MESH, meshname="extra_visual_mesh",
                                pos=[1.5, 1.5, 0], contype=0, conaffinity=0)

    assert _v2(edit) == nominal_v2


# ---- every physics edit moves v2 -------------------------------------------------------------------------------------------------


def _colliding_box(spec):
    spec.worldbody.add_geom(name="x_box", type=BOX, size=[.1, .1, .1], pos=[1.0, 1.0, 0.0], contype=1, conaffinity=1)


def _colliding_box_in_a_new_body(spec):
    spec.worldbody.add_body(name="x_body", pos=[1, 1, 0]).add_geom(type=BOX, size=[.1, .1, .1], contype=1, conaffinity=1)


def _one_sided_collider(spec):
    # contype 1 / conaffinity 0 can still collide with a geom that has the bit in its conaffinity: it is not visual-only
    spec.worldbody.add_geom(name="x_one_sided", type=BOX, size=[.1, .1, .1], pos=[1.0, 1.0, 0.0], contype=1, conaffinity=0)


def _friction(spec):
    spec.geom("table_collision").friction = [0.81, 0.01, 0.001]


def _mass(spec):
    spec.body("plastic_cup").mass = 0.021


def _collision_geom_size(spec):
    spec.geom("table_collision").size = [0.25, 0.30, 0.021]


def _timestep(spec):
    spec.option.timestep = 0.0021


def _joint_damping(spec):
    spec.joint("cup_free_joint").damping = [0.02, 0.0, 0.0]


def _arm_joint_damping(spec):
    joint = spec.joint("2")
    joint.damping = [joint.damping[0] + 0.1, 0.0, 0.0]


@pytest.mark.parametrize("edit", [_colliding_box, _colliding_box_in_a_new_body, _one_sided_collider, _friction, _mass,
                                  _collision_geom_size, _timestep, _joint_damping, _arm_joint_damping],
                         ids=lambda edit: edit.__name__.strip("_"))
def test_a_physics_edit_changes_v2(edit, nominal_v2):
    assert _v2(edit) != nominal_v2


def test_the_edits_change_v2_of_the_nominal_scene_too(nominal_v2):
    for edit in (_friction, _mass, _collision_geom_size, _timestep, _joint_damping, _colliding_box):
        assert _v2(edit, NOMINAL) != nominal_v2


# ---- the strip changes no mass -----------------------------------------------------------------------------------------------------


def _mover():
    spec = mujoco.MjSpec()
    body = spec.worldbody.add_body(name="mover")
    body.add_freejoint()
    body.add_geom(name="hull", type=BOX, size=[.1, .1, .1], contype=1, conaffinity=1)
    return spec, body


def test_the_mass_guard_fires_on_a_stripped_geom_that_carries_mass():
    spec, body = _mover()
    body.add_geom(name="heavy_visual", type=BOX, size=[.1, .1, .1], pos=[0, 0, .3], contype=0, conaffinity=0, mass=1.0)
    with pytest.raises(ValueError, match="PHYSICS_FINGERPRINT_STRIP_CHANGES_MASS: body_mass of body 'mover'"):
        pf.physics_fingerprint_v2(spec)


def test_a_moving_body_whose_only_geom_is_stripped_is_refused():
    spec = mujoco.MjSpec()
    body = spec.worldbody.add_body(name="mover")
    body.add_freejoint()
    body.add_geom(name="only_visual", type=BOX, size=[.1, .1, .1], contype=0, conaffinity=0)
    with pytest.raises(ValueError, match="PHYSICS_FINGERPRINT_STRIP_"):
        pf.physics_fingerprint_v2(spec)


def test_a_body_with_an_explicit_inertial_is_kept_and_its_mass_is_unchanged():
    def build(with_visual):
        spec = mujoco.MjSpec()
        body = spec.worldbody.add_body(name="mover")
        body.add_freejoint()
        body.explicitinertial = 1
        body.mass = 1.0
        body.inertia = [.01, .01, .01]
        if with_visual:
            body.add_geom(name="only_visual", type=BOX, size=[.1, .1, .1], contype=0, conaffinity=0)
        return spec

    record = pf.physics_fingerprint_v2_record(build(True))
    assert record["stripped"] == {"geoms": 1, "bodies": 0, "meshes": 0}      # the body stays: it has an inertial
    assert record["sha256"] == pf.physics_fingerprint_v2(build(False))
    heavier = build(True)
    heavier.body("mover").mass = 1.5
    assert pf.physics_fingerprint_v2(heavier) != record["sha256"]


def test_a_static_body_that_only_carries_visual_geoms_is_removed_with_them():
    spec, _body = _mover()
    prop = spec.worldbody.add_body(name="prop", pos=[1, 0, 0])
    prop.add_geom(name="prop_geom", type=BOX, size=[.1, .1, .1], contype=0, conaffinity=0)
    record = pf.physics_fingerprint_v2_record(spec)
    assert record["stripped"]["bodies"] == 1 and record["stripped"]["geoms"] == 1
    assert record["sha256"] == pf.physics_fingerprint_v2(_mover()[0])


def test_the_strip_does_not_touch_the_spec_it_was_given():
    spec = _spec(INDOOR)
    count = len(spec.geoms)
    pf.physics_fingerprint_v2(spec)
    assert len(spec.geoms) == count
    assert pf.physics_fingerprint_v2(spec) == pf.physics_fingerprint_v2(_spec(INDOOR))


def test_a_stripped_geom_that_a_contact_pair_names_is_refused():
    spec, _body = _mover()
    spec.worldbody.add_geom(name="floorish", type=BOX, size=[.5, .5, .1], contype=0, conaffinity=0)
    spec.add_pair(geomname1="hull", geomname2="floorish")
    with pytest.raises(ValueError, match="PHYSICS_FINGERPRINT_STRIP_INVALID"):
        pf.physics_fingerprint_v2(spec)
