"""Wave partitioning is ordered, complete and non-duplicating."""

from pathlib import Path

import pytest

from so101_demo.act.parallel_collection import partition_waves
from paths import PACKAGE_ROOT


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
    manifest = {"scenarios": rows}
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


def test_campaign_config_consumes_the_real_collection_config(tmp_path):
    import yaml

    from so101_demo.act.parallel_collection import campaign_config_from

    package = PACKAGE_ROOT
    document = yaml.safe_load((package / "config/act/parallel_collection.yaml").read_text())
    config = campaign_config_from(document, qualification=False)
    assert config == {"max_wave_size": document["qualification"]["max_wave_size"],
                      "qualification": False}
    assert campaign_config_from(document, qualification=True)["qualification"] is True

    # the posture is part of the contract: no auto-degrade and no business retry
    degraded = {**document, "qualification": {**document["qualification"], "no_auto_degrade": False}}
    with pytest.raises(ValueError, match="COLLECTION_NO_AUTO_DEGRADE_REQUIRED"):
        campaign_config_from(degraded, qualification=False)
    retrying = {**document, "recovery": {**document["recovery"], "business_retry_count": 1}}
    with pytest.raises(ValueError, match="COLLECTION_BUSINESS_RETRY_FORBIDDEN"):
        campaign_config_from(retrying, qualification=False)
    with pytest.raises(ValueError, match="COLLECTION_CONFIG_INVALID"):
        campaign_config_from({"qualification": document["qualification"]}, qualification=False)
    with pytest.raises(ValueError, match="COLLECTION_QUALIFICATION_MODE_INVALID"):
        campaign_config_from(document, qualification="yes")


def test_the_real_wave_size_partitions_a_full_formal_manifest(tmp_path):
    import json as _json
    import yaml

    from so101_demo.act.parallel_collection import (
        FixedActCollectionCampaign, campaign_config_from, partition_waves,
    )

    package = PACKAGE_ROOT
    document = yaml.safe_load((package / "config/act/parallel_collection.yaml").read_text())
    config = campaign_config_from(document, qualification=False)
    scene_ids = tuple(f"act-{index:03d}" for index in range(45))
    assert tuple(map(len, partition_waves(scene_ids, max_wave_size=config["max_wave_size"]))) == (
        20, 20, 5)

    rows = [{"scene_id": scene_id, "split": "train"} for scene_id in scene_ids]
    manifest = {"scenarios": rows}
    campaign = FixedActCollectionCampaign(manifest, config, context=None, root=tmp_path,
                                          collect_port=_CollectPort(), claim=_Claim())
    outcome = campaign.run()
    assert tuple(map(len, outcome["waves"])) == (20, 20, 5)
    assert outcome["scene_count"] == 45 and len(outcome["collected"]) == 45
    assert _json.loads(open(outcome["campaign_index"]).read())["scene_count"] == 45


def test_fixed_workload_refuses_dictionary_lease_before_any_port_call():
    from so101_demo.act.parallel_collection import ActFixedCollectionWorkload

    workload = ActFixedCollectionWorkload(scene_ids=("act-1",))
    for lease in ({"admitted": True}, None):
        with pytest.raises(ValueError, match="ACT_COLLECTION_SCENE_NOT_RESERVED"):
            workload.run_authorized(lease, runtime=None, broker=None,
                boundary=lambda _call: pytest.fail("boundary entered for an invalid lease"),
                teacher_boundary=None, stop_before_motion=None, recorder_stopped=None,
                start_event_id="s", start_event_type="ATTEMPT_STARTED", reset_epoch="reset-1")


def test_workload_has_one_current_constructor():
    from so101_demo.act.parallel_collection import ActFixedCollectionWorkload

    with pytest.raises(TypeError):
        ActFixedCollectionWorkload(object(), runtime=None)


def test_worker_accepts_fixed_collection_workload_only_in_execute_mode():
    from parallel_batch_worker_support import Fake
    from so101_demo.parallel_batch.contracts.common import RunMode
    from so101_demo.parallel_batch.worker import ParallelWorker
    from so101_demo.parallel_batch.worker_parts.contracts import WorkerError
    from so101_demo.act import collection as act_collection
    from so101_demo.act.parallel_collection import ActFixedCollectionWorkload

    workload = ActFixedCollectionWorkload(scene_ids=("p1",))
    ports = Fake(RunMode.EXECUTE).ports()
    ports["workload"] = workload
    ParallelWorker(ports)
    assert not hasattr(act_collection, "ActCollectionWorkload")
    for mode in (RunMode.PLAN_ONLY, RunMode.DRY_RUN):
        ports = Fake(mode).ports()
        ports["workload"] = workload
        with pytest.raises(WorkerError, match="WORKLOAD_PORT_INVALID"):
            ParallelWorker(ports)


WORKERS = tuple(f"w{index:02d}" for index in range(8))


def test_round_zero_plans_are_unchanged_and_carry_no_round_key():
    from so101_demo.act.parallel_collection import plan_campaign_waves
    scenes = tuple(f"scene-{index:03d}" for index in range(45))
    plans = plan_campaign_waves(scenes, WORKERS, plane=None)
    assert [plan["wave_index"] for plan in plans] == [0, 1, 2]
    assert all(set(plan) == {"wave_index", "scene_ids", "assignment"} and plan["assignment"] is None for plan in plans)
    assert plans == plan_campaign_waves(scenes, WORKERS, plane=None, first_wave_index=0, recording_round=0)
    gate = plan_campaign_waves(scenes[:20], WORKERS, plane="gate")
    assert set(gate[0]) == {"wave_index", "scene_ids", "assignment"} and gate[0]["assignment"] is not None


def test_a_retry_round_continues_the_wave_index_and_names_its_round():
    from so101_demo.act.parallel_collection import plan_campaign_waves
    scenes = tuple(f"scene-{index:03d}" for index in range(25))
    plans = plan_campaign_waves(scenes, WORKERS, plane=None, first_wave_index=4, recording_round=2)
    assert [(plan["wave_index"], plan["recording_round"], plan["assignment"]) for plan in plans] == [(4, 2, None), (5, 2, None)]
    assert [len(plan["scene_ids"]) for plan in plans] == [20, 5]


@pytest.mark.parametrize("arguments", [dict(first_wave_index=-1), dict(first_wave_index=True), dict(recording_round=-1),
                                       dict(recording_round=1, plane="gate")])
def test_a_bad_round_or_a_reserved_retry_is_refused(arguments):
    from so101_demo.act.parallel_collection import plan_campaign_waves
    with pytest.raises(ValueError, match="CAMPAIGN_ROUND_INVALID"):
        plan_campaign_waves(tuple(f"scene-{i}" for i in range(8)), WORKERS, **({"plane": None} | arguments))
