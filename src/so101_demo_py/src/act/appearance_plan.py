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
`wall_beige` and `floor_parquet` (also the table's); the cup colour families blue, purple, green and teal (as the hue bands that touch their
colour boxes, `indoor_assets.held_out_hue_bands`); and tints below `TINT_BAND`. These are the validation and test assets of the indoor YOLO
fine-tune, so the Teacher's detector and the ACT policy share one held-out set; a test pins the literal list.

Pools (goal 13). The drawing pools are the TRAIN pools of `indoor_assets` on layout A only: the legacy train textures, the train share of the
832 procedural textures and of the 180 CC0 textures (assigned by identity, disjoint from val and test), and the train hue bands of a continuous
HSV cup colour that must stay clearly different (OKLab) from the drawn wall, floor and table and from the red landing ring. Val and test assets,
and every held-out asset above, are never drawn: they are for evaluation rollouts. The identity of the pools (the sha256 of the procedural
manifest, the CC0 pack sha256, the split seed, the hash of the whole split assignment and of the cup rule) is part of the plan, so a plan
made for other pools, or for an install whose manifests or CC0 files differ, is refused (`APPEARANCE_POOL_IDENTITY_MISMATCH`,
`APPEARANCE_CC0_PACK_*`, `APPEARANCE_PROC_TEXTURE_*`).

Teacher source (decision D2). A nominal episode is demonstrated with the camera Teacher (`camera_rgbd`: the YOLO + depth pose). A
randomised episode uses the privileged pose (`privileged_pose`: the simulator's cup pose), allowed only on the indoor rig.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from xml.etree import ElementTree

from so101_demo.act import indoor_assets, scene_variant

PLAN_KIND = "ACT_APPEARANCE_PLAN"
#: 2: the plan carries the identity of the asset pools (goal 13); the draws are over the pools of `indoor_assets`, so a version 1 plan is refused
SCHEMA_VERSION = 2
RECIPE = "appearance-plan-recipe-2"
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

#: the pools of what is collected (layout A only) are not constants: they are the TRAIN pools of the installed assets (`scene_inventory`
#: -> `inventory["pools"]["train"]`, from `indoor_assets.texture_pools` over the manifests), and the train hue bands (`indoor_assets.hue_bands`)
TINT_BAND = (0.82, 1.00)
#: what is never collected: layouts B and C, and the validation and test assets of the indoor YOLO fine-tune. Besides these, no asset of the val
#: and test pools of `indoor_assets` is ever drawn (`check_pools`, `check_not_held_out`).
HELD_OUT = {
    "layouts": ("B", "C"),
    "textures": indoor_assets.HELD_OUT_LEGACY_TEXTURES,
    "cups": indoor_assets.HELD_OUT_CUP_FAMILIES,
    "cup_hue_bands": indoor_assets.held_out_hue_bands(),
    "tint_below": TINT_BAND[0],
}
CUP_FAMILIES = indoor_assets.CUP_FAMILY_BASES      # the base colours of the families; the held-out ones define `HELD_OUT["cup_hue_bands"]`
CUP_JITTER = indoor_assets.CUP_JITTER
LIGHT_SCALE = (0.7, 1.3)
LIGHT_TILT = (0.92, 1.08)
LIGHT_DIR_JITTER = 0.15
HEADLIGHT_SCALE = (0.7, 1.4)
FILL_OFF_PROBABILITY = 0.15
PROP_VISIBLE_PROBABILITY = 0.7
#: mean RGB of the legacy texture files (`assets/mujoco/textures/indoor/*.png`); a test pins them to the files. The procedural and CC0 means
#: are in their manifests.
TEXTURE_MEAN_RGB = {
    "wall_white": (0.9236, 0.9236, 0.9079), "wall_grey": (0.5858, 0.6054, 0.6251), "wall_beige": (0.8523, 0.7817, 0.6640),
    "floor_wood_light": (0.7564, 0.6021, 0.4092), "floor_tile_grey": (0.6483, 0.6680, 0.6876), "floor_carpet": (0.7433, 0.6844, 0.5864),
    "floor_parquet": (0.7195, 0.5259, 0.3323), "table_laminate": (0.7935, 0.7582, 0.6876), "cabinet_wood": (0.6113, 0.4355, 0.2596),
    "metal_shelf": (0.5876, 0.6072, 0.6268)}
#: bounded, ordered redraws of the cup colour (the draw index is part of the hash): the rule is `indoor_assets.cup_distinct` (OKLab distance to
#: the drawn wall, floor and table and to the red landing ring)
MAX_CUP_DRAWS = indoor_assets.CUP_ATTEMPTS
#: when no cup colour of the train bands is clearly different from the drawn surfaces, the surfaces are redrawn (as in `indoor_yolo_dataset`)
MATERIAL_REDRAWS = 8
POOL_IDENTITY_FIELDS = frozenset({"proc_manifest_sha256", "cc0_pack_sha256", "split_seed", "split_assignment_sha256", "cup_rule_sha256"})
PLAN_FIELDS = frozenset({"kind", "schema_version", "rig", "layout", "seed", "nominal_share", "nominal_scene_sha256", "pool_identity",
                         "plan_sha256"})
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


def check_pools(inventory: dict | None = None) -> None:
    """Raise `AppearanceInvalid` unless the collected (train) pools are disjoint from the held-out assets and from the val and test pools, are
    inside the texture libraries, and none is empty. Without `inventory` the pools are those of the committed names (legacy and procedural)."""

    held = set(HELD_OUT["textures"])
    pools = inventory["pools"] if inventory is not None else indoor_assets.texture_pools()
    train = pools["train"]
    for surface in indoor_assets.SURFACES:
        pool = set(train[surface])
        if not pool:
            _fail("APPEARANCE_POOL_EMPTY", surface)
        if any(not indoor_assets.texture_allowed(surface, texture) for texture in pool):
            _fail("APPEARANCE_POOL_UNKNOWN_TEXTURE", surface)
        if pool & held:
            _fail("APPEARANCE_POOL_HELD_OUT_TEXTURE", surface)
        for split in ("val", "test"):
            if pool & set(pools[split][surface]):
                _fail("APPEARANCE_POOL_HELD_OUT_TEXTURE", f"{surface}: also in {split}")
    try:
        indoor_assets.check_held_out_outside_train(pools)
    except ValueError as error:
        _fail("APPEARANCE_POOL_HELD_OUT_TEXTURE" if "TEXTURE" in str(error) else "APPEARANCE_POOL_CUP", str(error))
    if not indoor_assets.hue_bands("train") or set(indoor_assets.hue_bands("train")) & set(HELD_OUT["cup_hue_bands"]):
        _fail("APPEARANCE_POOL_CUP")
    if TINT_BAND[0] < HELD_OUT["tint_below"]:
        _fail("APPEARANCE_POOL_TINT")
    if LAYOUT in HELD_OUT["layouts"]:
        _fail("APPEARANCE_POOL_LAYOUT")


def make_plan(*, seed: int, nominal_share: float = NOMINAL_SHARE_DEFAULT, nominal_scene_sha256: str, pool_identity: dict) -> dict:
    """The plan document, with its hash. `nominal_scene_sha256` is the sha256 of the installed `scene_side_wrist_indoor.xml`; `pool_identity` is
    `scene_inventory(...)["pool_identity"]` of the install the plan is made for (it is part of the hash)."""

    document = {"kind": PLAN_KIND, "schema_version": SCHEMA_VERSION, "rig": RIG, "layout": LAYOUT, "seed": seed,
                "nominal_share": nominal_share, "nominal_scene_sha256": nominal_scene_sha256, "pool_identity": pool_identity}
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
    identity = plan["pool_identity"]
    if not isinstance(identity, dict) or set(identity) != POOL_IDENTITY_FIELDS:
        _fail("APPEARANCE_PLAN_POOL_IDENTITY_INVALID")
    if type(identity["split_seed"]) is not int or identity["split_seed"] < 0:
        _fail("APPEARANCE_PLAN_POOL_IDENTITY_INVALID", "split_seed")
    for key in sorted(POOL_IDENTITY_FIELDS - {"split_seed"}):
        value = identity[key]
        if value is None and key in ("proc_manifest_sha256", "cc0_pack_sha256"):
            continue                      # a tree without that pool: the draws then use the other pools only
        if type(value) is not str or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            _fail("APPEARANCE_PLAN_POOL_IDENTITY_INVALID", key)
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if plan["plan_sha256"] != _sha256(body):
        _fail("APPEARANCE_PLAN_HASH_MISMATCH")
    check_pools()
    return json.loads(canonical(plan))


def _floats(text) -> list:
    return [float(item) for item in str(text).split()]


_VERIFIED_TEXTURES: dict = {}


def _read_manifest(path: Path):
    """`(manifest, sha256 of the file)`, or `(None, None)` when the install has no such manifest."""

    if not path.is_file():
        return None, None
    data = path.read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def _verify_installed_textures(textures: Path, proc_manifest, cc0_manifest) -> None:
    """Raise `AppearanceInvalid` unless every file of the pools the install claims is there and is the manifest's: the CC0 pack file by file (sha256
    of the resized file), the procedural PNGs by their PNG sha256, or, when only the bytes differ (another zlib), by the decoded pixels. Remembered per
    directory while no file's size or mtime changes (one pass of about 1 s per process)."""

    expected = [(textures / f"{entry['id']}.png", entry) for manifest in (proc_manifest, cc0_manifest) if manifest for entry in manifest["textures"]]
    signature = []
    for path, _entry in expected:
        try:
            stat = path.stat()
        except OSError:
            signature.append(None)
        else:
            signature.append((stat.st_size, stat.st_mtime_ns))
    key = (str(textures), tuple(signature))
    if key in _VERIFIED_TEXTURES:
        return
    for (path, entry), seen in zip(expected, signature):
        cc0 = entry["id"].startswith(indoor_assets.CC0_DIRECTORY + "/")
        if seen is None:
            _fail("APPEARANCE_CC0_PACK_MISSING" if cc0 else "APPEARANCE_PROC_TEXTURE_MISSING", entry["id"])
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if cc0:
            if digest != entry["sha256_resized"]:
                _fail("APPEARANCE_CC0_PACK_MISMATCH", entry["id"])
        elif digest != entry["png_sha256"]:
            import io

            import numpy as np
            from PIL import Image

            try:
                with Image.open(io.BytesIO(data)) as image:
                    pixels = np.ascontiguousarray(np.asarray(image.convert("RGB")))
            except (OSError, SyntaxError, ValueError):
                _fail("APPEARANCE_PROC_TEXTURE_MISMATCH", entry["id"] + " (not a readable PNG)")
            if indoor_assets.pixel_sha256(pixels) != entry["pixel_sha256"]:
                _fail("APPEARANCE_PROC_TEXTURE_MISMATCH", entry["id"])
    _VERIFIED_TEXTURES[key] = True


def pool_state(nominal_dir, *, verify_files: bool = False, files_dir=None) -> dict:
    """`{"pools": {split: {surface: [texture]}}, "means": {texture: mean sRGB}, "pool_identity": {...}}` of the textures next to `nominal_dir`.

    The manifests decide which procedural and CC0 textures exist (an install without `cc0-manifest.json` has no CC0 pool, and a plan made for one
    with it is refused). The CC0 pack must match its manifest: `pack_sha256` is recomputed from the manifest's file hashes. `verify_files` also
    checks every file of the install (`_verify_installed_textures`): the production readers ask for it, the offline tests of the draw do not.

    `files_dir` (an installed `assets/mujoco/act` directory) is where those files are checked when it is not `nominal_dir`: in a frozen run the
    manifests and the scene come from the frozen execution snapshot (`nominal_dir`, the authority: the freeze bound its bytes), which holds no
    generated PNGs, and the installed share's files must be the frozen manifests' files (path plus sha256)."""

    textures = Path(nominal_dir) / scene_variant.INDOOR_TEXTURE_DIRECTORY
    proc_manifest, proc_sha = _read_manifest(textures / indoor_assets.PROC_MANIFEST)
    cc0_manifest, _cc0_sha = _read_manifest(textures / indoor_assets.CC0_MANIFEST)
    cc0_pack = None
    if cc0_manifest is not None:
        cc0_pack = indoor_assets.cc0_pack_sha256(cc0_manifest)
        if cc0_manifest.get("pack_sha256") != cc0_pack:
            _fail("APPEARANCE_CC0_PACK_MANIFEST_INVALID", "pack_sha256 is not the hash of the manifest's file hashes")
    if verify_files:
        installed = textures if files_dir is None else Path(files_dir) / scene_variant.INDOOR_TEXTURE_DIRECTORY
        _verify_installed_textures(installed, proc_manifest, cc0_manifest)
    pools = indoor_assets.texture_pools(proc_manifest, cc0_manifest)
    means = dict(TEXTURE_MEAN_RGB)
    for manifest in (proc_manifest, cc0_manifest):
        for entry in (manifest or {}).get("textures", []):
            means[entry["id"]] = tuple(entry["mean_rgb"])
    identity = {"proc_manifest_sha256": proc_sha, "cc0_pack_sha256": cc0_pack, "split_seed": indoor_assets.MASTER_SEED,
                "split_assignment_sha256": indoor_assets.split_assignment_sha256(proc_manifest, cc0_manifest),
                "cup_rule_sha256": indoor_assets.cup_rule_sha256()}
    return {"pools": pools, "means": means, "pool_identity": identity}


def scene_inventory(nominal_dir, *, verify_files: bool = False, files_dir=None) -> dict:
    """The lights (nominal diffuse and direction), props and headlight of the installed indoor scene, and the scene file's sha256, plus the asset
    pools and their identity (`pool_state`).

    `nominal_dir` is the installed `assets/mujoco/act` directory (`scene_variant_run.nominal_dir(share)`). Every reader that draws or verifies
    for a real run passes `verify_files=True`."""

    state = pool_state(nominal_dir, verify_files=verify_files, files_dir=files_dir)
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
            "headlight": {"ambient": _floats(headlights[0].get("ambient")), "diffuse": _floats(headlights[0].get("diffuse"))},
            "pools": state["pools"], "means": state["means"], "pool_identity": state["pool_identity"]}


def _tint(seed: int, scene_id: str, surface: str, redraw: int = 0) -> list:
    axis = f"tint.{surface}" if not redraw else f"tint.{surface}.{redraw}"
    return [round(_between(*TINT_BAND, _unit(seed, scene_id, axis, channel)), 4) for channel in range(3)] + [1.0]


def _distance(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _surface_colour(texture: str, tint, means: dict) -> tuple:
    return indoor_assets.surface_colour(tint, means[texture])


def _cup(seed: int, scene_id: str, surfaces: dict, bands=None, *, redraw: int = 0, fail: bool = True):
    """`(label, rgba)`: the first of the bounded draws whose colour is in a hue band of the train split and is clearly different (OKLab) from the
    drawn wall, floor and table and from the red landing ring (`indoor_assets.cup_distinct`). The label is `hue-band-NN`. When none of the
    `MAX_CUP_DRAWS` is, the result is None, or `AppearanceInvalid` (`fail`; the caller redraws its surfaces up to `MATERIAL_REDRAWS` times first).

    The hue is uniform inside a train band, saturation and value are uniform in their ranges; the colour is rounded to 4 decimals first and
    then its band is read back, so a colour at a band edge cannot be drawn into a band the rounding moved it out of."""

    import colorsys

    bands = tuple(indoor_assets.hue_bands("train") if bands is None else bands)
    suffix = f".{redraw}" if redraw else ""
    for draw in range(MAX_CUP_DRAWS):
        band = _choice(bands, _unit(seed, scene_id, "cup.band" + suffix, 0, draw))
        hue = (band + _unit(seed, scene_id, "cup.hue" + suffix, 0, draw)) * 360.0 / indoor_assets.HUE_BAND_COUNT
        saturation = _between(*indoor_assets.SATURATION, _unit(seed, scene_id, "cup.saturation" + suffix, 0, draw))
        value = _between(*indoor_assets.VALUE, _unit(seed, scene_id, "cup.value" + suffix, 0, draw))
        rgba = [round(channel, 4) for channel in colorsys.hsv_to_rgb(hue / 360.0, saturation, value)] + [1.0]
        if indoor_assets.hue_band_of(rgba) in bands and indoor_assets.cup_distinct(rgba[:3], surfaces):
            return f"hue-band-{indoor_assets.hue_band_of(rgba):02d}", rgba
    if fail:
        _fail("APPEARANCE_CUP_ALWAYS_BLENDS", scene_id)
    return None


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
    train, means = inventory["pools"]["train"], inventory["means"]
    for redraw in range(MATERIAL_REDRAWS + 1):
        fields, textures = {}, {}
        for surface in indoor_assets.SURFACES:
            texture = _choice(train[surface], _unit(seed, scene_id, f"texture.{surface}", redraw))
            tint = _tint(seed, scene_id, surface, redraw)
            fields[f"{surface}.texture"], fields[f"{surface}.rgba"] = texture, tint
            textures[surface] = _surface_colour(texture, tint, means)
        cup = _cup(seed, scene_id, textures, redraw=redraw, fail=redraw == MATERIAL_REDRAWS)
        if cup is not None:
            break
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
    family, rgba = cup
    fields["cup_material.rgba"] = rgba
    return fields, family


def check_not_held_out(variant: dict, inventory: dict) -> None:
    """Raise `AppearanceInvalid` if a (normalised) variant names a texture outside the train pool of its surface (a held-out one, or any val or test
    texture), a tint below the band, or a cup colour outside the train hue bands (the held-out families, or any val or test band)."""

    fields = variant["set"]
    if variant.get("base") != scene_variant.BASE_INDOOR:
        _fail("APPEARANCE_VARIANT_BASE_INVALID")
    for surface in indoor_assets.SURFACES:
        texture = fields.get(f"{surface}.texture")
        if texture is not None and (texture in HELD_OUT["textures"] or texture not in inventory["pools"]["train"][surface]):
            _fail("APPEARANCE_HELD_OUT_TEXTURE", f"{surface}.texture={texture}")
        tint = fields.get(f"{surface}.rgba")
        if tint is not None and any(channel < HELD_OUT["tint_below"] for channel in tint[:3]):
            _fail("APPEARANCE_HELD_OUT_TINT", f"{surface}.rgba")
    cup = fields.get("cup_material.rgba")
    if cup is not None:
        band = indoor_assets.hue_band_of(cup)
        if band in HELD_OUT["cup_hue_bands"] or band not in indoor_assets.hue_bands("train"):
            _fail("APPEARANCE_HELD_OUT_CUP", f"hue band {band}")
        for family in HELD_OUT["cups"]:
            if all(abs(channel - reference) <= CUP_JITTER + 1e-9 for channel, reference in zip(cup[:3], CUP_FAMILIES[family])):
                _fail("APPEARANCE_HELD_OUT_CUP", family)


def derive(plan: dict, scene_id: str, inventory: dict) -> dict:
    """The appearance of one scene: `{"kind", "variant", ...}` (a nominal one has `variant` None), a pure function of (plan, scene id, inventory)."""

    plan = validate_plan(plan)
    scene_id = _scene_id(scene_id)
    if inventory["scene_sha256"] != plan["nominal_scene_sha256"]:
        _fail("APPEARANCE_NOMINAL_SCENE_MISMATCH", "the installed indoor scene is not the plan's")
    if inventory["pool_identity"] != plan["pool_identity"]:
        differing = sorted(key for key in POOL_IDENTITY_FIELDS if inventory["pool_identity"].get(key) != plan["pool_identity"].get(key))
        _fail("APPEARANCE_POOL_IDENTITY_MISMATCH", "the installed asset pools are not the plan's: " + ", ".join(differing))
    check_pools(inventory)
    kind = kind_for(plan, scene_id)
    variant, variant_digest, family = None, None, None
    if kind == KIND_RANDOMISED:
        fields, family = _variant_fields(plan, scene_id, inventory)
        document = {"schema_version": scene_variant.SCHEMA_VERSION, "kind": scene_variant.KIND, "name": f"p3-{scene_id}"[:64],
                    "base": scene_variant.BASE_INDOOR, "set": fields}
        variant = scene_variant.normalize_variant(document)
        check_not_held_out(variant, inventory)
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
