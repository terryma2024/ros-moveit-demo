"""Plan of the indoor YOLO-Seg dataset: deterministic draws from the indoor scene-variant whitelist, split by asset identity.

The Teacher's `task_camera` YOLO was trained on the dark nominal scene. This module decides which frames to render for the bright
indoor nominal and the appearance library (indoor scene design 2026-10-24, "Teacher perception (decision D2)"). It is pure: no
MuJoCo, no file is written except by `materialize_layout`, which only builds a directory of symlinks and one rewritten scene file.
The renderer (`act/indoor_yolo_render.py`) turns a plan entry into an image, a mask and a depth map.

Draws come from `scene_variant` (the closed indoor whitelist: wall, floor and table texture and tint, per-light diffuse and active,
headlight, prop visibility, cup colour), so every draw is a valid variant document with a realized hash. The cup position is drawn
uniformly inside the Teacher success boundary polygon B_1..B_8 (the region the ACT collections used).

Split by asset identity (nothing of train is in val or test):
  textures      the texture FILES of train, val and test are disjoint; val and test share the held-out textures
  tints         each split draws tints from its own channel range (train brightest), so a held-out material is never a train one
  cup colours   each split has its own colour families (train: warm; val: blue, purple; test: green, teal)
  layouts       train A and B, val A and B, test A, B and C (C, the home with a sofa and a window, is never seen in training)
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from so101_demo.act import scene_variant

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

CUP_FAMILIES = {                                  # base colour (the nominal cup is "orange"); each draw jitters a channel by +-0.06
    "orange": (1.0, 0.55, 0.12), "red": (0.85, 0.10, 0.10), "yellow": (0.95, 0.85, 0.15), "magenta": (0.85, 0.15, 0.60),
    "blue": (0.15, 0.30, 0.85), "purple": (0.50, 0.20, 0.70), "green": (0.20, 0.70, 0.25), "teal": (0.10, 0.65, 0.65)}
CUP_JITTER = 0.06

SPLIT_POLICY = {
    "train": {"layouts": ("A", "B"), "wall": ("wall_white", "wall_grey"), "floor": ("floor_wood_light", "floor_tile_grey", "floor_carpet"),
              "table": ("table_laminate", "cabinet_wood", "metal_shelf"), "tint": (0.82, 1.00),
              "cups": ("orange", "red", "yellow", "magenta"), "nominal_fraction": 0.10},
    "val": {"layouts": ("A", "B"), "wall": ("wall_beige",), "floor": ("floor_parquet",), "table": ("floor_parquet",),
            "tint": (0.50, 0.64), "cups": ("blue", "purple"), "nominal_fraction": 0.0},
    "test": {"layouts": ("A", "B", "C"), "wall": ("wall_beige",), "floor": ("floor_parquet",), "table": ("floor_parquet",),
             "tint": (0.66, 0.78), "cups": ("green", "teal"), "nominal_fraction": 0.0},
}
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


def _textures(split: str) -> set:
    policy = SPLIT_POLICY[split]
    return set(policy["wall"]) | set(policy["floor"]) | set(policy["table"])


def check_split_disjoint() -> None:
    """Raise `ValueError` unless train shares no texture file, cup family or tint range with val or test, and val and test share no cup family or tint range."""
    for held_out in ("val", "test"):
        if _textures("train") & _textures(held_out):
            raise ValueError(f"SPLIT_TEXTURE_SHARED: train and {held_out}")
        if set(SPLIT_POLICY["train"]["cups"]) & set(SPLIT_POLICY[held_out]["cups"]):
            raise ValueError(f"SPLIT_CUP_SHARED: train and {held_out}")
    if set(SPLIT_POLICY["val"]["cups"]) & set(SPLIT_POLICY["test"]["cups"]):
        raise ValueError("SPLIT_CUP_SHARED: val and test")
    ranges = sorted(SPLIT_POLICY[split]["tint"] for split in SPLIT_POLICY)
    if any(low_next <= high for (_, high), (low_next, _) in zip(ranges, ranges[1:])):
        raise ValueError("SPLIT_TINT_OVERLAP")
    for split, policy in SPLIT_POLICY.items():
        for surface, library in (("wall", scene_variant.WALL_TEXTURES), ("floor", scene_variant.FLOOR_TEXTURES),
                                 ("table", scene_variant.TABLE_TEXTURES)):
            if not set(policy[surface]) <= set(library):
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


def _cup_rgba(rng: random.Random, family: str) -> list:
    return [round(min(1.0, max(0.0, channel + rng.uniform(-CUP_JITTER, CUP_JITTER))), 4) for channel in CUP_FAMILIES[family]] + [1.0]


def _variant(rng: random.Random, split: str, layout: str, inventory: dict, family: str, name: str) -> dict:
    policy = SPLIT_POLICY[split]
    fields = {}
    for surface in ("wall", "floor", "table"):
        fields[f"{surface}.texture"] = rng.choice(policy[surface])
        fields[f"{surface}.rgba"] = _tint(rng, policy["tint"])
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
    fields["cup_material.rgba"] = _cup_rgba(rng, family)
    return {"schema_version": scene_variant.SCHEMA_VERSION, "kind": scene_variant.KIND, "name": name, "base": "indoor", "set": fields}


def draw_sample(master_seed: int, set_name: str, index: int, inventories: dict, attempt: int = 0) -> dict:
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
    family = rng.choice(SPLIT_POLICY[split]["cups"])
    return {**entry, "layout": layout, "cup_family": family,
            "variant": _variant(rng, split, layout, inventories[layout], family, sample_id)}


def build_plan(counts: dict, master_seed: int, inventories: dict) -> list:
    """The ordered plan: `counts` maps train, val, test and the extra sets (`EXTRA_SETS`) to a number of frames."""
    check_split_disjoint()
    unknown = set(counts) - set(SPLIT_POLICY) - set(EXTRA_SETS)
    if unknown or any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError(f"PLAN_COUNTS_INVALID: {sorted(unknown) or counts}")
    return [draw_sample(master_seed, name, index, inventories) for name, count in counts.items() for index in range(count)]


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
