"""Evaluation-only visual variants of the side+wrist ACT scene (goal 35-R0, design 2026-10-23 "R0 实施方案").

`realize(nominal_dir, variant)` is a pure function: it reads the nominal scene (`scene_side_wrist.xml` and its robot MJCF) from
`nominal_dir`, applies the variant and returns the variant MJCF text, the applied values and a realized hash. It writes nothing.

Only rendering fields are editable, and the list is closed (anything else is refused):

    key_light.diffuse / key_light.dir               the one light of the scene
    headlight.ambient / .diffuse / .active          the MuJoCo headlight (`<visual><headlight>`)
    cup_material.rgba                               the `cup_orange` material (the cup's visual geoms only)
    table_material.rgba / .texture                  the table's visual geom: a colour, or a builtin texture
    side_camera.pos_delta_m / .quat_delta / .fovy   the fixed side camera: a world-frame shift, a rotation in the camera's own
                                                    frame (applied after the nominal orientation) and the vertical field of view

The wrist camera lives in the robot MJCF and is not touched. None of these fields enters the physics, which
`physics_fingerprint.py` proves for the compiled model.

A variant over the INDOOR nominal (`"base": "indoor"`, indoor scene design 2026-10-24, P1) has its own closed list, again rendering only:

    wall.texture / floor.texture / table.texture   a texture of the asset set (`WALL_TEXTURES`, `FLOOR_TEXTURES`, `TABLE_TEXTURES`)
    wall.rgba / floor.rgba / table.rgba            a tint, multiplied into the texture
    light.<name>.diffuse / .dir / .active          each light of the indoor scene (`key_light` and the `ind_*` lights)
    headlight.ambient / .diffuse / .active         the MuJoCo headlight
    prop.<geom>.visible                            0 hides, 1 shows an `ind_*` prop (never a wall, floor, ceiling or the desk)
    cup_material.rgba                              the `cup_orange` material (the cup's visual geoms only)

The cameras, every collision geom, masses, joints, friction and the timestep are not on the list, and `scene_variant_run` proves
that a realized indoor variant keeps the version 2 physics fingerprint of the nominal scene.

The variant MJCF is written by the caller into the run's own directory. Its `include` and its mesh directory are absolute paths into
`nominal_dir` (the mounted install), so nothing is copied and the geometry files are the installed ones. The realized hash does not
depend on where `nominal_dir` is: it covers the sha256 of the nominal files, the applied values and the variant text with the
directory replaced by a token.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

SCHEMA_VERSION = 1
KIND = "ACT_SCENE_VARIANT"
NOMINAL_SCENE = "scene_side_wrist.xml"
NOMINAL_ROBOT = "so101_side_wrist.xml"
DIRECTORY_TOKEN = "@NOMINAL_DIR@"
TEXTURES = ("checker", "gradient", "flat")
#: the value of `base` of a variant over the indoor nominal scene (a variant without `base` is over the side+wrist scene)
BASE_INDOOR = "indoor"
INDOOR_SCENE = "scene_side_wrist_indoor.xml"
#: where the indoor textures are, relative to the nominal directory (`assets/mujoco/act`)
INDOOR_TEXTURE_DIRECTORY = "../textures/indoor"
#: the texture asset set of each surface (`assets/mujoco/textures/indoor/manifest.json`)
WALL_TEXTURES = ("wall_white", "wall_grey", "wall_beige")
FLOOR_TEXTURES = ("floor_wood_light", "floor_tile_grey", "floor_parquet", "floor_carpet")
TABLE_TEXTURES = ("table_laminate", "cabinet_wood", "floor_wood_light", "floor_parquet", "metal_shelf")
#: surface -> (texture element, material element, its texture set)
_SURFACES = {"wall": ("t_wall", "m_wall", WALL_TEXTURES), "floor": ("t_floor", "m_floor", FLOOR_TEXTURES),
             "table": ("t_table", "m_table", TABLE_TEXTURES)}
#: the geoms of the room itself: never a prop, so never hidden
_STRUCTURE_PREFIXES = ("ind_wall", "ind_floor", "ind_ceiling", "ind_desk", "ind_ceil_light")
_INDOOR_FIXED = tuple(f"{surface}.{attribute}" for surface in _SURFACES for attribute in ("texture", "rgba")) + (
    "headlight.ambient", "headlight.diffuse", "headlight.active", "cup_material.rgba")
_LIGHT_FIELD = re.compile(r"light\.([a-z][a-z0-9_]*)\.(diffuse|dir|active)\Z")
_PROP_FIELD = re.compile(r"prop\.([a-z][a-z0-9_]*)\.visible\Z")
#: the largest edits the module accepts (the probe is small by design; a bigger edit is a different experiment)
MAX_CAMERA_SHIFT_M = 0.05
MAX_CAMERA_ROTATION_DEG = 10.0
FOVY_RANGE_DEG = (30.0, 100.0)

_FIELDS = ("key_light.diffuse", "key_light.dir", "headlight.ambient", "headlight.diffuse", "headlight.active",
           "cup_material.rgba", "table_material.rgba", "table_material.texture",
           "side_camera.pos_delta_m", "side_camera.quat_delta", "side_camera.fovy")
_TEXTURE_KEYS = {"builtin", "rgb1", "rgb2", "width", "height", "texrepeat"}


class SceneVariantRefused(ValueError):
    """The variant names a field outside the whitelist, or a value outside its range."""


def _numbers(name, value, count, low, high):
    if (not isinstance(value, (list, tuple)) or len(value) != count
            or any(type(item) not in (int, float) or not math.isfinite(item) for item in value)):
        raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {name}: need {count} finite numbers")
    if any(not low <= item <= high for item in value):
        raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {name}: outside [{low}, {high}]")
    return [float(item) for item in value]


def _unit_quaternion(name, value):
    quaternion = _numbers(name, value, 4, -1.0, 1.0)
    norm = math.sqrt(sum(item * item for item in quaternion))
    if abs(norm - 1.0) > 1e-6:
        raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {name}: not a unit quaternion")
    angle = math.degrees(2.0 * math.acos(min(1.0, abs(quaternion[0]))))
    if angle > MAX_CAMERA_ROTATION_DEG:
        raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {name}: rotation of {angle:.2f} deg exceeds {MAX_CAMERA_ROTATION_DEG}")
    return quaternion


def _zero_one(key, value):
    if type(value) is not int or value not in (0, 1):
        raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {key}: 0 or 1")
    return value


def _normalize_indoor_fields(fields) -> dict:
    """The validated `set` of a variant over the indoor nominal, in sorted key order (the light and prop names are checked when the
    variant is realized, against the lights and props of the nominal scene)."""
    out = {}
    for key, value in fields.items():
        light, prop = _LIGHT_FIELD.fullmatch(key), _PROP_FIELD.fullmatch(key)
        if key not in _INDOOR_FIXED and light is None and prop is None:
            raise SceneVariantRefused(f"SCENE_VARIANT_FIELD_REFUSED: {key}")
        surface, _, attribute = key.partition(".")
        if key in _INDOOR_FIXED and surface in _SURFACES:
            if attribute == "rgba":
                out[key] = _numbers(key, value, 4, 0.0, 1.0)
            elif not isinstance(value, str) or value not in _SURFACES[surface][2]:
                raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {key}: one of {_SURFACES[surface][2]}")
            else:
                out[key] = value
        elif key in ("headlight.ambient", "headlight.diffuse"):
            out[key] = _numbers(key, value, 3, 0.0, 1.0)
        elif key == "headlight.active":
            out[key] = _zero_one(key, value)
        elif key == "cup_material.rgba":
            out[key] = _numbers(key, value, 4, 0.0, 1.0)
        elif light is not None and light.group(2) == "diffuse":
            out[key] = _numbers(key, value, 3, 0.0, 4.0)
        elif light is not None and light.group(2) == "dir":
            direction = _numbers(key, value, 3, -1000.0, 1000.0)
            if math.sqrt(sum(item * item for item in direction)) < 1e-6:
                raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {key}: zero vector")
            out[key] = direction
        else:       # light.<name>.active or prop.<name>.visible
            out[key] = _zero_one(key, value)
    return {key: out[key] for key in sorted(out)}


def normalize_variant(document) -> dict:
    """The validated variant: `{"name", "set": {field: value}}` with canonical number types; raises `SceneVariantRefused`.

    A variant over the indoor nominal also carries `"base": "indoor"` (a variant without a base is over the side+wrist scene, and its
    normal form, its hash and its fields are exactly what they were before the indoor scene existed)."""

    keys = {"schema_version", "kind", "name", "set"}
    if isinstance(document, dict) and "base" in document:
        if document["base"] != BASE_INDOOR or not isinstance(document["base"], str):
            raise SceneVariantRefused("SCENE_VARIANT_BASE_INVALID")
        keys = keys | {"base"}
    if (not isinstance(document, dict) or set(document) != keys
            or document["schema_version"] != SCHEMA_VERSION or document["kind"] != KIND):
        raise SceneVariantRefused("SCENE_VARIANT_SHAPE_INVALID")
    name = document["name"]
    if not isinstance(name, str) or not name or len(name) > 64 or any(not (c.isalnum() or c in "._-") for c in name):
        raise SceneVariantRefused("SCENE_VARIANT_NAME_INVALID")
    fields = document["set"]
    if not isinstance(fields, dict) or not fields:
        raise SceneVariantRefused("SCENE_VARIANT_EMPTY")
    if "base" in keys:
        return {"name": name, "set": _normalize_indoor_fields(fields), "base": BASE_INDOOR}
    for key in fields:
        if key not in _FIELDS:
            raise SceneVariantRefused(f"SCENE_VARIANT_FIELD_REFUSED: {key}")
    out = {}
    for key, value in fields.items():
        if key == "key_light.diffuse":
            out[key] = _numbers(key, value, 3, 0.0, 4.0)
        elif key == "key_light.dir":
            direction = _numbers(key, value, 3, -1000.0, 1000.0)
            if math.sqrt(sum(item * item for item in direction)) < 1e-6:
                raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {key}: zero vector")
            out[key] = direction
        elif key in ("headlight.ambient", "headlight.diffuse"):
            out[key] = _numbers(key, value, 3, 0.0, 1.0)
        elif key == "headlight.active":
            if type(value) is not int or value not in (0, 1):
                raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {key}: 0 or 1")
            out[key] = value
        elif key in ("cup_material.rgba", "table_material.rgba"):
            out[key] = _numbers(key, value, 4, 0.0, 1.0)
        elif key == "table_material.texture":
            if (not isinstance(value, dict) or not {"builtin", "rgb1", "rgb2"} <= set(value) <= _TEXTURE_KEYS
                    or value["builtin"] not in TEXTURES):
                raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {key}: builtin one of {TEXTURES}, rgb1, rgb2")
            texture = {"builtin": value["builtin"], "rgb1": _numbers(key + ".rgb1", value["rgb1"], 3, 0.0, 1.0),
                       "rgb2": _numbers(key + ".rgb2", value["rgb2"], 3, 0.0, 1.0)}
            for size in ("width", "height"):
                item = value.get(size, 128)
                if type(item) is not int or not 8 <= item <= 1024:
                    raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {key}.{size}")
                texture[size] = item
            texture["texrepeat"] = _numbers(key + ".texrepeat", value.get("texrepeat", [1.0, 1.0]), 2, 0.0, 64.0)
            out[key] = texture
        elif key == "side_camera.pos_delta_m":
            out[key] = _numbers(key, value, 3, -MAX_CAMERA_SHIFT_M, MAX_CAMERA_SHIFT_M)
        elif key == "side_camera.quat_delta":
            out[key] = _unit_quaternion(key, value)
        elif key == "side_camera.fovy":
            if type(value) not in (int, float) or not FOVY_RANGE_DEG[0] <= value <= FOVY_RANGE_DEG[1]:
                raise SceneVariantRefused(f"SCENE_VARIANT_VALUE_INVALID: {key}: outside {FOVY_RANGE_DEG}")
            out[key] = float(value)
    return {"name": name, "set": {key: out[key] for key in _FIELDS if key in out}}


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def variant_sha256(variant: dict) -> str:
    """The hash of the validated variant (name and values)."""
    return hashlib.sha256(canonical(variant)).hexdigest()


def _text(values) -> str:
    return " ".join(format(float(item), ".10g") for item in values)


def _floats(text) -> list:
    return [float(item) for item in str(text).split()]


def quaternion_multiply(a, b) -> list:
    """Hamilton product `a * b` of two (w, x, y, z) quaternions."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return [aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw]


def quaternion_about(axis, degrees) -> list:
    """The (w, x, y, z) quaternion of a rotation by `degrees` about `axis` (not required to be a unit vector)."""
    norm = math.sqrt(sum(item * item for item in axis))
    if norm < 1e-12:
        raise SceneVariantRefused("SCENE_VARIANT_VALUE_INVALID: rotation axis is zero")
    half = math.radians(degrees) / 2.0
    return [math.cos(half), *(math.sin(half) * item / norm for item in axis)]


@dataclass(frozen=True)
class RealizedScene:
    name: str
    variant: dict
    variant_sha256: str
    xml_text: str
    xml_tokenized: str
    applied: dict
    realized_sha256: str

    def document(self) -> dict:
        """What a run records: the variant, the values that took effect and the two hashes."""
        return {"name": self.name, "variant": self.variant, "variant_sha256": self.variant_sha256, "applied": self.applied,
                "realized_sha256": self.realized_sha256}


def _sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _find(root, tag, name):
    found = [item for item in root.iter(tag) if item.get("name") == name]
    if len(found) != 1:
        raise SceneVariantRefused(f"SCENE_VARIANT_NOMINAL_DRIFT: {tag} {name!r} found {len(found)} times in the nominal scene")
    return found[0]


def _apply_indoor(root, fields, record) -> dict:
    """Apply the fields of a variant over the indoor nominal to the parsed scene `root`; return `{texture name: relative path}` of
    the library textures the variant names. Every texture path of the scene is made token-relative, so the realized scene can sit
    in any run directory (its `include` and mesh directory are rewritten by the caller in the same way)."""
    for item in root.iter("texture"):
        if item.get("file") is not None:
            item.set("file", DIRECTORY_TOKEN + "/" + item.get("file"))
    lights = {item.get("name"): item for item in root.iter("light")
              if item.get("name") == "key_light" or (item.get("name") or "").startswith("ind_")}
    props = {item.get("name"): item for item in root.iter("geom")
             if (item.get("name") or "").startswith("ind_") and not item.get("name").startswith(_STRUCTURE_PREFIXES)}
    named = {}
    for key, value in fields.items():
        surface, _, attribute = key.partition(".")
        light, prop = _LIGHT_FIELD.fullmatch(key), _PROP_FIELD.fullmatch(key)
        if surface in _SURFACES and key in _INDOOR_FIXED:
            texture_name, material_name, _library = _SURFACES[surface]
            if attribute == "texture":
                texture = _find(root, "texture", texture_name)
                nominal = Path(texture.get("file")).stem
                record(key, nominal, value)
                relative = f"{INDOOR_TEXTURE_DIRECTORY}/{value}.png"
                texture.set("file", DIRECTORY_TOKEN + "/" + relative)
                named[value] = relative
            else:
                material = _find(root, "material", material_name)
                record(key, _floats(material.get("rgba")), value)
                material.set("rgba", _text(value))
        elif key.startswith("headlight."):
            headlights = [item for visual in root.iter("visual") for item in visual.findall("headlight")]
            if len(headlights) != 1:
                raise SceneVariantRefused("SCENE_VARIANT_NOMINAL_DRIFT: the indoor scene needs exactly one headlight")
            attribute = key.split(".", 1)[1]
            nominal = int(headlights[0].get("active", "1")) if attribute == "active" else _floats(headlights[0].get(attribute))
            record(key, nominal, value)
            headlights[0].set(attribute, str(value) if attribute == "active" else _text(value))
        elif key == "cup_material.rgba":
            material = _find(root, "material", "cup_orange")
            record(key, _floats(material.get("rgba")), value)
            material.set("rgba", _text(value))
        elif light is not None:
            element = lights.get(light.group(1))
            if element is None:
                raise SceneVariantRefused(f"SCENE_VARIANT_FIELD_REFUSED: {key}: the indoor scene has no such light")
            attribute = light.group(2)
            if attribute == "diffuse":
                record(key, _floats(element.get("diffuse", "0.7 0.7 0.7")), value)
                element.set("diffuse", _text(value))
            elif attribute == "dir":
                record(key, _floats(element.get("dir", "0 0 -1")), value)
                element.set("dir", _text(value))
            else:
                record(key, 0 if element.get("active") == "false" else 1, value)
                element.set("active", "true" if value else "false")
        else:
            element = props.get(prop.group(1))
            if element is None:
                raise SceneVariantRefused(f"SCENE_VARIANT_FIELD_REFUSED: {key}: not a prop of the indoor scene")
            record(key, 0 if element.get("rgba") == "0 0 0 0" else 1, value)
            if not value:
                # alpha 0 hides the geom (the way the collision geoms of the scene are hidden) and group 4 is off in the default view
                element.set("rgba", "0 0 0 0")
                element.set("group", "4")
    return named


def realize(nominal_dir, variant_document) -> RealizedScene:
    """The variant scene of `variant_document` over the nominal scene in `nominal_dir` (a pure function: nothing is written)."""

    variant = normalize_variant(variant_document)
    nominal_dir = Path(nominal_dir)
    indoor = variant.get("base") == BASE_INDOOR
    scene_name = INDOOR_SCENE if indoor else NOMINAL_SCENE
    scene_path, robot_path = nominal_dir / scene_name, nominal_dir / NOMINAL_ROBOT
    if not scene_path.is_file() or not robot_path.is_file():
        raise SceneVariantRefused("SCENE_VARIANT_NOMINAL_MISSING")
    root = ElementTree.fromstring(scene_path.read_bytes())
    applied = {}
    fields = variant["set"]

    def record(key, nominal, value):
        applied[key] = {"nominal": nominal, "value": value}

    texture_files = {}
    if indoor:
        texture_files = _apply_indoor(root, fields, record)
    else:
        if "key_light.diffuse" in fields or "key_light.dir" in fields:
            light = _find(root, "light", "key_light")
            if "key_light.diffuse" in fields:
                record("key_light.diffuse", _floats(light.get("diffuse", "0.7 0.7 0.7")), fields["key_light.diffuse"])
                light.set("diffuse", _text(fields["key_light.diffuse"]))
            if "key_light.dir" in fields:
                record("key_light.dir", _floats(light.get("dir", "0 0 -1")), fields["key_light.dir"])
                light.set("dir", _text(fields["key_light.dir"]))
        headlight_keys = [key for key in fields if key.startswith("headlight.")]
        if headlight_keys:
            visual = root.find("visual")
            if visual is None:
                visual = ElementTree.SubElement(root, "visual")
            headlight = visual.find("headlight")
            if headlight is not None:
                raise SceneVariantRefused("SCENE_VARIANT_NOMINAL_DRIFT: the nominal scene declares a headlight")
            headlight = ElementTree.SubElement(visual, "headlight")
            defaults = {"ambient": [0.1, 0.1, 0.1], "diffuse": [0.4, 0.4, 0.4], "active": 1}
            for key in headlight_keys:
                attribute = key.split(".", 1)[1]
                record(key, defaults[attribute], fields[key])
                headlight.set(attribute, str(fields[key]) if attribute == "active" else _text(fields[key]))
        if "cup_material.rgba" in fields:
            material = _find(root, "material", "cup_orange")
            record("cup_material.rgba", _floats(material.get("rgba")), fields["cup_material.rgba"])
            material.set("rgba", _text(fields["cup_material.rgba"]))
        if "table_material.rgba" in fields or "table_material.texture" in fields:
            table = _find(root, "geom", "table_visual")
            asset = root.find("asset")
            nominal = _floats(table.get("rgba"))
            rgba = fields.get("table_material.rgba", [1.0, 1.0, 1.0, 1.0] if "table_material.texture" in fields else nominal)
            if "table_material.rgba" in fields:
                record("table_material.rgba", nominal, rgba)
            if "table_material.texture" in fields:
                texture = fields["table_material.texture"]
                record("table_material.texture", None, texture)
                ElementTree.SubElement(asset, "texture", {
                    "name": "table_variant_texture", "type": "2d", "builtin": texture["builtin"], "rgb1": _text(texture["rgb1"]),
                    "rgb2": _text(texture["rgb2"]), "width": str(texture["width"]), "height": str(texture["height"])})
                ElementTree.SubElement(asset, "material", {
                    "name": "table_variant_material", "texture": "table_variant_texture", "rgba": _text(rgba),
                    "texrepeat": _text(texture["texrepeat"])})
            else:
                ElementTree.SubElement(asset, "material", {"name": "table_variant_material", "rgba": _text(rgba)})
            table.attrib.pop("rgba", None)      # a geom colour would override the material
            table.set("material", "table_variant_material")
        camera_keys = [key for key in fields if key.startswith("side_camera.")]
        if camera_keys:
            camera = _find(root, "camera", "side_camera")
            if "side_camera.pos_delta_m" in fields:
                position = _floats(camera.get("pos"))
                moved = [a + b for a, b in zip(position, fields["side_camera.pos_delta_m"], strict=True)]
                record("side_camera.pos", position, moved)
                camera.set("pos", _text(moved))
            if "side_camera.quat_delta" in fields:
                quaternion = _floats(camera.get("quat"))
                norm = math.sqrt(sum(item * item for item in quaternion))
                quaternion = [item / norm for item in quaternion]
                turned = quaternion_multiply(quaternion, fields["side_camera.quat_delta"])
                record("side_camera.quat", quaternion, turned)
                camera.set("quat", _text(turned))
            if "side_camera.fovy" in fields:
                record("side_camera.fovy", float(camera.get("fovy")), fields["side_camera.fovy"])
                camera.set("fovy", format(fields["side_camera.fovy"], ".10g"))
    include = [item for item in root.iter("include")]
    if len(include) != 1 or include[0].get("file") != NOMINAL_ROBOT:
        raise SceneVariantRefused("SCENE_VARIANT_NOMINAL_DRIFT: the nominal scene does not include its robot file once")
    include[0].set("file", DIRECTORY_TOKEN + "/" + NOMINAL_ROBOT)
    if root.find("compiler") is not None:
        raise SceneVariantRefused("SCENE_VARIANT_NOMINAL_DRIFT: the nominal scene declares a compiler")
    root.insert(0, ElementTree.Element("compiler", {"meshdir": DIRECTORY_TOKEN}))
    tokenized = ElementTree.tostring(root, encoding="unicode")
    digest = variant_sha256(variant)
    nominal_files = {scene_name: _sha256_file(scene_path), NOMINAL_ROBOT: _sha256_file(robot_path)}
    identity = {"schema_version": SCHEMA_VERSION, "nominal": nominal_files, "applied": applied,
                "xml_sha256": hashlib.sha256(tokenized.encode("utf-8")).hexdigest()}
    if indoor:
        # the bytes of every texture the variant names are part of what was realized (a texture is an asset with an identity)
        identity["textures"] = {name: _sha256_file(nominal_dir / relative) for name, relative in sorted(texture_files.items())}
    realized = hashlib.sha256(canonical(identity)).hexdigest()
    return RealizedScene(name=variant["name"], variant=variant, variant_sha256=digest,
                         xml_text=tokenized.replace(DIRECTORY_TOKEN, str(nominal_dir)), xml_tokenized=tokenized, applied=applied,
                         realized_sha256=realized)
