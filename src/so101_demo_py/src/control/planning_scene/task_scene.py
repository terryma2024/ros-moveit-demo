"""Manifest-driven MoveIt task-scene messages, read-back, and ROS adapter."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from ...core.task_geometry import Pose7, TaskGeometry, TaskGeometryObject
from ...ports.planning_scene import SceneCommandReceipt


def _pose(value: Pose7):
    from geometry_msgs.msg import Pose

    result = Pose()
    (
        result.position.x,
        result.position.y,
        result.position.z,
        result.orientation.x,
        result.orientation.y,
        result.orientation.z,
        result.orientation.w,
    ) = value.values
    return result


def _collision_object(value: TaskGeometryObject, frame_id: str = "world"):
    from moveit_msgs.msg import CollisionObject
    from shape_msgs.msg import SolidPrimitive

    result = CollisionObject()
    result.header.frame_id = frame_id
    result.id = value.object_id
    result.pose = _pose(value.pose)
    result.operation = CollisionObject.ADD
    for primitive in value.primitives:
        primitive_type = (
            SolidPrimitive.BOX if primitive.kind == "box" else SolidPrimitive.CYLINDER
        )
        result.primitives.append(
            SolidPrimitive(type=primitive_type, dimensions=list(primitive.dimensions))
        )
        result.primitive_poses.append(_pose(primitive.pose))
    return result


def make_task_scene(geometry: TaskGeometry):
    from moveit_msgs.msg import (
        AttachedCollisionObject,
        CollisionObject,
        ObjectColor,
        PlanningScene,
    )
    from std_msgs.msg import ColorRGBA

    scene = PlanningScene()
    scene.is_diff = True
    scene.robot_state.is_diff = True
    stale_cup = AttachedCollisionObject()
    stale_cup.object.id = "plastic_cup"
    stale_cup.object.operation = CollisionObject.REMOVE
    scene.robot_state.attached_collision_objects = [stale_cup]
    scene.world.collision_objects = [
        _collision_object(value, geometry.frame_id) for value in geometry.objects
    ]
    scene.object_colors = [
        ObjectColor(
            id=value.object_id,
            color=ColorRGBA(
                r=value.color_rgba[0],
                g=value.color_rgba[1],
                b=value.color_rgba[2],
                a=value.color_rgba[3],
            ),
        )
        for value in geometry.objects
    ]
    return scene


@dataclass(frozen=True, slots=True)
class SceneVerification:
    success: bool
    failure_code: str | None
    evidence: dict[str, object]


def _pose_values(value) -> tuple[float, ...]:
    return (
        float(value.position.x),
        float(value.position.y),
        float(value.position.z),
        float(value.orientation.x),
        float(value.orientation.y),
        float(value.orientation.z),
        float(value.orientation.w),
    )


def _close(expected: tuple[float, ...], actual: tuple[float, ...]) -> bool:
    return len(expected) == len(actual) and all(
        math.isclose(left, right, rel_tol=0.0, abs_tol=1e-6)
        for left, right in zip(expected, actual, strict=True)
    )


def _pose_close(expected: tuple[float, ...], actual: tuple[float, ...]) -> bool:
    if len(expected) != 7 or len(actual) != 7:
        return False
    if not _close(expected[:3], actual[:3]):
        return False
    expected_orientation = expected[3:]
    actual_orientation = actual[3:]
    return _close(expected_orientation, actual_orientation) or _close(
        expected_orientation,
        tuple(-value for value in actual_orientation),
    )


def verify_task_scene(
    scene,
    geometry: TaskGeometry,
    *,
    expected_cup_attachment: str | None = None,
) -> SceneVerification:
    """Compare complete MoveIt read-back with the canonical geometry contract."""

    world = {value.id: value for value in scene.world.collision_objects}
    attached = {
        value.object.id: value for value in scene.robot_state.attached_collision_objects
    }
    colors = {
        value.id: (
            float(value.color.r),
            float(value.color.g),
            float(value.color.b),
            float(value.color.a),
        )
        for value in scene.object_colors
    }
    expected_world = {"table", "pedestal", "plastic_cup"}
    expected_attached: dict[str, str] = {}
    if expected_cup_attachment is not None:
        expected_world.remove("plastic_cup")
        expected_attached["plastic_cup"] = expected_cup_attachment
    mismatches: list[str] = []
    if set(world) != expected_world:
        mismatches.append("world_membership")
    if {name: value.link_name for name, value in attached.items()} != expected_attached:
        mismatches.append("attachment")

    primitive_counts: dict[str, int] = {}
    for expected in geometry.objects:
        observed = world.get(expected.object_id)
        if observed is None and expected.object_id in attached:
            observed = attached[expected.object_id].object
        if observed is None:
            continue
        primitive_counts[expected.object_id] = len(observed.primitives)
        if observed.header.frame_id != geometry.frame_id:
            mismatches.append(f"{expected.object_id}.frame")
        if not _pose_close(expected.pose.values, _pose_values(observed.pose)):
            mismatches.append(f"{expected.object_id}.pose")
        if len(observed.primitives) != len(expected.primitives):
            mismatches.append(f"{expected.object_id}.primitive_count")
            continue
        if len(observed.primitive_poses) != len(expected.primitives):
            mismatches.append(f"{expected.object_id}.primitive_pose_count")
            continue
        for index, primitive in enumerate(expected.primitives):
            actual_primitive = observed.primitives[index]
            expected_type = 1 if primitive.kind == "box" else 3
            if actual_primitive.type != expected_type:
                mismatches.append(f"{expected.object_id}.primitive[{index}].type")
            if not _close(primitive.dimensions, tuple(actual_primitive.dimensions)):
                mismatches.append(f"{expected.object_id}.primitive[{index}].dimensions")
            if not _pose_close(
                primitive.pose.values,
                _pose_values(observed.primitive_poses[index]),
            ):
                mismatches.append(f"{expected.object_id}.primitive[{index}].pose")
        if expected.object_id not in colors or not _close(
            expected.color_rgba, colors[expected.object_id]
        ):
            mismatches.append(f"{expected.object_id}.color")

    evidence: dict[str, object] = {
        "world_ids": sorted(world),
        "attached_ids": sorted(attached),
        "attached_links": dict(sorted(expected_attached.items())),
        "primitive_counts": primitive_counts,
        "mismatches": mismatches,
    }
    return SceneVerification(
        success=not mismatches,
        failure_code=None if not mismatches else "SCENE_READBACK_MISMATCH",
        evidence=evidence,
    )


class RosTaskScenePort:
    """Bounded `/apply_planning_scene` plus `/get_planning_scene` adapter."""

    def __init__(self, node: Any, backend: str, timeout_s: float) -> None:
        from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene

        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")
        self._node = node
        self._backend = backend
        self._timeout_s = timeout_s
        self._apply_client = node.create_client(
            ApplyPlanningScene, "/apply_planning_scene"
        )
        self._get_client = node.create_client(GetPlanningScene, "/get_planning_scene")

    def _receipt(
        self,
        phase: str,
        success: bool,
        failure_code: str | None,
        evidence: dict[str, object],
    ) -> SceneCommandReceipt:
        return SceneCommandReceipt(
            backend=self._backend,
            phase=phase,
            success=success,
            failure_code=failure_code,
            evidence=evidence,
        )

    def _wait_service(self, client: Any, service_name: str) -> SceneCommandReceipt | None:
        if client.wait_for_service(timeout_sec=self._timeout_s):
            return None
        return self._receipt(
            "READINESS",
            False,
            "SCENE_SERVICE_UNAVAILABLE",
            {"service": service_name, "timeout_s": self._timeout_s},
        )

    def _call(self, client: Any, request: Any, phase: str) -> Any:
        import rclpy

        future = client.call_async(request)
        rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout_s)
        if not future.done() or future.result() is None:
            return self._receipt(
                phase,
                False,
                "SCENE_SERVICE_TIMEOUT",
                {"timeout_s": self._timeout_s},
            )
        return future.result()

    def _apply(self, scene, phase: str) -> SceneCommandReceipt:
        from moveit_msgs.srv import ApplyPlanningScene

        unavailable = self._wait_service(self._apply_client, "/apply_planning_scene")
        if unavailable is not None:
            return unavailable
        response = self._call(
            self._apply_client,
            ApplyPlanningScene.Request(scene=scene),
            phase,
        )
        if isinstance(response, SceneCommandReceipt):
            return response
        if not response.success:
            return self._receipt(phase, False, "SCENE_APPLY_FAILED", {})
        return self._receipt(phase, True, None, {"applied": True})

    def _observe(self):
        from moveit_msgs.msg import PlanningSceneComponents
        from moveit_msgs.srv import GetPlanningScene

        unavailable = self._wait_service(self._get_client, "/get_planning_scene")
        if unavailable is not None:
            return unavailable
        request = GetPlanningScene.Request()
        request.components.components = (
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
            | PlanningSceneComponents.OBJECT_COLORS
        )
        return self._call(self._get_client, request, "READ_BACK")

    def apply_task_scene(self, geometry: TaskGeometry) -> SceneCommandReceipt:
        return self._apply(make_task_scene(geometry), "APPLY")

    def observe_task_scene(
        self,
        geometry: TaskGeometry,
        *,
        expected_cup_attachment: str | None,
    ) -> SceneCommandReceipt:
        deadline = time.monotonic() + self._timeout_s
        latest: SceneVerification | None = None
        while time.monotonic() < deadline:
            response = self._observe()
            if isinstance(response, SceneCommandReceipt):
                return response
            latest = verify_task_scene(
                response.scene,
                geometry,
                expected_cup_attachment=expected_cup_attachment,
            )
            if latest.success:
                return self._receipt("READ_BACK", True, None, latest.evidence)
            time.sleep(0.05)
        evidence = latest.evidence if latest is not None else {}
        return self._receipt(
            "READ_BACK", False, "SCENE_READBACK_MISMATCH", evidence
        )

    def attach_task_object(
        self,
        geometry: TaskGeometry,
        object_id: str,
        link_name: str,
    ) -> SceneCommandReceipt:
        from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene

        target = _collision_object(geometry.object(object_id), geometry.frame_id)
        attached = AttachedCollisionObject()
        attached.link_name = link_name
        attached.touch_links = ["gripper", "jaw"]
        attached.object = target
        remove = CollisionObject()
        remove.header.frame_id = geometry.frame_id
        remove.id = object_id
        remove.operation = CollisionObject.REMOVE
        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [attached]
        scene.world.collision_objects = [remove]
        return self._apply(scene, "ATTACH")

    def detach_task_object(
        self,
        geometry: TaskGeometry,
        object_id: str,
    ) -> SceneCommandReceipt:
        from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene

        remove = AttachedCollisionObject()
        remove.object.id = object_id
        remove.object.operation = CollisionObject.REMOVE
        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [remove]
        scene.world.collision_objects = [
            _collision_object(geometry.object(object_id), geometry.frame_id)
        ]
        return self._apply(scene, "DETACH")
