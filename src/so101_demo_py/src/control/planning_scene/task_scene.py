"""Manifest-driven MoveIt task-scene messages, read-back, and ROS adapter."""

from __future__ import annotations

import math
import time
import copy
import uuid
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


def make_plain_attach_scene():
    """The one ATTACH request the Teacher issues, whatever the data side can or cannot offer.

    It names the cup and the gripper links and carries no geometry: MoveIt attaches the cup it already holds. Any
    association or source evidence about the attachment is recorded data-side after the fact and never changes this
    request.
    """
    from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene

    attached = AttachedCollisionObject()
    attached.link_name = "gripper"
    attached.object.id = "plastic_cup"
    attached.object.operation = CollisionObject.ADD
    attached.touch_links = ["gripper", "jaw"]
    scene = PlanningScene()
    scene.is_diff = True
    scene.robot_state.is_diff = True
    scene.robot_state.attached_collision_objects = [attached]
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


def normalized_scene_geometry(scene) -> dict:
    """Retain actual geometry, including duplicate objects and unsupported geometry kinds."""
    from rosidl_runtime_py.convert import message_to_ordereddict

    def collision(value):
        return {
            "id": value.id, "frame_id": value.header.frame_id,
            "pose": list(_pose_values(value.pose)),
            "operation": (int.from_bytes(value.operation, "little")
                          if isinstance(value.operation, bytes) else int(value.operation)),
            "primitives": [{"type": int(item.type), "dimensions": list(item.dimensions)}
                           for item in value.primitives],
            "primitive_poses": [list(_pose_values(item)) for item in value.primitive_poses],
            "meshes": [dict(message_to_ordereddict(item)) for item in value.meshes],
            "mesh_poses": [list(_pose_values(item)) for item in value.mesh_poses],
            "planes": [dict(message_to_ordereddict(item)) for item in value.planes],
            "plane_poses": [list(_pose_values(item)) for item in value.plane_poses],
            "subframe_names": list(value.subframe_names),
            "subframe_poses": [list(_pose_values(item)) for item in value.subframe_poses],
        }

    return {
        "world": sorted([collision(item) for item in scene.world.collision_objects],
                        key=lambda item: item["id"]),
        "attached": sorted([{"link_name": item.link_name, "touch_links": list(item.touch_links),
                             "object": collision(item.object)}
                            for item in scene.robot_state.attached_collision_objects],
                           key=lambda item: item["object"]["id"]),
        "colors": sorted([{"id": item.id, "rgba": [float(item.color.r), float(item.color.g),
                                                    float(item.color.b), float(item.color.a)]}
                          for item in scene.object_colors], key=lambda item: item["id"]),
    }


#: What the `initial` source alignment asserts: exactly what the worker's reset and cleanup guarantee before the Teacher
#: starts, which is the initial gate of `parallel_ros_runtime` (`POINT_INITIAL_GATE`, the scene read of
#: ROBOT_STATE_ATTACHED_OBJECTS): NO attached collision object. World objects are not guaranteed either way before the
#: Teacher's SETUP writes the task scene, so they are recorded (audit) and never required.
PRE_SETUP_EXPECTATION = {"attached": []}


def verify_pre_setup_scene(scene) -> SceneVerification:
    """The pre-SETUP scene: no attached collision object (a residual attachment is a mismatch, never passed silently).

    Same evidence shape as `verify_task_scene`; the observed world objects and colours are recorded in `observed_geometry`."""

    attached = sorted(value.object.id for value in scene.robot_state.attached_collision_objects)
    mismatches = ["attached_not_empty"] if attached else []
    evidence = {
        "world_ids": sorted(value.id for value in scene.world.collision_objects),
        "attached_ids": attached, "attached_links": {}, "primitive_counts": {}, "mismatches": mismatches,
        "observed_geometry": normalized_scene_geometry(scene)}
    return SceneVerification(success=not mismatches, failure_code=None if not mismatches else "SCENE_READBACK_MISMATCH",
                             evidence=evidence)


def _cup_local_pose_audit(expected: Pose7 | None, observed: tuple[float, ...] | None) -> dict[str, object]:
    """Audit-only comparison of the source-derived and the observed attached cup pose; it never refuses."""

    result: dict[str, object] = {
        "refuses": False, "reason": None, "translation_delta_m": None, "rotation_delta_rad": None,
        "expected_pose": None if expected is None else list(expected.values),
        "observed_pose": None if observed is None else list(observed),
    }
    if observed is None:
        result["reason"] = "OBSERVED_CUP_NOT_PRESENT"
    elif expected is None:
        result["reason"] = "SOURCE_LOCAL_POSE_NOT_PROVIDED"
    else:
        translation = math.dist(expected.values[:3], observed[:3])
        left, right = expected.values[3:], observed[3:]
        norms = math.hypot(*left) * math.hypot(*right)
        dot = abs(sum(a * b for a, b in zip(left, right, strict=True))) / norms if norms > 0.0 else 0.0
        result["translation_delta_m"] = translation
        result["rotation_delta_rad"] = 2.0 * math.acos(min(1.0, dot))
        if not (math.isfinite(translation) and math.isfinite(result["rotation_delta_rad"])):
            result.update(translation_delta_m=None, rotation_delta_rad=None, reason="POSE_DELTA_NOT_FINITE")
    return result


def _cup_world_pose_tolerance(expected: Pose7, observed: tuple[float, ...],
                              tolerance: tuple[float, float]) -> dict[str, object]:
    """The world cup's pose delta against the frozen scene tolerances; a non-finite or malformed pose is outside them."""

    audit = _cup_local_pose_audit(expected, observed if len(observed) == 7 else None)
    translation, rotation = audit["translation_delta_m"], audit["rotation_delta_rad"]
    within = (translation is not None and rotation is not None
              and translation <= tolerance[0] and rotation <= tolerance[1])
    return {"within": bool(within), "reason": audit["reason"], "position_tolerance_m": tolerance[0],
            "orientation_tolerance_rad": tolerance[1], "translation_delta_m": translation,
            "rotation_delta_rad": rotation, "expected_pose": audit["expected_pose"],
            "observed_pose": audit["observed_pose"]}


def verify_task_scene(
    scene,
    geometry: TaskGeometry,
    *,
    expected_cup_attachment: str | None = None,
    expected_cup_local_pose: Pose7 | None = None,
    expected_touch_links: tuple[str, ...] | None = None,
    cup_local_pose_audit_only: bool = False,
    cup_world_pose_audit_only: bool = False,
    cup_world_pose_tolerance: tuple[float, float] | None = None,
) -> SceneVerification:
    """Compare complete MoveIt read-back with the canonical geometry contract.

    `cup_local_pose_audit_only` (Teacher broker, attached phases): the attached cup's local pose is MoveIt's own after a
    plain attach, so it is reported in `evidence["cup_local_pose_audit"]` and never added to `mismatches`. Attachment
    link, touch links, header frame, primitives, colors, duplicates and every other object stay fully checked. It needs
    `expected_cup_attachment`; the default (False) keeps the strict comparison for every other caller.

    `cup_world_pose_audit_only` (Recorder, initial association): nothing writes the cup's source pose at the start of a
    recording, so the world cup's measured pose delta against the physics-derived pose is reported in
    `evidence["cup_world_pose_audit"]` and never added to `mismatches`. Membership, frame, primitives, colors,
    duplicates and every other object stay fully checked. It cannot be combined with an attachment.

    `cup_world_pose_tolerance=(position_m, orientation_rad)` (Teacher broker, per-phase detached proof): the world cup's
    pose is compared with the physics-derived pose within the Teacher's own frozen scene tolerances instead of 1e-6
    (position distance <= position_m, orientation angle <= orientation_rad, quaternion sign-insensitive). The exact delta
    and both poses are reported in `evidence["cup_world_pose_tolerance"]`. Every other comparison stays strict, and the
    default (None) keeps the strict comparison for every other caller. Both values must be finite and positive.
    """

    if cup_local_pose_audit_only and expected_cup_attachment is None:
        raise ValueError("cup_local_pose_audit_only requires expected_cup_attachment")
    if cup_world_pose_audit_only and (expected_cup_attachment is not None or cup_local_pose_audit_only):
        raise ValueError("cup_world_pose_audit_only is for a cup that is a world object")
    if cup_world_pose_tolerance is not None:
        if (expected_cup_attachment is not None or cup_local_pose_audit_only or cup_world_pose_audit_only
                or not isinstance(cup_world_pose_tolerance, (tuple, list)) or len(cup_world_pose_tolerance) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0.0
                       for value in cup_world_pose_tolerance)):
            raise ValueError("cup_world_pose_tolerance is two finite positive numbers for a world cup")

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
    cup_audit: dict[str, object] | None = None
    cup_world_audit: dict[str, object] | None = None
    cup_tolerance_evidence: dict[str, object] | None = None
    if len(world) != len(scene.world.collision_objects):
        mismatches.append("world_duplicate_ids")
    if len(attached) != len(scene.robot_state.attached_collision_objects):
        mismatches.append("attached_duplicate_ids")
    if len(colors) != len(scene.object_colors):
        mismatches.append("color_duplicate_ids")
    if set(world) != expected_world:
        mismatches.append("world_membership")
    if set(colors) != set(geometry.object_ids):
        mismatches.append("color_membership")
    if {name: value.link_name for name, value in attached.items()} != expected_attached:
        mismatches.append("attachment")
    if expected_cup_local_pose is not None and expected_cup_attachment is None:
        mismatches.append("attachment_pose_without_link")
    if expected_touch_links is not None:
        cup_attachment = attached.get("plastic_cup")
        if (cup_attachment is None or list(cup_attachment.touch_links) != list(expected_touch_links)):
            mismatches.append("attachment_touch_links")

    primitive_counts: dict[str, int] = {}
    for expected in geometry.objects:
        observed = world.get(expected.object_id)
        if observed is None and expected.object_id in attached:
            observed = attached[expected.object_id].object
        if observed is None:
            continue
        primitive_counts[expected.object_id] = len(observed.primitives)
        is_cup = expected.object_id == "plastic_cup"
        local = is_cup and expected_cup_local_pose is not None
        audit = is_cup and cup_local_pose_audit_only
        world_audit = is_cup and cup_world_pose_audit_only
        frame = expected_cup_attachment if (local or audit) else geometry.frame_id
        pose = expected_cup_local_pose if local else expected.pose
        if observed.header.frame_id != frame:
            mismatches.append(f"{expected.object_id}.frame")
        if audit:
            cup_audit = _cup_local_pose_audit(expected_cup_local_pose, _pose_values(observed.pose))
        elif world_audit:
            cup_world_audit = _cup_local_pose_audit(expected.pose, _pose_values(observed.pose))
        elif is_cup and cup_world_pose_tolerance is not None:
            cup_tolerance_evidence = _cup_world_pose_tolerance(expected.pose, _pose_values(observed.pose),
                                                              cup_world_pose_tolerance)
            if not cup_tolerance_evidence["within"]:
                mismatches.append(f"{expected.object_id}.pose")
        elif not _pose_close(pose.values, _pose_values(observed.pose)):
            mismatches.append(f"{expected.object_id}.pose")
        if len(observed.primitives) != len(expected.primitives):
            mismatches.append(f"{expected.object_id}.primitive_count")
            continue
        if (observed.meshes or observed.mesh_poses or observed.planes or observed.plane_poses
                or observed.subframe_names or observed.subframe_poses):
            mismatches.append(f"{expected.object_id}.unexpected_geometry")
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
        "observed_geometry": normalized_scene_geometry(scene),
    }
    if cup_local_pose_audit_only:
        evidence["cup_local_pose_audit"] = cup_audit or _cup_local_pose_audit(None, None)
    if cup_world_pose_audit_only:
        evidence["cup_world_pose_audit"] = cup_world_audit or _cup_local_pose_audit(None, None)
    if cup_world_pose_tolerance is not None:
        evidence["cup_world_pose_tolerance"] = cup_tolerance_evidence or {
            "within": False, "reason": "OBSERVED_CUP_NOT_PRESENT", "position_tolerance_m": cup_world_pose_tolerance[0],
            "orientation_tolerance_rad": cup_world_pose_tolerance[1], "translation_delta_m": None,
            "rotation_delta_rad": None, "expected_pose": None, "observed_pose": None}
    return SceneVerification(
        success=not mismatches,
        failure_code=None if not mismatches else "SCENE_READBACK_MISMATCH",
        evidence=evidence,
    )


#: Wall-time budget of one clock refresh (a zero-timeout spin burst); the Teacher's executor is single threaded, so a
#: node clock only follows `/clock` as callbacks run.
_CLOCK_REFRESH_BUDGET_S = 0.010


def refresh_node_clock(node, budget_s=_CLOCK_REFRESH_BUDGET_S):
    """Run the node's queued callbacks (its `/clock` subscription among them) so its ROS clock is current.

    A stamp read from a node that has not been spun for a while lags the simulation by the callbacks still queued
    (178 ms at the pilot's first SETUP apply). Never raises: a node spun elsewhere simply keeps its own clock.
    """
    try:
        import rclpy

        began = time.monotonic()
        rclpy.spin_once(node, timeout_sec=0.0)
        while time.monotonic() - began < budget_s:
            rclpy.spin_once(node, timeout_sec=0.0)
    except Exception:
        pass


def record_scene_service_call(*, request, phase, service, invoke, records, ros_clock=None, on_record=None,
                              clock_refresh=None, clock_floor=None):
    """Retain an actual call's full ROS values and monotonic bounds, including refusals.

    `clock_refresh()` runs before every ros-clock read (request and response) so the stamp is the clock at the actual
    call; `clock_floor()` may return a simulation time in ns that the stamp must not be older than (the newest world
    sample already received). Both are best effort: an exception from either never changes the call.

    `on_record(record, request, response)` is offered every finished call (also a refused or failed one, with `response`
    None) after it was appended to `records`. It is for non-blocking publication of the call to an independent consumer
    (the Teacher event stream); whatever it does or raises can never change the call, its result or the exception.
    """
    from rosidl_runtime_py.convert import message_to_ordereddict

    response = None

    record = {
        "schema_version": 1 if ros_clock is None else 2,
        "call_id": str(uuid.uuid4()), "phase": phase,
        "service": service, "request": dict(message_to_ordereddict(request)),
        "request_monotonic_ns": time.monotonic_ns(),
        "response_monotonic_ns": None, "response": None, "error": None,
    }

    def clock_read():
        if clock_refresh is not None:
            try:
                clock_refresh()
            except Exception:
                pass
        begin = time.monotonic_ns()
        stamp = ros_clock.now().nanoseconds
        end = time.monotonic_ns()
        if clock_floor is not None and type(stamp) is int:
            try:
                floor = clock_floor()
                if type(floor) is int and floor > stamp:
                    stamp = floor
            except Exception:
                pass
        if type(stamp) is not int or stamp < 0:
            raise RuntimeError("SCENE_ROS_CLOCK_INVALID")
        return {"sim_time_ns": stamp, "begin_monotonic_ns": begin,
                "end_monotonic_ns": end}

    if ros_clock is not None:
        record.update(request_ros_clock=None, response_ros_clock=None)
    try:
        if ros_clock is not None:
            record["request_ros_clock"] = clock_read()
            record["request_monotonic_ns"] = time.monotonic_ns()
        response = invoke()
        record["response_monotonic_ns"] = time.monotonic_ns()
        if ros_clock is not None:
            record["response_ros_clock"] = clock_read()
        if isinstance(response, SceneCommandReceipt):
            record["error"] = response.failure_code
        elif response is None:
            record["error"] = "SCENE_SERVICE_TIMEOUT"
        else:
            record["response"] = dict(message_to_ordereddict(response))
        return response
    except Exception as error:
        if record["response_monotonic_ns"] is None:
            record["response_monotonic_ns"] = time.monotonic_ns()
        if ros_clock is not None and record["response_ros_clock"] is None:
            try:
                record["response_ros_clock"] = clock_read()
            except Exception as clock_error:
                error.add_note("Actual scene response clock read failed: " + str(clock_error))
        record["error"] = str(error) or type(error).__name__
        raise
    finally:
        records.append(record)
        if on_record is not None:
            try:
                on_record(record, request, response)
            except BaseException:
                pass


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
        # MoveIt's PlanningScene message carries no revision, so the ratified observation's
        # `scene_revision` is this port's own successful-read counter, documented as such
        self._read_revision = 0
        self._service_calls: list[dict] = []
        #: optional `(record, request, response)` callback offered every finished call (non-blocking publication only)
        self.on_service_call = None

    def service_call_records(self) -> tuple[dict, ...]:
        """Copy actual calls with wall-clock bounds; no field claims a simulator timestamp."""
        return tuple(copy.deepcopy(self._service_calls))

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

        def invoke():
            future = client.call_async(request)
            rclpy.spin_until_future_complete(self._node, future, timeout_sec=self._timeout_s)
            response = future.result() if future.done() else None
            if response is None:
                return self._receipt(phase, False, "SCENE_SERVICE_TIMEOUT",
                                     {"timeout_s": self._timeout_s})
            return response

        return record_scene_service_call(
            request=request, phase=phase,
            service=("/apply_planning_scene" if client is self._apply_client
                     else "/get_planning_scene"),
            invoke=invoke, records=self._service_calls,
            ros_clock=(self._node.get_clock() if hasattr(self._node, "get_clock") else None),
            clock_refresh=lambda: refresh_node_clock(self._node),
            on_record=lambda record, sent, received: (
                None if self.on_service_call is None else self.on_service_call(record, sent, received)))

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

    def observe_observation(self, *, source: str = "ros_task_scene_port") -> dict:
        """The ratified Planning Scene observation's parts, from the read the port already makes.

        `scene_revision` is this port's own read counter: MoveIt's `PlanningScene` message has no revision
        field, so the number is the port's and the field's meaning is documented here rather than invented.
        The simulation instant is **not** stamped here — the caller that owns the simulation clock adds it,
        at the same instant it derives the gate, which is the join the audit enforces.
        """

        response = self._observe()
        if isinstance(response, SceneCommandReceipt):
            raise RuntimeError("SCENE_OBSERVATION_UNAVAILABLE: %s" % response.failure_code)
        scene = response.scene
        self._read_revision += 1
        return {"scene_revision": self._read_revision,
                "attached_objects": sorted(value.object.id
                                           for value in scene.robot_state.attached_collision_objects),
                "world_object_ids": sorted(value.id for value in scene.world.collision_objects),
                "is_diff": bool(scene.is_diff), "source": source}

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
