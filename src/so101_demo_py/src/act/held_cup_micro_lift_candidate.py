"""Closed source-only held-cup micro-lift rows; no live command authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np

from so101_demo.act.contracts import validate_action_prefix
from so101_demo.act.execution import bounded_positions
from so101_demo.act.approach_grasp_contact_diagnostic import require_full_sources
from so101_demo.act.alternate_anchor_grasp_contact_diagnostic import require_alt_sources
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.phase_contact_allowlist import PhaseContactAllowlist


_PROFILE_SHA = "c950784be2827025cf8ce203d63a09adf6085f36b7a20cd9f6752837d93462b0"
_SOURCE_RESULT_SHA = "ae9450fe5216eaca3484d70834d6a76f673ccbd83479f8788c9a187cecfae0cf"
_SCENE_SHA = "4db48e35df9e91fc6868d303725badd0237fb10754d1e298637f5b0e1e55ed4f"
_MODEL_SHA = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
_POLICY_FINGERPRINT = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"
_BASE_KIND = {
    "default": "ACT_TASK6_FULL_CONTACT_DIAGNOSTIC",
    "left": "ACT_TASK6_ALT_FULL_CONTACT_DIAGNOSTIC",
    "forward": "ACT_TASK6_ALT_FULL_CONTACT_DIAGNOSTIC",
}
_BASE_COUNT = {"default": 281, "left": 168, "forward": 235}
_ROWS_SHA = {
    "default": "c785fd11243e1b9442553bbb9982b4f7bb762a9513dae78895f25a6e2a05812c",
    "left": "f85ee8d895322c959a9ee10832718214f70ae94ef519828f05ef526da95b15c3",
    "forward": "a3b1b04945f5422fcaa59f03f539f3c5017c396c6b1e87fff15ee84e3ca968bf",
}
_ADDED_KEYS = frozenset({
    "command_authority", "lift_profile_path", "lift_profile_sha256",
    "source_base_kind", "source_base_manifest_sha256", "lift_phase_start",
    "lift_rows_sha256", "source_result_sha256",
})


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _row_digest(rows: list[list[float]]) -> str:
    return hashlib.sha256(json.dumps(rows, separators=(",", ":"),
                                     allow_nan=False).encode() + b"\n").hexdigest()


def _base_from_candidate(value: dict) -> dict:
    base = {key: item for key, item in value.items() if key not in _ADDED_KEYS}
    base["kind"] = value["source_base_kind"]
    base["manifest_sha256"] = value["source_base_manifest_sha256"]
    base["target_positions"] = value["target_positions"][:-9]
    base["segment_phases"] = value["segment_phases"][:-1]
    base["allowed_contact_pairs_by_phase"] = {
        phase: pairs for phase, pairs in value["allowed_contact_pairs_by_phase"].items()
        if phase != "LIFT"
    }
    if value["anchor"] == "default":
        del base["anchor"]
    return base


def _check_base(base: dict, *, pairs_factory) -> str:
    if not isinstance(base, dict):
        raise ValueError("held-cup lift base manifest invalid")
    kind = base.get("kind")
    if kind == _BASE_KIND["default"]:
        require_full_sources(base, pairs_factory=pairs_factory)
        return "default"
    if kind == _BASE_KIND["left"]:
        require_alt_sources(base, pairs_factory=pairs_factory)
        return base["anchor"]
    raise ValueError("held-cup lift base kind invalid")


def build_lift_candidate_manifest(
    base_manifest: dict, *, profile_path: Path, pairs_factory=PhaseContactAllowlist,
) -> dict:
    """Append one pinned LIFT prefix while explicitly refusing command authority."""
    anchor = _check_base(base_manifest, pairs_factory=pairs_factory)
    if anchor not in _BASE_KIND:
        raise ValueError("held-cup lift anchor invalid")
    profile_path = Path(profile_path).resolve()
    if not profile_path.is_file() or _digest(profile_path) != _PROFILE_SHA:
        raise ValueError("held-cup lift profile drift")
    profile = json.loads(profile_path.read_bytes())
    if (not isinstance(profile, dict)
            or set(profile) != {"schema_version", "kind", "eligible_for_collection",
                                "mujoco_version", "scene_sha256", "model_sha256",
                                "policy_fingerprint", "source_result_sha256", "anchors"}
            or profile["schema_version"] != 1
            or profile["kind"] != "ACT_HELD_CUP_MICRO_LIFT_CANDIDATES"
            or profile["eligible_for_collection"] is not False
            or profile["mujoco_version"] != "3.12.0"
            or profile["scene_sha256"] != _SCENE_SHA
            or profile["model_sha256"] != _MODEL_SHA
            or profile["policy_fingerprint"] != _POLICY_FINGERPRINT
            or profile["source_result_sha256"] != _SOURCE_RESULT_SHA
            or not isinstance(profile["anchors"], dict)
            or set(profile["anchors"]) != set(_BASE_KIND)):
        raise ValueError("held-cup lift profile invalid")
    if (base_manifest["scene_sha256"] != _SCENE_SHA
            or base_manifest["model_sha256"] != _MODEL_SHA
            or base_manifest["policy_fingerprint"] != _POLICY_FINGERPRINT
            or len(base_manifest["segment_phases"]) != _BASE_COUNT[anchor]
            or base_manifest["segment_phases"][-1] != "CONTACT"):
        raise ValueError("held-cup lift base source drift")
    selected = profile["anchors"][anchor]
    if (not isinstance(selected, dict)
            or set(selected) != {"delta_q_rad", "candidate_rows_sha256"}
            or selected["candidate_rows_sha256"] != _ROWS_SHA[anchor]):
        raise ValueError("held-cup lift candidate invalid")
    delta = bounded_positions(selected["delta_q_rad"])
    start = np.array(bounded_positions(base_manifest["target_positions"][-1]))
    motion = np.array(delta)
    rows = [start.tolist()]
    for part in range(1, 8):
        fraction = part / 7
        ease = fraction * fraction * (3 - 2 * fraction)
        rows.append((start + motion * ease).tolist())
    rows.append((start + motion).tolist())
    if (_row_digest(rows) != _ROWS_SHA[anchor]
            or any(bounded_positions(row) != tuple(row) for row in rows)):
        raise ValueError("held-cup lift rows drift")
    scene = Path(base_manifest["scene_path"])
    model = mujoco.MjModel.from_xml_path(str(scene))
    pairs = pairs_factory(model=model, scene_path=scene,
                          proposal_path=Path(base_manifest["proposal_path"]),
                          receipt_path=Path(base_manifest["receipt_path"]),
                          expected_fingerprint=_POLICY_FINGERPRINT)
    if (model_sha256(model) != _MODEL_SHA
            or pairs.model_sha256 != _MODEL_SHA
            or pairs.fingerprint != _POLICY_FINGERPRINT):
        raise ValueError("held-cup lift activation drift")
    allowed = [list(pair) for pair in sorted(pairs.for_phase("MICRO_LIFT"))]
    if not allowed:
        raise ValueError("held-cup lift pairs missing")
    result = dict(base_manifest)
    result.update(
        kind="ACT_HELD_CUP_MICRO_LIFT_CANDIDATE",
        anchor=anchor, command_authority=False,
        lift_profile_path=str(profile_path), lift_profile_sha256=_PROFILE_SHA,
        source_base_kind=base_manifest["kind"],
        source_base_manifest_sha256=base_manifest["manifest_sha256"],
        lift_phase_start=_BASE_COUNT[anchor], lift_rows_sha256=_ROWS_SHA[anchor],
        source_result_sha256=_SOURCE_RESULT_SHA,
        target_positions=base_manifest["target_positions"] + rows,
        segment_phases=base_manifest["segment_phases"] + ["LIFT"],
        allowed_contact_pairs_by_phase={
            **base_manifest["allowed_contact_pairs_by_phase"], "LIFT": allowed,
        },
    )
    del result["manifest_sha256"]
    result["manifest_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    require_lift_candidate_manifest(result)
    return result


def require_lift_candidate_manifest(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("held-cup lift manifest invalid")
    anchor = value.get("anchor")
    if (anchor not in _BASE_KIND
            or value.get("kind") != "ACT_HELD_CUP_MICRO_LIFT_CANDIDATE"
            or value.get("eligible_for_collection") is not False
            or value.get("command_authority") is not False
            or value.get("backend") != "mujoco"
            or value.get("mujoco_version") != "3.12.0"
            or value.get("source_base_kind") != _BASE_KIND[anchor]
            or value.get("source_result_sha256") != _SOURCE_RESULT_SHA
            or value.get("lift_profile_sha256") != _PROFILE_SHA
            or value.get("scene_sha256") != _SCENE_SHA
            or value.get("model_sha256") != _MODEL_SHA
            or value.get("policy_fingerprint") != _POLICY_FINGERPRINT
            or value.get("segment_rows") != 9
            or value.get("lift_phase_start") != _BASE_COUNT[anchor]
            or value.get("lift_rows_sha256") != _ROWS_SHA[anchor]
            or not isinstance(value.get("lift_profile_path"), str)
            or not Path(value["lift_profile_path"]).is_absolute()
            or not isinstance(value.get("target_positions"), list)
            or len(value["target_positions"]) != (_BASE_COUNT[anchor] + 1) * 9
            or not isinstance(value.get("segment_phases"), list)
            or len(value["segment_phases"]) != _BASE_COUNT[anchor] + 1
            or value["segment_phases"][-1] != "LIFT"
            or not isinstance(value.get("allowed_contact_pairs_by_phase"), dict)
            or set(value["allowed_contact_pairs_by_phase"]) != {"APPROACH", "CONTACT", "LIFT"}
            or not isinstance(value.get("manifest_sha256"), str)):
        raise ValueError("held-cup lift manifest role invalid")
    base = _base_from_candidate(value)
    if (set(value) != set(base) | _ADDED_KEYS | ({"anchor"} if anchor == "default" else set())
            or hashlib.sha256(_canonical({key: item for key, item in base.items()
                                          if key != "manifest_sha256"})).hexdigest() !=
               value["source_base_manifest_sha256"]
            or _row_digest(value["target_positions"][-9:]) != _ROWS_SHA[anchor]
            or value["manifest_sha256"] != hashlib.sha256(_canonical(
                {key: item for key, item in value.items()
                 if key != "manifest_sha256"})).hexdigest()):
        raise ValueError("held-cup lift manifest replay invalid")
    return value


def require_lift_candidate_sources(value: dict, *, pairs_factory=PhaseContactAllowlist) -> dict:
    require_lift_candidate_manifest(value)
    rebuilt = build_lift_candidate_manifest(
        _base_from_candidate(value), profile_path=Path(value["lift_profile_path"]),
        pairs_factory=pairs_factory)
    if _canonical(rebuilt) != _canonical(value):
        raise ValueError("held-cup lift source replay mismatch")
    return value


def lift_prefix_matches(prefix: object, manifest: dict) -> bool:
    try:
        require_lift_candidate_manifest(manifest)
        checked = validate_action_prefix(prefix)
        sequence = manifest["lift_phase_start"]
        prior = manifest["target_positions"][sequence * 9 - 1]
        expected = [prior] + manifest["target_positions"][sequence * 9:(sequence + 1) * 9]
        return (checked["session_id"] == manifest["session_id"]
                and checked["attempt_id"] == manifest["attempt_id"]
                and checked["sequence"] == sequence
                and ("first_target_delay_s" not in manifest or
                     checked.get("first_target_delay_s") == manifest["first_target_delay_s"])
                and len(checked["positions"]) == len(expected)
                and all(all(abs(a - b) <= 1e-10 for a, b in zip(row, target, strict=True))
                        for row, target in zip(checked["positions"], expected, strict=True)))
    except (KeyError, TypeError, ValueError):
        return False
