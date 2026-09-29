"""Only owner-proved SEARCH may become a Task 8 physical phase result."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import json

import pytest

from so101_demo.act.task8 import Task8Runner
from so101_demo.adapters.act.pick_place_search_port import PickPlaceSearchPortError
from so101_demo.adapters.act.task8_search_port import (
    Task8SearchPhasePort, Task8SearchPortError,
)
from so101_demo.adapters.act.task8_search_segment import Task8SearchObservation
from so101_demo.core.simulation.types import ObjectState, SimulationEvidence
from so101_demo.ports.planning_scene import SceneCommandReceipt


SESSION = "session-296"
ATTEMPT = "attempt-296"


def request():
    return {
        "mode": "phase_prefix", "stop_after": "SEARCH",
        "lifecycle": "FULL_RESTART", "scenario_id": "prefix-01",
        "session_id": SESSION, "attempt_id": ATTEMPT,
        "deadline_ns": 9_000_000_000_000_000_000,
    }


def observation():
    object_state = ObjectState(
        body_id=1, body="plastic_cup", position_world=(0.0, 0.0, 0.2),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        linear_velocity_world=(0.0, 0.0, 0.0),
        angular_velocity_world=(0.0, 0.0, 0.0),
    )
    world = SimulationEvidence(
        simulation_time_s=1.2, frame_id="world", publisher_sequence=2,
        simulation_step=2, reset_epoch=2, simulation_session_id=SESSION,
        paused=False, object_state=object_state, has_contact=False,
        minimum_signed_distance_m=0.0, maximum_normal_force_n=0.0,
        truncated=False, left_fingertip_contacts=(),
        right_fingertip_contacts=(), other_object_contacts=(),
    )
    contact = {
        "simulation_session_id": SESSION, "reset_epoch": 2,
        "physics_step": 2, "simulation_time_s": 1.2,
        "geom_a": [], "geom_b": [], "signed_distance_m": [],
        "normal_force_n": [], "truncated": False, "evidence_loss": False,
    }
    rgb = {
        "session_id": SESSION, "attempt_id": ATTEMPT, "sim_time_s": 1.2,
        "state": (0.0,) * 6 + (0.0, 1.0),
        "head": np.zeros((480, 640, 3), dtype=np.uint8),
        "wrist": np.zeros((480, 640, 3), dtype=np.uint8),
    }
    raw = {
        "world": world,
        "scene": {"simulation_session_id": SESSION, "reset_epoch": 2,
                  "simulation_step": 2, "simulation_time_s": 1.2,
                  "paused": False, "model_sha256": "a" * 64,
                  "qpos": (0.0,), "qvel": (0.0,),
                  "clock_interval_begin_monotonic_ns": 9_999_800_000,
                  "clock_interval_end_monotonic_ns": 9_999_900_000},
        "contact": contact, "observation": rgb,
        "reference": {"positions": (0.0,) * 6,
                      "velocities": (0.0,) * 6,
                      "accelerations": (0.0,) * 6,
                      "requested_sim_time_s": 1.2},
        "source_stamps_s": {key: 1.2 for key in ("arm", "neck", "head", "wrist")},
        "source_received_wall_s": {key: 10.0 for key in
                                    ("world", "scene", "contact", "head", "wrist", "arm", "neck")},
    }
    search = {
        "found": True, "status": "TARGET_LOCKED", "bearing_rad": 0.0,
        "frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame",
        "neck_yaw_rad": 0.0, "confidence": 0.9, "timestamp": 1.1,
        "attempt_id": ATTEMPT,
    }
    scene = SceneCommandReceipt(
        backend="mujoco", phase="READ_BACK", success=True,
        failure_code=None, evidence={"world_ids": ["table", "pedestal", "plastic_cup"],
                                     "attached_ids": [], "mismatches": []},
    )
    return Task8SearchObservation(search, raw, scene)


def fixture(*, observed=None, contact_safe=True, sweep_safe=True):
    events = []
    observed = observation() if observed is None else observed
    sweep = SimpleNamespace(
        step_s=0.002, neck_qpos=0,
        check=lambda *_args, **_kwargs: events.append("sweep") or sweep_safe,
    )
    sources = SimpleNamespace(
        session_id=SESSION,
        contact_pairs=SimpleNamespace(
            model_sha256="a" * 64, for_phase=lambda phase: frozenset()),
        contacts=SimpleNamespace(safe=lambda: contact_safe),
        readback=SimpleNamespace(max_skew=0.02, joint_tolerance=0.002),
    )
    reset = SimpleNamespace(
        sources=sources, receipt=SimpleNamespace(new_epoch=2),
    )

    class Boundary:
        def __init__(self):
            self.reset = reset
            self.neck_sweep_checker = sweep

        def begin(self, item):
            events.append("begin")
            return {"session_id": item["session_id"], "attempt_id": item["attempt_id"],
                    "reset_epoch": 2, "release_epoch": 0, "full_restart": False}

        def search(self, _item):
            events.append("search")
            return observed

        def safe_stop(self, reason, _item):
            events.append(("stop", reason))
            return True

    return Task8SearchPhasePort(Boundary()), events


def bind(port):
    port.bind_startup_receipt({
        "schema_version": 1, "session_id": SESSION,
        "stack_owner": {"pid": 1}, "child_owner": {"pid": 2},
    })


def test_unbound_begin_cannot_reset_and_one_proved_search_can_pass():
    port, events = fixture()
    with pytest.raises(Task8SearchPortError, match="TASK8_STARTUP_PROOF_REQUIRED"):
        port.begin(request())
    assert events == []
    bind(port)
    result = Task8Runner(port).run(request())
    assert result["status"] == "PASSED"
    assert result["completed_phases"] == ["SEARCH"]
    assert result["formal_episode_eligible"] is False
    assert events == ["begin", "search", "sweep", ("stop", "PHASE_PREFIX_COMPLETE")]
    with pytest.raises(Task8SearchPortError, match="TASK8_BEGIN_ALREADY_STARTED"):
        port.begin(request())


def test_same_step_scene_and_contact_timestamps_accept_bounded_source_skew():
    observed = observation()
    raw = dict(observed.physical_readback)
    raw["scene"] = {**raw["scene"], "simulation_time_s": 1.19}
    raw["contact"] = {**raw["contact"], "simulation_time_s": 1.21}
    port, events = fixture(observed=replace(observed, physical_readback=raw))
    bind(port)
    port.begin(request())
    assert port.run_phase("SEARCH", request())["phase"] == "SEARCH"
    assert events == ["begin", "search", "sweep"]


@pytest.mark.parametrize("bad", ["missing_rgb", "missing_receipt", "wrong_step", "unsafe_contact", "bad_scene", "unsafe_sweep"])
def test_missing_or_unsafe_physical_evidence_cannot_pass_search(bad):
    observed = observation()
    raw = dict(observed.physical_readback)
    if bad == "missing_rgb":
        raw.pop("observation")
    elif bad == "missing_receipt":
        raw.pop("source_received_wall_s")
    elif bad == "wrong_step":
        raw["scene"] = {**raw["scene"], "simulation_step": 1}
    elif bad == "bad_scene":
        observed = replace(observed, planning_scene=SceneCommandReceipt(
            backend="mujoco", phase="READ_BACK", success=False,
            failure_code="SCENE_MISMATCH", evidence={"mismatches": ["cup"]},
        ))
    observed = replace(observed, physical_readback=raw)
    port, events = fixture(
        observed=observed, contact_safe=bad != "unsafe_contact",
        sweep_safe=bad != "unsafe_sweep",
    )
    bind(port)
    with pytest.raises(Task8SearchPortError, match="TASK8_SEARCH_EVIDENCE_INVALID"):
        port.begin(request())
        port.run_phase("SEARCH", request())
    assert ("stop", "TASK8_SEARCH_ABORT") in events


def test_later_phase_is_explicitly_unprovisioned_and_stopped():
    port, events = fixture()
    bind(port)
    port.begin(request())
    with pytest.raises(Task8SearchPortError, match="TASK8_PHASE_NOT_PROVISIONED"):
        port.run_phase("APPROACH", request())
    assert ("stop", "TASK8_PHASE_NOT_PROVISIONED") in events


def test_search_retains_only_validated_physical_observation_for_next_phase():
    port, events = fixture()
    bind(port)
    port.begin(request())
    port.run_phase("SEARCH", request())

    retained = port.validated_search_observation()
    assert isinstance(retained, Task8SearchObservation)
    assert retained.physical_readback["world"].simulation_step == 2
    assert retained.physical_readback["scene"]["simulation_step"] == 2
    assert retained.physical_readback["contact"]["physics_step"] == 2
    retained.physical_readback["scene"]["simulation_step"] = 999
    retained.physical_readback["observation"]["head"][0, 0, 0] = 255

    reread = port.validated_search_observation()
    assert reread.physical_readback["scene"]["simulation_step"] == 2
    assert reread.physical_readback["observation"]["head"][0, 0, 0] == 0
    assert events == ["begin", "search", "sweep"]


def test_failed_search_cannot_expose_a_physical_observation():
    observed = observation()
    raw = dict(observed.physical_readback)
    raw["scene"] = {**raw["scene"], "simulation_step": 1}
    port, events = fixture(observed=replace(observed, physical_readback=raw))
    bind(port)
    port.begin(request())
    with pytest.raises(Task8SearchPortError, match="TASK8_SEARCH_EVIDENCE_INVALID"):
        port.run_phase("SEARCH", request())
    with pytest.raises(Task8SearchPortError,
                       match="PICK_PLACE_SEARCH_OBSERVATION_UNAVAILABLE"):
        port.validated_search_observation()
    assert ("stop", "TASK8_SEARCH_ABORT") in events


def test_a_boundary_without_a_field_builder_is_refused_rather_than_skipped(tmp_path):
    """P1-3 replaced this test's premise: "records nothing and does not crash" is what the review refused.

    The old contract let an attached window go unfed - which is precisely how production ended up with a driver that
    was constructed and never used (CP-1467/1470). With a window attached and no way to derive the fields, the phase
    must refuse by name.
    """

    from so101_demo.act.task8_live_evidence import LiveEvidenceWindow, Task8LiveEvidenceRecorder

    port, events = fixture()
    recorder = Task8LiveEvidenceRecorder(case_id="case-20", evidence_root=tmp_path,
                                         session_id=SESSION, attempt_id=ATTEMPT)
    window = LiveEvidenceWindow(
        recorder,
        identity={"case_id": "case-20", "session_id": SESSION, "attempt_id": ATTEMPT,
                  "reset_epoch": 2, "release_epoch": 0},
        period_s=0.1, tolerance_s=0.01)
    port.bind_live_evidence(window, support_distance_max_m=0.02, raw_records_root=tmp_path)
    bind(port)
    port.begin(request())

    with pytest.raises(PickPlaceSearchPortError, match="TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: canonical_evidence"):
        port.run_phase("SEARCH", request())
    assert recorder._entries == [], "nothing was recorded, and nothing was silently skipped either"


# --- P1-3: the SEARCH phase must produce canonical evidence ITSELF, or refuse by name -----------------------

def _p13_window(tmp_path):
    """A real window and recorder for the case, so the port's own feed can be observed."""

    from so101_demo.act.task8_live_evidence import LiveEvidenceWindow, Task8LiveEvidenceRecorder

    recorder = Task8LiveEvidenceRecorder(case_id="prefix-01", evidence_root=tmp_path,
                                         session_id=SESSION, attempt_id=ATTEMPT)
    window = LiveEvidenceWindow(
        recorder,
        identity={"case_id": "prefix-01", "session_id": SESSION, "attempt_id": ATTEMPT,
                  "reset_epoch": 2, "release_epoch": 0},
        period_s=0.1, tolerance_s=0.01)
    return recorder, window


def test_a_search_phase_records_a_canonical_sample_through_the_port(tmp_path):
    """The port's own feed, not a fixture's: one canonical 24-key sample reaches the recorder."""

    from so101_demo.act.task8_live_evidence import build_live_evidence_sample  # noqa: F401  (the shape)

    recorder, window = _p13_window(tmp_path)
    port, events = fixture()
    port.boundary.canonical_evidence = lambda captured, *, support_distance_max_m, raw_records: {
        "physics_step": 12, "sim_time_s": 2.0,
        "source_stamps_s": {name: 2.0 for name in ("world", "scene", "contact", "head", "wrist", "arm", "neck")},
        "source_received_monotonic_s": {name: 2.0 for name in ("world", "scene", "contact", "head", "wrist", "arm", "neck")},
        "holding_state": "EMPTY", "cup_supported": False, "released": False,
        "placement_stable": False, "bilateral_contact": False, "no_fingertip_contact": True,
        "wrist_frame_valid": True, "wrist_target_visible": True,
        "cup_support_distance_m": 0.01, "end_effector_position_m": [0.0, 0.0, 0.1],
        "cup_position_m": [0.0, 0.0, 0.1], "cup_orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
        "contact_observation_valid": True}
    port.bind_live_evidence(window, support_distance_max_m=0.02, raw_records_root=tmp_path)
    bind(port)
    port.begin(request())

    port.run_phase("SEARCH", request())

    assert window._grid_count == 1, "the phase's own feed recorded exactly one sample"
    entries = recorder._entries
    assert len(entries) == 1
    recorded = json.loads((tmp_path / entries[0]["relative_path"]).read_bytes())
    assert len(recorded) == 24, f"the recorded sample is the canonical shape: {len(recorded)} keys"
    assert recorded["phase"] == "SEARCH" and recorded["reset_epoch"] == 2
    assert recorded["cup_supported"] is False and recorded["holding_state"] == "EMPTY"


def test_a_boundary_that_cannot_derive_the_fields_is_refused_by_name(tmp_path):
    """Fail closed: no silent None, no skipped sample - the phase raises and says which piece is missing."""

    _recorder, window = _p13_window(tmp_path)
    port, _events = fixture()                      # this boundary has no canonical_evidence method
    port.bind_live_evidence(window, support_distance_max_m=0.02, raw_records_root=tmp_path)
    bind(port)
    port.begin(request())

    with pytest.raises(Exception, match="TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED"):
        port.run_phase("SEARCH", request())


def test_an_attachment_without_the_support_threshold_is_refused_by_name(tmp_path):
    """And the threshold is not defaulted: a case that did not admit one cannot record evidence."""

    _recorder, window = _p13_window(tmp_path)
    port, _events = fixture()
    with pytest.raises(Exception, match="TASK8_LIVE_EVIDENCE_FIELDS_REQUIRED: support_distance_max_m"):
        port.bind_live_evidence(window)            # deliberately no support_distance_max_m: refused at attach


# --- P1-4: the unprovisioned sequence refuses BY NAME, one phase at a time -----------------------------------

@pytest.mark.parametrize("method", ["set_down", "detach_moveit", "planning_attached",
                                    "release_preflight", "run_retreat_segment"])
def test_the_unprovisioned_protocol_methods_refuse_by_name(method):
    """The runner calls five more methods than SEARCH implements, and each must fail closed with its own name."""

    port, _events = fixture()
    with pytest.raises(PickPlaceSearchPortError, match=f"TASK8_PHASE_NOT_PROVISIONED: {method}"):
        getattr(port, method)({"session_id": SESSION, "attempt_id": ATTEMPT})


@pytest.mark.parametrize("phase", ["APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN",
                                   "RELEASE", "RADIAL_RETREAT", "FINAL_CHECK"])
def test_the_unprovisioned_sequence_phases_refuse_by_their_own_name(phase):
    """And a phase that is not built yet says WHICH phase, so a staged build cannot look finished."""

    port, _events = fixture()
    bind(port)
    port.begin(request())

    with pytest.raises(PickPlaceSearchPortError, match=f"TASK8_PHASE_NOT_PROVISIONED: {phase}"):
        port.run_phase(phase, request())
