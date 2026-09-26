"""Exact offline Task 6 contact-transition candidate; no command authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import mujoco

from so101_demo.act.execution import bounded_positions
from so101_demo.adapters.act.physics import model_sha256


_PROFILE_SHA = "15fdd7bd4ac7f017b361e28a9da7b55c188c60e892df66a7e050c554217ca92a"
_CANDIDATE_SHA = "0e1be85eca2716ea31101b3fdfdd73bb72e4133067c10c0c9799ec288edb98bd"
_SCENE_SHA = "4db48e35df9e91fc6868d303725badd0237fb10754d1e298637f5b0e1e55ed4f"
_MODEL_SHA = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
_ROUTE_PROFILE_SHA = "25a272abeffbfaa7e6d6710f0e844856adca6bd09d81a40261956ccbd8021abe"
_POLICY_FINGERPRINT = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"
_KEYS = frozenset({
    "schema_version", "kind", "eligible_for_collection", "mujoco_version",
    "scene_sha256", "model_sha256", "source_route_profile_sha256",
    "policy_fingerprint", "candidate_segments_sha256", "cup_start_m",
    "joint_start_rad", "near_arm_rad", "contact_arm_rad", "close_q6_rad",
    "jaw_segments",
})


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
