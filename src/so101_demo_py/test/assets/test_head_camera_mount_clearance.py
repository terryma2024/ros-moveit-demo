"""The optical center clears the upright shoulder-to-elbow arm envelope."""

from xml.etree import ElementTree

import mujoco
import numpy as np
import pytest
from paths import PACKAGE_ROOT


ASSETS = PACKAGE_ROOT / "assets/mujoco/act"


def test_optical_center_is_eleven_centimeters_above_upright_upper_arm():
    model = mujoco.MjModel.from_xml_path(str(ASSETS / "head_search_scene.xml"))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    upper_arm = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "upper_arm")
    up = data.xmat[upper_arm].reshape(3, 3) @ np.array([-1.0, 0.0, 0.0])
    assert up[2] > 0.999999, "The reference upper arm must stand vertically."
    highest = -np.inf
    for geom in range(model.ngeom):
        if model.geom_bodyid[geom] != upper_arm:
            continue
        assert model.geom_type[geom] == mujoco.mjtGeom.mjGEOM_MESH
        mesh = model.geom_dataid[geom]
        first = model.mesh_vertadr[mesh]
        count = model.mesh_vertnum[mesh]
        vertices = model.mesh_vert[first:first + count].astype(float)
        world = vertices @ data.geom_xmat[geom].reshape(3, 3).T + data.geom_xpos[geom]
        highest = max(highest, float(world[:, 2].max()))
    assert np.isfinite(highest)
    camera = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "head_camera")
    assert data.cam_xpos[camera, 2] - highest == pytest.approx(0.11, abs=1e-6)


def test_urdf_and_mujoco_share_the_head_mount_position():
    mjcf = ElementTree.parse(ASSETS / "so101.xml")
    urdf = ElementTree.parse(ASSETS / "so101.urdf")
    body = mjcf.find(".//body[@name='head_mount']")
    joint = urdf.find("joint[@name='neck_yaw_joint']")
    assert joint.find("parent").get("link") == "base"
    assert joint.find("child").get("link") == "head_mount"
    assert np.fromstring(joint.find("origin").get("xyz"), sep=" ") == pytest.approx(
        np.fromstring(body.get("pos"), sep=" "), abs=1e-12
    )
