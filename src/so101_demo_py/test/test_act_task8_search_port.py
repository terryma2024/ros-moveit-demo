"""Only owner-proved SEARCH may become a Task 8 physical phase result."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from so101_demo.act.task8 import Task8Runner
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
                  "qpos": (0.0,), "qvel": (0.0,)},
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
