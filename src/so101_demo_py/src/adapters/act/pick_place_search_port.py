"""Provisional fresh-stack begin and one evidence-backed pick-place validation SEARCH phase."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os

import copy
import math

from pathlib import Path

from so101_demo.act.contracts import finite, validate_observation, validate_search_result
from so101_demo.act.task8_live_evidence import build_live_evidence_sample
from so101_demo.core.simulation.types import SimulationEvidence
from so101_demo.ports.planning_scene import SceneCommandReceipt
from .contact_evidence import FRAME_KEYS, contact_hazard
from .scene_state import SCENE_KEYS
from .pick_place_search_segment import PickPlaceSearchObservation


#: the recorder's canonical source names, and where this port finds each one's document in the capture.
#: `world`, `scene` and `contact` are the capture's own documents; the synchronizer's observation carries the head and
#: wrist frames and the arm/neck state vector (`synchronizer.py:83-91`), so the four streams are recorded from what the
#: capture actually measured rather than from a name that has no document.
#: the closed evidence document the runner accepts for a phase (its own _EVIDENCE_KEYS); a test asserts the two sets
#: are equal, so this mirror cannot drift without a failure
_PHASE_EVIDENCE_KEYS = frozenset({
    "phase", "session_id", "attempt_id", "reset_epoch", "release_epoch", "physics_step",
    "planning_ok", "controller_reference_ok", "joint_feedback_ok", "contact_ok",
    "mujoco_ok", "planning_scene_ok", "head_rgb_ok", "wrist_rgb_ok",
    "manual_intervention", "moveit_recovery", "holding_state", "bilateral_contact",
    "micro_lift_confirmed", "cup_off_table", "cup_supported", "released",
    "no_fingertip_contact", "placement_stable", "retreat_stable",
})
_SEQUENCE_PHASES = ("APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN",
                    "RELEASE", "RADIAL_RETREAT", "FINAL_CHECK")
_PHASE_GATES = ("planning_ok", "controller_reference_ok", "joint_feedback_ok", "contact_ok",
                "mujoco_ok", "planning_scene_ok", "head_rgb_ok", "wrist_rgb_ok")

_RAW_DOCUMENTS = ("world", "scene", "contact", "head", "wrist", "arm", "neck")


def _raw_document(value):
    """A JSON-safe rendering of one captured document, or a refusal - never a lossy str().

    The capture carries frozen dataclasses (simulation evidence, object state), so they are converted structurally.
    Anything this cannot render raises, because a raw record that silently became a string would be worse than no
    record at all: the recorder hashes these bytes and the index calls them evidence.
    """

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _raw_document(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _raw_document(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_raw_document(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "tolist") and hasattr(value, "dtype"):      # numpy arrays and scalars are capture content
        return _raw_document(value.tolist())
    raise PickPlaceSearchPortError(f"TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: raw:{type(value).__name__}")


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

    def bind_live_evidence(self, window, *, support_distance_max_m=None, raw_records_root=None) -> None:
        """Attach this case's evidence window once, before the port starts recording into it.

        The window is bound here rather than passed at construction because a case's identity - its attempt id in
        particular - only exists once the request arrives, and the port refuses anything after it begins, so the bind
        has to be explicit and one-shot rather than a later rebind.
        """

        if self._live_evidence_window is not None or self._begun:
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_ALREADY_BOUND")
        # Astra re-review #3, finding 3: the support threshold is an ADMITTED policy value, so it travels with the
        # attachment and is never defaulted - a case that did not admit one must not pretend to have measured it
        if type(support_distance_max_m) not in (int, float) or isinstance(support_distance_max_m, bool) \
                or not support_distance_max_m > 0:
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: support_distance_max_m")
        self._support_distance_max_m = float(support_distance_max_m)
        # the raw records must live under the recorder's own evidence root, and the caller that owns that root is the
        # one attaching the evidence - so it is named here rather than guessed from the window's internals
        if raw_records_root is None:
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: raw_records_root")
        self._raw_records_root = Path(raw_records_root)
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
        """One canonical grid sample, derived from this phase's own readback - or a named refusal.

        Astra re-review #3, finding 3: this method used to report `None`, so an attached window was never fed in
        production (CP-1467/1470). It now does the three things the review asks for, in this order:

        1. write the RAW records the recorder will index, under the recorder's own evidence root - the port is the
           component that owns that root;
        2. ask the BOUNDARY to derive the canonical fields, because the readback adapter that owns
           `capture_evidence_fields` is built inside the boundary's own search and is not reachable from here;
        3. build the canonical 24-key sample with the production `build_live_evidence_sample`.

        Any missing piece raises `TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED` naming it. Nothing is skipped and nothing is
        synthesised here.
        """

        raw = observed.physical_readback
        threshold = getattr(self, "_support_distance_max_m", None)
        if threshold is None:
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: support_distance_max_m")
        canonical = getattr(self.boundary, "canonical_evidence", None)
        if not callable(canonical):
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: canonical_evidence")
        root = getattr(self, "_raw_records_root", None)
        if root is None:
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: raw_records_root")

        for name in ("wrist_rgb_ok", "contact_ok", "released", "placement_stable"):
            if name not in evidence:
                raise PickPlaceSearchPortError(f"TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: phase:{name}")
        raw_records = self._write_raw_records(observed, root)
        fields = canonical(raw, support_distance_max_m=threshold, raw_records=raw_records)
        if not isinstance(fields, dict):
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: canonical_evidence_return")

        request = self._request
        # the port keeps the request as a dict, and the phase document's own key names are the ones to use here
        identity = {"case_id": request["scenario_id"], "session_id": request["session_id"],
                    "attempt_id": request["attempt_id"], "reset_epoch": self.boundary.reset.receipt.new_epoch,
                    "release_epoch": 0}
        try:
            found = observed.search_result.get("found")
            if found is not True:
                raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: wrist_target_visible")
            return build_live_evidence_sample(
                identity=identity, phase=phase, physics_step=fields["physics_step"],
                sim_time_s=fields["sim_time_s"], source_stamps_s=fields["source_stamps_s"],
                source_received_monotonic_s=fields["source_received_monotonic_s"],
                raw_records=raw_records, holding_state=fields["holding_state"],
                # the recorder wants the frame and contact groups; each member is taken from the component that
                # actually observed it: the canonical derivation for the physics aggregates, the PHASE DOCUMENT for
                # the release-epoch-relative facts (which the derivation deliberately does not provide), the phase's
                # own wrist-RGB verdict for frame validity, and the validated search result for target visibility
                frame={"wrist_frame_valid": evidence["wrist_rgb_ok"],
                       "wrist_target_visible": found},
                contact={"observation_valid": evidence["contact_ok"],
                         "bilateral_contact": fields["bilateral_contact"],
                         "no_fingertip_contact": fields["no_fingertip_contact"],
                         "cup_supported": fields["cup_supported"],
                         "released": evidence["released"],
                         "placement_stable": evidence["placement_stable"]},
                measurements={"cup_support_distance_m": fields["cup_support_distance_m"],
                              "end_effector_position_m": fields["end_effector_position_m"],
                              "cup_position_m": fields["cup_position_m"],
                              "cup_orientation_xyzw": fields["cup_orientation_xyzw"]},
            )
        except (KeyError, TypeError, ValueError) as error:
            raise PickPlaceSearchPortError(
                f"TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: {type(error).__name__}") from error

    def _write_raw_records(self, observed, root) -> dict:
        """Persist this capture's raw source documents under the recorder's root, with their digests."""

        raw = observed.physical_readback
        directory = Path(root) / "raw"
        directory.mkdir(parents=True, exist_ok=True)
        records = {}
        observation = raw.get("observation")
        if not isinstance(observation, dict):
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: raw:observation")
        state = observation.get("state")
        if not isinstance(state, (list, tuple)) or len(state) != 8:
            raise PickPlaceSearchPortError("TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: raw:arm")
        documents = {
            "world": raw.get("world"), "scene": raw.get("scene"), "contact": raw.get("contact"),
            "head": observation.get("head"), "wrist": observation.get("wrist"),
            "arm": {"sim_time_s": observation.get("sim_time_s"), "state": list(state[:6])},
            "neck": {"sim_time_s": observation.get("sim_time_s"), "state": list(state[6:])},
        }
        for name in _RAW_DOCUMENTS:
            document = documents.get(name)
            if document is None:
                raise PickPlaceSearchPortError(f"TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: raw:{name}")
            payload = json.dumps(_raw_document(document), sort_keys=True,
                                 separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
            target = directory / f"{name}.json"
            descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            records[name] = {"relative_path": f"raw/{name}.json",
                             "sha256": hashlib.sha256(payload).hexdigest()}
        return records

    def run_phase(self, phase: str, request: dict) -> dict:
        if not self._begun or self._request is None:
            raise PickPlaceSearchPortError("TASK8_BEGIN_REQUIRED")
        if request != self._request:
            self._stop_or_raise("TASK8_PHASE_SCOPE_MISMATCH", request)
            raise PickPlaceSearchPortError("TASK8_PHASE_SCOPE_MISMATCH")
        if phase != "SEARCH":
            # the eight sequence phases share one path: the boundary executes, the port validates and stamps scope
            if phase not in _SEQUENCE_PHASES:
                self._stop_or_raise("TASK8_PHASE_NOT_PROVISIONED", request)
                raise PickPlaceSearchPortError(f"TASK8_PHASE_NOT_PROVISIONED: {phase}")
            try:
                return self._sequence_evidence(phase, request)
            except BaseException:
                self._stop_or_raise("TASK8_PHASE_NOT_PROVISIONED", request)
                raise
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
                # no `is not None` guard: a phase with an attached window either records canonical evidence or has
                # already refused by name (Astra re-review #3, finding 3)
                self._live_evidence_window.add_grid(self._grid_sample(phase, observed, evidence))
            return evidence
        except PickPlaceSearchPortError:
            # this port's own refusal already names the missing piece (P1-3's FIELDS_REQUIRED); wrapping it into
            # SEARCH_EVIDENCE_INVALID would hide which contract failed
            self._validated_search_observation = None
            self._stop_or_raise("TASK8_SEARCH_ABORT", request)
            raise
        except BaseException as error:
            self._validated_search_observation = None
            self._stop_or_raise("TASK8_SEARCH_ABORT", request)
            raise PickPlaceSearchPortError("TASK8_SEARCH_EVIDENCE_INVALID") from error

    # --- the rest of the sequence, provisioned one phase at a time (Astra re-review #3, finding 4) -------------
    # The runner calls five more protocol methods besides run_phase, and eight more phases besides SEARCH. Until each
    # is implemented it refuses by NAME, so an unimplemented path can never be mistaken for a completed one - which is
    # exactly what the previous behaviour (an AttributeError, or a phase that silently returned nothing) allowed.

    def set_down(self, *args, **kwargs):
        raise PickPlaceSearchPortError("TASK8_PHASE_NOT_PROVISIONED: set_down")

    def detach_moveit(self, *args, **kwargs):
        raise PickPlaceSearchPortError("TASK8_PHASE_NOT_PROVISIONED: detach_moveit")

    def planning_attached(self, *args, **kwargs):
        raise PickPlaceSearchPortError("TASK8_PHASE_NOT_PROVISIONED: planning_attached")

    def release_preflight(self, *args, **kwargs):
        raise PickPlaceSearchPortError("TASK8_PHASE_NOT_PROVISIONED: release_preflight")

    def run_retreat_segment(self, *args, **kwargs):
        raise PickPlaceSearchPortError("TASK8_PHASE_NOT_PROVISIONED: run_retreat_segment")

    def _sequence_evidence(self, phase: str, request: dict) -> dict:
        """Assemble one sequence phase's evidence from the boundary's own facts, or refuse by name.

        The split is the one SEARCH already proves (CP-1490): the boundary EXECUTES the phase and reports what it
        observed; the port stamps the scope, refuses anything incomplete, and hands the document to the runner, whose
        `_verify_phase` remains the only judge of the per-phase semantics.
        """

        execute = getattr(self.boundary, "sequence_phase", None)
        if not callable(execute):
            raise PickPlaceSearchPortError(f"TASK8_PHASE_NOT_PROVISIONED: {phase}")
        try:
            facts = execute(phase, request)
        except PickPlaceSearchPortError:
            raise
        except Exception as error:
            raise PickPlaceSearchPortError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}") from error
        if type(facts) is not dict:
            raise PickPlaceSearchPortError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: not a mapping")
        document = {"phase": phase, "session_id": request["session_id"], "attempt_id": request["attempt_id"],
                    "reset_epoch": self.boundary.reset.receipt.new_epoch, "release_epoch": 0, **facts}
        if set(document) != _PHASE_EVIDENCE_KEYS:
            raise PickPlaceSearchPortError(
                f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: keys {sorted(set(_PHASE_EVIDENCE_KEYS) ^ set(document))}")
        if any(document[gate] is not True for gate in _PHASE_GATES):
            raise PickPlaceSearchPortError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: gate")
        if document["manual_intervention"] is not False or document["moveit_recovery"] is not False:
            raise PickPlaceSearchPortError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: intervention")
        if document["holding_state"] not in ("EMPTY", "HOLDING"):
            raise PickPlaceSearchPortError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: holding unknown")
        if type(document["physics_step"]) is not int:
            raise PickPlaceSearchPortError(f"TASK8_PHASE_EVIDENCE_INVALID: {phase}: step")
        return document

    def safe_stop(self, reason: str, request: dict) -> bool:
        return self.boundary.safe_stop(reason, request) is True


# Legacy Python API for version-one pick-place callers.
Task8SearchPortError = PickPlaceSearchPortError
Task8SearchPhasePort = PickPlaceSearchPhasePort
