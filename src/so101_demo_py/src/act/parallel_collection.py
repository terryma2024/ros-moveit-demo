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
