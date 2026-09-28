"""Task 11A: wave partitioning is ordered, complete and non-duplicating."""

import pytest

from so101_demo.act.parallel_collection import partition_waves


def test_manifest_order_is_partitioned_without_duplication():
    scene_ids = tuple(f"scene-{index:03d}" for index in range(45))
    waves = partition_waves(scene_ids, max_wave_size=20)
    assert tuple(map(len, waves)) == (20, 20, 5)
    assert tuple(item for wave in waves for item in wave) == scene_ids


def test_wave_partition_refuses_duplicates_emptiness_and_a_bad_size():
    with pytest.raises(ValueError, match="WAVE_SCENE_DUPLICATE"):
        partition_waves(("scene-1", "scene-2", "scene-1"))
    with pytest.raises(ValueError, match="WAVE_MANIFEST_EMPTY"):
        partition_waves(())
    for bad in (0, -1, "20", 2.0, True):
        with pytest.raises(ValueError, match="WAVE_SIZE_INVALID"):
            partition_waves(("scene-1",), max_wave_size=bad)
    with pytest.raises(ValueError, match="WAVE_MANIFEST_INVALID"):
        partition_waves(("scene-1", ""))
    # an exact multiple of the wave size yields no empty trailing wave
    assert tuple(map(len, partition_waves(tuple(f"s{index}" for index in range(40)),
                                          max_wave_size=20))) == (20, 20)
    assert partition_waves(("only-scene",), max_wave_size=20) == (("only-scene",),)
