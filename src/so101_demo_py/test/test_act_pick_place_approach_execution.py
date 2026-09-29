"""The boundary's APPROACH chain, with the real screen and snapshot and only the ROS calls substituted.

`PickPlaceSearchBoundary.execute_approach` is called unbound on a stub `self` that carries exactly the state the method
reads. The screen, its checker and the proof's snapshot come from the path-screen suite's own fixture - the one that
already drives a REAL screen against a REAL MuJoCo model and a REAL search readback - so this test substitutes the
broker/executor calls and nothing else.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_pick_place_approach_path_screen import physical_inputs  # noqa: E402

from so101_demo.adapters.act.pick_place_search_boundary import (  # noqa: E402
    PickPlaceSearchBoundary, PickPlaceSearchBoundaryError,
)

IDENTITY = {"policy_fingerprint": "ad" * 32, "profile_sha256": "af" * 32,
            "contact_scope_sha256": "ba" * 32, "checker_sha256": "bb" * 32,
            "expected_samples": 51}      # the fixture's checker reports 51 samples, so the identity says 51


def _case(tmp_path, calls, *, with_screen=True, with_executor=True, with_wait=True, with_snapshot=True):
    """The real screen and its snapshot, wrapped in the stub `self` `execute_approach` reads."""

    screen, prefix, goals, checks, sources, _driver, _owner, _events, _qpos, _qvel = physical_inputs()
    # the ticket names the PREFIX's own case: the issuing authority refuses any other scope
    ticket = (7, "owner-key-1", "act", prefix["session_id"], prefix["attempt_id"])
    # the REAL inspector stays in place and is wrapped only so this test can see that it ran: the real screen does not
    # report into the test's own call list, which is exactly why it is worth using
    real_inspect = screen.inspect

    def _recording_inspect(goals_, prefix_):
        calls.append(("inspect", len(goals_)))
        return real_inspect(goals_, prefix_)

    screen.inspect = _recording_inspect

    # the PROOF's snapshot is the paired execution's own document, whose shape `path_proof._state_bytes` and
    # `checker_inputs` fix field by field: the controller bridge (point + time), the model's dimensions and state,
    # the phase/holding facts, and the controller's start state and time - which must equal the request's axis
    checker = screen.path_checker
    checker.step, checker.clearance = 0.002, 0.01      # the prover reports these; the fixture's checker omits them
    proof_snapshot = {
        "model_sha256": checker.model_sha256,
        "model_qpos": [0.0] * checker.model.nq, "model_qvel": [0.0] * checker.model.nv,
        "phase": "APPROACH", "holding_state": "EMPTY", "cup_in_gripper_transform": None,
        "controller_start_time_s": 1.35,
        "controller_start_positions": [0.0] * 6, "controller_start_velocities": [0.0] * 6,
        "controller_bridge": {"time_s": 1.30,
                              "point": {"positions": [0.0] * 6, "velocities": [0.0] * 6,
                                        "accelerations": [0.0] * 6}}}

    class _Executor:
        def approve_with_source(self, ticket, prefix_, receipt):
            calls.append(("approve", receipt.source_kind))
            return "PERMIT"

        def submit(self, ticket, prefix_, permit):
            calls.append(("submit", permit))
            return 42

    if with_wait:
        _Executor.wait_for = lambda self, ticket, gid: calls.append(("wait", gid))
        _Executor.time_axis = lambda self, ticket, gid: (calls.append(("axis", gid)),
                                                         {"bridge_time_s": 1.30, "start_time_s": 1.35})[1]
    if with_snapshot:
        _Executor.snapshot = lambda self, ticket, gid: (calls.append(("snapshot", gid)), proof_snapshot)[1]

    sources.session_id, sources.reset_epoch, sources.phase = "session-1", 2, "APPROACH"
    sources.monotonic = lambda: 1.36
    sources.capture = lambda attempt_id, **kwargs: _capture(prefix)

    broker = SimpleNamespace(
        ownership=SimpleNamespace(ticket=lambda *parts: ticket),
        _prefix_source_port=lambda ticket: {"kind": "SOURCE"},
        prefix_executor=_Executor() if with_executor else None)
    broker.issue_prefix_source = lambda **kwargs: (calls.append(("issue", kwargs["source_kind"])),
                                                   _receipt(prefix, ticket))[1]
    boundary = SimpleNamespace(
        reset=SimpleNamespace(receipt=SimpleNamespace(new_epoch=2), sources=sources, broker=broker),
        approach_screen=screen if with_screen else None,
        # the validator is phase-aware now, so the stub mirrors that signature and records which phase it was asked about
        sequence_facts=lambda phase, snapshot, request, *, support_distance_max_m: (
            calls.append(("facts", support_distance_max_m, phase)) or {"physics_step": 10}))
    # the preparation is a DOCUMENT, so it is a dict - the method reads prepared["prefix"] and its two digests
    return boundary, {"prefix": prefix, "source_artifact_sha256": "ac" * 32,
                      "policy_fingerprint": "ad" * 32}, ticket


def _capture(prefix):
    """The readback the goals' held row and the phase facts come from - the robot's own state."""

    return {"observation": {"state": [0.0] * 6 + [1.0, 0.0], "sim_time_s": 1.32}}


def _source_document(ticket, prefix):
    """The case's frozen selected source, built to the authority's own field set (all seven SOURCE_KEYS receipts)."""

    from so101_demo.act.prefix_source import SOURCE_KEYS

    return {"session_id": ticket[3], "attempt_id": ticket[4], "reset_epoch": 2, "phase": "SEARCH",
            "physics_step": 9, "simulation_time_s": prefix["observation_time_s"],
            "observation_sha256": "ae" * 32, "source_received_wall_s": {key: 1.0 for key in SOURCE_KEYS}}


def _receipt(prefix, ticket):
    """A real receipt from the production issuing authority, which the prover demands by type."""

    from so101_demo.act.prefix_source import SOURCE_KEYS, PrefixSourceAuthority

    authority = PrefixSourceAuthority(ticket_guard=lambda ticket: None, max_observation_age_s=10.0,
                                      max_prefix_age_s=10.0, monotonic=lambda: 1.36)
    source = {"session_id": ticket[3], "attempt_id": ticket[4], "reset_epoch": 2, "phase": "SEARCH",
              "physics_step": 9, "simulation_time_s": prefix["observation_time_s"],
              "observation_sha256": "ae" * 32,
              "source_received_wall_s": {key: 1.0 for key in SOURCE_KEYS}}
    return authority.issue(ticket=ticket, prefix=prefix, source=source, source_kind="EXPERT_ROUTE",
                           source_artifact_sha256="ac" * 32, contact_policy_fingerprint="ad" * 32)


def test_the_chain_issues_approves_submits_waits_takes_the_snapshot_inspects_and_proves(tmp_path):
    calls = []
    boundary, prepared, ticket = _case(tmp_path, calls)
    result = PickPlaceSearchBoundary.execute_approach(
        boundary, prepared, {"attempt_id": ticket[4]}, prover_identity=IDENTITY, ticket=ticket,
        support_distance_max_m=0.02, source=_source_document(ticket, prepared["prefix"]))

    # the order is the method's own: register, approve, submit, wait, take the proof snapshot, inspect what was
    # submitted, take the time axis, then establish the facts
    # the method's own order: register, approve, submit, wait, take the proof snapshot, take the time axis, inspect
    # what was submitted, then establish the facts
    assert [call[0] for call in calls] == ["issue", "approve", "submit", "wait", "snapshot", "inspect", "axis",
                                          "facts"], calls
    assert calls[0][1] == "EXPERT_ROUTE" and calls[1][1] == "EXPERT_ROUTE"
    assert calls[2][1] == "PERMIT" and calls[3][1] == 42 and calls[4][1] == 42
    assert calls[7][1] == 0.02, "the admitted support distance reaches the facts validator"
    assert calls[7][2] == "APPROACH", "and the validator is told which phase it is establishing"
    assert set(result) == {"proof", "current_snapshot", "facts"}
    assert result["proof"].status == "SAFE", "the proof is computed by the production prover over the real snapshot"
    assert result["current_snapshot"]["observation"]["sim_time_s"] == 1.32, "the readback is what is returned"


def test_each_missing_piece_refuses_by_name(tmp_path):
    """One case per missing piece, so a half-wired APPROACH cannot pass as a finished one."""

    for kwargs, expected in (({"with_screen": False}, "APPROACH: screen"),
                             ({"with_executor": False}, "APPROACH: prefix_executor"),
                             ({"with_wait": False}, "APPROACH: prefix_executor.wait_for"),
                             ({"with_snapshot": False}, "APPROACH: prefix_executor.snapshot")):
        calls = []
        boundary, prepared, ticket = _case(tmp_path, calls, **kwargs)
        with pytest.raises(PickPlaceSearchBoundaryError, match=expected):
            PickPlaceSearchBoundary.execute_approach(
                boundary, prepared, {"attempt_id": ticket[4]}, prover_identity=IDENTITY,
                ticket=ticket, support_distance_max_m=0.02, source=_source_document(ticket, prepared["prefix"]))
