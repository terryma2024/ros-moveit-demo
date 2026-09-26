"""Frozen visible APPROACH diagnostic, with no collection or contact authority."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import mujoco

from so101_demo.act.contracts import validate_action_prefix
from so101_demo.act.execution import bounded_positions
from so101_demo.adapters.act.physics import model_sha256


_SCENE_SHA = "4db48e35df9e91fc6868d303725badd0237fb10754d1e298637f5b0e1e55ed4f"
_PLUGIN_SHA = "6a030c48fe4829803bd4e2ed980adbe53217ef39b271c274286081830eaf7aac"
_PROFILE_SHA = "73fa462230b0556b7d552977219e060f9f6c4e2f16944021230af947640462bb"
_MODEL_SHA = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
_PROFILE_KEYS = frozenset({
    "schema_version", "kind", "eligible_for_collection", "model_sha256",
    "scene_sha256", "source_route_sha256", "cup_start_m", "joint_start_rad",
    "stages",
})
_KEYS = frozenset({
    "schema_version", "kind", "eligible_for_collection", "backend", "session_id",
    "attempt_id", "mujoco_version", "scene_path", "scene_sha256",
    "plugin_path", "plugin_sha256", "profile_path", "profile_sha256",
    "model_sha256", "cup_start_m", "joint_start_rad", "neck_start_rad",
    "target_positions", "handoff_positions", "segment_rows",
    "allowed_contact_pairs", "diagnostic_limits", "path_step_s",
    "path_clearance_m", "velocity_limit_rad_s", "acceleration_limit_rad_s2",
    "max_age_s", "max_skew_s", "stop_velocity_rad_s", "submit_lead_s",
    "stop_max_age_s",
    "manifest_sha256",
})
_PATH_LIMITS = {
    "path_step_s": .02, "path_clearance_m": .002,
    "velocity_limit_rad_s": [.25] * 6,
    "acceleration_limit_rad_s2": [.75] * 6,
    "max_age_s": .2, "max_skew_s": .05,
    "stop_velocity_rad_s": .002, "submit_lead_s": .05,
}
_PHYSICS_LIMITS = {"maximum_force_n": 11.6,
                   "maximum_displacement_m": .03,
                   "maximum_ros_skew_s": .02,
                   "maximum_receipt_age_s": .2}
_CHUNK_DELTA_RAD = .016
_SEGMENT_ROWS = 9
_STOP_MAX_AGE_S = 1.5


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(profile: dict) -> list[list[float]]:
    if (not isinstance(profile, dict) or set(profile) != _PROFILE_KEYS
            or profile["schema_version"] != 1
            or profile["kind"] != "TASK6_VISIBLE_APPROACH_DIAGNOSTIC_PROFILE"
            or profile["eligible_for_collection"] is not False
            or profile["model_sha256"] != _MODEL_SHA
            or profile["scene_sha256"] != _SCENE_SHA
            or not isinstance(profile["source_route_sha256"], str)
            or len(profile["source_route_sha256"]) != 64
            or profile["cup_start_m"] != [.02, -.28, .165]
            or not isinstance(profile["stages"], list)
            or len(profile["stages"]) != 15):
        raise ValueError("Task 6 route profile invalid")
    previous = list(bounded_positions(profile["joint_start_rad"]))
    result: list[list[float]] = []
    for stage in profile["stages"]:
        if (not isinstance(stage, dict) or set(stage) != {"stage", "start", "end"}
                or not isinstance(stage["stage"], str) or not stage["stage"]):
            raise ValueError("Task 6 route stage invalid")
        first = list(bounded_positions(stage["start"]))
        last = list(bounded_positions(stage["end"]))
        if any(abs(a - b) > 1e-12 for a, b in zip(previous, first, strict=True)):
            raise ValueError("Task 6 route stage discontinuity")
        chunks = max(1, math.ceil(max(abs(b - a) for a, b in zip(first, last, strict=True))
                                  / _CHUNK_DELTA_RAD))
        if chunks > 200:
            raise ValueError("Task 6 route stage too long")
        for index in range(chunks):
            start = result[-1].copy() if result else first.copy()
            end = [a + (b - a) * (index + 1) / chunks
                   for a, b in zip(first, last, strict=True)]
            if any(abs(a - b) > _CHUNK_DELTA_RAD + 1e-12
                   for a, b in zip(start, end, strict=True)):
                raise ValueError("Task 6 route chunk invalid")
            rows = [start]
            for part in range(1, 8):
                fraction = part / 7
                ease = fraction * fraction * (3 - 2 * fraction)
                rows.append([a + (b - a) * ease
                             for a, b in zip(start, end, strict=True)])
            rows.append(end)
            if len(rows) != _SEGMENT_ROWS:
                raise ValueError("Task 6 route row count invalid")
            result.extend([list(bounded_positions(row)) for row in rows])
        previous = last
    if not result or len(result) > 5000:
        raise ValueError("Task 6 route length invalid")
    return result


def build_route_manifest(
    *, scene_path: Path, plugin_path: Path, profile_path: Path,
    session_id: str, attempt_id: str,
) -> dict:
    paths = tuple(Path(path).resolve() for path in
                  (scene_path, plugin_path, profile_path))
    if (any(not path.is_file() for path in paths)
            or tuple(_digest(path) for path in paths)
            != (_SCENE_SHA, _PLUGIN_SHA, _PROFILE_SHA)
            or mujoco.mj_versionString() != "3.12.0"):
        raise ValueError("Task 6 route source/runtime drift")
    model = mujoco.MjModel.from_xml_path(str(paths[0]))
    if model_sha256(model) != _MODEL_SHA or model.opt.timestep != .002:
        raise ValueError("Task 6 route compiled model drift")
    profile = json.loads(paths[2].read_bytes())
    rows = _rows(profile)
    if (not isinstance(session_id, str) or not session_id.strip()
            or not isinstance(attempt_id, str) or not attempt_id.strip()):
        raise ValueError("Task 6 route identity invalid")
    manifest = dict(
        schema_version=1, kind="ACT_TASK6_ROUTE_DIAGNOSTIC",
        eligible_for_collection=False, backend="mujoco",
        session_id=session_id, attempt_id=attempt_id,
        mujoco_version="3.12.0", scene_path=str(paths[0]),
        scene_sha256=_SCENE_SHA, plugin_path=str(paths[1]),
        plugin_sha256=_PLUGIN_SHA, profile_path=str(paths[2]),
        profile_sha256=_PROFILE_SHA, model_sha256=_MODEL_SHA,
        cup_start_m=[.02, -.28, .165],
        joint_start_rad=list(bounded_positions(profile["joint_start_rad"])),
        neck_start_rad=0., target_positions=rows,
        handoff_positions=rows[-1].copy(), segment_rows=_SEGMENT_ROWS,
        allowed_contact_pairs=[], diagnostic_limits=_PHYSICS_LIMITS.copy(),
        stop_max_age_s=_STOP_MAX_AGE_S,
        **{key: value.copy() if isinstance(value, list) else value
           for key, value in _PATH_LIMITS.items()},
    )
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    require_route_manifest(manifest)
    return manifest


def require_route_manifest(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _KEYS:
        raise ValueError("Task 6 route manifest schema invalid")
    if (value["schema_version"] != 1 or value["kind"] != "ACT_TASK6_ROUTE_DIAGNOSTIC"
            or value["eligible_for_collection"] is not False
            or value["backend"] != "mujoco" or value["mujoco_version"] != "3.12.0"
            or value["model_sha256"] != _MODEL_SHA
            or value["scene_sha256"] != _SCENE_SHA
            or value["plugin_sha256"] != _PLUGIN_SHA
            or value["profile_sha256"] != _PROFILE_SHA
            or value["cup_start_m"] != [.02, -.28, .165]
            or value["neck_start_rad"] != 0.
            or value["segment_rows"] != _SEGMENT_ROWS
            or value["stop_max_age_s"] != _STOP_MAX_AGE_S
            or value["allowed_contact_pairs"] != []
            or value["diagnostic_limits"] != _PHYSICS_LIMITS
            or any(value[key] != expected for key, expected in _PATH_LIMITS.items())):
        raise ValueError("Task 6 route role/limit invalid")
    if any(not isinstance(value[key], str) or not value[key].strip()
           for key in ("session_id", "attempt_id")):
        raise ValueError("Task 6 route identity invalid")
    if any(not isinstance(value[key], str) or not Path(value[key]).is_absolute()
           for key in ("scene_path", "plugin_path", "profile_path")):
        raise ValueError("Task 6 route path invalid")
    bounded_positions(value["joint_start_rad"])
    bounded_positions(value["handoff_positions"])
    rows = value["target_positions"]
    if (not isinstance(rows, list) or not rows or len(rows) > 5000
            or len(rows) % _SEGMENT_ROWS or rows[-1] != value["handoff_positions"]):
        raise ValueError("Task 6 route trajectory invalid")
    for row in rows:
        bounded_positions(row)
    if value["manifest_sha256"] != hashlib.sha256(_canonical(
            {key: item for key, item in value.items()
             if key != "manifest_sha256"})).hexdigest():
        raise ValueError("Task 6 route manifest hash invalid")
    return value


def require_route_sources(manifest: dict) -> dict:
    require_route_manifest(manifest)
    expected = build_route_manifest(
        scene_path=Path(manifest["scene_path"]),
        plugin_path=Path(manifest["plugin_path"]),
        profile_path=Path(manifest["profile_path"]),
        session_id=manifest["session_id"], attempt_id=manifest["attempt_id"],
    )
    if _canonical(expected) != _canonical(manifest):
        raise ValueError("Task 6 route source replay mismatch")
    return manifest


def route_prefix_matches(prefix: object, manifest: dict) -> bool:
    try:
        require_route_manifest(manifest)
        checked = validate_action_prefix(prefix)
        start = checked["sequence"] * _SEGMENT_ROWS
        prior = (manifest["joint_start_rad"] if start == 0 else
                 manifest["target_positions"][start - 1])
        expected = [prior] + manifest["target_positions"][start:start + _SEGMENT_ROWS]
        if (checked["session_id"] != manifest["session_id"]
                or checked["attempt_id"] != manifest["attempt_id"]
                or start >= len(manifest["target_positions"])
                or len(checked["positions"]) != len(expected)):
            return False
        return all(all(abs(a - b) <= 1e-10 for a, b in zip(row, frozen, strict=True))
                   for row, frozen in zip(checked["positions"], expected, strict=True))
    except (KeyError, TypeError, ValueError):
        return False
