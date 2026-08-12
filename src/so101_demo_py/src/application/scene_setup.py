"""Install the MuJoCo task geometry into MoveIt's live Planning Scene."""

import math
import time
from collections.abc import Sequence

REQUIRED_WORLD_OBJECTS = frozenset({"table", "pedestal", "plastic_cup"})
EXPECTED_PRIMITIVE_COUNTS = {"table": 1, "pedestal": 1, "plastic_cup": 13}


def _pose(x: float, y: float, z: float, yaw: float = 0.0):
    from geometry_msgs.msg import Pose

    value = Pose()
    value.position.x = x
    value.position.y = y
    value.position.z = z
    value.orientation.z = math.sin(yaw / 2.0)
    value.orientation.w = math.cos(yaw / 2.0)
    return value


def _box(x: float, y: float, z: float):
    from shape_msgs.msg import SolidPrimitive

    return SolidPrimitive(type=SolidPrimitive.BOX, dimensions=[x, y, z])


def _world_box(object_id: str, dimensions: tuple[float, float, float], at):
    from moveit_msgs.msg import CollisionObject

    value = CollisionObject()
    value.header.frame_id = "world"
    value.id = object_id
    value.operation = CollisionObject.ADD
    value.primitives = [_box(*dimensions)]
    value.primitive_poses = [at]
    return value


def _plastic_cup():
    from moveit_msgs.msg import CollisionObject
    from shape_msgs.msg import SolidPrimitive

    cup_x, cup_y, cup_z = 0.02, -0.28, 0.165
    walls = (
        (0.0, 0.039, 0.0),
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
    result = CollisionObject()
    result.header.frame_id = "world"
    result.id = "plastic_cup"
    result.operation = CollisionObject.ADD
    for x, y, yaw in walls:
        result.primitives.append(_box(0.020705524, 0.002, 0.088))
        result.primitive_poses.append(_pose(cup_x + x, cup_y + y, cup_z + 0.001, yaw))
    bottom = SolidPrimitive(type=SolidPrimitive.CYLINDER, dimensions=[0.002, 0.040])
    result.primitives.append(bottom)
    result.primitive_poses.append(_pose(cup_x, cup_y, cup_z - 0.044))
    return result


def task_collision_objects() -> list:
    """Return exact full-size SDF/MJCF collision geometry in the world frame."""

    return [
        _world_box("table", (0.50, 0.60, 0.04), _pose(0.0, -0.20, 0.10)),
        _world_box("pedestal", (0.18, 0.18, 0.10), _pose(0.0, 0.0, 0.17)),
        _plastic_cup(),
    ]


def task_object_colors() -> list:
    from moveit_msgs.msg import ObjectColor
    from std_msgs.msg import ColorRGBA

    values = {
        "table": (0.36, 0.24, 0.14, 1.0),
        "pedestal": (0.30, 0.30, 0.32, 1.0),
        "plastic_cup": (1.0, 0.55, 0.12, 1.0),
    }
    return [
        ObjectColor(id=object_id, color=ColorRGBA(r=r, g=g, b=b, a=a))
        for object_id, (r, g, b, a) in values.items()
    ]


def make_task_scene():
    from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene

    scene = PlanningScene()
    scene.is_diff = True
    scene.robot_state.is_diff = True
    stale_cup = AttachedCollisionObject()
    stale_cup.object.id = "plastic_cup"
    stale_cup.object.operation = CollisionObject.REMOVE
    scene.robot_state.attached_collision_objects = [stale_cup]
    scene.world.collision_objects = task_collision_objects()
    scene.object_colors = task_object_colors()
    return scene


def scene_contains_required_objects(object_ids: Sequence[str]) -> bool:
    return REQUIRED_WORLD_OBJECTS <= set(object_ids)


def task_scene_readback(scene) -> tuple[dict[str, int], set[str]]:
    """Summarize the collision geometry and colors returned by MoveIt."""

    primitive_counts = {
        collision_object.id: len(collision_object.primitives)
        for collision_object in scene.world.collision_objects
    }
    color_ids = {object_color.id for object_color in scene.object_colors}
    return primitive_counts, color_ids


def scene_matches_task_geometry(scene) -> bool:
    """Require the complete task geometry, not merely three matching names."""

    primitive_counts, color_ids = task_scene_readback(scene)
    return (
        all(
            primitive_counts.get(object_id) == expected_count
            for object_id, expected_count in EXPECTED_PRIMITIVE_COUNTS.items()
        )
        and REQUIRED_WORLD_OBJECTS <= color_ids
    )


def main() -> int:
    import rclpy
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene

    rclpy.init()
    node = rclpy.create_node("so101_mujoco_scene_setup")
    try:
        timeout_s = float(node.declare_parameter("readiness_timeout_s", 30.0).value)
        if timeout_s <= 0.0:
            raise RuntimeError("readiness_timeout_s must be positive")
        deadline = time.monotonic() + timeout_s
        apply_client = node.create_client(ApplyPlanningScene, "/apply_planning_scene")
        get_client = node.create_client(GetPlanningScene, "/get_planning_scene")
        if not apply_client.wait_for_service(timeout_sec=max(0.0, deadline - time.monotonic())):
            raise RuntimeError("/apply_planning_scene unavailable")
        if not get_client.wait_for_service(timeout_sec=max(0.0, deadline - time.monotonic())):
            raise RuntimeError("/get_planning_scene unavailable")
        future = apply_client.call_async(ApplyPlanningScene.Request(scene=make_task_scene()))
        rclpy.spin_until_future_complete(
            node,
            future,
            timeout_sec=max(0.0, deadline - time.monotonic()),
        )
        if not future.done() or future.result() is None or not future.result().success:
            raise RuntimeError("ApplyPlanningScene failed")
        query = GetPlanningScene.Request()
        query.components.components = (
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.OBJECT_COLORS
        )
        last_readback = ({}, set())
        while time.monotonic() < deadline:
            observed = get_client.call_async(query)
            rclpy.spin_until_future_complete(
                node,
                observed,
                timeout_sec=max(0.0, deadline - time.monotonic()),
            )
            if observed.done() and observed.result() is not None:
                scene = observed.result().scene
                last_readback = task_scene_readback(scene)
                if scene_matches_task_geometry(scene):
                    primitive_counts, color_ids = last_readback
                    print(
                        "SCENE_SETUP_OK "
                        f"primitive_counts={dict(sorted(primitive_counts.items()))} "
                        f"colors={sorted(color_ids)}",
                        flush=True,
                    )
                    return 0
            rclpy.spin_once(node, timeout_sec=0.05)
        primitive_counts, color_ids = last_readback
        raise RuntimeError(
            "Planning Scene geometry readback mismatch: "
            f"primitive_counts={dict(sorted(primitive_counts.items()))}, "
            f"colors={sorted(color_ids)}"
        )
    finally:
        node.destroy_node()
        rclpy.shutdown()
