"""The indoor YOLO evaluation CLI: dataset loading and report assembly with a stand-in detector (no ultralytics needed)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from so101_demo.cli import evaluate_indoor_yolo as cli
from so101_demo.runtime.point_cloud_preview import write_png_rgb8


def _dataset(root, hidden=False):
    for name in ("a", "b"):
        write_png_rgb8(np.zeros((480, 640, 3), np.uint8), root / "images" / "val" / f"{name}.png")
        mask = np.zeros((480, 640), bool)
        if not hidden:
            mask[100:140, 200:260] = True
        (root / "depth" / "val").mkdir(parents=True, exist_ok=True)
        np.savez_compressed(root / "depth" / "val" / f"{name}.npz", depth_mm=np.zeros((480, 640), np.uint16), mask_packed=np.packbits(mask))
        (root / "truth" / "val").mkdir(parents=True, exist_ok=True)
        (root / "truth" / "val" / f"{name}.json").write_text(json.dumps({
            "sample_id": name, "cup_xy": [0.0, -0.28], "cup_hidden": hidden,
            "camera": {"pos": [0.65, -0.65, 0.55], "mat": list(np.eye(3).ravel()), "fovy": 45.0, "width": 640, "height": 480}}))


def test_frames_are_loaded_with_truth_mask_depth_and_camera(tmp_path):
    _dataset(tmp_path)
    frames = cli.load_frames(tmp_path, "val")
    assert [frame["sample_id"] for frame in frames] == ["a", "b"]
    assert frames[0]["truth"].sum() == 40 * 60 and frames[0]["rgb"].shape == (480, 640, 3) and frames[0]["depth"].shape == (480, 640)


def test_the_report_scores_every_set_with_the_given_detector(tmp_path):
    _dataset(tmp_path)
    box = np.zeros((480, 640), bool)
    box[100:140, 200:260] = True
    detector = lambda rgb: [(0.9, box)]          # noqa: E731
    report = cli.evaluate(tmp_path, ["val"], detector, threshold=0.5)
    assert report["sets"]["val"]["summary"]["ok"] == 2 and report["sets"]["val"]["summary"]["success_rate"] == 1.0
    assert [row["sample_id"] for row in report["sets"]["val"]["rows"]] == ["a", "b"]
    assert set(report["sets"]["val"]["groups"]) == {"a", "b"}          # grouped by the draw set in the sample id (val, val_ring, val_negative)


def test_main_writes_the_report_and_refuses_an_existing_one(tmp_path, monkeypatch):
    _dataset(tmp_path / "ds")
    monkeypatch.setattr(cli, "load_detector", lambda **_: (lambda rgb: []))
    out = tmp_path / "report.json"
    argv = ["--weights", "/w.pt", "--dataset-root", str(tmp_path / "ds"), "--sets", "val", "--output", str(out)]
    assert cli.main(argv) == 0
    assert json.loads(out.read_text())["sets"]["val"]["summary"]["missed"] == 2
    with pytest.raises(SystemExit):
        cli.main(argv)
