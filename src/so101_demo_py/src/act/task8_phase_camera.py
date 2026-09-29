"""Task 3: phase-camera replay coverage, live continuity and deterministic projection.

Three time axes stay separate: 2 ms replay rows, 10 Hz calibration-live rows and 10 Hz Task 8 live rows. A replay
result may satisfy geometric feasibility, but it can never be reported as live continuity - the two axes are
checked by different functions and the live check refuses replay-shaped input outright. Nothing here imports ROS.
"""

from __future__ import annotations

import statistics

#: the approved phase list, taken from the design's phase-camera coverage table (section 6) and the approved
#: plan's live-evidence step, which agree exactly: a matrix that does not cover all nine is invalid
APPROVED_PHASES = ("SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT", "TRANSPORT", "ALIGN", "RELEASE",
                   "RADIAL_RETREAT", "FINAL_CHECK")
REPLAY_GRID_S = 0.002
REPLAY_SPACING_MAX_S = 0.005
LIVE_MIN_VISIBLE_FRACTION = 0.80
LIVE_MAX_OUT_OF_FRAME_FRACTION = 0.02
WINDOW_KINDS = ("calibration_live", "task8_live")

#: group-0 visual geoms the approved matrix permits to occlude the cup; anything else is refused
ALLOWED_OCCLUDER_OWNERS = (
    "fixed_fingertip_pad_visual", "gripper_visual_00", "gripper_visual_01",
    "jaw_visual_00", "moving_fingertip_pad_visual",
)


def occluder_owner_allowed(owner: str, *, group: int) -> bool:
    """Only the five approved group-0 visual geoms may own an occluder."""

    return group == 0 and owner in ALLOWED_OCCLUDER_OWNERS


def _phase_entries(matrix: dict) -> dict:
    entries = matrix.get("phases")
    if not isinstance(entries, list) or not entries:
        raise ValueError("PHASE_CAMERA_MATRIX_INVALID: no phases")
    resolved = {entry["phase"]: entry for entry in entries}
    missing = [phase for phase in APPROVED_PHASES if phase not in resolved]
    if missing:
        raise ValueError(f"PHASE_CAMERA_MATRIX_INVALID: missing {missing[0]}")
    return resolved


def evaluate_replay_coverage(rows, matrix: dict) -> dict:
    """Every phase in the matrix must be covered by replay rows for both cameras."""

    try:
        entries = _phase_entries(matrix)
    except ValueError as error:
        return {"verdict": "FAIL", "reason": str(error)}
    cameras = tuple(matrix.get("cameras", ()))
    observed = {(row.get("phase"), row.get("camera")) for row in rows}
    for phase, entry in entries.items():
        for camera in entry.get("cameras", cameras):
            if (phase, camera) not in observed:
                return {"verdict": "FAIL", "reason": f"PHASE_CAMERA_MISSING: {phase}/{camera}"}
    return {"verdict": "PASS", "reason": None}


def _looks_like_replay(frames) -> bool:
    spacings = [later["monotonic_s"] - earlier["monotonic_s"]
                for earlier, later in zip(frames, frames[1:])]
    dense = bool(spacings) and statistics.median(spacings) <= REPLAY_SPACING_MAX_S
    lacks_live_identity = any(name not in frames[0] for name in ("session_id", "attempt_id", "group_owner"))
    return dense or lacks_live_identity


def evaluate_live_continuity(frames, window_kind: str, matrix: dict) -> dict:
    """Live continuity over 10 Hz rows only; replay input is refused rather than re-interpreted."""

    if window_kind not in WINDOW_KINDS:
        raise ValueError(f"WINDOW_KIND_INVALID: {window_kind}")
    frames = list(frames)
    if not frames:
        raise ValueError("LIVE_FRAMES_REQUIRED")
    if _looks_like_replay(frames):
        return {"verdict": "INVALID", "reason": "REPLAY_ROWS: replay rows cannot establish live continuity"}
    try:
        entries = _phase_entries(matrix)
    except ValueError as error:
        return {"verdict": "FAIL", "reason": str(error)}
    first = frames[0]
    for frame in frames:
        for name in ("session_id", "reset_epoch", "attempt_id"):
            if frame.get(name) != first.get(name):
                return {"verdict": "FAIL", "reason": f"CROSSED_{name.upper()}"}
        entry = entries.get(frame.get("phase"))
        if entry is None:
            return {"verdict": "FAIL", "reason": f"PHASE_UNKNOWN: {frame.get('phase')}"}
        if frame.get("camera") not in entry.get("cameras", matrix.get("cameras", ())):
            return {"verdict": "FAIL", "reason": f"CAMERA_UNKNOWN: {frame.get('camera')}"}
        if frame.get("group_owner") not in ("arm", "gripper"):
            return {"verdict": "FAIL", "reason": f"GROUP_OWNER_INVALID: {frame.get('group_owner')}"}
        if frame.get("visible_fraction", 0.0) < entry["visible_fraction_min"]:
            return {"verdict": "FAIL", "reason": f"VISIBLE_FRACTION_LOW: {frame.get('visible_fraction')}"}
        if frame.get("out_of_frame_fraction", 1.0) > entry["out_of_frame_fraction_max"]:
            return {"verdict": "FAIL", "reason": "OUT_OF_FRAME_FRACTION_HIGH"}
        left, right, top, bottom = entry["bbox_center_bounds_px"]
        centre = frame.get("bbox_center_px", [0.0, 0.0])
        if not (left <= centre[0] <= right and top <= centre[1] <= bottom):
            return {"verdict": "FAIL", "reason": f"BBOX_CENTER_OUTSIDE: {centre}"}
    for earlier, later in zip(frames, frames[1:]):
        if later["monotonic_s"] - earlier["monotonic_s"] > entries[earlier["phase"]]["max_source_gap_s"]:
            return {"verdict": "FAIL", "reason": "SOURCE_GAP_EXCEEDED"}
    return {"verdict": "PASS", "reason": None}


def rasterize_cup_projection(*, cup_camera_xyz, width: int, height: int, fx: float, fy: float,
                             cx: float, cy: float, margin_m: float) -> dict:
    """Deterministic pinhole projection with top-left fill; the margin is inclusive."""

    if not fx or not fy or width <= 0 or height <= 0 or margin_m <= 0:
        raise ValueError("PROJECTION_DEGENERATE: focal length, size or margin is not usable")
    x, y, z = cup_camera_xyz
    if z <= 0.0:
        raise ValueError("PROJECTION_FAR_OR_BEHIND: cup is at or behind the camera plane")
    if z < margin_m:
        raise ValueError("PROJECTION_NEAR_PLANE: cup is inside the near-plane margin")
    u = fx * x / z + cx
    v = fy * y / z + cy
    if not (u == u and v == v):                       # NaN guard without importing math
        raise ValueError("PROJECTION_DEGENERATE: non-finite image point")
    return {"u_px": min(max(u, 0.0), float(width - 1)), "v_px": min(max(v, 0.0), float(height - 1))}
