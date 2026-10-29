"""Offline scoring of a cup detector against simulation truth (indoor YOLO fine-tune, goal 11).

Per frame: was the cup found, the mask IoU against the MuJoCo segmentation mask, the mask-centre error in pixels, and the cup centre in
the world after the Teacher's own RGB-D circle fit (`cli.rgbd_cup_pose.estimate_upright_cup_pose`) against the true cup xy. The Teacher
builds its cloud with Open3D, depth truncation and clustering; this module back-projects the predicted mask's depth pixels itself and
applies the same circle fit and radius check, so the xy error is a proxy of the Teacher's, not its exact output.
"""

from __future__ import annotations

import math

import numpy as np

#: the Teacher's defaults (`ros/rgbd_cup_pose/frames.py` RgbdCupPoseOptions)
TABLE_TOP_Z_M = 0.12
CUP_HEIGHT_M = 0.09
CUP_RADIUS_M = 0.04
RADIUS_TOLERANCE_M = 0.01
DEPTH_TRUNC_M = 3.0
MIN_POINTS = 200
#: points within this height of the table top are table, not cup wall
TABLE_CLEARANCE_M = 0.01


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    union = int(np.logical_or(a, b).sum())
    return float(np.logical_and(a, b).sum()) / union if union else 0.0


def mask_centre_px(mask: np.ndarray):
    rows, columns = np.nonzero(mask)
    return None if rows.size == 0 else (float(columns.mean()), float(rows.mean()))


def backproject_world(mask: np.ndarray, depth: np.ndarray, camera: dict) -> np.ndarray:
    """World points of the mask pixels that have a valid depth (`camera`: pos, mat = MuJoCo cam_xmat, fovy in degrees, width, height)."""
    rows, columns = np.nonzero(mask & (depth > 0.0) & (depth < DEPTH_TRUNC_M))
    if rows.size == 0:
        return np.empty((0, 3))
    focal = (camera["height"] / 2) / math.tan(math.radians(camera["fovy"]) / 2)
    z = depth[rows, columns].astype(np.float64)
    x = (columns + 0.5 - camera["width"] / 2) * z / focal
    y = -(rows + 0.5 - camera["height"] / 2) * z / focal
    in_camera = np.stack([x, y, -z], axis=1)                       # MuJoCo camera frame: x right, y up, looking along -z
    return np.asarray(camera["pos"]) + in_camera @ np.asarray(camera["mat"]).reshape(3, 3).T


def cup_xy_from_mask_depth(mask: np.ndarray, depth: np.ndarray, camera: dict):
    """`{"xy": [x, y], "radius_m": r, "points": n}` from the circle fit of the wall points of the mask, or None (too few points,
    degenerate fit, or a fitted radius the Teacher's radius check refuses)."""
    from so101_demo.cli.rgbd_cup_pose import estimate_upright_cup_pose

    points = backproject_world(mask, depth, camera)
    points = points[points[:, 2] > TABLE_TOP_Z_M + TABLE_CLEARANCE_M]
    if len(points) < MIN_POINTS:
        return None
    try:
        centre, radius = estimate_upright_cup_pose(points, table_top_z=TABLE_TOP_Z_M, cup_height=CUP_HEIGHT_M,
                                                   expected_radius=CUP_RADIUS_M, radius_tolerance=RADIUS_TOLERANCE_M)
    except ValueError:
        return None
    return {"xy": [float(centre[0]), float(centre[1])], "radius_m": float(radius), "points": int(len(points))}


def _stats(values) -> dict:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return {"n": 0, "mean": None, "median": None, "p95": None, "max": None}
    return {"n": int(values.size), "mean": float(values.mean()), "median": float(np.median(values)),
            "p95": float(np.percentile(values, 95)), "max": float(values.max())}


def read_png_rgb8(path) -> np.ndarray:
    """Read an 8-bit RGB PNG written by `runtime.point_cloud_preview.write_png_rgb8` (non-interlaced, filter type 0)."""
    import struct
    import zlib
    from pathlib import Path

    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    position, payload, width, height = 8, b"", 0, 0
    while position < len(data):
        length, kind = struct.unpack(">I4s", data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour, _compression, _filter, interlace = struct.unpack(">IIBBBBB", body)
            if (depth, colour, interlace) != (8, 2, 0):
                raise ValueError("PNG is not 8-bit RGB without interlacing")
        elif kind == b"IDAT":
            payload += body
        position += 12 + length
    rows = np.frombuffer(zlib.decompress(payload), dtype=np.uint8).reshape(height, 1 + 3 * width)
    if rows[:, 0].any():
        raise ValueError("PNG uses scanline filters")
    return rows[:, 1:].reshape(height, width, 3).copy()


IOU_SUCCESS = 0.5


def score_frames(frames: list, predict, *, threshold: float) -> list:
    """Score `predict(rgb) -> [(confidence, mask)]` on `frames` (dicts: truth mask, depth, camera, cup_xy, cup_hidden, rgb).

    The Teacher keeps the instances at or above `threshold` and refuses a frame with more than one (TARGET_AMBIGUOUS), so a positive
    frame is OK only with exactly one such instance whose mask overlaps the truth (IoU at least 0.5); a negative frame (cup hidden)
    is CLEAN only without any instance."""
    rows = []
    for frame in frames:
        found = sorted(((confidence, mask) for confidence, mask in predict(frame["rgb"]) if confidence >= threshold), key=lambda item: -item[0])
        if frame["cup_hidden"]:
            rows.append({"status": "FALSE_POSITIVE" if found else "CLEAN", "detections": len(found), "negative": True})
            continue
        row = {"status": "MISSED", "detected": False, "detections": len(found), "iou": 0.0, "centre_error_px": None, "xy_error_m": None,
               "negative": False}
        if found:
            best = found[0][1]
            row.update(detected=True, iou=mask_iou(best, frame["truth"]))
            truth_centre, centre = mask_centre_px(frame["truth"]), mask_centre_px(best)
            if truth_centre is not None and centre is not None:
                row["centre_error_px"] = math.dist(truth_centre, centre)
            row["status"] = "AMBIGUOUS" if len(found) > 1 else ("OK" if row["iou"] >= IOU_SUCCESS else "WRONG_OBJECT")
            if frame.get("depth") is not None and row["status"] in ("OK", "AMBIGUOUS"):
                estimate = cup_xy_from_mask_depth(best, frame["depth"], frame["camera"])
                if estimate is not None:
                    row["xy_error_m"] = math.dist(estimate["xy"], frame["cup_xy"])
        rows.append(row)
    return rows


def summarise(rows: list) -> dict:
    """The per-set report from per-frame rows; negative rows (cup hidden) are counted apart."""
    negatives = [row for row in rows if row.get("negative")]
    rows = [row for row in rows if not row.get("negative")]
    detected = [row for row in rows if row["detected"]]
    poses = [row["xy_error_m"] for row in rows if row.get("xy_error_m") is not None]
    frames = len(rows)
    count = lambda status: sum(1 for row in rows if row.get("status") == status)      # noqa: E731
    return {"frames": frames, "detected": len(detected), "detection_rate": len(detected) / frames if frames else None,
            "ok": count("OK"), "ambiguous": count("AMBIGUOUS"), "missed": count("MISSED"), "wrong_object": count("WRONG_OBJECT"),
            "success_rate": count("OK") / frames if frames else None,
            "negative_frames": len(negatives), "false_positive_frames": sum(1 for row in negatives if row["status"] == "FALSE_POSITIVE"),
            "mean_iou_detected": float(np.mean([row["iou"] for row in detected])) if detected else None,
            "mean_iou_all": float(np.mean([row["iou"] for row in rows])) if rows else None,
            "centre_error_px": _stats([row["centre_error_px"] for row in rows if row.get("centre_error_px") is not None]),
            "pose_ok": len(poses), "pose_rate_of_frames": len(poses) / frames if frames else None,
            "xy_error_mm": _stats([1000.0 * value for value in poses])}
