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


def test_qualification_contract_is_created_once_before_any_spawn(tmp_path):
    import json as _json

    from so101_demo.act.parallel_collection import create_qualification_contract

    target = tmp_path / "qualification-contract.json"
    path = create_qualification_contract(target, payload={"scenes": 8}, kind="W8")
    document = _json.loads(open(path).read())
    assert document["kind"] == "W8" and document["scenes"] == 8
    assert not (tmp_path / "qualification-contract.json.partial").exists()
    # an existing contract is a refusal, never an overwrite: another run must not inherit its evidence
    with pytest.raises(ValueError, match="QUALIFICATION_CONTRACT_EXISTS"):
        create_qualification_contract(target, payload={"scenes": 8}, kind="W8")
    with pytest.raises(ValueError, match="QUALIFICATION_KIND_INVALID"):
        create_qualification_contract(tmp_path / "other.json", payload={"scenes": 8}, kind="W9")
    with pytest.raises(ValueError, match="QUALIFICATION_CONTRACT_NOT_PERSISTABLE"):
        create_qualification_contract(tmp_path / "absent" / "qualification-contract.json",
                                      payload={"scenes": 8}, kind="W8")


def test_campaign_index_is_atomic_and_records_the_partition(tmp_path):
    import json as _json

    from so101_demo.act.parallel_collection import write_campaign_index

    target = tmp_path / "campaign-index.json"
    path = write_campaign_index(target, waves=(("a", "b"), ("c",)), qualification=False)
    document = _json.loads(open(path).read())
    assert document["scene_count"] == 3 and [wave["wave_index"] for wave in document["waves"]] == [0, 1]
    with pytest.raises(ValueError, match="CAMPAIGN_INDEX_EXISTS"):
        write_campaign_index(target, waves=(("a",),), qualification=False)
    with pytest.raises(ValueError, match="CAMPAIGN_INDEX_INVALID"):
        write_campaign_index(tmp_path / "bad.json", waves=((),), qualification=False)


def test_formal_runs_require_exact_w8_under_a_live_qualification_contract():
    from so101_demo.act.parallel_collection import require_collection_mode

    require_collection_mode(manifest_kind="W1", qualification_mode=True)
    require_collection_mode(manifest_kind="W2", qualification_mode=True)
    require_collection_mode(manifest_kind="W8", qualification_mode=True)
    with pytest.raises(ValueError, match="QUALIFICATION_MANIFEST_KIND_INVALID"):
        require_collection_mode(manifest_kind="train", qualification_mode=True)
    live = {"revoked": False, "scenes": 40}
    require_collection_mode(manifest_kind="W8", qualification_mode=False, contract=live)
    with pytest.raises(ValueError, match="FORMAL_MANIFEST_NOT_EXACT_W8"):
        require_collection_mode(manifest_kind="W1", qualification_mode=False, contract=live)
    for contract in (None, {"revoked": True, "scenes": 40}, {"revoked": False, "scenes": 8}):
        with pytest.raises(ValueError, match="FORMAL_QUALIFICATION"):
            require_collection_mode(manifest_kind="W8", qualification_mode=False, contract=contract)
