"""What a training bundle may contain, and what it must refuse."""

import json

import pytest

from act_export_fixture import ROW_CONTENT
from so101_demo.act.bundle import resolve_committed_episodes, training_rows


def test_normalization_uses_only_train():
    rows = [{"split": "train", "state": [1.]}, {"split": "validation", "state": [100.]}]
    assert training_rows(rows) == [rows[0]]


def test_directory_seal_without_coordinator_commit_is_rejected(tmp_path):
    (tmp_path / "episode-001").mkdir()
    assert resolve_committed_episodes(
        manifest={"episodes": [{"scene_id": "001", "status": "PASSED"}]},
        campaign_index=tmp_path / "campaign-index.json",
    ) == ()


def test_only_verified_committed_episodes_resolve(tmp_path,monkeypatch):
    from act_export_fixture import complete_export_entries
    entry=complete_export_entries(tmp_path,monkeypatch,('001',))[0]
    index = tmp_path / "campaign-index.json"
    index.write_text(json.dumps({"schema_version": 2, "committed_episodes": [entry]}))
    manifest = {"episodes": [{"scene_id": "001", "status": "PASSED"},
                             {"scene_id": "002", "status": "PASSED"},        # no commit
                             {"scene_id": "003", "status": "FAILED"}]}       # business failure
    resolved = resolve_committed_episodes(manifest=manifest, campaign_index=index)
    assert tuple(item["scene_id"] for item in resolved) == ("001",)

    # evidence outside the collection projection never enters a training bundle
    assert training_rows([{"split": "train"}, {"split": "rollout_test"},
                          {"split": "offline_test"}]) == [{"split": "train"}]
    for bad_rows in ("train", [{"state": [1.]}], [None]):
        with pytest.raises(ValueError, match="TRAINING_ROWS_INVALID"):
            training_rows(bad_rows)
    with pytest.raises(ValueError, match="MANIFEST_INVALID"):
        resolve_committed_episodes(manifest={}, campaign_index=index)
    with pytest.raises(ValueError, match="MANIFEST_INVALID"):
        resolve_committed_episodes(manifest={"episodes": [{"status": "PASSED"}]},
                                   campaign_index=index)
    with pytest.raises(ValueError, match="CAMPAIGN_INDEX_INVALID"):
        index.write_text("{not json")
        resolve_committed_episodes(manifest=manifest, campaign_index=index)


def test_conflicting_receipts_and_unverifiable_entries_are_refused(tmp_path,monkeypatch):
    from act_export_fixture import complete_export_entries
    entry=complete_export_entries(tmp_path,monkeypatch,('001',))[0]
    manifest = {"episodes": [{"scene_id": "001", "status": "PASSED"}]}
    index = tmp_path / "campaign-index.json"
    entry['journal_sha256']='b'*64
    index.write_text(json.dumps({"schema_version":2,"committed_episodes": [entry]}))
    with pytest.raises(ValueError, match="EPISODE_RECEIPT_CONFLICT"):
        resolve_committed_episodes(manifest=manifest, campaign_index=index)
    entry['verifier_sha256']='short'
    index.write_text(json.dumps({"schema_version":2,"committed_episodes": [entry]}))
    with pytest.raises(ValueError, match="EPISODE_RECEIPT_INVALID"):
        resolve_committed_episodes(manifest=manifest, campaign_index=index)


def _write_bundle(tmp_path, *, policy_bytes=b"model-bytes", normalization=None, **overrides):
    import hashlib

    (tmp_path / "policy.bin").write_bytes(policy_bytes)
    document = {"schema_version": 1, "kind": "act_bundle",
                "model_source": {"name": "act-v1", "sha256": "a" * 64},
                "dataset_sha256": "b" * 64, "config_sha256": "c" * 64,
                "policy_path": "policy.bin",
                "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
                # `normalization or {...}` would repair the deliberately empty normalisation,
                # so the case would never reach the guard it exists to exercise
                "normalization": ({"split": "train", "mean": [0.0]}
                                  if normalization is None else normalization),
                "action": {"chunk_size": 10, "execution_prefix": 1,
                           "temporal_ensembling": False, "tail_padding_mask": True}}
    document.update(overrides)
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(document))
    return path, document


def test_a_bundle_must_carry_the_policy_it_names(tmp_path):
    from so101_demo.act.bundle import BUNDLE_KEYS, load_bundle

    path, document = _write_bundle(tmp_path)
    loaded = load_bundle(path)
    assert set(loaded) == set(BUNDLE_KEYS)
    # the policy is checked against its bytes, so a swapped file cannot pass as the trained one
    (tmp_path / "policy.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="BUNDLE_POLICY_DIGEST_MISMATCH"):
        load_bundle(path)
    (tmp_path / "policy.bin").unlink()
    with pytest.raises(ValueError, match="BUNDLE_POLICY_MISSING"):
        load_bundle(path)
    with pytest.raises(ValueError, match="BUNDLE_MISSING"):
        load_bundle(tmp_path / "absent.json")


def test_normalization_must_come_from_the_train_split_alone(tmp_path):
    from so101_demo.act.bundle import load_bundle

    path, _ = _write_bundle(tmp_path, normalization={"split": "validation", "mean": [1.0]})
    with pytest.raises(ValueError, match="BUNDLE_NORMALIZATION_NOT_TRAIN_ONLY"):
        load_bundle(path)
    path, _ = _write_bundle(tmp_path, normalization={})
    with pytest.raises(ValueError, match="BUNDLE_NORMALIZATION_NOT_TRAIN_ONLY"):
        load_bundle(path)


def test_a_bundle_document_is_closed_and_its_policy_path_stays_inside(tmp_path):
    from so101_demo.act.bundle import load_bundle

    for overrides in ({"policy_path": "../outside.bin"}, {"policy_path": "/etc/passwd"},
                      {"policy_path": ""}, {"extra": 1}, {"model_source": {"name": "act-v1"}},
                      {"dataset_sha256": "short"}, {"kind": "other"}):
        path, _ = _write_bundle(tmp_path, **overrides)
        with pytest.raises(ValueError, match="BUNDLE_INVALID|BUNDLE_POLICY_PATH_INVALID"):
            load_bundle(path)


def test_the_policy_interface_is_required_before_a_runner_may_use_it(tmp_path):
    from so101_demo.act.bundle import load_policy, require_policy_interface

    path, _ = _write_bundle(tmp_path)

    class Model:
        def __init__(self):
            self.resets = 0

        def infer(self, observation):
            return ((0.0,) * 6,)

        def reset(self):
            self.resets += 1

    model = load_policy(path, loader=lambda bundle: Model())
    assert model.infer({"state": [0.0]}) == ((0.0,) * 6,)
    for bad in (object(), type("NoReset", (), {"infer": lambda self, o: ()})(),
                type("NoInfer", (), {"reset": lambda self: None})(),
                {"infer": lambda o: (), "reset": lambda: None}):
        with pytest.raises(ValueError, match="POLICY_INTERFACE_INVALID"):
            require_policy_interface(bad)
    with pytest.raises(ValueError, match="POLICY_LOADER_REQUIRED"):
        load_policy(path, loader=None)


def _committed(scene_ids=("act-1", "act-2"), *, split="train", status="PASSED", dataset_id=None,fixtures=None):
    return tuple({**({} if fixtures is None else fixtures.get(scene_id,{})),"scene_id": scene_id, "split": split, "status": status,
                  "content": ROW_CONTENT,
                  **({} if dataset_id is None else {"dataset_id": dataset_id})}
                 for scene_id in scene_ids)


def test_the_export_is_written_once_in_the_resolved_order(tmp_path,monkeypatch):
    import hashlib

    from so101_demo.act.bundle import EXPORT_KEYS, export_dataset
    from act_export_fixture import complete_export_entries
    fixtures={entry['scene_id']:entry for entry in complete_export_entries(tmp_path,monkeypatch)}

    output = tmp_path / "dataset"
    document = export_dataset(_committed(fixtures=fixtures), output, source_manifest_sha256="a" * 64,
                              campaign_index_sha256="b" * 64)
    assert set(document) == set(EXPORT_KEYS) | {"manifest_path", "export_sha256"}
    assert document["scene_count"] == 2
    assert [episode["scene_id"] for episode in document["episodes"]] == ["act-1", "act-2"]
    manifest = output / "export-manifest.json"
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == document["export_sha256"]
    for episode in document["episodes"]:
        path = output / "episodes" / f"{episode['scene_id']}.json"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == episode["content_sha256"]
    assert not list(output.rglob("*.partial"))
    # a second export must not append into the first: the dataset cannot grow under a training run
    with pytest.raises(ValueError, match="EXPORT_OUTPUT_EXISTS"):
        export_dataset(_committed(fixtures=fixtures), output, source_manifest_sha256="a" * 64,
                       campaign_index_sha256="b" * 64)


def test_the_export_refuses_what_must_not_enter_training(tmp_path,monkeypatch):
    from so101_demo.act.bundle import export_dataset
    from act_export_fixture import complete_export_entries
    fixtures={entry['scene_id']:entry for entry in complete_export_entries(tmp_path,monkeypatch)}

    cases = ((_committed(()), "a" * 64, "b" * 64, "EXPORT_EMPTY"),
             (_committed(("act-0917a-1",)), "a" * 64, "b" * 64, "EXPORT_STALE_DATASET_ID"),
             (_committed(dataset_id="0917a-run"), "a" * 64, "b" * 64, "EXPORT_STALE_DATASET_ID"),
             (_committed(split="rollout_test"), "a" * 64, "b" * 64, "EXPORT_SPLIT_FORBIDDEN"),
             (_committed(split="functional"), "a" * 64, "b" * 64, "EXPORT_SPLIT_FORBIDDEN"),
             (_committed(status="FAILED"), "a" * 64, "b" * 64, "EXPORT_EPISODE_NOT_PASSED"),
             (_committed(("act-1", "act-1"),fixtures=fixtures), "a" * 64, "b" * 64, "EXPORT_DUPLICATE_SCENE"),
             (({"scene_id": "act-1", "content": {}},), "short", "b" * 64,
              "EXPORT_SOURCE_DIGEST_INVALID"),
             ((({"scene_id": "act-1"},)), "a" * 64, "b" * 64,
              "EXPORT_EPISODE_CONTENT_MISSING"),
             ({"scene_id": "act-1"}, "a" * 64, "b" * 64, "EXPORT_EPISODES_INVALID"))
    for index, (committed, source, index_digest, code) in enumerate(cases):
        target = tmp_path / f"refused-{index}"
        with pytest.raises(ValueError, match=code):
            export_dataset(committed, target, source_manifest_sha256=source,
                           campaign_index_sha256=index_digest)
        assert not target.exists()            # a refused export leaves nothing behind


@pytest.mark.parametrize("override,code", [
    (dict(result_status="FAILED", teacher_task_result="FAIL"), "EXPORT_EPISODE_NOT_PASSED"),      # Teacher FAIL
    (dict(act_data_qc="FAIL", export_eligible=False), "EXPORT_EPISODE_DATA_QC_NOT_PASSED"),       # Teacher PASS, data FAIL
    (dict(act_data_qc="NOT_RUN", export_eligible=False), "EXPORT_EPISODE_DATA_QC_NOT_PASSED"),
    (dict(export_eligible=False), "EXPORT_EPISODE_DATA_QC_NOT_PASSED"),
    (dict(result_schema_version=2), "EXPORT_EPISODE_RESULT_SCHEMA_INVALID"),                              # read-only legacy
    (dict(result_schema_version=None), "EXPORT_EPISODE_RESULT_SCHEMA_INVALID")])
def test_export_needs_a_teacher_pass_and_a_passing_data_qc_on_a_schema_3_result(tmp_path, monkeypatch, override, code):
    from act_export_fixture import complete_export_entries
    scene = "001"
    entry = complete_export_entries(tmp_path, monkeypatch, (scene,), proof_overrides={scene: override})[0]
    index = tmp_path / "campaign-index.json"
    index.write_text(json.dumps({"schema_version": 2, "committed_episodes": [entry]}))
    with pytest.raises(ValueError, match=code):
        resolve_committed_episodes(manifest={"episodes": [{"scene_id": scene, "status": "PASSED"}]},
                                   campaign_index=index)


# ---- schema 3: container task episodes come only from a frozen, non-qualification index ----------------------------------------
# Controlled: the per-task readback (`verify_container_task_registration`) is replaced by the proof the schema 2 export fixture
# builds, over a real synthetic sealed episode directory. The real readback is covered in test_task_commit_readback.py.


def schema3_entries(tmp_path, monkeypatch, scene_ids=('001',), **kwargs):
    from pathlib import Path
    from act_export_fixture import complete_export_entries
    from so101_demo.act import result_store
    legacy_entries = complete_export_entries(tmp_path, monkeypatch, scene_ids, **kwargs)
    legacy = result_store.verify_coordinator_commit
    entries, coordinators = [], {}
    for entry in legacy_entries:
        evidence = entry['collection_evidence']
        location = Path(evidence['result_location'])
        task_id = 'task-'+entry['scene_id']
        registration = location.parent/'journal'/task_id/'collected.json'
        coordinators[str(registration)] = (evidence['coordinator_root'], entry['scene_id'])
        entries.append(dict(kind='ACT_COMMITTED_EPISODE', schema_version=3, scene_id=entry['scene_id'],
            verifier_sha256=entry['verifier_sha256'], task_result_sha256='e'*64,
            collection_evidence=dict(registration=str(registration), owner_root=str(location.parent), task_id=task_id,
                result_location=str(location), scope_path=evidence['scope_path'], inputs_manifest=evidence['inputs_manifest'])))
    calls = []

    def reader(registration, *, scope, inputs_manifest, trust_independent_qc_memo=False):
        coordinator, scene = coordinators[str(registration)]
        evidence = next(item for item in entries if item['scene_id'] == scene)['collection_evidence']
        calls.append(str(registration))
        proof = legacy(Path(coordinator), location=Path(evidence['result_location']), scope=scope, inputs_manifest=inputs_manifest)
        return dict(proof, task_id=evidence['task_id'], scene_id=scene, task_result_sha256='e'*64,
                    location=evidence['result_location'])
    monkeypatch.setattr(result_store, 'verify_container_task_registration', reader)
    return entries, calls


def frozen_index(path, entries, *, qualification=False, kind='act_collection_frozen_index'):
    path.write_text(json.dumps({"schema_version": 1, "kind": kind, "qualification": qualification,
                                "committed_episodes": entries}))
    return path


def test_export_reads_frozen_index_not_directory(tmp_path, monkeypatch):
    from so101_demo.act.bundle import export_dataset
    from so101_demo.act.training import attach_episode_content
    entries, calls = schema3_entries(tmp_path, monkeypatch, ('001', '002'))
    manifest = {"episodes": [{"scene_id": "001", "status": "PASSED"}, {"scene_id": "002", "status": "PASSED"}]}
    # both sealed directories exist, but only the index decides what is committed
    index = frozen_index(tmp_path/'collection-index.json', [entries[0]])
    resolved = resolve_committed_episodes(manifest=manifest, campaign_index=index)
    assert [item['scene_id'] for item in resolved] == ['001'] and resolved[0]['schema_version'] == 3
    assert calls == [entries[0]['collection_evidence']['registration']]
    assert resolve_committed_episodes(manifest=manifest, campaign_index=frozen_index(tmp_path/'empty.json', [])) == ()
    exported = export_dataset(attach_episode_content(resolved, root=tmp_path), tmp_path/'dataset',
                              source_manifest_sha256='a'*64, campaign_index_sha256='b'*64)
    assert exported['scene_count'] == 1


@pytest.mark.parametrize('problem', ['qualification_index', 'not_a_frozen_index'])
def test_qualification_index_never_exports(tmp_path, monkeypatch, problem):
    entries, calls = schema3_entries(tmp_path, monkeypatch)
    index = frozen_index(tmp_path/'collection-index.json', entries, qualification=problem == 'qualification_index',
                         kind='act_collection_frozen_index' if problem == 'qualification_index' else 'campaign')
    with pytest.raises(ValueError, match='EPISODE_FROZEN_INDEX_REQUIRED'):
        resolve_committed_episodes(manifest={"episodes": [{"scene_id": "001", "status": "PASSED"}]}, campaign_index=index)
    assert calls == []


@pytest.mark.parametrize('problem,match', [
    ('verifier_conflict', 'EPISODE_RECEIPT_CONFLICT'), ('task_result_conflict', 'EPISODE_RECEIPT_CONFLICT'),
    ('registration_name', 'EPISODE_COLLECTION_IDENTITY_INVALID'), ('foreign_location', 'EPISODE_COLLECTION_IDENTITY_INVALID'),
    ('extra_evidence', 'EPISODE_COLLECTION_EVIDENCE_REQUIRED'), ('bad_hash', 'EPISODE_RECEIPT_INVALID')])
def test_schema3_entries_are_closed_and_cross_checked(tmp_path, monkeypatch, problem, match):
    entries, _ = schema3_entries(tmp_path, monkeypatch)
    entry = entries[0]
    if problem == 'verifier_conflict':
        entry['verifier_sha256'] = 'b'*64
    elif problem == 'task_result_conflict':
        entry['task_result_sha256'] = 'b'*64
    elif problem == 'registration_name':
        entry['collection_evidence']['registration'] = entry['collection_evidence']['registration'].replace('collected', 'other')
    elif problem == 'foreign_location':
        entry['collection_evidence']['owner_root'] = str(tmp_path/'elsewhere')
    elif problem == 'extra_evidence':
        entry['collection_evidence']['coordinator_root'] = '/x'
    else:
        entry['task_result_sha256'] = 'short'
    index = frozen_index(tmp_path/'collection-index.json', [entry])
    with pytest.raises(ValueError, match=match):
        resolve_committed_episodes(manifest={"episodes": [{"scene_id": "001", "status": "PASSED"}]}, campaign_index=index)


@pytest.mark.parametrize('override,match', [({'export_eligible': False}, 'EXPORT_EPISODE_DATA_QC_NOT_PASSED'),
    ({'act_data_qc': 'FAIL'}, 'EXPORT_EPISODE_DATA_QC_NOT_PASSED'), ({'result_status': 'FAILED'}, 'EXPORT_EPISODE_NOT_PASSED'),
    ({'collection_mode': 'preselected_target_diagnostic'}, 'EPISODE_COLLECTION_IDENTITY_INVALID')])
def test_schema3_keeps_every_export_gate(tmp_path, monkeypatch, override, match):
    entries, _ = schema3_entries(tmp_path, monkeypatch, proof_overrides={'001': override})
    index = frozen_index(tmp_path/'collection-index.json', entries)
    with pytest.raises(ValueError, match=match):
        resolve_committed_episodes(manifest={"episodes": [{"scene_id": "001", "status": "PASSED"}]}, campaign_index=index)


def test_schema2_export_path_unchanged(tmp_path, monkeypatch):
    from act_export_fixture import complete_export_entries
    from so101_demo.act import result_store

    def forbidden(*args, **kwargs):
        raise AssertionError('the schema 2 path must not use the container readback')
    monkeypatch.setattr(result_store, 'verify_container_task_registration', forbidden)
    entry = complete_export_entries(tmp_path, monkeypatch, ('001',))[0]
    index = tmp_path/"campaign-index.json"
    index.write_text(json.dumps({"schema_version": 2, "committed_episodes": [entry]}))
    resolved, = resolve_committed_episodes(manifest={"episodes": [{"scene_id": "001", "status": "PASSED"}]}, campaign_index=index)
    assert resolved['schema_version'] == 2 and resolved['journal_sha256'] == 'd'*64 and resolved['verifier_sha256'] == 'c'*64
    # a schema 2 entry is not accepted by the frozen-index rule, and a frozen index may still carry no schema 2 entries by accident
    frozen = frozen_index(tmp_path/'frozen.json', [entry])
    assert resolve_committed_episodes(manifest={"episodes": [{"scene_id": "001", "status": "PASSED"}]},
                                      campaign_index=frozen)[0]['schema_version'] == 2
