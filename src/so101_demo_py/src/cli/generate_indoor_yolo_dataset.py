"""Render the indoor YOLO-Seg dataset (goal 11): bright indoor nominal, the appearance library and the old dark nominal, with sim-truth masks.

    python -m so101_demo.cli.generate_indoor_yolo_dataset --output-root /abs/dir --train 1600 --val 300 --test 300 \\
        --eval-indoor-nominal 100 --eval-dark-nominal 100 --train-dark 200

Needs MuJoCo and an offscreen GL (`MUJOCO_GL=osmesa`). The draw plan is a pure function of `--seed` (`act/indoor_yolo_dataset.py`);
a frame whose cup mask shows fewer than `MIN_MASK_PIXELS` pixels is drawn again with a numbered retry, recorded in the truth file.
The tree is the ultralytics layout (`images/<set>`, `labels/<set>`), plus `truth/<set>/<id>.json` for every frame and
`depth/<set>/<id>.npz` (`depth_mm`, uint16, and `mask_packed`, the sim-truth cup mask as `np.packbits`) for every set that is not `train`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from so101_demo.act import indoor_yolo_dataset as dataset
from so101_demo.act import indoor_yolo_render as render
from so101_demo.runtime.point_cloud_preview import write_png_rgb8

MIN_MASK_PIXELS = 150
MAX_REDRAWS = 20
SETS = ("train", "val", "test", *dataset.EXTRA_SETS)


def _absolute(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    return hashlib.sha256(data).hexdigest()


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generate_indoor_yolo_dataset", description=__doc__.split("\n")[0])
    parser.add_argument("--output-root", required=True, type=_absolute)
    parser.add_argument("--seed", type=int, default=dataset.MASTER_SEED)
    parser.add_argument("--act-assets", required=True, type=_absolute, help="the directory holding scene_side_wrist_indoor.xml (assets/mujoco/act)")
    for name in SETS:
        parser.add_argument("--" + name.replace("_", "-"), dest=name, type=int, default=0)
    parsed = parser.parse_args(arguments)
    root = parsed.output_root
    if root.exists():
        parser.error(f"output root exists: {root}")
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    counts = {name: getattr(parsed, name) for name in SETS if getattr(parsed, name)}
    inventories = dataset.layout_inventories(parsed.act_assets)
    assets = dataset.asset_pools(parsed.act_assets)
    plan = dataset.build_plan(counts, parsed.seed, inventories, assets)
    renderer = render.IndoorFrameRenderer(parsed.act_assets, root / "work")
    files, redraws, directories = {}, {}, set()
    try:
        for entry in plan:
            attempt = 0
            while True:
                frame = renderer.render(entry)
                pixels = int(frame.mask.sum())
                if pixels >= MIN_MASK_PIXELS or entry["cup_hidden"]:
                    break
                attempt += 1
                if attempt > MAX_REDRAWS:
                    raise RuntimeError(f"CUP_NOT_VISIBLE: {entry['sample_id']} after {MAX_REDRAWS} redraws")
                entry = dataset.draw_sample(parsed.seed, entry["sample_id"].rsplit("-", 1)[0], entry["index"], inventories, attempt=attempt, assets=assets)
            redraws[entry["sample_id"]] = attempt
            directory, stem = entry["directory"], entry["sample_id"]
            directories.add(directory)
            png = root / "images" / directory / f"{stem}.png"
            write_png_rgb8(frame.rgb, png)
            files[f"images/{directory}/{stem}.png"] = hashlib.sha256(png.read_bytes()).hexdigest()
            line = dataset.label_line(frame.mask)
            files[f"labels/{directory}/{stem}.txt"] = _write(root / "labels" / directory / f"{stem}.txt", (line + "\n").encode())
            truth = {"sample_id": stem, "split": entry["split"], "directory": directory, "layout": entry["layout"], "kind": entry["kind"],
                     "cup_xy": frame.cup_xy, "cup_hidden": entry["cup_hidden"], "cup_family": entry["cup_family"], "cup_rgba": frame.cup_rgba,
                     "realized_sha256": frame.realized_sha256, "mask_pixels": pixels, "camera": frame.camera, "redraws": attempt,
                     "seed": entry["seed"], "variant": entry["variant"]}
            files[f"truth/{directory}/{stem}.json"] = _write(root / "truth" / directory / f"{stem}.json",
                                                             json.dumps(truth, sort_keys=True, indent=1).encode() + b"\n")
            if directory != "train":
                depth_mm = np.clip(np.round(frame.depth * 1000.0), 0, 65535).astype(np.uint16)
                npz = root / "depth" / directory / f"{stem}.npz"
                npz.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(npz, depth_mm=depth_mm, mask_packed=np.packbits(frame.mask))
                files[f"depth/{directory}/{stem}.npz"] = hashlib.sha256(npz.read_bytes()).hexdigest()
        (root / "depth" / "train").mkdir(parents=True, exist_ok=True)
    finally:
        renderer.close()
    files["dataset.yaml"] = _write(root / "dataset.yaml", dataset.dataset_yaml(directories).encode())
    document = dataset.plan_document(plan, counts, parsed.seed)
    manifest = {"schema_version": 1, "kind": "INDOOR_YOLO_SEG_DATASET", "master_seed": parsed.seed, "counts": counts,
                "plan_sha256": document["plan_sha256"], "redraws": {key: value for key, value in redraws.items() if value},
                "min_mask_pixels": MIN_MASK_PIXELS, "split_policy": dataset.SPLIT_POLICY, "region_xy": dataset.REGION_XY,
                "texture_pools": {split: {surface: len(ids) for surface, ids in surfaces.items()} for split, surfaces in assets["pools"].items()},
                "files": dict(sorted(files.items()))}
    (root / "dataset-manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"status": "OK", "output_root": str(root), "frames": len(plan), "plan_sha256": document["plan_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
