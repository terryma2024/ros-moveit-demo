"""The side+wrist rig's simulator files: no head, no neck, a jaw-mounted wrist camera and a fixed side camera.

The MJCF, URDF, camera plugin config and controller config of the rig (`act/rig_files.py`) are checked against each other and against
the head+wrist rig's files they are variants of.
"""

from xml.etree import ElementTree as ET

import mujoco
import numpy as np
import yaml
from paths import PACKAGE_ROOT

from so101_demo.act.rig_files import RIG_MODEL_FILES, foreign_files, rig_for_scene, rig_model_files
from so101_demo.act.rig_profile import HEAD_WRIST_RIG, SIDE_WRIST_RIG

SIDE = rig_model_files(SIDE_WRIST_RIG)
HEAD = rig_model_files(HEAD_WRIST_RIG)
WRIST_POS = (-0.014, -0.012, 0.050)
WRIST_QUAT = np.array((0.8175, -0.5712, 0.0421, -0.0602))
SIDE_POS = (-0.50, -0.32, 0.42)
SIDE_QUAT = np.array((0.5969, 0.472, -0.4024, -0.509))


def _model(files=SIDE):
    return mujoco.MjModel.from_xml_path(str(PACKAGE_ROOT / files.scene))


def _name(model, kind, index):
    return mujoco.mj_id2name(model, kind, index)


def _names(model, kind, count):
    return [_name(model, kind, index) for index in range(count)]


def _unit(quat):
    return quat / np.linalg.norm(quat)


def test_every_rig_file_exists_and_the_two_rigs_share_none():
    for files in RIG_MODEL_FILES.values():
        for relative in files.exclusive:
            assert (PACKAGE_ROOT / relative).is_file(), relative
    assert not (SIDE.exclusive & HEAD.exclusive)
    assert foreign_files(HEAD_WRIST_RIG) == SIDE.exclusive
    assert foreign_files(SIDE_WRIST_RIG) == HEAD.exclusive
    assert rig_for_scene(SIDE.scene) is SIDE and rig_for_scene(HEAD.scene) is HEAD


def test_side_wrist_scene_has_no_head_and_no_neck():
    model = _model()
    bodies = _names(model, mujoco.mjtObj.mjOBJ_BODY, model.nbody)
    joints = _names(model, mujoco.mjtObj.mjOBJ_JOINT, model.njnt)
    actuators = _names(model, mujoco.mjtObj.mjOBJ_ACTUATOR, model.nu)
    cameras = _names(model, mujoco.mjtObj.mjOBJ_CAMERA, model.ncam)
    geoms = _names(model, mujoco.mjtObj.mjOBJ_GEOM, model.ngeom)
    assert joints == ["1", "2", "3", "4", "5", "6", "cup_free_joint"]
    assert actuators == ["1", "2", "3", "4", "5", "6"]
    assert sorted(cameras) == ["side_camera", "task_camera", "wrist_camera"]
    assert (model.nq, model.nv, model.nu) == (13, 12, 6)
    for names in (bodies, joints, actuators, cameras, geoms):
        assert not [name for name in names if name and ("head" in name or "neck" in name or "wrist_camera_mount" in name)]
    source = (PACKAGE_ROOT / SIDE.robot_mjcf).read_text() + (PACKAGE_ROOT / SIDE.scene).read_text()
    assert "head" not in source and "neck" not in source and "wrist_camera_mount" not in source


def test_side_wrist_keyframes_have_the_six_joint_layout():
    model = _model()
    for index in range(model.nkey):
        name = _name(model, mujoco.mjtObj.mjOBJ_KEY, index)
        assert name in {"task_start", "cup_test_forward_5cm", "cup_test_left_5cm", "cup_test_right_5cm"}
        assert len(model.key_qpos[index]) == 13 and len(model.key_ctrl[index]) == 6
        np.testing.assert_allclose(model.key_qpos[index][:6], 0.0)
    head = _model(HEAD)
    for index in range(model.nkey):
        # the cup start of every keyframe is the head+wrist scene's, only the neck column is gone
        np.testing.assert_allclose(model.key_qpos[index][6:], head.key_qpos[index][7:])


def test_wrist_camera_rides_the_moving_jaw_and_side_camera_is_a_world_camera():
    model = _model()
    wrist = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "wrist_camera")
    side = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "side_camera")
    jaw = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "jaw")
    assert model.cam_bodyid[wrist] == jaw and model.cam_bodyid[side] == 0
    np.testing.assert_allclose(model.cam_pos[wrist], WRIST_POS, atol=1e-12)
    np.testing.assert_allclose(model.cam_quat[wrist], _unit(WRIST_QUAT), atol=1e-12)
    np.testing.assert_allclose(model.cam_fovy[[wrist, side]], (90.0, 62.0))
    np.testing.assert_allclose(model.cam_pos[side], SIDE_POS, atol=1e-12)
    np.testing.assert_allclose(model.cam_quat[side], _unit(SIDE_QUAT), atol=1e-12)
    np.testing.assert_array_equal(model.cam_resolution[[wrist, side]], [[640, 480], [640, 480]])


def test_side_wrist_robot_is_the_head_wrist_robot_minus_the_head_and_the_camera_mount():
    side, head = _model(), _model(HEAD)
    keep = [name for name in _names(head, mujoco.mjtObj.mjOBJ_GEOM, head.ngeom)
            if name and not name.startswith("head_") and name != "wrist_camera_mount_collision"]
    assert [name for name in _names(side, mujoco.mjtObj.mjOBJ_GEOM, side.ngeom) if name] == keep
    # same masses and arm geometry: the jaw and the arm weigh what they weighed
    for body in ("base", "shoulder", "upper_arm", "lower_arm", "wrist", "gripper", "jaw"):
        a = mujoco.mj_name2id(side, mujoco.mjtObj.mjOBJ_BODY, body)
        b = mujoco.mj_name2id(head, mujoco.mjtObj.mjOBJ_BODY, body)
        np.testing.assert_allclose(side.body_mass[a], head.body_mass[b])
        np.testing.assert_allclose(side.body_pos[a], head.body_pos[b])


def _rpy_matrix(rpy):
    roll, pitch, yaw = rpy
    cx, sx, cy, sy, cz, sz = np.cos(roll), np.sin(roll), np.cos(pitch), np.sin(pitch), np.cos(yaw), np.sin(yaw)
    return np.array(((cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
                     (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx), (-sy, cy * sx, cy * cx)))


def _urdf_optical_pose(urdf, angles):
    """(position, rotation) of wrist_camera_frame in the root link of the URDF at the joint angles."""
    joints = {joint.find("child").attrib["link"]: joint for joint in urdf.findall("joint")}
    transform = np.eye(4)
    link = "wrist_camera_frame"
    while link in joints:
        joint = joints[link]
        origin = joint.find("origin")
        local = np.eye(4)
        local[:3, :3] = _rpy_matrix(np.fromstring(origin.attrib.get("rpy", "0 0 0"), sep=" "))
        local[:3, 3] = np.fromstring(origin.attrib.get("xyz", "0 0 0"), sep=" ")
        if joint.attrib["type"] in {"revolute", "continuous"}:
            axis = np.fromstring(joint.find("axis").attrib["xyz"], sep=" ")
            theta = angles[joint.attrib["name"]]
            cross = np.array(((0.0, -axis[2], axis[1]), (axis[2], 0.0, -axis[0]), (-axis[1], axis[0], 0.0)))
            rotation = np.eye(4)
            rotation[:3, :3] = np.eye(3) + np.sin(theta) * cross + (1.0 - np.cos(theta)) * cross @ cross
            local = local @ rotation
        transform = local @ transform
        link = joint.find("parent").attrib["link"]
    return transform[:3, 3], transform[:3, :3], link


def test_urdf_wrist_optical_frame_matches_the_mjcf_camera_at_arbitrary_arm_poses():
    model = _model()
    data = mujoco.MjData(model)
    urdf = ET.parse(PACKAGE_ROOT / SIDE.urdf).getroot()
    camera = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "wrist_camera")
    rng = np.random.default_rng(7)
    for _ in range(5):
        q = rng.uniform(-0.8, 0.8, 6)
        q[5] = rng.uniform(0.0, 1.2)
        mujoco.mj_resetData(model, data)
        data.qpos[:6] = q
        mujoco.mj_forward(model, data)
        position, rotation, root = _urdf_optical_pose(urdf, {str(i + 1): q[i] for i in range(6)})
        assert root == "world"
        expected_position = data.cam_xpos[camera]
        expected_rotation = data.cam_xmat[camera].reshape(3, 3) @ np.diag((1.0, -1.0, -1.0))
        np.testing.assert_allclose(position, expected_position, atol=1e-6)
        np.testing.assert_allclose(rotation, expected_rotation, atol=1e-6)


def test_side_wrist_urdf_has_no_head_neck_or_camera_mount_and_hangs_the_wrist_camera_on_the_jaw():
    urdf = ET.parse(PACKAGE_ROOT / SIDE.urdf).getroot()
    text = (PACKAGE_ROOT / SIDE.urdf).read_text()
    assert "neck" not in text and "head_" not in text and "wrist_camera_mount" not in text
    links = [link.attrib["name"] for link in urdf.findall("link")]
    assert "wrist_camera_frame" in links and "head_mount" not in links and "head_camera_frame" not in links
    optical = urdf.find("joint[@name='wrist_camera_optical_joint']")
    assert optical.find("parent").attrib["link"] == "jaw" and optical.find("child").attrib["link"] == "wrist_camera_frame"
    system = urdf.find("ros2_control")
    assert [joint.attrib["name"] for joint in system.findall("joint")] == ["1", "2", "3", "4", "5", "6"]
    head = ET.parse(PACKAGE_ROOT / HEAD.urdf).getroot()
    removed = {joint.attrib["name"] for joint in head.findall("joint")} - {joint.attrib["name"] for joint in urdf.findall("joint")}
    assert removed == {"neck_yaw_joint", "head_camera_optical_joint", "wrist_camera_mount_joint"}
    assert "@SO101_MUJOCO_SCENE@" in text


def test_side_wrist_camera_plugin_lists_wrist_side_and_task_cameras_only():
    plugins = yaml.safe_load((PACKAGE_ROOT / SIDE.plugins).read_text())["/**"]["ros__parameters"]
    cameras = plugins["mujoco_plugins"]["mujoco_camera_plugin"]
    assert cameras["camera_publish_rate"] == 10.0
    assert {key for key, value in cameras.items() if isinstance(value, dict)} == {"task_camera", "wrist_camera", "side_camera"}
    assert cameras["side_camera"] == {"policy": "streaming", "frame_name": "side_camera_frame",
                                      "image_topic": "/side_camera/color", "info_topic": "/side_camera/camera_info",
                                      "publish_depth": False}
    head = yaml.safe_load((PACKAGE_ROOT / HEAD.plugins).read_text())["/**"]["ros__parameters"]
    assert cameras["wrist_camera"] == head["mujoco_plugins"]["mujoco_camera_plugin"]["wrist_camera"]
    assert cameras["task_camera"] == head["mujoco_plugins"]["mujoco_camera_plugin"]["task_camera"]
    assert plugins["scalar_joint_audit_names"] == ["1", "2", "3", "4", "5", "6"]
    # everything else is the head+wrist config
    other = {key: value for key, value in plugins.items() if key not in {"mujoco_plugins", "scalar_joint_audit_names"}}
    assert other == {key: value for key, value in head.items() if key not in {"mujoco_plugins", "scalar_joint_audit_names"}}
    assert "head" not in (PACKAGE_ROOT / SIDE.plugins).read_text() and "neck" not in (PACKAGE_ROOT / SIDE.plugins).read_text()
    # the audited joints exist in the scene
    model = _model()
    for name in plugins["scalar_joint_audit_names"]:
        assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name) >= 0


def test_side_wrist_controllers_have_no_neck_controller():
    document = yaml.safe_load((PACKAGE_ROOT / SIDE.controllers).read_text())
    head = yaml.safe_load((PACKAGE_ROOT / HEAD.controllers).read_text())
    assert set(document) == set(head) - {"neck_controller"}
    assert set(document["controller_manager"]["ros__parameters"]) == set(head["controller_manager"]["ros__parameters"]) - {"neck_controller"}
    assert "neck" not in (PACKAGE_ROOT / SIDE.controllers).read_text()
    for key in document:
        assert document[key] == head[key] or key == "controller_manager"


def test_the_scene_keeps_the_model_extent_the_camera_poses_were_confirmed_in():
    """The camera near plane is a fraction of the model extent; the head body no longer inflates it, so the scene pins it."""
    side, head = _model(), _model(HEAD)
    assert side.stat.extent == head.stat.extent
    assert side.vis.map.znear * side.stat.extent == head.vis.map.znear * head.stat.extent


def test_moveit_configuration_never_names_the_neck_or_the_head():
    for relative in ("config/mujoco/so101.srdf", "config/mujoco/moveit_controllers.yaml", "config/mujoco/joint_limits.yaml",
                     "config/mujoco/kinematics.yaml", "config/mujoco/ompl_planning.yaml"):
        text = (PACKAGE_ROOT / relative).read_text()
        assert "neck" not in text and "head" not in text, relative
