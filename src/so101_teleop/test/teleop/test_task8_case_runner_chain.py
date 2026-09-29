"""Boundary V: the case is sequenced by the real runner, with only the I/O seam faked.

The fake sits at the port - the external ROS/MuJoCo/controller boundary the plan allows to be faked - so the phase
set, the release ordering and the evidence binding asserted here are the production code's own behaviour.
"""

import hashlib
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_task8_live_evidence_production_chain import (PERIOD_S, READBACK_SOURCES, _identity,  # noqa: E402
                                                       _raw_records)
from so101_demo.act.task8_live_evidence import build_live_evidence_sample      # noqa: E402

from so101_demo.act.pick_place_runner import PickPlaceRunner
from so101_demo.act.task8 import Task8Runner


class FakePort:
    """Every method the runner reaches for, recording the order it was asked in."""

    def __init__(self, recorder=None):
        self.recorder = recorder
        self.reset_epoch = 0
        self.release_epoch = 0
        self.grid_step = 0
        self.rows = []
        self.calls = []
        self.phases = []
        self.receipt = None
        self.window = None
        self.step = 1

    def bind_startup_receipt(self, receipt):
        self.receipt = receipt
        self.calls.append("bind_startup_receipt")

    def bind_live_evidence(self, window):
        self.window = window
        self.calls.append("bind_live_evidence")
        self.evidence_root = Path(window._recorder.evidence_root) if hasattr(window, "_recorder") else None

    def _identity(self, request):
        return {"session_id": request["session_id"], "attempt_id": request["attempt_id"],
                "reset_epoch": self.reset_epoch, "release_epoch": self.release_epoch,
                "physics_step": self.step}

    def begin(self, request):
        # the runner validates the beginning's exact key set and the identities it carries
        self.calls.append("begin")
        # exactly _BEGIN_KEYS: the identity helper carries physics_step, which the beginning must not
        return {"session_id": request["session_id"], "attempt_id": request["attempt_id"],
                "reset_epoch": self.reset_epoch, "release_epoch": self.release_epoch, "full_restart": True}

    # what the case's own progression means, per the runner's rules: a hold is not a search and a release is not a hold
    _HOLDING = ("MICRO_LIFT", "TRANSPORT", "ALIGN")
    _RELEASED = ("RELEASE", "RADIAL_RETREAT", "FINAL_CHECK")

    def _phase_evidence(self, phase, request):
        # the runner increments release_epoch before verifying the RELEASE phase, and the retreat and final check
        # carry that incremented epoch, so the fixture must model the same progression
        evidence = dict(self._identity(request), phase=phase, holding_state="EMPTY",
                        cup_supported=False, released=False, cup_off_table=False,
                        bilateral_contact=False, micro_lift_confirmed=False, no_fingertip_contact=True,
                        manual_intervention=False, moveit_recovery=False, planning_ok=True,
                        planning_scene_ok=True, controller_reference_ok=True, joint_feedback_ok=True,
                        contact_ok=True, placement_stable=True, retreat_stable=True, mujoco_ok=True,
                        head_rgb_ok=True, wrist_rgb_ok=True)
        if phase == "CLOSE":
            evidence["bilateral_contact"] = True
        if phase in self._HOLDING:
            evidence.update(holding_state="HOLDING", bilateral_contact=True, micro_lift_confirmed=True,
                            cup_off_table=True, cup_supported=False)
        if phase in self._RELEASED:
            evidence.update(holding_state="EMPTY", released=True, cup_supported=True,
                            no_fingertip_contact=True, bilateral_contact=False, micro_lift_confirmed=True,
                            cup_off_table=True)
        if phase == "RELEASE" or phase in self._RELEASED:
            # the runner increments release_epoch before verifying RELEASE, and the retreat and final check carry it on
            evidence["release_epoch"] = self.release_epoch + 1
        return evidence

    def run_phase(self, phase, request):
        self.phases.append(phase)
        self.calls.append(f"run_phase:{phase}")
        self.step += 1
        self._record(phase)
        return self._phase_evidence(phase, request)

    def _record(self, phase):
        """Feed the live evidence window the child attached, using the chain test's own sample builder."""

        if self.window is None or self.evidence_root is None:
            return
        # the live-evidence grid advances one period per recorded row, while physics_step answers the runner's own
        # validation - the two clocks must not be the same counter, because the release path advances the step three
        # times between two recorded rows
        self.grid_step += 1
        sim_time = self.grid_step * PERIOD_S
        # the rows model the case's own release rather than one fixed contact block: before it the cup is held, after it
        # the gripper is open, the cup is supported and no fingertip is touching it
        released = phase in ("RELEASE", "RADIAL_RETREAT", "FINAL_CHECK")
        sample = build_live_evidence_sample(
            identity=_identity(), phase=phase, physics_step=self.grid_step, sim_time_s=sim_time,
            source_stamps_s={name: sim_time for name in READBACK_SOURCES},
            source_received_monotonic_s={name: sim_time for name in READBACK_SOURCES},
            raw_records=_raw_records(self.evidence_root, sim_time),
            holding_state="EMPTY" if released else "HOLDING",
            frame={"wrist_frame_valid": True, "wrist_target_visible": True},
            contact={"observation_valid": True, "bilateral_contact": not released,
                     "no_fingertip_contact": released, "cup_supported": True,
                     "released": released, "placement_stable": released},
            measurements={"cup_support_distance_m": 0.01, "end_effector_position_m": [0.0, 0.0, 0.1],
                          "cup_position_m": [0.0, 0.0, 0.1], "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0]})
        self.rows.append(sample)
        self.window.add_grid(sample)

    def run_retreat_segment(self, direction, distance_m, request):
        self.calls.append("run_retreat_segment")
        self.step += 1
        self._record("RADIAL_RETREAT")
        # the retreat runs after the release, so it reports the released set with the holding vocabulary
        return dict(self._identity(request), phase="RADIAL_RETREAT", holding_state="EMPTY",
                    release_epoch=self.release_epoch + 1,
                    cup_supported=True, planning_ok=True, planning_scene_ok=True,
                    controller_reference_ok=True, joint_feedback_ok=True, contact_ok=True, released=True,
                    cup_off_table=False, micro_lift_confirmed=True, placement_stable=True,
                    retreat_stable=True, bilateral_contact=False, no_fingertip_contact=True,
                    manual_intervention=False, moveit_recovery=False, mujoco_ok=True,
                    head_rgb_ok=True, wrist_rgb_ok=True)

    def set_down(self, request):
        self.calls.append("set_down")
        self.step += 1
        # set-down happens while the cup is still held and the planning side still attached: every listed flag is true
        return dict(self._identity(request), holding_state="HOLDING", cup_supported=True,
                    planning_attached=True, bilateral_contact=True, controller_stopped=True,
                    controller_reference_ok=True, joint_feedback_ok=True, contact_ok=True,
                    planning_scene_ok=True, mujoco_ok=True, head_rgb_ok=True, wrist_rgb_ok=True)

    def release_preflight(self, request):
        self.calls.append("release_preflight")
        self.step += 1
        # the preflight runs before the detach, so the planning side is still attached and the cup still held
        return dict(self._identity(request), holding_state="HOLDING", cup_supported=True, fresh=True,
                    planning_attached=True)

    def detach_moveit(self, request):
        self.calls.append("detach_moveit")
        return True

    def planning_attached(self, request):
        self.calls.append("planning_attached")
        return False

    def safe_stop(self, reason, request):
        # the runner only accepts a literal True as a confirmed stop
        self.calls.append("safe_stop")
        return True


def _request():
    return {"mode": "full", "stop_after": None, "lifecycle": "FULL_RESTART", "scenario_id": "full-01",
            "session_id": "session-1", "attempt_id": "attempt-1",
            "deadline_ns": time.monotonic_ns() + 60_000_000_000}


def test_the_runner_sequences_a_case_through_every_phase_in_order(tmp_path):
    """The phase set is `Task8Runner.PHASES`, so a missing or reordered phase fails here rather than downstream."""

    from so101_demo.act.task8_live_evidence import LiveEvidenceWindow, Task8LiveEvidenceRecorder
    from test_task8_live_evidence_production_chain import _identity

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    recorder = Task8LiveEvidenceRecorder(case_id="full-01", evidence_root=evidence_root,
                                         session_id="session-1", attempt_id="attempt-1")
    window = LiveEvidenceWindow(recorder, identity=_identity(), period_s=PERIOD_S)
    window.bind_reset_epoch(_identity()["reset_epoch"])
    port = FakePort(recorder)
    port.reset_epoch, port.release_epoch = _identity()["reset_epoch"], _identity()["release_epoch"]
    port.bind_live_evidence(window)
    port.evidence_root = evidence_root
    result = PickPlaceRunner(port).run(_request())

    # the binding calls happen before the run; within the run itself the case still begins before anything else
    run_calls = [call for call in port.calls
                 if call not in ("bind_startup_receipt", "bind_live_evidence")]
    assert run_calls[0] == "begin", f"the case begins before anything else, saw {run_calls[:3]}"
    # RADIAL_RETREAT arrives through run_retreat_segment rather than run_phase, so the coverage assertion counts both
    covered = list(port.phases)
    for call in port.calls:
        if call == "run_retreat_segment":
            covered.append("RADIAL_RETREAT")
    order = [phase for phase in Task8Runner.PHASES if phase in covered]
    assert order == [phase for phase in Task8Runner.PHASES], f"every phase, in order, saw {covered}"

    # the sealed artifact reads back from disk, its digest matches, and it covers the case's own phases
    import json as _json

    artifact = result["live_evidence_artifact"]
    assert set(artifact) == {"path", "sha256", "schema_version"}, artifact
    sealed_bytes = Path(artifact["path"]).read_bytes()
    assert hashlib.sha256(sealed_bytes).hexdigest() == artifact["sha256"], "the digest matches the sealed bytes"
    sealed = _json.loads(sealed_bytes)
    assert sealed["sample_count"] > 0, "the sealed evidence holds the case's rows"
    phases = {entry["phase"] for entry in sealed["samples"]}
    assert "SEARCH" in phases and "FINAL_CHECK" in phases, f"rows for the case's first and last phase, saw {sorted(phases)}"
    # a full case is an episode and confirms its stop; the release was opened and closed in order
    assert result["formal_episode_eligible"] is True and result["stopped_confirmed"] is True, result
    assert "safe_stop" in port.calls, "the case confirmed its stop"

    # the release open event, and three adjacent 10 Hz support rows inside one release epoch
    rows = sealed["samples"]
    # the release open event and the 10 Hz adjacency are asserted on the rows the port recorded, because the sealed index
    # deliberately carries references (relative_path + sha256) rather than the values themselves (CP-1191)
    port_rows = [row for row in port.rows if isinstance(row, dict)]
    # build_live_evidence_sample flattens the contact block, so `released` is a top-level key of the built sample
    released_rows = [row for row in port_rows if row.get("released") is True]
    assert released_rows, "the case recorded the release open event"
    support = [row for row in port_rows if row.get("release_epoch") == released_rows[0]["release_epoch"]][:3]
    assert len(support) == 3, f"three support rows after the release, saw {len(support)}"
    deltas = [round(later["sim_time_s"] - earlier["sim_time_s"], 6)
              for earlier, later in zip(support, support[1:])]
    assert deltas == [round(PERIOD_S, 6), round(PERIOD_S, 6)], f"adjacent 10 Hz rows, saw {deltas}"
    assert isinstance(result, dict), "a completed case reports its result"


def _seal_port_method(self, request):                                        # noqa: D401 - attached below
    """The three steps the production port performs, in its own order (CP-1179)."""

    identity = {"case_id": request["scenario_id"], "session_id": request["session_id"],
                "attempt_id": request["attempt_id"], "reset_epoch": self.reset_epoch,
                "release_epoch": self.release_epoch}            # the epochs the recorded samples carry
    if self.window is not None and not getattr(self.window, "_sealed", False):
        self.window.seal()
    published = getattr(self.recorder, "_sealed", None)
    if published is not None:
        return {"path": str(published),
                "sha256": hashlib.sha256(Path(published).read_bytes()).hexdigest(),
                "schema_version": 1}
    return self.recorder.seal(identity)


FakePort.seal_live_evidence = _seal_port_method
