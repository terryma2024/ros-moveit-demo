"""Task 8's phase boundaries must fail closed before a live adapter is attached."""

from __future__ import annotations

import time

import pytest

from so101_demo.act.pick_place_runner import PickPlaceRunner, PickPlaceError


def request(mode="phase_prefix", stop_after="MICRO_LIFT", lifecycle="FULL_RESTART"):
    return {
        "mode": mode, "stop_after": stop_after, "lifecycle": lifecycle,
        "scenario_id": "scene-1", "session_id": "session-1", "attempt_id": "attempt-1",
        "deadline_ns": time.monotonic_ns() + 10**10,
    }


class FakePort:
    def __init__(self):
        self.calls = []
        self.fail_phase = None
        self.stop_confirmed = True
        self.intervention = False
        self.supported = True
        self.attached = True
        self.release_epoch = 0
        self.physics_step = 0
        self.sealed = 0
        self.root = __import__("pathlib").Path(".")

    def begin(self, req):
        self.calls.append(("begin", req["lifecycle"]))
        return {"session_id": req["session_id"], "attempt_id": req["attempt_id"],
                "reset_epoch": 4, "release_epoch": 0,
                "full_restart": req["lifecycle"] == "FULL_RESTART"}

    def evidence(self, phase, req):
        self.physics_step += 1
        return {
            "phase": phase, "session_id": req["session_id"], "attempt_id": req["attempt_id"],
            "reset_epoch": 4, "release_epoch": self.release_epoch,
            "physics_step": self.physics_step,
            "planning_ok": True, "controller_reference_ok": True, "joint_feedback_ok": True,
            "contact_ok": True, "mujoco_ok": True, "planning_scene_ok": True,
            "head_rgb_ok": True, "wrist_rgb_ok": True,
            "manual_intervention": self.intervention, "moveit_recovery": False,
            "holding_state": "EMPTY" if phase in ("SEARCH", "APPROACH", "CLOSE", "RELEASE", "RADIAL_RETREAT", "FINAL_CHECK") else "HOLDING",
            "bilateral_contact": phase in ("CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN"),
            "micro_lift_confirmed": phase in ("MICRO_LIFT", "TRANSPORT", "ALIGN"),
            "cup_off_table": phase in ("MICRO_LIFT", "TRANSPORT", "ALIGN"),
            "cup_supported": self.supported and phase not in ("MICRO_LIFT", "TRANSPORT", "ALIGN"),
            "released": phase in ("RELEASE", "RADIAL_RETREAT", "FINAL_CHECK"),
            "no_fingertip_contact": True, "placement_stable": True, "retreat_stable": True,
        }

    def run_phase(self, phase, req):
        self.calls.append(("phase", phase))
        if phase == "RELEASE":
            self.release_epoch += 1
        result = self.evidence(phase, req)
        if phase == self.fail_phase:
            result["contact_ok"] = False
        return result

    def release_preflight(self, req):
        self.calls.append(("release_preflight", None))
        self.physics_step += 1
        return {"holding_state": "HOLDING", "cup_supported": self.supported,
                "fresh": True, "planning_attached": self.attached,
                "session_id": req["session_id"], "attempt_id": req["attempt_id"],
                "reset_epoch": 4, "release_epoch": self.release_epoch,
                "physics_step": self.physics_step}

    def set_down(self, req):
        self.calls.append(("set_down", None))
        self.physics_step += 1
        return {"session_id": req["session_id"], "attempt_id": req["attempt_id"],
                "reset_epoch": 4, "release_epoch": self.release_epoch,
                "physics_step": self.physics_step,
                "holding_state": "HOLDING", "cup_supported": self.supported,
                "bilateral_contact": True, "controller_stopped": True,
                "controller_reference_ok": True, "joint_feedback_ok": True,
                "planning_attached": self.attached, "contact_ok": True,
                "mujoco_ok": True, "planning_scene_ok": True,
                "head_rgb_ok": True, "wrist_rgb_ok": True}

    def detach_moveit(self, req):
        self.calls.append(("detach_moveit", None))
        self.attached = False
        return True

    def planning_attached(self, req):
        self.calls.append(("planning_attached", None))
        return self.attached

    def run_retreat_segment(self, direction, distance_m, req):
        self.calls.append(("retreat", direction, distance_m))
        return self.evidence("RADIAL_RETREAT", req)

    def seal_live_evidence(self, req):
        self.sealed += 1
        return {"path": str(self.root / "live.json"), "sha256": "c" * 64, "schema_version": 1}

    def safe_stop(self, reason, req):
        self.calls.append(("safe_stop", reason))
        return self.stop_confirmed


def test_prefix_stops_after_exact_phase_and_never_counts_as_formal():
    port = FakePort()
    result = PickPlaceRunner(port).run(request())
    assert result["completed_phases"] == list(PickPlaceRunner.PHASES[:4])
    assert result["formal_episode_eligible"] is False
    assert result["stopped_confirmed"] is True
    assert port.calls[-1] == ("safe_stop", "PHASE_PREFIX_COMPLETE")
    assert ("phase", "TRANSPORT") not in port.calls


def test_full_requires_fresh_restart_before_any_phase():
    port = FakePort()
    with pytest.raises(PickPlaceError, match="FULL_RESTART_REQUIRED"):
        PickPlaceRunner(port).run(request("full", None, "REUSE_STACK"))
    assert port.calls == []


def test_prefix_rejects_world_reset_before_begin():
    port = FakePort()
    with pytest.raises(PickPlaceError, match="FULL_RESTART_REQUIRED"):
        PickPlaceRunner(port).run(request("phase_prefix", "SEARCH", "RESET_WORLD"))
    assert port.calls == []


def test_prefix_rejects_unproved_restart_before_search_and_stops():
    class UnprovedRestart(FakePort):
        def begin(self, req):
            result = super().begin(req)
            result["full_restart"] = False
            return result

    port = UnprovedRestart()
    with pytest.raises(PickPlaceError, match="FULL_RESTART_NOT_PROVED"):
        PickPlaceRunner(port).run(request("phase_prefix", "SEARCH"))
    assert not any(call[0] == "phase" for call in port.calls)
    assert port.calls[-1] == ("safe_stop", "TASK8_ABORT")


def test_release_detaches_before_opening_and_retreat_has_two_ordered_segments():
    port = FakePort()
    result = PickPlaceRunner(port).run(request("full", None))
    assert result["completed_phases"] == list(PickPlaceRunner.PHASES)
    assert result["formal_episode_eligible"] is True
    assert port.calls.index(("detach_moveit", None)) < port.calls.index(("phase", "RELEASE"))
    assert port.calls.index(("planning_attached", None)) < port.calls.index(("phase", "RELEASE"))
    assert [call for call in port.calls if call[0] == "retreat"] == [
        ("retreat", "radial", 0.01), ("retreat", "vertical", 0.06)]


def test_unsupported_release_never_sends_detach_or_open():
    port = FakePort()
    port.supported = False
    with pytest.raises(PickPlaceError, match="SET_DOWN_EVIDENCE_INVALID"):
        PickPlaceRunner(port).run(request("full", None))
    assert ("detach_moveit", None) not in port.calls
    assert ("phase", "RELEASE") not in port.calls
    assert port.calls[-1][0] == "safe_stop"


def test_bad_contact_or_human_intervention_stops_and_invalidates_full():
    for failure in ("contact", "intervention"):
        port = FakePort()
        if failure == "contact":
            port.fail_phase = "TRANSPORT"
        else:
            port.intervention = True
        with pytest.raises(PickPlaceError, match="PHASE_EVIDENCE_INVALID|HUMAN_OR_RECOVERY_INTERVENTION"):
            PickPlaceRunner(port).run(request("full", None))
        assert port.calls[-1][0] == "safe_stop"


def test_stop_without_physical_confirmation_is_indeterminate():
    port = FakePort()
    port.stop_confirmed = False
    with pytest.raises(PickPlaceError, match="STOP_NOT_CONFIRMED"):
        PickPlaceRunner(port).run(request())


def test_begin_failure_still_requests_stop_because_reset_may_have_started():
    class FailingBegin(FakePort):
        def begin(self, req):
            self.calls.append(("begin", req["lifecycle"]))
            raise RuntimeError("reset response lost")

    port = FailingBegin()
    with pytest.raises(RuntimeError, match="reset response lost"):
        PickPlaceRunner(port).run(request())
    assert port.calls[-1] == ("safe_stop", "TASK8_ABORT")


def test_release_requires_new_epoch_evidence():
    class StaleRelease(FakePort):
        def run_phase(self, phase, req):
            if phase == "RELEASE":
                self.calls.append(("phase", phase))
                return self.evidence(phase, req)
            return super().run_phase(phase, req)

    port = StaleRelease()
    with pytest.raises(PickPlaceError, match="PHASE_EVIDENCE_INVALID"):
        PickPlaceRunner(port).run(request("full", None))
    assert port.calls[-1][0] == "safe_stop"


def test_full_set_down_occurs_after_suspended_align_and_before_detach():
    port = FakePort()
    PickPlaceRunner(port).run(request("full", None))
    assert port.calls.index(("phase", "ALIGN")) < port.calls.index(("set_down", None))
    assert port.calls.index(("set_down", None)) < port.calls.index(("release_preflight", None))
    assert port.calls.index(("release_preflight", None)) < port.calls.index(("detach_moveit", None))
    assert port.calls.index(("detach_moveit", None)) < port.calls.index(("phase", "RELEASE"))


def test_set_down_must_prove_new_supported_step_before_detach_or_open():
    class StaleSetDown(FakePort):
        def set_down(self, req):
            result = super().set_down(req)
            result["physics_step"] -= 1
            return result

    port = StaleSetDown()
    with pytest.raises(PickPlaceError, match="SET_DOWN_EVIDENCE_INVALID"):
        PickPlaceRunner(port).run(request("full", None))
    assert ("detach_moveit", None) not in port.calls
    assert ("phase", "RELEASE") not in port.calls
    assert port.calls[-1] == ("safe_stop", "TASK8_ABORT")


@pytest.mark.parametrize("missing", ["controller_reference_ok", "joint_feedback_ok"])
def test_set_down_requires_controller_reference_and_feedback(missing):
    class MissingControllerEvidence(FakePort):
        def set_down(self, req):
            result = super().set_down(req)
            result[missing] = False
            return result

    port = MissingControllerEvidence()
    with pytest.raises(PickPlaceError, match="SET_DOWN_EVIDENCE_INVALID"):
        PickPlaceRunner(port).run(request("full", None))
    assert ("detach_moveit", None) not in port.calls
    assert ("phase", "RELEASE") not in port.calls
