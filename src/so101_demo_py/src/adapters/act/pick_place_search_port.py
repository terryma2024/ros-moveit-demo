"""Provisional fresh-stack begin and one evidence-backed pick-place validation SEARCH phase."""

from __future__ import annotations

import math

from so101_demo.act.contracts import finite, validate_observation, validate_search_result
from so101_demo.core.simulation.types import SimulationEvidence
from so101_demo.ports.planning_scene import SceneCommandReceipt
from .contact_evidence import FRAME_KEYS, contact_hazard
from .scene_state import SCENE_KEYS
from .pick_place_search_segment import PickPlaceSearchObservation


class PickPlaceSearchPortError(RuntimeError):
    """The first physical phase or its owner proof could not be established."""


class PickPlaceSearchPhasePort:
    """Expose only SEARCH while later physical phases remain unprovisioned."""

    def __init__(self, boundary) -> None:
        if (not callable(getattr(boundary, "begin", None))
                or not callable(getattr(boundary, "search", None))
                or not callable(getattr(boundary, "safe_stop", None))
                or not callable(getattr(boundary.neck_sweep_checker, "check", None))):
            raise ValueError("TASK8_SEARCH_PORT_CONFIG_INVALID")
        self.boundary = boundary
        self._startup_receipt = None
        self._request = None
        self._begun = False
        self._searched = False

    def bind_startup_receipt(self, receipt: dict) -> None:
        if (self._startup_receipt is not None or self._begun
                or type(receipt) is not dict
                or type(receipt.get("schema_version")) is not int
                or receipt["schema_version"] != 1
                or receipt.get("session_id") != self.boundary.reset.sources.session_id
                or type(receipt.get("stack_owner")) is not dict
                or type(receipt.get("child_owner")) is not dict
                or not receipt["stack_owner"] or not receipt["child_owner"]):
            raise PickPlaceSearchPortError("TASK8_STARTUP_PROOF_INVALID")
        self._startup_receipt = dict(receipt)

    def _stop_or_raise(self, reason: str, request: dict) -> None:
        try:
            confirmed = self.boundary.safe_stop(reason, request)
        except BaseException as error:
            raise PickPlaceSearchPortError("TASK8_STOP_UNCONFIRMED") from error
        if confirmed is not True:
            raise PickPlaceSearchPortError("TASK8_STOP_UNCONFIRMED")

    def begin(self, request: dict) -> dict:
        if self._startup_receipt is None:
            raise PickPlaceSearchPortError("TASK8_STARTUP_PROOF_REQUIRED")
        if self._begun:
            raise PickPlaceSearchPortError("TASK8_BEGIN_ALREADY_STARTED")
        if (not isinstance(request, dict)
                or request.get("session_id") != self._startup_receipt["session_id"]):
            raise PickPlaceSearchPortError("TASK8_BEGIN_SCOPE_INVALID")
        self._begun = True
        self._request = dict(request)
        try:
            result = self.boundary.begin(request)
            if (type(result) is not dict
                    or set(result) != {"session_id", "attempt_id", "reset_epoch",
                                       "release_epoch", "full_restart"}
                    or result["session_id"] != request["session_id"]
                    or result["attempt_id"] != request["attempt_id"]
                    or type(result["reset_epoch"]) is not int
                    or result["reset_epoch"] < 1
                    or type(result["release_epoch"]) is not int
                    or result["release_epoch"] != 0
                    or result["full_restart"] is not False):
                raise ValueError("reset proof")
            # The child already consumed the owner-issued fresh-stack receipt.
            # Final FULL_RESTART qualification additionally requires the parent
            # to verify exact stack and child retirement after this case.
            return {**result, "full_restart": True}
        except BaseException as error:
            self._stop_or_raise("TASK8_BEGIN_ABORT", request)
            raise PickPlaceSearchPortError("TASK8_BEGIN_EVIDENCE_INVALID") from error

    def _search_evidence(self, observed: PickPlaceSearchObservation,
                         request: dict) -> dict:
        if not isinstance(observed, PickPlaceSearchObservation):
            raise ValueError("search observation type")
        result = validate_search_result(observed.search_result)
        raw = observed.physical_readback
        if (type(raw) is not dict
                or set(raw) != {"world", "scene", "contact", "observation",
                                "reference", "source_stamps_s"}):
            raise ValueError("physical readback schema")
        world, scene, contact = raw["world"], raw["scene"], raw["contact"]
        reset_epoch = self.boundary.reset.receipt.new_epoch
        sources = self.boundary.reset.sources
        skew = finite(sources.readback.max_skew)
        if (result["found"] is not True
                or result["attempt_id"] != request["attempt_id"]
                or not isinstance(world, SimulationEvidence)
                or world.simulation_session_id != request["session_id"]
                or world.reset_epoch != reset_epoch
                or world.simulation_step < 1 or world.paused is not False
                or world.truncated is not False
                or world.object_state.body != "plastic_cup"
                or world.left_fingertip_contacts or world.right_fingertip_contacts
                or not 0 <= result["timestamp"] <= world.simulation_time_s
                or type(scene) is not dict or set(scene) != SCENE_KEYS
                or scene["simulation_session_id"] != world.simulation_session_id
                or scene["reset_epoch"] != reset_epoch
                or scene["simulation_step"] != world.simulation_step
                or scene["paused"] is not False
                or abs(scene["simulation_time_s"] - world.simulation_time_s) > skew
                or scene["model_sha256"] !=
                   sources.contact_pairs.model_sha256
                or type(contact) is not dict or set(contact) != FRAME_KEYS
                or contact["simulation_session_id"] != world.simulation_session_id
                or contact["reset_epoch"] != reset_epoch
                or contact["physics_step"] != world.simulation_step
                or abs(contact["simulation_time_s"] - world.simulation_time_s) > skew):
            raise ValueError("physical readback scope")
        if (sources.contacts.safe() is not True
                or contact_hazard(contact, sources.contact_pairs.for_phase("SEARCH"))):
            raise ValueError("contact hazard")
        observation = validate_observation(raw["observation"])
        if (observation["session_id"] != request["session_id"]
                or observation["attempt_id"] != request["attempt_id"]
                or observation["sim_time_s"] != world.simulation_time_s):
            raise ValueError("RGB scope")
        stamps = raw["source_stamps_s"]
        if (type(stamps) is not dict
                or set(stamps) != {"head", "wrist", "arm", "neck"}
                or skew <= 0
                or any(not 0 <= world.simulation_time_s - finite(stamp) <= skew
                       for stamp in stamps.values())):
            raise ValueError("RGB source skew")
        reference = raw["reference"]
        if (type(reference) is not dict
                or set(reference) != {"positions", "velocities", "accelerations",
                                      "requested_sim_time_s"}
                or reference["requested_sim_time_s"] != world.simulation_time_s
                or any(len(reference[name]) != 6
                       or any(not math.isfinite(finite(value))
                              for value in reference[name])
                       for name in ("positions", "velocities", "accelerations"))):
            raise ValueError("controller reference")
        scene_receipt = observed.planning_scene
        if (not isinstance(scene_receipt, SceneCommandReceipt)
                or scene_receipt.backend != "mujoco"
                or scene_receipt.phase != "READ_BACK"
                or scene_receipt.success is not True
                or scene_receipt.failure_code is not None
                or scene_receipt.evidence.get("mismatches") != []
                or set(scene_receipt.evidence.get("world_ids", ())) !=
                   {"table", "pedestal", "plastic_cup"}
                or scene_receipt.evidence.get("attached_ids") != []):
            raise ValueError("Planning Scene")
        sweep = self.boundary.neck_sweep_checker
        qpos = scene["qpos"]
        neck = finite(qpos[sweep.neck_qpos])
        tolerance = finite(sources.readback.joint_tolerance)
        if (tolerance <= 0 or abs(neck - result["neck_yaw_rad"]) > tolerance
                or sweep.check(qpos, current_rad=neck, target_rad=neck,
                               duration_s=sweep.step_s) is not True):
            raise ValueError("neck path")
        supported = any(item.body2 == "table" and item.normal_force_n > 0
                        for item in world.other_object_contacts)
        return {
            "phase": "SEARCH", "session_id": request["session_id"],
            "attempt_id": request["attempt_id"], "reset_epoch": reset_epoch,
            "release_epoch": 0, "planning_ok": True,
            "controller_reference_ok": True, "joint_feedback_ok": True,
            "contact_ok": True, "mujoco_ok": True,
            "planning_scene_ok": True, "head_rgb_ok": True,
            "wrist_rgb_ok": True, "manual_intervention": False,
            "moveit_recovery": False, "holding_state": "EMPTY",
            "bilateral_contact": False, "micro_lift_confirmed": False,
            "cup_off_table": False, "cup_supported": supported,
            "released": False, "no_fingertip_contact": True,
            "placement_stable": False, "retreat_stable": False,
        }

    def run_phase(self, phase: str, request: dict) -> dict:
        if not self._begun or self._request is None:
            raise PickPlaceSearchPortError("TASK8_BEGIN_REQUIRED")
        if request != self._request:
            self._stop_or_raise("TASK8_PHASE_SCOPE_MISMATCH", request)
            raise PickPlaceSearchPortError("TASK8_PHASE_SCOPE_MISMATCH")
        if phase != "SEARCH":
            self._stop_or_raise("TASK8_PHASE_NOT_PROVISIONED", request)
            raise PickPlaceSearchPortError("TASK8_PHASE_NOT_PROVISIONED")
        if self._searched:
            raise PickPlaceSearchPortError("TASK8_SEARCH_ALREADY_STARTED")
        self._searched = True
        try:
            return self._search_evidence(self.boundary.search(request), request)
        except BaseException as error:
            self._stop_or_raise("TASK8_SEARCH_ABORT", request)
            raise PickPlaceSearchPortError("TASK8_SEARCH_EVIDENCE_INVALID") from error

    def safe_stop(self, reason: str, request: dict) -> bool:
        return self.boundary.safe_stop(reason, request) is True


# Legacy Python API for version-one pick-place callers.
Task8SearchPortError = PickPlaceSearchPortError
Task8SearchPhasePort = PickPlaceSearchPhasePort
