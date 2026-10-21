"""The scene-list JSON of the container campaigns: row shape, plain decimals and exclusive writes (pure helpers).

The format is the one of ``formal-side-wrist-103.scenes.json`` and ``debug-16.scenes.json``: a top-level object with
``kind``, ``schema_version``, ``list``, ``cup_z_m`` and ``scenarios``; each row has ``scene_id``, ``seed``, ``split`` and
``cup_position_world_m`` (x, y, z).  ``parallel_collection_contracts.scene_ids`` only requires the rows, a non-empty
``split`` string and an identifier ``scene_id``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

KIND = "ACT_CONTAINER_SCENE_MANIFEST"
SCHEMA_VERSION = 1
CUP_Z_M = 0.165
_EXPONENT = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?[eE][-+]?\d+")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def plain_decimal_json(document: object, **options: object) -> str:
    """``json.dumps`` with every exponent number written as a plain six-decimal number."""

    text = _EXPONENT.sub(lambda match: format(float(match.group(0)), ".6f"), json.dumps(document, **options))
    if _EXPONENT.search(text):
        raise ValueError("SCENE_LIST_EXPONENT_REMAINS")
    return text


def scene_row(scene_id: str, seed: int, split: str, xy: tuple[float, float], cup_z_m: float = CUP_Z_M) -> dict:
    if not _IDENTIFIER.fullmatch(scene_id) or not split or type(seed) is not int:
        raise ValueError("SCENE_ROW_INVALID")
    return {
        "scene_id": scene_id,
        "seed": seed,
        "split": split,
        "cup_position_world_m": [float(xy[0]), float(xy[1]), float(cup_z_m)],
    }


def scene_document(list_name: str, rows: list[dict], *, cup_z_m: float = CUP_Z_M, **extra: object) -> dict:
    ids = [row["scene_id"] for row in rows]
    if not rows or len(set(ids)) != len(ids) or len({row["seed"] for row in rows}) != len(rows):
        raise ValueError("SCENE_LIST_INVALID")
    document = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "list": list_name,
        "cup_z_m": cup_z_m,
        "scenarios": rows,
    }
    document.update(extra)
    return document


def read_scene_rows(path: Path) -> list[dict]:
    document = json.loads(Path(path).read_text())
    rows = document.get("scenarios") if isinstance(document, dict) else None
    if not isinstance(rows, list) or not rows or document.get("kind") != KIND:
        raise ValueError("SCENE_LIST_INVALID")
    return rows


def write_new_json(path: Path, document: object) -> None:
    """Write ``document`` once, atomically; never over an existing file or link."""

    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError(f"OUTPUT_EXISTS: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.partial")
    temporary.write_text(plain_decimal_json(document, sort_keys=True, indent=2) + "\n")
    os.link(temporary, path)
    temporary.unlink()
