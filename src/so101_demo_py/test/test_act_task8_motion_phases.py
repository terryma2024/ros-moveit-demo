"""MICRO_LIFT (and the motion phases that follow it) aim at an admitted target, judged by the runner.

The template and the cup sample come from the dynamic-pick suite's own fixtures, the readback from the path-screen
suite's, and the IK is a stub: what is substituted is the solver and the broker, while the target resolution, the
phase flags and the judgement are production code.
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

from so101_demo.act.joints import ARM_JOINTS  # noqa: E402
from so101_demo.act.pick_place_runner import PickPlaceRunner  # noqa: E402
from so101_demo.adapters.act.pick_place_search_boundary import (  # noqa: E402
    PickPlaceSearchBoundary, PickPlaceSearchBoundaryError,
)


def _case(calls, *, lifted=True, with_dispatch=True, with_wait=True, with_ik=True, with_template=True,
          with_duration=True):
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

    contacts = (_grasp("left"),) if lifted else ()
    world = dataclasses.replace(raw["world"], left_fingertip_contacts=contacts,
                                right_fingertip_contacts=contacts, other_object_contacts=(),
                                minimum_signed_distance_m=0.5 if lifted else 0.0,
                                has_contact=lifted, maximum_normal_force_n=1.0 if lifted else 0.0)
    stamps = {name: world.simulation_time_s for name in ("head", "wrist", "arm", "neck")}
    capture = {**raw, "world": world, "source_stamps_s": stamps, "source_received_wall_s": dict(stamps)}
    sources.capture = lambda *args, **kwargs: capture
    sources.readback.max_skew = 0.05
    sources.monotonic = lambda: 3.0
    ticket = (7, "owner-key-1", "act", prefix["session_id"], prefix["attempt_id"])

    broker = SimpleNamespace(ownership=SimpleNamespace(ticket=lambda *parts: ticket),
                             driver=SimpleNamespace(reset_epoch=2))
    if with_wait:
        broker.driver.wait = lambda gid: calls.append(("wait", gid))
    if with_dispatch:
        broker.dispatch = lambda ticket_, kind, goal: (calls.append(("dispatch", kind, goal)), 42)[1]

    boundary = SimpleNamespace(
        reset=SimpleNamespace(receipt=SimpleNamespace(new_epoch=2), sources=sources, broker=broker,
                              act_context={"lease_token": "lease-1"}))
    if with_ik:
        boundary.motion_target_joints = lambda target: (calls.append(("ik", target)) or (0.5,) * 5)
    boundary.sequence_facts = MethodType(PickPlaceSearchBoundary.sequence_facts, boundary)
    boundary._motion_facts = MethodType(PickPlaceSearchBoundary._motion_facts, boundary)
    return (boundary, ticket, capture,
            _template() if with_template else None,
            0.4 if with_duration else None)


def _call(boundary, ticket, template, duration, phase="MICRO_LIFT"):
    return PickPlaceSearchBoundary.sequence_phase(
        boundary, phase, {"session_id": ticket[3], "attempt_id": ticket[4]},
        observed=None, selected_source=None, motion_template=template, motion_duration_s=duration,
        support_distance_max_m=0.02)


def test_micro_lift_aims_at_the_resolved_target_and_the_runner_accepts_the_document():
    calls = []
    boundary, ticket, capture, template, duration = _case(calls)
    document = _call(boundary, ticket, template, duration)

    assert [call[0] for call in calls] == ["ik", "dispatch", "wait"], calls
    target = calls[0][1]
    # the resolved target is the grasp pose lifted by the template's own micro-lift clearance: the assertion is about
    # the VALUE that production code computed, not about a label it attached
    cup_z = capture["world"].object_state.position_world[2]
    assert target.position_m[2] == pytest.approx(cup_z + 0.035 + 0.02, abs=1e-9)
    kind, goal = calls[1][1], calls[1][2]
    assert kind == "arm"
    assert tuple(goal["joint_names"]) == ARM_JOINTS[:5]
    assert tuple(goal["time_from_start_s"]) == (0.0, 0.4)
    assert goal["positions"][0] == tuple(capture["observation"]["state"][:5]), "it starts where the robot's arm is"

    assert document["holding_state"] == "HOLDING" and document["bilateral_contact"] is True
    assert document["micro_lift_confirmed"] is True and document["cup_off_table"] is True
    assert document["cup_supported"] is False
    request = {"session_id": ticket[3], "attempt_id": ticket[4]}
    with pytest.raises(Exception, match="PHASE_EVIDENCE_INVALID"):
        PickPlaceRunner(boundary)._verify_phase("MICRO_LIFT", document, request, reset_epoch=2,
                                                release_epoch=0, after_step=document["physics_step"] - 1)
    stamped = {**document, "phase": "MICRO_LIFT", "session_id": ticket[3], "attempt_id": ticket[4],
               "reset_epoch": 2, "release_epoch": 0}
    step = PickPlaceRunner(boundary)._verify_phase("MICRO_LIFT", stamped, request, reset_epoch=2,
                                                   release_epoch=0, after_step=document["physics_step"] - 1)
    assert step == document["physics_step"]


def test_a_cup_still_on_the_table_cannot_claim_a_micro_lift():
    """The flags are established, not asserted: no lift evidence, no MICRO_LIFT document."""

    calls = []
    boundary, ticket, _capture, template, duration = _case(calls, lifted=False)
    with pytest.raises(PickPlaceSearchBoundaryError, match="MICRO_LIFT: the cup is not held clear"):
        _call(boundary, ticket, template, duration)


def test_each_missing_piece_refuses_by_name():
    for kwargs, expected in (({"with_template": False}, "MICRO_LIFT: motion_template"),
                             ({"with_duration": False}, "MICRO_LIFT: motion_duration_s"),
                             ({"with_ik": False}, "MICRO_LIFT: ik"),
                             ({"with_dispatch": False}, "MICRO_LIFT: broker.dispatch"),
                             ({"with_wait": False}, "MICRO_LIFT: driver.wait")):
        calls = []
        boundary, ticket, _capture, template, duration = _case(calls, **kwargs)
        with pytest.raises(PickPlaceSearchBoundaryError, match=expected):
            _call(boundary, ticket, template, duration)


def test_the_phases_whose_evidence_is_not_designed_yet_refuse_by_name():
    calls = []
    boundary, ticket, _capture, template, duration = _case(calls)
    for phase in ("RELEASE", "RADIAL_RETREAT", "FINAL_CHECK"):
        with pytest.raises(PickPlaceSearchBoundaryError, match=f"{phase}"):
            _call(boundary, ticket, template, duration, phase=phase)
