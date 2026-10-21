"""State documents of the live boundary search: one round of scenes out, one round of Teacher verdicts back (pure).

``round_state`` / ``round_scenes`` turn the current brackets into the next debug-campaign scene list (one scene per
unfinished ray) plus a sidecar state; ``apply_verdicts`` folds the Teacher verdicts of that campaign back into the
brackets.  All functions take and return plain JSON-able documents, so the runners only add file I/O.
"""

from __future__ import annotations

from dataclasses import asdict

from so101_demo.act import scene_boundary as boundary
from so101_demo.act.scene_list_format import CUP_Z_M, scene_document, scene_row

STATE_KIND = "ACT_BOUNDARY_SEARCH_STATE"
LIMITS_KIND = "ACT_BOUNDARY_KINEMATIC_LIMITS"
STATUS_PENDING = "ROUND_PENDING"
STATUS_UPDATED = "UPDATED"
DEBUG_SPLIT = "functional"
#: A functional debug run takes exactly 8 or 16 scenes (parallel_collection_contracts.FUNCTIONAL_SCENE_COUNTS), so every round
#: has one scene per ray.  A ray that is already final runs a filler: its boundary radius again, which only confirms it and
#: never changes the bracket.
PROBE_FILLER = "filler"
_SEED_BASE = 300


def _bracket(document: dict) -> boundary.Bracket:
    return boundary.Bracket(**document)


def initial_state(limits: dict) -> dict:
    """Round 0: every ray bracketed by its offline kinematic limit."""

    if limits.get("kind") != LIMITS_KIND or set(limits.get("rays", {})) != set(boundary.RAY_NAMES):
        raise ValueError("BOUNDARY_LIMITS_INVALID")
    brackets = {
        name: asdict(boundary.initial_bracket(name, limits["rays"][name]["last_feasible_m"]))
        for name in boundary.RAY_NAMES
    }
    return {
        "kind": STATE_KIND,
        "schema_version": 1,
        "status": STATUS_UPDATED,
        "round": 0,
        "centre_xy": list(limits["centre_xy"]),
        "brackets": brackets,
        "probes": {},
        "history": {name: [] for name in boundary.RAY_NAMES},
    }


def is_finished(state: dict) -> bool:
    return all(b["phase"] == boundary.PHASE_FINAL for b in state["brackets"].values())


def round_state(state: dict) -> tuple[dict, dict | None]:
    """(pending state, scene list) of the next round; the scene list is None when every ray is final.

    Every round has eight scenes: a ray that is already final contributes a filler at its boundary radius.
    """

    if state.get("kind") != STATE_KIND or state.get("status") != STATUS_UPDATED:
        raise ValueError("BOUNDARY_STATE_NOT_UPDATED")
    number = state["round"] + 1
    if is_finished(state):
        return {**state}, None
    probes, rows = {}, []
    for index, name in enumerate(boundary.RAY_NAMES):
        bracket = _bracket(state["brackets"][name])
        probe = boundary.bisection_next(bracket) or boundary.Probe(PROBE_FILLER, bracket.boundary_m)
        xy = boundary.point_on_ray(state["centre_xy"], name, probe.radius_m)
        scene_id = f"bnd-{name}-r{number}"
        probes[name] = {"kind": probe.kind, "radius_m": probe.radius_m, "scene_id": scene_id, "xy": list(xy)}
        rows.append(scene_row(scene_id, _SEED_BASE + 10 * number + index, DEBUG_SPLIT, xy))
    pending = {**state, "status": STATUS_PENDING, "round": number, "probes": probes}
    scenes = scene_document(
        f"boundary-round-{number}",
        rows,
        cup_z_m=CUP_Z_M,
        provenance={
            "purpose": "Teacher success boundary search (debug campaign, not a formal collection)",
            "round": number,
            "centre_xy": state["centre_xy"],
        },
    )
    return pending, scenes


def apply_verdicts(pending: dict, verdicts: dict[str, dict]) -> dict:
    """Fold the Teacher verdict of every probe of the pending round into the brackets.

    ``verdicts`` maps scene id to ``{"teacher_pass": bool, ...}``; a probe without a verdict is an error, never a failure.
    """

    if pending.get("kind") != STATE_KIND or pending.get("status") != STATUS_PENDING:
        raise ValueError("BOUNDARY_STATE_NOT_PENDING")
    brackets, history = dict(pending["brackets"]), {k: list(v) for k, v in pending["history"].items()}
    for name, probe in pending["probes"].items():
        verdict = verdicts.get(probe["scene_id"])
        if verdict is None:
            raise ValueError(f"BOUNDARY_VERDICT_MISSING: {probe['scene_id']}")
        passed = bool(verdict["teacher_pass"])
        if probe["kind"] != PROBE_FILLER:
            updated = boundary.bisection_update(
                _bracket(brackets[name]), boundary.Probe(probe["kind"], probe["radius_m"]), passed
            )
            brackets[name] = asdict(updated)
        history[name].append({"round": pending["round"], **probe, **verdict})
    state = {**pending, "status": STATUS_UPDATED, "brackets": brackets, "probes": {}, "history": history}
    if is_finished(state):
        state["boundary_points"] = {
            name: list(boundary.point_on_ray(pending["centre_xy"], name, brackets[name]["boundary_m"]))
            for name in boundary.RAY_NAMES
        }
    return state
