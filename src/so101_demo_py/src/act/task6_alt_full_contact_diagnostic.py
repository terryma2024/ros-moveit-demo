"""Closed left/forward Task 6 approach-to-contact diagnostic profiles."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import mujoco

from so101_demo.act.contracts import validate_action_prefix
from so101_demo.act.execution import bounded_positions
from so101_demo.act.task6_contact_transition import _PATH_LIMITS
from so101_demo.adapters.act.physics import model_sha256
from so101_demo.adapters.act.task8_contact_pairs import Task8ContactPairs


_SCENE_SHA = "4db48e35df9e91fc6868d303725badd0237fb10754d1e298637f5b0e1e55ed4f"
_MODEL_SHA = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
_PLUGIN_SHA = "612212d5a61c74c4086c0cf2b229cfb5552e58055f8744ee0e9e4d46db655fae"
_ANCHORS_SHA = "91bbecbfd0914507ff7e55cd554960ce089375b5944809732512e645de42d10b"
_PROFILE_SHA = "d9e45eb71fcd969527ba87ed649bf8261094b903eb14a3680cb3a39eb0621886"
_POLICY_FINGERPRINT = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"
_CANDIDATE_SHA = {
    "left": "4635154f83833542053d24d899f90b890a39fc49a019f81fde9a0fd351781901",
    "forward": "5c8128668043cb5b80d47d0fb869d1a2d9c61206b572120c2b50ef4a51d0dae1",
}
_ROUTE_COUNT = {"left": 134, "forward": 197}
_TOTAL_COUNT = {"left": 168, "forward": 235}
_PROFILE_KEYS = frozenset({
    "schema_version", "kind", "eligible_for_collection", "mujoco_version",
    "scene_sha256", "model_sha256", "plugin_sha256", "anchors_sha256",
    "policy_fingerprint", "joint_start_rad", "open_q6_rad", "close_q6_rad",
    "jaw_segments", "anchors",
})
_ANCHOR_KEYS = frozenset({
    "cup_start_m", "waypoints_first5", "near_q_first5", "contact_q_first5",
    "visual_detour", "candidate_segments_sha256", "source_evidence_sha256",
})
_MANIFEST_KEYS = frozenset({
    "schema_version", "kind", "eligible_for_collection", "backend", "anchor",
    "session_id", "attempt_id", "mujoco_version", "scene_path", "scene_sha256",
    "plugin_path", "plugin_sha256", "anchors_path", "anchors_sha256",
    "profile_path", "profile_sha256", "proposal_path", "proposal_sha256",
    "receipt_path", "receipt_sha256", "policy_fingerprint", "model_sha256",
    "cup_start_m", "joint_start_rad", "neck_start_rad", "target_positions",
    "segment_phases", "segment_rows", "route_segment_count", "contact_phase_start",
    "first_target_delay_s",
    "candidate_segments_sha256", "allowed_contact_pairs_by_phase", "diagnostic_limits",
    *tuple(_PATH_LIMITS), "manifest_sha256",
})


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _between(a: list[float], b: list[float]) -> list[list[float]]:
    rows = [list(a)]
    for part in range(1, 8):
        fraction = part / 7
        ease = fraction * fraction * (3 - 2 * fraction)
        rows.append([float(x + (y - x) * ease)
                     for x, y in zip(a, b, strict=True)])
    rows.append(list(b))
    return rows


def _chunks(a: list[float], b: list[float]) -> list[list[list[float]]]:
    count = max(1, math.ceil(max(abs(x - y) for x, y in zip(a, b, strict=True)) / .016))
    if count > 200:
        raise ValueError("Task 6 alternate route stage too long")
    return [_between([x + (y - x) * index / count for x, y in zip(a, b, strict=True)],
                     [x + (y - x) * (index + 1) / count
                      for x, y in zip(a, b, strict=True)])
            for index in range(count)]


def _canonicalize(segments: list[tuple[str, list[list[float]]]]) -> None:
    for index in range(1, len(segments)):
        before = segments[index - 1][1][-1]
        after = segments[index][1][0]
        if max(abs(a - b) for a, b in zip(before, after, strict=True)) > 1e-12:
            raise ValueError("Task 6 alternate segment discontinuity")
        segments[index][1][0] = before.copy()


def build_alt_segments(
    *, scene_path: Path, plugin_path: Path, anchors_path: Path,
    profile_path: Path, anchor: str,
) -> list[tuple[str, list[list[float]]]]:
    """Rebuild a measured route and refuse a changed source or target row."""
    paths = tuple(Path(path).resolve() for path in
                  (scene_path, plugin_path, anchors_path, profile_path))
    if (anchor not in _CANDIDATE_SHA
            or any(not path.is_file() for path in paths)
            or tuple(_digest(path) for path in paths)
            != (_SCENE_SHA, _PLUGIN_SHA, _ANCHORS_SHA, _PROFILE_SHA)
            or mujoco.mj_versionString() != "3.12.0"):
        raise ValueError("Task 6 alternate source/runtime drift")
    model = mujoco.MjModel.from_xml_path(str(paths[0]))
    if model_sha256(model) != _MODEL_SHA or model.opt.timestep != .002:
        raise ValueError("Task 6 alternate compiled model drift")
    profile = json.loads(paths[3].read_bytes())
    if (not isinstance(profile, dict) or set(profile) != _PROFILE_KEYS
            or profile["schema_version"] != 1
            or profile["kind"] != "TASK6_ALT_FULL_CONTACT_DIAGNOSTIC_PROFILE"
            or profile["eligible_for_collection"] is not False
            or profile["mujoco_version"] != "3.12.0"
            or any(profile[key] != expected for key, expected in (
                ("scene_sha256", _SCENE_SHA), ("model_sha256", _MODEL_SHA),
                ("plugin_sha256", _PLUGIN_SHA), ("anchors_sha256", _ANCHORS_SHA),
                ("policy_fingerprint", _POLICY_FINGERPRINT)))
            or type(profile["jaw_segments"]) is not int
            or profile["jaw_segments"] != 32
            or not isinstance(profile["anchors"], dict)
            or set(profile["anchors"]) != set(_CANDIDATE_SHA)):
        raise ValueError("Task 6 alternate profile invalid")
    import yaml
    anchors = yaml.safe_load(paths[2].read_bytes())
    if (not isinstance(anchors, dict) or anchors.get("schema_version") != 1
            or set(anchors.get("anchors", {})) != {"default", "left", "forward"}):
        raise ValueError("Task 6 alternate anchor source invalid")
    entry = profile["anchors"][anchor]
    if (not isinstance(entry, dict) or set(entry) != _ANCHOR_KEYS
            or entry["cup_start_m"] != anchors["anchors"][anchor]["cup_start_m"]
            or entry["candidate_segments_sha256"] != _CANDIDATE_SHA[anchor]
            or not isinstance(entry["source_evidence_sha256"], str)
            or len(entry["source_evidence_sha256"]) != 64
            or (entry["visual_detour"] is None) != (anchor == "left")):
        raise ValueError("Task 6 alternate anchor profile invalid")
    start = list(bounded_positions(profile["joint_start_rad"]))
    opened = start.copy()
    opened[5] = float(profile["open_q6_rad"])
    bounded_positions(opened)
    near = list(bounded_positions([*entry["near_q_first5"], opened[5]]))
    contact = list(bounded_positions([*entry["contact_q_first5"], opened[5]]))
    final = list(bounded_positions([*entry["contact_q_first5"],
                                    profile["close_q6_rad"]]))
    waypoints = entry["waypoints_first5"]
    if (not isinstance(waypoints, list)
            or len(waypoints) != (4 if anchor == "left" else 3)
            or list(waypoints[0]) != start[:5]
            or max(abs(a - b) for a, b in zip(waypoints[-1], near[:5], strict=True)) > 1e-12):
        raise ValueError("Task 6 alternate waypoint invalid")
    route = [("APPROACH", rows) for rows in _chunks(start, opened)]
    for first, last in zip(waypoints[:-1], waypoints[1:], strict=True):
        a = list(bounded_positions([*first, opened[5]]))
        b = list(bounded_positions([*last, opened[5]]))
        route.extend(("APPROACH", rows) for rows in _chunks(a, b))
    if len(route) != _ROUTE_COUNT[anchor]:
        raise ValueError("Task 6 alternate route length drift")
    local = [("APPROACH", _between(near, near))]
    local.extend(("CONTACT", rows) for rows in _chunks(near, contact))
    for index in range(32):
        a = contact.copy()
        b = contact.copy()
        a[5] = opened[5] + (final[5] - opened[5]) * index / 32
        b[5] = opened[5] + (final[5] - opened[5]) * (index + 1) / 32
        local.append(("CONTACT", _between(a, b)))
    if max(abs(a - b) for a, b in zip(route[-1][1][-1], local[0][1][0], strict=True)) > 1e-12:
        raise ValueError("Task 6 alternate route/contact gap")
    route[-1][1][-1] = local[0][1][0].copy()
    segments = route + local
    _canonicalize(segments)
    if anchor == "forward":
        detour = entry["visual_detour"]
        if detour != {"joint_index": 0, "begin_segment": 175,
                      "full_segment": 185, "last_full_segment": 197,
                      "end_segment": 201, "peak_offset_rad": -.1}:
            raise ValueError("Task 6 alternate visual detour invalid")

        def offset(endpoint: int) -> float:
            if endpoint <= 174:
                return 0.
            if endpoint <= 185:
                return -.1 * (endpoint - 174) / 11.
            if endpoint <= 197:
                return -.1
            if endpoint <= 201:
                return -.1 * (201 - endpoint) / 4.
            return 0.

        for sequence, (_, rows) in enumerate(segments):
            before, after = offset(sequence - 1), offset(sequence)
            for part, row in enumerate(rows):
                fraction = min(part / 7, 1.)
                ease = fraction * fraction * (3 - 2 * fraction)
                row[0] += before + (after - before) * ease
        _canonicalize(segments)
    if (len(segments) != _TOTAL_COUNT[anchor]
            or any(len(rows) != 9 for _, rows in segments)
            or any(phase != ("APPROACH" if index < _ROUTE_COUNT[anchor] + 1 else "CONTACT")
                   for index, (phase, _) in enumerate(segments))):
        raise ValueError("Task 6 alternate phase or row count invalid")
    for _, rows in segments:
        for row in rows:
            bounded_positions(row)
    raw = json.dumps(segments, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != _CANDIDATE_SHA[anchor]:
        raise ValueError(f"Task 6 alternate candidate drift: {actual_sha}")
    return segments


def build_alt_manifest(
    *, scene_path: Path, plugin_path: Path, anchors_path: Path,
    profile_path: Path, proposal_path: Path, receipt_path: Path,
    anchor: str, session_id: str, attempt_id: str,
    pairs_factory=Task8ContactPairs,
) -> dict:
    scene, plugin, anchors, profile, proposal, receipt = (
        Path(path).resolve() for path in (scene_path, plugin_path, anchors_path,
                                          profile_path, proposal_path, receipt_path))
    segments = build_alt_segments(scene_path=scene, plugin_path=plugin,
                                  anchors_path=anchors, profile_path=profile,
                                  anchor=anchor)
    if (not isinstance(session_id, str) or not session_id.strip()
            or not isinstance(attempt_id, str) or not attempt_id.strip()
            or not proposal.is_file() or not receipt.is_file()):
        raise ValueError("Task 6 alternate identity or activation source invalid")
    model = mujoco.MjModel.from_xml_path(str(scene))
    pairs = pairs_factory(model=model, scene_path=scene,
                          proposal_path=proposal, receipt_path=receipt,
                          expected_fingerprint=_POLICY_FINGERPRINT)
    if (pairs.model_sha256 != _MODEL_SHA
            or pairs.fingerprint != _POLICY_FINGERPRINT):
        raise ValueError("Task 6 alternate activation invalid")
    proposal_value = json.loads(proposal.read_bytes())
    threshold = proposal_value["payload"]["thresholds"]["maximum_safe_force_n"]
    if type(threshold) not in (float, int) or not 0 < threshold <= 11.6:
        raise ValueError("Task 6 alternate force limit invalid")
    allowed = [list(pair) for pair in sorted(pairs.for_phase("CLOSE"))]
    if not allowed:
        raise ValueError("Task 6 alternate contact pairs missing")
    profile_value = json.loads(profile.read_bytes())
    value = dict(
        schema_version=1, kind="ACT_TASK6_ALT_FULL_CONTACT_DIAGNOSTIC",
        eligible_for_collection=False, backend="mujoco", anchor=anchor,
        session_id=session_id, attempt_id=attempt_id, mujoco_version="3.12.0",
        scene_path=str(scene), scene_sha256=_SCENE_SHA,
        plugin_path=str(plugin), plugin_sha256=_PLUGIN_SHA,
        anchors_path=str(anchors), anchors_sha256=_ANCHORS_SHA,
        profile_path=str(profile), profile_sha256=_PROFILE_SHA,
        proposal_path=str(proposal), proposal_sha256=_digest(proposal),
        receipt_path=str(receipt), receipt_sha256=_digest(receipt),
        policy_fingerprint=_POLICY_FINGERPRINT, model_sha256=_MODEL_SHA,
        cup_start_m=profile_value["anchors"][anchor]["cup_start_m"],
        joint_start_rad=profile_value["joint_start_rad"], neck_start_rad=0.,
        target_positions=[row for _, rows in segments for row in rows],
        segment_phases=[phase for phase, _ in segments], segment_rows=9,
        route_segment_count=_ROUTE_COUNT[anchor],
        contact_phase_start=_ROUTE_COUNT[anchor] + 1,
        first_target_delay_s=.1,
        candidate_segments_sha256=_CANDIDATE_SHA[anchor],
        allowed_contact_pairs_by_phase={"APPROACH": [], "CONTACT": allowed},
        diagnostic_limits=dict(maximum_force_n=float(threshold),
                               maximum_displacement_m=.03,
                               maximum_ros_skew_s=.02,
                               maximum_receipt_age_s=.2),
        **{key: item.copy() if isinstance(item, list) else item
           for key, item in _PATH_LIMITS.items()},
    )
    value["manifest_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    require_alt_manifest(value)
    return value


def require_alt_manifest(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _MANIFEST_KEYS:
        raise ValueError("Task 6 alternate manifest schema invalid")
    anchor = value["anchor"]
    if (anchor not in _CANDIDATE_SHA
            or value["schema_version"] != 1
            or value["kind"] != "ACT_TASK6_ALT_FULL_CONTACT_DIAGNOSTIC"
            or value["eligible_for_collection"] is not False
            or value["backend"] != "mujoco"
            or value["mujoco_version"] != "3.12.0"
            or value["scene_sha256"] != _SCENE_SHA
            or value["plugin_sha256"] != _PLUGIN_SHA
            or value["anchors_sha256"] != _ANCHORS_SHA
            or value["profile_sha256"] != _PROFILE_SHA
            or value["model_sha256"] != _MODEL_SHA
            or value["policy_fingerprint"] != _POLICY_FINGERPRINT
            or value["candidate_segments_sha256"] != _CANDIDATE_SHA[anchor]
            or value["route_segment_count"] != _ROUTE_COUNT[anchor]
            or value["contact_phase_start"] != _ROUTE_COUNT[anchor] + 1
            or value["neck_start_rad"] != 0.
            or value["segment_rows"] != 9
            or value["first_target_delay_s"] != .1
            or value["segment_phases"] != ["APPROACH"] * (_ROUTE_COUNT[anchor] + 1)
               + ["CONTACT"] * (_TOTAL_COUNT[anchor] - _ROUTE_COUNT[anchor] - 1)
            or any(value[key] != expected for key, expected in _PATH_LIMITS.items())):
        raise ValueError("Task 6 alternate manifest role/phase invalid")
    if any(not isinstance(value[key], str) or not value[key].strip()
           for key in ("session_id", "attempt_id")):
        raise ValueError("Task 6 alternate identity invalid")
    for key in ("scene", "plugin", "anchors", "profile", "proposal", "receipt"):
        path = value[key + "_path"]
        digest = value[key + "_sha256"]
        if (not isinstance(path, str) or not Path(path).is_absolute()
                or not isinstance(digest, str) or len(digest) != 64):
            raise ValueError("Task 6 alternate source path/hash invalid")
    if (not isinstance(value["target_positions"], list)
            or len(value["target_positions"]) != _TOTAL_COUNT[anchor] * 9):
        raise ValueError("Task 6 alternate target rows invalid")
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
        raise ValueError("Task 6 alternate phase pairs invalid")
    for pair in expected_pairs["CONTACT"]:
        if (not isinstance(pair, list) or len(pair) != 2 or pair != sorted(pair)
                or any(not isinstance(name, str) or not name for name in pair)):
            raise ValueError("Task 6 alternate contact pair invalid")
    limits = value["diagnostic_limits"]
    if (not isinstance(limits, dict)
            or set(limits) != {"maximum_force_n", "maximum_displacement_m",
                               "maximum_ros_skew_s", "maximum_receipt_age_s"}
            or type(limits["maximum_force_n"]) is not float
            or not 0 < limits["maximum_force_n"] <= 11.6
            or limits["maximum_displacement_m"] != .03
            or limits["maximum_ros_skew_s"] != .02
            or limits["maximum_receipt_age_s"] != .2):
        raise ValueError("Task 6 alternate physics limits invalid")
    if value["manifest_sha256"] != hashlib.sha256(_canonical(
            {key: item for key, item in value.items()
             if key != "manifest_sha256"})).hexdigest():
        raise ValueError("Task 6 alternate manifest hash invalid")
    return value


def require_alt_sources(manifest: dict, *, pairs_factory=Task8ContactPairs) -> dict:
    require_alt_manifest(manifest)
    expected = build_alt_manifest(
        scene_path=Path(manifest["scene_path"]),
        plugin_path=Path(manifest["plugin_path"]),
        anchors_path=Path(manifest["anchors_path"]),
        profile_path=Path(manifest["profile_path"]),
        proposal_path=Path(manifest["proposal_path"]),
        receipt_path=Path(manifest["receipt_path"]),
        anchor=manifest["anchor"], session_id=manifest["session_id"],
        attempt_id=manifest["attempt_id"], pairs_factory=pairs_factory)
    if _canonical(expected) != _canonical(manifest):
        raise ValueError("Task 6 alternate source replay mismatch")
    return manifest


def alt_prefix_matches(prefix: object, manifest: dict) -> bool:
    try:
        require_alt_manifest(manifest)
        checked = validate_action_prefix(prefix)
        start = checked["sequence"] * 9
        prior = (manifest["joint_start_rad"] if start == 0 else
                 manifest["target_positions"][start - 1])
        expected = [prior] + manifest["target_positions"][start:start + 9]
        if (checked["session_id"] != manifest["session_id"]
                or checked["attempt_id"] != manifest["attempt_id"]
                or checked.get("first_target_delay_s") != manifest["first_target_delay_s"]
                or start >= len(manifest["target_positions"])
                or len(checked["positions"]) != len(expected)):
            return False
        return all(all(abs(a - b) <= 1e-10
                       for a, b in zip(row, frozen, strict=True))
                   for row, frozen in zip(checked["positions"], expected, strict=True))
    except (KeyError, TypeError, ValueError):
        return False
