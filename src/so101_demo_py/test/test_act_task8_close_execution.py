"""CLOSE's boundary path, with the broker, the wait and the physics substituted and the RUNNER as the judge.

The readback comes from the path-screen suite's own fixture - a real SEARCH against a real MuJoCo model - with the
world's fingertip contacts made bilateral, which is what CLOSE's predicate requires. The goal that gets dispatched is
asserted field by field, and the document is handed to `PickPlaceRunner._verify_phase`, so the test cannot agree with
itself about what a CLOSE phase is.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_pick_place_approach_path_screen import physical_inputs  # noqa: E402

from so101_demo.act.joints import ARM_JOINTS  # noqa: E402
from so101_demo.act.pick_place_runner import PickPlaceRunner  # noqa: E402
from so101_demo.adapters.act.pick_place_search_boundary import (  # noqa: E402
    PickPlaceSearchBoundary, PickPlaceSearchBoundaryError,
)

TICKET = None      # bound per case below, because the issuing ticket names the prefix's own case


def _case(calls, *, bilateral=True, with_dispatch=True, with_wait=True):
    screen, prefix, goals, checks, sources, _driver, _owner, _events, _qpos, _qvel = physical_inputs()
    raw = sources.capture(prefix["attempt_id"], after_step=0)
    # the world's contacts are validated evidence, not placeholders: a bilateral grasp is two real ContactEvidence
    # the world validates against the CORE ContactEvidence, not the ports one - two classes share the name, and the
    # simulation type is the one the evidence dataclass accepts
    from so101_demo.core.simulation.types import ContactEvidence

    # the world requires every contact's FIRST body to be the object_state's own object, so the grasp is built against
    # the fixture's state rather than a string of my choosing
    state = raw["world"].object_state

    def _grasp(side):
        return ContactEvidence(body1_id=state.body_id, geom1_id=state.body_id, body1=state.body,
                               geom1=f"cup_{side}_geom", body2_id=991, geom2_id=992,
                               body2=f"gripper_{side}", geom2=f"{side}_pad",
                               position_world=(0.0, 0.0, 0.0), normal_world=(0.0, 0.0, 1.0),
                               signed_distance_m=0.5, normal_force_n=1.0)

    contacts = (_grasp("left"),) if bilateral else ()
    world = dataclasses.replace(raw["world"], left_fingertip_contacts=contacts,
                                right_fingertip_contacts=contacts,
                                other_object_contacts=(),
                                # with no contacts the aggregates must be zero, and with contacts the distance may
                                # be their own value - both rules are the world's, not this test's
                                # HOLDING means held AND not supported (derive_frame_aggregates): a grasp while the
                                # cup still rests on the table aggregates to APPROACHING, which the runner refuses
                                minimum_signed_distance_m=0.5 if bilateral else 0.0,
                                has_contact=bilateral,
                                maximum_normal_force_n=1.0 if bilateral else 0.0)
    # the validator compares both stamp maps against the four RGB sources, so the substituted readback supplies them
    stamps = {name: world.simulation_time_s for name in ("head", "wrist", "arm", "neck")}
    capture = {**raw, "world": world, "source_stamps_s": stamps, "source_received_wall_s": dict(stamps)}
    sources.capture = lambda *args, **kwargs: capture
    # the readback adapter's own configuration: the fixture supplies it, as it supplies the capture itself. The stamps
    # in this capture equal the world's time, so any positive skew accepts them and the validator's rule stays real.
    sources.readback.max_skew = 0.05
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
    # the real validator and the real close path are bound to this stub, so CLOSE's facts are established by the
    # production code rather than by a double that agrees with the test
    boundary._close_facts = MethodType(PickPlaceSearchBoundary._close_facts, boundary)
    boundary.sequence_facts = MethodType(PickPlaceSearchBoundary.sequence_facts, boundary)
    return boundary, ticket, capture


def test_close_dispatches_the_admitted_target_and_the_runner_accepts_the_document():
    calls = []
    boundary, ticket, capture = _case(calls)
    document = PickPlaceSearchBoundary.sequence_phase(
        boundary, "CLOSE", {"session_id": ticket[3], "attempt_id": ticket[4]},
        observed=None, selected_source=None, gripper_closed_rad=0.5, close_duration_s=0.4,
        support_distance_max_m=0.02)

    assert [call[0] for call in calls] == ["dispatch", "wait"], calls
    kind, goal = calls[0][1], calls[0][2]
    assert kind == "gripper", "CLOSE goes to the gripper controller, not the arm"
    assert tuple(goal["joint_names"]) == ARM_JOINTS[5:]
    assert tuple(goal["time_from_start_s"]) == (0.0, 0.4)
    assert goal["positions"][1] == (0.5,), "the closed position is the case's admitted target"
    assert goal["positions"][0] == (capture["observation"]["state"][5],), "and it starts where the robot is"

    runner = PickPlaceRunner(boundary)
    request = {"session_id": ticket[3], "attempt_id": ticket[4]}
    # the boundary reports the phase's own facts; the PORT is what stamps the case scope onto them, so the unstamped
    # document must be refused by name and the stamped one must be accepted - both are asserted here, because a test
    # that only checked the accepted case would hide which layer supplies the header
    with pytest.raises(Exception, match="PHASE_EVIDENCE_INVALID"):
        runner._verify_phase("CLOSE", document, request, reset_epoch=2, release_epoch=0,
                             after_step=document["physics_step"] - 1)
    stamped = {**document, "phase": "CLOSE", "session_id": ticket[3], "attempt_id": ticket[4],
               "reset_epoch": 2, "release_epoch": 0}
    step = runner._verify_phase("CLOSE", stamped, request, reset_epoch=2, release_epoch=0,
                                after_step=document["physics_step"] - 1)
    assert step == document["physics_step"]
    assert document["bilateral_contact"] is True and document["no_fingertip_contact"] is False
    assert document["holding_state"] == "HOLDING", "a grasped cup that is no longer supported is HOLDING"


def test_close_refuses_by_name_for_each_missing_piece():
    for kwargs, expected in (
            ({"with_dispatch": False}, "CLOSE: broker.dispatch"),
            ({"with_wait": False}, "CLOSE: driver.wait")):
        calls = []
        boundary, ticket, _capture = _case(calls, **kwargs)
        with pytest.raises(PickPlaceSearchBoundaryError, match=expected):
            PickPlaceSearchBoundary.sequence_phase(
                boundary, "CLOSE", {"session_id": ticket[3], "attempt_id": ticket[4]},
                observed=None, selected_source=None, gripper_closed_rad=0.5, close_duration_s=0.4,
                support_distance_max_m=0.02)

    calls = []
    boundary, ticket, _capture = _case(calls)
    for missing in ({"gripper_closed_rad": None}, {"close_duration_s": None},
                    {"support_distance_max_m": None}):
        arguments = {"gripper_closed_rad": 0.5, "close_duration_s": 0.4, "support_distance_max_m": 0.02,
                     **missing}
        with pytest.raises(PickPlaceSearchBoundaryError, match="TASK8_PHASE_NOT_PROVISIONED"):
            PickPlaceSearchBoundary.sequence_phase(
                boundary, "CLOSE", {"session_id": ticket[3], "attempt_id": ticket[4]},
                observed=None, selected_source=None, **arguments)


def test_close_refuses_a_readback_without_the_bilateral_grasp():
    calls = []
    boundary, ticket, _capture = _case(calls, bilateral=False)
    with pytest.raises(PickPlaceSearchBoundaryError, match="CLOSE: no bilateral grasp"):
        PickPlaceSearchBoundary.sequence_phase(
            boundary, "CLOSE", {"session_id": ticket[3], "attempt_id": ticket[4]},
            observed=None, selected_source=None, gripper_closed_rad=0.5, close_duration_s=0.4,
            support_distance_max_m=0.02)
