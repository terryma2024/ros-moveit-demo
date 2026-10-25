"""Plan of the indoor YOLO-Seg dataset: deterministic draws from the indoor scene-variant whitelist, split by asset identity.

The Teacher's `task_camera` YOLO was trained on the dark nominal scene. This module decides which frames to render for the bright
indoor nominal and the appearance library (indoor scene design 2026-10-24, "Teacher perception (decision D2)"). It is pure: no
MuJoCo, no file is written except by `materialize_layout`, which only builds a directory of symlinks and one rewritten scene file.
The renderer (`act/indoor_yolo_render.py`) turns a plan entry into an image, a mask and a depth map.

Draws come from `scene_variant` (the closed indoor whitelist: wall, floor and table texture and tint, per-light diffuse and active,
headlight, prop visibility, cup colour), so every draw is a valid variant document with a realized hash. The cup position is drawn
uniformly inside the Teacher success boundary polygon B_1..B_8 (the region the ACT collections used).

Split by asset identity (nothing of train is in val or test, and val and test share nothing either):
  textures      `act/indoor_assets.texture_pools`: the legacy, parametric (`proc/...`) and CC0 (`cc0/...`) textures, each assigned to one split by a
                seeded, disjoint three-way assignment per family; a draw takes the texture of every surface from the pool of its split
  tints         each split draws tints from its own channel range (train brightest), so a held-out material is never a train one
  cup colours   continuous: a hue is drawn inside a 10 degree band, and the 36 bands are partitioned among the splits; saturation and value are
                free; a draw must be clearly different (OKLab) from the drawn wall, floor and table and from the red landing ring
  layouts       train A only, val A and B, test A, B and C (B, the lab, and C, the home, are never seen in training or collected)
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from so101_demo.act import indoor_assets, scene_variant

MASTER_SEED = 20261024
CLASS_NAMES = {0: "plastic_cup"}

#: the eight boundary points of the Teacher success region, counter-clockwise (E, NE, N, NW, W, SW, S, SE); ledger CP-3668 and
#: `act/scene_sampling.py`
REGION_XY = ((0.09, -0.29), (0.077983, -0.232017), (0.02, -0.168), (-0.037696, -0.232304),
             (-0.05, -0.29), (-0.028083, -0.338083), (0.02, -0.342), (0.068083, -0.338083))
CUP_Z_M = 0.165

LAYOUT_SCENES = {"A": "scene_side_wrist_indoor.xml", "B": "indoor/scene_side_wrist_indoor_lab.xml",
                 "C": "indoor/scene_side_wrist_indoor_home.xml"}
NOMINAL_SCENE = "scene_side_wrist_indoor.xml"
DARK_SCENE = "scene_side_wrist.xml"

SPLIT_POLICY = {
    "train": {"layouts": ("A",), "tint": (0.82, 1.00), "nominal_fraction": 0.10},
    "val": {"layouts": ("A", "B"), "tint": (0.50, 0.64), "nominal_fraction": 0.0},
    "test": {"layouts": ("A", "B", "C"), "tint": (0.66, 0.78), "nominal_fraction": 0.0},
}
#: how many times a draw redraws its wall, floor and table when no cup colour of the split is clearly different from them
MATERIAL_REDRAWS = 8
LIGHT_SCALE = (0.6, 1.5)
LIGHT_TILT = (0.92, 1.08)
HEADLIGHT_SCALE = (0.7, 1.4)
FILL_OFF_PROBABILITY = 0.15
PROP_VISIBLE_PROBABILITY = 0.7
#: count keys beyond the three splits: name -> (split, image directory, kind). `ring`: the cup in the zone where the detector once took
#: the red landing ring and the cup's cast shadow for a second cup; `negative`: the cup is hidden, the label file is empty (hard negatives)
EXTRA_SETS = {"train_dark": ("train", "train", "dark"), "eval_indoor_nominal": ("eval_indoor_nominal", "eval_indoor_nominal", "nominal"),
              "eval_dark_nominal": ("eval_dark_nominal", "eval_dark_nominal", "dark"),
              **{f"{split}_ring": (split, split, "ring") for split in ("train", "val", "test")},
              **{f"{split}_negative": (split, split, "negative") for split in ("train", "val", "test")},
              **{f"{split}_ringnear": (split, split, "ringnear") for split in ("train", "val", "test")}}
#: the red target landing ring (visual only, `target_landing_tolerance_ring` at (-0.08, -0.05) in the table body at (0, -0.20)); it lies outside the
#: Teacher region (place-target exclusion), so `ringnear` puts the cup where the polygon comes closest to it. The ring is the key hard
#: negative (coordinator diagnosis 2026-10-24: ring hidden, 8/8; ring with the cup's shadow, a second instance at 0.66 to 0.79)
LANDING_RING_XY = (-0.08, -0.25)
RING_NEAR_ZONE = (-0.05, -0.02, -0.30, -0.22)
#: x0, x1, y0, y1 of the ambiguity zone (coordinator, 2026-10-24: misses at x 0.01 to 0.035, y -0.195 to -0.216), padded by about 2 cm
AMBIGUITY_ZONE = (-0.01, 0.06, -0.24, -0.17)
CUP_HIDDEN_Z_M = -5.0


def point_in_polygon(x: float, y: float, polygon) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def sample_cup_xy(rng: random.Random, zone=None) -> list:
    xs, ys = [point[0] for point in REGION_XY], [point[1] for point in REGION_XY]
    if zone is not None:
        xs, ys = list(zone[:2]), list(zone[2:])
    while True:
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        if point_in_polygon(x, y, REGION_XY):
            return [round(x, 6), round(y, 6)]


def asset_pools(act_assets: Path | None = None) -> dict:
    """`{"pools": {split: {surface: [texture]}}, "means": {texture: mean sRGB}}` for the textures next to `act_assets`
    (`assets/mujoco/act`): the manifests of the procedural and CC0 pools decide which textures exist. Without `act_assets` the pools are the
    procedural ones by name, with their means unknown (the cup rule then uses mid grey)."""
    proc = cc0 = None
    means = {}
    if act_assets is not None:
        directory = Path(act_assets).parent / "textures" / "indoor"
        if (directory / indoor_assets.PROC_MANIFEST).is_file():
            proc = indoor_assets.load_manifest(directory / indoor_assets.PROC_MANIFEST)
        if (directory / indoor_assets.CC0_MANIFEST).is_file():
            cc0 = indoor_assets.load_manifest(directory / indoor_assets.CC0_MANIFEST)
        means = indoor_assets.texture_means(directory, proc, cc0)
    return {"pools": indoor_assets.texture_pools(proc, cc0), "means": means}


def check_split_disjoint(pools: dict | None = None) -> None:
    """Raise `ValueError` unless the splits share no texture, no cup hue band and no tint range, and every pooled texture suits its surface."""
    pools = (pools or asset_pools())["pools"]
    owned = {split: {texture for ids in pools[split].values() for texture in ids} for split in SPLIT_POLICY}
    for first, second in (("train", "val"), ("train", "test"), ("val", "test")):
        if owned[first] & owned[second]:
            raise ValueError(f"SPLIT_TEXTURE_SHARED: {first} and {second}")
        if set(indoor_assets.hue_bands(first)) & set(indoor_assets.hue_bands(second)):
            raise ValueError(f"SPLIT_CUP_SHARED: {first} and {second}")
    ranges = sorted(SPLIT_POLICY[split]["tint"] for split in SPLIT_POLICY)
    if any(low_next <= high for (_, high), (low_next, _) in zip(ranges, ranges[1:])):
        raise ValueError("SPLIT_TINT_OVERLAP")
    for split in SPLIT_POLICY:
        layouts = set(SPLIT_POLICY[split]["layouts"])
        if (split == "train" and layouts != {"A"}) or (split == "val" and "C" in layouts):
            raise ValueError(f"SPLIT_LAYOUT_LEAK: {split}")
        for surface in indoor_assets.SURFACES:
            if not pools[split][surface]:
                raise ValueError(f"SPLIT_POOL_EMPTY: {split} {surface}")
            if not all(indoor_assets.texture_allowed(surface, texture) for texture in pools[split][surface]):
                raise ValueError(f"SPLIT_TEXTURE_UNKNOWN: {split} {surface}")


def _floats(text: str) -> list:
    return [float(item) for item in text.split()]


def layout_inventory(scene_xml: str) -> dict:
    """The lights (name -> nominal diffuse), props and headlight of a layout scene, with the rules `scene_variant` applies."""
    root = ElementTree.fromstring(scene_xml)
    lights = {item.get("name"): _floats(item.get("diffuse", "0.7 0.7 0.7")) for item in root.iter("light")
              if item.get("name") == "key_light" or (item.get("name") or "").startswith("ind_")}
    props = sorted(item.get("name") for item in root.iter("geom")
                   if (item.get("name") or "").startswith("ind_") and not item.get("name").startswith(scene_variant._STRUCTURE_PREFIXES)
                   and scene_variant._PROP_FIELD.fullmatch(f"prop.{item.get('name')}.visible"))     # a name the whitelist cannot spell stays shown
    headlight = next(root.iter("headlight"))
    return {"lights": dict(sorted(lights.items())), "props": props,
            "headlight": {"ambient": _floats(headlight.get("ambient")), "diffuse": _floats(headlight.get("diffuse"))}}


def layout_inventories(act_assets: Path) -> dict:
    act_assets = Path(act_assets)
    return {layout: layout_inventory((act_assets / scene).read_text(encoding="utf-8")) for layout, scene in LAYOUT_SCENES.items()}


def materialize_layout(act_assets: Path, layout: str, out_dir: Path) -> Path:
    """A `nominal_dir` for `scene_variant.realize` holding `layout`. A is the installed directory itself; B and C are rebuilt as a
    directory of symlinks to the installed `act` files with their scene rewritten under the nominal name (no compiler element, the
    robot include and the texture directory relative to the nominal directory), next to symlinks to `textures` and `assets`."""
    act_assets = Path(act_assets)
    if layout == "A":
        return act_assets
    out_dir = Path(out_dir)
    nominal = out_dir / "act"
    nominal.mkdir(parents=True, exist_ok=True)
    for entry in act_assets.iterdir():
        if entry.name not in (NOMINAL_SCENE, "indoor"):
            link = nominal / entry.name
            if not link.exists():
                link.symlink_to(entry)
    for sibling in ("textures", "assets"):
        link = out_dir / sibling
        if not link.exists():
            link.symlink_to(act_assets.parent / sibling)
    text = (act_assets / LAYOUT_SCENES[layout]).read_text(encoding="utf-8")
    text = text.replace('<compiler meshdir=".." />', "").replace('file="../so101_side_wrist.xml"', 'file="so101_side_wrist.xml"')
    text = text.replace("../../textures/", "../textures/")
    (nominal / NOMINAL_SCENE).write_text(text, encoding="utf-8")
    return nominal


def _tint(rng: random.Random, band) -> list:
    return [round(rng.uniform(*band), 4) for _ in range(3)] + [1.0]


def _variant(rng: random.Random, split: str, layout: str, inventory: dict, assets: dict, name: str) -> tuple:
    """`(variant document, cup draw)`: the surfaces first (texture of the split's pool, tint of its band), then a cup colour of the split's hue
    bands that is clearly different from them; the surfaces are redrawn up to `MATERIAL_REDRAWS` times when no colour is."""
    policy = SPLIT_POLICY[split]
    pools, means = assets["pools"][split], assets["means"]
    for _attempt in range(MATERIAL_REDRAWS + 1):
        fields, colours = {}, {}
        for surface in indoor_assets.SURFACES:
            texture = rng.choice(pools[surface])
            tint = _tint(rng, policy["tint"])
            fields[f"{surface}.texture"] = texture
            fields[f"{surface}.rgba"] = tint
            colours[surface] = indoor_assets.surface_colour(tint, means.get(texture, (0.5, 0.5, 0.5)))
        cup = indoor_assets.draw_cup_rgba(rng, split, colours)
        if cup["satisfied"]:
            break
    for light, nominal in inventory["lights"].items():
        scale = rng.uniform(*LIGHT_SCALE)
        fields[f"light.{light}.diffuse"] = [round(min(4.0, value * scale * rng.uniform(*LIGHT_TILT)), 5) for value in nominal]
        if light not in ("ind_main", "key_light"):
            fields[f"light.{light}.active"] = 0 if rng.random() < FILL_OFF_PROBABILITY else 1
    for attribute in ("ambient", "diffuse"):
        scale = rng.uniform(*HEADLIGHT_SCALE)
        fields[f"headlight.{attribute}"] = [round(min(1.0, value * scale), 5) for value in inventory["headlight"][attribute]]
    for prop in inventory["props"]:
        fields[f"prop.{prop}.visible"] = 1 if rng.random() < PROP_VISIBLE_PROBABILITY else 0
    fields["cup_material.rgba"] = cup["rgba"]
    variant = {"schema_version": scene_variant.SCHEMA_VERSION, "kind": scene_variant.KIND, "name": name, "base": "indoor", "set": fields}
    return variant, cup


def draw_sample(master_seed: int, set_name: str, index: int, inventories: dict, attempt: int = 0, assets: dict | None = None) -> dict:
    """One plan entry; `attempt` > 0 is a redraw of the same slot after the renderer found the cup hidden."""
    split, directory, kind = EXTRA_SETS.get(set_name, (set_name, set_name, "variant"))
    sample_id = f"{set_name}-{index:05d}"
    seed = f"{master_seed}/{set_name}/{index}" + (f"/redraw{attempt}" if attempt else "")
    rng = random.Random(seed)
    if kind == "variant" and rng.random() < SPLIT_POLICY[split]["nominal_fraction"]:
        kind = "nominal"
    cup_xy = sample_cup_xy(rng, {"ring": AMBIGUITY_ZONE, "ringnear": RING_NEAR_ZONE}.get(kind))
    entry = {"sample_id": sample_id, "split": split, "directory": directory, "index": index, "seed": seed,
             "cup_xy": cup_xy, "kind": kind, "cup_hidden": kind == "negative"}
    if kind == "dark":
        return {**entry, "layout": "dark", "cup_family": "orange", "variant": None}
    if kind == "nominal":
        return {**entry, "layout": "A", "cup_family": "orange", "variant": None}
    layout = rng.choice(SPLIT_POLICY[split]["layouts"])
    variant, cup = _variant(rng, split, layout, inventories[layout], assets or asset_pools(), sample_id)
    return {**entry, "layout": layout, "cup_family": f"hue-band-{cup['band']:02d}",
            "cup": {key: cup[key] for key in ("band", "hue", "saturation", "value", "satisfied")}, "variant": variant}


def build_plan(counts: dict, master_seed: int, inventories: dict, assets: dict | None = None) -> list:
    """The ordered plan: `counts` maps train, val, test and the extra sets (`EXTRA_SETS`) to a number of frames; `assets` is `asset_pools(...)`."""
    assets = assets or asset_pools()
    check_split_disjoint(assets)
    unknown = set(counts) - set(SPLIT_POLICY) - set(EXTRA_SETS)
    if unknown or any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError(f"PLAN_COUNTS_INVALID: {sorted(unknown) or counts}")
    return [draw_sample(master_seed, name, index, inventories, assets=assets) for name, count in counts.items() for index in range(count)]


def plan_document(plan: list, counts: dict, master_seed: int) -> dict:
    body = {"master_seed": master_seed, "counts": dict(counts), "samples": plan}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**body, "plan_sha256": digest}


def label_line(mask: np.ndarray) -> str:
    """The YOLO-Seg label of one cup: class 0 and the normalised convex outline of the visible mask ("" when nothing is visible)."""
    if not mask.any():
        return ""
    from so101_demo.adapters.perception.mujoco_dataset.render import _polygon_from_mask

    coordinates = " ".join(f"{value:.9f}" for point in _polygon_from_mask(mask) for value in point)
    return f"0 {coordinates}"


def dataset_yaml(directories) -> str:
    """The ultralytics dataset file: `train`, `val`, `test` as the standard splits; any other directory is evaluation-only and not listed."""
    lines = ["path: ."]
    lines += [f"{split}: images/{split}" for split in ("train", "val", "test") if split in directories]
    return "\n".join(lines + ["names:", "  0: plastic_cup", ""])
