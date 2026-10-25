"""The indoor YOLO dataset generator CLI: a tiny dataset end to end (skipped without MuJoCo and an offscreen GL)."""

from __future__ import annotations

import json
import os

import numpy as np
import pytest

os.environ.setdefault("MUJOCO_GL", "osmesa")
pytest.importorskip("mujoco")

from paths import PACKAGE_ROOT  # noqa: E402
from so101_demo.act import indoor_yolo_dataset as iyd  # noqa: E402
from so101_demo.act import indoor_yolo_render as render  # noqa: E402
from so101_demo.cli import generate_indoor_yolo_dataset as cli  # noqa: E402

ACT_ASSETS = PACKAGE_ROOT / "assets/mujoco/act"


def _run(root, act, *extra):
    return cli.main(["--output-root", str(root), "--act-assets", str(act), "--train", "3", "--val", "2", "--test", "2", "--eval-indoor-nominal", "2",
                     "--eval-dark-nominal", "2", "--train-dark", "1", "--train-ring", "2", "--train-negative", "2", *extra])


@pytest.fixture(scope="module")
def dataset(tmp_path_factory, indoor_pool_act):
    root = tmp_path_factory.mktemp("indoor-dataset") / "ds"
    try:
        probe = render.IndoorFrameRenderer(indoor_pool_act, tmp_path_factory.mktemp("probe"))
        probe.render(iyd.draw_sample(1, "eval_dark_nominal", 0, iyd.layout_inventories(indoor_pool_act)))
    except Exception as error:      # noqa: BLE001 - no usable GL context on this host
        pytest.skip(f"no offscreen GL: {error}")
    assert _run(root, indoor_pool_act) == 0
    return root


def test_the_tree_matches_the_ultralytics_layout(dataset):
    for directory, count in (("train", 8), ("val", 2), ("test", 2), ("eval_indoor_nominal", 2), ("eval_dark_nominal", 2)):
        images = sorted((dataset / "images" / directory).glob("*.png"))
        assert len(images) == count
        for image in images:
            assert (dataset / "labels" / directory / (image.stem + ".txt")).is_file()
            assert (dataset / "truth" / directory / (image.stem + ".json")).is_file()
    assert "train: images/train" in (dataset / "dataset.yaml").read_text()
    assert not list((dataset / "depth" / "train").glob("*")) and len(list((dataset / "depth" / "test").glob("*.npz"))) == 2


def test_labels_are_polygons_of_the_cup_and_truth_records_the_draw(dataset):
    label = next((dataset / "labels" / "val").glob("*.txt")).read_text().strip().splitlines()
    assert len(label) == 1 and label[0].startswith("0 ")
    truth = json.loads(next((dataset / "truth" / "test").glob("*.json")).read_text())
    assert {"sample_id", "layout", "cup_xy", "cup_family", "realized_sha256", "mask_pixels", "camera", "variant"} <= set(truth)
    assert truth["mask_pixels"] >= cli.MIN_MASK_PIXELS


def test_negative_frames_have_an_empty_label_and_ring_frames_a_cup_in_the_zone(dataset):
    labels = {path.stem: path.read_text() for path in (dataset / "labels" / "train").glob("*.txt")}
    negatives = [name for name in labels if name.startswith("train_negative")]
    assert len(negatives) == 2 and all(labels[name].strip() == "" for name in negatives)
    rings = [json.loads((dataset / "truth" / "train" / f"{name}.json").read_text()) for name in labels if name.startswith("train_ring")]
    assert len(rings) == 2 and all(labels[row["sample_id"]].startswith("0 ") and -0.24 <= row["cup_xy"][1] <= -0.17 for row in rings)
    hidden = json.loads((dataset / "truth" / "train" / f"{negatives[0]}.json").read_text())
    assert hidden["mask_pixels"] == 0 and hidden["cup_hidden"] is True


def test_depth_is_stored_in_millimetres_for_the_evaluation_sets(dataset):
    stored = np.load(next((dataset / "depth" / "eval_indoor_nominal").glob("*.npz")))
    depth, mask = stored["depth_mm"], np.unpackbits(stored["mask_packed"])[:480 * 640].reshape(480, 640).astype(bool)
    assert mask.sum() >= cli.MIN_MASK_PIXELS and depth[mask].min() > 300
    assert depth.dtype == np.uint16 and depth.shape == (480, 640) and depth.max() > 300


def test_the_manifest_hashes_the_plan_and_every_file(dataset):
    manifest = json.loads((dataset / "dataset-manifest.json").read_text())
    assert manifest["counts"]["train"] == 3 and len(manifest["plan_sha256"]) == 64 and manifest["master_seed"] == 20261024
    assert manifest["files"] and all(len(value) == 64 for value in manifest["files"].values())


def test_a_second_run_with_the_same_seed_writes_identical_files(dataset, tmp_path, indoor_pool_act):
    assert _run(tmp_path / "again", indoor_pool_act) == 0
    first = json.loads((dataset / "dataset-manifest.json").read_text())["files"]
    second = json.loads((tmp_path / "again" / "dataset-manifest.json").read_text())["files"]
    assert set(first) == set(second)
    # software GL is bit-exact; EGL on the GPU jitters a few pixels by one level, so images and depth are compared by content with that tolerance
    for key in first:
        if key.startswith("images/"):
            from PIL import Image
            one = np.asarray(Image.open(dataset / key).convert("RGB")).astype(int)
            other = np.asarray(Image.open(tmp_path / "again" / key).convert("RGB")).astype(int)
            assert np.abs(one - other).max() <= 1 and (one != other).sum() <= 300, key
        elif key.startswith("depth/"):
            a, b = np.load(dataset / key), np.load(tmp_path / "again" / key)
            assert np.array_equal(a["mask_packed"], b["mask_packed"]) and np.abs(a["depth_mm"].astype(int) - b["depth_mm"].astype(int)).max() <= 2, key
        else:
            assert first[key] == second[key], key       # labels (from the mask), truth records and dataset.yaml are exact


def test_an_existing_output_root_is_refused(dataset, indoor_pool_act):
    with pytest.raises(SystemExit):
        _run(dataset, indoor_pool_act)
