#!/usr/bin/env python3
"""Check the calibrated side camera of the real-twin scene against the real camera.

    MUJOCO_GL=egl python check_real_twin_side_camera.py CALIB_ROOT OUT_DIR [--snapshot FILE]

1. Reprojection: the ArUco corners of aruco-sheet-layout.json (plan coordinates, z = 0 on the table) are projected through
   the twin side camera (its MuJoCo pose and pinhole intrinsics read back from the compiled model, plus the real lens
   distortion, applied here only) and compared with the corners detected in the real frames aruco-side/*.png.
   Detection needs OpenCV with the aruco module; run --detect-only in such an environment if the MuJoCo one lacks it.
2. Rendering: the twin side camera at q = 0 and at the follower rest pose, with the bowl and cubes put at the mat layout,
   next to the real snapshot, the undistorted real snapshot, and a blend of the undistorted real frame with the render.

The calibration files are read from CALIB_ROOT; nothing is written there.
"""

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import cv2  # noqa: E402
try:
    import mujoco  # noqa: E402
except ImportError:  # --detect-only needs only OpenCV with the aruco module
    mujoco = None
import numpy as np  # noqa: E402

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCENE = PACKAGE_ROOT / "assets/mujoco/real_twin/scene_real_twin_cube_bowl.xml"
TABLE_TOP = 0.75


def plan_to_world(x_cm, y_cm, z_cm=0.0):
    return np.array([x_cm / 100.0, -y_cm / 100.0, TABLE_TOP + z_cm / 100.0])


def camera_matrices(model, data, name="side_camera"):
    """OpenCV K from the compiled MuJoCo camera, and its world pose (position, rotation world->opencv camera)."""
    cam = model.camera(name).id
    width, height = (int(v) for v in model.cam_resolution[cam])
    fx, fy, px, py = model.cam_intrinsic[cam] / model.cam_sensorsize[cam][[0, 1, 0, 1]] * [width, height, width, height]
    # principal shift is towards the top left in continuous pixels; OpenCV centre is (W - 1) / 2
    cx, cy = (width - 1) / 2.0 - px, (height - 1) / 2.0 - py
    K = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])
    r_mj = data.cam_xmat[cam].reshape(3, 3)  # columns: camera x, y, z in the world; the camera looks along -z
    r_cv = r_mj * np.array([1.0, -1.0, -1.0])  # OpenCV axes: x right, y down, z forward
    return K, data.cam_xpos[cam].copy(), r_cv


def project(points_world, K, position, r_cv, dist):
    cam_pts = (points_world - position) @ r_cv  # rows: R^T (P - c)
    pix, _ = cv2.projectPoints(cam_pts.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), K, dist)
    return pix.reshape(-1, 2)


def detect_corners(calib: Path) -> dict:
    """Detect the ArUco corners (DICT_5X5_100) in every aruco-side frame: {image: {marker id: [[u, v] x 4]}}."""
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100), cv2.aruco.DetectorParameters())
    found = {}
    for image_path in sorted((calib / "aruco-side").glob("*.png")):
        corners, ids, _ = detector.detectMarkers(cv2.imread(str(image_path)))
        found[image_path.name] = {} if ids is None else {str(int(i)): c.reshape(4, 2).tolist() for c, i in zip(corners, ids.ravel())}
    return found


def reprojection(layout_path: Path, detections: dict, model, data, dist):
    layout = json.loads(layout_path.read_text())
    markers = {k: np.array(v, dtype=float) for k, v in layout["markers"].items()}
    K, position, r_cv = camera_matrices(model, data)
    rows = []
    for image_name, per_marker in detections.items():
        errors = []
        for marker_id, found in per_marker.items():
            if marker_id not in markers:
                continue
            world = np.array([plan_to_world(*p) for p in markers[marker_id]])
            predicted = project(world, K, position, r_cv, dist)
            errors.extend(np.linalg.norm(predicted - np.array(found), axis=1))
        rows.append({"image": image_name, "markers": len(errors) // 4, "mean_px": float(np.mean(errors)), "max_px": float(np.max(errors))})
    return {"frames": rows, "mean_px": float(np.mean([r["mean_px"] for r in rows])), "max_px": max(r["max_px"] for r in rows), "K_from_model": K.tolist()}


def render(model, data, name="side_camera"):
    width, height = (int(v) for v in model.cam_resolution[model.camera(name).id])
    renderer = mujoco.Renderer(model, height=height, width=width)
    try:
        renderer.update_scene(data, camera=name)
        return renderer.render().copy()
    finally:
        renderer.close()


def place_free_body(model, data, joint_name, plan_xy_cm, z_m):
    qadr = model.joint(joint_name).qposadr[0]
    data.qpos[qadr : qadr + 3] = [plan_xy_cm[0] / 100.0, -plan_xy_cm[1] / 100.0, z_m]
    data.qpos[qadr + 3 : qadr + 7] = [1, 0, 0, 0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("calib_root", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--detect-only", type=Path, default=None, metavar="JSON", help="write the detected corners to JSON and stop (needs OpenCV with aruco, no MuJoCo)")
    parser.add_argument("--detections", type=Path, default=None, help="corners JSON written by --detect-only (default: detect here)")
    parser.add_argument("--layout", type=Path, default=None, help="ArUco layout JSON (default: CALIB_ROOT/aruco-sheet-layout.json); use the one the frames were captured with")
    parser.add_argument("--bowl", nargs=2, type=float, default=None, help="plan x y (cm) of the bowl centre, to match a snapshot taken at another sheet position")
    parser.add_argument("--snapshot", type=Path, default=None, help="real side snapshot (default: newest side_*.png in CALIB_ROOT/snap)")
    parser.add_argument("--cell-green", nargs=2, type=float, default=None, help="plan x y (cm) of the green cube")
    parser.add_argument("--cell-red", nargs=2, type=float, default=None, help="plan x y (cm) of the red cube")
    parser.add_argument("--green-z-cm", type=float, default=1.0, help="height of the green cube centre above the table (1.4 inside the bowl)")
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.detect_only:
        args.detect_only.write_text(json.dumps(detect_corners(args.calib_root)))
        return 0
    intrinsics = json.loads((args.calib_root / "intrinsics-side.json").read_text())
    K_real, D = np.array(intrinsics["K"]), np.array(intrinsics["D"])

    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, model.key("task_start").id)
    mujoco.mj_forward(model, data)
    detections = json.loads(args.detections.read_text()) if args.detections else detect_corners(args.calib_root)
    result = reprojection(args.layout or args.calib_root / "aruco-sheet-layout.json", detections, model, data, D)
    result["K_real"] = K_real.tolist()
    (args.out_dir / "reprojection.json").write_text(json.dumps(result, indent=1))
    print(f"reprojection: mean {result['mean_px']:.3f} px, max {result['max_px']:.3f} px")

    snapshot = args.snapshot or sorted((args.calib_root / "snap").glob("side_*.png"))[-1]
    real = cv2.cvtColor(cv2.imread(str(snapshot)), cv2.COLOR_BGR2RGB)
    undistorted = cv2.undistort(real, K_real, D, None, K_real)
    cv2.imwrite(str(args.out_dir / "real-side-undistorted.png"), cv2.cvtColor(undistorted, cv2.COLOR_RGB2BGR))
    for key in ("task_start", "rest_pose"):
        mujoco.mj_resetDataKeyframe(model, data, model.key(key).id)
        if args.bowl:
            model.body_pos[model.body("paper_bowl").id][:2] = [args.bowl[0] / 100.0, -args.bowl[1] / 100.0]
        if args.cell_green:
            place_free_body(model, data, "green_cube_joint", args.cell_green, TABLE_TOP + args.green_z_cm / 100.0)
        if args.cell_red:
            place_free_body(model, data, "red_cube_joint", args.cell_red, TABLE_TOP + 0.01)
        mujoco.mj_forward(model, data)
        sim = render(model, data)
        cv2.imwrite(str(args.out_dir / f"sim-side-{key}.png"), cv2.cvtColor(sim, cv2.COLOR_RGB2BGR))
        blend = cv2.addWeighted(undistorted, 0.5, sim, 0.5, 0.0)
        cv2.imwrite(str(args.out_dir / f"overlay-{key}.png"), cv2.cvtColor(blend, cv2.COLOR_RGB2BGR))
        sheet = np.hstack([real, undistorted, sim, blend])
        cv2.imwrite(str(args.out_dir / f"side-by-side-{key}.png"), cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))
    print(f"snapshot: {snapshot}")
    print(f"outputs: {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
