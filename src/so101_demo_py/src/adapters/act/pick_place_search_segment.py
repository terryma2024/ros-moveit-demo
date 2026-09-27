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


_STOP_INTERVAL_STEPS = 50
_STOP_INTERVAL_NS = 100_000_000


@dataclass(frozen=True, slots=True)
class PickPlaceSearchObservation:
    search_result: dict
    physical_readback: dict
    planning_scene: SceneCommandReceipt
    stationary_physics_proof: dict | None = None
    stationary_reference_proof: dict | None = None
    local_owner_goal_proof: dict | None = None
    physics_step_fence: dict | None = None
    native_controller_ingress_proof: dict | None = None


class PickPlaceSearchSegment:
    """Drive only SEARCH; the caller decides whether its evidence passes."""

    def __init__(self, sources, adapter, scene_port, geometry: TaskGeometry, *,
                 operation_guard, history_verifier, reference_verifier,
                 owner_verifier, native_ingress_verifier,
                 max_source_wait_s: float, poll_interval_s: float,
                 monotonic=time.monotonic, sleep=time.sleep,
                 clock_ns=time.monotonic_ns) -> None:
        if (not isinstance(geometry, TaskGeometry)
                or not callable(operation_guard)
                or not callable(history_verifier)
                or not callable(reference_verifier)
                or not callable(owner_verifier)
                or not callable(native_ingress_verifier)):
            raise ValueError("SEARCH_SEGMENT_CONFIG_INVALID")
        max_wait = finite(max_source_wait_s)
        poll = finite(poll_interval_s)
        if max_wait <= 0 or poll <= 0 or poll > max_wait:
            raise ValueError("SEARCH_SEGMENT_CONFIG_INVALID")
        self.sources, self.adapter, self.scene_port = sources, adapter, scene_port
        self.geometry, self.guard = geometry, operation_guard
        self.history_verifier = history_verifier
        self.reference_verifier = reference_verifier
        self.owner_verifier = owner_verifier
        self.native_ingress_verifier = native_ingress_verifier
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
                if str(error) not in ("SOURCE_STEP_NOT_ADVANCED",
                                      "RGB_READBACK_UNAVAILABLE"):
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

    def _post_stop_interval(self, request: dict, reset_epoch: int, cursor: int):
        """Select after a fresh stopped frame and 100 ms of advancing physics."""
        stopped_wall_s = self.monotonic()
        try:
            marker = self.sources.physics_fence.request_after_stop(
                reset_epoch, stopped_wall_s, request["deadline_ns"])
            if (not isinstance(marker, dict)
                    or marker.get("session_id") != request["session_id"]
                    or marker.get("reset_epoch") != reset_epoch
                    or type(marker.get("marked_physics_step")) is not int
                    or marker["marked_physics_step"] < 1
                    or marker.get("command_authority") is not False):
                raise ValueError("PHYSICS_STEP_FENCE_INVALID")
            cursor = max(cursor, marker["marked_physics_step"])
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise PickPlaceSearchError("SEARCH_PHYSICS_STEP_FENCE_INVALID") from error

        def received_after_stop(raw):
            try:
                receipts = raw["source_received_wall_s"]
                return all(finite(receipts[kind], nonnegative=True) >= stopped_wall_s
                           for kind in ("world", "scene", "contact"))
            except (KeyError, TypeError, ValueError) as error:
                raise PickPlaceSearchError("SEARCH_STOP_DWELL_RECEIPT_INVALID") from error

        while True:
            raw, geometry = self._next(request, reset_epoch, cursor)
            world = raw["world"]
            cursor = world.simulation_step
            if world.paused is not False:
                raise PickPlaceSearchError("SEARCH_STOP_DWELL_PAUSED")
            if received_after_stop(raw):
                break
        first_step = cursor
        first_ns = round(finite(world.simulation_time_s, nonnegative=True) * 1_000_000_000)
        while True:
            raw, geometry = self._next(request, reset_epoch, cursor)
            world = raw["world"]
            cursor = world.simulation_step
            if world.paused is not False:
                raise PickPlaceSearchError("SEARCH_STOP_DWELL_PAUSED")
            if not received_after_stop(raw):
                raise PickPlaceSearchError("SEARCH_STOP_DWELL_RECEIPT_INVALID")
            elapsed_steps = cursor - first_step
            elapsed_ns = round(finite(world.simulation_time_s, nonnegative=True)
                               * 1_000_000_000) - first_ns
            if elapsed_ns != elapsed_steps * 2_000_000:
                raise PickPlaceSearchError("SEARCH_STOP_DWELL_TIME_INVALID")
            if elapsed_steps >= _STOP_INTERVAL_STEPS:
                if elapsed_ns < _STOP_INTERVAL_NS:
                    raise PickPlaceSearchError("SEARCH_STOP_DWELL_TIME_INVALID")
                return raw, geometry, stopped_wall_s, marker

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
                final_raw, final_geometry, stopped_wall_s, marker = self._post_stop_interval(
                    request, reset_epoch, cursor)
                if final_raw["world"].simulation_time_s < result["timestamp"]:
                    raise PickPlaceSearchError("SEARCH_POST_LOCK_STEP_INVALID")
                scene_receipt = self._sync_scene(request, final_geometry)
                observed = PickPlaceSearchObservation(
                    result, final_raw, scene_receipt, physics_step_fence=marker)
                proof = self.history_verifier(observed, stopped_wall_s)
                if (not isinstance(proof, dict)
                        or proof.get("selected_physics_step") !=
                           final_raw["world"].simulation_step
                        or proof.get("stop_confirmed_wall_s") != stopped_wall_s
                        or proof.get("physics_step_fence") != marker
                        or proof.get("controller_interval_proof_required") is not True
                        or proof.get("command_authority") is not False
                        or proof.get("eligible_for_collection") is not False):
                    raise PickPlaceSearchError("SEARCH_PHYSICS_HISTORY_INVALID")
                references = self.reference_verifier(
                    observed, proof, stopped_wall_s)
                if (not isinstance(references, dict)
                        or references.get("selected_sim_time_ns") != round(
                            final_raw["world"].simulation_time_s * 1_000_000_000)
                        or references.get("selected_source_sha256") !=
                           proof.get("selected_source_sha256")
                        or references.get("stop_confirmed_wall_s") != stopped_wall_s
                        or references.get("owner_goal_interval_proof_required") is not True
                        or references.get("command_authority") is not False
                        or references.get("eligible_for_collection") is not False):
                    raise PickPlaceSearchError("SEARCH_REFERENCE_HISTORY_INVALID")
                owner = self.owner_verifier(
                    observed, proof, references, stopped_wall_s)
                if (not isinstance(owner, dict)
                        or owner.get("selected_source_sha256") !=
                           proof.get("selected_source_sha256")
                        or owner.get("reference_window_sha256") !=
                           references.get("reference_window_sha256")
                        or owner.get("stop_confirmed_wall_s") != stopped_wall_s
                        or owner.get("controller_native_ingress_proof_required") is not True
                        or owner.get("command_authority") is not False
                        or owner.get("eligible_for_collection") is not False):
                    raise PickPlaceSearchError("SEARCH_OWNER_GOAL_INTERVAL_INVALID")
                native = self.native_ingress_verifier(
                    observed, proof, references, owner, stopped_wall_s)
                if (not isinstance(native, dict)
                        or native.get("selected_source_sha256") !=
                           proof.get("selected_source_sha256")
                        or native.get("reference_window_sha256") !=
                           references.get("reference_window_sha256")
                        or native.get("control_event_window_sha256") !=
                           owner.get("control_event_window_sha256")
                        or native.get("owner_generation") != owner.get("owner_generation")
                        or native.get("stop_confirmed_wall_s") != stopped_wall_s
                        or native.get("commit_window_ingress_recheck_required") is not True
                        or native.get("command_authority") is not False
                        or native.get("eligible_for_collection") is not False):
                    raise PickPlaceSearchError("SEARCH_NATIVE_CONTROLLER_INGRESS_INVALID")
                self._guard(request)
                return PickPlaceSearchObservation(
                    result, final_raw, scene_receipt, proof, references, owner, marker, native)
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
