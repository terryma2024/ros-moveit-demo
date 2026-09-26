"""Bounded pick-place validation SEARCH execution over accepted physical readback."""

from __future__ import annotations

from dataclasses import dataclass
import time

from so101_demo.act.contracts import finite, identifier, validate_search_result
from so101_demo.core.task_geometry import TaskGeometry
from so101_demo.ports.planning_scene import SceneCommandReceipt
from .pick_place_readback import PickPlaceReadbackError
from .pick_place_scene import pick_place_scene_geometry


class PickPlaceSearchError(RuntimeError):
    """SEARCH could not produce safe, complete physical evidence."""


@dataclass(frozen=True, slots=True)
class PickPlaceSearchObservation:
    search_result: dict
    physical_readback: dict
    planning_scene: SceneCommandReceipt


class PickPlaceSearchSegment:
    """Drive only SEARCH; the caller decides whether its evidence passes."""

    def __init__(self, sources, adapter, scene_port, geometry: TaskGeometry, *,
                 operation_guard, max_source_wait_s: float, poll_interval_s: float,
                 monotonic=time.monotonic, sleep=time.sleep,
                 clock_ns=time.monotonic_ns) -> None:
        if not isinstance(geometry, TaskGeometry) or not callable(operation_guard):
            raise ValueError("SEARCH_SEGMENT_CONFIG_INVALID")
        max_wait = finite(max_source_wait_s)
        poll = finite(poll_interval_s)
        if max_wait <= 0 or poll <= 0 or poll > max_wait:
            raise ValueError("SEARCH_SEGMENT_CONFIG_INVALID")
        self.sources, self.adapter, self.scene_port = sources, adapter, scene_port
        self.geometry, self.guard = geometry, operation_guard
        self.max_wait, self.poll = max_wait, poll
        self.monotonic, self.sleep, self.clock_ns = monotonic, sleep, clock_ns

    def _guard(self, request: dict) -> None:
        self.guard()
        if self.clock_ns() >= request["deadline_ns"]:
            raise PickPlaceSearchError("SEARCH_DEADLINE_EXPIRED")

    def _next(self, request: dict, reset_epoch: int, after_step: int):
        started = self.monotonic()
        while True:
            self._guard(request)
            try:
                raw = self.sources.capture(request["attempt_id"], after_step=after_step)
            except PickPlaceReadbackError as error:
                if str(error) != "SOURCE_STEP_NOT_ADVANCED":
                    raise
                if self.monotonic() - started >= self.max_wait:
                    raise PickPlaceSearchError("SEARCH_SOURCE_TIMEOUT") from error
                self.sleep(self.poll)
                continue
            geometry = pick_place_scene_geometry(
                self.geometry, raw, session_id=request["session_id"],
                reset_epoch=reset_epoch,
            )
            world = raw["world"]
            if world.simulation_step <= after_step:
                raise PickPlaceSearchError("SEARCH_SOURCE_STEP_REUSED")
            if world.left_fingertip_contacts or world.right_fingertip_contacts:
                raise PickPlaceSearchError("SEARCH_CONTACT_UNSAFE")
            return raw, geometry

    def _sync_scene(self, request: dict, geometry: TaskGeometry) -> SceneCommandReceipt:
        self._guard(request)
        applied = self.scene_port.apply_task_scene(geometry)
        if (not isinstance(applied, SceneCommandReceipt) or applied.phase != "APPLY"
                or applied.success is not True):
            raise PickPlaceSearchError("SEARCH_SCENE_APPLY_FAILED")
        self._guard(request)
        observed = self.scene_port.observe_task_scene(
            geometry, expected_cup_attachment=None,
        )
        if (not isinstance(observed, SceneCommandReceipt)
                or observed.phase != "READ_BACK" or observed.success is not True
                or observed.backend != applied.backend):
            raise PickPlaceSearchError("SEARCH_SCENE_READBACK_FAILED")
        return observed

    def run(self, request: dict, *, reset_epoch: int) -> PickPlaceSearchObservation:
        try:
            if (not isinstance(request, dict) or type(reset_epoch) is not int
                    or reset_epoch < 1):
                raise ValueError("SEARCH_SCOPE_INVALID")
            identifier(request["session_id"])
            identifier(request["attempt_id"])
            if type(request["deadline_ns"]) is not int:
                raise ValueError("SEARCH_DEADLINE_INVALID")
            cursor = 0
            first = True
            while True:
                raw, geometry = self._next(request, reset_epoch, cursor)
                cursor = raw["world"].simulation_step
                if first:
                    self._sync_scene(request, geometry)
                    first = False
                self._guard(request)
                decision = self.adapter.tick(safe_observe=True)
                if not isinstance(decision, dict):
                    raise PickPlaceSearchError("SEARCH_DECISION_INVALID")
                if "found" not in decision:
                    continue
                result = validate_search_result(decision)
                if result["attempt_id"] != request["attempt_id"] or result["found"] is not True:
                    raise PickPlaceSearchError("SEARCH_NOT_LOCKED")
                if self.adapter.neck_port.stop_and_confirm() is not True:
                    raise PickPlaceSearchError("SEARCH_STOP_UNCONFIRMED")
                final_raw, final_geometry = self._next(request, reset_epoch, cursor)
                if final_raw["world"].simulation_time_s < result["timestamp"]:
                    raise PickPlaceSearchError("SEARCH_POST_LOCK_STEP_INVALID")
                observed = self._sync_scene(request, final_geometry)
                self._guard(request)
                return PickPlaceSearchObservation(result, final_raw, observed)
        except BaseException as error:
            try:
                stopped = self.adapter.neck_port.stop_and_confirm()
            except BaseException as stop_error:
                raise PickPlaceSearchError("SEARCH_STOP_UNCONFIRMED") from stop_error
            if stopped is not True:
                raise PickPlaceSearchError("SEARCH_STOP_UNCONFIRMED") from error
            raise


# Legacy Python API for version-one pick-place callers.
Task8SearchError = PickPlaceSearchError
Task8SearchObservation = PickPlaceSearchObservation
Task8SearchSegment = PickPlaceSearchSegment
