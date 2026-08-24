"""Read-only Gazebo TF and MoveIt Planning Scene cup observer."""

from __future__ import annotations

import math
import time
from typing import Any

from ..ports.cup_scene_observation import CupSceneObservation
from ..ports.evidence import PoseEvidence


class CupSceneObservationError(RuntimeError):
    pass


def _pose(value: Any) -> PoseEvidence:
    return PoseEvidence(
        (float(value.position.x), float(value.position.y), float(value.position.z)),
        (
            float(value.orientation.x),
            float(value.orientation.y),
            float(value.orientation.z),
            float(value.orientation.w),
        ),
    )


class RosCupSceneObserver:
    def __init__(self, node: Any) -> None:
        from moveit_msgs.srv import GetPlanningScene
        from tf2_msgs.msg import TFMessage

        self._node = node
        self._simulator: tuple[PoseEvidence, float] | None = None
        self._subscription = node.create_subscription(
            TFMessage, "/so101/gazebo_pose_info", self._on_tf, 100
        )
        self._scene_client = node.create_client(GetPlanningScene, "/get_planning_scene")

    def _on_tf(self, message: Any) -> None:
        for item in message.transforms:
            if "plastic_cup" not in item.child_frame_id:
                continue
            value = item.transform
            self._simulator = (
                PoseEvidence(
                    (
                        float(value.translation.x),
                        float(value.translation.y),
                        float(value.translation.z),
                    ),
                    (
                        float(value.rotation.x),
                        float(value.rotation.y),
                        float(value.rotation.z),
                        float(value.rotation.w),
                    ),
                ),
                time.monotonic(),
            )

    def observe(self, timeout_s: float) -> CupSceneObservation:
        import rclpy
        from moveit_msgs.msg import PlanningSceneComponents
        from moveit_msgs.srv import GetPlanningScene

        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")
        deadline = time.monotonic() + timeout_s
        while self._simulator is None and time.monotonic() < deadline:
            rclpy.spin_once(self._node, timeout_sec=min(0.05, deadline - time.monotonic()))
        if self._simulator is None:
            raise CupSceneObservationError("CUP_POSE_SCENE_UNAVAILABLE: Gazebo cup pose missing")
        if not self._scene_client.wait_for_service(
            timeout_sec=max(0.0, deadline - time.monotonic())
        ):
            raise CupSceneObservationError("CUP_POSE_SCENE_UNAVAILABLE: MoveIt service missing")
        request = GetPlanningScene.Request()
        request.components.components = (
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        )
        future = self._scene_client.call_async(request)
        while not future.done() and time.monotonic() < deadline:
            rclpy.spin_once(self._node, timeout_sec=min(0.05, deadline - time.monotonic()))
        if not future.done() or future.result() is None:
            raise CupSceneObservationError("CUP_POSE_SCENE_UNAVAILABLE: MoveIt readback timed out")
        scene = future.result().scene
        attached = {
            value.object.id: value.object for value in scene.robot_state.attached_collision_objects
        }
        world = {value.id: value for value in scene.world.collision_objects}
        observed = world.get("plastic_cup") or attached.get("plastic_cup")
        if observed is None:
            raise CupSceneObservationError("CUP_POSE_SCENE_UNAVAILABLE: plastic_cup missing")
        simulator_pose, simulator_time = self._simulator
        return CupSceneObservation(
            simulator_pose,
            simulator_time,
            _pose(observed.pose),
            time.monotonic(),
            "plastic_cup" in attached,
        )

    def close(self) -> None:
        self._node.destroy_subscription(self._subscription)


class RosMujocoCupSceneObserver:
    """Read the cup from atomic MuJoCo evidence plus MoveIt readback."""

    def __init__(self, node: Any, session_id: str) -> None:
        from moveit_msgs.srv import GetPlanningScene

        from ..backends.mujoco.observer import MujocoWorldObserver

        self._node = node
        self._observer = MujocoWorldObserver(node, session_id, max_age_s=0.5)
        self._scene_client = node.create_client(GetPlanningScene, "/get_planning_scene")

    def observe(self, timeout_s: float) -> CupSceneObservation:
        import rclpy
        from moveit_msgs.msg import PlanningSceneComponents
        from moveit_msgs.srv import GetPlanningScene

        from ..backends.mujoco.observer import EvidenceStale

        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")
        deadline = time.monotonic() + timeout_s
        evidence = None
        while evidence is None and time.monotonic() < deadline:
            rclpy.spin_once(self._node, timeout_sec=min(0.05, deadline - time.monotonic()))
            try:
                evidence = self._observer.snapshot()
            except EvidenceStale:
                pass
        if evidence is None:
            raise CupSceneObservationError("CUP_POSE_SCENE_UNAVAILABLE: MuJoCo cup pose missing")
        if not self._scene_client.wait_for_service(
            timeout_sec=max(0.0, deadline - time.monotonic())
        ):
            raise CupSceneObservationError("CUP_POSE_SCENE_UNAVAILABLE: MoveIt service missing")
        request = GetPlanningScene.Request()
        request.components.components = (
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        )
        future = self._scene_client.call_async(request)
        while not future.done() and time.monotonic() < deadline:
            rclpy.spin_once(self._node, timeout_sec=min(0.05, deadline - time.monotonic()))
        if not future.done() or future.result() is None:
            raise CupSceneObservationError("CUP_POSE_SCENE_UNAVAILABLE: MoveIt readback timed out")
        scene = future.result().scene
        attached = {
            value.object.id: value.object for value in scene.robot_state.attached_collision_objects
        }
        world = {value.id: value for value in scene.world.collision_objects}
        observed = world.get("plastic_cup") or attached.get("plastic_cup")
        if observed is None:
            raise CupSceneObservationError("CUP_POSE_SCENE_UNAVAILABLE: plastic_cup missing")
        return CupSceneObservation(
            PoseEvidence(
                tuple(float(value) for value in evidence.object_state.position_world),
                tuple(float(value) for value in evidence.object_state.orientation_xyzw),
            ),
            time.monotonic(),
            _pose(observed.pose),
            time.monotonic(),
            "plastic_cup" in attached,
        )

    def close(self) -> None:
        return None
