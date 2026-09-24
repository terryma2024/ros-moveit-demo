"""The calibrated ACT wrist image and ROS optical frame must share one mount pose."""

from pathlib import Path
from xml.etree import ElementTree as ET

import mujoco
import numpy as np


ASSETS = Path(__file__).parents[1] / "assets/mujoco/act"
EXPECTED_MJCF_QUAT = np.array(
    (0.9839547340865649, -0.14820831798181258,
     0.09624659121013797, -0.024575789510572335)
)


def _rpy_matrix(rpy: np.ndarray) -> np.ndarray:
    roll, pitch, yaw = rpy
    cx, sx = np.cos(roll), np.sin(roll)
    cy, sy = np.cos(pitch), np.sin(pitch)
    cz, sz = np.cos(yaw), np.sin(yaw)
    return np.array((
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    ))


def test_calibrated_wrist_camera_matches_urdf_optical_frame():
    model = mujoco.MjModel.from_xml_path(str(ASSETS / "scene.xml"))
    camera = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "wrist_camera")
    mount = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "wrist_camera_mount")
    np.testing.assert_allclose(model.cam_pos[camera], (0., 0., 0.), atol=1e-12)
    np.testing.assert_allclose(model.body_pos[mount], (.045, 0., .02), atol=1e-12)
    np.testing.assert_allclose(model.cam_quat[camera], EXPECTED_MJCF_QUAT, atol=1e-12)
    np.testing.assert_allclose(model.cam_fovy[camera], 95., atol=1e-12)

    urdf = ET.parse(ASSETS / "so101.urdf").getroot()
    mount_joint = urdf.find("joint[@name='wrist_camera_mount_joint']")
    optical_joint = urdf.find("joint[@name='wrist_camera_optical_joint']")
    assert mount_joint is not None and optical_joint is not None
    assert mount_joint.find("parent").attrib["link"] == "gripper"
    assert mount_joint.find("child").attrib["link"] == "wrist_camera_mount"
    assert mount_joint.find("origin").attrib == {"xyz": "0.045 0 0.02", "rpy": "0 0 0"}
    assert optical_joint.find("parent").attrib["link"] == "wrist_camera_mount"
    assert optical_joint.find("child").attrib["link"] == "wrist_camera_frame"
    origin = optical_joint.find("origin")
    np.testing.assert_allclose(np.fromstring(origin.attrib["xyz"], sep=" "), (0., 0., 0.))
    optical_from_urdf = _rpy_matrix(np.fromstring(origin.attrib["rpy"], sep=" "))
    camera_rotation = np.empty(9, dtype=np.float64)
    mujoco.mju_quat2Mat(camera_rotation, model.cam_quat[camera])
    camera_rotation = camera_rotation.reshape(3, 3)
    optical_from_mjcf = camera_rotation @ np.diag((1., -1., -1.))
    np.testing.assert_allclose(optical_from_urdf, optical_from_mjcf, atol=1e-9)
