"""Fixed pick-place phase orchestration over an independently verified execution port.

This module makes no ROS calls. The port owns planning, controller, MuJoCo, contact,
camera and Planning Scene readback. A phase is complete only after all six execution
evidence gates and both camera gates agree for the same reset and attempt.
"""

from __future__ import annotations

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
    _EVIDENCE_GATES = (
        "planning_ok", "controller_reference_ok", "joint_feedback_ok", "contact_ok",
        "mujoco_ok", "planning_scene_ok", "head_rgb_ok", "wrist_rgb_ok",
    )
    _RELEASE_KEYS = frozenset({
        "holding_state", "cup_supported", "fresh", "planning_attached",
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
                 window_factory=None) -> None:
        self.port = port
        self.clock_ns = clock_ns
        # optional: the live-evidence window this run records into, built by the child
        self.window_factory = window_factory

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
        if not isinstance(evidence, dict) or set(evidence) != self._EVIDENCE_KEYS:
            raise PickPlaceError("PHASE_EVIDENCE_INVALID")
        if evidence["phase"] != phase or not self._scope(evidence, request, reset_epoch, release_epoch):
            raise PickPlaceError("PHASE_EVIDENCE_INVALID")
        step = evidence["physics_step"]
        if type(step) is not int or step <= after_step:
            raise PickPlaceError("PHASE_EVIDENCE_INVALID")
        if evidence["manual_intervention"] is not False or evidence["moveit_recovery"] is not False:
            raise PickPlaceError("HUMAN_OR_RECOVERY_INTERVENTION")
        if any(evidence[key] is not True for key in self._EVIDENCE_GATES):
            raise PickPlaceError("PHASE_EVIDENCE_INVALID")
        if evidence["holding_state"] not in ("EMPTY", "HOLDING"):
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
                or evidence["holding_state"] != "HOLDING"
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
        if not (evidence["holding_state"] == "HOLDING" and evidence["cup_supported"] is True
                and evidence["fresh"] is True and evidence["planning_attached"] is True):
            raise PickPlaceError("RELEASE_UNSUPPORTED")
        if self.port.detach_moveit(request) is not True:
            raise PickPlaceError("DETACH_NOT_CONFIRMED")
        if self.port.planning_attached(request) is not False:
            raise PickPlaceError("DETACH_NOT_CONFIRMED")
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
        started = False
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
            latest_step = 0
            window = None
            if self.window_factory is not None:
                # the window opens on the first verified phase (SEARCH); the runner owns its lifetime
                # build the window only; its grid samples come from the port's readback so no sample is
                # synthesised here, and the first verified phase (SEARCH) opens it
                window = self.window_factory({
                    "case_id": request.get("case_id") or request["attempt_id"],
                    "session_id": request["session_id"], "attempt_id": request["attempt_id"],
                    "reset_epoch": reset_epoch, "release_epoch": release_epoch,
                })
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
                else:
                    evidence = self.port.run_phase(phase, request)
                    if phase == "RELEASE":
                        release_epoch += 1
                    latest_step = self._verify_phase(
                        phase, evidence, request, reset_epoch, release_epoch, latest_step,
                    )
                if request["deadline_ns"] <= self.clock_ns():
                    raise PickPlaceError("TASK8_DEADLINE_EXPIRED")
                completed.append(phase)
                if request["mode"] == "phase_prefix" and phase == request["stop_after"]:
                    self._stop("PHASE_PREFIX_COMPLETE", request)
                    # a prefix is never an episode: it must carry no live evidence artifact
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
            return {"status": "PASSED", "completed_phases": completed,
                    "stopped_confirmed": True, "formal_episode_eligible": True,
                    "live_evidence_artifact": artifact}
        except BaseException:
            if started:
                self._stop("TASK8_ABORT", request)
            raise


# Legacy Python API for version-one pick-place callers.
Task8Error = PickPlaceError
Task8Port = PickPlaceExecutionPort
Task8Runner = PickPlaceRunner
