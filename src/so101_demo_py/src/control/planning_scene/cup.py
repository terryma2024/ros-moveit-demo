"""Canonical dynamic Planning Scene geometry for the plastic cup."""

from __future__ import annotations

import math


def _multiply(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    x1, y1, z1, w1 = first
    x2, y2, z2, w2 = second
    return (
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    )


def _rotate(
    orientation: tuple[float, float, float, float],
    value: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z, w = orientation
    vx, vy, vz = value
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + y * tz - z * ty,
        vy + w * ty + z * tx - x * tz,
        vz + w * tz + x * ty - y * tx,
    )


def make_cup_collision_object(
    position: tuple[float, float, float],
    orientation: tuple[float, float, float, float],
):
    from geometry_msgs.msg import Pose
    from moveit_msgs.msg import CollisionObject
    from shape_msgs.msg import SolidPrimitive

    result = CollisionObject()
    result.header.frame_id = "world"
    result.id = "plastic_cup"
    result.operation = CollisionObject.ADD
    walls = (
        (0.0, 0.039, -0.0),
        (0.0195, 0.033775, -math.pi / 6.0),
        (0.033775, 0.0195, -math.pi / 3.0),
        (0.039, 0.0, -math.pi / 2.0),
        (0.033775, -0.0195, -2.0 * math.pi / 3.0),
        (0.0195, -0.033775, -5.0 * math.pi / 6.0),
        (0.0, -0.039, math.pi),
        (-0.0195, -0.033775, 5.0 * math.pi / 6.0),
        (-0.033775, -0.0195, 2.0 * math.pi / 3.0),
        (-0.039, 0.0, math.pi / 2.0),
        (-0.033775, 0.0195, math.pi / 3.0),
        (-0.0195, 0.033775, math.pi / 6.0),
    )
    for x, y, yaw in walls:
        offset = _rotate(orientation, (x, y, 0.001))
        local = (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))
        composed = _multiply(orientation, local)
        pose = Pose()
        pose.position.x = position[0] + offset[0]
        pose.position.y = position[1] + offset[1]
        pose.position.z = position[2] + offset[2]
        pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w = composed
        result.primitives.append(
            SolidPrimitive(type=SolidPrimitive.BOX, dimensions=[0.020705524, 0.002, 0.088])
        )
        result.primitive_poses.append(pose)
    bottom = _rotate(orientation, (0.0, 0.0, -0.044))
    pose = Pose()
    pose.position.x = position[0] + bottom[0]
    pose.position.y = position[1] + bottom[1]
    pose.position.z = position[2] + bottom[2]
    pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w = orientation
    result.primitives.append(
        SolidPrimitive(type=SolidPrimitive.CYLINDER, dimensions=[0.002, 0.040])
    )
    result.primitive_poses.append(pose)
    return result
