"""The ACT-scene perception gate (CP-3467): the production detector and the production localizer on rendered frames of the scene.

The saved Broker inputs of the pilot all show the same few cup positions, and the benchmark suite scores masks, not poses. This gate
renders the ACT scene (RGB, depth, the cup's ground truth, the production camera chain) over the three calibration anchors, 300
random cup positions on the table and a stratum around the red landing ring, then runs, inside the production perception image with
the package under test mounted: the production YOLO detector (confidence 0.25, NMS 0.7, BGR hand-over), the Broker's wire conversion
and the Worker's `BrokerMaskLocalizer` with rule R6. The detector returns the red landing ring as a second candidate when the cup is
near it; R6 must keep the cup.

Gates: exactly one cup in at least 99% of the cases, no case where the returned object is not the cup, p95 of the xy error under
1.5 mm. They are measured on the rendered scene (a simulator, not the real camera), so they bound the pipeline, not the sensor.

Explicit gate only: it needs Docker, a GPU, the production image, the YOLO weights and MuJoCo with EGL, and is skipped (with the missing
piece named) where they are absent. Run it with
`colcon test --packages-select so101_demo_py --pytest-args benchmark_test`; set `SO101_ACT_SCENE_GATE_REPORT` to keep the result.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
mujoco = pytest.importorskip("mujoco")
yaml = pytest.importorskip("yaml")

import so101_demo  # noqa: E402  (the EGL environment above must be set before MuJoCo is imported)

PACKAGE = Path(so101_demo.__file__).resolve().parent


def _share():
    """The package's share directory, as production resolves its assets; the source tree when it is not installed."""
    try:
        from ament_index_python.packages import get_package_share_directory

        return Path(get_package_share_directory("so101_demo_py"))
    except Exception:   # noqa: BLE001
        return PACKAGE.parent


SCENE = _share() / "assets" / "mujoco" / "act" / "scene.xml"
ANCHORS = _share() / "config" / "act" / "task8-live-anchors.yaml"
IMAGE = os.environ.get("SO101_ACT_SCENE_GATE_IMAGE", "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1")
YOLO_WEIGHTS = Path(os.environ.get("SO101_ACT_SCENE_GATE_YOLO", "/data/work/models/so101-perception/yolo11n-seg-plastic-cup/best.pt"))
GROUNDED = Path(os.environ.get("SO101_ACT_SCENE_GATE_GROUNDED",
                               "/data/work/models/so101-perception/grounded-sam-cup-pickplace/bundle"))
RUNNER = Path(__file__).with_name("act_scene_runner.py")
SEED, RANDOM_CASES, RING_CASES = 20261008, 300, 40
RANDOM_X, RANDOM_Y, CUP_Z = (-0.15, 0.15), (-0.42, -0.20), 0.165
RING_REACH_M = 0.12
#: the dense ring stratum (perception-risks findings, R-b): 12 distances from the ring centre x 12 azimuths
DENSE_RING_DISTANCES_M = (0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12)
DENSE_RING_AZIMUTHS = 12
GATE_DENSE_RING_P95_MM = 1.0
GATE_EXACTLY_ONE, GATE_P95_M, WRONG_OBJECT_M = 0.99, 0.0015, 0.02
GATE_SENSITIVITY_P95_MM = 1.0       # a 1 px dilation or erosion of the selected mask may move the pose by this much (anchors, random)
WIDTH, HEIGHT = 640, 480


def _missing_prerequisite():
    if shutil.which("docker") is None:
        return "docker is not installed"
    if not YOLO_WEIGHTS.is_file() or not GROUNDED.is_dir():
        return f"model files are absent ({YOLO_WEIGHTS}, {GROUNDED})"
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode != 0:
        return f"image {IMAGE} is absent"
    return None


def _rpy_matrix(roll, pitch, yaw):
    cr, sr, cp, sp, cy, sy = np.cos(roll), np.sin(roll), np.cos(pitch), np.sin(pitch), np.cos(yaw), np.sin(yaw)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def _quaternion(matrix):
    w = np.sqrt(max(1.0 + matrix[0, 0] + matrix[1, 1] + matrix[2, 2], 0.0)) / 2
    if w > 1e-6:
        return ((matrix[2, 1] - matrix[1, 2]) / (4 * w), (matrix[0, 2] - matrix[2, 0]) / (4 * w),
                (matrix[1, 0] - matrix[0, 1]) / (4 * w), w)
    index = int(np.argmax(np.diag(matrix)))
    j, k = (index + 1) % 3, (index + 2) % 3
    s = np.sqrt(matrix[index, index] - matrix[j, j] - matrix[k, k] + 1.0) * 2
    q = np.zeros(4)
    q[index], q[3] = 0.25 * s, (matrix[k, j] - matrix[j, k]) / s
    q[j], q[k] = (matrix[j, index] + matrix[index, j]) / s, (matrix[k, index] + matrix[index, k]) / s
    return tuple(float(v) for v in q)


def _camera_transform(model):
    """world <- task_camera_frame: the production static chain (runtime/camera_tf.py) on the scene's base body."""
    from so101_demo.runtime.camera_tf import BASE_TO_CAMERA, CAMERA_TO_OPTICAL

    base = np.asarray(model.body("base").pos, dtype=float)
    rotation = _rpy_matrix(*BASE_TO_CAMERA.rpy) @ _rpy_matrix(*CAMERA_TO_OPTICAL.rpy)
    translation = _rpy_matrix(0.0, 0.0, 0.0) @ np.asarray(BASE_TO_CAMERA.translation_xyz) + base
    x, y, z, w = _quaternion(rotation)
    return {"rotation": {"x": x, "y": y, "z": z, "w": w},
            "translation": {"x": float(translation[0]), "y": float(translation[1]), "z": float(translation[2])}}


def _cases(model, data):
    anchors = yaml.safe_load(ANCHORS.read_text())["anchors"]
    cases = [(f"anchor_{name}", "anchor", list(item["cup_start_m"])) for name, item in anchors.items()]
    rng = np.random.default_rng(SEED)
    for index in range(RANDOM_CASES):
        cases.append((f"random{index:03d}", "random",
                      [float(rng.uniform(*RANDOM_X)), float(rng.uniform(*RANDOM_Y)), CUP_Z]))
    mujoco.mj_forward(model, data)
    ring = np.asarray(data.geom_xpos[model.geom("target_landing_tolerance_ring").id], dtype=float)
    for index in range(RING_CASES):
        angle, reach = rng.uniform(0, 2 * np.pi), RING_REACH_M * np.sqrt(rng.uniform())
        cases.append((f"ring{index:02d}", "ring", [float(ring[0] + reach * np.cos(angle)), float(ring[1] + reach * np.sin(angle)), CUP_Z]))
    for distance in DENSE_RING_DISTANCES_M:
        for index in range(DENSE_RING_AZIMUTHS):
            angle = index * 2.0 * np.pi / DENSE_RING_AZIMUTHS + np.pi / DENSE_RING_AZIMUTHS
            cases.append((f"dense_d{round(distance * 1000):03d}_a{index:02d}", "dense_ring",
                          [float(ring[0] + distance * np.cos(angle)), float(ring[1] + distance * np.sin(angle)), CUP_Z]))
    return cases


def _render(directory):
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, HEIGHT, WIDTH)
    listing = []
    for name, stratum, position in _cases(model, data):
        mujoco.mj_resetDataKeyframe(model, data, model.key("task_start").id)
        data.qpos[7:10] = position
        mujoco.mj_forward(model, data)
        renderer.disable_depth_rendering()
        renderer.update_scene(data, camera="task_camera")
        rgb = renderer.render().copy()
        renderer.enable_depth_rendering()
        renderer.update_scene(data, camera="task_camera")
        depth = renderer.render().copy().astype(np.float32)
        np.savez_compressed(directory / f"{name}.npz", rgb=rgb, depth=depth)
        listing.append({"name": name, "stratum": stratum, "gt": position})
    focal = (HEIGHT / 2) / np.tan(np.radians(float(model.cam_fovy[model.cam("task_camera").id])) / 2)
    spec = {"width": WIDTH, "height": HEIGHT, "k": [focal, 0, WIDTH / 2, 0, focal, HEIGHT / 2, 0, 0, 1],
            "tf": _camera_transform(model), "cases": listing}
    (directory / "spec.json").write_text(json.dumps(spec))
    return spec


def _run_container(cases, out):
    out.mkdir(exist_ok=True)
    command = ["docker", "run", "--rm", "--gpus", "all", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,mode=1777",
               "--user", f"{os.getuid()}:{os.getgid()}", "--entrypoint", "python",
               "-e", "YOLO_CONFIG_DIR=/tmp/yc", "-e", "MPLCONFIGDIR=/tmp/mpl",
               "-v", f"{PACKAGE}:/opt/venv/lib/python3.12/site-packages/so101_demo:ro",
               "-v", f"{YOLO_WEIGHTS}:/models/yolo/best.pt:ro", "-v", f"{GROUNDED}:/models/grounded:ro",
               "-v", f"{cases}:/cases:ro", "-v", f"{out}:/out:rw", "-v", f"{RUNNER}:/runner.py:ro", IMAGE, "/runner.py"]
    done = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    return json.loads((out / "results.json").read_text())


def summarize(results):
    """The numbers the gates read (pure: also exercised by the tests below without Docker)."""
    ones = [r for r in results if r["outcome"] == "ONE"]
    wrong = [r for r in ones if r["xy_error_m"] > WRONG_OBJECT_M]
    errors = np.array([r["xy_error_m"] for r in ones if r["xy_error_m"] <= WRONG_OBJECT_M]) if ones else np.array([])
    strata = {}
    for stratum in sorted({r["stratum"] for r in results}):
        members = [r for r in results if r["stratum"] == stratum]
        errors = np.array([r["xy_error_m"] for r in members if r["outcome"] == "ONE" and r["xy_error_m"] <= WRONG_OBJECT_M])
        strata[stratum] = {"cases": len(members), "exactly_one": sum(1 for r in members if r["outcome"] == "ONE"),
                           "xy_error_mm": {"mean": float(errors.mean() * 1000) if errors.size else None,
                                           "p95": float(np.percentile(errors, 95) * 1000) if errors.size else None,
                                           "max": float(errors.max() * 1000) if errors.size else None}}
    sensitivity = {}
    for stratum in sorted({r["stratum"] for r in results}):
        moves = [r["sensitivity_mm"] for r in ones if r["stratum"] == stratum and r.get("sensitivity_mm")]
        values = [v for m in moves for k, v in m.items() if k in ("dilate1", "erode1") and v is not None]
        failed = sum(1 for m in moves for k in ("dilate1", "erode1") if m.get(k) is None)
        sensitivity[stratum] = {"variants": len(values), "unlocalizable": failed,
                                "p95_mm": float(np.percentile(values, 95)) if values else None,
                                "max_mm": float(max(values)) if values else None}
    return {"cases": len(results), "exactly_one": len(ones), "mask_sensitivity": sensitivity, "exactly_one_rate": len(ones) / len(results) if results else 0.0,
            "wrong_object": len(wrong), "outcomes": {o: sum(1 for r in results if r["outcome"] == o)
                                                      for o in sorted({r["outcome"] for r in results})},
            "xy_error_mm": {"mean": float(errors.mean() * 1000) if errors.size else None,
                            "p95": float(np.percentile(errors, 95) * 1000) if errors.size else None,
                            "max": float(errors.max() * 1000) if errors.size else None},
            "raw_candidate_counts": {str(n): sum(1 for r in results if len(r["candidates"]) == n)
                                     for n in sorted({len(r["candidates"]) for r in results})},
            "strata": strata}


def test_the_production_detector_and_localizer_find_exactly_one_cup_on_the_rendered_scene(tmp_path):
    missing = _missing_prerequisite()
    if missing is not None:
        pytest.skip(f"ACT-scene perception gate needs the ai-station perception stack: {missing}")
    cases = tmp_path / "cases"
    cases.mkdir()
    spec = _render(cases)
    assert [c["stratum"] for c in spec["cases"]].count("anchor") == 3
    assert [c["stratum"] for c in spec["cases"]].count("random") == RANDOM_CASES >= 300
    assert [c["stratum"] for c in spec["cases"]].count("dense_ring") == len(DENSE_RING_DISTANCES_M) * DENSE_RING_AZIMUTHS
    document = _run_container(cases, tmp_path / "out")
    summary = summarize(document["results"])
    summary["weights_sha256"], summary["image"] = document["weights_sha256"], IMAGE
    if os.environ.get("SO101_ACT_SCENE_GATE_REPORT"):
        Path(os.environ["SO101_ACT_SCENE_GATE_REPORT"]).write_text(json.dumps({"summary": summary, "results": document["results"]}, indent=1))
    print(json.dumps(summary, indent=1))
    assert summary["wrong_object"] == 0, summary
    assert summary["exactly_one_rate"] >= GATE_EXACTLY_ONE, summary
    assert summary["xy_error_mm"]["p95"] < GATE_P95_M * 1000, summary
    assert summary["strata"]["anchor"]["exactly_one"] == 3, summary
    dense = summary["strata"]["dense_ring"]
    assert dense["cases"] == len(DENSE_RING_DISTANCES_M) * DENSE_RING_AZIMUTHS, dense
    # the p95 is over the cases that gave one cup; a case that did not (dense_d030_a07: the cup and a 0.34 fragment both pass R6, a
    # known case inside the excluded 0.065 m disc around the ring) is counted in `exactly_one` and the overall 99% gate, not here
    assert dense["xy_error_mm"]["p95"] <= GATE_DENSE_RING_P95_MM, dense
    # one pixel of mask: gated on the anchors and the random positions, reported (not gated) for the ring stratum
    for stratum in ("anchor", "random"):
        moved = summary["mask_sensitivity"][stratum]
        assert moved["p95_mm"] <= GATE_SENSITIVITY_P95_MM, (stratum, moved)   # variants the localizer rejects are counted, not gated


# ---- the arithmetic of the gate, without Docker --------------------------------------------------------------------------------

def _row(stratum, outcome, error=None, candidates=2):
    return {"stratum": stratum, "outcome": outcome, "xy_error_m": error, "candidates": [["c", 0.9]] * candidates}


def test_the_summary_counts_exactly_one_wrong_object_and_the_error_percentile():
    rows = [_row("random", "ONE", 0.0005)] * 18 + [_row("ring", "ONE", 0.0021), _row("ring", "ONE", 0.05), _row("ring", "AMBIGUOUS"),
                                                   _row("anchor", "REJECTED")]
    summary = summarize(rows)
    assert summary["cases"] == 22 and summary["exactly_one"] == 20 and summary["wrong_object"] == 1
    assert summary["outcomes"] == {"AMBIGUOUS": 1, "ONE": 20, "REJECTED": 1}
    assert (summary["strata"]["ring"]["cases"], summary["strata"]["ring"]["exactly_one"]) == (3, 2)
    assert (summary["strata"]["random"]["cases"], summary["strata"]["random"]["exactly_one"]) == (18, 18)
    assert summary["strata"]["random"]["xy_error_mm"]["p95"] == pytest.approx(0.5)
    assert summary["xy_error_mm"]["max"] == pytest.approx(2.1)
    assert summary["raw_candidate_counts"] == {"2": 22}


def test_the_mask_sensitivity_summary_gates_anchor_and_random_but_only_reports_the_ring():
    def row(stratum, dilate, erode):
        return dict(_row(stratum, "ONE", 0.0005), sensitivity_mm={"dilate1": dilate, "erode1": erode})

    rows = [row("anchor", 0.05, 0.04), row("random", 0.3, 0.2), row("random", 0.9, None), row("ring", 8.0, 6.0)]
    moved = summarize(rows)["mask_sensitivity"]
    assert moved["anchor"] == {"variants": 2, "unlocalizable": 0, "p95_mm": pytest.approx(0.0495), "max_mm": 0.05}
    assert moved["random"]["unlocalizable"] == 1 and moved["random"]["variants"] == 3 and moved["random"]["max_mm"] == 0.9
    assert moved["ring"]["max_mm"] == 8.0, "reported for the ring stratum, which the gate does not read"


def test_the_camera_chain_matches_the_scene_camera():
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    transform = _camera_transform(model)
    camera = model.cam("task_camera").id
    assert np.allclose([transform["translation"][a] for a in "xyz"], data.cam_xpos[camera], atol=1e-6), "the scene camera is the TF chain"
