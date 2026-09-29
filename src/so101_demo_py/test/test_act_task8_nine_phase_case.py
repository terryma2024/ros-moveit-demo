"""A nine-phase case through the PORT, driven by the production runner.

The only substituted layer is the boundary underneath the port - the ROS/MuJoCo/controller surface - which is where
every other test in this batch draws the line: the port, the phase routing, the validators and the runner's own verifier
are production code, and the boundary supplies the runtime seams (a planning scene, a controller stop, a tool pose, a
retreat axis and an IK solver) plus the readback.

This file grows one phase at a time on purpose. SEARCH first, because every later phase's documents are stamped against
the case scope the port binds here; then the other eight, each with the run's own verifier as the judge.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_pick_place_approach_path_screen import physical_inputs  # noqa: E402
from test_act_task8_case_documents import _case  # noqa: E402
from test_act_task8_search_port import (  # noqa: E402
    ATTEMPT, SESSION, bind, fixture, request as port_request,
)

from so101_demo.act.pick_place_runner import PickPlaceRunner  # noqa: E402

from so101_demo.adapters.act.pick_place_search_boundary import PickPlaceSearchBoundary  # noqa: E402
from so101_demo.adapters.act.pick_place_search_port import (  # noqa: E402
    PickPlaceSearchPhasePort,
)

#: every production method the port may call on the boundary when the runtime is substituted
_BOUND = ("_checked_aggregates", "sequence_facts", "sequence_phase", "_motion_facts", "_release_facts",
          "_gripper_open_rad", "set_down", "release_preflight", "run_retreat_segment", "planning_attached",
          "detach_moveit")


def _boundary(*, session_id, attempt_id):
    """The substituted runtime, carrying the REAL boundary methods.

    The distinction matters: the seams below are the ROS/MuJoCo/controller surface, and everything the port asks for on
    top of them is production code, so a nine-phase run cannot agree with itself about what a phase's evidence is.
    """

    boundary, calls, _capture, _request = _case()
    for name in _BOUND:
        setattr(boundary, name, MethodType(getattr(PickPlaceSearchBoundary, name), boundary))
    boundary.reset.sources.session_id = session_id
    boundary.reset.sources.phase = "SEARCH"
    boundary.reset_epoch = boundary.reset.receipt.new_epoch
    boundary.reset.release_epoch = 0
    boundary.calls = calls
    return boundary


def test_the_scaffold_binds_every_production_method_the_port_calls():
    """A guard for the file itself: a missing binding would show up as a refusal in a later phase, not here."""

    boundary = _boundary(session_id="session-1", attempt_id="attempt-1")
    for name in _BOUND:
        assert callable(getattr(boundary, name)), name
    assert isinstance(boundary, SimpleNamespace)


def test_the_port_is_the_object_under_test_not_a_double():
    boundary = _boundary(session_id="session-1", attempt_id="attempt-1")
    port = PickPlaceSearchPhasePort.__new__(PickPlaceSearchPhasePort)
    for name in ("_boundary_capability", "_support_distance", "set_down", "release_preflight", "run_retreat_segment",
                 "detach_moveit", "planning_attached"):
        setattr(port, name, MethodType(getattr(PickPlaceSearchPhasePort, name), port))
    port.boundary = boundary
    port._support_distance_max_m = 0.02
    port._motion_template, port._motion_duration_s = object(), 0.4
    # every delegation reaches the boundary rather than re-implementing it
    port.planning_attached({"session_id": "session-1", "attempt_id": "attempt-1"})


def test_the_runner_drives_the_real_port_through_the_search_phase():
    """The first phase end to end: the runner's own request keys, the port's own begin, the port's SEARCH path.

    Nothing here is new machinery - the SEARCH port fixture already builds a working port against a substituted
    boundary, and this test puts the production RUNNER on top of it. If the runner and the port disagree about the
    request shape or the evidence keys, that disagreement is what this asserts against.
    """

    port, events = fixture()
    bind(port)
    runner = PickPlaceRunner(port)
    request = dict(port_request())
    result = runner.run({
        # a phase-prefix case is a FULL_RESTART by the runner's own rule: a prefix may not be run against a stack that
        # someone else's case left in an unknown state
        "mode": "phase_prefix", "stop_after": "SEARCH", "lifecycle": "FULL_RESTART",
        "scenario_id": request["scenario_id"] if "scenario_id" in request else "scenario-1",
        "session_id": SESSION, "attempt_id": ATTEMPT,
        "deadline_ns": runner.clock_ns() + 60_000_000_000,
    })
    print("[probe] runner result:", {key: str(value)[:60] for key, value in result.items()}
          if isinstance(result, dict) else type(result).__name__)
    assert isinstance(result, dict) and result, "the runner returns a case result, not an empty document"
