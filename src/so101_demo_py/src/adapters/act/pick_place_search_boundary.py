"""Child-owned reset and SEARCH composition without phase promotion."""

from __future__ import annotations

from pathlib import Path
import time

from so101_demo.act.contracts import finite, identifier
from so101_demo.core.task_geometry import TaskGeometry
from .pick_place_search_binding import build_pick_place_search_adapter
from .pick_place_search_history import verify_search_stationary_physics
from .pick_place_search_native_ingress import verify_search_native_controller_ingress
from .pick_place_search_owner import verify_search_owner_goal_interval
from .pick_place_search_reference import verify_search_stationary_references
from .pick_place_search_segment import PickPlaceSearchSegment


class PickPlaceSearchBoundaryError(RuntimeError):
    """The child cannot prove a scoped SEARCH or physical stop."""


def _scene_port(node, timeout_s):
    from so101_demo.control.planning_scene.task_scene import RosTaskScenePort
    return RosTaskScenePort(node, "mujoco", timeout_s)


class PickPlaceSearchBoundary:
    """Run one reset and one SEARCH using the admitted child's broker."""

    def __init__(self, reset_boundary, *, binding, geometry: TaskGeometry,
                 snapshot_root: Path, scene_node_factory, neck_sweep_checker,
                 scene_port_factory=None,
                 adapter_factory=build_pick_place_search_adapter,
                 segment_factory=PickPlaceSearchSegment,
                 scene_timeout_s=2.0, max_source_wait_s=0.2,
                 poll_interval_s=0.005, stop_timeout_s=5.0,
                 monotonic=time.monotonic, sleep=time.sleep) -> None:
        waits = tuple(finite(value) for value in (
            scene_timeout_s, max_source_wait_s, poll_interval_s, stop_timeout_s,
        ))
        if (not isinstance(geometry, TaskGeometry) or not isinstance(snapshot_root, Path)
                or not snapshot_root.is_absolute()
                or not all(callable(value) for value in (
                    scene_node_factory, adapter_factory, segment_factory, monotonic, sleep,
                ))
                or not callable(getattr(neck_sweep_checker, "check", None))
                or scene_port_factory is not None and not callable(scene_port_factory)
                or min(waits) <= 0 or poll_interval_s > max_source_wait_s
                or stop_timeout_s > 30):
            raise ValueError("TASK8_SEARCH_BOUNDARY_CONFIG_INVALID")
        self.reset, self.binding, self.geometry = reset_boundary, binding, geometry
        self.snapshot_root = snapshot_root
        self.neck_sweep_checker = neck_sweep_checker
        self.scene_node_factory = scene_node_factory
        self.scene_port_factory = scene_port_factory or (
            lambda node: _scene_port(node, scene_timeout_s)
        )
        self.adapter_factory, self.segment_factory = adapter_factory, segment_factory
        self.max_source_wait_s, self.poll_interval_s = max_source_wait_s, poll_interval_s
        self.stop_timeout_s = stop_timeout_s
        self.monotonic, self.sleep = monotonic, sleep
        self._request = None
        self._search_started = False

    def begin(self, request: dict) -> dict:
        if self._request is not None:
            raise PickPlaceSearchBoundaryError("TASK8_BEGIN_ALREADY_STARTED")
        try:
            result = self.reset.begin(request)
            if (not isinstance(result, dict)
                    or result.get("session_id") != request.get("session_id")
                    or result.get("attempt_id") != request.get("attempt_id")
                    or type(result.get("reset_epoch")) is not int
                    or result["reset_epoch"] < 1
                    or result.get("full_restart") is not False):
                raise PickPlaceSearchBoundaryError("TASK8_BEGIN_PROOF_INVALID")
        except BaseException as error:
            try:
                if self.safe_stop("TASK8_BEGIN_ABORT", request) is not True:
                    raise PickPlaceSearchBoundaryError("TASK8_BEGIN_STOP_UNCONFIRMED") from error
            except BaseException as stop_error:
                if isinstance(stop_error, PickPlaceSearchBoundaryError):
                    raise
                raise PickPlaceSearchBoundaryError("TASK8_BEGIN_STOP_UNCONFIRMED") from stop_error
            raise
        self._request = dict(request)
        return result

    def search(self, request: dict):
        if self._request is None:
            raise PickPlaceSearchBoundaryError("TASK8_BEGIN_REQUIRED")
        if request != self._request:
            raise PickPlaceSearchBoundaryError("TASK8_SEARCH_SCOPE_MISMATCH")
        if self._search_started:
            raise PickPlaceSearchBoundaryError("TASK8_SEARCH_ALREADY_STARTED")
        self._search_started = True
        service_node = None
        try:
            self.reset._guard(request)
            service_node = self.scene_node_factory()
            if service_node is self.reset.node or not callable(getattr(service_node, "destroy_node", None)):
                raise PickPlaceSearchBoundaryError("TASK8_SCENE_NODE_INVALID")
            scene_port = self.scene_port_factory(service_node)
            adapter = self.adapter_factory(
                self.reset.node, boundary=self.reset, binding=self.binding,
                request=request, snapshot_root=self.snapshot_root,
                neck_sweep_checker=self.neck_sweep_checker,
            )
            operation_guard = getattr(adapter, "operation_guard", None)
            if not callable(operation_guard):
                raise PickPlaceSearchBoundaryError("TASK8_SEARCH_GUARD_INVALID")
            segment = self.segment_factory(
                self.reset.sources, adapter, scene_port, self.geometry,
                operation_guard=operation_guard,
                history_verifier=lambda observed, stopped_wall_s:
                    verify_search_stationary_physics(
                        self.reset.sources, observed, model=self.reset.model,
                        stopped_wall_s=stopped_wall_s,
                    ),
                reference_verifier=lambda observed, physical_proof, stopped_wall_s:
                    verify_search_stationary_references(
                        self.reset.sources, observed, physical_proof,
                        stopped_wall_s=stopped_wall_s,
                    ),
                owner_verifier=lambda observed, physical_proof, references, stopped_wall_s:
                    verify_search_owner_goal_interval(
                        self.reset.broker,
                        self.reset.broker.ownership.ticket(
                            self.reset.act_context["lease_token"], "act",
                            request["session_id"], request["attempt_id"]),
                        self.reset.sources, observed, physical_proof, references,
                        stopped_wall_s=stopped_wall_s,
                    ),
                native_ingress_verifier=lambda observed, physical_proof, references,
                owner_proof, stopped_wall_s:
                    verify_search_native_controller_ingress(
                        self.reset.broker,
                        self.reset.broker.ownership.ticket(
                            self.reset.act_context["lease_token"], "act",
                            request["session_id"], request["attempt_id"]),
                        self.reset.sources, observed, physical_proof, references,
                        owner_proof, stopped_wall_s=stopped_wall_s,
                    ),
                max_source_wait_s=self.max_source_wait_s,
                poll_interval_s=self.poll_interval_s,
            )
            return segment.run(request, reset_epoch=self.reset.receipt.new_epoch)
        except BaseException as error:
            try:
                if self.safe_stop("TASK8_SEARCH_ABORT", request) is not True:
                    raise PickPlaceSearchBoundaryError("TASK8_SEARCH_STOP_UNCONFIRMED") from error
            except BaseException as stop_error:
                if isinstance(stop_error, PickPlaceSearchBoundaryError):
                    raise
                raise PickPlaceSearchBoundaryError("TASK8_SEARCH_STOP_UNCONFIRMED") from stop_error
            raise
        finally:
            if service_node is not None and service_node is not self.reset.node:
                service_node.destroy_node()

    def safe_stop(self, reason: str, request: dict) -> bool:
        identifier(reason)
        broker = self.reset.broker
        broker.stop_attempt(reason)
        deadline = self.monotonic() + self.stop_timeout_s
        while True:
            broker.tick()
            if broker.ownership.state == "IDLE" and broker.driver.stopped():
                return True
            if self.monotonic() >= deadline:
                return False
            self.sleep(self.poll_interval_s)


# Legacy Python API for version-one pick-place callers.
Task8SearchBoundaryError = PickPlaceSearchBoundaryError
Task8SearchBoundary = PickPlaceSearchBoundary
