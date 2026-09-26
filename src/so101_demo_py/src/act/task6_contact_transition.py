"""Exact offline Task 6 contact-transition candidate; no command authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import mujoco

from so101_demo.act.execution import bounded_positions
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.task8_contact_pairs import Task8ContactPairs


_PROFILE_SHA = "15fdd7bd4ac7f017b361e28a9da7b55c188c60e892df66a7e050c554217ca92a"
_CANDIDATE_SHA = "0e1be85eca2716ea31101b3fdfdd73bb72e4133067c10c0c9799ec288edb98bd"
_SCENE_SHA = "4db48e35df9e91fc6868d303725badd0237fb10754d1e298637f5b0e1e55ed4f"
_MODEL_SHA = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
_ROUTE_PROFILE_SHA = "25a272abeffbfaa7e6d6710f0e844856adca6bd09d81a40261956ccbd8021abe"
_POLICY_FINGERPRINT = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"
_PLUGIN_SHA = "612212d5a61c74c4086c0cf2b229cfb5552e58055f8744ee0e9e4d46db655fae"
_PATH_LIMITS = {
    "path_step_s": .02, "path_clearance_m": .002,
    "velocity_limit_rad_s": [.25] * 6,
    "acceleration_limit_rad_s2": [1.2] * 6,
    "max_age_s": .2, "max_skew_s": .05,
    "stop_velocity_rad_s": .002, "submit_lead_s": .05,
    "stop_max_age_s": 1.5,
}
_KEYS = frozenset({
    "schema_version", "kind", "eligible_for_collection", "mujoco_version",
    "scene_sha256", "model_sha256", "source_route_profile_sha256",
    "policy_fingerprint", "candidate_segments_sha256", "cup_start_m",
    "joint_start_rad", "near_arm_rad", "contact_arm_rad", "close_q6_rad",
    "jaw_segments",
})
_MANIFEST_KEYS = frozenset({
    "schema_version", "kind", "eligible_for_collection", "backend",
    "session_id", "attempt_id", "mujoco_version", "scene_path",
    "scene_sha256", "route_profile_path", "route_profile_sha256",
    "profile_path", "profile_sha256", "plugin_path", "plugin_sha256",
    "proposal_path", "proposal_sha256", "receipt_path", "receipt_sha256",
    "policy_fingerprint", "model_sha256", "cup_start_m", "joint_start_rad",
    "neck_start_rad", "target_positions", "segment_phases", "segment_rows",
    "allowed_contact_pairs_by_phase", "diagnostic_limits",
    *tuple(_PATH_LIMITS), "manifest_sha256",
})


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _rows_between(start: list[float], end: list[float]) -> list[list[float]]:
    rows = [start.copy()]
    for part in range(1, 8):
        fraction = part / 7
        ease = fraction * fraction * (3 - 2 * fraction)
        rows.append([a + (b - a) * ease for a, b in zip(start, end, strict=True)])
    rows.append(end.copy())
    return [list(bounded_positions(row)) for row in rows]


def build_transition_segments(
    *, scene_path: Path, route_profile_path: Path, profile_path: Path,
) -> list[tuple[str, list[list[float]]]]:
    """Replay the source-pinned candidate without granting a live permit."""
    scene, route, path = (Path(item).resolve() for item in
                          (scene_path, route_profile_path, profile_path))
    if (any(not item.is_file() for item in (scene, route, path))
            or (_digest(scene), _digest(route), _digest(path)) !=
            (_SCENE_SHA, _ROUTE_PROFILE_SHA, _PROFILE_SHA)
            or mujoco.mj_versionString() != "3.12.0"):
        raise ValueError("Task 6 contact-transition source/runtime drift")
    model = mujoco.MjModel.from_xml_path(str(scene))
    if model_sha256(model) != _MODEL_SHA or model.opt.timestep != .002:
        raise ValueError("Task 6 contact-transition compiled model drift")
    profile = json.loads(path.read_bytes())
    if (not isinstance(profile, dict) or set(profile) != _KEYS
            or profile["schema_version"] != 1
            or profile["kind"] != "TASK6_CONTACT_TRANSITION_DIAGNOSTIC_PROFILE"
            or profile["eligible_for_collection"] is not False
            or profile["mujoco_version"] != "3.12.0"
            or profile["scene_sha256"] != _SCENE_SHA
            or profile["model_sha256"] != _MODEL_SHA
            or profile["source_route_profile_sha256"] != _ROUTE_PROFILE_SHA
            or profile["policy_fingerprint"] != _POLICY_FINGERPRINT
            or profile["candidate_segments_sha256"] != _CANDIDATE_SHA
            or profile["cup_start_m"] != [.02, -.28, .165]
            or type(profile["jaw_segments"]) is not int
            or profile["jaw_segments"] != 32):
        raise ValueError("Task 6 contact-transition profile invalid")
    start = list(bounded_positions(profile["joint_start_rad"]))
    near = list(bounded_positions([*profile["near_arm_rad"], start[5]]))
    contact = list(bounded_positions([*profile["contact_arm_rad"], start[5]]))
    final = list(bounded_positions([*profile["contact_arm_rad"],
                                    profile["close_q6_rad"]]))
    segments = [("APPROACH", _rows_between(start, near)),
                ("CONTACT", _rows_between(near, contact))]
    for index in range(profile["jaw_segments"]):
        first = contact.copy()
        last = contact.copy()
        first[5] = start[5] + (final[5] - start[5]) * index / 32
        last[5] = start[5] + (final[5] - start[5]) * (index + 1) / 32
        if index == 31:
            last[5] = final[5]
        segments.append(("CONTACT", _rows_between(first, last)))
    if (len(segments) != 34 or any(len(rows) != 9 for _, rows in segments)
            or any(segments[index][1][0] != segments[index - 1][1][-1]
                   for index in range(1, len(segments)))):
        raise ValueError("Task 6 contact-transition continuity invalid")
    raw = json.dumps(segments, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if hashlib.sha256(raw).hexdigest() != _CANDIDATE_SHA:
        raise ValueError("Task 6 contact-transition candidate drift")
    return segments


def build_transition_manifest(
    *, scene_path: Path, route_profile_path: Path, profile_path: Path,
    plugin_path: Path, proposal_path: Path, receipt_path: Path,
    session_id: str, attempt_id: str, pairs_factory=Task8ContactPairs,
) -> dict:
    """Bind the exact trajectory to a verified activated model and phase pairs."""
    scene, route, profile, plugin, proposal, receipt = (
        Path(item).resolve() for item in (scene_path, route_profile_path,
                                            profile_path, plugin_path,
                                            proposal_path, receipt_path))
    segments = build_transition_segments(
        scene_path=scene, route_profile_path=route, profile_path=profile)
    if (not isinstance(session_id, str) or not session_id.strip()
            or not isinstance(attempt_id, str) or not attempt_id.strip()
            or any(not item.is_file() for item in (plugin, proposal, receipt))
            or _digest(plugin) != _PLUGIN_SHA):
        raise ValueError("Task 6 contact-transition source/identity invalid")
    model = mujoco.MjModel.from_xml_path(str(scene))
    pairs = pairs_factory(model=model, scene_path=scene,
                          proposal_path=proposal, receipt_path=receipt,
                          expected_fingerprint=_POLICY_FINGERPRINT)
    if (pairs.model_sha256 != _MODEL_SHA
            or pairs.fingerprint != _POLICY_FINGERPRINT):
        raise ValueError("Task 6 contact-transition activation invalid")
    proposal_value = json.loads(proposal.read_bytes())
    threshold = proposal_value["payload"]["thresholds"]["maximum_safe_force_n"]
    if (type(threshold) not in (float, int) or not 0 < threshold <= 11.6):
        raise ValueError("Task 6 contact-transition force limit invalid")
    allowed = [list(pair) for pair in sorted(pairs.for_phase("CLOSE"))]
    if not allowed:
        raise ValueError("Task 6 contact-transition pairs missing")
    profile_value = json.loads(profile.read_bytes())
    manifest = dict(
        schema_version=1, kind="ACT_TASK6_CONTACT_TRANSITION_DIAGNOSTIC",
        eligible_for_collection=False, backend="mujoco",
        session_id=session_id, attempt_id=attempt_id, mujoco_version="3.12.0",
        scene_path=str(scene), scene_sha256=_SCENE_SHA,
        route_profile_path=str(route), route_profile_sha256=_ROUTE_PROFILE_SHA,
        profile_path=str(profile), profile_sha256=_PROFILE_SHA,
        plugin_path=str(plugin), plugin_sha256=_PLUGIN_SHA,
        proposal_path=str(proposal), proposal_sha256=_digest(proposal),
        receipt_path=str(receipt), receipt_sha256=_digest(receipt),
        policy_fingerprint=_POLICY_FINGERPRINT, model_sha256=_MODEL_SHA,
        cup_start_m=profile_value["cup_start_m"],
        joint_start_rad=profile_value["joint_start_rad"], neck_start_rad=0.,
        target_positions=[row for _, rows in segments for row in rows],
        segment_phases=[phase for phase, _ in segments], segment_rows=9,
        allowed_contact_pairs_by_phase={"APPROACH": [], "CONTACT": allowed},
        diagnostic_limits=dict(maximum_force_n=float(threshold),
                               maximum_displacement_m=.03,
                               maximum_ros_skew_s=.02,
                               maximum_receipt_age_s=.2),
        **{key: value.copy() if isinstance(value, list) else value
           for key, value in _PATH_LIMITS.items()},
    )
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    require_transition_manifest(manifest)
    return manifest


def require_transition_manifest(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _MANIFEST_KEYS:
        raise ValueError("Task 6 contact-transition manifest schema invalid")
    if (value["schema_version"] != 1
            or value["kind"] != "ACT_TASK6_CONTACT_TRANSITION_DIAGNOSTIC"
            or value["eligible_for_collection"] is not False
            or value["backend"] != "mujoco"
            or value["mujoco_version"] != "3.12.0"
            or value["scene_sha256"] != _SCENE_SHA
            or value["route_profile_sha256"] != _ROUTE_PROFILE_SHA
            or value["profile_sha256"] != _PROFILE_SHA
            or value["plugin_sha256"] != _PLUGIN_SHA
            or value["model_sha256"] != _MODEL_SHA
            or value["policy_fingerprint"] != _POLICY_FINGERPRINT
            or value["cup_start_m"] != [.02, -.28, .165]
            or value["neck_start_rad"] != 0.
            or value["segment_rows"] != 9
            or value["segment_phases"] != ["APPROACH"] + ["CONTACT"] * 33
            or any(value[key] != expected for key, expected in _PATH_LIMITS.items())):
        raise ValueError("Task 6 contact-transition manifest role/limit invalid")
    if any(not isinstance(value[key], str) or not value[key].strip()
           for key in ("session_id", "attempt_id")):
        raise ValueError("Task 6 contact-transition identity invalid")
    for key, digest in (("scene", _SCENE_SHA),
                        ("route_profile", _ROUTE_PROFILE_SHA),
                        ("profile", _PROFILE_SHA), ("plugin", _PLUGIN_SHA),
                        ("proposal", value["proposal_sha256"]),
                        ("receipt", value["receipt_sha256"])):
        path = value[key + "_path"]
        if (not isinstance(path, str) or not Path(path).is_absolute()
                or not isinstance(digest, str) or len(digest) != 64):
            raise ValueError("Task 6 contact-transition source path/hash invalid")
    if (not isinstance(value["target_positions"], list)
            or len(value["target_positions"]) != 34 * 9):
        raise ValueError("Task 6 contact-transition trajectory invalid")
    for row in value["target_positions"]:
        bounded_positions(row)
    bounded_positions(value["joint_start_rad"])
    expected_pairs = value["allowed_contact_pairs_by_phase"]
    if (not isinstance(expected_pairs, dict)
            or set(expected_pairs) != {"APPROACH", "CONTACT"}
            or expected_pairs["APPROACH"] != []
            or not isinstance(expected_pairs["CONTACT"], list)
            or not expected_pairs["CONTACT"]
            or expected_pairs["CONTACT"] != sorted(expected_pairs["CONTACT"])):
        raise ValueError("Task 6 contact-transition phase pairs invalid")
    for pair in expected_pairs["CONTACT"]:
        if (not isinstance(pair, list) or len(pair) != 2
                or pair != sorted(pair)
                or any(not isinstance(name, str) or not name for name in pair)):
            raise ValueError("Task 6 contact-transition phase pair invalid")
    limits = value["diagnostic_limits"]
    if (not isinstance(limits, dict)
            or set(limits) != {"maximum_force_n", "maximum_displacement_m",
                               "maximum_ros_skew_s", "maximum_receipt_age_s"}
            or type(limits["maximum_force_n"]) is not float
            or not 0 < limits["maximum_force_n"] <= 11.6
            or limits["maximum_displacement_m"] != .03
            or limits["maximum_ros_skew_s"] != .02
            or limits["maximum_receipt_age_s"] != .2):
        raise ValueError("Task 6 contact-transition physics limits invalid")
    if value["manifest_sha256"] != hashlib.sha256(_canonical(
            {key: item for key, item in value.items()
             if key != "manifest_sha256"})).hexdigest():
        raise ValueError("Task 6 contact-transition manifest hash invalid")
    return value


def require_transition_sources(manifest: dict, *, pairs_factory=Task8ContactPairs) -> dict:
    require_transition_manifest(manifest)
    expected = build_transition_manifest(
        scene_path=Path(manifest["scene_path"]),
        route_profile_path=Path(manifest["route_profile_path"]),
        profile_path=Path(manifest["profile_path"]),
        plugin_path=Path(manifest["plugin_path"]),
        proposal_path=Path(manifest["proposal_path"]),
        receipt_path=Path(manifest["receipt_path"]),
        session_id=manifest["session_id"], attempt_id=manifest["attempt_id"],
        pairs_factory=pairs_factory)
    if _canonical(expected) != _canonical(manifest):
        raise ValueError("Task 6 contact-transition source replay mismatch")
    return manifest


def prefix_matches_transition(prefix: object, manifest: dict) -> bool:
    from so101_demo.act.contracts import validate_action_prefix
    try:
        require_transition_manifest(manifest)
        checked = validate_action_prefix(prefix)
        start = checked["sequence"] * manifest["segment_rows"]
        prior = (manifest["joint_start_rad"] if start == 0 else
                 manifest["target_positions"][start - 1])
        rows = [prior] + manifest["target_positions"][
            start:start + manifest["segment_rows"]]
        if (checked["session_id"] != manifest["session_id"]
                or checked["attempt_id"] != manifest["attempt_id"]
                or start >= len(manifest["target_positions"])
                or len(checked["positions"]) != len(rows)):
            return False
        return all(all(abs(a - b) <= 1e-10 for a, b in zip(row, expected, strict=True))
                   for row, expected in zip(checked["positions"], rows, strict=True))
    except (KeyError, TypeError, ValueError):
        return False
