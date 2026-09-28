"""Task 11A: partition a frozen manifest into fixed, ordered waves.

The wave boundary is the unit of recovery: a wave is re-entered whole or not at all, and the manifest
order is preserved so a wave record can be compared against the manifest without re-sorting.
"""

from __future__ import annotations


def partition_waves(scene_ids, *, max_wave_size: int = 20) -> tuple:
    """Split `scene_ids` into consecutive waves of at most `max_wave_size`, preserving order.

    Duplicates are refused rather than partitioned: a scene appearing twice in one campaign would make
    a wave record ambiguous and could collect the same scene under two attempts.
    """

    try:
        ids = tuple(scene_ids)
    except TypeError as error:
        raise ValueError("WAVE_MANIFEST_INVALID") from error
    if type(max_wave_size) is not int or max_wave_size < 1:
        raise ValueError("WAVE_SIZE_INVALID")
    if not ids:
        raise ValueError("WAVE_MANIFEST_EMPTY")
    if any(not isinstance(scene_id, str) or not scene_id for scene_id in ids):
        raise ValueError("WAVE_MANIFEST_INVALID")
    if len(set(ids)) != len(ids):
        raise ValueError("WAVE_SCENE_DUPLICATE")
    return tuple(ids[start:start + max_wave_size] for start in range(0, len(ids), max_wave_size))


QUALIFICATION_KINDS = frozenset({"W1", "W2", "W8"})
_W8_SCENES = 40


def create_qualification_contract(path, *, payload: dict, kind: str) -> str:
    """Atomically create the qualification contract BEFORE any spawn, or refuse.

    An existing or non-persistable path is a refusal, never an overwrite: a second campaign must not
    inherit or silently replace another run's qualification evidence.
    """

    import json
    import os
    from pathlib import Path as _Path

    if kind not in QUALIFICATION_KINDS:
        raise ValueError("QUALIFICATION_KIND_INVALID")
    if not isinstance(payload, dict) or not payload:
        raise ValueError("QUALIFICATION_PAYLOAD_INVALID")
    target = _Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("QUALIFICATION_CONTRACT_EXISTS")
    parent = target.parent
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        raise ValueError("QUALIFICATION_CONTRACT_NOT_PERSISTABLE")
    document = {"schema_version": 1, "kind": kind, **payload}
    temporary = target.with_name(target.name + ".partial")
    with open(temporary, "w") as handle:
        handle.write(json.dumps(document, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(target)
    return str(target)


def write_campaign_index(path, *, waves, qualification: bool) -> str:
    """Atomically publish the campaign index: the wave partition and what it was for."""

    import json
    import os
    from pathlib import Path as _Path

    partition = tuple(tuple(wave) for wave in waves)
    if not partition or any(not wave for wave in partition):
        raise ValueError("CAMPAIGN_INDEX_INVALID")
    if type(qualification) is not bool:
        raise ValueError("CAMPAIGN_INDEX_INVALID")
    target = _Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("CAMPAIGN_INDEX_EXISTS")
    if not target.parent.is_dir():
        raise ValueError("CAMPAIGN_INDEX_INVALID")
    document = {"schema_version": 1, "kind": "act_collection_campaign_index",
                "qualification": qualification,
                "waves": [{"wave_index": index, "scene_ids": list(wave)}
                          for index, wave in enumerate(partition)],
                "scene_count": sum(len(wave) for wave in partition)}
    temporary = target.with_name(target.name + ".partial")
    with open(temporary, "w") as handle:
        handle.write(json.dumps(document, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(target)
    return str(target)


def require_collection_mode(*, manifest_kind: str, qualification_mode: bool, contract=None) -> None:
    """Qualification runs accept W1/W2/W8; a formal run must be exact W8 under a live 40-scene gate."""

    if type(qualification_mode) is not bool:
        raise ValueError("COLLECTION_QUALIFICATION_MODE_INVALID")
    if qualification_mode:
        if manifest_kind not in QUALIFICATION_KINDS:
            raise ValueError("QUALIFICATION_MANIFEST_KIND_INVALID")
        return
    if manifest_kind != "W8":
        raise ValueError("FORMAL_MANIFEST_NOT_EXACT_W8")
    if not isinstance(contract, dict) or contract.get("revoked") is not False:
        raise ValueError("FORMAL_QUALIFICATION_CONTRACT_MISSING_OR_REVOKED")
    if contract.get("scenes") != _W8_SCENES:
        raise ValueError("FORMAL_QUALIFICATION_SCENE_COUNT_INVALID")
