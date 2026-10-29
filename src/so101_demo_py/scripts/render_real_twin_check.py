#!/usr/bin/env python3
"""Render the cameras of the real-twin scene next to the human's real photos and write a contact sheet.

    MUJOCO_GL=egl python render_real_twin_check.py OUT_DIR [--photos PHOTO_DIR] [--frames FRAME_DIR]

Renders (PNG, one file each): the side camera and the wrist camera at q = 0 (task_start), the wrist camera at the
folded rest pose, and the three overview cameras placed like the human's back, left and front photos. The contact sheet
puts each render beside the real image where one is comparable. The real side frame was taken with an earlier camera
mount and the real wrist frame at the folded rest pose, so they are shown only as a reference.
"""

import argparse
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCENE = PACKAGE_ROOT / "assets/mujoco/real_twin/scene_real_twin_cube_bowl.xml"


def render(model, data, camera: str) -> np.ndarray:
    width, height = (int(v) for v in model.cam_resolution[model.camera(camera).id])
    renderer = mujoco.Renderer(model, height=height, width=width)
    try:
        renderer.update_scene(data, camera=camera)
        return renderer.render().copy()
    finally:
        renderer.close()


def _labelled(image: Image.Image, text: str, height: int) -> Image.Image:
    scale = height / image.height
    image = image.resize((max(1, round(image.width * scale)), height))
    canvas = Image.new("RGB", (image.width, height + 16), "white")
    canvas.paste(image, (0, 16))
    ImageDraw.Draw(canvas).text((3, 2), text, fill="black")
    return canvas


def _row(items: list[tuple[str, Image.Image]], height: int) -> Image.Image:
    cells = [_labelled(image, text, height) for text, image in items]
    row = Image.new("RGB", (sum(c.width for c in cells) + 6 * (len(cells) - 1), height + 16), "white")
    x = 0
    for cell in cells:
        row.paste(cell, (x, 0))
        x += cell.width + 6
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--photos", type=Path, default=None, help="directory with view-back.png, view-left.png, view-front.png")
    parser.add_argument("--frames", type=Path, default=None, help="directory with the real side.png and wrist.png")
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, model.key("task_start").id)
    mujoco.mj_forward(model, data)
    shots: dict[str, np.ndarray] = {}
    for name in ("side_camera", "wrist_camera", "view_back", "view_left", "view_front"):
        shots[name if name != "side_camera" and name != "wrist_camera" else name + "_q0"] = render(model, data, name)
    mujoco.mj_resetDataKeyframe(model, data, model.key("rest_pose").id)
    mujoco.mj_forward(model, data)
    shots["wrist_camera_rest"] = render(model, data, "wrist_camera")
    shots["view_front_rest"] = render(model, data, "view_front")
    shots["view_back_rest"] = render(model, data, "view_back")
    for name, image in shots.items():
        Image.fromarray(image).save(args.out_dir / f"{name}.png")

    def real(directory: Path | None, name: str) -> Image.Image | None:
        if directory is None or not (directory / name).is_file():
            return None
        return Image.open(directory / name).convert("RGB")

    rows = []
    for view in ("view_back", "view_left", "view_front"):
        items = [(f"sim {view}", Image.fromarray(shots[view]))]
        photo = real(args.photos, view.replace("_", "-") + ".png")
        if photo is not None:
            items.append((f"real photo {view.replace('_', '-')}", photo))
        rows.append(_row(items, 520))
    side = [("sim side_camera (q=0)", Image.fromarray(shots["side_camera_q0"]))]
    side_real = real(args.frames, "side.png")
    if side_real is not None:
        side.append(("real side frame (earlier mount, reference only)", side_real))
    wrist = [
        ("sim wrist q=0", Image.fromarray(shots["wrist_camera_q0"])),
        ("sim wrist rest pose", Image.fromarray(shots["wrist_camera_rest"])),
    ]
    wrist_real = real(args.frames, "wrist.png")
    if wrist_real is not None:
        wrist.append(("real wrist frame (folded rest)", wrist_real))
    rows.append(_row(side + wrist, 300))
    width = max(r.width for r in rows)
    sheet = Image.new("RGB", (width, sum(r.height for r in rows) + 6 * len(rows)), "white")
    y = 0
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height + 6
    sheet.save(args.out_dir / "contact-sheet.png")
    print(args.out_dir / "contact-sheet.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
