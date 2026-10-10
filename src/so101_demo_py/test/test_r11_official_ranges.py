"""R11: the ACT model's joint ranges follow the official SO-101 MJCF (so101_new_calib.xml, sha256
OFFICIAL_SHA below, local copy of the SO101 side-comparison download); the main model, the robot parameters and every
frozen target stay as they were. Official strings are pinned here (the official copy is not in the repository)."""
import glob
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from act_identity import PACKAGE

pytestmark = pytest.mark.fast
OFFICIAL_SHA = "d75253eb568e8a7214db9c631ab7bed4217f608a26f7276ebe9a7636cac82580"  # sha256 of Simulation/SO101/so101_new_calib.xml as downloaded
# official joint range strings (so101_new_calib.xml joint elements) for the three joints that change
OFFICIAL_RANGE = {"3": "-1.69 1.69", "5": "-2.7438472969992493 2.841206309382605",
                  "6": "-0.17453297762778586 1.7453291995659765"}
# official actuator ctrlrange strings (so101_new_calib.xml actuator elements)
OFFICIAL_CTRL = {"3": "-1.69 1.69", "5": "-2.74385 2.84121", "6": "-0.17453 1.74533"}
UNCHANGED_RANGE = {"1": (-1.91986, 1.91986), "2": (-1.74533, 1.74533), "4": (-1.65806, 1.65806)}
MAIN_SHA = {"assets/mujoco/so101.xml": "f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca",
            "assets/mujoco/so101.urdf": "73ab5bdd26451778c094a837817c65748b1e8bacd48672e313c941d8ca85f0b2"}
ACT_MJCF, ACT_URDF = PACKAGE / "assets/mujoco/act/so101.xml", PACKAGE / "assets/mujoco/act/so101.urdf"


def numbers(text):
    return tuple(float(item) for item in text.split())


def mjcf_joints():
    return {item.get("name"): item for item in ET.parse(ACT_MJCF).getroot().iter("joint")}


def mjcf_actuators():
    return {item.get("name"): item for item in ET.parse(ACT_MJCF).getroot().iter("position")}


def urdf_limits():
    return {joint.get("name"): joint.find("limit") for joint in ET.parse(ACT_URDF).getroot().iter("joint")
            if joint.find("limit") is not None}


@pytest.mark.parametrize("joint", sorted(OFFICIAL_RANGE))
def test_act_mjcf_range_and_ctrlrange_are_the_official_strings(joint):
    assert mjcf_joints()[joint].get("range") == OFFICIAL_RANGE[joint]
    assert mjcf_actuators()[joint].get("ctrlrange") == OFFICIAL_CTRL[joint]


@pytest.mark.parametrize("joint", sorted(OFFICIAL_RANGE))
def test_act_urdf_limits_are_the_official_strings(joint):
    limit = urdf_limits()[joint]
    lower, upper = OFFICIAL_RANGE[joint].split()
    assert (limit.get("lower"), limit.get("upper")) == (lower, upper)


@pytest.mark.parametrize("joint", ["1", "2", "3", "4", "5", "6"])
def test_urdf_limits_equal_mjcf_ranges_and_ctrlrange_stays_inside_them(joint):
    lower, upper = numbers(mjcf_joints()[joint].get("range"))
    limit = urdf_limits()[joint]
    assert (float(limit.get("lower")), float(limit.get("upper"))) == pytest.approx((lower, upper), abs=1e-5)
    low, high = numbers(mjcf_actuators()[joint].get("ctrlrange"))
    # official actuator strings are rounded: they may overhang the joint range by their rounding only
    assert lower - 1e-5 <= low and high <= upper + 1e-5


@pytest.mark.parametrize("joint", sorted(UNCHANGED_RANGE))
def test_the_other_joint_ranges_are_unchanged(joint):
    assert numbers(mjcf_joints()[joint].get("range")) == UNCHANGED_RANGE[joint]


@pytest.mark.parametrize("relative", sorted(MAIN_SHA))
def test_the_main_model_files_are_byte_identical(relative):
    assert hashlib.sha256((PACKAGE / relative).read_bytes()).hexdigest() == MAIN_SHA[relative]


def test_robot_parameters_still_equal_the_official_sts3215_class_and_neck_stays_custom():
    import mujoco
    model = mujoco.MjModel.from_xml_path(str(PACKAGE / "assets/mujoco/act/scene.xml"))
    for name in "123456":
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        dof = int(model.jnt_dofadr[joint])
        assert (model.dof_damping[dof], model.dof_frictionloss[dof], model.dof_armature[dof]) == (0.60, 0.052, 0.028)
        actuator = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        assert model.actuator_gainprm[actuator][0] == 998.22 and model.actuator_biasprm[actuator][2] == -2.731
        assert tuple(model.actuator_forcerange[actuator]) == (-3.35, 3.35)
    neck = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "neck_yaw_joint")
    dof = int(model.jnt_dofadr[neck])
    assert (model.dof_damping[dof], model.dof_frictionloss[dof], model.dof_armature[dof]) == (0.05, 0.0, 0.001)


def act_range():
    return {name: numbers(item.get("range")) for name, item in mjcf_joints().items() if name in tuple("123456")}


def test_every_config_joint_vector_lies_inside_the_act_range():
    ranges = [act_range()[name] for name in "123456"]
    seen = 0

    def walk(value, path, where):
        nonlocal seen
        if isinstance(value, list):
            if len(value) in (5, 6) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value):
                seen += 1
                for index, number in enumerate(value):
                    low, high = ranges[index]
                    assert low <= number <= high, (where, path, index + 1, number)
            else:
                for index, item in enumerate(value):
                    walk(item, f"{path}[{index}]", where)
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}/{key}", where)

    for pattern in ("config/**/*.yaml", "config/**/*.json"):
        for name in sorted(glob.glob(str(PACKAGE / pattern), recursive=True)):
            try:
                text = Path(name).read_text()
                document = yaml.safe_load(text) if name.endswith("yaml") else json.loads(text)
            except Exception:
                continue
            walk(document, "", name)
    # vacuity guard: 134 vectors remain after the CP-3529 retirement of the Task 6 profiles (it was 200+ with them)
    assert seen >= 100


def test_every_keyframe_and_the_srdf_home_lie_inside_the_act_range():
    ranges = act_range()
    for scene in ("assets/mujoco/act/scene.xml",):
        for key in ET.parse(PACKAGE / scene).getroot().iter("key"):
            values = numbers(key.get("qpos"))[:6]
            for index, number in enumerate(values):
                low, high = ranges["123456"[index]]
                assert low <= number <= high, (scene, key.get("name"), index + 1)
    home = {item.get("name"): float(item.get("value")) for group in ET.parse(PACKAGE / "config/mujoco/so101.srdf").getroot().iter("group_state")
            for item in group.iter("joint")}
    for name, value in home.items():
        low, high = ranges[name]
        assert low <= value <= high, ("srdf home", name)


def test_act_and_main_joint_limit_tables_are_selected_by_profile():
    from so101_demo.act.execution import bounded_positions
    from so101_demo.act.joints import ACT_JOINT_LIMITS, JOINT_LIMITS, joint_limits_for
    assert JOINT_LIMITS["3"] == (-1.74533, 1.5708) and JOINT_LIMITS["6"] == (-0.059600220867817, 1.74533)  # main, unchanged
    assert joint_limits_for("main") is JOINT_LIMITS and joint_limits_for("act") is ACT_JOINT_LIMITS
    ranges = act_range()
    for name in "123456":
        assert ACT_JOINT_LIMITS[name] == pytest.approx(ranges[name], abs=1e-5), name
    with pytest.raises(ValueError):
        joint_limits_for("other")
    elbow_high = [0.0, 0.0, 1.6, 0.0, 0.0, 0.0]          # inside the ACT elbow range, outside main's
    assert bounded_positions(elbow_high) == tuple(elbow_high)
    with pytest.raises(ValueError, match="JOINT_LIMIT_INVALID"):
        bounded_positions(elbow_high, profile="main")
    gripper_low = [0.0, 0.0, 0.0, 0.0, 0.0, -0.12]       # ACT only
    assert bounded_positions(gripper_low) == tuple(gripper_low)
    with pytest.raises(ValueError, match="JOINT_LIMIT_INVALID"):
        bounded_positions(gripper_low, profile="main")
    with pytest.raises(ValueError, match="JOINT_LIMIT_INVALID"):
        bounded_positions([0.0, 0.0, 1.7, 0.0, 0.0, 0.0])  # outside both
    from so101_demo.backends.mujoco.client import JointResetOverride
    JointResetOverride("6", -0.12)                         # ACT reset client defaults to the ACT table
    with pytest.raises(ValueError, match="out of bounds"):
        JointResetOverride("6", -0.12, profile="main")
