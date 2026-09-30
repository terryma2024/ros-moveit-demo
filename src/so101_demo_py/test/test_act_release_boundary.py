"""Task 3: the release boundary holds instead of opening.

The runner may only ask the controller to open after a fresh, supported, detached preflight, every
refusal must stop the run rather than release the cup, and a release is only accepted under the
release epoch the controller actually entered. The fake port below is faithful enough to complete a
full run (the positive control proves it opens exactly once), so each negative control shows that the
missing precondition stops the run with no open at all or refuses the stale observation.
"""

from __future__ import annotations

import pytest

from so101_demo.act.pick_place_runner import PickPlaceRunner
from so101_demo.act.pick_place_runner import PickPlaceError


def request():
    return {"mode": "full", "stop_after": None, "lifecycle": "FULL_RESTART",
            "scenario_id": "default", "session_id": "s", "attempt_id": "a",
            "deadline_ns": 10 ** 18}


class FakePort:
    def __init__(self, *, cup_supported=True, detach=True, stale_set_down=False,
                 release_phase_epoch=2):
        self.cup_supported = cup_supported
        self.detach = detach
        self.stale_set_down = stale_set_down
        self.release_phase_epoch = release_phase_epoch
        self.attached = True
        self.step = 0
        self.opened = []
        self.stops = []

    def _next(self):
        self.step += 1
        return self.step

    def _evidence(self, phase, epoch, **overrides):
        record = {"phase": phase, "session_id": "s", "attempt_id": "a", "reset_epoch": 1,
                  "release_epoch": epoch, "physics_step": self._next(),
                  "planning_ok": True, "controller_reference_ok": True, "joint_feedback_ok": True,
                  "contact_ok": True, "mujoco_ok": True, "planning_scene_ok": True,
                  "head_rgb_ok": True, "wrist_rgb_ok": True, "manual_intervention": False,
                  "moveit_recovery": False, "holding_state": "EMPTY", "bilateral_contact": False,
                  "micro_lift_confirmed": False, "cup_off_table": False, "cup_supported": False,
                  "released": False, "no_fingertip_contact": False, "placement_stable": True,
                  "retreat_stable": True,
                  "physical_observation": {"simulation_time_s": round(0.1 * self.step, 4),
                                           "simulation_step": self.step,
                                           "left_contact_count": 2, "right_contact_count": 2,
                                           "table_contact": phase in ("RELEASE", "RADIAL_RETREAT",
                                                                      "FINAL_CHECK"),
                                           "maximum_normal_force_n": 0.5,
                                           "other_contact_geoms": ["table_collision"],
                                           "cup_position_world_m": [0.02, -0.28, 0.165]}}
        record.update(overrides)
        return record

    def begin(self, request):
        return {"session_id": "s", "attempt_id": "a", "reset_epoch": 1, "release_epoch": 1,
                "full_restart": True}

    def run_phase(self, phase, request):
        if phase in ("SEARCH", "APPROACH"):
            return self._evidence(phase, 1)
        if phase == "CLOSE":
            return self._evidence(phase, 1, bilateral_contact=True)
        if phase in ("MICRO_LIFT", "TRANSPORT", "ALIGN"):
            return self._evidence(phase, 1, holding_state="HOLDING", bilateral_contact=True,
                                  micro_lift_confirmed=True, cup_off_table=True)
        # RELEASE and everything after it belong to the release epoch the controller entered; only
        # the RELEASE phase itself is an open request
        if phase == "RELEASE":
            self.opened.append(phase)
        return self._evidence(phase, self.release_phase_epoch, holding_state="EMPTY",
                              released=True, cup_supported=True, no_fingertip_contact=True)

    def run_retreat_segment(self, direction, distance, request):
        return self._evidence("RADIAL_RETREAT", self.release_phase_epoch, holding_state="EMPTY",
                              released=True, cup_supported=True, no_fingertip_contact=True)

    def set_down(self, request):
        step = self.step if self.stale_set_down else self._next()
        return {"session_id": "s", "attempt_id": "a", "reset_epoch": 1, "release_epoch": 1,
                "physics_step": step, "holding_state": "HOLDING", "cup_supported": True,
                "bilateral_contact": True, "controller_stopped": True,
                "controller_reference_ok": True, "joint_feedback_ok": True,
                "planning_attached": True, "contact_ok": True, "mujoco_ok": True,
                "planning_scene_ok": True, "head_rgb_ok": True, "wrist_rgb_ok": True}

    def release_preflight(self, request):
        return {"holding_state": "HOLDING", "cup_supported": self.cup_supported, "fresh": True,
                "planning_attached": self.attached, "session_id": "s", "attempt_id": "a",
                "reset_epoch": 1, "release_epoch": 1, "physics_step": self._next()}

    def detach_moveit(self, request):
        if not self.detach:
            return False
        self.attached = False
        return True

    def planning_attached(self, request):
        return self.attached

    def safe_stop(self, reason, request):
        self.stops.append(reason)
        return True

    def seal_live_evidence(self, request):
        return {"path": "/tmp/live-evidence.json", "sha256": "a" * 64, "schema_version": 2}


def test_the_positive_control_opens_exactly_once_at_the_release_phase():
    port = FakePort()
    result = PickPlaceRunner(port).run(request())
    assert result["status"] == "PASSED"
    assert result["completed_phases"] == list(PickPlaceRunner.PHASES)
    assert port.opened == ["RELEASE"]
    assert port.stops == ["FULL_COMPLETE"]
    assert result["live_evidence_artifact"]["schema_version"] == 2


def test_a_detach_failure_never_opens_and_stops_instead():
    """A cup still attached to the planning scene may not be released."""

    port = FakePort(detach=False)
    with pytest.raises(PickPlaceError, match="DETACH_NOT_CONFIRMED"):
        PickPlaceRunner(port).run(request())
    assert port.opened == []
    assert port.stops == ["TASK8_ABORT"]


def test_an_unsupported_cup_is_held_not_released():
    port = FakePort(cup_supported=False)
    with pytest.raises(PickPlaceError, match="RELEASE_UNSUPPORTED"):
        PickPlaceRunner(port).run(request())
    assert port.opened == []
    assert port.stops == ["TASK8_ABORT"]


def test_a_stale_set_down_observation_is_refused_before_any_open():
    port = FakePort(stale_set_down=True)
    with pytest.raises(PickPlaceError, match="SET_DOWN_EVIDENCE_INVALID"):
        PickPlaceRunner(port).run(request())
    assert port.opened == []
    assert port.stops == ["TASK8_ABORT"]


def test_a_release_observation_from_the_old_epoch_is_refused():
    """The release evidence must carry the release epoch the controller actually entered."""

    port = FakePort(release_phase_epoch=1)
    with pytest.raises(PickPlaceError, match="PHASE_EVIDENCE_INVALID"):
        PickPlaceRunner(port).run(request())
    assert port.opened == ["RELEASE"]
    assert port.stops == ["TASK8_ABORT"]


class RecordingAudit:
    def __init__(self):
        self.events = []
        self.physics = []

    def append_source(self, kind, record):
        assert kind in ("events", "physics")
        (self.events if kind == "events" else self.physics).append(record)


def test_the_audit_receives_the_events_the_run_actually_produced():
    """Phase names come from the run's own verified boundaries, not from a preset list."""

    audit = RecordingAudit()
    port = FakePort()
    PickPlaceRunner(port, audit=audit).run(request())
    assert [(event["kind"], event["payload"].get("phase") or event["payload"].get("reason"))
            for event in audit.events] == (
        [("phase_complete", phase) for phase in PickPlaceRunner.PHASES]
        + [("run_complete", "FULL_COMPLETE")])
    assert [event["payload"]["physics_step"] for event in audit.events] == sorted(
        event["payload"]["physics_step"] for event in audit.events)
    assert all(event["sim_time_s"] is None for event in audit.events)
    assert all(event["identity"]["session_id"] == "s" for event in audit.events)
    assert all(event["monotonic_ns"] >= 1 for event in audit.events)


def test_an_aborted_run_records_its_abort_and_no_phase_it_did_not_verify():
    audit = RecordingAudit()
    port = FakePort(detach=False)
    with pytest.raises(PickPlaceError, match="DETACH_NOT_CONFIRMED"):
        PickPlaceRunner(port, audit=audit).run(request())
    kinds = [event["kind"] for event in audit.events]
    assert kinds.count("run_aborted") == 1
    assert "RELEASE" not in [event["payload"].get("phase") for event in audit.events]
    assert "run_complete" not in kinds


class PhysicsAudit:
    def __init__(self):
        self.physics = []
        self.events = []

    def append_source(self, kind, record):
        (self.physics if kind == "physics" else self.events).append(record)


def test_a_malformed_physical_observation_is_refused():
    """A raw block that is not finite numbers and booleans may not enter the audit."""

    port = FakePort()
    original = port.run_phase

    def poisoned(phase, request):
        evidence = original(phase, request)
        evidence["physical_observation"]["left_contact_count"] = "two"
        return evidence

    port.run_phase = poisoned
    with pytest.raises(PickPlaceError, match="PHASE_EVIDENCE_INVALID"):
        PickPlaceRunner(port, audit=PhysicsAudit()).run(request())


def test_a_completed_run_records_offline_recomputable_physics_rows():
    audit = PhysicsAudit()
    port = FakePort()
    PickPlaceRunner(port, audit=audit).run(request())
    assert [row["kind"] for row in audit.physics] == [
        "pose", "pose", "contact", "support", "support", "pose", "contact", "retract", "pose"]
    assert all(row["release_epoch"] in (1, 2) for row in audit.physics)
    assert all(row["sim_time_s"] is not None for row in audit.physics)
    # the recorded rows alone must be enough to recompute the release-epoch physical criteria
    released = [row for row in audit.physics if row["kind"] in ("contact", "retract", "pose")
                and row["release_epoch"] == 2]
    assert released and all(row["observation"]["table_contact"] is True for row in released)
    supported = [row for row in audit.physics if row["kind"] == "support"]
    assert supported and all(row["observation"]["supported"] is False for row in supported)
    assert all(row["observation"]["maximum_normal_force_n"] <= 20.0 for row in audit.physics)


def test_a_port_that_cannot_observe_physics_still_runs_and_says_so():
    """The raw block is optional, so a port without it records no physics rather than a fake one."""

    port = FakePort()
    original_phase, original_retreat = port.run_phase, port.run_retreat_segment

    def blind(phase, request):
        evidence = original_phase(phase, request)
        evidence.pop("physical_observation")
        return evidence

    def blind_retreat(direction, distance, request):
        evidence = original_retreat(direction, distance, request)
        evidence.pop("physical_observation")
        return evidence

    port.run_phase, port.run_retreat_segment = blind, blind_retreat
    audit = PhysicsAudit()
    result = PickPlaceRunner(port, audit=audit).run(request())
    assert result["status"] == "PASSED"
    assert audit.physics == []


def test_post_release_events_carry_the_release_epoch():
    """Events emitted after RELEASE must not keep the pre-release epoch (T3-F7)."""

    audit = RecordingAudit()
    port = FakePort()
    PickPlaceRunner(port, audit=audit).run(request())
    epochs = [(event["kind"], event["payload"].get("phase"), event["identity"]["release_epoch"])
              for event in audit.events]
    assert all(epoch == 1 for _, phase, epoch in epochs if phase in ("SEARCH", "CLOSE", "ALIGN"))
    for _, phase, epoch in epochs:
        if phase in ("RELEASE", "FINAL_CHECK"):
            assert epoch == 2
    assert epochs[-1][0] == "run_complete" and epochs[-1][2] == 2


def test_a_runner_is_one_shot_so_an_early_failure_cannot_inherit_an_identity():
    """A second attempt must not attribute its events to the previous attempt (T3-F7 minor)."""

    audit = RecordingAudit()
    port = FakePort(detach=False)
    runner = PickPlaceRunner(port, audit=audit)
    with pytest.raises(PickPlaceError, match="DETACH_NOT_CONFIRMED"):
        runner.run(request())
    recorded = len(audit.events)
    with pytest.raises(PickPlaceError, match="TASK8_RUNNER_REUSED"):
        runner.run(request())
    assert len(audit.events) == recorded
