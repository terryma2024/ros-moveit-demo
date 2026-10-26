"""The appearance and Teacher source of one scene, read from the scene list a frozen input set binds (indoor P3).

The scene list is bound into `inputs_sha256` (`diagnostic_episode_inputs.SCENE_MANIFEST_PATH`), so what its rows say is frozen with the
inputs. A list built for an appearance plan carries the plan at the top (`appearance_plan`) and, in every row, the derived `appearance` and
`teacher_source`. The shard (before it switches the stack), the Teacher child (before it moves) and the offline processor (when it opens the
episode) all read the same row through `scene_entry`, and each re-derives it from the plan: a row that is not the derivation of its scene
id is refused (`appearance_plan.verify_row`). A list without a plan has no appearance and no Teacher source, and every row of it must say
so: `appearance` or `teacher_source` in a row without a plan is a refusal, never a silent default.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import appearance_plan as ap
from .diagnostic_episode_inputs import SCENE_MANIFEST_PATH, frozen_scene_rows

PLAN_KEY = "appearance_plan"


def scene_document(frozen: dict, manifest_path) -> dict:
    """The bound scene list as a document (its rows were re-hashed and re-read by `frozen_scene_rows` first)."""

    manifest_path = Path(manifest_path)
    frozen_scene_rows(frozen, manifest_path)                  # the binding's size, hash and row count are verified here
    payload = (manifest_path.parent / SCENE_MANIFEST_PATH).read_bytes()
    if hashlib.sha256(payload).hexdigest() != frozen["scene_manifest"]["sha256"]:
        raise ValueError("INPUTS_SCENE_MANIFEST_INVALID")
    return json.loads(payload)


#: the files of the execution snapshot that decide the appearance pools: the pool manifests and the indoor scene (all bound by the freeze)
_SNAPSHOT_POOL_FILES = ("assets/mujoco/textures/indoor/" + ap.indoor_assets.PROC_MANIFEST,
                        "assets/mujoco/textures/indoor/" + ap.indoor_assets.CC0_MANIFEST,
                        "assets/mujoco/act/" + ap.scene_variant.INDOOR_SCENE)


def frozen_inventory(frozen: dict, manifest_path, installed_share, *, verify_files: bool = True) -> dict:
    """The appearance inventory of a frozen run: the scene, the pool manifests (so the pool identity) and the splits come from the FROZEN
    execution snapshot of `frozen` (`frozen["execution_snapshot"]`, next to `manifest_path`), the texture files are verified in the INSTALLED share
    `installed_share` against those frozen manifests, path plus sha256 (`appearance_plan.scene_inventory(files_dir=...)`).

    The snapshot holds the committed manifests and the legacy PNGs, never the 250 MB of generated textures, so its own files cannot be verified
    (EXP-7033). The authority stays the frozen pool identity: `derive` refuses a plan whose `pool_identity` differs from it. The snapshot's manifests
    and scene are compared with the file hashes its freeze recorded (`execution-manifest.json`, whose hash is the binding's), so a changed snapshot is
    refused (`APPEARANCE_FROZEN_SNAPSHOT_MISMATCH`). A freeze without an execution snapshot binding has no frozen manifests: the installed share is
    then the only source and is verified as before.
    """

    installed = Path(installed_share) / "assets/mujoco/act"
    binding = frozen.get("execution_snapshot")
    if binding is None:
        return ap.scene_inventory(installed, verify_files=verify_files)
    path = binding.get("path") if isinstance(binding, dict) else None
    if type(path) is not str or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        raise ap.AppearanceInvalid("APPEARANCE_FROZEN_SNAPSHOT_PATH_INVALID")
    root = Path(manifest_path).parent / path
    descriptor_path = root / "execution-manifest.json"
    if not descriptor_path.is_file() or not (root / _SNAPSHOT_POOL_FILES[2]).is_file():
        raise ap.AppearanceInvalid("APPEARANCE_FROZEN_SNAPSHOT_MISSING: " + str(path))
    try:
        descriptor = json.loads(descriptor_path.read_bytes())
        recorded = descriptor["files"]
        bound = descriptor["snapshot_sha256"]
    except (ValueError, KeyError, TypeError) as error:
        raise ap.AppearanceInvalid("APPEARANCE_FROZEN_SNAPSHOT_MISMATCH: unreadable execution-manifest.json") from error
    if bound != binding.get("sha256"):
        raise ap.AppearanceInvalid("APPEARANCE_FROZEN_SNAPSHOT_MISMATCH: the execution manifest is not the bound one")
    for relative in _SNAPSHOT_POOL_FILES:
        target = root / relative
        if not target.is_file():
            continue                                        # no CC0 manifest: a pool-less snapshot, the identity says so
        entry = recorded.get(relative) if isinstance(recorded, dict) else None
        if not isinstance(entry, dict) or entry.get("sha256") != hashlib.sha256(target.read_bytes()).hexdigest():
            raise ap.AppearanceInvalid("APPEARANCE_FROZEN_SNAPSHOT_MISMATCH: " + relative)
    return ap.scene_inventory(root / "assets/mujoco/act", verify_files=verify_files, files_dir=installed)


def scene_entry(frozen: dict, manifest_path, scene_id: str, *, inventory=None):
    """`None` for a scene list without an appearance plan, else `{"plan", "appearance", "teacher_source", "row"}` for `scene_id`.

    `inventory` is `appearance_plan.scene_inventory(<installed act assets>)` of the host that reads (the plan names the sha256 of the
    scene file it was made for), or a callable returning it; it is required when the list has a plan."""

    document = scene_document(frozen, manifest_path)
    rows = {row["scene_id"]: row for row in document["scenarios"]}
    if scene_id not in rows:
        raise ValueError("APPEARANCE_SCENE_NOT_IN_LIST: " + scene_id)
    row = rows[scene_id]
    if PLAN_KEY not in document:
        if "appearance" in row or "teacher_source" in row:
            raise ap.AppearanceInvalid("APPEARANCE_ROW_WITHOUT_PLAN: " + scene_id)
        return None
    if inventory is None:
        raise ap.AppearanceInvalid("APPEARANCE_INVENTORY_REQUIRED")
    if callable(inventory):
        inventory = inventory()
    plan = ap.validate_plan(document[PLAN_KEY])
    for other in document["scenarios"]:         # every row of the list is the plan's, not only the one asked for
        ap.verify_row(plan, other, inventory)
    return {"plan": plan, "appearance": row["appearance"], "teacher_source": row["teacher_source"], "row": row}


def identity_record(entry: dict, *, realized: dict | None) -> dict:
    """The `scene_appearance` record of an episode identity: the plan and the draw, plus what realizing the variant gave (None: a nominal episode)."""

    appearance = entry["appearance"]
    record = {"plan_sha256": appearance["plan_sha256"], "kind": appearance["kind"], "layout": appearance["layout"],
              "draw_sha256": appearance["draw_sha256"], "variant_sha256": appearance["variant_sha256"],
              "cup_family": appearance["cup_family"], "variant_name": None if appearance["variant"] is None else appearance["variant"]["name"]}
    if realized is not None:
        record.update(realized_sha256=realized["realized_sha256"], physics_fingerprint=realized["physics_fingerprint"],
                      fingerprint_version=realized["fingerprint_version"],
                      nominal_physics_fingerprint=realized["nominal_physics_fingerprint"])
    return record
