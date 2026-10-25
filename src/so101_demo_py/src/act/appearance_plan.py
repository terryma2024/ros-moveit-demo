"""The appearance plan of an indoor collection: which episodes are nominal, which are randomised, and how (indoor P3, R2).

A plan is one small document (a campaign seed, the nominal share, the hash of the nominal indoor scene) that is frozen with the scene
list it belongs to. The appearance of an episode is a pure function of (plan seed, scene id) over the closed `indoor` scene-variant
whitelist (`scene_variant.py`): the same inputs give the same draw on every host. The scene list carries the result per row
(`appearance` and `teacher_source`), so the frozen scene manifest binds it into the inputs hash, and every consumer re-derives it and
refuses a row that is not the derivation of its scene id.

What is collected. The nominal share (25 % by default) is the indoor layout A as it is. The rest is layout A with a randomised
appearance: wall, floor and table textures and tints, every light (intensity, direction, a fill light off now and then), the headlight,
the visibility of the props, and the cup colour. Every draw is a variant of the whitelist, so it changes no collision geom, mass, joint,
friction or camera (`scene_variant_run.realize_into` proves the stripped physics fingerprint equal to the nominal one, again for each
task in the shard).

What is never collected (kept for evaluating appearance generalisation, `HELD_OUT`): layouts B (lab) and C (home); the textures
`wall_beige` and `floor_parquet` (also the table's); the cup colour families blue, purple, green and teal; and tints below
`TINT_BAND`. These are the validation and test assets of the indoor YOLO fine-tune (`indoor_yolo_dataset.SPLIT_POLICY`), so the Teacher's
detector and the ACT policy share one held-out set. The drawing pools are the YOLO training pools on layout A only; a test pins the two
together.

Teacher source (decision D2). A nominal episode is demonstrated with the camera Teacher (`camera_rgbd`: the YOLO + depth pose). A
randomised episode uses the privileged pose (`privileged_pose`: the simulator's cup pose), allowed only on the indoor rig.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from xml.etree import ElementTree

from so101_demo.act import scene_variant

PLAN_KIND = "ACT_APPEARANCE_PLAN"
SCHEMA_VERSION = 1
RECIPE = "appearance-plan-recipe"
RIG = "side-wrist-indoor"
LAYOUT = "A"
NOMINAL_SHARE_DEFAULT = 0.25

KIND_NOMINAL = "nominal"
KIND_RANDOMISED = "randomised"
TEACHER_SOURCE_CAMERA = "camera_rgbd"
TEACHER_SOURCE_PRIVILEGED = "privileged_pose"
TEACHER_SOURCES = (TEACHER_SOURCE_CAMERA, TEACHER_SOURCE_PRIVILEGED)
#: the published pose of a privileged episode is the simulator's position at the paused instant: the Teacher child, which observes the same
#: state itself, refuses a `/cup_pose` that is farther from it than this (metres)
PRIVILEGED_PUBLISHED_TOLERANCE_M = 1e-4

#: what is collected (layout A only): the YOLO training pools of `indoor_yolo_dataset.SPLIT_POLICY["train"]`
POOLS = {
    "wall": ("wall_white", "wall_grey"),
    "floor": ("floor_wood_light", "floor_tile_grey", "floor_carpet"),
    "table": ("table_laminate", "cabinet_wood", "metal_shelf"),
    "cups": ("orange", "red", "yellow", "magenta"),
}
TINT_BAND = (0.82, 1.00)
#: what is never collected: layouts B and C, and the validation and test assets of the YOLO fine-tune
HELD_OUT = {
    "layouts": ("B", "C"),
    "textures": ("wall_beige", "floor_parquet"),
    "cups": ("blue", "purple", "green", "teal"),
    "tint_below": TINT_BAND[0],
}
CUP_FAMILIES = {                       # base colour of a family; each draw jitters every channel by +-CUP_JITTER
    "orange": (1.0, 0.55, 0.12), "red": (0.85, 0.10, 0.10), "yellow": (0.95, 0.85, 0.15), "magenta": (0.85, 0.15, 0.60),
    "blue": (0.15, 0.30, 0.85), "purple": (0.50, 0.20, 0.70), "green": (0.20, 0.70, 0.25), "teal": (0.10, 0.65, 0.65)}
CUP_JITTER = 0.06
LIGHT_SCALE = (0.7, 1.3)
LIGHT_TILT = (0.92, 1.08)
LIGHT_DIR_JITTER = 0.15
HEADLIGHT_SCALE = (0.7, 1.4)
FILL_OFF_PROBABILITY = 0.15
PROP_VISIBLE_PROBABILITY = 0.7
#: a cup colour whose distance (RGB, 0 to 1) from the mean colour of the tinted table or wall is below this blends into it and is redrawn
BLEND_MIN_DISTANCE = 0.20
#: mean RGB of the texture files (`assets/mujoco/textures/indoor/*.png`); a test pins them to the files
TEXTURE_MEAN_RGB = {
    "wall_white": (0.9236, 0.9236, 0.9079), "wall_grey": (0.5858, 0.6054, 0.6251), "wall_beige": (0.8523, 0.7817, 0.6640),
    "floor_wood_light": (0.7564, 0.6021, 0.4092), "floor_tile_grey": (0.6483, 0.6680, 0.6876), "floor_carpet": (0.7433, 0.6844, 0.5864),
    "floor_parquet": (0.7195, 0.5259, 0.3323), "table_laminate": (0.7935, 0.7582, 0.6876), "cabinet_wood": (0.6113, 0.4355, 0.2596),
    "metal_shelf": (0.5876, 0.6072, 0.6268)}
#: redraws of the cup colour when it blends in (a bounded, ordered list: the draw index is part of the hash)
MAX_CUP_DRAWS = 8
PLAN_FIELDS = frozenset({"kind", "schema_version", "rig", "layout", "seed", "nominal_share", "nominal_scene_sha256", "plan_sha256"})
APPEARANCE_FIELDS = frozenset({"kind", "plan_sha256", "scene_id", "layout", "variant", "variant_sha256", "cup_family", "draw_sha256"})
SEED_LIMIT = 2 ** 63


class AppearanceInvalid(ValueError):
    """The plan, a draw or a row is not what the plan derives; `args[0]` starts with the refusal code."""


def _fail(code: str, detail: str = ""):
    raise AppearanceInvalid(f"{code}: {detail}" if detail else code)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _unit(seed: int, scene_id: str, axis: str, index: int = 0, draw: int = 0) -> float:
    """A uniform number in [0, 1) that depends only on its arguments (the first eight bytes of a sha256)."""

    digest = hashlib.sha256(f"{RECIPE}|{seed}|{scene_id}|{axis}|{index}|{draw}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def _between(low: float, high: float, unit: float) -> float:
    return low + (high - low) * unit


def _choice(items, unit: float):
    return items[min(len(items) - 1, int(unit * len(items)))]


def check_pools() -> None:
    """Raise `AppearanceInvalid` unless the collected pools are disjoint from the held-out assets and inside the texture libraries."""

    held = set(HELD_OUT["textures"])
    for surface, library in (("wall", scene_variant.WALL_TEXTURES), ("floor", scene_variant.FLOOR_TEXTURES),
                             ("table", scene_variant.TABLE_TEXTURES)):
        pool = set(POOLS[surface])
        if not pool <= set(library):
            _fail("APPEARANCE_POOL_UNKNOWN_TEXTURE", surface)
        if pool & held:
            _fail("APPEARANCE_POOL_HELD_OUT_TEXTURE", surface)
    if set(POOLS["cups"]) & set(HELD_OUT["cups"]) or not set(POOLS["cups"]) <= set(CUP_FAMILIES):
        _fail("APPEARANCE_POOL_CUP")
    if TINT_BAND[0] < HELD_OUT["tint_below"]:
        _fail("APPEARANCE_POOL_TINT")
    if LAYOUT in HELD_OUT["layouts"]:
        _fail("APPEARANCE_POOL_LAYOUT")


def make_plan(*, seed: int, nominal_share: float = NOMINAL_SHARE_DEFAULT, nominal_scene_sha256: str) -> dict:
    """The plan document, with its hash. `nominal_scene_sha256` is the sha256 of the installed `scene_side_wrist_indoor.xml`."""

    document = {"kind": PLAN_KIND, "schema_version": SCHEMA_VERSION, "rig": RIG, "layout": LAYOUT, "seed": seed,
                "nominal_share": nominal_share, "nominal_scene_sha256": nominal_scene_sha256}
    return validate_plan({**document, "plan_sha256": _sha256(document)})


def validate_plan(plan) -> dict:
    """The checked plan (a copy); `AppearanceInvalid` for any field outside its form, a layout other than A, or a hash that is not the document's."""

    if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
        _fail("APPEARANCE_PLAN_SHAPE_INVALID")
    if plan["kind"] != PLAN_KIND or type(plan["schema_version"]) is not int or plan["schema_version"] != SCHEMA_VERSION:
        _fail("APPEARANCE_PLAN_SHAPE_INVALID")
    if plan["rig"] != RIG:
        _fail("APPEARANCE_PLAN_RIG_INVALID", str(plan["rig"]))
    if plan["layout"] != LAYOUT or plan["layout"] in HELD_OUT["layouts"]:
        _fail("APPEARANCE_PLAN_LAYOUT_INVALID", str(plan["layout"]))
    if type(plan["seed"]) is not int or not 0 <= plan["seed"] < SEED_LIMIT:
        _fail("APPEARANCE_PLAN_SEED_INVALID")
    share = plan["nominal_share"]
    if type(share) not in (int, float) or isinstance(share, bool) or not math.isfinite(share) or not 0.0 <= share <= 1.0:
        _fail("APPEARANCE_PLAN_SHARE_INVALID")
    digest = plan["nominal_scene_sha256"]
    if type(digest) is not str or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        _fail("APPEARANCE_PLAN_SCENE_HASH_INVALID")
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if plan["plan_sha256"] != _sha256(body):
        _fail("APPEARANCE_PLAN_HASH_MISMATCH")
    check_pools()
    return json.loads(canonical(plan))


def _floats(text) -> list:
    return [float(item) for item in str(text).split()]


def scene_inventory(nominal_dir) -> dict:
    """The lights (nominal diffuse and direction), props and headlight of the installed indoor scene, and the scene file's sha256.

    `nominal_dir` is the installed `assets/mujoco/act` directory (`scene_variant_run.nominal_dir(share)`)."""

    path = Path(nominal_dir) / scene_variant.INDOOR_SCENE
    data = path.read_bytes()
    root = ElementTree.fromstring(data)
    lights = {}
    for item in root.iter("light"):
        name = item.get("name") or ""
        if name == "key_light" or name.startswith("ind_"):
            lights[name] = {"diffuse": _floats(item.get("diffuse", "0.7 0.7 0.7")), "dir": _floats(item.get("dir", "0 0 -1"))}
    props = sorted(item.get("name") for item in root.iter("geom")
                   if (item.get("name") or "").startswith("ind_") and not item.get("name").startswith(scene_variant._STRUCTURE_PREFIXES)
                   and scene_variant._PROP_FIELD.fullmatch(f"prop.{item.get('name')}.visible"))
    headlights = [item for visual in root.iter("visual") for item in visual.findall("headlight")]
    if len(headlights) != 1 or not lights:
        _fail("APPEARANCE_NOMINAL_SCENE_DRIFT", "the indoor scene needs one headlight and its lights")
    return {"scene_sha256": hashlib.sha256(data).hexdigest(), "lights": dict(sorted(lights.items())), "props": props,
            "headlight": {"ambient": _floats(headlights[0].get("ambient")), "diffuse": _floats(headlights[0].get("diffuse"))}}


def _tint(seed: int, scene_id: str, surface: str) -> list:
    return [round(_between(*TINT_BAND, _unit(seed, scene_id, f"tint.{surface}", channel)), 4) for channel in range(3)] + [1.0]


def _distance(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _surface_colour(texture: str, tint) -> tuple:
    return tuple(mean * channel for mean, channel in zip(TEXTURE_MEAN_RGB[texture], tint))


def _cup(seed: int, scene_id: str, surfaces: dict) -> tuple:
    """`(family, rgba)`: the first of the bounded draws whose colour does not blend into the table or the wall."""

    for draw in range(MAX_CUP_DRAWS):
        family = _choice(POOLS["cups"], _unit(seed, scene_id, "cup.family", 0, draw))
        rgba = [round(min(1.0, max(0.0, channel + _between(-CUP_JITTER, CUP_JITTER, _unit(seed, scene_id, "cup.jitter", index, draw)))), 4)
                for index, channel in enumerate(CUP_FAMILIES[family])] + [1.0]
        if all(_distance(rgba[:3], colour) >= BLEND_MIN_DISTANCE for colour in surfaces.values()):
            return family, rgba
    _fail("APPEARANCE_CUP_ALWAYS_BLENDS", scene_id)


def _scene_id(scene_id) -> str:
    if not isinstance(scene_id, str) or not scene_id or scene_id != scene_id.strip():
        _fail("APPEARANCE_SCENE_ID_INVALID")
    return scene_id


def kind_for(plan: dict, scene_id: str) -> str:
    """`nominal` for the plan's share of the scene ids, else `randomised`: the first draw of (seed, scene id)."""

    return KIND_NOMINAL if _unit(plan["seed"], _scene_id(scene_id), "kind") < plan["nominal_share"] else KIND_RANDOMISED


def teacher_source_for(kind: str) -> str:
    """Decision D2: the camera Teacher for a nominal episode, the privileged pose for a randomised one."""

    if kind == KIND_NOMINAL:
        return TEACHER_SOURCE_CAMERA
    if kind == KIND_RANDOMISED:
        return TEACHER_SOURCE_PRIVILEGED
    _fail("APPEARANCE_KIND_INVALID", str(kind))


def _variant_fields(plan: dict, scene_id: str, inventory: dict) -> tuple:
    seed = plan["seed"]
    fields, textures = {}, {}
    for surface in ("wall", "floor", "table"):
        texture = _choice(POOLS[surface], _unit(seed, scene_id, f"texture.{surface}"))
        tint = _tint(seed, scene_id, surface)
        fields[f"{surface}.texture"], fields[f"{surface}.rgba"] = texture, tint
        textures[surface] = _surface_colour(texture, tint)
    for index, (name, nominal) in enumerate(inventory["lights"].items()):
        scale = _between(*LIGHT_SCALE, _unit(seed, scene_id, "light.scale", index))
        fields[f"light.{name}.diffuse"] = [
            round(min(4.0, value * scale * _between(*LIGHT_TILT, _unit(seed, scene_id, "light.tilt", index * 3 + channel))), 5)
            for channel, value in enumerate(nominal["diffuse"])]
        direction = [value + (_between(-LIGHT_DIR_JITTER, LIGHT_DIR_JITTER, _unit(seed, scene_id, "light.dir", index * 3 + axis))
                              if axis < 2 else 0.0) for axis, value in enumerate(nominal["dir"])]
        fields[f"light.{name}.dir"] = [round(value, 5) for value in direction]
        if name not in ("ind_main", "key_light"):
            fields[f"light.{name}.active"] = 0 if _unit(seed, scene_id, "light.off", index) < FILL_OFF_PROBABILITY else 1
    for index, attribute in enumerate(("ambient", "diffuse")):
        scale = _between(*HEADLIGHT_SCALE, _unit(seed, scene_id, "headlight", index))
        fields[f"headlight.{attribute}"] = [round(min(1.0, value * scale), 5) for value in inventory["headlight"][attribute]]
    for index, prop in enumerate(inventory["props"]):
        fields[f"prop.{prop}.visible"] = 1 if _unit(seed, scene_id, "prop", index) < PROP_VISIBLE_PROBABILITY else 0
    family, rgba = _cup(seed, scene_id, {"table": textures["table"], "wall": textures["wall"]})
    fields["cup_material.rgba"] = rgba
    return fields, family


def check_not_held_out(variant: dict) -> None:
    """Raise `AppearanceInvalid` if a (normalised) variant names a held-out layout, texture, tint or cup colour."""

    fields = variant["set"]
    if variant.get("base") != scene_variant.BASE_INDOOR:
        _fail("APPEARANCE_VARIANT_BASE_INVALID")
    for surface in ("wall", "floor", "table"):
        texture = fields.get(f"{surface}.texture")
        if texture is not None and (texture in HELD_OUT["textures"] or texture not in POOLS[surface]):
            _fail("APPEARANCE_HELD_OUT_TEXTURE", f"{surface}.texture={texture}")
        tint = fields.get(f"{surface}.rgba")
        if tint is not None and any(channel < HELD_OUT["tint_below"] for channel in tint[:3]):
            _fail("APPEARANCE_HELD_OUT_TINT", f"{surface}.rgba")
    cup = fields.get("cup_material.rgba")
    if cup is not None:
        for family in HELD_OUT["cups"]:
            base = CUP_FAMILIES[family]
            if all(abs(channel - reference) <= CUP_JITTER + 1e-9 for channel, reference in zip(cup[:3], base)):
                _fail("APPEARANCE_HELD_OUT_CUP", family)


def derive(plan: dict, scene_id: str, inventory: dict) -> dict:
    """The appearance of one scene: `{"kind", "variant", ...}` (a nominal one has `variant` None), a pure function of (plan, scene id, inventory)."""

    plan = validate_plan(plan)
    scene_id = _scene_id(scene_id)
    if inventory["scene_sha256"] != plan["nominal_scene_sha256"]:
        _fail("APPEARANCE_NOMINAL_SCENE_MISMATCH", "the installed indoor scene is not the plan's")
    kind = kind_for(plan, scene_id)
    variant, variant_digest, family = None, None, None
    if kind == KIND_RANDOMISED:
        fields, family = _variant_fields(plan, scene_id, inventory)
        document = {"schema_version": scene_variant.SCHEMA_VERSION, "kind": scene_variant.KIND, "name": f"p3-{scene_id}"[:64],
                    "base": scene_variant.BASE_INDOOR, "set": fields}
        variant = scene_variant.normalize_variant(document)
        check_not_held_out(variant)
        variant_digest = scene_variant.variant_sha256(variant)
    draw = {"kind": kind, "plan_sha256": plan["plan_sha256"], "scene_id": scene_id, "layout": plan["layout"], "variant": variant,
            "variant_sha256": variant_digest, "cup_family": family}
    return {**draw, "draw_sha256": _sha256(draw)}


def annotate_rows(plan: dict, rows, inventory: dict) -> list:
    """The scene rows with their derived `appearance` and `teacher_source` (the other fields are kept as they are)."""

    out = []
    for row in rows:
        appearance = derive(plan, row["scene_id"], inventory)
        out.append({**row, "appearance": appearance, "teacher_source": teacher_source_for(appearance["kind"])})
    return out


def verify_row(plan: dict, row: dict, inventory: dict) -> dict:
    """The row's appearance, if and only if it is the derivation of its scene id (and its Teacher source follows from it); else `AppearanceInvalid`."""

    if not isinstance(row, dict) or "appearance" not in row or "teacher_source" not in row:
        _fail("APPEARANCE_ROW_MISSING", str(row.get("scene_id") if isinstance(row, dict) else row))
    expected = derive(plan, row["scene_id"], inventory)
    if row["appearance"] != expected:
        _fail("APPEARANCE_ROW_NOT_DERIVED", row["scene_id"])
    if row["teacher_source"] != teacher_source_for(expected["kind"]):
        _fail("APPEARANCE_TEACHER_SOURCE_MISMATCH", row["scene_id"])
    return expected


def teacher_source_allowed(rig, source: str, kind: str) -> bool:
    """Which Teacher source an episode may use. The privileged pose: only a randomised episode of the indoor rig. The camera Teacher: only a
    nominal one (a randomised episode never uses the camera pose as the demonstration's input, decision D2)."""

    rig = getattr(rig, "rig", rig)
    if source == TEACHER_SOURCE_PRIVILEGED:
        return rig == RIG and kind == KIND_RANDOMISED
    if source == TEACHER_SOURCE_CAMERA:
        return kind == KIND_NOMINAL
    return False
