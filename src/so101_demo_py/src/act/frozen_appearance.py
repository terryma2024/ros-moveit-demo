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
