#!/usr/bin/env python3
"""Deterministic procedural indoor textures for the SO-101 indoor scene (design 2026-10-24, P1).

Every texture is drawn from numpy / PIL with a fixed per-texture seed, so there is no download and no licence question (the
textures are original, procedural, released under the repository licence). The script writes the PNGs and `manifest.json`
(sha256, size and dimensions of each PNG, the seed, the generator command and the library versions) into the output directory:

    python scripts/assets/gen_indoor_textures.py --out src/so101_demo_py/assets/mujoco/textures/indoor

The PNGs are visual-only inputs of the indoor scene files (`assets/mujoco/act/scene_side_wrist_indoor*.xml`); they never enter
the physics (`act/physics_fingerprint.py`, version 2).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFilter

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "src/so101_demo_py/assets/mujoco/textures/indoor"
OUT = DEFAULT_OUT
N = 512


def rng(seed):
    return np.random.default_rng(seed)


def save(name, arr):
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(OUT / f"{name}.png")


def noise(r, scale, shape=(N, N)):
    small = r.random((max(2, shape[0] // scale), max(2, shape[1] // scale)))
    img = Image.fromarray((small * 255).astype(np.uint8)).resize(shape[::-1], Image.BICUBIC)
    return np.asarray(img, dtype=np.float32) / 255.0


def wood(name, base, seed, planks=4, contrast=24, grain_freq=0.5, vertical_seams=True):
    r = rng(seed)
    y, x = np.mgrid[0:N, 0:N].astype(np.float32)
    img = np.zeros((N, N, 3), np.float32)
    h = N // planks
    for p in range(planks):
        tone = r.uniform(-12, 12)
        off = r.uniform(0, 100)
        rows = slice(p * h, (p + 1) * h)
        g = np.sin((y[rows] * 0.11 + noise(r, 24)[rows] * 14 + off) * grain_freq * 2) * 0.5 + noise(r, 6)[rows] * 0.5
        for c in range(3):
            img[rows, :, c] = base[c] + tone + (g - 0.5) * contrast
        img[p * h:p * h + 2, :, :] *= 0.55      # seam
        if vertical_seams:
            cx = int(r.uniform(0.2, 0.9) * N)
            img[rows, cx:cx + 2, :] *= 0.55
    save(name, img)


def tile(name, base, grout, seed, n=4):
    r = rng(seed)
    img = np.zeros((N, N, 3), np.float32)
    s = N // n
    for i in range(n):
        for j in range(n):
            t = r.uniform(-6, 6)
            img[i * s:(i + 1) * s, j * s:(j + 1) * s] = np.array(base) + t
    img += (noise(r, 4)[..., None] - 0.5) * 10
    for k in range(n):
        img[k * s:k * s + 4, :] = grout
        img[:, k * s:k * s + 4] = grout
    save(name, img)


def parquet(name, base, seed):
    r = rng(seed)
    img = np.zeros((N, N, 3), np.float32)
    s = N // 4
    for i in range(4):
        for j in range(4):
            horiz = (i + j) % 2 == 0
            blk = np.zeros((s, s, 3), np.float32)
            for k in range(4):
                tone = r.uniform(-14, 14)
                yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
                coord = (yy if horiz else xx)
                sl = (coord // (s // 4)) == k
                g = np.sin(((xx if horiz else yy) * 0.2 + r.uniform(0, 9))) * 7
                for c in range(3):
                    blk[..., c] = np.where(sl, base[c] + tone + g, blk[..., c])
            blk[:2, :] *= 0.6
            blk[:, :2] *= 0.6
            img[i * s:(i + 1) * s, j * s:(j + 1) * s] = blk
    save(name, img)


def carpet(name, base, seed):
    r = rng(seed)
    n = (r.random((N, N)) - 0.5) * 26 + (noise(r, 8) - 0.5) * 20
    img = np.array(base, np.float32)[None, None, :] + n[..., None]
    save(name, img)


def plaster(name, base, seed, amp=7):
    r = rng(seed)
    n = (noise(r, 16) - 0.5) * amp * 2 + (r.random((N, N)) - 0.5) * amp
    save(name, np.array(base, np.float32)[None, None, :] + n[..., None])


def laminate(name, base, seed):
    r = rng(seed)
    y, x = np.mgrid[0:N, 0:N].astype(np.float32)
    g = np.sin(x * 0.09 + noise(r, 30) * 9) * 0.5 + noise(r, 4) * 0.5
    save(name, np.array(base, np.float32)[None, None, :] + ((g - 0.5) * 9)[..., None])


def whiteboard(name, seed):
    r = rng(seed)
    im = Image.new("RGB", (N, N), (246, 247, 247))
    d = ImageDraw.Draw(im)
    for _ in range(14):
        c = [(30, 60, 190), (200, 40, 40), (30, 140, 60), (20, 20, 20)][int(r.integers(4))]
        x0, y0 = int(r.integers(30, 400)), int(r.integers(30, 460))
        pts = [(x0 + i * 12, y0 + int(r.integers(-10, 10))) for i in range(int(r.integers(4, 12)))]
        d.line(pts, fill=c, width=3)
    d.rectangle([4, 4, N - 5, N - 5], outline=(190, 190, 195), width=4)
    save(name, np.asarray(im.filter(ImageFilter.GaussianBlur(0.7)), np.float32))


def poster(name, seed):
    r = rng(seed)
    im = Image.new("RGB", (N, N), (236, 232, 220))
    d = ImageDraw.Draw(im)
    for _ in range(9):
        c = tuple(int(v) for v in r.integers(40, 230, 3))
        x0, y0 = int(r.integers(20, 360)), int(r.integers(20, 360))
        w, h = int(r.integers(40, 150)), int(r.integers(40, 150))
        (d.ellipse if r.random() < 0.5 else d.rectangle)([x0, y0, x0 + w, y0 + h], fill=c)
    d.rectangle([0, 0, N - 1, N - 1], outline=(30, 30, 30), width=10)
    save(name, np.asarray(im, np.float32))


def sky(name, seed, warm=False):
    r = rng(seed)
    y = np.linspace(0, 1, N, dtype=np.float32)[:, None, None]
    top = np.array([150, 195, 245] if not warm else [175, 205, 245], np.float32)
    bot = np.array([235, 245, 255] if not warm else [255, 244, 220], np.float32)
    img = top * (1 - y) + bot * y + np.zeros((N, N, 3), np.float32)
    im = Image.fromarray(img.astype(np.uint8))
    d = ImageDraw.Draw(im)
    for _ in range(40):                                  # trees / buildings along the bottom
        x0 = int(r.integers(0, N))
        w = int(r.integers(30, 90))
        h = int(r.integers(40, 150))
        c = (int(r.integers(60, 110)), int(r.integers(110, 170)), int(r.integers(60, 100)))
        d.ellipse([x0, N - h, x0 + w, N + 20], fill=c)
    save(name, np.asarray(im, np.float32))


def metal(name, base, seed):
    r = rng(seed)
    g = (r.random((N, 1)) - 0.5) * 22 + (noise(r, 20) - 0.5) * 10
    save(name, np.array(base, np.float32)[None, None, :] + g[..., None] + 0 * np.zeros((N, N, 3), np.float32))


def cardboard(name, seed):
    r = rng(seed)
    y, x = np.mgrid[0:N, 0:N].astype(np.float32)
    save(name, np.array([190, 150, 100], np.float32)[None, None, :] + ((np.sin(y * 0.5) * 6 + (noise(r, 6) - 0.5) * 18))[..., None])


#: (name, function, positional arguments before the seed, seed, keyword arguments); the order is the order of the manifest
TEXTURES = (
    ("floor_wood_light", wood, ((205, 165, 115),), 1, {"planks": 6, "contrast": 26}),
    ("cabinet_wood", wood, ((170, 125, 80),), 2, {"planks": 2, "contrast": 22, "vertical_seams": False}),
    ("floor_tile_grey", tile, ((170, 175, 180), (110, 115, 120)), 3, {"n": 4}),
    ("floor_parquet", parquet, ((185, 135, 85),), 4, {}),
    ("floor_carpet", carpet, ((190, 175, 150),), 5, {}),
    ("wall_white", plaster, ((236, 236, 232),), 6, {"amp": 5}),
    ("wall_grey", plaster, ((150, 155, 160),), 7, {"amp": 6}),
    ("wall_beige", plaster, ((218, 200, 170),), 8, {"amp": 6}),
    ("ceiling_white", plaster, ((240, 240, 238),), 9, {"amp": 3}),
    ("table_laminate", laminate, ((205, 196, 178),), 10, {}),
    ("whiteboard", whiteboard, (), 11, {}),
    ("poster", poster, (), 12, {}),
    ("outside_cool", sky, (), 13, {}),
    ("outside_warm", sky, (), 14, {"warm": True}),
    ("metal_shelf", metal, ((150, 155, 160),), 15, {}),
    ("cardboard", cardboard, (), 16, {}),
)


def generate(out: Path) -> dict:
    """Write every PNG and `manifest.json` into `out`; return the manifest."""
    global OUT
    OUT = Path(out)
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, function, args, seed, kwargs in TEXTURES:
        function(name, *args, seed, **kwargs)
        path = OUT / f"{name}.png"
        data = path.read_bytes()
        with Image.open(path) as image:
            width, height = image.size
        entries.append({"file": f"{name}.png", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "width": width,
                        "height": height, "generator": function.__name__, "seed": seed})
    manifest = {
        "kind": "SO101_INDOOR_TEXTURE_MANIFEST", "schema_version": 1,
        "generator": "scripts/assets/gen_indoor_textures.py",
        "command": "python scripts/assets/gen_indoor_textures.py --out src/so101_demo_py/assets/mujoco/textures/indoor",
        "source": "procedural (numpy + PIL, fixed seeds); no downloaded image", "licence": "original work, repository licence",
        "generated_with": {"numpy": np.__version__, "pillow": PIL.__version__},
        "textures": entries}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    arguments = parser.parse_args(argv)
    manifest = generate(arguments.out)
    print(f"{len(manifest['textures'])} textures in {arguments.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
