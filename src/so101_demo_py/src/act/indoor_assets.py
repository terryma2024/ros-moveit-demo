"""Indoor appearance asset pools: parametric procedural textures, CC0 textures, continuous cup colour, and the split of every asset by identity.

This module is standalone (standard library, plus numpy and PIL inside the renderers only; it imports nothing of `so101_demo`), so the
mount-tree build can load it by file path before the package exists, and `scene_variant` can validate texture names without numpy.

Textures (indoor scene design 2026-10-24, P3 appearance library)
  legacy   the 16 committed PNGs of P1 (`assets/mujoco/textures/indoor/*.png`, `scripts/assets/gen_indoor_textures.py`); unchanged
  proc     `proc/<family>_<NNN>`: 8 families x `PER_FAMILY` textures, each a pure function of (family, index): the parameters come from a
           seeded `random.Random`, the pixels from a seeded numpy `Generator`. The PNGs are NOT in git; `proc-manifest.json` is: the
           parameters, the seed, the sha256 of the decoded pixels and of the PNG bytes of every texture. The mount-tree build writes the PNGs into
           the install tree and fails unless every decoded-pixel sha256 equals the manifest (the pixel hash is the identity: the PNG bytes also
           depend on the zlib build, so the PNG hash is checked as well and a difference alone is reported, not fatal, by `verify_directory`)
  cc0      `cc0/<surface>_<slug>`: albedo maps of CC0 sources (Poly Haven, ambientCG), resized to 512 px; `cc0-manifest.json` is in git
           (source URL, asset id, licence, date, sha256 before and after resizing); the files are a separately hashed pack

Every texture has an eligible surface set (wall, floor, table) fixed by its family or its `cc0/<surface>_` prefix, and a split (train,
val, test) fixed by `split_of`: a deterministic, seeded, disjoint three-way assignment per group, so no asset of train is in val or test.
Cup colour is continuous: a hue band (of `HUE_BANDS`) belongs to one split, and a draw takes a hue in a band of its split, then a
saturation and a value, and is redrawn until it is clearly different (OKLab distance) from the drawn wall, floor and table and from the red
landing ring.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import random
import re
from pathlib import Path

MASTER_SEED = 20261025
SIZE = 512
PER_FAMILY = 104
PROC_FAMILIES = ("wood", "parquet", "tile", "fabric", "plaster", "laminate", "concrete", "wallpaper")
#: the surfaces a family may cover (wall, floor, table)
FAMILY_SURFACES = {
    "wood": ("floor", "table"), "parquet": ("floor", "table"), "tile": ("floor", "table", "wall"), "fabric": ("floor", "wall"),
    "plaster": ("wall",), "laminate": ("floor", "table"), "concrete": ("wall", "floor", "table"), "wallpaper": ("wall",)}
SURFACES = ("wall", "floor", "table")
SPLITS = ("train", "val", "test")
SPLIT_FRACTIONS = {"val": 0.15, "test": 0.15}            # the rest is train
#: the legacy textures, by surface (the lists of `scene_variant` before the pools) and their fixed split: held-out ones keep out of train
LEGACY = {
    "wall": ("wall_white", "wall_grey", "wall_beige"),
    "floor": ("floor_wood_light", "floor_tile_grey", "floor_parquet", "floor_carpet"),
    "table": ("table_laminate", "cabinet_wood", "floor_wood_light", "floor_parquet", "metal_shelf")}
LEGACY_SPLIT = {"wall_white": "train", "wall_grey": "train", "wall_beige": "val", "floor_wood_light": "train", "floor_tile_grey": "train",
                "floor_carpet": "train", "floor_parquet": "val", "table_laminate": "train", "cabinet_wood": "train", "metal_shelf": "train"}
PROC_MANIFEST = "proc-manifest.json"
CC0_MANIFEST = "cc0-manifest.json"
PROC_DIRECTORY = "proc"
CC0_DIRECTORY = "cc0"

_PROC_ID = re.compile(r"proc/([a-z]+)_(\d{3})\Z")
_CC0_ID = re.compile(r"cc0/(wall|floor|table)_([a-z0-9_]{1,60})\Z")
_LEGACY_ID = re.compile(r"[a-z][a-z0-9_]*\Z")


# ----------------------------------------------------------------------------------------------------------------------------------------
# texture names

def proc_id(family: str, index: int) -> str:
    if family not in PROC_FAMILIES or not 0 <= index < PER_FAMILY:
        raise ValueError(f"INDOOR_TEXTURE_UNKNOWN: {family} {index}")
    return f"{PROC_DIRECTORY}/{family}_{index:03d}"


def all_proc_ids() -> list:
    return [proc_id(family, index) for family in PROC_FAMILIES for index in range(PER_FAMILY)]


def texture_surfaces(texture: str) -> tuple:
    """The surfaces a texture name may cover, or `()` for a name outside the pools. The name alone decides (no file is read)."""
    match = _PROC_ID.fullmatch(texture)
    if match:
        family, index = match.group(1), int(match.group(2))
        return FAMILY_SURFACES[family] if family in FAMILY_SURFACES and index < PER_FAMILY else ()
    match = _CC0_ID.fullmatch(texture)
    if match:
        return (match.group(1),)
    return tuple(surface for surface in SURFACES if texture in LEGACY[surface])


def texture_allowed(surface: str, texture: str) -> bool:
    return surface in texture_surfaces(texture)


def texture_file(texture: str) -> str:
    """The path of a texture under `assets/mujoco/textures/indoor`."""
    if not texture_surfaces(texture):
        raise ValueError(f"INDOOR_TEXTURE_UNKNOWN: {texture}")
    return f"{texture}.png"


# ----------------------------------------------------------------------------------------------------------------------------------------
# colour: sRGB <-> OKLab (Bjorn Ottosson), distance in OKLab

def _lin(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _gamma(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def srgb_to_oklab(rgb) -> tuple:
    r, g, b = (_lin(float(value)) for value in rgb[:3])
    l = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def oklab_to_srgb(lab) -> tuple:
    big_l, a, b = lab
    l = (big_l + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (big_l - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (big_l - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (_gamma(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s), _gamma(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
            _gamma(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s))


def oklch_to_srgb(lightness: float, chroma: float, hue_deg: float) -> tuple:
    hue = math.radians(hue_deg)
    return oklab_to_srgb((lightness, chroma * math.cos(hue), chroma * math.sin(hue)))


def delta_e(rgb_a, rgb_b) -> float:
    """The OKLab distance of two sRGB colours (0 to 1 scale; 0.02 is about one just-noticeable difference)."""
    return math.dist(srgb_to_oklab(rgb_a), srgb_to_oklab(rgb_b))


# ----------------------------------------------------------------------------------------------------------------------------------------
# parametric procedural families

def _seed_int(name: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{MASTER_SEED}/{name}".encode()).digest()[:4], "big")


def _round(value, digits=4):
    return round(value, digits)


def _colour(rng: random.Random, lightness, chroma, hue) -> list:
    """A base colour drawn in OKLCH, stored as the sRGB triple (0 to 255, rounded to 0.1)."""
    return [_round(255 * channel, 1) for channel in oklch_to_srgb(rng.uniform(*lightness), rng.uniform(*chroma), rng.uniform(*hue))]


def proc_params(family: str, index: int) -> dict:
    """The parameters of one texture: a pure function of (family, index). Every family has a base colour (`base`, sRGB 0..255, drawn in
    OKLCH), a `scale`, an `orientation` (quarter turns), a `contrast`, a `wear` (noise amplitude), a `seed` for the pixel noise, and its own
    parameters (`grout` colour and width, `planks`, `motif`, ...)."""
    name = proc_id(family, index)
    rng = random.Random(f"{MASTER_SEED}/params/{name}")
    p = {"family": family, "seed": _seed_int(name), "orientation": rng.choice((0, 1, 2, 3)), "wear": _round(rng.uniform(0.0, 1.0), 3)}
    if family == "wood":
        p.update(base=_colour(rng, (0.38, 0.84), (0.035, 0.13), (45, 80)), planks=rng.randint(2, 10), contrast=_round(rng.uniform(10, 40), 2),
                 grain=_round(rng.uniform(0.25, 1.0), 3), seams=rng.random() < 0.8, scale=rng.randint(10, 40))
    elif family == "parquet":
        p.update(base=_colour(rng, (0.40, 0.80), (0.04, 0.12), (45, 80)), blocks=rng.randint(3, 8), strips=rng.randint(3, 6),
                 contrast=_round(rng.uniform(8, 28), 2), pattern=rng.choice(("basket", "stripes")), scale=rng.randint(10, 40))
    elif family == "tile":
        p.update(base=_colour(rng, (0.35, 0.92), (0.0, 0.10), (0, 360)), grout=_colour(rng, (0.30, 0.85), (0.0, 0.04), (0, 360)),
                 tiles=rng.randint(2, 9), grout_px=rng.randint(2, 9), jitter=_round(rng.uniform(2, 14), 2), bond=rng.choice(("grid", "running")),
                 speckle=_round(rng.uniform(0, 12), 2), scale=rng.randint(4, 30))
    elif family == "fabric":
        p.update(base=_colour(rng, (0.30, 0.85), (0.0, 0.14), (0, 360)), weave=rng.randint(2, 7), kind=rng.choice(("plain", "twill", "loop")),
                 contrast=_round(rng.uniform(8, 30), 2), scale=rng.randint(4, 20))
    elif family == "plaster":
        p.update(base=_colour(rng, (0.58, 0.97), (0.0, 0.07), (0, 360)), amp=_round(rng.uniform(2, 11), 2), scale=rng.randint(8, 40),
                 contrast=_round(rng.uniform(0.0, 1.0), 3))
    elif family == "laminate":
        p.update(base=_colour(rng, (0.50, 0.92), (0.0, 0.08), (30, 100)), grain=_round(rng.uniform(0.2, 1.0), 3),
                 contrast=_round(rng.uniform(4, 16), 2), planks=rng.choice((1, 1, 2, 3, 4)), scale=rng.randint(8, 40))
    elif family == "concrete":
        p.update(base=_colour(rng, (0.35, 0.80), (0.0, 0.02), (0, 360)), blotch=_round(rng.uniform(6, 26), 2), pores=rng.randint(40, 600),
                 contrast=_round(rng.uniform(0.0, 1.0), 3), scale=rng.randint(10, 60))
    elif family == "wallpaper":
        p.update(base=_colour(rng, (0.50, 0.95), (0.0, 0.10), (0, 360)), motif_colour=_colour(rng, (0.35, 0.90), (0.02, 0.14), (0, 360)),
                 motif=rng.choice(("stripes", "dots", "diamonds", "grid")), repeat=rng.randint(3, 12), contrast=_round(rng.uniform(0.2, 1.0), 3))
    else:
        raise ValueError(f"INDOOR_TEXTURE_UNKNOWN: {family}")
    return p


def _noise(gen, scale: int, shape=(SIZE, SIZE)):
    import numpy as np
    from PIL import Image

    small = gen.random((max(2, shape[0] // scale), max(2, shape[1] // scale)))
    image = Image.fromarray((small * 255).astype(np.uint8)).resize(shape[::-1], Image.BICUBIC)
    return np.asarray(image, dtype=np.float32) / 255.0


def _fbm(gen, scale: int):
    """Three octaves of upsampled noise in [0, 1] (the scale of the coarsest)."""
    return 0.55 * _noise(gen, scale) + 0.3 * _noise(gen, max(2, scale // 2)) + 0.15 * _noise(gen, max(2, scale // 4))


def _fill(base, field):
    """`base` (3 values) plus the 2-D `field` (grey levels) on every channel."""
    import numpy as np

    return np.asarray(base, np.float32)[None, None, :] + field[..., None]


def _wood(p, gen):
    import numpy as np

    y, _x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    img = np.zeros((SIZE, SIZE, 3), np.float32)
    height = SIZE // p["planks"]
    for plank in range(p["planks"]):
        rows = slice(plank * height, SIZE if plank == p["planks"] - 1 else (plank + 1) * height)
        tone = gen.uniform(-12, 12)
        offset = gen.uniform(0, 100)
        wave = np.sin((y[rows] * 0.11 + _noise(gen, p["scale"])[rows] * 14 + offset) * p["grain"] * 4) * 0.5 + _noise(gen, 6)[rows] * 0.5
        img[rows] = np.asarray(p["base"], np.float32)[None, None, :] + (tone + (wave - 0.5) * p["contrast"])[..., None]
        if p["seams"]:
            img[rows.start:rows.start + 2] *= 0.55
            cx = int(gen.uniform(0.2, 0.9) * SIZE)
            img[rows, cx:cx + 2] *= 0.6
    img += ((_noise(gen, 3) - 0.5) * 8 * p["wear"])[..., None]
    return img


def _parquet(p, gen):
    import numpy as np

    img = np.zeros((SIZE, SIZE, 3), np.float32)
    block = SIZE // p["blocks"]
    for i in range(p["blocks"]):
        for j in range(p["blocks"]):
            rows, cols = slice(i * block, (i + 1) * block), slice(j * block, (j + 1) * block)
            horizontal = (i + j) % 2 == 0 if p["pattern"] == "basket" else True
            yy, xx = np.mgrid[0:block, 0:block].astype(np.float32)
            coordinate, along = (yy, xx) if horizontal else (xx, yy)
            strip = (coordinate // max(1, block // p["strips"])).astype(np.int32)
            tones = np.asarray([gen.uniform(-p["contrast"], p["contrast"]) for _ in range(p["strips"] + 1)], np.float32)
            field = tones[np.minimum(strip, p["strips"])] + np.sin(along * 0.2 + gen.uniform(0, 9)) * 6
            tile = np.asarray(p["base"], np.float32)[None, None, :] + field[..., None]
            tile[:2] *= 0.6
            tile[:, :2] *= 0.6
            img[rows, cols] = tile
    img += ((_noise(gen, 3) - 0.5) * 6 * p["wear"])[..., None]
    return img


def _tile(p, gen):
    import numpy as np

    n = p["tiles"]
    size = SIZE / n
    img = np.zeros((SIZE, SIZE, 3), np.float32)
    for i in range(n + 1):
        shift = size / 2 if p["bond"] == "running" and i % 2 else 0.0
        for j in range(-1, n + 1):
            y0, y1 = int(i * size), int((i + 1) * size)
            x0, x1 = int(j * size + shift), int((j + 1) * size + shift)
            img[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = np.asarray(p["base"], np.float32) + gen.uniform(-p["jitter"], p["jitter"])
    img += ((_noise(gen, p["scale"]) - 0.5) * 12)[..., None] + ((gen.random((SIZE, SIZE)) - 0.5) * p["speckle"])[..., None]
    mask = np.zeros((SIZE, SIZE), bool)
    for i in range(n + 1):
        y = int(i * size)
        mask[max(0, y - p["grout_px"] // 2):y + (p["grout_px"] + 1) // 2] = True
        if p["bond"] == "grid":
            mask[:, max(0, y - p["grout_px"] // 2):y + (p["grout_px"] + 1) // 2] = True
        else:
            for row in range(n):
                shift = size / 2 if row % 2 else 0.0
                for j in range(-1, n + 1):
                    x = int(j * size + shift)
                    if 0 <= x < SIZE:
                        mask[int(row * size):int((row + 1) * size), max(0, x - p["grout_px"] // 2):x + (p["grout_px"] + 1) // 2] = True
    img[mask] = np.asarray(p["grout"], np.float32)
    return img


def _fabric(p, gen):
    import numpy as np

    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    period = float(p["weave"] * 2)
    if p["kind"] == "plain":
        field = (np.sin(x * 2 * math.pi / period) * np.sin(y * 2 * math.pi / period)) * p["contrast"] * 0.5
    elif p["kind"] == "twill":
        field = np.sin((x + y) * 2 * math.pi / period) * p["contrast"] * 0.5
    else:
        field = (gen.random((SIZE, SIZE)) - 0.5) * p["contrast"] * 1.6 + (_noise(gen, p["scale"]) - 0.5) * p["contrast"]
    field = field + (_noise(gen, p["scale"]) - 0.5) * p["contrast"] * 0.6 * p["wear"]
    return _fill(p["base"], field)


def _plaster(p, gen):
    field = (_fbm(gen, p["scale"]) - 0.5) * p["amp"] * 2 * (0.4 + 0.6 * p["contrast"]) + (gen.random((SIZE, SIZE)) - 0.5) * p["amp"]
    return _fill(p["base"], field.astype("float32"))


def _laminate(p, gen):
    import numpy as np

    _y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    grain = np.sin(x * 0.09 * (0.5 + p["grain"]) + _noise(gen, p["scale"]) * 9) * 0.5 + _noise(gen, 4) * 0.5
    img = _fill(p["base"], (grain - 0.5) * p["contrast"] * 1.6)
    if p["planks"] > 1:
        height = SIZE // p["planks"]
        for plank in range(p["planks"]):
            img[plank * height:(plank + 1) * height] += gen.uniform(-5, 5)
            img[plank * height:plank * height + 2] *= 0.6
    img += ((_noise(gen, 3) - 0.5) * 6 * p["wear"])[..., None]
    return img


def _concrete(p, gen):
    import numpy as np

    field = (_fbm(gen, p["scale"]) - 0.5) * p["blotch"] * (0.5 + p["contrast"]) + (gen.random((SIZE, SIZE)) - 0.5) * 5
    img = _fill(p["base"], field.astype(np.float32))
    for _ in range(p["pores"]):
        cy, cx = int(gen.integers(0, SIZE)), int(gen.integers(0, SIZE))
        radius = int(gen.integers(1, 3))
        img[max(0, cy - radius):cy + radius, max(0, cx - radius):cx + radius] *= 0.62
    return img


def _wallpaper(p, gen):
    import numpy as np

    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    period = SIZE / p["repeat"]
    u, v = (x % period) / period, (y % period) / period
    if p["motif"] == "stripes":
        mask = (np.abs(u - 0.5) < 0.18).astype(np.float32)
    elif p["motif"] == "dots":
        mask = (np.hypot(u - 0.5, v - 0.5) < 0.22).astype(np.float32)
    elif p["motif"] == "diamonds":
        mask = ((np.abs(u - 0.5) + np.abs(v - 0.5)) < 0.30).astype(np.float32)
    else:
        mask = ((np.abs(u - 0.5) < 0.06) | (np.abs(v - 0.5) < 0.06)).astype(np.float32)
    mix = (mask * p["contrast"])[..., None]
    img = np.asarray(p["base"], np.float32)[None, None, :] * (1 - mix) + np.asarray(p["motif_colour"], np.float32)[None, None, :] * mix
    img += ((_noise(gen, 12) - 0.5) * 6 + (gen.random((SIZE, SIZE)) - 0.5) * 3 * p["wear"])[..., None]
    return img


_RENDERERS = {"wood": _wood, "parquet": _parquet, "tile": _tile, "fabric": _fabric, "plaster": _plaster, "laminate": _laminate,
              "concrete": _concrete, "wallpaper": _wallpaper}


def render_texture(params: dict):
    """The pixels (uint8, SIZE x SIZE x 3) of a texture from its parameters; deterministic."""
    import numpy as np

    gen = np.random.default_rng(params["seed"])
    img = _RENDERERS[params["family"]](params, gen)
    img = np.clip(np.rint(img), 0, 255).astype(np.uint8)
    return np.ascontiguousarray(np.rot90(img, params["orientation"]))


def png_bytes(pixels) -> bytes:
    """Deterministic PNG bytes of an RGB array (fixed compression level, no metadata)."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(pixels, "RGB").save(buffer, format="PNG", compress_level=6, optimize=False)
    return buffer.getvalue()


def pixel_sha256(pixels) -> str:
    return hashlib.sha256(pixels.tobytes()).hexdigest()


def mean_srgb(pixels) -> list:
    return [round(float(value) / 255.0, 4) for value in pixels.reshape(-1, 3).mean(axis=0)]


def texture_entry(family: str, index: int) -> tuple:
    """`(manifest entry, pixels)` of one procedural texture."""
    params = proc_params(family, index)
    pixels = render_texture(params)
    data = png_bytes(pixels)
    entry = {"id": proc_id(family, index), "family": family, "index": index, "seed": params["seed"], "params": params,
             "pixel_sha256": pixel_sha256(pixels), "png_sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
             "mean_rgb": mean_srgb(pixels)}
    return entry, pixels


def build_proc_manifest(ids=None, progress=None) -> dict:
    """The manifest of the procedural pool (all of it, or just `ids`); the committed `proc-manifest.json` is the full one."""
    import numpy as np
    import PIL

    wanted = set(ids) if ids is not None else None
    entries = []
    for family in PROC_FAMILIES:
        for index in range(PER_FAMILY):
            if wanted is not None and proc_id(family, index) not in wanted:
                continue
            entry, _pixels = texture_entry(family, index)
            entries.append(entry)
            if progress:
                progress(entry["id"])
    return {"kind": "SO101_INDOOR_PROC_TEXTURE_MANIFEST", "schema_version": 1, "master_seed": MASTER_SEED, "size": SIZE,
            "per_family": PER_FAMILY, "families": list(PROC_FAMILIES), "family_surfaces": {k: list(v) for k, v in FAMILY_SURFACES.items()},
            "generator": "scripts/assets/gen_indoor_textures.py --procedural (act/indoor_assets.py)",
            "generated_with": {"numpy": np.__version__, "pillow": PIL.__version__}, "textures": entries}


def load_manifest(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_manifest(path, manifest: dict) -> None:
    Path(path).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def materialize(manifest: dict, out_dir, ids=None) -> list:
    """Write the PNG of every manifest texture (or just `ids`) under `out_dir/proc/`, and raise unless each decoded pixel hash equals
    the manifest's. Returns the ids written. The PNG byte hash is checked by `verify_directory`."""
    out = Path(out_dir) / PROC_DIRECTORY
    out.mkdir(parents=True, exist_ok=True)
    wanted = set(ids) if ids is not None else None
    written = []
    for entry in manifest["textures"]:
        if wanted is not None and entry["id"] not in wanted:
            continue
        pixels = render_texture(entry["params"])
        if pixel_sha256(pixels) != entry["pixel_sha256"]:
            raise ValueError(f"INDOOR_TEXTURE_NOT_REPRODUCED: {entry['id']}: pixel sha256 differs from the manifest")
        (out / (entry["id"].split("/", 1)[1] + ".png")).write_bytes(png_bytes(pixels))
        written.append(entry["id"])
    return written


def verify_directory(manifest: dict, textures_dir, ids=None) -> dict:
    """Compare the PNG files under `textures_dir` with the manifest (PNG sha256 and decoded pixel sha256).

    Returns `{"missing": [...], "png_differs": [...], "pixels_differ": [...], "checked": n}`; a clean install has the first and third empty,
    and the second empty on the toolchain that wrote the manifest."""
    import numpy as np
    from PIL import Image

    wanted = set(ids) if ids is not None else None
    result = {"missing": [], "png_differs": [], "pixels_differ": [], "checked": 0}
    for entry in manifest["textures"]:
        if wanted is not None and entry["id"] not in wanted:
            continue
        path = Path(textures_dir) / (entry["id"] + ".png")
        if not path.is_file():
            result["missing"].append(entry["id"])
            continue
        result["checked"] += 1
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["png_sha256"]:
            result["png_differs"].append(entry["id"])
        with Image.open(path) as image:
            pixels = np.asarray(image.convert("RGB"))
        if pixel_sha256(np.ascontiguousarray(pixels)) != entry["pixel_sha256"]:
            result["pixels_differ"].append(entry["id"])
    return result


# ----------------------------------------------------------------------------------------------------------------------------------------
# splits by asset identity

def split_groups(proc_manifest: dict | None = None, cc0_manifest: dict | None = None) -> dict:
    """`{group: [texture id, ...]}`: one group per procedural family and one per (cc0 surface); ids sorted. The legacy textures are
    fixed by `LEGACY_SPLIT` and not in a group. Without a manifest the procedural ids are the full `PER_FAMILY` set."""
    groups = {}
    for family in PROC_FAMILIES:
        groups[f"proc/{family}"] = [proc_id(family, index) for index in range(PER_FAMILY)]
    for entry in (cc0_manifest or {}).get("textures", []):
        groups.setdefault(f"cc0/{entry['surface']}", []).append(entry["id"])
    return {group: sorted(ids) for group, ids in sorted(groups.items())}


def split_assignment(groups: dict, seed: int = MASTER_SEED) -> dict:
    """`{texture id: split}` for every id of `groups`: per group, a seeded shuffle, then `val` and `test` get `SPLIT_FRACTIONS` of the
    group (at least one each when the group has three or more), the rest is `train`. Disjoint by construction; deterministic."""
    assignment = {}
    for group, ids in groups.items():
        ordered = sorted(ids)
        random.Random(f"{seed}/split/{group}").shuffle(ordered)
        count = len(ordered)
        n_val = max(1, round(count * SPLIT_FRACTIONS["val"])) if count >= 3 else 0
        n_test = max(1, round(count * SPLIT_FRACTIONS["test"])) if count >= 3 else 0
        for position, texture in enumerate(ordered):
            assignment[texture] = "val" if position < n_val else "test" if position < n_val + n_test else "train"
    return assignment


_POOL_CACHE: dict = {}


def texture_pools(proc_manifest: dict | None = None, cc0_manifest: dict | None = None, seed: int = MASTER_SEED) -> dict:
    """`{split: {surface: [texture id, ...]}}`, each list sorted and each id in exactly one split."""
    key = (seed, tuple(sorted(entry["id"] for entry in (cc0_manifest or {}).get("textures", []))))
    if key not in _POOL_CACHE:           # the assignment depends on the ids only (the procedural ids are the full set whatever the manifest)
        assignment = split_assignment(split_groups(proc_manifest, cc0_manifest), seed)
        assignment.update(LEGACY_SPLIT)
        pools = {split: {surface: [] for surface in SURFACES} for split in SPLITS}
        for texture, split in sorted(assignment.items()):
            for surface in texture_surfaces(texture):
                pools[split][surface].append(texture)
        _POOL_CACHE[key] = pools
    return {split: {surface: list(ids) for surface, ids in surfaces.items()} for split, surfaces in _POOL_CACHE[key].items()}


#: the legacy textures that are the validation and test textures of the indoor YOLO fine-tune: never in a train pool (`LEGACY_SPLIT` keeps them in val)
HELD_OUT_LEGACY_TEXTURES = ("wall_beige", "floor_parquet")


def check_held_out_outside_train(pools: dict | None = None) -> None:
    """Raise `ValueError` unless no held-out legacy texture and no held-out cup hue band is in train, and the three splits share nothing."""
    pools = pools or texture_pools()
    owned = {split: {texture for ids in pools[split].values() for texture in ids} for split in SPLITS}
    if owned["train"] & set(HELD_OUT_LEGACY_TEXTURES):
        raise ValueError("HELD_OUT_TEXTURE_IN_TRAIN")
    if set(hue_bands("train")) & set(held_out_hue_bands()):
        raise ValueError("HELD_OUT_HUE_BAND_IN_TRAIN")
    for first, second in (("train", "val"), ("train", "test"), ("val", "test")):
        if owned[first] & owned[second]:
            raise ValueError(f"SPLIT_TEXTURE_SHARED: {first} and {second}")


def split_assignment_sha256(proc_manifest: dict | None = None, cc0_manifest: dict | None = None, seed: int = MASTER_SEED) -> str:
    """The identity of the whole assignment: every texture's split (legacy and held-out moves included) and every hue band's split."""
    pools = texture_pools(proc_manifest, cc0_manifest, seed)
    document = {"seed": seed, "textures": {split: {surface: pools[split][surface] for surface in SURFACES} for split in SPLITS},
                "hue_bands": {split: hue_bands(split, seed) for split in SPLITS}}
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def cup_rule_sha256() -> str:
    """The identity of the cup colour rule: what a draw's cup colour depends on besides the hue bands."""
    document = {"hue_band_count": HUE_BAND_COUNT, "saturation": SATURATION, "value": VALUE, "min_delta_e": MIN_DELTA_E,
                "landing_ring_rgb": LANDING_RING_RGB, "attempts": CUP_ATTEMPTS}
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def split_of(texture: str, proc_manifest: dict | None = None, cc0_manifest: dict | None = None, seed: int = MASTER_SEED) -> str:
    pools = texture_pools(proc_manifest, cc0_manifest, seed)
    for split in SPLITS:
        if any(texture in ids for ids in pools[split].values()):
            return split
    raise ValueError(f"INDOOR_TEXTURE_UNKNOWN: {texture}")


# ----------------------------------------------------------------------------------------------------------------------------------------
# continuous cup colour

HUE_BAND_COUNT = 36                                   # bands of 10 degrees
SATURATION = (0.55, 1.0)
VALUE = (0.55, 1.0)
#: the red target landing ring and the nominal cup (visual colours of the indoor scene); a cup colour must stay clearly different from the ring
LANDING_RING_RGB = (0.80, 0.10, 0.10)
MIN_DELTA_E = {"wall": 0.12, "floor": 0.08, "table": 0.15, "ring": 0.15}
CUP_ATTEMPTS = 64


def hue_band_split(band: int, seed: int = MASTER_SEED) -> str:
    """The split of one hue band (of `HUE_BAND_COUNT`): a seeded, disjoint three-way assignment of the bands."""
    return _hue_assignment(seed)[band]


#: the base colours of the cup families of the P3 appearance plan and of the indoor YOLO fine-tune; each draw of the old plan jittered every
#: channel by +-`CUP_JITTER`. Blue, purple, green and teal were the fine-tune's validation and test cups: `HELD_OUT_CUP_FAMILIES`.
CUP_FAMILY_BASES = {
    "orange": (1.0, 0.55, 0.12), "red": (0.85, 0.10, 0.10), "yellow": (0.95, 0.85, 0.15), "magenta": (0.85, 0.15, 0.60),
    "blue": (0.15, 0.30, 0.85), "purple": (0.50, 0.20, 0.70), "green": (0.20, 0.70, 0.25), "teal": (0.10, 0.65, 0.65)}
CUP_JITTER = 0.06
HELD_OUT_CUP_FAMILIES = ("blue", "purple", "green", "teal")


@functools.lru_cache(maxsize=None)
def held_out_hue_bands() -> tuple:
    """The hue bands that touch the colour box (base +- `CUP_JITTER` on every channel) of a held-out cup family: sorted, never in train.

    Blue 21 to 23, purple 26 to 29, green 11 to 14, teal 16 to 19 (15 of the 36 bands)."""
    import itertools

    bands = set()
    for family in HELD_OUT_CUP_FAMILIES:
        for offsets in itertools.product((-CUP_JITTER, 0.0, CUP_JITTER), repeat=3):
            colour = [min(1.0, max(0.0, channel + offset)) for channel, offset in zip(CUP_FAMILY_BASES[family], offsets)]
            bands.add(hue_band_of(colour))
    return tuple(sorted(bands))


def hue_band_of(rgb) -> int:
    """The hue band (0 to `HUE_BAND_COUNT` - 1) of an sRGB colour (0 to 1)."""
    import colorsys

    return int(colorsys.rgb_to_hsv(*[float(value) for value in rgb[:3]])[0] * 360.0 // (360.0 / HUE_BAND_COUNT)) % HUE_BAND_COUNT


@functools.lru_cache(maxsize=None)
def _hue_assignment(seed: int) -> tuple:
    """Per band: `val`, `test` or `train`. The seeded shuffle gives `round(0.15 * 36)` = 5 bands each to val and test (the rest train, 26);
    then every band of `held_out_hue_bands()` that came out as train is moved, in ascending band order, to whichever of val and test has
    fewer bands (val on a tie). The held-out cup families of the indoor YOLO fine-tune therefore never reach the train pool, whatever the seed."""
    order = list(range(HUE_BAND_COUNT))
    random.Random(f"{seed}/hue-bands").shuffle(order)
    n_val, n_test = round(HUE_BAND_COUNT * SPLIT_FRACTIONS["val"]), round(HUE_BAND_COUNT * SPLIT_FRACTIONS["test"])
    out = ["train"] * HUE_BAND_COUNT
    for position, band in enumerate(order):
        out[band] = "val" if position < n_val else "test" if position < n_val + n_test else "train"
    for band in held_out_hue_bands():
        if out[band] == "train":
            out[band] = "val" if out.count("val") <= out.count("test") else "test"
    return tuple(out)


def hue_bands(split: str, seed: int = MASTER_SEED) -> list:
    return [band for band, owner in enumerate(_hue_assignment(seed)) if owner == split]


def surface_colour(tint, mean_rgb) -> tuple:
    """The colour a lit surface shows on average: the texture mean multiplied by the tint."""
    return tuple(min(1.0, max(0.0, mean_rgb[index] * tint[index])) for index in range(3))


def cup_contrast(rgb, surfaces: dict) -> dict:
    """`{name: distance}` of a cup colour to each drawn surface colour (`surfaces` maps wall, floor, table to an sRGB triple) and the ring."""
    out = {name: delta_e(rgb, colour) for name, colour in surfaces.items()}
    out["ring"] = delta_e(rgb, LANDING_RING_RGB)
    return out


def cup_distinct(rgb, surfaces: dict) -> bool:
    return all(value >= MIN_DELTA_E[name] for name, value in cup_contrast(rgb, surfaces).items())


def draw_cup_rgba(rng: random.Random, split: str, surfaces: dict, seed: int = MASTER_SEED) -> dict:
    """A cup colour for `split` against the drawn `surfaces` (wall, floor, table sRGB triples): hue uniformly inside a band of the split,
    then saturation and value; redrawn up to `CUP_ATTEMPTS` times until `cup_distinct`. If none passes, the candidate farthest (smallest
    shortfall) from the rule is kept and `satisfied` is false (the caller may redraw its materials). Returns
    `{"rgba", "band", "hue", "saturation", "value", "satisfied", "attempts"}`."""
    import colorsys

    bands = hue_bands(split, seed)
    best = None
    for attempt in range(1, CUP_ATTEMPTS + 1):
        band = rng.choice(bands)
        hue = (band + rng.random()) * 360.0 / HUE_BAND_COUNT
        saturation, value = rng.uniform(*SATURATION), rng.uniform(*VALUE)
        rgb = tuple(round(channel, 4) for channel in colorsys.hsv_to_rgb(hue / 360.0, saturation, value))
        if hue_band_of(rgb) != band:                  # the stored colour has 4 decimals: one at a band edge could land in the neighbour's band
            continue
        shortfall = max(MIN_DELTA_E[name] - dist for name, dist in cup_contrast(rgb, surfaces).items())
        candidate = {"rgba": [round(channel, 4) for channel in rgb] + [1.0], "band": band, "hue": round(hue, 3),
                     "saturation": round(saturation, 4), "value": round(value, 4), "satisfied": shortfall <= 0, "attempts": attempt}
        if candidate["satisfied"]:
            return candidate
        if best is None or shortfall < best[0]:
            best = (shortfall, candidate)
    return {**best[1], "attempts": CUP_ATTEMPTS}


def texture_means(textures_dir, proc_manifest: dict | None = None, cc0_manifest: dict | None = None) -> dict:
    """`{texture id: mean sRGB (0..1)}` for the textures of a directory: the manifests carry the means of the procedural and CC0 pools, the
    committed legacy PNGs are read."""
    means = {}
    for manifest in (proc_manifest, cc0_manifest):
        for entry in (manifest or {}).get("textures", []):
            means[entry["id"]] = entry["mean_rgb"]
    directory = Path(textures_dir)
    legacy = sorted({name for names in LEGACY.values() for name in names})
    if any((directory / f"{name}.png").is_file() for name in legacy):
        import numpy as np
        from PIL import Image

        for name in legacy:
            path = directory / f"{name}.png"
            if path.is_file():
                with Image.open(path) as image:
                    means[name] = mean_srgb(np.asarray(image.convert("RGB")))
    return means


def cc0_pack_sha256(manifest: dict) -> str:
    """The identity of the CC0 pack: sha256 over the sorted `id sha256_resized` lines of its manifest."""
    lines = sorted(f"{entry['id']} {entry['sha256_resized']}" for entry in manifest["textures"])
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()
