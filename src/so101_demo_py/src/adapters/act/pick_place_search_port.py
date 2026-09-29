"""Provisional fresh-stack begin and one evidence-backed pick-place validation SEARCH phase."""

from __future__ import annotations

import hashlib

import copy
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

    def __init__(self, boundary, *, expert_route_factory=None, evidence_recorder=None,
                 live_evidence_window=None) -> None:
        if (not callable(getattr(boundary, "begin", None))
                or not callable(getattr(boundary, "search", None))
                or not callable(getattr(boundary, "safe_stop", None))
                or not callable(getattr(boundary.neck_sweep_checker, "check", None))
                or expert_route_factory is not None
                and not callable(expert_route_factory)
                or evidence_recorder is not None
                and not callable(getattr(evidence_recorder, "append", None))):
            raise ValueError("TASK8_SEARCH_PORT_CONFIG_INVALID")
        self.boundary = boundary
        self._expert_route_factory = expert_route_factory
        self._evidence_recorder = evidence_recorder
        # the window this case's frozen 10 Hz grid is recorded into; fed only from the port's own readback
        self._live_evidence_window = live_evidence_window
        self._expert_route = None
        self._startup_receipt = None
        self._request = None
        self._begun = False
        self._searched = False
        self._validated_search_observation = None

    def validated_search_observation(self) -> PickPlaceSearchObservation:
        """Return isolated physical SEARCH evidence only after full validation."""
        if self._validated_search_observation is None:
            raise PickPlaceSearchPortError("PICK_PLACE_SEARCH_OBSERVATION_UNAVAILABLE")
        return copy.deepcopy(self._validated_search_observation)

    def selected_prefix_source(self, *, max_skew_s: float) -> dict:
        """Freeze only the previously validated physical SEARCH sample."""
        from .selected_search_source import freeze_selected_search_source

        return freeze_selected_search_source(
            self.validated_search_observation(), max_skew_s=max_skew_s)

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

    def bind_live_evidence(self, window) -> None:
        """Attach this case's evidence window once, before the port starts recording into it.

        The window is bound here rather than passed at construction because a case's identity - its attempt id in
        particular - only exists once the request arrives, and the port refuses anything after it begins, so the bind
        has to be explicit and one-shot rather than a later rebind.
        """

        if self._live_evidence_window is not None or self._begun:
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_ALREADY_BOUND")
        if window is None or not callable(getattr(window, "seal", None)):
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_WINDOW_INVALID")
        self._live_evidence_window = window

    def _bind_case_epoch(self, result: dict) -> None:
        """Give the attached window the epoch of the receipt just verified; refuse a window that cannot take it."""

        if self._live_evidence_window is None:
            return
        bind = getattr(self._live_evidence_window, "bind_reset_epoch", None)
        if not callable(bind):
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_WINDOW_INVALID")
        bind(result["reset_epoch"])

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
            if self._expert_route_factory is not None:
                from .trusted_visible_approach_source import TrustedVisibleApproachSourcePort
                from .visible_approach_expert_route import VisibleApproachExpertRoute

                reset = self.boundary.reset
                manifest = reset.manifest
                cases = (*manifest["prefix_cases"], *manifest["full_cases"])
                matching = [case for case in cases
                            if case["case_id"] == request.get("scenario_id")]
                if (len(matching) != 1
                        or any(matching[0][key] != request.get(key)
                               for key in ("mode", "stop_after", "lifecycle"))
                        or manifest["contact_policy_fingerprint"] !=
                           reset.sources.contact_pairs.fingerprint):
                    raise ValueError("expert route scope")
                if (matching[0]["anchor"] == "default"
                        and request.get("stop_after") != "SEARCH"):
                    if not isinstance(reset.broker._prefix_source_port,
                                      TrustedVisibleApproachSourcePort):
                        raise ValueError("expert source unavailable")
                    self._expert_route = self._expert_route_factory(request)
                    if (not isinstance(self._expert_route, VisibleApproachExpertRoute)
                            or self._expert_route.manifest["policy_fingerprint"] !=
                               manifest["contact_policy_fingerprint"]):
                        raise ValueError("expert route invalid")
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
            # The verified receipt is the only thing that knows this case's reset generation, and nothing has been
            # recorded yet, so this is where the window's identity learns its epoch - and where a window that cannot
            # bind at all is refused rather than left to stamp an unknown generation into every sample.
            self._bind_case_epoch(result)
            # The child already consumed the owner-issued fresh-stack receipt.
            # Final FULL_RESTART qualification additionally requires the parent
            # to verify exact stack and child retirement after this case.
            return {**result, "full_restart": True}
        except BaseException as error:
            self._request = None
            self._expert_route = None
            self._stop_or_raise("TASK8_BEGIN_ABORT", request)
            raise PickPlaceSearchPortError("TASK8_BEGIN_EVIDENCE_INVALID") from error

    def record_evidence(self, sample) -> None:
        """Forward one complete canonical sample; a refusal invalidates the case.

        The SEARCH observation alone cannot fill the canonical sample shape, so a partial sample is
        refused here rather than recorded: evidence loss must make the case INVALID instead of
        producing a record that looks complete.
        """

        recorder = self._evidence_recorder
        if recorder is None:
            return
        if type(sample) is not dict or len(sample) != 24:
            raise ValueError("TASK8_SEARCH_PORT_EVIDENCE_INVALID")
        try:
            recorder.append(sample)
        except ValueError as error:
            raise ValueError(f"TASK8_SEARCH_PORT_EVIDENCE_INVALID: {error}") from error

    def seal_live_evidence(self, request: dict) -> dict:
        """Seal this case's live evidence through the recorder, if one is attached."""

        recorder = self._evidence_recorder
        if recorder is None or not callable(getattr(recorder, "seal", None)):
            raise ValueError("LIVE_EVIDENCE_SEAL_UNAVAILABLE")
        identity = {
            "case_id": request["scenario_id"],
            "session_id": request["session_id"],
            "attempt_id": request["attempt_id"],
            "reset_epoch": request["reset_epoch"],
            "release_epoch": request["release_epoch"],
        }
        window = self._live_evidence_window
        if window is not None and not getattr(window, "_sealed", False):
            # seal the window first: a window that cannot be sealed must not leave a sealed recorder behind.
            # A window that already sealed itself on reaching FINAL_CHECK is left as it is, so a second call is safe.
            window.seal()
        # the recorder seals itself when the chain completes (its `_sealed` holds the published index path), so a
        # completed chain must return that artifact instead of sealing again - seal_live_evidence is idempotent
        published = getattr(recorder, "_sealed", None)
        if published is not None:
            from pathlib import Path as _Path

            from so101_demo.act.task8_live_evidence import SCHEMA_VERSION as _EVIDENCE_SCHEMA
            return {"path": str(published),
                    "sha256": hashlib.sha256(_Path(published).read_bytes()).hexdigest(),
                    "schema_version": _EVIDENCE_SCHEMA}
        return recorder.seal(identity)

    def _search_evidence(self, observed: PickPlaceSearchObservation,
                         request: dict) -> dict:
        if not isinstance(observed, PickPlaceSearchObservation):
            raise ValueError("search observation type")
        result = validate_search_result(observed.search_result)
        raw = observed.physical_readback
        if (type(raw) is not dict
                or set(raw) != {"world", "scene", "contact", "observation",
                                "reference", "source_stamps_s",
                                "source_received_wall_s"}):
            raise ValueError("physical readback schema")
        receipts = raw["source_received_wall_s"]
        if (type(receipts) is not dict
                or set(receipts) != {"world", "scene", "contact",
                                     "head", "wrist", "arm", "neck"}
                or any(finite(value, nonnegative=True) != value
                       for value in receipts.values())):
            raise ValueError("physical receipt schema")
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
            "release_epoch": 0, "physics_step": world.simulation_step,
            "planning_ok": True,
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

    @property
    def live_evidence_window(self):
        """The window this port records into, or None - public so callers need not touch a private name."""

        return self._live_evidence_window

    def _grid_sample(self, phase: str, observed, evidence: dict) -> dict:
        """One grid sample taken from the port's own readback - never synthesised by a caller."""

        raw = observed.physical_readback
        sim_time = None
        for source in (raw.get("observation"), raw.get("world"), raw.get("reference")):
            if isinstance(source, dict):
                for key in ("sim_time_s", "simulation_time_s", "requested_sim_time_s"):
                    value = source.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        sim_time = float(value)
                        break
            if sim_time is not None:
                break
        if sim_time is None:
            raise PickPlaceSearchPortError("LIVE_EVIDENCE_SIM_TIME_UNAVAILABLE")
        step = evidence.get("physics_step")
        if type(step) is not int:
            raise PickPlaceSearchPortError("LIVE_EVIDENCE_STEP_UNAVAILABLE")
        return {"phase": phase, "sim_time_s": sim_time, "physics_step": step}

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
            observed = copy.deepcopy(self.boundary.search(request))
            evidence = self._search_evidence(observed, request)
            self._validated_search_observation = observed
            if self._expert_route is not None:
                reset = self.boundary.reset
                context = reset.act_context
                ticket = reset.broker.ownership.ticket(
                    context["lease_token"], "act", request["session_id"],
                    request["attempt_id"])
                reset.broker._prefix_source_port.register(
                    reset.broker, self, self._expert_route, ticket,
                    active_policy_fingerprint=reset.sources.contact_pairs.fingerprint)
            if self._live_evidence_window is not None:
                self._live_evidence_window.add_grid(self._grid_sample(phase, observed, evidence))
            return evidence
        except BaseException as error:
            self._validated_search_observation = None
            self._stop_or_raise("TASK8_SEARCH_ABORT", request)
            raise PickPlaceSearchPortError("TASK8_SEARCH_EVIDENCE_INVALID") from error

    def safe_stop(self, reason: str, request: dict) -> bool:
        return self.boundary.safe_stop(reason, request) is True


# Legacy Python API for version-one pick-place callers.
Task8SearchPortError = PickPlaceSearchPortError
Task8SearchPhasePort = PickPlaceSearchPhasePort
