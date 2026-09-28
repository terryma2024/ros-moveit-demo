"""Preflight adapter: the 14 gates from controlled vocabulary, with independent IK and plan receipts.

Every phase's IK gate and plan gate must come from its own plan() call, bound to the same candidate
identity, start state, target and provenance. Nothing here may invent a pose, a threshold, a state name
or an implicit default.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.candidate_source import candidate_identity, load_candidate_source
from so101_demo.act.sampling import REACHABILITY_GATES
from so101_demo.adapters.act.candidate_reachability import (
    PHASE_STATES,
    build_candidate_source_document,
    build_reachability_document,
    probe_candidate,
    require_gate_kind,
    table_clearance,
    visibility,
)
from so101_demo.adapters.act.reachability_report import ReachabilityReportPort
from so101_demo.core.domain import State
from so101_demo.ports.evidence import PoseEvidence
from so101_demo.ports.robot_control import JointStateEvidence

PROFILE = {"cup_start_m": [0.21, -0.02, 0.0], "joint_start_rad": [0.0] * 6,
           "model_sha256": "1" * 64, "scene_sha256": "2" * 64, "eligible_for_collection": True}


def _candidate(seed=7):
    return {"xy": [0.21, -0.02], "arm_q": [0.0] * 6, "search_start_rad": 0.0, "seed": seed}


def _start_state():
    return JointStateEvidence(("1", "2", "3", "4", "5", "6"), (0.0,) * 6, 0.0)


def _cup_pose():
    return PoseEvidence((0.21, -0.02, 0.02), (0.0, 0.0, 0.0, 1.0))


def _targets():
    """The policy's own five phase states, each with its own resolved pose (no literal chosen here)."""
    return {state: PoseEvidence((0.2, -0.02, 0.12 + 0.02 * index), (0.0, 0.0, 0.0, 1.0))
            for index, state in enumerate(PHASE_STATES.values())}


class _Planner:
    def __init__(self, *, refuse_ik=(), collision_free=True):
        self.calls = []
        self._refuse_ik = set(refuse_ik)
        self._collision_free = collision_free
        self._kind = "plan"

    def plan(self, state, target, start, cup_pose_world, timeout_s):
        self._kind = "ik" if self._kind == "plan" else "plan"      # call order: ik then plan per phase
        kind = self._kind
        self.calls.append({"state": str(state), "kind": kind, "target": target, "start": start,
                           "cup_pose_world": cup_pose_world, "timeout_s": timeout_s})
        accepted = not (kind == "ik" and str(state) in self._refuse_ik)
        return SimpleNamespace(accepted=accepted, terminal_state=None,
                               moveit_error_code=0 if accepted else -1,
                               failure_code=None if accepted else "PLAN_FAILED",
                               collision_pairs=() if self._collision_free else (("cup", "wall"),),
                               planning_receipts=({"kind": kind},))


def _probe(planner=None, targets=None):
    return probe_candidate(candidate=_candidate(), targets=targets or _targets(),
                           start_state=_start_state(), planner=planner or _Planner(),
                           provenance={"calibration_sha256": "a" * 64, "config_sha256": "b" * 64,
                                       "policy_fingerprint": "c" * 64, "source_sha256": "d" * 64},
                           cup_pose_world=_cup_pose(), timeout_s=1.0)


def test_five_phases_come_from_the_policy_state_vocabulary():
    assert [str(state) for state in PHASE_STATES.values()] == [
        "MOVE_ABOVE_OBJECT", "DESCEND", "LIFT", "DESCEND_TO_PLACE", "RETREAT"]
    assert all(isinstance(state, State) for state in PHASE_STATES.values())


def test_each_phase_has_its_own_ik_and_plan_receipt_from_its_own_call():
    planner = _Planner()
    probe = _probe(planner)
    kinds = [receipt["gate_kind"] for receipt in probe["receipts"]]
    assert kinds.count("ik") == 5 and kinds.count("plan") == 5
    assert len(planner.calls) == 10
    identity = candidate_identity(_candidate())
    for receipt in probe["receipts"]:
        assert receipt["candidate_identity"] == identity
        assert receipt["provenance_sha256"] and receipt["start_sha256"] and receipt["target_sha256"]
    binding = lambda kind: {json.dumps({key: receipt[key] for key in
                                        ("candidate_identity", "start_sha256", "target_sha256",
                                         "provenance_sha256", "cup_sha256")}, sort_keys=True)
                            for receipt in probe["receipts"] if receipt["gate_kind"] == kind}
    assert binding("ik") == binding("plan")          # both calls bound to identical evidence


def test_each_receipt_hash_is_its_own_so_one_gate_cannot_borrow_another():
    probe = _probe()
    hashes = [receipt["receipt_sha256"] for receipt in probe["receipts"]]
    assert len(set(hashes)) == 10


def test_a_full_plan_receipt_cannot_be_used_as_ik_proof():
    with pytest.raises(ValueError, match="GATE_KIND_MISMATCH"):
        require_gate_kind({"gate_kind": "plan", "phase": "pregrasp"}, "ik")
    with pytest.raises(ValueError, match="GATE_KIND_MISMATCH"):
        require_gate_kind({"gate_kind": "ik", "phase": "pregrasp"}, "plan")
    require_gate_kind({"gate_kind": "ik", "phase": "pregrasp"}, "ik")


def test_a_refused_ik_call_does_not_leak_an_accepted_plan_verdict():
    probe = _probe(_Planner(refuse_ik=("DESCEND",)))
    verdicts = {f"{receipt['phase']}_{receipt['gate_kind']}": receipt["ok"]
                for receipt in probe["receipts"]}
    assert verdicts["grasp_ik"] is False          # DESCEND is the grasp phase's controlled state
    assert verdicts["grasp_plan"] is True


def test_collision_pairs_and_table_clearance_fail_closed():
    probe = _probe(_Planner(collision_free=False))
    document = build_reachability_document({**probe, "table_clear": {"ok": False,
                                              "reason": "SCENE_GEOMETRY_UNAVAILABLE"},
                                            "head_visible": False, "wrist_visible": False})
    gates = document["gates"][candidate_identity(_candidate())]
    assert set(gates) == set(REACHABILITY_GATES)
    assert gates["collision_free"]["ok"] is False
    assert gates["table_clear"]["ok"] is False
    assert table_clearance(targets=_targets(), minimum_table_clearance_m=0.01,
                           table_height_m=None)["reason"] == "SCENE_GEOMETRY_UNAVAILABLE"


def test_reachability_document_is_accepted_by_the_cp765_port(tmp_path):
    probe = _probe()
    document = build_reachability_document({**probe, "table_clear": {"ok": True, "reason": None,
                                              "lowest_target_z_m": 0.12,
                                              "minimum_table_clearance_m": 0.01},
                                            "head_visible": True, "wrist_visible": True})
    path = tmp_path / "reachability.json"
    path.write_text(json.dumps(document))
    verdicts = ReachabilityReportPort.from_path(path).verify(_candidate())
    assert len(verdicts) == 14 and all(verdicts[name] is True for name in REACHABILITY_GATES)
    with pytest.raises(ValueError, match="CANDIDATE_NOT_IN_REACHABILITY_REPORT"):
        ReachabilityReportPort.from_path(path).verify(_candidate(seed=99))


def test_candidate_source_document_is_accepted_by_the_cp765_loader(tmp_path):
    document = build_candidate_source_document(
        candidates={"train": [_candidate(1)], "validation": [_candidate(2)],
                    "offline_test": [_candidate(3)], "rollout_validation": [_candidate(4)],
                    "rollout_test": [_candidate(5)]},
        qualification={"functional": [_candidate(100 + index) for index in range(8)],
                       "load": [_candidate(200 + index) for index in range(40)]},
        config_sha256="a" * 64, minimum_gap_m=0.02)
    path = tmp_path / "candidate-source.json"
    path.write_text(json.dumps(document))
    loaded = load_candidate_source(path)
    assert len(loaded["qualification"]["load"]) == 40
    assert loaded["minimum_gap_m"] == 0.02
    with pytest.raises(ValueError, match="QUALIFICATION_CANDIDATE_COUNT_INVALID"):
        build_candidate_source_document(
            candidates={"train": [_candidate(1)], "validation": [_candidate(2)],
                        "offline_test": [_candidate(3)], "rollout_validation": [_candidate(4)],
                        "rollout_test": [_candidate(5)]},
            qualification={"functional": [_candidate(100 + index) for index in range(7)],
                           "load": [_candidate(200 + index) for index in range(40)]},
            config_sha256="a" * 64, minimum_gap_m=0.02)


def test_visibility_requires_the_frozen_eligible_profile():
    eligible = visibility(candidate=_candidate(), profile=PROFILE)
    assert eligible["head_visible"] is True and eligible["wrist_visible"] is True
    ineligible = visibility(candidate=_candidate(), profile={**PROFILE, "eligible_for_collection": False})
    assert ineligible["head_visible"] is False and ineligible["wrist_visible"] is False
    assert ineligible["reason"] == "VISIBILITY_PROFILE_NOT_ELIGIBLE"
    incomplete = visibility(candidate=_candidate(), profile={"cup_start_m": [0.0, 0.0, 0.0]})
    assert incomplete["reason"] == "VISIBILITY_PROFILE_INCOMPLETE"
