"""Explicit measured-joint ordering and simulator limits in radians."""

from math import isfinite

ARM_JOINTS = tuple(str(index) for index in range(1, 7))
ACT_JOINTS = ARM_JOINTS + ("neck_yaw_joint",)
JOINT_LIMITS = dict(zip(ARM_JOINTS, ((-1.91986, 1.91986),
    (-1.74533, 1.74533), (-1.74533, 1.5708), (-1.65806, 1.65806),
    (-2.79253, 2.79253), (-0.059600220867817, 1.74533)), strict=True))


def ordered_positions(values, names):
    if not names or len(set(names)) != len(names) or any(name not in values for name in names):
        raise ValueError("JOINT_MAPPING_INVALID")
    result = tuple(values[name] for name in names)
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not isfinite(value) for value in result):
        raise ValueError("JOINT_MAPPING_INVALID")
    return tuple(float(value) for value in result)
