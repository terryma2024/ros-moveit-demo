"""Offline, source-verified visible approach candidate without motion authority."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import mujoco

from so101_demo.act.visible_approach_diagnostic import (
    build_route_manifest, require_route_sources,
)
from so101_demo.adapters.act.physics import MujocoPathChecker


_PROFILE_KEYS = frozenset({
    "schema_version", "kind", "eligible_for_collection", "source_profile_sha256",
    "scene_sha256", "model_sha256", "path_step_s", "path_clearance_m",
    "velocity_limit_rad_s", "acceleration_limit_rad_s2",
    "segment_last_indices", "row_sha256s",
})
_DETOUR_ANCHORS = (181, 191, 201, 211)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _prefix_rows(prior: list[float], goal: list[float]) -> list[list[float]]:
    rows = []
    for index in range(1, 601):
        progress = index / 600
        ease = progress * progress * (3 - 2 * progress)
        rows.append([start + (end - start) * ease
                     for start, end in zip(prior, goal, strict=True)])
    return rows


def _required_anchors(source_profile: dict, segment_count: int) -> set[int]:
    cumulative = 0
    anchors = set(_DETOUR_ANCHORS)
    for stage in source_profile["stages"]:
        start, end = stage["start"], stage["end"]
        cumulative += max(1, math.ceil(max(abs(b - a)
                                           for a, b in zip(start, end, strict=True)) / .016))
        anchors.add(cumulative - 1)
    if cumulative != segment_count or max(anchors) >= segment_count:
        raise ValueError("APPROACH_CANDIDATE_SOURCE_ANCHORS_INVALID")
    return anchors


def require_candidate_profile(profile: dict, source_route: dict) -> list[dict]:
    """Recompute every exact path from the pinned noncollecting source."""
    require_route_sources(source_route)
    if not isinstance(profile, dict) or set(profile) != _PROFILE_KEYS:
        raise ValueError("APPROACH_CANDIDATE_PROFILE_INVALID")
    if (profile["schema_version"] != 1
            or profile["kind"] != "ACT_VISIBLE_APPROACH_CANDIDATE_PROFILE"
            or profile["eligible_for_collection"] is not False
            or source_route["eligible_for_collection"] is not False
            or profile["source_profile_sha256"] != source_route["profile_sha256"]
            or profile["scene_sha256"] != source_route["scene_sha256"]
            or profile["model_sha256"] != source_route["model_sha256"]
            or profile["path_step_s"] != .002
            or profile["path_clearance_m"] != .002
            or profile["velocity_limit_rad_s"] != [.25] * 6
            or profile["acceleration_limit_rad_s2"] != [1.2] * 6):
        raise ValueError("APPROACH_CANDIDATE_ROLE_OR_LIMIT_INVALID")
    ends, hashes = profile["segment_last_indices"], profile["row_sha256s"]
    source_rows = source_route["target_positions"]
    segment_rows = source_route["segment_rows"]
    segment_count = len(source_rows) // segment_rows
    if (not isinstance(ends, list) or not ends or not isinstance(hashes, list)
            or len(ends) != len(hashes) or len(ends) > segment_count
            or any(type(index) is not int for index in ends)
            or ends[-1] != segment_count - 1
            or any(type(value) is not str or len(value) != 64 for value in hashes)):
        raise ValueError("APPROACH_CANDIDATE_SEGMENTS_INVALID")
    first = 0
    for end in ends:
        if not first <= end < min(first + 16, segment_count):
            raise ValueError("APPROACH_CANDIDATE_GROUP_INVALID")
        first = end + 1
    source_profile = json.loads(Path(source_route["profile_path"]).read_bytes())
    if not _required_anchors(source_profile, segment_count).issubset(ends):
        raise ValueError("APPROACH_CANDIDATE_ANCHOR_MISSING")

    checker = MujocoPathChecker(
        source_route["scene_path"], protected_roots=("base",),
        cup_joint="cup_free_joint", gripper_body="gripper",
        path_step_s=.002, path_clearance_m=.002,
        velocity_limit_rad_s=[.25] * 6,
        acceleration_limit_rad_s2=[1.2] * 6,
        allowed_pairs_by_phase={},
    )
    if checker.model_sha256 != source_route["model_sha256"]:
        raise ValueError("APPROACH_CANDIDATE_MODEL_INVALID")
    checked = []
    first = 0
    for sequence, (end, expected_hash) in enumerate(zip(ends, hashes, strict=True)):
        prior = (source_route["joint_start_rad"] if first == 0
                 else source_rows[first * segment_rows - 1])
        goal = source_rows[(end + 1) * segment_rows - 1]
        rows = _prefix_rows(prior, goal)
        row_hash = hashlib.sha256(json.dumps(
            rows, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if row_hash != expected_hash:
            raise ValueError("APPROACH_CANDIDATE_ROWS_INVALID")
        data = checker._data
        mujoco.mj_resetDataKeyframe(checker.model, data, 0)
        data.qpos[checker.joints] = prior
        data.qpos[checker.cup_address:checker.cup_address + 3] = source_route["cup_start_m"]
        data.qpos[checker.cup_address + 3:checker.cup_address + 7] = (1., 0., 0., 0.)
        prefix = dict(
            session_id=source_route["session_id"],
            attempt_id=source_route["attempt_id"], sequence=sequence,
            observation_time_s=10., first_target_delay_s=.1,
            target_interval_s=.002,
            target_times_s=[10.1 + .002 * index for index in range(1, 601)],
            positions=rows,
        )
        snapshot = dict(
            model_qpos=data.qpos.tolist(), model_sha256=checker.model_sha256,
            phase="APPROACH", holding_state="EMPTY", sim_time_s=10.,
            controller_bridge=dict(time_s=9.9, point=dict(
                positions=prior, velocities=[0.] * 6, accelerations=[])),
            controller_start_time_s=10.05, controller_start_positions=prior,
            controller_start_velocities=[0.] * 6,
            cup_in_gripper_transform=None,
        )
        if not checker.check_path(prefix, snapshot) or checker.last_check.get("samples") != 701:
            raise ValueError("APPROACH_CANDIDATE_PATH_UNSAFE")
        checked.append(dict(
            first_segment=first, last_segment=end, prior=prior, goal=goal,
            rows_sha256=row_hash, samples=701,
        ))
        first = end + 1
    return checked


def build_candidate_manifest(
    *, scene_path: Path, plugin_path: Path, source_profile_path: Path,
    candidate_profile_path: Path, session_id: str, attempt_id: str,
) -> dict:
    source_route = build_route_manifest(
        scene_path=scene_path, plugin_path=plugin_path,
        profile_path=source_profile_path, session_id=session_id,
        attempt_id=attempt_id,
    )
    candidate_path = Path(candidate_profile_path).resolve()
    candidate_bytes = candidate_path.read_bytes()
    profile = json.loads(candidate_bytes)
    segments = require_candidate_profile(profile, source_route)
    manifest = dict(
        schema_version=1, kind="ACT_VISIBLE_APPROACH_CANDIDATE",
        eligible_for_collection=False, source_route_sha256=source_route["manifest_sha256"],
        candidate_profile_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
        model_sha256=source_route["model_sha256"],
        scene_sha256=source_route["scene_sha256"],
        segments=segments,
    )
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    return manifest
