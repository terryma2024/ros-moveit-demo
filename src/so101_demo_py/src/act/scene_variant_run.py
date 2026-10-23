"""A scene variant in a run: the variant file, its record, the scene a shard loads, and the identity entry (goal 35-R0).

The Host reads the variant file once (`host_record`): it validates it, realizes it over the nominal scene of the mounted install and
proves that the physics fingerprint of the variant equals the nominal one. The run binds the variant file, the realized hash and the
fingerprint into its identity. Each shard (`prepare_shard_scene`) realizes the same file into its OWN directory, proves the same two
facts again, compares the realized hash with the Host's, and hands the stack that file as its `mujoco_scene`. The contact-activation
receipt stays on the nominal installed files: nothing in this module touches it.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from .physics_fingerprint import physics_fingerprint_of_file
from .scene_variant import (
    KIND, NOMINAL_SCENE, SCHEMA_VERSION, SceneVariantRefused, normalize_variant, realize)

SCENE_DIRECTORY = "scene-variant"
SCENE_FILE = "scene_variant.xml"
RECORD_FILE = "scene-variant-realized.json"
_HEX64 = "0123456789abcdef"


def nominal_dir(share) -> Path:
    """The directory of the nominal side+wrist scene under a package share directory."""
    return Path(share) / "assets" / "mujoco" / "act"


def file_ref(path) -> dict:
    """`{"path", "sha256"}` of a file, the reference form every run input has."""
    target = Path(path)
    return {"path": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SceneVariantRefused("SCENE_VARIANT_FILE_INVALID: duplicate key " + key)
        result[key] = value
    return result


def _refuse_constant(_name):
    raise SceneVariantRefused("SCENE_VARIANT_FILE_INVALID: non-finite number")


def read_variant_file(path) -> dict:
    """The validated variant of a JSON file; `SceneVariantRefused` for anything that is not a well-formed whitelisted variant."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates,
                              parse_constant=_refuse_constant)
    except (OSError, ValueError) as error:
        if isinstance(error, SceneVariantRefused):
            raise
        raise SceneVariantRefused("SCENE_VARIANT_FILE_INVALID: " + type(error).__name__) from error
    return normalize_variant(document)


def _document(variant: dict) -> dict:
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "name": variant["name"], "set": variant["set"]}


def realize_into(directory, share, variant: dict) -> dict:
    """Realize `variant` into `directory` (created if absent), check the physics, and return the full record.

    The scene file stays only when the variant's physics fingerprint equals the nominal one; otherwise nothing is left behind."""
    realized = realize(nominal_dir(share), _document(variant))
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    scene = target / SCENE_FILE
    scene.write_text(realized.xml_text, encoding="utf-8")
    try:
        nominal = physics_fingerprint_of_file(nominal_dir(share) / NOMINAL_SCENE)
        variant_print = physics_fingerprint_of_file(scene)
        if variant_print != nominal:
            raise SceneVariantRefused("SCENE_VARIANT_PHYSICS_MISMATCH: the variant changes the physics of the scene")
    except BaseException:
        scene.unlink(missing_ok=True)
        raise
    return {**realized.document(), "scene_path": str(scene), "physics_fingerprint": variant_print,
            "nominal_physics_fingerprint": nominal}


def identity_entry(record: dict) -> dict:
    """What the run identity binds: the variant's name and hashes (the values are in the record and in the variant file)."""
    return {"name": record["name"], "variant_sha256": record["variant_sha256"], "realized_sha256": record["realized_sha256"],
            "physics_fingerprint": record["physics_fingerprint"]}


def host_record(path, share) -> dict:
    """The Host's record of a variant file: realized and checked in a scratch directory that is removed again."""
    variant = read_variant_file(path)
    with tempfile.TemporaryDirectory(prefix="so101-scene-variant-") as scratch:
        record = realize_into(Path(scratch) / SCENE_DIRECTORY, share, variant)
    record = {key: value for key, value in record.items() if key != "scene_path"}
    record["file"] = file_ref(path)
    return record


def bind_variant(path, share, identity: dict):
    """The Host record of the variant file `path` (None: no variant), with its identity entry added to `identity`."""
    if path is None:
        return None
    record = host_record(path, share)
    identity["scene_variant"] = identity_entry(record)
    return record


def spec_entry(record: dict) -> dict:
    """The closed `scene_variant` entry of a rollout shard spec."""
    return {"file": dict(record["file"]), "realized_sha256": record["realized_sha256"],
            "physics_fingerprint": record["physics_fingerprint"]}


def valid_spec_entry(entry) -> bool:
    """Whether `entry` has the shape of `spec_entry` (the file itself is read back by the shard)."""
    try:
        file = entry["file"]
        return (type(entry) is dict and set(entry) == {"file", "realized_sha256", "physics_fingerprint"}
                and type(file) is dict and set(file) == {"path", "sha256"} and type(file["path"]) is str
                and file["path"].startswith("/") and ".." not in Path(file["path"]).parts
                and all(type(value) is str and len(value) == 64 and set(value) <= set(_HEX64)
                        for value in (file["sha256"], entry["realized_sha256"], entry["physics_fingerprint"])))
    except (KeyError, TypeError):
        return False


def prepare_shard_scene(spec: dict, share):
    """`(scene_path, record)` of the variant a shard spec names, realized into the shard's owned root; `(None, None)` without one."""
    entry = spec.get("scene_variant")
    if entry is None:
        return None, None
    if not valid_spec_entry(entry):
        raise SceneVariantRefused("SCENE_VARIANT_SPEC_INVALID")
    path = Path(entry["file"]["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["file"]["sha256"]:
        raise SceneVariantRefused("SCENE_VARIANT_FILE_DRIFT")
    root = Path(spec["owned_root"])
    record = realize_into(root / SCENE_DIRECTORY, share, read_variant_file(path))
    if record["realized_sha256"] != entry["realized_sha256"] or record["physics_fingerprint"] != entry["physics_fingerprint"]:
        Path(record["scene_path"]).unlink(missing_ok=True)
        raise SceneVariantRefused("SCENE_VARIANT_REALIZED_MISMATCH: the shard realized another scene than the Host did")
    (root / RECORD_FILE).write_text(json.dumps(record, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return Path(record["scene_path"]), record
