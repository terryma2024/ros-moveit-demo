"""Immutable robot state evidence used by planning boundaries."""

from dataclasses import dataclass

ARM_JOINTS = ("1", "2", "3", "4", "5")
GRIPPER_JOINT = "6"
ALL_JOINTS = ARM_JOINTS + (GRIPPER_JOINT,)
TCP_LINK = "so101_tcp"


@dataclass(frozen=True, slots=True)
class RobotStateEvidence:
    joint_names: tuple[str, ...]
    positions: tuple[float, ...]
    velocities: tuple[float, ...]
    tcp_position: tuple[float, float, float]
