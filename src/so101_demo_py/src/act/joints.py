"""Explicit measured-joint ordering and simulator limits in radians."""

from math import isfinite

ARM_JOINTS = tuple(str(index) for index in range(1, 7))
ACT_JOINTS = ARM_JOINTS + ("neck_yaw_joint",)


def act_joints_for(rig) -> tuple:
    """The measured joints of the ACT station of a camera rig: the six arm joints, and the neck yaw only for a rig with a neck."""
    return ACT_JOINTS if rig.has_neck else ARM_JOINTS
# main profile: the limits of the original assets/mujoco/so101.xml (unchanged)
JOINT_LIMITS = dict(zip(ARM_JOINTS, ((-1.91986, 1.91986),
    (-1.74533, 1.74533), (-1.74533, 1.5708), (-1.65806, 1.65806),
    (-2.79253, 2.79253), (-0.059600220867817, 1.74533)), strict=True))
# ACT profile: the official SO-101 ranges that assets/mujoco/act/so101.xml carries (R11): elbow, wrist_roll, gripper
ACT_JOINT_LIMITS = dict(zip(ARM_JOINTS, ((-1.91986, 1.91986),
    (-1.74533, 1.74533), (-1.69, 1.69), (-1.65806, 1.65806),
    (-2.7438472969992493, 2.841206309382605), (-0.17453297762778586, 1.7453291995659765)), strict=True))


def joint_limits_for(profile):
    """The joint limit table of a model profile: "act" (the ACT scene) or "main" (the original pick-place)."""

    if profile == "act":
        return ACT_JOINT_LIMITS
    if profile == "main":
        return JOINT_LIMITS
    raise ValueError("JOINT_PROFILE_INVALID")


def ordered_positions(values, names):
    if not names or len(set(names)) != len(names) or any(name not in values for name in names):
        raise ValueError("JOINT_MAPPING_INVALID")
    result = tuple(values[name] for name in names)
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not isfinite(value) for value in result):
        raise ValueError("JOINT_MAPPING_INVALID")
    return tuple(float(value) for value in result)
