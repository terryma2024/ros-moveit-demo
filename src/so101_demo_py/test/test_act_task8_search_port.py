"""Only owner-proved SEARCH may become a Task 8 physical phase result."""

from dataclasses import replace
from types import SimpleNamespace

import dataclasses
import re
import numpy as np
import json

import pytest

from so101_demo.act.pick_place_runner import PickPlaceRunner
from so101_demo.core.simulation.types import ObjectState, SimulationEvidence
from so101_demo.ports.planning_scene import SceneCommandReceipt


SESSION = "session-296"
ATTEMPT = "attempt-296"


def feedback_at(kind, instant, *, source_instant=None):
    names = ["1", "2", "3", "4", "5"] if kind == "arm" else ["6"]
    return {"controller": kind, "joint_names": names,
            "commanded_positions": [0.0] * len(names), "measured_positions": [0.0] * len(names),
            "measured_velocities": [0.0] * len(names), "status_sequence": 1,
            "sim_time_s": instant, "source_sim_time_s": instant if source_instant is None else source_instant}


def request():
    return {
        "mode": "phase_prefix", "stop_after": "SEARCH",
        "lifecycle": "FULL_RESTART", "scenario_id": "prefix-01",
        "session_id": SESSION, "attempt_id": ATTEMPT,
        "deadline_ns": 9_000_000_000_000_000_000,
    }


def bind(port):
    port.bind_startup_receipt({
        "schema_version": 1, "session_id": SESSION,
        "stack_owner": {"pid": 1}, "child_owner": {"pid": 2},
    })


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


# --- P1-4: the unprovisioned sequence refuses BY NAME, one phase at a time -----------------------------------


# --- P1-4: the sequence phases, judged by the RUNNER's own verifier -----------------------------------------

def _sequence_facts(step, **overrides):
    """The facts a boundary reports for one sequence phase: everything but the scope the port stamps."""

    facts = {"physics_step": step, "planning_ok": True, "controller_reference_ok": True,
             "joint_feedback_ok": True, "contact_ok": True, "mujoco_ok": True,
             "planning_scene_ok": True, "head_rgb_ok": True, "wrist_rgb_ok": True,
             "manual_intervention": False, "moveit_recovery": False, "holding_state": "EMPTY",
             "bilateral_contact": False, "micro_lift_confirmed": False, "cup_off_table": False,
             "cup_supported": True, "released": False, "no_fingertip_contact": True,
             "placement_stable": False, "retreat_stable": False}
    facts.update(overrides)
    return facts


class _PrefixSource:
    """The broker's prefix-source authority: the port registers the frozen source with it and the broker asks it
    for that source when it issues a prefix permit. External-motion machinery, so it is
    substituted here exactly as the broker itself is."""

    def __init__(self):
        self.registered = []

    def register(self, *args, **kwargs):
        self.registered.append((args, kwargs))
        return True

    def __call__(self, ticket):
        return {"kind": "PREFIX_SOURCE", "ticket": ticket}


def test_the_scene_port_returns_the_ratified_observation_parts():
    """CP-2017 step one: the record's parts come from the read the port already makes."""

    from types import SimpleNamespace

    from so101_demo.control.planning_scene.task_scene import RosTaskScenePort

    port = object.__new__(RosTaskScenePort)
    port._read_revision = 0
    scene = SimpleNamespace(
        is_diff=False,
        world=SimpleNamespace(collision_objects=[SimpleNamespace(id="table"),
                                                 SimpleNamespace(id="plastic_cup")]),
        robot_state=SimpleNamespace(attached_collision_objects=[
            SimpleNamespace(object=SimpleNamespace(id="plastic_cup"))]))
    port._observe = lambda: SimpleNamespace(scene=scene)
    first = port.observe_observation()
    assert first == {"scene_revision": 1, "attached_objects": ["plastic_cup"],
                     "world_object_ids": ["plastic_cup", "table"], "is_diff": False,
                     "source": "ros_task_scene_port"}
    assert port.observe_observation()["scene_revision"] == 2
    from so101_demo.ports.planning_scene import SceneCommandReceipt
    port._observe = lambda: SceneCommandReceipt(backend="moveit", phase="READ_BACK", success=False,
                                                failure_code="SCENE_SERVICE_TIMEOUT", evidence={})
    with pytest.raises(RuntimeError, match="SCENE_OBSERVATION_UNAVAILABLE"):
        port.observe_observation()


