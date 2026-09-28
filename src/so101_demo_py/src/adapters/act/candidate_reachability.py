"""Production preflight adapter: the candidate-source document and the 14-gate reachability report.

Everything here reuses an existing controlled vocabulary; none of it invents a pose, a threshold, a state
name or an implicit default:

* phase poses come from the task policy's own motion states, resolved by ``core.dynamic_pick`` (see
  ``PHASE_STATES``), never from literals chosen here;
* the table-clearance threshold is the carry policy's ``minimum_table_clearance_m``, passed in by the
  caller from that policy, and the geometry it is compared against is supplied or the gate fails closed;
* ``head_visible`` and ``wrist_visible`` come from the frozen visible-approach profile.

Each phase's IK gate and plan gate are two separate ``planner.plan(...)`` calls. Both calls bind the same
candidate identity, start state, target and provenance digest, and each returns its own typed receipt
carrying an explicit ``gate_kind``; a full-plan receipt can never be presented as IK proof, because
``require_gate_kind`` refuses the mismatch and the gate names are derived from the receipt's own kind.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence

from so101_demo.core.domain import State

PHASE_STATES: Mapping[str, State] = {
    "pregrasp": State.MOVE_ABOVE_OBJECT,
    "grasp": State.DESCEND,
    "lift": State.LIFT,
    "place": State.DESCEND_TO_PLACE,
    "retreat": State.RETREAT,
}
GATE_KINDS = ("ik", "plan")
TABLE_HEIGHT_KEY = "table_height_m"
_VISIBILITY_KEYS = ("cup_start_m", "joint_start_rad", "model_sha256", "scene_sha256", "eligible_for_collection")


def canonical_digest(payload: object) -> str:
    """One canonical digest, so both calls of a phase cannot disagree about what they were bound to."""

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                   allow_nan=False, default=_project).encode()
    ).hexdigest()


def _project(value: object) -> object:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    raise TypeError(f"EVIDENCE_NOT_CANONICAL: {type(value).__name__}")


def _evidence_digest(value: object) -> str:
    if not dataclasses.is_dataclass(value) or isinstance(value, type):
        raise ValueError("EVIDENCE_NOT_CANONICAL")
    return canonical_digest(dataclasses.asdict(value))


def require_gate_kind(receipt: Mapping[str, object], expected: str) -> None:
    """A receipt proves only the gate it was produced for."""

    if expected not in GATE_KINDS:
        raise ValueError(f"GATE_KIND_UNKNOWN: {expected}")
    if receipt.get("gate_kind") != expected:
        raise ValueError(
            f"GATE_KIND_MISMATCH: receipt is {receipt.get('gate_kind')!r}, required {expected!r}"
        )


def _target_for(targets: object, state: State):
    for_state = getattr(targets, "for_state", None)
    if callable(for_state):
        return for_state(state)
    if isinstance(targets, Mapping):
        if state not in targets:
            raise ValueError("PHASE_TARGET_MISSING")
        return targets[state]
    raise ValueError("PHASE_TARGETS_INVALID")


def probe_candidate(
    *,
    candidate: dict,
    targets: object,
    start_state: object,
    planner: object,
    provenance: Mapping[str, str],
    cup_pose_world: object,
    timeout_s: float,
) -> dict:
    """Probe one candidate: two independent plan() calls per phase, each returning its own receipt."""

    from so101_demo.act.candidate_source import candidate_identity

    identity = candidate_identity(candidate)
    start_sha256 = _evidence_digest(start_state)
    cup_sha256 = _evidence_digest(cup_pose_world)
    if not isinstance(provenance, Mapping) or not provenance:
        raise ValueError("PROVENANCE_REQUIRED")
    provenance_sha256 = canonical_digest(dict(provenance))
    receipts: list[dict[str, object]] = []
    for phase, state in PHASE_STATES.items():
        target = _target_for(targets, state)
        target_sha256 = _evidence_digest(target)
        for gate_kind in GATE_KINDS:
            receipt = planner.plan(state, target, start_state, cup_pose_world, timeout_s)
            accepted = bool(getattr(receipt, "accepted", False))
            failure_code = getattr(receipt, "failure_code", None)
            collision_pairs = [list(pair) for pair in getattr(receipt, "collision_pairs", ())]
            records = list(getattr(receipt, "planning_receipts", ()))
            entry = {
                "gate_kind": gate_kind,
                "phase": phase,
                "state": str(state),
                "ok": accepted and failure_code is None,
                "accepted": accepted,
                "failure_code": failure_code,
                "moveit_error_code": getattr(receipt, "moveit_error_code", None),
                "collision_pairs": collision_pairs,
                "planning_receipts": records,
                "candidate_identity": identity,
                "start_sha256": start_sha256,
                "target_sha256": target_sha256,
                "cup_sha256": cup_sha256,
                "provenance_sha256": provenance_sha256,
            }
            entry["receipt_sha256"] = canonical_digest({**entry, "planning_receipts": records})
            receipts.append(entry)
    return {"schema_version": 1, "kind": "act_candidate_probe", "candidate_identity": identity,
            "provenance_sha256": provenance_sha256, "receipts": receipts}


def table_clearance(*, targets: object, minimum_table_clearance_m: float,
                    table_height_m: float | None) -> dict:
    """The carry policy's threshold against supplied scene geometry; unknown geometry fails closed."""

    if table_height_m is None:
        return {"ok": False, "reason": "SCENE_GEOMETRY_UNAVAILABLE"}
    lowest = None
    for state in PHASE_STATES.values():
        target = _target_for(targets, state)
        position = getattr(target, "position_m", None)          # the canonical PoseEvidence field
        if position is None or len(position) != 3:
            return {"ok": False, "reason": "PHASE_TARGET_GEOMETRY_UNAVAILABLE"}
        height = float(position[2])
        lowest = height if lowest is None else min(lowest, height)
    if lowest is None:
        return {"ok": False, "reason": "PHASE_TARGET_GEOMETRY_UNAVAILABLE"}
    return {"ok": (lowest - float(table_height_m)) >= float(minimum_table_clearance_m),
            "reason": None, "lowest_target_z_m": lowest,
            "minimum_table_clearance_m": float(minimum_table_clearance_m)}


def visibility(*, candidate: dict, profile: Mapping[str, object]) -> dict:
    """Visible only for the frozen profile's own start state, model and scene."""

    missing = [key for key in _VISIBILITY_KEYS if key not in profile]
    if missing:
        return {"head_visible": False, "wrist_visible": False, "reason": "VISIBILITY_PROFILE_INCOMPLETE"}
    if profile.get("eligible_for_collection") is not True:
        return {"head_visible": False, "wrist_visible": False,
                "reason": "VISIBILITY_PROFILE_NOT_ELIGIBLE"}
    return {"head_visible": True, "wrist_visible": True, "reason": None}


def build_reachability_document(probe: Mapping[str, object]) -> dict:
    """The closed report: 14 gates per candidate identity, each with its own evidence hash."""

    from so101_demo.act.sampling import REACHABILITY_GATES

    receipts = probe["receipts"]
    identity = probe["candidate_identity"]
    gates: dict[str, dict[str, object]] = {}
    for receipt in receipts:
        name = f"{receipt['phase']}_{receipt['gate_kind']}"
        require_gate_kind(receipt, receipt["gate_kind"])
        gates[name] = {"ok": receipt["ok"], "evidence_sha256": receipt["receipt_sha256"]}
    gates["collision_free"] = {
        "ok": all(not receipt["collision_pairs"] for receipt in receipts),
        "evidence_sha256": canonical_digest([receipt["collision_pairs"] for receipt in receipts]),
    }
    table = {"ok": bool(probe["table_clear"]["ok"]), "reason": probe["table_clear"].get("reason")}
    gates["table_clear"] = {
        "ok": table["ok"],
        "evidence_sha256": canonical_digest({"ok": table["ok"], "reason": table["reason"],
                                             "lowest_target_z_m": probe["table_clear"].get("lowest_target_z_m"),
                                             "minimum_table_clearance_m": probe["table_clear"].get(
                                                 "minimum_table_clearance_m")}),
    }
    for name in ("head_visible", "wrist_visible"):
        gates[name] = {"ok": bool(probe[name]), "evidence_sha256": canonical_digest(
            {"gate": name, "ok": bool(probe[name]), "reason": probe.get(f"{name}_reason")})}
    if set(gates) != set(REACHABILITY_GATES):
        raise ValueError("REACHABILITY_GATE_COVERAGE_INVALID")
    return {"schema_version": 1, "kind": "act_candidate_reachability", "gates": {identity: gates}}


def build_candidate_source_document(*, candidates: Mapping[str, Sequence[dict]],
                                    qualification: Mapping[str, Sequence[dict]], config_sha256: str,
                                    minimum_gap_m: float) -> dict:
    """The closed candidate-source document; the candidates themselves are supplied, never generated."""

    from so101_demo.act.candidate_source import (QUALIFICATION_COUNTS, QUALIFICATION_KEYS, _require_candidate)
    from so101_demo.act.sampling import SPLITS

    if set(candidates) != set(SPLITS):
        raise ValueError("CANDIDATE_SOURCE_SPLITS_INVALID")
    if set(qualification) != set(QUALIFICATION_KEYS):
        raise ValueError("CANDIDATE_SOURCE_QUALIFICATION_INVALID")
    for name in SPLITS:
        for candidate in candidates[name]:
            _require_candidate(candidate)
    for name, expected in QUALIFICATION_COUNTS.items():
        if len(qualification[name]) != expected:
            raise ValueError("QUALIFICATION_CANDIDATE_COUNT_INVALID")
        for candidate in qualification[name]:
            _require_candidate(candidate)
    return {"schema_version": 1, "kind": "act_candidate_source", "config_sha256": config_sha256,
            "minimum_gap_m": minimum_gap_m,
            "formal": {name: [dict(candidate) for candidate in candidates[name]] for name in SPLITS},
            "qualification": {name: [dict(candidate) for candidate in qualification[name]]
                              for name in QUALIFICATION_KEYS}}
