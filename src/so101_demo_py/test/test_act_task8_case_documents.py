"""The two documents the runner asks for around the release, and the retreat segment, with their seams substituted.

`set_down` and `release_preflight` are not phases' evidence: they are the runner's own set-down and preflight documents,
and they must be established from the SAME validated readback the phases use. These tests substitute the controller stop,
the tool pose and the retreat axis - and the axis substitution is the point: which way "radial" points is the runtime's
decision, not this component's.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_pick_place_approach_path_screen import physical_inputs  # noqa: E402
from test_dynamic_pick import _template  # noqa: E402

from so101_demo.adapters.act.pick_place_search_boundary import (  # noqa: E402
    PickPlaceSearchBoundary, PickPlaceSearchBoundaryError,
)
from so101_demo.ports.evidence import PoseEvidence  # noqa: E402

# the request names the FIXTURE's own case: the scope rule compares the world's session against it
REQUEST = None


def _case(*, stopped=True, step_delta=1, released=True, with_stop=True, with_tcp=True, with_axis=True):
    calls = []
    screen, prefix, goals, checks, sources, _driver, _owner, _events, _qpos, _qvel = physical_inputs()
    raw = sources.capture(prefix["attempt_id"], after_step=0)
    from so101_demo.core.simulation.types import ContactEvidence

    state = raw["world"].object_state

    def _grasp(side):
        return ContactEvidence(body1_id=state.body_id, geom1_id=state.body_id, body1=state.body,
                               geom1=f"cup_{side}_geom", body2_id=991, geom2_id=992,
                               body2=f"gripper_{side}", geom2=f"{side}_pad",
                               position_world=(0.0, 0.0, 0.0), normal_world=(0.0, 0.0, 1.0),
                               signed_distance_m=0.5, normal_force_n=1.0)

    contacts = () if released else (_grasp("left"),)
    world = dataclasses.replace(raw["world"], left_fingertip_contacts=contacts,
                                right_fingertip_contacts=contacts, other_object_contacts=(),
                                minimum_signed_distance_m=0.0 if released else 0.5,
                                has_contact=not released, maximum_normal_force_n=0.0 if released else 1.0,
                                simulation_step=raw["world"].simulation_step + step_delta)
    stamps = {name: world.simulation_time_s for name in ("head", "wrist", "arm", "neck")}
    # the scope rule compares steps AND times across the three documents, so a fixture that bumps one must bump the
    # others - the same reason the world's own validation refuses an inconsistent capture
    step = world.simulation_step
    moment = world.simulation_time_s
    capture = {**raw, "world": world, "source_stamps_s": stamps, "source_received_wall_s": dict(stamps),
               "scene": {**raw["scene"], "simulation_step": step, "simulation_time_s": moment},
               "contact": {**raw["contact"], "physics_step": step, "simulation_time_s": moment},
               "observation": {**raw["observation"], "sim_time_s": moment}}
    # the fixture's OWN sources object: it already carries the contact pairs, the model digest and the safety probes
    # the scope rule compares against, so this test substitutes the capture rather than rebuilding the source card
    # a LIVE readback advances between calls, and it advances CONSISTENTLY: the scope rule compares the world, the
    # scene and the contact frame against each other, so a fixture that bumped one and not the others would be refused
    readings = []

    def _capture(*args, **kwargs):
        index = len(readings)
        readings.append(index)
        step = raw["world"].simulation_step + step_delta * (1 + index)
        moment = world.simulation_time_s
        advanced = dataclasses.replace(world, simulation_step=step)
        stamps = {name: moment for name in ("head", "wrist", "arm", "neck")}
        return {**raw, "world": advanced, "source_stamps_s": stamps, "source_received_wall_s": dict(stamps),
                "scene": {**raw["scene"], "simulation_step": step, "simulation_time_s": moment},
                "contact": {**raw["contact"], "physics_step": step, "simulation_time_s": moment},
                "observation": {**raw["observation"], "sim_time_s": moment}}

    sources.capture = _capture
    sources.readback.max_skew = 0.05
    sources.monotonic = lambda: 3.0
    boundary = SimpleNamespace(
        reset=SimpleNamespace(receipt=SimpleNamespace(new_epoch=2), sources=sources,
                              broker=SimpleNamespace(), act_context={"lease_token": "lease-1"}),
        planning_scene=SimpleNamespace(is_attached=lambda: False))
    boundary._release_epoch, boundary._set_down_step = 0, None
    if with_stop:
        boundary.controller_stop = lambda request: (calls.append(("stop", None)), stopped)[1]
    if with_tcp:
        boundary.tool_pose = lambda request: PoseEvidence((0.2, -0.2, 0.2), (0.0, 0.0, 0.0, 1.0))
    if with_axis:
        boundary.retreat_axis = lambda direction: {"radial": (1.0, 0.0, 0.0),
                                                  "vertical": (0.0, 0.0, 1.0)}[direction]
    boundary.motion_target_joints = lambda target: (calls.append(("ik", target)) or (0.5,) * 5)
    boundary.reset.broker.dispatch = lambda ticket, kind, goal: (calls.append(("dispatch", kind, goal)), 7)[1]
    boundary.reset.broker.driver = SimpleNamespace(wait=lambda gid: calls.append(("wait", gid)))
    request = {"session_id": prefix["session_id"], "attempt_id": prefix["attempt_id"]}
    boundary.reset.broker.ownership = SimpleNamespace(
        ticket=lambda *parts: (7, "owner-key", "act", request["session_id"], request["attempt_id"]))
    for name in ("_checked_aggregates", "sequence_facts", "planning_attached", "set_down", "release_preflight",
                 "run_retreat_segment"):
        setattr(boundary, name, MethodType(getattr(PickPlaceSearchBoundary, name), boundary))
    return boundary, calls, capture, request


def test_set_down_establishes_its_document_and_the_preflight_must_be_fresh():
    boundary, calls, capture, request = _case()
    document = boundary.set_down(request, support_distance_max_m=0.02)
    assert calls == [("stop", None)], calls
    assert set(document) == {"session_id", "attempt_id", "reset_epoch", "release_epoch", "physics_step",
                             "holding_state", "cup_supported", "bilateral_contact", "controller_stopped"}
    assert document["holding_state"] == "EMPTY" and document["cup_supported"] is True
    assert document["controller_stopped"] is True and document["release_epoch"] == 0

    preflight = boundary.release_preflight(request, support_distance_max_m=0.02)
    assert set(preflight) == {"session_id", "attempt_id", "reset_epoch", "release_epoch", "physics_step",
                              "holding_state", "cup_supported", "fresh", "planning_attached"}
    assert preflight["fresh"] is True and preflight["planning_attached"] is False


def test_a_preflight_on_the_set_downs_own_sample_is_refused():
    """The rule with a consequence: the release may not be authorised by evidence that predates the stop."""

    boundary, _calls, _capture, request = _case(step_delta=0)
    boundary.set_down(request, support_distance_max_m=0.02)
    with pytest.raises(PickPlaceSearchBoundaryError, match="release_preflight: not fresh"):
        boundary.release_preflight(request, support_distance_max_m=0.02)


def test_a_controller_that_did_not_stop_is_refused_and_a_preflight_without_a_set_down_too():
    boundary, _calls, _capture, request = _case(stopped=False)
    with pytest.raises(PickPlaceSearchBoundaryError, match="set_down: controller did not stop"):
        boundary.set_down(request, support_distance_max_m=0.02)

    boundary, _calls, _capture, request = _case()
    with pytest.raises(PickPlaceSearchBoundaryError, match="release_preflight: set_down first"):
        boundary.release_preflight(request, support_distance_max_m=0.02)


def test_a_retreat_segment_steps_from_the_current_tool_pose_along_the_runtimes_axis():
    boundary, calls, _capture, request = _case(released=True)
    document = boundary.run_retreat_segment("vertical", 0.06, request, motion_template=_template(),
                                           motion_duration_s=0.4, support_distance_max_m=0.02)

    assert [call[0] for call in calls] == ["ik", "dispatch", "wait"], calls
    target = calls[0][1]
    assert target.position_m == pytest.approx((0.2, -0.2, 0.26), abs=1e-9), \
        "the step is the tool pose moved along the axis the RUNTIME supplied"
    assert calls[1][1] == "arm"
    assert document["holding_state"] == "EMPTY" and document["released"] is True


def test_each_retreat_seam_refuses_by_name():
    for kwargs, expected in (({"with_tcp": False}, "run_retreat_segment: tool_pose"),
                             ({"with_axis": False}, "run_retreat_segment: retreat_axis")):
        boundary, _calls, _capture, request = _case(**kwargs)
        with pytest.raises(PickPlaceSearchBoundaryError, match=expected):
            boundary.run_retreat_segment("radial", 0.01, request, motion_template=_template(),
                                         motion_duration_s=0.4, support_distance_max_m=0.02)

    boundary, _calls, _capture, request = _case(with_stop=False)
    with pytest.raises(PickPlaceSearchBoundaryError, match="set_down: controller_stop"):
        boundary.set_down(request, support_distance_max_m=0.02)
