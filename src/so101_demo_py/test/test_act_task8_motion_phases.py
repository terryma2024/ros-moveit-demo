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
                              act_context={"lease_token": "lease-1"}),
        # the release phases read the gripper's open position from the MODEL's own joint range, so the stub carries
        # the fixture's real screen - the same MuJoCo model the rest of this suite uses
        approach_screen=screen)
    if with_ik:
        boundary.motion_target_joints = lambda target: (calls.append(("ik", target)) or (0.5,) * 5)
    for name in ("sequence_phase", "sequence_facts", "_checked_aggregates", "_motion_facts", "_release_facts",
                 "_gripper_open_rad"):
        setattr(boundary, name, MethodType(getattr(PickPlaceSearchBoundary, name), boundary))
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


def test_release_opens_the_gripper_at_the_models_own_limit_and_the_runner_accepts_it():
    """A released cup is one nothing is pinching, that is supported, and that the aggregates call EMPTY."""

    from so101_demo.act.joints import ARM_JOINTS

    calls = []
    boundary, ticket, capture, template, duration = _case(calls, lifted=False)
    document = _call(boundary, ticket, template, duration, phase="RELEASE")

    assert [call[0] for call in calls] == ["dispatch", "wait"], calls
    kind, goal = calls[0][1], calls[0][2]
    assert kind == "gripper"
    assert tuple(goal["joint_names"]) == ARM_JOINTS[5:]
    # the expected value is read from the same model the boundary reads, so the assertion is about the SOURCE of the
    # number rather than about a literal this test would have had to invent
    import mujoco

    model = boundary.approach_screen.path_checker.model
    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, ARM_JOINTS[5])
    low, high = (float(value) for value in model.jnt_range[joint])
    assert goal["positions"][1][0] == (high if abs(high) >= abs(low) else low), \
        "the open position is the model's own limit, not a number this component chose"
    assert goal["positions"][0][0] == capture["observation"]["state"][5], "it starts where the gripper is"
    assert tuple(goal["time_from_start_s"]) == (0.0, 0.4)

    assert document["holding_state"] == "EMPTY" and document["released"] is True
    assert document["cup_supported"] is True and document["no_fingertip_contact"] is True
    stamped = {**document, "phase": "RELEASE", "session_id": ticket[3], "attempt_id": ticket[4],
               "reset_epoch": 2, "release_epoch": 1}
    step = PickPlaceRunner(boundary)._verify_phase("RELEASE", stamped,
                                                   {"session_id": ticket[3], "attempt_id": ticket[4]},
                                                   reset_epoch=2, release_epoch=1,
                                                   after_step=document["physics_step"] - 1)
    assert step == document["physics_step"]


def test_radial_retreat_moves_to_the_retreat_target_and_reports_the_released_facts():
    """RADIAL_RETREAT is the one phase that is BOTH: it aims at the retreat target and its facts are the released ones."""

    calls = []
    boundary, ticket, _capture, template, duration = _case(calls, lifted=False)
    document = _call(boundary, ticket, template, duration, phase="RADIAL_RETREAT")

    assert [call[0] for call in calls] == ["ik", "dispatch", "wait"], calls
    assert calls[0][1].position_m[2] == pytest.approx(template.place_tcp_world.values[2] + 0.10, abs=1e-9), \
        "the retreat target is the place pose plus the template's own retreat clearance"
    assert calls[1][1] == "arm"
    stamped = {**document, "phase": "RADIAL_RETREAT", "session_id": ticket[3], "attempt_id": ticket[4],
               "reset_epoch": 2, "release_epoch": 1}
    step = PickPlaceRunner(boundary)._verify_phase("RADIAL_RETREAT", stamped,
                                                   {"session_id": ticket[3], "attempt_id": ticket[4]},
                                                   reset_epoch=2, release_epoch=1,
                                                   after_step=document["physics_step"] - 1)
    assert step == document["physics_step"]


def test_a_cup_still_held_cannot_claim_a_release():
    calls = []
    boundary, ticket, _capture, template, duration = _case(calls, lifted=True)
    with pytest.raises(PickPlaceSearchBoundaryError, match="RELEASE: the cup is not released"):
        _call(boundary, ticket, template, duration, phase="RELEASE")


def test_final_check_accepts_a_cup_settled_where_it_was_put_and_refuses_one_that_moved():
    """FINAL_CHECK's stability is a comparison against the place target, using the policy's own tolerances."""

    from so101_demo.core.dynamic_pick import compose_pose, inverse_pose
    from so101_demo.core.task_geometry import Pose7

    template = _template()
    expected = compose_pose(template.place_tcp_world, inverse_pose(template.cup_to_cup_grasp)) \
        if hasattr(template, "cup_to_cup_grasp") else compose_pose(template.place_tcp_world,
                                                                  inverse_pose(template.cup_to_tcp_grasp))
    for displacement, expect_accept in ((0.0, True), (0.05, False)):
        calls = []
        boundary, ticket, capture, template, duration = _case(calls, lifted=False)
        settled = (expected.values[0] + displacement,) + tuple(expected.values[1:])
        boundary.reset.sources.capture = lambda *args, **kwargs: {
            **capture, "world": dataclasses.replace(capture["world"],
                                                    object_state=dataclasses.replace(
                                                        capture["world"].object_state,
                                                        position_world=settled[:3],
                                                        orientation_xyzw=settled[3:]))}
        if expect_accept:
            document = _call(boundary, ticket, template, duration, phase="FINAL_CHECK")
            assert document["placement_stable"] is True and document["retreat_stable"] is True
            stamped = {**document, "phase": "FINAL_CHECK", "session_id": ticket[3], "attempt_id": ticket[4],
                       "reset_epoch": 2, "release_epoch": 1}
            step = PickPlaceRunner(boundary)._verify_phase("FINAL_CHECK", stamped,
                                                           {"session_id": ticket[3], "attempt_id": ticket[4]},
                                                           reset_epoch=2, release_epoch=1,
                                                           after_step=document["physics_step"] - 1)
            assert step == document["physics_step"]
        else:
            with pytest.raises(PickPlaceSearchBoundaryError, match="FINAL_CHECK: placement moved by"):
                _call(boundary, ticket, template, duration, phase="FINAL_CHECK")
