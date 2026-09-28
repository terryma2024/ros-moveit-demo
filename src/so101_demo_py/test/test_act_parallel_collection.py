"""Task 11A: wave partitioning is ordered, complete and non-duplicating."""

from pathlib import Path

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


def _result(scene_id="act-1", **overrides):
    record = {"scene_id": scene_id, "status": "PASSED", "qc": "PASS", "done": True,
              "interventions": 0, "coordinator_committed": True, "reset_epoch": 4}
    record.update(overrides)
    return record


def test_results_are_published_once_and_re_entry_is_idempotent(tmp_path):
    from so101_demo.adapters.act.parallel_collection_results import ActCollectionResultStore

    store = ActCollectionResultStore(tmp_path)
    first = store.publish(_result())
    assert Path(first["path"]).is_file() and len(first["sha256"]) == 64
    assert not (tmp_path / "results" / "act-1.json.partial").exists()
    # re-entering a wave publishes the identical document again without changing history
    again = store.publish(_result())
    assert again == first
    # a different document for a scene that already has a result is refused
    with pytest.raises(ValueError, match="SCENE_TERMINAL_STATE_IMMUTABLE"):
        store.publish(_result(status="FAILED", qc="FAIL"))
    assert store.read("act-1")["status"] == "PASSED"
    with pytest.raises(ValueError, match="RESULT_MISSING"):
        store.read("act-absent")
    for bad in ({"scene_id": "act-2"}, _result("act-3", status="MAYBE")):
        with pytest.raises(ValueError, match="RESULT_INVALID"):
            store.publish(bad)
    with pytest.raises(ValueError, match="RESULT_SCENE_ID_INVALID"):
        store.publish(_result("../escape"))
    with pytest.raises(ValueError, match="RESULT_ROOT_INVALID"):
        ActCollectionResultStore(tmp_path / "absent")


def test_result_verifier_re_reads_the_bytes_rather_than_trusting_the_digest(tmp_path):
    from so101_demo.adapters.act.parallel_collection_results import (
        ActCollectionResultStore, ActCollectionResultVerifier,
    )

    store = ActCollectionResultStore(tmp_path)
    entry = store.publish(_result())
    verifier = ActCollectionResultVerifier(store)
    assert verifier.verify(entry)["scene_id"] == "act-1"
    # tampering with the published bytes is detected
    Path(entry["path"]).write_text('{"scene_id": "act-1", "status": "PASSED"}')
    with pytest.raises(ValueError, match="RESULT_DIGEST_MISMATCH"):
        verifier.verify(entry)
    with pytest.raises(ValueError, match="RESULT_ENTRY_INVALID"):
        verifier.verify({"path": entry["path"]})
    Path(entry["path"]).unlink()
    with pytest.raises(ValueError, match="RESULT_MISSING"):
        verifier.verify(entry)


class _Claim:
    def __init__(self):
        self.releases = []

    def release(self, document):
        self.releases.append(document)


class _CollectPort:
    def __init__(self, *, fail_at=None):
        self.calls = []
        self._fail_at = fail_at

    def collect(self, scene_id, context, wave):
        self.calls.append((scene_id, wave["wave_index"]))
        if scene_id == self._fail_at:
            raise RuntimeError("SEARCH_AMBIGUOUS")
        return {"scene_id": scene_id, "status": "PASSED", "qc": "PASS", "done": True,
                "interventions": 0, "coordinator_committed": True, "reset_epoch": 1}


def _campaign_fixture(tmp_path, *, scene_count=5, max_wave_size=2, terminal=(), fail_at=None):
    import json as _json

    from so101_demo.act.parallel_collection import FixedActCollectionCampaign

    rows = [{"scene_id": f"act-{index}", "split": "train"} for index in range(scene_count)]
    manifest = {"kind": "W8", "scenarios": rows,
                "qualification_contract": {"revoked": False, "scenes": 40}}
    store = __import__("so101_demo.adapters.act.parallel_collection_results",
                       fromlist=["ActCollectionResultStore"]).ActCollectionResultStore(tmp_path)
    for scene_id in terminal:
        store.publish({"scene_id": scene_id, "status": "PASSED", "qc": "PASS", "done": True,
                       "interventions": 0, "coordinator_committed": True, "reset_epoch": 1})
    config = {"max_wave_size": max_wave_size, "qualification": False}
    port, claim = _CollectPort(fail_at=fail_at), _Claim()
    campaign = FixedActCollectionCampaign(manifest, config, context=None, root=tmp_path,
                                          collect_port=port, claim=claim, store=store)
    return campaign, port, claim, store, _json


def test_campaign_runs_fixed_waves_and_holds_the_claim_until_the_last_scene(tmp_path):
    campaign, port, claim, store, _json = _campaign_fixture(tmp_path)
    outcome = campaign.run()
    assert outcome["waves"] == [["act-0", "act-1"], ["act-2", "act-3"], ["act-4"]]
    assert [call[0] for call in port.calls] == ["act-0", "act-1", "act-2", "act-3", "act-4"]
    assert outcome["collected"] == ["act-0", "act-1", "act-2", "act-3", "act-4"]
    assert len(claim.releases) == 1 and len(claim.releases[0]["terminal"]) == 5
    assert _json.loads(open(outcome["campaign_index"]).read())["scene_count"] == 5
    for scene_id in campaign.scene_ids:
        assert store.read(scene_id)["status"] == "PASSED"


def test_campaign_skips_terminal_scenes_and_keeps_the_claim_on_failure(tmp_path):
    campaign, port, claim, _store, _json = _campaign_fixture(tmp_path, terminal=("act-1",))
    outcome = campaign.run()
    assert outcome["already_terminal"] == ["act-1"]
    assert "act-1" not in [call[0] for call in port.calls]      # never collected twice
    assert len(claim.releases) == 1

    (tmp_path / "failing").mkdir(exist_ok=True)      # the store refuses a root that does not exist
    failing, port, claim, _store, _json = _campaign_fixture(tmp_path / "failing", fail_at="act-2")
    with pytest.raises(RuntimeError, match="SEARCH_AMBIGUOUS"):
        failing.run()
    # an unresolved campaign must not hand the stack on: no release, and the earlier scenes stay sealed
    assert claim.releases == []
    assert port.calls[-1][0] == "act-2"
