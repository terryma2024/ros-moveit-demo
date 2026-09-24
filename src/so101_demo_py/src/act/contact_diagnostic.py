"""Frozen physical diagnostic trajectories; never an ACT collection authority."""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

import mujoco
import yaml

from so101_demo.act.contracts import validate_action_prefix
from so101_demo.act.execution import bounded_positions
from so101_demo.adapters.act.physics import model_sha256

_SCENE_SHA = "4db48e35df9e91fc6868d303725badd0237fb10754d1e298637f5b0e1e55ed4f"
_MOTION_SHA = "aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356"
_PLUGIN_SHA = "6a030c48fe4829803bd4e2ed980adbe53217ef39b271c274286081830eaf7aac"
_MODEL_SHA = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
_ROWS = {
    "no_contact": 5, "bilateral_touch": 45, "over_compression": 50,
    "micro_lift_slip": 45, "stable_hold": 50, "table_only": 5,
    "post_release": 75, "left_only": 1, "right_only": 25,
}
_KEYS = frozenset({
    "schema_version", "kind", "eligible_for_collection", "backend", "session_id",
    "attempt_id", "regime", "seed", "mujoco_version", "scene_path", "scene_sha256",
    "motion_policy_path", "motion_policy_sha256", "plugin_path", "plugin_sha256",
    "model_sha256", "cup_start_m", "joint_start_rad", "neck_start_rad",
    "target_positions", "allowed_contact_pairs", "diagnostic_limits",
    "path_step_s", "path_clearance_m", "velocity_limit_rad_s",
    "acceleration_limit_rad_s2", "max_age_s", "max_skew_s",
    "stop_velocity_rad_s", "submit_lead_s",
    "manifest_sha256",
})
_LIMITS = {"maximum_force_n": 11.6, "maximum_displacement_m": .03,
           "maximum_ros_skew_s": .02, "maximum_receipt_age_s": .2}
_PATH_LIMITS = {
    "path_step_s": .02, "path_clearance_m": .002,
    "velocity_limit_rad_s": [.5] * 6,
    "acceleration_limit_rad_s2": [16.] * 6,
    "max_age_s": .2, "max_skew_s": .02,
    "stop_velocity_rad_s": .002, "submit_lead_s": .05,
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _row_route(policy: dict, regime: str) -> tuple[list[float], list[list[float]]]:
    preopen = float(policy["gripper_actions"]["preopen_q6"])
    close = -.049 if regime == "over_compression" else float(
        policy["gripper_actions"]["grasp_close_q6"]
    )
    start = list(policy["states"]["DESCEND"]["waypoints"][-1]) + [preopen]
    closed = start[:]; closed[5] = close
    lift = list(policy["states"]["LIFT"]["waypoints"][0]) + [close]
    opened = lift[:]; opened[5] = preopen
    stages = ((5, start, start), (20, start, closed), (20, closed, lift),
              (5, lift, lift), (20, lift, opened), (5, opened, opened))
    rows = []
    for count, first, last in stages:
        for index in range(1, count + 1):
            ratio = index / count
            rows.append(list(bounded_positions(
                [a + (b - a) * ratio for a, b in zip(first, last, strict=True)]
            )))
    return list(bounded_positions(start)), rows[:_ROWS[regime]]


def build_contact_diagnostic_manifest(
    *, scene_path: Path, motion_policy_path: Path, plugin_path: Path,
    regime: str, seed: int, session_id: str, attempt_id: str,
) -> dict:
    if regime not in _ROWS or type(seed) is not int or seed < 0:
        raise ValueError("physical diagnostic regime/seed invalid")
    if (not isinstance(session_id, str) or not session_id.strip()
            or not isinstance(attempt_id, str) or not attempt_id.strip()):
        raise ValueError("physical diagnostic identity invalid")
    scene_path = Path(scene_path).resolve()
    motion_policy_path = Path(motion_policy_path).resolve()
    plugin_path = Path(plugin_path).resolve()
    if (_digest(scene_path), _digest(motion_policy_path), _digest(plugin_path)) != (
        _SCENE_SHA, _MOTION_SHA, _PLUGIN_SHA
    ) or mujoco.mj_versionString() != "3.12.0":
        raise ValueError("physical diagnostic source/runtime drift")
    model = mujoco.MjModel.from_xml_path(str(scene_path))
    if model_sha256(model) != _MODEL_SHA or model.opt.timestep != .002:
        raise ValueError("physical diagnostic compiled model drift")
    policy = yaml.safe_load(motion_policy_path.read_bytes())
    plugin = yaml.safe_load(plugin_path.read_bytes())["/**"]["ros__parameters"]
    start, rows = _row_route(policy, regime)
    cup_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "plastic_cup")
    if cup_body < 0:
        raise ValueError("physical diagnostic cup body missing")
    cup_geoms = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, index)
                 for index in range(model.ngeom) if model.geom_bodyid[index] == cup_body]
    finger_geoms = plugin["left_fingertip_geoms"] + plugin["right_fingertip_geoms"]
    if not cup_geoms or not finger_geoms or any(
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name) < 0
        for name in (*cup_geoms, *finger_geoms)
    ):
        raise ValueError("physical diagnostic geometry whitelist invalid")
    pairs = sorted({tuple(sorted((cup, finger)))
                    for cup in cup_geoms for finger in finger_geoms})
    jitter = 0.0 if regime == "left_only" else round(
        random.Random(seed).uniform(-.000008, .000008), 12
    )
    manifest = {
        "schema_version": 1, "kind": "ACT_CONTACT_DIAGNOSTIC",
        "eligible_for_collection": False, "backend": "mujoco",
        "session_id": session_id, "attempt_id": attempt_id,
        "regime": regime, "seed": seed, "mujoco_version": "3.12.0",
        "scene_path": str(scene_path), "scene_sha256": _SCENE_SHA,
        "motion_policy_path": str(motion_policy_path), "motion_policy_sha256": _MOTION_SHA,
        "plugin_path": str(plugin_path), "plugin_sha256": _PLUGIN_SHA,
        "model_sha256": _MODEL_SHA,
        "cup_start_m": [.02 + jitter, -.28 + (.001 if regime == "left_only" else 0.), .165],
        "joint_start_rad": start, "neck_start_rad": 0.0,
        "target_positions": rows,
        "allowed_contact_pairs": [list(pair) for pair in pairs],
        "diagnostic_limits": _LIMITS.copy(),
        **{key: value.copy() if isinstance(value, list) else value
           for key, value in _PATH_LIMITS.items()},
    }
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    require_contact_diagnostic_manifest(manifest)
    return manifest


def require_contact_diagnostic_manifest(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _KEYS:
        raise ValueError("contact diagnostic manifest schema invalid")
    if (value["schema_version"] != 1 or value["kind"] != "ACT_CONTACT_DIAGNOSTIC"
            or value["eligible_for_collection"] is not False or value["backend"] != "mujoco"
            or value["mujoco_version"] != "3.12.0"
            or value["regime"] not in _ROWS or type(value["seed"]) is not int
            or value["seed"] < 0):
        raise ValueError("contact diagnostic manifest role invalid")
    for field, expected in (("scene_sha256", _SCENE_SHA),
                            ("motion_policy_sha256", _MOTION_SHA),
                            ("plugin_sha256", _PLUGIN_SHA), ("model_sha256", _MODEL_SHA)):
        if value[field] != expected:
            raise ValueError("contact diagnostic source/model hash invalid")
    if value["diagnostic_limits"] != _LIMITS:
        raise ValueError("contact diagnostic hard limits changed")
    if any(value[key] != expected for key, expected in _PATH_LIMITS.items()):
        raise ValueError("contact diagnostic path limits changed")
    if any(not isinstance(value[field], str) or not value[field].strip()
           for field in ("session_id", "attempt_id")):
        raise ValueError("contact diagnostic identity invalid")
    if any(not isinstance(value[field], str) or not Path(value[field]).is_absolute()
           for field in ("scene_path", "motion_policy_path", "plugin_path")):
        raise ValueError("contact diagnostic source path invalid")
    rows = value["target_positions"]
    if not isinstance(rows, list) or len(rows) != _ROWS[value["regime"]]:
        raise ValueError("contact diagnostic trajectory length invalid")
    for row in rows:
        bounded_positions(row)
    if not isinstance(value["joint_start_rad"], list):
        raise ValueError("contact diagnostic joint start invalid")
    bounded_positions(value["joint_start_rad"])
    if (not isinstance(value["cup_start_m"], list) or len(value["cup_start_m"]) != 3
            or any(isinstance(number, bool) or not isinstance(number, (int, float))
                   or not math.isfinite(number) for number in value["cup_start_m"])):
        raise ValueError("contact diagnostic cup start invalid")
    if not isinstance(value["allowed_contact_pairs"], list) or not value["allowed_contact_pairs"]:
        raise ValueError("contact diagnostic contact whitelist missing")
    for pair in value["allowed_contact_pairs"]:
        if (not isinstance(pair, list) or len(pair) != 2
                or any(not isinstance(name, str) or not name for name in pair)
                or pair != sorted(pair)):
            raise ValueError("contact diagnostic contact whitelist invalid")
    if value["allowed_contact_pairs"] != sorted(value["allowed_contact_pairs"]):
        raise ValueError("contact diagnostic contact whitelist order invalid")
    digest = value["manifest_sha256"]
    if digest != hashlib.sha256(_canonical({key: item for key, item in value.items()
                                            if key != "manifest_sha256"})).hexdigest():
        raise ValueError("contact diagnostic manifest hash mismatch")
    return value


def prefix_matches_diagnostic(prefix: object, manifest: dict) -> bool:
    try:
        require_contact_diagnostic_manifest(manifest)
        checked = validate_action_prefix(prefix)
        if (checked["session_id"] != manifest["session_id"]
                or checked["attempt_id"] != manifest["attempt_id"]
                or checked["sequence"] != 0
                or len(checked["positions"]) != len(manifest["target_positions"])):
            return False
        return all(all(abs(a - b) <= 1e-10 for a, b in zip(row, expected, strict=True))
                   for row, expected in zip(checked["positions"],
                                            manifest["target_positions"], strict=True))
    except (KeyError, TypeError, ValueError):
        return False


def require_contact_diagnostic_sources(manifest: dict) -> dict:
    """Rebuild the complete motion/whitelist from pinned current source bytes."""

    require_contact_diagnostic_manifest(manifest)
    expected = build_contact_diagnostic_manifest(
        scene_path=Path(manifest["scene_path"]),
        motion_policy_path=Path(manifest["motion_policy_path"]),
        plugin_path=Path(manifest["plugin_path"]),
        regime=manifest["regime"], seed=manifest["seed"],
        session_id=manifest["session_id"], attempt_id=manifest["attempt_id"],
    )
    if _canonical(expected) != _canonical(manifest):
        raise ValueError("contact diagnostic source replay mismatch")
    return manifest
