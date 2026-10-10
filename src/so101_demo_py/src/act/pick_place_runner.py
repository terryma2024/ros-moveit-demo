"""Fixed pick-place phase orchestration over an independently verified execution port.

This module makes no ROS calls. The port owns planning, controller, MuJoCo, contact,
camera and Planning Scene readback. A phase is complete only after all six execution
evidence gates and both camera gates agree for the same reset and attempt.
"""

from __future__ import annotations

import math
import time
from typing import Protocol


class PickPlaceError(RuntimeError):
    """A phase boundary or physical stop could not be proved."""


class PickPlaceExecutionPort(Protocol):
    def begin(self, request: dict) -> dict: ...
    def run_phase(self, phase: str, request: dict) -> dict: ...
    def set_down(self, request: dict) -> dict: ...
    def release_preflight(self, request: dict) -> dict: ...
    def detach_moveit(self, request: dict) -> bool: ...
    def planning_attached(self, request: dict) -> bool: ...
    def run_retreat_segment(self, direction: str, distance_m: float, request: dict) -> dict: ...
    def safe_stop(self, reason: str, request: dict) -> bool: ...


#: the only nested records the raw block may carry, by their ratified names (CP-2115)
_RAW_RECORD_KEYS = ("planning_scene_observation", "controller_feedback")


class PickPlaceRunner:
    PHASES = (
        "SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT",
        "ALIGN", "RELEASE", "RADIAL_RETREAT", "FINAL_CHECK",
    )
    _REQUEST_KEYS = frozenset({
        "mode", "stop_after", "lifecycle", "scenario_id", "session_id",
        "attempt_id", "deadline_ns",
    })
    _BEGIN_KEYS = frozenset({
        "session_id", "attempt_id", "reset_epoch", "release_epoch", "full_restart",
    })
    _EVIDENCE_KEYS = frozenset({
        "phase", "session_id", "attempt_id", "reset_epoch", "release_epoch", "physics_step",
        "planning_ok", "controller_reference_ok", "joint_feedback_ok", "contact_ok",
        "mujoco_ok", "planning_scene_ok", "head_rgb_ok", "wrist_rgb_ok",
        "manual_intervention", "moveit_recovery", "holding_state", "bilateral_contact",
        "micro_lift_confirmed", "cup_off_table", "cup_supported", "released",
        "no_fingertip_contact", "placement_stable", "retreat_stable",
    })
    # the raw physical numbers a phase predicate used, so the audit can recompute its thresholds
    # offline; optional in the contract, because a port that cannot observe them must not fake them
    _PHYSICS_KINDS = {
        "SEARCH": "pose", "APPROACH": "pose", "CLOSE": "contact", "MICRO_LIFT": "support",
        "TRANSPORT": "support", "ALIGN": "pose", "RELEASE": "contact",
        "RADIAL_RETREAT": "retract", "FINAL_CHECK": "pose",
    }
    _EVIDENCE_GATES = (
        "planning_ok", "controller_reference_ok", "joint_feedback_ok", "contact_ok",
        "mujoco_ok", "planning_scene_ok", "head_rgb_ok", "wrist_rgb_ok",
    )
    _RELEASE_KEYS = frozenset({
        "holding_state", "cup_supported", "bilateral_contact", "fresh", "planning_attached",
        "session_id", "attempt_id", "reset_epoch", "release_epoch", "physics_step",
    })
    _SET_DOWN_KEYS = frozenset({
        "session_id", "attempt_id", "reset_epoch", "release_epoch", "physics_step",
        "holding_state", "cup_supported", "bilateral_contact", "controller_stopped",
        "controller_reference_ok", "joint_feedback_ok",
        "planning_attached", "contact_ok", "mujoco_ok", "planning_scene_ok",
        "head_rgb_ok", "wrist_rgb_ok",
    })

    def __init__(self, port: PickPlaceExecutionPort, *, clock_ns=time.monotonic_ns,
                 audit=None) -> None:
        self.port = port
        self.clock_ns = clock_ns
        # the audit receives the events this run actually produced, in the order it produced them
        self.audit = audit
        self._event_identity: dict = {}
        self._missing_raw: list = []
        self._ran = False

    @staticmethod
    def _raw(observation) -> bool:
        """A raw block is a flat mapping of finite numbers and booleans, or it is refused."""

        if not isinstance(observation, dict) or not observation:
            return False
        for key, value in observation.items():
            if not isinstance(key, str) or not key:
                return False
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if not math.isfinite(value):
                    return False
                continue
            if (isinstance(value, (list, tuple))
                    and all(isinstance(item, (int, float)) and not isinstance(item, bool)
                            and math.isfinite(item) for item in value)):
                continue
            if (isinstance(value, (list, tuple))
                    and all(isinstance(item, str) and item for item in value)):
                # the source contract also carries names, such as the contact geometry list
                continue
            if isinstance(value, dict) and key in _RAW_RECORD_KEYS and value:
                # the ratified typed records travel inside the raw block (F12/CP-2115); every other key keeps
                # the flat rule above, and the common audit validates these records strictly for itself
                continue
            if isinstance(value, str) and value:
                # F1: the registered sample names the session it came from, which is a raw value like any other
                continue
            if (isinstance(value, list) and value
                    and all(isinstance(item, dict) and item for item in value)):
                # F1: the registered sample publishes its contact records as a list of non-empty dictionaries
                continue
            return False
        return True

    def _physics(self, phase: str, evidence: dict) -> None:
        if "physical_observation" not in evidence:
            # a phase that carries no raw observation cannot support a formal claim
            self._missing_raw.append(phase)
            return
        if self.audit is None:
            return
        raw = dict(evidence["physical_observation"])
        sim_time_s = raw.get("simulation_time_s")
        if isinstance(sim_time_s, bool) or not isinstance(sim_time_s, (int, float)) \
                or not math.isfinite(sim_time_s) or sim_time_s < 0:
            sim_time_s = None
        if self._PHYSICS_KINDS[phase] == "support":
            # the raw numbers let a reader recompute this offline; the verified boolean is recorded
            # beside them so the audit states what the run actually concluded
            raw["supported"] = evidence["cup_supported"]
        self.audit.append_source("physics", {"kind": self._PHYSICS_KINDS[phase],
                                            "sim_time_s": sim_time_s,
                                            "release_epoch": evidence["release_epoch"],
                                            "observation": raw})

    def _event(self, kind: str, detail: str, physics_step: int, *, payload: dict | None = None) -> None:
        if self.audit is None:
            return
        # the event names the identity it belongs to and the monotonic instant it happened at; the
        # verified physics step lives in the kind's own payload instead of a generic detail string
        self.audit.append_source("events", {
            # a copy: the identity advances with the release epoch, and an event must keep the
            # identity it was emitted under rather than following later mutations
            "kind": kind, "identity": dict(self._event_identity), "sim_time_s": None,
            "monotonic_ns": int(self.clock_ns()) or 1,
            # a caller that owns the kind's schema supplies the payload; otherwise every terminal run outcome
            # names its reason and a phase event names its phase
            "payload": payload if payload is not None
            else ({"reason": detail, "physics_step": physics_step}
                  if kind in ("run_complete", "run_aborted", "run_incomplete_evidence")
                  else {"phase": detail, "physics_step": physics_step})})

    def _validate_request(self, request: dict) -> None:
        if not isinstance(request, dict) or set(request) != self._REQUEST_KEYS:
            raise PickPlaceError("TASK8_REQUEST_SCHEMA")
        if any(not isinstance(request[key], str) or not request[key] for key in (
            "scenario_id", "session_id", "attempt_id",
        )):
            raise PickPlaceError("TASK8_REQUEST_IDENTITY_INVALID")
        if type(request["deadline_ns"]) is not int or request["deadline_ns"] <= self.clock_ns():
            raise PickPlaceError("TASK8_DEADLINE_EXPIRED")
        mode = request["mode"]
        if mode == "full":
            if request["stop_after"] is not None or request["lifecycle"] != "FULL_RESTART":
                raise PickPlaceError("FULL_RESTART_REQUIRED")
        elif mode == "phase_prefix":
            if request["stop_after"] not in self.PHASES:
                raise PickPlaceError("TASK8_PREFIX_INVALID")
            if request["lifecycle"] != "FULL_RESTART":
                raise PickPlaceError("FULL_RESTART_REQUIRED")
        else:
            raise PickPlaceError("TASK8_MODE_INVALID")

    @staticmethod
    def _scope(evidence: dict, request: dict, reset_epoch: int, release_epoch: int) -> bool:
        return (
            evidence.get("session_id") == request["session_id"]
            and evidence.get("attempt_id") == request["attempt_id"]
            and type(evidence.get("reset_epoch")) is int
            and evidence["reset_epoch"] == reset_epoch
            and type(evidence.get("release_epoch")) is int
            and evidence["release_epoch"] == release_epoch
        )

    def _verify_phase(
        self, phase: str, evidence: dict, request: dict,
        reset_epoch: int, release_epoch: int, after_step: int,
    ) -> int:
        if (not isinstance(evidence, dict)
                or set(evidence) not in (self._EVIDENCE_KEYS,
                                         self._EVIDENCE_KEYS | {"physical_observation"})):
            raise PickPlaceError("PHASE_EVIDENCE_INVALID")
        if "physical_observation" in evidence and not self._raw(evidence["physical_observation"]):
            raise PickPlaceError("PHASE_EVIDENCE_INVALID")
        if evidence["phase"] != phase or not self._scope(evidence, request, reset_epoch, release_epoch):
            raise PickPlaceError("PHASE_EVIDENCE_INVALID")
        step = evidence["physics_step"]
        if type(step) is not int or step <= after_step:
            raise PickPlaceError("PHASE_EVIDENCE_INVALID")
        if evidence["manual_intervention"] is not False or evidence["moveit_recovery"] is not False:
            raise PickPlaceError("HUMAN_OR_RECOVERY_INTERVENTION")
        failing = [key for key in self._EVIDENCE_GATES if evidence[key] is not True]
        if failing:
            # named, because a gate that is not True says which one it was - the same reason every other refusal in
            # this task names what it wants rather than reporting a category
            raise PickPlaceError(f"PHASE_EVIDENCE_INVALID: gates not established: {failing}")
        supported_close = (phase == "CLOSE" and evidence["holding_state"] == "APPROACHING"
                           and evidence["bilateral_contact"] is True and evidence["cup_supported"] is True)
        if evidence["holding_state"] not in ("EMPTY", "HOLDING") and not supported_close:
            raise PickPlaceError("HOLDING_UNKNOWN")
        if phase == "CLOSE" and evidence["bilateral_contact"] is not True:
            raise PickPlaceError("BILATERAL_CONTACT_MISSING")
        if phase in ("MICRO_LIFT", "TRANSPORT", "ALIGN") and not (
            evidence["holding_state"] == "HOLDING"
            and evidence["bilateral_contact"] is True
            and evidence["micro_lift_confirmed"] is True
            and evidence["cup_off_table"] is True
            and evidence["cup_supported"] is False
        ):
            raise PickPlaceError("HOLD_NOT_CONFIRMED")
        if phase in ("RELEASE", "RADIAL_RETREAT", "FINAL_CHECK") and not (
            evidence["holding_state"] == "EMPTY"
            and evidence["released"] is True
            and evidence["cup_supported"] is True
            and evidence["no_fingertip_contact"] is True
        ):
            raise PickPlaceError("RELEASE_NOT_CONFIRMED")
        if phase == "FINAL_CHECK" and not (
            evidence["placement_stable"] is True and evidence["retreat_stable"] is True
        ):
            raise PickPlaceError("FINAL_PLACEMENT_INVALID")
        return step

    def _set_down(self, request: dict, reset_epoch: int,
                  release_epoch: int, after_step: int) -> int:
        evidence = self.port.set_down(request)
        if (not isinstance(evidence, dict) or set(evidence) != self._SET_DOWN_KEYS
                or not self._scope(evidence, request, reset_epoch, release_epoch)
                or type(evidence["physics_step"]) is not int
                or evidence["physics_step"] <= after_step
                or evidence["holding_state"] not in ("HOLDING", "APPROACHING")
                or any(evidence[key] is not True for key in (
                    "cup_supported", "bilateral_contact", "controller_stopped",
                    "controller_reference_ok", "joint_feedback_ok",
                    "planning_attached", "contact_ok", "mujoco_ok", "planning_scene_ok",
                    "head_rgb_ok", "wrist_rgb_ok",
                ))):
            raise PickPlaceError("SET_DOWN_EVIDENCE_INVALID")
        return evidence["physics_step"]

    def _release_preflight(
        self, request: dict, reset_epoch: int, release_epoch: int, after_step: int,
    ) -> int:
        evidence = self.port.release_preflight(request)
        if not isinstance(evidence, dict) or set(evidence) != self._RELEASE_KEYS:
            raise PickPlaceError("RELEASE_PREFLIGHT_INVALID")
        if not self._scope(evidence, request, reset_epoch, release_epoch):
            raise PickPlaceError("RELEASE_PREFLIGHT_INVALID")
        if (type(evidence["physics_step"]) is not int
                or evidence["physics_step"] <= after_step):
            raise PickPlaceError("RELEASE_PREFLIGHT_INVALID")
        if not (evidence["holding_state"] in ("HOLDING", "APPROACHING") and evidence["cup_supported"] is True
                and evidence["bilateral_contact"] is True
                and evidence["fresh"] is True and evidence["planning_attached"] is True):
            raise PickPlaceError("RELEASE_UNSUPPORTED")
        if self.port.detach_moveit(request) is not True:
            raise PickPlaceError("DETACH_NOT_CONFIRMED")
        # source alignment's apply record: the planning-scene interaction that changed what MoveIt holds. The instant stays null
        # because no publication covered it, which is the protocol's own rule rather than a value from another clock.
        self._event("alignment_apply", "detach_moveit", evidence["physics_step"],
                    payload={"apply_event_id": "detach_moveit:" + str(evidence["attempt_id"]),
                             "applied_at_s": None, "accepted": True})
        if self.port.planning_attached(request) is not False:
            raise PickPlaceError("DETACH_NOT_CONFIRMED")
        # source alignment's query and its receipt: the query is the question asked of the consumer, the receipt is the answer
        self._event("alignment_query", "planning_attached", evidence["physics_step"],
                    payload={"query_id": "planning_attached:" + str(evidence["attempt_id"]),
                             "query_at_s": None, "request_bytes": 0, "response_bytes": 1})
        self._event("alignment_receipt", "release_preflight", evidence["physics_step"],
                    payload={"receipt_id": "release_preflight:" + str(evidence["attempt_id"]),
                             "received_at_s": None, "clock_source": None, "uncertainty_s": None})
        return evidence["physics_step"]

    def _stop(self, reason: str, request: dict) -> None:
        try:
            confirmed = self.port.safe_stop(reason, request)
        except BaseException as error:
            raise PickPlaceError("STOP_NOT_CONFIRMED") from error
        if confirmed is not True:
            raise PickPlaceError("STOP_NOT_CONFIRMED")

    def run(self, request: dict) -> dict:
        self._validate_request(request)
        if self._ran:
            # one runner owns one attempt: a second run would otherwise let an early failure attribute
            # its events to the previous attempt's identity
            raise PickPlaceError("TASK8_RUNNER_REUSED")
        self._ran = True
        started = False
        latest_step = 0
        try:
            # begin may perform a reset before its response is lost. Treat even an
            # uncertain begin as task-owned activity that requires physical stop.
            started = True
            beginning = self.port.begin(request)
            if not isinstance(beginning, dict) or set(beginning) != self._BEGIN_KEYS:
                raise PickPlaceError("BEGIN_EVIDENCE_INVALID")
            if (beginning["session_id"] != request["session_id"]
                    or beginning["attempt_id"] != request["attempt_id"]
                    or type(beginning["reset_epoch"]) is not int
                    or type(beginning["release_epoch"]) is not int
                    or beginning["reset_epoch"] < 0 or beginning["release_epoch"] < 0
                    or type(beginning["full_restart"]) is not bool):
                raise PickPlaceError("BEGIN_EVIDENCE_INVALID")
            if not beginning["full_restart"]:
                raise PickPlaceError("FULL_RESTART_NOT_PROVED")
            reset_epoch = beginning["reset_epoch"]
            release_epoch = beginning["release_epoch"]
            self._event_identity = {"session_id": request["session_id"],
                                    "attempt_id": request["attempt_id"],
                                    "reset_epoch": reset_epoch, "release_epoch": release_epoch}
            # T3-F3(c): a formal writer admits a registered lease, and its events may not omit it
            _lease = getattr(self.audit, "identity", None)
            if isinstance(_lease, dict) and _lease.get("lease") is not None:
                self._event_identity["lease"] = _lease["lease"]
            # T3-F5 integration: a formal writer fences the first event against the initial epoch its own identity
            # declares, so the runner adopts that epoch instead of assuming zero and being refused
            if isinstance(_lease, dict) and type(_lease.get("release_epoch")) is int:
                self._event_identity["release_epoch"] = _lease["release_epoch"]
                release_epoch = _lease["release_epoch"]
            completed: list[str] = []
            for phase in self.PHASES:
                if request["deadline_ns"] <= self.clock_ns():
                    raise PickPlaceError("TASK8_DEADLINE_EXPIRED")
                if phase == "RELEASE":
                    latest_step = self._set_down(
                        request, reset_epoch, release_epoch, latest_step,
                    )
                    latest_step = self._release_preflight(
                        request, reset_epoch, release_epoch, latest_step,
                    )
                if phase == "RADIAL_RETREAT":
                    for direction, distance in (("radial", 0.01), ("vertical", 0.06)):
                        evidence = self.port.run_retreat_segment(direction, distance, request)
                        latest_step = self._verify_phase(
                            phase, evidence, request, reset_epoch, release_epoch, latest_step,
                        )
                        # every segment's raw observation is evidence the plan requires, so record
                        # each one rather than only the last segment the loop happened to leave behind
                        self._physics(phase, evidence)
                else:
                    evidence = self.port.run_phase(phase, request)
                    if phase == "RELEASE":
                        release_epoch += 1
                        # every event from here on belongs to the epoch the controller entered, so the
                        # audit never mixes pre-release support evidence into post-release outcomes
                        self._event_identity["release_epoch"] = release_epoch
                    latest_step = self._verify_phase(
                        phase, evidence, request, reset_epoch, release_epoch, latest_step,
                    )
                    if phase == "RELEASE":
                        # T3-F3(c)+(eighth verdict): the epoch advances before the verification, because that
                        # verification must judge the post-release evidence, but the event that names the epoch is
                        # emitted only after it - so the event records what was verified, not what was assumed, and
                        # the flags are stated rather than coerced or defaulted (`is True` can only refuse a gate)
                        self._event("release", "RELEASE", latest_step,
                                    payload={"release_epoch": release_epoch,
                                             "supported": evidence.get("cup_supported") is True,
                                             "no_fingertip_contact":
                                                 evidence.get("no_fingertip_contact") is True})
                if request["deadline_ns"] <= self.clock_ns():
                    raise PickPlaceError("TASK8_DEADLINE_EXPIRED")
                completed.append(phase)
                self._event("phase_complete", phase, latest_step)
                if phase != "RADIAL_RETREAT":
                    # the retreat loop already recorded each of its segments; recording again here
                    # would duplicate the last one under the same phase
                    self._physics(phase, evidence)
                if request["mode"] == "phase_prefix" and phase == request["stop_after"]:
                    self._stop("PHASE_PREFIX_COMPLETE", request)
                    # a prefix is never an episode: it must carry no live evidence artifact
                    return {"status": "PASSED", "completed_phases": completed,
                            "stopped_confirmed": True, "formal_episode_eligible": False,
                            "live_evidence_artifact": None}
            if self._missing_raw:
                # fail closed on the claim, not on the motion: without the raw observation of every
                # phase the run may finish, but it is never a formal episode and seals no live artifact
                self._stop("FULL_COMPLETE_INCOMPLETE_EVIDENCE", request)
                self._event("run_incomplete_evidence", "FORMAL_EVIDENCE_INCOMPLETE", latest_step)
                return {"status": "PASSED", "completed_phases": completed,
                        "stopped_confirmed": True, "formal_episode_eligible": False,
                        "live_evidence_artifact": None}
            # only a full case that reached FINAL_CHECK may seal its live evidence
            sealer = getattr(self.port, "seal_live_evidence", None)
            if not callable(sealer):
                raise PickPlaceError("LIVE_EVIDENCE_SEAL_UNAVAILABLE")
            artifact = sealer(request)
            if (type(artifact) is not dict
                    or set(artifact) != {"path", "sha256", "schema_version"}
                    or not isinstance(artifact["path"], str) or not artifact["path"]
                    or not isinstance(artifact["sha256"], str) or len(artifact["sha256"]) != 64
                    or type(artifact["schema_version"]) is not int):
                raise PickPlaceError("LIVE_EVIDENCE_ARTIFACT_INVALID")
            self._stop("FULL_COMPLETE", request)
            self._event("run_complete", "FULL_COMPLETE", latest_step)
            return {"status": "PASSED", "completed_phases": completed,
                    "stopped_confirmed": True, "formal_episode_eligible": True,
                    "live_evidence_artifact": artifact}
        except BaseException:
            if started:
                self._stop("TASK8_ABORT", request)
                self._event("run_aborted", "TASK8_ABORT", latest_step)
            raise
