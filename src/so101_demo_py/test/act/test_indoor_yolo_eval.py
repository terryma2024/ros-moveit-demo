"""Offline scoring of a cup detector against simulation truth: mask IoU, centre error in pixels, cup xy after the RGB-D circle fit."""

from __future__ import annotations

import math

import numpy as np
import pytest

from so101_demo.act import indoor_yolo_eval as ev

WIDTH, HEIGHT, FOVY = 640, 480, 45.0
CAMERA = {"pos": [0.65, -0.65, 0.55], "mat": None, "fovy": FOVY, "width": WIDTH, "height": HEIGHT}


def _looking_at(target):
    """A MuJoCo camera matrix (x right, y up, z backward) for a camera at CAMERA["pos"] looking at `target`."""
    eye = np.array(CAMERA["pos"])
    forward = np.array(target) - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return np.column_stack([right, up, -forward])


def _cylinder_scene(center_xy, radius=0.04, z0=0.12, height=0.09):
    """Depth map and mask of the standing wall of a cup, ray-cast from the camera (analytic cylinder, wall only)."""
    camera = dict(CAMERA, mat=_looking_at([center_xy[0], center_xy[1], 0.16]).reshape(9).tolist())
    mat = np.array(camera["mat"]).reshape(3, 3)
    focal = (HEIGHT / 2) / math.tan(math.radians(FOVY) / 2)
    us, vs = np.meshgrid(np.arange(WIDTH) + 0.5, np.arange(HEIGHT) + 0.5)
    rays = np.stack([(us - WIDTH / 2) / focal, -(vs - HEIGHT / 2) / focal, -np.ones_like(us)], axis=-1) @ mat.T
    eye = np.array(camera["pos"])
    ox, oy = eye[0] - center_xy[0], eye[1] - center_xy[1]
    a = rays[..., 0] ** 2 + rays[..., 1] ** 2
    b = 2 * (ox * rays[..., 0] + oy * rays[..., 1])
    c = ox * ox + oy * oy - radius * radius
    disc = b * b - 4 * a * c
    t = np.where(disc >= 0, (-b - np.sqrt(np.maximum(disc, 0))) / (2 * a), np.inf)
    z = eye[2] + t * rays[..., 2]
    mask = np.isfinite(t) & (z >= z0) & (z <= z0 + height)
    depth = np.where(mask, t * (rays @ -mat[:, 2]), 0.0).astype(np.float32)        # distance along the optical axis, as MuJoCo's depth buffer
    return camera, mask, depth


def test_mask_iou_and_centre_pixels():
    a = np.zeros((10, 10), bool)
    a[2:6, 2:6] = True
    b = np.zeros((10, 10), bool)
    b[4:8, 4:8] = True
    assert ev.mask_iou(a, a) == 1.0 and ev.mask_iou(a, np.zeros_like(a)) == 0.0
    assert ev.mask_iou(a, b) == pytest.approx(4 / 28)
    assert ev.mask_centre_px(a) == (3.5, 3.5)
    assert ev.mask_centre_px(np.zeros_like(a)) is None


def test_the_circle_fit_recovers_the_cup_centre_from_mask_and_depth():
    for centre in ((0.02, -0.28), (-0.04, -0.25), (0.07, -0.33)):
        camera, mask, depth = _cylinder_scene(centre)
        assert mask.sum() > 500
        estimate = ev.cup_xy_from_mask_depth(mask, depth, camera)
        assert estimate is not None
        assert math.dist(estimate["xy"], centre) < 0.003
        assert estimate["radius_m"] == pytest.approx(0.04, abs=0.004)


def test_a_mask_without_depth_or_with_too_few_points_gives_no_pose():
    camera, mask, depth = _cylinder_scene((0.02, -0.28))
    assert ev.cup_xy_from_mask_depth(np.zeros_like(mask), depth, camera) is None
    assert ev.cup_xy_from_mask_depth(mask, np.zeros_like(depth), camera) is None


def test_a_mask_on_the_floor_is_rejected_by_the_radius_check():
    camera, mask, depth = _cylinder_scene((0.02, -0.28), radius=0.12)      # a far bigger cylinder: the Teacher's radius check refuses it
    assert ev.cup_xy_from_mask_depth(mask, depth, camera) is None


def test_the_summary_counts_detections_misses_and_pose_failures():
    rows = [
        {"detected": True, "iou": 0.9, "centre_error_px": 1.0, "xy_error_m": 0.001},
        {"detected": True, "iou": 0.7, "centre_error_px": 3.0, "xy_error_m": None},
        {"detected": False, "iou": 0.0, "centre_error_px": None, "xy_error_m": None},
        {"detected": True, "iou": 0.8, "centre_error_px": 2.0, "xy_error_m": 0.003},
    ]
    summary = ev.summarise(rows)
    assert summary["frames"] == 4 and summary["detected"] == 3 and summary["detection_rate"] == 0.75
    assert summary["mean_iou_detected"] == pytest.approx(0.8) and summary["mean_iou_all"] == pytest.approx(0.6)
    assert summary["centre_error_px"]["median"] == 2.0
    assert summary["pose_ok"] == 2 and summary["pose_rate_of_frames"] == 0.5
    assert summary["xy_error_mm"]["median"] == pytest.approx(2.0)
    assert ev.summarise([])["frames"] == 0


class _Fake:
    """A predictor stand-in: returns the instances queued for each call, as (confidence, mask) pairs."""

    def __init__(self, *calls):
        self.calls = list(calls)

    def __call__(self, rgb):
        return self.calls.pop(0)


def _frame(mask_box=(100, 140, 200, 260)):
    mask = np.zeros((480, 640), bool)
    top, bottom, left, right = mask_box
    mask[top:bottom, left:right] = True
    return mask


def test_a_frame_with_one_good_instance_is_a_success_and_two_instances_are_ambiguous():
    truth = _frame()
    camera, _mask, depth = _cylinder_scene((0.02, -0.28))
    good = (0.96, truth)
    ring = (0.7, _frame((300, 330, 400, 440)))
    rows = ev.score_frames([
        {"truth": truth, "depth": depth, "camera": camera, "cup_xy": [0.02, -0.28], "cup_hidden": False, "rgb": None},
        {"truth": truth, "depth": depth, "camera": camera, "cup_xy": [0.02, -0.28], "cup_hidden": False, "rgb": None},
        {"truth": truth, "depth": depth, "camera": camera, "cup_xy": [0.02, -0.28], "cup_hidden": False, "rgb": None},
    ], _Fake([good], [good, ring], []), threshold=0.5)
    assert [row["status"] for row in rows] == ["OK", "AMBIGUOUS", "MISSED"]
    assert rows[0]["iou"] == 1.0 and rows[0]["centre_error_px"] == 0.0
    assert rows[1]["detections"] == 2 and rows[2]["detected"] is False


def test_instances_below_the_threshold_do_not_count_and_a_wrong_mask_is_not_a_success():
    truth = _frame()
    row = ev.score_frames([{"truth": truth, "depth": None, "camera": None, "cup_xy": [0, 0], "cup_hidden": False, "rgb": None}],
                          _Fake([(0.4, truth), (0.9, _frame((300, 330, 400, 440)))]), threshold=0.5)[0]
    assert row["status"] == "WRONG_OBJECT" and row["detections"] == 1 and row["iou"] == 0.0


def test_negative_frames_count_any_instance_as_a_false_positive():
    rows = ev.score_frames([{"truth": np.zeros((480, 640), bool), "depth": None, "camera": None, "cup_xy": [0, 0], "cup_hidden": True, "rgb": None}] * 2,
                           _Fake([], [(0.8, _frame())]), threshold=0.5)
    assert [row["status"] for row in rows] == ["CLEAN", "FALSE_POSITIVE"]
    summary = ev.summarise(rows)
    assert summary["false_positive_frames"] == 1 and summary["negative_frames"] == 2 and summary["frames"] == 0


def test_the_summary_reports_the_teacher_view_success_ambiguous_and_missed_counts():
    rows = [{"status": "OK", "detected": True, "iou": 0.9, "centre_error_px": 1.0, "xy_error_m": 0.001, "detections": 1},
            {"status": "AMBIGUOUS", "detected": True, "iou": 0.9, "centre_error_px": 1.0, "xy_error_m": 0.001, "detections": 2},
            {"status": "MISSED", "detected": False, "iou": 0.0, "centre_error_px": None, "xy_error_m": None, "detections": 0}]
    summary = ev.summarise(rows)
    assert (summary["ok"], summary["ambiguous"], summary["missed"]) == (1, 1, 1) and summary["success_rate"] == pytest.approx(1 / 3)


def test_png_round_trip(tmp_path):
    from so101_demo.runtime.point_cloud_preview import write_png_rgb8

    image = np.random.default_rng(0).integers(0, 255, (12, 16, 3), dtype=np.uint8)
    write_png_rgb8(image, tmp_path / "a.png")
    assert np.array_equal(ev.read_png_rgb8(tmp_path / "a.png"), image)
