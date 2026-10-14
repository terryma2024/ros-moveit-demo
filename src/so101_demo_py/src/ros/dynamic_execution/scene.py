"""Planning scene operations: attach, detach and membership."""

from __future__ import annotations

import copy
from dataclasses import asdict
import time

from so101_demo.control.planning_scene.acm import set_collision_allowed
from so101_demo.core.domain import State
from so101_demo.ros.dynamic_execution.common import _spin_burst


class SceneOperations:
    def _call(self, client, request, timeout_s: float, code: str, *, before_dispatch=None):
        self._check_stop()
        if not client.wait_for_service(timeout_sec=timeout_s):
            raise RuntimeError(f"{code}_UNAVAILABLE")

        def invoke():
            if before_dispatch is not None:
                before_dispatch()
            future = client.call_async(request)
            deadline = time.monotonic() + timeout_s
            while not future.done() and time.monotonic() < deadline:
                self._wait_progress()  # a service wait has no active goal: a stop flag ends it
            response = future.result() if future.done() else None
            if response is None:
                raise RuntimeError(f"{code}_TIMEOUT")
            return response

        from so101_demo.control.planning_scene.task_scene import record_scene_service_call

        return record_scene_service_call(
            request=request, phase=code,
            service=("/apply_planning_scene" if client is self._apply_scene
                     else "/get_planning_scene"),
            invoke=invoke, records=self._scene_service_calls,
            ros_clock=(self._node.get_clock() if hasattr(self._node, "get_clock") else None),
            clock_refresh=self._refresh_node_clock, clock_floor=self._world_sim_floor_ns,
            on_record=self._scene_operation_hook())

    def _refresh_node_clock(self) -> None:
        """Drain the node's queued callbacks so its simulation clock is current (stamps only; never raises)."""
        try:
            _spin_burst(self._node, first_timeout_s=0.0)
        except Exception:
            pass

    def _world_sim_floor_ns(self):
        """Simulation time (ns) of the newest world sample already received, or None. A clock stamp is never older."""
        try:
            return round(self.observer.snapshot_with_receipt().evidence.simulation_time_s * 1e9)
        except Exception:
            return None

    def _scene_operation_hook(self):
        """Offer every Teacher scene call to the event stream (non-blocking); None when there is no stream."""
        stream = getattr(self, "_event_stream", None)
        if stream is None:
            return None
        from so101_demo.act.scene_operation import make_scene_operation_hook

        return make_scene_operation_hook(stream, state=lambda: getattr(self, "_scene_state_value", None),
                                         source=lambda: getattr(self, "_scene_op_source", None))

    def _scene_membership(self) -> tuple[list[str], dict[str, int]]:
        from moveit_msgs.msg import PlanningSceneComponents
        from moveit_msgs.srv import GetPlanningScene

        request = GetPlanningScene.Request()
        request.components.components = (
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
            | PlanningSceneComponents.OBJECT_COLORS
        )
        response = self._call(self._get_scene, request, 5.0, "DYNAMIC_SCENE_READBACK")
        self._last_scene_response = response.scene
        attached = [
            item.object.id for item in response.scene.robot_state.attached_collision_objects
        ]
        world = {item.id: len(item.primitives) for item in response.scene.world.collision_objects}
        return attached, world

    def _set_touch_collision(self, allowed: bool) -> None:
        from moveit_msgs.msg import PlanningScene, PlanningSceneComponents
        from moveit_msgs.srv import ApplyPlanningScene, GetPlanningScene

        request = GetPlanningScene.Request()
        request.components.components = PlanningSceneComponents.ALLOWED_COLLISION_MATRIX
        response = self._call(self._get_scene, request, 5.0, "DYNAMIC_ACM_READBACK")
        matrix = copy.deepcopy(response.scene.allowed_collision_matrix)
        set_collision_allowed(matrix, "jaw", "plastic_cup", allowed)
        set_collision_allowed(matrix, "gripper", "plastic_cup", allowed)
        scene = PlanningScene()
        scene.is_diff = True
        # MoveIt replaces the robot state (and re-creates its attached bodies, losing the attached cup's colour) when the
        # message's robot_state is not a diff; every other apply here already sets it.
        scene.robot_state.is_diff = True
        scene.allowed_collision_matrix = matrix
        applied = self._call(
            self._apply_scene,
            ApplyPlanningScene.Request(scene=scene),
            5.0,
            "DYNAMIC_ACM_APPLY",
        )
        if not applied.success:
            raise RuntimeError("DYNAMIC_ACM_APPLY_FAILED")
        self._touch_collision_allowed = allowed

    def _transaction_scene_membership(self, transaction):
        start = len(getattr(self, "_scene_service_calls", ()))
        try:
            return self._scene_membership()
        finally:
            calls = getattr(self, "_scene_service_calls", ())
            if len(calls) > start:
                transaction["query_call_id"] = calls[start]["call_id"]
                self._write()

    def _attach(self, state: State) -> None:
        from moveit_msgs.srv import ApplyPlanningScene

        from so101_demo.control.planning_scene.task_scene import make_plain_attach_scene

        # One request form: the plain attach. The independent Recorder derives its scene association from the
        # `scene_operation` events of this apply and read-back; nothing here depends on it.
        before = self._snapshot()
        response = self._call(self._apply_scene, ApplyPlanningScene.Request(scene=make_plain_attach_scene()),
                              5.0, "DYNAMIC_ATTACH")
        if not response.success:
            raise RuntimeError("DYNAMIC_ATTACH_FAILED")
        attached_ids, world = self._scene_membership()
        if "plastic_cup" not in attached_ids:
            raise RuntimeError("DYNAMIC_ATTACH_READBACK_MISMATCH")
        self._attached = True
        if self._touch_collision_allowed:
            self._set_touch_collision(False)
        self._record(state, before, self._snapshot(), attached_ids=attached_ids, world=world)

    def _detach_or_sync(self, state: State) -> None:
        from moveit_msgs.msg import AttachedCollisionObject, CollisionObject, PlanningScene
        from moveit_msgs.srv import ApplyPlanningScene

        from so101_demo.act.scene_association import source_geometry
        from so101_demo.control.planning_scene.task_scene import (
            _collision_object,
            verify_task_scene,
        )
        from so101_demo.core.simulation.types import SimulationEvidence
        from so101_demo.core.task_geometry import TaskGeometry

        # Teacher run (design 5a): a fresh snapshot supplies the cup pose; there is no release preflight
        before = (self._supported_release_preflight()
                  if state in (State.DETACH_MOVEIT, State.RECOVER_DETACH_MOVEIT) and not self._teacher_run() else self._snapshot())
        if (not isinstance(self._task_geometry, TaskGeometry)
                or not isinstance(before, SimulationEvidence)
                or before.simulation_session_id != self._session_id
                or before.reset_epoch != self._expected_reset_epoch
                or before.paused or (before.truncated and not self._teacher_run()) or before.object_state.body != "plastic_cup"):
            raise RuntimeError("DYNAMIC_DETACH_SYNC_SOURCE_INVALID")
        expected_geometry = source_geometry(self._task_geometry, before)
        cup = expected_geometry.object("plastic_cup")
        # The apply's exact source survives refusal/timeout; a later failure snapshot cannot
        # replace the sample from which this requested scene was derived.
        import uuid

        transaction = {
            "schema_version": 1, "transaction_id": str(uuid.uuid4()), "phase": state.value,
            "source_physics": asdict(before), "expected_geometry": asdict(expected_geometry),
            "apply_call_id": None, "query_call_id": None, "geometry_verification": None,
        }
        # No manifest write here: it sat between the physics snapshot this request names and the request itself, and a slow write
        # (IO pressure) aged the named source past the Recorder's 100 ms window. The transaction is persisted right after the call
        # (also when the call is refused, times out or raises), so the source still survives every outcome.
        self._document.setdefault("scene_transactions", []).append(transaction)
        remove = AttachedCollisionObject()
        remove.object.id = "plastic_cup"
        remove.object.operation = CollisionObject.REMOVE
        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [remove]
        scene.world.collision_objects = [
            _collision_object(cup, expected_geometry.frame_id)
        ]
        def before_dispatch():
            if state in (State.DETACH_MOVEIT, State.RECOVER_DETACH_MOVEIT) and not self._teacher_run():
                self._check_selected_release_freshness(before)
        start = len(getattr(self, "_scene_service_calls", ()))
        # The physics snapshot this request's cup pose was derived from, named on the scene_operation event so an
        # independent consumer joins the same original step.
        self._scene_op_source = {"simulation_step": before.simulation_step,
                                 "publisher_sequence": before.publisher_sequence,
                                 "simulation_time_s": before.simulation_time_s}
        try:
            response = self._call(
                self._apply_scene, ApplyPlanningScene.Request(scene=scene), 5.0,
                "DYNAMIC_DETACH_SYNC", before_dispatch=before_dispatch)
        finally:
            self._scene_op_source = None
            calls = getattr(self, "_scene_service_calls", ())
            if len(calls) > start:
                transaction["apply_call_id"] = calls[start]["call_id"]
            self._write()
        calls = getattr(self, "_scene_service_calls", ())
        if not response.success:
            raise RuntimeError("DYNAMIC_DETACH_SYNC_FAILED")
        attached_ids, world = self._transaction_scene_membership(transaction)
        if "plastic_cup" in attached_ids or world.get("plastic_cup") != 13:
            raise RuntimeError("DYNAMIC_DETACH_SYNC_READBACK_MISMATCH")
        verification = verify_task_scene(self._last_scene_response, expected_geometry)
        transaction["geometry_verification"] = verification.evidence
        self._write()
        if not verification.success:
            raise RuntimeError("DYNAMIC_DETACH_SYNC_GEOMETRY_MISMATCH")
        self._attached = False
        self._release_scene_geometry = expected_geometry
        self._scene_readback = {
            "attached_object_ids": attached_ids,
            "world_primitive_counts": world,
            "source_physics": asdict(before),
            "geometry_verification": verification.evidence,
        }
        if self._touch_collision_allowed:
            self._set_touch_collision(False)
        self._record(state, before, self._snapshot(), **self._scene_readback)
