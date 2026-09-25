"""Fixed Task 8 phase orchestration over an independently verified execution port.

This module makes no ROS calls. The port owns planning, controller, MuJoCo, contact,
camera and Planning Scene readback. A phase is complete only after all six execution
evidence gates and both camera gates agree for the same reset and attempt.
"""

from __future__ import annotations

import time
from typing import Protocol


class Task8Error(RuntimeError):
    """A phase boundary or physical stop could not be proved."""


class Task8Port(Protocol):
    def begin(self, request: dict) -> dict: ...
    def run_phase(self, phase: str, request: dict) -> dict: ...
    def release_preflight(self, request: dict) -> dict: ...
    def detach_moveit(self, request: dict) -> bool: ...
    def planning_attached(self, request: dict) -> bool: ...
    def run_retreat_segment(self, direction: str, distance_m: float, request: dict) -> dict: ...
    def safe_stop(self, reason: str, request: dict) -> bool: ...


class Task8Runner:
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
        "phase", "session_id", "attempt_id", "reset_epoch", "release_epoch",
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
        "session_id", "attempt_id", "reset_epoch", "release_epoch",
    })

    def __init__(self, port: Task8Port, *, clock_ns=time.monotonic_ns) -> None:
        self.port = port
        self.clock_ns = clock_ns

    def _validate_request(self, request: dict) -> None:
        if not isinstance(request, dict) or set(request) != self._REQUEST_KEYS:
            raise Task8Error("TASK8_REQUEST_SCHEMA")
        if any(not isinstance(request[key], str) or not request[key] for key in (
            "scenario_id", "session_id", "attempt_id",
        )):
            raise Task8Error("TASK8_REQUEST_IDENTITY_INVALID")
        if type(request["deadline_ns"]) is not int or request["deadline_ns"] <= self.clock_ns():
            raise Task8Error("TASK8_DEADLINE_EXPIRED")
        mode = request["mode"]
        if mode == "full":
            if request["stop_after"] is not None or request["lifecycle"] != "FULL_RESTART":
                raise Task8Error("FULL_RESTART_REQUIRED")
        elif mode == "phase_prefix":
            if request["stop_after"] not in self.PHASES or request["lifecycle"] not in (
                "FULL_RESTART", "RESET_WORLD",
            ):
                raise Task8Error("TASK8_PREFIX_INVALID")
        else:
            raise Task8Error("TASK8_MODE_INVALID")

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
        reset_epoch: int, release_epoch: int,
    ) -> None:
        if not isinstance(evidence, dict) or set(evidence) != self._EVIDENCE_KEYS:
            raise Task8Error("PHASE_EVIDENCE_INVALID")
        if evidence["phase"] != phase or not self._scope(evidence, request, reset_epoch, release_epoch):
            raise Task8Error("PHASE_EVIDENCE_INVALID")
        if evidence["manual_intervention"] is not False or evidence["moveit_recovery"] is not False:
            raise Task8Error("HUMAN_OR_RECOVERY_INTERVENTION")
        if any(evidence[key] is not True for key in self._EVIDENCE_GATES):
            raise Task8Error("PHASE_EVIDENCE_INVALID")
        if evidence["holding_state"] not in ("EMPTY", "HOLDING"):
            raise Task8Error("HOLDING_UNKNOWN")
        if phase == "CLOSE" and evidence["bilateral_contact"] is not True:
            raise Task8Error("BILATERAL_CONTACT_MISSING")
        if phase in ("MICRO_LIFT", "TRANSPORT", "ALIGN") and not (
            evidence["holding_state"] == "HOLDING"
            and evidence["bilateral_contact"] is True
            and evidence["micro_lift_confirmed"] is True
            and evidence["cup_off_table"] is True
        ):
            raise Task8Error("HOLD_NOT_CONFIRMED")
        if phase in ("RELEASE", "RADIAL_RETREAT", "FINAL_CHECK") and not (
            evidence["holding_state"] == "EMPTY"
            and evidence["released"] is True
            and evidence["cup_supported"] is True
            and evidence["no_fingertip_contact"] is True
        ):
            raise Task8Error("RELEASE_NOT_CONFIRMED")
        if phase == "FINAL_CHECK" and not (
            evidence["placement_stable"] is True and evidence["retreat_stable"] is True
        ):
            raise Task8Error("FINAL_PLACEMENT_INVALID")

    def _release_preflight(
        self, request: dict, reset_epoch: int, release_epoch: int,
    ) -> None:
        evidence = self.port.release_preflight(request)
        if not isinstance(evidence, dict) or set(evidence) != self._RELEASE_KEYS:
            raise Task8Error("RELEASE_PREFLIGHT_INVALID")
        if not self._scope(evidence, request, reset_epoch, release_epoch):
            raise Task8Error("RELEASE_PREFLIGHT_INVALID")
        if not (evidence["holding_state"] == "HOLDING" and evidence["cup_supported"] is True
                and evidence["fresh"] is True and evidence["planning_attached"] is True):
            raise Task8Error("RELEASE_UNSUPPORTED")
        if self.port.detach_moveit(request) is not True:
            raise Task8Error("DETACH_NOT_CONFIRMED")
        if self.port.planning_attached(request) is not False:
            raise Task8Error("DETACH_NOT_CONFIRMED")

    def _stop(self, reason: str, request: dict) -> None:
        try:
            confirmed = self.port.safe_stop(reason, request)
        except BaseException as error:
            raise Task8Error("STOP_NOT_CONFIRMED") from error
        if confirmed is not True:
            raise Task8Error("STOP_NOT_CONFIRMED")

    def run(self, request: dict) -> dict:
        self._validate_request(request)
        started = False
        try:
            # begin may perform a reset before its response is lost. Treat even an
            # uncertain begin as task-owned activity that requires physical stop.
            started = True
            beginning = self.port.begin(request)
            if not isinstance(beginning, dict) or set(beginning) != self._BEGIN_KEYS:
                raise Task8Error("BEGIN_EVIDENCE_INVALID")
            if (beginning["session_id"] != request["session_id"]
                    or beginning["attempt_id"] != request["attempt_id"]
                    or type(beginning["reset_epoch"]) is not int
                    or type(beginning["release_epoch"]) is not int
                    or beginning["reset_epoch"] < 0 or beginning["release_epoch"] < 0
                    or type(beginning["full_restart"]) is not bool):
                raise Task8Error("BEGIN_EVIDENCE_INVALID")
            if request["mode"] == "full" and not beginning["full_restart"]:
                raise Task8Error("FULL_RESTART_NOT_PROVED")
            reset_epoch = beginning["reset_epoch"]
            release_epoch = beginning["release_epoch"]
            completed: list[str] = []
            for phase in self.PHASES:
                if request["deadline_ns"] <= self.clock_ns():
                    raise Task8Error("TASK8_DEADLINE_EXPIRED")
                if phase == "RELEASE":
                    self._release_preflight(request, reset_epoch, release_epoch)
                if phase == "RADIAL_RETREAT":
                    for direction, distance in (("radial", 0.01), ("vertical", 0.06)):
                        evidence = self.port.run_retreat_segment(direction, distance, request)
                        self._verify_phase(phase, evidence, request, reset_epoch, release_epoch)
                else:
                    evidence = self.port.run_phase(phase, request)
                    if phase == "RELEASE":
                        release_epoch += 1
                    self._verify_phase(phase, evidence, request, reset_epoch, release_epoch)
                if request["deadline_ns"] <= self.clock_ns():
                    raise Task8Error("TASK8_DEADLINE_EXPIRED")
                completed.append(phase)
                if request["mode"] == "phase_prefix" and phase == request["stop_after"]:
                    self._stop("PHASE_PREFIX_COMPLETE", request)
                    return {"status": "PASSED", "completed_phases": completed,
                            "stopped_confirmed": True, "formal_episode_eligible": False}
            self._stop("FULL_COMPLETE", request)
            return {"status": "PASSED", "completed_phases": completed,
                    "stopped_confirmed": True, "formal_episode_eligible": True}
        except BaseException:
            if started:
                self._stop("TASK8_ABORT", request)
            raise
